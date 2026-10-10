"""A small desktop/CLI reader; all project access is read-only."""
from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
import hashlib
import html
import json
from pathlib import Path
import platform
import queue
import sys
import threading
import uuid

from cavity_tem_light_p1.canonical_json import loads_canonical_json
from cavity_tem_light_p1.errors import ValidationError
from cavity_tem_light_p1.path_safety import plain_directory, plain_file, stable_plain_bytes
from cavity_tem_light_p1.run_consumer import verify_run_directory
from cavity_tem_light_p1.run_context import load_run_context
from cavity_tem_light_p1.run_disposition import require_scientific_eligibility
from cavity_tem_light_p1.science import compute_stats, zero_event_summary

from . import __version__

LIMITATIONS = (
    "Vista técnica de resultados descriptivos, sin validación científica de la aplicación. "
    "Cada informe corresponde a un único RUN seleccionado expresamente. "
    "Las sesiones y sus clones no son réplicas experimentales independientes. "
    "No se calculan intervalos de confianza, inferencia, repetibilidad, profundidad ni modelos 3D. "
    "Solo se admiten RUN de Prompt 3 dentro de su proyecto, con evidencia de escala disponible. "
    "La verificación corresponde a la fecha indicada; una invalidación posterior requiere volver a abrir el RUN."
)
POLICIES = {"primary": ("Primario: confirmadas", {"confirmed"}),
            "sensitivity": ("Sensibilidad: confirmadas + inciertas", {"confirmed", "uncertain"})}


def _json(value):
    return json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False,
                      default=lambda item: str(item) if isinstance(item, (Decimal, Path)) else _unsupported(item))


def _unsupported(item):
    raise TypeError(f"Tipo no serializable: {type(item).__name__}")


def _project_for_run(path):
    path = plain_directory(path, label="RUN seleccionado")
    if path.parent.name != "runs":
        raise ValidationError("Seleccione la carpeta RUN dentro de la carpeta runs de una sesión.")
    session = plain_directory(path.parent.parent, label="Sesión del RUN")
    projects = [parent for parent in session.parents if (parent / "project.json").is_file()]
    if len(projects) != 1:
        raise ValidationError("No se encuentra un único proyecto schema 2 para este RUN.")
    return path, session, plain_directory(projects[0], label="Proyecto del RUN")


def describe_verified_run(run):
    """Project the already-verified policy fields; reuse the reference statistics."""
    records = []
    for raw in run.object_rows:
        row = dict(raw)
        for endpoint in ("count", "size", "position"):
            for name in (f"{endpoint}_valid", f"primary_{endpoint}_included", f"sensitivity_{endpoint}_included"):
                row[name] = int(row[name])
        if row["size_valid"]:
            row["equivalent_diameter_nm"] = Decimal(row["equivalent_diameter_nm"])
        records.append(row)
    result = {}
    for key, (label, classes) in POLICIES.items():
        selected = [row for row in records if row["cavity_class"] in classes]
        summary = zero_event_summary(selected, net_area_nm2=run.manifest["net_area_nm2"])
        counts = {endpoint: sum(row[f"{key}_{endpoint}_included"] for row in records)
                  for endpoint in ("count", "size", "position")}
        if any(summary[f"N_{endpoint}_valid"] != count for endpoint, count in counts.items()):
            raise ValidationError("La selección de clases no reconcilia con los indicadores de inclusión.")
        sizes = [row["equivalent_diameter_nm"] for row in selected if row["size_valid"]]
        result[key] = {"label": label, "count": counts["count"], "size_count": counts["size"],
                       "position_count": counts["position"], "density_N_per_um2": summary["density_N_per_um2"],
                       "diameter_nm": compute_stats(sizes)}
    return result


def analyze_run(run_dir, progress=lambda _message: None):
    progress("Comprobando proyecto y sesión…")
    path, session, project = _project_for_run(run_dir)
    context = load_run_context(project, session)
    progress("Verificando integridad del RUN y su registro…")
    run = verify_run_directory(path, run_context=context, registry_path=session / "run_registry.json")
    revision_path = session / "revisions" / f"REV_{run.manifest['revision_id']}" / "revision_manifest.json"
    revision = loads_canonical_json(stable_plain_bytes(
        plain_file(revision_path, label="Revisión del RUN", single_link=True), label="Revisión del RUN"))
    if revision.get("schema") != "CTL_P2A_REVISION_MANIFEST_V2":
        raise ValidationError("Esta vista admite RUN de Prompt 3. Los RUN anteriores requieren otro adaptador.")
    progress("Verificando escala, revisión y estado científico…")
    # This existing gate checks external invalidations AND persisted P3 scale/source/revision authority.
    require_scientific_eligibility(run, session_root=session)
    progress("Preparando resultados primarios y de sensibilidad…")
    return {
        "schema": "CTL_DESCRIPTIVE_REPORT_V1", "application_version": __version__,
        "status": "TECHNICAL_PREVIEW", "scientific_validation": False,
        "verified_at_utc": datetime.now(timezone.utc).isoformat(),
        "environment": {"python": platform.python_version(), "platform": platform.platform()},
        "verification": "RUN_INTEGRITY_REGISTRY_AND_P3_SCIENTIFIC_ELIGIBILITY_PASS",
        "source_project": str(project), "source_session": str(session), "source_run": str(path),
        "run_manifest_sha256": run.manifest_sha256,
        "source_manifest": dict(run.manifest), "pooling": "NONE_SINGLE_EXPLICIT_RUN",
        "summaries": describe_verified_run(run), "object_columns": list(run.object_header),
        "objects": [dict(row) for row in run.object_rows], "limitations": LIMITATIONS,
    }


def _display(value):
    if value is None:
        return "No definido"
    return f"{value:.7g}" if isinstance(value, (float, Decimal)) else str(value)


def report_text(report):
    manifest = report["source_manifest"]
    lines = ["Cavity Light · Resultados descriptivos", "",
             f"RUN: {manifest['run_id']}", f"Imagen: {manifest.get('image_id', manifest['image_uid'])}",
             f"Sesión: {manifest.get('analysis_session_id', manifest['analysis_session_uid'])}",
             f"Revisión: {manifest['revision_id']}", f"Área neta (nm²): {manifest['net_area_nm2']}",
             f"Verificado: {report['verified_at_utc']}", ""]
    for summary in report["summaries"].values():
        size = summary["diameter_nm"]
        lines.extend([summary["label"], f"  Recuento: {summary['count']} · Tamaño: {summary['size_count']} · Posición: {summary['position_count']}",
                      f"  Densidad areal (1/µm²): {_display(summary['density_N_per_um2'])}",
                      f"  Diámetro equivalente (nm): media {_display(size['mean'])} · mediana {_display(size['p50'])}",
                      f"  P25–P75: {_display(size['p25'])} – {_display(size['p75'])}", ""])
    lines.extend(["Alcance", LIMITATIONS, "", f"Origen: {report['source_run']}",
                  f"SHA-256 del manifiesto: {report['run_manifest_sha256']}"])
    return "\n".join(lines)


def _csv_cell(value):
    # Protect spreadsheet users from formulas in text metadata without altering numeric cells.
    if isinstance(value, str) and value.lstrip().startswith(("=", "+", "-", "@")):
        try:
            if Decimal(value).is_finite():
                return value
        except InvalidOperation:
            pass
        return "'" + value
    return value


def export_report(report, output_dir):
    """Write a new report folder outside any enclosing schema-2 project; never overwrite."""
    target = plain_directory(output_dir, label="Carpeta de informes")
    source = Path(report["source_project"]).resolve(strict=True)
    if target == source or source in target.parents or any((p / "project.json").exists() for p in (target, *target.parents)):
        raise ValidationError("Elija una carpeta de informes fuera de los proyectos de análisis.")
    folder = target / ("Cavity_informe_" + datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_") + uuid.uuid4().hex[:8])
    folder.mkdir()
    (folder / "informe.json").write_text(_json(report) + "\n", encoding="utf-8", newline="\n")
    body = html.escape(report_text(report))
    document = ("<!doctype html><html lang='es'><meta charset='utf-8'><title>Cavity Light · Informe</title>"
                "<style>body{max-width:1000px;margin:40px auto;padding:20px;background:#f4f7fa;color:#172938;"
                "font:16px/1.6 system-ui}pre{white-space:pre-wrap;background:white;padding:28px;border-radius:12px;"
                "font:inherit}h1{color:#11626e}</style><h1>Cavity Light</h1><pre>" + body + "</pre></html>")
    (folder / "informe.html").write_text(document, encoding="utf-8", newline="\n")
    with (folder / "resumen.csv").open("x", encoding="utf-8-sig", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(["run_uid", "run_manifest_sha256", "poblacion", "N_recuento", "N_tamano", "N_posicion",
                         "densidad_1_por_um2", "diametro_media_nm", "diametro_mediana_nm", "diametro_p25_nm", "diametro_p75_nm"])
        for summary in report["summaries"].values():
            sizes = summary["diameter_nm"]
            writer.writerow([report["source_manifest"]["run_uid"], report["run_manifest_sha256"], summary["label"],
                             summary["count"], summary["size_count"], summary["position_count"], summary["density_N_per_um2"],
                             sizes["mean"], sizes["p50"], sizes["p25"], sizes["p75"]])
    with (folder / "objetos.csv").open("x", encoding="utf-8-sig", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(report["object_columns"])
        for row in report["objects"]:
            writer.writerow([_csv_cell(row[field]) for field in report["object_columns"]])
    hashes = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(folder.iterdir())}
    (folder / "SHA256.json").write_text(_json(hashes) + "\n", encoding="utf-8", newline="\n")
    return folder


def error_text(error):
    details = getattr(error, "details", {})
    message = "No se ha completado la operación.\n\n" + str(error)
    if details:
        message += "\n\n" + _json(details)
    message += "\n\nSeleccione un RUN completo de Prompt 3 dentro de su proyecto. No se sustituye por otro RUN automáticamente."
    return message


def launch_gui():
    import tkinter as tk
    from tkinter import filedialog, messagebox, scrolledtext, ttk

    window = tk.Tk()
    window.title("Cavity Light · Resultados")
    window.geometry("960x730")
    window.minsize(720, 520)
    pending = queue.Queue()
    state = {"report": None, "busy": False}
    path = tk.StringVar()
    status = tk.StringVar(value="Seleccione un RUN de Prompt 3 para verificarlo y ver sus resultados.")
    container = ttk.Frame(window, padding=18)
    container.pack(fill="both", expand=True)
    ttk.Label(container, text="Resultados descriptivos", font=("Segoe UI", 18, "bold")).pack(anchor="w")
    ttk.Label(container, text="Primario y sensibilidad · Un RUN por informe · Solo lectura").pack(anchor="w", pady=(0, 12))
    entry = ttk.Entry(container, textvariable=path)
    entry.pack(fill="x")
    controls = ttk.Frame(container)
    controls.pack(fill="x", pady=8)
    output = scrolledtext.ScrolledText(container, wrap="word", font=("Segoe UI", 10), state="disabled")
    output.pack(fill="both", expand=True)
    progress_bar = ttk.Progressbar(container, mode="indeterminate")
    progress_bar.pack(fill="x", pady=(8, 4))
    ttk.Label(container, textvariable=status, wraplength=880).pack(anchor="w")

    def set_output(text):
        output.configure(state="normal")
        output.delete("1.0", "end")
        output.insert("end", text)
        output.configure(state="disabled")

    def work(action):
        if state["busy"]:
            return
        state["busy"] = True
        for button in buttons:
            button.configure(state="disabled")
        entry.configure(state="disabled")
        progress_bar.start()
        def worker():
            try:
                pending.put(("done", action()))
            except Exception as exc:
                pending.put(("error", error_text(exc)))
        threading.Thread(target=worker, daemon=True, name="CavityStatsReader").start()

    def load():
        selected = path.get().strip()
        if not selected:
            choose()
            return
        state["report"] = None
        set_output("Verificando el RUN seleccionado…")
        work(lambda: ("loaded", analyze_run(selected, lambda text: pending.put(("progress", text)))))

    def choose():
        selected = filedialog.askdirectory(title="Seleccione la carpeta RUN completa")
        if selected:
            path.set(selected)
            load()

    def save():
        if state["report"] is None:
            return
        selected = filedialog.askdirectory(title="Carpeta de informes fuera del proyecto")
        if selected:
            status.set("Exportando la instantánea verificada…")
            work(lambda: ("exported", export_report(state["report"], selected)))

    buttons = [ttk.Button(controls, text="Elegir RUN…", command=choose),
               ttk.Button(controls, text="Verificar y mostrar", command=load),
               ttk.Button(controls, text="Exportar HTML, CSV y JSON…", command=save, state="disabled")]
    for button in buttons:
        button.pack(side="left", padx=(0, 8))

    def poll():
        try:
            while True:
                kind, value = pending.get_nowait()
                if kind == "progress":
                    status.set(value)
                    continue
                state["busy"] = False
                progress_bar.stop()
                entry.configure(state="normal")
                for button in buttons[:2]:
                    button.configure(state="normal")
                buttons[2].configure(state="normal" if state["report"] else "disabled")
                if kind == "error":
                    status.set("La operación no se ha completado. Revise el detalle.")
                    messagebox.showerror("Cavity Light", value)
                elif value[0] == "loaded":
                    state["report"] = value[1]
                    buttons[2].configure(state="normal")
                    set_output(report_text(value[1]))
                    status.set("RUN verificado. Puede exportar una instantánea del informe.")
                else:
                    status.set(f"Informe guardado: {value[1]}")
                    messagebox.showinfo("Informe guardado", str(value[1]))
        except queue.Empty:
            pass
        window.after(120, poll)
    set_output("1. Pulse «Elegir RUN» y seleccione la carpeta del resultado que desea consultar.\n\n"
               "2. Espere a que termine la verificación. Aparecerán el recuento, la densidad y los tamaños.\n\n"
               "3. Pulse «Exportar HTML, CSV y JSON» para guardar un informe fuera del proyecto.\n\n"
               "La lectura conserva los datos originales. Cada informe corresponde a un único resultado; "
               "esta versión ofrece estadística descriptiva.")
    window.after(120, poll)
    window.mainloop()


def main(argv=None):
    parser = argparse.ArgumentParser(description="Cavity Light: lector descriptivo de RUN Prompt 3 verificados")
    parser.add_argument("--run-dir", help="RUN elegido expresamente dentro de su proyecto")
    parser.add_argument("--output-dir", help="Carpeta existente fuera del proyecto para el informe")
    args = parser.parse_args(argv)
    if args.output_dir and not args.run_dir:
        parser.error("--output-dir requiere --run-dir")
    try:
        if not args.run_dir:
            launch_gui()
        else:
            report = analyze_run(args.run_dir)
            print(report_text(report))
            if args.output_dir:
                print("\nInforme guardado:", export_report(report, args.output_dir))
        return 0
    except Exception as exc:
        print(error_text(exc), file=sys.stderr)
        return 2
