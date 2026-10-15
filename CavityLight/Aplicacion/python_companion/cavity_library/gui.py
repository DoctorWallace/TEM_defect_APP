"""Spanish desktop library. Scientific sources are opened read-only by the readers.

Worker threads never access Tk. A generation token prevents a delayed result from
replacing a newer selection, including when the window is being closed.
"""
from __future__ import annotations

import argparse
import copy
from datetime import datetime
import hashlib
import math
import os
from pathlib import Path
import queue
import struct
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from .catalog import Catalog
from .readers import compare_runs, plain_path, read_revision_details, read_run

TITLE = "Cavity TEM Light · Biblioteca y revisiones"
OPEN_EXTENSIONS = frozenset({".png", ".csv", ".tsv", ".html", ".htm"})


def matching_images(project, query):
    """Search names and source paths without opening a TEM source."""
    words = str(query).casefold().split()
    common = " ".join(str(project.get(k, "")) for k in ("name", "project_id", "path"))
    return [item for item in project.get("images", []) if all(
        word in (common + " " + " ".join(str(item.get(k, "")) for k in
                ("name", "image_id", "source_path", "status"))).casefold()
        for word in words)]


def image_selection_key(image):
    """Stable within-project identity, including repeated P3 display IDs."""
    if not image:
        return None
    if image.get("image_uid"):
        return ("uid", str(image["image_uid"]))
    if image.get("path"):
        return ("path", os.path.normcase(os.path.abspath(str(image["path"]))))
    return ("id", str(image.get("image_id", "")))


def history_selection_key(entry):
    if not entry:
        return None
    return (str(entry.get("revision_id", "")), str(entry.get("session_uid", "")), str(entry.get("run_id", "")))


def revision_history(project, image):
    """One chronological list of saved results and revisions without results."""
    revisions = {(str(revision.get("revision_id")), str(revision.get("session_uid", ""))): revision
                 for revision in image.get("revisions", [])}
    entries, represented = [], set()
    for run in image.get("runs", []):
        identity = (str(run.get("revision_id")), str(run.get("session_uid", "")))
        revision = revisions.get(identity, {})
        represented.add(identity)
        entry = dict(run, entry_kind="run", name=revision.get("name", ""), comment=revision.get("comment", ""),
                     created_ms=revision.get("created_ms", ""))
        entry["label"] = ((entry["name"] + " · ") if entry["name"] else "") + f"{entry.get('run_id')} / {entry.get('revision_id')}"
        entries.append(entry)
    for identity, revision in revisions.items():
        if identity not in represented:
            entry = dict(revision, entry_kind="revision")
            entry["label"] = entry.get("name") or entry.get("revision_id")
            entries.append(entry)
    for entry in entries:
        labels = ["Sin resultado"] if entry["entry_kind"] == "revision" else []
        if (entry.get("revision_id") == image.get("revision_id")
                and (not image.get("session_uid") or entry.get("session_uid") == image.get("session_uid"))
                and (entry["entry_kind"] == "revision" or entry.get("run_id") == image.get("run_id"))):
            labels.insert(0, "Actual")
        entry["state"] = " · ".join(labels)
    def order(entry):
        try:
            stamp = int(entry.get("created_ms") or 0)
        except (TypeError, ValueError):
            stamp = 0
        if not stamp:
            try:
                stamp = int(datetime.strptime(str(entry.get("revision_id"))[4:19], "%Y%m%d_%H%M%S").timestamp() * 1000)
            except (ValueError, OverflowError):
                pass
        return stamp, str(entry.get("revision_id", "")), str(entry.get("run_id", ""))
    return sorted(entries, key=order, reverse=True)


def reference_matches(reference, project, image, run=None):
    """Keep the accepted identity separate from the current image pointers."""
    if str(reference.get("image_id", "")) != str(image.get("image_id", "")):
        return False
    if reference.get("image_uid") and reference.get("image_uid") != image.get("image_uid"):
        return False
    if reference.get("project_uid") and reference.get("project_uid") != project.get("project_uid"):
        return False
    source = reference.get("project_path") or reference.get("project_root")
    if source and os.path.normcase(os.path.abspath(str(source))) != os.path.normcase(
            os.path.abspath(str(project.get("path", "")))):
        return False
    if not source and reference.get("project_id") != project.get("project_id"):
        return False
    if run is None:
        return True
    if reference.get("run_path") and run.get("path"):
        if os.path.normcase(os.path.abspath(str(reference["run_path"]))) != os.path.normcase(os.path.abspath(str(run["path"]))):
            return False
    if reference.get("session_uid") and reference.get("session_uid") != run.get("session_uid"):
        return False
    return (str(reference.get("run_id")) == str(run.get("run_id"))
            and str(reference.get("revision_id")) == str(run.get("revision_id")))


def safe_result_path(report, item, run_path):
    """Only hand the OS a data file listed by this verified result reader."""
    if not report.get("verification", {}).get("ok"):
        errors = report.get("verification", {}).get("errors", [])
        if errors:
            raise ValueError("No se puede confirmar la integridad de este RUN:\n\n"
                             + "\n".join("• " + str(error) for error in errors)
                             + "\n\nLa comprobación es automática al seleccionar el RUN. "
                             "Consulta los detalles en Resumen guardado.")
        raise ValueError("Este RUN todavía no tiene una comprobación de integridad completada. "
                         "Selecciónalo en el historial y espera a que termine la lectura.")
    candidate = str(item.get("path", ""))
    if candidate not in {str(entry.get("path", "")) for entry in report.get("files", [])}:
        raise ValueError("El archivo no pertenece al resultado seleccionado.")
    path = plain_path(candidate).resolve(strict=True)
    root = plain_path(run_path).resolve(strict=True)
    if root not in path.parents or not path.is_file() or path.suffix.lower() not in OPEN_EXTENSIONS:
        raise ValueError("Solo se abren tablas, gráficos e informes contenidos en el resultado seleccionado.")
    expected = item.get("sha256")
    if expected:
        digest = hashlib.sha256()
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
        if digest.hexdigest() != expected:
            raise ValueError("El archivo cambió después de comprobar el resultado. Vuelva a seleccionar el RUN.")
    return path


class LibraryWindow:
    """Desktop view; accept a launcher callback for integration and UI checks."""

    def __init__(self, root, catalog, launcher=None):
        self.root = root
        self.catalog = catalog
        self.launcher = launcher
        self.projects = []
        self.references = []
        self.project = self.image = self.run = self.report = None
        self._project_items = {}
        self._image_items = {}
        self._run_items = {}
        self._file_items = {}
        self._events = queue.Queue()
        self._generation = 0
        self._busy = None
        self._cancel = None
        self._closed = False
        self._poll_id = self._search_id = None
        self._photo = None
        self._revision_photo = None
        self.revision_details = None
        self._comparison_run = None
        self._comparison_rows = {}
        self._restore_history = None
        self.search = tk.StringVar(root)
        self.status = tk.StringVar(root, value="Añada una carpeta de proyecto o una carpeta que contenga varios proyectos.")
        self.project_title = tk.StringVar(root, value="Su biblioteca de proyectos")
        self.project_detail = tk.StringVar(root, value="Consulte imágenes, revisiones y resultados en sus carpetas actuales.")
        self.image_detail = tk.StringVar(root, value="Seleccione una imagen para consultar sus resultados.")
        self.reference_text = tk.StringVar(root, value="Referencia aceptada: ninguna seleccionada")
        self.run_status = tk.StringVar(root, value="Seleccione un resultado del historial.")
        self.revision_heading = tk.StringVar(root, value="Seleccione una revisión del historial.")
        self.comparison_heading = tk.StringVar(root, value="Elija un RUN íntegro como A y otro de una revisión distinta como B.")
        self.root.title(TITLE)
        self.root.geometry("1280x840")
        self.root.minsize(1020, 720)
        self.root.protocol("WM_DELETE_WINDOW", self.close)
        self._build()
        self.search.trace_add("write", self._search_changed)
        self._snapshot()
        if getattr(catalog, "load_warning", ""):
            self.status.set(catalog.load_warning)
        self._poll_id = self.root.after(80, self._poll)

    def _build(self):
        style = ttk.Style(self.root)
        if "clam" in style.theme_names():
            style.theme_use("clam")
        style.configure("TFrame", background="#f5f7fa")
        style.configure("TLabel", background="#f5f7fa", foreground="#20334a", font=("Segoe UI", 10))
        style.configure("Title.TLabel", font=("Segoe UI", 20, "bold"), foreground="#17334f")
        style.configure("Heading.TLabel", font=("Segoe UI", 13, "bold"))
        style.configure("Muted.TLabel", foreground="#56697b", font=("Segoe UI", 9))
        style.configure("TButton", font=("Segoe UI", 10), padding=(9, 6))
        style.configure("Accent.TButton", foreground="white", background="#236887")
        style.map("Accent.TButton", background=[("active", "#174e69"), ("disabled", "#bac8d1")])
        style.configure("Treeview", rowheight=29, font=("Segoe UI", 10), background="white", fieldbackground="white")
        style.configure("Treeview.Heading", font=("Segoe UI", 9, "bold"), padding=(5, 7))
        style.map("Treeview", background=[("selected", "#d8eaf5")], foreground=[("selected", "#17334f")])

        outer = ttk.Frame(self.root, padding=18)
        outer.pack(fill="both", expand=True)
        header = ttk.Frame(outer)
        header.pack(fill="x")
        ttk.Label(header, text="Cavity TEM Light", style="Title.TLabel").pack(side="left")
        ttk.Label(header, text="1.2 RC1 US1  ·  Biblioteca local", style="Muted.TLabel").pack(side="left", padx=16, pady=(9, 0))
        self.editor_new = ttk.Button(header, text="Nuevo proyecto / Abrir editor", command=self._new_editor)
        self.editor_new.pack(side="right")
        self.study_button = ttk.Button(header, text="Estudio del proyecto", command=self._project_study, state="disabled")
        self.study_button.pack(side="right", padx=7)
        toolbar = ttk.Frame(outer, padding=(0, 15, 0, 12))
        toolbar.pack(fill="x")
        self.add_button = ttk.Button(toolbar, text="+ Añadir carpeta", style="Accent.TButton", command=self._add)
        self.add_button.pack(side="left")
        self.refresh_button = ttk.Button(toolbar, text="Actualizar biblioteca", command=self.refresh)
        self.refresh_button.pack(side="left", padx=7)
        self.locations_button = ttk.Button(toolbar, text="Carpetas…", command=self._locations)
        self.locations_button.pack(side="left")
        ttk.Label(toolbar, text="Buscar", style="Muted.TLabel").pack(side="left", padx=(26, 7))
        entry = ttk.Entry(toolbar, textvariable=self.search)
        entry.pack(side="left", fill="x", expand=True)
        entry.bind("<Escape>", lambda _event: self.search.set(""))
        self.cancel_button = ttk.Button(toolbar, text="Cancelar", state="disabled", command=self.cancel)
        self.cancel_button.pack(side="left", padx=(10, 0))

        body = ttk.Panedwindow(outer, orient="horizontal")
        body.pack(fill="both", expand=True)
        sidebar = ttk.Frame(body, width=265)
        body.add(sidebar, weight=1)
        self.count_label = ttk.Label(sidebar, text="PROYECTOS", style="Heading.TLabel")
        self.count_label.pack(anchor="w", pady=(2, 10))
        self.project_tree = self._tree(sidebar, ("images", "results"), {"#0": ("Proyecto", 170),
                                       "images": ("Img.", 45), "results": ("RUN", 45)}, tree=True)
        self.project_tree.bind("<<TreeviewSelect>>", self._select_project)
        ttk.Label(sidebar, text="El catálogo es local. Las imágenes y los\nresultados permanecen en su ubicación.",
                  style="Muted.TLabel", justify="left").pack(anchor="w", pady=(12, 0))

        main = ttk.Frame(body, padding=(18, 0, 0, 0))
        body.add(main, weight=4)
        ttk.Label(main, textvariable=self.project_title, style="Heading.TLabel").pack(anchor="w", fill="x")
        ttk.Label(main, textvariable=self.project_detail, style="Muted.TLabel", wraplength=930,
                  justify="left").pack(anchor="w", fill="x", pady=(4, 10))
        image_box = ttk.Frame(main, height=200)
        image_box.pack(fill="both", expand=False)
        self.image_tree = self._tree(image_box, ("image", "state", "revision", "result", "source"), {
            "image": ("Imagen", 240), "state": ("Avance guardado", 155), "revision": ("Revisiones", 70),
            "result": ("Resultados", 70), "source": ("Fuente", 95)}, height=5)
        self.image_tree.bind("<<TreeviewSelect>>", self._select_image)
        image_bar = ttk.Frame(main, padding=(0, 8, 0, 8))
        image_bar.pack(fill="x")
        ttk.Label(image_bar, textvariable=self.image_detail, style="Muted.TLabel", wraplength=660,
                  justify="left").pack(side="left", fill="x", expand=True)
        self.edit_button = ttk.Button(image_bar, text="Abrir imagen en Fiji", state="disabled", command=self._edit)
        self.edit_button.pack(side="right", padx=(8, 0))

        lower = ttk.Panedwindow(main, orient="horizontal")
        lower.pack(fill="both", expand=True)
        history = ttk.Frame(lower, width=255)
        lower.add(history, weight=2)
        ttk.Label(history, text="Historial por imagen", style="Heading.TLabel").pack(anchor="w", pady=(0, 8))
        self.run_tree = self._tree(history, ("label", "state"), {
            "label": ("Resultado / revisión", 200), "state": ("Selección", 100)}, height=5)
        self.run_tree.bind("<<TreeviewSelect>>", self._select_run)
        ttk.Label(history, textvariable=self.reference_text, wraplength=300,
                  style="Muted.TLabel", justify="left").pack(fill="x", pady=9)
        self.accept_button = ttk.Button(history, text="Aceptar como referencia", state="disabled", command=self._accept)
        self.accept_button.pack(fill="x")
        self.compare_pin_button = ttk.Button(history, text="Tomar resultado como A", state="disabled", command=self._pin_comparison)
        self.compare_pin_button.pack(fill="x", pady=(9, 4))
        self.compare_button = ttk.Button(history, text="Comparar A con selección", state="disabled", command=self._compare)
        self.compare_button.pack(fill="x")

        results = ttk.Frame(lower, padding=(14, 0, 0, 0), width=470)
        lower.add(results, weight=4)
        ttk.Label(results, textvariable=self.run_status, style="Muted.TLabel", wraplength=650,
                  justify="left").pack(fill="x", pady=(0, 8))
        self.tabs = ttk.Notebook(results)
        self.tabs.pack(fill="both", expand=True)
        summary = ttk.Frame(self.tabs)
        self.tabs.add(summary, text="Resumen guardado")
        self.summary = tk.Text(summary, wrap="word", state="disabled", relief="flat", background="white",
                               foreground="#243c51", font=("Segoe UI", 10), padx=14, pady=12)
        self.summary.pack(side="left", fill="both", expand=True)
        scroll = ttk.Scrollbar(summary, command=self.summary.yview)
        scroll.pack(side="right", fill="y")
        self.summary.configure(yscrollcommand=scroll.set)
        self.workspace_tab = ttk.Frame(self.tabs, padding=10)
        self.tabs.add(self.workspace_tab, text="Revisión e imagen")
        ttk.Label(self.workspace_tab, textvariable=self.revision_heading, style="Heading.TLabel", wraplength=650).pack(fill="x", pady=(0, 6))
        self.revision_preview = ttk.Label(self.workspace_tab, text="Imagen de trabajo guardada: no registrada", anchor="center")
        self.revision_preview.pack(fill="x", pady=6)
        revision_text_frame = ttk.Frame(self.workspace_tab)
        revision_text_frame.pack(fill="both", expand=True)
        self.revision_text = tk.Text(revision_text_frame, wrap="word", state="disabled", relief="flat", background="white",
                                     foreground="#243c51", font=("Segoe UI", 10), padx=10, pady=8, height=9)
        self.revision_text.pack(side="left", fill="both", expand=True)
        revision_scroll = ttk.Scrollbar(revision_text_frame, command=self.revision_text.yview)
        revision_scroll.pack(side="right", fill="y")
        self.revision_text.configure(yscrollcommand=revision_scroll.set)
        files = ttk.Frame(self.tabs, padding=8)
        self.tabs.add(files, text="Tablas y gráficos")
        self.file_tree = self._tree(files, ("name",), {"name": ("Archivo", 350)}, height=6)
        self.file_tree.bind("<Double-1>", lambda _event: self._open_file())
        self.open_file_button = ttk.Button(files, text="Abrir archivo seleccionado", command=self._open_file, state="disabled")
        self.open_file_button.pack(anchor="e", pady=(8, 0))
        self.preview_tab = ttk.Frame(self.tabs, padding=8)
        self.tabs.add(self.preview_tab, text="Vista del gráfico")
        self.preview_label = ttk.Label(self.preview_tab, text="Seleccione un PNG en Tablas y gráficos y ábralo.", anchor="center")
        self.preview_label.pack(fill="both", expand=True)
        self.comparison_tab = ttk.Frame(self.tabs, padding=10)
        self.tabs.add(self.comparison_tab, text="Comparar revisiones")
        ttk.Label(self.comparison_tab, textvariable=self.comparison_heading, style="Muted.TLabel", wraplength=650,
                  justify="left").pack(fill="x", pady=(0, 8))
        self.comparison_tree = self._tree(self.comparison_tab, ("field", "left", "right", "state"), {
            "field": ("Parámetro / resultado", 190), "left": ("A · guardado", 150), "right": ("B · guardado", 150),
            "state": ("Comparación", 105)}, height=9)
        self.comparison_tree.bind("<Double-1>", self._comparison_detail)
        ttk.Label(self.comparison_tab, text="Doble clic en una fila para leer sus valores completos.", style="Muted.TLabel").pack(anchor="w", pady=(7, 0))
        self._text("Seleccione un proyecto y una imagen. Los valores se leen de cada resultado guardado, con su escala y criterios originales.")

        footer = ttk.Frame(outer, padding=(0, 12, 0, 0))
        footer.pack(fill="x")
        self.progress = ttk.Progressbar(footer, mode="indeterminate", length=115)
        self.progress.pack(side="left", padx=(0, 12))
        ttk.Label(footer, textvariable=self.status, style="Muted.TLabel", wraplength=1000).pack(side="left", fill="x", expand=True)

    @staticmethod
    def _tree(parent, columns, headings, tree=False, height=8):
        wrapper = ttk.Frame(parent)
        wrapper.pack(fill="both", expand=True)
        view = ttk.Treeview(wrapper, columns=columns, show="tree headings" if tree else "headings", height=height, selectmode="browse")
        for key, (title, width) in headings.items():
            view.heading(key, text=title)
            view.column(key, width=width, minwidth=40, stretch=True)
        wrapper.rowconfigure(0, weight=1)
        wrapper.columnconfigure(0, weight=1)
        view.grid(row=0, column=0, sticky="nsew")
        scroll = ttk.Scrollbar(wrapper, orient="vertical", command=view.yview)
        scroll.grid(row=0, column=1, sticky="ns")
        horizontal = ttk.Scrollbar(wrapper, orient="horizontal", command=view.xview)
        horizontal.grid(row=1, column=0, sticky="ew")
        view.configure(yscrollcommand=scroll.set, xscrollcommand=horizontal.set)
        return view

    def _snapshot(self):
        if self.project and self.image and self.run:
            self._restore_history = (self.project.get("path"), image_selection_key(self.image), history_selection_key(self.run))
        self.projects = copy.deepcopy(self.catalog.list_projects())
        references = self.catalog.data.get("references", {})
        self.references = copy.deepcopy(list(references.values()) if isinstance(references, dict) else references)
        self._render_projects()

    def _search_changed(self, *_args):
        if self._search_id:
            self.root.after_cancel(self._search_id)
        self._search_id = self.root.after(150, self._render_projects)

    def _render_projects(self):
        self._search_id = None
        selected = self.project.get("path") if self.project else None
        self.project_tree.delete(*self.project_tree.get_children())
        self._project_items = {}
        for index, project in enumerate(self.projects):
            project_text = " ".join(str(project.get(key, "")) for key in ("name", "path", "project_id")).casefold()
            project_match = all(word in project_text for word in self.search.get().casefold().split())
            if self.search.get().strip() and not project_match and not matching_images(project, self.search.get()):
                continue
            ident = f"project{index}"
            self._project_items[ident] = project
            name = str(project.get("name") or project.get("project_id") or Path(project["path"]).name)
            if project.get("available") is False:
                name = "○ " + name
            images = project.get("images", [])
            self.project_tree.insert("", "end", iid=ident, text=name,
                                     values=(len(images), sum(len(i.get("runs", [])) for i in images)))
            if project.get("path") == selected:
                self.project_tree.selection_set(ident)
        self.count_label.configure(text=f"PROYECTOS  ·  {len(self._project_items)}")
        if not self.project_tree.selection() and self._project_items:
            self.project_tree.selection_set(next(iter(self._project_items)))
        elif not self._project_items:
            self._clear_project()

    def _clear_project(self):
        self.project = None
        self.study_button.configure(state="disabled")
        self.project_title.set("Su biblioteca de proyectos")
        self.project_detail.set("No hay coincidencias." if self.search.get() else "Añada una carpeta para comenzar.")
        self.image_tree.delete(*self.image_tree.get_children())
        self._clear_image()

    def _select_project(self, _event=None):
        selected = self.project_tree.selection()
        if not selected:
            return
        old_image = image_selection_key(self.image)
        previous = self.project.get("path") if self.project else None
        self.project = self._project_items[selected[0]]
        self.study_button.configure(state="normal" if self.project.get("available", True) and not self._busy else "disabled")
        self.project_title.set(str(self.project.get("name") or self.project.get("project_id")))
        images = self.project.get("images", [])
        counts = f"{len(images)} imágenes  ·  {sum(bool(i.get('revision_id') or i.get('revisions')) for i in images)} con revisión  ·  {sum(bool(i.get('runs')) for i in images)} con resultados"
        if self.project.get("available") is False:
            counts += "  ·  Sin conexión: resumen conservado"
        stamp = self.project.get("last_scanned") or self.project.get("scanned_at") or "sin actualizar"
        errors = self.project.get("errors", [])
        detail = f"{counts}\n{self.project.get('path', '')}\nÚltima lectura: {stamp}"
        if errors:
            detail += "\nIncidencias: " + "; ".join(str(e) for e in errors)
        self.project_detail.set(detail)
        self.image_tree.delete(*self.image_tree.get_children())
        self._image_items = {}
        self._clear_image()
        for index, item in enumerate(matching_images(self.project, self.search.get())):
            ident = f"image{index}"
            self._image_items[ident] = item
            runs = item.get("runs", [])
            state = "Revisar incidencias" if item.get("errors") else "Resultado disponible" if runs else "Revisión guardada" if item.get("revision_id") or item.get("revisions") else "Imagen registrada"
            revisions = item.get("revisions", [])
            rev_count = len(revisions) if isinstance(revisions, list) else revisions
            if not rev_count and item.get("revision_id"):
                rev_count = "≥ 1"
            self.image_tree.insert("", "end", iid=ident, values=(item.get("name") or item.get("image_id"), state,
                rev_count or "—", len(runs), "Disponible" if item.get("source_available") else "No localizada"))
            if self.project.get("path") == previous and image_selection_key(item) == old_image:
                self.image_tree.selection_set(ident)
        if not self.image_tree.selection() and self._image_items:
            self.image_tree.selection_set(next(iter(self._image_items)))

    def _clear_image(self):
        if self._busy in ("read", "compare"):
            self.cancel()
        self.image = self.run = self.report = None
        self.run_tree.delete(*self.run_tree.get_children())
        self._run_items = {}
        self.image_detail.set("Seleccione una imagen para consultar sus resultados.")
        self.reference_text.set("Referencia aceptada: ninguna seleccionada")
        self._comparison_run = None
        self._comparison_rows = {}
        self.comparison_heading.set("Elija un RUN íntegro como A y otro de una revisión distinta como B.")
        self.comparison_tree.delete(*self.comparison_tree.get_children())
        self.edit_button.configure(state="disabled")
        self._clear_result()

    def _select_image(self, _event=None):
        selected = self.image_tree.selection()
        if not selected:
            return
        self._clear_image()
        self.image = self._image_items[selected[0]]
        self.image_detail.set(f"{self.image.get('source_path') or 'Fuente no registrada'}\nRevisión actual: {self.image.get('revision_id') or 'sin revisión'}")
        self.edit_button.configure(state="normal" if self.project.get("available", True) and not self._busy else "disabled")
        reference = next((r for r in reversed(self.references) if reference_matches(r, self.project, self.image)), None)
        if reference:
            session = f"{reference['session_id']} · " if reference.get("session_id") else ""
            self.reference_text.set(f"Última referencia aceptada:\n{session}{reference.get('revision_id')}\n{reference.get('run_id')}")
        for index, entry in enumerate(revision_history(self.project, self.image)):
            ident = f"history{index}"
            self._run_items[ident] = entry
            labels = [entry["state"]] if entry["state"] else []
            if entry["entry_kind"] == "run" and any(reference_matches(r, self.project, self.image, entry) for r in self.references):
                labels.append("Aceptado")
            prefix = f"{entry['session_id']} · " if entry.get("session_id") else ""
            self.run_tree.insert("", "end", iid=ident, values=(prefix + str(entry["label"]), " · ".join(labels)))
            if (self._restore_history and self._restore_history[:2] == (self.project.get("path"), image_selection_key(self.image))
                    and self._restore_history[2] == history_selection_key(entry)):
                self.run_tree.selection_set(ident)
        if self._restore_history and self._restore_history[:2] == (self.project.get("path"), image_selection_key(self.image)):
            self._restore_history = None
        if not self._run_items:
            message = "Esta imagen todavía no tiene resultados guardados. Puede abrirla en Fiji y continuar su análisis individual."
            if self.image.get("errors"):
                message += "\n\nIncidencias de lectura:\n" + "\n".join(str(e) for e in self.image["errors"])
            self._text(message)
            self.run_status.set("Sin resultados guardados")
        else:
            total_runs = len(self.image.get("runs", []))
            self.run_status.set(f"{total_runs} resultados. Seleccione un RUN para consultarlo o una revisión para abrirla en Fiji.")

    def _clear_result(self):
        self.report = None
        self.accept_button.configure(state="disabled")
        self.compare_pin_button.configure(state="disabled")
        self.compare_button.configure(state="disabled")
        self.open_file_button.configure(state="disabled")
        self.file_tree.delete(*self.file_tree.get_children())
        self._file_items = {}
        self._photo = None
        self._revision_photo = None
        self.revision_details = None
        self.revision_heading.set("Seleccione una revisión del historial.")
        self.revision_preview.configure(image="", text="Imagen de trabajo guardada: no registrada")
        self._set_text(self.revision_text, "El nombre, comentario, imagen y parámetros se registran al guardar una revisión en el editor.")
        self.preview_label.configure(image="", text="Seleccione un PNG en Tablas y gráficos y ábralo.")
        self.run_status.set("Seleccione un resultado del historial.")
        self._text("Los valores se mostrarán tras comprobar el resultado seleccionado.")

    def _select_run(self, _event=None):
        selected = self.run_tree.selection()
        if not selected:
            return
        if self._busy and self._busy not in ("read", "compare"):
            self.status.set("Espere a que finalice la actualización o cancélela antes de abrir un resultado.")
            return
        if self._busy in ("read", "compare"):
            self.cancel()
        self.run = self._run_items[selected[0]]
        self._clear_result()
        self.image_detail.set(f"{self.image.get('source_path') or 'Fuente no registrada'}\nRevisión seleccionada para abrir: {self.run.get('revision_id')}")
        if self.run.get("entry_kind") == "revision":
            self.run_status.set("Revisión guardada sin resultado")
            self._text(f"Revisión: {self.run.get('revision_id')}\n\nEsta revisión no tiene un RUN guardado.\n\nPulse Abrir imagen en Fiji para recuperar esta revisión y continuar su análisis.")
            self.status.set(f"Revisión seleccionada: {self.run.get('revision_id')}")
            project, image, revision = copy.deepcopy(self.project), copy.deepcopy(self.image), copy.deepcopy(self.run)
            self._start_job("read", lambda cancel, _progress: {"details": read_revision_details(project, image, revision, cancel)}, self._show_selection)
            return
        path = self.run["path"]
        project, image, revision = copy.deepcopy(self.project), copy.deepcopy(self.image), copy.deepcopy(self.run)
        self.run_status.set(f"Comprobando {self.run.get('run_id')}…")
        def selected(cancel, _progress):
            report = read_run(path, cancel=cancel)
            revision_row = dict(revision)
            if project.get("kind") == "R9":
                revision_row["path"] = str(Path(path).parent.parent)
            return {"report": report, "details": read_revision_details(project, image, revision_row, cancel, verified_run=report)}
        self._start_job("read", selected, self._show_selection)

    def _show_selection(self, selected):
        self._show_revision_details(selected["details"])
        if selected.get("report"):
            self._show_result(selected["report"])
        else:
            self.tabs.select(self.workspace_tab)

    def _show_revision_details(self, details):
        self.revision_details = details
        self.revision_heading.set(details.get("title") or details.get("revision_id") or "Revisión")
        self._set_text(self.revision_text, details.get("text", "No registrado"))
        preview = details.get("preview")
        if preview:
            try:
                photo = tk.PhotoImage(master=self.root, data=preview["data"], format="png")
                scale = max(1, math.ceil(preview["width"] / 560), math.ceil(preview["height"] / 220))
                self._revision_photo = photo.subsample(scale, scale) if scale > 1 else photo
                self.revision_preview.configure(image=self._revision_photo, text="")
            except tk.TclError:
                self.revision_preview.configure(image="", text="La miniatura guardada no puede mostrarse.")
        else:
            self.revision_preview.configure(image="", text="Imagen de trabajo guardada: no registrada o no verificable")

    def _show_result(self, report):
        self.report = report
        verification = report.get("verification", {})
        ok = bool(verification.get("ok"))
        if ok:
            self.run_status.set("Integridad comprobada · Valores guardados, sin recalcular" if report.get("kind") == "R9"
                                else "Integridad comprobada · Descriptivos del RUN seleccionado")
        else:
            errors = verification.get("errors", [])
            self.run_status.set("Integridad no confirmada: " + str(errors[0]) if errors
                                else "Comprobación de integridad no completada")
        text = report.get("text") or "\n".join(f"{key}: {value}" for key, value in report.get("summary", {}).items())
        heading = f"{report.get('label') or 'Resultado individual'}\nRevisión: {report.get('revision_id')}\nRUN: {report.get('run_id')}\n\n"
        if report.get("kind") == "R9":
            summary = report.get("summary", {})
            fields = (("N_count_valid", "Cavidades para recuento"), ("N_size_valid", "Cavidades para tamaño"),
                      ("valid_area_um2", "Área válida (µm²)"), ("mean_diameter_nm", "Diámetro medio (nm)"),
                      ("median_diameter_nm", "Mediana (nm)"), ("density_N_per_um2", "Densidad superficial (µm⁻²)"))
            heading += "\n".join(f"{label}: {summary[key]}" for key, label in fields if key in summary) + "\n"
            if "scale_x_nm_px" in summary and "scale_y_nm_px" in summary:
                heading += f"Escala guardada X × Y (nm/píxel): {summary['scale_x_nm_px']} × {summary['scale_y_nm_px']}\n"
            if "include_uncertain" in summary:
                policy = {"1": "incluidas", "0": "excluidas"}.get(str(summary["include_uncertain"]), str(summary["include_uncertain"]))
                heading += f"Dudosas: {policy} (criterio guardado)\n"
            heading += "\nRegistro completo del resultado\n" + "─" * 35 + "\n"
        reference = next((r for r in reversed(self.references) if reference_matches(r, self.project, self.image, self.run)), None)
        if reference and reference.get("fingerprint") != report.get("fingerprint"):
            heading = "ATENCIÓN: el contenido difiere de la referencia aceptada en el catálogo.\n\n" + heading
        errors = verification.get("errors", [])
        if errors:
            heading = "No se puede confirmar la integridad de este RUN:\n" + "\n".join(str(e) for e in errors) + "\n\n" + heading
        self._text(heading + str(text))
        for index, item in enumerate(report.get("files", [])):
            if Path(item.get("path", "")).suffix.lower() not in OPEN_EXTENSIONS:
                continue
            ident = f"file{index}"
            self._file_items[ident] = item
            self.file_tree.insert("", "end", iid=ident, values=(item.get("name") or Path(item.get("path", "")).name,))
        self.accept_button.configure(state="normal" if ok else "disabled")
        self.open_file_button.configure(state="normal" if ok else "disabled")
        self.tabs.select(0)
        self.status.set(f"Resultado leído: {report.get('run_id')} · La referencia aceptada se elige de forma explícita.")
        self._comparison_buttons()

    def _text(self, value):
        self._set_text(self.summary, value)

    @staticmethod
    def _set_text(widget, value):
        widget.configure(state="normal")
        widget.delete("1.0", "end")
        widget.insert("1.0", value)
        widget.configure(state="disabled")

    def _comparison_buttons(self):
        ok = bool(not self._busy and self.report and self.report.get("kind") == "R9"
                  and self.report.get("verification", {}).get("ok"))
        self.compare_pin_button.configure(state="normal" if ok else "disabled")
        different = bool(ok and self._comparison_run and self.run and self._comparison_run.get("revision_id") != self.run.get("revision_id"))
        self.compare_button.configure(state="normal" if different else "disabled")

    def _pin_comparison(self):
        if self.run and self.report and self.report.get("verification", {}).get("ok") and self.report.get("kind") == "R9":
            self._comparison_run = copy.deepcopy(self.run)
            self.comparison_heading.set(f"A: {self.run.get('revision_id')} · {self.run.get('run_id')}\nSeleccione un RUN de otra revisión de esta imagen y pulse Comparar A con selección.")
            self._comparison_buttons()
            self.tabs.select(self.comparison_tab)

    def _compare(self):
        if not self._comparison_run or not self.run or self._busy:
            return
        left_path, right_path = self._comparison_run["path"], self.run["path"]
        self.status.set("Comprobando ambos resultados guardados antes de compararlos…")
        self._start_job("compare", lambda cancel, _progress: compare_runs(left_path, right_path, cancel), self._show_comparison)

    def _show_comparison(self, comparison):
        self.comparison_heading.set("\n".join(comparison["text"].splitlines()[:4]))
        self.comparison_tree.delete(*self.comparison_tree.get_children())
        self._comparison_rows = {}
        labels = {"equal": "Igual", "different": "Diferente", "unknown": "No registrado"}
        for index, row in enumerate(comparison["rows"]):
            ident = f"comparison{index}"
            self._comparison_rows[ident] = row
            self.comparison_tree.insert("", "end", iid=ident, values=(row["label"], row["left"], row["right"], labels[row["state"]]))
        self.tabs.select(self.comparison_tab)
        self.status.set("Comparación de dos revisiones de la misma imagen · Valores guardados, sin recalcular.")

    def _comparison_detail(self, _event=None):
        selection = self.comparison_tree.selection()
        if not selection:
            return
        row = self._comparison_rows.get(selection[0])
        if not row:
            return
        dialog = tk.Toplevel(self.root)
        dialog.title(row["label"])
        dialog.geometry("760x470")
        dialog.transient(self.root)
        frame = ttk.Frame(dialog, padding=14)
        frame.pack(fill="both", expand=True)
        text = tk.Text(frame, wrap="word", relief="flat", background="white", font=("Segoe UI", 10), padx=10, pady=10)
        text.pack(side="left", fill="both", expand=True)
        scroll = ttk.Scrollbar(frame, command=text.yview)
        scroll.pack(side="right", fill="y")
        text.configure(yscrollcommand=scroll.set)
        self._set_text(text, f"{row['label']}\n\nA · valor guardado\n{row['left']}\n\nB · valor guardado\n{row['right']}")

    def _project_study(self):
        if self.project and self.project.get("available", True) and not self._busy:
            from .project_study import show_project_study
            show_project_study(self.root, copy.deepcopy(self.project))

    def _set_busy(self, kind):
        self._busy = kind
        disabled = "disabled" if kind else "normal"
        for button in (self.add_button, self.refresh_button, self.locations_button, self.editor_new):
            button.configure(state=disabled)
        self.cancel_button.configure(state="normal" if kind in ("catalog", "read", "compare") else "disabled")
        self.study_button.configure(state="normal" if not kind and self.project and self.project.get("available", True) else "disabled")
        self.edit_button.configure(state="normal" if not kind and self.image and self.project.get("available", True) else "disabled")
        self.accept_button.configure(state="normal" if not kind and self.report and self.report.get("verification", {}).get("ok") else "disabled")
        self._comparison_buttons()
        if kind:
            self.progress.start(14)
        else:
            self.progress.stop()

    def _start_job(self, kind, work, complete):
        if self._busy or self._closed:
            return False
        self._generation += 1
        generation = self._generation
        cancel = self._cancel = threading.Event()
        self._set_busy(kind)

        def progress(*message):
            self._events.put((generation, "progress", " · ".join(str(v) for v in message), None))

        def worker():
            try:
                value = work(cancel, progress)
                self._events.put((generation, "done", value, complete))
            except Exception as exc:
                self._events.put((generation, "error", str(exc), None))
        threading.Thread(target=worker, daemon=True, name=f"cavity-library-{kind}").start()
        return True

    def _poll(self):
        if self._closed:
            return
        try:
            while True:
                generation, kind, value, callback = self._events.get_nowait()
                if generation != self._generation:
                    continue
                if kind == "progress":
                    self.status.set(value)
                else:
                    self._set_busy(None)
                    if self._cancel and self._cancel.is_set():
                        self.status.set("Operación cancelada. Se conserva la última biblioteca disponible.")
                    elif kind == "error":
                        self.status.set("No se pudo completar la operación.")
                        self.run_status.set("No se ha cargado el resultado." if self.run else "")
                        messagebox.showerror(TITLE, value, parent=self.root)
                    elif callback:
                        callback(value)
        except queue.Empty:
            pass
        self._poll_id = self.root.after(80, self._poll)

    def cancel(self):
        if self._cancel:
            self._cancel.set()
        if self._busy in ("read", "compare"):
            # Reading cannot mutate the catalogue. A new selection may start at once.
            self._generation += 1
            self._set_busy(None)
            self.run_status.set("Lectura cancelada")
        self.status.set("Cancelación solicitada…" if self._busy else "Lectura cancelada.")
        self.cancel_button.configure(state="disabled")

    def _add(self):
        path = filedialog.askdirectory(title="Seleccione un proyecto o una carpeta que contenga proyectos", parent=self.root, mustexist=True)
        if path:
            self.status.set("Buscando proyectos y leyendo sus índices…")
            self._start_job("catalog", lambda cancel, progress: self.catalog.add_location(path, cancel=cancel, on_progress=progress), self._catalog_updated)

    def refresh(self):
        self.status.set("Actualizando los proyectos localizados…")
        self._start_job("catalog", lambda cancel, progress: self.catalog.refresh(cancel=cancel, on_progress=progress), self._catalog_updated)

    def _catalog_updated(self, _result=None):
        self._snapshot()
        missing = sum(p.get("available") is False for p in self.projects)
        self.status.set(f"Biblioteca actualizada: {len(self.projects)} proyectos" + (f" · {missing} sin conexión, con resumen conservado." if missing else "."))

    def _locations(self):
        dialog = tk.Toplevel(self.root)
        dialog.title("Carpetas de la biblioteca")
        dialog.geometry("720x350")
        dialog.transient(self.root)
        dialog.grab_set()
        frame = ttk.Frame(dialog, padding=18)
        frame.pack(fill="both", expand=True)
        ttk.Label(frame, text="Carpetas consultadas", style="Heading.TLabel").pack(anchor="w")
        ttk.Label(frame, text="Quitar una carpeta solo cambia el catálogo local; conserva todos sus archivos.", style="Muted.TLabel").pack(anchor="w", pady=10)
        box = tk.Listbox(frame, font=("Segoe UI", 10), relief="solid", borderwidth=1)
        box.pack(fill="both", expand=True)
        locations = self.catalog.data.get("locations", [])
        for location in locations:
            box.insert("end", location.get("path") if isinstance(location, dict) else str(location))

        def remove():
            selection = box.curselection()
            if selection:
                path = box.get(selection[0])
                dialog.destroy()
                self._start_job("remove", lambda _cancel, _progress: self.catalog.remove_location(path), self._catalog_updated)
        ttk.Button(frame, text="Quitar carpeta seleccionada", command=remove).pack(side="left", pady=(12, 0))
        ttk.Button(frame, text="Cerrar", command=dialog.destroy).pack(side="right", pady=(12, 0))

    def _accept(self):
        if not self.report or not self.run or not self.image or not self.project:
            return
        report = copy.deepcopy(self.report)
        def accepted(_result):
            self._snapshot()
            self.status.set(f"Referencia aceptada: {report.get('revision_id')} / {report.get('run_id')}. Se guarda en el catálogo local.")
        self.status.set("Comprobando y registrando la referencia seleccionada…")
        self._start_job("reference", lambda _cancel, _progress: self.catalog.accept_reference(report), accepted)

    def _open_file(self):
        selection = self.file_tree.selection()
        if not selection or not self.report or not self.run:
            return
        try:
            path = safe_result_path(self.report, self._file_items[selection[0]], self.run["path"])
            if path.suffix.lower() == ".png":
                self._preview(path)
            else:
                os.startfile(str(path))
        except Exception as exc:
            messagebox.showerror("No se puede abrir el archivo", str(exc), parent=self.root)

    def _preview(self, path):
        if path.stat().st_size > 32 * 1024 * 1024:
            os.startfile(str(path))
            self.status.set(f"PNG grande abierto en el visor externo: {path.name}")
            return
        with path.open("rb") as stream:
            header = stream.read(24)
        if len(header) != 24 or header[:8] != b"\x89PNG\r\n\x1a\n":
            raise ValueError("El archivo seleccionado no es un PNG válido.")
        width, height = struct.unpack(">II", header[16:24])
        if not width or not height:
            raise ValueError("El PNG tiene dimensiones no válidas.")
        if width * height > 24_000_000:
            os.startfile(str(path))
            self.status.set(f"PNG grande abierto en el visor externo: {path.name}")
            return
        photo = tk.PhotoImage(master=self.root, file=str(path))
        scale = max(1, math.ceil(width / max(350, self.preview_tab.winfo_width() - 30)),
                    math.ceil(height / max(240, self.preview_tab.winfo_height() - 35)))
        self._photo = photo.subsample(scale, scale) if scale > 1 else photo
        self.preview_label.configure(image=self._photo, text="")
        self.tabs.select(self.preview_tab)
        self.status.set(f"Gráfico guardado: {path.name}")

    def _launch(self, **kwargs):
        if self.launcher is None:
            from .launch import launch_editor
            launcher = launch_editor
        else:
            launcher = self.launcher
        self.status.set("Abriendo el editor de imágenes individuales…")
        self._start_job("launch", lambda _cancel, _progress: launcher(**kwargs),
                        lambda value: self.status.set(value.get("message") if isinstance(value, dict) and value.get("message") else "Editor solicitado. Continúe el trabajo sobre la imagen en Fiji."))

    def _new_editor(self):
        self._launch()

    def _edit(self):
        if self.project and self.image:
            self._launch(project_path=self.project["path"], image_id=self.image.get("image_id"),
                         revision_id=self.run.get("revision_id") if self.run else self.image.get("revision_id"),
                         project_kind=self.project.get("kind"))

    def close(self):
        self._closed = True
        self._generation += 1
        if self._cancel:
            self._cancel.set()
        for callback in (self._poll_id, self._search_id):
            if callback:
                self.root.after_cancel(callback)
        self.root.destroy()


def main(argv=None):
    parser = argparse.ArgumentParser(description="Biblioteca local de proyectos Cavity TEM Light")
    parser.add_argument("--catalog", type=Path, help="Archivo del catálogo local")
    parser.add_argument("--add", action="append", default=[], metavar="CARPETA", help="Incorporar una carpeta de proyectos al arrancar")
    parser.add_argument("--refresh", action="store_true", help="Actualizar la biblioteca después de mostrarla")
    args = parser.parse_args(argv)
    root = tk.Tk()
    try:
        catalog = Catalog(state_path=args.catalog)
        window = LibraryWindow(root, catalog)
    except Exception as exc:
        root.withdraw()
        messagebox.showerror(TITLE, f"No se pudo abrir el catálogo local.\n\n{exc}", parent=root)
        root.destroy()
        return 1
    if args.add:
        paths = tuple(args.add)
        def add_all(cancel, progress):
            for path in paths:
                if cancel.is_set():
                    break
                catalog.add_location(path, cancel=cancel, on_progress=progress)
        root.after(50, lambda: window._start_job("catalog", add_all, window._catalog_updated))
    elif args.refresh:
        root.after(50, window.refresh)
    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
