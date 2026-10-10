"""Machine-readable invariants shared by the Prompt-1 scientific core."""

from __future__ import annotations

import csv
from dataclasses import dataclass
from decimal import Decimal
from functools import lru_cache
import hashlib
import io
import math
from pathlib import Path
import re
from typing import Any, Mapping, Sequence

from .errors import ContractError, ValidationError
from .identity import validate_canonical_uuid, validate_cavity_id, validate_human_id


TYPED_NUMERIC_STATUSES = frozenset(
    {"KNOWN", "UNKNOWN", "NOT_APPLICABLE", "NOT_MEASURED", "UNDEFINED"}
)
TYPED_NUMERIC_STATUS_LITERAL = "KNOWN|UNKNOWN|NOT_APPLICABLE|NOT_MEASURED|UNDEFINED"
CLASSIFICATION_POLICY = "PRIMARY_CONFIRMED_ONLY_WITH_SENSITIVITY"
VALIDITY_UPDATE_MODE = "INDEPENDENT_FLAGS"

CANONICAL_PROTOCOLS = frozenset(
    {
        "CAVITY_CIRCLE",
        "CAVITY_ELLIPSE",
        "CAVITY_CONTOUR",
        "LOOP_CIRCLE",
        "LOOP_ELLIPSE",
        "LOOP_CONTOUR",
    }
)
CAVITY_PROTOCOLS = frozenset({"CAVITY_CIRCLE", "CAVITY_ELLIPSE", "CAVITY_CONTOUR"})
CAVITY_CLASSES = frozenset(
    {"confirmed", "uncertain", "possible_artifact", "rejected", "pending"}
)

LEGACY_READ_ALIASES: dict[str, str] = {
    "Count_valid": "count_valid",
    "Size_valid": "size_valid",
    "Position_valid": "position_valid",
    "distance_gb_nm": "distance_to_grain_boundary_nm",
    "area_nm2": "projected_area_nm2",
}
LEGACY_PROTOCOL_ALIASES: dict[str, str] = {
    "LINEAR_DIAMETER_CIRCLE": "CAVITY_CIRCLE",
    "FITTED_ELLIPSE": "CAVITY_ELLIPSE",
    "MANUAL_CONTOUR": "CAVITY_CONTOUR",
}

SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$", re.ASCII)

SCHEMA_DICTIONARY_PROFILE_ID = "SCHEMA_V2_DICTIONARY_469X11_V1"
SCHEMA_DICTIONARY_SHA256 = "e4d9f44a31544583d0fad154199f02b8b4642e4e09dd50e79699a8923116af03"
SCHEMA_DICTIONARY_BYTES = 81353
SCHEMA_DICTIONARY_ROWS = 469
SCHEMA_DICTIONARY_COLUMNS = (
    "entity",
    "field_name",
    "status",
    "logical_type",
    "allowed_values",
    "requirement",
    "unit",
    "origin",
    "authority_role",
    "migration_r5_r9",
    "notes",
)
SCHEMA_DICTIONARY_RUNTIME_PATH = (
    Path(__file__).resolve().parents[1] / "data" / "schema_v2_field_dictionary.csv"
)
CAVITY_OBJECTS_HEADER_PROFILE_STATUS = "APPROVED_RUNTIME_CONTRACT"
CAVITY_OBJECTS_HEADER_BLOCK_REASON = "NOT_APPLICABLE_PROFILE_MATERIALIZED"

_DICTIONARY_STATUSES = frozenset({"H", "R", "N", "X"})
_DICTIONARY_REQUIREMENTS = frozenset({"REQ", "COND", "OPT"})
_DICTIONARY_ENTITY_PATTERN = re.compile(r"^[a-z][a-z0-9_]*$", re.ASCII)
_DICTIONARY_FIELD_PATTERN = re.compile(r"^[A-Za-z][A-Za-z0-9_.]*$", re.ASCII)
_LEGACY_DICTIONARY_TYPES = frozenset(
    {"legacy_enum_alias", "legacy_field_alias", "legacy_identifier", "migration_rule"}
)


def _fail(message: str, **details: Any) -> None:
    raise ValidationError(message, details=details)


def is_finite_number(value: Any) -> bool:
    if isinstance(value, bool):
        return False
    if isinstance(value, int):
        return True
    if isinstance(value, float):
        return math.isfinite(value)
    if isinstance(value, Decimal):
        return value.is_finite()
    return False


def require_finite_number(
    value: Any,
    *,
    field: str,
    minimum: int | float | Decimal | None = None,
    strictly_positive: bool = False,
) -> int | float | Decimal:
    if not is_finite_number(value):
        _fail("field must be a finite number", field=field, value=repr(value))
    if strictly_positive and value <= 0:
        _fail("field must be strictly positive", field=field, value=value)
    if minimum is not None and value < minimum:
        _fail("field is below its minimum", field=field, value=value, minimum=minimum)
    return value


def validate_typed_magnitude(
    record: Mapping[str, Any],
    field: str,
    *,
    tsv: bool = False,
    minimum: int | float | Decimal | None = None,
    strictly_positive: bool = False,
) -> None:
    """Enforce ``KNOWN iff finite value present`` bidirectionally."""

    status_field = f"{field}_status"
    if field not in record or status_field not in record:
        _fail("nullable magnitude and status sibling are both required", field=field)
    status = record[status_field]
    if status not in TYPED_NUMERIC_STATUSES:
        _fail("invalid typed magnitude status", field=status_field, value=status)
    value = record[field]
    absent = value == "" if tsv else value is None
    if status == "KNOWN":
        if absent:
            _fail("KNOWN magnitude is missing", field=field)
        require_finite_number(
            value,
            field=field,
            minimum=minimum,
            strictly_positive=strictly_positive,
        )
    elif not absent:
        _fail("non-KNOWN magnitude must be absent", field=field, status=status, value=value)


def typed_magnitude(value: Any, status: str) -> dict[str, Any]:
    record = {"value": value, "value_status": status}
    validate_typed_magnitude(record, "value")
    return record


def typed_magnitude_to_tsv(value: Any, status: str) -> tuple[str, str]:
    record = {"value": value, "value_status": status}
    validate_typed_magnitude(record, "value")
    if value is None:
        return "", status
    return str(value), status


def validate_boolean_01(value: Any, *, field: str) -> int:
    if type(value) is not int or value not in {0, 1}:
        _fail("required boolean must be encoded as integer 0 or 1", field=field, value=value)
    return value


def normalize_legacy_read_record(record: Mapping[str, Any]) -> dict[str, Any]:
    """Map the five case-sensitive legacy field aliases for read/migration only."""

    if not isinstance(record, Mapping):
        _fail("legacy record must be an object")
    result: dict[str, Any] = {}
    for field, value in record.items():
        canonical = LEGACY_READ_ALIASES.get(field, field)
        if canonical in result:
            _fail(
                "legacy alias collides with another input field",
                source_field=field,
                canonical_field=canonical,
            )
        result[canonical] = value
    protocol = result.get("measurement_protocol")
    if protocol in LEGACY_PROTOCOL_ALIASES:
        result["measurement_protocol"] = LEGACY_PROTOCOL_ALIASES[protocol]
    return result


def assert_canonical_v2_field_names(record: Mapping[str, Any]) -> None:
    aliases = sorted(set(record).intersection(LEGACY_READ_ALIASES))
    if aliases:
        _fail("v2 writer attempted to emit legacy field alias", aliases=aliases)
    protocol = record.get("measurement_protocol")
    if protocol in LEGACY_PROTOCOL_ALIASES:
        _fail("v2 writer attempted to emit legacy protocol alias", protocol=protocol)


_INCLUSION_FIELDS = (
    "primary_count_included",
    "primary_size_included",
    "primary_position_included",
    "sensitivity_count_included",
    "sensitivity_size_included",
    "sensitivity_position_included",
)
_VALIDITY_FIELDS = ("count_valid", "size_valid", "position_valid")

_REQUIRED_INDIVISIBLE_FIELDS = frozenset(
    {
        "object_uuid",
        "cavity_id",
        "measurement_protocol",
        "cavity_class",
        "classification_confidence",
        "review_status",
        "count_valid",
        "size_valid",
        "position_valid",
        *_INCLUSION_FIELDS,
        "center_inside_net_area",
        "touches_image_edge",
        "touches_mask_edge",
        "touches_exclusion",
        "touches_surface",
        "revision_id",
        "measurement_source",
        "identity_provenance",
        "signed_depth_nm",
        "signed_depth_nm_status",
        "distance_to_grain_boundary_nm",
        "distance_to_grain_boundary_nm_status",
        "distance_to_dislocation_nm",
        "distance_to_dislocation_nm_status",
        "distance_to_interface_nm",
        "distance_to_interface_nm_status",
    }
)


def validate_indivisible_object_record(record: Mapping[str, Any]) -> None:
    """Validate the minimum indivisible observation envelope from WP-02."""

    if not isinstance(record, Mapping):
        _fail("object observation must be one record")
    assert_canonical_v2_field_names(record)
    missing = sorted(_REQUIRED_INDIVISIBLE_FIELDS - set(record))
    if missing:
        _fail("indivisible object record is incomplete", missing=missing)
    validate_canonical_uuid(record["object_uuid"])
    validate_cavity_id(record["cavity_id"])
    validate_human_id(record["revision_id"], field="revision_id")
    if record["measurement_protocol"] not in CANONICAL_PROTOCOLS:
        _fail("invalid canonical measurement protocol", value=record["measurement_protocol"])
    if record["cavity_class"] not in CAVITY_CLASSES:
        _fail("invalid cavity class", value=record["cavity_class"])
    if record["review_status"] not in {
        "pending",
        "reviewed",
        "imported_unreviewed",
        "NOT_APPLICABLE",
    }:
        _fail("invalid object review status", value=record["review_status"])
    if record["measurement_source"] not in {
        "manual",
        "algorithmic_proposal",
        "algorithmic_refined",
        "imported_legacy",
    }:
        _fail("invalid object measurement source", value=record["measurement_source"])
    for field in (*_VALIDITY_FIELDS, *_INCLUSION_FIELDS, "center_inside_net_area", "touches_image_edge", "touches_mask_edge", "touches_exclusion", "touches_surface"):
        validate_boolean_01(record[field], field=field)
    for field in (
        "signed_depth_nm",
        "distance_to_grain_boundary_nm",
        "distance_to_dislocation_nm",
        "distance_to_interface_nm",
    ):
        validate_typed_magnitude(record, field, minimum=0 if field.startswith("distance_") else None)
    provenance = record["identity_provenance"]
    if not isinstance(provenance, Sequence) or isinstance(provenance, (str, bytes)) or not provenance:
        _fail("object identity provenance must travel with the observation")
    primary_class = record["cavity_class"] == "confirmed"
    sensitivity_class = record["cavity_class"] in {"confirmed", "uncertain"}
    for endpoint in ("count", "size", "position"):
        valid = record[f"{endpoint}_valid"]
        expected_primary = int(primary_class and valid == 1)
        expected_sensitivity = int(sensitivity_class and valid == 1)
        if record[f"primary_{endpoint}_included"] != expected_primary:
            _fail("primary inclusion flag contradicts class/validity", endpoint=endpoint)
        if record[f"sensitivity_{endpoint}_included"] != expected_sensitivity:
            _fail("sensitivity inclusion flag contradicts class/validity", endpoint=endpoint)


def sort_records_for_statistic(
    records: Sequence[Mapping[str, Any]],
    *,
    numeric_field: str,
) -> list[dict[str, Any]]:
    """Sort copied whole records, never parallel value arrays."""

    copied: list[dict[str, Any]] = []
    seen_uuids: set[str] = set()
    seen_natural: set[tuple[str, str]] = set()
    for index, source in enumerate(records):
        if not isinstance(source, Mapping):
            _fail("observation is not an object", row=index)
        if "object_uuid" not in source or "cavity_id" not in source:
            _fail("observation lacks indivisible identity", row=index)
        validate_canonical_uuid(source["object_uuid"])
        validate_cavity_id(source["cavity_id"])
        if source["object_uuid"] in seen_uuids:
            _fail("duplicate object_uuid", object_uuid=source["object_uuid"])
        seen_uuids.add(source["object_uuid"])
        session_id = str(source.get("analysis_session_id", ""))
        natural = (session_id, source["cavity_id"])
        if natural in seen_natural:
            _fail("duplicate session/cavity natural key", key=natural)
        seen_natural.add(natural)
        if numeric_field not in source:
            _fail("statistical field missing from record", row=index, field=numeric_field)
        require_finite_number(source[numeric_field], field=numeric_field)
        copied.append(dict(source))
    return sorted(copied, key=lambda item: item[numeric_field])


def validate_sha256(value: Any, *, field: str) -> str:
    if not isinstance(value, str) or SHA256_PATTERN.fullmatch(value) is None:
        _fail("invalid lowercase SHA-256", field=field, value=value)
    return value


_READ_ONLY_MASTER_OPERATIONS = frozenset({"INSPECT_READ_ONLY", "MIGRATE_READ_ONLY"})
_VERIFIED_MASTER_OPERATIONS = frozenset(
    {"SCIENTIFIC_EDIT", "REVIEW", "EXPORT_RUN", "INSPECT_READ_ONLY", "MIGRATE_READ_ONLY"}
)


def validate_master_protection(source: Mapping[str, Any], *, operation: str) -> None:
    """Enforce separate source/pixel hashes and MASTER_READ_ONLY capability."""

    required = {
        "image_role",
        "source_sha256",
        "master_pixel_sha256",
        "master_pixel_hash_method",
        "master_pixel_hash_status",
        "source_width_px",
        "source_height_px",
    }
    missing = sorted(required - set(source))
    if missing:
        _fail("master protection record is incomplete", missing=missing)
    if source["image_role"] != "MASTER_READ_ONLY":
        _fail("source/master role must be MASTER_READ_ONLY", role=source["image_role"])
    validate_sha256(source["source_sha256"], field="source_sha256")
    validate_sha256(source["master_pixel_sha256"], field="master_pixel_sha256")
    if not isinstance(source["master_pixel_hash_method"], str) or not source["master_pixel_hash_method"]:
        _fail("master pixel hash method is required")
    for field in ("source_width_px", "source_height_px"):
        if type(source[field]) is not int or source[field] <= 0:
            _fail("master dimensions must be positive integers", field=field)
    status = source["master_pixel_hash_status"]
    if status == "MISMATCH":
        _fail("master pixel hash mismatch")
    if status == "NOT_VERIFIED":
        if operation not in _READ_ONLY_MASTER_OPERATIONS:
            _fail("unverified master permits only read-only inspection/migration", operation=operation)
    elif status == "VERIFIED":
        if operation not in _VERIFIED_MASTER_OPERATIONS:
            _fail("unknown master operation", operation=operation)
    else:
        _fail("invalid master pixel hash status", status=status)


def assert_nonfinite_free(value: Any, *, path: str = "$") -> None:
    """Recursively reject NaN/Inf and unexpected numeric strings."""

    if isinstance(value, Mapping):
        for key, item in value.items():
            assert_nonfinite_free(item, path=f"{path}.{key}")
    elif isinstance(value, (list, tuple)):
        for index, item in enumerate(value):
            assert_nonfinite_free(item, path=f"{path}[{index}]")
    elif isinstance(value, (float, Decimal)) and not is_finite_number(value):
        _fail("non-finite value in contract object", path=path, value=repr(value))


def propose_study_id(project_id: str) -> str:
    """Return the editable UI proposal without asserting identity equivalence."""

    return validate_human_id(project_id, field="project_id")


def validate_project_study_cardinality(
    *,
    project_id: str,
    study_ids: Sequence[str],
    legacy_unconfirmed: bool = False,
) -> None:
    """Enforce initial ``1 project : 1 study`` without inventing legacy identity."""

    validate_human_id(project_id, field="project_id")
    if isinstance(study_ids, (str, bytes)) or not isinstance(study_ids, Sequence):
        _fail("study_ids must be a sequence")
    if len(study_ids) != 1:
        _fail("initial schema permits exactly one study per project", count=len(study_ids))
    study_id = study_ids[0]
    if legacy_unconfirmed:
        if study_id != "UNKNOWN":
            _fail("unconfirmed legacy study identity must remain UNKNOWN", study_id=study_id)
    else:
        validate_human_id(study_id, field="study_id")


@dataclass(frozen=True, slots=True)
class SchemaFieldDefinition:
    """One byte-order-preserving row of the sealed 469x11 dictionary."""

    ordinal: int
    entity: str
    field_name: str
    status: str
    logical_type: str
    allowed_values: str
    requirement: str
    unit: str
    origin: str
    authority_role: str
    migration_r5_r9: str
    notes: str

    @property
    def key(self) -> tuple[str, str]:
        return self.entity, self.field_name

    @property
    def canonical_writer_field(self) -> bool:
        return self.status != "X" and self.logical_type not in _LEGACY_DICTIONARY_TYPES


class SealedSchemaDictionary:
    """Validated view with consumer-owned indexes and immutable row definitions."""

    __slots__ = ("_by_entity", "_by_key", "_rows", "byte_length", "sha256")

    def __init__(
        self,
        rows: Sequence[SchemaFieldDefinition],
        *,
        byte_length: int,
        sha256: str,
    ) -> None:
        self._rows = tuple(rows)
        self._by_key = {row.key: row for row in rows}
        by_entity: dict[str, list[SchemaFieldDefinition]] = {}
        for row in rows:
            by_entity.setdefault(row.entity, []).append(row)
        self._by_entity = {entity: tuple(fields) for entity, fields in by_entity.items()}
        self.byte_length = byte_length
        self.sha256 = sha256

    @property
    def rows(self) -> tuple[SchemaFieldDefinition, ...]:
        return self._rows

    @property
    def entities(self) -> tuple[str, ...]:
        return tuple(self._by_entity)

    def lookup(self, entity: str, field_name: str) -> SchemaFieldDefinition:
        try:
            return self._by_key[(entity, field_name)]
        except KeyError:
            _fail(
                "emitted field is absent from the sealed schema dictionary",
                entity=entity,
                field_name=field_name,
                dictionary_profile=SCHEMA_DICTIONARY_PROFILE_ID,
            )

    def fields_for_entity(self, entity: str) -> tuple[SchemaFieldDefinition, ...]:
        try:
            return self._by_entity[entity]
        except KeyError:
            _fail(
                "entity is absent from the sealed schema dictionary",
                entity=entity,
                dictionary_profile=SCHEMA_DICTIONARY_PROFILE_ID,
            )

    def canonical_field_names_for_entity(self, entity: str) -> tuple[str, ...]:
        return tuple(
            row.field_name for row in self.fields_for_entity(entity) if row.canonical_writer_field
        )


def validate_schema_dictionary_rows(
    rows: Sequence[Mapping[str, str]],
) -> tuple[SchemaFieldDefinition, ...]:
    """Reject duplicate or internally inconsistent parsed dictionary rows.

    This function validates structure only.  Authority comes exclusively from
    :func:`load_sealed_schema_dictionary`, which verifies the exact bytes first.
    """

    if isinstance(rows, (str, bytes)) or not isinstance(rows, Sequence):
        _fail("schema dictionary rows must be a sequence")
    if len(rows) != SCHEMA_DICTIONARY_ROWS:
        _fail(
            "schema dictionary row count mismatch",
            expected=SCHEMA_DICTIONARY_ROWS,
            actual=len(rows),
        )
    definitions: list[SchemaFieldDefinition] = []
    seen: set[tuple[str, str]] = set()
    for ordinal, source in enumerate(rows, start=1):
        if not isinstance(source, Mapping):
            _fail("schema dictionary row is not an object", row=ordinal)
        if tuple(source.keys()) != SCHEMA_DICTIONARY_COLUMNS:
            _fail(
                "schema dictionary row columns/order mismatch",
                row=ordinal,
                expected=list(SCHEMA_DICTIONARY_COLUMNS),
                actual=list(source.keys()),
            )
        values = {column: source[column] for column in SCHEMA_DICTIONARY_COLUMNS}
        if any(not isinstance(value, str) for value in values.values()):
            _fail("schema dictionary cells must be strings", row=ordinal)
        for column in SCHEMA_DICTIONARY_COLUMNS[:-1]:
            if values[column] == "":
                _fail("schema dictionary required cell is empty", row=ordinal, column=column)
        if _DICTIONARY_ENTITY_PATTERN.fullmatch(values["entity"]) is None:
            _fail("invalid schema dictionary entity", row=ordinal, entity=values["entity"])
        if _DICTIONARY_FIELD_PATTERN.fullmatch(values["field_name"]) is None:
            _fail(
                "invalid schema dictionary field name",
                row=ordinal,
                field_name=values["field_name"],
            )
        if values["status"] not in _DICTIONARY_STATUSES:
            _fail("invalid schema dictionary status", row=ordinal, status=values["status"])
        if values["requirement"] not in _DICTIONARY_REQUIREMENTS:
            _fail(
                "invalid schema dictionary requirement",
                row=ordinal,
                requirement=values["requirement"],
            )
        key = values["entity"], values["field_name"]
        if key in seen:
            _fail("duplicate schema dictionary entity/field", row=ordinal, key=list(key))
        seen.add(key)
        definitions.append(SchemaFieldDefinition(ordinal=ordinal, **values))

    by_key = {definition.key: definition for definition in definitions}
    for definition in definitions:
        if definition.logical_type.endswith("_or_null"):
            sibling_key = (definition.entity, f"{definition.field_name}_status")
            sibling = by_key.get(sibling_key)
            if sibling is None:
                _fail(
                    "nullable dictionary field lacks its status sibling",
                    key=list(definition.key),
                )
            if (
                sibling.logical_type != "enum"
                or sibling.allowed_values != TYPED_NUMERIC_STATUS_LITERAL
                or sibling.requirement != "REQ"
            ):
                _fail(
                    "nullable dictionary field has inconsistent status sibling",
                    key=list(definition.key),
                    sibling_key=list(sibling_key),
                )
    return tuple(definitions)


def load_sealed_schema_dictionary(
    path: str | Path | None = None,
) -> SealedSchemaDictionary:
    """Load only the exact 81,353-byte, 469x11 Prompt-0 dictionary.

    The default is package-relative and therefore independent of the process
    working directory and of ``developer_sources`` being installed.

    Every call reads and hashes the physical file. Only the interpretation of
    identical verified bytes is reused; each consumer gets its own mutable view.
    """

    resolved = SCHEMA_DICTIONARY_RUNTIME_PATH if path is None else Path(path)
    try:
        payload = resolved.read_bytes()
    except OSError as exc:
        _fail("sealed schema dictionary is unavailable", path=str(resolved), error=str(exc))
    digest = hashlib.sha256(payload).hexdigest()
    if len(payload) != SCHEMA_DICTIONARY_BYTES or digest != SCHEMA_DICTIONARY_SHA256:
        _fail(
            "sealed schema dictionary bytes/hash mismatch",
            path=str(resolved),
            expected_bytes=SCHEMA_DICTIONARY_BYTES,
            actual_bytes=len(payload),
            expected_sha256=SCHEMA_DICTIONARY_SHA256,
            actual_sha256=digest,
        )
    definitions = _parse_sealed_schema_dictionary_bytes(payload)
    return SealedSchemaDictionary(
        definitions,
        byte_length=len(payload),
        sha256=digest,
    )


@lru_cache(maxsize=1)
def _parse_sealed_schema_dictionary_bytes(
    payload: bytes,
) -> tuple[SchemaFieldDefinition, ...]:
    """Interpret bytes already verified by the loader, caching only frozen rows.

    The key is the complete byte string, never a path or filesystem timestamp.
    Do not cache ``SealedSchemaDictionary`` itself: its indexes and metadata can
    be mutated by callers and must not be shared between loads.
    """

    if payload.startswith(b"\xef\xbb\xbf"):
        _fail("sealed schema dictionary must not contain a UTF-8 BOM")
    if b"\r" in payload or b"\x00" in payload:
        _fail("sealed schema dictionary contains a forbidden byte")
    if payload.count(b"\n") != SCHEMA_DICTIONARY_ROWS + 1 or not payload.endswith(b"\n"):
        _fail("sealed schema dictionary line framing mismatch")
    try:
        text = payload.decode("utf-8", errors="strict")
        parsed = list(csv.reader(io.StringIO(text, newline=""), strict=True))
    except (UnicodeDecodeError, csv.Error) as exc:
        _fail("sealed schema dictionary cannot be parsed", error=str(exc))
    if not parsed or tuple(parsed[0]) != SCHEMA_DICTIONARY_COLUMNS:
        _fail(
            "sealed schema dictionary header mismatch",
            expected=list(SCHEMA_DICTIONARY_COLUMNS),
            actual=parsed[0] if parsed else [],
        )
    if len(parsed) != SCHEMA_DICTIONARY_ROWS + 1:
        _fail(
            "sealed schema dictionary CSV record count mismatch",
            expected=SCHEMA_DICTIONARY_ROWS + 1,
            actual=len(parsed),
        )
    objects: list[dict[str, str]] = []
    for ordinal, values in enumerate(parsed[1:], start=1):
        if len(values) != len(SCHEMA_DICTIONARY_COLUMNS):
            _fail(
                "sealed schema dictionary CSV width mismatch",
                row=ordinal,
                expected=len(SCHEMA_DICTIONARY_COLUMNS),
                actual=len(values),
            )
        objects.append(dict(zip(SCHEMA_DICTIONARY_COLUMNS, values)))
    return validate_schema_dictionary_rows(objects)


def validate_dictionary_bound_emission(
    record: Mapping[str, Any],
    field_entities: Mapping[str, str],
    *,
    dictionary: SealedSchemaDictionary | None = None,
    tsv: bool = False,
) -> tuple[SchemaFieldDefinition, ...]:
    """Validate that every proposed output column is a canonical dictionary field.

    ``field_entities`` is explicit because the same field name occurs under
    multiple dictionary entities.  This routine cannot silently guess ownership.
    It deliberately does not claim that the bindings form the canonical
    ``cavity_objects.tsv`` header; that cross-entity profile is not sealed.
    """

    if not isinstance(record, Mapping) or not isinstance(field_entities, Mapping):
        _fail("emission record and field/entity bindings must be objects")
    if set(record) != set(field_entities):
        _fail(
            "emission fields and dictionary bindings differ",
            unbound_fields=sorted(set(record) - set(field_entities)),
            bindings_without_fields=sorted(set(field_entities) - set(record)),
        )
    assert_canonical_v2_field_names(record)
    sealed = dictionary if dictionary is not None else load_sealed_schema_dictionary()
    definitions: list[SchemaFieldDefinition] = []
    bound_keys: set[tuple[str, str]] = set()
    for field_name in record:
        entity = field_entities[field_name]
        if not isinstance(field_name, str) or not isinstance(entity, str):
            _fail("emission field/entity bindings must be strings")
        definition = sealed.lookup(entity, field_name)
        if not definition.canonical_writer_field:
            _fail(
                "v2 writer attempted to emit a legacy/migration-only dictionary field",
                entity=entity,
                field_name=field_name,
                status=definition.status,
                logical_type=definition.logical_type,
            )
        bound_keys.add(definition.key)
        definitions.append(definition)

        value = record[field_name]
        if definition.logical_type == "boolean":
            if tsv:
                if value not in {"0", "1"}:
                    _fail("TSV boolean must be encoded as 0 or 1", field=field_name, value=value)
            else:
                validate_boolean_01(value, field=field_name)
        elif definition.logical_type == "enum" and value not in definition.allowed_values.split("|"):
            _fail(
                "emitted enum violates the sealed dictionary",
                entity=entity,
                field=field_name,
                value=value,
                allowed_values=definition.allowed_values,
            )

    for definition in definitions:
        if not definition.logical_type.endswith("_or_null"):
            continue
        sibling_key = (definition.entity, f"{definition.field_name}_status")
        if sibling_key not in bound_keys:
            _fail(
                "emitted nullable field lacks its bound status sibling",
                key=list(definition.key),
                sibling_key=list(sibling_key),
            )
        status_value = record[sibling_key[1]]
        value = record[definition.field_name]
        absent = value == "" if tsv else value is None
        if status_value == "KNOWN" and absent:
            _fail("KNOWN emitted value is absent", field=definition.field_name)
        if status_value != "KNOWN" and not absent:
            _fail(
                "non-KNOWN emitted value must be absent",
                field=definition.field_name,
                status=status_value,
            )
        if status_value == "KNOWN" and not tsv and (
            "decimal" in definition.logical_type or "integer" in definition.logical_type
        ):
            require_finite_number(value, field=definition.field_name)
    return tuple(definitions)


def validate_complete_dictionary_entity_record(
    entity: str,
    record: Mapping[str, Any],
    *,
    dictionary: SealedSchemaDictionary | None = None,
    tsv: bool = False,
) -> tuple[SchemaFieldDefinition, ...]:
    """Validate a complete single-entity record against every dictionary REQ field."""

    sealed = dictionary if dictionary is not None else load_sealed_schema_dictionary()
    entity_fields = sealed.fields_for_entity(entity)
    required = {
        definition.field_name
        for definition in entity_fields
        if definition.canonical_writer_field and definition.requirement == "REQ"
    }
    missing = sorted(required - set(record))
    if missing:
        _fail(
            "complete dictionary entity record lacks required fields",
            entity=entity,
            missing=missing,
        )
    return validate_dictionary_bound_emission(
        record,
        {field_name: entity for field_name in record},
        dictionary=sealed,
        tsv=tsv,
    )


def cavity_objects_header(
    *, dictionary: SealedSchemaDictionary | None = None
) -> tuple[str, ...]:
    """Return the exact approved 234-column runtime header.

    Loading re-hashes the physical profile/header and reconciles all 233
    canonical non-X pairs with the sealed dictionary.  ``identity_provenance``
    is the single structured flattening extension at physical column 116.
    """

    from .object_table_profile import (
        DICTIONARY_SHA256,
        IDENTITY_PROVENANCE_ORDINAL,
        load_object_table_profile,
    )

    profile = load_object_table_profile()
    sealed = dictionary if dictionary is not None else load_sealed_schema_dictionary()
    if sealed.sha256 != DICTIONARY_SHA256:
        raise ContractError(
            "object-table profile dictionary authority mismatch",
            details={
                "profile_id": profile.profile["profile_id"],
                "expected_sha256": DICTIONARY_SHA256,
                "observed_sha256": sealed.sha256,
            },
        )
    selected_pairs: set[tuple[str, str]] = set()
    for column in profile.columns:
        if column.ordinal == IDENTITY_PROVENANCE_ORDINAL:
            continue
        if column.source_field_name is None:
            raise ContractError(
                "canonical object-table column lacks a dictionary field binding",
                details={"ordinal": column.ordinal, "output_name": column.output_name},
            )
        definition = sealed.lookup(column.source_entity, column.source_field_name)
        if not definition.canonical_writer_field or (
            definition.status != column.source_status
            or definition.logical_type != column.logical_type
            or definition.requirement != column.requirement
            or definition.field_name != column.output_name
        ):
            raise ContractError(
                "object-table column differs from sealed dictionary authority",
                details={
                    "ordinal": column.ordinal,
                    "entity": column.source_entity,
                    "field_name": column.source_field_name,
                },
            )
        if definition.key in selected_pairs:
            raise ContractError(
                "object-table profile selects a dictionary pair more than once",
                details={"key": list(definition.key)},
            )
        selected_pairs.add(definition.key)
    if len(selected_pairs) != 233:
        raise ContractError(
            "object-table profile does not bind exactly 233 canonical pairs",
            details={"observed": len(selected_pairs), "expected": 233},
        )
    return profile.header
