"""External scientific-use dispositions for physically immutable RUNs.

The Prompt-1 RUN directory remains byte-for-byte immutable and its existing
trust-chain verifier remains purely physical.  This additive profile records
that a physically valid RUN must not be used scientifically and binds it to a
verified successor without adding bytes to either RUN directory.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, InvalidOperation
import hashlib
import os
from pathlib import Path
import re
import unicodedata
from typing import Any, Iterable, Mapping

from .canonical_json import canonical_json_bytes, loads_canonical_json
from .errors import ValidationError
from .identity import validate_canonical_uuid, validate_human_id
from .path_safety import PathSafetyError, plain_directory, plain_file, stable_plain_bytes


DISPOSITION_SCHEMA = "CTL_RUN_SCIENTIFIC_DISPOSITION_V1"
DISPOSITION_POLICY = "CTL_RUN_SCALE_PROVENANCE_DISPOSITION_V1"
INVALIDATED_DISPOSITION = "INVALIDATED_AND_SUPERSEDED"
SCALE_REASON_CODE = "SPATIAL_SCALE_UNIT_MISLABELLED_AS_NM"
DISPOSITION_DIRECTORY = "run_dispositions"

DISPOSITION_FIELDS = frozenset(
    {
        "affected_outputs",
        "analysis_session_uid",
        "area_factor_error",
        "correct_scale_x_nm_px",
        "correct_scale_y_nm_px",
        "created_at",
        "disposition",
        "image_uid",
        "immutable_run_preserved",
        "linear_factor_error",
        "policy_id",
        "project_uid",
        "raw_fiji_pixel_height",
        "raw_fiji_pixel_width",
        "raw_x_unit",
        "raw_y_unit",
        "reason_code",
        "replacement_run_id",
        "replacement_run_manifest_sha256",
        "replacement_run_uid",
        "revision_id",
        "revision_uid",
        "run_id",
        "run_manifest_sha256",
        "run_uid",
        "schema",
        "scientific_use_allowed",
        "source_sha256",
        "stored_scale_x_nm_px",
        "stored_scale_y_nm_px",
    }
)

SHA256_RE = re.compile(r"^[0-9a-f]{64}$", re.ASCII)
UTC_Z_RE = re.compile(
    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?Z$",
    re.ASCII,
)
DISPOSITION_FILE_RE = re.compile(r"^(RUN_[A-Za-z0-9][A-Za-z0-9._-]{0,59})\.json$", re.ASCII)
RETAINED_STAGE_RE = re.compile(
    r"^\.RUN_[A-Za-z0-9][A-Za-z0-9._-]{0,59}\.json\.partial\.[0-9a-f]{32}$",
    re.ASCII,
)
AFFECTED_OUTPUT_RE = re.compile(r"^[A-Z][A-Z0-9_.:-]{0,127}$", re.ASCII)
POSITIVE_DECIMAL_TEXT_RE = re.compile(
    r"^(?:0\.[0-9]*[1-9]|[1-9][0-9]*(?:\.[0-9]*[1-9])?)$",
    re.ASCII,
)


class ScientificRunRejected(ValidationError):
    """A physically valid RUN is forbidden as a scientific input."""

    code = "REJECT_SCIENTIFICALLY_INVALID_RUN"


@dataclass(frozen=True)
class RunDisposition:
    """One canonical external disposition and its physical identity."""

    value: Mapping[str, Any]
    path: Path | None = None
    sha256: str | None = None

    @property
    def run_id(self) -> str:
        return str(self.value["run_id"])

    @property
    def run_uid(self) -> str:
        return str(self.value["run_uid"])

    @property
    def replacement_run_id(self) -> str:
        return str(self.value["replacement_run_id"])

    @property
    def replacement_run_uid(self) -> str:
        return str(self.value["replacement_run_uid"])


def _require_sha(value: Any, field: str) -> str:
    if not isinstance(value, str) or SHA256_RE.fullmatch(value) is None:
        raise ValidationError(
            "run disposition SHA-256 is not canonical",
            details={"field": field, "value": value},
        )
    return value


def _require_timestamp(value: Any) -> str:
    if not isinstance(value, str) or UTC_Z_RE.fullmatch(value) is None:
        raise ValidationError("run disposition created_at is not canonical UTC Z")
    try:
        datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as exc:
        raise ValidationError("run disposition created_at is not a real time") from exc
    return value


def _positive_decimal_text(value: Any, field: str) -> tuple[str, Decimal]:
    if (
        not isinstance(value, str)
        or POSITIVE_DECIMAL_TEXT_RE.fullmatch(value) is None
    ):
        raise ValidationError(
            "run disposition decimal must be canonical text",
            details={"field": field},
        )
    try:
        decimal = Decimal(value)
    except (InvalidOperation, ValueError) as exc:
        raise ValidationError(
            "run disposition decimal is invalid", details={"field": field}
        ) from exc
    if not decimal.is_finite() or decimal <= 0:
        raise ValidationError(
            "run disposition decimal must be finite and positive",
            details={"field": field},
        )
    return value, decimal


def _decimal_close(actual: Decimal, expected: Decimal) -> bool:
    tolerance = max(Decimal("1e-24"), abs(expected) * Decimal("1e-12"))
    return abs(actual - expected) <= tolerance


def _unit_text(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value or value.strip() != value:
        raise ValidationError("run disposition raw spatial unit is missing", details={"field": field})
    if unicodedata.normalize("NFC", value) != value:
        raise ValidationError(
            "run disposition raw spatial unit is not Unicode NFC",
            details={"field": field},
        )
    return value


def _validate_value(raw: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(raw, Mapping):
        raise ValidationError("run disposition root must be an object")
    value = dict(raw)
    if set(value) != DISPOSITION_FIELDS:
        raise ValidationError(
            "run disposition field inventory is not closed",
            details={
                "missing": sorted(DISPOSITION_FIELDS - set(value)),
                "extra": sorted(set(value) - DISPOSITION_FIELDS),
            },
        )
    exact = {
        "disposition": INVALIDATED_DISPOSITION,
        "immutable_run_preserved": True,
        "policy_id": DISPOSITION_POLICY,
        "reason_code": SCALE_REASON_CODE,
        "schema": DISPOSITION_SCHEMA,
        "scientific_use_allowed": False,
    }
    for field, expected in exact.items():
        if value.get(field) != expected or type(value.get(field)) is not type(expected):
            raise ValidationError(
                "run disposition closed field differs",
                details={"field": field, "expected": expected, "actual": value.get(field)},
            )

    for field in (
        "project_uid",
        "image_uid",
        "analysis_session_uid",
        "revision_uid",
        "run_uid",
        "replacement_run_uid",
    ):
        validate_canonical_uuid(value[field])
    for field in ("revision_id", "run_id", "replacement_run_id"):
        validate_human_id(value[field], field=field)
    if value["run_id"] == value["replacement_run_id"] or value["run_uid"] == value["replacement_run_uid"]:
        raise ValidationError("run disposition replacement identity is not distinct")
    for field in (
        "source_sha256",
        "run_manifest_sha256",
        "replacement_run_manifest_sha256",
    ):
        _require_sha(value[field], field)
    _require_timestamp(value["created_at"])
    _unit_text(value["raw_x_unit"], "raw_x_unit")
    _unit_text(value["raw_y_unit"], "raw_y_unit")

    decimals: dict[str, Decimal] = {}
    for field in (
        "stored_scale_x_nm_px",
        "stored_scale_y_nm_px",
        "raw_fiji_pixel_width",
        "raw_fiji_pixel_height",
        "correct_scale_x_nm_px",
        "correct_scale_y_nm_px",
        "linear_factor_error",
        "area_factor_error",
    ):
        _text, decimals[field] = _positive_decimal_text(value[field], field)
    factor_x = decimals["correct_scale_x_nm_px"] / decimals["stored_scale_x_nm_px"]
    factor_y = decimals["correct_scale_y_nm_px"] / decimals["stored_scale_y_nm_px"]
    if not _decimal_close(factor_x, decimals["linear_factor_error"]) or not _decimal_close(
        factor_y, decimals["linear_factor_error"]
    ):
        raise ValidationError("run disposition linear error factor does not reconcile")
    if not _decimal_close(
        factor_x * factor_y, decimals["area_factor_error"]
    ):
        raise ValidationError("run disposition area error factor does not reconcile")

    outputs = value["affected_outputs"]
    if (
        not isinstance(outputs, list)
        or not outputs
        or any(not isinstance(item, str) or AFFECTED_OUTPUT_RE.fullmatch(item) is None for item in outputs)
        or outputs != sorted(outputs)
        or len(outputs) != len(set(outputs))
    ):
        raise ValidationError("run disposition affected_outputs is not a closed sorted set")
    return value


def render_run_disposition(value: Mapping[str, Any]) -> bytes:
    """Render and self-parse one exact canonical disposition."""

    validated = _validate_value(value)
    data = canonical_json_bytes(validated)
    parsed = parse_run_disposition(data)
    if dict(parsed.value) != validated:
        raise AssertionError("run disposition canonical round-trip changed its value")
    return data


def parse_run_disposition(
    data: bytes,
    *,
    path: Path | None = None,
) -> RunDisposition:
    """Parse canonical JSON and validate the closed disposition profile."""

    if not isinstance(data, bytes):
        raise ValidationError("run disposition input must be bytes")
    value = _validate_value(loads_canonical_json(data))
    expected_name = f"{value['run_id']}.json"
    if path is not None and path.name != expected_name:
        raise ValidationError(
            "run disposition file name differs from run_id",
            details={"expected": expected_name, "actual": path.name},
        )
    return RunDisposition(
        value=value,
        path=path,
        sha256=hashlib.sha256(data).hexdigest(),
    )


def is_run_disposition_file_name(name: str) -> bool:
    return isinstance(name, str) and DISPOSITION_FILE_RE.fullmatch(name) is not None


def _disposition_root(session_root: os.PathLike[str] | str) -> Path:
    session = plain_directory(session_root, label="run disposition session root")
    return session / DISPOSITION_DIRECTORY


def load_run_dispositions(
    session_root: os.PathLike[str] | str,
) -> tuple[RunDisposition, ...]:
    """Read the complete safe disposition directory without mutating it."""

    root = _disposition_root(session_root)
    if not root.exists():
        if root.is_symlink():
            raise ValidationError("run disposition directory is a dangling link")
        return ()
    try:
        root = plain_directory(root, label="run disposition directory")
        entries = sorted(os.scandir(root), key=lambda item: item.name)
    except (PathSafetyError, OSError) as exc:
        raise ValidationError(
            "run disposition directory is unsafe or unreadable",
            details={"path": str(root), "reason": str(exc)},
        ) from exc
    records: list[RunDisposition] = []
    seen_ids: set[str] = set()
    seen_uids: set[str] = set()
    for entry in entries:
        if RETAINED_STAGE_RE.fullmatch(entry.name) is not None:
            # Retained staging is recovery evidence and never authority.
            continue
        if not is_run_disposition_file_name(entry.name):
            raise ValidationError(
                "run disposition directory contains an undeclared entry",
                details={"name": entry.name},
            )
        path = Path(entry.path)
        try:
            checked = plain_file(path, label="run disposition record", single_link=True)
            data = stable_plain_bytes(checked, label="run disposition record")
        except PathSafetyError as exc:
            raise ValidationError(
                "run disposition record is unsafe",
                details={"path": str(path), "reason": str(exc)},
            ) from exc
        record = parse_run_disposition(data, path=checked)
        if record.run_id in seen_ids or record.run_uid in seen_uids:
            raise ValidationError("run disposition identity is duplicated")
        seen_ids.add(record.run_id)
        seen_uids.add(record.run_uid)
        records.append(record)
    records.sort(key=lambda item: item.run_id)
    return tuple(records)


def _run_manifest(run: Any) -> Mapping[str, Any]:
    manifest = getattr(run, "manifest", None)
    if not isinstance(manifest, Mapping):
        raise ValidationError("run disposition verifier requires a physically verified RUN")
    return manifest


def _verified_object_scale_pair(run: Any) -> tuple[Decimal, Decimal] | None:
    """Read one coherent physical scale pair from verified object rows."""

    rows = getattr(run, "object_rows", None)
    if not isinstance(rows, tuple):
        raise ValidationError(
            "run disposition verifier requires verified object-table rows"
        )
    if not rows:
        return None
    pairs: set[tuple[Decimal, Decimal]] = set()
    for index, row in enumerate(rows):
        if not isinstance(row, Mapping):
            raise ValidationError(
                "verified RUN object row is not an object", details={"row": index + 1}
            )
        try:
            scale_x = Decimal(str(row["scale_x_nm_px"]))
            scale_y = Decimal(str(row["scale_y_nm_px"]))
        except (InvalidOperation, KeyError, ValueError) as exc:
            raise ValidationError(
                "verified RUN object row lacks a usable scale pair",
                details={"row": index + 1},
            ) from exc
        if not scale_x.is_finite() or not scale_y.is_finite() or scale_x <= 0 or scale_y <= 0:
            raise ValidationError(
                "verified RUN object row has an invalid scale pair",
                details={"row": index + 1},
            )
        pairs.add((scale_x, scale_y))
    if len(pairs) != 1:
        raise ValidationError("verified RUN object rows mix spatial scales")
    return next(iter(pairs))


def validate_run_binding(disposition: RunDisposition, run: Any) -> None:
    """Bind the invalidated side of a disposition to one verified RUN."""

    manifest = _run_manifest(run)
    expected = {
        "analysis_session_uid": manifest.get("analysis_session_uid"),
        "image_uid": manifest.get("image_uid"),
        "project_uid": manifest.get("project_uid"),
        "revision_id": manifest.get("revision_id"),
        "revision_uid": manifest.get("revision_uid"),
        "run_id": manifest.get("run_id"),
        "run_manifest_sha256": getattr(run, "manifest_sha256", None),
        "run_uid": manifest.get("run_uid"),
        "source_sha256": manifest.get("source_sha256"),
    }
    for field, actual in expected.items():
        if disposition.value.get(field) != actual:
            raise ValidationError(
                "run disposition does not bind the invalidated RUN",
                details={"field": field, "expected": actual, "actual": disposition.value.get(field)},
            )
    pair = _verified_object_scale_pair(run)
    if pair is not None:
        stored_x = _positive_decimal_text(
            disposition.value["stored_scale_x_nm_px"], "stored_scale_x_nm_px"
        )[1]
        stored_y = _positive_decimal_text(
            disposition.value["stored_scale_y_nm_px"], "stored_scale_y_nm_px"
        )[1]
        if not _decimal_close(pair[0], stored_x) or not _decimal_close(pair[1], stored_y):
            raise ValidationError(
                "run disposition stored scale differs from the invalidated RUN object table"
            )


def validate_replacement_binding(disposition: RunDisposition, replacement: Any) -> None:
    """Bind the successor and prove it stays in the same scientific scope."""

    manifest = _run_manifest(replacement)
    expected = {
        "replacement_run_id": manifest.get("run_id"),
        "replacement_run_manifest_sha256": getattr(replacement, "manifest_sha256", None),
        "replacement_run_uid": manifest.get("run_uid"),
    }
    for field, actual in expected.items():
        if disposition.value.get(field) != actual:
            raise ValidationError(
                "run disposition does not bind the replacement RUN",
                details={"field": field, "expected": actual, "actual": disposition.value.get(field)},
            )
    same_scope = {
        "analysis_session_uid": manifest.get("analysis_session_uid"),
        "image_uid": manifest.get("image_uid"),
        "project_uid": manifest.get("project_uid"),
        "revision_id": manifest.get("revision_id"),
        "revision_uid": manifest.get("revision_uid"),
        "source_sha256": manifest.get("source_sha256"),
    }
    for field, actual in same_scope.items():
        if disposition.value.get(field) != actual:
            raise ValidationError(
                "replacement RUN leaves the invalidated scientific scope",
                details={"field": field, "expected": disposition.value.get(field), "actual": actual},
            )
    pair = _verified_object_scale_pair(replacement)
    if pair is not None:
        correct_x = _positive_decimal_text(
            disposition.value["correct_scale_x_nm_px"], "correct_scale_x_nm_px"
        )[1]
        correct_y = _positive_decimal_text(
            disposition.value["correct_scale_y_nm_px"], "correct_scale_y_nm_px"
        )[1]
        if not _decimal_close(pair[0], correct_x) or not _decimal_close(pair[1], correct_y):
            raise ValidationError(
                "run disposition correct scale differs from the replacement RUN object table"
            )


def validate_run_disposition_directory(
    session_root: os.PathLike[str] | str,
    verified_runs: Iterable[Any],
) -> tuple[RunDisposition, ...]:
    """Validate every disposition against a closed set of physical RUNs."""

    runs = tuple(verified_runs)
    by_id = {str(_run_manifest(run).get("run_id")): run for run in runs}
    by_uid = {str(_run_manifest(run).get("run_uid")): run for run in runs}
    if len(by_id) != len(runs) or len(by_uid) != len(runs):
        raise ValidationError("physical RUN identity set is duplicated")
    dispositions = load_run_dispositions(session_root)
    for disposition in dispositions:
        invalid = by_id.get(disposition.run_id)
        replacement = by_id.get(disposition.replacement_run_id)
        if invalid is None or replacement is None:
            raise ValidationError(
                "run disposition references an absent physical RUN",
                details={
                    "run_id": disposition.run_id,
                    "replacement_run_id": disposition.replacement_run_id,
                },
            )
        if by_uid.get(disposition.run_uid) is not invalid or by_uid.get(
            disposition.replacement_run_uid
        ) is not replacement:
            raise ValidationError("run disposition RUN ID/UUID lookup disagrees")
        validate_run_binding(disposition, invalid)
        validate_replacement_binding(disposition, replacement)
    return dispositions


def _session_root_for_run(run: Any) -> Path | None:
    path = getattr(run, "path", None)
    if not isinstance(path, Path):
        try:
            path = Path(path)
        except TypeError:
            return None
    if path.parent.name != "runs":
        return None
    return path.parent.parent


def find_run_disposition(
    run: Any,
    *,
    session_root: os.PathLike[str] | str | None = None,
) -> RunDisposition | None:
    """Find an exact target record; partial identity matches fail closed."""

    root = Path(session_root) if session_root is not None else _session_root_for_run(run)
    if root is None:
        return None
    manifest = _run_manifest(run)
    run_id = str(manifest.get("run_id"))
    run_uid = str(manifest.get("run_uid"))
    run_sha = str(getattr(run, "manifest_sha256", ""))
    candidates = [
        item
        for item in load_run_dispositions(root)
        if item.run_id == run_id
        or item.run_uid == run_uid
        or item.value["run_manifest_sha256"] == run_sha
    ]
    if not candidates:
        return None
    if len(candidates) != 1:
        raise ValidationError("multiple run dispositions match one physical RUN")
    validate_run_binding(candidates[0], run)
    return candidates[0]


def require_scientific_eligibility(
    run: Any,
    *,
    session_root: os.PathLike[str] | str | None = None,
) -> Any:
    """Reject a disposed RUN while returning untouched eligible RUN objects."""

    root = Path(session_root) if session_root is not None else _session_root_for_run(run)
    disposition = find_run_disposition(run, session_root=root)
    if disposition is None:
        if root is None:
            return run
        try:
            from cavity_tem_light_p3.run_science import (
                run_requires_spatial_scale_verification,
                verify_run_against_persisted_scale,
            )

            if not run_requires_spatial_scale_verification(run, session_root=root):
                return run
            verify_run_against_persisted_scale(run, session_root=root)
        except ScientificRunRejected:
            raise
        except (PathSafetyError, ValidationError) as exc:
            reason_code = (
                "SPATIAL_SCALE_EVIDENCE_PATH_UNSAFE"
                if isinstance(exc, PathSafetyError)
                else exc.details.get("reason_code", getattr(exc, "code", None))
            )
            raise ScientificRunRejected(
                "REJECT_SCIENTIFICALLY_INVALID_RUN",
                details={
                    "reason_code": reason_code
                    or "SPATIAL_SCALE_PROVENANCE_MISMATCH",
                    "run_id": _run_manifest(run).get("run_id"),
                    "run_manifest_sha256": getattr(run, "manifest_sha256", None),
                    "run_uid": _run_manifest(run).get("run_uid"),
                    "scientific_use_allowed": False,
                },
            ) from exc
        return run
    raise ScientificRunRejected(
        "REJECT_SCIENTIFICALLY_INVALID_RUN",
        details={
            "disposition": disposition.value["disposition"],
            "disposition_sha256": disposition.sha256,
            "reason_code": disposition.value["reason_code"],
            "replacement_run_id": disposition.value["replacement_run_id"],
            "replacement_run_manifest_sha256": disposition.value[
                "replacement_run_manifest_sha256"
            ],
            "replacement_run_uid": disposition.value["replacement_run_uid"],
            "run_id": disposition.value["run_id"],
            "run_manifest_sha256": disposition.value["run_manifest_sha256"],
            "run_uid": disposition.value["run_uid"],
            "scientific_use_allowed": False,
        },
    )


__all__ = [
    "DISPOSITION_DIRECTORY",
    "DISPOSITION_FIELDS",
    "DISPOSITION_POLICY",
    "DISPOSITION_SCHEMA",
    "INVALIDATED_DISPOSITION",
    "RunDisposition",
    "SCALE_REASON_CODE",
    "ScientificRunRejected",
    "find_run_disposition",
    "is_run_disposition_file_name",
    "load_run_dispositions",
    "parse_run_disposition",
    "render_run_disposition",
    "require_scientific_eligibility",
    "validate_replacement_binding",
    "validate_run_binding",
    "validate_run_disposition_directory",
]
