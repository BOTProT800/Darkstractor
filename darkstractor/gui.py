from __future__ import annotations

import os
import queue
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from tkinter import simpledialog

from .errors import CancelledError, DarkstractorError
from .models import Archive, Entry
from .repack import RepackResult, create_patched_upak
from .installation import (
    InstallationResult,
    active_installations,
    default_backup_root,
    install_mod,
    read_mod_manifest,
    restore_backup,
)
from .service import ensure_free_space, extract_entries, human_size, list_obp_members, scan_game

DEFAULT_GAME = Path(r"C:\Program Files (x86)\Steam\steamapps\common\Darksiders II Deathinitive Edition")


class DarkstractorApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("Darkstractor — Darksiders II Deathinitive Edition")
        self.geometry("1180x760")
        self.minsize(940, 620)
        self.configure(bg="#111317")

        self.messages: queue.Queue[tuple[str, object]] = queue.Queue()
        self.cancel_event = threading.Event()
        self.worker: threading.Thread | None = None
        self.archives: list[Archive] = []
        self.current_archive: Archive | None = None
        self.current_entries: list[Entry] = []
        self.inner_parent: Entry | None = None
        self.visible_entries: list[Entry] = []

        default_output = Path.cwd() / "extraccion"
        self.game_var = tk.StringVar(value=str(DEFAULT_GAME if DEFAULT_GAME.exists() else Path.cwd()))
        self.output_var = tk.StringVar(value=str(default_output))
        self.filter_var = tk.StringVar()
        self.auto_unpack_var = tk.BooleanVar(value=True)
        self.collision_var = tk.StringVar(value="Renombrar")
        self.status_var = tk.StringVar(value="Selecciona la instalación y pulsa Analizar")
        self.summary_var = tk.StringVar(value="Sin analizar")

        self._configure_styles()
        self._build_ui()
        self.filter_var.trace_add("write", lambda *_: self.after(180, self._refresh_entries))
        self.after(100, self._poll_messages)
        self.after(250, self.scan)

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
        header = ttk.Frame(self, padding=(22, 18, 22, 10))
        header.pack(fill="x")
        ttk.Label(header, text="DARKSTRACTOR", style="Title.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(
            header,
            text="Extractor y gestor seguro de mods para Darksiders II Deathinitive Edition",
            style="Muted.TLabel",
        ).grid(row=1, column=0, sticky="w", pady=(2, 0))
        ttk.Label(header, textvariable=self.summary_var, style="Muted.TLabel").grid(row=0, column=1, rowspan=2, sticky="e")
        header.columnconfigure(1, weight=1)

        paths = ttk.Frame(self, style="Panel.TFrame", padding=14)
        paths.pack(fill="x", padx=22, pady=(0, 12))
        ttk.Label(paths, text="Instalación", background="#1a1e24").grid(row=0, column=0, sticky="w")
        ttk.Entry(paths, textvariable=self.game_var).grid(row=1, column=0, sticky="ew", padx=(0, 8), pady=(4, 0))
        ttk.Button(paths, text="Elegir…", command=self._choose_game).grid(row=1, column=1, padx=(0, 12), pady=(4, 0))
        ttk.Label(paths, text="Salida", background="#1a1e24").grid(row=0, column=2, sticky="w")
        ttk.Entry(paths, textvariable=self.output_var).grid(row=1, column=2, sticky="ew", padx=(0, 8), pady=(4, 0))
        ttk.Button(paths, text="Elegir…", command=self._choose_output).grid(row=1, column=3, padx=(0, 12), pady=(4, 0))
        self.scan_button = ttk.Button(paths, text="Analizar", style="Accent.TButton", command=self.scan)
        self.scan_button.grid(row=1, column=4, pady=(4, 0))
        paths.columnconfigure(0, weight=1)
        paths.columnconfigure(2, weight=1)

        pane = ttk.Panedwindow(self, orient="horizontal")
        pane.pack(fill="both", expand=True, padx=22)

        left = ttk.Frame(pane, style="Panel.TFrame", padding=10)
        right = ttk.Frame(pane, style="Panel.TFrame", padding=10)
        pane.add(left, weight=2)
        pane.add(right, weight=5)

        ttk.Label(left, text="CONTENEDORES", background="#1a1e24", foreground="#aeb5c0", font=("Segoe UI Semibold", 9)).pack(anchor="w", pady=(0, 8))
        self.archive_tree = ttk.Treeview(left, columns=("type", "count", "size"), show="tree headings", selectmode="browse")
        self.archive_tree.heading("#0", text="Nombre")
        self.archive_tree.heading("type", text="Tipo")
        self.archive_tree.heading("count", text="Archivos")
        self.archive_tree.heading("size", text="Tamaño")
        self.archive_tree.column("#0", width=150)
        self.archive_tree.column("type", width=60, anchor="center")
        self.archive_tree.column("count", width=65, anchor="e")
        self.archive_tree.column("size", width=82, anchor="e")
        self.archive_tree.pack(fill="both", expand=True)
        self.archive_tree.bind("<<TreeviewSelect>>", self._select_archive)

        top_right = ttk.Frame(right, style="Panel.TFrame")
        top_right.pack(fill="x", pady=(0, 8))
        ttk.Label(top_right, text="ARCHIVOS", background="#1a1e24", foreground="#aeb5c0", font=("Segoe UI Semibold", 9)).pack(side="left")
        self.back_button = ttk.Button(top_right, text="← Volver", command=self.back_from_package, state="disabled")
        self.back_button.pack(side="left", padx=(12, 6))
        self.explore_button = ttk.Button(top_right, text="Abrir paquete", command=self.explore_selected)
        self.explore_button.pack(side="left")
        ttk.Entry(top_right, textvariable=self.filter_var, width=30).pack(side="right")
        ttk.Label(top_right, text="Filtrar  ", background="#1a1e24", foreground="#9299a6").pack(side="right")

        entry_frame = ttk.Frame(right, style="Panel.TFrame")
        entry_frame.pack(fill="both", expand=True)
        self.entry_tree = ttk.Treeview(entry_frame, columns=("kind", "size", "offset"), show="headings", selectmode="extended")
        self.entry_tree.heading("kind", text="Tipo")
        self.entry_tree.heading("size", text="Tamaño")
        self.entry_tree.heading("offset", text="Offset")
        self.entry_tree["displaycolumns"] = ("kind", "size", "offset")
        self.entry_tree.column("kind", width=95)
        self.entry_tree.column("size", width=100, anchor="e")
        self.entry_tree.column("offset", width=115, anchor="e")
        self.entry_tree.heading("#0", text="Ruta")
        # Treeview necesita #0 visible para mostrar la ruta.
        self.entry_tree.configure(show="tree headings")
        self.entry_tree.column("#0", width=470)
        scrollbar = ttk.Scrollbar(entry_frame, orient="vertical", command=self.entry_tree.yview)
        self.entry_tree.configure(yscrollcommand=scrollbar.set)
        self.entry_tree.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        self.entry_tree.bind("<Double-1>", lambda _event: self.explore_selected())

        options = ttk.Frame(self, padding=(22, 12, 22, 8))
        options.pack(fill="x")
        ttk.Checkbutton(
            options,
            text="Separar recursos internos (DDS, .2, BMAT, O3D…)",
            variable=self.auto_unpack_var,
        ).pack(side="left")
        ttk.Label(options, text="  Si existe:").pack(side="left")
        ttk.Combobox(
            options,
            textvariable=self.collision_var,
            values=("Renombrar", "Omitir", "Sobrescribir"),
            state="readonly",
            width=13,
        ).pack(side="left", padx=(4, 0))
        self.extract_selected_button = ttk.Button(options, text="Extraer selección", style="Accent.TButton", command=self.extract_selected)
        self.extract_selected_button.pack(side="right")
        self.extract_all_button = ttk.Button(options, text="Extraer visibles", command=self.extract_visible)
        self.extract_all_button.pack(side="right", padx=(0, 8))
        self.replace_button = ttk.Button(options, text="Reemplazar DDS…", command=self.replace_dds)
        self.replace_button.pack(side="right", padx=(0, 8))
        self.cancel_button = ttk.Button(options, text="Cancelar", command=self.cancel, state="disabled")
        self.cancel_button.pack(side="right", padx=(0, 8))

        mods = ttk.Frame(self, padding=(22, 0, 22, 8))
        mods.pack(fill="x")
        ttk.Label(mods, text="MODIFICACIONES", foreground="#aeb5c0", font=("Segoe UI Semibold", 9)).pack(side="left")
        self.install_button = ttk.Button(mods, text="Instalar UPAK verificado…", command=self.install_upak)
        self.install_button.pack(side="left", padx=(12, 8))
        self.restore_button = ttk.Button(mods, text="Restaurar respaldo", command=self.restore_upak)
        self.restore_button.pack(side="left")
        ttk.Label(
            mods,
            text="El juego debe estar cerrado; nunca se instala sin respaldo y SHA-256.",
            style="Muted.TLabel",
        ).pack(side="right")

        bottom = ttk.Frame(self, padding=(22, 0, 22, 18))
        bottom.pack(fill="x")
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
        self.log_window.pack(fill="x", padx=22, pady=(0, 18))

    def _choose_game(self) -> None:
        selected = filedialog.askdirectory(title="Carpeta de Darksiders II Deathinitive Edition", initialdir=self.game_var.get())
        if selected:
            self.game_var.set(selected)

    def _choose_output(self) -> None:
        selected = filedialog.askdirectory(title="Carpeta de salida", initialdir=self.output_var.get())
        if selected:
            self.output_var.set(selected)

    def _set_busy(self, busy: bool, status: str | None = None) -> None:
        state = "disabled" if busy else "normal"
        for widget in (
            self.scan_button,
            self.extract_selected_button,
            self.extract_all_button,
            self.explore_button,
            self.replace_button,
            self.install_button,
            self.restore_button,
        ):
            widget.configure(state=state)
        self.back_button.configure(state="disabled" if busy or self.inner_parent is None else "normal")
        self.cancel_button.configure(state="normal" if busy else "disabled")
        if busy:
            self.progress.start(12)
        else:
            self.progress.stop()
        if status:
            self.status_var.set(status)

    def _start_worker(self, target, success_message: str) -> None:
        if self.worker and self.worker.is_alive():
            return
        self.cancel_event.clear()
        self._set_busy(True)

        def run() -> None:
            try:
                result = target()
                self.messages.put(("done", (result, success_message)))
            except CancelledError as exc:
                self.messages.put(("cancelled", str(exc)))
            except Exception as exc:
                self.messages.put(("error", exc))

        self.worker = threading.Thread(target=run, daemon=True)
        self.worker.start()

    def _log(self, message: str) -> None:
        self.messages.put(("log", message))

    def _append_log(self, message: str) -> None:
        self.log_window.configure(state="normal")
        self.log_window.insert("end", message.rstrip() + "\n")
        self.log_window.see("end")
        self.log_window.configure(state="disabled")

    def scan(self) -> None:
        game = Path(self.game_var.get()).expanduser()
        self._start_worker(lambda: scan_game(game), "Análisis terminado")
        self.status_var.set("Leyendo manifest.bin y tablas de audio…")

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
        self.summary_var.set(f"{len(archives)} contenedores  •  {total_entries:,} entradas  •  {human_size(total_bytes)}")
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
        self.status_var.set(f"{archive.name}: {archive.note}")

    def _refresh_entries(self) -> None:
        if not self.current_archive:
            return
        needle = self.filter_var.get().strip().casefold()
        self.visible_entries = [entry for entry in self.current_entries if needle in entry.name.casefold()]
        self.entry_tree.delete(*self.entry_tree.get_children())
        for index, entry in enumerate(self.visible_entries):
            self.entry_tree.insert(
                "", "end", iid=str(index), text=entry.name,
                values=(entry.kind.removeprefix("obp-").upper(), human_size(entry.size), f"0x{entry.offset:016X}"),
            )
        context = self.inner_parent.name if self.inner_parent else self.current_archive.name
        self.status_var.set(f"{context}: {len(self.visible_entries):,} entradas visibles")

    def explore_selected(self) -> None:
        selected = self.entry_tree.selection()
        if len(selected) != 1:
            messagebox.showinfo("Darkstractor", "Selecciona un único paquete UPAK para abrirlo.")
            return
        entry = self.visible_entries[int(selected[0])]
        if entry.kind != "upak-segment":
            return
        try:
            members = list_obp_members(entry)
        except DarkstractorError as error:
            messagebox.showinfo(
                "Paquete sin tabla interna",
                f"Este segmento no tiene una tabla Deathinitive separable.\n\n{error}",
            )
            return
        self.inner_parent = entry
        self.current_entries = members
        self.filter_var.set("")
        self.back_button.configure(state="normal")
        self._refresh_entries()
        self.status_var.set(f"{entry.name}: {len(members):,} recursos internos")

    def back_from_package(self) -> None:
        if not self.current_archive:
            return
        self.inner_parent = None
        self.current_entries = self.current_archive.entries
        self.filter_var.set("")
        self.back_button.configure(state="disabled")
        self._refresh_entries()

    def _collision_policy(self) -> str:
        return {"Renombrar": "rename", "Omitir": "skip", "Sobrescribir": "overwrite"}[self.collision_var.get()]

    def extract_selected(self) -> None:
        selected = self.entry_tree.selection()
        if not selected:
            messagebox.showinfo("Darkstractor", "Selecciona uno o más archivos de la lista.")
            return
        self._extract([self.visible_entries[int(item)] for item in selected])

    def extract_visible(self) -> None:
        if not self.visible_entries:
            return
        total = sum(entry.size for entry in self.visible_entries)
        if not messagebox.askyesno(
            "Confirmar extracción",
            f"Se procesarán {len(self.visible_entries):,} entradas ({human_size(total)} empaquetados).\n\n¿Continuar?",
        ):
            return
        self._extract(list(self.visible_entries))

    def _extract(self, entries: list[Entry]) -> None:
        output = Path(self.output_var.get()).expanduser()
        estimate = sum(entry.size for entry in entries)
        auto_unpack = self.auto_unpack_var.get()
        collision_policy = self._collision_policy()
        if auto_unpack and any(entry.kind in ("upak-segment", "zlib-all") for entry in entries):
            # zlib puede expandirse mucho; una reserva conservadora evita llenar el disco a mitad.
            estimate *= 3

        def task():
            ensure_free_space(output, estimate)
            return extract_entries(
                entries,
                output,
                auto_unpack=auto_unpack,
                policy=collision_policy,
                cancel=self.cancel_event,
                log=self._log,
            )

        self._start_worker(task, "Extracción terminada")
        self.status_var.set(f"Procesando {len(entries):,} entradas…")

    def replace_dds(self) -> None:
        selected = self.entry_tree.selection()
        if len(selected) != 1:
            messagebox.showinfo(
                "Reemplazar DDS",
                "Abre un paquete y selecciona una única textura DDS interna.",
            )
            return
        entry = self.visible_entries[int(selected[0])]
        if entry.kind != "obp-dds":
            messagebox.showinfo(
                "Reemplazar DDS",
                "La entrada seleccionada no es una textura DDS interna.",
            )
            return
        replacement = filedialog.askopenfilename(
            title="DDS de reemplazo compatible",
            filetypes=(("DirectDraw Surface", "*.dds"), ("Todos los archivos", "*.*")),
        )
        if not replacement:
            return

        output_dir = Path(self.output_var.get()).expanduser()
        initial_dir = output_dir if output_dir.is_dir() else Path.cwd()
        source_name = entry.source.stem + "_mod" + entry.source.suffix
        destination_text = filedialog.asksaveasfilename(
            title="Guardar copia UPAK modificada",
            initialdir=initial_dir,
            initialfile=source_name,
            defaultextension=entry.source.suffix,
            filetypes=(("Darksiders II UPAK", "*.upak"), ("Todos los archivos", "*.*")),
        )
        if not destination_text:
            return
        destination = Path(destination_text)
        overwrite = False
        if destination.exists():
            overwrite = messagebox.askyesno(
                "Sobrescribir copia",
                f"Ya existe:\n{destination}\n\n¿Quieres reemplazar esa copia?",
            )
            if not overwrite:
                return

        def task():
            return create_patched_upak(
                entry,
                Path(replacement),
                destination,
                overwrite=overwrite,
                cancel=self.cancel_event,
                log=self._log,
            )

        self._start_worker(task, "UPAK modificado creado")
        self.status_var.set(
            f"Validando DDS y reconstruyendo una copia de {entry.source.name}…"
        )

    def install_upak(self, patched_path: Path | None = None) -> None:
        if patched_path is None:
            selected = filedialog.askopenfilename(
                title="UPAK generado por Darkstractor",
                initialdir=self.output_var.get(),
                filetypes=(("Darksiders II UPAK", "*.upak"), ("Todos los archivos", "*.*")),
            )
            if not selected:
                return
            patched_path = Path(selected)
        try:
            manifest = read_mod_manifest(patched_path)
        except DarkstractorError as error:
            messagebox.showerror("UPAK no verificable", str(error))
            return
        game = Path(self.game_var.get()).expanduser()
        target = game / "media" / manifest.source_name
        if not messagebox.askyesno(
            "Instalar modificación",
            f"Se instalará como:\n{target}\n\n"
            f"Textura: {manifest.texture_name}\n"
            f"SHA-256 del mod: {manifest.patched_sha256[:16]}…\n\n"
            f"El estado actual se respaldará en:\n{default_backup_root()}\n\n"
            "Cierra el juego antes de continuar. ¿Instalar?",
        ):
            return

        def task():
            return install_mod(
                game,
                patched_path,
                cancel=self.cancel_event,
                log=self._log,
            )

        self._start_worker(task, "Modificación instalada")
        self.status_var.set(f"Verificando, respaldando e instalando {manifest.source_name}…")

    def restore_upak(self) -> None:
        game = Path(self.game_var.get()).expanduser()
        try:
            states = active_installations(game)
        except DarkstractorError as error:
            messagebox.showerror("Restaurar respaldo", str(error))
            return
        if not states:
            messagebox.showinfo("Restaurar respaldo", "No hay modificaciones activas administradas por Darkstractor.")
            return
        names = [state.target_name for state in states]
        preferred = self.current_archive.name if self.current_archive and self.current_archive.name in names else None
        if preferred:
            target_name = preferred
        elif len(names) == 1:
            target_name = names[0]
        else:
            target_name = simpledialog.askstring(
                "Restaurar respaldo",
                "Escribe el archivo que quieres restaurar:\n\n" + "\n".join(names),
                parent=self,
            )
            if not target_name:
                return
            target_name = target_name.strip()
            if target_name not in names:
                messagebox.showerror("Restaurar respaldo", "Ese archivo no tiene una modificación activa.")
                return
        state = next(item for item in states if item.target_name == target_name)
        if not messagebox.askyesno(
            "Restaurar estado anterior",
            f"Se restaurará {target_name} desde:\n{state.backup_path}\n\n"
            "El archivo instalado será reemplazado. ¿Continuar?",
        ):
            return

        def task():
            return restore_backup(
                game,
                target_name,
                cancel=self.cancel_event,
                log=self._log,
            )

        self._start_worker(task, "Respaldo restaurado")
        self.status_var.set(f"Verificando y restaurando {target_name}…")

    def cancel(self) -> None:
        self.cancel_event.set()
        self.status_var.set("Cancelando al terminar el bloque actual…")

    def _poll_messages(self) -> None:
        try:
            while True:
                kind, payload = self.messages.get_nowait()
                if kind == "log":
                    self._append_log(str(payload))
                elif kind == "done":
                    result, message = payload
                    self._set_busy(False, message)
                    if isinstance(result, list) and (not result or isinstance(result[0], Archive)):
                        self._load_archives(result)
                        self._append_log(f"Análisis completo: {len(result)} contenedores")
                    elif isinstance(result, list):
                        self._append_log(f"Completado: {len(result)} archivos escritos")
                        messagebox.showinfo("Darkstractor", f"{message}.\n\nArchivos escritos: {len(result)}")
                    elif isinstance(result, RepackResult):
                        self._append_log(
                            f"Reempaquetado verificado: {result.output} "
                            f"({result.padding} bytes de margen en el OBP)"
                        )
                        install_now = messagebox.askyesno(
                            "UPAK modificado creado",
                            f"La textura fue reemplazada y verificada.\n\n"
                            f"Salida:\n{result.output}\n\n"
                            f"Manifiesto SHA-256:\n{result.manifest}\n\n"
                            "El archivo original del juego no fue modificado.\n\n"
                            "¿Quieres instalarlo ahora con respaldo automático?",
                        )
                        if install_now:
                            self.install_upak(result.output)
                    elif isinstance(result, InstallationResult):
                        verb = "instalado" if result.action == "install" else "restaurado"
                        self._append_log(
                            f"UPAK {verb}: {result.target} | SHA-256 {result.installed_sha256}"
                        )
                        detail = "Ya estaba en ese estado." if result.already_done else "La comprobación SHA-256 fue correcta."
                        messagebox.showinfo(
                            "Modificación instalada" if result.action == "install" else "Respaldo restaurado",
                            f"Archivo {verb} correctamente:\n{result.target}\n\n"
                            f"Respaldo:\n{result.backup}\n\n{detail}",
                        )
                elif kind == "cancelled":
                    self._set_busy(False, str(payload))
                    self._append_log(str(payload))
                elif kind == "error":
                    self._set_busy(False, "La operación terminó con un error")
                    error = payload
                    self._append_log(f"ERROR: {error}")
                    messagebox.showerror("Darkstractor", str(error))
        except queue.Empty:
            pass
        self.after(100, self._poll_messages)


def main() -> None:
    app = DarkstractorApp()
    app.mainloop()
