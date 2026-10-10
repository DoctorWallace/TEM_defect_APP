"""Fail-closed persistence for mutable Prompt-1 control files.

The scientific payloads and immutable RUN/revision directories use exclusive
creation.  Mutable control files (pointers and the external registry) use the
journalled protocol implemented here.  A successful operation deliberately
keeps its journal and backup: Prompt 1 applies ``RETAIN_NO_AUTOMATIC_DELETE``.

``PROVEN_ATOMIC`` is never inferred from the platform name or from a successful
``os.replace`` alone.  It requires an :class:`AtomicMoveProof` supplied by the
caller after an observed capability test on the same filesystem.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import unicodedata
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping

from .errors import RecoveryBlocked, TransactionError, ValidationError
from .path_safety import (
    PathSafetyError,
    lexical_absolute,
    plain_directory,
    plain_file,
    reject_reparse_chain,
    rename_file_no_replace,
    stable_plain_bytes,
)


JOURNAL_STATES = (
    "PREPARED",
    "BACKUP_VERIFIED",
    "TARGET_REPLACED",
    "TARGET_VERIFIED",
    "COMMITTED",
    "ROLLBACK_REQUIRED",
    "ROLLED_BACK",
    "RECOVERY_BLOCKED",
)
TERMINAL_JOURNAL_STATES = frozenset({"COMMITTED", "ROLLED_BACK", "RECOVERY_BLOCKED"})
ATOMIC_CAPABILITIES = frozenset({"PROVEN_ATOMIC", "UNAVAILABLE", "UNKNOWN"})
RETENTION_POLICY = "RETAIN_NO_AUTOMATIC_DELETE"
RFC3339_UTC_RE = re.compile(
    r"[0-9]{4}-(?:0[1-9]|1[0-2])-(?:0[1-9]|[12][0-9]|3[01])T"
    r"(?:[01][0-9]|2[0-3]):[0-5][0-9]:[0-5][0-9](?:\.[0-9]{1,6})?Z\Z",
    re.ASCII,
)
_JOURNAL_BASE_KEYS = frozenset(
    {
        "atomic_move_capability",
        "backup_relative_path",
        "created_at",
        "history",
        "journal_state",
        "journal_version",
        "new_target_sha256",
        "old_target_existed",
        "old_target_sha256",
        "quarantine_relative_path",
        "retention_policy",
        "target_relative_path",
        "temp_relative_path",
        "updated_at",
    }
)
_JOURNAL_EVIDENCE_KEYS = frozenset(
    {
        "backup_sha256",
        "committed_target_sha256",
        "conflict_detected",
        "identical_bytes_ambiguous",
        "observed_target_sha256",
        "quarantined_path",
        "recovered_from_hashes",
        "recovered_old_state",
        "recovered_target_sha256",
        "recovery_error",
        "recovery_hash_mismatch",
        "replace_error",
        "rollback_verified",
        "target_untouched_by_writer",
        "verified_target_sha256",
    }
)
_TRUE_EVIDENCE_KEYS = frozenset(
    {
        "conflict_detected",
        "identical_bytes_ambiguous",
        "recovered_from_hashes",
        "recovered_old_state",
        "recovery_hash_mismatch",
        "rollback_verified",
        "target_untouched_by_writer",
    }
)
_TARGET_HASH_EVIDENCE_KEYS = frozenset(
    {
        "committed_target_sha256",
        "recovered_target_sha256",
        "verified_target_sha256",
    }
)

_NORMAL_FORWARD = {
    "PREPARED": {"BACKUP_VERIFIED", "ROLLBACK_REQUIRED"},
    "BACKUP_VERIFIED": {"TARGET_REPLACED", "ROLLBACK_REQUIRED"},
    "TARGET_REPLACED": {"TARGET_VERIFIED", "ROLLBACK_REQUIRED"},
    "TARGET_VERIFIED": {"COMMITTED", "ROLLBACK_REQUIRED"},
    "ROLLBACK_REQUIRED": {"ROLLED_BACK", "RECOVERY_BLOCKED"},
    "COMMITTED": set(),
    "ROLLED_BACK": set(),
    "RECOVERY_BLOCKED": set(),
}

Validator = Callable[[Path], Any]
FaultHook = Callable[[str, Mapping[str, Any]], None]


def utc_now_z() -> str:
    """Return canonical RFC3339 UTC with no redundant fractional zeroes."""

    value = datetime.now(timezone.utc)
    fraction = f"{value.microsecond:06d}".rstrip("0")
    base = value.strftime("%Y-%m-%dT%H:%M:%S")
    return f"{base}.{fraction}Z" if fraction else f"{base}Z"


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: os.PathLike[str] | str) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _assert_plain_parent(target: Path) -> None:
    try:
        absolute = lexical_absolute(target, label="critical target")
        plain_directory(absolute.parent, label="critical target parent")
        reject_reparse_chain(absolute, label="critical target", must_exist=False)
    except PathSafetyError as exc:
        raise TransactionError(
            "critical target path is unsafe",
            details={"target": str(target), "cause": str(exc)},
        ) from exc


def _fsync_handle(handle: Any) -> None:
    handle.flush()
    os.fsync(handle.fileno())


def fsync_directory(path: os.PathLike[str] | str) -> None:
    """Best-effort directory fsync; unsupported platforms remain conservative."""

    directory = Path(path)
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
    try:
        descriptor = os.open(str(directory), flags)
    except (OSError, AttributeError):
        return
    try:
        os.fsync(descriptor)
    except OSError:
        pass
    finally:
        os.close(descriptor)


def write_new_file(path: os.PathLike[str] | str, data: bytes) -> None:
    """Create one plain sibling file exclusively, close it, and force its bytes."""

    try:
        file_path = lexical_absolute(path, label="new file")
    except PathSafetyError as exc:
        raise TransactionError("new file path is unsafe", details={"cause": str(exc)}) from exc
    _assert_plain_parent(file_path)
    with file_path.open("xb") as handle:
        handle.write(data)
        _fsync_handle(handle)
    try:
        plain_file(file_path, label="new file", single_link=True)
    except PathSafetyError as exc:
        raise TransactionError(
            "new file did not close as a plain single-link file",
            details={"path": str(file_path), "cause": str(exc)},
        ) from exc
    fsync_directory(file_path.parent)


@dataclass(frozen=True)
class AtomicMoveProof:
    """Evidence that an atomic replace was observed on this filesystem."""

    api: str
    filesystem_identity: str
    probe_path: str
    observed_success: bool
    observed_at: str

    def is_sufficient_for(self, target: Path) -> bool:
        if not self.observed_success or not self.api or not self.filesystem_identity:
            return False
        try:
            probe = Path(self.probe_path).resolve(strict=True)
            parent = target.parent.resolve(strict=True)
            return probe.stat().st_dev == parent.stat().st_dev
        except OSError:
            return False


@dataclass(frozen=True)
class CriticalWritePaths:
    target: Path
    temp: Path
    backup: Path
    journal: Path
    quarantine: Path


@dataclass(frozen=True)
class CriticalWriteResult:
    target: Path
    journal: Path
    backup: Path
    target_sha256: str
    journal_state: str
    atomic_move_capability: str
    retention_policy: str = RETENTION_POLICY


def sibling_paths(target: os.PathLike[str] | str, transaction_id: str | None = None) -> CriticalWritePaths:
    # ``abspath`` makes the location explicit without following a pre-existing
    # target symlink/reparse point (``Path.resolve`` would hide that evidence).
    target_path = Path(os.path.abspath(os.fspath(target)))
    token = transaction_id or uuid.uuid4().hex
    if not token or any(not (ch.isascii() and (ch.isalnum() or ch in "-_")) for ch in token):
        raise TransactionError("invalid transaction id", details={"transaction_id": token})
    prefix = f".{target_path.name}.{token}"
    return CriticalWritePaths(
        target=target_path,
        temp=target_path.with_name(prefix + ".tmp"),
        backup=target_path.with_name(prefix + ".bak"),
        journal=target_path.with_name(prefix + ".journal.json"),
        quarantine=target_path.with_name(prefix + ".quarantine"),
    )


def _journal_bytes(journal: Mapping[str, Any]) -> bytes:
    text = json.dumps(journal, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return (unicodedata.normalize("NFC", text) + "\n").encode("utf-8")


def _reject_duplicate_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            raise ValueError(f"duplicate JSON key: {key}")
        value[key] = item
    return value


def _reject_json_constant(value: str) -> Any:
    raise ValueError(f"non-RFC8259 constant: {value}")


def _valid_utc_timestamp(value: Any) -> bool:
    if not isinstance(value, str) or RFC3339_UTC_RE.fullmatch(value) is None:
        return False
    try:
        datetime.strptime(
            value,
            "%Y-%m-%dT%H:%M:%S.%fZ" if "." in value else "%Y-%m-%dT%H:%M:%SZ",
        )
    except ValueError:
        return False
    return True


def _canonical_hash(value: Any) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value)
    )


def _validate_evidence_field(
    field: str,
    evidence_value: Any,
    journal: Mapping[str, Any],
) -> bool:
    """Validate evidence types and their authoritative hash relationships."""

    if field == "atomic_move_capability":
        return evidence_value in ATOMIC_CAPABILITIES
    if field in _TRUE_EVIDENCE_KEYS:
        return evidence_value is True
    if field in _TARGET_HASH_EVIDENCE_KEYS:
        return evidence_value == journal.get("new_target_sha256")
    if field == "backup_sha256":
        expected = (
            journal.get("old_target_sha256")
            if journal.get("old_target_existed") is True
            else "NOT_APPLICABLE"
        )
        return evidence_value == expected
    if field == "observed_target_sha256":
        return evidence_value == "NOT_APPLICABLE" or _canonical_hash(evidence_value)
    if field in {"recovery_error", "replace_error"}:
        return isinstance(evidence_value, str) and bool(evidence_value)
    if field == "quarantined_path":
        return isinstance(evidence_value, str) and (
            evidence_value == "NOT_APPLICABLE" or Path(evidence_value).is_absolute()
        )
    return False


def _persist_journal(path: Path, journal: dict[str, Any]) -> None:
    # Updating the recovery journal must itself avoid direct truncation.  This
    # one-level helper intentionally does not recurse into another journal.
    existed = path.exists() or path.is_symlink()
    if existed:
        try:
            plain_file(path, label="critical-write journal", single_link=True)
        except PathSafetyError as exc:
            raise TransactionError(
                "critical-write journal is unsafe",
                details={"path": str(path), "cause": str(exc)},
            ) from exc
    temp = path.with_name(path.name + ".next")
    data = _journal_bytes(journal)
    if temp.exists() or temp.is_symlink():
        # A prior interrupted journal update is evidence; select a fresh name.
        temp = path.with_name(path.name + f".next.{uuid.uuid4().hex}")
    write_new_file(temp, data)
    if existed:
        os.replace(temp, path)
    else:
        rename_file_no_replace(temp, path, error_type=TransactionError)
    try:
        persisted = stable_plain_bytes(path, label="critical-write journal")
    except PathSafetyError as exc:
        raise TransactionError(
            "critical-write journal publication is unsafe",
            details={"path": str(path), "cause": str(exc)},
        ) from exc
    if persisted != data:
        raise TransactionError(
            "critical-write journal publication bytes differ",
            details={"path": str(path)},
        )
    fsync_directory(path.parent)


def _new_journal(paths: CriticalWritePaths, new_hash: str, old_hash: str | None) -> dict[str, Any]:
    now = utc_now_z()
    return {
        "journal_version": 1,
        "target_relative_path": paths.target.name,
        "temp_relative_path": paths.temp.name,
        "backup_relative_path": paths.backup.name,
        "quarantine_relative_path": paths.quarantine.name,
        "new_target_sha256": new_hash,
        "old_target_sha256": old_hash if old_hash is not None else "NOT_APPLICABLE",
        "old_target_existed": old_hash is not None,
        "atomic_move_capability": "UNKNOWN",
        "retention_policy": RETENTION_POLICY,
        "journal_state": "PREPARED",
        "history": [{"journal_state": "PREPARED", "at": now}],
        "created_at": now,
        "updated_at": now,
    }


def _transition(path: Path, journal: dict[str, Any], state: str, **evidence: Any) -> None:
    if state not in JOURNAL_STATES:
        raise TransactionError("unknown journal state", details={"state": state})
    current = journal["journal_state"]
    if state not in _NORMAL_FORWARD.get(current, set()):
        raise TransactionError(
            "non-monotonic journal transition",
            details={"current": current, "requested": state},
        )
    now = utc_now_z()
    entry: dict[str, Any] = {"journal_state": state, "at": now}
    if evidence:
        entry["evidence"] = evidence
        journal.update(evidence)
    journal["journal_state"] = state
    journal["updated_at"] = now
    journal["history"].append(entry)
    _persist_journal(path, journal)


def _call_fault(hook: FaultHook | None, state: str, journal: Mapping[str, Any]) -> None:
    # Private test seam.  Production callers do not receive a public fault
    # injection mode; tests use it only inside TemporaryDirectory fixtures.
    if hook is not None:
        hook(state, journal)


def _validate_exact(path: Path, expected_hash: str, validator: Validator) -> None:
    try:
        plain_file(path, label="critical file", single_link=True)
    except PathSafetyError as exc:
        raise ValidationError(
            "critical file is absent or unsafe",
            details={"path": str(path), "cause": str(exc)},
        ) from exc
    actual_hash = sha256_file(path)
    if actual_hash != expected_hash:
        raise ValidationError(
            "critical file hash mismatch",
            details={"path": str(path), "expected": expected_hash, "actual": actual_hash},
        )
    outcome = validator(path)
    if outcome is False:
        raise ValidationError("critical file validator returned false", details={"path": str(path)})


def _stable_plain_bytes(path: Path, *, label: str) -> bytes:
    """Read a single-link control file and reject a concurrent path swap."""

    try:
        return stable_plain_bytes(path, label=label)
    except PathSafetyError as exc:
        raise TransactionError(
            f"{label} cannot be read as a stable single-link file",
            details={"path": str(path), "cause": str(exc)},
        ) from exc


def _capability_for(target: Path, requested: str, proof: AtomicMoveProof | None) -> str:
    if requested not in ATOMIC_CAPABILITIES:
        raise TransactionError("invalid atomic capability", details={"capability": requested})
    if requested == "UNAVAILABLE":
        return "UNAVAILABLE"
    if requested == "PROVEN_ATOMIC" and proof is not None and proof.is_sufficient_for(target):
        return "PROVEN_ATOMIC"
    return "UNKNOWN"


def _move_target_to_quarantine(paths: CriticalWritePaths) -> Path | None:
    if not paths.target.exists() and not paths.target.is_symlink():
        return None
    quarantine = paths.quarantine
    if quarantine.exists():
        quarantine = quarantine.with_name(quarantine.name + f".{uuid.uuid4().hex}")
    rename_file_no_replace(paths.target, quarantine, error_type=TransactionError)
    fsync_directory(paths.target.parent)
    return quarantine


def _rollback(paths: CriticalWritePaths, journal: dict[str, Any], validator: Validator) -> CriticalWriteResult:
    try:
        quarantined = _move_target_to_quarantine(paths)
        if journal["old_target_existed"]:
            old_hash = journal["old_target_sha256"]
            _validate_exact(paths.backup, old_hash, validator)
            restore = paths.target.with_name(paths.target.name + f".restore.{uuid.uuid4().hex}")
            backup_bytes = _stable_plain_bytes(paths.backup, label="critical backup")
            if sha256_bytes(backup_bytes) != old_hash:
                raise ValidationError("critical backup changed before rollback")
            write_new_file(restore, backup_bytes)
            rename_file_no_replace(restore, paths.target, error_type=TransactionError)
            fsync_directory(paths.target.parent)
            _validate_exact(paths.target, old_hash, validator)
        elif paths.target.exists() or paths.target.is_symlink():
            raise ValidationError("rollback could not restore prior absence")
        _transition(
            paths.journal,
            journal,
            "ROLLED_BACK",
            rollback_verified=True,
            quarantined_path=str(quarantined) if quarantined else "NOT_APPLICABLE",
        )
        return CriticalWriteResult(
            target=paths.target,
            journal=paths.journal,
            backup=paths.backup,
            target_sha256=journal["old_target_sha256"],
            journal_state="ROLLED_BACK",
            atomic_move_capability=journal["atomic_move_capability"],
        )
    except Exception as exc:
        try:
            _transition(paths.journal, journal, "RECOVERY_BLOCKED", recovery_error=repr(exc))
        except Exception:
            pass
        raise RecoveryBlocked(
            "critical target cannot be verified or rolled back; evidence retained",
            details={"target": str(paths.target), "journal": str(paths.journal), "cause": repr(exc)},
        ) from exc


def critical_replace(
    target: os.PathLike[str] | str,
    data: bytes,
    *,
    validator: Validator,
    atomic_capability: str = "UNKNOWN",
    atomic_proof: AtomicMoveProof | None = None,
    transaction_id: str | None = None,
    expected_target_sha256: str | None = None,
    _fault: FaultHook | None = None,
) -> CriticalWriteResult:
    """Replace a mutable file through a retained, hash-recoverable journal.

    ``validator`` is run against the closed/reopened temp, backup (when one
    exists), and final target.  It must parse and validate the file's schema in
    addition to any caller-specific identity checks.
    """

    if not isinstance(data, bytes):
        raise TypeError("critical_replace data must be bytes")
    if expected_target_sha256 is not None and (
        expected_target_sha256 != "NOT_APPLICABLE"
        and not _canonical_hash(expected_target_sha256)
    ):
        raise TransactionError(
            "expected target SHA-256 is malformed",
            details={"expected_target_sha256": expected_target_sha256},
        )
    paths = sibling_paths(target, transaction_id)
    _assert_plain_parent(paths.target)
    for evidence_path in (paths.temp, paths.backup, paths.journal, paths.quarantine):
        if evidence_path.exists() or evidence_path.is_symlink():
            raise RecoveryBlocked(
                "critical write evidence path already exists",
                details={"path": str(evidence_path)},
            )
    old_bytes: bytes | None = None
    if paths.target.exists() or paths.target.is_symlink():
        old_bytes = _stable_plain_bytes(paths.target, label="critical target")

    new_hash = sha256_bytes(data)
    old_hash = sha256_bytes(old_bytes) if old_bytes is not None else None
    observed_old = old_hash if old_hash is not None else "NOT_APPLICABLE"
    if expected_target_sha256 is not None and observed_old != expected_target_sha256:
        raise TransactionError(
            "critical target no longer matches caller snapshot",
            details={
                "target": str(paths.target),
                "expected": expected_target_sha256,
                "observed": observed_old,
            },
        )
    write_new_file(paths.temp, data)
    _validate_exact(paths.temp, new_hash, validator)
    journal = _new_journal(paths, new_hash, old_hash)
    _persist_journal(paths.journal, journal)
    _call_fault(_fault, "PREPARED", journal)

    if old_hash is not None:
        # Atomically claim the mutable target name by moving the exact current
        # file to the retained backup with a true no-replace primitive.  A
        # check followed by ``os.replace`` cannot implement CAS: another
        # writer could update the name in that gap and be overwritten.  Here a
        # pre-claim update moves with the name and is detected by its hash; a
        # post-claim creator wins because publication is also no-replace.
        try:
            rename_file_no_replace(
                paths.target,
                paths.backup,
                error_type=TransactionError,
            )
            fsync_directory(paths.target.parent)
            claimed_bytes = _stable_plain_bytes(
                paths.backup,
                label="claimed critical target backup",
            )
        except Exception as exc:
            observed = "NOT_APPLICABLE"
            if paths.target.exists() or paths.target.is_symlink():
                try:
                    observed = sha256_bytes(
                        _stable_plain_bytes(paths.target, label="conflicting critical target")
                    )
                except Exception:
                    observed = "NOT_APPLICABLE"
            _transition(
                paths.journal,
                journal,
                "ROLLBACK_REQUIRED",
                conflict_detected=True,
                observed_target_sha256=observed,
            )
            _transition(
                paths.journal,
                journal,
                "RECOVERY_BLOCKED",
                recovery_error="critical target could not be claimed without replacement",
            )
            raise RecoveryBlocked(
                "critical target changed or its claim destination was reserved",
                details={"target": str(paths.target), "cause": repr(exc)},
            ) from exc
        claimed_hash = sha256_bytes(claimed_bytes)
        if claimed_hash != old_hash:
            # The name changed after the caller snapshot but before the atomic
            # claim.  Restore those concurrent bytes only when the name is
            # still absent; never overwrite a later creator.
            restored = False
            if not paths.target.exists() and not paths.target.is_symlink():
                try:
                    rename_file_no_replace(
                        paths.backup,
                        paths.target,
                        error_type=TransactionError,
                    )
                    fsync_directory(paths.target.parent)
                    restored = True
                except Exception:
                    restored = False
            _transition(
                paths.journal,
                journal,
                "ROLLBACK_REQUIRED",
                conflict_detected=True,
                observed_target_sha256=claimed_hash,
            )
            _transition(
                paths.journal,
                journal,
                "RECOVERY_BLOCKED",
                recovery_error=(
                    "concurrent target bytes were restored after claim mismatch"
                    if restored
                    else "claim mismatch retained for manual recovery"
                ),
            )
            raise RecoveryBlocked(
                "critical target changed between caller snapshot and atomic claim",
                details={
                    "target": str(paths.target),
                    "expected": old_hash,
                    "observed": claimed_hash,
                    "concurrent_target_restored": restored,
                },
            )
        _validate_exact(paths.backup, old_hash, validator)
        backup_hash: str = old_hash
    else:
        backup_hash = "NOT_APPLICABLE"
    _transition(paths.journal, journal, "BACKUP_VERIFIED", backup_sha256=backup_hash)
    _call_fault(_fault, "BACKUP_VERIFIED", journal)

    capability = _capability_for(paths.target, atomic_capability, atomic_proof)
    journal["atomic_move_capability"] = capability
    try:
        try:
            rename_file_no_replace(paths.temp, paths.target, error_type=TransactionError)
        except Exception as exc:
            if paths.target.exists() or paths.target.is_symlink():
                _transition(
                    paths.journal,
                    journal,
                    "ROLLBACK_REQUIRED",
                    replace_error=repr(exc),
                )
                _transition(
                    paths.journal,
                    journal,
                    "RECOVERY_BLOCKED",
                    recovery_error="a concurrent creator won the no-replace target publication",
                )
                raise RecoveryBlocked(
                    "critical target was concurrently created; concurrent bytes preserved",
                    details={"target": str(paths.target)},
                ) from exc
            raise
        fsync_directory(paths.target.parent)
        _transition(paths.journal, journal, "TARGET_REPLACED", atomic_move_capability=capability)
        _call_fault(_fault, "TARGET_REPLACED", journal)
        _validate_exact(paths.target, new_hash, validator)
        _transition(paths.journal, journal, "TARGET_VERIFIED", verified_target_sha256=new_hash)
        _call_fault(_fault, "TARGET_VERIFIED", journal)
        _transition(paths.journal, journal, "COMMITTED", committed_target_sha256=new_hash)
        _call_fault(_fault, "COMMITTED", journal)
        return CriticalWriteResult(
            target=paths.target,
            journal=paths.journal,
            backup=paths.backup,
            target_sha256=new_hash,
            journal_state="COMMITTED",
            atomic_move_capability=capability,
        )
    except BaseException as exc:
        # A BaseException from the private test hook models a process crash.  It
        # must leave the exact durable checkpoint for a later recovery call.
        if not isinstance(exc, Exception):
            raise
        if journal["journal_state"] == "RECOVERY_BLOCKED":
            raise
        if journal["journal_state"] not in {"ROLLBACK_REQUIRED", "ROLLED_BACK", "RECOVERY_BLOCKED"}:
            try:
                _transition(paths.journal, journal, "ROLLBACK_REQUIRED", replace_error=repr(exc))
            except Exception as transition_error:
                raise RecoveryBlocked(
                    "could not persist rollback requirement",
                    details={"journal": str(paths.journal), "cause": repr(transition_error)},
                ) from transition_error
        return _rollback(paths, journal, validator)


def read_journal(path: os.PathLike[str] | str) -> dict[str, Any]:
    journal_path = Path(path)
    try:
        raw = _stable_plain_bytes(journal_path, label="critical-write journal")
    except (PathSafetyError, TransactionError) as exc:
        raise ValidationError(
            "journal path is unsafe",
            details={"path": str(journal_path), "cause": str(exc)},
        ) from exc
    if raw.startswith(b"\xef\xbb\xbf") or not raw.endswith(b"\n") or b"\r" in raw:
        raise ValidationError("journal encoding/profile is invalid", details={"path": str(journal_path)})
    try:
        value = json.loads(
            raw.decode("utf-8", "strict"),
            object_pairs_hook=_reject_duplicate_pairs,
            parse_constant=_reject_json_constant,
        )
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        raise ValidationError("journal is not valid JSON", details={"path": str(journal_path)}) from exc
    if not isinstance(value, dict) or raw != _journal_bytes(value):
        raise ValidationError("journal is not canonical JSON", details={"path": str(journal_path)})
    keys = set(value)
    if not _JOURNAL_BASE_KEYS <= keys or not keys <= _JOURNAL_BASE_KEYS | _JOURNAL_EVIDENCE_KEYS:
        raise ValidationError("journal fields are not closed", details={"path": str(journal_path)})
    if (
        value.get("journal_version") != 1
        or value.get("retention_policy") != RETENTION_POLICY
        or value.get("journal_state") not in JOURNAL_STATES
        or type(value.get("old_target_existed")) is not bool
        or not _valid_utc_timestamp(value.get("created_at"))
        or not _valid_utc_timestamp(value.get("updated_at"))
    ):
        raise ValidationError("journal state is invalid", details={"path": str(journal_path)})
    for field in (
        "target_relative_path",
        "temp_relative_path",
        "backup_relative_path",
        "quarantine_relative_path",
    ):
        item = value.get(field)
        if (
            not isinstance(item, str)
            or not item
            or Path(item).name != item
            or any(char in item for char in ("/", "\\", "\x00", "\r", "\n", "\t"))
        ):
            raise ValidationError("journal sibling path is invalid", details={"path": str(journal_path), "field": field})
    for field in ("new_target_sha256",):
        item = value.get(field)
        if not _canonical_hash(item):
            raise ValidationError("journal hash is invalid", details={"path": str(journal_path), "field": field})
    old_hash = value.get("old_target_sha256")
    if old_hash != "NOT_APPLICABLE" and not _canonical_hash(old_hash):
        raise ValidationError("journal old-target hash is invalid", details={"path": str(journal_path)})
    if value["old_target_existed"] != (old_hash != "NOT_APPLICABLE"):
        raise ValidationError("journal old-target existence/hash conflict", details={"path": str(journal_path)})
    if value.get("atomic_move_capability") not in ATOMIC_CAPABILITIES:
        raise ValidationError("journal atomic capability is invalid", details={"path": str(journal_path)})
    history = value.get("history")
    if not isinstance(history, list) or not history:
        raise ValidationError("journal history does not reconcile", details={"path": str(journal_path)})
    previous_state: str | None = None
    latest_evidence: dict[str, Any] = {}
    for index, entry in enumerate(history):
        if (
            not isinstance(entry, dict)
            or set(entry) not in ({"at", "journal_state"}, {"at", "evidence", "journal_state"})
            or entry.get("journal_state") not in JOURNAL_STATES
            or not _valid_utc_timestamp(entry.get("at"))
            or index == 0 and entry["journal_state"] != "PREPARED"
            or previous_state is not None
            and entry["journal_state"] not in _NORMAL_FORWARD.get(previous_state, set())
        ):
            raise ValidationError("journal history transition is invalid", details={"path": str(journal_path)})
        evidence = entry.get("evidence")
        if evidence is not None:
            if (
                not isinstance(evidence, dict)
                or not evidence
                or not set(evidence) <= _JOURNAL_EVIDENCE_KEYS | {"atomic_move_capability"}
            ):
                raise ValidationError("journal history evidence is invalid", details={"path": str(journal_path)})
            for field, evidence_value in evidence.items():
                if not _validate_evidence_field(field, evidence_value, value):
                    raise ValidationError(
                        "journal history evidence value is invalid",
                        details={"path": str(journal_path), "field": field},
                    )
                if field in latest_evidence and latest_evidence[field] != evidence_value:
                    raise ValidationError(
                        "journal history evidence changes an established fact",
                        details={"path": str(journal_path), "field": field},
                    )
                latest_evidence[field] = evidence_value
        previous_state = entry["journal_state"]
    if (
        history[0]["at"] != value["created_at"]
        or history[-1]["at"] != value["updated_at"]
        or history[-1]["journal_state"] != value["journal_state"]
    ):
        raise ValidationError("journal history does not reconcile", details={"path": str(journal_path)})
    for field, evidence_value in latest_evidence.items():
        if value.get(field) != evidence_value:
            raise ValidationError(
                "journal top-level evidence does not reconcile",
                details={"path": str(journal_path), "field": field},
            )
    if any(field not in latest_evidence for field in keys & _JOURNAL_EVIDENCE_KEYS):
        raise ValidationError("journal contains unhistoried evidence", details={"path": str(journal_path)})
    return value


def recover_critical_write(
    journal_path: os.PathLike[str] | str,
    *,
    validator: Validator,
) -> CriticalWriteResult:
    """Recover by actual hashes, never merely by trusting the last state."""

    try:
        path = plain_file(journal_path, label="critical-write journal", single_link=True)
    except PathSafetyError as exc:
        raise RecoveryBlocked(
            "critical-write journal path is unsafe",
            details={"path": str(journal_path), "cause": str(exc)},
        ) from exc
    journal = read_journal(path)
    parent = path.parent
    paths = CriticalWritePaths(
        target=parent / journal["target_relative_path"],
        temp=parent / journal["temp_relative_path"],
        backup=parent / journal["backup_relative_path"],
        journal=path,
        quarantine=parent / journal["quarantine_relative_path"],
    )
    if any(item.parent != paths.target.parent for item in (paths.temp, paths.backup, paths.journal, paths.quarantine)):
        raise RecoveryBlocked("journal evidence is not sibling-contained", details={"journal": str(path)})
    if journal["journal_state"] == "RECOVERY_BLOCKED":
        raise RecoveryBlocked("journal is recovery-blocked", details={"journal": str(path)})

    new_hash = journal["new_target_sha256"]
    try:
        _validate_exact(paths.target, new_hash, validator)
    except Exception:
        new_valid = False
    else:
        new_valid = True

    if (
        new_valid
        and journal["journal_state"] in {"PREPARED", "BACKUP_VERIFIED"}
        and journal.get("old_target_existed")
        and journal.get("old_target_sha256") == new_hash
    ):
        # Bytes are identical and the journal has not durably proved
        # replacement.  BACKUP_VERIFIED is just as ambiguous as PREPARED: a
        # crash there occurs before TARGET_REPLACED.  The conservative
        # interpretation is restoration of the previous state.
        _transition(path, journal, "ROLLBACK_REQUIRED", identical_bytes_ambiguous=True)
        _transition(path, journal, "ROLLED_BACK", identical_bytes_ambiguous=True)
        return CriticalWriteResult(
            target=paths.target,
            journal=path,
            backup=paths.backup,
            target_sha256=new_hash,
            journal_state="ROLLED_BACK",
            atomic_move_capability=journal.get("atomic_move_capability", "UNKNOWN"),
        )

    if (
        not new_valid
        and journal["journal_state"] in {"PREPARED", "BACKUP_VERIFIED"}
        and journal.get("old_target_existed")
        and journal.get("old_target_sha256") == new_hash
        and not paths.target.exists()
        and not paths.target.is_symlink()
    ):
        # With atomic target claiming, BACKUP_VERIFIED normally has no target
        # name.  Identical old/new bytes remain semantically ambiguous until
        # TARGET_REPLACED; restore the retained backup and record that fact.
        try:
            _validate_exact(paths.backup, new_hash, validator)
        except Exception:
            pass
        else:
            _transition(path, journal, "ROLLBACK_REQUIRED", identical_bytes_ambiguous=True)
            return _rollback(paths, journal, validator)

    if new_valid:
        if journal["journal_state"] == "ROLLED_BACK":
            raise RecoveryBlocked(
                "rolled-back journal conflicts with the new target bytes",
                details={"journal": str(path), "state": journal["journal_state"]},
            )
        if journal["journal_state"] == "BACKUP_VERIFIED":
            _transition(path, journal, "TARGET_REPLACED", recovered_from_hashes=True)
        if journal["journal_state"] == "TARGET_REPLACED":
            _transition(path, journal, "TARGET_VERIFIED", recovered_target_sha256=new_hash)
        if journal["journal_state"] == "TARGET_VERIFIED":
            _transition(path, journal, "COMMITTED", recovered_target_sha256=new_hash)
        elif journal["journal_state"] in {"PREPARED", "ROLLBACK_REQUIRED"}:
            # A target with the new exact bytes proves replacement occurred, but
            # PREPARED/BACKUP_VERIFIED lack the durable TARGET_REPLACED checkpoint.
            # Do not invent skipped journal transitions; block for audit.
            if journal["journal_state"] == "ROLLBACK_REQUIRED":
                return _rollback(paths, journal, validator)
            raise RecoveryBlocked(
                "new target exists without a recoverable journal checkpoint",
                details={"journal": str(path), "state": journal["journal_state"]},
            )
        return CriticalWriteResult(
            target=paths.target,
            journal=path,
            backup=paths.backup,
            target_sha256=new_hash,
            journal_state=journal["journal_state"],
            atomic_move_capability=journal.get("atomic_move_capability", "UNKNOWN"),
        )

    old_hash = journal["old_target_sha256"]
    if journal["old_target_existed"]:
        try:
            _validate_exact(paths.target, old_hash, validator)
        except Exception:
            old_target_valid = False
        else:
            old_target_valid = True
    else:
        old_target_valid = not paths.target.exists() and not paths.target.is_symlink()
    if old_target_valid:
        if journal["journal_state"] in {"PREPARED", "BACKUP_VERIFIED"}:
            _transition(path, journal, "ROLLBACK_REQUIRED", recovered_old_state=True)
            _transition(path, journal, "ROLLED_BACK", recovered_old_state=True)
        elif journal["journal_state"] == "ROLLBACK_REQUIRED":
            _transition(path, journal, "ROLLED_BACK", recovered_old_state=True)
        elif journal["journal_state"] != "ROLLED_BACK":
            try:
                _transition(path, journal, "ROLLBACK_REQUIRED", recovered_old_state=True)
                _transition(path, journal, "ROLLED_BACK", recovered_old_state=True)
            except Exception as exc:
                raise RecoveryBlocked("old target is valid but journal cannot reconcile", details={"journal": str(path)}) from exc
        return CriticalWriteResult(
            target=paths.target,
            journal=path,
            backup=paths.backup,
            target_sha256=old_hash,
            journal_state=journal["journal_state"],
            atomic_move_capability=journal.get("atomic_move_capability", "UNKNOWN"),
        )

    if journal["journal_state"] != "ROLLBACK_REQUIRED":
        try:
            _transition(path, journal, "ROLLBACK_REQUIRED", recovery_hash_mismatch=True)
        except Exception as exc:
            raise RecoveryBlocked("cannot enter rollback during recovery", details={"journal": str(path)}) from exc
    return _rollback(paths, journal, validator)


def find_blocking_journals(parent: os.PathLike[str] | str) -> list[Path]:
    """Return unresolved/recovery-blocked journals without modifying anything."""

    result: list[Path] = []
    for path in sorted(Path(parent).glob(".*.journal.json"), key=lambda item: item.name):
        try:
            state = read_journal(path)["journal_state"]
        except ValidationError:
            result.append(path)
            continue
        if state not in {"COMMITTED", "ROLLED_BACK"}:
            result.append(path)
    return result


def assert_no_blocking_journals(parent: os.PathLike[str] | str) -> None:
    blocked = find_blocking_journals(parent)
    if blocked:
        raise RecoveryBlocked(
            "unresolved critical-write evidence blocks writers and consumers",
            details={"journals": [str(path) for path in blocked]},
        )


def retain_paths(paths: list[os.PathLike[str] | str]) -> dict[str, Any]:
    """Audit the Prompt-1 retention policy; it intentionally deletes nothing."""

    records = []
    for raw_path in paths:
        path = Path(raw_path)
        records.append(
            {
                "path": str(path),
                "exists": path.exists(),
                "sha256": sha256_file(path) if path.is_file() else "NOT_APPLICABLE",
                "action": "RETAINED",
            }
        )
    return {"retention_policy": RETENTION_POLICY, "automatic_delete": False, "records": records}
