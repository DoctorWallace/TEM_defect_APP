"""Explicit, read-only project studies from verified and frozen R9 results.

Different fields are pooled by summing counts and sampled areas. Diameter
statistics use the individual size-valid objects, never means of field means.
Revisions can also be compared, but comparison never pools them.
"""
from __future__ import annotations

import copy
import csv
from decimal import Decimal, InvalidOperation
import hashlib
import html
import io
import json
import math
from pathlib import Path
import queue
import re
import shutil
import statistics
import threading
import uuid

from .readers import (ScanCancelled, _r9_saved_number_matches, check_cancel,
                      path_key, plain_path, read_bytes, read_run, utc_now)

LIMITATIONS = (
    "Estudio descriptivo; la integridad comprobada no equivale a validación científica. "
    "La independencia espacial de las zonas la confirma el usuario; no se comprueba el solapamiento. "
    "Los diámetros proceden de las cavidades válidas para tamaño. "
    "No se calculan modelos 3D, intervalos de confianza ni inferencia entre muestras. "
    "Se conserva el protocolo de cada RUN: no se recalculan sus cavidades ni su área. "
    "Se comprueban los hashes guardados del RUN y la revisión; no los píxeles de las fuentes originales."
)
PROTOCOL_LABELS = {
    "method_version": "Versión del método", "geometry": "Geometría",
    "area_method": "Método de área", "size_rule": "Regla de tamaño",
    "size_classes_nm": "Límites de tamaño (nm)", "image_mode": "Modo de imagen",
    "include_uncertain": "Incluir dudosas", "band_mode": "Modo de bandas",
    "band_width_nm": "Ancho de banda (nm)", "configured_band_count": "Bandas configuradas",
    "feature_distance_bin_nm": "Intervalo de distancia (nm)",
    "foil_thickness_nm": "Espesor (nm)", "thickness_method": "Método de espesor",
    "linear_length_domain": "Dominio de longitud",
}


def _number(value, label, *, positive=False, integer=False):
    try:
        if isinstance(value, bool) or value is None or str(value).strip() == "":
            raise InvalidOperation
        number = Decimal(str(value))
        if not number.is_finite() or not math.isfinite(float(number)):
            raise InvalidOperation
        if positive and number <= 0 or not positive and number < 0:
            raise InvalidOperation
        if integer and number != number.to_integral_value():
            raise InvalidOperation
    except (InvalidOperation, ValueError, OverflowError) as exc:
        raise ValueError(f"Metadato guardado no válido: {label}.") from exc
    return int(number) if integer else number


def _flag(value, label):
    result = _number(value, label, integer=True)
    if result not in (0, 1):
        raise ValueError(f"Metadato guardado no válido: {label}.")
    return result


def _text(value, label):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"Falta evidencia guardada: {label}.")
    return value.strip()


def _evidence_bytes(report, name):
    matches = [entry for entry in report["files"] if entry["name"] == name]
    if len(matches) != 1:
        raise ValueError(f"Falta evidencia verificada: {name}.")
    data = read_bytes(matches[0]["path"])
    if hashlib.sha256(data).hexdigest() != matches[0]["sha256"]:
        raise ValueError(f"El archivo cambió después de comprobar el RUN: {name}.")
    return data


def _same_number(saved, manifest, label):
    try:
        if not _r9_saved_number_matches(str(saved), manifest):
            raise InvalidOperation
    except (InvalidOperation, ValueError, TypeError, OverflowError) as exc:
        raise ValueError(f"Metadatos congelados contradictorios: {label}.") from exc


def load_study_run(path, *, project=None, image=None, run=None, cancel=None):
    """Verify one chosen RUN and load its own objects/method, never current settings."""
    report = read_run(path, cancel=cancel)
    check_cancel(cancel)
    if not report.get("verification", {}).get("ok"):
        raise ValueError("Integridad no confirmada: " + "; ".join(report["verification"].get("errors", [])))
    if report["kind"] != "R9":
        raise ValueError("Este estudio admite RUN R9 con protocolo congelado. Los resultados P3 se consultan individualmente.")
    if project is not None:
        if (report["project_uid"] != project.get("project_uid") or
                report["project_id"] != project.get("project_id") or
                path_key(report["project_path"]) != path_key(project["path"])):
            raise ValueError("El RUN ya no corresponde al proyecto seleccionado; actualice la biblioteca.")
    if image is not None:
        source = image.get("metadata", {}).get("source_sha256")
        if report["image_id"] != image.get("image_id") or not source or source != report["manifest"]["image"]["sha256"]:
            raise ValueError("La referencia de imagen/fuente no coincide; actualice la biblioteca.")
    if run is not None:
        if (report["run_id"] != run.get("run_id") or report["revision_id"] != run.get("revision_id") or
                path_key(report["path"]) != path_key(run["path"])):
            raise ValueError("La referencia de RUN/revisión cambió; actualice la biblioteca.")
        if run.get("fingerprint") and run["fingerprint"] != report["fingerprint"]:
            raise ValueError("El RUN cambió desde su selección; vuelva a comprobarlo.")
    summary, manifest = report["summary"], report["manifest"]
    method = json.loads(_evidence_bytes(report, "analysis_method.json").decode("utf-8-sig"))
    if not isinstance(method, dict):
        raise ValueError("El método guardado no es un objeto JSON.")
    context = manifest.get("scientific_context", {})
    sample = _text(summary.get("sample_name"), "muestra")
    condition = _text(summary.get("experimental_condition"), "condición experimental")
    if sample != context.get("sample") or condition != context.get("condition"):
        raise ValueError("La muestra/condición no coincide en el resultado guardado.")
    mode = _text(summary.get("image_mode"), "modo de imagen")
    if mode not in ("with_surface", "without_surface") or mode != manifest.get("analysis_mode"):
        raise ValueError("Modo de imagen guardado inconsistente.")
    scale = manifest.get("scale", {})
    if _flag(scale.get("confirmed"), "escala confirmada") != 1:
        raise ValueError("La escala no estaba confirmada en este RUN.")
    sx = _number(summary.get("scale_x_nm_px"), "escala X", positive=True)
    sy = _number(summary.get("scale_y_nm_px"), "escala Y", positive=True)
    _same_number(sx, scale.get("active_nm_per_px_x"), "escala X")
    _same_number(sy, scale.get("active_nm_per_px_y"), "escala Y")
    area = _number(summary.get("valid_area_nm2"), "área válida", positive=True)
    count = _number(summary.get("N_count_valid"), "recuento", integer=True)
    size_count = _number(summary.get("N_size_valid"), "recuento para tamaño", integer=True)
    source_hash = _text(manifest.get("image", {}).get("sha256"), "hash de fuente").lower()
    if not re.fullmatch(r"[a-f0-9]{64}", source_hash):
        raise ValueError("Hash de fuente no válido.")
    classes = method.get("size_classes_nm")
    if not isinstance(classes, list):
        raise ValueError("Faltan los límites de clasificación de tamaño guardados.")
    classes = [_number(value, "límite de tamaño", positive=True) for value in classes]
    if any(right <= left for left, right in zip(classes, classes[1:])):
        raise ValueError("Límites de clasificación de tamaño no crecientes.")
    include = _flag(manifest.get("settings", {}).get("include_uncertain"), "incluir dudosas")
    if include != _flag(summary.get("include_uncertain"), "incluir dudosas"):
        raise ValueError("La inclusión de dudosas guardada es contradictoria.")
    thickness = _number(summary.get("foil_thickness_nm"), "espesor")
    _same_number(thickness, manifest.get("thickness", {}).get("nm"), "espesor")
    _same_number(thickness, method.get("foil_thickness_nm"), "espesor del método")
    band_mode = _text(method.get("band_mode"), "modo de bandas")
    if band_mode not in ("count", "width"):
        raise ValueError("Modo de bandas desconocido.")
    band_width = _number(method.get("band_width_nm"), "ancho de banda", positive=True)
    _same_number(band_width, manifest.get("bands", {}).get("width_nm"), "ancho de banda")
    band_count = _number(method.get("bands_in_image"), "bandas en imagen", integer=True)
    configured_count = (_number(manifest.get("bands", {}).get("count"), "bandas configuradas", positive=True, integer=True)
                        if band_mode == "count" else None)
    feature_bin = _number(manifest.get("settings", {}).get("feature_distance_bin_nm"), "intervalo de distancia", positive=True)
    protocol = {
        "method_version": _text(method.get("version"), "versión del método"),
        "geometry": _text(method.get("geometry"), "geometría"),
        "area_method": _text(method.get("area_method"), "método de área"),
        "size_rule": _text(method.get("size_rule"), "regla de tamaño"),
        "linear_length_domain": _text(method.get("linear_length_domain"), "dominio de longitud"),
        "size_classes_nm": [str(value) for value in classes], "image_mode": mode,
        "include_uncertain": include, "band_mode": band_mode,
        "band_width_nm": str(band_width), "configured_band_count": configured_count,
        "feature_distance_bin_nm": str(feature_bin), "foil_thickness_nm": str(thickness),
        "thickness_method": str(manifest.get("thickness", {}).get("method", "")),
    }
    objects = list(csv.DictReader(io.StringIO(_evidence_bytes(report, "cavity_objects.tsv").decode("utf-8-sig")), delimiter="\t"))
    counted, diameters, size_objects = 0, [], []
    for row in objects:
        check_cancel(cancel)
        included = _flag(row.get("count_valid"), "count_valid de " + str(row.get("cavity_id", "")))
        sized = _flag(row.get("size_valid"), "size_valid de " + str(row.get("cavity_id", "")))
        if sized and not included:
            raise ValueError("Una cavidad válida para tamaño no es válida para recuento.")
        counted += included
        if sized:
            diameter = float(_number(row.get("equivalent_diameter_nm"), "diámetro de " + str(row.get("cavity_id", "")), positive=True))
            diameters.append(diameter)
            size_objects.append({"cavity_id": row["cavity_id"], "equivalent_diameter_nm": diameter})
    if counted != count or len(diameters) != size_count:
        raise ValueError("El recuento guardado no coincide con las cavidades incluidas.")
    return {
        "project_id": report["project_id"], "project_uid": report["project_uid"],
        "project_path": report["project_path"], "image_id": report["image_id"],
        "revision_id": report["revision_id"], "run_id": report["run_id"],
        "run_path": report["path"], "fingerprint": report["fingerprint"],
        "source_sha256": source_hash, "sample_name": sample, "experimental_condition": condition,
        "count": count, "size_count": size_count, "valid_area_nm2": str(area),
        "scale_x_nm_px": str(sx), "scale_y_nm_px": str(sy), "bands_in_image": band_count,
        "protocol": protocol, "diameters_nm": diameters, "size_objects": size_objects,
        "saved_summary": dict(summary), "saved_method": copy.deepcopy(method),
        "saved_manifest": copy.deepcopy(manifest), "checked_at": report["verification"]["checked_at"],
    }


def diameter_statistics(diameters):
    values = sorted(diameters)
    def percentile(fraction):
        if not values:
            return None
        position = (len(values) - 1) * fraction
        low, high = math.floor(position), math.ceil(position)
        return values[low] + (position - low) * (values[high] - values[low])
    return {"n": len(values), "mean_nm": statistics.fmean(values) if values else None,
            "std_sample_nm": statistics.stdev(values) if len(values) > 1 else None,
            "median_nm": percentile(.5), "q25_nm": percentile(.25), "q75_nm": percentile(.75),
            "min_nm": values[0] if values else None, "max_nm": values[-1] if values else None}


def _protocol_differences(left, right):
    differences = []
    for key, label in PROTOCOL_LABELS.items():
        a, b = left["protocol"][key], right["protocol"][key]
        if key in ("band_width_nm", "feature_distance_bin_nm", "foil_thickness_nm"):
            equal = Decimal(a) == Decimal(b)
        elif key == "size_classes_nm":
            equal = [Decimal(v) for v in a] == [Decimal(v) for v in b]
        else:
            equal = a == b
        if not equal:
            differences.append(label)
    return differences


def build_study(records, *, mode="combine", non_overlapping_confirmed=False):
    """Combine compatible fields, or compare explicitly chosen RUNs without pooling."""
    if mode not in ("combine", "compare") or len(records) < 2:
        raise ValueError("Seleccione al menos dos RUN para combinar zonas o comparar revisiones.")
    first = records[0]
    seen_runs, images, sources = set(), set(), set()
    differences = []
    for record in records:
        identity = (record["project_uid"], record["project_id"], path_key(record["project_path"]))
        if identity != (first["project_uid"], first["project_id"], path_key(first["project_path"])):
            raise ValueError("Todos los RUN deben pertenecer al mismo proyecto.")
        if not all(identity[:2]):
            raise ValueError("Falta la identidad del proyecto.")
        run_key = path_key(record["run_path"])
        if run_key in seen_runs:
            raise ValueError("El mismo RUN está seleccionado más de una vez.")
        seen_runs.add(run_key)
        mismatch = _protocol_differences(first, record)
        if (record["sample_name"], record["experimental_condition"]) != (first["sample_name"], first["experimental_condition"]):
            mismatch += ["Muestra/condición"]
        if mismatch:
            differences.append({"image_id": record["image_id"], "run_id": record["run_id"], "fields": mismatch})
        if mode == "combine":
            if record["image_id"] in images:
                raise ValueError("Seleccione un único RUN por imagen; las revisiones de una imagen no son zonas independientes.")
            if record["source_sha256"] in sources:
                raise ValueError("Dos imágenes tienen la misma fuente SHA-256; no se pueden contar como zonas distintas.")
        images.add(record["image_id"])
        sources.add(record["source_sha256"])
    if mode == "combine" and differences:
        labels = sorted({field for item in differences for field in item["fields"]})
        raise ValueError("Protocolos incompatibles: " + ", ".join(labels) + ". Compare los RUN o seleccione un grupo compatible.")
    if mode == "combine" and not non_overlapping_confirmed:
        raise ValueError("Confirme que las zonas seleccionadas son distintas y no se solapan antes de combinarlas.")
    result = {"schema": "CTL_PROJECT_STUDY_V1", "mode": mode, "created_at": utc_now(),
              "project_id": first["project_id"], "project_uid": first["project_uid"],
              "scientific_validation": False, "non_overlapping_confirmed_by_user": bool(non_overlapping_confirmed) if mode == "combine" else False,
              "protocol_differences": differences, "limitations": LIMITATIONS,
              "records": copy.deepcopy(records), "combined": None}
    if mode == "combine":
        area = sum((Decimal(record["valid_area_nm2"]) for record in records), Decimal(0))
        count = sum(record["count"] for record in records)
        if not area.is_finite() or area <= 0:
            raise ValueError("Área combinada no válida.")
        diameters = [value for record in records for value in record["diameters_nm"]]
        result["combined"] = {"image_count": len(records), "N_count_valid": count,
                              "N_size_valid": len(diameters), "valid_area_nm2": str(area),
                              "valid_area_um2": str(area / Decimal(1000000)),
                              "density_N_per_um2": str(Decimal(count) * Decimal(1000000) / area),
                              "diameter": diameter_statistics(diameters)}
    return result


def _display(value):
    if value is None:
        return "No definido"
    if isinstance(value, float):
        return f"{value:.8g}"
    return str(value)


def study_text(study):
    title = "Estudio combinado de zonas" if study["mode"] == "combine" else "Comparación de revisiones/resultados"
    lines = [title, "Proyecto: " + study["project_id"], ""]
    combined = study["combined"]
    if combined:
        lines.extend([f"Imágenes: {combined['image_count']} · Recuento: {combined['N_count_valid']} · Tamaño: {combined['N_size_valid']}",
                      "Área total (µm²): " + combined["valid_area_um2"],
                      "Densidad (µm⁻²): " + combined["density_N_per_um2"],
                      "Diámetro medio / mediana (nm): " + _display(combined["diameter"]["mean_nm"]) + " / " + _display(combined["diameter"]["median_nm"]),
                      "Zonas distintas y sin solapamiento: confirmado por el usuario.", ""])
    else:
        lines.append("Los RUN se muestran por separado; no se suman sus áreas ni sus cavidades.\n")
    for record in study["records"]:
        area = Decimal(record["valid_area_nm2"]) / Decimal(1000000)
        lines.extend([record["image_id"], f"  Revisión: {record['revision_id']} · RUN: {record['run_id']}",
                      f"  N: {record['count']} · Tamaño: {record['size_count']} · Área (µm²): {area}",
                      f"  Densidad (µm⁻²): {Decimal(record['count']) / area}",
                      "  Escala X/Y (nm/px): " + record["scale_x_nm_px"] + " / " + record["scale_y_nm_px"],
                      "  Bandas en imagen: " + str(record["bands_in_image"]),
                      "  Muestra: " + record["sample_name"] + " · Condición: " + record["experimental_condition"]])
        for key, label in PROTOCOL_LABELS.items():
            lines.append("  " + label + ": " + _display(record["protocol"][key]))
        if study["mode"] == "compare":
            saved = record["saved_summary"]
            lines.append("  Diámetro medio / mediana guardados (nm): " + str(saved.get("mean_diameter_nm", "No disponible")) + " / " + str(saved.get("median_diameter_nm", "No disponible")))
        lines.append("")
    if study["protocol_differences"]:
        lines.append("Diferencias frente al primer RUN:")
        lines.extend("  " + item["run_id"] + ": " + ", ".join(item["fields"]) for item in study["protocol_differences"])
        lines.append("")
    lines.append(study["limitations"])
    return "\n".join(lines)


def _csv_cell(value):
    if isinstance(value, str) and value.lstrip().startswith(("=", "+", "-", "@")):
        try:
            if Decimal(value).is_finite():
                return value
        except InvalidOperation:
            pass
        return "'" + value
    return value


def export_study(study, output_parent, *, cancel=None):
    """Reverify inputs and create a new folder in the user-selected destination."""
    target = plain_path(output_parent)
    if not target.is_dir():
        raise ValueError("Seleccione una carpeta de destino existente.")
    fresh_records = []
    for record in study["records"]:
        source = plain_path(record["project_path"])
        if target == source or source in target.parents or any(
                (parent / "project.json").is_file() or (parent / "cavity_light_project.tsv").is_file()
                for parent in (target, *target.parents)):
            raise ValueError("Guarde el estudio en una carpeta externa al proyecto científico.")
        check_cancel(cancel)
        current = load_study_run(record["run_path"], cancel=cancel)
        if current["fingerprint"] != record["fingerprint"]:
            raise ValueError("Un RUN cambió desde la comprobación. Compruebe otra vez la selección antes de guardar.")
        fresh_records.append(current)
    # Rebuild from the verified records to detect an accidental modified report.
    fresh = build_study(fresh_records, mode=study["mode"], non_overlapping_confirmed=study["non_overlapping_confirmed_by_user"])
    if fresh["records"] != study["records"]:
        # checked_at is naturally refreshed and is excluded from equality below.
        if [{k: v for k, v in record.items() if k != "checked_at"} for record in fresh["records"]] != [
                {k: v for k, v in record.items() if k != "checked_at"} for record in study["records"]]:
            raise ValueError("La evidencia seleccionada cambió; compruebe de nuevo el estudio.")
    # Export the reconstruction, so even a modified cached combined summary
    # cannot override the figures obtained from the newly verified evidence.
    payload = fresh
    payload["created_at"] = study["created_at"]
    payload["export_verified_at"] = utc_now()
    folder = target / ("Cavity_estudio_" + utc_now().replace(":", "").replace("-", "").replace(".", "_") + "_" + uuid.uuid4().hex[:8])
    folder.mkdir()
    try:
        check_cancel(cancel)
        with (folder / "estudio.json").open("x", encoding="utf-8", newline="\n") as stream:
            json.dump(payload, stream, ensure_ascii=False, indent=2, allow_nan=False)
            stream.write("\n")
        body = html.escape(study_text(payload))
        with (folder / "informe.html").open("x", encoding="utf-8", newline="\n") as stream:
            stream.write("<!doctype html><html lang='es'><meta charset='utf-8'><title>Estudio Cavity Light</title><style>body{font:16px system-ui;margin:2rem auto;max-width:1100px;color:#193344}pre{white-space:pre-wrap;line-height:1.5}</style><h1>Estudio Cavity Light</h1><pre>" + body + "</pre></html>\n")
        columns = ["image_id", "revision_id", "run_id", "source_sha256", "sample_name", "experimental_condition", "count", "size_count", "valid_area_nm2", "scale_x_nm_px", "scale_y_nm_px", "bands_in_image", "fingerprint", "run_path"]
        with (folder / "por_imagen.csv").open("x", encoding="utf-8-sig", newline="") as stream:
            writer = csv.writer(stream)
            writer.writerow(columns + list(PROTOCOL_LABELS))
            for record in payload["records"]:
                writer.writerow([_csv_cell(record[key]) for key in columns] + [_csv_cell(json.dumps(record["protocol"][key], ensure_ascii=False) if isinstance(record["protocol"][key], list) else record["protocol"][key]) for key in PROTOCOL_LABELS])
        with (folder / "diametros.csv").open("x", encoding="utf-8-sig", newline="") as stream:
            writer = csv.writer(stream)
            writer.writerow(["image_id", "revision_id", "run_id", "cavity_id", "equivalent_diameter_nm"])
            for record in payload["records"]:
                check_cancel(cancel)
                writer.writerows([_csv_cell(record["image_id"]), _csv_cell(record["revision_id"]), _csv_cell(record["run_id"]), _csv_cell(obj["cavity_id"]), obj["equivalent_diameter_nm"]] for obj in record["size_objects"])
        if payload["combined"]:
            combined = dict(payload["combined"])
            combined.update(combined.pop("diameter"))
            combined["non_overlapping_confirmed_by_user"] = True
            with (folder / "resumen_combinado.csv").open("x", encoding="utf-8-sig", newline="") as stream:
                writer = csv.DictWriter(stream, fieldnames=list(combined))
                writer.writeheader()
                writer.writerow(combined)
    except BaseException:
        shutil.rmtree(folder)
        raise
    return folder


def show_project_study(parent, project):
    """Open an owned Tk dialog. File reading and export run outside the UI thread."""
    return ProjectStudyWindow(parent, project)


class ProjectStudyWindow:
    def __init__(self, parent, project):
        import tkinter as tk
        from tkinter import ttk
        from tkinter.scrolledtext import ScrolledText
        self.project = copy.deepcopy(project)
        self.window = tk.Toplevel(parent)
        self.window.transient(parent)
        self.window.title("Cavity Light · Estudio del proyecto")
        self.window.geometry("1100x780")
        self.window.minsize(860, 620)
        self.window.protocol("WM_DELETE_WINDOW", self.close)
        self.mode = tk.StringVar(self.window, value="combine")
        self.confirmed = tk.BooleanVar(self.window, value=False)
        self.status = tk.StringVar(self.window, value="Seleccione expresamente los RUN con Ctrl o Mayús y compruebe la selección.")
        self.events = queue.Queue()
        self.cancel = threading.Event()
        self.closed = self.busy = False
        self.study = None
        self.items = {}
        self.generation = 0
        self.poll_id = None
        frame = ttk.Frame(self.window, padding=14)
        frame.pack(fill="both", expand=True)
        ttk.Label(frame, text=project.get("name", project.get("project_id", "Proyecto")), font=("Segoe UI", 15, "bold")).pack(anchor="w")
        modes = ttk.Frame(frame)
        modes.pack(fill="x", pady=8)
        ttk.Radiobutton(modes, text="Combinar zonas: un RUN por imagen", variable=self.mode, value="combine", command=self._changed).pack(side="left", padx=(0, 24))
        ttk.Radiobutton(modes, text="Comparar revisiones/resultados", variable=self.mode, value="compare", command=self._changed).pack(side="left")
        trees = ttk.Frame(frame)
        trees.pack(fill="both", expand=True)
        trees.rowconfigure(0, weight=1)
        trees.columnconfigure(0, weight=1)
        self.tree = ttk.Treeview(trees, columns=("revision", "run"), selectmode="extended", height=10)
        self.tree.heading("#0", text="Imagen / resultado")
        self.tree.heading("revision", text="Revisión")
        self.tree.heading("run", text="RUN")
        self.tree.column("#0", width=400)
        self.tree.column("revision", width=235)
        self.tree.column("run", width=235)
        self.tree.grid(row=0, column=0, sticky="nsew")
        scroll = ttk.Scrollbar(trees, orient="vertical", command=self.tree.yview)
        scroll.grid(row=0, column=1, sticky="ns")
        self.tree.configure(yscrollcommand=scroll.set)
        self.tree.bind("<<TreeviewSelect>>", self._changed)
        for image in project.get("images", []):
            root = self.tree.insert("", "end", text=image.get("name", image["image_id"]), open=True)
            for run in image.get("runs", []):
                revision = next((rev for rev in image.get("revisions", []) if rev.get("revision_id") == run["revision_id"]), {})
                label = revision.get("name") or "Resultado guardado"
                iid = self.tree.insert(root, "end", text=label, values=(run["revision_id"], run["run_id"]))
                self.items[iid] = (image, run)
        self.check = ttk.Checkbutton(frame, text="Confirmo que las imágenes seleccionadas estudian zonas distintas y que sus áreas no se solapan.", variable=self.confirmed, command=self._changed)
        self.check.pack(anchor="w", pady=(9, 5))
        actions = ttk.Frame(frame)
        actions.pack(fill="x", pady=5)
        self.verify_button = ttk.Button(actions, text="Comprobar selección", command=self.verify)
        self.verify_button.pack(side="left")
        self.export_button = ttk.Button(actions, text="Guardar estudio…", command=self.save, state="disabled")
        self.export_button.pack(side="left", padx=8)
        ttk.Button(actions, text="Cerrar", command=self.close).pack(side="right")
        ttk.Label(frame, textvariable=self.status, wraplength=1000).pack(anchor="w", pady=5)
        self.output = ScrolledText(frame, height=15, wrap="word", font=("Consolas", 10), state="disabled")
        self.output.pack(fill="both", expand=True)
        self._put_text("Puede elegir revisiones históricas: se usan sus parámetros guardados.\nLas diferencias de escala calibrada son admisibles. Las diferencias de protocolo bloquean la combinación.\nLa comparación muestra esas diferencias sin sumar los resultados.\n\n" + LIMITATIONS)
        self.poll_id = self.window.after(80, self._poll)

    def _put_text(self, text):
        self.output.configure(state="normal")
        self.output.delete("1.0", "end")
        self.output.insert("1.0", text)
        self.output.configure(state="disabled")

    def _changed(self, _event=None):
        self.generation += 1
        self.study = None
        self.export_button.configure(state="disabled")
        self.check.configure(state="normal" if self.mode.get() == "combine" else "disabled")
        if self.busy:
            self.cancel.set()
        self.status.set("Selección modificada; compruébela antes de guardar.")

    def _start(self, operation):
        if self.busy:
            return
        generation = self.generation
        self.cancel = threading.Event()
        cancel = self.cancel
        self.busy = True
        self.verify_button.configure(state="disabled")
        self.export_button.configure(state="disabled")
        def worker():
            try:
                value = operation(cancel)
                self.events.put((generation, "done", value))
            except Exception as exc:
                self.events.put((generation, "error", str(exc)))
        threading.Thread(target=worker, name="cavity-project-study", daemon=True).start()

    def verify(self):
        from tkinter import messagebox
        selected = [self.items[iid] for iid in self.tree.selection() if iid in self.items]
        if len(selected) < 2:
            messagebox.showinfo("Estudio del proyecto", "Seleccione al menos dos resultados (filas RUN).", parent=self.window)
            return
        mode, confirmed = self.mode.get(), self.confirmed.get()
        self.status.set("Comprobando la integridad y el protocolo de los RUN seleccionados…")
        project = copy.deepcopy(self.project)
        def operation(cancel):
            records = []
            for image, run in selected:
                check_cancel(cancel)
                records.append(load_study_run(run["path"], project=project, image=image, run=run, cancel=cancel))
            return ("study", build_study(records, mode=mode, non_overlapping_confirmed=confirmed))
        self._start(operation)

    def save(self):
        from tkinter import filedialog
        if self.study is None or self.busy:
            return
        target = filedialog.askdirectory(title="Seleccione una carpeta externa al proyecto para guardar el estudio", parent=self.window, mustexist=True)
        if not target:
            return
        study = copy.deepcopy(self.study)
        self.status.set("Verificando otra vez los RUN y guardando una carpeta nueva…")
        self._start(lambda cancel: ("export", export_study(study, target, cancel=cancel)))

    def _poll(self):
        from tkinter import messagebox
        if self.closed:
            return
        try:
            while True:
                generation, kind, value = self.events.get_nowait()
                self.busy = False
                self.verify_button.configure(state="normal")
                if generation != self.generation:
                    continue
                if kind == "error":
                    self.study = None
                    self.status.set(value)
                    self._put_text(value + "\n\nLos archivos del proyecto se han conservado.")
                elif value[0] == "study":
                    self.study = value[1]
                    self._put_text(study_text(self.study))
                    self.status.set("Selección comprobada. Puede guardar CSV, JSON e informe HTML en una carpeta nueva.")
                else:
                    self.status.set("Estudio guardado: " + str(value[1]))
                    messagebox.showinfo("Estudio guardado", str(value[1]), parent=self.window)
                self.export_button.configure(state="normal" if self.study is not None else "disabled")
        except queue.Empty:
            pass
        self.poll_id = self.window.after(80, self._poll)

    def close(self):
        self.closed = True
        self.cancel.set()
        if self.poll_id is not None:
            self.window.after_cancel(self.poll_id)
        self.window.destroy()
