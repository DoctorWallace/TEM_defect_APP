"""Literal schema-1 project / RUN-contract-2 bridge for Prompt 1."""

from __future__ import annotations

from typing import Any, Mapping

from .contract import normalize_legacy_read_record
from .errors import ValidationError
from .identity import resolve_bridge_session_id


PROJECT_SCHEMA_VERSION = 1
SOURCE_PROJECT_SCHEMA_VERSION = 1
RUN_CONTRACT_VERSION = 2
SESSION_MODEL_STATUS = "LEGACY_SINGLE_SESSION_BRIDGE"
PROJECT_MIGRATION = False

BRIDGE_FIELDS = {
    "project_schema_version": PROJECT_SCHEMA_VERSION,
    "source_project_schema_version": SOURCE_PROJECT_SCHEMA_VERSION,
    "run_contract_version": RUN_CONTRACT_VERSION,
    "session_model_status": SESSION_MODEL_STATUS,
}

# ``project_migration=false`` is an execution/bridge assertion from WP-16, not
# a fifth persisted RUN field: the sealed dictionary contains only the four
# names above.  Keeping it separate prevents a v2 writer from inventing an
# undeclared manifest field.
PROMPT1_EXECUTION_ASSERTIONS = {"project_migration": PROJECT_MIGRATION}


def prompt1_bridge_record() -> dict[str, int | str | bool]:
    """Return a fresh literal bridge record; callers cannot mutate constants."""

    return dict(BRIDGE_FIELDS)


def validate_prompt1_bridge(record: Mapping[str, Any], *, exact: bool = False) -> None:
    """Reject any schema promotion, migration claim, or bridge drift."""

    if not isinstance(record, Mapping):
        raise ValidationError("Prompt-1 bridge must be an object")
    missing = sorted(set(BRIDGE_FIELDS) - set(record))
    if missing:
        raise ValidationError("Prompt-1 bridge fields are missing", details={"missing": missing})
    if exact:
        extra = sorted(set(record) - set(BRIDGE_FIELDS))
        if extra:
            raise ValidationError("Prompt-1 bridge has extra fields", details={"extra": extra})
    for field, expected in BRIDGE_FIELDS.items():
        observed = record[field]
        # bool must not be accepted as integer 0, and int 0 must not be accepted
        # as the literal false migration claim.
        if type(observed) is not type(expected) or observed != expected:
            raise ValidationError(
                "Prompt-1 bridge value mismatch",
                details={"field": field, "expected": expected, "observed": observed},
            )


def build_legacy_session_bridge(image_uid: str, legacy_analysis_session_id: str | None) -> dict[str, Any]:
    """Build a session bridge without rewriting a schema-1 project."""

    return {**prompt1_bridge_record(), **resolve_bridge_session_id(image_uid, legacy_analysis_session_id)}


def read_schema1_record(record: Mapping[str, Any]) -> dict[str, Any]:
    """Apply only the closed, one-way legacy aliases on an in-memory copy."""

    return normalize_legacy_read_record(record)


def assert_run_contract_schema(schema_version: Any) -> None:
    """Clarify that marker ``schema_version=2`` identifies the RUN, not project."""

    if type(schema_version) is not int or schema_version != RUN_CONTRACT_VERSION:
        raise ValidationError(
            "RUN schema_version must identify run_contract_version=2",
            details={"observed": schema_version},
        )


def assert_project_remains_schema1(project_schema_version: Any, *, project_migration: Any) -> None:
    candidate = {
        "project_schema_version": project_schema_version,
        "source_project_schema_version": SOURCE_PROJECT_SCHEMA_VERSION,
        "run_contract_version": RUN_CONTRACT_VERSION,
        "session_model_status": SESSION_MODEL_STATUS,
    }
    validate_prompt1_bridge(candidate, exact=True)
    if type(project_migration) is not bool or project_migration is not PROJECT_MIGRATION:
        raise ValidationError(
            "Prompt-1 execution must assert project_migration=false",
            details={"observed": project_migration},
        )
