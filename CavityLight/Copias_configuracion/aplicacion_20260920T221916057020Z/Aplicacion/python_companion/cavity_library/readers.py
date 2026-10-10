"""Read-only, format-specific library adapters.

Inventory deliberately reads small descriptors, never source pixels or source
hashes. Explicit RUN opening verifies the saved evidence. R9 values remain
strings exactly as written; no current P3 selection policy is applied to them.
"""
from __future__ import annotations

import csv
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
import hashlib
import io
import json
import os
from pathlib import Path
import re
import stat


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


def read_pairs(path):
    rows = list(csv.reader(io.StringIO(read_bytes(path).decode("utf-8-sig")), delimiter="\t"))
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
                rev = {"revision_id": revision.name, "path": str(revision)}
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
                if Decimal(summary.get(key, "")) != Decimal(str(expected)):
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
            "manifest": manifest, "files": files,
            "verification": {"ok": not errors, "errors": errors, "checked_files": len(digests),
                             "checked_at": utc_now(), "source_pixels_checked": False, "scientific_validation": False}}


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
