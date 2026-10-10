"""Fail-closed reconciliation of a terminal native RUN reservation.

The RUN v2 writer deliberately retains a failed partial and its transaction
descriptor.  That evidence reserves the RUN ID and therefore cannot simply be
deleted before a retry.  This module moves one *terminal*, internally
consistent attempt into a session-scoped recovery bundle with a canonical
receipt.  Published RUNs, the registry and ``current_run.tsv`` are read-only
authorities throughout the operation.

Nothing in this module repairs or republishes the retained partial.  Once the
bundle is committed, the caller may perform a new publication with a new UUID
and transaction token while reusing the human RUN ID.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from pathlib import Path
import os
import re
import uuid
from typing import Any

from cavity_tem_light_p1.canonical_json import canonical_json_bytes, loads_canonical_json
from cavity_tem_light_p1.critical_io import (
    RETENTION_POLICY,
    find_blocking_journals,
    read_journal,
    sha256_bytes,
)
from cavity_tem_light_p1.errors import RecoveryBlocked, TransactionError, ValidationError
from cavity_tem_light_p1.path_safety import (
    PathSafetyError,
    _native_rename_no_replace,
    lexical_absolute,
    plain_directory,
    plain_file,
    reject_reparse_chain,
    stable_plain_bytes,
)
from cavity_tem_light_p1.run_context import load_run_context
from cavity_tem_light_p1.run_transaction import RunRegistry, inspect_retained_partial
from cavity_tem_light_p2.session_core import (
    SessionCore,
    _replace_exact,
    _write_new,
    sha256_file,
    snapshot_tree,
    utc_now_z,
)


RECEIPT_SCHEMA = "CTL_P3_FAILED_RUN_ATTEMPT_RECOVERY_RECEIPT_V1"
JOURNAL_SCHEMA = "CTL_P3_FAILED_RUN_ATTEMPT_RECOVERY_JOURNAL_V1"
RUN_ID_RE = re.compile(r"RUN_[0-9]{6}")
ACTIVE_TRANSACTION_STATES = frozenset(
    {"PARTIAL_CREATED", "WRITING", "VALIDATING", "VERIFIED_STAGED"}
)
JOURNAL_STATES = frozenset({"PREPARED", "MOVING", "COMMITTED"})
FaultHook = Callable[[str, Mapping[str, Any]], None]


def _canonical_mapping(path: Path, *, label: str) -> tuple[bytes, dict[str, Any]]:
    try:
        data = stable_plain_bytes(path, label=label)
    except PathSafetyError as exc:
        raise ValidationError(
            f"{label} is not a stable plain file",
            details={"path": str(path), "reason": str(exc)},
        ) from exc
    value = loads_canonical_json(data)
    if not isinstance(value, dict):
        raise ValidationError(f"{label} must be a canonical JSON object")
    return data, value


def _ensure_directory(path: Path, *, label: str) -> Path:
    """Create one ordinary directory level and re-open it through path safety."""

    if path.exists() or path.is_symlink():
        try:
            return plain_directory(path, label=label)
        except PathSafetyError as exc:
            raise RecoveryBlocked(
                f"{label} is unsafe", details={"path": str(path), "reason": str(exc)}
            ) from exc
    try:
        plain_directory(path.parent, label=f"{label} parent")
        path.mkdir()
        return plain_directory(path, label=label)
    except (OSError, PathSafetyError) as exc:
        raise RecoveryBlocked(
            f"{label} cannot be created safely",
            details={"path": str(path), "reason": str(exc)},
        ) from exc


def _file_record(path: Path, relative_path: str) -> dict[str, Any]:
    try:
        data = stable_plain_bytes(path, label="failed RUN recovery evidence")
    except PathSafetyError as exc:
        raise RecoveryBlocked(
            "failed RUN recovery evidence is unsafe",
            details={"path": str(path), "reason": str(exc)},
        ) from exc
    return {
        "bytes": len(data),
        "relative_path": relative_path,
        "sha256": sha256_bytes(data),
    }


def _source_inventory(partial: Path, controls: list[Path]) -> list[dict[str, Any]]:
    records = [_file_record(path, path.name) for path in controls]
    try:
        plain_directory(partial, label="failed native RUN partial")
    except PathSafetyError as exc:
        raise RecoveryBlocked(
            "failed native RUN partial is unsafe",
            details={"path": str(partial), "reason": str(exc)},
        ) from exc
    for path in sorted(
        partial.rglob("*"), key=lambda item: item.relative_to(partial).as_posix()
    ):
        if path.is_dir() and not path.is_symlink():
            continue
        relative = f"{partial.name}/{path.relative_to(partial).as_posix()}"
        records.append(_file_record(path, relative))
    return sorted(records, key=lambda item: item["relative_path"])


def _bundle_inventory(bundle: Path) -> list[dict[str, Any]]:
    try:
        plain_directory(bundle, label="failed RUN recovery bundle")
    except PathSafetyError as exc:
        raise RecoveryBlocked(
            "failed RUN recovery bundle is unsafe",
            details={"path": str(bundle), "reason": str(exc)},
        ) from exc
    records: list[dict[str, Any]] = []
    for path in sorted(bundle.rglob("*"), key=lambda item: item.relative_to(bundle).as_posix()):
        relative = path.relative_to(bundle).as_posix()
        if relative == "RECOVERY_RECEIPT.json":
            continue
        if path.is_dir() and not path.is_symlink():
            continue
        records.append(_file_record(path, relative))
    return records


def _inventory_sha256(records: list[dict[str, Any]]) -> str:
    return sha256_bytes(canonical_json_bytes({"files": records}))


def _published_authority_snapshot(session_root: Path, run_id: str) -> dict[str, Any]:
    pointer_path = session_root / "current_run.tsv"
    registry_path = session_root / "run_registry.json"
    try:
        pointer = stable_plain_bytes(pointer_path, label="current RUN pointer")
        registry_bytes = stable_plain_bytes(registry_path, label="RUN registry")
    except PathSafetyError as exc:
        raise RecoveryBlocked(
            "published RUN control authority is unsafe", details={"reason": str(exc)}
        ) from exc
    registry = RunRegistry(registry_path).load()
    if any(item.get("run_id") == run_id for item in registry.get("runs", [])):
        raise RecoveryBlocked(
            "failed RUN reservation is already present in the physical registry",
            details={"run_id": run_id},
        )
    rows = pointer.decode("utf-8").splitlines()
    if len(rows) == 2:
        fields = rows[0].split("\t")
        values = rows[1].split("\t")
        if len(fields) != len(values):
            raise RecoveryBlocked("current RUN pointer is structurally invalid")
        if dict(zip(fields, values)).get("run_id") == run_id:
            raise RecoveryBlocked(
                "failed RUN reservation is already the physical current RUN",
                details={"run_id": run_id},
            )
    elif len(rows) != 1:
        raise RecoveryBlocked("current RUN pointer has an invalid row count")

    runs_root = plain_directory(session_root / "runs", label="native RUN directory")
    published: dict[str, str] = {}
    for path in sorted(runs_root.iterdir(), key=lambda item: item.name):
        if not path.is_dir() or re.fullmatch(r"RUN_RUN_[0-9]{6}", path.name) is None:
            continue
        published[path.name] = sha256_bytes(canonical_json_bytes(snapshot_tree(path)))
    return {
        "current_run_sha256": sha256_bytes(pointer),
        "published_run_inventory_sha256": sha256_bytes(canonical_json_bytes(published)),
        "published_runs": published,
        "run_registry_sha256": sha256_bytes(registry_bytes),
    }


def _same_device(source: Path, destination_parent: Path) -> None:
    if source.stat(follow_symlinks=False).st_dev != destination_parent.stat(
        follow_symlinks=False
    ).st_dev:
        raise RecoveryBlocked(
            "failed RUN evidence cannot be reconciled across filesystems",
            details={"source": str(source), "destination_parent": str(destination_parent)},
        )


def _move_no_replace(source: Path, destination: Path, *, kind: str) -> None:
    """Move across contained directories with the platform no-replace primitive."""

    try:
        destination = lexical_absolute(destination, label="recovery destination")
        destination_parent = plain_directory(
            destination.parent, label="recovery destination parent"
        )
        reject_reparse_chain(destination, label="recovery destination", must_exist=False)
        if destination.exists() or destination.is_symlink():
            raise RecoveryBlocked(
                "failed RUN recovery destination already exists",
                details={"destination": str(destination)},
            )
        if kind == "directory":
            checked_source = plain_directory(source, label="failed RUN partial source")
        elif kind == "file":
            checked_source = plain_file(
                source, label="failed RUN control source", single_link=True
            )
        else:  # pragma: no cover - journal schema construction owns this value
            raise RecoveryBlocked("failed RUN recovery move kind is invalid")
        _same_device(checked_source, destination_parent)
        _native_rename_no_replace(checked_source, destination)
        if checked_source.exists() or checked_source.is_symlink():
            raise RecoveryBlocked("failed RUN recovery move left the source name present")
        if kind == "directory":
            plain_directory(destination, label="moved failed RUN partial")
        else:
            plain_file(destination, label="moved failed RUN control", single_link=True)
    except RecoveryBlocked:
        raise
    except (OSError, PathSafetyError) as exc:
        raise RecoveryBlocked(
            "failed RUN recovery no-replace move failed",
            details={
                "source": str(source),
                "destination": str(destination),
                "reason": str(exc),
            },
        ) from exc


def _record_fingerprint(path: Path, move: Mapping[str, Any]) -> str:
    if move["kind"] == "directory":
        return sha256_bytes(canonical_json_bytes(snapshot_tree(path)))
    return sha256_file(path)


def _move_or_verify(
    runs_root: Path,
    bundle: Path,
    move: Mapping[str, Any],
    *,
    fault: FaultHook | None,
) -> None:
    name = str(move["name"])
    source = runs_root / name
    destination = bundle / name
    source_exists = source.exists() or source.is_symlink()
    destination_exists = destination.exists() or destination.is_symlink()
    if source_exists and destination_exists:
        raise RecoveryBlocked(
            "failed RUN evidence exists at both live and recovery names",
            details={"name": name},
        )
    if not source_exists and not destination_exists:
        raise RecoveryBlocked(
            "failed RUN evidence is absent from both live and recovery names",
            details={"name": name},
        )
    if source_exists:
        if _record_fingerprint(source, move) != move["fingerprint_sha256"]:
            raise RecoveryBlocked(
                "live failed RUN evidence differs from the recovery journal",
                details={"name": name},
            )
        _move_no_replace(source, destination, kind=str(move["kind"]))
    if _record_fingerprint(destination, move) != move["fingerprint_sha256"]:
        raise RecoveryBlocked(
            "recovered failed RUN evidence differs from the recovery journal",
            details={"name": name},
        )
    if fault is not None:
        fault(f"AFTER_MOVE:{name}", move)


def _assert_run_id_reusable(runs_root: Path, run_id: str) -> None:
    stem = f"RUN_{run_id}"
    reservations = [
        path.name
        for path in runs_root.iterdir()
        if path.name == stem
        or path.name == f"{stem}.transaction.json"
        or path.name.startswith(f"{stem}.partial.")
        or path.name.startswith(f".{stem}.transaction.json.")
    ]
    if reservations:
        raise RecoveryBlocked(
            "failed RUN recovery did not release the complete identity reservation",
            details={"run_id": run_id, "reservations": sorted(reservations)},
        )
    blocked = find_blocking_journals(runs_root)
    if blocked:
        raise RecoveryBlocked(
            "RUN writer remains blocked by unresolved critical evidence",
            details={"journals": [str(path) for path in blocked]},
        )


def _verify_receipt_bundle(
    journal_path: Path,
    journal: Mapping[str, Any],
    *,
    authority: Mapping[str, Any],
) -> dict[str, Any]:
    if journal.get("schema") != JOURNAL_SCHEMA or journal.get("state") not in JOURNAL_STATES:
        raise RecoveryBlocked("failed RUN recovery journal schema/state is invalid")
    bundle = journal_path.parent.parent / str(journal["bundle_relative_path"])
    expected_inventory = journal.get("evidence_inventory")
    if not isinstance(expected_inventory, list):
        raise RecoveryBlocked("failed RUN recovery journal inventory is invalid")
    observed_inventory = _bundle_inventory(bundle)
    if observed_inventory != expected_inventory or _inventory_sha256(
        observed_inventory
    ) != journal.get("evidence_inventory_sha256"):
        raise RecoveryBlocked("failed RUN recovery bundle inventory does not reconcile")
    receipt_path = bundle / "RECOVERY_RECEIPT.json"
    receipt_bytes = canonical_json_bytes(journal["receipt"])
    if stable_plain_bytes(receipt_path, label="failed RUN recovery receipt") != receipt_bytes:
        raise RecoveryBlocked("failed RUN recovery receipt differs from its journal")
    wrapper_path = journal_path.parent.parent / str(
        journal["receipt"]["wrapper_journal_relative_path"]
    )
    if sha256_file(wrapper_path) != journal["receipt"]["wrapper_journal_sha256"]:
        raise RecoveryBlocked("failed RUN wrapper journal changed after reconciliation")
    if authority != journal.get("published_authority_before"):
        raise RecoveryBlocked("published RUN authority changed during failed-attempt recovery")
    return {
        "bundle_path": str(bundle),
        "evidence_file_count": len(observed_inventory),
        "evidence_inventory_sha256": journal["evidence_inventory_sha256"],
        "failed_run_uid": journal["failed_run_uid"],
        "idempotent_replay": journal.get("state") == "COMMITTED",
        "immutable_published_runs_preserved": True,
        "journal_path": str(journal_path),
        "receipt_path": str(receipt_path),
        "receipt_sha256": sha256_bytes(receipt_bytes),
        "run_id": journal["run_id"],
        "run_id_reusable": True,
        "status": "IDEMPOTENT_VERIFIED" if journal.get("state") == "COMMITTED" else "RECOVERED_VERIFIED",
    }


def _resume_journal(
    session_root: Path,
    journal_path: Path,
    journal: dict[str, Any],
    *,
    fault: FaultHook | None,
) -> dict[str, Any]:
    run_id = str(journal.get("run_id", ""))
    was_committed = journal.get("state") == "COMMITTED"
    if journal.get("schema") != JOURNAL_SCHEMA or journal.get("state") not in JOURNAL_STATES:
        raise RecoveryBlocked("failed RUN recovery journal schema/state is invalid")
    authority = _published_authority_snapshot(session_root, run_id)
    if authority != journal.get("published_authority_before"):
        raise RecoveryBlocked("published RUN authority changed during failed-attempt recovery")
    runs_root = plain_directory(session_root / "runs", label="native RUN directory")
    bundle = session_root / str(journal["bundle_relative_path"])
    _ensure_directory(bundle, label="failed RUN recovery bundle")
    if journal["state"] == "PREPARED":
        journal["state"] = "MOVING"
        _replace_exact(
            journal_path,
            canonical_json_bytes(journal),
            expected_sha256=sha256_file(journal_path),
            token="failed_run_recovery_moving",
        )
    if journal["state"] == "MOVING":
        for move in journal["moves"]:
            _move_or_verify(runs_root, bundle, move, fault=fault)
        observed = _bundle_inventory(bundle)
        if observed != journal["evidence_inventory"]:
            raise RecoveryBlocked("moved failed RUN evidence inventory is not exact")
        receipt_path = bundle / "RECOVERY_RECEIPT.json"
        receipt_bytes = canonical_json_bytes(journal["receipt"])
        if receipt_path.exists() or receipt_path.is_symlink():
            if stable_plain_bytes(receipt_path, label="failed RUN recovery receipt") != receipt_bytes:
                raise RecoveryBlocked("existing failed RUN recovery receipt is divergent")
        else:
            _write_new(receipt_path, receipt_bytes)
        if fault is not None:
            fault("AFTER_RECEIPT", journal["receipt"])
        journal["state"] = "COMMITTED"
        _replace_exact(
            journal_path,
            canonical_json_bytes(journal),
            expected_sha256=sha256_file(journal_path),
            token="failed_run_recovery_committed",
        )
    _assert_run_id_reusable(runs_root, run_id)
    result = _verify_receipt_bundle(journal_path, journal, authority=authority)
    result["idempotent_replay"] = was_committed
    if not was_committed:
        result["status"] = "RECOVERED_VERIFIED"
    return result


def reconcile_failed_run_reservation(
    project_root: os.PathLike[str] | str,
    *,
    image_uid: str,
    analysis_session_uid: str,
    run_id: str,
    recovered_at: str | None = None,
    _fault: FaultHook | None = None,
) -> dict[str, Any]:
    """Preserve one failed native attempt and release its RUN ID for one retry.

    Replay is idempotent.  Active transactions, published/registered targets,
    ambiguous partial sets and any owner/hash mismatch fail without moving the
    evidence.
    """

    if RUN_ID_RE.fullmatch(run_id) is None:
        raise ValidationError("failed RUN recovery requires RUN_[0-9]{6}")
    core = SessionCore(project_root)
    record = core.session_by_uid(str(image_uid), str(analysis_session_uid))
    session_root = plain_directory(record.session_root, label="failed RUN owning session")
    runs_root = plain_directory(session_root / "runs", label="native RUN directory")

    existing_journals = sorted(
        (session_root / "journals").glob(f"JOURNAL_failed_run_recovery_{run_id}_*.json"),
        key=lambda path: path.name,
    )
    if len(existing_journals) > 1:
        raise RecoveryBlocked(
            "multiple recovery journals claim one failed RUN ID",
            details={"journals": [str(path) for path in existing_journals]},
        )
    if existing_journals:
        _data, journal = _canonical_mapping(
            existing_journals[0], label="failed RUN recovery journal"
        )
        if (
            journal.get("project_uid") != core.project_uid
            or journal.get("image_uid") != record.image_uid
            or journal.get("analysis_session_uid") != record.analysis_session_uid
            or journal.get("run_id") != run_id
        ):
            raise RecoveryBlocked("failed RUN recovery journal owner mismatch")
        return _resume_journal(
            session_root, existing_journals[0], journal, fault=_fault
        )

    authority = _published_authority_snapshot(session_root, run_id)
    final = runs_root / f"RUN_{run_id}"
    if final.exists() or final.is_symlink():
        raise RecoveryBlocked("cannot reconcile a failed reservation over a final RUN")
    context = load_run_context(core.root, session_root)
    diagnosis = inspect_retained_partial(runs_root, run_id, run_context=context)
    descriptor = diagnosis.get("descriptor")
    if not isinstance(descriptor, dict):
        raise RecoveryBlocked("failed RUN recovery requires its transaction descriptor")
    state = descriptor.get("transaction_state")
    if state in ACTIVE_TRANSACTION_STATES:
        raise RecoveryBlocked(
            "active RUN transaction cannot be reconciled as failed evidence",
            details={"run_id": run_id, "transaction_state": state},
        )
    if state != "FAILED_PARTIAL" or descriptor.get("validation_status") != "FAIL":
        raise RecoveryBlocked(
            "RUN reservation is not a terminal failed partial",
            details={"run_id": run_id, "transaction_state": state},
        )
    if diagnosis.get("sealed_candidate_status") != "VERIFIED_STAGED":
        raise RecoveryBlocked(
            "failed RUN partial is not a physically verified retained candidate"
        )
    failed_uid = str(descriptor.get("run_uid", ""))
    try:
        parsed_uid = uuid.UUID(failed_uid)
    except (ValueError, TypeError, AttributeError) as exc:
        raise RecoveryBlocked("failed RUN descriptor UUID is invalid") from exc
    if str(parsed_uid) != failed_uid or parsed_uid.version != 4:
        raise RecoveryBlocked("failed RUN descriptor UUID is not canonical UUIDv4")

    partial = Path(str(diagnosis["partial_path"]))
    manifest_data, manifest = _canonical_mapping(
        partial / "run_manifest.json", label="retained failed RUN manifest"
    )
    if (
        manifest.get("run_id") != run_id
        or manifest.get("run_uid") != failed_uid
        or descriptor.get("partial_relative_path") != partial.name
    ):
        raise RecoveryBlocked("failed RUN partial/descriptor identity mismatch")
    if sha256_bytes(manifest_data) != diagnosis.get("run_manifest_sha256"):
        raise RecoveryBlocked("failed RUN retained manifest hash mismatch")

    wrappers: list[tuple[Path, bytes, dict[str, Any]]] = []
    for path in sorted(
        (session_root / "journals").glob(f"JOURNAL_native_run_{run_id}_*.json"),
        key=lambda item: item.name,
    ):
        data, value = _canonical_mapping(path, label="native RUN wrapper journal")
        if value.get("run_uid") == failed_uid:
            wrappers.append((path, data, value))
    if len(wrappers) != 1:
        raise RecoveryBlocked(
            "failed RUN wrapper journal is absent or ambiguous",
            details={"run_id": run_id, "matches": len(wrappers)},
        )
    wrapper_path, wrapper_bytes, wrapper = wrappers[0]
    if (
        wrapper.get("schema") != "CTL_P2A_NATIVE_RUN_WRAPPER_JOURNAL_V1"
        or wrapper.get("state") != "FAILED_PARTIAL_RETAINED"
        or wrapper.get("run_id") != run_id
        or wrapper.get("analysis_session_uid") != record.analysis_session_uid
        or wrapper.get("retained_partial_count") != 1
    ):
        raise RecoveryBlocked("failed RUN wrapper journal does not reconcile")

    blocking = find_blocking_journals(runs_root)
    if blocking:
        raise RecoveryBlocked(
            "failed RUN controls contain unresolved critical-write journals",
            details={"journals": [str(path) for path in blocking]},
        )
    descriptor_path = runs_root / f"RUN_{run_id}.transaction.json"
    control_prefix = f".{descriptor_path.name}."
    control_paths = sorted(
        [
            path
            for path in runs_root.iterdir()
            if path.is_file() and path.name.startswith(control_prefix)
        ],
        key=lambda path: path.name,
    )
    failure_journal_path = runs_root / f".{descriptor_path.name}.failed_partial.journal.json"
    if failure_journal_path not in control_paths:
        raise RecoveryBlocked("terminal failed RUN critical journal is absent")
    failure_journal = read_journal(failure_journal_path)
    if (
        failure_journal.get("journal_state") != "COMMITTED"
        or failure_journal.get("new_target_sha256") != sha256_file(descriptor_path)
    ):
        raise RecoveryBlocked("terminal failed RUN descriptor journal does not reconcile")

    controls = control_paths + [descriptor_path]
    evidence_inventory = _source_inventory(partial, controls)
    evidence_inventory_sha = _inventory_sha256(evidence_inventory)
    recovered = recovered_at or utc_now_z()
    recovery = _ensure_directory(session_root / "recovery", label="session recovery directory")
    # Keep the recovery name deliberately short.  Real schema-2 session paths
    # can already be close to the Win32/fsutil path boundary; a decorative
    # multi-level hierarchy would make otherwise safe retained evidence
    # unverifiable on Windows.  The full UUID remains bound inside the receipt.
    bundle = recovery / f"F_{run_id}"
    if bundle.exists() or bundle.is_symlink():
        raise RecoveryBlocked("failed RUN recovery bundle already exists without a journal")

    moves: list[dict[str, Any]] = [
        {
            "fingerprint_sha256": sha256_bytes(canonical_json_bytes(snapshot_tree(partial))),
            "kind": "directory",
            "name": partial.name,
        }
    ]
    moves.extend(
        {
            "fingerprint_sha256": sha256_file(path),
            "kind": "file",
            "name": path.name,
        }
        for path in controls
    )
    journal_name = f"JOURNAL_failed_run_recovery_{run_id}_{failed_uid}.json"
    journal_path = session_root / "journals" / journal_name
    bundle_relative = bundle.relative_to(session_root).as_posix()
    receipt = {
        "analysis_session_uid": record.analysis_session_uid,
        "evidence_inventory_sha256": evidence_inventory_sha,
        "failed_descriptor_sha256": sha256_file(descriptor_path),
        "failed_partial_manifest_sha256": diagnosis["run_manifest_sha256"],
        "failed_run_uid": failed_uid,
        "image_uid": record.image_uid,
        "journal_relative_path": journal_path.relative_to(session_root).as_posix(),
        "project_uid": core.project_uid,
        "recovered_at": recovered,
        "recovery_status": "COMMITTED",
        "retention_policy": RETENTION_POLICY,
        "run_id": run_id,
        "schema": RECEIPT_SCHEMA,
        "wrapper_journal_relative_path": wrapper_path.relative_to(session_root).as_posix(),
        "wrapper_journal_sha256": sha256_bytes(wrapper_bytes),
    }
    journal: dict[str, Any] = {
        "analysis_session_uid": record.analysis_session_uid,
        "bundle_relative_path": bundle_relative,
        "created_at": recovered,
        "evidence_inventory": evidence_inventory,
        "evidence_inventory_sha256": evidence_inventory_sha,
        "failed_run_uid": failed_uid,
        "image_uid": record.image_uid,
        "moves": moves,
        "project_uid": core.project_uid,
        "published_authority_before": authority,
        "receipt": receipt,
        "run_id": run_id,
        "schema": JOURNAL_SCHEMA,
        "state": "PREPARED",
    }
    _write_new(journal_path, canonical_json_bytes(journal))
    if _fault is not None:
        _fault("AFTER_JOURNAL_PREPARED", journal)
    return _resume_journal(session_root, journal_path, journal, fault=_fault)


def reconcile_failed_run_reservation_request(
    arguments: Mapping[str, Any],
) -> dict[str, Any]:
    """Closed bridge adapter for an explicitly authorized recovery command."""

    expected = {
        "analysis_session_uid",
        "image_uid",
        "project_root",
        "run_id",
    }
    if set(arguments) != expected:
        raise ValidationError(
            "failed RUN recovery request field inventory is not closed",
            details={
                "expected": sorted(expected),
                "observed": sorted(str(field) for field in arguments),
            },
        )
    return reconcile_failed_run_reservation(
        arguments["project_root"],
        image_uid=str(arguments["image_uid"]),
        analysis_session_uid=str(arguments["analysis_session_uid"]),
        run_id=str(arguments["run_id"]),
    )


__all__ = [
    "ACTIVE_TRANSACTION_STATES",
    "JOURNAL_SCHEMA",
    "RECEIPT_SCHEMA",
    "reconcile_failed_run_reservation",
    "reconcile_failed_run_reservation_request",
]
