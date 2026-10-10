"""Small Fiji onboarding bridge over the existing immutable session core.

Fiji supplies decoded pixel evidence; this module does not decode DM files or
certify calibration. It independently binds source bytes, normalizes the raw
calibration, and records the explicitly entered hierarchy as user declarations.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping
import hashlib
import uuid

from cavity_tem_light_p1.canonical_json import canonical_json_bytes, loads_canonical_json
from cavity_tem_light_p1.errors import StaleContextError, TransactionError, ValidationError
from cavity_tem_light_p1.path_safety import (
    PathSafetyError, plain_directory, plain_file, reject_reparse_chain,
    rename_file_no_replace, stable_plain_bytes,
)
from cavity_tem_light_p2.session_core import SessionCore, _safe_component, _write_new
from cavity_tem_light_p2.vertical_manager import _require_sha, _source_blob_path
from .spatial_scale import normalize_spatial_calibration


PROVENANCE_SCHEMA = "CTL_P3_FIJI_SOURCE_IMPORT_V1"
PIXEL_METHOD = "CTL_MASTER_PIXEL_SHA256_V1"
_HIERARCHY = ("study_id", "condition_id", "specimen_id", "lamella_id", "image_id")


def _mapping(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValidationError(f"{label}: falta un objeto de datos explícito")
    return value


def _text(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip() or any(c in value for c in "\x00\r\n"):
        raise ValidationError(f"{label}: introduzca un valor explícito sin saltos de línea")
    return value


def _path(value: Any, label: str, *, new: bool = False) -> Path:
    try:
        return reject_reparse_chain(_text(value, label), label=label, must_exist=not new)
    except (PathSafetyError, OSError) as exc:
        raise ValidationError(f"{label}: la ruta no es local, absoluta y verificable", details={"reason": str(exc)}) from exc


def _core(arguments: Mapping[str, Any]) -> SessionCore:
    root = _path(arguments.get("project_root"), "project_root")
    core = SessionCore(root)
    if arguments.get("expected_project_uid") != core.project_uid:
        raise StaleContextError("El proyecto cambió desde la última lectura. Ábralo de nuevo antes de continuar.")
    return core


def _positive_integer(value: Any, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValidationError(f"{label}: se requiere un entero positivo")
    return value


def _verified_context(raw: Any, source_sha: str) -> dict[str, Any]:
    context = _mapping(raw, "image_context")
    evidence = _mapping(context.get("master_pixel_evidence"), "master_pixel_evidence")
    dimensions = {key: _positive_integer(context.get(key), key) for key in ("width_px", "height_px", "bit_depth")}
    if dimensions["bit_depth"] not in (8, 16, 24, 32):
        raise ValidationError("La profundidad de píxeles no está soportada")
    if (
        evidence.get("schema") != "CTL_P3_MASKS_MASTER_PIXEL_EVIDENCE_V1"
        or evidence.get("method") != PIXEL_METHOD
        or evidence.get("source_sha256") != source_sha
        or any(evidence.get(key) != value for key, value in (
            ("width", dimensions["width_px"]), ("height", dimensions["height_px"]),
            ("bit_depth", dimensions["bit_depth"]), ("channels", 1), ("slices", 1), ("frames", 1),
        ))
    ):
        raise ValidationError("La evidencia de Fiji no corresponde a esta fuente y a una imagen plana de un canal")
    _require_sha(evidence.get("sha256"), "master_pixel_evidence.sha256")
    spatial = normalize_spatial_calibration(context)
    # Only import-relevant facts are immutable provenance. Runtime analysis
    # settings, image titles and active session identifiers are deliberately absent.
    return {
        **dimensions, **spatial,
        "decoder_opening_method": _text(context.get("decoder_opening_method"), "decoder_opening_method"),
        "fiji_imagej_version": _text(context.get("fiji_imagej_version"), "fiji_imagej_version"),
        "master_pixel_evidence": {
            key: evidence[key] for key in (
                "schema", "method", "sha256", "source_sha256", "width", "height", "bit_depth", "channels", "slices", "frames",
            )
        },
        "scale_method": "FIJI_CALIBRATION_UNIT_NORMALIZED_CLOSED_V1",
        "scientific_validation": False,
    }


def create_project(arguments: Mapping[str, Any]) -> dict[str, Any]:
    root = _path(arguments.get("project_root"), "project_root", new=True)
    project_id = _safe_component(arguments.get("project_id"), "project_id")
    try:
        plain_directory(root.parent, label="carpeta contenedora del proyecto")
        core = SessionCore.create(root, project_uid=str(uuid.uuid4()), project_id=project_id)
    except (PathSafetyError, OSError) as exc:
        raise TransactionError(
            "No se pudo crear el proyecto. Se conserva cualquier estado parcial para su recuperación.",
            details={"project_root": str(root), "reason": str(exc)},
        ) from exc
    return {"project_root": str(core.root), "project_uid": core.project_uid, "project_id": core.project_id}


def register_source_image(arguments: Mapping[str, Any]) -> dict[str, Any]:
    core = _core(arguments)
    ids = {key: _safe_component(arguments.get(key), key) for key in _HIERARCHY}
    session_id = _safe_component(arguments.get("analysis_session_id"), "analysis_session_id")
    operator = _text(arguments.get("operator_id"), "operator_id")
    source = _path(arguments.get("source_path"), "source_path")
    if source.suffix.lower() not in (".dm3", ".dm4"):
        raise ValidationError("Seleccione una fuente DM3 o DM4 original")
    expected_sha = _require_sha(arguments.get("source_sha256"), "source_sha256")
    context = _verified_context(arguments.get("image_context"), expected_sha)
    try:
        source_bytes = stable_plain_bytes(source, label="fuente TEM original")
    except (PathSafetyError, OSError) as exc:
        raise ValidationError("No se pudo leer una fuente TEM estable", details={"source_path": str(source), "reason": str(exc)}) from exc
    source_sha = hashlib.sha256(source_bytes).hexdigest()
    if source_sha != expected_sha:
        raise StaleContextError("La fuente cambió desde que Fiji la abrió. Vuelva a abrirla antes de añadirla.")
    if not source_bytes:
        raise ValidationError("La fuente TEM está vacía")
    provenance = {
        "schema": PROVENANCE_SCHEMA,
        "hierarchy_origin": "USER_ENTERED_NOT_INFERRED_FROM_FILENAME",
        "hierarchy_declaration": ids,
        "operator_id": operator,
        "source_path_at_import": str(source),
        "source_file_name": source.name,
        "source_sha256": source_sha,
        "initial_image_context": context,
        "scientific_validation": False,
    }
    provenance_sha = hashlib.sha256(canonical_json_bytes(provenance)).hexdigest()
    # Keep duplicate detection and the existing journalled registration under
    # the same core lock. Public register_source_image takes this very lock;
    # its locked implementation avoids a nested Windows lock here.
    with core._source_registry_writer_lock():
        core = _core(arguments)  # Recheck project identity immediately before mutation.
        core._reconcile_source_registry_journals(_source_lock_held=True)
        registry = core._source_registry()
        same_id = [row for row in registry["image_bindings"] if all(row[key] == ids[key] for key in _HIERARCHY)]
        same_source = [row for row in registry["image_bindings"] if row["source_sha256"] == source_sha]
        if same_id:
            existing = same_id[0]
            if existing["source_sha256"] != source_sha or existing["identity_provenance_sha256"] != provenance_sha:
                raise ValidationError(
                    "Esa imagen ya existe con otra fuente o procedencia. No se ha sustituido nada.",
                    details={"reason_code": "IMAGE_ID_ALREADY_REGISTERED", "image_uid": existing["image_uid"]},
                )
            binding = existing
            registration_status = "ALREADY_REGISTERED"
        elif same_source:
            raise ValidationError(
                "Esta fuente ya está incorporada al proyecto. Abra su imagen existente para continuar.",
                details={"reason_code": "SOURCE_ALREADY_REGISTERED", "image_uid": same_source[0]["image_uid"], "image_id": same_source[0]["image_id"]},
            )
        else:
            result = core._register_source_image_locked(
                source_bytes, **ids, identity_provenance=provenance, source_file_name=source.name,
                master_pixel_hash_method=PIXEL_METHOD, master_pixel_hash_status="VERIFIED",
                master_pixel_sha256=context["master_pixel_evidence"]["sha256"],
            )
            binding = core._binding(result.image_uid)
            registration_status = "REGISTERED"
    image_uid = binding["image_uid"]
    rows = core._read_registry(image_uid)
    matching = [row for row in rows if row["analysis_session_id"] == session_id]
    if matching:
        record = core.session_by_uid(image_uid, matching[0]["analysis_session_uid"])
        session_status = "EXISTING"
    elif rows:
        raise ValidationError(
            "La imagen ya tiene sesiones. Use Abrir sesión o Crear sesión; no se ha añadido otra automáticamente.",
            details={"reason_code": "IMAGE_ALREADY_HAS_SESSIONS", "image_uid": image_uid},
        )
    else:
        try:
            record = core.create_empty_session(image_uid, analysis_session_id=session_id)
            session_status = "CREATED" if registration_status == "REGISTERED" else "RECOVERED_AFTER_SOURCE_REGISTRATION"
        except Exception as exc:
            raise TransactionError(
                "La fuente está conservada, pero no se completó la sesión. Reabra el proyecto; puede repetir el alta con los mismos datos. Si hay una sesión parcial, consérvela para recuperación.",
                details={"reason_code": "SOURCE_SAVED_SESSION_PENDING", "project_root": str(core.root), "image_uid": image_uid, "analysis_session_id": session_id, "source_sha256": source_sha, "reason": str(exc)},
            ) from exc
    return {
        "project_root": str(core.root), "project_uid": core.project_uid,
        "image_uid": image_uid, "image_id": ids["image_id"],
        "analysis_session_uid": record.analysis_session_uid, "analysis_session_id": record.analysis_session_id,
        "source_sha256": source_sha, "master_pixel_sha256": binding["master_pixel_sha256"],
        "registration_status": registration_status, "session_status": session_status,
        "initial_image_context": context,
    }


def source_image_context(arguments: Mapping[str, Any]) -> dict[str, Any]:
    core = _core(arguments)
    binding = core._binding(arguments.get("image_uid"))
    source_path = _source_blob_path(core, binding)
    source_bytes = stable_plain_bytes(source_path, label="fuente inmutable registrada")
    if hashlib.sha256(source_bytes).hexdigest() != binding["source_sha256"]:
        raise ValidationError("La fuente registrada no coincide con su huella")
    descriptor = loads_canonical_json(stable_plain_bytes(core._image_root(binding["image_uid"]) / "image.json", label="procedencia de imagen"))
    provenance = descriptor["identity_provenance"]
    initial_context = provenance.get("initial_image_context") if provenance.get("schema") == PROVENANCE_SCHEMA else None
    if initial_context is not None:
        initial_context = _verified_context(initial_context, binding["source_sha256"])
        if initial_context["master_pixel_evidence"]["sha256"] != binding["master_pixel_sha256"]:
            raise ValidationError("La procedencia inicial contradice los píxeles registrados")
    if arguments.get("cache_directory") is not None:
        try:
            cache = plain_directory(arguments["cache_directory"], label="caché externa de originales")
            if cache == core.root or core.root in cache.parents:
                raise ValidationError("La caché de apertura debe estar fuera del proyecto")
            suffix = Path(binding["source_file_name"]).suffix.lower()
            if suffix not in (".dm3", ".dm4"):
                raise ValidationError("La apertura guiada solo admite las fuentes DM3 y DM4 registradas")
            cached = cache / ("CTL_" + binding["source_sha256"] + suffix)
            if not cached.exists() and not cached.is_symlink():
                partial = cache / ("." + cached.name + ".partial." + uuid.uuid4().hex)
                _write_new(partial, source_bytes)
                rename_file_no_replace(partial, cached, error_type=TransactionError)
            if stable_plain_bytes(cached, label="copia de apertura") != source_bytes:
                raise ValidationError("La copia de apertura fue modificada. Se conserva y no se sustituye; use otra carpeta de caché.")
            source_path = plain_file(cached, label="original para abrir en Fiji")
        except (PathSafetyError, OSError) as exc:
            raise ValidationError("No se pudo preparar una copia de apertura verificable", details={"reason": str(exc)}) from exc
    return {
        "project_root": str(core.root), "project_uid": core.project_uid,
        "image_uid": binding["image_uid"], "image_id": binding["image_id"],
        "source_path": str(source_path), "source_file_name": binding["source_file_name"],
        "source_sha256": binding["source_sha256"],
        "master_pixel_sha256": binding["master_pixel_sha256"],
        "master_pixel_hash_method": binding["master_pixel_hash_method"],
        "master_pixel_hash_status": binding["master_pixel_hash_status"],
        "initial_image_context": initial_context,
    }
