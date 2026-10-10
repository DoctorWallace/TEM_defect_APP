"""Pure scientific calculations allowed in Prompt 1.

This module implements integrity-preserving statistics, policy flags,
anisotropic sampling, border preflight, closed geometric authority, and
explicitly labelled modelled (not observed) 3-D quantities.  It deliberately
does not implement Poisson intervals or the Prompt-3 exact full-geometry
tangency engine.
"""

from __future__ import annotations

from copy import deepcopy
from decimal import Decimal
import hashlib
import math
from typing import Any, Iterable, Mapping, Sequence

from .canonical_json import canonical_subobject_bytes
from .contract import (
    CAVITY_CLASSES,
    CAVITY_PROTOCOLS,
    CLASSIFICATION_POLICY,
    TYPED_NUMERIC_STATUSES,
    VALIDITY_UPDATE_MODE,
    assert_nonfinite_free,
    is_finite_number,
    require_finite_number,
    sort_records_for_statistic,
    validate_boolean_01,
    validate_typed_magnitude,
)
from .errors import ValidationError


ANISOTROPIC_AXIS_VERSION = "ANISOTROPIC_AXIS_V1"
COORDINATE_TRANSFORM_VERSION = "AXIS_ALIGNED_XY_V1"
SAMPLING_POLICY_VERSION = "PROVISIONAL_SAMPLING_POLICY_V1"
SAMPLING_POLICY_STATUS = "PROVISIONAL"
BORDER_ALGORITHM_VERSION = "R9_LEGACY_APPROX"
BORDER_ALGORITHM_STATUS = "PROVISIONAL"
CENTER_BORDER_EPSILON_PX = 1e-6
GEOMETRY_HASH_PROFILE_ID = "GEOMETRY_HASH_V1"
GEOMETRY_STATUS_AUTHORITY_ROLE = "PROTOCOL_APPLICABILITY_METADATA"


def _fail(message: str, **details: Any) -> None:
    raise ValidationError(message, details=details)


def _finite_derived(value: float, *, field: str, strictly_positive: bool = False) -> float:
    if not math.isfinite(value):
        _fail("derived scientific result is non-finite", field=field, value=repr(value))
    if strictly_positive and value <= 0:
        _fail("derived scientific result is not positive", field=field, value=value)
    return value


def _as_finite_float(
    value: Any,
    *,
    field: str,
    minimum: int | float | Decimal | None = None,
    strictly_positive: bool = False,
) -> float:
    require_finite_number(
        value,
        field=field,
        minimum=minimum,
        strictly_positive=strictly_positive,
    )
    try:
        converted = float(value)
    except (OverflowError, ValueError, TypeError):
        _fail("scientific number cannot be represented finitely", field=field)
    return _finite_derived(converted, field=field, strictly_positive=strictly_positive)


def _validated_values(values: Sequence[Any], *, require_sorted: bool = False) -> list[float]:
    if isinstance(values, (str, bytes)) or not isinstance(values, Sequence):
        _fail("statistical input must be a sequence")
    copied: list[float] = []
    for index, value in enumerate(values):
        copied.append(_as_finite_float(value, field=f"values[{index}]"))
    if require_sorted and any(copied[index] > copied[index + 1] for index in range(len(copied) - 1)):
        _fail("percentile input must already be sorted")
    return copied


def percentile_sorted(sorted_values: Sequence[Any], percentile: Any) -> float | None:
    """Linear percentile with the closed ``(n-1)*p/100`` convention.

    The upper index is computed without ``ceil`` and the source sequence is
    never changed.  Empty input returns the typed-absence value ``None``; its
    caller must persist the sibling status ``UNDEFINED``.
    """

    values = _validated_values(sorted_values, require_sorted=True)
    p = _as_finite_float(percentile, field="percentile")
    if p < 0 or p > 100:
        _fail("percentile must be in [0,100]", percentile=p)
    count = len(values)
    if count == 0:
        return None
    position = (count - 1) * p / 100.0
    lower = math.floor(position)
    upper = lower if position == lower else lower + 1
    if lower == upper:
        return values[lower]
    result = values[lower] + (position - lower) * (values[upper] - values[lower])
    return _finite_derived(result, field="percentile_result")


def percentile(values: Sequence[Any], p: Any) -> float | None:
    copied = _validated_values(values)
    copied.sort()
    return percentile_sorted(copied, p)


def _typed_stat(value: float | None) -> tuple[float | None, str]:
    return (value, "KNOWN") if value is not None else (None, "UNDEFINED")


def compute_stats(values: Sequence[Any]) -> dict[str, Any]:
    """Compute deterministic descriptive statistics on a private sorted copy."""

    copied = _validated_values(values)
    ordered = sorted(copied)
    count = len(ordered)
    if count == 0:
        result: dict[str, Any] = {"N": 0}
        for field in ("minimum", "p25", "p50", "p75", "maximum", "mean"):
            result[field] = None
            result[f"{field}_status"] = "UNDEFINED"
        return result
    try:
        mean = math.fsum(ordered) / count
    except OverflowError:
        _fail("statistical mean overflowed")
    calculations = {
        "minimum": ordered[0],
        "p25": percentile_sorted(ordered, 25),
        "p50": percentile_sorted(ordered, 50),
        "p75": percentile_sorted(ordered, 75),
        "maximum": ordered[-1],
        "mean": _finite_derived(mean, field="mean"),
    }
    result = {"N": count}
    for field, value in calculations.items():
        result[field] = value
        result[f"{field}_status"] = "KNOWN"
    return result


lightPercentileSorted = percentile_sorted
lightComputeStats = compute_stats


def compute_record_statistics(
    records: Sequence[Mapping[str, Any]],
    *,
    numeric_field: str = "equivalent_diameter_nm",
) -> dict[str, Any]:
    """Sort whole copied observations while retaining every object association."""

    ordered_records = sort_records_for_statistic(records, numeric_field=numeric_field)
    stats = compute_stats([record[numeric_field] for record in ordered_records])
    return {"numeric_field": numeric_field, "ordered_records": ordered_records, "statistics": stats}


def derive_inclusion_flags(record: Mapping[str, Any]) -> dict[str, int]:
    """Derive the six estimand flags independently from class and endpoint flags."""

    cavity_class = record.get("cavity_class")
    if cavity_class not in CAVITY_CLASSES:
        _fail("invalid cavity class", value=cavity_class)
    result: dict[str, int] = {}
    for endpoint in ("count", "size", "position"):
        field = f"{endpoint}_valid"
        if field not in record:
            _fail("endpoint validity flag is missing", field=field)
        valid = validate_boolean_01(record[field], field=field)
        result[f"primary_{endpoint}_included"] = int(cavity_class == "confirmed" and valid == 1)
        result[f"sensitivity_{endpoint}_included"] = int(
            cavity_class in {"confirmed", "uncertain"} and valid == 1
        )
    return result


def reconcile_inclusion_flags(record: Mapping[str, Any]) -> None:
    expected = derive_inclusion_flags(record)
    for field, value in expected.items():
        if field not in record:
            _fail("derived inclusion flag is missing", field=field)
        validate_boolean_01(record[field], field=field)
        if record[field] != value:
            _fail(
                "stored inclusion flag contradicts the closed policy",
                field=field,
                expected=value,
                observed=record[field],
            )


def reclassify_without_rewriting_validity(record: Mapping[str, Any], new_class: str) -> dict[str, Any]:
    """Change class on a copy; validity flags remain byte-for-byte values."""

    if new_class not in CAVITY_CLASSES:
        _fail("invalid cavity class", value=new_class)
    for field in ("count_valid", "size_valid", "position_valid"):
        if field not in record:
            _fail("endpoint validity flag is missing", field=field)
        validate_boolean_01(record[field], field=field)
    result = deepcopy(dict(record))
    preserved = {field: result[field] for field in ("count_valid", "size_valid", "position_valid")}
    result["cavity_class"] = new_class
    result.update(derive_inclusion_flags(result))
    if any(result[field] != value for field, value in preserved.items()):  # pragma: no cover - defensive
        _fail("classification changed an independent validity flag")
    return result


def validate_scientific_policy(record: Mapping[str, Any]) -> None:
    if record.get("classification_policy") != CLASSIFICATION_POLICY:
        _fail("classification policy mismatch", observed=record.get("classification_policy"))
    if record.get("validity_update_mode") != VALIDITY_UPDATE_MODE:
        _fail("validity update mode mismatch", observed=record.get("validity_update_mode"))


def count_endpoint_validities(records: Sequence[Mapping[str, Any]]) -> dict[str, int]:
    counts = {"N_count_valid": 0, "N_size_valid": 0, "N_position_valid": 0}
    for index, record in enumerate(records):
        if not isinstance(record, Mapping):
            _fail("observation is not a record", row=index)
        reconcile_inclusion_flags(record)
        for endpoint in ("count", "size", "position"):
            value = validate_boolean_01(record[f"{endpoint}_valid"], field=f"{endpoint}_valid")
            counts[f"N_{endpoint}_valid"] += value
    return counts


def zero_event_summary(
    records: Sequence[Mapping[str, Any]],
    *,
    net_area_nm2: Any | None = None,
    net_area_um2: Any | None = None,
    volumetric_context: Mapping[str, Any] | None = None,
    unavailable_volumetric_status: str = "NOT_APPLICABLE",
) -> dict[str, Any]:
    """Build the Prompt-1 RUN statistics block, including valid N=0.

    Exactly one area unit may be supplied.  A nominal volumetric zero is
    emitted only when the caller proves thickness, model, and assumptions via
    three explicit boolean fields and a positive effective volume.
    """

    if (net_area_nm2 is None) == (net_area_um2 is None):
        _fail("provide exactly one of net_area_nm2 or net_area_um2")
    if net_area_nm2 is None:
        area_um2 = _as_finite_float(
            net_area_um2,
            field="net_area_um2",
            strictly_positive=True,
        )
        area_nm2 = _finite_derived(
            area_um2 * 1_000_000.0,
            field="net_area_nm2",
            strictly_positive=True,
        )
    else:
        area_nm2 = _as_finite_float(
            net_area_nm2,
            field="net_area_nm2",
            strictly_positive=True,
        )
        area_um2 = _finite_derived(
            area_nm2 / 1_000_000.0,
            field="net_area_um2",
            strictly_positive=True,
        )

    counts = count_endpoint_validities(records)
    size_values: list[Any] = []
    for index, record in enumerate(records):
        if record["size_valid"] == 1:
            if "equivalent_diameter_nm" not in record:
                _fail("size-valid record lacks equivalent diameter", row=index)
            require_finite_number(
                record["equivalent_diameter_nm"],
                field=f"records[{index}].equivalent_diameter_nm",
                strictly_positive=True,
            )
            size_values.append(record["equivalent_diameter_nm"])
    if len(size_values) != counts["N_size_valid"]:
        _fail("N_size_valid does not reconcile with size records")

    try:
        mean_size = (
            None
            if not size_values
            else math.fsum(float(value) for value in size_values) / len(size_values)
        )
    except OverflowError:
        _fail("mean size overflowed")
    if mean_size is not None:
        mean_size = _finite_derived(mean_size, field="mean_size_nm", strictly_positive=True)
    result: dict[str, Any] = {
        "zero_event_status": "ZERO_EVENTS_VALID" if len(records) == 0 else "EVENTS_PRESENT",
        **counts,
        "mean_size_nm": mean_size,
        "mean_size_nm_status": "UNDEFINED" if mean_size is None else "KNOWN",
        "net_area_nm2": area_nm2,
        "density_N_per_um2": _finite_derived(
            counts["N_count_valid"] / area_um2,
            field="density_N_per_um2",
        ),
        "density_ci_status": "NOT_COMPUTED",
        "density_intervals": [],
    }
    if volumetric_context is None:
        if unavailable_volumetric_status not in TYPED_NUMERIC_STATUSES - {"KNOWN", "UNDEFINED"}:
            _fail("invalid unavailable volumetric status", status=unavailable_volumetric_status)
        result["density_N_per_m3_nominal"] = None
        result["density_N_per_m3_nominal_status"] = unavailable_volumetric_status
    else:
        required = {
            "thickness_validated",
            "model_validated",
            "assumptions_validated",
            "effective_volume_m3",
        }
        missing = sorted(required - set(volumetric_context))
        if missing:
            _fail("volumetric context is incomplete", missing=missing)
        for field in ("thickness_validated", "model_validated", "assumptions_validated"):
            if volumetric_context[field] is not True:
                _fail("nominal volumetric density context is not validated", field=field)
        volume = require_finite_number(
            volumetric_context["effective_volume_m3"],
            field="effective_volume_m3",
            strictly_positive=True,
        )
        result["density_N_per_m3_nominal"] = _finite_derived(
            counts["N_count_valid"] / float(volume),
            field="density_N_per_m3_nominal",
        )
        result["density_N_per_m3_nominal_status"] = "KNOWN"
    return result


_SCALE_ORIGINS = {
    "BIOFORMATS_METADATA_CONFIRMED",
    "MANUAL_XY_REFERENCE",
    "MANUAL_LINE_REFERENCE",
    "IMPORTED_LEGACY",
    "OTHER",
    "UNKNOWN",
}
_SCALE_TYPED_FIELDS = (
    "source_scale_x_nm_px",
    "source_scale_y_nm_px",
    "scale_uncertainty_x_nm_px",
    "scale_uncertainty_y_nm_px",
    "scale_reference_length_px",
    "scale_reference_length_nm",
    "scale_reference_angle_deg",
)


def build_scale_record(
    *,
    scale_x_nm_px: Any,
    scale_y_nm_px: Any,
    scale_origin: str,
    coordinate_origin_x_nm: Any,
    coordinate_origin_y_nm: Any,
    source_scale_x_nm_px: Any | None = None,
    source_scale_x_nm_px_status: str = "NOT_APPLICABLE",
    source_scale_y_nm_px: Any | None = None,
    source_scale_y_nm_px_status: str = "NOT_APPLICABLE",
    scale_uncertainty_x_nm_px: Any | None = None,
    scale_uncertainty_x_nm_px_status: str = "NOT_MEASURED",
    scale_uncertainty_y_nm_px: Any | None = None,
    scale_uncertainty_y_nm_px_status: str = "NOT_MEASURED",
    scale_reference_length_px: Any | None = None,
    scale_reference_length_px_status: str = "NOT_APPLICABLE",
    scale_reference_length_nm: Any | None = None,
    scale_reference_length_nm_status: str = "NOT_APPLICABLE",
    scale_reference_angle_deg: Any | None = None,
    scale_reference_angle_deg_status: str = "NOT_APPLICABLE",
) -> dict[str, Any]:
    record = {
        "scale_x_nm_px": _as_finite_float(
            scale_x_nm_px,
            field="scale_x_nm_px",
            strictly_positive=True,
        ),
        "scale_y_nm_px": _as_finite_float(
            scale_y_nm_px,
            field="scale_y_nm_px",
            strictly_positive=True,
        ),
        "source_scale_x_nm_px": source_scale_x_nm_px,
        "source_scale_x_nm_px_status": source_scale_x_nm_px_status,
        "source_scale_y_nm_px": source_scale_y_nm_px,
        "source_scale_y_nm_px_status": source_scale_y_nm_px_status,
        "scale_origin": scale_origin,
        "coordinate_transform_version": COORDINATE_TRANSFORM_VERSION,
        "coordinate_origin_x_nm": _as_finite_float(
            coordinate_origin_x_nm,
            field="coordinate_origin_x_nm",
        ),
        "coordinate_origin_y_nm": _as_finite_float(
            coordinate_origin_y_nm,
            field="coordinate_origin_y_nm",
        ),
        "scale_confirmed": 1,
        "scale_uncertainty_x_nm_px": scale_uncertainty_x_nm_px,
        "scale_uncertainty_x_nm_px_status": scale_uncertainty_x_nm_px_status,
        "scale_uncertainty_y_nm_px": scale_uncertainty_y_nm_px,
        "scale_uncertainty_y_nm_px_status": scale_uncertainty_y_nm_px_status,
        "scale_reference_length_px": scale_reference_length_px,
        "scale_reference_length_px_status": scale_reference_length_px_status,
        "scale_reference_length_nm": scale_reference_length_nm,
        "scale_reference_length_nm_status": scale_reference_length_nm_status,
        "scale_reference_angle_deg": scale_reference_angle_deg,
        "scale_reference_angle_deg_status": scale_reference_angle_deg_status,
    }
    validate_scale_record(record)
    return record


def validate_scale_record(record: Mapping[str, Any]) -> None:
    required = {
        "scale_x_nm_px",
        "scale_y_nm_px",
        "scale_origin",
        "coordinate_transform_version",
        "coordinate_origin_x_nm",
        "coordinate_origin_y_nm",
        "scale_confirmed",
        *(_SCALE_TYPED_FIELDS),
        *(f"{field}_status" for field in _SCALE_TYPED_FIELDS),
    }
    missing = sorted(required - set(record))
    if missing:
        _fail("scale record is incomplete", missing=missing)
    _as_finite_float(record["scale_x_nm_px"], field="scale_x_nm_px", strictly_positive=True)
    _as_finite_float(record["scale_y_nm_px"], field="scale_y_nm_px", strictly_positive=True)
    _as_finite_float(record["coordinate_origin_x_nm"], field="coordinate_origin_x_nm")
    _as_finite_float(record["coordinate_origin_y_nm"], field="coordinate_origin_y_nm")
    if record["scale_origin"] not in _SCALE_ORIGINS:
        _fail("invalid scale_origin", value=record["scale_origin"])
    if record["coordinate_transform_version"] != COORDINATE_TRANSFORM_VERSION:
        _fail("coordinate transform version mismatch")
    if validate_boolean_01(record["scale_confirmed"], field="scale_confirmed") != 1:
        _fail("usable XY scale must be explicitly confirmed")
    for field in _SCALE_TYPED_FIELDS:
        validate_typed_magnitude(
            record,
            field,
            minimum=0 if "uncertainty" in field or field == "scale_reference_angle_deg" else None,
            strictly_positive=field not in {
                "scale_uncertainty_x_nm_px",
                "scale_uncertainty_y_nm_px",
                "scale_reference_angle_deg",
            },
        )
    angle = record["scale_reference_angle_deg"]
    if angle is not None and not 0 <= float(angle) < 360:
        _fail("scale reference angle must be in [0,360)")
    if record["scale_origin"] == "MANUAL_LINE_REFERENCE":
        for field in (
            "scale_reference_length_px",
            "scale_reference_length_nm",
            "scale_reference_angle_deg",
        ):
            if record[f"{field}_status"] != "KNOWN":
                _fail("manual line calibration requires complete line evidence", field=field)


def resolve_xy_calibration(evidence: Mapping[str, Any]) -> dict[str, Any]:
    """Resolve X/Y only from explicit two-axis or independently constrained evidence."""

    if not isinstance(evidence, Mapping):
        _fail("scale evidence must be an object")
    origin = evidence.get("scale_origin")
    origin_x = evidence.get("coordinate_origin_x_nm", 0)
    origin_y = evidence.get("coordinate_origin_y_nm", 0)
    if origin == "MANUAL_XY_REFERENCE":
        required = (
            "x_reference_length_px",
            "x_reference_length_nm",
            "y_reference_length_px",
            "y_reference_length_nm",
            "evidence_id",
        )
        missing = [field for field in required if field not in evidence]
        if missing or not isinstance(evidence.get("evidence_id"), str) or not evidence["evidence_id"]:
            _fail("manual XY evidence is incomplete", missing=missing)
        x_px = _as_finite_float(
            evidence["x_reference_length_px"],
            field="x_reference_length_px",
            strictly_positive=True,
        )
        x_nm = _as_finite_float(
            evidence["x_reference_length_nm"],
            field="x_reference_length_nm",
            strictly_positive=True,
        )
        y_px = _as_finite_float(
            evidence["y_reference_length_px"],
            field="y_reference_length_px",
            strictly_positive=True,
        )
        y_nm = _as_finite_float(
            evidence["y_reference_length_nm"],
            field="y_reference_length_nm",
            strictly_positive=True,
        )
        return build_scale_record(
            scale_x_nm_px=x_nm / x_px,
            scale_y_nm_px=y_nm / y_px,
            scale_origin=origin,
            coordinate_origin_x_nm=origin_x,
            coordinate_origin_y_nm=origin_y,
        )
    if origin == "MANUAL_LINE_REFERENCE":
        required = (
            "scale_reference_length_px",
            "scale_reference_length_nm",
            "scale_reference_angle_deg",
            "independent_scale_x_nm_px",
            "independent_scale_y_nm_px",
            "independent_evidence_id",
        )
        missing = [field for field in required if field not in evidence]
        if missing or not isinstance(evidence.get("independent_evidence_id"), str) or not evidence["independent_evidence_id"]:
            _fail(
                "one line cannot justify two XY scales without independent evidence",
                missing=missing,
            )
        length_px = _as_finite_float(
            evidence["scale_reference_length_px"],
            field="scale_reference_length_px",
            strictly_positive=True,
        )
        length_nm = _as_finite_float(
            evidence["scale_reference_length_nm"],
            field="scale_reference_length_nm",
            strictly_positive=True,
        )
        angle = _as_finite_float(
            evidence["scale_reference_angle_deg"],
            field="scale_reference_angle_deg",
            minimum=0,
        )
        if angle >= 360:
            _fail("scale reference angle must be in [0,360)")
        sx = _as_finite_float(
            evidence["independent_scale_x_nm_px"],
            field="independent_scale_x_nm_px",
            strictly_positive=True,
        )
        sy = _as_finite_float(
            evidence["independent_scale_y_nm_px"],
            field="independent_scale_y_nm_px",
            strictly_positive=True,
        )
        measured_axis_scale = length_nm / length_px
        predicted_axis_scale = scale_along_axis_nm_px(sx, sy, angle % 180.0)
        if not math.isclose(measured_axis_scale, predicted_axis_scale, rel_tol=1e-12, abs_tol=0.0):
            _fail(
                "manual line evidence conflicts with independently justified XY scales",
                measured=measured_axis_scale,
                predicted=predicted_axis_scale,
            )
        return build_scale_record(
            scale_x_nm_px=sx,
            scale_y_nm_px=sy,
            scale_origin=origin,
            coordinate_origin_x_nm=origin_x,
            coordinate_origin_y_nm=origin_y,
            scale_reference_length_px=length_px,
            scale_reference_length_px_status="KNOWN",
            scale_reference_length_nm=length_nm,
            scale_reference_length_nm_status="KNOWN",
            scale_reference_angle_deg=angle,
            scale_reference_angle_deg_status="KNOWN",
        )
    if origin == "BIOFORMATS_METADATA_CONFIRMED":
        if not isinstance(evidence.get("evidence_id"), str) or not evidence["evidence_id"]:
            _fail("Bio-Formats scale requires identified evidence")
        sx = _as_finite_float(evidence.get("scale_x_nm_px"), field="scale_x_nm_px", strictly_positive=True)
        sy = _as_finite_float(evidence.get("scale_y_nm_px"), field="scale_y_nm_px", strictly_positive=True)
        return build_scale_record(
            scale_x_nm_px=sx,
            scale_y_nm_px=sy,
            source_scale_x_nm_px=sx,
            source_scale_x_nm_px_status="KNOWN",
            source_scale_y_nm_px=sy,
            source_scale_y_nm_px_status="KNOWN",
            scale_origin=origin,
            coordinate_origin_x_nm=origin_x,
            coordinate_origin_y_nm=origin_y,
        )
    _fail("scale evidence does not use a closed resolvable origin", scale_origin=origin)


def scale_along_axis_nm_px(scale_x_nm_px: Any, scale_y_nm_px: Any, orientation_deg: Any) -> float:
    sx = _as_finite_float(scale_x_nm_px, field="scale_x_nm_px", strictly_positive=True)
    sy = _as_finite_float(scale_y_nm_px, field="scale_y_nm_px", strictly_positive=True)
    theta = _as_finite_float(orientation_deg, field="orientation_deg")
    if theta < 0 or theta >= 180:
        _fail("orientation_deg must be in [0,180)", orientation_deg=theta)
    radians = theta * math.pi / 180.0
    result = math.hypot(sx * math.cos(radians), sy * math.sin(radians))
    return _finite_derived(result, field="scale_along_axis_nm_px", strictly_positive=True)


def axis_length_px(axis_length_nm: Any, scale_x_nm_px: Any, scale_y_nm_px: Any, orientation_deg: Any) -> float:
    length = _as_finite_float(axis_length_nm, field="axis_length_nm", strictly_positive=True)
    result = length / scale_along_axis_nm_px(scale_x_nm_px, scale_y_nm_px, orientation_deg)
    return _finite_derived(result, field="axis_length_px", strictly_positive=True)


def sampling_axis(
    measurement_protocol: str,
    *,
    scale_x_nm_px: Any,
    scale_y_nm_px: Any,
    diameter_nm: Any | None = None,
    minor_diameter_nm: Any | None = None,
    major_orientation_deg: Any | None = None,
    feret_min_nm: Any | None = None,
    feret_min_orientation_deg: Any | None = None,
) -> dict[str, Any]:
    sx = _as_finite_float(scale_x_nm_px, field="scale_x_nm_px", strictly_positive=True)
    sy = _as_finite_float(scale_y_nm_px, field="scale_y_nm_px", strictly_positive=True)
    if measurement_protocol == "CAVITY_CIRCLE":
        length = _as_finite_float(diameter_nm, field="diameter_nm", strictly_positive=True)
        scale = max(sx, sy)
        pixels = _finite_derived(length / scale, field="axis_length_px", strictly_positive=True)
        method = "CIRCLE_CONSERVATIVE_MAX_SCALE"
        orientation = None
    elif measurement_protocol == "CAVITY_ELLIPSE":
        length = _as_finite_float(
            minor_diameter_nm,
            field="minor_diameter_nm",
            strictly_positive=True,
        )
        major_orientation = _as_finite_float(
            major_orientation_deg,
            field="major_orientation_deg",
        )
        if major_orientation < 0 or major_orientation >= 180:
            _fail("major ellipse orientation must be in [0,180)")
        orientation = (major_orientation + 90.0) % 180.0
        scale = scale_along_axis_nm_px(sx, sy, orientation)
        pixels = _finite_derived(length / scale, field="axis_length_px", strictly_positive=True)
        method = "ELLIPSE_MINOR_ORIENTED"
    elif measurement_protocol == "CAVITY_CONTOUR":
        length = _as_finite_float(
            feret_min_nm,
            field="feret_min_nm",
            strictly_positive=True,
        )
        orientation = _as_finite_float(
            feret_min_orientation_deg,
            field="feret_min_orientation_deg",
        )
        scale = scale_along_axis_nm_px(sx, sy, orientation)
        pixels = _finite_derived(length / scale, field="axis_length_px", strictly_positive=True)
        method = "CONTOUR_FERET_MIN_ORIENTED"
    else:
        _fail("sampling axis requires one of the three closed cavity protocols", protocol=measurement_protocol)
    return {
        "sampling_axis_method": method,
        "sampling_axis_method_version": ANISOTROPIC_AXIS_VERSION,
        "scale_along_axis_nm_px": scale,
        "axis_length_px": pixels,
    }


def classify_sampling(axis_length_px_value: Any) -> dict[str, Any]:
    pixels = _as_finite_float(
        axis_length_px_value,
        field="axis_length_px",
        strictly_positive=True,
    )
    if pixels < 3:
        warning = "severe"
        size_eligible = 0
        maximum_recommended_class = "uncertain"
        manual_override_required = 1
    elif pixels < 5:
        warning = "near_limit"
        size_eligible = 0
        maximum_recommended_class = "uncertain"
        manual_override_required = 1
    else:
        warning = "none"
        size_eligible = 1
        maximum_recommended_class = "NOT_APPLICABLE"
        manual_override_required = 0
    return {
        "limit_policy_id": SAMPLING_POLICY_VERSION,
        "detection_limit_px": 3,
        "size_measurement_limit_px": 5,
        "sampling_warning": warning,
        "sampling_size_eligible": size_eligible,
        "maximum_recommended_class": maximum_recommended_class,
        "manual_override_required": manual_override_required,
        "automatic_pass": 0,
    }


def inside_image_domain(x_px: Any, y_px: Any, width_px: Any, height_px: Any) -> bool:
    x = _as_finite_float(x_px, field="x_px")
    y = _as_finite_float(y_px, field="y_px")
    if type(width_px) is not int or width_px <= 0 or type(height_px) is not int or height_px <= 0:
        _fail("image dimensions must be positive integers")
    return 0.0 <= x < width_px and 0.0 <= y < height_px


def _vertex(vertex: Any, *, index: int) -> tuple[float, float]:
    if isinstance(vertex, Mapping) and set(vertex) == {"x_nm", "y_nm"}:
        x, y = vertex["x_nm"], vertex["y_nm"]
    elif isinstance(vertex, (list, tuple)) and len(vertex) == 2:
        x, y = vertex
    else:
        _fail("polygon vertex must be [x,y] or {x_nm,y_nm}", index=index)
    return (
        _as_finite_float(x, field=f"vertices[{index}].x"),
        _as_finite_float(y, field=f"vertices[{index}].y"),
    )


def _vertices(polygon: Sequence[Any]) -> list[tuple[float, float]]:
    if isinstance(polygon, (str, bytes)) or not isinstance(polygon, Sequence) or len(polygon) < 3:
        _fail("polygon requires at least three ordered vertices")
    points = [_vertex(vertex, index=index) for index, vertex in enumerate(polygon)]
    if points[0] == points[-1]:
        points.pop()
    if len(points) < 3:
        _fail("polygon requires three distinct ordered vertices")
    return points


def _point_on_segment(
    x: float,
    y: float,
    x1: float,
    y1: float,
    x2: float,
    y2: float,
    epsilon: float,
) -> bool:
    dx = x2 - x1
    dy = y2 - y1
    length_squared = dx * dx + dy * dy
    if length_squared == 0:
        return math.hypot(x - x1, y - y1) <= epsilon
    projection = ((x - x1) * dx + (y - y1) * dy) / length_squared
    if projection < 0 or projection > 1:
        return False
    nearest_x = x1 + projection * dx
    nearest_y = y1 + projection * dy
    return math.hypot(x - nearest_x, y - nearest_y) <= epsilon


def point_in_polygon_inclusive(
    x: Any,
    y: Any,
    polygon: Sequence[Any],
    *,
    epsilon_px: Any = CENTER_BORDER_EPSILON_PX,
) -> bool:
    px = _as_finite_float(x, field="x")
    py = _as_finite_float(y, field="y")
    epsilon = _as_finite_float(epsilon_px, field="epsilon_px", minimum=0)
    points = _vertices(polygon)
    inside = False
    previous = points[-1]
    for current in points:
        x1, y1 = previous
        x2, y2 = current
        if _point_on_segment(px, py, x1, y1, x2, y2, epsilon):
            return True
        if (y1 > py) != (y2 > py):
            crossing_x = (x2 - x1) * (py - y1) / (y2 - y1) + x1
            if px < crossing_x:
                inside = not inside
        previous = current
    return inside


def center_in_net_area(
    x_px: Any,
    y_px: Any,
    *,
    width_px: int,
    height_px: int,
    outer_polygon: Sequence[Any],
    exclusion_polygons: Sequence[Sequence[Any]] = (),
) -> dict[str, Any]:
    """Closed center preflight: strict image domain, inclusive outer, exclusion wins."""

    if not inside_image_domain(x_px, y_px, width_px, height_px):
        return {
            "center_inside_image_domain": 0,
            "center_inside_outer": 0,
            "center_inside_exclusion": 0,
            "center_inside_net_area": 0,
            "center_border_epsilon_px": CENTER_BORDER_EPSILON_PX,
            "border_algorithm_version": BORDER_ALGORITHM_VERSION,
            "border_algorithm_status": BORDER_ALGORITHM_STATUS,
        }
    inside_outer = point_in_polygon_inclusive(x_px, y_px, outer_polygon)
    inside_exclusion = any(
        point_in_polygon_inclusive(x_px, y_px, polygon) for polygon in exclusion_polygons
    )
    return {
        "center_inside_image_domain": 1,
        "center_inside_outer": int(inside_outer),
        "center_inside_exclusion": int(inside_exclusion),
        "center_inside_net_area": int(inside_outer and not inside_exclusion),
        "center_border_epsilon_px": CENTER_BORDER_EPSILON_PX,
        "border_algorithm_version": BORDER_ALGORITHM_VERSION,
        "border_algorithm_status": BORDER_ALGORITHM_STATUS,
    }


def apply_surface_minimum_policy(
    record: Mapping[str, Any],
    *,
    surface_defined: bool,
    material_side_defined: bool,
) -> dict[str, Any]:
    """Apply OD-22 without overriding unrelated endpoint gates."""

    result = dict(record)
    for field in ("count_valid", "size_valid", "position_valid", "center_inside_net_area", "touches_surface"):
        if field not in result:
            _fail("surface policy input is incomplete", field=field)
        validate_boolean_01(result[field], field=field)
    if result["touches_surface"] == 1:
        if result["center_inside_net_area"] != 1:
            result["count_valid"] = 0
        # Center inside may preserve an already-valid count; it does not grant
        # validity when another gate has denied it.
        result["size_valid"] = 0
        result["position_valid"] = int(
            result["position_valid"] == 1 and surface_defined and material_side_defined
        )
    result["border_algorithm_version"] = BORDER_ALGORITHM_VERSION
    result["border_algorithm_status"] = BORDER_ALGORITHM_STATUS
    result.update(derive_inclusion_flags(result))
    return result


def derive_pixel_center(
    center_x_nm: Any,
    center_y_nm: Any,
    *,
    scale_x_nm_px: Any,
    scale_y_nm_px: Any,
    coordinate_origin_x_nm: Any,
    coordinate_origin_y_nm: Any,
) -> dict[str, Any]:
    x_nm = _as_finite_float(center_x_nm, field="center_x_nm")
    y_nm = _as_finite_float(center_y_nm, field="center_y_nm")
    sx = _as_finite_float(scale_x_nm_px, field="scale_x_nm_px", strictly_positive=True)
    sy = _as_finite_float(scale_y_nm_px, field="scale_y_nm_px", strictly_positive=True)
    origin_x = _as_finite_float(coordinate_origin_x_nm, field="coordinate_origin_x_nm")
    origin_y = _as_finite_float(coordinate_origin_y_nm, field="coordinate_origin_y_nm")
    return {
        "center_x_px": _finite_derived((x_nm - origin_x) / sx, field="center_x_px"),
        "center_y_px": _finite_derived((y_nm - origin_y) / sy, field="center_y_px"),
        "coordinate_transform_version": COORDINATE_TRANSFORM_VERSION,
    }


def reconcile_legacy_pixel_center(
    *,
    center_x_nm: Any,
    center_y_nm: Any,
    scale_x_nm_px: Any,
    scale_y_nm_px: Any,
    coordinate_origin_x_nm: Any,
    coordinate_origin_y_nm: Any,
    legacy_center_x_px: Any,
    legacy_center_y_px: Any,
    legacy_center_method_id: str,
) -> dict[str, Any]:
    """Require legacy center evidence to match the declared X/Y transform exactly."""

    if not isinstance(legacy_center_method_id, str) or not legacy_center_method_id:
        _fail("legacy center method evidence is required")
    expected = derive_pixel_center(
        center_x_nm,
        center_y_nm,
        scale_x_nm_px=scale_x_nm_px,
        scale_y_nm_px=scale_y_nm_px,
        coordinate_origin_x_nm=coordinate_origin_x_nm,
        coordinate_origin_y_nm=coordinate_origin_y_nm,
    )
    observed_x = _as_finite_float(legacy_center_x_px, field="legacy_center_x_px")
    observed_y = _as_finite_float(legacy_center_y_px, field="legacy_center_y_px")
    if observed_x != expected["center_x_px"] or observed_y != expected["center_y_px"]:
        _fail(
            "legacy pixel center contradicts the declared X/Y transform",
            expected_center_x_px=expected["center_x_px"],
            expected_center_y_px=expected["center_y_px"],
            observed_center_x_px=observed_x,
            observed_center_y_px=observed_y,
        )
    return {
        "legacy_center_x_px": observed_x,
        "legacy_center_y_px": observed_y,
        "legacy_center_method_id": legacy_center_method_id,
        "legacy_center_reconciliation_status": "MATCHED_DECLARED_XY_TRANSFORM",
    }


def geometry_hash_domain(record: Mapping[str, Any]) -> dict[str, Any]:
    protocol = record.get("measurement_protocol")
    if protocol == "CAVITY_CIRCLE":
        fields = ("center_x_nm", "center_y_nm", "diameter_nm", "measurement_protocol")
    elif protocol == "CAVITY_ELLIPSE":
        fields = (
            "center_x_nm",
            "center_y_nm",
            "major_diameter_nm",
            "measurement_protocol",
            "minor_diameter_nm",
            "orientation_deg",
        )
    elif protocol == "CAVITY_CONTOUR":
        fields = ("canonical_geometry", "measurement_protocol")
    else:
        _fail("GEOMETRY_HASH_V1 supports only closed cavity protocols", protocol=protocol)
    missing = [field for field in fields if field not in record]
    if missing:
        _fail("geometry hash domain is incomplete", missing=missing)
    return {field: record[field] for field in fields}


def geometry_sha256(record: Mapping[str, Any]) -> str:
    return hashlib.sha256(canonical_subobject_bytes(geometry_hash_domain(record))).hexdigest()


_CONTOUR_METRICS = (
    "perimeter_nm",
    "circularity",
    "feret_max_nm",
    "feret_min_nm",
    "feret_min_orientation_deg",
    "solidity",
)

_GEOMETRY_STATUS_FIELDS = (
    "diameter_nm_status",
    "major_diameter_nm_status",
    "minor_diameter_nm_status",
    "orientation_deg_status",
    "aspect_ratio_status",
    "equivalent_diameter_nm_status",
    "perimeter_nm_status",
    "circularity_status",
    "feret_max_nm_status",
    "feret_min_nm_status",
    "feret_min_orientation_deg_status",
    "solidity_status",
)


def geometry_authority_matrix(measurement_protocol: str) -> dict[str, str]:
    """Return schema authority roles; these roles are not object payload fields."""

    if measurement_protocol not in CAVITY_PROTOCOLS:
        _fail("geometry authority matrix requires a closed cavity protocol")
    roles = {
        "center_x_px": "SCIENTIFIC_DERIVATION",
        "center_y_px": "SCIENTIFIC_DERIVATION",
        "projected_area_nm2": "SCIENTIFIC_DERIVATION",
        "equivalent_diameter_nm": "STATISTICAL_DERIVATION",
        "aspect_ratio": (
            "STATISTICAL_DERIVATION"
            if measurement_protocol == "CAVITY_ELLIPSE"
            else "NOT_APPLICABLE"
        ),
        "canonical_geometry": (
            "SCIENTIFIC_AUTHORITY"
            if measurement_protocol == "CAVITY_CONTOUR"
            else "NOT_APPLICABLE"
        ),
        "final_geometry_sha256": (
            "SCIENTIFIC_AUTHORITY_COMPANION"
            if measurement_protocol == "CAVITY_CONTOUR"
            else "INTEGRITY_DERIVATION"
        ),
    }
    if measurement_protocol == "CAVITY_CIRCLE":
        roles.update(
            {
                "center_x_nm": "SCIENTIFIC_AUTHORITY",
                "center_y_nm": "SCIENTIFIC_AUTHORITY",
                "diameter_nm": "SCIENTIFIC_AUTHORITY",
                "major_diameter_nm": "NOT_APPLICABLE",
                "minor_diameter_nm": "NOT_APPLICABLE",
                "orientation_deg": "NOT_APPLICABLE",
            }
        )
    elif measurement_protocol == "CAVITY_ELLIPSE":
        roles.update(
            {
                "center_x_nm": "SCIENTIFIC_AUTHORITY",
                "center_y_nm": "SCIENTIFIC_AUTHORITY",
                "diameter_nm": "NOT_APPLICABLE",
                "major_diameter_nm": "SCIENTIFIC_AUTHORITY",
                "minor_diameter_nm": "SCIENTIFIC_AUTHORITY",
                "orientation_deg": "SCIENTIFIC_AUTHORITY",
            }
        )
    else:
        roles.update(
            {
                "center_x_nm": "DERIVED_FROM_CANONICAL_GEOMETRY",
                "center_y_nm": "DERIVED_FROM_CANONICAL_GEOMETRY",
                "diameter_nm": "NOT_APPLICABLE",
                "major_diameter_nm": "NOT_APPLICABLE",
                "minor_diameter_nm": "NOT_APPLICABLE",
                "orientation_deg": "DERIVED_FROM_CANONICAL_GEOMETRY",
            }
        )
    roles.update({field: GEOMETRY_STATUS_AUTHORITY_ROLE for field in _GEOMETRY_STATUS_FIELDS})
    return roles


def _na_geometry_fields(result: dict[str, Any], fields: Iterable[str]) -> None:
    for field in fields:
        result[field] = None
        result[f"{field}_status"] = "NOT_APPLICABLE"


def _known_geometry_fields(result: dict[str, Any], fields: Iterable[str]) -> None:
    for field in fields:
        result[f"{field}_status"] = "KNOWN"


def _common_geometry_result(area: float) -> dict[str, Any]:
    if not math.isfinite(area) or area <= 0:
        _fail("projected area must be finite and positive", area=area)
    equivalent = _finite_derived(
        math.sqrt(4.0 * area / math.pi),
        field="equivalent_diameter_nm",
        strictly_positive=True,
    )
    return {
        "projected_area_nm2": area,
        "equivalent_diameter_nm": equivalent,
        "equivalent_diameter_nm_status": "KNOWN",
        "geometry_hash_profile_id": GEOMETRY_HASH_PROFILE_ID,
    }


def build_circle_geometry(
    *,
    center_x_nm: Any,
    center_y_nm: Any,
    diameter_nm: Any,
    center_method_id: str,
    scale_x_nm_px: Any,
    scale_y_nm_px: Any,
    coordinate_origin_x_nm: Any,
    coordinate_origin_y_nm: Any,
) -> dict[str, Any]:
    center_x = _as_finite_float(center_x_nm, field="center_x_nm")
    center_y = _as_finite_float(center_y_nm, field="center_y_nm")
    diameter = _as_finite_float(diameter_nm, field="diameter_nm", strictly_positive=True)
    if not isinstance(center_method_id, str) or not center_method_id:
        _fail("center_method_id is required")
    result = {
        "measurement_protocol": "CAVITY_CIRCLE",
        "center_x_nm": center_x,
        "center_y_nm": center_y,
        "center_method_id": center_method_id,
        "diameter_nm": diameter,
        "diameter_nm_status": "KNOWN",
        "canonical_geometry": "NOT_APPLICABLE",
        "contour_derivation_method_id": "NOT_APPLICABLE",
        **_common_geometry_result(math.pi * diameter * diameter / 4.0),
        **derive_pixel_center(
            center_x,
            center_y,
            scale_x_nm_px=scale_x_nm_px,
            scale_y_nm_px=scale_y_nm_px,
            coordinate_origin_x_nm=coordinate_origin_x_nm,
            coordinate_origin_y_nm=coordinate_origin_y_nm,
        ),
    }
    _na_geometry_fields(
        result,
        (
            "major_diameter_nm",
            "minor_diameter_nm",
            "orientation_deg",
            "aspect_ratio",
            *_CONTOUR_METRICS,
        ),
    )
    result["final_geometry_sha256"] = geometry_sha256(result)
    return result


def build_ellipse_geometry(
    *,
    center_x_nm: Any,
    center_y_nm: Any,
    major_diameter_nm: Any,
    minor_diameter_nm: Any,
    orientation_deg: Any,
    center_method_id: str,
    scale_x_nm_px: Any,
    scale_y_nm_px: Any,
    coordinate_origin_x_nm: Any,
    coordinate_origin_y_nm: Any,
) -> dict[str, Any]:
    center_x = _as_finite_float(center_x_nm, field="center_x_nm")
    center_y = _as_finite_float(center_y_nm, field="center_y_nm")
    major = _as_finite_float(
        major_diameter_nm,
        field="major_diameter_nm",
        strictly_positive=True,
    )
    minor = _as_finite_float(
        minor_diameter_nm,
        field="minor_diameter_nm",
        strictly_positive=True,
    )
    orientation = _as_finite_float(orientation_deg, field="orientation_deg")
    if major < minor:
        _fail("ellipse major diameter cannot be smaller than minor diameter")
    if orientation < 0 or orientation >= 180:
        _fail("ellipse orientation must be in [0,180)")
    if not isinstance(center_method_id, str) or not center_method_id:
        _fail("center_method_id is required")
    result = {
        "measurement_protocol": "CAVITY_ELLIPSE",
        "center_x_nm": center_x,
        "center_y_nm": center_y,
        "center_method_id": center_method_id,
        "major_diameter_nm": major,
        "minor_diameter_nm": minor,
        "orientation_deg": orientation,
        "aspect_ratio": _finite_derived(
            major / minor,
            field="aspect_ratio",
            strictly_positive=True,
        ),
        "canonical_geometry": "NOT_APPLICABLE",
        "contour_derivation_method_id": "NOT_APPLICABLE",
        **_common_geometry_result(math.pi * major * minor / 4.0),
        **derive_pixel_center(
            center_x,
            center_y,
            scale_x_nm_px=scale_x_nm_px,
            scale_y_nm_px=scale_y_nm_px,
            coordinate_origin_x_nm=coordinate_origin_x_nm,
            coordinate_origin_y_nm=coordinate_origin_y_nm,
        ),
    }
    _known_geometry_fields(
        result,
        ("major_diameter_nm", "minor_diameter_nm", "orientation_deg", "aspect_ratio"),
    )
    _na_geometry_fields(result, ("diameter_nm", *_CONTOUR_METRICS))
    result["final_geometry_sha256"] = geometry_sha256(result)
    return result


def _shoelace_area(points: Sequence[tuple[float, float]]) -> float:
    try:
        signed_twice = math.fsum(
            points[index][0] * points[(index + 1) % len(points)][1]
            - points[(index + 1) % len(points)][0] * points[index][1]
            for index in range(len(points))
        )
    except (OverflowError, ValueError):
        _fail("canonical contour area overflowed")
    return _finite_derived(abs(signed_twice) / 2.0, field="projected_area_nm2")


def validate_canonical_geometry(canonical_geometry: Sequence[Any]) -> list[dict[str, float]]:
    points = _vertices(canonical_geometry)
    if _shoelace_area(points) <= 0:
        _fail("canonical contour geometry has zero area")
    # Persist a single representation; accepting pair input is API convenience,
    # never an alternative on-disk geometry grammar.
    return [{"x_nm": x, "y_nm": y} for x, y in points]


def _convex_hull(points: Sequence[tuple[float, float]]) -> list[tuple[float, float]]:
    unique = sorted(set(points))
    if len(unique) < 3:
        _fail("contour convex hull requires at least three distinct points")

    def cross(
        origin: tuple[float, float],
        first: tuple[float, float],
        second: tuple[float, float],
    ) -> float:
        return (first[0] - origin[0]) * (second[1] - origin[1]) - (
            first[1] - origin[1]
        ) * (second[0] - origin[0])

    lower: list[tuple[float, float]] = []
    for point in unique:
        while len(lower) >= 2 and cross(lower[-2], lower[-1], point) <= 0:
            lower.pop()
        lower.append(point)
    upper: list[tuple[float, float]] = []
    for point in reversed(unique):
        while len(upper) >= 2 and cross(upper[-2], upper[-1], point) <= 0:
            upper.pop()
        upper.append(point)
    hull = lower[:-1] + upper[:-1]
    if len(hull) < 3 or _shoelace_area(hull) <= 0:
        _fail("contour convex hull is degenerate")
    return hull


def derive_contour_metrics(
    canonical_geometry: Sequence[Any],
    *,
    contour_derivation_method_id: str = "CONTOUR_METRICS_V1",
) -> dict[str, float]:
    """Reproduce closed polygon metrics without choosing the OD-20 center."""

    if contour_derivation_method_id != "CONTOUR_METRICS_V1":
        _fail(
            "unknown contour metric derivation method",
            contour_derivation_method_id=contour_derivation_method_id,
        )
    geometry = validate_canonical_geometry(canonical_geometry)
    points = [(vertex["x_nm"], vertex["y_nm"]) for vertex in geometry]
    area = _shoelace_area(points)
    perimeter = _finite_derived(
        math.fsum(
            math.hypot(
                points[(index + 1) % len(points)][0] - points[index][0],
                points[(index + 1) % len(points)][1] - points[index][1],
            )
            for index in range(len(points))
        ),
        field="perimeter_nm",
        strictly_positive=True,
    )
    hull = _convex_hull(points)
    hull_area = _shoelace_area(hull)

    max_candidates: list[tuple[float, float]] = []
    for first_index, first in enumerate(hull):
        for second in hull[first_index + 1 :]:
            dx = second[0] - first[0]
            dy = second[1] - first[1]
            distance = math.hypot(dx, dy)
            angle = math.degrees(math.atan2(dy, dx)) % 180.0
            max_candidates.append((distance, angle))
    feret_max, orientation = sorted(max_candidates, key=lambda item: (-item[0], item[1]))[0]

    min_candidates: list[tuple[float, float]] = []
    for index, first in enumerate(hull):
        second = hull[(index + 1) % len(hull)]
        edge_x = second[0] - first[0]
        edge_y = second[1] - first[1]
        edge_length = math.hypot(edge_x, edge_y)
        normal_x = -edge_y / edge_length
        normal_y = edge_x / edge_length
        projections = [point[0] * normal_x + point[1] * normal_y for point in hull]
        width = max(projections) - min(projections)
        normal_angle = math.degrees(math.atan2(normal_y, normal_x)) % 180.0
        min_candidates.append((width, normal_angle))
    feret_min, feret_min_orientation = sorted(min_candidates, key=lambda item: (item[0], item[1]))[0]

    circularity = 4.0 * math.pi * area / (perimeter * perimeter)
    solidity = area / hull_area
    return {
        "orientation_deg": _finite_derived(orientation, field="orientation_deg"),
        "perimeter_nm": perimeter,
        "circularity": min(1.0, _finite_derived(circularity, field="circularity")),
        "feret_max_nm": _finite_derived(feret_max, field="feret_max_nm", strictly_positive=True),
        "feret_min_nm": _finite_derived(feret_min, field="feret_min_nm", strictly_positive=True),
        "feret_min_orientation_deg": _finite_derived(
            feret_min_orientation,
            field="feret_min_orientation_deg",
        ),
        "solidity": min(1.0, _finite_derived(solidity, field="solidity")),
    }


def build_contour_geometry(
    *,
    canonical_geometry: Sequence[Any],
    center_x_nm: Any,
    center_y_nm: Any,
    center_method_id: str,
    orientation_deg: Any | None = None,
    contour_derivation_method_id: str,
    perimeter_nm: Any | None = None,
    circularity: Any | None = None,
    feret_max_nm: Any | None = None,
    feret_min_nm: Any | None = None,
    feret_min_orientation_deg: Any | None = None,
    solidity: Any | None = None,
    scale_x_nm_px: Any,
    scale_y_nm_px: Any,
    coordinate_origin_x_nm: Any,
    coordinate_origin_y_nm: Any,
) -> dict[str, Any]:
    """Validate contour authority while preserving the declared center method.

    Prompt 1 intentionally does not choose the OD-20 center algorithm.  The
    supplied center and method are retained and checked, while the closed
    polygon area is recomputed from canonical vertices.
    """

    geometry = validate_canonical_geometry(canonical_geometry)
    points = [(vertex["x_nm"], vertex["y_nm"]) for vertex in geometry]
    area = _shoelace_area(points)
    center_x = _as_finite_float(center_x_nm, field="center_x_nm")
    center_y = _as_finite_float(center_y_nm, field="center_y_nm")
    if not isinstance(center_method_id, str) or not center_method_id:
        _fail("center_method_id is required and cannot be invented")
    if not isinstance(contour_derivation_method_id, str) or not contour_derivation_method_id:
        _fail("contour_derivation_method_id is required")
    derived_metrics = derive_contour_metrics(
        geometry,
        contour_derivation_method_id=contour_derivation_method_id,
    )
    supplied_metrics = {
        "orientation_deg": orientation_deg,
        "perimeter_nm": perimeter_nm,
        "circularity": circularity,
        "feret_max_nm": feret_max_nm,
        "feret_min_nm": feret_min_nm,
        "feret_min_orientation_deg": feret_min_orientation_deg,
        "solidity": solidity,
    }
    for field, supplied in supplied_metrics.items():
        if supplied is not None:
            observed = _as_finite_float(
                supplied,
                field=field,
                minimum=0 if field in {"circularity", "solidity"} else None,
                strictly_positive=field in {"perimeter_nm", "feret_max_nm", "feret_min_nm"},
            )
            if not math.isclose(observed, derived_metrics[field], rel_tol=1e-12, abs_tol=1e-12):
                _fail(
                    "supplied contour metric disagrees with canonical geometry",
                    field=field,
                    expected=derived_metrics[field],
                    observed=observed,
                )
    metrics = {
        **derived_metrics,
    }
    for field in ("orientation_deg", "feret_min_orientation_deg"):
        if metrics[field] < 0 or metrics[field] >= 180:
            _fail("contour orientation must be in [0,180)", field=field)
    for field in ("circularity", "solidity"):
        if metrics[field] > 1:
            _fail("contour unitless metric must be in [0,1]", field=field)
    if metrics["feret_max_nm"] < metrics["feret_min_nm"]:
        _fail("contour Feret maximum cannot be smaller than Feret minimum")
    result = {
        "measurement_protocol": "CAVITY_CONTOUR",
        "canonical_geometry": geometry,
        "center_x_nm": center_x,
        "center_y_nm": center_y,
        "center_method_id": center_method_id,
        "contour_derivation_method_id": contour_derivation_method_id,
        **metrics,
        **_common_geometry_result(area),
        **derive_pixel_center(
            center_x,
            center_y,
            scale_x_nm_px=scale_x_nm_px,
            scale_y_nm_px=scale_y_nm_px,
            coordinate_origin_x_nm=coordinate_origin_x_nm,
            coordinate_origin_y_nm=coordinate_origin_y_nm,
        ),
    }
    _known_geometry_fields(result, ("orientation_deg", *_CONTOUR_METRICS))
    _na_geometry_fields(result, ("diameter_nm", "major_diameter_nm", "minor_diameter_nm", "aspect_ratio"))
    result["final_geometry_sha256"] = geometry_sha256(result)
    return result


def validate_geometry_authority(record: Mapping[str, Any]) -> None:
    protocol = record.get("measurement_protocol")
    if protocol not in CAVITY_PROTOCOLS:
        _fail("geometry authority requires a closed cavity protocol", protocol=protocol)
    if record.get("geometry_hash_profile_id") != GEOMETRY_HASH_PROFILE_ID:
        _fail("geometry hash profile mismatch")
    observed_hash = record.get("final_geometry_sha256")
    expected_hash = geometry_sha256(record)
    if observed_hash != expected_hash:
        _fail("final geometry hash mismatch", expected=expected_hash, observed=observed_hash)
    required_statuses: dict[str, str]
    expected_area: float
    if protocol == "CAVITY_CIRCLE":
        required_statuses = {
            "diameter_nm": "KNOWN",
            "major_diameter_nm": "NOT_APPLICABLE",
            "minor_diameter_nm": "NOT_APPLICABLE",
            "orientation_deg": "NOT_APPLICABLE",
            "aspect_ratio": "NOT_APPLICABLE",
            "equivalent_diameter_nm": "KNOWN",
            **{field: "NOT_APPLICABLE" for field in _CONTOUR_METRICS},
        }
        if record.get("canonical_geometry") != "NOT_APPLICABLE":
            _fail("canonical_geometry is not applicable to circle")
        diameter = _as_finite_float(
            record.get("diameter_nm"),
            field="diameter_nm",
            strictly_positive=True,
        )
        expected_area = _finite_derived(
            math.pi * diameter * diameter / 4.0,
            field="projected_area_nm2",
            strictly_positive=True,
        )
    elif protocol == "CAVITY_ELLIPSE":
        required_statuses = {
            "diameter_nm": "NOT_APPLICABLE",
            "major_diameter_nm": "KNOWN",
            "minor_diameter_nm": "KNOWN",
            "orientation_deg": "KNOWN",
            "aspect_ratio": "KNOWN",
            "equivalent_diameter_nm": "KNOWN",
            **{field: "NOT_APPLICABLE" for field in _CONTOUR_METRICS},
        }
        if record.get("canonical_geometry") != "NOT_APPLICABLE":
            _fail("canonical_geometry is not applicable to ellipse")
        major = _as_finite_float(
            record.get("major_diameter_nm"),
            field="major_diameter_nm",
            strictly_positive=True,
        )
        minor = _as_finite_float(
            record.get("minor_diameter_nm"),
            field="minor_diameter_nm",
            strictly_positive=True,
        )
        if major < minor:
            _fail("ellipse major diameter cannot be smaller than minor diameter")
        expected_area = _finite_derived(
            math.pi * major * minor / 4.0,
            field="projected_area_nm2",
            strictly_positive=True,
        )
        observed_aspect = _as_finite_float(
            record.get("aspect_ratio"),
            field="aspect_ratio",
            strictly_positive=True,
        )
        if not math.isclose(observed_aspect, major / minor, rel_tol=1e-14, abs_tol=0.0):
            _fail("ellipse aspect ratio does not reconcile with authoritative axes")
    else:
        required_statuses = {
            "diameter_nm": "NOT_APPLICABLE",
            "major_diameter_nm": "NOT_APPLICABLE",
            "minor_diameter_nm": "NOT_APPLICABLE",
            "orientation_deg": "KNOWN",
            "aspect_ratio": "NOT_APPLICABLE",
            "equivalent_diameter_nm": "KNOWN",
            **{field: "KNOWN" for field in _CONTOUR_METRICS},
        }
        canonical = validate_canonical_geometry(record.get("canonical_geometry"))
        expected_area = _shoelace_area(
            [(vertex["x_nm"], vertex["y_nm"]) for vertex in canonical]
        )
        derived_contour = derive_contour_metrics(
            canonical,
            contour_derivation_method_id=record.get("contour_derivation_method_id"),
        )
        for field, expected in derived_contour.items():
            observed = _as_finite_float(record.get(field), field=field)
            if not math.isclose(observed, expected, rel_tol=1e-12, abs_tol=1e-12):
                _fail(
                    "contour metric does not reproduce from canonical geometry",
                    field=field,
                    expected=expected,
                    observed=observed,
                )
    for field, status in required_statuses.items():
        if record.get(f"{field}_status") != status:
            _fail("geometric status contradicts protocol", field=field, expected=status)
        validate_typed_magnitude(
            record,
            field,
            minimum=0 if field in {"circularity", "solidity"} else None,
            strictly_positive=field not in {"orientation_deg", "feret_min_orientation_deg", "circularity", "solidity"},
        )
    observed_area = _as_finite_float(
        record.get("projected_area_nm2"),
        field="projected_area_nm2",
        strictly_positive=True,
    )
    if not math.isclose(observed_area, expected_area, rel_tol=1e-14, abs_tol=0.0):
        _fail(
            "projected area does not reconcile with authoritative geometry",
            expected=expected_area,
            observed=observed_area,
        )
    if not math.isclose(
        float(record["equivalent_diameter_nm"]),
        math.sqrt(4.0 * observed_area / math.pi),
        rel_tol=1e-14,
        abs_tol=0.0,
    ):
        _fail("equivalent diameter does not reconcile with projected area")


def not_modelled_3d_record() -> dict[str, Any]:
    return {
        "model_3d": "NONE",
        "model_3d_status": "NOT_MODELLED",
        "third_axis_assumption": "NOT_APPLICABLE",
        "third_axis_value_nm": None,
        "third_axis_value_nm_status": "NOT_APPLICABLE",
        "model_source": "NOT_APPLICABLE",
        "model_uncertainty": "NOT_APPLICABLE",
        "modelled_volume_nm3": None,
        "modelled_volume_nm3_status": "NOT_APPLICABLE",
        "nominal_volume_fraction": None,
        "nominal_volume_fraction_status": "NOT_APPLICABLE",
        "quantity_claim": "MODELLED_NOT_OBSERVED_ONLY",
    }


def model_sphere(
    diameter_nm: Any,
    *,
    model_source: str,
    model_uncertainty: Mapping[str, Any],
    justification: str,
) -> dict[str, Any]:
    diameter = _as_finite_float(diameter_nm, field="diameter_nm", strictly_positive=True)
    if not all(isinstance(value, str) and value for value in (model_source, justification)):
        _fail("model source and justification are required")
    if not isinstance(model_uncertainty, Mapping) or not model_uncertainty:
        _fail("model uncertainty/status is required")
    assert_nonfinite_free(model_uncertainty, path="$.model_uncertainty")
    volume = _finite_derived(
        math.pi * diameter * diameter * diameter / 6.0,
        field="modelled_volume_nm3",
        strictly_positive=True,
    )
    return {
        "model_3d": "SPHERE_ASSUMED",
        "model_3d_status": "MODELLED_NOT_OBSERVED",
        "model_protocol": "CAVITY_CIRCLE",
        "model_inputs": {"diameter_nm": diameter},
        "model_units": {"diameter_nm": "nm", "modelled_volume_nm3": "nm3"},
        "third_axis_assumption": "NOT_APPLICABLE",
        "third_axis_value_nm": None,
        "third_axis_value_nm_status": "NOT_APPLICABLE",
        "model_source": model_source,
        "model_uncertainty": dict(model_uncertainty),
        "model_justification": justification,
        "modelled_volume_nm3": volume,
        "modelled_volume_nm3_status": "KNOWN",
        "quantity_claim": "MODELLED_NOT_OBSERVED",
    }


def model_ellipsoid(
    major_diameter_nm: Any,
    minor_diameter_nm: Any,
    third_axis_value_nm: Any,
    *,
    third_axis_assumption: str,
    model_source: str,
    model_uncertainty: Mapping[str, Any],
    justification: str,
) -> dict[str, Any]:
    major = _as_finite_float(
        major_diameter_nm,
        field="major_diameter_nm",
        strictly_positive=True,
    )
    minor = _as_finite_float(
        minor_diameter_nm,
        field="minor_diameter_nm",
        strictly_positive=True,
    )
    third = _as_finite_float(
        third_axis_value_nm,
        field="third_axis_value_nm",
        strictly_positive=True,
    )
    if not all(
        isinstance(value, str) and value
        for value in (third_axis_assumption, model_source, justification)
    ):
        _fail("ellipsoid model assumption, source, and justification are required")
    if not isinstance(model_uncertainty, Mapping) or not model_uncertainty:
        _fail("model uncertainty/status is required")
    assert_nonfinite_free(model_uncertainty, path="$.model_uncertainty")
    volume = _finite_derived(
        math.pi * major * minor * third / 6.0,
        field="modelled_volume_nm3",
        strictly_positive=True,
    )
    return {
        "model_3d": "ELLIPSOID_ASSUMED",
        "model_3d_status": "MODELLED_NOT_OBSERVED",
        "model_protocol": "CAVITY_ELLIPSE",
        "model_inputs": {
            "major_diameter_nm": major,
            "minor_diameter_nm": minor,
            "third_axis_value_nm": third,
        },
        "model_units": {"diameters": "nm", "modelled_volume_nm3": "nm3"},
        "third_axis_assumption": third_axis_assumption,
        "third_axis_value_nm": third,
        "third_axis_value_nm_status": "KNOWN",
        "model_source": model_source,
        "model_uncertainty": dict(model_uncertainty),
        "model_justification": justification,
        "modelled_volume_nm3": volume,
        "modelled_volume_nm3_status": "KNOWN",
        "quantity_claim": "MODELLED_NOT_OBSERVED",
    }


def model_thin_cylinder(
    loop_diameter_nm: Any,
    loop_thickness_nm: Any,
    *,
    loop_thickness_source: str,
    loop_material: str,
    lattice_parameter_value_nm: Any,
    lattice_parameter_uncertainty_nm: Any,
    lattice_parameter_source: str,
    justification: str,
) -> dict[str, Any]:
    diameter = _as_finite_float(
        loop_diameter_nm,
        field="loop_diameter_nm",
        strictly_positive=True,
    )
    thickness = _as_finite_float(
        loop_thickness_nm,
        field="loop_thickness_nm",
        strictly_positive=True,
    )
    lattice = _as_finite_float(
        lattice_parameter_value_nm,
        field="loop_lattice_parameter_value_nm",
        strictly_positive=True,
    )
    uncertainty = _as_finite_float(
        lattice_parameter_uncertainty_nm,
        field="loop_lattice_parameter_uncertainty_nm",
        minimum=0,
    )
    for field, value in (
        ("loop_thickness_source", loop_thickness_source),
        ("loop_material", loop_material),
        ("lattice_parameter_source", lattice_parameter_source),
        ("justification", justification),
    ):
        if not isinstance(value, str) or not value:
            _fail("thin-cylinder model evidence is required", field=field)
    volume = _finite_derived(
        math.pi * (diameter / 2.0) * (diameter / 2.0) * thickness,
        field="modelled_volume_nm3",
        strictly_positive=True,
    )
    return {
        "loop_model": "THIN_CYLINDER",
        "model_3d_status": "MODELLED_NOT_OBSERVED",
        "model_protocol": "THIN_CYLINDER",
        "loop_thickness_nm": thickness,
        "loop_thickness_nm_status": "KNOWN",
        "loop_thickness_source": loop_thickness_source,
        "loop_material": loop_material,
        "loop_lattice_parameter_value_nm": lattice,
        "loop_lattice_parameter_value_nm_status": "KNOWN",
        "loop_lattice_parameter_uncertainty_nm": uncertainty,
        "loop_lattice_parameter_uncertainty_nm_status": "KNOWN",
        "loop_lattice_parameter_source": lattice_parameter_source,
        "loop_thickness_justification": justification,
        "modelled_volume_nm3": volume,
        "modelled_volume_nm3_status": "KNOWN",
        "quantity_claim": "MODELLED_NOT_OBSERVED",
    }


def validate_model_3d(record: Mapping[str, Any]) -> None:
    """Reject any 3-D record that could be mistaken for an observation."""

    forbidden = {
        "observed_volume_nm3",
        "real_volume_nm3",
        "observed_volume_fraction",
        "real_porosity",
    }.intersection(record)
    if forbidden:
        _fail("3-D model record contains a forbidden observed/real claim", fields=sorted(forbidden))
    status = record.get("model_3d_status")
    if status == "NOT_MODELLED":
        if record.get("model_3d") != "NONE":
            _fail("NOT_MODELLED requires model_3d=NONE")
        validate_typed_magnitude(record, "modelled_volume_nm3")
        if record["modelled_volume_nm3_status"] != "NOT_APPLICABLE":
            _fail("non-modelled volume must be NOT_APPLICABLE")
        if record.get("quantity_claim") != "MODELLED_NOT_OBSERVED_ONLY":
            _fail("non-modelled record has an invalid quantity claim")
        return
    if status != "MODELLED_NOT_OBSERVED":
        _fail("invalid model_3d_status", status=status)
    if record.get("quantity_claim") != "MODELLED_NOT_OBSERVED":
        _fail("modelled quantity lacks explicit MODELLED_NOT_OBSERVED claim")
    model = record.get("model_3d")
    loop_model = record.get("loop_model")
    if model not in {"SPHERE_ASSUMED", "ELLIPSOID_ASSUMED"} and loop_model != "THIN_CYLINDER":
        _fail("modelled record lacks a closed 3-D protocol")
    validate_typed_magnitude(record, "modelled_volume_nm3", strictly_positive=True)
    if record["modelled_volume_nm3_status"] != "KNOWN":
        _fail("validated model must have a known modelled volume")
    if model in {"SPHERE_ASSUMED", "ELLIPSOID_ASSUMED"}:
        if record.get("model_source") in {None, "", "NOT_APPLICABLE"}:
            _fail("modelled cavity requires a model source")
        if not isinstance(record.get("model_uncertainty"), Mapping) or not record["model_uncertainty"]:
            _fail("modelled cavity requires uncertainty/status evidence")
        assert_nonfinite_free(record["model_uncertainty"], path="$.model_uncertainty")
