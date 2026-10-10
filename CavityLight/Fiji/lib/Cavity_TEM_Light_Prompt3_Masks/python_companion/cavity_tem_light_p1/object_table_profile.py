"""Runtime authority for the approved 234-column cavity object table.

The two files loaded here are byte-for-byte copies of the approved contract
supplement.  They are deliberately verified on every load: replacing either
file, changing a newline, or reordering one column is a terminal contract
failure.  There is no R9 header fallback.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

from .errors import ContractError


PROFILE_ID = "CTL_CAVITY_OBJECTS_TSV_PROFILE_V1"
PROFILE_SHA256 = "ce90a7bee957b185f1178232cab99c622c134c574c1e6942cb126174c255657f"
HEADER_SHA256 = "0d78507e225361fe29035cb5131edb88fe6905d843ac680bf817d11dbe1745a5"
HEADER_BYTES = 4998
COLUMN_COUNT = 234
IDENTITY_PROVENANCE_ORDINAL = 116
DICTIONARY_SHA256 = "e4d9f44a31544583d0fad154199f02b8b4642e4e09dd50e79699a8923116af03"

_DATA_DIRECTORY = Path(__file__).resolve().parents[1] / "data"
PROFILE_PATH = _DATA_DIRECTORY / "CTL_CAVITY_OBJECTS_TSV_PROFILE_V1.json"
HEADER_PATH = _DATA_DIRECTORY / "cavity_objects_header.tsv"

_ENTITY_ORDER = (
    "prompt1_bridge",
    "hierarchy",
    "analysis_trace",
    "source",
    "scale",
    "specimen_metadata",
    "policy",
    "revision",
    "object",
    "model_3d",
)
_STRUCTURED_COLUMNS = frozenset(
    {
        "identity_provenance",
        "classification_confidence",
        "canonical_geometry",
        "duplicate_partners",
    }
)


def _contract_failure(message: str, **details: Any) -> None:
    raise ContractError(message, details={"profile_id": PROFILE_ID, **details})


@dataclass(frozen=True)
class ProfileColumn:
    ordinal: int
    output_name: str
    source_entity: str
    source_field_name: str | None
    source_status: str | None
    logical_type: str
    requirement: str
    cell_encoding: str
    kind: str


@dataclass(frozen=True)
class ObjectTableProfile:
    profile: Mapping[str, Any]
    profile_bytes: bytes
    header_bytes: bytes
    columns: tuple[ProfileColumn, ...]

    @property
    def header(self) -> tuple[str, ...]:
        return tuple(column.output_name for column in self.columns)

    @property
    def field_entities(self) -> dict[str, str]:
        return {
            column.output_name: column.source_entity
            for column in self.columns
            if column.output_name != "identity_provenance"
        }


def _read_exact(path: Path, expected_sha256: str, role: str) -> bytes:
    try:
        payload = path.read_bytes()
    except OSError as exc:
        _contract_failure(
            f"runtime {role} authority is absent or unreadable",
            path=str(path),
            error_type=type(exc).__name__,
        )
    observed = hashlib.sha256(payload).hexdigest()
    if observed != expected_sha256:
        _contract_failure(
            f"runtime {role} authority SHA-256 mismatch",
            path=str(path),
            expected_sha256=expected_sha256,
            observed_sha256=observed,
        )
    return payload


def _column(raw: Any, ordinal: int) -> ProfileColumn:
    if not isinstance(raw, dict):
        _contract_failure("profile column is not an object", ordinal=ordinal)
    required = {
        "ordinal",
        "output_name",
        "logical_type",
        "requirement",
        "cell_encoding",
        "kind",
    }
    missing = sorted(required - set(raw))
    if missing:
        _contract_failure("profile column is incomplete", ordinal=ordinal, missing=missing)
    if raw["ordinal"] != ordinal:
        _contract_failure(
            "profile ordinals are not contiguous",
            expected=ordinal,
            observed=raw["ordinal"],
        )
    return ProfileColumn(
        ordinal=ordinal,
        output_name=raw["output_name"],
        source_entity=raw.get("source_entity", "identity_provenance"),
        source_field_name=raw.get("source_field_name"),
        source_status=raw.get("source_status"),
        logical_type=raw["logical_type"],
        requirement=raw["requirement"],
        cell_encoding=raw["cell_encoding"],
        kind=raw["kind"],
    )


def load_object_table_profile() -> ObjectTableProfile:
    """Load and re-verify the physical profile without mutable caching."""

    profile_bytes = _read_exact(PROFILE_PATH, PROFILE_SHA256, "profile")
    header_bytes = _read_exact(HEADER_PATH, HEADER_SHA256, "header")
    if not profile_bytes.endswith(b"\n") or b"\r" in profile_bytes:
        _contract_failure("runtime profile newline encoding differs from authority")
    if len(header_bytes) != HEADER_BYTES or not header_bytes.endswith(b"\n") or b"\r" in header_bytes:
        _contract_failure("runtime header byte/newline profile differs from authority")
    try:
        profile = json.loads(profile_bytes.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        _contract_failure("runtime profile is not valid UTF-8 JSON", error_type=type(exc).__name__)
    if not isinstance(profile, dict) or profile.get("profile_id") != PROFILE_ID:
        _contract_failure("runtime profile identity mismatch")
    raw_columns = profile.get("columns")
    if not isinstance(raw_columns, list) or len(raw_columns) != COLUMN_COUNT:
        _contract_failure(
            "runtime profile column count mismatch",
            expected=COLUMN_COUNT,
            observed=len(raw_columns) if isinstance(raw_columns, list) else None,
        )
    columns = tuple(_column(raw, ordinal) for ordinal, raw in enumerate(raw_columns, 1))
    names = tuple(column.output_name for column in columns)
    if len(names) != len(set(names)):
        _contract_failure("runtime profile contains duplicate output names")
    expected_header = ("\t".join(names) + "\n").encode("utf-8")
    if expected_header != header_bytes:
        _contract_failure("runtime profile columns do not reproduce exact header bytes")
    provenance = columns[IDENTITY_PROVENANCE_ORDINAL - 1]
    if (
        provenance.output_name != "identity_provenance"
        or provenance.cell_encoding != "CTL_JSON_CELL_V1"
        or provenance.kind != "STRUCTURED_FLATTENING"
    ):
        _contract_failure("identity_provenance is not the exact physical column 116")
    structured = {column.output_name for column in columns if column.cell_encoding == "CTL_JSON_CELL_V1"}
    if structured != _STRUCTURED_COLUMNS:
        _contract_failure(
            "structured-cell column set mismatch",
            expected=sorted(_STRUCTURED_COLUMNS),
            observed=sorted(structured),
        )
    canonical = [column for column in columns if column.output_name != "identity_provenance"]
    if len(canonical) != 233 or any(column.source_status == "X" for column in canonical):
        _contract_failure("canonical non-X dictionary selection is not exactly 233 fields")
    observed_entities: list[str] = []
    for column in canonical:
        if not observed_entities or observed_entities[-1] != column.source_entity:
            observed_entities.append(column.source_entity)
    if tuple(observed_entities) != _ENTITY_ORDER:
        _contract_failure(
            "canonical entity blocks are not in approved order",
            expected=list(_ENTITY_ORDER),
            observed=observed_entities,
        )
    physical = profile.get("physical_tsv")
    identity = profile.get("identity_provenance")
    scope = profile.get("scope")
    dictionary = profile.get("dictionary_authority")
    if not isinstance(physical, dict) or (
        physical.get("column_count") != COLUMN_COUNT
        or physical.get("header_bytes") != HEADER_BYTES
        or physical.get("header_sha256") != HEADER_SHA256
        or physical.get("encoding") != "UTF-8"
        or physical.get("field_separator") != "HT"
        or physical.get("line_separator") != "LF"
        or physical.get("final_lf") != "EXACTLY_ONE"
        or physical.get("quoting") != "FORBIDDEN"
    ):
        _contract_failure("physical TSV profile metadata mismatch")
    if not isinstance(identity, dict) or identity.get("physical_column") != IDENTITY_PROVENANCE_ORDINAL:
        _contract_failure("identity provenance ordinal metadata mismatch")
    if not isinstance(dictionary, dict) or (
        dictionary.get("sha256") != DICTIONARY_SHA256
        or dictionary.get("selected_canonical_pair_count") != 233
    ):
        _contract_failure("dictionary authority binding mismatch")
    if not isinstance(scope, dict) or (
        scope.get("defect_type") != ["CAVITY"]
        or scope.get("measurement_protocol")
        != ["CAVITY_CIRCLE", "CAVITY_ELLIPSE", "CAVITY_CONTOUR"]
        or scope.get("model_3d") != "NONE"
        or scope.get("model_3d_status") != "NOT_MODELLED"
        or scope.get("model_uncertainty") != "NOT_APPLICABLE"
    ):
        _contract_failure("runtime scope is not CAVITY-only without 3-D models")
    for index, column in enumerate(columns[:-1]):
        if column.logical_type.endswith("_or_null"):
            sibling = columns[index + 1]
            if (
                sibling.output_name != f"{column.output_name}_status"
                or sibling.source_entity != column.source_entity
            ):
                _contract_failure(
                    "nullable field/status pair is not physically indivisible",
                    field=column.output_name,
                    ordinal=column.ordinal,
                )
    return ObjectTableProfile(
        profile=profile,
        profile_bytes=profile_bytes,
        header_bytes=header_bytes,
        columns=columns,
    )
