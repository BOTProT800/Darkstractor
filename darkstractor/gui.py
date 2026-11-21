# SPDX-FileCopyrightText: 2026 BOTProT800
# SPDX-License-Identifier: MIT

from __future__ import annotations

import os
import queue
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from .errors import CancelledError, DarkstractorError
from .formats import dds
from .i18n import SUPPORTED_LANGUAGES, get_language, resolve_language, set_language, t
from .models import Archive, Entry
from .preview import FULL_DETAIL_MAX_SIDE, PREVIEW_MAX_SIDE, ImageWindow
from .settings import COLLISION_POLICIES, load_settings, resolve_collision, save_settings
from .service import (
    ensure_free_space,
    estimate_output_bytes,
    estimate_source_bytes,
    extract_entries,
    human_size,
    kind_label,
    list_obp_members,
    looks_like_game,
    read_member_bytes,
    scan_game,
)

DEFAULT_GAME = Path(r"C:\Program Files (x86)\Steam\steamapps\common\Darksiders II Deathinitive Edition")

#: Clave de la etiqueta de cada política en el desplegable "Si existe".
COLLISION_LABELS = {
    "rename": "gui.collision_rename",
    "skip": "gui.collision_skip",
    "overwrite": "gui.collision_overwrite",
}

#: Tipos de recurso que la vista previa sabe dibujar.
VIEWABLE_KINDS = frozenset({"obp-dds"})


class DarkstractorApp(tk.Tk):
    def __init__(self, language: str | None = None) -> None:
        super().__init__()
        self.title("Darkstractor — Darksiders II Deathinitive Edition")
        self.geometry("1180x760")
        self.minsize(940, 620)
        self.configure(bg="#111317")

        self.messages: queue.Queue[tuple[str, object]] = queue.Queue()
        self.cancel_event = threading.Event()
        self.worker: threading.Thread | None = None
        self.progress_lock = threading.Lock()
        self.progress_done = 0
        self.progress_total = 0
        self.archives: list[Archive] = []
        self.current_archive: Archive | None = None
        self.current_entries: list[Entry] = []
        self.inner_parent: Entry | None = None
        self.visible_entries: list[Entry] = []
        self.preview_window: ImageWindow | None = None
        self.preview_thread: threading.Thread | None = None
        #: Última textura abierta y sus bytes, para no releerla al pedir detalle.
        self.preview_entry: Entry | None = None
        self.preview_data: bytes | None = None

        saved = load_settings()
        # La CLI ya resolvió --lang antes de llegar aquí; sin ella manda lo
        # guardado, y sin nada guardado, el inglés.
        set_language(resolve_language(language if language is not None else saved.get("language")))
        self.game_var = tk.StringVar(
            value=str(saved.get("game") or (DEFAULT_GAME if DEFAULT_GAME.exists() else Path.cwd()))
        )
        self.output_var = tk.StringVar(value=str(saved.get("output") or Path.cwd() / "extraccion"))
        self.filter_var = tk.StringVar()
        self.auto_unpack_var = tk.BooleanVar(value=bool(saved.get("auto_unpack", True)))
        #: La aplicación trabaja con la política; `collision_var` solo guarda la
        #: etiqueta que se ve, que cambia con el idioma.
        self.collision_policy = resolve_collision(saved.get("collision"))
        self.collision_var = tk.StringVar()
        self.language_var = tk.StringVar()
        self.status_var = tk.StringVar()
        self.summary_var = tk.StringVar()
        # El estado y el resumen se guardan como clave más parámetros para
        # poder repintarlos en otro idioma sin dejar texto mezclado.
        self._status: tuple[str, dict[str, object]] = ("status.ready", {})
        self._summary: tuple[str, dict[str, object]] = ("summary.not_scanned", {})

        self._configure_styles()
        self._build_ui()
        self._apply_language()
        self.filter_var.trace_add("write", lambda *_: self.after(180, self._refresh_entries))
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.after(100, self._poll_messages)
        # Analizar a ciegas recibía al usuario con un diálogo de error cuando el
        # juego no estaba en la ruta por defecto.
        if looks_like_game(Path(self.game_var.get())):
            self.after(250, self.scan)
        else:
            self._set_status("status.game_not_found")

    def _configure_styles(self) -> None:
        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure("TFrame", background="#111317")
        style.configure("Panel.TFrame", background="#1a1e24")
        style.configure("TLabel", background="#111317", foreground="#e7eaf0", font=("Segoe UI", 10))
        style.configure("Title.TLabel", font=("Segoe UI Semibold", 22), foreground="#f2f4f8")
        style.configure("Muted.TLabel", foreground="#9299a6")
        style.configure("Accent.TButton", font=("Segoe UI Semibold", 10), padding=(16, 9), background="#8b5cf6", foreground="white")
        style.map("Accent.TButton", background=[("active", "#9d72f8"), ("disabled", "#3d344f")])
        style.configure("TButton", font=("Segoe UI", 10), padding=(12, 8), background="#292f38", foreground="#eef0f5")
        style.map("TButton", background=[("active", "#343c48")])
        style.configure("TEntry", fieldbackground="#0f1216", foreground="#edf0f5", insertcolor="white", padding=7)
        style.configure("TCombobox", fieldbackground="#0f1216", foreground="#edf0f5", padding=5)
        # El tema clam pinta el desplegable de solo lectura con fondo claro, y
        # con el texto claro de la aplicación no se lee. Los dos desplegables
        # de la ventana (idioma y duplicados) usan este estilo, como el de la
        # vista previa usa el suyo.
        style.configure("Selector.TCombobox", padding=4)
        style.map(
            "Selector.TCombobox",
            fieldbackground=[("readonly", "#0f1216")],
            foreground=[("readonly", "#edf0f5")],
            selectbackground=[("readonly", "#0f1216")],
            selectforeground=[("readonly", "#edf0f5")],
        )
        style.configure("TCheckbutton", background="#111317", foreground="#d7dbe2")
        style.map("TCheckbutton", background=[("active", "#111317")])
        style.configure("Treeview", background="#171b20", fieldbackground="#171b20", foreground="#dfe3ea", rowheight=28, borderwidth=0)
        style.map("Treeview", background=[("selected", "#6d4cc2")], foreground=[("selected", "white")])
        style.configure("Treeview.Heading", background="#242a33", foreground="#cdd2dc", font=("Segoe UI Semibold", 9), relief="flat")
        style.map("Treeview.Heading", background=[("active", "#303744")])
        style.configure("TNotebook", background="#111317", borderwidth=0)
        style.configure("TNotebook.Tab", background="#1a1e24", foreground="#aeb5c0", padding=(14, 8))
        style.map("TNotebook.Tab", background=[("selected", "#292f38")], foreground=[("selected", "white")])
        style.configure("Horizontal.TProgressbar", troughcolor="#242a33", background="#8b5cf6", borderwidth=0)

    def _build_ui(self) -> None:
        """Monta los widgets sin texto: lo pone `_apply_language`, en un solo sitio.

        La ventana va en una rejilla y no apilada: con `pack`, la lista pedía
        su alto entero y lo que venía detrás (opciones, estado y registro) se
        quedaba sin sitio en el tamaño mínimo. Ahora la cabecera, las rutas,
        las opciones y el estado nunca encogen, y la lista y el registro se
        reparten el alto que quede, tres a uno.
        """
        self.columnconfigure(0, weight=1)
        self.rowconfigure(2, weight=3)
        self.rowconfigure(5, weight=1)

        header = ttk.Frame(self, padding=(22, 18, 22, 10))
        header.grid(row=0, column=0, sticky="ew")
        ttk.Label(header, text="DARKSTRACTOR", style="Title.TLabel").grid(row=0, column=0, sticky="w")
        self.subtitle_label = ttk.Label(header, style="Muted.TLabel")
        self.subtitle_label.grid(row=1, column=0, sticky="w", pady=(2, 0))
        language_bar = ttk.Frame(header)
        language_bar.grid(row=0, column=1, sticky="e")
        self.language_label = ttk.Label(language_bar, style="Muted.TLabel")
        self.language_label.pack(side="left", padx=(0, 6))
        # Los nombres de los idiomas no se traducen nunca: cada uno va en su lengua.
        self.language_box = ttk.Combobox(
            language_bar,
            textvariable=self.language_var,
            values=tuple(SUPPORTED_LANGUAGES.values()),
            state="readonly",
            width=9,
            style="Selector.TCombobox",
        )
        self.language_box.pack(side="left")
        self.language_box.bind("<<ComboboxSelected>>", self._on_language_selected)
        ttk.Label(header, textvariable=self.summary_var, style="Muted.TLabel").grid(row=1, column=1, sticky="e")
        header.columnconfigure(1, weight=1)

        paths = ttk.Frame(self, style="Panel.TFrame", padding=14)
        paths.grid(row=1, column=0, sticky="ew", padx=22, pady=(0, 12))
        self.installation_label = ttk.Label(paths, background="#1a1e24")
        self.installation_label.grid(row=0, column=0, sticky="w")
        ttk.Entry(paths, textvariable=self.game_var).grid(row=1, column=0, sticky="ew", padx=(0, 8), pady=(4, 0))
        self.game_browse_button = ttk.Button(paths, command=self._choose_game)
        self.game_browse_button.grid(row=1, column=1, padx=(0, 12), pady=(4, 0))
        self.output_label = ttk.Label(paths, background="#1a1e24")
        self.output_label.grid(row=0, column=2, sticky="w")
        ttk.Entry(paths, textvariable=self.output_var).grid(row=1, column=2, sticky="ew", padx=(0, 8), pady=(4, 0))
        self.output_browse_button = ttk.Button(paths, command=self._choose_output)
        self.output_browse_button.grid(row=1, column=3, padx=(0, 12), pady=(4, 0))
        self.scan_button = ttk.Button(paths, style="Accent.TButton", command=self.scan)
        self.scan_button.grid(row=1, column=4, pady=(4, 0))
        paths.columnconfigure(0, weight=1)
        paths.columnconfigure(2, weight=1)

        pane = ttk.Panedwindow(self, orient="horizontal")
        pane.grid(row=2, column=0, sticky="nsew", padx=22)

        left = ttk.Frame(pane, style="Panel.TFrame", padding=10)
        right = ttk.Frame(pane, style="Panel.TFrame", padding=10)
        pane.add(left, weight=2)
        pane.add(right, weight=5)

        self.containers_label = ttk.Label(left, background="#1a1e24", foreground="#aeb5c0", font=("Segoe UI Semibold", 9))
        self.containers_label.pack(anchor="w", pady=(0, 8))
        self.archive_tree = ttk.Treeview(left, columns=("type", "count", "size"), show="tree headings", selectmode="browse")
        self.archive_tree.column("#0", width=150)
        self.archive_tree.column("type", width=60, anchor="center")
        self.archive_tree.column("count", width=65, anchor="e")
        self.archive_tree.column("size", width=82, anchor="e")
        self.archive_tree.pack(fill="both", expand=True)
        self.archive_tree.bind("<<TreeviewSelect>>", self._select_archive)

        top_right = ttk.Frame(right, style="Panel.TFrame")
        top_right.pack(fill="x", pady=(0, 8))
        self.files_label = ttk.Label(top_right, background="#1a1e24", foreground="#aeb5c0", font=("Segoe UI Semibold", 9))
        self.files_label.pack(side="left")
        self.back_button = ttk.Button(top_right, command=self.back_from_package, state="disabled")
        self.back_button.pack(side="left", padx=(12, 6))
        self.explore_button = ttk.Button(top_right, command=self.explore_selected)
        self.explore_button.pack(side="left")
        self.preview_button = ttk.Button(top_right, command=self.view_selected)
        self.preview_button.pack(side="left", padx=(6, 0))
        # La etiqueta y el campo van juntos, y dentro el campo se empaqueta el
        # último: si la fila no cabe, encoge el campo en lugar de desaparecer
        # la etiqueta, que es lo que pasaba en el ancho mínimo.
        filter_box = ttk.Frame(top_right, style="Panel.TFrame")
        filter_box.pack(side="right", padx=(12, 0))
        self.filter_label = ttk.Label(filter_box, background="#1a1e24", foreground="#9299a6")
        self.filter_label.pack(side="left", padx=(0, 6))
        ttk.Entry(filter_box, textvariable=self.filter_var, width=30).pack(side="left", fill="x", expand=True)

        entry_frame = ttk.Frame(right, style="Panel.TFrame")
        entry_frame.pack(fill="both", expand=True)
        self.entry_tree = ttk.Treeview(entry_frame, columns=("kind", "size", "offset"), show="headings", selectmode="extended")
        self.entry_tree["displaycolumns"] = ("kind", "size", "offset")
        self.entry_tree.column("kind", width=95)
        self.entry_tree.column("size", width=100, anchor="e")
        self.entry_tree.column("offset", width=115, anchor="e")
        # Treeview necesita #0 visible para mostrar la ruta.
        self.entry_tree.configure(show="tree headings")
        self.entry_tree.column("#0", width=470)
        scrollbar = ttk.Scrollbar(entry_frame, orient="vertical", command=self.entry_tree.yview)
        self.entry_tree.configure(yscrollcommand=scrollbar.set)
        entry_frame.columnconfigure(0, weight=1)
        entry_frame.rowconfigure(0, weight=1)
        self.entry_tree.grid(row=0, column=0, sticky="nsew")
        scrollbar.grid(row=0, column=1, sticky="ns")
        self.entry_tree.bind("<Double-1>", lambda _event: self.activate_selected())

        options = ttk.Frame(self, padding=(22, 12, 22, 8))
        options.grid(row=3, column=0, sticky="ew")
        self.auto_unpack_check = ttk.Checkbutton(options, variable=self.auto_unpack_var)
        self.auto_unpack_check.pack(side="left")
        self.if_exists_label = ttk.Label(options)
        self.if_exists_label.pack(side="left", padx=(8, 0))
        self.collision_box = ttk.Combobox(
            options,
            textvariable=self.collision_var,
            state="readonly",
            width=13,
            style="Selector.TCombobox",
        )
        self.collision_box.pack(side="left", padx=(4, 0))
        self.collision_box.bind("<<ComboboxSelected>>", self._on_collision_selected)
        self.extract_selected_button = ttk.Button(options, style="Accent.TButton", command=self.extract_selected)
        self.extract_selected_button.pack(side="right")
        self.extract_all_button = ttk.Button(options, command=self.extract_visible)
        self.extract_all_button.pack(side="right", padx=(0, 8))
        self.cancel_button = ttk.Button(options, command=self.cancel, state="disabled")
        self.cancel_button.pack(side="right", padx=(0, 8))

        bottom = ttk.Frame(self, padding=(22, 0, 22, 18))
        bottom.grid(row=4, column=0, sticky="ew")
        self.progress = ttk.Progressbar(bottom, mode="indeterminate")
        self.progress.pack(fill="x", pady=(0, 7))
        ttk.Label(bottom, textvariable=self.status_var, style="Muted.TLabel").pack(anchor="w")

        self.log_window = tk.Text(
            self,
            height=7,
            bg="#0d1014",
            fg="#aeb6c3",
            insertbackground="white",
            relief="flat",
            padx=10,
            pady=8,
            font=("Cascadia Mono", 9),
            state="disabled",
        )
        self.log_window.grid(row=5, column=0, sticky="nsew", padx=22, pady=(0, 18))

    def _apply_language(self) -> None:
        """Reasigna todos los textos al idioma activo, sin reiniciar.

        Los desplegables conservan la opción elegida porque la aplicación
        guarda la clave y no la etiqueta. Las líneas que ya están en el
        registro se quedan en su idioma.
        """
        self.subtitle_label.configure(text=t("gui.subtitle"))
        self.language_label.configure(text=t("gui.language"))
        self.language_var.set(SUPPORTED_LANGUAGES[get_language()])
        self.installation_label.configure(text=t("gui.installation"))
        self.output_label.configure(text=t("gui.output"))
        self.game_browse_button.configure(text=t("gui.browse"))
        self.output_browse_button.configure(text=t("gui.browse"))
        self.scan_button.configure(text=t("gui.scan"))
        self.containers_label.configure(text=t("gui.containers"))
        for column, key in (
            ("#0", "gui.col_name"),
            ("type", "gui.col_type"),
            ("count", "gui.col_files"),
            ("size", "gui.col_size"),
        ):
            self.archive_tree.heading(column, text=t(key))
        self.files_label.configure(text=t("gui.files"))
        self.back_button.configure(text=t("gui.back"))
        self.explore_button.configure(text=t("gui.open_package"))
        self.preview_button.configure(text=t("gui.view_image"))
        self.filter_label.configure(text=t("gui.filter"))
        for column, key in (
            ("#0", "gui.col_path"),
            ("kind", "gui.col_type"),
            ("size", "gui.col_size"),
            ("offset", "gui.col_offset"),
        ):
            self.entry_tree.heading(column, text=t(key))
        self.auto_unpack_check.configure(text=t("gui.split_internal"))
        self.if_exists_label.configure(text=t("gui.if_exists"))
        self.collision_box.configure(values=[t(COLLISION_LABELS[policy]) for policy in COLLISION_POLICIES])
        self.collision_var.set(t(COLLISION_LABELS[self.collision_policy]))
        self.extract_selected_button.configure(text=t("gui.extract_selection"))
        self.extract_all_button.configure(text=t("gui.extract_visible"))
        self.cancel_button.configure(text=t("gui.cancel"))
        self._refresh_kind_labels()
        self._render_status()
        self._render_summary()
        if self.preview_window is not None and self.preview_window.winfo_exists():
            self.preview_window.apply_language()

    def _on_language_selected(self, _event=None) -> None:
        index = self.language_box.current()
        codes = tuple(SUPPORTED_LANGUAGES)
        if 0 <= index < len(codes) and codes[index] != get_language():
            set_language(codes[index])
            self._apply_language()
        self.language_box.selection_clear()

    def _on_collision_selected(self, _event=None) -> None:
        index = self.collision_box.current()
        if 0 <= index < len(COLLISION_POLICIES):
            self.collision_policy = COLLISION_POLICIES[index]
        self.collision_box.selection_clear()

    @staticmethod
    def _format(key: str, params: dict[str, object]) -> str:
        """Rellena el texto; un parámetro invocable se evalúa ahora, en el idioma activo."""
        return t(key, **{name: value() if callable(value) else value for name, value in params.items()})

    def _set_status(self, key: str, **params: object) -> None:
        self._status = (key, params)
        self._render_status()

    def _render_status(self) -> None:
        self.status_var.set(self._format(*self._status))

    def _set_summary(self, key: str, **params: object) -> None:
        self._summary = (key, params)
        self._render_summary()

    def _render_summary(self) -> None:
        self.summary_var.set(self._format(*self._summary))

    def _choose_game(self) -> None:
        selected = filedialog.askdirectory(title=t("gui.game_folder_title"), initialdir=self.game_var.get())
        if selected:
            self.game_var.set(selected)

    def _choose_output(self) -> None:
        selected = filedialog.askdirectory(title=t("gui.output_folder_title"), initialdir=self.output_var.get())
        if selected:
            self.output_var.set(selected)

    def _set_busy(self, busy: bool) -> None:
        state = "disabled" if busy else "normal"
        for widget in (
            self.scan_button,
            self.extract_selected_button,
            self.extract_all_button,
            self.explore_button,
        ):
            widget.configure(state=state)
        self.back_button.configure(state="disabled" if busy or self.inner_parent is None else "normal")
        self.cancel_button.configure(state="normal" if busy else "disabled")
        if busy:
            # Con un total conocido la barra avanza de verdad; el análisis, que
            # no lo tiene, se queda con la marquesina.
            if self.progress_total:
                self.progress.configure(mode="determinate", maximum=self.progress_total, value=0)
            else:
                self.progress.start(12)
        else:
            self.progress.stop()
            self.progress_total = 0
            self.progress.configure(mode="indeterminate", value=0)

    def _start_worker(self, target, success_key: str, on_done, *, total: int = 0) -> bool:
        """Arranca el hilo de trabajo; devuelve False si ya había uno vivo.

        ``success_key`` es la clave del mensaje de éxito, no el texto: se
        traduce al terminar, en el idioma que haya entonces. ``on_done`` recibe
        el resultado en el hilo de la interfaz. Lo dice quien lanza la tarea
        porque el resultado no basta para saberlo: una extracción que no
        escribe nada devuelve una lista vacía, igual que un análisis vacío, y
        tomarla por análisis borraba la lista de contenedores.

        El estado del progreso se fija aquí, pasada la guarda, para que un
        arranque rechazado no pise el de la operación que sigue en curso.
        """
        if self.worker and self.worker.is_alive():
            return False
        self.cancel_event.clear()
        with self.progress_lock:
            self.progress_done = 0
        self.progress_total = total
        self._set_busy(True)

        def run() -> None:
            try:
                result = target()
                self.messages.put(("done", (result, success_key, on_done)))
            except CancelledError as exc:
                self.messages.put(("cancelled", str(exc)))
            except Exception as exc:
                self.messages.put(("error", exc))

        self.worker = threading.Thread(target=run, daemon=True)
        self.worker.start()
        return True

    def _log(self, message: str) -> None:
        self.messages.put(("log", message))

    def _on_progress(self, count: int) -> None:
        """Corre en el hilo de trabajo: solo suma, nunca toca Tk."""
        with self.progress_lock:
            self.progress_done += count

    def _refresh_progress(self) -> None:
        if not self.progress_total:
            return
        with self.progress_lock:
            done = min(self.progress_done, self.progress_total)
        self.progress.configure(value=done)
        self._set_status(
            "status.progress",
            percent=100 * done / self.progress_total,
            done=human_size(done),
            total=human_size(self.progress_total),
        )

    def _append_log(self, message: str) -> None:
        self.log_window.configure(state="normal")
        self.log_window.insert("end", message.rstrip() + "\n")
        self.log_window.see("end")
        self.log_window.configure(state="disabled")

    def scan(self) -> None:
        game = Path(self.game_var.get()).expanduser()
        self._start_worker(lambda: scan_game(game), "status.scan_done", self._scan_finished)
        self._set_status("status.reading_manifest")

    def _scan_finished(self, archives: list[Archive], _success_key: str) -> None:
        self._load_archives(archives)
        self._append_log(t("log.scan_done", count=len(archives)))

    def _extraction_finished(self, written: list[Path], success_key: str) -> None:
        self._append_log(t("log.files_written", count=len(written)))
        messagebox.showinfo(
            "Darkstractor",
            t("dialog.files_written", message=t(success_key), count=len(written)),
        )

    def _load_archives(self, archives: list[Archive]) -> None:
        self.archives = archives
        self.archive_tree.delete(*self.archive_tree.get_children())
        total_entries = 0
        total_bytes = 0
        for index, archive in enumerate(archives):
            total_entries += len(archive.entries)
            size = archive.path.stat().st_size if archive.path.is_file() else sum(entry.size for entry in archive.entries)
            total_bytes += size
            self.archive_tree.insert("", "end", iid=str(index), text=archive.name, values=(archive.kind.upper(), len(archive.entries), human_size(size)))
        self._set_summary(
            "summary.totals", archives=len(archives), entries=total_entries, size=human_size(total_bytes)
        )
        if archives:
            self.archive_tree.selection_set("0")
            self.archive_tree.focus("0")
            self._show_archive(archives[0])

    def _select_archive(self, _event=None) -> None:
        selection = self.archive_tree.selection()
        if selection:
            self._show_archive(self.archives[int(selection[0])])

    def _show_archive(self, archive: Archive) -> None:
        self.current_archive = archive
        self.current_entries = archive.entries
        self.inner_parent = None
        self.back_button.configure(state="disabled")
        self._refresh_entries()
        # La nota es una clave: se traduce cada vez que se pinta el estado.
        self._set_status("status.archive", name=archive.name, note=lambda: t(archive.note))

    def _refresh_entries(self) -> None:
        if not self.current_archive:
            return
        needle = self.filter_var.get().strip().casefold()
        self.visible_entries = [entry for entry in self.current_entries if needle in entry.name.casefold()]
        self.entry_tree.delete(*self.entry_tree.get_children())
        for index, entry in enumerate(self.visible_entries):
            self.entry_tree.insert(
                "", "end", iid=str(index), text=entry.name,
                values=(kind_label(entry.kind).upper(), human_size(entry.size), f"0x{entry.offset:016X}"),
            )
        context = self.inner_parent.name if self.inner_parent else self.current_archive.name
        self._set_status("status.visible_entries", context=context, count=len(self.visible_entries))

    def _refresh_kind_labels(self) -> None:
        """Retraduce la columna Tipo sin rehacer la lista ni tocar el estado.

        Solo cambian con el idioma los tipos OBP; las entradas de primer nivel
        (segmentos UPAK, vídeos…) se quedan como están.
        """
        for index, entry in enumerate(self.visible_entries):
            if entry.kind.startswith("obp-"):
                self.entry_tree.set(str(index), "kind", kind_label(entry.kind).upper())

    def _single_selection(self) -> Entry | None:
        selected = self.entry_tree.selection()
        if len(selected) != 1:
            return None
        return self.visible_entries[int(selected[0])]

    def activate_selected(self) -> None:
        """Doble clic: abre el paquete, o enseña la textura si lo que hay es una."""
        entry = self._single_selection()
        if entry is not None and entry.kind in VIEWABLE_KINDS:
            self.view_selected()
        else:
            self.explore_selected()

    def view_selected(self) -> None:
        entry = self._single_selection()
        if entry is None:
            messagebox.showinfo("Darkstractor", t("dialog.select_texture"))
            return
        if entry.kind not in VIEWABLE_KINDS:
            messagebox.showinfo(t("preview.title"), t("dialog.only_dds"))
            return
        self._load_preview(entry)

    def _load_preview(self, entry: Entry, *, full_detail: bool = False) -> None:
        """Lee y decodifica la textura fuera del hilo de la interfaz.

        No usa el hilo de trabajo principal: mirar una textura no debería
        quedarse esperando a que termine una extracción, ni cancelarla.
        """
        if self.preview_thread and self.preview_thread.is_alive():
            return
        # Pedir más detalle de la textura que ya está abierta no vuelve al
        # disco: en la variante de payload único releerla cuesta más que
        # decodificarla.
        cached = self.preview_data if entry is self.preview_entry else None
        self.preview_button.configure(state="disabled")
        self._set_status("status.reading", name=entry.name)
        max_side = FULL_DETAIL_MAX_SIDE if full_detail else PREVIEW_MAX_SIDE

        def run() -> None:
            try:
                data = cached if cached is not None else read_member_bytes(entry)
                image = dds.decode(data, max_side=max_side)
            except Exception as exc:
                self.messages.put(("preview-error", exc))
            else:
                self.messages.put(("preview", (entry, data, image, full_detail)))

        self.preview_thread = threading.Thread(target=run, daemon=True)
        self.preview_thread.start()

    def _reload_full_detail(self, _name: str) -> None:
        if self.preview_entry is not None:
            self._load_preview(self.preview_entry, full_detail=True)

    def _show_preview(self, name: str, image: dds.DecodedImage, full_detail: bool) -> None:
        if self.preview_window is None or not self.preview_window.winfo_exists():
            self.preview_window = ImageWindow(self, on_full_detail=self._reload_full_detail)
        self.preview_window.show(name, image, full_detail=full_detail)

    def explore_selected(self) -> None:
        entry = self._single_selection()
        if entry is None:
            messagebox.showinfo("Darkstractor", t("dialog.select_package"))
            return
        if entry.kind != "upak-segment":
            return
        try:
            members = list_obp_members(entry)
        except DarkstractorError as error:
            messagebox.showinfo(t("dialog.no_table_title"), t("dialog.no_table", error=error))
            return
        self.inner_parent = entry
        self.current_entries = members
        self.filter_var.set("")
        self.back_button.configure(state="normal")
        self._refresh_entries()
        self._set_status("status.internal_resources", name=entry.name, count=len(members))

    def back_from_package(self) -> None:
        if not self.current_archive:
            return
        self.inner_parent = None
        self.current_entries = self.current_archive.entries
        self.filter_var.set("")
        self.back_button.configure(state="disabled")
        self._refresh_entries()

    def _collision_policy(self) -> str:
        return self.collision_policy

    def _on_close(self) -> None:
        self.cancel_event.set()
        save_settings(
            {
                "game": self.game_var.get(),
                "output": self.output_var.get(),
                "auto_unpack": self.auto_unpack_var.get(),
                "collision": self.collision_policy,
                "language": get_language(),
            }
        )
        self.destroy()

    def extract_selected(self) -> None:
        selected = self.entry_tree.selection()
        if not selected:
            messagebox.showinfo("Darkstractor", t("dialog.select_files"))
            return
        self._extract([self.visible_entries[int(item)] for item in selected])

    def extract_visible(self) -> None:
        if not self.visible_entries:
            return
        total = sum(entry.size for entry in self.visible_entries)
        if not messagebox.askyesno(
            t("dialog.confirm_title"),
            t("dialog.confirm", count=len(self.visible_entries), size=human_size(total)),
        ):
            return
        self._extract(list(self.visible_entries))

    def _extract(self, entries: list[Entry]) -> None:
        output = Path(self.output_var.get()).expanduser()
        auto_unpack = self.auto_unpack_var.get()
        collision_policy = self._collision_policy()
        reserve = estimate_output_bytes(entries, auto_unpack=auto_unpack)

        def task():
            ensure_free_space(output, reserve)
            return extract_entries(
                entries,
                output,
                auto_unpack=auto_unpack,
                policy=collision_policy,
                cancel=self.cancel_event,
                progress=self._on_progress,
                log=self._log,
            )

        if self._start_worker(
            task,
            "status.extraction_done",
            self._extraction_finished,
            total=estimate_source_bytes(entries),
        ):
            self._set_status("status.processing", count=len(entries))

    def cancel(self) -> None:
        self.cancel_event.set()
        self._set_status("status.cancelling")

    def _poll_messages(self) -> None:
        try:
            while True:
                kind, payload = self.messages.get_nowait()
                if kind == "log":
                    self._append_log(str(payload))
                elif kind == "preview":
                    entry, data, image, full_detail = payload
                    self.preview_entry, self.preview_data = entry, data
                    self.preview_button.configure(state="normal")
                    self._show_preview(entry.name, image, full_detail)
                    self._set_status(
                        "status.preview",
                        name=entry.name,
                        label=lambda header=image.header: header.label,
                        width=image.header.width,
                        height=image.header.height,
                    )
                elif kind == "preview-error":
                    self.preview_button.configure(state="normal")
                    if self.preview_window is not None and self.preview_window.winfo_exists():
                        self.preview_window.detail_failed()
                    self._append_log(t("log.preview_error", error=payload))
                    self._set_status("status.preview_failed")
                    messagebox.showinfo(t("preview.title"), str(payload))
                elif kind == "done":
                    result, success_key, on_done = payload
                    self._set_busy(False)
                    self._set_status(success_key)
                    on_done(result, success_key)
                elif kind == "cancelled":
                    self._set_busy(False)
                    # El hilo de trabajo solo cancela extracciones: el estado
                    # usa su clave para poder repintarse en otro idioma.
                    self._set_status("status.cancelled")
                    self._append_log(str(payload))
                elif kind == "error":
                    self._set_busy(False)
                    self._set_status("status.error")
                    error = payload
                    self._append_log(f"ERROR: {error}")
                    messagebox.showerror("Darkstractor", str(error))
        except queue.Empty:
            pass
        self._refresh_progress()
        self.after(100, self._poll_messages)


def main(language: str | None = None) -> None:
    """Arranca la GUI; ``language`` fuerza el idioma, si no, se usa el guardado."""
    app = DarkstractorApp(language)
    app.mainloop()
