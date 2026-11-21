# SPDX-FileCopyrightText: 2026 BOTProT800
# SPDX-License-Identifier: MIT

"""Ventana que enseña una textura ya decodificada.

Tk 8.6 sabe cargar PNG desde memoria, así que la imagen nunca toca el disco:
el decodificador entrega píxeles, aquí se empaquetan en PNG y se los come
``PhotoImage``. El zoom usa ``zoom`` y ``subsample``, que son enteros, por eso
los pasos son potencias de dos en lugar de un porcentaje libre.
"""

from __future__ import annotations

import base64
import tkinter as tk
from tkinter import ttk

from .formats.dds import DecodedImage, to_png
from .i18n import t

#: Lado máximo que se decodifica al abrir. Por encima de esto la vista previa
#: tarda más de lo que aporta, y el detalle completo está a un botón.
PREVIEW_MAX_SIDE = 512

#: Tope del detalle completo. El juego trae texturas de 4096 píxeles de lado:
#: enteras son más de diez segundos de decodificación y cientos de megas entre
#: el PNG intermedio y la copia de Tk, para una ventana que no puede enseñarlas.
FULL_DETAIL_MAX_SIDE = 2048

#: Modo que entiende `to_png` y clave de su etiqueta en el desplegable. La
#: ventana trabaja con el modo; la etiqueta solo se usa para enseñarlo.
VIEW_MODES = {
    "color": "preview.mode_color",
    "opaque": "preview.mode_opaque",
    "alpha": "preview.mode_alpha",
}

#: Pasos de zoom como (ampliar, reducir), los dos enteros que acepta Tk.
ZOOM_STEPS = ((1, 8), (1, 4), (1, 2), (1, 1), (2, 1), (4, 1))
#: Tope de píxeles de la imagen ampliada: Tk guarda cuatro bytes por píxel.
ZOOM_PIXEL_LIMIT = 4_000_000

BACKGROUND = "#0f1216"


class ImageWindow(tk.Toplevel):
    """Visor de una textura. Se reutiliza para las siguientes que se abran."""

    def __init__(self, master: tk.Misc, *, on_full_detail=None) -> None:
        super().__init__(master)
        self.geometry("900x720")
        self.minsize(420, 320)
        self.configure(bg="#111317")
        self.on_full_detail = on_full_detail

        self.image: DecodedImage | None = None
        self.name = ""
        #: La imagen sigue reducida aunque ya se pidió el detalle completo.
        self.capped = False
        self.photo: tk.PhotoImage | None = None
        #: Imagen a tamaño real ya cargada en Tk, y de qué textura y modo salió.
        self.base_photo: tk.PhotoImage | None = None
        self.base_source: tuple[DecodedImage, str] | None = None
        self.zoom_index = 3
        self.fitted = True
        #: Modo de `VIEW_MODES` elegido; `mode_var` solo guarda su etiqueta.
        self.mode = "color"

        self.mode_var = tk.StringVar()
        self.info_var = tk.StringVar(value="")
        self.zoom_var = tk.StringVar(value="100%")

        # El tema clam pinta el desplegable de solo lectura con fondo claro, y
        # con el texto claro de la aplicación no se lee. El estilo es propio
        # de esta ventana para no cambiar el aspecto de la principal.
        style = ttk.Style(self)
        style.configure("Preview.TCombobox", padding=5)
        style.map(
            "Preview.TCombobox",
            fieldbackground=[("disabled", "#1a1e24"), ("readonly", BACKGROUND)],
            foreground=[("disabled", "#6b7280"), ("readonly", "#edf0f5")],
            selectbackground=[("readonly", BACKGROUND)],
            selectforeground=[("readonly", "#edf0f5")],
        )

        bar = ttk.Frame(self, style="Panel.TFrame", padding=(10, 8))
        bar.pack(fill="x")
        self.view_label = ttk.Label(bar, background="#1a1e24", foreground="#9299a6")
        self.view_label.pack(side="left")
        self.mode_box = ttk.Combobox(
            bar,
            textvariable=self.mode_var,
            state="readonly",
            width=10,
            style="Preview.TCombobox",
        )
        self.mode_box.pack(side="left", padx=(6, 14))
        self.mode_box.bind("<<ComboboxSelected>>", self._on_mode_selected)

        ttk.Button(bar, text="−", width=3, command=lambda: self.step_zoom(-1)).pack(side="left")
        ttk.Label(bar, textvariable=self.zoom_var, background="#1a1e24", width=6).pack(side="left", padx=4)
        ttk.Button(bar, text="+", width=3, command=lambda: self.step_zoom(1)).pack(side="left")
        self.fit_button = ttk.Button(bar, command=self.fit)
        self.fit_button.pack(side="left", padx=(8, 0))
        self.detail_button = ttk.Button(bar, command=self._request_detail)
        self.detail_button.pack(side="left", padx=(8, 0))

        body = ttk.Frame(self, style="Panel.TFrame")
        body.pack(fill="both", expand=True, padx=10, pady=(0, 6))
        self.canvas = tk.Canvas(body, bg=BACKGROUND, highlightthickness=0, bd=0)
        vertical = ttk.Scrollbar(body, orient="vertical", command=self.canvas.yview)
        horizontal = ttk.Scrollbar(body, orient="horizontal", command=self.canvas.xview)
        self.canvas.configure(yscrollcommand=vertical.set, xscrollcommand=horizontal.set)
        self.canvas.grid(row=0, column=0, sticky="nsew")
        vertical.grid(row=0, column=1, sticky="ns")
        horizontal.grid(row=1, column=0, sticky="ew")
        body.rowconfigure(0, weight=1)
        body.columnconfigure(0, weight=1)

        ttk.Label(self, textvariable=self.info_var, style="Muted.TLabel", padding=(12, 0, 12, 10)).pack(
            anchor="w"
        )

        self.bind("<Escape>", lambda _event: self.withdraw())
        self.protocol("WM_DELETE_WINDOW", self.withdraw)
        self.canvas.bind("<Configure>", self._on_resize)
        self.apply_language()

    def apply_language(self) -> None:
        """Reasigna los textos al idioma activo sin perder el modo elegido."""
        self._update_title()
        self.view_label.configure(text=t("preview.view"))
        self.fit_button.configure(text=t("preview.fit"))
        self.detail_button.configure(text=t("preview.full_detail"))
        self.mode_box.configure(values=[t(key) for key in VIEW_MODES.values()])
        self._set_mode(self.mode)
        if self.image is not None:
            self.info_var.set(self._describe(self.image))

    def _update_title(self) -> None:
        self.title(t("preview.title_named", name=self.name) if self.name else t("preview.title"))

    def _set_mode(self, mode: str) -> None:
        self.mode = mode if mode in VIEW_MODES else "color"
        self.mode_var.set(t(VIEW_MODES[self.mode]))

    def _on_mode_selected(self, _event=None) -> None:
        index = self.mode_box.current()
        if 0 <= index < len(VIEW_MODES):
            self.mode = tuple(VIEW_MODES)[index]
        self.render()

    def show(self, name: str, image: DecodedImage, *, full_detail: bool = False) -> None:
        """Carga una textura y deja la ventana al frente.

        ``full_detail`` avisa de que ya se pidió el máximo: aunque la imagen
        siga reducida por el tope de la vista previa, no se vuelve a ofrecer.
        """
        same_texture = self.image is not None and name == self.name
        shown_width = self._shown_width() if same_texture else None
        self.name = name
        self.image = image
        self.capped = full_detail and image.reduced
        self._update_title()
        if image.alpha is None:
            self._set_mode("color")
        self.mode_box.configure(state="readonly" if image.alpha is not None else "disabled")
        self.detail_button.configure(
            state="normal" if image.reduced and not full_detail else "disabled"
        )
        self.deiconify()
        self.lift()
        # Sin esto el lienzo todavía mide un píxel la primera vez y el ajuste
        # elegiría el zoom más pequeño.
        self.update_idletasks()
        if shown_width is None or self.fitted:
            self.fit()
        else:
            # La misma textura con más detalle trae más píxeles: se busca el
            # paso que la deja del tamaño que ya tenía en pantalla, en lugar
            # de conservar un factor que la haría crecer.
            self.zoom_index = self._closest_step(shown_width)
            self.render()

    def _shown_width(self) -> float:
        enlarge, reduce = ZOOM_STEPS[self.zoom_index]
        return self.image.width * enlarge / reduce

    def _closest_step(self, shown_width: float) -> int:
        candidates = [index for index in range(len(ZOOM_STEPS)) if self._affordable(index)]
        return min(
            candidates or [ZOOM_STEPS.index((1, 1))],
            key=lambda index: abs(
                self.image.width * ZOOM_STEPS[index][0] / ZOOM_STEPS[index][1] - shown_width
            ),
        )

    def _on_resize(self, _event=None) -> None:
        if self.fitted:
            self.fit()

    def _request_detail(self) -> None:
        if self.on_full_detail and self.image is not None:
            self.detail_button.configure(state="disabled")
            self.on_full_detail(self.name)

    def detail_failed(self) -> None:
        """La recarga con más detalle no llegó: el botón vuelve a ofrecerse."""
        if self.image is not None and self.image.reduced and not self.capped:
            self.detail_button.configure(state="normal")

    def _affordable(self, index: int) -> bool:
        """Ampliar multiplica por el cuadrado la memoria que reserva Tk.

        El tamaño real y las reducciones siempre valen: esa imagen ya está
        cargada, y lo que se limita es la copia ampliada.
        """
        if self.image is None:
            return False
        enlarge, _reduce = ZOOM_STEPS[index]
        if enlarge == 1:
            return True
        return self.image.width * self.image.height * enlarge * enlarge <= ZOOM_PIXEL_LIMIT

    def step_zoom(self, direction: int) -> None:
        target = max(0, min(len(ZOOM_STEPS) - 1, self.zoom_index + direction))
        if target == self.zoom_index or not self._affordable(target):
            return
        self.fitted = False
        self.zoom_index = target
        self.render()

    def fit(self) -> None:
        """Elige el paso de zoom más grande que quepa en el lienzo."""
        if self.image is None:
            return
        self.fitted = True
        width = max(self.canvas.winfo_width(), 1)
        height = max(self.canvas.winfo_height(), 1)
        chosen = 0
        for index, (enlarge, reduce) in enumerate(ZOOM_STEPS):
            shown_width = self.image.width * enlarge // reduce
            shown_height = self.image.height * enlarge // reduce
            if shown_width <= width and shown_height <= height and self._affordable(index):
                chosen = index
        self.zoom_index = chosen
        self.render()

    def render(self) -> None:
        if self.image is None:
            return
        image = self.image
        mode = self.mode
        if mode == "alpha" and image.alpha is None:
            mode = "color"
        # Empaquetar el PNG y cargarlo en Tk es lo caro (casi un segundo a
        # 2048 píxeles), así que solo se repite al cambiar de textura o de
        # modo; el zoom parte de la imagen ya cargada.
        source = self.base_source
        if source is None or source[0] is not image or source[1] != mode:
            self.base_photo = tk.PhotoImage(data=base64.b64encode(to_png(image, mode=mode)))
            self.base_source = (image, mode)
        photo = self.base_photo

        if not self._affordable(self.zoom_index):
            self.zoom_index = ZOOM_STEPS.index((1, 1))
        enlarge, reduce = ZOOM_STEPS[self.zoom_index]
        if reduce > 1:
            photo = photo.subsample(reduce, reduce)
        elif enlarge > 1:
            photo = photo.zoom(enlarge, enlarge)

        self.photo = photo
        self.canvas.delete("all")
        width, height = photo.width(), photo.height()
        canvas_width = max(self.canvas.winfo_width(), width)
        canvas_height = max(self.canvas.winfo_height(), height)
        self.canvas.create_image(canvas_width // 2, canvas_height // 2, image=photo)
        self.canvas.configure(scrollregion=(0, 0, canvas_width, canvas_height))
        self.zoom_var.set(f"{100 * enlarge // reduce}%")
        self.info_var.set(self._describe(image))

    def _describe(self, image: DecodedImage) -> str:
        header = image.header
        parts = [
            header.label,
            f"{header.width}x{header.height}",
            t("preview.mipmaps", count=header.mipmaps) if header.mipmaps > 1 else t("preview.no_mipmaps"),
            t("preview.with_alpha") if image.alpha is not None else t("preview.opaque"),
        ]
        if image.reduced:
            size = {"width": image.width, "height": image.height}
            if image.level:
                detail = t("preview.reduced_mipmap", level=image.level, **size)
            else:
                detail = t("preview.reduced", **size)
            if self.capped:
                detail = t("preview.capped", detail=detail)
            parts.append(detail)
        else:
            parts.append(t("preview.complete"))
        return "  •  ".join(parts)
