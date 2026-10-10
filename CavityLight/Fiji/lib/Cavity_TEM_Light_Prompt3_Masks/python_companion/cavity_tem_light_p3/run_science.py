"""Scientific spatial-scale verification layered over immutable RUN bytes.

``verify_run_directory`` deliberately proves only physical completeness and
the established RUN trust chain.  Prompt 3 needs a second, independent gate:
the scale and every derived physical cavity value must reproduce from the
selected immutable revision's pixel geometry and the independently
normalised Fiji calibration.  Keeping these responsibilities separate lets a
physically sound historical RUN remain preserved while being rejected for
scientific use.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
import math
from pathlib import Path
from typing import Any, Mapping, Sequence

from cavity_tem_light_p1.canonical_json import canonical_json_bytes, loads_canonical_json
from cavity_tem_light_p1.errors import ValidationError
from cavity_tem_light_p1.path_safety import plain_directory, plain_file, stable_plain_bytes
from cavity_tem_light_p1.object_table import parse_canonical_json_cell
from cavity_tem_light_p2.session_core import SessionCore, sha256_bytes, sha256_file, validate_manual_candidate, MANUAL_CANDIDATE_SCHEMA

from .spatial_scale import (
    scales_agree,
    transient_physical_objects,
    verify_spatial_scale_provenance,
)


SCIENTIFIC_RUN_SCALE_SCHEMA = "CTL_P3_RUN_SCALE_SCIENTIFIC_VERIFICATION_V1"


class ScientificScaleMismatch(ValidationError):
    """One physically verified RUN cannot be used at the required scale."""

    code = "SPATIAL_SCALE_PROVENANCE_MISMATCH"


def _fail(message: str, **details: Any) -> None:
    raise ScientificScaleMismatch(message, details=details)


def _decimal(value: Any, field: str, *, positive: bool = False) -> Decimal:
    if isinstance(value, bool):
        _fail("scientific RUN decimal is invalid", field=field)
    try:
        number = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        _fail("scientific RUN decimal is invalid", field=field)
    if not number.is_finite() or (positive and number <= 0):
        _fail("scientific RUN decimal is invalid", field=field)
    return number


def _close(left: Any, right: Any, *, relative: str = "1e-12") -> bool:
    a = _decimal(left, "left")
    b = _decimal(right, "right")
    tolerance = max(Decimal("1e-12"), Decimal(relative) * max(abs(a), abs(b)))
    return abs(a - b) <= tolerance


def _property(item: Mapping[str, Any], *names: str, default: Any = None) -> Any:
    wanted = {name.casefold() for name in names}
    for source in (
        item,
        item.get("geometry"),
        item.get("legacy_properties"),
    ):
        if not isinstance(source, Mapping):
            continue
        for key, value in source.items():
            if str(key).casefold() in wanted:
                return value
    return default


def _flag(item: Mapping[str, Any], *names: str) -> int:
    value = _property(item, *names, default=0)
    try:
        flag = int(str(value))
    except (TypeError, ValueError, OverflowError):
        _fail("revision endpoint flag is invalid", field=names[0])
    if flag not in (0, 1):
        _fail("revision endpoint flag is invalid", field=names[0])
    return flag


def _verified_run_parts(run: Any) -> tuple[Mapping[str, Any], Sequence[Mapping[str, str]]]:
    manifest = getattr(run, "manifest", None)
    rows = getattr(run, "object_rows", None)
    if not isinstance(manifest, Mapping) or not isinstance(rows, tuple):
        raise ValidationError(
            "scientific scale verification requires a physically verified RUN"
        )
    if any(not isinstance(row, Mapping) for row in rows):
        raise ValidationError("verified RUN object table contains a non-object row")
    return manifest, rows


def verify_manual_candidate_run_trace(
    row: Mapping[str, str], cavity_object: Mapping[str, Any], candidates: Sequence[Mapping[str, Any]]
) -> None:
    """Bind additive candidate TSV fields to the immutable review authority."""
    linked = [item for item in candidates if item.get("candidate_uuid") == cavity_object.get("candidate_uuid")]
    candidate = linked[0] if len(linked) == 1 else None
    if candidate is None or candidate.get("candidate_schema") != MANUAL_CANDIDATE_SCHEMA:
        if row.get("candidate_id") != "NOT_APPLICABLE":
            _fail("RUN candidate trace has no reviewed manual candidate authority")
        return
    validate_manual_candidate(candidate, cavity_object)
    for field in ("candidate_id", "view_id", "proposed_geometry_sha256"):
        if row.get(field) != candidate[field]:
            _fail("RUN candidate provenance differs from immutable review", field=field)
    for field in ("source_sha256", "master_pixel_sha256"):
        if row.get(field) != candidate[field]:
            _fail("RUN candidate belongs to another source image", field=field)
    provenance = parse_canonical_json_cell(row.get("identity_provenance"), field="identity_provenance")
    identities = [item for item in provenance if item.get("entity_type") == "candidate"]
    if len(identities) != 1 or identities[0].get("uid_value") != candidate["candidate_uuid"]:
        _fail("RUN candidate UUID differs from immutable review")
    if row.get("cavity_class") != candidate["accepted_cavity_class"] or row.get("review_status") != "reviewed" or row.get("measurement_source") != "manual":
        _fail("RUN candidate review class or measurement authority differs")


def verify_run_scientific_scale(
    run: Any,
    *,
    revision_manifest: Mapping[str, Any],
    calibration: Mapping[str, Any],
    valid_pixel_count: int | None = None,
) -> dict[str, Any]:
    """Reconcile one verified RUN against pixel geometry and normalised XY.

    The function performs no writes and does not consult any visibility or
    overlay state.  A mismatch raises ``ScientificScaleMismatch`` even when
    the RUN's physical publication/hash chain is otherwise valid.
    """

    manifest, rows = _verified_run_parts(run)
    expected_scope = {
        "analysis_session_uid": revision_manifest.get("analysis_session_uid"),
        "image_uid": revision_manifest.get("image_uid"),
        "project_uid": revision_manifest.get("project_uid"),
        "revision_id": revision_manifest.get("revision_id"),
        "revision_uid": revision_manifest.get("revision_uid"),
        "source_sha256": revision_manifest.get("source_sha256"),
    }
    for field, expected in expected_scope.items():
        if manifest.get(field) != expected:
            _fail(
                "RUN scientific scope differs from the selected revision",
                field=field,
                expected=expected,
                actual=manifest.get(field),
            )

    scale_x = _decimal(calibration.get("scale_x_nm_px"), "scale_x_nm_px", positive=True)
    scale_y = _decimal(calibration.get("scale_y_nm_px"), "scale_y_nm_px", positive=True)
    try:
        source_width = int(calibration.get("source_width_px"))
        source_height = int(calibration.get("source_height_px"))
    except (TypeError, ValueError, OverflowError) as exc:
        _fail("scientific source dimensions are invalid")
    if source_width <= 0 or source_height <= 0:
        _fail("scientific source dimensions are invalid")
    source_objects = revision_manifest.get("objects")
    if not isinstance(source_objects, list):
        _fail("selected revision object inventory is invalid")
    expected_objects = transient_physical_objects(source_objects, calibration)
    original_by_uid = {str(item.get("object_uuid")): item for item in source_objects}
    by_uid = {str(item.get("object_uuid")): item for item in expected_objects}
    if len(by_uid) != len(expected_objects) or len(rows) != len(expected_objects):
        _fail(
            "RUN/revision object cardinality differs",
            revision_count=len(expected_objects),
            run_count=len(rows),
        )

    center_count = diameter_count = area_count = border_count = 0
    seen: set[str] = set()
    for index, row in enumerate(rows):
        uid = str(row.get("object_uuid") or "")
        expected = by_uid.get(uid)
        if expected is None or uid in seen:
            _fail("RUN object identity is absent or duplicated", index=index, object_uuid=uid)
        seen.add(uid)
        if row.get("cavity_id") != str(expected.get("cavity_id")):
            _fail("RUN cavity_id differs from revision identity", object_uuid=uid)
        verify_manual_candidate_run_trace(row, original_by_uid[uid], revision_manifest.get("candidates", []))
        if not scales_agree(row.get("scale_x_nm_px"), scale_x) or not scales_agree(
            row.get("scale_y_nm_px"), scale_y
        ):
            _fail(
                "RUN object scale differs from independent spatial calibration",
                object_uuid=uid,
                stored_scale_x_nm_px=row.get("scale_x_nm_px"),
                stored_scale_y_nm_px=row.get("scale_y_nm_px"),
                correct_scale_x_nm_px=str(scale_x),
                correct_scale_y_nm_px=str(scale_y),
            )

        geometry = expected.get("geometry")
        if not isinstance(geometry, Mapping):
            _fail("recomputed revision geometry is absent", object_uuid=uid)
        comparisons = (
            ("center_x_px", geometry.get("center_x_px")),
            ("center_y_px", geometry.get("center_y_px")),
            ("center_x_nm", geometry.get("center_x_nm")),
            ("center_y_nm", geometry.get("center_y_nm")),
        )
        for field, expected_value in comparisons:
            if not _close(row.get(field), expected_value, relative="1e-12"):
                _fail(
                    "RUN center does not reproduce from revision pixel coordinates",
                    field=field,
                    object_uuid=uid,
                    expected=str(expected_value),
                    actual=row.get(field),
                )
        center_count += 1

        expected_diameter = _decimal(
            geometry.get("diameter_nm"), "expected_diameter_nm", positive=True
        )
        if not _close(row.get("diameter_nm"), expected_diameter, relative="1e-12"):
            _fail(
                "RUN diameter does not reproduce from revision pixel geometry",
                object_uuid=uid,
                expected=str(expected_diameter),
                actual=row.get("diameter_nm"),
            )
        diameter_count += 1
        expected_area = Decimal(
            str(math.pi * float(expected_diameter) * float(expected_diameter) / 4.0)
        )
        if not _close(row.get("projected_area_nm2"), expected_area, relative="1e-12"):
            _fail(
                "RUN projected area does not reproduce from corrected diameter",
                object_uuid=uid,
                expected=str(expected_area),
                actual=row.get("projected_area_nm2"),
            )
        area_count += 1

        width = _decimal(geometry.get("width_px"), "width_px", positive=True)
        height = _decimal(geometry.get("height_px"), "height_px", positive=True)
        center_x = _decimal(geometry.get("center_x_px"), "center_x_px")
        center_y = _decimal(geometry.get("center_y_px"), "center_y_px")
        try:
            stored_source_width = int(row.get("source_width_px", "0"))
            stored_source_height = int(row.get("source_height_px", "0"))
        except (TypeError, ValueError, OverflowError):
            _fail("RUN source dimensions are invalid", object_uuid=uid)
        if (
            stored_source_width != source_width
            or stored_source_height != source_height
        ):
            _fail(
                "RUN source dimensions differ from master-pixel evidence",
                object_uuid=uid,
                expected_width_px=source_width,
                expected_height_px=source_height,
                actual_width_px=stored_source_width,
                actual_height_px=stored_source_height,
            )
        touches_image = int(
            center_x - width / 2 <= 0
            or center_y - height / 2 <= 0
            or center_x + width / 2 >= source_width
            or center_y + height / 2 >= source_height
        )
        edge_intersecting = _flag(expected, "edge_intersecting", "Edge_intersecting")
        touches_mask = int(edge_intersecting == 1 and touches_image == 0)
        if int(row.get("touches_image_edge", "-1")) != touches_image or int(
            row.get("touches_mask_edge", "-1")
        ) != touches_mask:
            _fail("RUN border classification differs from REV_000005", object_uuid=uid)
        border_count += 1

    expected_counts = {
        "N_count_valid": sum(_flag(item, "count_valid", "Count_valid") for item in expected_objects),
        "N_size_valid": sum(_flag(item, "size_valid", "Size_valid") for item in expected_objects),
        "N_position_valid": sum(
            _flag(item, "position_valid", "Position_valid") for item in expected_objects
        ),
    }
    for field, expected in expected_counts.items():
        if int(manifest.get(field, -1)) != expected:
            _fail(
                "RUN endpoint count differs from selected revision",
                field=field,
                expected=expected,
                actual=manifest.get(field),
            )

    expected_area_text: str | None = None
    if valid_pixel_count is not None:
        if isinstance(valid_pixel_count, bool) or not isinstance(valid_pixel_count, int) or valid_pixel_count <= 0:
            _fail("scientific valid-pixel count is invalid")
        expected_net_area = Decimal(valid_pixel_count) * scale_x * scale_y
        if not _close(manifest.get("net_area_nm2"), expected_net_area, relative="1e-12"):
            _fail(
                "RUN area denominator differs from corrected valid-pixel area",
                expected=str(expected_net_area),
                actual=manifest.get("net_area_nm2"),
                valid_pixel_count=valid_pixel_count,
            )
        expected_area_text = str(expected_net_area)

    return {
        "N_count_valid": expected_counts["N_count_valid"],
        "N_position_valid": expected_counts["N_position_valid"],
        "N_size_valid": expected_counts["N_size_valid"],
        "analysis_session_uid": manifest["analysis_session_uid"],
        "area_denominator_nm2": expected_area_text,
        "border_classifications_reconciled": border_count,
        "centers_reconciled": center_count,
        "diameters_reconciled": diameter_count,
        "projected_areas_reconciled": area_count,
        "revision_id": manifest["revision_id"],
        "revision_uid": manifest["revision_uid"],
        "run_id": manifest["run_id"],
        "run_manifest_sha256": getattr(run, "manifest_sha256"),
        "run_uid": manifest["run_uid"],
        "scale_x_nm_px": str(scale_x),
        "scale_y_nm_px": str(scale_y),
        "schema": SCIENTIFIC_RUN_SCALE_SCHEMA,
        "scientific_scale_status": "PASS",
    }


def _project_root_for_session(session_root: Path) -> Path:
    candidates = [
        candidate
        for candidate in (session_root, *session_root.parents)
        if (candidate / "project.json").is_file()
    ]
    if len(candidates) != 1:
        raise ValidationError(
            "Prompt-3 scientific consumer cannot resolve one project root",
            details={"matches": len(candidates)},
        )
    return plain_directory(candidates[0], label="Prompt-3 scientific project root")


def _verified_run_revision_context(
    run: Any,
    session_root: Path,
) -> tuple[Mapping[str, Any], SessionCore, Any, dict[str, Any], str]:
    """Resolve one physical RUN back to its verified immutable revision."""

    manifest, _rows = _verified_run_parts(run)
    project_root = _project_root_for_session(session_root)
    core = SessionCore(project_root)
    record = core.session_by_uid(
        str(manifest.get("image_uid")),
        str(manifest.get("analysis_session_uid")),
    )
    if record.session_root.resolve(strict=True) != session_root.resolve(strict=True):
        _fail("Prompt-3 scientific RUN session path is not its registry owner")
    revision_id = str(manifest.get("revision_id") or "")
    revision_root = session_root / "revisions" / f"REV_{revision_id}"
    revision_manifest = core._verify_revision(record, revision_root)
    revision_sha = sha256_file(revision_root / "revision_manifest.json")
    if revision_sha != manifest.get("revision_manifest_sha256"):
        _fail("Prompt-3 scientific RUN revision hash differs")
    return manifest, core, record, revision_manifest, revision_sha


def run_requires_spatial_scale_verification(
    run: Any,
    *,
    session_root: str | Path,
) -> bool:
    """Identify Prompt-3-native RUNs from immutable revision authority.

    Operational evidence may legitimately be absent after archive/restore, so
    its absence can never be used to classify a RUN as pre-Prompt-3.  Revision
    manifest V2 is the closed profile that introduced scientific geometries.
    """

    root = plain_directory(session_root, label="Prompt-3 scientific session root")
    manifest, _rows = _verified_run_parts(run)
    revision_id = str(manifest.get("revision_id") or "")
    revision_path = root / "revisions" / f"REV_{revision_id}" / "revision_manifest.json"
    if not revision_path.exists() and not revision_path.is_symlink():
        # Historical P1 projects have no per-session schema-2 revision tree.
        return False
    revision_preview = loads_canonical_json(
        stable_plain_bytes(
            plain_file(
                revision_path,
                label="scientific RUN revision profile",
                single_link=True,
            ),
            label="scientific RUN revision profile",
        )
    )
    if (
        not isinstance(revision_preview, Mapping)
        or revision_preview.get("schema") != "CTL_P2A_REVISION_MANIFEST_V2"
    ):
        return False
    # Once the immutable profile identifies Prompt 3, require its complete
    # project/session/revision trust chain; malformed or displaced V2 authority
    # must never fall back to legacy eligibility.
    _manifest, _core, _record, revision_manifest, _revision_sha = (
        _verified_run_revision_context(run, root)
    )
    return revision_manifest.get("schema") == "CTL_P2A_REVISION_MANIFEST_V2"


def _verified_cache_pixel_count(
    session_root: Path,
    *,
    core: SessionCore,
    record: Any,
    revision_manifest: Mapping[str, Any],
    revision_manifest_sha256: str,
    evidence_sha256: str,
    calibration: Mapping[str, Any],
) -> int | None:
    path = session_root / "autosave" / "prompt3" / "analysis_area_cache.json"
    if not path.exists() and not path.is_symlink():
        _fail(
            "Prompt-3 scientific area denominator evidence is absent",
            reason_code="AREA_DENOMINATOR_EVIDENCE_REQUIRED",
        )
    data = stable_plain_bytes(
        plain_file(path, label="Prompt-3 scientific area cache", single_link=True),
        label="Prompt-3 scientific area cache",
    )
    value = loads_canonical_json(data)
    required = {
        "analysis_session_uid",
        "authority",
        "geometry_set_sha256",
        "image_uid",
        "input_fingerprint_sha256",
        "net_area_nm2",
        "payload_sha256",
        "project_uid",
        "raster_algorithm",
        "revision_id",
        "revision_manifest_sha256",
        "revision_uid",
        "schema",
        "spatial_calibration_evidence_sha256",
        "valid_pixel_count",
    }
    if not isinstance(value, Mapping) or set(value) != required:
        _fail(
            "Prompt-3 scientific area denominator evidence has an invalid profile",
            reason_code="AREA_DENOMINATOR_EVIDENCE_REQUIRED",
        )
    expected = {
        "analysis_session_uid": record.analysis_session_uid,
        "authority": False,
        "geometry_set_sha256": core.geometry_set_sha256(
            revision_manifest.get("geometries", [])
        ),
        "image_uid": record.image_uid,
        "project_uid": core.project_uid,
        "raster_algorithm": "IMAGEJ_BYTEPROCESSOR_FILL_V1",
        "revision_id": revision_manifest.get("revision_id"),
        "revision_manifest_sha256": revision_manifest_sha256,
        "revision_uid": revision_manifest.get("revision_uid"),
        "schema": "CTL_P3_ANALYSIS_AREA_CACHE_V2",
        "spatial_calibration_evidence_sha256": evidence_sha256,
    }
    for field, expected_value in expected.items():
        if value.get(field) != expected_value:
            _fail(
                "Prompt-3 scientific area cache binding is invalid",
                field=field,
            )
    # The current Prompt-3 bridge has one closed calculation policy: surfaces
    # are display guidance only, while the scientific raster is 2-D and has no
    # material-side depth exclusion.  Recompute the same V2 area-input record
    # rather than trusting the self-declared fingerprint in the cache.
    from .mask_visibility import _area_input

    reconstructed_input = _area_input(
        core,
        revision_manifest.get("geometries", []),
        {
            "depth_policy": {
                "exclude_negative_depth": False,
                "material_side": "NOT_APPLICABLE",
                "mode": "NONE",
            },
            "height_px": int(calibration["source_height_px"]),
            "image_mode": "without_surface",
            "scale_x_nm_px": calibration["scale_x_nm_px"],
            "scale_y_nm_px": calibration["scale_y_nm_px"],
            "spatial_calibration_evidence_sha256": evidence_sha256,
            "width_px": int(calibration["source_width_px"]),
        },
    )
    if value.get("input_fingerprint_sha256") != reconstructed_input.get(
        "input_fingerprint_sha256"
    ):
        _fail(
            "Prompt-3 scientific area cache input fingerprint is invalid",
            reason_code="AREA_DENOMINATOR_EVIDENCE_REQUIRED",
        )
    payload = {key: item for key, item in value.items() if key != "payload_sha256"}
    if value.get("payload_sha256") != sha256_bytes(canonical_json_bytes(payload)):
        _fail("Prompt-3 scientific area cache payload hash is invalid")
    raw_count = value.get("valid_pixel_count")
    if isinstance(raw_count, bool):
        _fail("Prompt-3 scientific area cache pixel count is invalid")
    try:
        count = int(raw_count)
    except (TypeError, ValueError, OverflowError):
        _fail("Prompt-3 scientific area cache pixel count is invalid")
    if str(count) != str(raw_count).strip():
        _fail("Prompt-3 scientific area cache pixel count is not canonical")
    width = int(calibration["source_width_px"])
    height = int(calibration["source_height_px"])
    if count <= 0 or count > width * height:
        _fail("Prompt-3 scientific area cache pixel count is invalid")
    expected_area = (
        Decimal(count)
        * Decimal(str(calibration["scale_x_nm_px"]))
        * Decimal(str(calibration["scale_y_nm_px"]))
    )
    if not _close(value.get("net_area_nm2"), expected_area, relative="1e-12"):
        _fail("Prompt-3 scientific area cache denominator is invalid")
    return count


def verify_run_against_persisted_scale(
    run: Any,
    *,
    session_root: str | Path,
) -> dict[str, Any]:
    """Apply the independent scale gate in every Prompt-3 scientific consumer.

    Physical RUN verification remains unchanged.  This read-only layer
    rebuilds the complete provenance claim from the persisted raw Fiji
    evidence, re-verifies source/baseline/REV_000005/current revision, then
    reconciles the immutable RUN.  It therefore rejects RUN2 before any
    external disposition exists.
    """

    root = plain_directory(session_root, label="Prompt-3 scientific session root")
    evidence_path = plain_file(
        root / "autosave" / "prompt3" / "SPATIAL_CALIBRATION_EVIDENCE.json",
        label="Prompt-3 spatial calibration evidence",
        single_link=True,
    )
    evidence_bytes = stable_plain_bytes(
        evidence_path, label="Prompt-3 spatial calibration evidence"
    )
    evidence = loads_canonical_json(evidence_bytes)
    if not isinstance(evidence, Mapping):
        _fail("Prompt-3 spatial calibration evidence root is invalid")
    manifest, core, record, revision_manifest, revision_sha = (
        _verified_run_revision_context(run, root)
    )
    try:
        image_context = {
            "bit_depth": evidence["bit_depth"],
            "decoder_opening_method": evidence["decoder_opening_method"],
            "default_unit": evidence["default_unit"],
            "factor_x_to_nm": evidence["factor_x_to_nm"],
            "factor_y_to_nm": evidence["factor_y_to_nm"],
            "fiji_imagej_version": evidence["fiji_imagej_version"],
            "height_px": evidence["height"],
            "master_pixel_evidence": {
                "bit_depth": evidence["bit_depth"],
                "height": evidence["height"],
                "sha256": evidence["master_pixel_sha256"],
                "source_sha256": evidence["source_sha256"],
                "width": evidence["width"],
            },
            "raw_pixel_height": evidence["raw_pixel_height"],
            "raw_pixel_width": evidence["raw_pixel_width"],
            "raw_x_unit": evidence["raw_x_unit"],
            "raw_y_unit": evidence["raw_y_unit"],
            "scale_x_nm_px": evidence["scale_x_nm_px"],
            "scale_y_nm_px": evidence["scale_y_nm_px"],
            "width_px": evidence["width"],
        }
    except KeyError as exc:
        _fail("Prompt-3 spatial calibration evidence field is absent", field=str(exc))
    provenance = verify_spatial_scale_provenance(
        core=core,
        record=record,
        revision_manifest=revision_manifest,
        revision_manifest_sha256=revision_sha,
        image_context=image_context,
    )
    if dict(provenance["evidence"]) != dict(evidence):
        _fail("Prompt-3 persisted spatial calibration evidence did not reproduce")
    calibration = {
        "scale_x_nm_px": provenance["calibration"]["scale_x_nm_px"],
        "scale_y_nm_px": provenance["calibration"]["scale_y_nm_px"],
        "source_height_px": evidence["height"],
        "source_width_px": evidence["width"],
    }
    # Reject a mislabeled RUN from its own immutable rows first.  This keeps
    # RUN_000002's reason scientifically precise even though its historical V1
    # cache is deliberately non-authoritative.
    verify_run_scientific_scale(
        run,
        revision_manifest=revision_manifest,
        calibration=calibration,
        valid_pixel_count=None,
    )
    valid_pixel_count = _verified_cache_pixel_count(
        root,
        core=core,
        record=record,
        revision_manifest=revision_manifest,
        revision_manifest_sha256=revision_sha,
        evidence_sha256=sha256_bytes(evidence_bytes),
        calibration=calibration,
    )
    return verify_run_scientific_scale(
        run,
        revision_manifest=revision_manifest,
        calibration=calibration,
        valid_pixel_count=valid_pixel_count,
    )


__all__ = [
    "SCIENTIFIC_RUN_SCALE_SCHEMA",
    "ScientificScaleMismatch",
    "run_requires_spatial_scale_verification",
    "verify_run_against_persisted_scale",
    "verify_run_scientific_scale",
]
