"""No-replace publication of Prompt-3 scientific RUN dispositions.

This module never writes inside ``runs/``.  It first verifies the immutable
invalidated and replacement RUNs, then publishes one canonical external
record in the owning session and reconciles only the mutable project indexes.
"""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path
import uuid
from typing import Any, Mapping

from cavity_tem_light_p1.canonical_json import canonical_json_bytes
from cavity_tem_light_p1.critical_io import sha256_bytes
from cavity_tem_light_p1.errors import TransactionError, ValidationError
from cavity_tem_light_p1.path_safety import (
    PathSafetyError,
    plain_directory,
    rename_file_no_replace,
    stable_plain_bytes,
)
from cavity_tem_light_p1.run_consumer import (
    load_current_run,
    resolve_contained,
    verify_run_directory,
)
from cavity_tem_light_p1.run_context import load_run_context
from cavity_tem_light_p1.run_disposition import (
    DISPOSITION_DIRECTORY,
    RunDisposition,
    parse_run_disposition,
    render_run_disposition,
    validate_replacement_binding,
    validate_run_binding,
    validate_run_disposition_directory,
)
from cavity_tem_light_p1.run_transaction import RunRegistry
from cavity_tem_light_p2.session_core import (
    SessionCore,
    _replace_exact,
    _write_new,
    sha256_file,
    snapshot_tree,
)

from .spatial_scale import decimal_text, normalize_spatial_unit


PUBLICATION_JOURNAL_SCHEMA = "CTL_RUN_SCIENTIFIC_DISPOSITION_PUBLICATION_JOURNAL_V1"
PUBLICATION_STATES = frozenset(
    {
        "COMMITTED",
        "FAILED_PARTIAL_RETAINED",
        "PREPARED",
        "PUBLISHED_PENDING_INDEX_RECONCILIATION",
    }
)


def _revision_verifier(core: SessionCore, record: Any):
    binding = core._binding(record.image_uid)

    def verify(run_manifest: Mapping[str, Any]) -> bool:
        revision_id = str(run_manifest.get("revision_id", ""))
        revision_root = record.session_root / "revisions" / f"REV_{revision_id}"
        revision = core._verify_revision(record, revision_root)
        revision_sha = sha256_file(revision_root / "revision_manifest.json")
        exact = {
            "analysis_session_uid": record.analysis_session_uid,
            "image_uid": record.image_uid,
            "project_uid": core.project_uid,
            "revision_id": revision.get("revision_id"),
            "revision_manifest_sha256": revision_sha,
            "revision_uid": revision.get("revision_uid"),
            "source_sha256": binding["source_sha256"],
        }
        if binding.get("master_pixel_hash_status") == "VERIFIED":
            exact["master_pixel_sha256"] = binding["master_pixel_sha256"]
        for field, expected in exact.items():
            if run_manifest.get(field) != expected:
                raise ValidationError(
                    "RUN disposition revision/source trust chain mismatch",
                    details={"field": field, "expected": expected, "actual": run_manifest.get(field)},
                )
        return True

    return verify


def _verified_session_runs(
    core: SessionCore,
    record: Any,
) -> tuple[dict[str, Any], Mapping[str, Any], Any]:
    """Return all physical RUNs, their registry and exact current RUN."""

    registry_path = record.session_root / "run_registry.json"
    pointer_path = record.session_root / "current_run.tsv"
    if not registry_path.is_file() or not pointer_path.is_file():
        raise ValidationError("run disposition requires existing RUN registry and pointer")
    context = load_run_context(core.root, record.session_root)
    revision_verifier = _revision_verifier(core, record)
    registry = RunRegistry(registry_path).load()
    verified: dict[str, Any] = {}
    for item in registry["runs"]:
        run_path = resolve_contained(
            record.session_root,
            str(item["relative_path"]),
            stage="RUN_DISPOSITION_PATH",
        )
        run = verify_run_directory(
            run_path,
            registry_path=registry_path,
            revision_verifier=revision_verifier,
            run_context=context,
        )
        if run.run_id in verified:
            raise ValidationError("run disposition preflight found duplicate RUN IDs")
        verified[run.run_id] = run
    current = load_current_run(
        record.session_root,
        pointer_path,
        registry_path=registry_path,
        revision_verifier=revision_verifier,
        run_context=context,
    )
    return verified, registry, current


def _registry_item(registry: Mapping[str, Any], run_uid: str) -> Mapping[str, Any]:
    matches = [
        item
        for item in registry.get("runs", [])
        if isinstance(item, Mapping) and item.get("run_uid") == run_uid
    ]
    if len(matches) != 1:
        raise ValidationError(
            "run disposition preflight cannot resolve one registry RUN",
            details={"run_uid": run_uid, "matches": len(matches)},
        )
    return matches[0]


def _validate_raw_calibration_binding(disposition: RunDisposition) -> None:
    """Independently recompute corrected nm/px from raw Fiji value + unit."""

    value = disposition.value
    raw_x = Decimal(str(value["raw_fiji_pixel_width"]))
    raw_y = Decimal(str(value["raw_fiji_pixel_height"]))
    unit_x, factor_x = normalize_spatial_unit(value["raw_x_unit"], field="raw_x_unit")
    unit_y, factor_y = normalize_spatial_unit(value["raw_y_unit"], field="raw_y_unit")
    if unit_x != value["raw_x_unit"] or unit_y != value["raw_y_unit"]:
        raise ValidationError("run disposition raw spatial-unit text changed during normalization")
    if (
        Decimal(str(value["stored_scale_x_nm_px"])) != raw_x
        or Decimal(str(value["stored_scale_y_nm_px"])) != raw_y
    ):
        raise ValidationError(
            "run disposition stored scale is not the raw Fiji value mislabeled as nm"
        )
    expected_x = decimal_text(raw_x * factor_x)
    expected_y = decimal_text(raw_y * factor_y)
    if (
        value["correct_scale_x_nm_px"] != expected_x
        or value["correct_scale_y_nm_px"] != expected_y
    ):
        raise ValidationError(
            "run disposition corrected scale does not derive from raw Fiji value and unit",
            details={
                "expected_scale_x_nm_px": expected_x,
                "expected_scale_y_nm_px": expected_y,
            },
        )


def _runs_snapshot_sha256(record: Any) -> tuple[dict[str, str], str]:
    value = snapshot_tree(record.session_root / "runs")
    return value, sha256_bytes(canonical_json_bytes(value))


def _ensure_disposition_directory(record: Any) -> Path:
    root = record.session_root / DISPOSITION_DIRECTORY
    if not root.exists():
        if root.is_symlink():
            raise ValidationError("run disposition directory is a dangling link")
        try:
            root.mkdir()
        except FileExistsError:
            pass
    try:
        return plain_directory(root, label="run disposition publication directory")
    except PathSafetyError as exc:
        raise ValidationError(
            "run disposition publication directory is unsafe",
            details={"path": str(root), "reason": str(exc)},
        ) from exc


def _session_indexes_need_refresh(core: SessionCore, record: Any) -> bool:
    matches = [
        row
        for row in core._read_registry(record.image_uid)
        if row["analysis_session_uid"] == record.analysis_session_uid
    ]
    if len(matches) != 1:
        raise ValidationError("run disposition session registry owner is not unique")
    measured = core._session_stats(record.session_root)
    return any(
        matches[0][field] != measured[field]
        for field in (
            "object_count",
            "revision_count",
            "run_count",
            "logical_bytes",
            "physical_bytes",
        )
    )


def _reconcile_indexes(core: SessionCore, record: Any, created_at: str) -> None:
    if _session_indexes_need_refresh(core, record):
        core._refresh_session_registry(record.image_uid, created_at)
    # This method is byte-idempotent: it performs no replace when the
    # reconstructed manifest already equals the published bytes.
    core.refresh_storage_manifest()


def _result(
    disposition: RunDisposition,
    *,
    idempotent: bool,
    runs_snapshot_sha256: str,
) -> dict[str, Any]:
    return {
        "disposition": dict(disposition.value),
        "disposition_path": str(disposition.path),
        "disposition_sha256": disposition.sha256,
        "idempotent_replay": idempotent,
        "immutable_runs_preserved": True,
        "runs_tree_sha256": runs_snapshot_sha256,
        "scientific_use_allowed": False,
        "status": "IDEMPOTENT_VERIFIED" if idempotent else "PUBLISHED_VERIFIED",
    }


def publish_run_disposition(
    project_root: str | Path,
    *,
    image_uid: str,
    analysis_session_uid: str,
    disposition_value: Mapping[str, Any],
) -> dict[str, Any]:
    """Publish one external immutable record and never alter RUN bytes."""

    core = SessionCore(project_root)
    record = core.session_by_uid(str(image_uid), str(analysis_session_uid))
    if disposition_value.get("image_uid") != record.image_uid or disposition_value.get(
        "analysis_session_uid"
    ) != record.analysis_session_uid:
        raise ValidationError("run disposition request owner differs from selected session")

    data = render_run_disposition(disposition_value)
    candidate = parse_run_disposition(data)
    _validate_raw_calibration_binding(candidate)
    verified, registry, current = _verified_session_runs(core, record)
    invalid = verified.get(candidate.run_id)
    replacement = verified.get(candidate.replacement_run_id)
    if invalid is None or replacement is None:
        raise ValidationError("run disposition request references an absent physical RUN")
    validate_run_binding(candidate, invalid)
    validate_replacement_binding(candidate, replacement)
    invalid_registry = _registry_item(registry, invalid.run_uid)
    replacement_registry = _registry_item(registry, replacement.run_uid)
    if (
        invalid_registry.get("run_lifecycle") != "HISTORICAL"
        or invalid_registry.get("quarantine_status") != "ACTIVE"
    ):
        raise ValidationError("invalidated RUN must be a physically active historical RUN")
    if replacement_registry.get("quarantine_status") != "ACTIVE":
        raise ValidationError("replacement RUN must remain physically active")

    runs_before, runs_before_sha = _runs_snapshot_sha256(record)
    disposition_root = _ensure_disposition_directory(record)
    final = disposition_root / f"{candidate.run_id}.json"
    if final.exists() or final.is_symlink():
        try:
            observed = stable_plain_bytes(final, label="existing run disposition")
        except PathSafetyError as exc:
            raise ValidationError("existing run disposition is unsafe") from exc
        if observed != data:
            raise TransactionError(
                "divergent run disposition already exists; replacement is forbidden",
                details={"path": str(final)},
            )
        existing = parse_run_disposition(observed, path=final)
        validate_run_binding(existing, invalid)
        validate_replacement_binding(existing, replacement)
        _reconcile_indexes(core, record, str(existing.value["created_at"]))
        verified_after, _registry_after, current_after = _verified_session_runs(core, record)
        dispositions = validate_run_disposition_directory(
            record.session_root, verified_after.values()
        )
        if current_after.run_uid in {item.run_uid for item in dispositions}:
            raise ValidationError("current RUN is scientifically invalidated")
        runs_after, runs_after_sha = _runs_snapshot_sha256(record)
        if runs_after != runs_before or runs_after_sha != runs_before_sha:
            raise TransactionError("RUN bytes changed during disposition replay")
        return _result(
            existing,
            idempotent=True,
            runs_snapshot_sha256=runs_after_sha,
        )

    if (
        replacement_registry.get("run_lifecycle") != "CURRENT"
        or current.run_uid != replacement.run_uid
        or current.manifest_sha256 != replacement.manifest_sha256
    ):
        raise ValidationError("replacement RUN must be the exact physically current RUN")

    token = uuid.uuid4().hex
    stage = disposition_root / f".{candidate.run_id}.json.partial.{token}"
    journal_path = record.session_root / "journals" / f"JOURNAL_run_disposition_{token}.json"
    disposition_sha = sha256_bytes(data)
    journal = {
        "analysis_session_uid": record.analysis_session_uid,
        "created_at": disposition_value["created_at"],
        "disposition_relative_path": final.relative_to(record.session_root).as_posix(),
        "disposition_sha256": disposition_sha,
        "invalidated_run_id": candidate.run_id,
        "invalidated_run_manifest_sha256": invalid.manifest_sha256,
        "replacement_run_id": candidate.replacement_run_id,
        "replacement_run_manifest_sha256": replacement.manifest_sha256,
        "runs_tree_sha256_before": runs_before_sha,
        "schema": PUBLICATION_JOURNAL_SCHEMA,
        "state": "PREPARED",
    }
    _write_new(journal_path, canonical_json_bytes(journal))
    try:
        _write_new(stage, data)
        rename_file_no_replace(stage, final, error_type=TransactionError)
        published = parse_run_disposition(
            stable_plain_bytes(final, label="published run disposition"),
            path=final,
        )
        if published.sha256 != disposition_sha:
            raise TransactionError("published run disposition differs from staged bytes")
        _reconcile_indexes(core, record, str(published.value["created_at"]))
        verified_after, _registry_after, current_after = _verified_session_runs(core, record)
        validate_run_disposition_directory(record.session_root, verified_after.values())
        if current_after.run_uid != replacement.run_uid:
            raise ValidationError("current RUN changed during disposition publication")
        runs_after, runs_after_sha = _runs_snapshot_sha256(record)
        if runs_after != runs_before or runs_after_sha != runs_before_sha:
            raise TransactionError("immutable RUN tree changed during disposition publication")
        journal["runs_tree_sha256_after"] = runs_after_sha
        journal["state"] = "COMMITTED"
        _replace_exact(
            journal_path,
            canonical_json_bytes(journal),
            expected_sha256=sha256_file(journal_path),
            token=f"{token}_commit",
        )
        return _result(
            published,
            idempotent=False,
            runs_snapshot_sha256=runs_after_sha,
        )
    except BaseException:
        try:
            journal["state"] = (
                "PUBLISHED_PENDING_INDEX_RECONCILIATION"
                if final.is_file()
                else "FAILED_PARTIAL_RETAINED"
            )
            if journal["state"] not in PUBLICATION_STATES:
                raise AssertionError("invalid disposition journal state")
            _replace_exact(
                journal_path,
                canonical_json_bytes(journal),
                expected_sha256=sha256_file(journal_path),
                token=f"{token}_failure",
            )
        except BaseException:
            # The original failure is the operative error.  Both journal and
            # staging/final evidence remain available for exact replay.
            pass
        raise


def publish_run_disposition_request(arguments: Mapping[str, Any]) -> dict[str, Any]:
    """Closed bridge adapter for later registration in the P3 manager."""

    if set(arguments) != {
        "analysis_session_uid",
        "disposition",
        "image_uid",
        "project_root",
    }:
        raise ValidationError("run disposition request field inventory is not closed")
    disposition = arguments["disposition"]
    if not isinstance(disposition, Mapping):
        raise ValidationError("run disposition request payload must be an object")
    return publish_run_disposition(
        arguments["project_root"],
        image_uid=str(arguments["image_uid"]),
        analysis_session_uid=str(arguments["analysis_session_uid"]),
        disposition_value=disposition,
    )


__all__ = [
    "PUBLICATION_JOURNAL_SCHEMA",
    "publish_run_disposition",
    "publish_run_disposition_request",
]
