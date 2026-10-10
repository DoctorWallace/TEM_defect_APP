"""Transactional writer for Prompt-1 RUN v2 packages.

The writer keeps four entities separate:

* ``run_transaction`` -- mutable operational evidence beside ``.partial``;
* ``run_manifest`` -- immutable scientific manifest created exactly once;
* ``run_integrity`` -- external sidecar and ``COMPLETE`` marker;
* ``run_registry`` -- mutable lifecycle/quarantine authority outside the RUN.

No operation in this module migrates a schema-1 project or writes into a real
project unless the caller explicitly supplies that copied project as its root.
"""

from __future__ import annotations

import mimetypes
import os
import re
import uuid
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path, PurePosixPath
from typing import Any, Callable, Mapping, MutableMapping

from .canonical_json import PROFILE_ID, canonical_json_bytes, loads_canonical_json
from .critical_io import (
    ATOMIC_CAPABILITIES,
    AtomicMoveProof,
    CriticalWriteResult,
    RETENTION_POLICY,
    assert_no_blocking_journals,
    critical_replace,
    fsync_directory,
    sha256_bytes,
    sha256_file,
    utc_now_z,
    write_new_file,
)
from .errors import RecoveryBlocked, TransactionError, ValidationError
from .path_safety import (
    PathSafetyError,
    lexical_absolute,
    plain_directory,
    plain_file,
    rename_directory_no_replace,
    rename_file_no_replace,
    stable_plain_bytes,
)
from .run_consumer import (
    POINTER_COLUMNS,
    CurrentRunPointer,
    VerifiedRun,
    _parse_object_table,
    _validate_manifest_core,
    parse_current_run_pointer,
    render_complete_marker,
    render_current_run_pointer,
    render_sidecar,
    resolve_contained,
    validate_relative_path,
    verify_run_directory,
)
from .run_context import RunContractContext, normalize_run_context


TRANSACTION_STATES = (
    "PARTIAL_CREATED",
    "WRITING",
    "VALIDATING",
    "VERIFIED_STAGED",
    "FAILED_PARTIAL",
    "CANCELLED_PARTIAL",
    "INTERRUPTED_PARTIAL",
)
_EMPTY_CURRENT_RUN_POINTER_BYTES = ("\t".join(POINTER_COLUMNS) + "\n").encode("utf-8")
PUBLISHABLE_VALIDATION_STATES = frozenset({"PASS", "PASS_WITH_WARNINGS"})
RUN_LIFECYCLES = frozenset({"CURRENT", "HISTORICAL", "SUPERSEDED", "ARCHIVED"})
QUARANTINE_STATES = frozenset({"ACTIVE", "QUARANTINED"})
CONTROL_SET = frozenset({"run_manifest.json", "RUN_SHA256.txt", "COMPLETE"})

_TX_TRANSITIONS = {
    "PARTIAL_CREATED": {"WRITING", "FAILED_PARTIAL"},
    "WRITING": {"VALIDATING", "FAILED_PARTIAL", "CANCELLED_PARTIAL", "INTERRUPTED_PARTIAL"},
    "VALIDATING": {"VERIFIED_STAGED", "FAILED_PARTIAL", "CANCELLED_PARTIAL", "INTERRUPTED_PARTIAL"},
    "VERIFIED_STAGED": {"FAILED_PARTIAL", "INTERRUPTED_PARTIAL"},
    "FAILED_PARTIAL": set(),
    "CANCELLED_PARTIAL": set(),
    "INTERRUPTED_PARTIAL": set(),
}

FaultHook = Callable[[str, Mapping[str, Any]], None]
ContentValidator = Callable[[Path, Mapping[str, Any]], Any]


def _valid_partial_name(run_id: str, value: Any) -> bool:
    if not isinstance(value, str):
        return False
    return value == f"RUN_{run_id}.partial" or re.fullmatch(
        rf"RUN_{re.escape(run_id)}\.partial\.[0-9a-f]{{32}}",
        value,
    ) is not None


@dataclass(frozen=True)
class ValidationEvidence:
    status: str
    validated_at: str
    fingerprint_sha256: str
    errors: tuple[dict[str, Any], ...] = ()
    warnings: tuple[dict[str, Any], ...] = ()

    def validate_publishable(self) -> None:
        if self.status not in PUBLISHABLE_VALIDATION_STATES:
            raise ValidationError("FAIL/NOT_RUN validation cannot be published", details={"status": self.status})
        if self.errors:
            raise ValidationError("publishable validation must have no errors", details={"errors": list(self.errors)})
        if not re.fullmatch(r"[0-9a-f]{64}", self.fingerprint_sha256):
            raise ValidationError("validation fingerprint is not lowercase SHA-256")
        # Reuse marker rendering's canonical time validation through a harmless
        # temporary construction with known-valid identities.
        render_complete_marker(
            run_id="VALIDATION_PROBE",
            run_uid="00000000-0000-4000-8000-000000000000",
            manifest_sha256="0" * 64,
            completed_at=self.validated_at,
        )


@dataclass(frozen=True)
class PayloadSpec:
    data: bytes
    media_type: str
    authority_role: str

    @classmethod
    def infer(cls, relative_path: str, data: bytes, authority_role: str) -> "PayloadSpec":
        media_type = mimetypes.guess_type(relative_path)[0] or "application/octet-stream"
        if relative_path.endswith(".tsv"):
            media_type = "text/tab-separated-values; charset=utf-8"
        return cls(data=data, media_type=media_type, authority_role=authority_role)


@dataclass(frozen=True)
class DirectoryPublishResult:
    final_path: Path
    atomic_move_capability: str
    quarantine_path: Path | None = None


@dataclass(frozen=True)
class PublishedRun:
    run_path: Path
    manifest_sha256: str
    pointer: CurrentRunPointer
    pointer_write: CriticalWriteResult
    registry_path: Path
    verified: VerifiedRun
    directory_atomic_move_capability: str
    retention_policy: str = RETENTION_POLICY


def _validate_tx_descriptor_path(path: Path) -> None:
    try:
        raw = stable_plain_bytes(path, label="run transaction descriptor")
    except PathSafetyError as exc:
        raise ValidationError(
            "run_transaction descriptor path is unsafe",
            details={"cause": str(exc)},
        ) from exc
    value = loads_canonical_json(raw)
    if value.get("descriptor_type") != "run_transaction" or value.get("transaction_state") not in TRANSACTION_STATES:
        raise ValidationError("run_transaction descriptor schema/state is invalid")
    run_id = value.get("run_id")
    if not isinstance(run_id, str) or not _valid_partial_name(
        run_id,
        value.get("partial_relative_path"),
    ):
        raise ValidationError("run_transaction partial path is invalid")
    state = value["transaction_state"]
    validation_status = value.get("validation_status")
    if state in {"PARTIAL_CREATED", "WRITING"}:
        if (
            validation_status != "NOT_RUN"
            or value.get("validation_at") != "NOT_APPLICABLE"
            or value.get("validation_fingerprint_sha256") != "NOT_APPLICABLE"
        ):
            raise ValidationError("pre-validation descriptor evidence is invalid")
    if state == "VERIFIED_STAGED" and validation_status not in PUBLISHABLE_VALIDATION_STATES:
        raise ValidationError("VERIFIED_STAGED descriptor is not publishable")
    if "run_manifest_sha256" in value:
        raise ValidationError("run_transaction must not contain run manifest hash")


class RunTransaction:
    """Operational state for one sibling private partial directory."""

    def __init__(self, parent: Path, descriptor: dict[str, Any]) -> None:
        self.parent = parent
        self.descriptor = descriptor
        self.run_id = str(descriptor["run_id"])
        self.run_uid = str(descriptor["run_uid"])
        partial_relative_path = descriptor.get(
            "partial_relative_path",
            f"RUN_{self.run_id}.partial",
        )
        if not _valid_partial_name(self.run_id, partial_relative_path):
            raise TransactionError("run transaction partial path is invalid")
        self.partial_path = parent / partial_relative_path
        self.final_path = parent / f"RUN_{self.run_id}"
        self.descriptor_path = parent / f"RUN_{self.run_id}.transaction.json"
        self._descriptor_sha256 = sha256_bytes(canonical_json_bytes(descriptor))

    @classmethod
    def begin(
        cls,
        parent: os.PathLike[str] | str,
        *,
        run_id: str,
        run_uid: str,
        context: Mapping[str, Any] | None = None,
        partial_token: str | None = None,
    ) -> "RunTransaction":
        try:
            root = plain_directory(parent, label="RUN parent")
        except PathSafetyError as exc:
            raise TransactionError("RUN parent is unsafe", details={"parent": str(parent), "cause": str(exc)}) from exc
        # Consumer validates the closed ID/UUID grammar later; validate it now
        # by rendering a syntactically correct marker.
        render_complete_marker(
            run_id=run_id,
            run_uid=run_uid,
            manifest_sha256="0" * 64,
            completed_at=utc_now_z(),
        )
        if partial_token is not None and re.fullmatch(r"[0-9a-f]{32}", partial_token) is None:
            raise TransactionError("native RUN partial transaction token is invalid")
        partial_name = (
            f"RUN_{run_id}.partial.{partial_token}"
            if partial_token is not None
            else f"RUN_{run_id}.partial"
        )
        partial = root / partial_name
        legacy_partial = root / f"RUN_{run_id}.partial"
        final = root / f"RUN_{run_id}"
        descriptor_path = root / f"RUN_{run_id}.transaction.json"
        retained_native_partial = (
            partial_token is not None
            and any(root.glob(f"RUN_{run_id}.partial.*"))
        )
        if (
            partial.exists()
            or partial.is_symlink()
            or (partial_token is not None and (legacy_partial.exists() or legacy_partial.is_symlink()))
            or retained_native_partial
            or final.exists()
            or final.is_symlink()
            or descriptor_path.exists()
            or descriptor_path.is_symlink()
        ):
            raise TransactionError(
                "RUN identity is already reserved",
                details={"partial": str(partial), "final": str(final), "descriptor": str(descriptor_path)},
            )
        partial.mkdir()
        fsync_directory(root)
        now = utc_now_z()
        descriptor: dict[str, Any] = {
            "descriptor_type": "run_transaction",
            "descriptor_version": 1,
            "run_id": run_id,
            "run_uid": run_uid,
            "partial_relative_path": partial.name,
            "transaction_state": "PARTIAL_CREATED",
            "validation_status": "NOT_RUN",
            "validation_at": "NOT_APPLICABLE",
            "validation_fingerprint_sha256": "NOT_APPLICABLE",
            "validation_errors": [],
            "validation_warnings": [],
            "retention_policy": RETENTION_POLICY,
            "created_at": now,
            "updated_at": now,
            "history": [{"state": "PARTIAL_CREATED", "at": now}],
            "context": dict(context or {}),
        }
        critical_replace(
            descriptor_path,
            canonical_json_bytes(descriptor),
            validator=_validate_tx_descriptor_path,
            transaction_id="partial_created",
            expected_target_sha256="NOT_APPLICABLE",
        )
        return cls(root, descriptor)

    @property
    def state(self) -> str:
        return str(self.descriptor["transaction_state"])

    def _persist(self, token: str) -> None:
        data = canonical_json_bytes(self.descriptor)
        result = critical_replace(
            self.descriptor_path,
            data,
            validator=_validate_tx_descriptor_path,
            transaction_id=token,
            expected_target_sha256=self._descriptor_sha256,
        )
        if result.journal_state != "COMMITTED":
            raise TransactionError("run_transaction descriptor update rolled back", details={"state": result.journal_state})
        self._descriptor_sha256 = sha256_bytes(data)

    def transition(
        self,
        new_state: str,
        *,
        validation: ValidationEvidence | None = None,
        errors: list[dict[str, Any]] | None = None,
        warnings: list[dict[str, Any]] | None = None,
    ) -> None:
        current = self.state
        if new_state not in _TX_TRANSITIONS.get(current, set()):
            raise TransactionError("invalid run_transaction transition", details={"current": current, "requested": new_state})
        now = utc_now_z()
        if new_state == "VALIDATING":
            self.descriptor["validation_status"] = "NOT_RUN"
            self.descriptor["validation_at"] = "NOT_APPLICABLE"
            self.descriptor["validation_fingerprint_sha256"] = "NOT_APPLICABLE"
        elif new_state == "VERIFIED_STAGED":
            if validation is None:
                raise TransactionError("VERIFIED_STAGED requires validation evidence")
            validation.validate_publishable()
            self.descriptor["validation_status"] = validation.status
            self.descriptor["validation_at"] = validation.validated_at
            self.descriptor["validation_fingerprint_sha256"] = validation.fingerprint_sha256
            self.descriptor["validation_errors"] = list(validation.errors)
            self.descriptor["validation_warnings"] = list(validation.warnings)
        elif new_state == "FAILED_PARTIAL":
            self.descriptor["validation_status"] = "FAIL"
            self.descriptor["validation_at"] = now
            self.descriptor["validation_fingerprint_sha256"] = "NOT_APPLICABLE"
            self.descriptor["validation_errors"] = list(errors or [])
            self.descriptor["validation_warnings"] = list(warnings or [])
        self.descriptor["transaction_state"] = new_state
        self.descriptor["updated_at"] = now
        self.descriptor["history"].append({"state": new_state, "at": now})
        self._persist(new_state.lower())

    def write_payload(self, relative_path: str, data: bytes) -> tuple[int, str]:
        if self.state == "PARTIAL_CREATED":
            self.transition("WRITING")
        if self.state != "WRITING":
            raise TransactionError("payload may only be written in WRITING", details={"state": self.state})
        relative = validate_relative_path(relative_path, stage="PAYLOAD_WRITE")
        if relative in CONTROL_SET or relative == "run_transaction.json":
            raise TransactionError("payload path is reserved", details={"relative_path": relative})
        path = self.partial_path.joinpath(*PurePosixPath(relative).parts)
        path.parent.mkdir(parents=True, exist_ok=True)
        # Parent directories were just created inside a private partial; reject
        # any link/reparse entry introduced concurrently.
        try:
            resolved_parent = plain_directory(path.parent, label="payload parent")
        except PathSafetyError as exc:
            raise TransactionError(
                "payload parent is unsafe",
                details={"relative_path": relative, "cause": str(exc)},
            ) from exc
        if os.path.commonpath((str(self.partial_path), str(resolved_parent))) != str(self.partial_path):
            raise TransactionError("payload parent escapes partial", details={"relative_path": relative})
        write_new_file(path, data)
        if path.stat().st_size != len(data) or sha256_file(path) != sha256_bytes(data):
            raise TransactionError("closed payload bytes failed verification", details={"relative_path": relative})
        return len(data), sha256_bytes(data)

    def fail(self, exc: BaseException) -> None:
        if self.state in {"FAILED_PARTIAL", "CANCELLED_PARTIAL", "INTERRUPTED_PARTIAL"}:
            return
        if "FAILED_PARTIAL" not in _TX_TRANSITIONS.get(self.state, set()):
            return
        self.transition(
            "FAILED_PARTIAL",
            errors=[{"code": "RUN_WRITE_FAILED", "path": "", "row": None, "column": None, "message": str(exc)}],
        )

    def cancel(self) -> None:
        self.transition("CANCELLED_PARTIAL")

    def interrupt(self) -> None:
        self.transition("INTERRUPTED_PARTIAL")


def _validate_registry_value(value: Mapping[str, Any]) -> None:
    generation = value.get("registry_generation")
    if (
        value.get("registry_version") != 1
        or isinstance(generation, bool)
        or not isinstance(generation, (int, Decimal))
        or generation != int(generation)
        or generation < 0
    ):
        raise ValidationError("run registry schema is invalid")
    runs = value.get("runs")
    if not isinstance(runs, list):
        raise ValidationError("run registry runs is not an array")
    seen: set[str] = set()
    previous = ""
    for item in runs:
        if not isinstance(item, dict):
            raise ValidationError("run registry record is not an object")
        uid = item.get("run_uid")
        if not isinstance(uid, str) or uid in seen or (previous and uid < previous):
            raise ValidationError("run registry is duplicated or unsorted")
        seen.add(uid)
        previous = uid
        if item.get("run_lifecycle") not in RUN_LIFECYCLES or item.get("quarantine_status") not in QUARANTINE_STATES:
            raise ValidationError("run registry lifecycle/quarantine state is invalid")
        required = {
            "project_uid",
            "image_uid",
            "analysis_session_uid",
            "run_uid",
            "run_id",
            "relative_path",
            "run_manifest_sha256",
            "run_lifecycle",
            "quarantine_status",
            "quarantine_reason",
            "quarantined_at",
            "pointer_generation",
            "pointer_updated_at",
            "registered_at",
            "updated_at",
        }
        if set(item) != required:
            raise ValidationError("run registry record fields are not exact", details={"fields": sorted(item)})
        for field in ("project_uid", "image_uid", "analysis_session_uid", "run_uid"):
            try:
                if not isinstance(item[field], str) or str(uuid.UUID(item[field])) != item[field]:
                    raise ValueError
            except ValueError as exc:
                raise ValidationError("run registry UUID is invalid", details={"field": field}) from exc
        validate_relative_path(item["relative_path"], stage="RUN_REGISTRY")
        if not isinstance(item["run_manifest_sha256"], str) or not re.fullmatch(r"[0-9a-f]{64}", item["run_manifest_sha256"]):
            raise ValidationError("run registry manifest hash is invalid")
        if item["quarantine_status"] == "ACTIVE":
            if item["quarantine_reason"] != "NOT_APPLICABLE" or item["quarantined_at"] != "NOT_APPLICABLE":
                raise ValidationError("active RUN has contradictory quarantine evidence")
        elif item["quarantine_reason"] == "NOT_APPLICABLE" or item["quarantined_at"] == "NOT_APPLICABLE":
            raise ValidationError("quarantined RUN lacks reason/time")
        if item["run_lifecycle"] == "CURRENT":
            pointer_generation = item["pointer_generation"]
            if (
                isinstance(pointer_generation, bool)
                or not isinstance(pointer_generation, (int, Decimal))
                or pointer_generation != int(pointer_generation)
                or pointer_generation < 1
                or item["pointer_updated_at"] == "NOT_APPLICABLE"
            ):
                raise ValidationError("CURRENT registry record lacks pointer generation/time")


def _validate_registry_file(path: Path) -> None:
    try:
        raw = stable_plain_bytes(path, label="run registry")
    except PathSafetyError as exc:
        raise ValidationError("run registry path is unsafe", details={"cause": str(exc)}) from exc
    value = loads_canonical_json(raw)
    _validate_registry_value(value)


class RunRegistry:
    """External mutable lifecycle authority; never embedded in a RUN."""

    def __init__(self, path: os.PathLike[str] | str) -> None:
        try:
            self.path = lexical_absolute(path, label="run registry")
            if self.path.exists() or self.path.is_symlink():
                plain_file(self.path, label="run registry", single_link=True)
            else:
                plain_directory(self.path.parent, label="run registry parent")
        except PathSafetyError as exc:
            raise TransactionError("run registry path is unsafe", details={"cause": str(exc)}) from exc
        if self.path.name != "run_registry.json":
            raise TransactionError("run registry must be named run_registry.json")

    def _load_snapshot(self) -> tuple[dict[str, Any], str]:
        if not self.path.exists() and not self.path.is_symlink():
            return (
                {"registry_version": 1, "registry_generation": 0, "runs": []},
                "NOT_APPLICABLE",
            )
        try:
            raw = stable_plain_bytes(self.path, label="run registry")
        except PathSafetyError as exc:
            raise ValidationError("run registry path became unsafe", details={"cause": str(exc)}) from exc
        value = loads_canonical_json(raw)
        _validate_registry_value(value)
        return value, sha256_bytes(raw)

    def load(self) -> dict[str, Any]:
        value, _ = self._load_snapshot()
        return value

    def _store(
        self,
        value: dict[str, Any],
        token: str,
        *,
        expected_target_sha256: str,
    ) -> CriticalWriteResult:
        value["runs"] = sorted(value["runs"], key=lambda item: item["run_uid"])
        value["registry_generation"] = int(value["registry_generation"]) + 1
        evidence_token = f"{token}_{int(value['registry_generation'])}_{uuid.uuid4().hex[:8]}"
        result = critical_replace(
            self.path,
            canonical_json_bytes(value),
            validator=_validate_registry_file,
            transaction_id=evidence_token,
            expected_target_sha256=expected_target_sha256,
        )
        if result.journal_state != "COMMITTED":
            raise TransactionError("run registry update rolled back", details={"state": result.journal_state})
        return result

    def register_historical(
        self,
        *,
        manifest: Mapping[str, Any],
        relative_path: str,
        manifest_sha256: str,
    ) -> CriticalWriteResult:
        value, expected_target_sha256 = self._load_snapshot()
        matches = [item for item in value["runs"] if item.get("run_uid") == manifest["run_uid"]]
        if matches:
            item = matches[0]
            expected = (manifest["run_id"], relative_path, manifest_sha256)
            actual = (item.get("run_id"), item.get("relative_path"), item.get("run_manifest_sha256"))
            if expected != actual:
                raise TransactionError("existing registry identity conflicts with published RUN")
            return self._store(
                value,
                "historical_idempotent",
                expected_target_sha256=expected_target_sha256,
            )
        now = utc_now_z()
        value["runs"].append(
            {
                "project_uid": manifest["project_uid"],
                "image_uid": manifest["image_uid"],
                "analysis_session_uid": manifest["analysis_session_uid"],
                "run_uid": manifest["run_uid"],
                "run_id": manifest["run_id"],
                "relative_path": relative_path,
                "run_manifest_sha256": manifest_sha256,
                "run_lifecycle": "HISTORICAL",
                "quarantine_status": "ACTIVE",
                "quarantine_reason": "NOT_APPLICABLE",
                "quarantined_at": "NOT_APPLICABLE",
                "pointer_generation": "NOT_APPLICABLE",
                "pointer_updated_at": "NOT_APPLICABLE",
                "registered_at": now,
                "updated_at": now,
            }
        )
        return self._store(
            value,
            "register_historical",
            expected_target_sha256=expected_target_sha256,
        )

    def promote_current(self, pointer: CurrentRunPointer) -> CriticalWriteResult:
        value, expected_target_sha256 = self._load_snapshot()
        matches = [item for item in value["runs"] if item.get("run_uid") == pointer.run_uid]
        if len(matches) != 1:
            raise TransactionError("cannot promote unregistered RUN", details={"run_uid": pointer.run_uid})
        target = matches[0]
        if target["quarantine_status"] != "ACTIVE" or target["run_manifest_sha256"] != pointer.run_manifest_sha256:
            raise TransactionError("cannot promote quarantined or hash-conflicting RUN")
        now = utc_now_z()
        for item in value["runs"]:
            if item.get("analysis_session_uid") == pointer.analysis_session_uid and item.get("run_lifecycle") == "CURRENT":
                item["run_lifecycle"] = "HISTORICAL"
                item["updated_at"] = now
        target["run_lifecycle"] = "CURRENT"
        target["pointer_generation"] = pointer.generation
        target["pointer_updated_at"] = pointer.updated_at
        target["updated_at"] = now
        return self._store(
            value,
            "promote_current",
            expected_target_sha256=expected_target_sha256,
        )

    def quarantine(self, run_uid: str, *, reason: str) -> CriticalWriteResult:
        if not reason.strip():
            raise TransactionError("quarantine reason is required")
        value, expected_target_sha256 = self._load_snapshot()
        matches = [item for item in value["runs"] if item.get("run_uid") == run_uid]
        if len(matches) != 1:
            raise TransactionError("registry RUN not found for quarantine", details={"run_uid": run_uid})
        item = matches[0]
        now = utc_now_z()
        item["quarantine_status"] = "QUARANTINED"
        item["quarantine_reason"] = reason
        item["quarantined_at"] = now
        item["updated_at"] = now
        return self._store(
            value,
            "quarantine",
            expected_target_sha256=expected_target_sha256,
        )

    def reconcile_pointer(self, pointer: CurrentRunPointer) -> None:
        value = self.load()
        current = [
            item
            for item in value["runs"]
            if item.get("analysis_session_uid") == pointer.analysis_session_uid
            and item.get("run_lifecycle") == "CURRENT"
            and item.get("quarantine_status") == "ACTIVE"
        ]
        if len(current) != 1:
            raise ValidationError("registry does not contain exactly one active CURRENT RUN")
        item = current[0]
        for field in ("project_uid", "image_uid", "analysis_session_uid", "run_uid", "run_id", "relative_path", "run_manifest_sha256"):
            if item.get(field) != getattr(pointer, field):
                raise ValidationError("registry CURRENT does not reconcile with pointer", details={"field": field})
        if int(item.get("pointer_generation", -1)) != pointer.generation or item.get("pointer_updated_at") != pointer.updated_at:
            raise ValidationError("registry pointer generation/time does not reconcile")


def _validate_native_registry_owner(
    context: RunContractContext,
    registry: Mapping[str, Any],
    *,
    fallback_image_uid: Any = None,
) -> None:
    if not context.is_native_schema2:
        return
    expected_owner = {
        "project_uid": context.project_uid,
        "image_uid": context.image_uid or fallback_image_uid,
        "analysis_session_uid": context.analysis_session_uid,
    }
    for item in registry.get("runs", []):
        for field, expected in expected_owner.items():
            if expected is not None and item.get(field) != expected:
                raise ValidationError(
                    "owning session RUN registry contains a cross-owner record",
                    details={
                        "field": field,
                        "expected": expected,
                        "actual": item.get(field),
                        "run_uid": item.get("run_uid"),
                    },
                )


def _directory_capability(
    parent: Path,
    requested: str,
    proof: AtomicMoveProof | None,
) -> str:
    if requested not in ATOMIC_CAPABILITIES:
        raise TransactionError("invalid directory atomic capability", details={"capability": requested})
    if requested == "UNAVAILABLE":
        return "UNAVAILABLE"
    if requested == "PROVEN_ATOMIC" and proof is not None and proof.is_sufficient_for(parent / "probe"):
        return "PROVEN_ATOMIC"
    return "UNKNOWN"


def publish_directory_no_replace(
    partial: os.PathLike[str] | str,
    final: os.PathLike[str] | str,
    *,
    verifier: Callable[[Path], Any],
    atomic_capability: str = "UNKNOWN",
    atomic_proof: AtomicMoveProof | None = None,
) -> DirectoryPublishResult:
    """Move a sibling partial to a new final name, never replacing a RUN."""

    try:
        partial_path = plain_directory(partial, label="publication partial")
        final_path = lexical_absolute(final, label="publication final")
        plain_directory(final_path.parent, label="publication parent")
    except PathSafetyError as exc:
        raise TransactionError("RUN publication path is unsafe", details={"cause": str(exc)}) from exc
    if partial_path.parent != final_path.parent:
        raise TransactionError("RUN partial/final must be sibling directories")
    if final_path.exists() or final_path.is_symlink():
        raise TransactionError("RUN final already exists; replace is forbidden", details={"final": str(final_path)})
    capability = _directory_capability(partial_path.parent, atomic_capability, atomic_proof)
    try:
        rename_directory_no_replace(partial_path, final_path, error_type=TransactionError)
        fsync_directory(final_path.parent)
    except TransactionError as exc:
        raise TransactionError("RUN directory move failed without replacement", details={"cause": str(exc)}) from exc
    try:
        outcome = verifier(final_path)
        if outcome is False:
            raise ValidationError("published RUN verifier returned false")
    except Exception as exc:
        quarantine = final_path.with_name(final_path.name + f".{uuid.uuid4().hex}.quarantine")
        try:
            rename_directory_no_replace(final_path, quarantine, error_type=TransactionError)
            fsync_directory(quarantine.parent)
        except TransactionError as quarantine_error:
            raise RecoveryBlocked(
                "published RUN is invalid and quarantine rename failed",
                details={"final": str(final_path), "cause": repr(exc), "quarantine_error": repr(quarantine_error)},
            ) from quarantine_error
        raise TransactionError(
            "published RUN failed verification and was quarantined",
            details={"quarantine": str(quarantine), "cause": repr(exc)},
        ) from exc
    return DirectoryPublishResult(final_path=final_path, atomic_move_capability=capability)


def _normalize_payloads(payloads: Mapping[str, PayloadSpec | bytes]) -> dict[str, PayloadSpec]:
    result: dict[str, PayloadSpec] = {}
    for relative_raw, raw_spec in payloads.items():
        relative = validate_relative_path(relative_raw, stage="PAYLOAD_WRITE")
        if relative in result or relative in CONTROL_SET:
            raise TransactionError("duplicate/reserved payload path", details={"relative_path": relative})
        if isinstance(raw_spec, bytes):
            role = "OBJECT_TABLE_AUTHORITY" if relative == "cavity_objects.tsv" else "DERIVED_SUMMARY"
            spec = PayloadSpec.infer(relative, raw_spec, role)
        elif isinstance(raw_spec, PayloadSpec):
            spec = raw_spec
        else:
            raise TypeError("payload values must be bytes or PayloadSpec")
        if not isinstance(spec.data, bytes):
            raise TypeError("PayloadSpec.data must be bytes")
        result[relative] = spec
    if "cavity_objects.tsv" not in result or result["cavity_objects.tsv"].authority_role != "OBJECT_TABLE_AUTHORITY":
        raise ValidationError("payloads require cavity_objects.tsv as OBJECT_TABLE_AUTHORITY")
    return dict(sorted(result.items()))


def _make_file_records(payloads: Mapping[str, PayloadSpec]) -> list[dict[str, Any]]:
    return [
        {
            "relative_path": relative,
            "bytes": len(spec.data),
            "sha256": sha256_bytes(spec.data),
            "media_type": spec.media_type,
            "authority_role": spec.authority_role,
        }
        for relative, spec in payloads.items()
    ]


def _build_manifest(
    manifest_fields: Mapping[str, Any],
    *,
    files: list[dict[str, Any]],
    validation: ValidationEvidence,
    run_context: RunContractContext | None = None,
) -> dict[str, Any]:
    contract_context = normalize_run_context(run_context)
    forbidden = {
        "files",
        "run_manifest_sha256",
        "run_state",
        "serialization_profile",
        "project_schema_version",
        "run_contract_version",
        "source_project_schema_version",
        "session_model_status",
        "project_migration",
        "validation_status",
        "validation_at",
        "validation_fingerprint_sha256",
        "validation_errors",
        "validation_warnings",
    }
    overlap = sorted(forbidden & set(manifest_fields))
    if overlap:
        raise ValidationError("caller may not override sealed manifest fields", details={"fields": overlap})
    manifest = dict(manifest_fields)
    manifest.update(
        {
            "run_state": "COMPLETE",
            "serialization_profile": PROFILE_ID,
            **contract_context.manifest_values,
            "validation_status": validation.status,
            "validation_at": validation.validated_at,
            "validation_fingerprint_sha256": validation.fingerprint_sha256,
            "validation_errors": list(validation.errors),
            "validation_warnings": list(validation.warnings),
            "files": files,
        }
    )
    _validate_manifest_core(manifest, run_context=contract_context)
    # Canonical serialization here also validates semantic array ordering.
    canonical_json_bytes(manifest)
    return manifest


def _pointer_validator(path: Path) -> None:
    try:
        raw = stable_plain_bytes(path, label="current RUN pointer")
    except PathSafetyError as exc:
        raise ValidationError("current RUN pointer is unsafe", details={"cause": str(exc)}) from exc
    parse_current_run_pointer(raw)


def _native_pointer_validator(path: Path) -> None:
    """Validate a P1 pointer or schema-2 pre-first-RUN header placeholder."""

    try:
        raw = stable_plain_bytes(path, label="empty current RUN pointer")
    except PathSafetyError as exc:
        raise ValidationError("empty current RUN pointer is unsafe", details={"cause": str(exc)}) from exc
    if raw == _EMPTY_CURRENT_RUN_POINTER_BYTES:
        return
    parse_current_run_pointer(raw)


def _relative_to_project(project_root: Path, run_path: Path) -> str:
    try:
        relative = run_path.relative_to(project_root).as_posix()
    except ValueError as exc:
        raise TransactionError("published RUN is outside project root") from exc
    validate_relative_path(relative, stage="POINTER_PATH")
    resolve_contained(project_root, relative, stage="POINTER_PATH")
    return relative


def _quarantine_pointer_snapshot(
    pointer_path: Path,
    quarantine_path: Path,
    *,
    expected_sha256: str,
) -> None:
    """Move only the pointer version written by this transaction."""

    try:
        before = stable_plain_bytes(pointer_path, label="pointer quarantine source")
    except PathSafetyError as exc:
        raise RecoveryBlocked(
            "pointer cannot be quarantined from an unsafe source",
            details={"pointer": str(pointer_path), "cause": str(exc)},
        ) from exc
    if sha256_bytes(before) != expected_sha256:
        raise RecoveryBlocked(
            "pointer changed before quarantine; concurrent update preserved",
            details={"pointer": str(pointer_path)},
        )
    rename_file_no_replace(pointer_path, quarantine_path, error_type=TransactionError)
    try:
        moved = stable_plain_bytes(quarantine_path, label="quarantined pointer")
    except PathSafetyError as exc:
        raise RecoveryBlocked(
            "quarantined pointer evidence is unsafe",
            details={"quarantine": str(quarantine_path), "cause": str(exc)},
        ) from exc
    if sha256_bytes(moved) == expected_sha256:
        return
    restored = False
    if not pointer_path.exists() and not pointer_path.is_symlink():
        try:
            rename_file_no_replace(
                quarantine_path,
                pointer_path,
                error_type=TransactionError,
            )
            restored = True
        except TransactionError:
            restored = False
    raise RecoveryBlocked(
        "pointer source changed during quarantine; raced bytes retained",
        details={
            "pointer": str(pointer_path),
            "quarantine": str(quarantine_path),
            "restored": restored,
        },
    )


def _call_fault(hook: FaultHook | None, stage: str, evidence: Mapping[str, Any]) -> None:
    if hook is not None:
        hook(stage, evidence)


def publish_run(
    run_parent: os.PathLike[str] | str,
    *,
    project_root: os.PathLike[str] | str,
    current_pointer_path: os.PathLike[str] | str,
    registry_path: os.PathLike[str] | str,
    run_id: str,
    run_uid: str,
    payloads: Mapping[str, PayloadSpec | bytes],
    manifest_fields: Mapping[str, Any],
    validation: ValidationEvidence,
    content_validator: ContentValidator | None = None,
    run_context: RunContractContext | None = None,
    atomic_capability: str = "UNKNOWN",
    atomic_proof: AtomicMoveProof | None = None,
    _fault: FaultHook | None = None,
) -> PublishedRun:
    """Execute the thirteen-step Prompt-1 publication sequence."""

    contract_context = normalize_run_context(run_context)
    validation.validate_publishable()
    normalized = _normalize_payloads(payloads)
    try:
        root = plain_directory(project_root, label="project root")
        parent = plain_directory(run_parent, label="RUN parent")
        parent.relative_to(root)
        pointer_path = lexical_absolute(current_pointer_path, label="current_run.tsv")
        if pointer_path.exists() or pointer_path.is_symlink():
            pointer_path = plain_file(pointer_path, label="current_run.tsv", single_link=True)
        else:
            plain_directory(pointer_path.parent, label="current_run.tsv parent")
        pointer_path.relative_to(root)
        registry_file = lexical_absolute(registry_path, label="run_registry.json")
        if registry_file.exists() or registry_file.is_symlink():
            registry_file = plain_file(registry_file, label="run_registry.json", single_link=True)
        else:
            plain_directory(registry_file.parent, label="run_registry.json parent")
        registry_file.relative_to(root)
    except (PathSafetyError, ValueError) as exc:
        raise TransactionError("RUN publication control path is unsafe", details={"cause": str(exc)}) from exc
    if pointer_path.name != "current_run.tsv":
        raise TransactionError("authoritative pointer must be current_run.tsv")
    if registry_file.name != "run_registry.json":
        raise TransactionError("external registry must be run_registry.json")
    contract_context.validate_control_paths(
        run_parent=parent,
        resolution_root=root,
        current_pointer_path=pointer_path,
        registry_path=registry_file,
    )
    sealed_context_fields = set(contract_context.manifest_values)
    caller_context_fields = sorted(sealed_context_fields.intersection(manifest_fields))
    if caller_context_fields:
        raise ValidationError(
            "caller may not override the selected RUN context",
            details={"fields": caller_context_fields},
        )
    requested_manifest = dict(manifest_fields)
    requested_manifest.update(contract_context.manifest_values)
    contract_context.validate_manifest_owner(requested_manifest)
    if contract_context.is_native_schema2:
        if manifest_fields.get("run_id") != run_id or manifest_fields.get("run_uid") != run_uid:
            raise ValidationError(
                "native RUN arguments differ from the immutable manifest identity",
                details={
                    "argument_run_id": run_id,
                    "manifest_run_id": manifest_fields.get("run_id"),
                    "argument_run_uid": run_uid,
                    "manifest_run_uid": manifest_fields.get("run_uid"),
                },
            )
        try:
            parsed_run_uid = uuid.UUID(run_uid)
        except (ValueError, AttributeError, TypeError) as exc:
            raise ValidationError("native schema-2 run_uid is invalid") from exc
        if str(parsed_run_uid) != run_uid or parsed_run_uid.version != 4:
            raise ValidationError(
                "native schema-2 run_uid must be a new canonical UUIDv4",
                details={"run_uid": run_uid},
            )
        registry_snapshot = RunRegistry(registry_file).load()
        _validate_native_registry_owner(
            contract_context,
            registry_snapshot,
            fallback_image_uid=manifest_fields.get("image_uid"),
        )
        if any(item.get("run_uid") == run_uid for item in registry_snapshot.get("runs", [])):
            raise ValidationError(
                "native schema-2 run_uid is already present in the owning session registry",
                details={"run_uid": run_uid},
            )
    for control_parent in {parent, pointer_path.parent, registry_file.parent}:
        assert_no_blocking_journals(control_parent)

    try:
        if pointer_path.exists() or pointer_path.is_symlink():
            old_pointer_bytes = stable_plain_bytes(
                pointer_path,
                label="current_run.tsv caller snapshot",
            )
            expected_pointer_sha256 = sha256_bytes(old_pointer_bytes)
        else:
            old_pointer_bytes = None
            expected_pointer_sha256 = "NOT_APPLICABLE"
    except PathSafetyError as exc:
        raise TransactionError(
            "current RUN pointer snapshot is unsafe",
            details={"cause": str(exc)},
        ) from exc
    native_empty_pointer = (
        contract_context.is_native_schema2
        and old_pointer_bytes == _EMPTY_CURRENT_RUN_POINTER_BYTES
    )
    old_pointer = (
        None
        if old_pointer_bytes is None or native_empty_pointer
        else parse_current_run_pointer(old_pointer_bytes)
    )
    if contract_context.is_native_schema2 and old_pointer is not None:
        expected_pointer_owner = {
            "project_uid": contract_context.project_uid,
            "image_uid": contract_context.image_uid or manifest_fields.get("image_uid"),
            "analysis_session_uid": contract_context.analysis_session_uid,
        }
        for field, expected in expected_pointer_owner.items():
            if getattr(old_pointer, field) != expected:
                raise ValidationError(
                    "existing current_run.tsv belongs to a different owner",
                    details={
                        "field": field,
                        "expected": expected,
                        "actual": getattr(old_pointer, field),
                    },
                )

    descriptor_context = {
        key: manifest_fields[key]
        for key in ("project_uid", "image_uid", "analysis_session_uid", "revision_uid")
        if key in manifest_fields
    }
    if contract_context.is_native_schema2:
        descriptor_context.update(
            {
                "run_adapter_id": contract_context.adapter_id,
                "analysis_session_id": contract_context.analysis_session_id,
            }
        )
    tx = RunTransaction.begin(
        parent,
        run_id=run_id,
        run_uid=run_uid,
        context=descriptor_context,
        partial_token=(uuid.uuid4().hex if contract_context.is_native_schema2 else None),
    )
    _call_fault(_fault, "PARTIAL_CREATED", tx.descriptor)
    try:
        for relative, spec in normalized.items():
            tx.write_payload(relative, spec.data)
            _call_fault(_fault, f"PAYLOAD_WRITTEN:{relative}", tx.descriptor)
        tx.transition("VALIDATING")
        records = _make_file_records(normalized)
        manifest = _build_manifest(
            manifest_fields,
            files=records,
            validation=validation,
            run_context=contract_context,
        )
        _parse_object_table(
            normalized["cavity_objects.tsv"].data,
            manifest,
            run_context=contract_context,
        )
        if content_validator is not None:
            outcome = content_validator(tx.partial_path, manifest)
            if outcome is False:
                raise ValidationError("content validator returned false")
        tx.transition("VERIFIED_STAGED", validation=validation)
        _call_fault(_fault, "VERIFIED_STAGED", tx.descriptor)

        manifest_bytes = canonical_json_bytes(manifest)
        _call_fault(_fault, "BEFORE_MANIFEST_HASH", {"partial": str(tx.partial_path)})
        manifest_hash = sha256_bytes(manifest_bytes)
        completed_at = utc_now_z()
        write_new_file(tx.partial_path / "run_manifest.json", manifest_bytes)
        write_new_file(tx.partial_path / "RUN_SHA256.txt", render_sidecar(manifest_hash))
        write_new_file(
            tx.partial_path / "COMPLETE",
            render_complete_marker(
                run_id=run_id,
                run_uid=run_uid,
                manifest_sha256=manifest_hash,
                completed_at=completed_at,
            ),
        )
        # Verify staged controls/inventory without exposing it to consumers.
        verify_run_directory(
            tx.partial_path,
            allow_partial=True,
            run_context=contract_context,
        )
        _call_fault(_fault, "AFTER_COMPLETE_BEFORE_RENAME", {"partial": str(tx.partial_path), "manifest_sha256": manifest_hash})

        directory_result = publish_directory_no_replace(
            tx.partial_path,
            tx.final_path,
            verifier=lambda final: verify_run_directory(
                final,
                run_context=contract_context,
            ),
            atomic_capability=atomic_capability,
            atomic_proof=atomic_proof,
        )
        verified = verify_run_directory(
            directory_result.final_path,
            run_context=contract_context,
        )
        relative_path = _relative_to_project(root, directory_result.final_path)
        registry = RunRegistry(registry_file)
        registry.register_historical(
            manifest=manifest,
            relative_path=relative_path,
            manifest_sha256=manifest_hash,
        )
        _call_fault(_fault, "AFTER_RENAME_BEFORE_POINTER", {"final": str(directory_result.final_path), "lifecycle": "HISTORICAL"})

        if old_pointer is not None:
            if old_pointer.analysis_session_uid != manifest["analysis_session_uid"]:
                raise TransactionError("current pointer belongs to another analysis_session_uid")
            generation = old_pointer.generation + 1
        else:
            generation = 1
        pointer = CurrentRunPointer(
            pointer_version=1,
            project_uid=str(manifest["project_uid"]),
            image_uid=str(manifest["image_uid"]),
            analysis_session_uid=str(manifest["analysis_session_uid"]),
            run_uid=str(manifest["run_uid"]),
            run_id=str(manifest["run_id"]),
            relative_path=relative_path,
            run_manifest_sha256=manifest_hash,
            generation=generation,
            updated_at=utc_now_z(),
        )
        pointer_write = critical_replace(
            pointer_path,
            render_current_run_pointer(pointer),
            validator=(
                _native_pointer_validator
                if contract_context.is_native_schema2
                else _pointer_validator
            ),
            atomic_capability=atomic_capability,
            atomic_proof=atomic_proof,
            transaction_id=f"pointer_{generation}",
            expected_target_sha256=expected_pointer_sha256,
        )
        if pointer_write.journal_state != "COMMITTED":
            raise TransactionError("current_run.tsv replacement rolled back", details={"state": pointer_write.journal_state})
        _call_fault(_fault, "POINTER_COMMITTED_BEFORE_REGISTRY_PROMOTION", pointer.as_dict())
        try:
            registry.promote_current(pointer)
            registry.reconcile_pointer(pointer)
        except Exception as registry_error:
            # Restore the prior pointer bytes when possible.  If no prior
            # pointer existed, retain the new one under a quarantine name and
            # restore prior absence without deleting evidence.
            if old_pointer_bytes is not None:
                rollback = critical_replace(
                    pointer_path,
                    old_pointer_bytes,
                    validator=(
                        _native_pointer_validator
                        if contract_context.is_native_schema2
                        else _pointer_validator
                    ),
                    transaction_id=f"pointer_registry_rollback_{generation}",
                    expected_target_sha256=pointer_write.target_sha256,
                )
                if rollback.journal_state != "COMMITTED":
                    raise RecoveryBlocked("registry promotion failed and prior pointer rollback failed") from registry_error
            else:
                quarantine_pointer = pointer_path.with_name(pointer_path.name + f".{uuid.uuid4().hex}.quarantine")
                _quarantine_pointer_snapshot(
                    pointer_path,
                    quarantine_pointer,
                    expected_sha256=pointer_write.target_sha256,
                )
                fsync_directory(pointer_path.parent)
            raise TransactionError("registry promotion failed; prior pointer restored", details={"cause": repr(registry_error)}) from registry_error

        verified_current = verify_run_directory(
            directory_result.final_path,
            expected_pointer=pointer,
            registry_path=registry_file,
            run_context=contract_context,
        )
        return PublishedRun(
            run_path=directory_result.final_path,
            manifest_sha256=manifest_hash,
            pointer=pointer,
            pointer_write=pointer_write,
            registry_path=registry_file,
            verified=verified_current,
            directory_atomic_move_capability=directory_result.atomic_move_capability,
        )
    except BaseException as exc:
        if isinstance(exc, Exception) and tx.partial_path.exists():
            try:
                tx.fail(exc)
            except Exception:
                pass
        raise


def quarantine_corrupt_run(
    registry_path: os.PathLike[str] | str,
    *,
    run_uid: str,
    reason: str,
    run_context: RunContractContext | None = None,
) -> CriticalWriteResult:
    """Record post-publication corruption without mutating sealed RUN bytes."""

    contract_context = normalize_run_context(run_context)
    contract_context.validate_control_paths(
        registry_path=registry_path,
    )
    registry = RunRegistry(registry_path)
    _validate_native_registry_owner(contract_context, registry.load())
    return registry.quarantine(run_uid, reason=reason)


def inspect_retained_partial(
    parent: os.PathLike[str] | str,
    run_id: str,
    *,
    run_context: RunContractContext | None = None,
) -> dict[str, Any]:
    """Read-only diagnosis of a retained partial; it never auto-publishes/deletes."""

    try:
        root = plain_directory(parent, label="retained partial parent")
    except PathSafetyError as exc:
        raise ValidationError("retained partial parent is unsafe", details={"cause": str(exc)}) from exc
    contract_context = normalize_run_context(run_context)
    contract_context.validate_control_paths(run_parent=root)
    if contract_context.is_native_schema2:
        observed_candidates = sorted(
            root.glob(f"RUN_{run_id}.partial.*"),
            key=lambda path: path.name,
        )
        invalid_candidates = [
            path
            for path in observed_candidates
            if not _valid_partial_name(run_id, path.name)
        ]
        legacy_partial = root / f"RUN_{run_id}.partial"
        if legacy_partial.exists() or legacy_partial.is_symlink():
            invalid_candidates.append(legacy_partial)
        if invalid_candidates:
            raise RecoveryBlocked(
                "retained native RUN partial naming is outside its contract",
                details={
                    "run_id": run_id,
                    "partials": [str(path) for path in invalid_candidates],
                },
            )
        candidates = observed_candidates
        if len(candidates) > 1:
            raise RecoveryBlocked(
                "multiple retained native RUN partials claim one run_id",
                details={"run_id": run_id, "partials": [str(path) for path in candidates]},
            )
        partial = candidates[0] if candidates else root / f"RUN_{run_id}.partial.NOT_FOUND"
    else:
        partial = root / f"RUN_{run_id}.partial"
    descriptor = root / f"RUN_{run_id}.transaction.json"
    result: dict[str, Any] = {
        "retention_policy": RETENTION_POLICY,
        "automatic_delete": False,
        "partial_path": str(partial),
        "partial_exists": partial.is_dir(),
        "descriptor_path": str(descriptor),
        "descriptor_exists": descriptor.is_file(),
        "published": False,
    }
    if descriptor.is_file():
        _validate_tx_descriptor_path(descriptor)
        try:
            descriptor_bytes = stable_plain_bytes(
                descriptor,
                label="retained transaction descriptor",
            )
        except PathSafetyError as exc:
            raise ValidationError(
                "retained transaction descriptor cannot be read safely",
                details={"cause": str(exc)},
            ) from exc
        descriptor_value = loads_canonical_json(descriptor_bytes)
        if contract_context.is_native_schema2:
            descriptor_context = descriptor_value.get("context", {})
            expected_descriptor_owner = {
                "run_adapter_id": contract_context.adapter_id,
                "project_uid": contract_context.project_uid,
                "image_uid": contract_context.image_uid,
                "analysis_session_id": contract_context.analysis_session_id,
                "analysis_session_uid": contract_context.analysis_session_uid,
            }
            for field, expected in expected_descriptor_owner.items():
                if expected is not None and descriptor_context.get(field) != expected:
                    raise RecoveryBlocked(
                        "retained RUN descriptor differs from its verified physical owner",
                        details={
                            "field": field,
                            "expected": expected,
                            "actual": descriptor_context.get(field),
                        },
                    )
        result["descriptor"] = descriptor_value
    if partial.is_dir():
        result["files"] = sorted(path.relative_to(partial).as_posix() for path in partial.rglob("*") if path.is_file())
        if CONTROL_SET.issubset(set(result["files"])):
            try:
                verified = verify_run_directory(
                    partial,
                    allow_partial=True,
                    run_context=contract_context,
                )
            except ValidationError as exc:
                result["sealed_candidate_status"] = "INVALID"
                result["sealed_candidate_error"] = str(exc)
            else:
                result["sealed_candidate_status"] = "VERIFIED_STAGED"
                result["run_manifest_sha256"] = verified.manifest_sha256
    return result
