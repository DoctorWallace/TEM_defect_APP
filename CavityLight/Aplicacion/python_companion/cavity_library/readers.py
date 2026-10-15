"""Read-only, format-specific library adapters.

Inventory deliberately reads small descriptors, never source pixels or source
hashes. Explicit RUN opening verifies the saved evidence. R9 values remain
strings exactly as written; no current P3 selection policy is applied to them.
"""
from __future__ import annotations

import csv
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_EVEN
import hashlib
import io
import json
import math
import os
from pathlib import Path
import re
import stat
import struct


class ScanCancelled(Exception):
    """Cancellation leaves the previous complete catalogue intact."""


def check_cancel(cancel=None):
    if cancel is not None and (cancel() if callable(cancel) else cancel.is_set()):
        raise ScanCancelled("Lectura cancelada; se conserva el catálogo anterior.")


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def path_key(path):
    return os.path.normcase(os.path.abspath(os.fspath(path)))


def is_link(path):
    info = Path(path).lstat()
    return stat.S_ISLNK(info.st_mode) or bool(getattr(info, "st_file_attributes", 0) & 0x400)


def plain_path(path, *, base=None):
    """Reject links/reparse points, including existing ancestors of a path."""
    path = Path(os.path.abspath(os.fspath(path)))
    if base is not None:
        base = Path(os.path.abspath(os.fspath(base)))
        try:
            path.relative_to(base)
        except ValueError as exc:
            raise ValueError(f"Ruta fuera de la carpeta de evidencia: {path}") from exc
    for item in [path, *path.parents]:
        if item.exists() or item.is_symlink():
            if is_link(item):
                raise ValueError(f"Se omite enlace o punto de reanálisis: {item}")
    return path


def contained(base, relative):
    relative = str(relative).replace("\\", "/")
    if not relative or Path(relative).is_absolute() or re.match(r"^[a-zA-Z]:", relative):
        raise ValueError(f"Ruta relativa no válida: {relative!r}")
    if any(part in ("..", ".") for part in relative.split("/")):
        raise ValueError(f"Ruta relativa no válida: {relative!r}")
    return plain_path(Path(base) / relative, base=base)


def read_bytes(path, limit=32 * 1024 * 1024):
    path = plain_path(path)
    before = path.stat()
    if not stat.S_ISREG(before.st_mode) or before.st_size > limit:
        raise ValueError(f"Archivo de metadatos no regular o demasiado grande: {path}")
    data = path.read_bytes()
    after = path.stat()
    if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
        raise ValueError(f"El archivo cambió durante la lectura: {path}")
    return data


def read_json(path):
    value = json.loads(read_bytes(path).decode("utf-8-sig"))
    if not isinstance(value, dict):
        raise ValueError(f"Se esperaba un objeto JSON: {path}")
    return value


def read_table(path):
    text = read_bytes(path).decode("utf-8-sig")
    return list(csv.DictReader(io.StringIO(text), delimiter="\t"))


def read_pairs(path, limit=32 * 1024 * 1024):
    rows = list(csv.reader(io.StringIO(read_bytes(path, limit=limit).decode("utf-8-sig")), delimiter="\t"))
    result = {}
    for row in rows:
        if not row:
            continue
        if len(row) != 2 or not row[0] or row[0] in result:
            raise ValueError(f"Metadatos de clave/valor ambiguos: {path}")
        result[row[0]] = row[1]
    return result


def directories(path):
    if not Path(path).exists():
        return []
    plain_path(path)
    with os.scandir(path) as entries:
        return sorted((Path(e.path) for e in entries
                       if e.is_dir(follow_symlinks=False) and not is_link(e.path)),
                      key=lambda p: p.name.casefold())


def _pointer(path, key):
    if not path.is_file():
        return ""
    rows = read_table(path)
    return str(rows[0].get(key, "")) if rows else ""


def _source_path(root, row):
    candidates = []
    # A moved schema-1 project may still contain its immutable source copy.
    stored = row.get("stored_path", "")
    source = row.get("source_path", "")
    if stored:
        candidates.append(root / "images" / row["image_id"] / "source" / Path(stored).name)
    for value in (stored, source):
        if value:
            candidates.append(Path(value) if Path(value).is_absolute() else root / value)
    for candidate in candidates:
        try:
            if plain_path(candidate).is_file():
                return str(candidate), True
        except (OSError, ValueError):
            continue
    return (str(candidates[0]), False) if candidates else ("", False)


def _status(image):
    if image.get("errors"):
        return "Revisar incidencias"
    if image.get("runs"):
        return "Resultado disponible (sin verificar)"
    if image.get("revision_id") or image.get("revisions"):
        return "Revisión guardada"
    return "Imagen registrada"


def _r9_project(root, cancel):
    descriptor = read_pairs(root / "cavity_light_project.tsv")
    if descriptor.get("schema_version") != "1" or descriptor.get("descriptor_type") != "cavity_tem_light_project":
        raise ValueError("Descriptor de proyecto R9 no reconocido.")
    project = {"kind": "R9", "project_id": descriptor.get("project_id", ""),
               "project_uid": descriptor.get("project_uid", ""),
               "name": descriptor.get("project_name") or descriptor.get("project_id") or root.name,
               "metadata": descriptor, "images": []}
    seen = set()
    for row in read_table(root / "images.tsv"):
        check_cancel(cancel)
        image = {"image_id": row.get("image_id", ""), "name": row.get("display_name") or row.get("image_id", ""),
                 "kind": "R9", "revision_id": row.get("current_revision", ""),
                 "run_id": row.get("current_run", ""), "metadata": row, "runs": [], "revisions": [], "errors": []}
        project["images"].append(image)
        try:
            if image["image_id"] in seen:
                raise ValueError("Identificador de imagen duplicado en images.tsv.")
            seen.add(image["image_id"])
            image_root = contained(root, "images/" + image["image_id"])
            image["path"] = str(image_root)
            image["source_path"], image["source_available"] = _source_path(root, row)
            for revision in directories(image_root / "roi_sessions"):
                check_cancel(cancel)
                if not (revision / "revision_manifest.tsv").is_file():
                    continue
                rev = {"revision_id": revision.name, "path": str(revision), "kind": "R9"}
                try:
                    metadata = read_pairs(revision / "revision_manifest.tsv", limit=128 * 1024)
                    rev.update(created_ms=metadata.get("created_ms", ""), analysis_state=metadata.get("analysis_state", ""))
                    workspace = _read_workspace(revision, project, image, metadata)
                    if workspace is not None:
                        rev.update(name=workspace.get("name", ""), comment=workspace.get("comment", ""), workspace_status="verified")
                    else:
                        rev["workspace_status"] = "legacy"
                except (OSError, ValueError, TypeError) as exc:
                    rev.update(workspace_status="invalid", workspace_error=str(exc))
                image["revisions"].append(rev)
                for run in directories(revision / "measurement_runs"):
                    check_cancel(cancel)
                    if (run / "run_manifest.json").is_file():
                        image["runs"].append({"kind": "R9", "path": str(run), "run_id": run.name,
                                              "revision_id": revision.name, "current": run.name == image["run_id"],
                                              "verification_status": "NOT_CHECKED"})
            image["runs"].sort(key=lambda r: (r["revision_id"], r["run_id"]), reverse=True)
        except (OSError, ValueError, KeyError) as exc:
            image["errors"].append(str(exc))
        image["status"] = _status(image)
    return project


def _p3_project(root, cancel):
    descriptor = read_json(root / "project.json")
    if descriptor.get("project_schema_version") != 2:
        raise ValueError("Descriptor de proyecto schema 2 no reconocido.")
    registry = read_json(root / "controls" / "source_registry.json")
    if registry.get("project_uid") != descriptor.get("project_uid"):
        raise ValueError("El registro de fuentes corresponde a otro proyecto.")
    project = {"kind": "P3", "project_id": descriptor.get("project_id", ""),
               "project_uid": descriptor.get("project_uid", ""),
               "name": descriptor.get("project_name") or descriptor.get("project_id") or root.name,
               "metadata": descriptor, "images": []}
    blobs = {b["source_sha256"]: b for b in registry.get("blobs", [])}
    for binding in registry.get("image_bindings", []):
        check_cancel(cancel)
        image = {"kind": "P3", "image_id": binding.get("image_id", ""), "image_uid": binding.get("image_uid", ""),
                 "name": binding.get("source_file_name") or binding.get("image_id", ""),
                 "metadata": binding, "revision_id": "", "run_id": "", "runs": [], "revisions": [],
                 "sessions": [], "errors": []}
        project["images"].append(image)
        try:
            image_root = contained(root, binding["image_relative_path"])
            image["path"] = str(image_root)
            blob = blobs.get(binding.get("source_sha256"), {})
            source = contained(root, blob["storage_relative_path"]) if blob else None
            image["source_path"] = str(source) if source else ""
            image["source_available"] = bool(source and source.is_file())
            for row in read_table(image_root / "sessions" / "session_registry.tsv"):
                check_cancel(cancel)
                session = contained(image_root, row["relative_path"])
                sid = row.get("analysis_session_id", "")
                suid = row.get("analysis_session_uid", "")
                try:
                    rid = _pointer(session / "current_revision.tsv", "revision_id")
                    runid = _pointer(session / "current_run.tsv", "run_id")
                    image["sessions"].append({**row, "path": str(session), "revision_id": rid, "run_id": runid})
                    if row.get("lifecycle") == "CURRENT":
                        image.update(revision_id=rid, run_id=runid, session_id=sid, session_uid=suid)
                    if rid:
                        image["revisions"].append({"revision_id": rid, "session_id": sid, "session_uid": suid})
                    reg = read_json(session / "run_registry.json") if (session / "run_registry.json").is_file() else {}
                    for run in reg.get("runs", []):
                        check_cancel(cancel)
                        try:
                            run_path = contained(session, run["relative_path"])
                            manifest = read_json(run_path / "run_manifest.json")
                            image["runs"].append({"kind": "P3", "path": str(run_path), "run_id": run.get("run_id", ""),
                                              "revision_id": manifest.get("revision_id", ""),
                                              "session_id": sid, "session_uid": suid,
                                              "current": run.get("run_id") == runid,
                                              "quarantine_status": run.get("quarantine_status"),
                                              "verification_status": "NOT_CHECKED"})
                        except (OSError, ValueError, KeyError) as exc:
                            image["errors"].append(f"Sesión {sid}, RUN {run.get('run_id', '')}: {exc}")
                except (OSError, ValueError, KeyError) as exc:
                    image["errors"].append(f"Sesión {sid}: {exc}")
        except (OSError, ValueError, KeyError) as exc:
            image["errors"].append(str(exc))
        image["status"] = _status(image)
    return project


def read_project(path, cancel=None):
    """Read an inventory without invoking scientific validators or source IO."""
    root = plain_path(path)
    check_cancel(cancel)
    if (root / "project.json").is_file():
        project = _p3_project(root, cancel)
    elif (root / "cavity_light_project.tsv").is_file():
        project = _r9_project(root, cancel)
    else:
        raise ValueError(f"No se encuentra un proyecto Cavity Light en {root}")
    now = utc_now()
    project.update(path=str(root), available=True, last_scanned=now, last_seen=now, errors=[],
                   image_count=len(project["images"]),
                   images_with_results=sum(bool(i["runs"]) for i in project["images"]),
                   images_with_revisions=sum(bool(i["revisions"]) for i in project["images"]))
    return project


def _hash_file(path, cancel=None):
    path = plain_path(path)
    before = path.stat()
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            check_cancel(cancel)
            digest.update(chunk)
    after = path.stat()
    if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
        raise ValueError(f"El archivo cambió durante la comprobación: {path}")
    return digest.hexdigest()


def _legacy_json_number(value):
    """Numeric value emitted by R9 jsonNumber's ``"" + v`` conversion.

    In the bundled ImageJ 1.54p, Interpreter.toString(double) uses exact
    32-bit integers or IJ.d2s(v, 4, 9), then strips insignificant zeroes.
    That formatter chooses decimal places from magnitude, not a fixed
    tolerance (801212.954679220 becomes 801212.955). DecimalFormat uses
    half-even rounding of the binary double. This adapter is used only for
    the explicit area/scale fields written by jsonNumber; hashes, IDs and
    saved TSV values are unchanged.
    """
    number = float(value)
    if not math.isfinite(number):
        raise InvalidOperation("Número guardado no finito")
    if -2147483648 <= number <= 2147483647 and number == int(number):
        return Decimal(int(number))
    binary = Decimal.from_float(number)
    # IJ.d2s(double, decimalPlaces=4, significantDigits=9).
    integer_digits = math.ceil(math.log10(abs(number)) + 0.223 * 10 ** -9)
    places = 9 - integer_digits
    if places < 0 or integer_digits < -4:
        # DecimalFormat("0.0000E0"): four digits after the mantissa dot.
        quantum = Decimal(1).scaleb(binary.copy_abs().adjusted() - 4)
    else:
        if places > 4:
            places = max(4, places - 9 + 4)
        quantum = Decimal(1).scaleb(-min(9, places))
    return binary.quantize(quantum, rounding=ROUND_HALF_EVEN)


def _r9_saved_number_matches(saved, manifest_value):
    saved_number = Decimal(saved)
    manifest_number = Decimal(str(manifest_value))
    if not saved_number.is_finite() or not manifest_number.is_finite():
        raise InvalidOperation("Número guardado no finito")
    return saved_number == manifest_number or _legacy_json_number(saved_number) == manifest_number


def _r9_run(path, manifest, cancel):
    errors, files, digests = [], [], {}
    sidecar = path / "RUN_SHA256.txt"
    data = read_bytes(sidecar)
    for line in data.decode("utf-8-sig").splitlines():
        check_cancel(cancel)
        match = re.fullmatch(r"([0-9a-fA-F]{64}) [ *](.+)", line)
        if not match:
            errors.append("Línea no válida en RUN_SHA256.txt")
            continue
        expected, relative = match.groups()
        try:
            target = contained(path, relative)
            if relative in digests:
                raise ValueError(f"Entrada de hash duplicada: {relative}")
            actual = _hash_file(target, cancel)
            digests[relative] = actual
            files.append({"name": relative, "path": str(target), "sha256": actual})
            if actual.lower() != expected.lower():
                errors.append(f"Hash distinto: {relative}")
        except (OSError, ValueError) as exc:
            errors.append(str(exc))
    required = {"run_manifest.json", "image_summary.tsv", "cavity_objects.tsv", "analysis_method.json"}
    if required - digests.keys():
        errors.append("Faltan archivos obligatorios en el manifiesto de hashes: " + ", ".join(sorted(required - digests.keys())))
    summary = read_pairs(path / "image_summary.tsv")
    revision = path.parent.parent
    initial_revision_hash = _hash_file(revision / "revision_manifest.tsv", cancel)
    rev = read_pairs(revision / "revision_manifest.tsv")
    project_id = str(manifest.get("project", {}).get("id", ""))
    project_uid = str(manifest.get("project", {}).get("uid", ""))
    image_id = str(manifest.get("image", {}).get("id", ""))
    revision_id = str(manifest.get("revision_id", ""))
    identities = {"project_id": project_id, "image_id": image_id, "revision_id": revision_id}
    for key, expected in identities.items():
        if not expected or summary.get(key) != expected or rev.get(key) != expected:
            errors.append(f"Identidad inconsistente: {key}")
    if not project_uid or rev.get("project_uid") != project_uid:
        errors.append("Identidad inconsistente: project_uid")
    if summary.get("run_id") != path.name or revision_id != revision.name or path.parent.name != "measurement_runs":
        errors.append("RUN/revisión no coinciden con sus carpetas.")
    source_hash = str(manifest.get("image", {}).get("sha256", ""))
    if not source_hash or summary.get("source_sha256") != source_hash or rev.get("source_sha256") != source_hash:
        errors.append("Identidad inconsistente: source_sha256")
    try:
        roi_hash = _hash_file(revision / "cavity_rois.zip", cancel)
        if roi_hash != rev.get("roi_zip_sha256"):
            errors.append("Hash distinto: cavity_rois.zip de la revisión")
    except (OSError, ValueError) as exc:
        roi_hash = ""
        errors.append(str(exc))
    # Compare saved geometry/policy metadata only; never recompute R9 science.
    for key, expected in (("include_uncertain", manifest.get("settings", {}).get("include_uncertain")),):
        if expected is not None and summary.get(key) != str(expected):
            errors.append(f"Interpretación guardada inconsistente: {key}")
    for key, expected in (("scale_x_nm_px", manifest.get("scale", {}).get("active_nm_per_px_x")),
                          ("scale_y_nm_px", manifest.get("scale", {}).get("active_nm_per_px_y")),
                          ("valid_area_nm2", manifest.get("area", {}).get("valid_area_nm2"))):
        if expected is not None:
            try:
                if not _r9_saved_number_matches(summary.get(key, ""), expected):
                    errors.append(f"Metadato guardado inconsistente: {key}")
            except InvalidOperation:
                errors.append(f"Metadato numérico no válido: {key}")
    objects = read_table(path / "cavity_objects.tsv")
    ids = [row.get("cavity_id", "") for row in objects]
    if any(not item for item in ids) or len(ids) != len(set(ids)):
        errors.append("Identificadores de cavidad vacíos o duplicados.")
    if any(row.get("image_id") != image_id for row in objects):
        errors.append("Una cavidad corresponde a otra imagen.")
    if len(objects) != manifest.get("objects", {}).get("cavities"):
        errors.append("El número de cavidades no coincide con el manifiesto.")
    project_path = ""
    for parent in revision.parents:
        if (parent / "cavity_light_project.tsv").is_file():
            project_path = str(parent)
            descriptor = read_pairs(parent / "cavity_light_project.tsv")
            if descriptor.get("project_id") != project_id or descriptor.get("project_uid") != project_uid:
                errors.append("El RUN corresponde a otro proyecto.")
            break
    # Prevent a concurrent publication/edit from mixing old metadata with new
    # hashes. Source pixels are still intentionally not read here.
    for name in required & digests.keys():
        if _hash_file(contained(path, name), cancel) != digests[name]:
            errors.append(f"El archivo cambió durante la lectura: {name}")
    if read_json(path / "run_manifest.json") != manifest:
        errors.append("El manifiesto cambió durante la lectura.")
    if read_bytes(sidecar) != data or _hash_file(revision / "revision_manifest.tsv", cancel) != initial_revision_hash:
        errors.append("La evidencia de RUN/revisión cambió durante la lectura.")
    fingerprint_data = {"files": digests, "sidecar": hashlib.sha256(data).hexdigest(),
                        "revision_manifest": initial_revision_hash, "roi_zip": roi_hash}
    fingerprint = hashlib.sha256(json.dumps(fingerprint_data, sort_keys=True).encode()).hexdigest()
    label = "R9 · resultados históricos conservados"
    text = "\n".join([label, f"Proyecto: {project_id}", f"Imagen: {image_id}",
                      f"Revisión: {revision_id}", f"RUN: {path.name}",
                      "Valores guardados; sin recalcular ni cambiar la inclusión de dudosas.",
                      "Integridad verificada; no equivale a validación científica." if not errors else
                      "INTEGRIDAD NO CONFIRMADA: " + "; ".join(errors), ""] +
                     [f"{key}: {value}" for key, value in summary.items()])
    return {"kind": "R9", "summary": summary, "summary_rows": list(summary.items()), "label": label, "text": text,
            "path": str(path), "run_path": str(path), "project_path": project_path,
            "project_id": project_id, "project_uid": project_uid, "image_id": image_id,
            "revision_id": revision_id, "run_id": path.name, "fingerprint": fingerprint,
            "manifest": manifest, "files": files, "revision_manifest": rev, "revision_roi_sha256": roi_hash,
            "verification": {"ok": not errors, "errors": errors, "checked_files": len(digests),
                             "checked_at": utc_now(), "source_pixels_checked": False, "scientific_validation": False}}


WORKSPACE_LIMIT = 1024 * 1024
THUMBNAIL_LIMIT = 8 * 1024 * 1024
NO_VALUE = "No registrado"
CONFIGURATION_FIELDS = (
    ("sample_name", "Muestra", ("scientific_context", "sample")),
    ("experimental_condition", "Condición", ("scientific_context", "condition")),
    ("image_mode", "Modo de análisis", ("analysis_mode",)),
    ("scale_x_nm_px", "Escala X (nm/píxel)", ("scale", "active_nm_per_px_x")),
    ("scale_y_nm_px", "Escala Y (nm/píxel)", ("scale", "active_nm_per_px_y")),
    ("scale_confirmed", "Calibración confirmada", ("scale", "confirmed")),
    ("scale_origin", "Origen de calibración", ("scale", "origin")),
    ("band_width_nm", "Ancho de banda (nm)", ("bands", "width_nm")),
    ("band_count", "Número de bandas", ("bands", "count")),
    ("histogram_bin_nm", "Intervalo de histograma (nm)", ("settings", "histogram_bin_nm")),
    ("feature_distance_bin_nm", "Intervalo de distancia (nm)", ("settings", "feature_distance_bin_nm")),
    ("include_uncertain", "Inclusión de dudosas", ("settings", "include_uncertain")),
    ("use_whole_image", "Área de imagen completa", ("area", "whole_image_confirmed")),
    ("valid_area_nm2", "Área guardada (nm²)", ("area", "valid_area_nm2")),
    ("foil_thickness_nm", "Espesor (nm)", ("thickness", "nm")),
    ("thickness_uncertainty_nm", "Incertidumbre del espesor (nm)", ("thickness", "uncertainty_nm")),
    ("thickness_method", "Método de espesor", ("thickness", "method")),
)


def _nested(data, keys):
    for key in keys:
        if not isinstance(data, dict) or key not in data:
            return None
        data = data[key]
    return data


def _display_saved(value):
    if value is None or value == "":
        return NO_VALUE
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    return str(value)


def _valid_digest(value):
    return isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value) is not None


def _read_workspace(revision, project, image, metadata):
    """Read only bounded metadata. Artifact bytes are loaded explicitly later."""
    sidecar = contained(revision, "revision_workspace.json")
    expected = metadata.get("workspace_sha256")
    if not sidecar.is_file() and not expected:
        return None
    if not _valid_digest(expected):
        raise ValueError("Los metadatos de trabajo no tienen una huella registrada en la revisión.")
    raw = read_bytes(sidecar, limit=WORKSPACE_LIMIT)
    if hashlib.sha256(raw).hexdigest() != expected:
        raise ValueError("Los metadatos de trabajo cambiaron: revision_workspace.json.")
    workspace = json.loads(raw.decode("utf-8-sig"))
    if not isinstance(workspace, dict) or workspace.get("type") != "cavity_revision_workspace" or workspace.get("schema_version") != 1:
        raise ValueError("Formato de metadatos de trabajo no reconocido.")
    if workspace.get("revision_id") != revision.name:
        raise ValueError("La identidad de los metadatos de trabajo no coincide con la revisión.")
    binding = workspace.get("binding")
    if not isinstance(binding, dict):
        raise ValueError("Falta la vinculación de los metadatos de trabajo.")
    identities = {"project_id": project.get("project_id"), "project_uid": project.get("project_uid"),
                  "image_id": image.get("image_id"), "source_sha256": metadata.get("source_sha256"),
                  "roi_zip_sha256": metadata.get("roi_zip_sha256")}
    for field, value in identities.items():
        if not value or binding.get(field) != value or metadata.get(field, value) != value:
            raise ValueError(f"Identidad de los metadatos de trabajo inconsistente: {field}")
    for field, maximum in (("name", 120), ("comment", 4000)):
        if not isinstance(workspace.get(field, ""), str) or len(workspace.get(field, "")) > maximum:
            raise ValueError(f"Texto de revisión no válido: {field}")
    if not isinstance(workspace.get("settings"), dict) or workspace.get("settings_provenance") != "saved_session_project_json":
        raise ValueError("No se reconoce la procedencia de los parámetros guardados.")
    settings = workspace["settings"]
    settings_identities = (("project_id", ("project", "id")), ("project_uid", ("project", "uid")),
                           ("image_id", ("image", "id")), ("source_sha256", ("image", "sha256")))
    for field, location in settings_identities:
        if _nested(settings, location) != identities[field]:
            raise ValueError(f"Los parámetros guardados corresponden a otra identidad: {field}")
    if settings.get("revision_id") != revision.name:
        raise ValueError("Los parámetros guardados corresponden a otra revisión.")
    operations = workspace.get("operations")
    if not isinstance(operations, list) or len(operations) > 1000:
        raise ValueError("Registro de tratamientos no válido o demasiado grande.")
    for operation in operations:
        if not isinstance(operation, dict) or not isinstance(operation.get("kind"), str) or not isinstance(operation.get("params"), dict):
            raise ValueError("Entrada de tratamiento no válida.")
        region = operation.get("region")
        if region is not None:
            if not isinstance(region, dict) or not _valid_digest(region.get("sha256")):
                raise ValueError("Región de tratamiento no válida.")
            region_path = contained(revision, region.get("roi_relative_path", ""))
            if not region_path.relative_to(revision).as_posix().startswith("workspace/regions/"):
                raise ValueError("Región de tratamiento fuera de la carpeta de trabajo guardada.")
    artifacts = workspace.get("artifacts")
    if not isinstance(artifacts, dict):
        raise ValueError("No se registraron archivos de la imagen de trabajo.")
    for kind in ("working_image", "annotated_view", "thumbnail", "treatment_regions"):
        artifact = artifacts.get(kind)
        if not isinstance(artifact, dict) or not _valid_digest(artifact.get("sha256")):
            raise ValueError(f"Archivo de trabajo no válido: {kind}")
        path = contained(revision, artifact.get("relative_path", ""))
        if not path.relative_to(revision).as_posix().startswith("workspace/"):
            raise ValueError(f"Archivo fuera de la carpeta de trabajo guardada: {kind}")
    return workspace


def read_revision_details(project, image, revision, cancel=None, verified_run=None):
    """Inspect one saved R9 revision without decoding its TEM or TIFF images."""
    revision_id = str(revision.get("revision_id", ""))
    result = {"revision_id": revision_id, "name": "", "title": revision_id, "comment": "", "preview": None,
              "configuration": [], "workspace": {"status": "legacy"}, "verification": {"ok": False, "errors": []}}
    if project.get("kind") != "R9":
        result["text"] = "Esta ficha admite revisiones R9. El proyecto P3 conserva su editor y lector propios."
        return result
    try:
        check_cancel(cancel)
        root = plain_path(project["path"])
        image_root = contained(root, "images/" + image["image_id"])
        path = contained(image_root, "roi_sessions/" + revision_id)
        if revision.get("path") and path_key(path) != path_key(revision["path"]):
            raise ValueError("La revisión seleccionada no pertenece a esta imagen.")
        metadata = read_pairs(path / "revision_manifest.tsv", limit=128 * 1024)
        for key, expected in (("revision_id", revision_id), ("project_id", project.get("project_id")),
                              ("project_uid", project.get("project_uid")), ("image_id", image["image_id"])):
            if not expected or metadata.get(key) != expected:
                raise ValueError(f"Identidad de revisión inconsistente: {key}")
        source_hash = image.get("metadata", {}).get("source_sha256")
        if source_hash and source_hash != metadata.get("source_sha256"):
            raise ValueError("La revisión corresponde a otra fuente.")
        expected_zip = metadata.get("roi_zip_sha256")
        if not _valid_digest(expected_zip):
            raise ValueError("Falta la huella del ZIP de ROI de la revisión.")
        # Check the selected ZIP again: a cached RUN report must never confer
        # integrity on revision bytes that changed after the RUN was read.
        zip_hash = _hash_file(path / "cavity_rois.zip", cancel)
        if zip_hash != expected_zip:
            raise ValueError("El ZIP de ROI no coincide con la revisión guardada.")
        result.update(path=str(path), metadata=metadata, created_ms=metadata.get("created_ms"),
                      analysis_state=metadata.get("analysis_state", ""), parent_revision=metadata.get("parent_revision", ""))
        result["verification"]["ok"] = True
        workspace = _read_workspace(path, project, image, metadata)
        settings, source = {}, "No registrado"
        if workspace is not None:
            settings, source = workspace["settings"], "revision_workspace.json · huella comprobada"
            result.update(name=workspace.get("name", ""), title=workspace.get("name") or revision_id,
                          comment=workspace.get("comment", ""))
            result["workspace"] = dict(workspace, status="verified")
            result["preview"] = read_workspace_thumbnail(path, workspace["artifacts"]["thumbnail"], cancel)
        else:
            legacy_path = path / "session_metadata.json"
            if legacy_path.is_file():
                try:
                    legacy = json.loads(read_bytes(legacy_path, limit=WORKSPACE_LIMIT).decode("utf-8-sig"))
                    if (isinstance(legacy, dict) and legacy.get("revision_id") == revision_id
                            and _nested(legacy, ("project", "id")) == project.get("project_id")
                            and _nested(legacy, ("project", "uid")) == project.get("project_uid")
                            and _nested(legacy, ("image", "id")) == image["image_id"]
                            and _nested(legacy, ("image", "sha256")) == metadata.get("source_sha256")):
                        settings, source = legacy, "session_metadata.json · histórico sin sello"
                except (OSError, ValueError, TypeError):
                    pass
        result["configuration"] = [
            {"field": field, "label": label, "value": _display_saved(_nested(settings, location)), "source": source,
             "state": "unknown" if _nested(settings, location) in (None, "") else "recorded"}
            for field, label, location in CONFIGURATION_FIELDS]
        check_cancel(cancel)
        if read_pairs(path / "revision_manifest.tsv", limit=128 * 1024) != metadata:
            raise ValueError("La revisión cambió durante la lectura de sus parámetros.")
    except ScanCancelled:
        raise
    except (OSError, ValueError, TypeError, KeyError) as exc:
        result["verification"] = {"ok": False, "errors": [str(exc)]}
        result["workspace"] = {"status": "invalid"}
        result["preview"] = None
    result["text"] = revision_details_text(result)
    return result


def read_workspace_thumbnail(revision_path, artifact, cancel=None):
    """Verify bounded PNG bytes before passing them to Tk; never open the TIFF."""
    path = contained(revision_path, artifact["relative_path"])
    if path.suffix.lower() != ".png":
        raise ValueError("La miniatura guardada no es un PNG.")
    raw = read_bytes(path, limit=THUMBNAIL_LIMIT)
    check_cancel(cancel)
    if hashlib.sha256(raw).hexdigest() != artifact["sha256"]:
        raise ValueError("La miniatura cambió respecto de la revisión guardada.")
    if len(raw) < 24 or raw[:8] != b"\x89PNG\r\n\x1a\n" or raw[12:16] != b"IHDR":
        raise ValueError("La miniatura no contiene una cabecera PNG válida.")
    width, height = struct.unpack(">II", raw[16:24])
    if not width or not height or max(width, height) > 1200 or width * height > 1_440_000:
        raise ValueError("La miniatura excede el tamaño admitido por la biblioteca.")
    for key, value in (("width_px", width), ("height_px", height), ("size_bytes", len(raw))):
        if artifact.get(key) != value:
            raise ValueError(f"La miniatura no coincide con los metadatos guardados: {key}")
    return {"path": str(path), "sha256": artifact["sha256"], "width": width, "height": height, "data": raw}


def revision_details_text(result):
    metadata = result.get("metadata", {})
    state = {"pending": "Pendiente de recalcular", "prepared": "Preparada para calcular"}.get(result.get("analysis_state"), NO_VALUE)
    lines = [result.get("title") or result.get("revision_id", ""), f"Revisión: {result.get('revision_id')}",
             "Comentario: " + (result.get("comment") or NO_VALUE), "Estado al guardar: " + state,
             "Revisión anterior: " + (result.get("parent_revision") or NO_VALUE),
             "Fuente SHA-256: " + (metadata.get("source_sha256") or NO_VALUE),
             "ROI SHA-256: " + (metadata.get("roi_zip_sha256") or NO_VALUE)]
    status = result.get("workspace", {}).get("status")
    if status == "verified":
        lines += ["", "Parámetros y miniatura de la revisión: integridad comprobada.",
                  "La imagen TIFF completa permanece guardada; esta ficha no la decodifica."]
    elif status == "legacy":
        lines += ["", "Revisión histórica: imagen de trabajo y tratamiento sellados: No registrado.",
                  "Los parámetros históricos sin sello se indican con su archivo de procedencia."]
    else:
        lines += ["", "No se pudo verificar la revisión:"] + result.get("verification", {}).get("errors", [])
    if result.get("analysis_state") == "pending":
        lines.append("El área y otras medidas guardadas pueden estar pendientes de actualizar. Consulte un RUN íntegro para sus resultados calculados.")
    lines += ["", "Configuración guardada"]
    for row in result.get("configuration", []):
        lines.append(f"{row['label']}: {row['value']} ({row['source']})")
    operations = result.get("workspace", {}).get("operations")
    lines += ["", "Tratamientos de la copia de trabajo"]
    recipe_complete = _nested(result.get("workspace"), ("preparation", "recipe_complete"))
    if recipe_complete is False or any(op.get("kind") == "external_pixel_changes" for op in (operations or [])):
        lines.append("Receta parcial: contiene cambios cuyos pasos no quedaron registrados. Se conserva la imagen de trabajo; la receta no permite reproducir todos esos cambios.")
    elif recipe_complete is True:
        lines.append("Receta registrada como completa al guardar.")
    if operations is None:
        lines.append(NO_VALUE)
    elif not operations:
        lines.append("Sin tratamientos registrados")
    else:
        for index, operation in enumerate(operations, 1):
            region = " · región guardada" if operation.get("region") else " · imagen completa"
            kind, parameters = treatment_text(operation)
            lines.append(f"{index}. {kind}{region}: {parameters}")
    return "\n".join(lines)


def treatment_text(operation):
    """Render saved parameters without exposing pixel bookkeeping in the flow."""
    kinds = {"brightness_contrast": "Brillo y contraste", "local_contrast": "Contraste local",
             "background_correction": "Corrección de fondo", "external_pixel_changes": "Cambios externos en Fiji"}
    labels = {"brightness": "Brillo", "contrast": "Contraste", "center": "Centro de intensidad",
              "radius": "Radio (píxeles)", "radius_px": "Radio (píxeles)", "amount": "Intensidad",
              "max_gain": "Ganancia máxima", "noise_floor": "Umbral de ruido", "target_stddev": "Desviación objetivo",
              "strength": "Intensidad", "mode": "Modo", "reference": "Referencia", "epsilon": "Tolerancia",
              "description": "Descripción", "algorithm": "Algoritmo"}
    parameters = []
    for key, value in operation.get("params", {}).items():
        if key in ("before_pixel_sha256", "after_pixel_sha256"):
            continue
        if key == "mode" and isinstance(value, str):
            value = {"subtract": "Restar fondo", "divide": "Dividir por fondo"}.get(value, value)
        parameters.append(labels.get(key, key) + "=" + _display_saved(value))
    return kinds.get(operation.get("kind"), operation.get("kind", NO_VALUE)), "; ".join(parameters) or NO_VALUE


def _comparison_values(report):
    summary, manifest = report["summary"], report["manifest"]
    values = {field: summary.get(field) for field, _label, _location in CONFIGURATION_FIELDS}
    for field, _label, location in CONFIGURATION_FIELDS:
        if values[field] in (None, ""):
            values[field] = _nested(manifest, location)
    for field in ("N_count_valid", "N_size_valid", "mean_diameter_nm", "median_diameter_nm", "density_N_per_um2"):
        values[field] = summary.get(field)
    methods = next((item for item in report["files"] if item.get("name") == "analysis_method.json"), None)
    if methods is None:
        raise ValueError("No se encuentra el método guardado del RUN.")
    method_bytes = read_bytes(methods["path"], limit=WORKSPACE_LIMIT)
    if hashlib.sha256(method_bytes).hexdigest() != methods.get("sha256"):
        raise ValueError("El método cambió después de comprobar el RUN.")
    method = json.loads(method_bytes.decode("utf-8-sig"))
    if not isinstance(method, dict):
        raise ValueError("El método guardado del RUN no tiene un formato válido.")
    values["method_parameters"] = {key: value for key, value in method.items() if key != "application_version"}
    workspace = _read_workspace(Path(report["path"]).parent.parent,
                                {"project_id": report["project_id"], "project_uid": report["project_uid"]},
                                {"image_id": report["image_id"]}, report["revision_manifest"])
    values["revision_name"] = workspace.get("name") if workspace else None
    values["revision_comment"] = workspace.get("comment") if workspace else None
    values["treatment_operations"] = workspace.get("operations") if workspace else None
    values["working_image_sha256"] = _nested(workspace, ("artifacts", "working_image", "sha256"))
    return values


def compare_runs(left_path, right_path, cancel=None):
    """Reverify and compare two saved R9 revisions of one physical image."""
    if path_key(left_path) == path_key(right_path):
        raise ValueError("Seleccione dos revisiones distintas para compararlas.")
    left = read_run(left_path, cancel)
    right = read_run(right_path, cancel)
    for report in (left, right):
        if not report.get("verification", {}).get("ok"):
            raise ValueError("No se puede comparar un RUN con integridad no confirmada: "
                             + "; ".join(report.get("verification", {}).get("errors", [])))
        if report.get("kind") != "R9":
            raise ValueError("Esta comparación usa resultados R9 guardados; los proyectos P3 conservan su lector propio.")
    for field in ("project_uid", "image_id"):
        if not left.get(field) or left[field] != right.get(field):
            raise ValueError("Seleccione revisiones de la misma imagen y proyecto.")
    if path_key(left.get("project_path", "")) != path_key(right.get("project_path", "")):
        raise ValueError("La comparación debe utilizar el mismo proyecto, en su misma ubicación.")
    source = left["summary"].get("source_sha256")
    if not source or source != right["summary"].get("source_sha256"):
        raise ValueError("Los resultados corresponden a fuentes de imagen diferentes.")
    if left["revision_id"] == right["revision_id"]:
        raise ValueError("Seleccione un RUN de otra revisión de esta imagen.")
    left_values, right_values = _comparison_values(left), _comparison_values(right)
    fields = [(field, label) for field, label, _location in CONFIGURATION_FIELDS] + [
        ("revision_name", "Nombre de la revisión"), ("revision_comment", "Comentario guardado"),
        ("treatment_operations", "Tratamientos guardados"), ("working_image_sha256", "Huella registrada de imagen de trabajo"),
        ("method_parameters", "Método y parámetros"), ("N_count_valid", "Cavidades para recuento"),
        ("N_size_valid", "Cavidades para tamaño"), ("mean_diameter_nm", "Diámetro medio (nm)"),
        ("median_diameter_nm", "Mediana (nm)"), ("density_N_per_um2", "Densidad superficial (µm⁻²)")]
    rows = []
    for field, label in fields:
        a, b = left_values.get(field), right_values.get(field)
        if a in (None, "") or b in (None, ""):
            state = "unknown"
        else:
            try:
                state = "equal" if Decimal(str(a)) == Decimal(str(b)) else "different"
            except (InvalidOperation, ValueError):
                state = "equal" if a == b else "different"
        rows.append({"field": field, "label": label, "left": _display_saved(a), "right": _display_saved(b), "state": state})
    text = [f"A: {left['revision_id']} · {left['run_id']}", f"B: {right['revision_id']} · {right['run_id']}",
            "Ambos RUN tienen integridad comprobada. Se muestran sus valores guardados, sin recalcular.",
            "Las diferencias de parámetros se muestran junto a los resultados. No registrado significa que la comparación de ese campo es desconocida.", ""]
    text += [f"{row['label']}: A={row['left']} · B={row['right']}" for row in rows if row["state"] != "equal"]
    check_cancel(cancel)
    return {"left": left, "right": right, "rows": rows, "text": "\n".join(text), "scientific_validation": False}


def read_run(path, cancel=None):
    """Open one explicitly selected RUN. Never writes into the project."""
    path = plain_path(path)
    check_cancel(cancel)
    manifest = read_json(path / "run_manifest.json")
    if str(manifest.get("schema_version")) == "1" and "project" in manifest:
        return _r9_run(path, manifest, cancel)
    from cavity_stats_app.app import analyze_run, report_text
    report = analyze_run(path, progress=lambda _message: check_cancel(cancel))
    m = report["source_manifest"]
    return {"kind": "P3", "path": str(path), "run_path": str(path),
            "project_path": report["source_project"], "project_uid": m.get("project_uid", ""),
            "project_id": m.get("project_id", ""), "image_id": m.get("image_id", m.get("image_uid", "")),
            "image_uid": m.get("image_uid", ""), "session_id": m.get("analysis_session_id", ""),
            "session_uid": m.get("analysis_session_uid", ""), "revision_id": m["revision_id"], "run_id": m["run_id"],
            "summary": report["summaries"], "summary_rows": list(report["summaries"].items()),
            "label": "P3 · resultados descriptivos", "text": report_text(report), "manifest": m,
            "fingerprint": report["run_manifest_sha256"], "p3_report": report,
            "files": [{"name": name, "path": str(contained(path, name)), "sha256": _hash_file(contained(path, name), cancel)}
                      for name in ("cavity_objects.tsv", "run_manifest.json")],
            "verification": {"ok": True, "errors": [], "checked_at": report["verified_at_utc"],
                             "checked_files": 2, "scientific_validation": False}}
