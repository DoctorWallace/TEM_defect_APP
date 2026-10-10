"""Fail-closed descriptive pooling of already verified RUNs.

Prompt 1 implements integrity and descriptive pooling only.  It deliberately
does not infer experimental independence, fit hierarchical models, or rebin
incompatible observations; those decisions remain in Prompt 8.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from .canonical_json import PROFILE_ID, canonical_json_bytes, loads_canonical_json
from .critical_io import (
    AtomicMoveProof,
    fsync_directory,
    sha256_bytes,
    utc_now_z,
    write_new_file,
)
from .errors import TransactionError, ValidationError
from .identity import validate_canonical_uuid, validate_human_id
from .path_safety import (
    PathSafetyError,
    is_reparse_or_link,
    plain_directory,
    plain_file,
    stable_plain_bytes,
)
from .run_consumer import VerifiedRun, verify_run_directory
from .run_disposition import require_scientific_eligibility
from .run_transaction import publish_directory_no_replace


COMBINED_CONTROL_SET = frozenset({"combined_manifest.json", "COMBINED_SHA256.txt", "COMPLETE"})
COMBINED_PAYLOAD_PATH = "combined_cavity_objects.tsv"
COMBINED_SIDECAR_BYTES = 89
COMBINED_RESERVED_COLUMNS = ("source_run_uid", "source_run_manifest_sha256")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
UTC_Z_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d*[1-9])?Z$")


class BinCompatibilityError(ValidationError):
    code = "INCOMPATIBLE_BINS"


@dataclass(frozen=True)
class CombinedObjectRow:
    source_run_uid: str
    source_run_manifest_sha256: str
    values: Mapping[str, str]


@dataclass(frozen=True)
class CombinedResult:
    manifest: dict[str, Any]
    manifest_bytes: bytes
    manifest_sha256: str
    rows: tuple[CombinedObjectRow, ...]
    verified_runs: tuple[VerifiedRun, ...]
    object_table_bytes: bytes


@dataclass(frozen=True)
class VerifiedCombinedRun:
    """A sealed combined artifact verified before its data rows were parsed."""

    path: Path
    manifest: dict[str, Any]
    manifest_sha256: str
    marker: dict[str, str]
    rows: tuple[CombinedObjectRow, ...]
    object_header: tuple[str, ...]
    verified_runs: tuple[VerifiedRun, ...]

    @property
    def combined_run_id(self) -> str:
        return str(self.manifest["combined_run_id"])

    @property
    def combined_run_uid(self) -> str:
        return str(self.manifest["combined_run_uid"])


@dataclass(frozen=True)
class PublishedCombinedRun:
    path: Path
    manifest_sha256: str
    atomic_move_capability: str
    verified: VerifiedCombinedRun


def _decimal(value: Any, field: str) -> Decimal:
    if isinstance(value, bool):
        raise ValidationError("boolean is not a descriptive numeric value", details={"field": field})
    try:
        result = value if isinstance(value, Decimal) else Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise ValidationError("descriptive numeric value is invalid", details={"field": field, "value": value}) from exc
    if not result.is_finite():
        raise ValidationError("descriptive numeric value is not finite", details={"field": field})
    return result


def _collect_bin_policy(value: Any, path: str, result: list[dict[str, Any]]) -> None:
    """Collect explicit bin policies without interpreting or normalizing them."""

    if isinstance(value, Mapping):
        for key in sorted(value):
            child = value[key]
            child_path = f"{path}.{key}" if path else key
            lowered = key.lower()
            if (
                lowered in {"bin_contract", "bins", "bin_edges", "bin_edges_nm", "histogram_bin_nm", "feature_distance_bin_nm", "depth_bin_nm"}
                or lowered.endswith("_bin_edges_nm")
                or lowered.endswith("_bin_width_nm")
            ):
                result.append({"path": child_path, "value": child})
            elif isinstance(child, Mapping):
                _collect_bin_policy(child, child_path, result)


def bin_contract(run: VerifiedRun) -> dict[str, Any]:
    """Return the exact explicit bin domain used for compatibility checking."""

    declarations: list[dict[str, Any]] = []
    _collect_bin_policy(run.manifest, "manifest", declarations)
    header = set(run.object_header)
    required = {"depth_bin_index", "depth_bin_low_nm", "depth_bin_high_nm"}
    table_bins: list[dict[str, Any]] = []
    if required.issubset(header):
        seen: set[tuple[str, str, str]] = set()
        for row in run.object_rows:
            triple = (row["depth_bin_index"], row["depth_bin_low_nm"], row["depth_bin_high_nm"])
            if triple == ("", "", ""):
                continue
            if any(component == "" for component in triple):
                raise ValidationError("object table contains a partially specified depth bin", details={"run_id": run.run_id})
            seen.add(triple)
        for index, low, high in sorted(seen, key=lambda item: (Decimal(item[1]), Decimal(item[2]), int(item[0]))):
            table_bins.append({"depth_bin_index": index, "depth_bin_low_nm": low, "depth_bin_high_nm": high})
    return {"declarations": declarations, "object_table_depth_bins": table_bins}


def bin_contract_sha256(run: VerifiedRun) -> str:
    return sha256_bytes(canonical_json_bytes(bin_contract(run)))


def assert_compatible_bins(runs: Sequence[VerifiedRun]) -> str:
    if not runs:
        raise ValidationError("combined pooling requires at least one RUN")
    signatures = [(run.run_uid, bin_contract_sha256(run)) for run in runs]
    expected = signatures[0][1]
    incompatible = [{"run_uid": uid, "bin_contract_sha256": digest} for uid, digest in signatures if digest != expected]
    if incompatible:
        raise BinCompatibilityError(
            "Prompt 1 rejects incompatible bins; implicit rebinning is forbidden",
            details={"expected": expected, "incompatible": incompatible},
        )
    return expected


def _reverify(item: VerifiedRun | os.PathLike[str] | str) -> VerifiedRun:
    if isinstance(item, VerifiedRun):
        # Re-read immutable bytes so a mutation after the first verification is
        # never hidden behind a stale in-memory object.
        verified = verify_run_directory(item.path, expected_pointer=item.pointer)
    else:
        verified = verify_run_directory(Path(item))
    return require_scientific_eligibility(verified)


def _validate_optional_combined_identity(
    combined_run_id: str | None,
    combined_run_uid: str | None,
) -> None:
    if (combined_run_id is None) != (combined_run_uid is None):
        raise ValidationError("combined_run_id and combined_run_uid must be supplied together")
    if combined_run_id is not None:
        validate_human_id(combined_run_id, field="combined_run_id")
        validate_canonical_uuid(combined_run_uid)


def _render_combined_object_table(
    rows: Sequence[CombinedObjectRow],
    object_header: Sequence[str],
) -> bytes:
    if not object_header or len(object_header) != len(set(object_header)):
        raise ValidationError("combined source object header is empty or duplicated")
    if any(column in object_header for column in COMBINED_RESERVED_COLUMNS):
        raise ValidationError("source object header collides with combined provenance columns")
    all_columns = (*COMBINED_RESERVED_COLUMNS, *object_header)
    lines = ["\t".join(all_columns)]
    for combined_row in rows:
        values = combined_row.values
        if set(values) != set(object_header):
            raise ValidationError(
                "combined row fields differ from its source header",
                details={"source_run_uid": combined_row.source_run_uid},
            )
        cells = [combined_row.source_run_uid, combined_row.source_run_manifest_sha256]
        cells.extend(str(values[column]) for column in object_header)
        if any("\t" in cell or "\r" in cell or "\n" in cell for cell in cells):
            raise ValidationError("combined object cell contains a forbidden delimiter")
        lines.append("\t".join(cells))
    return ("\n".join(lines) + "\n").encode("utf-8")


def render_combined_sidecar(manifest_sha256: str) -> bytes:
    if not isinstance(manifest_sha256, str) or SHA256_RE.fullmatch(manifest_sha256) is None:
        raise ValidationError("combined manifest SHA-256 is invalid")
    result = f"{manifest_sha256}  combined_manifest.json\n".encode("ascii")
    if len(result) != COMBINED_SIDECAR_BYTES:
        raise AssertionError("combined sidecar byte length changed")
    return result


def parse_combined_sidecar(data: bytes) -> str:
    if len(data) != COMBINED_SIDECAR_BYTES:
        raise ValidationError(
            "COMBINED_SHA256.txt has an invalid byte length",
            details={"expected": COMBINED_SIDECAR_BYTES, "actual": len(data)},
        )
    try:
        text = data.decode("ascii")
    except UnicodeDecodeError as exc:
        raise ValidationError("COMBINED_SHA256.txt is not ASCII") from exc
    match = re.fullmatch(r"([0-9a-f]{64})  combined_manifest\.json\n", text)
    if match is None:
        raise ValidationError("COMBINED_SHA256.txt format is not exact")
    return match.group(1)


def render_combined_complete_marker(
    *,
    combined_run_id: str,
    combined_run_uid: str,
    manifest_sha256: str,
    completed_at: str,
) -> bytes:
    validate_human_id(combined_run_id, field="combined_run_id")
    validate_canonical_uuid(combined_run_uid)
    if SHA256_RE.fullmatch(manifest_sha256 or "") is None:
        raise ValidationError("combined manifest SHA-256 is invalid")
    _validate_utc(completed_at, "completed_at")
    result = (
        "marker_version\t1\n"
        f"combined_run_id\t{combined_run_id}\n"
        f"combined_run_uid\t{combined_run_uid}\n"
        "schema_version\t1\n"
        f"combined_manifest_sha256\t{manifest_sha256}\n"
        f"completed_at\t{completed_at}\n"
    ).encode("ascii")
    parse_combined_complete_marker(result)
    return result


def parse_combined_complete_marker(data: bytes) -> dict[str, str]:
    try:
        text = data.decode("ascii")
    except UnicodeDecodeError as exc:
        raise ValidationError("combined COMPLETE marker is not ASCII") from exc
    if "\r" in text or not text.endswith("\n"):
        raise ValidationError("combined COMPLETE marker must use exact LF lines")
    lines = text.splitlines()
    expected = (
        "marker_version",
        "combined_run_id",
        "combined_run_uid",
        "schema_version",
        "combined_manifest_sha256",
        "completed_at",
    )
    if len(lines) != len(expected):
        raise ValidationError("combined COMPLETE marker must contain exactly six lines")
    parsed: dict[str, str] = {}
    for key, line in zip(expected, lines):
        if line.count("\t") != 1:
            raise ValidationError("combined COMPLETE line must contain exactly one HT")
        actual_key, value = line.split("\t")
        if actual_key != key or not value:
            raise ValidationError("combined COMPLETE key order/value is invalid")
        parsed[key] = value
    if parsed["marker_version"] != "1" or parsed["schema_version"] != "1":
        raise ValidationError("combined COMPLETE versions are invalid")
    validate_human_id(parsed["combined_run_id"], field="combined_run_id")
    validate_canonical_uuid(parsed["combined_run_uid"])
    if SHA256_RE.fullmatch(parsed["combined_manifest_sha256"]) is None:
        raise ValidationError("combined COMPLETE hash is invalid")
    _validate_utc(parsed["completed_at"], "completed_at")
    return parsed


def _validate_utc(value: Any, field: str) -> str:
    if not isinstance(value, str) or UTC_Z_RE.fullmatch(value) is None:
        raise ValidationError("combined timestamp is not canonical UTC", details={"field": field})
    try:
        datetime.strptime(value[:-1], "%Y-%m-%dT%H:%M:%S.%f" if "." in value else "%Y-%m-%dT%H:%M:%S")
    except ValueError as exc:
        raise ValidationError("combined timestamp is not a real calendar time", details={"field": field}) from exc
    return value


def pool_descriptive_runs(
    runs: Iterable[VerifiedRun | os.PathLike[str] | str],
    *,
    requested_rebin: bool = False,
    combined_run_id: str | None = None,
    combined_run_uid: str | None = None,
) -> CombinedResult:
    """Pool counts/areas descriptively after full independent re-verification."""

    if requested_rebin:
        raise BinCompatibilityError("rebinning is outside Prompt 1 and cannot be requested")
    _validate_optional_combined_identity(combined_run_id, combined_run_uid)
    verified = tuple(_reverify(item) for item in runs)
    if not verified:
        raise ValidationError("combined pooling requires at least one RUN")
    run_uids = [run.run_uid for run in verified]
    if len(run_uids) != len(set(run_uids)):
        raise ValidationError("combined input contains a duplicate RUN")
    projects = {str(run.manifest["project_uid"]) for run in verified}
    if len(projects) != 1:
        raise ValidationError("Prompt-1 combined pooling cannot cross project_uid")
    signature = assert_compatible_bins(verified)
    expected_header = verified[0].object_header
    incompatible_headers = [run.run_uid for run in verified if run.object_header != expected_header]
    if incompatible_headers:
        raise ValidationError(
            "combined input object schemas differ; implicit column union is forbidden",
            details={"incompatible_run_uids": incompatible_headers},
        )

    total_count = sum(int(run.manifest["N_count_valid"]) for run in verified)
    total_size = sum(int(run.manifest["N_size_valid"]) for run in verified)
    total_position = sum(int(run.manifest["N_position_valid"]) for run in verified)
    total_area = sum((_decimal(run.manifest["net_area_nm2"], "net_area_nm2") for run in verified), Decimal(0))
    if total_area <= 0:
        raise ValidationError("combined net area must be positive")
    density_areal = Decimal(total_count) * Decimal(1_000_000) / total_area

    combined_rows: list[CombinedObjectRow] = []
    primary_counts = {"count": 0, "size": 0, "position": 0}
    sensitivity_counts = {"count": 0, "size": 0, "position": 0}
    for run in sorted(verified, key=lambda item: item.run_uid):
        for row in run.object_rows:
            combined_rows.append(
                CombinedObjectRow(
                    source_run_uid=run.run_uid,
                    source_run_manifest_sha256=run.manifest_sha256,
                    values=dict(row),
                )
            )
            for endpoint in ("count", "size", "position"):
                primary_counts[endpoint] += int(row[f"primary_{endpoint}_included"])
                sensitivity_counts[endpoint] += int(row[f"sensitivity_{endpoint}_included"])

    input_runs = [
        {
            "run_id": run.run_id,
            "run_uid": run.run_uid,
            "run_manifest_sha256": run.manifest_sha256,
            "project_uid": run.manifest["project_uid"],
            "image_uid": run.manifest["image_uid"],
            "analysis_session_uid": run.manifest["analysis_session_uid"],
            "revision_uid": run.manifest["revision_uid"],
            "object_row_count": len(run.object_rows),
        }
        for run in sorted(verified, key=lambda item: item.run_uid)
    ]
    object_table_bytes = _render_combined_object_table(combined_rows, expected_header)
    manifest: dict[str, Any] = {
        "descriptor_type": "combined_run",
        "combined_contract_version": 1,
        "combined_state": "COMPLETE",
        "serialization_profile": PROFILE_ID,
        "created_at": utc_now_z(),
        "project_uid": next(iter(projects)),
        "pooling_mode": "DESCRIPTIVE_ONLY",
        "hierarchical_inference_status": "NOT_IMPLEMENTED_PROMPT8",
        "implicit_rebin": False,
        "bin_contract_sha256": signature,
        "input_runs": input_runs,
        "run_count": len(verified),
        "object_row_count": len(combined_rows),
        "N_count_valid": total_count,
        "N_size_valid": total_size,
        "N_position_valid": total_position,
        "total_net_area_nm2": total_area,
        "density_N_per_um2": density_areal,
        "primary_included": primary_counts,
        "sensitivity_included": sensitivity_counts,
        "object_columns": list(expected_header),
        "files": [
            {
                "relative_path": COMBINED_PAYLOAD_PATH,
                "bytes": len(object_table_bytes),
                "sha256": sha256_bytes(object_table_bytes),
                "media_type": "text/tab-separated-values; charset=utf-8",
                "authority_role": "DERIVED_SUMMARY",
            }
        ],
        "scientific_validation": False,
        "functional_release": False,
        "prompt2_started": False,
    }
    if combined_run_id is not None:
        manifest["combined_run_id"] = combined_run_id
        manifest["combined_run_uid"] = combined_run_uid
    manifest_bytes = canonical_json_bytes(manifest)
    return CombinedResult(
        manifest=manifest,
        manifest_bytes=manifest_bytes,
        manifest_sha256=sha256_bytes(manifest_bytes),
        rows=tuple(combined_rows),
        verified_runs=verified,
        object_table_bytes=object_table_bytes,
    )


def _is_link_or_reparse(path: Path) -> bool:
    try:
        return is_reparse_or_link(path)
    except PathSafetyError as exc:
        raise ValidationError(
            "native combined path identity could not be established",
            details={"path": str(path), "cause": str(exc)},
        ) from exc


def _enumerate_combined_files(path: Path) -> set[str]:
    result: set[str] = set()
    try:
        entries = sorted(os.scandir(path), key=lambda entry: entry.name)
    except OSError as exc:
        raise ValidationError("combined artifact cannot be enumerated") from exc
    for entry in entries:
        item = Path(entry.path)
        relative = item.relative_to(path).as_posix()
        try:
            if is_reparse_or_link(item):
                raise PathSafetyError(f"linked/reparse entry: {item}")
            if entry.is_dir(follow_symlinks=False):
                raise PathSafetyError(f"undeclared directory: {item}")
            plain_file(item, label="combined immutable file", single_link=True)
        except PathSafetyError as exc:
            raise ValidationError(
                "combined artifact contains an unsafe entry",
                details={"relative_path": relative, "cause": str(exc)},
            ) from exc
        if "/" in relative or "\\" in relative or relative in result:
            raise ValidationError("combined artifact path inventory is not canonical")
        result.add(relative)
    return result


def _nonnegative_int(value: Any, field: str) -> int:
    if isinstance(value, bool):
        raise ValidationError("combined integer field is boolean", details={"field": field})
    try:
        decimal = value if isinstance(value, Decimal) else Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise ValidationError("combined integer field is invalid", details={"field": field}) from exc
    if not decimal.is_finite() or decimal != decimal.to_integral_value() or decimal < 0:
        raise ValidationError("combined integer field is not nonnegative", details={"field": field})
    return int(decimal)


def _validate_combined_manifest(manifest: Any) -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
    if not isinstance(manifest, dict):
        raise ValidationError("combined manifest root must be an object")
    expected_keys = {
        "descriptor_type",
        "combined_contract_version",
        "combined_state",
        "serialization_profile",
        "combined_run_id",
        "combined_run_uid",
        "created_at",
        "project_uid",
        "pooling_mode",
        "hierarchical_inference_status",
        "implicit_rebin",
        "bin_contract_sha256",
        "input_runs",
        "run_count",
        "object_row_count",
        "N_count_valid",
        "N_size_valid",
        "N_position_valid",
        "total_net_area_nm2",
        "density_N_per_um2",
        "primary_included",
        "sensitivity_included",
        "object_columns",
        "files",
        "scientific_validation",
        "functional_release",
        "prompt2_started",
    }
    if set(manifest) != expected_keys:
        raise ValidationError(
            "combined manifest field set is not exact",
            details={"missing": sorted(expected_keys - set(manifest)), "extra": sorted(set(manifest) - expected_keys)},
        )
    exact = {
        "descriptor_type": "combined_run",
        "combined_contract_version": 1,
        "combined_state": "COMPLETE",
        "serialization_profile": PROFILE_ID,
        "pooling_mode": "DESCRIPTIVE_ONLY",
        "hierarchical_inference_status": "NOT_IMPLEMENTED_PROMPT8",
        "implicit_rebin": False,
        "scientific_validation": False,
        "functional_release": False,
        "prompt2_started": False,
    }
    for field, expected in exact.items():
        if manifest.get(field) != expected:
            raise ValidationError(
                "combined manifest closed field differs",
                details={"field": field, "expected": expected, "actual": manifest.get(field)},
            )
    validate_human_id(manifest["combined_run_id"], field="combined_run_id")
    validate_canonical_uuid(manifest["combined_run_uid"])
    validate_canonical_uuid(manifest["project_uid"])
    _validate_utc(manifest["created_at"], "created_at")
    if SHA256_RE.fullmatch(str(manifest["bin_contract_sha256"])) is None:
        raise ValidationError("combined bin contract hash is invalid")

    object_columns = manifest["object_columns"]
    if (
        not isinstance(object_columns, list)
        or not object_columns
        or any(not isinstance(column, str) or not column for column in object_columns)
        or len(object_columns) != len(set(object_columns))
        or any(column in COMBINED_RESERVED_COLUMNS for column in object_columns)
    ):
        raise ValidationError("combined object_columns is invalid")
    required_columns = {
        "primary_count_included",
        "primary_size_included",
        "primary_position_included",
        "sensitivity_count_included",
        "sensitivity_size_included",
        "sensitivity_position_included",
    }
    if not required_columns.issubset(object_columns):
        raise ValidationError("combined object_columns lacks inclusion audit fields")

    files = manifest["files"]
    if not isinstance(files, list) or len(files) != 1 or not isinstance(files[0], dict):
        raise ValidationError("combined manifest must declare exactly one payload")
    file_record = files[0]
    expected_file_keys = {"relative_path", "bytes", "sha256", "media_type", "authority_role"}
    if set(file_record) != expected_file_keys:
        raise ValidationError("combined payload record field set is not exact")
    if (
        file_record["relative_path"] != COMBINED_PAYLOAD_PATH
        or file_record["media_type"] != "text/tab-separated-values; charset=utf-8"
        or file_record["authority_role"] != "DERIVED_SUMMARY"
        or SHA256_RE.fullmatch(str(file_record["sha256"])) is None
    ):
        raise ValidationError("combined payload record has an invalid closed field")
    _nonnegative_int(file_record["bytes"], "files[0].bytes")

    input_runs = manifest["input_runs"]
    run_count = _nonnegative_int(manifest["run_count"], "run_count")
    if not isinstance(input_runs, list) or not input_runs or len(input_runs) != run_count:
        raise ValidationError("combined input_runs/run_count is invalid")
    expected_input_keys = {
        "run_id",
        "run_uid",
        "run_manifest_sha256",
        "project_uid",
        "image_uid",
        "analysis_session_uid",
        "revision_uid",
        "object_row_count",
    }
    by_uid: dict[str, dict[str, Any]] = {}
    order: list[str] = []
    input_row_total = 0
    for index, record in enumerate(input_runs):
        if not isinstance(record, dict) or set(record) != expected_input_keys:
            raise ValidationError("combined input RUN record field set is not exact", details={"index": index})
        validate_human_id(record["run_id"], field="input_runs.run_id")
        run_uid = validate_canonical_uuid(record["run_uid"])
        for field in ("project_uid", "image_uid", "analysis_session_uid", "revision_uid"):
            validate_canonical_uuid(record[field])
        if record["project_uid"] != manifest["project_uid"]:
            raise ValidationError("combined input RUN belongs to another project", details={"run_uid": run_uid})
        if SHA256_RE.fullmatch(str(record["run_manifest_sha256"])) is None:
            raise ValidationError("combined input RUN hash is invalid", details={"run_uid": run_uid})
        if run_uid in by_uid:
            raise ValidationError("combined input RUN UID is duplicated", details={"run_uid": run_uid})
        input_row_total += _nonnegative_int(record["object_row_count"], "input_runs.object_row_count")
        by_uid[run_uid] = record
        order.append(run_uid)
    if order != sorted(order):
        raise ValidationError("combined input_runs must be sorted by run_uid")
    if input_row_total != _nonnegative_int(manifest["object_row_count"], "object_row_count"):
        raise ValidationError("combined input row counts do not reconcile")

    primary = manifest["primary_included"]
    sensitivity = manifest["sensitivity_included"]
    for name, counters in (("primary_included", primary), ("sensitivity_included", sensitivity)):
        if not isinstance(counters, dict) or set(counters) != {"count", "size", "position"}:
            raise ValidationError("combined inclusion counter object is invalid", details={"field": name})
        for endpoint in ("count", "size", "position"):
            _nonnegative_int(counters[endpoint], f"{name}.{endpoint}")
    for endpoint, manifest_counter in (
        ("count", "N_count_valid"),
        ("size", "N_size_valid"),
        ("position", "N_position_valid"),
    ):
        expected = _nonnegative_int(manifest[manifest_counter], manifest_counter)
        if _nonnegative_int(primary[endpoint], f"primary_included.{endpoint}") != expected:
            raise ValidationError("combined primary counters do not reconcile", details={"endpoint": endpoint})
    area = _decimal(manifest["total_net_area_nm2"], "total_net_area_nm2")
    density = _decimal(manifest["density_N_per_um2"], "density_N_per_um2")
    if area <= 0 or density < 0:
        raise ValidationError("combined area/density domain is invalid")
    expected_density = Decimal(_nonnegative_int(manifest["N_count_valid"], "N_count_valid")) * Decimal(1_000_000) / area
    if density != expected_density:
        raise ValidationError("combined density does not reconcile with count and area")
    return file_record, by_uid


def _parse_combined_object_table(
    data: bytes,
    manifest: Mapping[str, Any],
    input_by_uid: Mapping[str, Mapping[str, Any]],
) -> tuple[tuple[str, ...], tuple[CombinedObjectRow, ...]]:
    if data.startswith(b"\xef\xbb\xbf") or b"\r" in data or not data.endswith(b"\n"):
        raise ValidationError("combined object table encoding/line endings are not exact")
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValidationError("combined object table is not UTF-8") from exc
    lines = text[:-1].split("\n")
    if not lines or not lines[0]:
        raise ValidationError("combined object table header is missing")
    header = tuple(lines[0].split("\t"))
    expected_header = (*COMBINED_RESERVED_COLUMNS, *tuple(manifest["object_columns"]))
    if header != expected_header or len(header) != len(set(header)):
        raise ValidationError("combined object table header differs from manifest")
    per_run_counts = {uid: 0 for uid in input_by_uid}
    rows: list[CombinedObjectRow] = []
    primary = {"count": 0, "size": 0, "position": 0}
    sensitivity = {"count": 0, "size": 0, "position": 0}
    for row_number, line in enumerate(lines[1:], start=2):
        cells = line.split("\t")
        if len(cells) != len(header):
            raise ValidationError("combined object row width is invalid", details={"row": row_number})
        source_uid, source_hash = cells[:2]
        source = input_by_uid.get(source_uid)
        if source is None or source_hash != source["run_manifest_sha256"]:
            raise ValidationError("combined object provenance does not match input_runs", details={"row": row_number})
        values = dict(zip(manifest["object_columns"], cells[2:]))
        per_run_counts[source_uid] += 1
        for endpoint in ("count", "size", "position"):
            for mode, accumulator in (("primary", primary), ("sensitivity", sensitivity)):
                value = values[f"{mode}_{endpoint}_included"]
                if value not in {"0", "1"}:
                    raise ValidationError(
                        "combined inclusion flag is not canonical boolean",
                        details={"row": row_number, "field": f"{mode}_{endpoint}_included"},
                    )
                accumulator[endpoint] += int(value)
        rows.append(
            CombinedObjectRow(
                source_run_uid=source_uid,
                source_run_manifest_sha256=source_hash,
                values=values,
            )
        )
    if len(rows) != _nonnegative_int(manifest["object_row_count"], "object_row_count"):
        raise ValidationError("combined object row count differs from manifest")
    for uid, actual in per_run_counts.items():
        expected = _nonnegative_int(input_by_uid[uid]["object_row_count"], "input_runs.object_row_count")
        if actual != expected:
            raise ValidationError("combined per-RUN row count differs", details={"run_uid": uid})
    for name, actual in (("primary_included", primary), ("sensitivity_included", sensitivity)):
        expected_counters = manifest[name]
        if any(actual[endpoint] != _nonnegative_int(expected_counters[endpoint], f"{name}.{endpoint}") for endpoint in actual):
            raise ValidationError("combined table inclusion counts differ from manifest", details={"field": name})
    return header, tuple(rows)


def _verify_combined_sources(
    manifest: Mapping[str, Any],
    sources: Iterable[VerifiedRun | os.PathLike[str] | str],
) -> tuple[VerifiedRun, ...]:
    verified = tuple(_reverify(source) for source in sources)
    by_uid: dict[str, VerifiedRun] = {}
    for run in verified:
        if run.run_uid in by_uid:
            raise ValidationError("combined verifier received a duplicate source RUN")
        by_uid[run.run_uid] = run
    listed = {str(record["run_uid"]): record for record in manifest["input_runs"]}
    if set(by_uid) != set(listed):
        raise ValidationError(
            "combined verifier source set differs from manifest",
            details={"missing": sorted(set(listed) - set(by_uid)), "extra": sorted(set(by_uid) - set(listed))},
        )
    for uid, run in by_uid.items():
        record = listed[uid]
        exact = {
            "run_id": run.run_id,
            "run_manifest_sha256": run.manifest_sha256,
            "project_uid": run.manifest["project_uid"],
            "image_uid": run.manifest["image_uid"],
            "analysis_session_uid": run.manifest["analysis_session_uid"],
            "revision_uid": run.manifest["revision_uid"],
            "object_row_count": len(run.object_rows),
        }
        for field, expected in exact.items():
            if record[field] != expected:
                raise ValidationError(
                    "combined source RUN does not reconcile with manifest",
                    details={"run_uid": uid, "field": field},
                )
    compatible_hash = assert_compatible_bins(tuple(by_uid.values()))
    if compatible_hash != manifest["bin_contract_sha256"]:
        raise ValidationError("combined bin contract hash differs from source RUNs")
    total_area = sum((_decimal(run.manifest["net_area_nm2"], "net_area_nm2") for run in by_uid.values()), Decimal(0))
    aggregates = {
        "N_count_valid": sum(int(run.manifest["N_count_valid"]) for run in by_uid.values()),
        "N_size_valid": sum(int(run.manifest["N_size_valid"]) for run in by_uid.values()),
        "N_position_valid": sum(int(run.manifest["N_position_valid"]) for run in by_uid.values()),
        "total_net_area_nm2": total_area,
    }
    for field, expected in aggregates.items():
        if manifest[field] != expected:
            raise ValidationError("combined aggregate differs from source RUNs", details={"field": field})
    expected_density = Decimal(aggregates["N_count_valid"]) * Decimal(1_000_000) / total_area
    if manifest["density_N_per_um2"] != expected_density:
        raise ValidationError("combined density differs from source RUNs")
    return tuple(sorted(verified, key=lambda run: run.run_uid))


def verify_combined_run(
    combined_dir: os.PathLike[str] | str,
    *,
    source_runs: Iterable[VerifiedRun | os.PathLike[str] | str] | None = None,
    allow_partial: bool = False,
) -> VerifiedCombinedRun:
    """Verify controls and all hashes before opening combined object data."""

    try:
        path = plain_directory(combined_dir, label="combined artifact directory")
    except PathSafetyError as exc:
        raise ValidationError("combined artifact path is unsafe", details={"cause": str(exc)}) from exc
    if path.name.lower().endswith(".partial") and not allow_partial:
        raise ValidationError("partial combined artifacts are invisible to consumers")
    if not path.name.startswith("COMBINED_"):
        raise ValidationError("combined artifact directory name is not canonical")

    actual_files = _enumerate_combined_files(path)
    if not COMBINED_CONTROL_SET.issubset(actual_files):
        raise ValidationError(
            "combined control set is incomplete",
            details={"missing": sorted(COMBINED_CONTROL_SET - actual_files)},
        )
    try:
        marker_bytes = stable_plain_bytes(path / "COMPLETE", label="combined COMPLETE marker")
        sidecar_bytes = stable_plain_bytes(path / "COMBINED_SHA256.txt", label="combined SHA-256 sidecar")
        manifest_bytes = stable_plain_bytes(path / "combined_manifest.json", label="combined manifest")
    except PathSafetyError as exc:
        raise ValidationError(
            "combined control bytes cannot be read safely",
            details={"cause": str(exc)},
        ) from exc
    marker = parse_combined_complete_marker(marker_bytes)
    sidecar_hash = parse_combined_sidecar(sidecar_bytes)
    if marker["combined_manifest_sha256"] != sidecar_hash:
        raise ValidationError("combined COMPLETE and sidecar hashes differ")
    manifest_path = path / "combined_manifest.json"
    actual_manifest_hash = sha256_bytes(manifest_bytes)
    if actual_manifest_hash != sidecar_hash:
        raise ValidationError("combined manifest bytes do not match controls")
    try:
        manifest = loads_canonical_json(manifest_bytes)
    except ValidationError as exc:
        raise ValidationError("combined manifest is not canonical", details={"cause": str(exc)}) from exc
    file_record, input_by_uid = _validate_combined_manifest(manifest)
    if (
        marker["combined_run_id"] != manifest["combined_run_id"]
        or marker["combined_run_uid"] != manifest["combined_run_uid"]
    ):
        raise ValidationError("combined COMPLETE identity differs from manifest")
    expected_name = f"COMBINED_{manifest['combined_run_id']}"
    allowed_names = {expected_name, expected_name + ".partial"} if allow_partial else {expected_name}
    if path.name not in allowed_names:
        raise ValidationError("combined directory name differs from manifest identity")
    expected_files = set(COMBINED_CONTROL_SET) | {COMBINED_PAYLOAD_PATH}
    if actual_files != expected_files:
        raise ValidationError(
            "combined directory inventory is not closed",
            details={"missing": sorted(expected_files - actual_files), "extra": sorted(actual_files - expected_files)},
        )
    payload = path / COMBINED_PAYLOAD_PATH
    try:
        payload_bytes = stable_plain_bytes(payload, label="combined object-table payload")
    except PathSafetyError as exc:
        raise ValidationError(
            "combined payload cannot be read safely",
            details={"cause": str(exc)},
        ) from exc
    if len(payload_bytes) != _nonnegative_int(file_record["bytes"], "files[0].bytes"):
        raise ValidationError("combined payload byte count differs from manifest")
    if sha256_bytes(payload_bytes) != file_record["sha256"]:
        raise ValidationError("combined payload hash differs from manifest")

    # If source RUNs are supplied, authenticate all of them before opening the
    # already-hashed combined table.  Offline verification still checks every
    # source UID/hash carried by every table row against the sealed manifest.
    verified_sources = _verify_combined_sources(manifest, source_runs) if source_runs is not None else ()
    header, rows = _parse_combined_object_table(payload_bytes, manifest, input_by_uid)
    return VerifiedCombinedRun(
        path=path,
        manifest=manifest,
        manifest_sha256=actual_manifest_hash,
        marker=marker,
        rows=rows,
        object_header=header,
        verified_runs=verified_sources,
    )


def publish_combined_run(
    combined_parent: os.PathLike[str] | str,
    *,
    combined_run_id: str,
    combined_run_uid: str,
    runs: Iterable[VerifiedRun | os.PathLike[str] | str],
    requested_rebin: bool = False,
    atomic_capability: str = "UNKNOWN",
    atomic_proof: AtomicMoveProof | None = None,
) -> PublishedCombinedRun:
    """Seal and publish one immutable combined artifact without a pointer."""

    validate_human_id(combined_run_id, field="combined_run_id")
    validate_canonical_uuid(combined_run_uid)
    try:
        parent = plain_directory(combined_parent, label="combined_runs parent")
    except PathSafetyError as exc:
        raise TransactionError("combined_runs parent is unsafe", details={"cause": str(exc)}) from exc
    final = parent / f"COMBINED_{combined_run_id}"
    partial = parent / f"COMBINED_{combined_run_id}.partial"
    if (
        final.exists()
        or final.is_symlink()
        or partial.exists()
        or partial.is_symlink()
    ):
        raise TransactionError("combined final/partial already exists; replacement is forbidden")

    result = pool_descriptive_runs(
        runs,
        requested_rebin=requested_rebin,
        combined_run_id=combined_run_id,
        combined_run_uid=combined_run_uid,
    )
    try:
        partial.mkdir()
        fsync_directory(parent)
        write_new_file(partial / COMBINED_PAYLOAD_PATH, result.object_table_bytes)
        write_new_file(partial / "combined_manifest.json", result.manifest_bytes)
        write_new_file(partial / "COMBINED_SHA256.txt", render_combined_sidecar(result.manifest_sha256))
        write_new_file(
            partial / "COMPLETE",
            render_combined_complete_marker(
                combined_run_id=combined_run_id,
                combined_run_uid=combined_run_uid,
                manifest_sha256=result.manifest_sha256,
                completed_at=utc_now_z(),
            ),
        )
        fsync_directory(partial)
        verify_combined_run(partial, source_runs=result.verified_runs, allow_partial=True)
    except Exception:
        # The retained sibling remains invisible because normal consumers
        # categorically reject the .partial suffix.
        raise

    holder: dict[str, VerifiedCombinedRun] = {}

    def final_verifier(path: Path) -> bool:
        holder["verified"] = verify_combined_run(path, source_runs=result.verified_runs)
        return True

    directory_result = publish_directory_no_replace(
        partial,
        final,
        verifier=final_verifier,
        atomic_capability=atomic_capability,
        atomic_proof=atomic_proof,
    )
    verified = holder["verified"]
    return PublishedCombinedRun(
        path=directory_result.final_path,
        manifest_sha256=result.manifest_sha256,
        atomic_move_capability=directory_result.atomic_move_capability,
        verified=verified,
    )


# A concise public alias for callers that already know the operation is only
# descriptive.  There is intentionally no inferential ``combine`` alternative.
combine_runs = pool_descriptive_runs
