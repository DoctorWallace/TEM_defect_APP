"""Prompt-2 vertical integration service and file bridge.

The approved :mod:`session_core` remains the storage authority.  This module
adds the smallest product-facing orchestration layer needed by the Fiji
technical preview: explicit session actions, revision/RUN publication,
read-only inspection and calls into the separately tested migration and
archive adapters.

Every mutating request is bound to caller-observed hashes or generations.
The command-line bridge reads one immutable request file and creates one new
response file outside the scientific project.  It never communicates through
stdout parsing or a shared mutable "latest" file.
"""

from __future__ import annotations

import argparse
import csv
from dataclasses import asdict
from decimal import Decimal, InvalidOperation
import hashlib
import io
import os
from pathlib import Path
import re
import sys
from types import SimpleNamespace
from typing import Any, Callable, Mapping, Sequence
import uuid

from cavity_tem_light_p1.canonical_json import (
    canonical_json_bytes,
    loads_canonical_json,
)
from cavity_tem_light_p1.errors import (
    StaleContextError,
    TransactionError,
    ValidationError,
)
from cavity_tem_light_p1.identity import new_uuid4_identity, validate_canonical_uuid
from cavity_tem_light_p1.object_table import (
    PreparedObjectTable,
    _geometry,
    render_object_table,
)
from cavity_tem_light_p1.object_table_profile import load_object_table_profile
from cavity_tem_light_p1.run_context import load_run_context
from cavity_tem_light_p1.science import zero_event_summary
from cavity_tem_light_p1.path_safety import stable_plain_bytes

from .session_core import (
    CURRENT_REVISION_FIELDS,
    CURRENT_RUN_FIELDS,
    CURRENT_SESSION_FIELDS,
    SESSION_REGISTRY_FIELDS,
    SessionCore,
    _contained,
    _parse_tsv,
    _replace_exact,
    _restore_exact,
    _tsv_bytes,
    _write_new,
    sha256_bytes,
    sha256_file,
    snapshot_tree,
    utc_now_z,
    validate_project,
)


REQUEST_SCHEMA = "CTL_P2_VERTICAL_BRIDGE_REQUEST_V1"
RESPONSE_SCHEMA = "CTL_P2_VERTICAL_BRIDGE_RESPONSE_V1"
ROI_SNAPSHOT_SCHEMA = "CTL_P2_VERTICAL_FIJI_ROI_SNAPSHOT_V1"
SESSION_TRANSITION_JOURNAL_SCHEMA = "CTL_P2_VERTICAL_SESSION_TRANSITION_JOURNAL_V1"

_SHA_RE = re.compile(r"[0-9a-f]{64}")
_ID_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}")
_CAVITY_RE = re.compile(r"CAV_[0-9]{6}")


def _require_mapping(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValidationError(f"{label} must be an object")
    return value


def _jsonable(value: Any) -> Any:
    """Convert result objects without weakening canonical JSON input rules."""

    if isinstance(value, Path):
        return str(value)
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, Mapping):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    return value


def _require_sequence(value: Any, label: str) -> Sequence[Any]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise ValidationError(f"{label} must be an array")
    return value


def _require_id(value: Any, label: str) -> str:
    if not isinstance(value, str) or _ID_RE.fullmatch(value) is None:
        raise ValidationError(f"{label} is not a canonical identifier")
    return value


def _require_sha(value: Any, label: str) -> str:
    if not isinstance(value, str) or _SHA_RE.fullmatch(value) is None:
        raise ValidationError(f"{label} is not a lowercase SHA-256")
    return value


def _require_uuid4(value: Any, label: str) -> str:
    try:
        parsed = uuid.UUID(str(value))
    except (ValueError, AttributeError, TypeError) as exc:
        raise ValidationError(f"{label} is not a UUID") from exc
    if parsed.version != 4 or str(parsed) != str(value):
        raise ValidationError(f"{label} is not a canonical UUIDv4")
    return str(parsed)


def _decimal(value: Any, label: str, *, positive: bool = False) -> Decimal:
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise ValidationError(f"{label} is not a decimal") from exc
    if not result.is_finite() or (positive and result <= 0):
        raise ValidationError(f"{label} is not finite and positive")
    return result


def _read_pointer(path: Path, fields: Sequence[str]) -> dict[str, str] | None:
    rows = _parse_tsv(
        stable_plain_bytes(path, label=f"{path.name} pointer"),
        fields,
        allow_header_only=True,
    )
    if len(rows) > 1:
        raise ValidationError(f"{path.name} contains multiple authority rows")
    return None if not rows else dict(rows[0])


def _source_blob_path(core: SessionCore, binding: Mapping[str, Any]) -> Path:
    registry = core._source_registry()
    matches = [
        item
        for item in registry["blobs"]
        if item["source_sha256"] == binding["source_sha256"]
    ]
    if len(matches) != 1:
        raise ValidationError("source binding does not resolve one immutable blob")
    return _contained(core.root, matches[0]["storage_relative_path"])


def detect_project_kind(project_root: os.PathLike[str] | str) -> str:
    """Detect schema without writing and without guessing from directory names."""

    root = Path(project_root)
    if not root.is_dir() or root.is_symlink():
        raise ValidationError("project root is absent or unsafe")
    project_json = root / "project.json"
    legacy_descriptor = root / "cavity_light_project.tsv"
    legacy_images = root / "images.tsv"
    if project_json.is_file() and not project_json.is_symlink():
        value = loads_canonical_json(
            stable_plain_bytes(project_json, label="schema-2 project descriptor")
        )
        if (
            value.get("schema") == "CTL_P2A_PROJECT_JSON_V1"
            and value.get("project_schema_version") == 2
        ):
            return "SCHEMA2"
        raise ValidationError("project.json is present but is not approved schema 2")
    if (
        legacy_descriptor.is_file()
        and not legacy_descriptor.is_symlink()
        and legacy_images.is_file()
        and not legacy_images.is_symlink()
    ):
        return "LEGACY_SCHEMA1_READ_ONLY"
    raise ValidationError("project schema cannot be detected from physical authority")


def _legacy_inspection(project_root: Path) -> dict[str, Any]:
    """Call the closed migration reader while keeping this layer read-only."""

    try:
        from .migration import inspect_legacy_project
    except ImportError as exc:  # pragma: no cover - package assembly guard
        raise ValidationError("legacy migration adapter is not installed") from exc
    result = inspect_legacy_project(project_root)
    if hasattr(result, "to_dict"):
        value = result.to_dict()
    elif hasattr(result, "__dataclass_fields__"):
        value = asdict(result)
    elif isinstance(result, Mapping):
        value = dict(result)
    else:
        raise ValidationError("legacy inspection returned an unsupported result")
    value.setdefault("project_kind", "LEGACY_SCHEMA1_READ_ONLY")
    value.setdefault("editable", False)
    value.setdefault("session_state", "LEGACY_SESSION")
    value.setdefault("scientific_mutations", 0)
    return value


def inspect_project(project_root: os.PathLike[str] | str) -> dict[str, Any]:
    """Return the complete minimal UI model from verified physical pointers."""

    root = Path(project_root)
    kind = detect_project_kind(root)
    if kind == "LEGACY_SCHEMA1_READ_ONLY":
        before = snapshot_tree(root)
        result = _legacy_inspection(root)
        if snapshot_tree(root) != before:
            raise TransactionError("legacy inspection mutated the source project")
        return result

    validation = validate_project(root)
    try:
        from .migration import inspect_migration_limitation
    except ImportError as exc:  # pragma: no cover - package assembly guard
        raise ValidationError("legacy migration adapter is not installed") from exc
    core = SessionCore(root)
    project = loads_canonical_json(
        stable_plain_bytes(root / "project.json", label="project descriptor")
    )
    registry = core._source_registry()
    images: list[dict[str, Any]] = []
    for binding in registry["image_bindings"]:
        image_uid = binding["image_uid"]
        current = core._read_current_session(image_uid)
        sessions: list[dict[str, Any]] = []
        for row in core._read_registry(image_uid):
            record = core.session_by_uid(image_uid, row["analysis_session_uid"])
            migration_limitation = inspect_migration_limitation(record.session_root)
            revision = _read_pointer(
                record.session_root / "current_revision.tsv", CURRENT_REVISION_FIELDS
            )
            run_path = record.session_root / "current_run.tsv"
            run = (
                _read_pointer(run_path, CURRENT_RUN_FIELDS)
                if run_path.exists()
                else None
            )
            is_current = (
                current is not None
                and current["analysis_session_uid"] == row["analysis_session_uid"]
            )
            display_state = row["lifecycle"]
            if row["lifecycle"] == "HISTORICAL" and row["canonical_role"] == "NON_CANONICAL":
                display_state = "HISTORICAL_NON_CANONICAL"
            sessions.append(
                {
                    "analysis_session_id": row["analysis_session_id"],
                    "analysis_session_uid": row["analysis_session_uid"],
                    "active": is_current,
                    "state": display_state,
                    "lifecycle": row["lifecycle"],
                    "canonical_role": row["canonical_role"],
                    "current_revision_id": None if revision is None else revision["revision_id"],
                    "current_revision_uid": None if revision is None else revision["revision_uid"],
                    "current_revision_manifest_sha256": None
                    if revision is None
                    else revision["revision_manifest_sha256"],
                    "current_run_id": None if run is None else run["run_id"],
                    "current_run_uid": None if run is None else run["run_uid"],
                    "current_run_manifest_sha256": None
                    if run is None
                    else run["run_manifest_sha256"],
                    "revision_count": row["revision_count"],
                    "run_count": row["run_count"],
                    "object_count": row["object_count"],
                    "logical_bytes": row["logical_bytes"],
                    "physical_bytes": row["physical_bytes"],
                    "compressed_bytes_status": row["compressed_bytes_status"],
                    "compressed_bytes": row["compressed_bytes"],
                    "origin": row["origin_type"],
                    "integrity_status": row["integrity_status"],
                    "migration_status": None
                    if migration_limitation is None
                    else migration_limitation["migration_status"],
                    "editable_baseline_revision": None
                    if migration_limitation is None
                    else migration_limitation["editable_baseline_revision"],
                    "quarantined_revision_count": 0
                    if migration_limitation is None
                    else migration_limitation["quarantined_revision_count"],
                    "migration_limitation": _jsonable(migration_limitation),
                    "working_state_sha256": sha256_file(
                        record.session_root / "working" / "working_state.json"
                    ),
                    "current_revision_pointer_sha256": sha256_file(
                        record.session_root / "current_revision.tsv"
                    ),
                }
            )
        sessions.sort(key=lambda item: item["analysis_session_uid"])
        _current, generation, registry_sha = core._selection_snapshot(image_uid)
        images.append(
            {
                "image_id": binding["image_id"],
                "image_uid": image_uid,
                "source_sha256": binding["source_sha256"],
                "source_sha256_status": "VERIFIED",
                "master_pixel_hash_status": binding["master_pixel_hash_status"],
                "current_session_generation": generation,
                "session_registry_sha256": registry_sha,
                "sessions": sessions,
            }
        )
    images.sort(key=lambda item: item["image_uid"])
    return {
        "project_kind": "SCHEMA2",
        "editable": True,
        "project_id": project["project_id"],
        "project_uid": project["project_uid"],
        "validation": asdict(validation),
        "images": images,
        "scientific_validation": False,
    }


def _active_record(core: SessionCore, image_uid: str, session_uid: str):
    current = core._read_current_session(image_uid)
    if current is None or current["analysis_session_uid"] != session_uid:
        raise StaleContextError("the requested session is not the explicit active session")
    return core.session_by_uid(image_uid, session_uid)


def _working_payload(record: Any) -> dict[str, Any]:
    path = record.session_root / "working" / "working_state.json"
    working = loads_canonical_json(
        stable_plain_bytes(path, label="selected session working state")
    )
    return {
        "objects": working["objects"],
        "candidates": working["candidates"],
        "working_state_id": working["working_state_id"],
        "working_state_sha256": sha256_file(path),
    }


def _normalize_entities(
    record: Any,
    objects: Sequence[Any],
    candidates: Sequence[Any],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    working = loads_canonical_json(
        stable_plain_bytes(
            record.session_root / "working" / "working_state.json",
            label="working state identity authority",
        )
    )
    existing_by_cavity = {
        item["cavity_id"]: item
        for item in working["objects"]
        if isinstance(item, Mapping) and "cavity_id" in item
    }
    normalized_objects: list[dict[str, Any]] = []
    for index, raw in enumerate(_require_sequence(objects, "objects"), start=1):
        source = dict(_require_mapping(raw, f"objects[{index}]") )
        cavity_id = source.get("cavity_id") or f"CAV_{index:06d}"
        if not isinstance(cavity_id, str) or _CAVITY_RE.fullmatch(cavity_id) is None:
            raise ValidationError("object cavity_id must use CAV_000001 form")
        prior = existing_by_cavity.get(cavity_id)
        supplied_uuid = source.get("object_uuid")
        if prior is not None:
            prior_uuid = prior["object_uuid"]
            if supplied_uuid is not None and supplied_uuid != prior_uuid:
                raise ValidationError("existing cavity cannot silently change object_uuid")
            object_uuid = prior_uuid
        else:
            object_uuid = new_uuid4_identity() if supplied_uuid is None else _require_uuid4(
                supplied_uuid, "object_uuid"
            )
        source["cavity_id"] = cavity_id
        source["object_uuid"] = object_uuid
        source.setdefault("candidate_uuid", None)
        source.setdefault(
            "identity_provenance",
            {
                "generation_method": "PRESERVED"
                if prior is not None
                else "UUIDV4_RANDOM",
                "source": "FIJI_ACTIVE_SESSION_ROI_SNAPSHOT",
            },
        )
        normalized_objects.append(source)

    normalized_candidates: list[dict[str, Any]] = []
    for index, raw in enumerate(_require_sequence(candidates, "candidates"), start=1):
        source = dict(_require_mapping(raw, f"candidates[{index}]") )
        source["candidate_id"] = _require_id(
            source.get("candidate_id"), f"candidates[{index}].candidate_id"
        )
        source["candidate_uuid"] = _require_uuid4(
            source.get("candidate_uuid"), f"candidates[{index}].candidate_uuid"
        )
        source.setdefault(
            "identity_provenance",
            {"generation_method": "PRESERVED", "source": "FIJI_ACTIVE_SESSION_ROI_SNAPSHOT"},
        )
        source.setdefault("object_uuid", None)
        source.setdefault("review_status", "pending")
        source.setdefault("review_decision", "pending")
        normalized_candidates.append(source)
    return normalized_objects, normalized_candidates


def _next_revision_id(record: Any) -> str:
    used: set[int] = set()
    for path in (record.session_root / "revisions").iterdir():
        if not path.is_dir():
            continue
        # Retained partials reserve their IDs even without COMPLETE. Retrying
        # uses a new ID and preserves the failed transaction for inspection.
        match = re.fullmatch(r"REV_REV_([0-9]{6})(?:\.partial\..+)?", path.name)
        if match:
            used.add(int(match.group(1)))
    candidate = 1
    while candidate in used:
        candidate += 1
    return f"REV_{candidate:06d}"


def _next_run_id(record: Any) -> str:
    used: set[int] = set()
    runs_root = record.session_root / "runs"
    for path in runs_root.iterdir():
        if not path.is_dir() or ".partial." in path.name or ".quarantine" in path.name:
            continue
        match = re.fullmatch(r"RUN_RUN_([0-9]{6})", path.name)
        if match:
            used.add(int(match.group(1)))
    candidate = 1
    while candidate in used:
        candidate += 1
    return f"RUN_{candidate:06d}"


def create_session(arguments: Mapping[str, Any]) -> dict[str, Any]:
    core = SessionCore(arguments["project_root"])
    image_uid = str(arguments["image_uid"])
    _current, generation, registry_sha = core._selection_snapshot(image_uid)
    if int(arguments["expected_current_generation"]) != generation:
        raise StaleContextError("create-session generation snapshot is stale")
    if _require_sha(arguments["expected_registry_sha256"], "expected_registry_sha256") != registry_sha:
        raise StaleContextError("create-session registry snapshot is stale")
    record = core.create_empty_session(
        image_uid,
        analysis_session_id=_require_id(
            arguments["analysis_session_id"], "analysis_session_id"
        ),
        expected_current_generation=generation,
        expected_registry_sha256=registry_sha,
    )
    return {
        "session": _jsonable(asdict(record)),
        **_working_payload(record),
        "project": inspect_project(core.root),
    }


def select_session(arguments: Mapping[str, Any]) -> dict[str, Any]:
    core = SessionCore(arguments["project_root"])
    image_uid = str(arguments["image_uid"])
    target_uid = str(arguments["analysis_session_uid"])
    result = core.select_session(
        image_uid,
        analysis_session_uid=target_uid,
        expected_current_generation=int(arguments["expected_current_generation"]),
        expected_registry_sha256=_require_sha(
            arguments["expected_registry_sha256"], "expected_registry_sha256"
        ),
        cancel=bool(arguments.get("cancel", False)),
    )
    effective_uid = result.selected_session_uid
    if effective_uid is None:
        payload = {
            "objects": [],
            "candidates": [],
            "working_state_id": None,
            "working_state_sha256": None,
        }
    else:
        target = core.session_by_uid(image_uid, effective_uid)
        payload = _working_payload(target)
    return {
        "selection": asdict(result),
        **payload,
        "project": inspect_project(core.root),
    }


def save_revision(arguments: Mapping[str, Any]) -> dict[str, Any]:
    core = SessionCore(arguments["project_root"])
    image_uid = str(arguments["image_uid"])
    session_uid = str(arguments["analysis_session_uid"])
    record = _active_record(core, image_uid, session_uid)
    objects, candidates = _normalize_entities(
        record,
        _require_sequence(arguments.get("objects", []), "objects"),
        _require_sequence(arguments.get("candidates", []), "candidates"),
    )
    expected_working = _require_sha(
        arguments["expected_working_sha256"], "expected_working_sha256"
    )
    expected_pointer = _require_sha(
        arguments["expected_revision_pointer_sha256"],
        "expected_revision_pointer_sha256",
    )
    if sha256_file(record.session_root / "current_revision.tsv") != expected_pointer:
        raise StaleContextError("revision pointer snapshot is stale")
    working_sha = core.update_working_state(
        image_uid,
        session_uid,
        objects=objects,
        candidates=candidates,
        expected_working_sha256=expected_working,
    )
    parent = _read_pointer(
        record.session_root / "current_revision.tsv", CURRENT_REVISION_FIELDS
    )
    revision_id = (
        _require_id(arguments["revision_id"], "revision_id")
        if arguments.get("revision_id") is not None
        else _next_revision_id(record)
    )
    published = core.publish_revision(
        image_uid,
        session_uid,
        revision_id=revision_id,
        objects=objects,
        candidates=candidates,
        identity_provenance=[
            {
                "owner": "ACTIVE_SESSION_FIJI_ROI_SNAPSHOT",
                "roi_zip_sha256": _require_sha(
                    arguments["roi_zip_sha256"], "roi_zip_sha256"
                ),
            }
        ],
        parent_revision_id="NOT_APPLICABLE" if parent is None else parent["revision_id"],
        expected_pointer_sha256=expected_pointer,
    )
    return {
        "working_state_sha256": working_sha,
        "revision": _jsonable(asdict(published)),
        "project": inspect_project(core.root),
    }


def clone_revision(arguments: Mapping[str, Any]) -> dict[str, Any]:
    core = SessionCore(arguments["project_root"])
    result = core.clone_revision_to_session(
        str(arguments["image_uid"]),
        source_session_uid=str(arguments["source_session_uid"]),
        source_revision_uid=_require_uuid4(
            arguments["source_revision_uid"], "source_revision_uid"
        ),
        source_revision_manifest_sha256=_require_sha(
            arguments["source_revision_manifest_sha256"],
            "source_revision_manifest_sha256",
        ),
        destination_session_id=_require_id(
            arguments["destination_session_id"], "destination_session_id"
        ),
    )
    return {
        "session": _jsonable(asdict(result.session)),
        "genesis_revision": _jsonable(asdict(result.genesis_revision)),
        "clone_provenance_sha256": result.clone_provenance_sha256,
        "object_mappings": list(result.object_mappings),
        "candidate_mappings": list(result.candidate_mappings),
        "geometry_mappings": list(result.geometry_mappings),
        **_working_payload(result.session),
        "project": inspect_project(core.root),
    }


def _entry_for_object(
    raw: Mapping[str, Any],
    *,
    scale_x: Decimal,
    scale_y: Decimal,
    preserve_authoritative_pixel_geometry: bool = False,
) -> SimpleNamespace:
    geometry = raw.get("geometry")
    values = dict(raw)
    legacy_properties = raw.get("legacy_properties")
    if isinstance(legacy_properties, Mapping):
        for key, value in legacy_properties.items():
            values.setdefault(str(key), value)
    if isinstance(geometry, Mapping):
        values.update(geometry)
    folded = {str(key).casefold(): value for key, value in values.items()}

    def pick(*names: str, default: Any = None) -> Any:
        for name in names:
            if name in values:
                return values[name]
            if name.casefold() in folded:
                return folded[name.casefold()]
        return default

    center_x_px = _decimal(pick("center_x_px"), "center_x_px")
    center_y_px = _decimal(pick("center_y_px"), "center_y_px")
    diameter_nm = _decimal(
        pick("diameter_nm", "equivalent_diameter_nm", "Diameter_nm"),
        "diameter_nm",
        positive=True,
    )
    center_x_nm = _decimal(
        pick("center_x_nm", "Center_x_nm", default=center_x_px * scale_x), "center_x_nm"
    )
    center_y_nm = _decimal(
        pick("center_y_nm", "Center_y_nm", default=center_y_px * scale_y), "center_y_nm"
    )
    if preserve_authoritative_pixel_geometry:
        # Prompt 3 supplies a private, identity-checked transient view whose
        # physical fields have been recomputed from the immutable revision.
        # Pixel geometry remains the authority for ROI/image boundaries.  Do
        # not round-trip width/height through nm and a separately serialized
        # scale: a sub-ulp decimal difference can move an exact x=0 boundary
        # inside the image and silently exchange image/mask classifications.
        if not isinstance(geometry, Mapping):
            raise ValidationError(
                "RUN physical-object adapter omitted authoritative pixel geometry"
            )
        width_px = _decimal(geometry.get("width_px"), "geometry.width_px", positive=True)
        height_px = _decimal(
            geometry.get("height_px"), "geometry.height_px", positive=True
        )
        x_px = center_x_px - width_px / 2
        y_px = center_y_px - height_px / 2
        raw_bounds = raw.get("bounds")
        if raw_bounds is not None:
            if not isinstance(raw_bounds, Mapping):
                raise ValidationError(
                    "RUN physical-object adapter bounds are not an object"
                )

            def bound_value(primary: str, legacy: str) -> Any:
                if primary in raw_bounds:
                    return raw_bounds[primary]
                return raw_bounds.get(legacy)

            bound_x = _decimal(bound_value("x_px", "x"), "bounds.x_px")
            bound_y = _decimal(bound_value("y_px", "y"), "bounds.y_px")
            bound_width = _decimal(
                bound_value("width_px", "width"), "bounds.width_px", positive=True
            )
            bound_height = _decimal(
                bound_value("height_px", "height"), "bounds.height_px", positive=True
            )
            if (
                bound_width != width_px
                or bound_height != height_px
                or bound_x + bound_width / 2 != center_x_px
                or bound_y + bound_height / 2 != center_y_px
            ):
                raise ValidationError(
                    "RUN physical-object adapter pixel bounds disagree with geometry"
                )
            x_px = bound_x
            y_px = bound_y
    else:
        width_px = diameter_nm / scale_x
        height_px = diameter_nm / scale_y
        x_px = center_x_px - width_px / 2
        y_px = center_y_px - height_px / 2
    review_status = str(pick("review_status", "Review_status", default="reviewed"))
    default_valid = "0" if review_status == "pending" else "1"
    properties = {
        "Type": "cavity",
        "Cavity_id": str(raw["cavity_id"]),
        "Object_uuid": str(raw["object_uuid"]),
        "Object_uuid_generation_method": str(
            _require_mapping(raw["identity_provenance"], "identity_provenance").get(
                "generation_method", "PRESERVED"
            )
        ),
        "Geometry_kind": "circle",
        "Center_x_nm": str(center_x_nm),
        "Center_y_nm": str(center_y_nm),
        "Center_x_px": str(center_x_px),
        "Center_y_px": str(center_y_px),
        "Diameter_nm": str(diameter_nm),
        "Cavity_class": str(pick("cavity_class", "Cavity_class", default="confirmed")),
        "Review_status": review_status,
        "Count_valid": str(pick("count_valid", "Count_valid", default=default_valid)),
        "Size_valid": str(pick("size_valid", "Size_valid", default=default_valid)),
        "Position_valid": str(pick("position_valid", "Position_valid", default=default_valid)),
        "Manual_excluded": str(pick("manual_excluded", "Manual_excluded", default=0)),
        "Inside_analysis_mask": str(pick("inside_analysis_mask", "Inside_analysis_mask", default=1)),
        "Edge_intersecting": str(pick("edge_intersecting", "Edge_intersecting", default=0)),
        "Duplicate_status": str(pick("duplicate_status", "Duplicate_status", default="none")),
        "Measurement_source": str(pick("measurement_source", "Measurement_source", default="manual")),
        "Last_edit_method": str(pick("last_edit_method", "Last_edit_method", default="manual")),
    }
    for optional in (
        "Signed_depth_nm",
        "Depth_absolute_nm",
        "Specimen_id",
        "Specimen_label",
        "Condition_id",
        "Condition_label",
    ):
        key = optional[0].lower() + optional[1:]
        snake = re.sub(r"(?<!^)(?=[A-Z])", "_", optional).lower()
        selected = pick(snake, key, optional)
        if selected is not None:
            properties[optional] = str(selected)
    return SimpleNamespace(
        properties=properties,
        bounds={
            "x_px": x_px,
            "y_px": y_px,
            "width_px": width_px,
            "height_px": height_px,
        },
        x_coordinates=(),
        y_coordinates=(),
        imagej_roi_type="oval",
    )


def _build_object_table(
    core: SessionCore,
    record: Any,
    *,
    run_id: str,
    run_uid: str,
    analysis_at: str,
    roi_zip_sha256: str,
    image_context: Mapping[str, Any],
    _verified_revision_objects_override: Sequence[Mapping[str, Any]] | None = None,
) -> tuple[bytes, dict[str, Any], int]:
    pointer = _read_pointer(
        record.session_root / "current_revision.tsv", CURRENT_REVISION_FIELDS
    )
    if pointer is None:
        raise ValidationError("RUN requires an explicit current revision")
    revision_root = _contained(record.session_root, pointer["relative_path"])
    revision_manifest = core._verify_revision(record, revision_root)
    binding = core._binding(record.image_uid)
    if binding["master_pixel_hash_status"] != "VERIFIED":
        raise ValidationError("RUN requires independently verified master pixels")
    roi_bindings = [
        item.get("roi_zip_sha256")
        for item in revision_manifest.get("revision_identity_provenance", [])
        if isinstance(item, Mapping)
        and item.get("owner") == "ACTIVE_SESSION_FIJI_ROI_SNAPSHOT"
    ]
    if roi_bindings != [roi_zip_sha256]:
        raise StaleContextError(
            "RUN ROI snapshot hash does not match the explicit immutable revision"
        )
    width = int(image_context["width_px"])
    height = int(image_context["height_px"])
    if width <= 0 or height <= 0:
        raise ValidationError("image dimensions must be positive")
    scale_x = _decimal(image_context["scale_x_nm_px"], "scale_x_nm_px", positive=True)
    scale_y = _decimal(image_context["scale_y_nm_px"], "scale_y_nm_px", positive=True)
    master_evidence = _require_mapping(
        image_context.get("master_pixel_evidence"), "master_pixel_evidence"
    )
    if (
        _require_sha(master_evidence.get("sha256"), "master_pixel_evidence.sha256")
        != binding["master_pixel_sha256"]
        or int(master_evidence.get("width", -1)) != width
        or int(master_evidence.get("height", -1)) != height
    ):
        raise StaleContextError(
            "active Fiji pixels do not match the verified image binding"
        )
    evidence_source = master_evidence.get("source_sha256")
    if evidence_source != binding["source_sha256"]:
        raise StaleContextError("active Fiji source identity differs from the project binding")
    use_whole = int(image_context.get("use_whole_image", 1))
    if use_whole not in (0, 1):
        raise ValidationError("use_whole_image must be 0 or 1")
    if use_whole == 0 and image_context.get("net_area_nm2") is None:
        raise ValidationError("masked analysis requires an explicit verified net_area_nm2")
    net_area = (
        _decimal(image_context["net_area_nm2"], "net_area_nm2", positive=True)
        if image_context.get("net_area_nm2") is not None
        else Decimal(width) * Decimal(height) * scale_x * scale_y
    )
    feature_bin = _decimal(
        image_context["feature_distance_bin_nm"],
        "feature_distance_bin_nm",
        positive=True,
    )
    source_path = _source_blob_path(core, binding)
    snapshot = SimpleNamespace(
        project_root=core.root,
        source_path=source_path,
        context={
            "project_id": core.project_id,
            "project_uid": core.project_uid,
            "image_id": binding["image_id"],
            "image_uid": record.image_uid,
            "analysis_session_id": record.analysis_session_id,
            "analysis_session_uid": record.analysis_session_uid,
            "revision_id": revision_manifest["revision_id"],
            "revision_uid": revision_manifest["revision_uid"],
            "source_sha256": binding["source_sha256"],
            "master_pixel_sha256": binding["master_pixel_sha256"],
            "generation_token": sha256_file(
                record.session_root / "current_revision.tsv"
            ),
        },
        payload={
            "operator_id": str(image_context.get("operator_id", "UNKNOWN")),
            "scale_method": str(
                image_context.get("scale_method", "IMPORTED_LEGACY")
            ),
        },
        image={
            "width_px": width,
            "height_px": height,
            "scale_x_nm_px": scale_x,
            "scale_y_nm_px": scale_y,
            "master_pixel_hash_method": binding["master_pixel_hash_method"],
            "master_pixel_hash_status": binding["master_pixel_hash_status"],
        },
        analysis={
            "use_whole_image": use_whole,
            "image_mode": str(image_context.get("image_mode", "without_surface")),
            "thickness_nm": image_context.get("thickness_nm"),
            "thickness_status": str(
                image_context.get("thickness_status", "NOT_APPLICABLE")
            ),
            "feature_distance_bin_nm": feature_bin,
        },
    )
    revision_objects: Sequence[Mapping[str, Any]] = revision_manifest["objects"]
    if _verified_revision_objects_override is not None:
        # Private adapter used by a later scientific layer after it has
        # independently recomputed physical values from immutable pixel
        # geometry.  The public bridge cannot provide this keyword.  Keep the
        # complete identity/order of the verified revision closed here so an
        # adapter can never add, remove, reorder or substitute a cavity while
        # rebuilding derived physical fields for a RUN.
        override = list(_verified_revision_objects_override)
        if len(override) != len(revision_manifest["objects"]):
            raise ValidationError(
                "RUN physical-object adapter changed revision cardinality"
            )
        identity_fields = (
            "candidate_uuid",
            "cavity_id",
            "identity_provenance",
            "object_uuid",
        )
        for index, (source, adapted) in enumerate(
            zip(revision_manifest["objects"], override)
        ):
            if not isinstance(adapted, Mapping):
                raise ValidationError(
                    "RUN physical-object adapter produced a non-object",
                    details={"index": index},
                )
            for field in identity_fields:
                if adapted.get(field) != source.get(field):
                    raise ValidationError(
                        "RUN physical-object adapter changed scientific identity",
                        details={"field": field, "index": index},
                    )
            # A derived transient view may remove the immutable revision
            # record hash because its physical fields no longer match those
            # original bytes.  It may never substitute a different hash.
            adapted_object_sha = adapted.get("object_sha256")
            if adapted_object_sha not in {None, source.get("object_sha256")}:
                raise ValidationError(
                    "RUN physical-object adapter substituted a revision object hash",
                    details={"index": index},
                )
        revision_objects = override
    entries = tuple(
        _entry_for_object(
            item,
            scale_x=scale_x,
            scale_y=scale_y,
            preserve_authoritative_pixel_geometry=(
                _verified_revision_objects_override is not None
            ),
        )
        for item in revision_objects
    )
    # Only the verified immutable revision can supply candidate provenance.
    # ROI properties are editable and cannot establish this scientific link.
    candidates_by_uuid = {item["candidate_uuid"]: item for item in revision_manifest.get("candidates", [])}
    for item, entry in zip(revision_objects, entries):
        candidate = candidates_by_uuid.get(item.get("candidate_uuid"))
        if candidate is not None and candidate.get("candidate_schema") == "CTL_P7_MANUAL_CANDIDATE_V1":
            if candidate.get("object_uuid") != item["object_uuid"] or candidate.get("cavity_id") != item["cavity_id"]:
                raise ValidationError("RUN manual candidate/object authority differs")
            entry.candidate_trace = {name: candidate[name] for name in
                                     ("candidate_uuid", "candidate_id", "view_id", "proposed_geometry_sha256")}
    geometries = tuple(_geometry(entry, snapshot) for entry in entries)
    prepared_revision = SimpleNamespace(
        manifest={
            "parent_revision_id": revision_manifest["parent_revision_id"],
            "roi_zip_sha256": roi_zip_sha256,
        },
        manifest_sha256=sha256_file(revision_root / "revision_manifest.json"),
        path=revision_root,
    )
    prepared = PreparedObjectTable(
        snapshot=snapshot,
        profile=load_object_table_profile(),
        revision=prepared_revision,
        cavity_entries=entries,
        geometries=geometries,
        net_area_nm2=net_area,
        revision_complete_marker_sha256=sha256_file(revision_root / "COMPLETE"),
    )
    records = prepared.materialize(
        run_id=run_id, run_uid=run_uid, analysis_at=analysis_at
    )
    run_context = load_run_context(core.root, record.session_root)
    table = render_object_table(records, run_context=run_context)
    statistics = zero_event_summary(records, net_area_nm2=net_area)
    return table, statistics, len(records)


def publish_run(
    arguments: Mapping[str, Any],
    *,
    _verified_revision_objects_override: Sequence[Mapping[str, Any]] | None = None,
    _staged_run_validator: Callable[[Any], Any] | None = None,
) -> dict[str, Any]:
    core = SessionCore(arguments["project_root"])
    image_uid = str(arguments["image_uid"])
    session_uid = str(arguments["analysis_session_uid"])
    record = _active_record(core, image_uid, session_uid)
    expected_pointer = _require_sha(
        arguments["expected_revision_pointer_sha256"],
        "expected_revision_pointer_sha256",
    )
    if sha256_file(record.session_root / "current_revision.tsv") != expected_pointer:
        raise StaleContextError("RUN revision-pointer snapshot is stale")
    run_id = (
        _require_id(arguments["run_id"], "run_id")
        if arguments.get("run_id") is not None
        else _next_run_id(record)
    )
    run_uid = new_uuid4_identity()
    analysis_at = utc_now_z()
    roi_zip_sha = _require_sha(arguments["roi_zip_sha256"], "roi_zip_sha256")
    image_context = _require_mapping(arguments["image_context"], "image_context")
    table, statistics, object_row_count = _build_object_table(
        core,
        record,
        run_id=run_id,
        run_uid=run_uid,
        analysis_at=analysis_at,
        roi_zip_sha256=roi_zip_sha,
        image_context=image_context,
        _verified_revision_objects_override=_verified_revision_objects_override,
    )
    feature_bin = str(image_context["feature_distance_bin_nm"])
    payload = {
        **statistics,
        "cavity_objects_tsv": table,
        "roi_zip_sha256": roi_zip_sha,
        "bin_contract": {
            "depth_bin_nm": feature_bin,
            "feature_distance_bin_nm": feature_bin,
            "histogram_bin_nm": str(
                image_context.get("histogram_bin_nm", feature_bin)
            ),
        },
    }
    result = core.publish_run(
        image_uid,
        session_uid,
        run_id=run_id,
        run_uid=run_uid,
        payload=payload,
        created_at=analysis_at,
        _staged_run_validator=_staged_run_validator,
    )
    return {
        "run": _jsonable(asdict(result)),
        "object_table_sha256": sha256_bytes(table),
        "object_row_count": object_row_count,
        "N_count_valid": statistics["N_count_valid"],
        "project": inspect_project(core.root),
    }


def _transition_session(
    arguments: Mapping[str, Any],
    *,
    transition: str,
    compressed_bytes: int | None = None,
) -> dict[str, Any]:
    """Commit canonical/lifecycle metadata, registry and pointer as one CAS."""

    core = SessionCore(arguments["project_root"])
    image_uid = str(arguments["image_uid"])
    target_uid = str(arguments["analysis_session_uid"])
    current, old_generation, registry_sha = core._selection_snapshot(image_uid)
    if int(arguments["expected_current_generation"]) != old_generation:
        raise StaleContextError("session transition generation snapshot is stale")
    if _require_sha(arguments["expected_registry_sha256"], "expected_registry_sha256") != registry_sha:
        raise StaleContextError("session transition registry snapshot is stale")
    rows = core._read_registry(image_uid)
    if len([row for row in rows if row["analysis_session_uid"] == target_uid]) != 1:
        raise ValidationError("session transition target is not unique")
    if transition in {"ARCHIVED", "SUPERSEDED"} and current is not None and current["analysis_session_uid"] == target_uid:
        raise ValidationError(
            "select another explicit session before archiving or superseding the current session"
        )
    timestamp = utc_now_z()
    binding = core._binding(image_uid)
    old_registry = stable_plain_bytes(
        core._registry_path(image_uid), label="session transition registry"
    )
    pointer_path = core._current_session_path(image_uid)
    old_pointer = stable_plain_bytes(pointer_path, label="session transition pointer")
    metadata_updates: list[tuple[Path, bytes, bytes]] = []
    metadata_bytes_by_uid: dict[str, bytes] = {}
    new_rows: list[dict[str, Any]] = []
    new_generation = old_generation + 1
    existing_by_uid = {row["analysis_session_uid"]: row for row in rows}
    for row in rows:
        session_root = _contained(core._image_root(image_uid), row["relative_path"])
        path = session_root / "session_metadata.json"
        old_bytes = stable_plain_bytes(path, label="session transition metadata")
        metadata = loads_canonical_json(old_bytes)
        if transition == "CANONICAL":
            metadata["canonical_role"] = (
                "CANONICAL" if row["analysis_session_uid"] == target_uid else "NON_CANONICAL"
            )
        elif row["analysis_session_uid"] == target_uid:
            metadata["canonical_role"] = "NON_CANONICAL"
            metadata["lifecycle"] = (
                "ARCHIVED" if transition == "ARCHIVED" else "HISTORICAL"
            )
        new_bytes = canonical_json_bytes(metadata)
        if new_bytes != old_bytes:
            metadata["generation"] = int(metadata["generation"]) + 1
            metadata["updated_at"] = timestamp
            new_bytes = canonical_json_bytes(metadata)
            metadata_updates.append((path, old_bytes, new_bytes))
        metadata_bytes_by_uid[row["analysis_session_uid"]] = new_bytes
        effective = loads_canonical_json(new_bytes)
        new_row = core._make_registry_row(
            binding,
            effective,
            session_root,
            generation=new_generation,
            lifecycle=effective["lifecycle"],
            stats=core._session_stats(
                session_root,
                byte_overrides={path: new_bytes},
            ),
        )
        new_row["session_metadata_sha256"] = sha256_bytes(new_bytes)
        prior = existing_by_uid[row["analysis_session_uid"]]
        new_row["compressed_bytes_status"] = prior["compressed_bytes_status"]
        new_row["compressed_bytes"] = prior["compressed_bytes"]
        new_row["integrity_status"] = prior["integrity_status"]
        if transition == "ARCHIVED" and row["analysis_session_uid"] == target_uid:
            if compressed_bytes is None or compressed_bytes <= 0:
                raise ValidationError("verified archive byte size is required")
            new_row["compressed_bytes_status"] = "KNOWN"
            new_row["compressed_bytes"] = compressed_bytes
        new_rows.append(new_row)
    new_rows.sort(key=lambda row: row["analysis_session_uid"])
    core._validate_registry_rows(image_uid, new_rows)
    new_registry = _tsv_bytes(SESSION_REGISTRY_FIELDS, new_rows)
    if current is None:
        raise ValidationError("session transition requires an explicit current session")
    current_row = next(
        row
        for row in new_rows
        if row["analysis_session_uid"] == current["analysis_session_uid"]
    )
    pointer = dict(current)
    pointer["generation"] = new_generation
    pointer["session_metadata_sha256"] = current_row["session_metadata_sha256"]
    pointer["session_registry_sha256"] = sha256_bytes(new_registry)
    pointer["updated_at"] = timestamp
    new_pointer = _tsv_bytes(CURRENT_SESSION_FIELDS, [pointer])
    token = f"vertical_{transition.lower()}_{uuid.uuid4().hex}"
    journal_owner = core.session_by_uid(image_uid, current["analysis_session_uid"])
    journal_path = journal_owner.session_root / "journals" / f"JOURNAL_{token}.json"
    journal = {
        "created_at": timestamp,
        "image_uid": image_uid,
        "new_generation": new_generation,
        "new_pointer_sha256": sha256_bytes(new_pointer),
        "new_registry_sha256": sha256_bytes(new_registry),
        "old_generation": old_generation,
        "old_pointer_sha256": sha256_bytes(old_pointer),
        "old_registry_sha256": sha256_bytes(old_registry),
        "schema": SESSION_TRANSITION_JOURNAL_SCHEMA,
        "state": "PREPARED",
        "target_session_uid": target_uid,
        "transition": transition,
    }
    _write_new(journal_path, canonical_json_bytes(journal))
    written: list[tuple[Path, bytes, bytes, str]] = []
    try:
        for index, (path, old_bytes, new_bytes) in enumerate(metadata_updates):
            owned = f"{token}_metadata_{index}"
            _replace_exact(
                path,
                new_bytes,
                expected_sha256=sha256_bytes(old_bytes),
                token=owned,
            )
            written.append((path, old_bytes, new_bytes, owned))
        _replace_exact(
            core._registry_path(image_uid),
            new_registry,
            expected_sha256=registry_sha,
            token=f"{token}_registry",
        )
        written.append((core._registry_path(image_uid), old_registry, new_registry, f"{token}_registry"))
        _replace_exact(
            pointer_path,
            new_pointer,
            expected_sha256=sha256_bytes(old_pointer),
            token=f"{token}_pointer",
        )
        written.append((pointer_path, old_pointer, new_pointer, f"{token}_pointer"))
        journal["state"] = "COMMITTED"
        _replace_exact(
            journal_path,
            canonical_json_bytes(journal),
            expected_sha256=sha256_file(journal_path),
            token=f"{token}_commit",
        )
    except BaseException:
        rollback_error: BaseException | None = None
        try:
            for path, old_bytes, new_bytes, owned in reversed(written):
                _restore_exact(
                    path,
                    old_bytes,
                    owned,
                    expected_owned_sha256=sha256_bytes(new_bytes),
                )
            journal["state"] = "ROLLED_BACK"
            journal["rollback_verified"] = True
            _replace_exact(
                journal_path,
                canonical_json_bytes(journal),
                expected_sha256=sha256_file(journal_path),
                token=f"{token}_rollback",
            )
        except BaseException as exc:
            rollback_error = exc
        if rollback_error is not None:
            raise TransactionError(
                "session transition failed and rollback could not be verified"
            ) from rollback_error
        raise
    core.refresh_storage_manifest()
    validate_project(core.root)
    return {"transition": transition, "project": inspect_project(core.root)}


def set_canonical(arguments: Mapping[str, Any]) -> dict[str, Any]:
    return _transition_session(arguments, transition="CANONICAL")


def mark_superseded(arguments: Mapping[str, Any]) -> dict[str, Any]:
    result = _transition_session(arguments, transition="SUPERSEDED")
    result["stored_semantics"] = "HISTORICAL+NON_CANONICAL"
    return result


def migrate_legacy(arguments: Mapping[str, Any]) -> dict[str, Any]:
    try:
        from .migration import migrate_legacy_project_by_copy
    except ImportError as exc:  # pragma: no cover - package assembly guard
        raise ValidationError("legacy migration adapter is not installed") from exc
    legacy_root = Path(arguments["legacy_root"])
    before = snapshot_tree(legacy_root)
    has_migration_evidence = "migration_evidence" in arguments
    has_revision_chain = "revision_chain" in arguments
    has_roi_exports = "roi_exports" in arguments
    if has_migration_evidence:
        if has_revision_chain or has_roi_exports:
            raise ValidationError(
                "migration_evidence cannot be mixed with legacy revision_chain/roi_exports"
            )
        migration_evidence: Mapping[str, Any] | None = _require_mapping(
            arguments["migration_evidence"], "migration_evidence"
        )
        revision_chain: list[str] | None = None
        roi_exports: Mapping[str, Any] | None = None
    else:
        if not has_revision_chain or not has_roi_exports:
            raise ValidationError(
                "legacy migration compatibility requires explicit revision_chain and roi_exports"
            )
        migration_evidence = None
        revision_chain = [
            _require_id(item, "revision_chain item")
            for item in _require_sequence(arguments["revision_chain"], "revision_chain")
        ]
        roi_exports = _require_mapping(arguments["roi_exports"], "roi_exports")
    result = migrate_legacy_project_by_copy(
        legacy_root,
        Path(arguments["destination_root"]),
        image_id=_require_id(arguments["image_id"], "image_id"),
        revision_chain=revision_chain,
        roi_exports=roi_exports,
        migration_evidence=migration_evidence,
        master_pixel_evidence=_require_mapping(
            arguments["master_pixel_evidence"], "master_pixel_evidence"
        ),
        created_at=str(arguments.get("created_at", utc_now_z())),
        target_project_uid=arguments.get("target_project_uid"),
        target_project_id=arguments.get("target_project_id"),
        analysis_session_id=arguments.get("analysis_session_id"),
        idempotency_key=arguments.get("idempotency_key"),
    )
    if snapshot_tree(legacy_root) != before:
        raise TransactionError("legacy migration changed the original project")
    if hasattr(result, "to_dict"):
        return result.to_dict()
    if hasattr(result, "__dataclass_fields__"):
        return _jsonable(asdict(result))
    return dict(_require_mapping(result, "migration result"))


def inspect_legacy_quarantine(arguments: Mapping[str, Any]) -> dict[str, Any]:
    """Validate one explicitly selected session-owned quarantine without writes."""

    try:
        from .migration import validate_legacy_quarantine
    except ImportError as exc:  # pragma: no cover - package assembly guard
        raise ValidationError("legacy migration adapter is not installed") from exc
    project_root = Path(arguments["project_root"])
    before = snapshot_tree(project_root)
    core = SessionCore(project_root)
    image_uid = validate_canonical_uuid(arguments["image_uid"])
    analysis_session_uid = _require_uuid4(
        arguments["analysis_session_uid"], "analysis_session_uid"
    )
    record = core.session_by_uid(image_uid, analysis_session_uid)
    validation = validate_legacy_quarantine(record.session_root)
    if snapshot_tree(project_root) != before:
        raise TransactionError("legacy quarantine inspection mutated the project")
    return _jsonable(validation)


def archive_session(arguments: Mapping[str, Any]) -> dict[str, Any]:
    try:
        from .session_archive import build_session_archive, validate_session_archive
    except ImportError as exc:  # pragma: no cover - package assembly guard
        raise ValidationError("session archive adapter is not installed") from exc
    core = SessionCore(arguments["project_root"])
    record = core.session_by_uid(
        str(arguments["image_uid"]), str(arguments["analysis_session_uid"])
    )
    # Reject an ineligible/current target before the comparatively expensive
    # external ZIP publication.  _transition_session repeats the same CAS
    # checks after archive validation so a concurrent selection change still
    # fails closed; this preflight prevents a known-invalid request from
    # leaving a plausible external archive behind.
    current, current_generation, registry_sha = core._selection_snapshot(
        record.image_uid
    )
    if int(arguments["expected_current_generation"]) != current_generation:
        raise StaleContextError("archive generation snapshot is stale")
    if (
        _require_sha(arguments["expected_registry_sha256"], "expected_registry_sha256")
        != registry_sha
    ):
        raise StaleContextError("archive registry snapshot is stale")
    if current is not None and current["analysis_session_uid"] == record.analysis_session_uid:
        raise ValidationError(
            "select another explicit session before archiving the current session"
        )
    archive_name = (
        f"CTL_SESSION_{record.analysis_session_id}_{record.analysis_session_uid}.zip"
    )
    if arguments.get("archive_directory") is not None:
        archive_path = Path(arguments["archive_directory"]) / archive_name
    else:
        archive_path = Path(arguments["archive_path"])
    if archive_path.name != archive_name:
        raise ValidationError(
            "archive file name must bind the exact session ID and UID"
        )
    result = build_session_archive(
        core.root,
        image_uid=record.image_uid,
        analysis_session_uid=record.analysis_session_uid,
        archive_path=archive_path,
        archive_id=_require_id(
            arguments.get("archive_id", f"ARCHIVE_{record.analysis_session_id}"),
            "archive_id",
        ),
        created_at=str(arguments.get("created_at", utc_now_z())),
    )
    validation = validate_session_archive(archive_path)
    validation_value = _jsonable(
        asdict(validation)
        if hasattr(validation, "__dataclass_fields__")
        else dict(validation)
    )
    if validation_value.get("result") != "PASS":
        raise ValidationError("new session archive did not validate")
    transition_args = dict(arguments)
    transition_args["project_root"] = str(core.root)
    transition = _transition_session(
        transition_args,
        transition="ARCHIVED",
        compressed_bytes=archive_path.stat().st_size,
    )
    result_value = (
        _jsonable(asdict(result))
        if hasattr(result, "__dataclass_fields__")
        else _jsonable(dict(result))
    )
    return {
        "archive": result_value,
        "validation": validation_value,
        "retention_policy": "RETAIN_NO_AUTOMATIC_DELETE",
        "expanded_session_deleted": False,
        "project": transition["project"],
    }


def restore_session(arguments: Mapping[str, Any]) -> dict[str, Any]:
    try:
        from .session_archive import restore_session_archive, validate_session_archive
    except ImportError as exc:  # pragma: no cover - package assembly guard
        raise ValidationError("session archive adapter is not installed") from exc
    archive_path = Path(arguments["archive_path"])
    validation = validate_session_archive(archive_path)
    if arguments.get("destination_parent") is not None:
        destination = Path(arguments["destination_parent"]) / (
            f"SESSION_{validation.analysis_session_id}"
        )
    else:
        destination = Path(arguments["destination_root"])
    result = restore_session_archive(
        archive_path,
        source_project_root=Path(arguments["project_root"]),
        destination_session_root=destination,
        restored_at=str(arguments.get("restored_at", utc_now_z())),
    )
    if hasattr(result, "to_dict"):
        return result.to_dict()
    if hasattr(result, "__dataclass_fields__"):
        return _jsonable(asdict(result))
    return _jsonable(dict(_require_mapping(result, "restore result")))


def verify_project(arguments: Mapping[str, Any]) -> dict[str, Any]:
    result = validate_project(arguments["project_root"])
    return {"validation": asdict(result), "project": inspect_project(arguments["project_root"])}


_OPERATIONS = {
    "inspect_project": lambda arguments: inspect_project(arguments["project_root"]),
    "create_session": create_session,
    "select_session": select_session,
    "set_canonical": set_canonical,
    "mark_superseded": mark_superseded,
    "save_revision": save_revision,
    "clone_revision": clone_revision,
    "publish_run": publish_run,
    "migrate_legacy": migrate_legacy,
    "inspect_legacy_quarantine": inspect_legacy_quarantine,
    "archive_session": archive_session,
    "restore_session": restore_session,
    "verify_project": verify_project,
}


def execute_request(request: Mapping[str, Any]) -> dict[str, Any]:
    if set(request) != {"arguments", "operation", "request_id", "schema"}:
        raise ValidationError("bridge request field inventory is not closed")
    if request["schema"] != REQUEST_SCHEMA:
        raise ValidationError("bridge request schema is not supported")
    request_id = _require_uuid4(request["request_id"], "request_id")
    operation = str(request["operation"])
    if operation == "cancel":
        return {
            "schema": RESPONSE_SCHEMA,
            "request_id": request_id,
            "operation": operation,
            "status": "CANCELLED",
            "result": {
                "scientific_mutations": 0,
                "disk_writes": "RESPONSE_ONLY_OUTSIDE_PROJECT",
            },
            "errors": [],
            "warnings": [],
        }
    handler = _OPERATIONS.get(operation)
    if handler is None:
        raise ValidationError("bridge operation is not supported")
    result = handler(_require_mapping(request["arguments"], "arguments"))
    return {
        "schema": RESPONSE_SCHEMA,
        "request_id": request_id,
        "operation": operation,
        "status": "PASS",
        "result": result,
        "errors": [],
        "warnings": [],
    }


def _outside_project(response: Path, request: Mapping[str, Any]) -> None:
    arguments = request.get("arguments")
    if not isinstance(arguments, Mapping):
        return
    roots = [
        Path(arguments[key]).resolve(strict=False)
        for key in (
            "project_root",
            "legacy_root",
            "destination_root",
            "destination_parent",
        )
        if isinstance(arguments.get(key), str)
    ]
    resolved = response.resolve(strict=False)
    for root in roots:
        if resolved == root or root in resolved.parents:
            raise ValidationError("bridge response must be outside every scientific project")


def _write_new_response(path: Path, payload: bytes) -> None:
    if not path.parent.is_dir() or path.exists() or path.is_symlink():
        raise TransactionError("bridge response target must be new in an existing directory")
    temporary = path.with_name(f".{path.name}.partial.{uuid.uuid4().hex}")
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    descriptor = os.open(temporary, flags, 0o600)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.rename(temporary, path)
    except BaseException:
        # A retained external response partial is diagnostic-only and never
        # scientific authority.  Do not delete it automatically under OD-17.
        raise


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Cavity TEM Light Prompt-2 vertical bridge")
    parser.add_argument("--request", required=True)
    parser.add_argument("--request-sha256", required=True)
    parser.add_argument("--response", required=True)
    args = parser.parse_args(argv)
    request_path = Path(args.request)
    response_path = Path(args.response)
    request_bytes = stable_plain_bytes(request_path, label="vertical bridge request")
    expected = _require_sha(args.request_sha256, "request_sha256")
    observed = hashlib.sha256(request_bytes).hexdigest()
    if expected != observed:
        raise StaleContextError("vertical bridge request SHA-256 mismatch")
    request = loads_canonical_json(request_bytes)
    _outside_project(response_path, request)
    try:
        response = execute_request(request)
        code = 0
    except (ValidationError, StaleContextError, TransactionError) as exc:
        response = {
            "schema": RESPONSE_SCHEMA,
            "request_id": request.get("request_id", "UNKNOWN")
            if isinstance(request, Mapping)
            else "UNKNOWN",
            "operation": request.get("operation", "UNKNOWN")
            if isinstance(request, Mapping)
            else "UNKNOWN",
            "status": "ERROR",
            "result": {},
            "errors": [
                {
                    "code": exc.__class__.__name__,
                    "path": getattr(exc, "details", {}).get("path"),
                    "row": getattr(exc, "details", {}).get("row"),
                    "column": getattr(exc, "details", {}).get("column"),
                    "message": str(exc),
                    "details": getattr(exc, "details", {}),
                }
            ],
            "warnings": [],
        }
        code = 2
    except Exception as exc:  # closed last-resort envelope for supported requests
        response = {
            "schema": RESPONSE_SCHEMA,
            "request_id": request.get("request_id", "UNKNOWN")
            if isinstance(request, Mapping)
            else "UNKNOWN",
            "operation": request.get("operation", "UNKNOWN")
            if isinstance(request, Mapping)
            else "UNKNOWN",
            "status": "ERROR",
            "result": {},
            "errors": [
                {
                    "code": "INTERNAL_ERROR_REINSPECT_REQUIRED",
                    "path": None,
                    "row": None,
                    "column": None,
                    "message": "unexpected bridge failure; re-inspect physical state before retry",
                    "details": {"exception_type": type(exc).__name__},
                }
            ],
            "warnings": [],
        }
        code = 3
    _write_new_response(response_path, canonical_json_bytes(response))
    return code


if __name__ == "__main__":
    sys.exit(main())


__all__ = [
    "REQUEST_SCHEMA",
    "RESPONSE_SCHEMA",
    "archive_session",
    "clone_revision",
    "create_session",
    "detect_project_kind",
    "execute_request",
    "inspect_legacy_quarantine",
    "inspect_project",
    "mark_superseded",
    "migrate_legacy",
    "publish_run",
    "restore_session",
    "save_revision",
    "select_session",
    "set_canonical",
    "verify_project",
]
