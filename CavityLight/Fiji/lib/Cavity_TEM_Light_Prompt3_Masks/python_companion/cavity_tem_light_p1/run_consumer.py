"""Strict consumer for Prompt-1 ``COMPLETE`` RUN directories.

The module intentionally separates trust establishment from scientific data
access.  ``verify_run_directory`` verifies controls, canonical manifest,
closed inventory, bridge versions, registry state and every payload hash
*before* parsing ``cavity_objects.tsv``.  It never searches for the newest
directory and never falls back to ``current_run.txt``.
"""

from __future__ import annotations

import os
import re
import unicodedata
import uuid
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path, PurePosixPath
from typing import Any, Callable, Mapping

from .canonical_json import PROFILE_ID, loads_canonical_json
from .critical_io import assert_no_blocking_journals, sha256_bytes
from .errors import Prompt1Error, UnsafePathError, ValidationError
from .path_safety import (
    PathSafetyError,
    is_reparse_or_link,
    lexical_absolute,
    plain_directory,
    plain_file,
    stable_plain_bytes,
)
from .run_context import RunContractContext, normalize_run_context


CONTROL_SET = frozenset({"run_manifest.json", "RUN_SHA256.txt", "COMPLETE"})
POINTER_COLUMNS = (
    "pointer_version",
    "project_uid",
    "image_uid",
    "analysis_session_uid",
    "run_uid",
    "run_id",
    "relative_path",
    "run_manifest_sha256",
    "generation",
    "updated_at",
)
FILE_AUTHORITY_ROLES = frozenset(
    {
        "SOURCE_REFERENCE",
        "REVISION_AUTHORITY",
        "OBJECT_TABLE_AUTHORITY",
        "DERIVED_SUMMARY",
        "VISUALIZATION_ONLY",
        "DERIVED_CACHE",
        "AUDIT_LOG",
    }
)
RUN_LIFECYCLES = frozenset({"CURRENT", "HISTORICAL", "SUPERSEDED", "ARCHIVED"})
UUID_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
UTC_Z_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d*[1-9])?Z$")


class RunVerificationError(ValidationError):
    """A stage-specific failure in the immutable RUN trust chain."""

    code = "RUN_TRUST_CHAIN_FAILED"

    def __init__(self, stage: str, message: str, *, details: dict[str, Any] | None = None) -> None:
        payload = {"stage": stage}
        if details:
            payload.update(details)
        super().__init__(message, details=payload)
        self.stage = stage


@dataclass(frozen=True)
class CurrentRunPointer:
    pointer_version: int
    project_uid: str
    image_uid: str
    analysis_session_uid: str
    run_uid: str
    run_id: str
    relative_path: str
    run_manifest_sha256: str
    generation: int
    updated_at: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "pointer_version": self.pointer_version,
            "project_uid": self.project_uid,
            "image_uid": self.image_uid,
            "analysis_session_uid": self.analysis_session_uid,
            "run_uid": self.run_uid,
            "run_id": self.run_id,
            "relative_path": self.relative_path,
            "run_manifest_sha256": self.run_manifest_sha256,
            "generation": self.generation,
            "updated_at": self.updated_at,
        }


@dataclass(frozen=True)
class VerifiedRun:
    path: Path
    manifest: dict[str, Any]
    manifest_sha256: str
    marker: dict[str, str]
    payload_paths: dict[str, Path]
    object_rows: tuple[dict[str, str], ...]
    object_header: tuple[str, ...]
    pointer: CurrentRunPointer | None = None

    @property
    def run_id(self) -> str:
        return str(self.manifest["run_id"])

    @property
    def run_uid(self) -> str:
        return str(self.manifest["run_uid"])


def _fail(stage: str, message: str, **details: Any) -> None:
    raise RunVerificationError(stage, message, details=details or None)


def _is_link_or_reparse(path: Path) -> bool:
    try:
        return is_reparse_or_link(path)
    except PathSafetyError as exc:
        _fail("PATH_IDENTITY", "native path identity could not be established", path=str(path), reason=str(exc))


def _require_uuid(value: Any, field: str, stage: str) -> str:
    if not isinstance(value, str) or not UUID_RE.fullmatch(value):
        _fail(stage, "UUID is not canonical lowercase", field=field, value=value)
    try:
        if str(uuid.UUID(value)) != value:
            _fail(stage, "UUID does not round-trip canonically", field=field, value=value)
    except ValueError:
        _fail(stage, "UUID is invalid", field=field, value=value)
    return value


def _require_sha(value: Any, field: str, stage: str) -> str:
    if not isinstance(value, str) or not SHA256_RE.fullmatch(value):
        _fail(stage, "SHA-256 is not 64 lowercase hex", field=field, value=value)
    return value


def _require_id(value: Any, field: str, stage: str) -> str:
    if not isinstance(value, str) or not ID_RE.fullmatch(value):
        _fail(stage, "identifier does not satisfy the closed grammar", field=field, value=value)
    if value in {".", "..", "UNKNOWN", "NOT_APPLICABLE", "NOT_MEASURED", "UNDEFINED"}:
        _fail(stage, "identifier is a reserved sentinel/path token", field=field, value=value)
    stem = value.split(".", 1)[0].upper()
    if stem in {"CON", "PRN", "AUX", "NUL"} or re.fullmatch(r"(?:COM|LPT)[1-9]", stem):
        _fail(stage, "identifier is a reserved Windows device name", field=field, value=value)
    return value


def _require_utc_z(value: Any, field: str, stage: str) -> str:
    if not isinstance(value, str) or not UTC_Z_RE.fullmatch(value):
        _fail(stage, "timestamp must be canonical RFC3339 UTC Z", field=field, value=value)
    from datetime import datetime
    try:
        body = value[:-1]
        base, separator, fraction = body.partition(".")
        datetime.strptime(base, "%Y-%m-%dT%H:%M:%S")
        if separator and (not fraction.isdigit() or len(fraction) > 6):
            raise ValueError("invalid fractional second")
    except ValueError:
        _fail(stage, "timestamp is not a real calendar time", field=field, value=value)
    return value


def _finite_decimal(value: Any, field: str, stage: str, *, positive: bool = False, nonnegative: bool = False) -> Decimal:
    if isinstance(value, bool) or value is None:
        _fail(stage, "numeric field is absent or boolean", field=field, value=value)
    try:
        number = value if isinstance(value, Decimal) else Decimal(str(value))
    except (InvalidOperation, ValueError):
        _fail(stage, "numeric field is invalid", field=field, value=value)
    if not number.is_finite():
        _fail(stage, "numeric field is non-finite", field=field, value=str(value))
    if positive and number <= 0:
        _fail(stage, "numeric field must be positive", field=field, value=str(value))
    if nonnegative and number < 0:
        _fail(stage, "numeric field must be nonnegative", field=field, value=str(value))
    return number


def _decimal_close(actual: Decimal, expected: Decimal) -> bool:
    tolerance = max(Decimal("1e-24"), abs(expected) * Decimal("1e-12"))
    return abs(actual - expected) <= tolerance


def validate_relative_path(value: Any, *, stage: str = "PATH") -> str:
    if not isinstance(value, str) or not value:
        _fail(stage, "relative path is missing")
    if unicodedata.normalize("NFC", value) != value:
        _fail(stage, "relative path is not NFC", relative_path=value)
    if any(char in value for char in ("\\", "\x00", "\r", "\n", "\t")):
        _fail(stage, "relative path contains a forbidden character", relative_path=value)
    if value.startswith("/") or re.match(r"^[A-Za-z]:", value) or "://" in value:
        _fail(stage, "relative path is absolute, drive-qualified, or a URI", relative_path=value)
    pure = PurePosixPath(value)
    parts = pure.parts
    if not parts or str(pure) != value or any(part in {"", ".", ".."} for part in parts):
        _fail(stage, "relative path is not canonical", relative_path=value)
    if any(part.endswith((".", " ")) for part in parts):
        _fail(stage, "relative path segment has trailing dot/space", relative_path=value)
    return value


def resolve_contained(root: os.PathLike[str] | str, relative_path: str, *, stage: str = "PATH") -> Path:
    relative_path = validate_relative_path(relative_path, stage=stage)
    try:
        root_path = plain_directory(root, label="authorized root")
    except PathSafetyError as exc:
        raise UnsafePathError(
            "authorized root is not a plain directory",
            details={"root": str(root), "cause": str(exc)},
        ) from exc
    candidate = root_path.joinpath(*PurePosixPath(relative_path).parts)
    try:
        # Check the full lexical chain before resolving it so a link cannot be
        # hidden by canonicalisation.
        if candidate.is_file():
            resolved = plain_file(candidate, label=f"{stage} target", single_link=True)
        elif candidate.is_dir():
            resolved = plain_directory(candidate, label=f"{stage} target")
        else:
            raise PathSafetyError(f"{stage} target is not a regular file or directory: {candidate}")
    except (OSError, PathSafetyError) as exc:
        _fail(stage, "relative path target does not exist", relative_path=relative_path, reason=str(exc))
    try:
        if os.path.commonpath((str(root_path), str(resolved))) != str(root_path):
            _fail(stage, "relative path escapes the authorized root", relative_path=relative_path)
    except ValueError:
        _fail(stage, "relative path is on a different volume", relative_path=relative_path)
    return resolved


def render_current_run_pointer(pointer: CurrentRunPointer) -> bytes:
    validate_pointer(pointer)
    row = pointer.as_dict()
    header = "\t".join(POINTER_COLUMNS)
    values = "\t".join(str(row[column]) for column in POINTER_COLUMNS)
    return (header + "\n" + values + "\n").encode("utf-8")


def validate_pointer(pointer: CurrentRunPointer) -> None:
    if pointer.pointer_version != 1:
        _fail("POINTER_SCHEMA", "pointer_version must be 1", value=pointer.pointer_version)
    for field in ("project_uid", "image_uid", "analysis_session_uid", "run_uid"):
        _require_uuid(getattr(pointer, field), field, "POINTER_IDENTITY")
    _require_id(pointer.run_id, "run_id", "POINTER_IDENTITY")
    validate_relative_path(pointer.relative_path, stage="POINTER_PATH")
    if any(part.lower().endswith(".partial") for part in PurePosixPath(pointer.relative_path).parts):
        _fail("POINTER_PATH", "pointer may not address a partial directory", relative_path=pointer.relative_path)
    _require_sha(pointer.run_manifest_sha256, "run_manifest_sha256", "POINTER_IDENTITY")
    if isinstance(pointer.generation, bool) or not isinstance(pointer.generation, int) or pointer.generation < 1:
        _fail("POINTER_IDENTITY", "generation must be a positive integer", generation=pointer.generation)
    _require_utc_z(pointer.updated_at, "updated_at", "POINTER_IDENTITY")


def parse_current_run_pointer(data: bytes) -> CurrentRunPointer:
    stage = "POINTER_SCHEMA"
    if not isinstance(data, bytes) or data.startswith(b"\xef\xbb\xbf") or b"\r" in data or not data.endswith(b"\n"):
        _fail(stage, "pointer must be UTF-8 without BOM/CR and with final LF")
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as exc:
        _fail(stage, "pointer is not UTF-8", offset=exc.start)
    lines = text.split("\n")
    if len(lines) != 3 or lines[-1] != "":
        _fail(stage, "pointer must contain exactly header + one row + final LF")
    header = tuple(lines[0].split("\t"))
    values = lines[1].split("\t")
    if header != POINTER_COLUMNS or len(values) != len(POINTER_COLUMNS):
        _fail(stage, "pointer columns are not exact", header=list(header), field_count=len(values))
    if any(any(forbidden in value for forbidden in ("\r", "\n", "\x00")) for value in values):
        _fail(stage, "pointer contains a forbidden unescaped field character")
    if not values[0].isdigit() or str(int(values[0])) != values[0]:
        _fail(stage, "pointer_version is not canonical integer text")
    if not values[8].isdigit() or str(int(values[8])) != values[8]:
        _fail(stage, "generation is not canonical integer text")
    pointer = CurrentRunPointer(
        pointer_version=int(values[0]),
        project_uid=values[1],
        image_uid=values[2],
        analysis_session_uid=values[3],
        run_uid=values[4],
        run_id=values[5],
        relative_path=values[6],
        run_manifest_sha256=values[7],
        generation=int(values[8]),
        updated_at=values[9],
    )
    validate_pointer(pointer)
    return pointer


def parse_complete_marker(data: bytes) -> dict[str, str]:
    stage = "COMPLETE_MARKER"
    if data.startswith(b"\xef\xbb\xbf") or b"\r" in data or not data.endswith(b"\n"):
        _fail(stage, "COMPLETE marker encoding is not exact")
    try:
        text = data.decode("ascii")
    except UnicodeDecodeError as exc:
        _fail(stage, "COMPLETE marker is not ASCII", offset=exc.start)
    lines = text.splitlines()
    expected_keys = (
        "marker_version",
        "run_id",
        "run_uid",
        "schema_version",
        "run_manifest_sha256",
        "completed_at",
    )
    if len(lines) != 6:
        _fail(stage, "COMPLETE must contain exactly six lines", line_count=len(lines))
    result: dict[str, str] = {}
    for expected, line in zip(expected_keys, lines):
        if line.count("\t") != 1:
            _fail(stage, "COMPLETE line must contain exactly one HT", line=line)
        key, value = line.split("\t")
        if key != expected or not value:
            _fail(stage, "COMPLETE key order/value is invalid", expected=expected, actual=key)
        result[key] = value
    if result["marker_version"] != "1" or result["schema_version"] != "2":
        _fail(stage, "COMPLETE versions are invalid")
    _require_id(result["run_id"], "run_id", stage)
    _require_uuid(result["run_uid"], "run_uid", stage)
    _require_sha(result["run_manifest_sha256"], "run_manifest_sha256", stage)
    _require_utc_z(result["completed_at"], "completed_at", stage)
    return result


def render_complete_marker(*, run_id: str, run_uid: str, manifest_sha256: str, completed_at: str) -> bytes:
    marker = (
        f"marker_version\t1\n"
        f"run_id\t{run_id}\n"
        f"run_uid\t{run_uid}\n"
        f"schema_version\t2\n"
        f"run_manifest_sha256\t{manifest_sha256}\n"
        f"completed_at\t{completed_at}\n"
    ).encode("ascii")
    parse_complete_marker(marker)
    return marker


def parse_sidecar(data: bytes) -> str:
    stage = "RUN_SIDECAR"
    if len(data) != 84:
        _fail(stage, "RUN_SHA256.txt must be exactly 84 bytes", bytes=len(data))
    try:
        text = data.decode("ascii")
    except UnicodeDecodeError as exc:
        _fail(stage, "RUN_SHA256.txt is not ASCII", offset=exc.start)
    match = re.fullmatch(r"([0-9a-f]{64})  run_manifest\.json\n", text)
    if match is None:
        _fail(stage, "RUN_SHA256.txt format is not exact")
    return match.group(1)


def render_sidecar(manifest_sha256: str) -> bytes:
    _require_sha(manifest_sha256, "run_manifest_sha256", "RUN_SIDECAR")
    data = f"{manifest_sha256}  run_manifest.json\n".encode("ascii")
    if len(data) != 84:
        raise AssertionError("closed sidecar format must be 84 bytes")
    return data


def _enumerate_plain_files(run_dir: Path) -> set[str]:
    stage = "DIRECTORY_INVENTORY"
    actual: set[str] = set()

    def visit(directory: Path) -> None:
        try:
            entries = sorted(os.scandir(directory), key=lambda entry: entry.name)
        except OSError as exc:
            _fail(stage, "RUN directory cannot be enumerated", path=str(directory), reason=str(exc))
        if directory != run_dir and not entries:
            _fail(stage, "RUN contains an undeclared empty directory", relative_path=directory.relative_to(run_dir).as_posix())
        for entry in entries:
            path = Path(entry.path)
            relative = path.relative_to(run_dir).as_posix()
            try:
                if is_reparse_or_link(path):
                    _fail(stage, "RUN contains a link/reparse point", relative_path=relative)
                if entry.is_dir(follow_symlinks=False):
                    plain_directory(path, label="RUN inventory directory")
                    visit(path)
                    continue
                plain_file(path, label="RUN inventory file", single_link=True)
            except PathSafetyError as exc:
                _fail(stage, "RUN contains an unsafe or non-regular entry", relative_path=relative, reason=str(exc))
            validate_relative_path(relative, stage=stage)
            if relative in actual:
                _fail(stage, "RUN contains a duplicate relative path", relative_path=relative)
            actual.add(relative)

    visit(run_dir)
    return actual


def _validate_manifest_core(
    manifest: dict[str, Any],
    *,
    run_context: RunContractContext | None = None,
) -> None:
    stage = "MANIFEST_SCHEMA"
    context = normalize_run_context(run_context)
    exact_values = {
        "run_state": "COMPLETE",
        "serialization_profile": PROFILE_ID,
        **context.manifest_values,
    }
    for field, expected in exact_values.items():
        if manifest.get(field) != expected:
            _fail(stage, "manifest bridge/state field is invalid", field=field, expected=expected, actual=manifest.get(field))
    try:
        context.validate_manifest_owner(manifest)
    except ValidationError as exc:
        _fail(
            stage,
            "manifest owner differs from the selected RUN authority",
            cause_code=exc.code,
            cause_message=str(exc),
            cause_details=exc.details,
        )
    if "run_manifest_sha256" in manifest:
        _fail(stage, "manifest must not contain its own hash")
    if manifest.get("validation_status") not in {"PASS", "PASS_WITH_WARNINGS"}:
        _fail(stage, "sealed manifest validation_status is not publishable")
    _require_utc_z(manifest.get("validation_at"), "validation_at", stage)
    _require_sha(manifest.get("validation_fingerprint_sha256"), "validation_fingerprint_sha256", stage)
    if manifest.get("validation_errors") != []:
        _fail(stage, "sealed manifest validation_errors must be empty")
    if not isinstance(manifest.get("validation_warnings"), list):
        _fail(stage, "sealed manifest validation_warnings must be an array")
    for field in ("project_uid", "image_uid", "analysis_session_uid", "revision_uid", "run_uid"):
        _require_uuid(manifest.get(field), field, stage)
    for field in ("revision_id", "run_id"):
        _require_id(manifest.get(field), field, stage)
    for field in ("source_sha256", "master_pixel_sha256", "roi_zip_sha256", "revision_manifest_sha256"):
        _require_sha(manifest.get(field), field, stage)
    if manifest.get("zero_event_status") not in {"EVENTS_PRESENT", "ZERO_EVENTS_VALID"}:
        _fail(stage, "zero_event_status is invalid")
    for field in ("N_count_valid", "N_size_valid", "N_position_valid"):
        value = manifest.get(field)
        if isinstance(value, bool) or not isinstance(value, (int, Decimal)) or value != int(value) or value < 0:
            _fail(stage, "RUN counter must be a nonnegative integer", field=field, value=str(value))
    if manifest["N_count_valid"] == 0 and manifest["zero_event_status"] != "ZERO_EVENTS_VALID":
        _fail(stage, "N=0 must be explicitly ZERO_EVENTS_VALID")
    if manifest["N_count_valid"] > 0 and manifest["zero_event_status"] != "EVENTS_PRESENT":
        _fail(stage, "positive N must be EVENTS_PRESENT")
    if manifest["N_size_valid"] == 0:
        if manifest.get("mean_size_nm") is not None or manifest.get("mean_size_nm_status") != "UNDEFINED":
            _fail(stage, "empty size endpoint must persist null + UNDEFINED")
    else:
        _finite_decimal(manifest.get("mean_size_nm"), "mean_size_nm", stage, positive=True)
        if manifest.get("mean_size_nm_status") != "KNOWN":
            _fail(stage, "present mean size requires KNOWN status")
    nominal = manifest.get("density_N_per_m3_nominal")
    nominal_status = manifest.get("density_N_per_m3_nominal_status")
    if nominal_status == "KNOWN":
        _finite_decimal(nominal, "density_N_per_m3_nominal", stage, nonnegative=True)
    elif nominal is not None or nominal_status not in {"UNKNOWN", "NOT_APPLICABLE", "NOT_MEASURED", "UNDEFINED"}:
        _fail(stage, "nominal density violates typed absence invariant")
    area = _finite_decimal(manifest.get("net_area_nm2"), "net_area_nm2", stage, positive=True)
    areal_density = _finite_decimal(manifest.get("density_N_per_um2"), "density_N_per_um2", stage, nonnegative=True)
    expected_density = Decimal(int(manifest["N_count_valid"])) * Decimal(1_000_000) / area
    if not _decimal_close(areal_density, expected_density):
        _fail(
            stage,
            "areal density does not reconcile with N_count_valid/net_area_nm2",
            expected=str(expected_density),
            actual=str(areal_density),
        )
    if manifest.get("density_ci_status") != "NOT_COMPUTED" or manifest.get("density_intervals") != []:
        _fail(stage, "Prompt 1 requires density_ci_status=NOT_COMPUTED and empty intervals")


def _manifest_payload_records(manifest: dict[str, Any]) -> tuple[list[dict[str, Any]], set[str]]:
    stage = "MANIFEST_FILES"
    files = manifest.get("files")
    if not isinstance(files, list):
        _fail(stage, "manifest files must be an array")
    records: list[dict[str, Any]] = []
    seen: set[str] = set()
    previous = ""
    object_authorities = 0
    for index, record in enumerate(files):
        if not isinstance(record, dict):
            _fail(stage, "manifest file record is not an object", index=index)
        required = {"relative_path", "bytes", "sha256", "media_type", "authority_role"}
        if set(record) != required:
            _fail(stage, "manifest file record fields are not exact", index=index, fields=sorted(record))
        relative = validate_relative_path(record["relative_path"], stage=stage)
        if relative in CONTROL_SET:
            _fail(stage, "control file may not appear in files[]", relative_path=relative)
        if relative in seen or (previous and relative < previous):
            _fail(stage, "files[] is duplicated or not sorted", relative_path=relative)
        seen.add(relative)
        previous = relative
        size = record["bytes"]
        if isinstance(size, bool) or not isinstance(size, (int, Decimal)) or size != int(size) or size < 0:
            _fail(stage, "payload byte count is invalid", relative_path=relative, value=str(size))
        _require_sha(record["sha256"], "sha256", stage)
        if not isinstance(record["media_type"], str) or not record["media_type"]:
            _fail(stage, "payload media_type is missing", relative_path=relative)
        if record["authority_role"] not in FILE_AUTHORITY_ROLES:
            _fail(stage, "payload authority_role is invalid", relative_path=relative)
        if record["authority_role"] == "OBJECT_TABLE_AUTHORITY":
            object_authorities += 1
            if relative != "cavity_objects.tsv":
                _fail(stage, "object-table authority must be cavity_objects.tsv", relative_path=relative)
        records.append(record)
    if object_authorities != 1 or "cavity_objects.tsv" not in seen:
        _fail(stage, "RUN must contain exactly one cavity_objects.tsv authority")
    return records, seen


def _parse_object_table(
    data: bytes,
    manifest: Mapping[str, Any],
    *,
    run_context: RunContractContext | None = None,
) -> tuple[tuple[str, ...], tuple[dict[str, str], ...]]:
    # The consumer must use the same complete physical contract as the writer.
    # Keeping a permissive subset parser here would silently reintroduce the
    # obsolete R9/17-column fallback that the approved profile explicitly
    # closes.  Import lazily to avoid a module cycle through run_transaction.
    from .object_table import parse_object_table_bytes

    try:
        parsed = parse_object_table_bytes(
            data,
            manifest=manifest,
            run_context=run_context,
        )
    except RunVerificationError:
        raise
    except Prompt1Error as exc:
        _fail(
            "OBJECT_TABLE",
            "cavity_objects.tsv violates CTL_CAVITY_OBJECTS_TSV_PROFILE_V1",
            cause_code=exc.code,
            cause_message=str(exc),
            cause_details=exc.details,
        )
    return parsed.header, parsed.rows


def _check_registry(
    registry_path: Path,
    manifest: Mapping[str, Any],
    manifest_hash: str,
    run_dir: Path,
    expected_pointer: CurrentRunPointer | None,
    run_context: RunContractContext | None = None,
) -> None:
    stage = "RUN_REGISTRY"
    context = normalize_run_context(run_context)
    assert_no_blocking_journals(registry_path.parent)
    try:
        registry = loads_canonical_json(
            stable_plain_bytes(registry_path, label="external RUN registry")
        )
    except (PathSafetyError, ValidationError) as exc:
        _fail(stage, "external registry is absent or invalid", path=str(registry_path), reason=str(exc))
    if registry.get("registry_version") != 1 or not isinstance(registry.get("runs"), list):
        _fail(stage, "external registry schema is invalid")
    if context.is_native_schema2:
        expected_owner = {
            "project_uid": context.project_uid,
            "image_uid": manifest["image_uid"],
            "analysis_session_uid": context.analysis_session_uid,
        }
        for index, record in enumerate(registry["runs"]):
            if not isinstance(record, dict):
                _fail(stage, "external registry record is not an object", index=index)
            for field, expected in expected_owner.items():
                if record.get(field) != expected:
                    _fail(
                        stage,
                        "external registry contains a cross-owner RUN",
                        index=index,
                        field=field,
                        expected=expected,
                        actual=record.get(field),
                    )
    matches = [item for item in registry["runs"] if isinstance(item, dict) and item.get("run_uid") == manifest["run_uid"]]
    if len(matches) != 1:
        _fail(stage, "external registry does not contain exactly one RUN", matches=len(matches))
    item = matches[0]
    if item.get("run_lifecycle") not in RUN_LIFECYCLES:
        _fail(stage, "registry lifecycle is invalid")
    if item.get("quarantine_status") != "ACTIVE":
        _fail(stage, "RUN is quarantined by external authority", reason=item.get("quarantine_reason"))
    expected = {
        "run_id": manifest["run_id"],
        "run_manifest_sha256": manifest_hash,
    }
    for field, value in expected.items():
        if item.get(field) != value:
            _fail(stage, "registry and RUN do not reconcile", field=field)
    if expected_pointer is not None:
        if item.get("run_lifecycle") != "CURRENT":
            _fail(stage, "pointer addresses a RUN not CURRENT in registry")
        if item.get("relative_path") != expected_pointer.relative_path:
            _fail(stage, "registry relative_path differs from pointer")
        generation = item.get("pointer_generation")
        if generation != expected_pointer.generation or item.get("pointer_updated_at") != expected_pointer.updated_at:
            _fail(stage, "registry pointer generation/time differs", registry_generation=str(generation), pointer_generation=expected_pointer.generation)
    if "absolute_path" in item and Path(item["absolute_path"]).resolve(strict=True) != run_dir:
        _fail(stage, "registry path does not reconcile")


RevisionVerifier = Callable[[Mapping[str, Any]], Any]


def verify_run_directory(
    run_dir: os.PathLike[str] | str,
    *,
    expected_pointer: CurrentRunPointer | None = None,
    registry_path: os.PathLike[str] | str | None = None,
    revision_verifier: RevisionVerifier | None = None,
    allow_partial: bool = False,
    run_context: RunContractContext | None = None,
) -> VerifiedRun:
    """Verify an immutable RUN and only then parse its authority table."""

    if allow_partial and run_context is None:
        _fail(
            "RUN_DIRECTORY",
            "partial RUN verification requires an explicit closed contract context",
        )
    context = normalize_run_context(run_context)
    try:
        path = plain_directory(run_dir, label="RUN directory")
    except PathSafetyError as exc:
        _fail("RUN_DIRECTORY", "RUN path is not a plain directory", path=str(run_dir), reason=str(exc))
    partial_like_name = re.search(r"\.partial(?:\.|$)", path.name, re.IGNORECASE) is not None
    if partial_like_name and not allow_partial:
        _fail("RUN_DIRECTORY", "partial RUN is invisible to consumers", path=str(path))
    if not path.name.startswith("RUN_"):
        _fail("RUN_DIRECTORY", "RUN directory name is not canonical", name=path.name)
    try:
        context.validate_control_paths(run_directory=path)
        if registry_path is not None:
            context.validate_control_paths(registry_path=registry_path)
    except ValidationError as exc:
        _fail(
            "RUN_SESSION_PARENT",
            "RUN controls differ from the verified physical parent",
            cause_code=exc.code,
            cause_message=str(exc),
            cause_details=exc.details,
        )

    # Enumerate safely first.  Exact set equality follows only after the
    # independently authenticated manifest can declare PAYLOAD_SET.
    actual_files = _enumerate_plain_files(path)
    if not CONTROL_SET.issubset(actual_files):
        _fail("DIRECTORY_INVENTORY", "RUN control set is incomplete", missing=sorted(CONTROL_SET - actual_files))

    try:
        marker_bytes = stable_plain_bytes(path / "COMPLETE", label="RUN COMPLETE marker")
        sidecar_bytes = stable_plain_bytes(path / "RUN_SHA256.txt", label="RUN SHA-256 sidecar")
        manifest_bytes = stable_plain_bytes(path / "run_manifest.json", label="RUN manifest")
    except PathSafetyError as exc:
        _fail("RUN_INTEGRITY", "RUN control bytes cannot be read safely", reason=str(exc))
    marker = parse_complete_marker(marker_bytes)
    sidecar_hash = parse_sidecar(sidecar_bytes)
    if marker["run_manifest_sha256"] != sidecar_hash:
        _fail("RUN_INTEGRITY", "COMPLETE and RUN_SHA256.txt hashes differ")
    if expected_pointer is not None and expected_pointer.run_manifest_sha256 != sidecar_hash:
        _fail("RUN_INTEGRITY", "pointer hash differs from RUN controls")

    manifest_path = path / "run_manifest.json"
    actual_manifest_hash = sha256_bytes(manifest_bytes)
    if actual_manifest_hash != sidecar_hash:
        _fail("MANIFEST_HASH", "run_manifest.json bytes do not match controls", expected=sidecar_hash, actual=actual_manifest_hash)
    try:
        manifest = loads_canonical_json(manifest_bytes)
    except ValidationError as exc:
        _fail("MANIFEST_PROFILE", "run_manifest.json is not canonical", reason=str(exc), details=getattr(exc, "details", {}))
    _validate_manifest_core(manifest, run_context=context)
    if marker["run_id"] != manifest["run_id"] or marker["run_uid"] != manifest["run_uid"]:
        _fail("RUN_IDENTITY", "COMPLETE identity differs from manifest")
    expected_directory_name = f"RUN_{manifest['run_id']}"
    allowed_names = {expected_directory_name}
    if allow_partial:
        if context.is_native_schema2:
            partial_pattern = re.escape(expected_directory_name) + r"\.partial\.[0-9a-f]{32}"
        else:
            partial_pattern = re.escape(expected_directory_name) + r"\.partial"
        if re.fullmatch(partial_pattern, path.name) is not None:
            allowed_names.add(path.name)
    if path.name not in allowed_names:
        _fail("RUN_IDENTITY", "directory name differs from manifest run_id", directory=path.name, run_id=manifest["run_id"])
    if expected_pointer is not None:
        for field in ("project_uid", "image_uid", "analysis_session_uid", "run_uid", "run_id"):
            if getattr(expected_pointer, field) != str(manifest[field]):
                _fail("RUN_IDENTITY", "pointer identity differs from manifest", field=field)

    records, payload_set = _manifest_payload_records(manifest)
    expected_files = payload_set | set(CONTROL_SET)
    if actual_files != expected_files:
        _fail(
            "DIRECTORY_INVENTORY",
            "RUN directory is not the exact CONTROL_SET union PAYLOAD_SET",
            missing=sorted(expected_files - actual_files),
            extra=sorted(actual_files - expected_files),
        )

    payload_paths: dict[str, Path] = {}
    object_data: bytes | None = None
    for record in records:
        relative = str(record["relative_path"])
        payload = resolve_contained(path, relative, stage="PAYLOAD_PATH")
        try:
            payload_data = stable_plain_bytes(payload, label=f"RUN payload {relative}")
        except PathSafetyError as exc:
            _fail(
                "PAYLOAD_HASH",
                "payload cannot be read safely",
                relative_path=relative,
                reason=str(exc),
            )
        actual_size = len(payload_data)
        if actual_size != int(record["bytes"]):
            _fail("PAYLOAD_HASH", "payload byte count differs", relative_path=relative, expected=str(record["bytes"]), actual=actual_size)
        actual_hash = sha256_bytes(payload_data)
        if actual_hash != record["sha256"]:
            _fail("PAYLOAD_HASH", "payload SHA-256 differs", relative_path=relative, expected=record["sha256"], actual=actual_hash)
        payload_paths[relative] = payload
        if relative == "cavity_objects.tsv":
            object_data = payload_data

    # Revision/master agreement is checked after all immutable bytes are
    # authenticated but before the scientific table is opened.
    if revision_verifier is not None:
        outcome = revision_verifier(manifest)
        if outcome is False:
            _fail("REVISION_CHAIN", "revision verifier rejected RUN binding")
    if registry_path is not None:
        try:
            checked_registry = plain_file(registry_path, label="external RUN registry", single_link=True)
        except PathSafetyError as exc:
            _fail("RUN_REGISTRY", "external registry is unsafe", path=str(registry_path), reason=str(exc))
        _check_registry(
            checked_registry,
            manifest,
            actual_manifest_hash,
            path,
            expected_pointer,
            run_context=context,
        )

    if object_data is None:  # Defensive: the manifest validator requires it.
        _fail("OBJECT_TABLE", "authenticated cavity_objects.tsv bytes are unavailable")
    header, rows = _parse_object_table(
        object_data,
        manifest,
        run_context=context,
    )
    return VerifiedRun(
        path=path,
        manifest=manifest,
        manifest_sha256=actual_manifest_hash,
        marker=marker,
        payload_paths=payload_paths,
        object_rows=rows,
        object_header=header,
        pointer=expected_pointer,
    )


def load_current_run(
    project_root: os.PathLike[str] | str,
    pointer_path: os.PathLike[str] | str,
    *,
    registry_path: os.PathLike[str] | str | None = None,
    revision_verifier: RevisionVerifier | None = None,
    run_context: RunContractContext | None = None,
) -> VerifiedRun:
    """Follow exactly one v2 pointer; there is deliberately no fallback."""

    context = normalize_run_context(run_context)
    if context.is_native_schema2 and registry_path is None:
        _fail(
            "RUN_REGISTRY",
            "native schema-2 current RUN consumption requires its owning session registry",
        )
    try:
        root = plain_directory(project_root, label="project root")
    except PathSafetyError as exc:
        _fail("POINTER_PATH", "project root is unsafe", path=str(project_root), reason=str(exc))
    try:
        pointer_file = plain_file(pointer_path, label="current_run.tsv", single_link=True)
    except PathSafetyError as exc:
        _fail("POINTER_SCHEMA", "current_run.tsv is unsafe", path=str(pointer_path), reason=str(exc))
    if pointer_file.name != "current_run.tsv":
        _fail("POINTER_SCHEMA", "authoritative pointer must be named current_run.tsv")
    try:
        context.validate_control_paths(
            resolution_root=root,
            current_pointer_path=pointer_file,
            registry_path=registry_path,
        )
    except ValidationError as exc:
        _fail(
            "RUN_SESSION_PARENT",
            "current RUN controls differ from the verified physical parent",
            cause_code=exc.code,
            cause_message=str(exc),
            cause_details=exc.details,
        )
    assert_no_blocking_journals(pointer_file.parent)
    try:
        pointer_bytes = stable_plain_bytes(pointer_file, label="current_run.tsv")
    except PathSafetyError as exc:
        _fail("POINTER_SCHEMA", "current_run.tsv cannot be read safely", reason=str(exc))
    pointer = parse_current_run_pointer(pointer_bytes)
    if context.is_native_schema2:
        expected_pointer_owner = {
            "project_uid": context.project_uid,
            "image_uid": context.image_uid,
            "analysis_session_uid": context.analysis_session_uid,
        }
        for field, expected in expected_pointer_owner.items():
            if expected is not None and getattr(pointer, field) != expected:
                _fail(
                    "RUN_SESSION_PARENT",
                    "current_run.tsv belongs to a different verified owner",
                    field=field,
                    expected=expected,
                    actual=getattr(pointer, field),
                )
    run_dir = resolve_contained(root, pointer.relative_path, stage="POINTER_PATH")
    return verify_run_directory(
        run_dir,
        expected_pointer=pointer,
        registry_path=registry_path,
        revision_verifier=revision_verifier,
        run_context=context,
    )
