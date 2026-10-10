"""Prompt-3 scientific geometry, display preferences and derived caches.

The module enforces one hard separation:

* revision ``geometries`` are scientific authority;
* ``autosave/prompt3`` contains disposable operational state only;
* visibility never participates in a geometry or area fingerprint.

The area raster itself is produced by ImageJ's ``ByteProcessor`` in Fiji.  The
companion computes the closed fingerprint, validates the returned pixel count,
derives ``net_area_nm2`` itself and persists the result with a physical revision
binding.  Consequently RUN publication cannot accept an arbitrary area value
from the UI.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Mapping, Sequence
import re
import uuid

from cavity_tem_light_p1.canonical_json import canonical_json_bytes, loads_canonical_json
from cavity_tem_light_p1.errors import StaleContextError, TransactionError, ValidationError
from cavity_tem_light_p1.path_safety import PathSafetyError, plain_directory, stable_plain_bytes
from cavity_tem_light_p2 import vertical_manager as p2
from cavity_tem_light_p2.session_core import (
    CURRENT_REVISION_FIELDS,
    SessionCore,
    _require_timestamp,
    _replace_exact,
    _write_new,
    sha256_bytes,
    sha256_file,
    utc_now_z,
)
from cavity_tem_light_p3.spatial_scale import verify_spatial_scale_provenance


DISPLAY_PREFERENCES_SCHEMA = "CTL_P3_GEOMETRY_DISPLAY_PREFERENCES_V1"
GEOMETRY_CACHE_SCHEMA = "CTL_P3_ANALYSIS_GEOMETRY_CACHE_V2"
AREA_CACHE_SCHEMA = "CTL_P3_ANALYSIS_AREA_CACHE_V2"
AREA_RASTER_ALGORITHM = "IMAGEJ_BYTEPROCESSOR_FILL_V1"
AREA_FINGERPRINT_SCHEMA = "CTL_P3_ANALYSIS_AREA_INPUT_V2"
SPATIAL_CALIBRATION_EVIDENCE_NAME = "SPATIAL_CALIBRATION_EVIDENCE.json"

GEOMETRY_TYPES = ("analysis_mask", "exclusion", "surface")
PERSISTED_MODES = ("HIDDEN", "OUTLINE")
DEFAULT_MODES = {
    "analysis_mask": "OUTLINE",
    "exclusion": "OUTLINE",
    "surface": "OUTLINE",
}

_SHA_RE = re.compile(r"^[0-9a-f]{64}$", re.ASCII)


def _fail(message: str, **details: Any) -> None:
    raise ValidationError(message, details=details)


def _sha(value: Any, field: str) -> str:
    if not isinstance(value, str) or _SHA_RE.fullmatch(value) is None:
        _fail("Prompt-3 SHA-256 is malformed", field=field)
    return value


def _positive_int(value: Any, field: str) -> int:
    if isinstance(value, bool):
        _fail("Prompt-3 integer cannot be boolean", field=field)
    try:
        converted = int(value)
    except (TypeError, ValueError, OverflowError):
        _fail("Prompt-3 integer is invalid", field=field)
    if converted <= 0 or str(converted) != str(value).strip():
        _fail("Prompt-3 integer must be a canonical positive integer", field=field)
    return converted


def _nonnegative_int(value: Any, field: str) -> int:
    if isinstance(value, bool):
        _fail("Prompt-3 integer cannot be boolean", field=field)
    try:
        converted = int(value)
    except (TypeError, ValueError, OverflowError):
        _fail("Prompt-3 integer is invalid", field=field)
    if converted < 0 or str(converted) != str(value).strip():
        _fail("Prompt-3 integer must be canonical and non-negative", field=field)
    return converted


def _positive_decimal(value: Any, field: str) -> Decimal:
    if isinstance(value, bool):
        _fail("Prompt-3 decimal cannot be boolean", field=field)
    try:
        converted = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        _fail("Prompt-3 decimal is invalid", field=field)
    if not converted.is_finite() or converted <= 0:
        _fail("Prompt-3 decimal must be finite and positive", field=field)
    return converted


def _decimal_text(value: Decimal) -> str:
    normalized = value.normalize()
    text = format(normalized, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return "0" if text in {"", "-0"} else text


def _scope(core: SessionCore, image_uid: str, session_uid: str) -> dict[str, str]:
    return {
        "analysis_session_uid": session_uid,
        "image_uid": image_uid,
        "project_uid": core.project_uid,
    }


def _operational_root(record: Any) -> Path:
    root = record.session_root / "autosave" / "prompt3"
    root.mkdir(parents=True, exist_ok=True)
    try:
        plain_directory(root, label="Prompt-3 operational state")
    except PathSafetyError as exc:
        raise ValidationError(
            "Prompt-3 operational state path is unsafe",
            details={"path": str(root), "reason": str(exc)},
        ) from exc
    return root


def _read_optional_json(
    path: Path, label: str
) -> tuple[dict[str, Any] | None, str, str]:
    if not path.exists() and not path.is_symlink():
        return None, "NOT_APPLICABLE", "MISSING"
    try:
        raw = stable_plain_bytes(path, label=label)
    except PathSafetyError as exc:
        raise ValidationError(
            "Prompt-3 operational JSON path is unsafe",
            details={"path": str(path), "reason": str(exc)},
        ) from exc
    digest = sha256_bytes(raw)
    try:
        value = loads_canonical_json(raw)
        if not isinstance(value, dict):
            raise ValueError("JSON root is not an object")
        return value, digest, "VALID"
    except (ValidationError, ValueError, TypeError):
        # Preserve the exact corrupt-byte digest.  Automatic rebuilds must CAS
        # against the bytes inspected during preflight rather than accepting
        # whichever corrupt file happens to exist at write time.
        return None, digest, "CORRUPT"


def _write_operational_json(path: Path, value: Mapping[str, Any], expected_sha256: str) -> str:
    data = canonical_json_bytes(dict(value))
    token = "p3_" + uuid.uuid4().hex
    if expected_sha256 == "NOT_APPLICABLE":
        if path.exists() or path.is_symlink():
            raise StaleContextError("Prompt-3 operational target appeared after preflight")
        _write_new(path, data)
    else:
        _replace_exact(
            path,
            data,
            expected_sha256=_sha(expected_sha256, "expected_operational_sha256"),
            token=token,
        )
    observed = sha256_file(path)
    expected = sha256_bytes(data)
    if observed != expected:
        raise TransactionError("Prompt-3 operational JSON failed post-write verification")
    return observed


def _preferences_payload(
    scope: Mapping[str, str],
    *,
    generation: int,
    modes: Mapping[str, str],
    edit_fill_alpha: int,
    updated_at: str,
) -> dict[str, Any]:
    body = {
        "analysis_session_uid": scope["analysis_session_uid"],
        "authority": False,
        "edit_fill_alpha": edit_fill_alpha,
        "image_uid": scope["image_uid"],
        "modes": {key: modes[key] for key in GEOMETRY_TYPES},
        "preference_generation": generation,
        "project_uid": scope["project_uid"],
        "schema": DISPLAY_PREFERENCES_SCHEMA,
        "updated_at": updated_at,
    }
    body["payload_sha256"] = sha256_bytes(canonical_json_bytes(body))
    return body


def _validate_preferences(value: Mapping[str, Any], scope: Mapping[str, str]) -> dict[str, Any]:
    expected = {
        "analysis_session_uid",
        "authority",
        "edit_fill_alpha",
        "image_uid",
        "modes",
        "payload_sha256",
        "preference_generation",
        "project_uid",
        "schema",
        "updated_at",
    }
    if set(value) != expected or value.get("schema") != DISPLAY_PREFERENCES_SCHEMA:
        _fail("Prompt-3 display preference field inventory is not closed")
    if value.get("authority") is not False:
        _fail("Prompt-3 display preferences cannot claim scientific authority")
    for key, expected_value in scope.items():
        if value.get(key) != expected_value:
            _fail("Prompt-3 display preference scope mismatch", field=key)
    modes = value.get("modes")
    if not isinstance(modes, Mapping) or set(modes) != set(GEOMETRY_TYPES):
        _fail("Prompt-3 display modes are not closed")
    for geometry_type in GEOMETRY_TYPES:
        if modes[geometry_type] not in PERSISTED_MODES:
            _fail("EDIT or an unknown mode cannot be persisted", geometry_type=geometry_type)
    generation = _positive_int(value.get("preference_generation"), "preference_generation")
    alpha = _nonnegative_int(value.get("edit_fill_alpha"), "edit_fill_alpha")
    if alpha > 160:
        _fail("Prompt-3 edit alpha must be in [0,160]")
    _require_timestamp(value.get("updated_at"), "updated_at")
    without_hash = {key: item for key, item in value.items() if key != "payload_sha256"}
    if _sha(value.get("payload_sha256"), "payload_sha256") != sha256_bytes(
        canonical_json_bytes(without_hash)
    ):
        _fail("Prompt-3 display preference payload hash mismatch")
    return dict(value)


def load_display_preferences(record: Any, core: SessionCore) -> tuple[dict[str, Any], str]:
    scope = _scope(core, record.image_uid, record.analysis_session_uid)
    path = _operational_root(record) / "geometry_display_preferences.json"
    value, digest, _read_status = _read_optional_json(path, "Prompt-3 display preferences")
    if value is None:
        default = _preferences_payload(
            scope,
            generation=1,
            modes=DEFAULT_MODES,
            edit_fill_alpha=72,
            updated_at="1970-01-01T00:00:00Z",
        )
        return default, digest
    try:
        return _validate_preferences(value, scope), digest
    except ValidationError:
        default = _preferences_payload(
            scope,
            generation=1,
            modes=DEFAULT_MODES,
            edit_fill_alpha=72,
            updated_at="1970-01-01T00:00:00Z",
        )
        return default, digest


def set_display_mode(arguments: Mapping[str, Any]) -> dict[str, Any]:
    core = SessionCore(arguments["project_root"])
    image_uid = str(arguments["image_uid"])
    session_uid = str(arguments["analysis_session_uid"])
    record = p2._active_record(core, image_uid, session_uid)
    preferences, observed_sha = load_display_preferences(record, core)
    if "expected_preferences_sha256" not in arguments:
        _fail("Prompt-3 display preference caller snapshot SHA-256 is required")
    expected_sha = str(arguments["expected_preferences_sha256"])
    if expected_sha != observed_sha:
        raise StaleContextError("Prompt-3 display preference caller snapshot is stale")
    geometry_type = str(arguments["geometry_type"])
    mode = str(arguments["mode"])
    if mode not in PERSISTED_MODES:
        _fail("Prompt-3 persisted display mode must be HIDDEN or OUTLINE")
    modes = dict(preferences["modes"])
    if geometry_type == "all":
        modes = {key: mode for key in GEOMETRY_TYPES}
    elif geometry_type in GEOMETRY_TYPES:
        modes[geometry_type] = mode
    else:
        _fail("Prompt-3 geometry display type is invalid")
    alpha = _nonnegative_int(
        arguments.get("edit_fill_alpha", preferences["edit_fill_alpha"]),
        "edit_fill_alpha",
    )
    if alpha > 160:
        _fail("Prompt-3 edit alpha must be in [0,160]")
    updated = _preferences_payload(
        _scope(core, image_uid, session_uid),
        generation=int(preferences["preference_generation"]) + 1,
        modes=modes,
        edit_fill_alpha=alpha,
        updated_at=utc_now_z(),
    )
    path = _operational_root(record) / "geometry_display_preferences.json"
    digest = _write_operational_json(path, updated, observed_sha)
    return {
        "preferences": updated,
        "preferences_sha256": digest,
        "scientific_mutations": 0,
        "revision_mutations": 0,
        "run_mutations": 0,
    }


def _current_revision(
    core: SessionCore, record: Any, expected_pointer_sha256: str | None = None
) -> tuple[dict[str, Any], dict[str, Any], str, str]:
    pointer_path = record.session_root / "current_revision.tsv"
    pointer_sha = sha256_file(pointer_path)
    if expected_pointer_sha256 is not None and _sha(
        expected_pointer_sha256, "expected_revision_pointer_sha256"
    ) != pointer_sha:
        raise StaleContextError("Prompt-3 revision pointer caller snapshot is stale")
    pointer = p2._read_pointer(pointer_path, CURRENT_REVISION_FIELDS)
    if pointer is None:
        _fail("Prompt-3 geometry state requires an explicit current revision")
    revision_root = record.session_root / Path(pointer["relative_path"])
    manifest = core._verify_revision(record, revision_root)
    manifest_sha = sha256_file(revision_root / "revision_manifest.json")
    if manifest_sha != pointer["revision_manifest_sha256"]:
        _fail("Prompt-3 revision pointer does not bind the immutable manifest")
    if sha256_file(pointer_path) != pointer_sha:
        raise StaleContextError("Prompt-3 revision pointer changed during verified read")
    return pointer, manifest, manifest_sha, pointer_sha


def _assert_revision_pointer(record: Any, expected_sha256: str) -> None:
    if sha256_file(record.session_root / "current_revision.tsv") != expected_sha256:
        raise StaleContextError("Prompt-3 revision pointer changed during cache operation")


def _geometry_set_sha256(
    core: SessionCore, geometries: Sequence[Mapping[str, Any]]
) -> str:
    # Keep one hash domain for revision provenance, geometry cache, area cache
    # and RUN.  SessionCore also normalizes/sorts before hashing.
    return core.geometry_set_sha256(geometries)


def _canonical_copy(value: Any) -> Any:
    """Copy one nested value through the exact canonical JSON profile."""

    return loads_canonical_json(canonical_json_bytes({"value": value}))["value"]


def _image_context(
    arguments: Mapping[str, Any], provenance: Mapping[str, Any]
) -> dict[str, Any]:
    raw = arguments.get("image_context")
    if not isinstance(raw, Mapping):
        _fail("Prompt-3 image_context is required")
    width = _positive_int(raw.get("width_px"), "width_px")
    height = _positive_int(raw.get("height_px"), "height_px")
    calibration = provenance.get("calibration")
    evidence_sha = provenance.get("evidence_sha256")
    if not isinstance(calibration, Mapping):
        _fail("SPATIAL_SCALE_PROVENANCE_MISMATCH", field="calibration")
    scale_x = _positive_decimal(calibration.get("scale_x_nm_px"), "scale_x_nm_px")
    scale_y = _positive_decimal(calibration.get("scale_y_nm_px"), "scale_y_nm_px")
    evidence_sha = _sha(evidence_sha, "spatial_calibration_evidence_sha256")
    depth = raw.get(
        "depth_policy",
        {
            "exclude_negative_depth": False,
            "material_side": "NOT_APPLICABLE",
            "mode": "NONE",
        },
    )
    if not isinstance(depth, Mapping) or set(depth) != {
        "exclude_negative_depth",
        "material_side",
        "mode",
    }:
        _fail("Prompt-3 depth policy field inventory is not closed")
    if depth["mode"] not in {"NONE", "MATERIAL_SIDE"}:
        _fail("Prompt-3 depth policy mode is invalid")
    if not isinstance(depth["exclude_negative_depth"], bool):
        _fail("Prompt-3 depth exclusion flag must be boolean")
    if not isinstance(depth["material_side"], str) or not depth["material_side"]:
        _fail("Prompt-3 material side must be an explicit token")
    image_mode = raw.get(
        "image_mode",
        "with_surface" if depth["mode"] == "MATERIAL_SIDE" else "without_surface",
    )
    if image_mode not in {"with_surface", "without_surface"}:
        _fail("Prompt-3 image mode is invalid")
    expected_image_mode = (
        "with_surface" if depth["mode"] == "MATERIAL_SIDE" else "without_surface"
    )
    if image_mode != expected_image_mode:
        _fail("Prompt-3 image mode contradicts the depth policy")
    return {
        "depth_policy": dict(depth),
        "height_px": height,
        "image_mode": image_mode,
        "scale_x_nm_px": _decimal_text(scale_x),
        "scale_y_nm_px": _decimal_text(scale_y),
        "spatial_calibration_evidence_sha256": evidence_sha,
        "width_px": width,
    }


def _persist_spatial_calibration_evidence(
    record: Any,
    provenance: Mapping[str, Any],
    *,
    revision_pointer_sha256: str,
) -> tuple[str, str, str | None, bool]:
    """Publish the compact evidence by no-replace/CAS before any cache.

    Exact replay is a read-only hit.  A different but independently verified
    revision binding is replaced only against the byte snapshot inspected in
    this preflight; a concurrent writer therefore fails closed.
    """

    evidence = provenance.get("evidence")
    expected_digest = _sha(
        provenance.get("evidence_sha256"), "spatial_calibration_evidence_sha256"
    )
    if not isinstance(evidence, Mapping):
        _fail("SPATIAL_SCALE_PROVENANCE_MISMATCH", field="evidence")
    if sha256_bytes(canonical_json_bytes(dict(evidence))) != expected_digest:
        _fail("SPATIAL_SCALE_PROVENANCE_MISMATCH", field="evidence_sha256")
    operational = _operational_root(record)
    path = operational / SPATIAL_CALIBRATION_EVIDENCE_NAME
    existing, observed_sha, read_status = _read_optional_json(
        path, "Prompt-3 spatial calibration evidence"
    )
    if existing == dict(evidence) and observed_sha == expected_digest:
        return expected_digest, "HIT", observed_sha, False
    revision_fields = {
        "revision_id",
        "revision_manifest_sha256",
        "revision_uid",
    }
    revision_only_change = (
        isinstance(existing, Mapping)
        and set(existing) == set(evidence)
        and {
            key: value
            for key, value in existing.items()
            if key not in revision_fields
        }
        == {
            key: value
            for key, value in evidence.items()
            if key not in revision_fields
        }
        and any(existing.get(key) != evidence.get(key) for key in revision_fields)
    )
    previous_digest = observed_sha if isinstance(existing, Mapping) else None
    _assert_revision_pointer(record, revision_pointer_sha256)
    written_sha = _write_operational_json(path, evidence, observed_sha)
    _assert_revision_pointer(record, revision_pointer_sha256)
    if written_sha != expected_digest:
        raise TransactionError("Prompt-3 spatial calibration evidence digest changed")
    return (
        written_sha,
        (
            "PUBLISHED_NO_REPLACE"
            if read_status == "MISSING"
            else "REPLACED_BY_VERIFIED_CAS"
        ),
        previous_digest,
        revision_only_change,
    )


def _area_input(
    core: SessionCore,
    geometries: Sequence[Mapping[str, Any]],
    image_context: Mapping[str, Any],
) -> dict[str, Any]:
    geometry_set_sha = _geometry_set_sha256(core, geometries)
    types = {item["geometry_type"] for item in geometries}
    value = {
        "depth_policy": dict(image_context["depth_policy"]),
        "geometry_set_sha256": geometry_set_sha,
        "height_px": image_context["height_px"],
        "image_mode": image_context["image_mode"],
        "raster_algorithm": AREA_RASTER_ALGORITHM,
        "scale_x_nm_px": image_context["scale_x_nm_px"],
        "scale_y_nm_px": image_context["scale_y_nm_px"],
        "schema": AREA_FINGERPRINT_SCHEMA,
        "spatial_calibration_evidence_sha256": image_context[
            "spatial_calibration_evidence_sha256"
        ],
        "use_whole_image": "analysis_mask" not in types,
        "width_px": image_context["width_px"],
    }
    value["input_fingerprint_sha256"] = sha256_bytes(canonical_json_bytes(value))
    return value


def _geometry_cache_payload(
    core: SessionCore,
    record: Any,
    pointer: Mapping[str, Any],
    manifest_sha: str,
    geometries: Sequence[Mapping[str, Any]],
    image_context: Mapping[str, Any],
) -> dict[str, Any]:
    derived: list[dict[str, Any]] = []
    for item in geometries:
        derived.append(
            {
                "bounds": _canonical_copy(item["bounds"]),
                "coordinates": _canonical_copy(item["coordinates"]),
                "geometry_id": item["geometry_id"],
                "geometry_schema": item["geometry_schema"],
                "geometry_sha256": item["geometry_sha256"],
                "geometry_type": item["geometry_type"],
                "geometry_uid": item["geometry_uid"],
                "labels": _canonical_copy(item["labels"]),
                "source_roi_sha256": item["source_roi_sha256"],
            }
        )
    value = {
        "analysis_session_uid": record.analysis_session_uid,
        "authority": False,
        "geometry_set_sha256": _geometry_set_sha256(core, geometries),
        "geometries": derived,
        "image_uid": record.image_uid,
        "project_uid": core.project_uid,
        "revision_id": pointer["revision_id"],
        "revision_manifest_sha256": manifest_sha,
        "revision_uid": pointer["revision_uid"],
        "scale_x_nm_px": image_context["scale_x_nm_px"],
        "scale_y_nm_px": image_context["scale_y_nm_px"],
        "schema": GEOMETRY_CACHE_SCHEMA,
        "spatial_calibration_evidence_sha256": image_context[
            "spatial_calibration_evidence_sha256"
        ],
    }
    value["payload_sha256"] = sha256_bytes(canonical_json_bytes(value))
    return value


def _geometry_cache_matches(
    value: Mapping[str, Any], expected: Mapping[str, Any]
) -> bool:
    if set(value) != set(expected) or value != expected:
        return False
    payload = {key: item for key, item in value.items() if key != "payload_sha256"}
    return value.get("payload_sha256") == sha256_bytes(canonical_json_bytes(payload))


def _validate_area_cache(
    value: Mapping[str, Any],
    *,
    scope: Mapping[str, str],
    area_input: Mapping[str, Any],
) -> dict[str, Any]:
    required = {
        "analysis_session_uid",
        "authority",
        "geometry_set_sha256",
        "image_uid",
        "input_fingerprint_sha256",
        "net_area_nm2",
        "payload_sha256",
        "project_uid",
        "raster_algorithm",
        "revision_id",
        "revision_manifest_sha256",
        "revision_uid",
        "schema",
        "spatial_calibration_evidence_sha256",
        "valid_pixel_count",
    }
    if set(value) != required or value.get("schema") != AREA_CACHE_SCHEMA:
        _fail("Prompt-3 area cache inventory is not closed")
    if value.get("authority") is not False:
        _fail("Prompt-3 area cache cannot claim scientific authority")
    for key, expected in scope.items():
        if value.get(key) != expected:
            _fail("Prompt-3 area cache scope mismatch", field=key)
    if value.get("geometry_set_sha256") != area_input["geometry_set_sha256"]:
        _fail("Prompt-3 area cache geometry set is stale")
    if value.get("input_fingerprint_sha256") != area_input["input_fingerprint_sha256"]:
        _fail("Prompt-3 area cache scientific input is stale")
    if value.get("raster_algorithm") != AREA_RASTER_ALGORITHM:
        _fail("Prompt-3 area raster algorithm mismatch")
    if value.get("spatial_calibration_evidence_sha256") != area_input[
        "spatial_calibration_evidence_sha256"
    ]:
        _fail("Prompt-3 area cache spatial calibration evidence is stale")
    count = _nonnegative_int(value.get("valid_pixel_count"), "valid_pixel_count")
    max_count = int(area_input["width_px"]) * int(area_input["height_px"])
    if count > max_count:
        _fail("Prompt-3 area cache pixel count exceeds the image")
    sx = Decimal(str(area_input["scale_x_nm_px"]))
    sy = Decimal(str(area_input["scale_y_nm_px"]))
    expected_area = _decimal_text(Decimal(count) * sx * sy)
    if value.get("net_area_nm2") != expected_area:
        _fail("Prompt-3 area cache denominator does not derive from pixel count and XY scale")
    payload = {key: item for key, item in value.items() if key != "payload_sha256"}
    if _sha(value.get("payload_sha256"), "payload_sha256") != sha256_bytes(
        canonical_json_bytes(payload)
    ):
        _fail("Prompt-3 area cache payload hash mismatch")
    for field in (
        "revision_manifest_sha256",
        "spatial_calibration_evidence_sha256",
    ):
        _sha(value.get(field), field)
    return dict(value)


def _rebind_area_cache(
    value: Mapping[str, Any],
    pointer: Mapping[str, Any],
    manifest_sha: str,
    area_input: Mapping[str, Any],
) -> dict[str, Any]:
    rebound = dict(value)
    rebound.update(
        {
            "revision_id": pointer["revision_id"],
            "revision_manifest_sha256": manifest_sha,
            "revision_uid": pointer["revision_uid"],
            "input_fingerprint_sha256": area_input["input_fingerprint_sha256"],
            "spatial_calibration_evidence_sha256": area_input[
                "spatial_calibration_evidence_sha256"
            ],
        }
    )
    rebound.pop("payload_sha256", None)
    rebound["payload_sha256"] = sha256_bytes(canonical_json_bytes(rebound))
    return rebound


def prepare_geometry_state(arguments: Mapping[str, Any]) -> dict[str, Any]:
    core = SessionCore(arguments["project_root"])
    image_uid = str(arguments["image_uid"])
    session_uid = str(arguments["analysis_session_uid"])
    record = p2._active_record(core, image_uid, session_uid)
    pointer, manifest, manifest_sha, pointer_sha = _current_revision(
        core,
        record,
        arguments.get("expected_revision_pointer_sha256"),
    )
    geometries = core._normalize_revision_geometries(manifest.get("geometries", []))
    raw_image_context = arguments.get("image_context")
    if not isinstance(raw_image_context, Mapping):
        _fail("Prompt-3 image_context is required")
    provenance = verify_spatial_scale_provenance(
        core=core,
        record=record,
        revision_manifest=manifest,
        revision_manifest_sha256=manifest_sha,
        image_context=raw_image_context,
    )
    image_context = _image_context(arguments, provenance)
    (
        evidence_sha,
        evidence_status,
        previous_evidence_sha,
        revision_only_evidence_change,
    ) = _persist_spatial_calibration_evidence(
        record, provenance, revision_pointer_sha256=pointer_sha
    )
    operational = _operational_root(record)

    expected_geometry_cache = _geometry_cache_payload(
        core, record, pointer, manifest_sha, geometries, image_context
    )
    geometry_path = operational / "analysis_geometry.json"
    existing_geometry, geometry_sha, geometry_read_status = _read_optional_json(
        geometry_path, "Prompt-3 analysis geometry cache"
    )
    geometry_cache_status = "HIT"
    if existing_geometry is None or not _geometry_cache_matches(
        existing_geometry, expected_geometry_cache
    ):
        geometry_cache_status = (
            "CORRUPT_REBUILT_FROM_REVISION"
            if geometry_read_status == "CORRUPT"
            else "STALE_OR_MISSING_REBUILT_FROM_REVISION"
        )
        _assert_revision_pointer(record, pointer_sha)
        geometry_sha = _write_operational_json(
            geometry_path, expected_geometry_cache, geometry_sha
        )
        _assert_revision_pointer(record, pointer_sha)

    area_input = _area_input(core, geometries, image_context)
    area_path = operational / "analysis_area_cache.json"
    existing_area, area_sha, _area_read_status = _read_optional_json(
        area_path, "Prompt-3 analysis area cache"
    )
    area_cache: dict[str, Any] | None = None
    area_status = "RECALCULATION_REQUIRED"
    if existing_area is not None:
        try:
            area_cache = _validate_area_cache(
                existing_area,
                scope=_scope(core, image_uid, session_uid),
                area_input=area_input,
            )
            current_binding = (
                area_cache["revision_id"] == pointer["revision_id"]
                and area_cache["revision_uid"] == pointer["revision_uid"]
                and area_cache["revision_manifest_sha256"] == manifest_sha
            )
            if current_binding:
                area_status = "HIT"
            else:
                area_cache = _rebind_area_cache(
                    area_cache, pointer, manifest_sha, area_input
                )
                _assert_revision_pointer(record, pointer_sha)
                area_sha = _write_operational_json(area_path, area_cache, area_sha)
                _assert_revision_pointer(record, pointer_sha)
                area_status = "REBOUND_WITHOUT_RASTER_RECALCULATION"
        except ValidationError:
            # A cavity-only revision changes the full evidence record only in
            # its current-revision identity.  Prove that exact delta, then
            # validate the cache against its prior evidence hash and the same
            # closed geometry/raster inputs before rebinding it by CAS.  Any
            # scale, source, baseline, REV_000005, geometry or policy change
            # still fails closed and requires a fresh Fiji raster count.
            if revision_only_evidence_change and previous_evidence_sha is not None:
                prior_context = dict(image_context)
                prior_context["spatial_calibration_evidence_sha256"] = (
                    previous_evidence_sha
                )
                prior_area_input = _area_input(core, geometries, prior_context)
                try:
                    area_cache = _validate_area_cache(
                        existing_area,
                        scope=_scope(core, image_uid, session_uid),
                        area_input=prior_area_input,
                    )
                    area_cache = _rebind_area_cache(
                        area_cache, pointer, manifest_sha, area_input
                    )
                    _assert_revision_pointer(record, pointer_sha)
                    area_sha = _write_operational_json(
                        area_path, area_cache, area_sha
                    )
                    _assert_revision_pointer(record, pointer_sha)
                    area_status = "REBOUND_WITHOUT_RASTER_RECALCULATION"
                except ValidationError:
                    area_cache = None
                    area_status = "CORRUPT_OR_STALE_RECALCULATION_REQUIRED"
            else:
                area_cache = None
                area_status = "CORRUPT_OR_STALE_RECALCULATION_REQUIRED"
    preferences, preferences_sha = load_display_preferences(record, core)
    _assert_revision_pointer(record, pointer_sha)
    return {
        "analysis_area_cache": area_cache,
        "analysis_area_cache_sha256": area_sha,
        "analysis_area_cache_status": area_status,
        "analysis_geometry": expected_geometry_cache,
        "analysis_geometry_sha256": geometry_sha,
        "analysis_geometry_status": geometry_cache_status,
        "area_input": area_input,
        "geometries": geometries,
        "legacy_quarantine_input_count": 0,
        "preferences": preferences,
        "preferences_sha256": preferences_sha,
        "revision_binding": {
            "revision_id": pointer["revision_id"],
            "revision_manifest_sha256": manifest_sha,
            "revision_pointer_sha256": pointer_sha,
            "revision_uid": pointer["revision_uid"],
        },
        "spatial_calibration_evidence": provenance["evidence"],
        "spatial_calibration_evidence_sha256": evidence_sha,
        "spatial_calibration_evidence_status": evidence_status,
    }


def commit_analysis_area_cache(arguments: Mapping[str, Any]) -> dict[str, Any]:
    core = SessionCore(arguments["project_root"])
    image_uid = str(arguments["image_uid"])
    session_uid = str(arguments["analysis_session_uid"])
    record = p2._active_record(core, image_uid, session_uid)
    pointer, manifest, manifest_sha, pointer_sha = _current_revision(
        core,
        record,
        str(arguments["expected_revision_pointer_sha256"]),
    )
    geometries = core._normalize_revision_geometries(manifest.get("geometries", []))
    raw_image_context = arguments.get("image_context")
    if not isinstance(raw_image_context, Mapping):
        _fail("Prompt-3 image_context is required")
    provenance = verify_spatial_scale_provenance(
        core=core,
        record=record,
        revision_manifest=manifest,
        revision_manifest_sha256=manifest_sha,
        image_context=raw_image_context,
    )
    image_context = _image_context(arguments, provenance)
    area_input = _area_input(core, geometries, image_context)
    if _sha(arguments.get("input_fingerprint_sha256"), "input_fingerprint_sha256") != area_input[
        "input_fingerprint_sha256"
    ]:
        raise StaleContextError("Prompt-3 Fiji raster input fingerprint is stale")
    evidence_sha, evidence_status, _previous_evidence_sha, _revision_only = (
        _persist_spatial_calibration_evidence(
        record, provenance, revision_pointer_sha256=pointer_sha
        )
    )
    count = _nonnegative_int(arguments.get("valid_pixel_count"), "valid_pixel_count")
    maximum = image_context["width_px"] * image_context["height_px"]
    if count > maximum:
        _fail("Prompt-3 Fiji raster pixel count exceeds the image")
    sx = Decimal(image_context["scale_x_nm_px"])
    sy = Decimal(image_context["scale_y_nm_px"])
    payload = {
        **_scope(core, image_uid, session_uid),
        "authority": False,
        "geometry_set_sha256": area_input["geometry_set_sha256"],
        "input_fingerprint_sha256": area_input["input_fingerprint_sha256"],
        "net_area_nm2": _decimal_text(Decimal(count) * sx * sy),
        "raster_algorithm": AREA_RASTER_ALGORITHM,
        "revision_id": pointer["revision_id"],
        "revision_manifest_sha256": manifest_sha,
        "revision_uid": pointer["revision_uid"],
        "schema": AREA_CACHE_SCHEMA,
        "spatial_calibration_evidence_sha256": evidence_sha,
        "valid_pixel_count": count,
    }
    payload["payload_sha256"] = sha256_bytes(canonical_json_bytes(payload))
    path = _operational_root(record) / "analysis_area_cache.json"
    _existing, observed_sha, _read_status = _read_optional_json(
        path, "Prompt-3 analysis area cache"
    )
    if "expected_area_cache_sha256" not in arguments:
        _fail("Prompt-3 area-cache caller snapshot SHA-256 is required")
    expected_sha = str(arguments["expected_area_cache_sha256"])
    if expected_sha != observed_sha:
        raise StaleContextError("Prompt-3 area-cache caller snapshot is stale")
    _assert_revision_pointer(record, pointer_sha)
    digest = _write_operational_json(path, payload, observed_sha)
    _assert_revision_pointer(record, pointer_sha)
    return {
        "analysis_area_cache": payload,
        "analysis_area_cache_sha256": digest,
        "analysis_area_cache_status": "COMMITTED_FROM_VERIFIED_FIJI_RASTER",
        "scientific_revision_mutations": 0,
        "spatial_calibration_evidence": provenance["evidence"],
        "spatial_calibration_evidence_sha256": evidence_sha,
        "spatial_calibration_evidence_status": evidence_status,
        "visibility_inputs": 0,
    }


def area_cache_for_run(arguments: Mapping[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    state = prepare_geometry_state(arguments)
    cache = state["analysis_area_cache"]
    if cache is None or state["analysis_area_cache_status"] not in {
        "HIT",
        "REBOUND_WITHOUT_RASTER_RECALCULATION",
    }:
        _fail("Prompt-3 RUN requires a current verified analysis area cache")
    if int(cache["valid_pixel_count"]) <= 0:
        _fail("Prompt-3 RUN requires a positive scientific analysis area")
    return cache, state


__all__ = [
    "AREA_CACHE_SCHEMA",
    "AREA_FINGERPRINT_SCHEMA",
    "AREA_RASTER_ALGORITHM",
    "DEFAULT_MODES",
    "DISPLAY_PREFERENCES_SCHEMA",
    "GEOMETRY_CACHE_SCHEMA",
    "GEOMETRY_TYPES",
    "PERSISTED_MODES",
    "SPATIAL_CALIBRATION_EVIDENCE_NAME",
    "area_cache_for_run",
    "commit_analysis_area_cache",
    "load_display_preferences",
    "prepare_geometry_state",
    "set_display_mode",
]
