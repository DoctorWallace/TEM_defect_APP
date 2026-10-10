"""Fail-closed broker used by the narrow Fiji ``ProcessBuilder`` bridge.

The broker accepts one exact request schema.  Mutating operations use a
stateless PREPARE/COMMIT protocol: the prepare token is a canonical digest of
the request identity, context and operation input.  Fiji compares the live
context between phases; COMMIT independently revalidates the same bytes and
token before any scientific write.
"""

from __future__ import annotations

import base64
import hashlib
import io
import json
import math
import os
import re
import uuid
import zipfile
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path, PurePosixPath
from typing import Any, Mapping, Sequence

from .bridge import prompt1_bridge_record, validate_prompt1_bridge
from .canonical_json import canonical_json_bytes, loads_canonical_json
from .contract import (
    CLASSIFICATION_POLICY,
    VALIDITY_UPDATE_MODE,
    require_finite_number,
    validate_master_protection,
)
from .errors import Prompt1Error, StaleContextError, TransactionError, ValidationError
from .identity import (
    derive_image_uid,
    derive_session_uid,
    legacy_image_parent_component,
    legacy_image_parent_identity_token,
    new_uuid4_identity,
    synthesize_legacy_session_id,
    validate_canonical_uuid,
    validate_cavity_id,
    validate_human_id,
)
from .revision import (
    REVISION_ROI_NAME,
    RevisionBinding,
    make_working_state,
    publish_revision,
    verify_revision,
    verify_revision_pointer,
)
from .run_consumer import validate_relative_path
from .run_disposition import require_scientific_eligibility
from .path_safety import (
    PathSafetyError,
    is_reparse_or_link,
    lexical_absolute,
    plain_directory,
    plain_file,
    reject_reparse_chain,
    stable_plain_bytes,
)


REQUEST_SCHEMA = "CTL_IJM_BRIDGE_REQUEST_V1"
RESPONSE_SCHEMA = "CTL_IJM_BRIDGE_RESPONSE_V1"
CONTEXT_SCHEMA = "CTL_OPERATION_CONTEXT_V1"
SNAPSHOT_SCHEMA = "CTL_FIJI_OPERATION_SNAPSHOT_V1"
FACADE_VERSION = "CTL_P1_FIJI_FACADE_V1"
RUNTIME_VERSION = "CTL_P1_FIJI_RUNTIME_V1"
CANDIDATE_VERSION = "1.2.0-R10-DEV01"
ROI_ENCODING = "IMAGEJ_ROI_ZIP_BASE64_V1"

OPERATIONS = {"validate", "load_revision", "save_revision", "export_run", "combined_analysis"}
READ_ONLY_OPERATIONS = {"validate", "load_revision"}
MUTATING_OPERATIONS = OPERATIONS - READ_ONLY_OPERATIONS
PHASES = {"EXECUTE", "PREPARE", "COMMIT", "ABORT"}
SHA_RE = re.compile(r"^[0-9a-f]{64}$", re.ASCII)
UUID4_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$",
    re.ASCII,
)
SAFE_COUNTER_RE = re.compile(r"^(0|[1-9][0-9]*)$", re.ASCII)
LEGACY_IMAGE_REGISTRY_RELATIVE_PATH = "images.tsv"
LEGACY_IMAGE_REGISTRY_HEADER = (
    b"image_id\tdisplay_name\tsource_path\tstored_path\tsha256\tsample_name\t"
    b"condition\tmode\tthickness_nm\tscale_x_nm_px\tscale_y_nm_px\t"
    b"current_revision\tcurrent_run\tupdated_ms"
)

REQUEST_FIELDS = {
    "schema",
    "request_id",
    "operation",
    "phase",
    "technical_preview",
    "context",
    "payload",
    "prepare_token",
    "project_root",
    "forbidden_response_roots",
    "response_policy",
}
CONTEXT_FIELDS = {
    "schema",
    "project_id",
    "project_uid",
    "image_id",
    "image_uid",
    "source_sha256",
    "master_pixel_sha256",
    "analysis_session_id",
    "analysis_session_uid",
    "revision_id",
    "revision_uid",
    "working_state_id",
    "state_identity",
    "imageplus_identity",
    "window_identity",
    "object_uuid",
    "cavity_id",
    "selection_revision",
    "generation_token",
    "command_id",
    "context_fingerprint_sha256",
}
CONTEXT_FINGERPRINT_ORDER = (
    "project_id",
    "project_uid",
    "image_id",
    "image_uid",
    "source_sha256",
    "master_pixel_sha256",
    "analysis_session_id",
    "analysis_session_uid",
    "state_identity",
    "imageplus_identity",
    "window_identity",
    "object_uuid",
    "cavity_id",
    "selection_revision",
    "generation_token",
    "command_id",
    "revision_id",
    "revision_uid",
    "working_state_id",
)
PAYLOAD_FIELDS = {
    "facade_version",
    "runtime_version",
    "candidate_version",
    "image_directory",
    "source_path",
    "operator_id",
    "scale_x_nm_px",
    "scale_y_nm_px",
    "scale_method",
    "operation_input",
}
COMMON_SNAPSHOT_FIELDS = {
    "snapshot_schema",
    "image",
    "roi_snapshot",
    "roi_records",
    "state",
    "analysis_parameters",
}
IMAGE_FIELDS = {
    "width_px",
    "height_px",
    "bit_depth",
    "image_role",
    "source_hash_status",
    "master_pixel_hash_status",
    "master_pixel_hash_method",
    "scale_x_nm_px",
    "scale_y_nm_px",
    "scale_method",
}
ROI_SNAPSHOT_FIELDS = {"encoding", "bytes", "sha256", "base64", "roi_count"}
ROI_RECORD_FIELDS = {
    "index",
    "name",
    "imagej_roi_type",
    "group",
    "properties_text",
    "properties_sha256",
    "serialized_roi_sha256",
    "bounds",
    "coordinates",
}
BOUNDS_FIELDS = {"x_px", "y_px", "width_px", "height_px"}
COORDINATE_FIELDS = {"x_px", "y_px"}
STATE_FIELDS = {"parent_revision_id", "parent_revision_uid", "working_state_id"}
ANALYSIS_FIELDS = {
    "classification_policy",
    "validity_update_mode",
    "image_mode",
    "use_whole_image",
    "thickness_nm",
    "thickness_status",
    "histogram_bin_nm",
    "feature_distance_bin_nm",
}
COMBINED_FIELDS = {
    "selected_image_ids",
    "current_run_pointer_relative_paths",
    "combined_runs_relative_path",
    "histogram_bin_nm",
    "feature_distance_bin_nm",
}
LOAD_REVISION_FIELDS = {
    "load_schema",
    "revision_relative_path",
    "current_revision_pointer_relative_path",
    "current_run_pointer_relative_path",
    "working_state_id",
}
REVISION_METADATA_FIELDS = {
    "metadata_schema",
    "context_fingerprint_sha256",
    "working_state_id",
    "roi_count",
    "classification_policy",
    "validity_update_mode",
    "image_role",
    "master_pixel_hash_method",
    "technical_preview",
    "scientific_validation",
}


@dataclass(frozen=True)
class RoiEntry:
    index: int
    name: str
    imagej_roi_type: str
    group: int
    properties_text: str
    properties: dict[str, str]
    serialized_sha256: str
    bounds: dict[str, float]
    x_coordinates: tuple[float, ...]
    y_coordinates: tuple[float, ...]


@dataclass(frozen=True)
class PreparedSnapshot:
    project_root: Path
    image_directory: Path
    source_path: Path
    context: dict[str, Any]
    payload: dict[str, Any]
    operation_input: dict[str, Any]
    image: dict[str, Any]
    roi_zip_bytes: bytes
    roi_entries: tuple[RoiEntry, ...]
    state: dict[str, Any]
    analysis: dict[str, Any]


def _utc_now_z() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _exact_fields(value: Any, expected: set[str], label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValidationError(f"{label} must be an object")
    missing = sorted(expected - set(value))
    extra = sorted(set(value) - expected)
    if missing or extra:
        raise ValidationError(
            f"{label} fields are not exact",
            details={"missing": missing, "extra": extra},
        )
    return value


def _sha(value: Any, field: str) -> str:
    if not isinstance(value, str) or SHA_RE.fullmatch(value) is None:
        raise ValidationError("lowercase SHA-256 required", details={"field": field})
    return value


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as stream:
            for block in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(block)
    except OSError as exc:
        raise ValidationError(
            "source bytes cannot be read",
            details={"error_type": type(exc).__name__},
        ) from exc
    return digest.hexdigest()


def _string(value: Any, field: str, *, allow_empty: bool = False) -> str:
    if not isinstance(value, str) or (not allow_empty and not value):
        raise ValidationError("non-empty string required", details={"field": field})
    if "\x00" in value or "\r" in value:
        raise ValidationError("NUL/CR is forbidden", details={"field": field})
    return value


def _finite(value: Any, field: str, *, positive: bool = False) -> float:
    result = require_finite_number(value, field=field, strictly_positive=positive)
    return float(result)


def _nonnegative_integer(value: Any, field: str) -> int:
    if type(value) is not int or value < 0:
        raise ValidationError("nonnegative integer required", details={"field": field})
    return value


def _positive_integer(value: Any, field: str) -> int:
    result = _nonnegative_integer(value, field)
    if result == 0:
        raise ValidationError("positive integer required", details={"field": field})
    return result


def _is_reparse_or_link(path: Path) -> bool:
    if not path.exists() and not path.is_symlink():
        return False
    try:
        return is_reparse_or_link(path)
    except FileNotFoundError:
        return False
    except PathSafetyError as exc:
        raise ValidationError(
            "native path identity could not be established",
            details={"path_role": path.name, "cause": str(exc)},
        ) from exc


def _assert_plain_chain(path: Path, stop: Path) -> None:
    try:
        checked = reject_reparse_chain(path, label="project-contained path", must_exist=path.exists())
        checked.relative_to(stop)
    except (PathSafetyError, ValueError) as exc:
        raise ValidationError(
            "symlink/reparse or escaping path rejected",
            details={"path_role": path.name, "cause": str(exc)},
        ) from exc


def _contained_absolute(root: Path, raw: Any, field: str, *, must_exist: bool) -> Path:
    text = _string(raw, field)
    try:
        candidate = lexical_absolute(text, label=field)
        reject_reparse_chain(candidate, label=field, must_exist=must_exist)
    except PathSafetyError as exc:
        raise ValidationError("absolute path is unsafe", details={"field": field, "cause": str(exc)}) from exc
    try:
        candidate.relative_to(root)
    except ValueError as exc:
        raise ValidationError("path escapes project root", details={"field": field}) from exc
    return candidate


def _contained_relative(root: Path, raw: Any, field: str, *, must_exist: bool) -> Path:
    relative = validate_relative_path(raw, stage=field)
    lexical = root.joinpath(*PurePosixPath(relative).parts)
    try:
        candidate = reject_reparse_chain(lexical, label=field, must_exist=must_exist)
    except (OSError, PathSafetyError) as exc:
        raise ValidationError(
            "required relative path is absent or inaccessible",
            details={"field": field, "error_type": type(exc).__name__},
        ) from exc
    try:
        candidate.relative_to(root)
    except ValueError as exc:
        raise ValidationError("relative path escapes project root", details={"field": field}) from exc
    return candidate


def _context_fingerprint(context: Mapping[str, Any]) -> str:
    text = "".join(f"{key}={context[key]}\n" for key in CONTEXT_FINGERPRINT_ORDER)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _validate_context(raw: Any) -> dict[str, Any]:
    context = dict(_exact_fields(raw, CONTEXT_FIELDS, "context"))
    if context["schema"] != CONTEXT_SCHEMA:
        raise ValidationError("operation context schema mismatch")
    for field in ("project_id", "image_id", "analysis_session_id", "command_id"):
        validate_human_id(context[field], field=field)
    for field in ("project_uid", "image_uid", "analysis_session_uid"):
        validate_canonical_uuid(context[field])
    for field in ("source_sha256", "master_pixel_sha256"):
        _sha(context[field], field)
    for field in ("selection_revision", "generation_token"):
        value = context[field]
        if not isinstance(value, str) or SAFE_COUNTER_RE.fullmatch(value) is None:
            raise ValidationError("context counter must be canonical decimal text", details={"field": field})
    for field in ("imageplus_identity", "window_identity", "state_identity"):
        _string(context[field], field)

    revision_id = context["revision_id"]
    revision_uid = context["revision_uid"]
    working_state_id = context["working_state_id"]
    revision_active = revision_id != "NOT_APPLICABLE"
    working_active = working_state_id != "NOT_APPLICABLE"
    if revision_active == working_active:
        raise ValidationError("exactly one revision or working_state must be active")
    if revision_active:
        validate_human_id(revision_id, field="revision_id")
        validate_canonical_uuid(revision_uid)
        if context["state_identity"] != f"{revision_id}|{revision_uid}":
            raise ValidationError("revision state_identity mismatch")
    else:
        if revision_uid != "NOT_APPLICABLE":
            raise ValidationError("inapplicable revision UID must be NOT_APPLICABLE")
        validate_human_id(working_state_id, field="working_state_id")
        if context["state_identity"] != working_state_id:
            raise ValidationError("working-state identity mismatch")

    object_uuid = context["object_uuid"]
    cavity_id = context["cavity_id"]
    if (object_uuid == "NOT_APPLICABLE") != (cavity_id == "NOT_APPLICABLE"):
        raise ValidationError("object_uuid/cavity_id applicability mismatch")
    if object_uuid != "NOT_APPLICABLE":
        validate_canonical_uuid(object_uuid)
        validate_cavity_id(cavity_id)
    observed = _sha(context["context_fingerprint_sha256"], "context_fingerprint_sha256")
    expected = _context_fingerprint(context)
    if observed != expected:
        raise StaleContextError(
            "operation context fingerprint mismatch",
            details={"expected": expected, "observed": observed},
        )
    return context


def _split_registry_rows_exact(data: bytes) -> list[bytes]:
    """Split physical registry rows while retaining each original terminator."""

    rows: list[bytes] = []
    start = 0
    for index, value in enumerate(data):
        if value == 0x0A:
            rows.append(data[start : index + 1])
            start = index + 1
    if start < len(data):
        rows.append(data[start:])
    return rows


def _registry_row_content(row: bytes) -> bytes:
    content = row
    if content.endswith(b"\n"):
        content = content[:-1]
        if content.endswith(b"\r"):
            content = content[:-1]
    if b"\r" in content or b"\n" in content:
        raise ValidationError("images.tsv contains a non-canonical row terminator")
    return content


def _validate_registry_bound_identity(root: Path, context: Mapping[str, Any]) -> dict[str, Any]:
    """Bind bridge image/session identities to the exact WP-17 registry bytes.

    Prompt 1 is not a schema migration, so the authoritative legacy evidence is
    the existing direct-child ``images.tsv`` row.  The row bytes include their
    original LF/CRLF terminator and the frozen golden numbers the header as row
    1 (therefore the first data row has ordinal 2).
    """

    lexical_registry = root / LEGACY_IMAGE_REGISTRY_RELATIVE_PATH
    try:
        registry = plain_file(lexical_registry, label="images.tsv", single_link=True)
    except PathSafetyError as exc:
        raise ValidationError("images.tsv is missing or unsafe", details={"cause": str(exc)}) from exc
    if registry.parent != root or registry.name != LEGACY_IMAGE_REGISTRY_RELATIVE_PATH:
        raise ValidationError("images.tsv is not the canonical direct child")
    _assert_plain_chain(registry, root)
    try:
        data = stable_plain_bytes(registry, label="images.tsv")
    except PathSafetyError as exc:
        raise ValidationError(
            "images.tsv cannot be read safely",
            details={"error_type": type(exc).__name__},
        ) from exc
    rows = _split_registry_rows_exact(data)
    if len(rows) < 2 or _registry_row_content(rows[0]) != LEGACY_IMAGE_REGISTRY_HEADER:
        raise ValidationError("images.tsv header mismatch")

    image_id_bytes = context["image_id"].encode("ascii")
    selected: bytes | None = None
    selected_ordinal = 0
    for ordinal, row in enumerate(rows[1:], start=2):
        content = _registry_row_content(row)
        if not content:
            raise ValidationError("images.tsv contains an empty data row")
        if content.count(b"\t") != 13:
            raise ValidationError("images.tsv data row width mismatch")
        if content.split(b"\t", 1)[0] == image_id_bytes:
            if selected is not None:
                raise ValidationError("duplicate image_id in images.tsv")
            selected = row
            selected_ordinal = ordinal
    if selected is None:
        raise ValidationError("image_id absent from images.tsv")

    token = legacy_image_parent_identity_token(
        LEGACY_IMAGE_REGISTRY_RELATIVE_PATH,
        selected_ordinal,
        selected,
    )
    parent = legacy_image_parent_component(token)
    expected_image_uid = derive_image_uid(
        context["project_uid"],
        parent,
        context["image_id"],
    )
    if context["image_uid"] != expected_image_uid:
        raise ValidationError(
            "image_uid is not the WP-17 UUIDv5 derived from images.tsv",
            details={"expected": expected_image_uid, "observed": context["image_uid"]},
        )

    expected_session_uid = derive_session_uid(
        context["project_uid"],
        expected_image_uid,
        context["analysis_session_id"],
    )
    if context["analysis_session_uid"] != expected_session_uid:
        raise ValidationError(
            "analysis_session_uid is not the WP-17 UUIDv5",
            details={"expected": expected_session_uid, "observed": context["analysis_session_uid"]},
        )
    synthetic_session_id = synthesize_legacy_session_id(expected_image_uid)
    return {
        "legacy_image_registry_relative_path": LEGACY_IMAGE_REGISTRY_RELATIVE_PATH,
        "legacy_image_registry_row_ordinal": selected_ordinal,
        "legacy_image_registry_row_sha256": hashlib.sha256(selected).hexdigest(),
        "legacy_image_parent_identity_token": token,
        "image_parent_identity_component": parent,
        "image_uid": expected_image_uid,
        "analysis_session_id_origin": (
            "SYNTHESIZED_LEGACY_IMAGE_UID_V1"
            if context["analysis_session_id"] == synthetic_session_id
            else "PRESERVED_LEGACY"
        ),
        "analysis_session_uid": expected_session_uid,
    }


def _parse_properties(text: str) -> dict[str, str]:
    if "\x00" in text or "\r" in text:
        raise ValidationError("ROI properties contain forbidden NUL/CR")
    result: dict[str, str] = {}
    for number, line in enumerate(text.split("\n"), 1):
        if not line:
            continue
        if ":" not in line:
            raise ValidationError("ROI property line has no colon", details={"line": number})
        key, value = line.split(":", 1)
        key = key.strip()
        value = value[1:] if value.startswith(" ") else value
        if not key or key in result or any(character in key for character in "\t\n:"):
            raise ValidationError("ROI property key is empty/duplicated/unsafe", details={"line": number})
        result[key] = value
    return result


def _validate_zip_and_rois(snapshot: Mapping[str, Any]) -> tuple[bytes, tuple[RoiEntry, ...]]:
    roi_snapshot = _exact_fields(snapshot["roi_snapshot"], ROI_SNAPSHOT_FIELDS, "roi_snapshot")
    if roi_snapshot["encoding"] != ROI_ENCODING:
        raise ValidationError("ROI snapshot encoding mismatch")
    declared_bytes = _nonnegative_integer(roi_snapshot["bytes"], "roi_snapshot.bytes")
    declared_count = _nonnegative_integer(roi_snapshot["roi_count"], "roi_snapshot.roi_count")
    declared_sha = _sha(roi_snapshot["sha256"], "roi_snapshot.sha256")
    encoded = _string(roi_snapshot["base64"], "roi_snapshot.base64", allow_empty=True)
    try:
        zip_bytes = base64.b64decode(encoded.encode("ascii"), validate=True)
    except (UnicodeEncodeError, ValueError) as exc:
        raise ValidationError("ROI snapshot base64 is invalid") from exc
    if len(zip_bytes) != declared_bytes or hashlib.sha256(zip_bytes).hexdigest() != declared_sha:
        raise ValidationError("ROI snapshot bytes/hash mismatch")

    members: dict[str, bytes] = {}
    try:
        with zipfile.ZipFile(io.BytesIO(zip_bytes), "r") as archive:
            for info in archive.infolist():
                name = info.filename
                pure = PurePosixPath(name)
                if info.is_dir() or pure.is_absolute() or "\\" in name or any(part in {"", ".", ".."} for part in pure.parts):
                    raise ValidationError("ROI ZIP contains unsafe/non-file entry", details={"entry": name})
                key = name.casefold()
                if key in {existing.casefold() for existing in members}:
                    raise ValidationError("ROI ZIP contains duplicate portable entry", details={"entry": name})
                members[name] = archive.read(info)
    except (zipfile.BadZipFile, OSError) as exc:
        raise ValidationError("ROI snapshot is not a valid ZIP") from exc
    if len(members) != declared_count:
        raise ValidationError("ROI ZIP count differs from declared roi_count")

    raw_records = snapshot["roi_records"]
    if not isinstance(raw_records, list) or len(raw_records) != declared_count:
        raise ValidationError("roi_records count differs from ROI ZIP")
    entries: list[RoiEntry] = []
    seen_names: set[str] = set()
    for expected_index, raw_record in enumerate(raw_records):
        record = _exact_fields(raw_record, ROI_RECORD_FIELDS, f"roi_records[{expected_index}]")
        if record["index"] != expected_index:
            raise ValidationError("roi_records must use contiguous zero-based indices")
        name = _string(record["name"], f"roi_records[{expected_index}].name")
        if name not in members or name.casefold() in seen_names:
            raise ValidationError("ROI record name is absent/duplicated in ZIP", details={"name": name})
        seen_names.add(name.casefold())
        serialized_sha = _sha(record["serialized_roi_sha256"], "serialized_roi_sha256")
        if hashlib.sha256(members[name]).hexdigest() != serialized_sha:
            raise ValidationError("serialized ROI hash mismatch", details={"name": name})
        properties_text = _string(record["properties_text"], "properties_text", allow_empty=True)
        if hashlib.sha256(properties_text.encode("utf-8")).hexdigest() != _sha(record["properties_sha256"], "properties_sha256"):
            raise ValidationError("ROI properties hash mismatch", details={"name": name})
        bounds_raw = _exact_fields(record["bounds"], BOUNDS_FIELDS, "ROI bounds")
        bounds = {field: _finite(bounds_raw[field], f"bounds.{field}") for field in BOUNDS_FIELDS}
        if bounds["width_px"] < 0 or bounds["height_px"] < 0:
            raise ValidationError("ROI bounds dimensions cannot be negative")
        coordinates = _exact_fields(record["coordinates"], COORDINATE_FIELDS, "ROI coordinates")
        x_values = coordinates["x_px"]
        y_values = coordinates["y_px"]
        if not isinstance(x_values, list) or not isinstance(y_values, list) or len(x_values) != len(y_values):
            raise ValidationError("ROI coordinate arrays must have equal length")
        x_tuple = tuple(_finite(value, f"coordinates.x_px[{index}]") for index, value in enumerate(x_values))
        y_tuple = tuple(_finite(value, f"coordinates.y_px[{index}]") for index, value in enumerate(y_values))
        group = _nonnegative_integer(record["group"], "ROI group")
        entries.append(
            RoiEntry(
                index=expected_index,
                name=name,
                imagej_roi_type=_string(record["imagej_roi_type"], "imagej_roi_type"),
                group=group,
                properties_text=properties_text,
                properties=_parse_properties(properties_text),
                serialized_sha256=serialized_sha,
                bounds=bounds,
                x_coordinates=x_tuple,
                y_coordinates=y_tuple,
            )
        )
    return zip_bytes, tuple(entries)


def _validate_analysis(raw: Any) -> dict[str, Any]:
    analysis = dict(_exact_fields(raw, ANALYSIS_FIELDS, "analysis_parameters"))
    if analysis["classification_policy"] != CLASSIFICATION_POLICY:
        raise ValidationError("classification policy mismatch")
    if analysis["validity_update_mode"] != VALIDITY_UPDATE_MODE:
        raise ValidationError("validity update mode mismatch")
    if analysis["image_mode"] not in {"with_surface", "without_surface"}:
        raise ValidationError("image_mode is outside Prompt-1 vocabulary")
    if type(analysis["use_whole_image"]) is not int or analysis["use_whole_image"] not in {0, 1}:
        raise ValidationError("use_whole_image must be 0 or 1")
    status = analysis["thickness_status"]
    if status not in {"KNOWN", "UNKNOWN", "NOT_APPLICABLE", "NOT_MEASURED", "UNDEFINED"}:
        raise ValidationError("thickness_status is invalid")
    thickness = analysis["thickness_nm"]
    if status == "KNOWN":
        _finite(thickness, "thickness_nm", positive=True)
    elif thickness is not None:
        raise ValidationError("non-KNOWN thickness must be null")
    _finite(analysis["histogram_bin_nm"], "histogram_bin_nm", positive=True)
    _finite(analysis["feature_distance_bin_nm"], "feature_distance_bin_nm", positive=True)
    return analysis


def _validate_state(raw: Any) -> dict[str, Any]:
    state = dict(_exact_fields(raw, STATE_FIELDS, "state"))
    if state["parent_revision_id"] == "NOT_APPLICABLE":
        if state["parent_revision_uid"] != "NOT_APPLICABLE":
            raise ValidationError("parent revision ID/UID applicability mismatch")
    else:
        validate_human_id(state["parent_revision_id"], field="parent_revision_id")
        validate_canonical_uuid(state["parent_revision_uid"])
    if state["working_state_id"] != "NOT_APPLICABLE":
        validate_human_id(state["working_state_id"], field="working_state_id")
    return state


def _validate_common_snapshot(
    root: Path,
    context: dict[str, Any],
    payload: dict[str, Any],
    operation_input: Mapping[str, Any],
) -> PreparedSnapshot:
    snapshot = dict(_exact_fields(operation_input, COMMON_SNAPSHOT_FIELDS, "operation_input"))
    if snapshot["snapshot_schema"] != SNAPSHOT_SCHEMA:
        raise ValidationError("operation snapshot schema mismatch")
    image = dict(_exact_fields(snapshot["image"], IMAGE_FIELDS, "snapshot.image"))
    for field in ("width_px", "height_px"):
        _positive_integer(image[field], f"image.{field}")
    if image["bit_depth"] not in {8, 16, 24, 32}:
        raise ValidationError("unsupported Fiji bit depth")
    if image["image_role"] != "MASTER_READ_ONLY":
        raise ValidationError("image role must be MASTER_READ_ONLY")
    if image["source_hash_status"] not in {"VERIFIED", "NOT_VERIFIED", "MISMATCH"}:
        raise ValidationError("source hash status is invalid")
    if image["master_pixel_hash_status"] not in {"VERIFIED", "NOT_VERIFIED", "MISMATCH"}:
        raise ValidationError("master pixel hash status is invalid")
    _string(image["master_pixel_hash_method"], "master_pixel_hash_method")
    for field in ("scale_x_nm_px", "scale_y_nm_px"):
        _finite(image[field], f"image.{field}", positive=True)
        if float(image[field]) != float(payload[field]):
            raise ValidationError("snapshot/payload scale mismatch", details={"field": field})
    if image["scale_method"] != payload["scale_method"]:
        raise ValidationError("snapshot/payload scale_method mismatch")

    expected_image_dir = root / "images" / context["image_id"]
    image_directory = _contained_absolute(root, payload["image_directory"], "payload.image_directory", must_exist=True)
    if image_directory != expected_image_dir or not image_directory.is_dir():
        raise ValidationError("image_directory is not the canonical project image directory")
    try:
        plain_directory(image_directory, label="payload.image_directory")
    except PathSafetyError as exc:
        raise ValidationError("image_directory is unsafe", details={"cause": str(exc)}) from exc
    source_path = _contained_absolute(root, payload["source_path"], "payload.source_path", must_exist=True)
    try:
        source_path.relative_to(image_directory)
    except ValueError as exc:
        raise ValidationError("source_path is outside image_directory") from exc
    try:
        plain_file(source_path, label="payload.source_path", single_link=True)
    except PathSafetyError as exc:
        raise ValidationError("source_path must be a plain single-link file", details={"cause": str(exc)}) from exc
    actual_source = _sha256_file(source_path)
    if actual_source != context["source_sha256"]:
        raise ValidationError("live source bytes differ from operation context")
    if image["source_hash_status"] == "VERIFIED" and actual_source != context["source_sha256"]:
        raise ValidationError("verified source hash status contradicts bytes")

    roi_zip_bytes, roi_entries = _validate_zip_and_rois(snapshot)
    state = _validate_state(snapshot["state"])
    analysis = _validate_analysis(snapshot["analysis_parameters"])
    return PreparedSnapshot(
        project_root=root,
        image_directory=image_directory,
        source_path=source_path,
        context=context,
        payload=payload,
        operation_input=snapshot,
        image=image,
        roi_zip_bytes=roi_zip_bytes,
        roi_entries=roi_entries,
        state=state,
        analysis=analysis,
    )


def _validate_combined_input(root: Path, raw: Any) -> dict[str, Any]:
    value = dict(_exact_fields(raw, COMBINED_FIELDS, "combined operation_input"))
    image_ids = value["selected_image_ids"]
    pointers = value["current_run_pointer_relative_paths"]
    if not isinstance(image_ids, list) or not image_ids or len(image_ids) != len(set(image_ids)):
        raise ValidationError("selected_image_ids must be a non-empty unique array")
    if not isinstance(pointers, list) or len(pointers) != len(image_ids):
        raise ValidationError("pointer list must align with selected_image_ids")
    for image_id, relative in zip(image_ids, pointers):
        validate_human_id(image_id, field="selected_image_id")
        expected = f"images/{image_id}/current_run.tsv"
        if relative != expected:
            raise ValidationError("combined pointer path is not canonical", details={"image_id": image_id})
        _contained_relative(root, relative, "combined pointer", must_exist=True)
    if value["combined_runs_relative_path"] != "combined_runs":
        raise ValidationError("combined_runs_relative_path must be exactly combined_runs")
    combined_parent = _contained_relative(
        root,
        value["combined_runs_relative_path"],
        "combined_runs_relative_path",
        must_exist=True,
    )
    if not combined_parent.is_dir():
        raise ValidationError("combined_runs must be an existing plain directory")
    _finite(value["histogram_bin_nm"], "histogram_bin_nm", positive=True)
    _finite(value["feature_distance_bin_nm"], "feature_distance_bin_nm", positive=True)
    return value


def _positive_decimal_exact(value: Any, field: str) -> Decimal:
    if isinstance(value, bool) or value is None:
        raise ValidationError("combined bin value is absent or boolean", details={"field": field})
    try:
        number = value if isinstance(value, Decimal) else Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise ValidationError("combined bin value is not decimal", details={"field": field}) from exc
    if not number.is_finite() or number <= 0:
        raise ValidationError("combined bin value must be finite and positive", details={"field": field})
    return number


def _verify_combined_sources(
    root: Path,
    combined: Mapping[str, Any],
    *,
    expected_project_uid: str,
) -> tuple[Any, ...]:
    """Consume exact current_run.tsv authorities and reverify their revisions.

    The selected human image ID is bound lexically to its own pointer,
    registry and measurement_runs directory.  ``current_run.txt`` and newest-
    directory discovery are intentionally absent from this path.
    """

    from .combined import assert_compatible_bins
    from .revision import make_revision_verifier
    from .run_consumer import load_current_run

    expected_bins = {
        "histogram_bin_nm": _positive_decimal_exact(
            combined["histogram_bin_nm"],
            "histogram_bin_nm",
        ),
        "feature_distance_bin_nm": _positive_decimal_exact(
            combined["feature_distance_bin_nm"],
            "feature_distance_bin_nm",
        ),
    }
    verified: list[Any] = []
    seen_run_uids: set[str] = set()
    seen_image_uids: set[str] = set()
    for image_id, pointer_relative in zip(
        combined["selected_image_ids"],
        combined["current_run_pointer_relative_paths"],
    ):
        image_directory = _contained_relative(
            root,
            f"images/{image_id}",
            "combined image directory",
            must_exist=True,
        )
        if not image_directory.is_dir():
            raise ValidationError("combined image directory is not a plain directory")
        pointer_path = _contained_relative(
            root,
            pointer_relative,
            "combined current_run.tsv",
            must_exist=True,
        )
        registry_path = image_directory / "run_registry.json"
        try:
            plain_file(registry_path, label="combined source run_registry.json", single_link=True)
        except PathSafetyError as exc:
            raise ValidationError(
                "combined source run_registry.json is absent or unsafe",
                details={"image_id": image_id, "cause": str(exc)},
            ) from exc

        def verify_revision_binding(
            run_manifest: Mapping[str, Any],
            *,
            bound_image_directory: Path = image_directory,
        ) -> bool:
            revision_id = validate_human_id(
                run_manifest.get("revision_id"),
                field="revision_id",
            )
            revision_path = bound_image_directory / "roi_sessions" / f"REV_{revision_id}"
            return make_revision_verifier(revision_path)(run_manifest)

        run = load_current_run(
            root,
            pointer_path,
            registry_path=registry_path,
            revision_verifier=verify_revision_binding,
        )
        run = require_scientific_eligibility(run)
        if run.pointer is None:
            raise ValidationError("combined source RUN lacks its verified pointer")
        expected_run_parent = PurePosixPath(f"images/{image_id}/measurement_runs")
        run_relative = PurePosixPath(run.pointer.relative_path)
        if (
            run_relative.parent != expected_run_parent
            or run_relative.name != f"RUN_{run.run_id}"
        ):
            raise ValidationError(
                "combined current_run.tsv does not address its selected image measurement_runs",
                details={"image_id": image_id},
            )
        if run.manifest["project_uid"] != expected_project_uid:
            raise ValidationError(
                "combined source RUN belongs to another project_uid",
                details={"image_id": image_id},
            )
        if run.run_uid in seen_run_uids or run.manifest["image_uid"] in seen_image_uids:
            raise ValidationError("combined selection repeats a RUN or image identity")
        seen_run_uids.add(run.run_uid)
        seen_image_uids.add(run.manifest["image_uid"])
        if any(row.get("image_id") != image_id for row in run.object_rows):
            raise ValidationError(
                "combined object rows do not bind the selected image_id",
                details={"image_id": image_id},
            )
        bin_policy = run.manifest.get("bin_contract")
        if not isinstance(bin_policy, Mapping):
            raise ValidationError(
                "combined source RUN lacks an explicit bin_contract",
                details={"image_id": image_id},
            )
        for field, expected in expected_bins.items():
            observed = _positive_decimal_exact(
                bin_policy.get(field),
                f"{image_id}.bin_contract.{field}",
            )
            if observed != expected:
                raise ValidationError(
                    "combined source RUN bin differs from the exact request",
                    details={
                        "image_id": image_id,
                        "field": field,
                        "expected": str(expected),
                        "observed": str(observed),
                    },
                )
        verified.append(run)
    assert_compatible_bins(tuple(verified))
    return tuple(verified)


def _validate_request(request: Any) -> tuple[dict[str, Any], Path, dict[str, Any], dict[str, Any]]:
    value = dict(_exact_fields(request, REQUEST_FIELDS, "request"))
    if value["schema"] != REQUEST_SCHEMA:
        raise ValidationError("request schema mismatch")
    if not isinstance(value["request_id"], str) or UUID4_RE.fullmatch(value["request_id"]) is None:
        raise ValidationError("request_id must be a lowercase canonical UUIDv4")
    operation = value["operation"]
    phase = value["phase"]
    if operation not in OPERATIONS or phase not in PHASES:
        raise ValidationError("operation or phase is invalid")
    if value["technical_preview"] is not True:
        raise ValidationError("technical_preview must be literal true")
    if operation in READ_ONLY_OPERATIONS and phase != "EXECUTE":
        raise ValidationError("read-only operation accepts only EXECUTE")
    if operation in MUTATING_OPERATIONS and phase not in {"PREPARE", "COMMIT", "ABORT"}:
        raise ValidationError("mutating operation requires PREPARE/COMMIT/ABORT")
    token = value["prepare_token"]
    if phase in {"EXECUTE", "PREPARE"}:
        if token != "NOT_APPLICABLE":
            raise ValidationError("prepare_token must be NOT_APPLICABLE before PREPARE")
    elif not isinstance(token, str) or SHA_RE.fullmatch(token) is None:
        raise ValidationError("COMMIT/ABORT requires a prepare token")

    root_raw = _string(value["project_root"], "project_root")
    try:
        root = plain_directory(root_raw, label="project_root")
    except PathSafetyError as exc:
        raise ValidationError("project_root must be a plain existing directory", details={"cause": str(exc)}) from exc
    context = _validate_context(value["context"])
    _validate_registry_bound_identity(root, context)
    payload = dict(_exact_fields(value["payload"], PAYLOAD_FIELDS, "payload"))
    if payload["facade_version"] != FACADE_VERSION or payload["runtime_version"] != RUNTIME_VERSION or payload["candidate_version"] != CANDIDATE_VERSION:
        raise ValidationError("facade/runtime/candidate version mismatch")
    validate_human_id(payload["operator_id"], field="operator_id")
    for field in ("scale_x_nm_px", "scale_y_nm_px"):
        _finite(payload[field], field, positive=True)
    validate_human_id(payload["scale_method"], field="scale_method")
    forbidden = value["forbidden_response_roots"]
    if not isinstance(forbidden, list) or len(forbidden) < 2 or not all(isinstance(item, str) and Path(item).is_absolute() for item in forbidden):
        raise ValidationError("forbidden_response_roots must contain absolute project/package roots")
    try:
        forbidden_lexical = [lexical_absolute(item, label="forbidden response root") for item in forbidden]
    except PathSafetyError as exc:
        raise ValidationError("forbidden_response_roots contains an unsafe path", details={"cause": str(exc)}) from exc
    if root not in forbidden_lexical:
        raise ValidationError("project_root missing from forbidden_response_roots")
    policy = _exact_fields(value["response_policy"], {"temporary_root"}, "response_policy")
    try:
        plain_directory(_string(policy["temporary_root"], "temporary_root"), label="temporary_root")
    except PathSafetyError as exc:
        raise ValidationError("temporary_root must be a plain existing absolute directory", details={"cause": str(exc)}) from exc
    return value, root, context, payload


def _prepare_token(request: Mapping[str, Any]) -> str:
    bound = {
        "schema": "CTL_P1_PREPARE_TOKEN_INPUT_V1",
        "request_id": request["request_id"],
        "operation": request["operation"],
        "technical_preview": request["technical_preview"],
        "context": request["context"],
        "payload": request["payload"],
        "project_root": request["project_root"],
    }
    return hashlib.sha256(canonical_json_bytes(bound)).hexdigest()


def _master_record(snapshot: PreparedSnapshot) -> dict[str, Any]:
    return {
        "image_role": snapshot.image["image_role"],
        "source_sha256": snapshot.context["source_sha256"],
        "master_pixel_sha256": snapshot.context["master_pixel_sha256"],
        "master_pixel_hash_method": snapshot.image["master_pixel_hash_method"],
        "master_pixel_hash_status": snapshot.image["master_pixel_hash_status"],
        "source_width_px": snapshot.image["width_px"],
        "source_height_px": snapshot.image["height_px"],
    }


def _prepare_common(snapshot: PreparedSnapshot, *, operation: str) -> dict[str, Any]:
    validate_master_protection(_master_record(snapshot), operation="EXPORT_RUN" if operation != "validate" else "REVIEW")
    if snapshot.image["source_hash_status"] != "VERIFIED":
        raise ValidationError("source hash must be VERIFIED for scientific operation")
    return {
        "context_fingerprint_sha256": snapshot.context["context_fingerprint_sha256"],
        "source_sha256": snapshot.context["source_sha256"],
        "master_pixel_sha256": snapshot.context["master_pixel_sha256"],
        "roi_zip_sha256": hashlib.sha256(snapshot.roi_zip_bytes).hexdigest(),
        "roi_count": len(snapshot.roi_entries),
        "source_read_only_verified": True,
        "project_schema_version": 1,
        "run_contract_version": 2,
        "project_migration": False,
    }


def _revision_parent(snapshot: PreparedSnapshot, raw: Any) -> Path:
    expected = f"images/{snapshot.context['image_id']}/roi_sessions"
    if raw != expected:
        raise ValidationError("revisions_relative_path is not canonical")
    parent = _contained_relative(snapshot.project_root, raw, "revisions_relative_path", must_exist=False)
    if parent.exists() and not parent.is_dir():
        raise ValidationError("revision parent is not a directory")
    return parent


def _prepare_save(snapshot: PreparedSnapshot, raw_input: Mapping[str, Any]) -> dict[str, Any]:
    expected = COMMON_SNAPSHOT_FIELDS | {"revisions_relative_path"}
    _exact_fields(raw_input, expected, "save_revision operation_input")
    common_snapshot = {key: raw_input[key] for key in COMMON_SNAPSHOT_FIELDS}
    prepared = _validate_common_snapshot(snapshot.project_root, snapshot.context, snapshot.payload, common_snapshot)
    if prepared.context["working_state_id"] == "NOT_APPLICABLE":
        raise ValidationError("save_revision requires an active working_state")
    if prepared.state["working_state_id"] != prepared.context["working_state_id"]:
        raise StaleContextError("working_state changed between context and ROI snapshot")
    parent = _revision_parent(prepared, raw_input["revisions_relative_path"])
    result = _prepare_common(prepared, operation="save_revision")
    result["revision_parent_relative_path"] = parent.relative_to(prepared.project_root).as_posix()
    result["parent_revision_id"] = prepared.state["parent_revision_id"]
    return result


def _new_revision_identity(parent: Path) -> tuple[str, str]:
    for _ in range(16):
        revision_id = "P1_" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%f") + "_" + uuid.uuid4().hex[:8]
        if not (parent / f"REV_{revision_id}").exists() and not (parent / f"REV_{revision_id}.partial").exists():
            return revision_id, new_uuid4_identity()
    raise TransactionError("could not reserve a unique revision identity")


def _commit_save(snapshot: PreparedSnapshot, raw_input: Mapping[str, Any]) -> dict[str, Any]:
    _prepare_save(snapshot, raw_input)
    parent = _revision_parent(snapshot, raw_input["revisions_relative_path"])
    if not parent.exists():
        parent.mkdir(exist_ok=False)
    revision_id, revision_uid = _new_revision_identity(parent)
    binding = RevisionBinding(
        project_uid=snapshot.context["project_uid"],
        image_uid=snapshot.context["image_uid"],
        analysis_session_uid=snapshot.context["analysis_session_uid"],
        revision_id=revision_id,
        revision_uid=revision_uid,
        parent_revision_id=snapshot.state["parent_revision_id"],
        source_sha256=snapshot.context["source_sha256"],
        master_pixel_sha256=snapshot.context["master_pixel_sha256"],
    )
    metadata = {
        "metadata_schema": "CTL_P1_REVISION_SNAPSHOT_METADATA_V1",
        "context_fingerprint_sha256": snapshot.context["context_fingerprint_sha256"],
        "working_state_id": snapshot.context["working_state_id"],
        "roi_count": len(snapshot.roi_entries),
        "classification_policy": snapshot.analysis["classification_policy"],
        "validity_update_mode": snapshot.analysis["validity_update_mode"],
        "image_role": snapshot.image["image_role"],
        "master_pixel_hash_method": snapshot.image["master_pixel_hash_method"],
        "technical_preview": True,
        "scientific_validation": False,
    }
    pointer_path = snapshot.image_directory / "current_revision_p1.json"
    published = publish_revision(
        parent,
        binding=binding,
        roi_zip_bytes=snapshot.roi_zip_bytes,
        metadata=metadata,
        current_pointer_path=pointer_path,
        project_root=snapshot.project_root,
        atomic_capability="UNKNOWN",
    )
    verified = verify_revision(published.path, source_path=snapshot.source_path)
    return {
        "result": "REVISION_PUBLISHED",
        "revision_id": revision_id,
        "revision_uid": revision_uid,
        "relative_path": verified.path.relative_to(snapshot.project_root).as_posix(),
        "revision_manifest_sha256": verified.manifest_sha256,
        "roi_zip_sha256": verified.manifest["roi_zip_sha256"],
        "pointer_relative_path": pointer_path.relative_to(snapshot.project_root).as_posix(),
        "directory_atomic_move_capability": published.directory_atomic_move_capability,
        "retention_policy": published.retention_policy,
    }


def _prepare_load_revision(
    root: Path,
    context: dict[str, Any],
    payload: dict[str, Any],
    raw_input: Any,
) -> dict[str, Any]:
    """Verify one P1 revision for an in-memory working-state load.

    This operation is byte-read-only with respect to the schema-1 project.  It
    verifies both the explicitly selected historical revision and the current
    pointer target, then returns the selected ROI ZIP as response bytes.  Fiji
    applies those bytes transactionally in memory and clears only its live RUN
    association; neither project pointer is rewritten here.
    """

    value = dict(_exact_fields(raw_input, LOAD_REVISION_FIELDS, "load_revision operation_input"))
    if value["load_schema"] != "CTL_P1_LOAD_REVISION_REQUEST_V1":
        raise ValidationError("load revision request schema mismatch")
    working_state_id = validate_human_id(value["working_state_id"], field="working_state_id")
    if working_state_id in {
        context["working_state_id"],
        context["revision_id"],
        context["revision_uid"],
    }:
        raise ValidationError("load revision requires a fresh working_state_id")

    expected_image_directory = root / "images" / context["image_id"]
    image_directory = _contained_absolute(
        root,
        payload["image_directory"],
        "payload.image_directory",
        must_exist=True,
    )
    if image_directory != expected_image_directory or not image_directory.is_dir():
        raise ValidationError("image_directory is not the canonical project image directory")
    try:
        plain_directory(image_directory, label="payload.image_directory")
    except PathSafetyError as exc:
        raise ValidationError("image_directory is unsafe", details={"cause": str(exc)}) from exc
    source_path = _contained_absolute(
        root,
        payload["source_path"],
        "payload.source_path",
        must_exist=True,
    )
    try:
        plain_file(source_path, label="payload.source_path", single_link=True)
    except PathSafetyError as exc:
        raise ValidationError("source_path is unsafe", details={"cause": str(exc)}) from exc
    try:
        source_path.relative_to(image_directory)
    except ValueError as exc:
        raise ValidationError("source_path is outside image_directory") from exc
    if not source_path.is_file() or _sha256_file(source_path) != context["source_sha256"]:
        raise ValidationError("live source bytes differ from operation context")

    revision_relative = validate_relative_path(
        value["revision_relative_path"],
        stage="LOAD_REVISION",
    )
    revision_parts = PurePosixPath(revision_relative).parts
    expected_prefix = ("images", context["image_id"], "roi_sessions")
    if (
        len(revision_parts) != 4
        or revision_parts[:3] != expected_prefix
        or not revision_parts[3].startswith("REV_")
    ):
        raise ValidationError("selected revision path is not a canonical direct P1 revision")
    selected_path = _contained_relative(
        root,
        revision_relative,
        "revision_relative_path",
        must_exist=True,
    )
    selected = verify_revision(selected_path, source_path=source_path)
    selected_expected = {
        "project_uid": context["project_uid"],
        "image_uid": context["image_uid"],
        "analysis_session_uid": context["analysis_session_uid"],
        "source_sha256": context["source_sha256"],
        "master_pixel_sha256": context["master_pixel_sha256"],
    }
    for field, expected in selected_expected.items():
        if selected.manifest[field] != expected:
            raise ValidationError(
                "selected revision does not bind the live image/session",
                details={"field": field},
            )

    roi_record = next(
        (
            record
            for record in selected.manifest["files"]
            if record["relative_path"] == REVISION_ROI_NAME
        ),
        None,
    )
    if roi_record is None:
        raise ValidationError("selected revision omits the ROI authority record")
    roi_path = selected.path / REVISION_ROI_NAME
    try:
        roi_bytes = stable_plain_bytes(roi_path, label="selected revision ROI authority")
    except PathSafetyError as exc:
        raise ValidationError(
            "selected ROI authority cannot be read safely",
            details={"cause": str(exc)},
        ) from exc
    if (
        len(roi_bytes) != int(roi_record["bytes"])
        or hashlib.sha256(roi_bytes).hexdigest() != roi_record["sha256"]
        or roi_record["sha256"] != selected.manifest["roi_zip_sha256"]
    ):
        raise ValidationError("selected ROI authority changed after revision verification")
    with zipfile.ZipFile(io.BytesIO(roi_bytes), "r") as archive:
        roi_count = sum(1 for info in archive.infolist() if not info.is_dir())

    metadata_record = next(
        (
            record
            for record in selected.manifest["files"]
            if record["relative_path"] == "revision_metadata.json"
        ),
        None,
    )
    if metadata_record is None:
        raise ValidationError("selected revision omits verified revision_metadata.json")
    try:
        metadata_bytes = stable_plain_bytes(
            selected.path / "revision_metadata.json",
            label="selected revision metadata",
        )
    except PathSafetyError as exc:
        raise ValidationError(
            "revision metadata cannot be read safely",
            details={"cause": str(exc)},
        ) from exc
    if (
        len(metadata_bytes) != int(metadata_record["bytes"])
        or hashlib.sha256(metadata_bytes).hexdigest() != metadata_record["sha256"]
    ):
        raise ValidationError("revision metadata changed after revision verification")
    metadata = dict(
        _exact_fields(
            loads_canonical_json(metadata_bytes),
            REVISION_METADATA_FIELDS,
            "revision_metadata.json",
        )
    )
    if (
        metadata["metadata_schema"] != "CTL_P1_REVISION_SNAPSHOT_METADATA_V1"
        or metadata["classification_policy"] != CLASSIFICATION_POLICY
        or metadata["validity_update_mode"] != VALIDITY_UPDATE_MODE
        or metadata["image_role"] != "MASTER_READ_ONLY"
        or metadata["master_pixel_hash_method"] != "CTL_MASTER_PIXEL_SHA256_V1"
        or metadata["technical_preview"] is not True
        or metadata["scientific_validation"] is not False
        or metadata["roi_count"] != roi_count
    ):
        raise ValidationError("revision metadata does not satisfy the P1 snapshot contract")
    _sha(metadata["context_fingerprint_sha256"], "revision_metadata.context_fingerprint_sha256")
    validate_human_id(metadata["working_state_id"], field="revision_metadata.working_state_id")

    expected_pointer_relative = f"images/{context['image_id']}/current_revision_p1.json"
    if value["current_revision_pointer_relative_path"] != expected_pointer_relative:
        raise ValidationError("current revision pointer path is not canonical")
    pointer_path = _contained_relative(
        root,
        expected_pointer_relative,
        "current_revision_pointer_relative_path",
        must_exist=True,
    )
    current_pointer = verify_revision_pointer(
        pointer_path,
        project_root=root,
        source_path=source_path,
    )
    current_target_parts = PurePosixPath(current_pointer.pointer["relative_path"]).parts
    if (
        len(current_target_parts) != 4
        or current_target_parts[:3] != expected_prefix
        or not current_target_parts[3].startswith("REV_")
    ):
        raise ValidationError("current revision pointer target is not a canonical direct P1 revision")
    pointer_expected = {
        "project_uid": context["project_uid"],
        "image_uid": context["image_uid"],
        "analysis_session_uid": context["analysis_session_uid"],
        "source_sha256": context["source_sha256"],
        "master_pixel_sha256": context["master_pixel_sha256"],
    }
    for field, expected in pointer_expected.items():
        if current_pointer.target.manifest[field] != expected:
            raise ValidationError(
                "current revision pointer target does not bind the live image/session",
                details={"field": field},
            )

    expected_run_pointer_relative = f"images/{context['image_id']}/current_run.tsv"
    if value["current_run_pointer_relative_path"] != expected_run_pointer_relative:
        raise ValidationError("current RUN pointer path is not canonical")
    run_pointer_lexical = root.joinpath(*PurePosixPath(expected_run_pointer_relative).parts)
    run_pointer_sha256 = "NOT_APPLICABLE"
    if run_pointer_lexical.exists() or _is_reparse_or_link(run_pointer_lexical):
        try:
            run_pointer = plain_file(
                run_pointer_lexical,
                label="current RUN pointer",
                single_link=True,
            )
        except PathSafetyError as exc:
            raise ValidationError("current RUN pointer is not a plain file", details={"cause": str(exc)}) from exc
        if run_pointer.parent != image_directory:
            raise ValidationError("current RUN pointer is outside the canonical image directory")
        try:
            run_pointer_sha256 = hashlib.sha256(
                stable_plain_bytes(run_pointer, label="current RUN pointer")
            ).hexdigest()
        except PathSafetyError as exc:
            raise ValidationError(
                "current RUN pointer cannot be read safely",
                details={"cause": str(exc)},
            ) from exc

    working_state = make_working_state(
        selected,
        working_state_id=working_state_id,
        operator_id=payload["operator_id"],
        reason="load verified Prompt-1 revision into in-memory working state",
    )
    selected_after = verify_revision(selected.path, source_path=source_path)
    pointer_after = verify_revision_pointer(
        pointer_path,
        project_root=root,
        source_path=source_path,
    )
    if (
        selected_after.manifest_sha256 != selected.manifest_sha256
        or pointer_after.pointer_sha256 != current_pointer.pointer_sha256
        or pointer_after.target.manifest_sha256 != current_pointer.target.manifest_sha256
    ):
        raise ValidationError("revision authority changed while preparing the load response")
    if run_pointer_sha256 == "NOT_APPLICABLE":
        if run_pointer_lexical.exists() or _is_reparse_or_link(run_pointer_lexical):
            raise ValidationError("current RUN pointer appeared while preparing the load response")
    else:
        try:
            run_pointer_after_sha256 = hashlib.sha256(
                stable_plain_bytes(run_pointer_lexical, label="current RUN pointer")
            ).hexdigest()
        except PathSafetyError as exc:
            raise ValidationError(
                "current RUN pointer changed while preparing the load response",
                details={"cause": str(exc)},
            ) from exc
        if run_pointer_after_sha256 != run_pointer_sha256:
            raise ValidationError("current RUN pointer changed while preparing the load response")
    return {
        "result": "REVISION_VERIFIED_FOR_IN_MEMORY_WORKING_STATE",
        "load_schema": "CTL_P1_LOAD_REVISION_RESPONSE_V1",
        "source_context_fingerprint_sha256": context["context_fingerprint_sha256"],
        "project_uid": context["project_uid"],
        "image_uid": context["image_uid"],
        "analysis_session_uid": context["analysis_session_uid"],
        "source_sha256": context["source_sha256"],
        "master_pixel_sha256": context["master_pixel_sha256"],
        "revision_id": selected.manifest["revision_id"],
        "revision_uid": selected.manifest["revision_uid"],
        "parent_revision_id": selected.manifest["parent_revision_id"],
        "revision_manifest_sha256": selected.manifest_sha256,
        "revision_metadata_sha256": metadata_record["sha256"],
        "roi_zip_sha256": selected.manifest["roi_zip_sha256"],
        "roi_zip_bytes": len(roi_bytes),
        "roi_count": roi_count,
        "roi_zip_base64": base64.b64encode(roi_bytes).decode("ascii"),
        "working_state": working_state,
        "current_revision_pointer": {
            "relative_path": expected_pointer_relative,
            "pointer_sha256": current_pointer.pointer_sha256,
            "generation": int(current_pointer.pointer["generation"]),
            "revision_id": current_pointer.pointer["revision_id"],
            "revision_uid": current_pointer.pointer["revision_uid"],
            "revision_manifest_sha256": current_pointer.pointer["revision_manifest_sha256"],
        },
        "selected_is_current": selected.manifest_sha256 == current_pointer.target.manifest_sha256,
        "current_run_binding": {
            "action": "CLEARED_IN_MEMORY_NO_POINTER_WRITE",
            "relative_path": expected_run_pointer_relative,
            "pointer_sha256_before": run_pointer_sha256,
        },
        "project_mutations": 0,
        "revision_mutations": 0,
        "pointer_mutations": 0,
    }


def _prepare_operation(
    request: dict[str, Any],
    root: Path,
    context: dict[str, Any],
    payload: dict[str, Any],
) -> tuple[dict[str, Any], PreparedSnapshot | None]:
    operation = request["operation"]
    raw_input = payload["operation_input"]
    if operation == "load_revision":
        return _prepare_load_revision(root, context, payload, raw_input), None
    if operation == "combined_analysis":
        combined = _validate_combined_input(root, raw_input)
        runs = _verify_combined_sources(
            root,
            combined,
            expected_project_uid=context["project_uid"],
        )
        from .combined import assert_compatible_bins

        return (
            {
                "selected_image_count": len(combined["selected_image_ids"]),
                "pointer_count": len(combined["current_run_pointer_relative_paths"]),
                "verified_run_count": len(runs),
                "input_runs": [
                    {
                        "run_id": run.run_id,
                        "run_uid": run.run_uid,
                        "run_manifest_sha256": run.manifest_sha256,
                        "image_uid": run.manifest["image_uid"],
                        "revision_uid": run.manifest["revision_uid"],
                    }
                    for run in sorted(runs, key=lambda item: item.run_uid)
                ],
                "bin_contract_sha256": assert_compatible_bins(runs),
                "pointer_authority": "CURRENT_RUN_TSV_V1",
                "registry_verification": "PASS",
                "revision_verification": "PASS",
                "implicit_rebin": False,
            },
            None,
        )
    if operation == "save_revision":
        expected = COMMON_SNAPSHOT_FIELDS | {"revisions_relative_path"}
    elif operation == "export_run":
        expected = COMMON_SNAPSHOT_FIELDS | {
            "current_run_pointer_relative_path",
            "run_registry_relative_path",
            "runs_relative_path",
        }
    else:
        expected = COMMON_SNAPSHOT_FIELDS
    full_input = _exact_fields(raw_input, expected, f"{operation} operation_input")
    common = {key: full_input[key] for key in COMMON_SNAPSHOT_FIELDS}
    snapshot = _validate_common_snapshot(root, context, payload, common)
    if operation == "save_revision":
        observed = _prepare_save(snapshot, full_input)
    elif operation == "validate":
        observed = _prepare_common(snapshot, operation="validate")
    elif operation == "export_run":
        # Export-specific science/table/revision validation is performed by
        # the integration functions below before publication.
        observed = _prepare_export(snapshot, full_input)
    else:  # pragma: no cover - guarded by request validation
        raise ValidationError("unknown operation")
    return observed, snapshot


def _prepare_export(snapshot: PreparedSnapshot, raw_input: Mapping[str, Any]) -> dict[str, Any]:
    """Read-only export preflight; publication is implemented below."""

    if snapshot.context["revision_id"] == "NOT_APPLICABLE":
        raise ValidationError("export_run requires a published immutable revision")
    expected_paths = {
        "current_run_pointer_relative_path": f"images/{snapshot.context['image_id']}/current_run.tsv",
        "run_registry_relative_path": f"images/{snapshot.context['image_id']}/run_registry.json",
        "runs_relative_path": f"images/{snapshot.context['image_id']}/measurement_runs",
    }
    for field, expected in expected_paths.items():
        if raw_input[field] != expected:
            raise ValidationError("export control path is not canonical", details={"field": field})
        _contained_relative(snapshot.project_root, raw_input[field], field, must_exist=False)
    result = _prepare_common(snapshot, operation="export_run")
    result["control_paths"] = expected_paths
    # Added by the final integration pass once the dictionary-backed writer
    # has been loaded; refusing here is safer than a legacy fallback.
    result.update(_prepare_dictionary_backed_export(snapshot))
    return result


def _prepare_dictionary_backed_export(snapshot: PreparedSnapshot) -> dict[str, Any]:
    from .object_table import prepare_object_table

    prepared = prepare_object_table(snapshot)
    return prepared.preflight_result()


def _commit_export(snapshot: PreparedSnapshot, raw_input: Mapping[str, Any]) -> dict[str, Any]:
    from .object_table import publish_snapshot_run

    _prepare_export(snapshot, raw_input)
    return publish_snapshot_run(snapshot, raw_input)


def _commit_combined(
    root: Path,
    raw_input: Mapping[str, Any],
    *,
    request_id: str,
    project_uid: str,
) -> dict[str, Any]:
    """Publish a combined descriptive RUN bound one-to-one to the request.

    The request UUID is already an authenticated canonical UUIDv4 in the
    PREPARE token.  Reusing it as the combined UID makes the identity recipe
    explicit and collision resistant without introducing an unapproved UUID
    derivation.  The human ID is a reversible ASCII projection of those same
    UUID bytes.
    """

    from .combined import assert_compatible_bins, publish_combined_run

    combined = _validate_combined_input(root, raw_input)
    runs = _verify_combined_sources(
        root,
        combined,
        expected_project_uid=project_uid,
    )
    combined_run_id = "P1C_" + request_id.replace("-", "")
    combined_run_uid = request_id
    published = publish_combined_run(
        root / combined["combined_runs_relative_path"],
        combined_run_id=combined_run_id,
        combined_run_uid=combined_run_uid,
        runs=runs,
        requested_rebin=False,
        atomic_capability="UNKNOWN",
    )
    manifest = published.verified.manifest
    return {
        "result": "COMBINED_RUN_PUBLISHED",
        "combined_run_id": combined_run_id,
        "combined_run_uid": combined_run_uid,
        "identity_binding": {
            "method": "REQUEST_ID_UUIDV4_DIRECT_V1",
            "request_id": request_id,
            "project_uid": project_uid,
        },
        "relative_path": published.path.relative_to(root).as_posix(),
        "combined_manifest_sha256": published.manifest_sha256,
        "bin_contract_sha256": assert_compatible_bins(runs),
        "input_runs": [dict(record) for record in manifest["input_runs"]],
        "run_count": manifest["run_count"],
        "object_row_count": manifest["object_row_count"],
        "pooling_mode": "DESCRIPTIVE_ONLY",
        "pointer_authority": "CURRENT_RUN_TSV_V1",
        "implicit_rebin": False,
        "directory_atomic_move_capability": published.atomic_move_capability,
        "technical_preview": True,
        "scientific_validation": False,
        "functional_release": False,
    }


def _response(request: Mapping[str, Any], *, status: str, result: Any, errors: list[dict[str, Any]], warnings: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    return {
        "schema": RESPONSE_SCHEMA,
        "request_id": request.get("request_id", "NOT_AVAILABLE"),
        "operation": request.get("operation", "NOT_AVAILABLE"),
        "phase": request.get("phase", "NOT_AVAILABLE"),
        "status": status,
        "result": result,
        "errors": errors,
        "warnings": warnings or [],
    }


def handle_fiji_request(request: dict[str, Any]) -> dict[str, Any]:
    """Validate and execute one exact Fiji request without legacy fallback."""

    safe_request: Mapping[str, Any] = request if isinstance(request, Mapping) else {}
    try:
        validated, root, context, payload = _validate_request(request)
        operation = validated["operation"]
        phase = validated["phase"]
        observed, snapshot = _prepare_operation(validated, root, context, payload)
        token = _prepare_token(validated)
        if phase == "EXECUTE":
            result = {"result": "VALIDATED_READ_ONLY", **observed}
        elif phase == "PREPARE":
            result = {"result": "PREPARED", "prepare_token": token, **observed}
        else:
            if validated["prepare_token"] != token:
                raise StaleContextError("prepare token does not bind this exact request/context/input")
            if phase == "ABORT":
                result = {
                    "result": "ABORTED_WITHOUT_SCIENTIFIC_MUTATION",
                    "prepare_token": token,
                    "mutations": 0,
                    "retention_policy": "RETAIN_NO_AUTOMATIC_DELETE",
                }
            elif operation == "save_revision":
                assert snapshot is not None
                result = _commit_save(snapshot, payload["operation_input"])
            elif operation == "export_run":
                assert snapshot is not None
                result = _commit_export(snapshot, payload["operation_input"])
            elif operation == "combined_analysis":
                result = _commit_combined(
                    root,
                    payload["operation_input"],
                    request_id=validated["request_id"],
                    project_uid=context["project_uid"],
                )
            else:  # pragma: no cover - phase validation prevents validate COMMIT
                raise ValidationError("operation does not support COMMIT")
        # operator_id and absolute paths are deliberately never projected into
        # the response result.
        return _response(validated, status="PASS", result=result, errors=[])
    except Prompt1Error as exc:
        error = {"code": exc.code, "message": str(exc)}
        if exc.details:
            error["details"] = exc.details
        return _response(safe_request, status="FAIL", result=None, errors=[error])
    except Exception as exc:
        return _response(
            safe_request,
            status="FAIL",
            result=None,
            errors=[{"code": "FIJI_HANDLER_FAIL_CLOSED", "message": str(exc) or exc.__class__.__name__}],
        )
