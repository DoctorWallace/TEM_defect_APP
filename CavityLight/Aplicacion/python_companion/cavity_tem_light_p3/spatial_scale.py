"""Closed spatial-scale normalization and Prompt-3 provenance checks.

The Fiji ``Calibration`` object stores a numeric pixel size and a separate
unit.  Treating the numeric component as if it were already expressed in
``nm/px`` changes every physical coordinate and the scientific area
denominator.  This module therefore repeats the UI-side conversion from raw
value plus raw unit, binds it to the active source/master pixels and compares
it with the immutable migrated revision evidence before any Prompt-3 cache or
RUN can consume it.

Top-level physical fields in a migrated revision are deliberately *not* scale
authority.  In particular, a revision created while Fiji exposed micrometres
can contain derived ``*_nm`` values that were mislabeled by the caller.  The
only migrated-revision scale evidence accepted here is the preserved legacy
``Session_scale_nm_per_px_x/y`` pair, present consistently on every migrated
object. A later explicitly reviewed P7 manual object instead retains its
verified source-view calibration; it must agree with the migrated authority.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any, Mapping, Sequence
import unicodedata

from cavity_tem_light_p1.canonical_json import canonical_json_bytes, loads_canonical_json
from cavity_tem_light_p1.errors import ValidationError
from cavity_tem_light_p1.path_safety import stable_plain_bytes
from cavity_tem_light_p2.migration import inspect_migration_limitation
from cavity_tem_light_p2.session_core import (
    SessionCore, sha256_bytes, sha256_file, validate_manual_candidate,
    MANUAL_CANDIDATE_SCHEMA,
)


NORMALIZATION_RULE_ID = "CTL_SPATIAL_UNIT_NORMALIZATION_V1"
EVIDENCE_SCHEMA = "CTL_P3_SPATIAL_CALIBRATION_EVIDENCE_V1"
EDITABLE_BASELINE_REVISION_ID = "REV_20260811_101800_973"
SCALE_REFERENCE_REVISION_ID = "REV_000005"
ABSOLUTE_SCALE_TOLERANCE = Decimal("1e-12")
RELATIVE_SCALE_TOLERANCE = Decimal("1e-6")

_UNIT_FACTORS_CASEFOLDED: dict[str, Decimal] = {
    "nm": Decimal("1"),
    "nanometer": Decimal("1"),
    "nanometers": Decimal("1"),
    "nanometre": Decimal("1"),
    "nanometres": Decimal("1"),
    "µm": Decimal("1000"),
    "μm": Decimal("1000"),
    "um": Decimal("1000"),
    "micron": Decimal("1000"),
    "microns": Decimal("1000"),
    "micrometer": Decimal("1000"),
    "micrometers": Decimal("1000"),
    "micrometre": Decimal("1000"),
    "micrometres": Decimal("1000"),
    "å": Decimal("0.1"),
    "angstrom": Decimal("0.1"),
    "angstroms": Decimal("0.1"),
    "ångström": Decimal("0.1"),
    "ångströms": Decimal("0.1"),
    "pm": Decimal("0.001"),
    "picometer": Decimal("0.001"),
    "picometers": Decimal("0.001"),
    "picometre": Decimal("0.001"),
    "picometres": Decimal("0.001"),
}

_LEGACY_SCALE_X = "session_scale_nm_per_px_x"
_LEGACY_SCALE_Y = "session_scale_nm_per_px_y"


def _fail(code: str, **details: Any) -> None:
    raise ValidationError(code, details={"reason_code": code, **details})


def _decimal(value: Any, field: str, *, positive: bool = False) -> Decimal:
    if isinstance(value, bool):
        _fail("SPATIAL_SCALE_VALUE_INVALID", field=field)
    try:
        converted = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        _fail("SPATIAL_SCALE_VALUE_INVALID", field=field)
    if not converted.is_finite() or (positive and converted <= 0):
        _fail("SPATIAL_SCALE_VALUE_INVALID", field=field)
    return converted


def decimal_text(value: Decimal) -> str:
    normalized = value.normalize()
    text = format(normalized, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return "0" if text in {"", "-0"} else text


def scales_agree(left: Any, right: Any) -> bool:
    """Use the policy's explicit combined absolute/relative tolerance."""

    a = _decimal(left, "scale.left", positive=True)
    b = _decimal(right, "scale.right", positive=True)
    tolerance = max(
        ABSOLUTE_SCALE_TOLERANCE,
        RELATIVE_SCALE_TOLERANCE * max(abs(a), abs(b)),
    )
    return abs(a - b) <= tolerance


def normalize_spatial_unit(raw_unit: Any, *, field: str) -> tuple[str, Decimal]:
    """Return one NFC unit token and its exact factor to nanometres.

    ``A`` is accepted only as ImageJ's exact spatial Angstrom alias.  It is
    checked before case folding so arbitrary lower-case ``a`` is not promoted
    to a spatial unit.
    """

    if raw_unit is None:
        _fail("SPATIAL_SCALE_UNIT_MISSING", field=field)
    normalized = unicodedata.normalize("NFC", str(raw_unit)).strip()
    if not normalized:
        _fail("SPATIAL_SCALE_UNIT_MISSING", field=field)
    if normalized == "A":
        return normalized, Decimal("0.1")
    factor = _UNIT_FACTORS_CASEFOLDED.get(normalized.casefold())
    if factor is None:
        _fail(
            "SPATIAL_SCALE_UNIT_UNSUPPORTED",
            field=field,
            raw_unit=normalized,
        )
    return normalized, factor


def normalize_spatial_calibration(raw: Mapping[str, Any]) -> dict[str, Any]:
    """Recompute both nm/px values from raw values and raw axis units.

    Caller-supplied factors and normalized values are treated only as claims;
    they must agree with this independent recomputation.
    """

    raw_x = _decimal(raw.get("raw_pixel_width"), "raw_pixel_width", positive=True)
    raw_y = _decimal(raw.get("raw_pixel_height"), "raw_pixel_height", positive=True)
    unit_x, factor_x = normalize_spatial_unit(raw.get("raw_x_unit"), field="raw_x_unit")
    unit_y, factor_y = normalize_spatial_unit(raw.get("raw_y_unit"), field="raw_y_unit")
    default_unit, default_factor = normalize_spatial_unit(
        raw.get("default_unit"), field="default_unit"
    )

    # In ImageJ Calibration, getUnit() is the default/X unit.  Y may be
    # independently calibrated, but the default token must not contradict X.
    if default_factor != factor_x:
        _fail(
            "SPATIAL_SCALE_AXIS_UNIT_CONTRADICTION",
            axis="x",
            default_unit=default_unit,
            raw_x_unit=unit_x,
        )

    scale_x = raw_x * factor_x
    scale_y = raw_y * factor_y
    claimed_factor_x = _decimal(raw.get("factor_x_to_nm"), "factor_x_to_nm", positive=True)
    claimed_factor_y = _decimal(raw.get("factor_y_to_nm"), "factor_y_to_nm", positive=True)
    claimed_scale_x = _decimal(raw.get("scale_x_nm_px"), "scale_x_nm_px", positive=True)
    claimed_scale_y = _decimal(raw.get("scale_y_nm_px"), "scale_y_nm_px", positive=True)
    if (
        claimed_factor_x != factor_x
        or claimed_factor_y != factor_y
        or not scales_agree(claimed_scale_x, scale_x)
        or not scales_agree(claimed_scale_y, scale_y)
    ):
        _fail(
            "SPATIAL_SCALE_PROVENANCE_MISMATCH",
            claimed_scale_x_nm_px=decimal_text(claimed_scale_x),
            claimed_scale_y_nm_px=decimal_text(claimed_scale_y),
            recomputed_scale_x_nm_px=decimal_text(scale_x),
            recomputed_scale_y_nm_px=decimal_text(scale_y),
        )
    return {
        "default_unit": default_unit,
        "factor_x_to_nm": decimal_text(factor_x),
        "factor_y_to_nm": decimal_text(factor_y),
        "normalization_rule_id": NORMALIZATION_RULE_ID,
        "raw_pixel_height": decimal_text(raw_y),
        "raw_pixel_width": decimal_text(raw_x),
        "raw_x_unit": unit_x,
        "raw_y_unit": unit_y,
        "scale_x_nm_px": decimal_text(scale_x),
        "scale_y_nm_px": decimal_text(scale_y),
    }


def _legacy_property(properties: Mapping[str, Any], wanted: str, *, field: str) -> Decimal:
    matches = [
        value
        for key, value in properties.items()
        if unicodedata.normalize("NFC", str(key)).casefold() == wanted
    ]
    if len(matches) != 1:
        _fail(
            "SPATIAL_SCALE_PROVENANCE_MISMATCH",
            field=field,
            match_count=len(matches),
        )
    return _decimal(matches[0], field, positive=True)


def _manual_candidate_scale_pair(manifest: Mapping[str, Any], item: Mapping[str, Any], *, label: str) -> tuple[Decimal, Decimal] | None:
    candidates = manifest.get("candidates", [])
    if not isinstance(candidates, list):
        _fail("SPATIAL_SCALE_PROVENANCE_MISMATCH", authority=label, field="candidates")
    matching = [candidate for candidate in candidates if isinstance(candidate, Mapping)
                and candidate.get("candidate_uuid") == item.get("candidate_uuid")
                and candidate.get("candidate_schema") == MANUAL_CANDIDATE_SCHEMA]
    if not matching:
        return None
    if len(matching) != 1:
        _fail("SPATIAL_SCALE_PROVENANCE_MISMATCH", authority=label, field="manual_candidate_link")
    candidate = matching[0]
    try:
        validate_manual_candidate(candidate, item)
    except ValidationError as exc:
        _fail("SPATIAL_SCALE_PROVENANCE_MISMATCH", authority=label, field="manual_candidate_authority", cause=str(exc))
    view = candidate["source_view"]["record"]
    if (view.get("project_uid") != manifest.get("project_uid") or view.get("image_uid") != manifest.get("image_uid")
            or candidate.get("source_sha256") != manifest.get("source_sha256")):
        _fail("SPATIAL_SCALE_PROVENANCE_MISMATCH", authority=label, field="manual_candidate_source_scope")
    return (_decimal(view["scale_x_nm_px"], "manual_view.scale_x_nm_px", positive=True),
            _decimal(view["scale_y_nm_px"], "manual_view.scale_y_nm_px", positive=True))


def revision_legacy_scale(manifest: Mapping[str, Any], *, label: str) -> tuple[Decimal, Decimal] | None:
    """Extract only preserved legacy scale authority from one revision.

    Native sessions need not contain legacy properties.  A partially covered
    migrated inventory is rejected. Only linked, validated P7 manual objects
    may use their independently recorded view scale instead of legacy fields.
    """

    objects = manifest.get("objects")
    if not isinstance(objects, list):
        _fail("SPATIAL_SCALE_PROVENANCE_MISMATCH", authority=label, field="objects")
    if not objects:
        return None
    has_legacy = [isinstance(item.get("legacy_properties"), Mapping) for item in objects]
    if not any(has_legacy):
        return None
    pairs: list[tuple[Decimal, Decimal]] = []
    manual_pairs: list[tuple[Decimal, Decimal]] = []
    for index, item in enumerate(objects):
        if not has_legacy[index]:
            pair = _manual_candidate_scale_pair(manifest, item, label=label)
            if pair is None:
                _fail("SPATIAL_SCALE_PROVENANCE_MISMATCH", authority=label, field="legacy_properties_coverage")
            manual_pairs.append(pair)
            continue
        properties = item["legacy_properties"]
        pairs.append(
            (
                _legacy_property(
                    properties,
                    _LEGACY_SCALE_X,
                    field=f"{label}.objects[{index}].Session_scale_nm_per_px_x",
                ),
                _legacy_property(
                    properties,
                    _LEGACY_SCALE_Y,
                    field=f"{label}.objects[{index}].Session_scale_nm_per_px_y",
                ),
            )
        )
    expected_x, expected_y = pairs[0]
    if any(
        not scales_agree(x, expected_x) or not scales_agree(y, expected_y)
        for x, y in pairs[1:] + manual_pairs
    ):
        _fail(
            "SPATIAL_SCALE_PROVENANCE_MISMATCH",
            authority=label,
            field="legacy_scale_consistency",
        )
    return expected_x, expected_y


def _checked_source_calibration(binding: Mapping[str, Any], image_context: Mapping[str, Any]) -> tuple[dict[str, Any], int, int, int]:
    calibration = normalize_spatial_calibration(image_context)
    if binding.get("master_pixel_hash_status") != "VERIFIED":
        _fail("SPATIAL_SCALE_PROVENANCE_MISMATCH", authority="source_registry")
    master = image_context.get("master_pixel_evidence")
    if not isinstance(master, Mapping):
        _fail("SPATIAL_SCALE_PROVENANCE_MISMATCH", field="master_pixel_evidence")
    try:
        width, height, bit_depth = (int(image_context.get(key)) for key in ("width_px", "height_px", "bit_depth"))
    except (TypeError, ValueError, OverflowError):
        _fail("SPATIAL_SCALE_VALUE_INVALID", field="image_dimensions_or_bit_depth")
    if width <= 0 or height <= 0 or bit_depth not in {8, 16, 24, 32}:
        _fail("SPATIAL_SCALE_VALUE_INVALID", field="image_dimensions_or_bit_depth")
    if (master.get("sha256") != binding["master_pixel_sha256"] or master.get("source_sha256") != binding["source_sha256"]
            or master.get("width") != width or master.get("height") != height or master.get("bit_depth") != bit_depth):
        _fail("SPATIAL_SCALE_PROVENANCE_MISMATCH", authority="source_master_pixels")
    if not str(image_context.get("fiji_imagej_version") or "").strip() or not str(image_context.get("decoder_opening_method") or "").strip():
        _fail("SPATIAL_SCALE_PROVENANCE_MISMATCH", field="fiji_or_decoder_evidence")
    return calibration, width, height, bit_depth


def validate_revision_scale_snapshot(
    manifest: Mapping[str, Any], *, source_binding: Mapping[str, Any], image_context: Mapping[str, Any], label: str = "pending_revision"
) -> tuple[dict[str, Any], int, int, int]:
    """Check caller scale/proposal evidence before writes, without scanning history."""
    calibration, width, height, bit_depth = _checked_source_calibration(source_binding, image_context)
    pair = revision_legacy_scale(manifest, label=label)
    expected = (Decimal(calibration["scale_x_nm_px"]), Decimal(calibration["scale_y_nm_px"]))
    if pair is not None and any(not scales_agree(value, wanted) for value, wanted in zip(pair, expected)):
        _fail("SPATIAL_SCALE_PROVENANCE_MISMATCH", authority=label, field="revision_scale_vs_current_calibration")
    for item in manifest["objects"]:
        manual_pair = _manual_candidate_scale_pair(manifest, item, label=label)
        if manual_pair is None:
            continue
        candidate = next(candidate for candidate in manifest["candidates"] if candidate.get("candidate_uuid") == item.get("candidate_uuid"))
        view = candidate["source_view"]["record"]
        if (any(not scales_agree(value, wanted) for value, wanted in zip(manual_pair, expected))
                or candidate["master_pixel_sha256"] != source_binding["master_pixel_sha256"]
                or view["width_px"] != width or view["height_px"] != height or view["bit_depth"] != bit_depth):
            _fail("SPATIAL_SCALE_PROVENANCE_MISMATCH", authority=label, field="manual_view_vs_current_calibration")
    return calibration, width, height, bit_depth


def _verified_record_metadata(core: SessionCore, record: Any) -> dict[str, Any]:
    """Verify that one session still binds the selected physical source."""

    metadata = core._metadata(record.session_root)
    binding = core._binding(record.image_uid)
    if (
        metadata.get("analysis_session_uid") != record.analysis_session_uid
        or metadata.get("image_uid") != record.image_uid
        or metadata.get("source_sha256") != binding["source_sha256"]
        or metadata.get("master_pixel_hash_status") != "VERIFIED"
        or metadata.get("master_pixel_sha256") != binding["master_pixel_sha256"]
    ):
        _fail(
            "SPATIAL_SCALE_PROVENANCE_MISMATCH",
            authority="session_metadata",
            analysis_session_uid=record.analysis_session_uid,
        )
    return metadata


def _clone_source_record(core: SessionCore, record: Any) -> Any | None:
    """Resolve one clone edge by its verified UID, never by a directory name."""

    metadata = _verified_record_metadata(core, record)
    if metadata.get("origin_type") != "CLONE_REVISION":
        return None
    clone_path = record.session_root / "clone_provenance.json"
    clone_bytes = stable_plain_bytes(clone_path, label="session clone provenance")
    if sha256_bytes(clone_bytes) != metadata.get("clone_provenance_sha256"):
        _fail("SPATIAL_SCALE_PROVENANCE_MISMATCH", authority="clone_provenance")
    clone = loads_canonical_json(clone_bytes)
    source = clone.get("source") if isinstance(clone, Mapping) else None
    if not isinstance(source, Mapping):
        _fail("SPATIAL_SCALE_PROVENANCE_MISMATCH", authority="clone_provenance")
    source_record = core.session_by_uid(
        record.image_uid, str(source.get("session_uid") or "")
    )
    if (
        source_record.analysis_session_id != source.get("session_id")
        or source_record.analysis_session_uid == record.analysis_session_uid
    ):
        _fail("SPATIAL_SCALE_PROVENANCE_MISMATCH", authority="clone_provenance")
    _verified_record_metadata(core, source_record)
    return source_record


def _clone_lineage(core: SessionCore, record: Any) -> list[Any]:
    lineage: list[Any] = []
    seen: set[str] = set()
    current = record
    while current is not None:
        if current.analysis_session_uid in seen:
            _fail("SPATIAL_SCALE_PROVENANCE_MISMATCH", authority="clone_cycle")
        seen.add(current.analysis_session_uid)
        _verified_record_metadata(core, current)
        lineage.append(current)
        current = _clone_source_record(core, current)
    return lineage


def _all_image_records(core: SessionCore, image_uid: str) -> list[Any]:
    """Return the closed registry inventory, resolved by session UUID."""

    return [
        core.session_by_uid(image_uid, row["analysis_session_uid"])
        for row in core._read_registry(image_uid)
    ]


def _verified_baseline_manifest(
    core: SessionCore, record: Any
) -> tuple[dict[str, Any], str, str, str] | None:
    """Locate the one migrated editable baseline in the clone lineage/image.

    A clone does not copy ``legacy_quarantine``.  Consequently looking only at
    its own recovery directory silently drops one of the three required scale
    authorities.  Follow verified clone provenance first; only if that yields
    none, examine the closed same-image session registry and require a unique
    match.  ``inspect_migration_limitation`` validates quarantine control
    evidence; the quarantined revision payload is never read here.
    """

    lineage = _clone_lineage(core, record)
    candidates = list(lineage)
    known = {candidate.analysis_session_uid for candidate in candidates}
    candidates.extend(
        item
        for item in _all_image_records(core, record.image_uid)
        if item.analysis_session_uid not in known
    )
    matches: list[tuple[dict[str, Any], str, str, str]] = []
    saw_migration_limitation = False
    for candidate in candidates:
        limitation = inspect_migration_limitation(candidate.session_root)
        if limitation is None:
            continue
        saw_migration_limitation = True
        revision_id = str(limitation.get("editable_baseline_revision") or "")
        if revision_id != EDITABLE_BASELINE_REVISION_ID:
            continue
        _verified_record_metadata(core, candidate)
        revision_root = candidate.session_root / "revisions" / f"REV_{revision_id}"
        if not revision_root.is_dir() or revision_root.is_symlink():
            _fail(
                "SPATIAL_SCALE_PROVENANCE_MISMATCH",
                authority="editable_baseline",
                revision_id=revision_id,
            )
        manifest = core._verify_revision(candidate, revision_root)
        digest = sha256_file(revision_root / "revision_manifest.json")
        if manifest.get("revision_id") != revision_id:
            _fail(
                "SPATIAL_SCALE_PROVENANCE_MISMATCH",
                authority="editable_baseline",
                field="revision_id",
            )
        matches.append(
            (manifest, digest, revision_id, candidate.analysis_session_uid)
        )
    unique = {
        (digest, session_uid): (manifest, digest, revision_id, session_uid)
        for manifest, digest, revision_id, session_uid in matches
    }
    if not saw_migration_limitation:
        # A genuinely native schema-2 lineage has no migrated baseline.  The
        # three-authority rule applies whenever migration control evidence is
        # present; it must not manufacture a legacy authority for native data.
        return None
    if len(unique) != 1:
        _fail(
            "SPATIAL_SCALE_PROVENANCE_MISMATCH",
            authority="editable_baseline",
            match_count=len(unique),
        )
    return next(iter(unique.values()))


def _verified_scale_reference_manifest(
    core: SessionCore, record: Any
) -> tuple[dict[str, Any], str, str]:
    """Resolve REV_000005 from the selected session or its clone ancestry."""

    lineage = _clone_lineage(core, record)
    matches: list[tuple[dict[str, Any], str, str]] = []
    for candidate in lineage:
        revision_root = (
            candidate.session_root
            / "revisions"
            / f"REV_{SCALE_REFERENCE_REVISION_ID}"
        )
        if not revision_root.exists() and not revision_root.is_symlink():
            continue
        if not revision_root.is_dir() or revision_root.is_symlink():
            _fail(
                "SPATIAL_SCALE_PROVENANCE_MISMATCH",
                authority="REV_000005",
            )
        manifest = core._verify_revision(candidate, revision_root)
        digest = sha256_file(revision_root / "revision_manifest.json")
        matches.append((manifest, digest, candidate.analysis_session_uid))
        break
    if not matches:
        for candidate in _all_image_records(core, record.image_uid):
            revision_root = (
                candidate.session_root
                / "revisions"
                / f"REV_{SCALE_REFERENCE_REVISION_ID}"
            )
            if not revision_root.exists() and not revision_root.is_symlink():
                continue
            _verified_record_metadata(core, candidate)
            manifest = core._verify_revision(candidate, revision_root)
            digest = sha256_file(revision_root / "revision_manifest.json")
            matches.append((manifest, digest, candidate.analysis_session_uid))
    if len(matches) != 1 or matches[0][0].get("revision_id") != SCALE_REFERENCE_REVISION_ID:
        _fail(
            "SPATIAL_SCALE_PROVENANCE_MISMATCH",
            authority="REV_000005",
            match_count=len(matches),
        )
    return matches[0]


def verify_spatial_scale_provenance(
    *,
    core: SessionCore,
    record: Any,
    revision_manifest: Mapping[str, Any],
    revision_manifest_sha256: str,
    image_context: Mapping[str, Any],
) -> dict[str, Any]:
    """Bind one normalized Fiji scale to source, baseline and current revision."""

    binding = core._binding(record.image_uid)
    calibration, width, height, bit_depth = validate_revision_scale_snapshot(
        revision_manifest, source_binding=binding, image_context=image_context, label="current_revision"
    )

    current_scale = revision_legacy_scale(revision_manifest, label="current_revision")
    baseline = _verified_baseline_manifest(core, record)
    baseline_manifest: Mapping[str, Any] | None = None
    baseline_scale: tuple[Decimal, Decimal] | None = None
    baseline_sha: str | None = None
    baseline_id: str | None = None
    baseline_session_uid: str | None = None
    rev5_manifest: Mapping[str, Any] | None = None
    rev5_scale: tuple[Decimal, Decimal] | None = None
    rev5_sha: str | None = None
    rev5_session_uid: str | None = None
    if baseline is not None:
        baseline_manifest, baseline_sha, baseline_id, baseline_session_uid = baseline
        baseline_scale = revision_legacy_scale(
            baseline_manifest, label=f"editable_baseline.{baseline_id}"
        )
        if baseline_scale is None:
            _fail(
                "SPATIAL_SCALE_PROVENANCE_MISMATCH",
                authority="editable_baseline",
                field="legacy_scale_absent",
            )
        rev5_manifest, rev5_sha, rev5_session_uid = _verified_scale_reference_manifest(
            core, record
        )
        rev5_scale = revision_legacy_scale(rev5_manifest, label="REV_000005")
        if rev5_scale is None:
            _fail(
                "SPATIAL_SCALE_PROVENANCE_MISMATCH",
                authority="REV_000005",
                field="legacy_scale_absent",
            )
    normalized_pair = (
        Decimal(calibration["scale_x_nm_px"]),
        Decimal(calibration["scale_y_nm_px"]),
    )
    for authority, pair in (
        ("current_revision", current_scale),
        ("editable_baseline", baseline_scale),
        ("REV_000005", rev5_scale),
    ):
        if pair is not None and (
            not scales_agree(normalized_pair[0], pair[0])
            or not scales_agree(normalized_pair[1], pair[1])
        ):
            _fail(
                "SPATIAL_SCALE_PROVENANCE_MISMATCH",
                authority=authority,
                normalized_scale_x_nm_px=calibration["scale_x_nm_px"],
                normalized_scale_y_nm_px=calibration["scale_y_nm_px"],
                reference_scale_x_nm_px=decimal_text(pair[0]),
                reference_scale_y_nm_px=decimal_text(pair[1]),
            )

    fiji_version = str(image_context.get("fiji_imagej_version") or "").strip()
    decoder = str(image_context.get("decoder_opening_method") or "").strip()
    if not fiji_version or not decoder:
        _fail("SPATIAL_SCALE_PROVENANCE_MISMATCH", field="fiji_or_decoder_evidence")
    evidence = {
        "bit_depth": bit_depth,
        "decoder_opening_method": decoder,
        "default_unit": calibration["default_unit"],
        "editable_baseline_analysis_session_uid": baseline_session_uid,
        "editable_baseline_manifest_sha256": baseline_sha,
        "editable_baseline_revision_id": baseline_id,
        "editable_baseline_revision_uid": (
            None if baseline_manifest is None else str(baseline_manifest["revision_uid"])
        ),
        "factor_x_to_nm": calibration["factor_x_to_nm"],
        "factor_y_to_nm": calibration["factor_y_to_nm"],
        "fiji_imagej_version": fiji_version,
        "height": height,
        "image_id": binding["image_id"],
        "master_pixel_sha256": binding["master_pixel_sha256"],
        "normalization_rule_id": NORMALIZATION_RULE_ID,
        "raw_pixel_height": calibration["raw_pixel_height"],
        "raw_pixel_width": calibration["raw_pixel_width"],
        "raw_x_unit": calibration["raw_x_unit"],
        "raw_y_unit": calibration["raw_y_unit"],
        "rev_000005_analysis_session_uid": rev5_session_uid,
        "rev_000005_manifest_sha256": rev5_sha,
        "rev_000005_revision_id": (
            None if rev5_manifest is None else str(rev5_manifest["revision_id"])
        ),
        "rev_000005_revision_uid": (
            None if rev5_manifest is None else str(rev5_manifest["revision_uid"])
        ),
        "revision_id": str(revision_manifest["revision_id"]),
        "revision_manifest_sha256": revision_manifest_sha256,
        "revision_uid": str(revision_manifest["revision_uid"]),
        "scale_x_nm_px": calibration["scale_x_nm_px"],
        "scale_y_nm_px": calibration["scale_y_nm_px"],
        "schema": EVIDENCE_SCHEMA,
        "source_sha256": binding["source_sha256"],
        "width": width,
    }
    evidence_bytes = canonical_json_bytes(evidence)
    return {
        "calibration": calibration,
        "evidence": evidence,
        "evidence_sha256": sha256_bytes(evidence_bytes),
    }


def _object_value(item: Mapping[str, Any], *names: str) -> Any:
    geometry = item.get("geometry")
    sources = [geometry] if isinstance(geometry, Mapping) else []
    sources.append(item)
    legacy = item.get("legacy_properties")
    if isinstance(legacy, Mapping):
        sources.append(legacy)
    wanted = {name.casefold() for name in names}
    found: list[Any] = []
    for source in sources:
        for key, value in source.items():
            if str(key).casefold() in wanted and value is not None and value != "":
                found.append(value)
    distinct = {str(value) for value in found}
    if len(distinct) > 1:
        _fail(
            "SCALE_ANISOTROPY_REQUIRES_PROTOCOL",
            field="|".join(names),
            conflicting_values=sorted(distinct),
        )
    return found[0] if found else None


def transient_physical_objects(
    objects: Sequence[Mapping[str, Any]], calibration: Mapping[str, Any]
) -> list[dict[str, Any]]:
    """Return a non-authoritative RUN view recomputed from pixel geometry.

    This helper never writes a revision.  It is intended for the Prompt-3 RUN
    adapter so contaminated physical fields in ``REV_000005`` are not reused.
    """

    sx = _decimal(calibration.get("scale_x_nm_px"), "scale_x_nm_px", positive=True)
    sy = _decimal(calibration.get("scale_y_nm_px"), "scale_y_nm_px", positive=True)
    anisotropic = not scales_agree(sx, sy)
    derived: list[dict[str, Any]] = []
    for index, raw in enumerate(objects):
        item = loads_canonical_json(canonical_json_bytes({"value": dict(raw)}))["value"]
        geometry = item.get("geometry")
        if not isinstance(geometry, dict):
            _fail("SPATIAL_SCALE_PROVENANCE_MISMATCH", field=f"objects[{index}].geometry")
        center_x_px = _decimal(geometry.get("center_x_px"), f"objects[{index}].center_x_px")
        center_y_px = _decimal(geometry.get("center_y_px"), f"objects[{index}].center_y_px")
        width_px = _decimal(
            geometry.get("width_px"), f"objects[{index}].width_px", positive=True
        )
        height_px = _decimal(
            geometry.get("height_px"), f"objects[{index}].height_px", positive=True
        )
        width_nm = width_px * sx
        height_nm = height_px * sy
        if anisotropic:
            protocol = str(
                _object_value(
                    item,
                    "sampling_axis_method",
                    "Sampling_axis_method",
                )
                or ""
            )
            measurement = str(
                _object_value(
                    item,
                    "measurement_protocol",
                    "Measurement_protocol",
                    "primary_measurement_protocol",
                )
                or ""
            )
            protocol_version = str(
                _object_value(
                    item,
                    "sampling_axis_method_version",
                    "Sampling_axis_method_version",
                )
                or ""
            )
            if (
                measurement != "CAVITY_CIRCLE"
                or protocol != "CIRCLE_CONSERVATIVE_MAX_SCALE"
                or protocol_version != "ANISOTROPIC_AXIS_V1"
            ):
                _fail(
                    "SCALE_ANISOTROPY_REQUIRES_PROTOCOL",
                    index=index,
                    measurement_protocol=measurement,
                    sampling_axis_method=protocol,
                    sampling_axis_method_version=protocol_version,
                )
            diameter = max(width_nm, height_nm)
        else:
            diameter = (width_nm + height_nm) / Decimal(2)
        geometry["center_x_nm"] = decimal_text(center_x_px * sx)
        geometry["center_y_nm"] = decimal_text(center_y_px * sy)
        geometry["diameter_nm"] = decimal_text(diameter)
        # This is a transient RUN adapter view, not a revision entity.  Never
        # retain a digest that authenticated the pre-conversion bytes.
        item.pop("object_sha256", None)
        item["center"] = {
            "x": float(center_x_px),
            "y": float(center_y_px),
        }
        item["diameter_nm"] = decimal_text(diameter)
        # These are derived outputs and must be rebuilt by the RUN assembler.
        for field in (
            "projected_area_nm2",
            "equivalent_diameter_nm",
            "major_diameter_nm",
            "minor_diameter_nm",
            "perimeter_nm",
            "final_geometry_sha256",
        ):
            item.pop(field, None)
            geometry.pop(field, None)
        derived.append(item)
    return derived


__all__ = [
    "ABSOLUTE_SCALE_TOLERANCE",
    "EDITABLE_BASELINE_REVISION_ID",
    "EVIDENCE_SCHEMA",
    "NORMALIZATION_RULE_ID",
    "RELATIVE_SCALE_TOLERANCE",
    "SCALE_REFERENCE_REVISION_ID",
    "decimal_text",
    "normalize_spatial_calibration",
    "normalize_spatial_unit",
    "revision_legacy_scale",
    "scales_agree",
    "transient_physical_objects",
    "validate_revision_scale_snapshot",
    "verify_spatial_scale_provenance",
]
