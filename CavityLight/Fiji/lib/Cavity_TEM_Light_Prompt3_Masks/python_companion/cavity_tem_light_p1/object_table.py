"""Fail-closed writer/parser for ``CTL_CAVITY_OBJECTS_TSV_PROFILE_V1``.

The approved physical table is a 234-column contract, not a convenience CSV.
This module therefore shares one validator between publication and consumption:
the exact authoritative header is mandatory, structured cells are canonical
JSON, nullable values travel with their status sibling, and the CAVITY-only,
no-3-D scope cannot be widened by a caller or by legacy data.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
import hashlib
import json
import math
from pathlib import Path
import re
import unicodedata
import uuid
from typing import Any, Mapping, Sequence

from .canonical_json import canonical_json_bytes
from .contract import (
    CLASSIFICATION_POLICY,
    VALIDITY_UPDATE_MODE,
    cavity_objects_header,
    load_sealed_schema_dictionary,
    validate_dictionary_bound_emission,
    validate_indivisible_object_record,
)
from .errors import ContractError, ValidationError
from .identity import validate_canonical_uuid, validate_identity_provenance
from .object_table_profile import (
    COLUMN_COUNT,
    HEADER_SHA256,
    IDENTITY_PROVENANCE_ORDINAL,
    PROFILE_ID,
    PROFILE_SHA256,
    ObjectTableProfile,
    ProfileColumn,
    load_object_table_profile,
)
from .run_context import P1_RUN_CONTEXT, RunContractContext, normalize_run_context
from .path_safety import PathSafetyError, stable_plain_bytes
from .revision import VerifiedRevision, verify_revision
from .science import (
    ANISOTROPIC_AXIS_VERSION,
    BORDER_ALGORITHM_STATUS,
    BORDER_ALGORITHM_VERSION,
    CENTER_BORDER_EPSILON_PX,
    GEOMETRY_HASH_PROFILE_ID,
    SAMPLING_POLICY_VERSION,
    build_circle_geometry,
    build_contour_geometry,
    build_ellipse_geometry,
    classify_sampling,
    derive_inclusion_flags,
    sampling_axis,
    validate_geometry_authority,
    zero_event_summary,
)


_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$", re.ASCII)
_SHA_RE = re.compile(r"^[0-9a-f]{64}$", re.ASCII)
_UUID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
    re.ASCII,
)
_UTC_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{0,5}[1-9])?Z$", re.ASCII)
_INTEGER_RE = re.compile(r"^(?:0|-?[1-9][0-9]*)$", re.ASCII)
_DECIMAL_RE = re.compile(r"^-?(?:0|[1-9][0-9]*)(?:\.[0-9]*[1-9])?$", re.ASCII)
_TYPED_STATUSES = frozenset({"KNOWN", "UNKNOWN", "NOT_APPLICABLE", "NOT_MEASURED", "UNDEFINED"})
_CAVITY_PROTOCOLS = frozenset({"CAVITY_CIRCLE", "CAVITY_ELLIPSE", "CAVITY_CONTOUR"})
_STRUCTURED_SENTINELS = {
    "classification_confidence": frozenset({"UNKNOWN"}),
    "canonical_geometry": frozenset({"NOT_APPLICABLE"}),
}
_BOOLEAN_FIELDS = frozenset(
    {
        "scale_confirmed",
        "count_valid",
        "size_valid",
        "position_valid",
        "primary_count_included",
        "primary_size_included",
        "primary_position_included",
        "sensitivity_count_included",
        "sensitivity_size_included",
        "sensitivity_position_included",
        "manual_excluded",
        "center_inside_net_area",
        "touches_image_edge",
        "touches_mask_edge",
        "touches_exclusion",
        "touches_surface",
    }
)
_NO_3D_CELLS = {
    "model_3d": "NONE",
    "model_3d_status": "NOT_MODELLED",
    "third_axis_assumption": "NOT_APPLICABLE",
    "third_axis_value_nm": "",
    "third_axis_value_nm_status": "NOT_APPLICABLE",
    "model_source": "NOT_APPLICABLE",
    "model_uncertainty": "NOT_APPLICABLE",
    "modelled_volume_nm3": "",
    "modelled_volume_nm3_status": "NOT_APPLICABLE",
    "nominal_volume_fraction": "",
    "nominal_volume_fraction_status": "NOT_APPLICABLE",
    "loop_model": "NONE",
    "loop_thickness_nm": "",
    "loop_thickness_nm_status": "NOT_APPLICABLE",
    "loop_thickness_source": "NOT_APPLICABLE",
    "loop_material": "NOT_APPLICABLE",
    "loop_lattice_parameter_value_nm": "",
    "loop_lattice_parameter_value_nm_status": "NOT_APPLICABLE",
    "loop_lattice_parameter_source": "NOT_APPLICABLE",
    "loop_lattice_parameter_uncertainty_nm": "",
    "loop_lattice_parameter_uncertainty_nm_status": "NOT_APPLICABLE",
    "loop_thickness_justification": "NOT_APPLICABLE",
}


def _fail(message: str, **details: Any) -> None:
    raise ValidationError(message, details={"profile_id": PROFILE_ID, **details})


@dataclass(frozen=True)
class ParsedObjectTable:
    header: tuple[str, ...]
    rows: tuple[dict[str, str], ...]


def _profile() -> ObjectTableProfile:
    profile = load_object_table_profile()
    header = cavity_objects_header()
    if header != profile.header:
        raise ContractError(
            "runtime dictionary/header reconciliation changed after profile load",
            details={"profile_id": PROFILE_ID},
        )
    return profile


def _canonical_cell_bytes(value: Any) -> bytes:
    wrapped = canonical_json_bytes({"value": value})
    prefix = b'{"value":'
    if not wrapped.startswith(prefix) or not wrapped.endswith(b"}\n"):
        raise AssertionError("canonical JSON wrapper invariant failed")
    return wrapped[len(prefix) : -2]


def canonical_json_cell(value: Any) -> str:
    """Encode one structured cell without a terminal LF."""

    return _canonical_cell_bytes(value).decode("utf-8")


def _reject_constant(token: str) -> None:
    _fail("structured cell contains a non-finite JSON constant", token=token)


def _pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        normalized = unicodedata.normalize("NFC", key)
        if key != normalized or normalized in result:
            _fail("structured cell contains a duplicate/non-NFC JSON key", key=key)
        result[normalized] = value
    return result


def parse_canonical_json_cell(text: str, *, field: str) -> Any:
    """Parse one exact compact/sorted/NFC JSON cell and reject alternatives."""

    if not isinstance(text, str) or not text or any(character in text for character in "\t\r\n\x00"):
        _fail("structured cell is empty or contains a forbidden literal", field=field)
    try:
        value = json.loads(
            text,
            object_pairs_hook=_pairs,
            parse_float=Decimal,
            parse_int=int,
            parse_constant=_reject_constant,
        )
    except (json.JSONDecodeError, InvalidOperation, ValueError) as exc:
        _fail("structured cell is not valid JSON", field=field, error_type=type(exc).__name__)
    try:
        expected = canonical_json_cell(value)
    except ValidationError as exc:
        _fail("structured cell cannot be canonicalized", field=field, cause=str(exc))
    if expected != text:
        _fail("structured cell bytes are not canonical CTL_JSON_CELL_V1", field=field)
    return value


def _plain_decimal(value: Any, *, field: str) -> str:
    if isinstance(value, bool) or value is None:
        _fail("numeric cell requires a finite decimal", field=field)
    try:
        number = value if isinstance(value, Decimal) else Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        _fail("numeric cell is not a decimal", field=field, value=repr(value))
    if not number.is_finite() or (number.is_zero() and number.is_signed()):
        _fail("numeric cell is non-finite or negative zero", field=field)
    rendered = format(number, "f")
    if "." in rendered:
        rendered = rendered.rstrip("0").rstrip(".")
    if rendered in {"", "-", "-0"}:
        _fail("numeric cell has no canonical plain-decimal form", field=field)
    return rendered


def _encode_cell(column: ProfileColumn, value: Any) -> str:
    field = column.output_name
    if column.cell_encoding == "CTL_JSON_CELL_V1":
        sentinels = _STRUCTURED_SENTINELS.get(field, frozenset())
        if isinstance(value, str) and value in sentinels:
            return value
        if isinstance(value, str):
            parse_canonical_json_cell(value, field=field)
            return value
        return canonical_json_cell(value)
    if value is None:
        return ""
    if column.logical_type.endswith("_or_null") and value == "":
        # Parsed rows and the fixed no-3-D envelope use the physical empty-cell
        # spelling, while newly constructed typed records normally use None.
        return ""
    if column.logical_type == "boolean":
        if value is True or value == 1 or value == "1":
            return "1"
        if value is False or value == 0 or value == "0":
            return "0"
        _fail("boolean cell must be exactly 0 or 1", field=field, value=repr(value))
    if "integer" in column.logical_type and not column.logical_type.startswith("identifier"):
        rendered = _plain_decimal(value, field=field)
        if _INTEGER_RE.fullmatch(rendered) is None:
            _fail("integer cell is not canonically integral", field=field, value=rendered)
        return rendered
    if "decimal" in column.logical_type:
        return _plain_decimal(value, field=field)
    if not isinstance(value, str):
        value = str(value)
    normalized = unicodedata.normalize("NFC", value)
    if value != normalized or any(character in value for character in "\t\r\n\x00"):
        _fail("scalar cell is not NFC or contains a forbidden literal", field=field)
    return value


def _number(text: str, *, field: str, integer: bool = False) -> Decimal:
    pattern = _INTEGER_RE if integer else _DECIMAL_RE
    if pattern.fullmatch(text) is None:
        _fail("numeric cell is not canonical plain decimal", field=field, value=text)
    try:
        number = Decimal(text)
    except InvalidOperation:
        _fail("numeric cell is invalid", field=field, value=text)
    if not number.is_finite() or (number.is_zero() and number.is_signed()):
        _fail("numeric cell is non-finite or negative zero", field=field)
    if _plain_decimal(number, field=field) != text:
        _fail("numeric cell is not in unique canonical form", field=field, value=text)
    return number


def _validate_scalar_cell(column: ProfileColumn, text: str) -> None:
    field = column.output_name
    logical = column.logical_type
    if text != unicodedata.normalize("NFC", text) or any(character in text for character in "\t\r\n\x00"):
        _fail("scalar cell is not NFC or contains a forbidden literal", field=field)
    if logical == "boolean":
        if text not in {"0", "1"}:
            _fail("boolean cell must be exactly 0 or 1", field=field, value=text)
        return
    nullable = logical.endswith("_or_null")
    if nullable and text == "":
        return
    if logical in {"integer", "positive_integer", "nonnegative_integer_or_null", "positive_integer_or_null"}:
        number = _number(text, field=field, integer=True)
        if logical.startswith("positive") and number <= 0:
            _fail("positive integer cell is not positive", field=field)
        if logical.startswith("nonnegative") and number < 0:
            _fail("nonnegative integer cell is negative", field=field)
        return
    if "decimal" in logical:
        number = _number(text, field=field)
        if logical.startswith("positive") and number <= 0:
            _fail("positive decimal cell is not positive", field=field)
        if logical.startswith("nonnegative") and number < 0:
            _fail("nonnegative decimal cell is negative", field=field)
        return
    if logical == "uuid" and _UUID_RE.fullmatch(text) is None:
        _fail("UUID cell is not lowercase canonical text", field=field)
    if logical == "uuid_or_UNKNOWN" and text != "UNKNOWN" and _UUID_RE.fullmatch(text) is None:
        _fail("UUID-or-UNKNOWN cell is invalid", field=field)
    if logical in {"sha256", "sha256_or_NOT_APPLICABLE"} and (
        text != "NOT_APPLICABLE" or logical == "sha256"
    ) and _SHA_RE.fullmatch(text) is None:
        _fail("SHA-256 cell is invalid", field=field)
    if logical in {"rfc3339_utc", "rfc3339_utc_or_UNKNOWN", "rfc3339_or_UNKNOWN"} and (
        text != "UNKNOWN" or logical == "rfc3339_utc"
    ):
        if _UTC_RE.fullmatch(text) is None:
            _fail("RFC3339 UTC cell is invalid", field=field, value=text)
        base, separator, fraction = text[:-1].partition(".")
        try:
            datetime.strptime(base, "%Y-%m-%dT%H:%M:%S")
        except ValueError:
            _fail("RFC3339 UTC cell is invalid", field=field, value=text)
        if separator and (not fraction.isdigit() or len(fraction) > 6):
            _fail("RFC3339 UTC fractional second is invalid", field=field, value=text)
    if column.requirement == "REQ" and not nullable and text == "":
        _fail("required scalar cell is empty", field=field)


def _typed_row(profile: ObjectTableProfile, row: Mapping[str, str], structured: Mapping[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for column in profile.columns:
        field = column.output_name
        text = row[field]
        if field in structured:
            result[field] = structured[field]
        elif column.logical_type == "boolean":
            result[field] = int(text)
        elif column.logical_type.endswith("_or_null") and text == "":
            result[field] = None
        elif "integer" in column.logical_type and not column.logical_type.startswith("identifier"):
            result[field] = int(text)
        elif "decimal" in column.logical_type:
            result[field] = Decimal(text)
        else:
            result[field] = text
    return result


def _validate_structured_cells(row: Mapping[str, str]) -> dict[str, Any]:
    structured: dict[str, Any] = {}
    provenance = parse_canonical_json_cell(row["identity_provenance"], field="identity_provenance")
    if not isinstance(provenance, list):
        _fail("identity_provenance cell must be an array")
    structured["identity_provenance"] = provenance
    confidence = row["classification_confidence"]
    if confidence == "UNKNOWN":
        structured["classification_confidence"] = confidence
    else:
        value = parse_canonical_json_cell(confidence, field="classification_confidence")
        if not isinstance(value, dict) or not value:
            _fail("classification_confidence must be UNKNOWN or a non-empty object")
        structured["classification_confidence"] = value
    geometry = row["canonical_geometry"]
    if geometry == "NOT_APPLICABLE":
        structured["canonical_geometry"] = geometry
    else:
        value = parse_canonical_json_cell(geometry, field="canonical_geometry")
        if not isinstance(value, list) or len(value) < 3:
            _fail("canonical_geometry must be NOT_APPLICABLE or an ordered vertex array")
        structured["canonical_geometry"] = value
    partners = parse_canonical_json_cell(row["duplicate_partners"], field="duplicate_partners")
    if not isinstance(partners, list) or any(not isinstance(value, str) for value in partners):
        _fail("duplicate_partners must be an array of object UUID strings")
    if partners != sorted(set(partners)):
        _fail("duplicate_partners must be sorted and unique")
    for value in partners:
        validate_canonical_uuid(value)
    if row["object_uuid"] in partners:
        _fail("duplicate_partners cannot contain the row object_uuid")
    structured["duplicate_partners"] = partners
    return structured


def _validate_pairs(profile: ObjectTableProfile, row: Mapping[str, str]) -> None:
    by_name = {column.output_name: column for column in profile.columns}
    for column in profile.columns:
        if not column.logical_type.endswith("_or_null"):
            continue
        field = column.output_name
        status_field = f"{field}_status"
        status = row[status_field]
        if status not in _TYPED_STATUSES:
            _fail("typed status is invalid", field=status_field, value=status)
        present = row[field] != ""
        if (status == "KNOWN") != present:
            _fail(
                "nullable value/status pair is not indivisible",
                field=field,
                status=status,
                value_present=present,
            )
        if status_field not in by_name:
            raise AssertionError("profile loader should have rejected missing status sibling")


def _validate_row(
    profile: ObjectTableProfile,
    row: dict[str, str],
    *,
    row_number: int,
    manifest: Mapping[str, Any] | None,
    run_context: RunContractContext | None,
) -> dict[str, Any]:
    context = normalize_run_context(run_context)
    for column in profile.columns:
        if column.cell_encoding == "CTL_SCALAR_CELL_V1":
            _validate_scalar_cell(column, row[column.output_name])
    _validate_pairs(profile, row)
    dictionary_record = {name: row[name] for name in profile.field_entities}
    for field, expected in context.object_table_overlay.items():
        if row[field] != str(expected):
            _fail(
                "object-table context overlay differs from selected RUN authority",
                row=row_number,
                field=field,
                expected=str(expected),
                actual=row[field],
            )
    if context.is_native_schema2:
        # CTL_RUN_V2_SCHEMA2_NATIVE_ADAPTER_V1 is an overlay of physical
        # columns 1--4 only.  All remaining columns retain the sealed P1
        # dictionary validation unchanged.
        for field, legacy_value in P1_RUN_CONTEXT.object_table_overlay.items():
            dictionary_record[field] = str(legacy_value)
    try:
        validate_dictionary_bound_emission(
            dictionary_record,
            profile.field_entities,
            dictionary=load_sealed_schema_dictionary(),
            tsv=True,
        )
    except ValidationError as exc:
        _fail("row violates its sealed dictionary bindings", row=row_number, cause=str(exc), cause_details=exc.details)
    structured = _validate_structured_cells(row)
    typed = _typed_row(profile, row, structured)
    if context.is_native_schema2:
        expected_owner = {
            "project_uid": context.project_uid,
            "image_uid": context.image_uid,
            "analysis_session_id": context.analysis_session_id,
            "analysis_session_uid": context.analysis_session_uid,
        }
        for field, expected_value in expected_owner.items():
            if expected_value is not None and typed[field] != expected_value:
                _fail(
                    "object-table row differs from verified physical session owner",
                    row=row_number,
                    field=field,
                    expected=expected_value,
                    actual=typed[field],
                )
    if typed["defect_type"] != "CAVITY" or typed["measurement_protocol"] not in _CAVITY_PROTOCOLS:
        _fail("row widens the approved CAVITY protocol scope", row=row_number)
    for field, expected in _NO_3D_CELLS.items():
        if row[field] != expected:
            _fail("row attempts a 3-D model outside the approved scope", row=row_number, field=field)
    candidate_rows = [item for item in structured["identity_provenance"] if isinstance(item, Mapping) and item.get("entity_type") == "candidate"]
    candidate_uid = "UNKNOWN"
    if typed["candidate_id"] != "NOT_APPLICABLE":
        if len(candidate_rows) != 1:
            _fail("candidate trace requires exactly one candidate identity row", row=row_number)
        candidate_uid = candidate_rows[0].get("uid_value")
        validate_canonical_uuid(candidate_uid, expected_version=4)
        if candidate_uid == typed["object_uuid"] or typed["review_status"] != "reviewed":
            _fail("candidate-derived object requires a distinct candidate and an explicit review", row=row_number)
        if typed["view_id"] == "NOT_APPLICABLE" or typed["proposed_geometry_sha256"] == "NOT_APPLICABLE":
            _fail("candidate-derived object lacks its view/geometry provenance", row=row_number)
    owner_uids = {
        "project": typed["project_uid"],
        "study": typed["study_uid"],
        "specimen": typed["specimen_uid"],
        "lamella": typed["lamella_uid"],
        "image": typed["image_uid"],
        "analysis_session": typed["analysis_session_uid"],
        "revision": typed["revision_uid"],
        "run": typed["run_uid"],
        "object": typed["object_uuid"],
        "candidate": candidate_uid,
    }
    try:
        validate_identity_provenance(structured["identity_provenance"], owner_uids)
        validate_indivisible_object_record(typed)
        validate_geometry_authority(typed)
    except ValidationError as exc:
        _fail("row semantic envelope is invalid", row=row_number, cause=str(exc), cause_details=exc.details)
    if typed["review_status"] == "pending" and any(
        typed[field] != 0
        for field in (
            "primary_count_included",
            "primary_size_included",
            "primary_position_included",
            "sensitivity_count_included",
            "sensitivity_size_included",
            "sensitivity_position_included",
        )
    ):
        _fail("pending row may not enter an estimand", row=row_number)
    if manifest is not None:
        for field in (
            "project_uid",
            "image_uid",
            "analysis_session_uid",
            "revision_uid",
            "run_uid",
            "run_id",
            "revision_id",
            "source_sha256",
            "master_pixel_sha256",
            "roi_zip_sha256",
            "revision_manifest_sha256",
        ):
            if str(row[field]) != str(manifest.get(field)):
                _fail("row binding differs from RUN manifest", row=row_number, field=field)
    return typed


def parse_object_table_bytes(
    data: bytes,
    *,
    manifest: Mapping[str, Any] | None = None,
    run_context: RunContractContext | None = None,
) -> ParsedObjectTable:
    """Parse exact table bytes; there is no legacy/subset-header mode."""

    context = normalize_run_context(run_context)
    if manifest is not None:
        try:
            context.validate_manifest_owner(manifest)
        except ValidationError as exc:
            _fail(
                "RUN manifest differs from selected object-table context",
                cause_code=exc.code,
                cause_message=str(exc),
                cause_details=exc.details,
            )
    if not isinstance(data, bytes):
        _fail("cavity_objects.tsv input must be bytes")
    profile = _profile()
    if data.startswith(b"\xef\xbb\xbf") or b"\r" in data or not data.endswith(b"\n"):
        _fail("cavity_objects.tsv must be UTF-8 without BOM/CR and with exact final LF")
    if not data.startswith(profile.header_bytes):
        observed = data.split(b"\n", 1)[0] + b"\n" if b"\n" in data else data
        _fail(
            "cavity_objects.tsv header bytes differ from the approved 234-column authority",
            expected_sha256=HEADER_SHA256,
            observed_sha256=hashlib.sha256(observed).hexdigest(),
        )
    if data == profile.header_bytes:
        if manifest is not None and any(int(manifest.get(field, -1)) != 0 for field in ("N_count_valid", "N_size_valid", "N_position_valid")):
            _fail("header-only N=0 table disagrees with RUN counters")
        return ParsedObjectTable(profile.header, ())
    body = data[len(profile.header_bytes) :]
    if not body or body.endswith(b"\n\n"):
        _fail("object table contains a blank row or more than one terminal LF")
    try:
        text = body.decode("utf-8", errors="strict")
    except UnicodeDecodeError as exc:
        _fail("object table row bytes are not UTF-8", offset=exc.start)
    raw_lines = text[:-1].split("\n")
    rows: list[dict[str, str]] = []
    typed_rows: list[dict[str, Any]] = []
    seen_objects: set[str] = set()
    seen_cavities: set[str] = set()
    for row_number, line in enumerate(raw_lines, start=2):
        if line == "":
            _fail("object table contains a blank data row", row=row_number)
        values = line.split("\t")
        if len(values) != COLUMN_COUNT:
            _fail(
                "object table row width differs from the exact profile",
                row=row_number,
                expected=COLUMN_COUNT,
                observed=len(values),
            )
        row = dict(zip(profile.header, values))
        object_uuid = row["object_uuid"]
        cavity_id = row["cavity_id"]
        if object_uuid in seen_objects or cavity_id in seen_cavities:
            _fail("object_uuid/cavity_id is duplicated", row=row_number)
        seen_objects.add(object_uuid)
        seen_cavities.add(cavity_id)
        typed_rows.append(
            _validate_row(
                profile,
                row,
                row_number=row_number,
                manifest=manifest,
                run_context=context,
            )
        )
        rows.append(row)
    if manifest is not None:
        reconciled = {
            "N_count_valid": sum(row["count_valid"] for row in typed_rows),
            "N_size_valid": sum(row["size_valid"] for row in typed_rows),
            "N_position_valid": sum(row["position_valid"] for row in typed_rows),
        }
        for field, count in reconciled.items():
            if count != int(manifest.get(field, -1)):
                _fail("object table counter differs from RUN manifest", field=field, table=count)
        if reconciled["N_count_valid"] == 0:
            _fail("approved zero-event encoding is header-only; data rows with N_count_valid=0 are forbidden")
        sizes = [row["equivalent_diameter_nm"] for row in typed_rows if row["size_valid"] == 1]
        if sizes:
            expected_mean = sum(sizes, Decimal(0)) / Decimal(len(sizes))
            try:
                observed_mean = Decimal(str(manifest.get("mean_size_nm")))
            except InvalidOperation:
                _fail("RUN mean_size_nm is not decimal")
            tolerance = max(Decimal("1e-24"), abs(expected_mean) * Decimal("1e-12"))
            if abs(observed_mean - expected_mean) > tolerance:
                _fail("RUN mean_size_nm differs from object rows")
    return ParsedObjectTable(profile.header, tuple(rows))


def render_object_table(
    records: Sequence[Mapping[str, Any]],
    *,
    manifest: Mapping[str, Any] | None = None,
    run_context: RunContractContext | None = None,
) -> bytes:
    """Render whole records; parallel column arrays are intentionally unsupported."""

    context = normalize_run_context(run_context)
    if isinstance(records, (str, bytes)) or not isinstance(records, Sequence):
        _fail("object table records must be a sequence of mappings")
    profile = _profile()
    lines: list[str] = []
    expected = set(profile.header)
    for index, source in enumerate(records, start=2):
        if not isinstance(source, Mapping):
            _fail("object table record is not a mapping", row=index)
        missing = sorted(expected - set(source))
        extra = sorted(set(source) - expected)
        if missing or extra:
            _fail("object table record fields are not exact", row=index, missing=missing, extra=extra)
        record = dict(source)
        if context.is_native_schema2:
            # The adapter owns these four cells; accepting their values from
            # an unverified record would let a row choose its own contract.
            record.update(context.object_table_overlay)
        lines.append("\t".join(_encode_cell(column, record[column.output_name]) for column in profile.columns))
    payload = profile.header_bytes + (("\n".join(lines) + "\n").encode("utf-8") if lines else b"")
    parse_object_table_bytes(
        payload,
        manifest=manifest,
        run_context=context,
    )
    return payload


def _utc_now_z() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _entry_properties(entry: Any) -> dict[str, str]:
    properties = getattr(entry, "properties", None)
    if not isinstance(properties, Mapping):
        _fail("ROI entry has no parsed property mapping")
    folded: dict[str, str] = {}
    for raw_key, raw_value in properties.items():
        if not isinstance(raw_key, str) or not isinstance(raw_value, str):
            _fail("ROI properties must be string pairs")
        key = raw_key.casefold()
        if key in folded:
            _fail("ROI properties collide case-insensitively", key=raw_key)
        folded[key] = raw_value
    return folded


def _prop(entry: Any, *names: str, default: str | None = None) -> str | None:
    properties = _entry_properties(entry)
    matches = [properties[name.casefold()] for name in names if name.casefold() in properties]
    if len(set(matches)) > 1:
        _fail("ROI property aliases disagree", aliases=list(names))
    return matches[0] if matches else default


def _roi_type(entry: Any) -> str:
    value = _prop(entry, "Type", "Object_type", default="")
    return str(value).strip().casefold()


def _optional_number(entry: Any, *names: str) -> Decimal | None:
    raw = _prop(entry, *names, default="")
    if raw is None or raw.strip() in {"", "NaN", "nan", "N/A", "NOT_APPLICABLE"}:
        return None
    try:
        value = Decimal(raw.strip())
    except InvalidOperation:
        _fail("ROI numeric property is invalid", aliases=list(names), value=raw)
    if not value.is_finite() or (value.is_zero() and value.is_signed()):
        _fail("ROI numeric property is non-finite or negative zero", aliases=list(names), value=raw)
    return value


def _required_number(entry: Any, *names: str, positive: bool = False) -> Decimal:
    value = _optional_number(entry, *names)
    if value is None:
        _fail("required ROI numeric property is absent", aliases=list(names))
    if positive and value <= 0:
        _fail("required ROI numeric property is not positive", aliases=list(names))
    return value


def _flag(entry: Any, *names: str, default: int | None = None) -> int:
    raw = _prop(entry, *names, default=None)
    if raw is None:
        if default is None:
            _fail("required ROI boolean property is absent", aliases=list(names))
        return default
    if raw not in {"0", "1"}:
        _fail("ROI boolean property must be exactly 0 or 1", aliases=list(names), value=raw)
    return int(raw)


def _timestamp_from_milliseconds(raw: str | None) -> str:
    if raw is None or raw.strip() in {"", "NaN", "nan", "NOT_APPLICABLE"}:
        return "UNKNOWN"
    try:
        milliseconds = Decimal(raw.strip())
        if not milliseconds.is_finite() or milliseconds != milliseconds.to_integral_value() or milliseconds < 0:
            raise InvalidOperation
        stamp = datetime.fromtimestamp(float(milliseconds / 1000), tz=timezone.utc)
    except (InvalidOperation, ValueError, OSError, OverflowError):
        _fail("ROI millisecond timestamp is invalid", value=raw)
    return stamp.strftime("%Y-%m-%dT%H:%M:%SZ")


def _uuid_method(value: str, *, prefer_random: bool) -> str:
    validate_canonical_uuid(value)
    parsed = uuid.UUID(value)
    return "UUIDV4_RANDOM" if prefer_random and parsed.version == 4 else "PRESERVED"


def _provenance_row(
    *,
    ordinal: int,
    entity_type: str,
    uid_field: str,
    uid_value: str,
    method: str,
    recorded_at: str,
) -> dict[str, str]:
    common = {
        "owner_entity_key": f"{ordinal:02d}-{entity_type}",
        "coverage_map_version": "IDENTITY_PROVENANCE_COVERAGE_V1",
        "entity_type": entity_type,
        "uid_field": uid_field,
        "uid_value": uid_value,
        "uuid_generation_method": method,
        "recorded_at": recorded_at,
    }
    if method == "NOT_ASSIGNED_UNKNOWN":
        recipe = {
            "uuid_namespace_version": "NOT_APPLICABLE",
            "uuid_namespace_uuid": "NOT_APPLICABLE",
            "uuid_name_template_id": "NOT_APPLICABLE",
            "uuid_name_utf8_sha256": "NOT_APPLICABLE",
            "source_identity_evidence_sha256": "NOT_APPLICABLE",
        }
    elif method == "UUIDV4_RANDOM":
        recipe = {
            "uuid_namespace_version": "NOT_APPLICABLE",
            "uuid_namespace_uuid": "NOT_APPLICABLE",
            "uuid_name_template_id": "NOT_APPLICABLE",
            "uuid_name_utf8_sha256": "NOT_APPLICABLE",
            "source_identity_evidence_sha256": "NOT_APPLICABLE",
        }
    elif method == "PRESERVED":
        recipe = {
            "uuid_namespace_version": "NOT_APPLICABLE",
            "uuid_namespace_uuid": "NOT_APPLICABLE",
            "uuid_name_template_id": "NOT_APPLICABLE",
            "uuid_name_utf8_sha256": "NOT_APPLICABLE",
            "source_identity_evidence_sha256": _sha256_text(f"{entity_type}\0{uid_field}\0{uid_value}"),
        }
    else:
        _fail("unsupported runtime provenance method", method=method)
    return {**common, **recipe}


def _identity_provenance(
    *,
    snapshot: Any,
    object_uuid: str,
    object_method: str,
    run_uid: str,
    recorded_at: str,
    candidate_uuid: str | None = None,
) -> list[dict[str, str]]:
    context = snapshot.context
    values = (
        (1, "project", "project_uid", context["project_uid"], "PRESERVED"),
        (2, "study", "study_uid", "UNKNOWN", "NOT_ASSIGNED_UNKNOWN"),
        (3, "specimen", "specimen_uid", "UNKNOWN", "NOT_ASSIGNED_UNKNOWN"),
        (4, "lamella", "lamella_uid", "UNKNOWN", "NOT_ASSIGNED_UNKNOWN"),
        (5, "image", "image_uid", context["image_uid"], "PRESERVED"),
        (6, "analysis_session", "analysis_session_uid", context["analysis_session_uid"], "PRESERVED"),
        (7, "revision", "revision_uid", context["revision_uid"], _uuid_method(context["revision_uid"], prefer_random=True)),
        (8, "run", "run_uid", run_uid, _uuid_method(run_uid, prefer_random=True)),
        (9, "object", "object_uuid", object_uuid, object_method),
        (10, "candidate", "candidate_uuid", candidate_uuid or "UNKNOWN", "PRESERVED" if candidate_uuid else "NOT_ASSIGNED_UNKNOWN"),
    )
    return [
        _provenance_row(
            ordinal=ordinal,
            entity_type=entity_type,
            uid_field=uid_field,
            uid_value=uid_value,
            method=method,
            recorded_at=recorded_at,
        )
        for ordinal, entity_type, uid_field, uid_value, method in values
    ]


def _normalise_scale_origin(raw: str) -> str:
    exact = raw.strip().upper()
    if exact in {
        "BIOFORMATS_METADATA_CONFIRMED",
        "MANUAL_XY_REFERENCE",
        "MANUAL_LINE_REFERENCE",
        "IMPORTED_LEGACY",
        "OTHER",
        "UNKNOWN",
    }:
        # The operation snapshot does not carry complete line/XY evidence.  A
        # legacy scale already verified by the master preflight is represented
        # honestly as imported rather than inventing missing calibration rows.
        if exact in {"MANUAL_XY_REFERENCE", "MANUAL_LINE_REFERENCE"}:
            return "IMPORTED_LEGACY"
        return exact
    return "IMPORTED_LEGACY"


def _geometry(entry: Any, snapshot: Any) -> dict[str, Any]:
    sx = Decimal(str(snapshot.image["scale_x_nm_px"]))
    sy = Decimal(str(snapshot.image["scale_y_nm_px"]))
    bounds = entry.bounds
    center_px_x = Decimal(str(bounds["x_px"])) + Decimal(str(bounds["width_px"])) / 2
    center_px_y = Decimal(str(bounds["y_px"])) + Decimal(str(bounds["height_px"])) / 2
    center_nm_x = _required_number(entry, "Center_x_nm", "center_x_nm")
    center_nm_y = _required_number(entry, "Center_y_nm", "center_y_nm")
    if not math.isclose(float(center_nm_x / sx), float(center_px_x), rel_tol=1e-9, abs_tol=1e-6):
        _fail("ROI center_x nm/px evidence disagrees with the verified X scale")
    if not math.isclose(float(center_nm_y / sy), float(center_px_y), rel_tol=1e-9, abs_tol=1e-6):
        _fail("ROI center_y nm/px evidence disagrees with the verified Y scale")
    raw_kind = str(_prop(entry, "Geometry_kind", "geometry_kind", default="")).strip().casefold()
    if raw_kind in {"circle", "cavity_circle"}:
        diameter = _required_number(entry, "Diameter_nm", "Equivalent_diameter_nm", positive=True)
        result = build_circle_geometry(
            center_x_nm=center_nm_x,
            center_y_nm=center_nm_y,
            diameter_nm=diameter,
            center_method_id="ROI_CENTER_DECLARED_V1",
            scale_x_nm_px=sx,
            scale_y_nm_px=sy,
            coordinate_origin_x_nm=0,
            coordinate_origin_y_nm=0,
        )
    elif raw_kind in {"ellipse", "cavity_ellipse"}:
        major = _required_number(entry, "Major_axis_nm", "major_diameter_nm", positive=True)
        minor = _required_number(entry, "Minor_axis_nm", "minor_diameter_nm", positive=True)
        orientation = _optional_number(entry, "Orientation_deg", "orientation_deg")
        if orientation is None:
            if str(getattr(entry, "imagej_roi_type", "")).casefold() not in {"oval", "ellipse"}:
                _fail("ellipse orientation is absent for a non-axis-aligned ImageJ ROI")
            orientation = Decimal(0)
        result = build_ellipse_geometry(
            center_x_nm=center_nm_x,
            center_y_nm=center_nm_y,
            major_diameter_nm=major,
            minor_diameter_nm=minor,
            orientation_deg=orientation,
            center_method_id="ROI_CENTER_DECLARED_V1",
            scale_x_nm_px=sx,
            scale_y_nm_px=sy,
            coordinate_origin_x_nm=0,
            coordinate_origin_y_nm=0,
        )
    elif raw_kind in {"contour", "manual_contour", "cavity_contour"}:
        center_method = _prop(entry, "Center_method_id", "center_method_id", default="")
        contour_method = _prop(entry, "Contour_derivation_method_id", "contour_derivation_method_id", default="")
        if not center_method or not contour_method:
            _fail("contour export requires explicit center and contour derivation method IDs")
        if len(entry.x_coordinates) != len(entry.y_coordinates) or len(entry.x_coordinates) < 3:
            _fail("contour ROI lacks at least three paired vertices")
        vertices = [
            {"x_nm": Decimal(str(x)) * sx, "y_nm": Decimal(str(y)) * sy}
            for x, y in zip(entry.x_coordinates, entry.y_coordinates)
        ]
        result = build_contour_geometry(
            canonical_geometry=vertices,
            center_x_nm=center_nm_x,
            center_y_nm=center_nm_y,
            center_method_id=center_method,
            contour_derivation_method_id=contour_method,
            scale_x_nm_px=sx,
            scale_y_nm_px=sy,
            coordinate_origin_x_nm=0,
            coordinate_origin_y_nm=0,
        )
    else:
        _fail("cavity ROI has no approved measurement protocol", geometry_kind=raw_kind)
    observed_x = _optional_number(entry, "Center_x_px", "center_x_px")
    observed_y = _optional_number(entry, "Center_y_px", "center_y_px")
    for field, observed in (("center_x_px", observed_x), ("center_y_px", observed_y)):
        if observed is not None and not math.isclose(
            float(observed), float(result[field]), rel_tol=1e-9, abs_tol=1e-6
        ):
            _fail("legacy pixel center disagrees with protocol-aware derivation", field=field)
    return result


def _polygon_area_nm2(entry: Any, sx: Decimal, sy: Decimal) -> Decimal:
    if len(entry.x_coordinates) >= 3 and len(entry.x_coordinates) == len(entry.y_coordinates):
        points = [
            (Decimal(str(x)) * sx, Decimal(str(y)) * sy)
            for x, y in zip(entry.x_coordinates, entry.y_coordinates)
        ]
        twice = sum(
            points[index][0] * points[(index + 1) % len(points)][1]
            - points[(index + 1) % len(points)][0] * points[index][1]
            for index in range(len(points))
        )
        area = abs(twice) / 2
    else:
        area = Decimal(str(entry.bounds["width_px"])) * sx * Decimal(str(entry.bounds["height_px"])) * sy
    if not area.is_finite() or area <= 0:
        _fail("analysis-region geometry has non-positive area")
    return area


def _net_area_nm2(snapshot: Any) -> Decimal:
    sx = Decimal(str(snapshot.image["scale_x_nm_px"]))
    sy = Decimal(str(snapshot.image["scale_y_nm_px"]))
    exclusions = [entry for entry in snapshot.roi_entries if _roi_type(entry) == "exclusion"]
    if exclusions:
        _fail("net-area union/subtraction with exclusion ROIs is not closed in Prompt 1")
    if snapshot.analysis["use_whole_image"] == 1:
        area = Decimal(snapshot.image["width_px"]) * sx * Decimal(snapshot.image["height_px"]) * sy
    else:
        masks = [entry for entry in snapshot.roi_entries if _roi_type(entry) == "analysis_mask"]
        if len(masks) != 1:
            _fail("non-whole-image export requires exactly one auditable analysis_mask ROI")
        area = _polygon_area_nm2(masks[0], sx, sy)
    if not area.is_finite() or area <= 0:
        _fail("net analysis area is not positive and finite")
    return area


def _revision_for_snapshot(snapshot: Any) -> VerifiedRevision:
    revision_path = snapshot.image_directory / "roi_sessions" / f"REV_{snapshot.context['revision_id']}"
    verified = verify_revision(revision_path, source_path=snapshot.source_path)
    bindings = {
        "project_uid": snapshot.context["project_uid"],
        "image_uid": snapshot.context["image_uid"],
        "analysis_session_uid": snapshot.context["analysis_session_uid"],
        "revision_id": snapshot.context["revision_id"],
        "revision_uid": snapshot.context["revision_uid"],
        "source_sha256": snapshot.context["source_sha256"],
        "master_pixel_sha256": snapshot.context["master_pixel_sha256"],
    }
    for field, expected in bindings.items():
        if str(verified.manifest.get(field)) != str(expected):
            _fail("published revision binding differs from export snapshot", field=field)
    snapshot_roi_hash = hashlib.sha256(snapshot.roi_zip_bytes).hexdigest()
    if snapshot_roi_hash != verified.manifest["roi_zip_sha256"]:
        _fail(
            "live ROI snapshot differs from the immutable published revision",
            expected=verified.manifest["roi_zip_sha256"],
            observed=snapshot_roi_hash,
        )
    return verified


def _duplicate_partners(entry: Any, by_cavity: Mapping[str, str]) -> list[str]:
    raw = str(_prop(entry, "Duplicate_partners", "duplicate_partners", default="")).strip()
    if not raw:
        return []
    tokens = [token.strip() for token in re.split(r"[;,]", raw) if token.strip()]
    values: list[str] = []
    for token in tokens:
        if token in by_cavity:
            values.append(by_cavity[token])
        elif _UUID_RE.fullmatch(token):
            validate_canonical_uuid(token)
            values.append(token)
        else:
            _fail("legacy duplicate partner cannot be resolved to object_uuid", partner=token)
    if len(values) != len(set(values)):
        _fail("duplicate partner evidence contains duplicates")
    return sorted(values)


def _confidence(entry: Any) -> str | dict[str, str]:
    raw = str(_prop(entry, "Cavity_confidence", "classification_confidence", default="")).strip()
    if not raw or raw.upper() == "UNKNOWN":
        return "UNKNOWN"
    return {
        "interpretation_status": "NOT_INTERPRETED_OD_06_OPEN",
        "kind": "LEGACY_RAW",
        "raw": raw,
        "source": "Fiji ROI property Cavity_confidence",
    }


def _duplicate_status(entry: Any) -> str:
    raw = str(_prop(entry, "Duplicate_status", "duplicate_status", default="UNKNOWN")).strip().casefold()
    aliases = {
        "clear": "none",
        "none": "none",
        "suspect": "suspected",
        "suspected": "suspected",
        "confirmed": "confirmed",
        "pending_recheck": "pending_recheck",
        "unknown": "UNKNOWN",
    }
    if raw not in aliases:
        _fail("duplicate status is outside the closed vocabulary", value=raw)
    return aliases[raw]


def _measurement_source(entry: Any) -> str:
    raw = str(_prop(entry, "Measurement_source", "measurement_source", default="")).strip().casefold()
    if not raw:
        _fail("cavity measurement_source is absent")
    if raw in {"manual", "algorithmic_proposal", "algorithmic_refined", "imported_legacy"}:
        return raw
    if "algorithm" in raw or "auto" in raw:
        return "algorithmic_refined" if "refin" in raw else "algorithmic_proposal"
    if "import" in raw or "legacy" in raw:
        return "imported_legacy"
    return "manual"


def _typed_optional(value: Decimal | None, *, unavailable: str) -> tuple[Decimal | None, str]:
    return (value, "KNOWN") if value is not None else (None, unavailable)


def _object_record(
    *,
    prepared: "PreparedObjectTable",
    entry: Any,
    geometry: Mapping[str, Any],
    primary_protocol: str,
    run_id: str,
    run_uid: str,
    analysis_at: str,
    by_cavity: Mapping[str, str],
) -> dict[str, Any]:
    snapshot = prepared.snapshot
    context = snapshot.context
    revision = prepared.revision
    profile = prepared.profile
    cavity_id = str(_prop(entry, "Cavity_id", "cavity_id", default=""))
    object_uuid = str(_prop(entry, "Object_uuid", "object_uuid", default=""))
    if not re.fullmatch(r"CAV_[0-9]{6}", cavity_id):
        _fail("cavity ROI lacks a canonical CAV_000001 identifier", cavity_id=cavity_id)
    validate_canonical_uuid(object_uuid)
    declared_object_method = str(_prop(entry, "Object_uuid_generation_method", default="")).strip()
    object_method = (
        "UUIDV4_RANDOM"
        if declared_object_method == "UUIDV4_RANDOM" and uuid.UUID(object_uuid).version == 4
        else "PRESERVED"
    )
    object_template = "NOT_APPLICABLE"
    legacy_component = (
        context["analysis_session_id"]
        if context["analysis_session_id"].startswith("LEGACY_SESSION_")
        else "NOT_APPLICABLE"
    )
    legacy_origin = "PRESERVED_LEGACY" if legacy_component != "NOT_APPLICABLE" else "NOT_APPLICABLE"
    specimen_id = str(_prop(entry, "Specimen_id", default="UNKNOWN") or "UNKNOWN")
    specimen_label = str(_prop(entry, "Specimen_label", "Sample_name", default="UNKNOWN") or "UNKNOWN")
    condition_label = str(_prop(entry, "Condition_label", "Experimental_condition", default="UNKNOWN") or "UNKNOWN")
    condition_id = str(_prop(entry, "Condition_id", default="UNKNOWN") or "UNKNOWN")
    if specimen_id != "UNKNOWN" and _ID_RE.fullmatch(specimen_id) is None:
        _fail("specimen_id from ROI is not a canonical identifier", specimen_id=specimen_id)
    if condition_id != "UNKNOWN" and _ID_RE.fullmatch(condition_id) is None:
        _fail("condition_id from ROI is not a canonical identifier", condition_id=condition_id)
    scale_origin = _normalise_scale_origin(str(snapshot.payload["scale_method"]))
    thickness = snapshot.analysis["thickness_nm"]
    thickness_status = snapshot.analysis["thickness_status"]
    if thickness_status == "KNOWN" and thickness is None:
        _fail("KNOWN thickness is absent")
    surface_active = snapshot.analysis["image_mode"] == "with_surface"
    surface_id = "SURFACE_001" if surface_active else "NOT_APPLICABLE"
    geometry_protocol = str(geometry["measurement_protocol"])
    sampling = sampling_axis(
        geometry_protocol,
        scale_x_nm_px=snapshot.image["scale_x_nm_px"],
        scale_y_nm_px=snapshot.image["scale_y_nm_px"],
        diameter_nm=geometry.get("diameter_nm"),
        minor_diameter_nm=geometry.get("minor_diameter_nm"),
        major_orientation_deg=geometry.get("orientation_deg"),
        feret_min_nm=geometry.get("feret_min_nm"),
        feret_min_orientation_deg=geometry.get("feret_min_orientation_deg"),
    )
    sampling_class = classify_sampling(sampling["axis_length_px"])
    cavity_class = str(_prop(entry, "Cavity_class", "cavity_class", default="")).strip().casefold()
    if cavity_class not in {"confirmed", "uncertain", "possible_artifact", "rejected", "pending"}:
        _fail("cavity class is outside the closed vocabulary", value=cavity_class)
    review_status = str(_prop(entry, "Review_status", "review_status", default="imported_unreviewed")).strip()
    if review_status not in {"pending", "reviewed", "imported_unreviewed", "NOT_APPLICABLE"}:
        _fail("review_status is outside the closed vocabulary", value=review_status)
    validity = {
        "count_valid": _flag(entry, "Count_valid", "count_valid"),
        "size_valid": _flag(entry, "Size_valid", "size_valid"),
        "position_valid": _flag(entry, "Position_valid", "position_valid"),
    }
    if review_status == "pending" and any(validity.values()):
        _fail("pending cavity has nonzero endpoint validity; review is required before export", cavity_id=cavity_id)
    inclusions = derive_inclusion_flags({"cavity_class": cavity_class, **validity})
    manual_excluded = _flag(entry, "Manual_excluded", "manual_excluded", default=0)
    exclusion_reason_raw = str(_prop(entry, "Exclusion_reason", "exclusion_reason", default="")).strip()
    exclusion_reason = exclusion_reason_raw or "NOT_APPLICABLE"
    center_inside = _flag(entry, "Inside_analysis_mask", "center_inside_net_area", default=validity["position_valid"])
    x = Decimal(str(entry.bounds["x_px"]))
    y = Decimal(str(entry.bounds["y_px"]))
    width = Decimal(str(entry.bounds["width_px"]))
    height = Decimal(str(entry.bounds["height_px"]))
    touches_image = int(
        x <= 0
        or y <= 0
        or x + width >= snapshot.image["width_px"]
        or y + height >= snapshot.image["height_px"]
    )
    edge_intersecting = _flag(entry, "Edge_intersecting", default=0)
    touches_mask = int(edge_intersecting == 1 and touches_image == 0)
    duplicate_partners = _duplicate_partners(entry, by_cavity)
    signed = _optional_number(entry, "Signed_depth_nm", "signed_depth_nm")
    absolute = _optional_number(entry, "Depth_absolute_nm", "absolute_depth_nm")
    depth_absence = "NOT_MEASURED" if surface_active else "NOT_APPLICABLE"
    signed_value, signed_status = _typed_optional(signed, unavailable=depth_absence)
    absolute_value, absolute_status = _typed_optional(absolute, unavailable=depth_absence)
    if absolute_value is not None and absolute_value < 0:
        _fail("absolute_depth_nm cannot be negative")
    depth_bin = Decimal(str(snapshot.analysis["feature_distance_bin_nm"]))
    if signed_value is not None:
        bin_coordinate = absolute_value if absolute_value is not None else abs(signed_value)
        depth_index = int(bin_coordinate // depth_bin)
        depth_low = Decimal(depth_index) * depth_bin
        depth_high = Decimal(depth_index + 1) * depth_bin
        depth_status = "KNOWN"
    else:
        depth_index = depth_low = depth_high = None
        depth_status = depth_absence
    distances: dict[str, tuple[Decimal | None, str]] = {}
    for field, aliases in {
        "distance_to_grain_boundary_nm": ("Distance_to_grain_boundary_nm", "distance_to_grain_boundary_nm"),
        "distance_to_dislocation_nm": ("Distance_to_dislocation_nm", "distance_to_dislocation_nm"),
        "distance_to_interface_nm": ("Distance_to_interface_nm", "distance_to_interface_nm"),
    }.items():
        value = _optional_number(entry, *aliases)
        if value is not None and value < 0:
            _fail("feature distance cannot be negative", field=field)
        distances[field] = _typed_optional(value, unavailable="NOT_MEASURED")
    created_at = _timestamp_from_milliseconds(_prop(entry, "Created_time_ms", "created_time_ms"))
    modified_at = _timestamp_from_milliseconds(_prop(entry, "Modified_time_ms", "Last_edit_ms", "last_edit_ms"))
    last_edit_raw = str(_prop(entry, "Last_edit_method", "last_edit_method", default="manual")).strip()
    if not last_edit_raw:
        last_edit_raw = "manual"
    source_scale_status = "KNOWN" if scale_origin == "BIOFORMATS_METADATA_CONFIRMED" else "UNKNOWN"
    source_scale_x = snapshot.image["scale_x_nm_px"] if source_scale_status == "KNOWN" else None
    source_scale_y = snapshot.image["scale_y_nm_px"] if source_scale_status == "KNOWN" else None
    # This private adapter field is populated from the verified P2 revision,
    # never from user-editable ROI properties in the legacy P1 entry path.
    candidate_trace = getattr(entry, "candidate_trace", None)
    provenance = _identity_provenance(
        snapshot=snapshot,
        object_uuid=object_uuid,
        object_method=object_method,
        run_uid=run_uid,
        recorded_at=analysis_at,
        candidate_uuid=None if candidate_trace is None else candidate_trace["candidate_uuid"],
    )
    record: dict[str, Any] = {
        "project_schema_version": 1,
        "run_contract_version": 2,
        "source_project_schema_version": 1,
        "session_model_status": "LEGACY_SINGLE_SESSION_BRIDGE",
        "project_id": context["project_id"],
        "project_uid": context["project_uid"],
        "project_uid_generation_method": "PRESERVED",
        "project_uid_name_template_id": "NOT_APPLICABLE",
        "study_id": "UNKNOWN",
        "study_uid": "UNKNOWN",
        "condition_id": condition_id,
        "condition_label": condition_label,
        "treatment_batch_id": "NOT_APPLICABLE",
        "specimen_id": specimen_id,
        "specimen_uid": "UNKNOWN",
        "specimen_label": specimen_label,
        "lamella_id": "UNKNOWN",
        "lamella_uid": "UNKNOWN",
        "image_id": context["image_id"],
        "image_uid": context["image_uid"],
        "image_uid_generation_method": "PRESERVED",
        "image_uid_name_template_id": "NOT_APPLICABLE",
        "image_parent_identity_component": f"uids|{context['project_uid']}",
        "legacy_image_parent_identity_token": "NOT_APPLICABLE",
        "legacy_image_parent_identity_token_method": "NOT_APPLICABLE",
        "legacy_image_registry_relative_path": "NOT_APPLICABLE",
        "legacy_image_registry_row_ordinal": None,
        "legacy_image_registry_row_ordinal_status": "NOT_APPLICABLE",
        "legacy_image_registry_row_sha256": "NOT_APPLICABLE",
        "analysis_region_id": "WHOLE_IMAGE" if snapshot.analysis["use_whole_image"] == 1 else "ANALYSIS_MASK_001",
        "experimental_unit_id": specimen_id,
        "experimental_unit_level": "specimen" if specimen_id != "UNKNOWN" else "UNKNOWN",
        "analysis_session_id": context["analysis_session_id"],
        "analysis_session_id_origin": "NATIVE_V2",
        "analysis_session_uid": context["analysis_session_uid"],
        "analysis_session_uid_generation_method": "PRESERVED",
        "analysis_session_uid_name_template_id": "NOT_APPLICABLE",
        "legacy_analysis_session_id": legacy_component,
        "working_state_id": "NOT_APPLICABLE",
        "revision_id": context["revision_id"],
        "revision_uid": context["revision_uid"],
        "revision_uid_generation_method": _uuid_method(context["revision_uid"], prefer_random=True),
        "revision_uid_name_template_id": "NOT_APPLICABLE",
        "parent_revision_id": revision.manifest["parent_revision_id"],
        "run_id": run_id,
        "run_uid": run_uid,
        "generation_token": context["generation_token"],
        "operator_id": snapshot.payload["operator_id"] or "UNKNOWN",
        "source_file_name": snapshot.source_path.name,
        "source_path_or_alias": snapshot.source_path.relative_to(snapshot.project_root).as_posix(),
        "source_sha256": context["source_sha256"],
        "master_pixel_sha256": context["master_pixel_sha256"],
        "master_pixel_hash_method": snapshot.image["master_pixel_hash_method"],
        "master_pixel_hash_status": snapshot.image["master_pixel_hash_status"],
        "source_width_px": snapshot.image["width_px"],
        "source_height_px": snapshot.image["height_px"],
        "acquisition_datetime": "UNKNOWN",
        "analysis_datetime": analysis_at,
        "scale_x_nm_px": snapshot.image["scale_x_nm_px"],
        "scale_y_nm_px": snapshot.image["scale_y_nm_px"],
        "source_scale_x_nm_px": source_scale_x,
        "source_scale_x_nm_px_status": source_scale_status,
        "source_scale_y_nm_px": source_scale_y,
        "source_scale_y_nm_px_status": source_scale_status,
        "scale_origin": scale_origin,
        "coordinate_transform_version": "AXIS_ALIGNED_XY_V1",
        "coordinate_origin_x_nm": 0,
        "coordinate_origin_y_nm": 0,
        "scale_confirmed": 1,
        "scale_uncertainty_x_nm_px": None,
        "scale_uncertainty_x_nm_px_status": "NOT_MEASURED",
        "scale_uncertainty_y_nm_px": None,
        "scale_uncertainty_y_nm_px_status": "NOT_MEASURED",
        "scale_reference_length_px": None,
        "scale_reference_length_px_status": "NOT_APPLICABLE",
        "scale_reference_length_nm": None,
        "scale_reference_length_nm_status": "NOT_APPLICABLE",
        "scale_reference_angle_deg": None,
        "scale_reference_angle_deg_status": "NOT_APPLICABLE",
        "thickness_nm": thickness,
        "thickness_nm_status": thickness_status,
        "thickness_uncertainty_nm": None,
        "thickness_uncertainty_nm_status": "NOT_MEASURED",
        "thickness_method": "UNKNOWN",
        "thickness_notes": "",
        "surface_id": surface_id,
        "material_side": "UNKNOWN",
        "depth_rule": "SIGNED_NEAREST_SURFACE_V1" if surface_active else "NOT_APPLICABLE",
        "depth_bin_nm": depth_bin,
        "depth_bin_nm_status": "KNOWN",
        "defect_type": "CAVITY",
        "measurement_protocol": geometry_protocol,
        "primary_measurement_protocol": primary_protocol,
        "measurement_protocol_policy_version": "CAVITY_PROTOCOL_POLICY_V1",
        "classification_policy": CLASSIFICATION_POLICY,
        "classification_policy_version": "CLASSIFICATION_POLICY_V1",
        "validity_update_mode": VALIDITY_UPDATE_MODE,
        "count_rule": "CENTER_IN_NET_AREA",
        "size_rule": "FULL_GEOMETRY_VISIBLE",
        "border_rule": "CENTER_IN_NET_AREA_MINIMUM_V1",
        "border_center_tolerance_px": CENTER_BORDER_EPSILON_PX,
        "border_algorithm_version": BORDER_ALGORITHM_VERSION,
        "border_algorithm_status": BORDER_ALGORITHM_STATUS,
        "limit_policy_id": SAMPLING_POLICY_VERSION,
        "detection_limit_px": 3,
        "size_measurement_limit_px": 5,
        "roi_zip_sha256": revision.manifest["roi_zip_sha256"],
        "revision_manifest_sha256": revision.manifest_sha256,
        "revision_complete_marker_sha256": prepared.revision_complete_marker_sha256,
        "object_uuid": object_uuid,
        "object_uuid_generation_method": object_method,
        "object_uuid_name_template_id": object_template,
        "legacy_analysis_session_identity_component": legacy_component,
        "legacy_analysis_session_identity_component_origin": legacy_origin,
        "cavity_id": cavity_id,
        "identity_provenance": provenance,
        "created_at": created_at,
        "last_modified_at": modified_at,
        "candidate_id": "NOT_APPLICABLE" if candidate_trace is None else candidate_trace["candidate_id"],
        "cavity_class": cavity_class,
        "classification_confidence": _confidence(entry),
        "review_status": review_status,
        **geometry,
        "major_axis_px": max(width, height),
        "minor_axis_px": min(width, height),
        **validity,
        **inclusions,
        "manual_excluded": manual_excluded,
        "exclusion_reason": exclusion_reason,
        "center_inside_net_area": center_inside,
        "touches_image_edge": touches_image,
        "touches_mask_edge": touches_mask,
        "touches_exclusion": int(exclusion_reason != "NOT_APPLICABLE" and manual_excluded == 0),
        "touches_surface": int(surface_active and signed_value is not None and signed_value == 0),
        "duplicate_status": _duplicate_status(entry),
        "duplicate_partners": duplicate_partners,
        "signed_depth_nm": signed_value,
        "signed_depth_nm_status": signed_status,
        "absolute_depth_nm": absolute_value,
        "absolute_depth_nm_status": absolute_status,
        "depth_bin_index": depth_index,
        "depth_bin_index_status": depth_status,
        "depth_bin_low_nm": depth_low,
        "depth_bin_low_nm_status": depth_status,
        "depth_bin_high_nm": depth_high,
        "depth_bin_high_nm_status": depth_status,
        "distance_to_grain_boundary_nm": distances["distance_to_grain_boundary_nm"][0],
        "distance_to_grain_boundary_nm_status": distances["distance_to_grain_boundary_nm"][1],
        "distance_to_dislocation_nm": distances["distance_to_dislocation_nm"][0],
        "distance_to_dislocation_nm_status": distances["distance_to_dislocation_nm"][1],
        "distance_to_interface_nm": distances["distance_to_interface_nm"][0],
        "distance_to_interface_nm_status": distances["distance_to_interface_nm"][1],
        "sampling_warning": sampling_class["sampling_warning"],
        "sampling_axis_method": sampling["sampling_axis_method"],
        "sampling_axis_method_version": ANISOTROPIC_AXIS_VERSION,
        "scale_along_axis_nm_px": sampling["scale_along_axis_nm_px"],
        "axis_length_px": sampling["axis_length_px"],
        "local_cnr": None,
        "local_cnr_status": "NOT_MEASURED",
        "cnr_method_id": "UNKNOWN",
        "cnr_defect_region_ref": "NOT_APPLICABLE",
        "cnr_background_region_ref": "NOT_APPLICABLE",
        "cnr_defect_pixel_count": None,
        "cnr_defect_pixel_count_status": "NOT_MEASURED",
        "cnr_background_pixel_count": None,
        "cnr_background_pixel_count_status": "NOT_MEASURED",
        "focus_or_quality_flag": "UNKNOWN",
        "measurement_source": _measurement_source(entry),
        "view_id": "NOT_APPLICABLE" if candidate_trace is None else candidate_trace["view_id"],
        "proposed_geometry_sha256": "NOT_APPLICABLE" if candidate_trace is None else candidate_trace["proposed_geometry_sha256"],
        "last_edit_method": last_edit_raw,
        "last_edit_at": modified_at,
        **_NO_3D_CELLS,
    }
    expected = set(profile.header)
    missing = sorted(expected - set(record))
    extra = sorted(set(record) - expected)
    if missing or extra:
        _fail("runtime row construction does not match exact profile", missing=missing, extra=extra)
    return record


def _revision_complete_marker_sha256(revision: VerifiedRevision) -> str:
    try:
        payload = stable_plain_bytes(
            revision.path / "COMPLETE",
            label="revision COMPLETE marker authority",
        )
    except PathSafetyError as exc:
        raise ValidationError(
            "revision COMPLETE authority cannot be read safely",
            details={"cause": str(exc)},
        ) from exc
    return hashlib.sha256(payload).hexdigest()


@dataclass(frozen=True)
class PreparedObjectTable:
    snapshot: Any
    profile: ObjectTableProfile
    revision: VerifiedRevision
    cavity_entries: tuple[Any, ...]
    geometries: tuple[Mapping[str, Any], ...]
    net_area_nm2: Decimal
    revision_complete_marker_sha256: str

    def materialize(self, *, run_id: str, run_uid: str, analysis_at: str) -> tuple[dict[str, Any], ...]:
        if not _ID_RE.fullmatch(run_id):
            _fail("run_id is not a canonical identifier")
        validate_canonical_uuid(run_uid, expected_version=4)
        if _revision_complete_marker_sha256(self.revision) != self.revision_complete_marker_sha256:
            _fail("revision COMPLETE authority changed after object-table preflight")
        protocols = {str(geometry["measurement_protocol"]) for geometry in self.geometries}
        primary_protocol = next(iter(protocols)) if len(protocols) == 1 else "MIXED_STRATIFIED"
        by_cavity: dict[str, str] = {}
        seen_objects: set[str] = set()
        for entry in self.cavity_entries:
            cavity_id = str(_prop(entry, "Cavity_id", "cavity_id", default=""))
            object_uuid = str(_prop(entry, "Object_uuid", "object_uuid", default=""))
            if cavity_id in by_cavity or object_uuid in seen_objects:
                _fail("ROI snapshot contains duplicate cavity/object identity")
            by_cavity[cavity_id] = object_uuid
            seen_objects.add(object_uuid)
        return tuple(
            _object_record(
                prepared=self,
                entry=entry,
                geometry=geometry,
                primary_protocol=primary_protocol,
                run_id=run_id,
                run_uid=run_uid,
                analysis_at=analysis_at,
                by_cavity=by_cavity,
            )
            for entry, geometry in zip(self.cavity_entries, self.geometries)
        )

    def preflight_result(self) -> dict[str, Any]:
        preview_run_uid = "00000000-0000-4000-8000-000000000000"
        preview_at = self.revision.marker["completed_at"]
        records = self.materialize(
            run_id="PREFLIGHT",
            run_uid=preview_run_uid,
            analysis_at=preview_at,
        )
        payload = render_object_table(records)
        return {
            "object_table_profile_id": PROFILE_ID,
            "object_table_profile_sha256": PROFILE_SHA256,
            "object_table_header_sha256": HEADER_SHA256,
            "object_table_column_count": COLUMN_COUNT,
            "identity_provenance_ordinal": IDENTITY_PROVENANCE_ORDINAL,
            "object_row_count": len(records),
            "zero_event_status": "ZERO_EVENTS_VALID" if not records else "EVENTS_PRESENT",
            "header_only_zero_event": not records and payload == self.profile.header_bytes,
            "no_3d_models": True,
            "revision_manifest_sha256": self.revision.manifest_sha256,
            "preview_table_sha256": hashlib.sha256(payload).hexdigest(),
        }


def prepare_object_table(snapshot: Any) -> PreparedObjectTable:
    """Read-only preflight of profile, revision binding and every cavity row."""

    profile = _profile()
    revision = _revision_for_snapshot(snapshot)
    cavity_entries = tuple(entry for entry in snapshot.roi_entries if _roi_type(entry) == "cavity")
    geometries = tuple(_geometry(entry, snapshot) for entry in cavity_entries)
    prepared = PreparedObjectTable(
        snapshot=snapshot,
        profile=profile,
        revision=revision,
        cavity_entries=cavity_entries,
        geometries=geometries,
        net_area_nm2=_net_area_nm2(snapshot),
        revision_complete_marker_sha256=_revision_complete_marker_sha256(revision),
    )
    # Materializing a deterministic probe catches incomplete indivisible rows
    # without reserving a RUN identity or writing any file.
    prepared.preflight_result()
    return prepared


def publish_snapshot_run(snapshot: Any, raw_input: Mapping[str, Any]) -> dict[str, Any]:
    """Publish one immutable RUN through the existing thirteen-step transaction."""

    from .canonical_json import canonical_json_sha256
    from .identity import new_uuid4_identity
    from .run_transaction import PayloadSpec, ValidationEvidence, publish_run

    prepared = prepare_object_table(snapshot)
    now = datetime.now(timezone.utc)
    analysis_at = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    run_id = now.strftime("P1_%Y%m%dT%H%M%S%f_") + uuid.uuid4().hex[:8]
    run_uid = new_uuid4_identity()
    records = prepared.materialize(run_id=run_id, run_uid=run_uid, analysis_at=analysis_at)
    if records and not any(int(record["count_valid"]) == 1 for record in records):
        _fail("approved zero-event encoding is header-only; review/exclude all-cavity snapshot before export")
    table_bytes = render_object_table(records)
    statistics = zero_event_summary(records, net_area_nm2=prepared.net_area_nm2)
    if not records:
        statistics["zero_event_status"] = "ZERO_EVENTS_VALID"
    manifest_fields: dict[str, Any] = {
        "project_uid": snapshot.context["project_uid"],
        "image_uid": snapshot.context["image_uid"],
        "analysis_session_uid": snapshot.context["analysis_session_uid"],
        "revision_id": snapshot.context["revision_id"],
        "revision_uid": snapshot.context["revision_uid"],
        "run_id": run_id,
        "run_uid": run_uid,
        "source_sha256": snapshot.context["source_sha256"],
        "master_pixel_sha256": snapshot.context["master_pixel_sha256"],
        "roi_zip_sha256": prepared.revision.manifest["roi_zip_sha256"],
        "revision_manifest_sha256": prepared.revision.manifest_sha256,
        **statistics,
        "bin_contract": {
            "depth_bin_nm": snapshot.analysis["feature_distance_bin_nm"],
            "feature_distance_bin_nm": snapshot.analysis["feature_distance_bin_nm"],
            "histogram_bin_nm": snapshot.analysis["histogram_bin_nm"],
        },
        "object_table_profile_id": PROFILE_ID,
        "object_table_profile_sha256": PROFILE_SHA256,
        "object_table_header_sha256": HEADER_SHA256,
        "object_table_column_count": COLUMN_COUNT,
        "identity_provenance_ordinal": IDENTITY_PROVENANCE_ORDINAL,
        "defect_type_scope": "CAVITY",
        "model_3d_scope": "NONE",
        "technical_preview": True,
        "scientific_validation": False,
        "functional_release": False,
    }
    render_object_table(records, manifest=manifest_fields)
    evidence_domain = {
        "evidence_schema": "CTL_P1_OBJECT_TABLE_VALIDATION_EVIDENCE_V1",
        "object_table_sha256": hashlib.sha256(table_bytes).hexdigest(),
        "profile_sha256": PROFILE_SHA256,
        "header_sha256": HEADER_SHA256,
        "revision_manifest_sha256": prepared.revision.manifest_sha256,
        "run_uid": run_uid,
    }
    validation = ValidationEvidence(
        status="PASS",
        validated_at=analysis_at,
        fingerprint_sha256=canonical_json_sha256(evidence_domain),
    )
    run_parent = snapshot.project_root.joinpath(*Path(raw_input["runs_relative_path"]).parts)
    run_parent.mkdir(parents=True, exist_ok=True)
    pointer_path = snapshot.project_root.joinpath(*Path(raw_input["current_run_pointer_relative_path"]).parts)
    registry_path = snapshot.project_root.joinpath(*Path(raw_input["run_registry_relative_path"]).parts)
    published = publish_run(
        run_parent,
        project_root=snapshot.project_root,
        current_pointer_path=pointer_path,
        registry_path=registry_path,
        run_id=run_id,
        run_uid=run_uid,
        payloads={
            "cavity_objects.tsv": PayloadSpec(
                table_bytes,
                "text/tab-separated-values; charset=utf-8",
                "OBJECT_TABLE_AUTHORITY",
            )
        },
        manifest_fields=manifest_fields,
        validation=validation,
        atomic_capability="UNKNOWN",
    )
    return {
        "result": "RUN_PUBLISHED",
        "run_id": run_id,
        "run_uid": run_uid,
        "relative_path": published.run_path.relative_to(snapshot.project_root).as_posix(),
        "run_manifest_sha256": published.manifest_sha256,
        "current_run_pointer_relative_path": pointer_path.relative_to(snapshot.project_root).as_posix(),
        "run_registry_relative_path": registry_path.relative_to(snapshot.project_root).as_posix(),
        "object_table_profile_id": PROFILE_ID,
        "object_table_header_sha256": HEADER_SHA256,
        "object_table_column_count": COLUMN_COUNT,
        "object_row_count": len(records),
        "zero_event_status": statistics["zero_event_status"],
        "directory_atomic_move_capability": published.directory_atomic_move_capability,
        "retention_policy": published.retention_policy,
        "technical_preview": True,
        "scientific_validation": False,
        "functional_release": False,
    }
