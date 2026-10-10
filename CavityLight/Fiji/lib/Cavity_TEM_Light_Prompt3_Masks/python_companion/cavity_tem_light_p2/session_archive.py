"""Deterministic, non-destructive schema-2 session archives.

``CTL_SESSION_ARCHIVE_V1`` stores the expanded session bytes below a single
archive root and stores only a verified reference to the immutable source
blob.  Archive validation is deliberately read-only: it opens the archive
through a stable, single-link handle, never extracts during validation and
does not create caches or recovery state.

Restore publishes a new *session* root.  It does not silently enrol that root
in a project's session registry and it never rewrites ``session_metadata``.
The operational fact that the copy came from an archive is recorded in a
hidden receipt adjacent to the restored root, outside the restored authority.
"""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import unicodedata
import uuid
from typing import Any, BinaryIO, Iterable, Iterator, Mapping, Sequence
import zipfile
import zlib

from cavity_tem_light_p1.errors import TransactionError, ValidationError
from cavity_tem_light_p1.identity import validate_canonical_uuid, validate_human_id
from cavity_tem_light_p1.path_safety import (
    PathSafetyError,
    is_reparse_or_link,
    plain_directory,
    plain_file,
    rename_directory_no_replace,
    rename_file_no_replace,
    stable_plain_bytes,
)

from .session_core import (
    SESSION_METADATA_FIELDS,
    SessionCore,
    snapshot_tree,
    validate_project,
)


ARCHIVE_PROFILE_ID = "CTL_SESSION_ARCHIVE_V1"
ARCHIVE_DESCRIPTOR_SCHEMA = "CTL_SESSION_ARCHIVE_DESCRIPTOR_V1"
SOURCE_REFERENCE_SCHEMA = "CTL_SOURCE_REFERENCE_V1"
RESTORE_RECEIPT_SCHEMA = "CTL_SESSION_ARCHIVE_RESTORE_RECEIPT_V1"

MAX_ENTRY_COUNT = 10_000
MAX_MEMBER_UNCOMPRESSED_BYTES = 2_147_483_648
MAX_TOTAL_UNCOMPRESSED_BYTES = 8_589_934_592
MAX_PATH_CHARACTERS = 240
MAX_PATH_DEPTH = 32

FIXED_ZIP_TIMESTAMP = (1980, 1, 1, 0, 0, 0)
FIXED_FILE_MODE = stat.S_IFREG | 0o644
MANDATORY_CONTROL_MEMBERS = frozenset(
    {
        "MANIFEST_SHA256.txt",
        "PACKAGE_TREE.txt",
        "archive_descriptor.json",
        "source_reference.json",
    }
)
DESCRIPTOR_FIELDS = frozenset(
    {
        "analysis_session_uid",
        "archive_id",
        "archive_profile_id",
        "created_at",
        "expanded_logical_bytes",
        "files",
        "project_uid",
        "schema",
        "source_reference",
        "uncompressed_physical_bytes",
    }
)
FILE_RECORD_FIELDS = frozenset({"bytes", "path", "sha256"})
SOURCE_REFERENCE_FIELDS = frozenset({"project_uid", "schema", "source_sha256"})
SHA256_RE = re.compile(r"^[0-9a-f]{64}$", re.ASCII)
RFC3339_Z_RE = re.compile(
    r"^[0-9]{4}-(?:0[1-9]|1[0-2])-(?:0[1-9]|[12][0-9]|3[01])T"
    r"(?:[01][0-9]|2[0-3]):[0-5][0-9]:[0-5][0-9](?:\.[0-9]{1,6})?Z$",
    re.ASCII,
)
WINDOWS_RESERVED = frozenset(
    {"CON", "PRN", "AUX", "NUL"}
    | {f"COM{number}" for number in range(1, 10)}
    | {f"LPT{number}" for number in range(1, 10)}
)
STANDARD_SESSION_DIRECTORIES = frozenset(
    {"working", "autosave", "journals", "recovery", "revisions", "runs"}
)
LEGACY_QUARANTINE_SESSION_RELATIVE = "recovery/legacy_quarantine"
LEGACY_QUARANTINE_PAYLOAD_PREFIX = f"payload/{LEGACY_QUARANTINE_SESSION_RELATIVE}/"


@dataclass(frozen=True)
class ArchiveFileRecord:
    path: str
    byte_size: int
    sha256: str


@dataclass(frozen=True)
class ArchiveValidation:
    archive_path: Path
    archive_sha256: str
    archive_bytes: int
    archive_root: str
    analysis_session_id: str
    analysis_session_uid: str
    project_uid: str
    source_sha256: str
    descriptor: Mapping[str, Any]
    payload_files: tuple[ArchiveFileRecord, ...]
    member_count: int
    result: str = "PASS"


@dataclass(frozen=True)
class ArchiveBuildResult:
    archive_path: Path
    archive_sha256: str
    archive_bytes: int
    archive_root: str
    analysis_session_uid: str
    source_tree_retained: bool
    validation_result: str = "PASS"


@dataclass(frozen=True)
class RestoreResult:
    session_root: Path
    receipt_path: Path
    archive_sha256: str
    analysis_session_uid: str
    source_sha256: str
    published: bool
    result: str


class _ObjectPairs(list):
    """Marker that keeps JSON objects distinct from arrays during parsing."""


def _fail(message: str, **details: Any) -> None:
    raise ValidationError(message, details=details)


def _require_sha256(value: Any, field: str) -> str:
    if not isinstance(value, str) or SHA256_RE.fullmatch(value) is None:
        _fail("invalid SHA-256", field=field, value=value)
    return value


def _require_nonnegative(value: Any, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        _fail("expected non-negative integer", field=field, value=value)
    return value


def _require_timestamp(value: Any, field: str = "created_at") -> str:
    if not isinstance(value, str) or RFC3339_Z_RE.fullmatch(value) is None:
        _fail("timestamp is not canonical RFC3339 UTC-Z", field=field)
    base = value[:-1].split(".", 1)[0]
    try:
        datetime.strptime(base, "%Y-%m-%dT%H:%M:%S")
    except ValueError as exc:
        raise ValidationError("timestamp is not a real calendar time", details={"field": field}) from exc
    fraction = value[:-1].partition(".")[2]
    if fraction and fraction.endswith("0"):
        _fail("timestamp has a redundant fractional zero", field=field)
    return value


def _check_unicode(value: str, *, field: str) -> str:
    if value != unicodedata.normalize("NFC", value):
        _fail("text is not NFC", field=field)
    if any(0xD800 <= ord(character) <= 0xDFFF for character in value):
        _fail("isolated Unicode surrogate is forbidden", field=field)
    return value


def _normalise_json(value: Any, *, path: str = "$") -> Any:
    if isinstance(value, _ObjectPairs):
        result: dict[str, Any] = {}
        exact: set[str] = set()
        for raw_key, raw_item in value:
            if raw_key in exact:
                _fail("duplicate JSON key", path=path, key=raw_key)
            exact.add(raw_key)
            key = _check_unicode(raw_key, field=f"{path}.<key>")
            if key in result:
                _fail("JSON keys collide after NFC normalization", path=path, key=key)
            result[key] = _normalise_json(raw_item, path=f"{path}.{key}")
        return result
    if isinstance(value, Mapping):
        result: dict[str, Any] = {}
        for raw_key, raw_item in value.items():
            if not isinstance(raw_key, str):
                _fail("JSON object key is not text", path=path)
            key = _check_unicode(raw_key, field=f"{path}.<key>")
            if key in result:
                _fail("JSON keys collide after NFC normalization", path=path, key=key)
            result[key] = _normalise_json(raw_item, path=f"{path}.{key}")
        return result
    if isinstance(value, list):
        return [_normalise_json(item, path=f"{path}[{index}]") for index, item in enumerate(value)]
    if isinstance(value, str):
        return _check_unicode(value, field=path)
    if value is None or isinstance(value, (bool, int)):
        return value
    _fail("unsupported JSON value", path=path, python_type=type(value).__name__)
    raise AssertionError("unreachable")


def _reject_json_number(token: str) -> None:
    _fail("non-integer JSON number is forbidden", token=token)


def _canonical_json_bytes(value: Mapping[str, Any]) -> bytes:
    normalised = _normalise_json(_ObjectPairs(value.items()))
    return (
        json.dumps(
            normalised,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        + b"\n"
    )


def _load_canonical_json(data: bytes, *, label: str) -> dict[str, Any]:
    if data.startswith(b"\xef\xbb\xbf") or b"\r" in data or b"\x00" in data:
        _fail("canonical JSON transport is invalid", label=label)
    try:
        text = data.decode("utf-8", errors="strict")
    except UnicodeDecodeError as exc:
        raise ValidationError("canonical JSON is not UTF-8", details={"label": label}) from exc
    try:
        parsed = json.loads(
            text,
            object_pairs_hook=_ObjectPairs,
            parse_float=_reject_json_number,
            parse_constant=_reject_json_number,
        )
    except ValidationError:
        raise
    except (json.JSONDecodeError, ValueError) as exc:
        raise ValidationError("canonical JSON is invalid", details={"label": label, "reason": str(exc)}) from exc
    value = _normalise_json(parsed)
    if not isinstance(value, dict) or _canonical_json_bytes(value) != data:
        _fail("JSON bytes are not canonical", label=label)
    return value


def _validate_portable_relative(value: Any, *, field: str = "path") -> str:
    if not isinstance(value, str) or not value:
        _fail("relative path is absent", field=field)
    _check_unicode(value, field=field)
    if (
        len(value) > MAX_PATH_CHARACTERS
        or "\\" in value
        or ":" in value
        or value.startswith("/")
        or "\x00" in value
    ):
        _fail("relative path is not portable", field=field, value=value)
    parts = value.split("/")
    if len(parts) > MAX_PATH_DEPTH or any(not part or part in {".", ".."} for part in parts):
        _fail("relative path contains unsafe components", field=field, value=value)
    for part in parts:
        if part.endswith((".", " ")) or part.split(".", 1)[0].upper() in WINDOWS_RESERVED:
            _fail("relative path has a Windows-reserved component", field=field, value=value)
        if any(ord(character) < 0x20 or ord(character) == 0x7F for character in part):
            _fail("relative path has a control codepoint", field=field, value=value)
    if PurePosixPath(value).as_posix() != value:
        _fail("relative path is not canonical", field=field, value=value)
    return value


def _archive_root_identity(root: str) -> tuple[str, str]:
    prefix = "CTL_SESSION_"
    if not root.startswith(prefix) or len(root) <= len(prefix) + 37 or root[-37] != "_":
        _fail("archive root does not match CTL_SESSION_<id>_<uid>", root=root)
    session_id = root[len(prefix) : -37]
    session_uid = root[-36:]
    validate_human_id(session_id, field="analysis_session_id")
    validate_canonical_uuid(session_uid)
    if root != f"CTL_SESSION_{session_id}_{session_uid}":
        _fail("archive root identity is not canonical", root=root)
    return session_id, session_uid


def _session_directory_matches_id(directory_name: str, session_id: str) -> bool:
    validate_human_id(session_id, field="analysis_session_id")
    preferred = f"SESSION_{session_id}"
    discriminator = hashlib.sha256(session_id.encode("utf-8")).hexdigest()[:12]
    return directory_name in {preferred, f"{preferred}~CASE_{discriminator}"}


def _stat_snapshot(info: os.stat_result) -> tuple[int, ...]:
    return (
        int(info.st_dev),
        int(info.st_ino),
        int(info.st_mode),
        int(info.st_nlink),
        int(info.st_size),
        int(info.st_mtime_ns),
        int(info.st_ctime_ns),
        int(getattr(info, "st_file_attributes", 0)),
        int(getattr(info, "st_reparse_tag", 0)),
    )


def _cross_handle_snapshot(snapshot: tuple[int, ...]) -> tuple[int, ...]:
    # CPython on Windows can expose the same NTFS change time differently via
    # stat and fstat.  It remains checked inside each observation domain.
    return snapshot[:6] + snapshot[7:]


@contextmanager
def _stable_archive_handle(raw: os.PathLike[str] | str) -> Iterator[tuple[BinaryIO, int]]:
    path = Path(raw)
    try:
        checked = plain_file(path, label="session archive", single_link=True)
        before_path = _stat_snapshot(os.stat(checked, follow_symlinks=False))
        handle = checked.open("rb")
        opened_before = _stat_snapshot(os.fstat(handle.fileno()))
        if _cross_handle_snapshot(before_path) != _cross_handle_snapshot(opened_before):
            handle.close()
            raise PathSafetyError("archive changed between path check and open")
    except PathSafetyError as exc:
        raise ValidationError("archive is absent, linked, reparsed or hardlinked", details={"reason": str(exc)}) from exc
    except OSError as exc:
        raise ValidationError("archive cannot be opened safely", details={"reason": str(exc)}) from exc
    pending_error: BaseException | None = None
    try:
        yield handle, before_path[4]
    except BaseException as exc:
        pending_error = exc
        raise
    finally:
        try:
            opened_after = _stat_snapshot(os.fstat(handle.fileno()))
            handle.close()
            checked_after = plain_file(path, label="session archive", single_link=True)
            after_path = _stat_snapshot(os.stat(checked_after, follow_symlinks=False))
            if (
                before_path != after_path
                or opened_before != opened_after
                or len(
                    {
                        _cross_handle_snapshot(item)
                        for item in (before_path, opened_before, opened_after, after_path)
                    }
                )
                != 1
            ):
                raise ValidationError("archive changed while it was validated")
        except BaseException:
            if pending_error is None:
                raise


def _hash_open_file(handle: BinaryIO, expected_size: int) -> str:
    handle.seek(0)
    digest = hashlib.sha256()
    measured = 0
    while True:
        block = handle.read(1024 * 1024)
        if not block:
            break
        measured += len(block)
        digest.update(block)
    if measured != expected_size:
        _fail("archive byte size changed during hashing", expected=expected_size, measured=measured)
    handle.seek(0)
    return digest.hexdigest()


def _validate_member_name(name: str) -> tuple[str, str]:
    if not isinstance(name, str) or not name or name.endswith("/") or "\\" in name:
        _fail("ZIP member path is not a regular portable file", member=name)
    _validate_portable_relative(name, field="zip_member")
    parts = name.split("/")
    if len(parts) < 2:
        _fail("ZIP member is outside the single archive root", member=name)
    root = parts[0]
    relative = "/".join(parts[1:])
    _archive_root_identity(root)
    _validate_portable_relative(relative, field="archive_relative_path")
    return root, relative


def _validate_zip_info(info: zipfile.ZipInfo) -> None:
    if info.orig_filename != info.filename:
        _fail("ZIP member name was truncated or rewritten", member=info.orig_filename)
    if info.compress_type != zipfile.ZIP_STORED or info.compress_size != info.file_size:
        _fail("ZIP member is compressed or has a non-unit ratio", member=info.filename)
    if info.file_size < 0 or info.file_size > MAX_MEMBER_UNCOMPRESSED_BYTES:
        _fail("ZIP member exceeds the contractual size limit", member=info.filename)
    if info.date_time != FIXED_ZIP_TIMESTAMP:
        _fail("ZIP member timestamp is not deterministic", member=info.filename)
    mode = (info.external_attr >> 16) & 0xFFFF
    if info.create_system != 3 or mode != FIXED_FILE_MODE or not stat.S_ISREG(mode):
        _fail("ZIP member is not mode 100644 regular data", member=info.filename, mode=oct(mode))
    if info.comment or info.internal_attr != 0:
        _fail("ZIP member carries undeclared metadata", member=info.filename)
    if info.extra:
        # The profile permits entries up to 2 GiB and an archive up to 8 GiB,
        # so the standard ZIP64 extension can be physically necessary.  No
        # timestamp, platform, ownership or application-specific extra field
        # is accepted.
        cursor = 0
        zip64_seen = False
        while cursor < len(info.extra):
            if cursor + 4 > len(info.extra):
                _fail("ZIP extra field header is truncated", member=info.filename)
            header_id = int.from_bytes(info.extra[cursor : cursor + 2], "little")
            field_size = int.from_bytes(info.extra[cursor + 2 : cursor + 4], "little")
            cursor += 4
            payload = info.extra[cursor : cursor + field_size]
            if len(payload) != field_size:
                _fail("ZIP extra field payload is truncated", member=info.filename)
            cursor += field_size
            if header_id != 0x0001 or zip64_seen or field_size not in {8, 16, 24, 28}:
                _fail("ZIP member carries a non-essential or malformed extra field", member=info.filename)
            zip64_seen = True
            values = [
                int.from_bytes(payload[offset : offset + 8], "little")
                for offset in range(0, field_size - (4 if field_size == 28 else 0), 8)
            ]
            if not values or not any(
                value in {info.file_size, info.compress_size, info.header_offset}
                for value in values
            ):
                _fail("ZIP64 extra field is not bound to a required 64-bit value", member=info.filename)
    if info.flag_bits & ~0x800:
        _fail("ZIP member carries encryption/data-descriptor/unknown flags", member=info.filename)
    if any(ord(character) > 0x7F for character in info.filename) and not (info.flag_bits & 0x800):
        _fail("non-ASCII ZIP name lacks the UTF-8 flag", member=info.filename)


def _read_member_bytes(
    archive: zipfile.ZipFile,
    info: zipfile.ZipInfo,
    *,
    maximum: int | None = None,
) -> bytes:
    limit = info.file_size if maximum is None else min(info.file_size, maximum)
    if maximum is not None and info.file_size > maximum:
        _fail("ZIP control member is implausibly large", member=info.filename, bytes=info.file_size)
    chunks: list[bytes] = []
    measured = 0
    crc = 0
    try:
        with archive.open(info, "r") as source:
            while True:
                block = source.read(min(1024 * 1024, limit - measured + 1))
                if not block:
                    break
                measured += len(block)
                if measured > limit:
                    _fail("ZIP member exceeded its declared limit while reading", member=info.filename)
                crc = zlib.crc32(block, crc)
                chunks.append(block)
    except (zipfile.BadZipFile, RuntimeError, OSError, EOFError) as exc:
        raise ValidationError("ZIP member failed CRC or structural validation", details={"member": info.filename}) from exc
    if measured != info.file_size or (crc & 0xFFFFFFFF) != info.CRC:
        _fail("ZIP member size or CRC differs from the central directory", member=info.filename)
    return b"".join(chunks)


def _digest_member(archive: zipfile.ZipFile, info: zipfile.ZipInfo) -> tuple[int, str]:
    digest = hashlib.sha256()
    measured = 0
    crc = 0
    try:
        with archive.open(info, "r") as source:
            while True:
                block = source.read(1024 * 1024)
                if not block:
                    break
                measured += len(block)
                if measured > info.file_size:
                    _fail("ZIP member exceeds its declared byte size", member=info.filename)
                digest.update(block)
                crc = zlib.crc32(block, crc)
    except (zipfile.BadZipFile, RuntimeError, OSError, EOFError) as exc:
        raise ValidationError("ZIP member failed CRC or structural validation", details={"member": info.filename}) from exc
    if measured != info.file_size or (crc & 0xFFFFFFFF) != info.CRC:
        _fail("ZIP member size or CRC differs from the central directory", member=info.filename)
    return measured, digest.hexdigest()


def _parse_manifest(data: bytes) -> dict[str, tuple[int, str]]:
    if data.startswith(b"\xef\xbb\xbf") or b"\r" in data or b"\x00" in data or not data.endswith(b"\n"):
        _fail("archive manifest transport is not UTF-8/LF")
    try:
        text = data.decode("utf-8", errors="strict")
    except UnicodeDecodeError as exc:
        raise ValidationError("archive manifest is not UTF-8") from exc
    records: dict[str, tuple[int, str]] = {}
    ordered: list[str] = []
    pattern = re.compile(r"^([0-9a-f]{64})  (0|[1-9][0-9]*)  (.+)$", re.ASCII)
    for line in text[:-1].split("\n"):
        match = pattern.fullmatch(line)
        if match is None:
            _fail("archive manifest line does not match the closed grammar", line=line)
        digest, size_text, path = match.groups()
        _validate_portable_relative(path, field="manifest.path")
        if path in records:
            _fail("archive manifest repeats a path", path=path)
        records[path] = (int(size_text), digest)
        ordered.append(path)
    if ordered != sorted(ordered):
        _fail("archive manifest is not lexicographically sorted")
    return records


def _parse_package_tree(data: bytes) -> tuple[str, ...]:
    if data.startswith(b"\xef\xbb\xbf") or b"\r" in data or b"\x00" in data or not data.endswith(b"\n"):
        _fail("package tree transport is not UTF-8/LF")
    try:
        text = data.decode("utf-8", errors="strict")
    except UnicodeDecodeError as exc:
        raise ValidationError("package tree is not UTF-8") from exc
    paths = tuple(text[:-1].split("\n"))
    if not paths or any(not path for path in paths):
        _fail("package tree is empty or has a blank record")
    for path in paths:
        _validate_portable_relative(path, field="package_tree.path")
    if list(paths) != sorted(paths) or len(paths) != len(set(paths)):
        _fail("package tree is unsorted or duplicated")
    return paths


def _quarantine_payload_records(
    records: Sequence[ArchiveFileRecord],
) -> tuple[ArchiveFileRecord, ...]:
    """Return the one permitted recovery payload, rejecting mixed recovery."""

    recovery_prefix = "payload/recovery/"
    recovery_records = tuple(
        record
        for record in records
        if record.path == "payload/recovery" or record.path.startswith(recovery_prefix)
    )
    quarantine_records = tuple(
        record
        for record in recovery_records
        if record.path.startswith(LEGACY_QUARANTINE_PAYLOAD_PREFIX)
    )
    if len(recovery_records) != len(quarantine_records):
        _fail("archive contains recovery material outside legacy_quarantine")
    return quarantine_records


def _load_quarantine_json(data: bytes, *, label: str) -> dict[str, Any]:
    """Parse the same canonical JSON profile used by migration evidence."""

    from cavity_tem_light_p1.canonical_json import (  # local: no archive/migration cycle
        canonical_json_bytes,
        loads_canonical_json,
    )

    value = loads_canonical_json(data)
    if not isinstance(value, dict) or canonical_json_bytes(value) != data:
        _fail("embedded legacy quarantine JSON is not canonical", label=label)
    return value


def _validate_embedded_legacy_quarantine(
    archive: zipfile.ZipFile,
    info_by_relative: Mapping[str, zipfile.ZipInfo],
    payload_records: Sequence[ArchiveFileRecord],
    *,
    analysis_session_id: str,
    analysis_session_uid: str,
    project_uid: str,
    source_sha256: str,
) -> dict[str, Any] | None:
    """Validate a session-owned quarantine directly from ZIP bytes.

    Archive validation remains read-only: only the small JSON/text controls are
    materialised.  Legacy payload members are bound through the already checked
    archive descriptor, outer manifest and their inner SHA-256 manifests.
    """

    quarantine_records = _quarantine_payload_records(payload_records)
    if not quarantine_records:
        return None

    try:
        from . import migration as migration_adapter  # local: migration imports no archive code
    except ImportError as exc:  # pragma: no cover - package assembly guard
        raise ValidationError(
            "legacy quarantine validator is not installed in the archive package"
        ) from exc

    record_by_relative: dict[str, ArchiveFileRecord] = {}
    for record in quarantine_records:
        relative = record.path[len(LEGACY_QUARANTINE_PAYLOAD_PREFIX) :]
        _validate_portable_relative(relative, field="legacy_quarantine.path")
        if relative in record_by_relative:
            _fail("legacy quarantine archive path is duplicated", path=relative)
        record_by_relative[relative] = record

    root_manifest_name = "MANIFEST_SHA256.txt"
    required_root_controls = {
        root_manifest_name,
        "MIGRATION_STATUS.json",
        "R9_LEGACY_CONFLICTS.json",
        "R9_LEGACY_QUARANTINE_REPORT.md",
    }
    if not required_root_controls.issubset(record_by_relative):
        _fail(
            "embedded legacy quarantine control inventory is incomplete",
            missing=sorted(required_root_controls - set(record_by_relative)),
        )

    # This is a materialisation guard derived from the contractual entry bound,
    # not an additional archive-profile limit.
    control_limit = min(MAX_MEMBER_UNCOMPRESSED_BYTES, MAX_ENTRY_COUNT * 16_384)

    def control_bytes(relative: str, *, maximum: int = control_limit) -> bytes:
        archive_relative = LEGACY_QUARANTINE_PAYLOAD_PREFIX + relative
        info = info_by_relative.get(archive_relative)
        if info is None:
            _fail("embedded legacy quarantine control is absent", path=relative)
        return _read_member_bytes(archive, info, maximum=maximum)

    root_manifest = _parse_manifest(
        control_bytes(root_manifest_name, maximum=MAX_ENTRY_COUNT * 512)
    )
    observed_without_root = {
        relative: (record.byte_size, record.sha256)
        for relative, record in record_by_relative.items()
        if relative != root_manifest_name
    }
    if root_manifest != observed_without_root:
        _fail("embedded legacy quarantine root manifest is not the exact inventory")

    metadata_path = "payload/session_metadata.json"
    metadata_info = info_by_relative.get(metadata_path)
    if metadata_info is None:
        _fail("archive with legacy quarantine lacks session metadata")
    metadata = _load_canonical_json(
        _read_member_bytes(archive, metadata_info, maximum=64 * 1024),
        label=metadata_path,
    )
    if (
        set(metadata) != SESSION_METADATA_FIELDS
        or metadata.get("schema") != "CTL_SESSION_METADATA_JSON_V1"
        or metadata.get("analysis_session_id") != analysis_session_id
        or metadata.get("analysis_session_uid") != analysis_session_uid
        or metadata.get("project_uid") != project_uid
        or metadata.get("source_sha256") != source_sha256
        or metadata.get("origin_type") != "MIGRATED_LEGACY_BRIDGE"
    ):
        _fail("legacy quarantine archive parent session binding is invalid")
    image_uid = validate_canonical_uuid(metadata.get("image_uid"))
    image_id = validate_human_id(metadata.get("image_id"), field="image_id")

    status = _load_quarantine_json(
        control_bytes("MIGRATION_STATUS.json"),
        label="legacy_quarantine/MIGRATION_STATUS.json",
    )
    status_fields = {
        "analysis_session_uid",
        "authority_role",
        "automatic_identity_repair",
        "canonical_session_role",
        "editable",
        "editable_baseline_revision",
        "idempotency_key",
        "image_id",
        "image_uid",
        "legacy_bytes_preserved",
        "legacy_revision_chain",
        "migration_id",
        "migration_status",
        "object_level_migration_complete",
        "policy_id",
        "project_uid",
        "quarantined_revision_count",
        "quarantined_revisions",
        "reconciliation_required",
        "run_input_role",
        "schema",
        "scientific_equivalence_to_latest_legacy_revision",
        "source_sha256",
        "statistics_role",
        "valid_revision_prefix",
    }
    parent_binding = {
        "analysis_session_uid": analysis_session_uid,
        "image_id": image_id,
        "image_uid": image_uid,
        "project_uid": project_uid,
        "source_sha256": source_sha256,
    }
    if (
        set(status) != status_fields
        or status.get("schema") != migration_adapter.QUARANTINE_STATUS_SCHEMA
        or status.get("policy_id") != migration_adapter.QUARANTINE_POLICY_ID
        or status.get("migration_status") != migration_adapter.PARTIAL_MIGRATION_STATUS
        or status.get("authority_role") != "LEGACY_EVIDENCE_ONLY"
        or status.get("editable") is not False
        or status.get("statistics_role") != "FORBIDDEN"
        or status.get("run_input_role") != "FORBIDDEN"
        or status.get("canonical_session_role") != "FORBIDDEN"
        or status.get("automatic_identity_repair") is not False
        or status.get("legacy_bytes_preserved") is not True
        or status.get("object_level_migration_complete") is not False
        or status.get("scientific_equivalence_to_latest_legacy_revision") is not False
        or status.get("reconciliation_required") is not True
        or any(status.get(field) != value for field, value in parent_binding.items())
    ):
        _fail("embedded legacy quarantine status semantics are invalid")
    _require_sha256(status.get("idempotency_key"), "legacy_quarantine.idempotency_key")
    validate_human_id(status.get("migration_id"), field="migration_id")

    valid_prefix = status.get("valid_revision_prefix")
    full_chain = status.get("legacy_revision_chain")
    quarantined_ids = status.get("quarantined_revisions")
    quarantined_count = status.get("quarantined_revision_count")
    if (
        not isinstance(valid_prefix, list)
        or not valid_prefix
        or not isinstance(full_chain, list)
        or not isinstance(quarantined_ids, list)
        or not quarantined_ids
        or full_chain[: len(valid_prefix)] != valid_prefix
        or full_chain[len(valid_prefix) :] != quarantined_ids
        or status.get("editable_baseline_revision") != valid_prefix[-1]
        or isinstance(quarantined_count, bool)
        or not isinstance(quarantined_count, int)
        or quarantined_count != len(quarantined_ids)
    ):
        _fail("embedded legacy quarantine prefix/tail binding is invalid")
    for revision_id in full_chain:
        validate_human_id(revision_id, field="legacy revision_id")
    if len(full_chain) != len(set(full_chain)):
        _fail("embedded legacy revision chain repeats an identity")

    conflicts = _load_quarantine_json(
        control_bytes("R9_LEGACY_CONFLICTS.json"),
        label="legacy_quarantine/R9_LEGACY_CONFLICTS.json",
    )
    conflict_fields = {
        "analysis_session_uid",
        "automatic_mapping_proposed",
        "editable_baseline_revision",
        "image_id",
        "image_uid",
        "migration_id",
        "policy_id",
        "project_uid",
        "quarantined_revisions",
        "schema",
        "selected_migration_action",
        "source_sha256",
    }
    conflict_rows = conflicts.get("quarantined_revisions")
    if (
        set(conflicts) != conflict_fields
        or conflicts.get("schema") != migration_adapter.QUARANTINE_CONFLICTS_SCHEMA
        or conflicts.get("policy_id") != migration_adapter.QUARANTINE_POLICY_ID
        or conflicts.get("migration_id") != status["migration_id"]
        or conflicts.get("editable_baseline_revision") != valid_prefix[-1]
        or conflicts.get("automatic_mapping_proposed") is not False
        or conflicts.get("selected_migration_action") != "QUARANTINE_NO_CONVERSION"
        or any(conflicts.get(field) != value for field, value in parent_binding.items())
        or not isinstance(conflict_rows, list)
        or [row.get("revision_id") if isinstance(row, Mapping) else None for row in conflict_rows]
        != quarantined_ids
    ):
        _fail("embedded legacy quarantine conflict report binding is invalid")

    conflict_by_revision = {
        row["revision_id"]: row for row in conflict_rows if isinstance(row, Mapping)
    }
    allowed_root_controls = required_root_controls
    for relative in record_by_relative:
        if relative in allowed_root_controls:
            continue
        if not any(relative.startswith(f"{revision_id}/") for revision_id in quarantined_ids):
            _fail("embedded legacy quarantine has an undeclared root entry", path=relative)

    for revision_id in quarantined_ids:
        prefix = f"{revision_id}/"
        revision_records = {
            relative[len(prefix) :]: record
            for relative, record in record_by_relative.items()
            if relative.startswith(prefix)
        }
        required_revision_controls = {
            "CONFLICT_REPORT.json",
            "MANIFEST_SHA256.txt",
            "QUARANTINE_MANIFEST.json",
        }
        if not required_revision_controls.issubset(revision_records):
            _fail(
                "embedded quarantined revision control inventory is incomplete",
                revision_id=revision_id,
            )
        revision_manifest = _parse_manifest(
            control_bytes(f"{revision_id}/MANIFEST_SHA256.txt", maximum=MAX_ENTRY_COUNT * 512)
        )
        revision_observed = {
            relative: (record.byte_size, record.sha256)
            for relative, record in revision_records.items()
            if relative != "MANIFEST_SHA256.txt"
        }
        if revision_manifest != revision_observed:
            _fail(
                "embedded quarantined revision manifest is not the exact inventory",
                revision_id=revision_id,
            )

        conflict_report = _load_quarantine_json(
            control_bytes(f"{revision_id}/CONFLICT_REPORT.json"),
            label=f"legacy_quarantine/{revision_id}/CONFLICT_REPORT.json",
        )
        if conflict_report != conflict_by_revision.get(revision_id):
            _fail("quarantined revision conflict reports disagree", revision_id=revision_id)

        quarantine_manifest = _load_quarantine_json(
            control_bytes(f"{revision_id}/QUARANTINE_MANIFEST.json"),
            label=f"legacy_quarantine/{revision_id}/QUARANTINE_MANIFEST.json",
        )
        quarantine_manifest_fields = {
            "analysis_session_uid",
            "authority_role",
            "canonical_session_role",
            "conversion_status",
            "editable",
            "image_uid",
            "migration_id",
            "payload_files",
            "project_uid",
            "reconciliation_required",
            "revision_id",
            "run_input_role",
            "schema",
            "selected_migration_action",
            "source_sha256",
            "statistics_role",
        }
        if (
            set(quarantine_manifest) != quarantine_manifest_fields
            or quarantine_manifest.get("schema")
            != migration_adapter.QUARANTINE_MANIFEST_SCHEMA
            or quarantine_manifest.get("revision_id") != revision_id
            or quarantine_manifest.get("authority_role") != "LEGACY_EVIDENCE_ONLY"
            or quarantine_manifest.get("conversion_status")
            != "NOT_CONVERTED_IDENTITY_CONFLICT"
            or quarantine_manifest.get("editable") is not False
            or quarantine_manifest.get("migration_id") != status["migration_id"]
            or quarantine_manifest.get("canonical_session_role") != "FORBIDDEN"
            or quarantine_manifest.get("run_input_role") != "FORBIDDEN"
            or quarantine_manifest.get("statistics_role") != "FORBIDDEN"
            or quarantine_manifest.get("reconciliation_required") is not True
            or quarantine_manifest.get("selected_migration_action")
            != "QUARANTINE_NO_CONVERSION"
            or any(
                quarantine_manifest.get(field) != value
                for field, value in parent_binding.items()
                if field != "image_id"
            )
        ):
            _fail("embedded quarantined revision semantics are invalid", revision_id=revision_id)

        payload_rows = quarantine_manifest.get("payload_files")
        if not isinstance(payload_rows, list):
            _fail("embedded quarantined revision payload inventory is not an array")
        expected_payload: dict[str, tuple[int, str]] = {}
        ordered_payload_paths: list[str] = []
        for index, row in enumerate(payload_rows):
            if not isinstance(row, Mapping) or set(row) != {"bytes", "path", "sha256"}:
                _fail(
                    "embedded quarantined payload record inventory is invalid",
                    revision_id=revision_id,
                    index=index,
                )
            path = _validate_portable_relative(
                row["path"], field=f"quarantine.payload_files[{index}].path"
            )
            if path in expected_payload:
                _fail("embedded quarantined payload path is duplicated", path=path)
            expected_payload[f"payload/{path}"] = (
                _require_nonnegative(row["bytes"], f"quarantine.payload_files[{index}].bytes"),
                _require_sha256(row["sha256"], f"quarantine.payload_files[{index}].sha256"),
            )
            ordered_payload_paths.append(path)
        if ordered_payload_paths != sorted(ordered_payload_paths):
            _fail("embedded quarantined payload inventory is not sorted")
        observed_payload = {
            relative: measured_value
            for relative, measured_value in revision_observed.items()
            if relative.startswith("payload/")
        }
        if expected_payload != observed_payload:
            _fail("embedded quarantined legacy payload is not byte-exact")
        allowed_revision_files = {
            "CONFLICT_REPORT.json",
            "QUARANTINE_MANIFEST.json",
            *expected_payload,
        }
        if set(revision_observed) != allowed_revision_files:
            _fail(
                "embedded quarantined revision contains an undeclared file",
                revision_id=revision_id,
            )

    return {
        "analysis_session_uid": analysis_session_uid,
        "migration_id": status["migration_id"],
        "quarantined_revisions": tuple(quarantined_ids),
        "root_manifest_sha256": record_by_relative[root_manifest_name].sha256,
    }


def _validate_descriptor(
    descriptor_data: bytes,
    source_reference_data: bytes,
    *,
    root_session_uid: str,
    measured: Mapping[str, tuple[int, str]],
    relative_names: Sequence[str],
) -> tuple[dict[str, Any], tuple[ArchiveFileRecord, ...]]:
    descriptor = _load_canonical_json(descriptor_data, label="archive_descriptor.json")
    if set(descriptor) != DESCRIPTOR_FIELDS:
        _fail("archive descriptor field inventory is not closed")
    if descriptor["schema"] != ARCHIVE_DESCRIPTOR_SCHEMA or descriptor["archive_profile_id"] != ARCHIVE_PROFILE_ID:
        _fail("archive descriptor schema/profile identity is invalid")
    validate_human_id(descriptor["archive_id"], field="archive_id")
    _require_timestamp(descriptor["created_at"])
    descriptor_uid = validate_canonical_uuid(descriptor["analysis_session_uid"])
    project_uid = validate_canonical_uuid(descriptor["project_uid"])
    if descriptor_uid != root_session_uid:
        _fail("archive root/session descriptor UID mismatch")

    source_reference = _load_canonical_json(source_reference_data, label="source_reference.json")
    if set(source_reference) != SOURCE_REFERENCE_FIELDS or source_reference["schema"] != SOURCE_REFERENCE_SCHEMA:
        _fail("source reference field inventory/schema is invalid")
    validate_canonical_uuid(source_reference["project_uid"])
    _require_sha256(source_reference["source_sha256"], "source_reference.source_sha256")
    expected_nested_reference = {
        "project_uid": source_reference["project_uid"],
        "source_sha256": source_reference["source_sha256"],
    }
    if descriptor["source_reference"] != expected_nested_reference:
        _fail("descriptor/source_reference bytes are not bound exactly")
    if source_reference["project_uid"] != project_uid:
        _fail("archive project/source-reference project mismatch")

    raw_files = descriptor["files"]
    if not isinstance(raw_files, list):
        _fail("descriptor files is not an array")
    records: list[ArchiveFileRecord] = []
    ordered_paths: list[str] = []
    for index, raw_record in enumerate(raw_files):
        if not isinstance(raw_record, dict) or set(raw_record) != FILE_RECORD_FIELDS:
            _fail("descriptor file record inventory is invalid", index=index)
        path = _validate_portable_relative(raw_record["path"], field=f"files[{index}].path")
        byte_size = _require_nonnegative(raw_record["bytes"], f"files[{index}].bytes")
        digest = _require_sha256(raw_record["sha256"], f"files[{index}].sha256")
        if path in MANDATORY_CONTROL_MEMBERS - {"source_reference.json"}:
            _fail("descriptor files illegally includes a control member", path=path)
        records.append(ArchiveFileRecord(path, byte_size, digest))
        ordered_paths.append(path)
    if ordered_paths != sorted(ordered_paths) or len(ordered_paths) != len(set(ordered_paths)):
        _fail("descriptor files is unsorted or duplicated")

    expected_record_paths = set(relative_names) - {
        "MANIFEST_SHA256.txt",
        "PACKAGE_TREE.txt",
        "archive_descriptor.json",
    }
    if set(ordered_paths) != expected_record_paths:
        _fail(
            "descriptor files is not the exact closed payload/source inventory",
            missing=sorted(expected_record_paths - set(ordered_paths)),
            extra=sorted(set(ordered_paths) - expected_record_paths),
        )
    record_by_path = {record.path: record for record in records}
    for path, record in record_by_path.items():
        if measured.get(path) != (record.byte_size, record.sha256):
            _fail("descriptor file record differs from physical bytes", path=path)
    payload_records = tuple(record for record in records if record.path.startswith("payload/"))
    if not payload_records or "payload/session_metadata.json" not in record_by_path:
        _fail("archive lacks the required session metadata payload")
    if any(
        path == "payload/source.bin"
        or path.endswith("/source.bin")
        or "sources/blobs" in PurePosixPath(path).as_posix()
        for path in record_by_path
    ):
        _fail("archive embeds a source blob instead of a source reference")
    expanded = sum(record.byte_size for record in payload_records)
    physical = expanded + record_by_path["source_reference.json"].byte_size
    if _require_nonnegative(descriptor["expanded_logical_bytes"], "expanded_logical_bytes") != expanded:
        _fail("expanded_logical_bytes differs from payload bytes")
    if _require_nonnegative(descriptor["uncompressed_physical_bytes"], "uncompressed_physical_bytes") != physical:
        _fail("uncompressed_physical_bytes differs from payload plus source reference")
    return descriptor, payload_records


def _validate_archive_from_handle(
    handle: BinaryIO,
    archive_size: int,
    archive_path: Path,
) -> ArchiveValidation:
    archive_sha = _hash_open_file(handle, archive_size)
    try:
        with zipfile.ZipFile(handle, "r") as archive:
            if archive.comment != b"":
                _fail("ZIP archive comment must be empty")
            infos = archive.infolist()
            if not infos or len(infos) > MAX_ENTRY_COUNT:
                _fail("ZIP entry count is outside the contractual limits", count=len(infos))
            names: list[str] = []
            relative_names: list[str] = []
            roots: set[str] = set()
            collision_keys: set[str] = set()
            total = 0
            info_by_relative: dict[str, zipfile.ZipInfo] = {}
            for info in infos:
                root, relative = _validate_member_name(info.filename)
                _validate_zip_info(info)
                collision_key = unicodedata.normalize("NFC", info.filename).casefold()
                if info.filename in names:
                    _fail("ZIP contains an exact duplicate member", member=info.filename)
                if collision_key in collision_keys:
                    _fail("ZIP contains a case/NFC member collision", member=info.filename)
                if relative in info_by_relative:
                    _fail("ZIP relative member name is duplicated", member=relative)
                names.append(info.filename)
                relative_names.append(relative)
                roots.add(root)
                collision_keys.add(collision_key)
                info_by_relative[relative] = info
                total += info.file_size
                if total > MAX_TOTAL_UNCOMPRESSED_BYTES:
                    _fail("ZIP total uncompressed bytes exceed the contractual limit")
            if len(roots) != 1:
                _fail("ZIP does not contain exactly one archive root", roots=sorted(roots))
            root = next(iter(roots))
            session_id, session_uid = _archive_root_identity(root)
            if set(MANDATORY_CONTROL_MEMBERS) - set(relative_names):
                _fail(
                    "ZIP mandatory control inventory is incomplete",
                    missing=sorted(set(MANDATORY_CONTROL_MEMBERS) - set(relative_names)),
                )

            # These bounds are derived from entry/path limits, not additional
            # archive-profile limits.  They prevent malformed controls from
            # being materialised as multi-gigabyte Python objects.
            manifest_limit = MAX_ENTRY_COUNT * (64 + 2 + 10 + 2 + MAX_PATH_CHARACTERS + 1)
            tree_limit = MAX_ENTRY_COUNT * (MAX_PATH_CHARACTERS + 1)
            descriptor_limit = MAX_ENTRY_COUNT * 512 + 16_384
            manifest_data = _read_member_bytes(
                archive, info_by_relative["MANIFEST_SHA256.txt"], maximum=manifest_limit
            )
            tree_data = _read_member_bytes(
                archive, info_by_relative["PACKAGE_TREE.txt"], maximum=tree_limit
            )
            descriptor_data = _read_member_bytes(
                archive, info_by_relative["archive_descriptor.json"], maximum=descriptor_limit
            )
            source_reference_data = _read_member_bytes(
                archive, info_by_relative["source_reference.json"], maximum=16_384
            )

            manifest = _parse_manifest(manifest_data)
            package_tree = _parse_package_tree(tree_data)
            expected_tree = tuple(sorted(relative_names))
            if package_tree != expected_tree:
                _fail("PACKAGE_TREE.txt is not the exact archive inventory")
            expected_manifest_paths = set(relative_names) - {"MANIFEST_SHA256.txt"}
            if set(manifest) != expected_manifest_paths:
                _fail(
                    "manifest is not the exact non-self archive inventory",
                    missing=sorted(expected_manifest_paths - set(manifest)),
                    extra=sorted(set(manifest) - expected_manifest_paths),
                )

            measured: dict[str, tuple[int, str]] = {}
            for relative in sorted(relative_names):
                size, digest = _digest_member(archive, info_by_relative[relative])
                measured[relative] = (size, digest)
                if relative != "MANIFEST_SHA256.txt" and manifest[relative] != (size, digest):
                    _fail("manifest record differs from physical bytes", path=relative)
            descriptor, payload_records = _validate_descriptor(
                descriptor_data,
                source_reference_data,
                root_session_uid=session_uid,
                measured=measured,
                relative_names=relative_names,
            )
            _validate_embedded_legacy_quarantine(
                archive,
                info_by_relative,
                payload_records,
                analysis_session_id=session_id,
                analysis_session_uid=session_uid,
                project_uid=descriptor["project_uid"],
                source_sha256=descriptor["source_reference"]["source_sha256"],
            )
    except ValidationError:
        raise
    except (zipfile.BadZipFile, RuntimeError, NotImplementedError, OSError, EOFError) as exc:
        raise ValidationError("archive is not a structurally valid CTL ZIP", details={"reason": str(exc)}) from exc

    return ArchiveValidation(
        archive_path=archive_path,
        archive_sha256=archive_sha,
        archive_bytes=archive_size,
        archive_root=root,
        analysis_session_id=session_id,
        analysis_session_uid=session_uid,
        project_uid=descriptor["project_uid"],
        source_sha256=descriptor["source_reference"]["source_sha256"],
        descriptor=descriptor,
        payload_files=payload_records,
        member_count=len(infos),
    )


def validate_session_archive(archive_path: os.PathLike[str] | str) -> ArchiveValidation:
    """Validate one archive without writing or extracting any byte."""

    path = Path(archive_path)
    with _stable_archive_handle(path) as (handle, archive_size):
        return _validate_archive_from_handle(handle, archive_size, path)


def _excluded_operational_path(parts: Sequence[str]) -> bool:
    if any(".partial." in part or part.endswith(".partial") for part in parts):
        return True
    if any(part in {"autosave", "journals", "recovery"} for part in parts):
        return True
    name = parts[-1] if parts else ""
    return (
        name.startswith(".")
        or name.endswith(".transaction.json")
        or name.endswith(".journal.json")
        or ".backup." in name
        or ".quarantine" in name
        or name.endswith(".tmp")
    )


def _safe_tree_inventory(
    root: Path,
    *,
    include_operational: bool,
    capture_bytes: bool,
) -> tuple[dict[str, str], dict[str, bytes]]:
    """Return a safe closed tree snapshot and optionally stable file bytes."""

    try:
        plain_directory(root, label="expanded session root")
    except PathSafetyError as exc:
        raise ValidationError("expanded session root is unsafe", details={"reason": str(exc)}) from exc
    snapshot: dict[str, str] = {".": "DIRECTORY"}
    payload: dict[str, bytes] = {}
    collision_keys: set[str] = set()
    pending = [root]
    while pending:
        directory = pending.pop()
        try:
            entries = list(os.scandir(directory))
        except OSError as exc:
            raise ValidationError("expanded session directory cannot be enumerated", details={"path": str(directory)}) from exc
        for entry in sorted(entries, key=lambda item: item.name):
            path = Path(entry.path)
            relative = path.relative_to(root).as_posix()
            parts = tuple(relative.split("/"))
            _validate_portable_relative(relative, field="expanded_session_path")
            collision_key = unicodedata.normalize("NFC", relative).casefold()
            if collision_key in collision_keys:
                _fail("expanded session has a case/NFC collision", relative_path=relative)
            collision_keys.add(collision_key)
            if not include_operational and _excluded_operational_path(parts):
                continue
            try:
                if is_reparse_or_link(path):
                    raise PathSafetyError("link/reparse point")
                info = os.stat(entry.path, follow_symlinks=False)
                if stat.S_ISDIR(info.st_mode):
                    plain_directory(path, label="expanded session directory")
                    snapshot[relative] = "DIRECTORY"
                    pending.append(path)
                elif stat.S_ISREG(info.st_mode):
                    if int(info.st_nlink) != 1:
                        raise PathSafetyError(f"hardlink count is {info.st_nlink}")
                    data = stable_plain_bytes(path, label="expanded session file")
                    snapshot[relative] = f"FILE:{len(data)}:{hashlib.sha256(data).hexdigest()}"
                    if capture_bytes:
                        payload[relative] = data
                else:
                    raise PathSafetyError("special filesystem entry")
            except PathSafetyError as exc:
                raise ValidationError(
                    "expanded session contains a linked, reparsed, hardlinked or special entry",
                    details={"relative_path": relative, "reason": str(exc)},
                ) from exc
    return snapshot, payload


def _validate_session_legacy_quarantine(session_root: Path) -> dict[str, Any]:
    """Use the migration adapter's canonical filesystem validator lazily."""

    try:
        from .migration import validate_legacy_quarantine
    except ImportError as exc:  # pragma: no cover - package assembly guard
        raise ValidationError(
            "legacy quarantine validator is not installed in the archive package"
        ) from exc

    return validate_legacy_quarantine(session_root)


def _zip_info(name: str) -> zipfile.ZipInfo:
    info = zipfile.ZipInfo(name, date_time=FIXED_ZIP_TIMESTAMP)
    info.compress_type = zipfile.ZIP_STORED
    info.create_system = 3
    info.external_attr = FIXED_FILE_MODE << 16
    info.extra = b""
    info.comment = b""
    info.internal_attr = 0
    return info


def _fsync_directory(path: Path) -> None:
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
    try:
        descriptor = os.open(str(path), flags)
    except (OSError, AttributeError):
        return
    try:
        os.fsync(descriptor)
    except OSError:
        pass
    finally:
        os.close(descriptor)


def _write_new_file(path: Path, data: bytes) -> None:
    try:
        with path.open("xb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        _fsync_directory(path.parent)
        observed = stable_plain_bytes(path, label="new archive transaction file")
    except PathSafetyError as exc:
        raise TransactionError("new file failed path-safety verification", details={"path": str(path)}) from exc
    if observed != data:
        raise TransactionError("new file failed post-write verification", details={"path": str(path)})


def _write_archive(path: Path, root: str, members: Mapping[str, bytes]) -> None:
    with path.open("xb") as raw:
        with zipfile.ZipFile(raw, "w", compression=zipfile.ZIP_STORED, allowZip64=True) as archive:
            archive.comment = b""
            for relative, data in sorted(members.items()):
                archive.writestr(_zip_info(f"{root}/{relative}"), data)
        raw.flush()
        os.fsync(raw.fileno())
    _fsync_directory(path.parent)


def build_session_archive(
    source_project_root: os.PathLike[str] | str,
    *,
    image_uid: str,
    analysis_session_uid: str,
    archive_path: os.PathLike[str] | str,
    archive_id: str,
    created_at: str,
) -> ArchiveBuildResult:
    """Build and publish one deterministic archive without deleting expanded data."""

    source_root = Path(source_project_root)
    validate_project(source_root)
    core = SessionCore(source_root)
    session_uid = validate_canonical_uuid(analysis_session_uid)
    record = core.session_by_uid(image_uid, session_uid)
    metadata = core._metadata(record.session_root)
    binding = core._binding(image_uid)
    if metadata["source_sha256"] != binding["source_sha256"]:
        _fail("session/source registry binding mismatch")
    validate_human_id(archive_id, field="archive_id")
    timestamp = _require_timestamp(created_at)
    archive_root = f"CTL_SESSION_{record.analysis_session_id}_{record.analysis_session_uid}"
    target = Path(archive_path)
    if not target.is_absolute():
        _fail("archive path must be absolute", path=str(target))
    if target.name != f"{archive_root}.zip":
        _fail("archive file name does not match the physical profile", expected=f"{archive_root}.zip")
    try:
        plain_directory(target.parent, label="archive destination directory")
    except PathSafetyError as exc:
        raise ValidationError("archive destination directory is unsafe", details={"reason": str(exc)}) from exc
    if target.exists() or target.is_symlink():
        raise TransactionError("archive destination already exists", details={"path": str(target)})

    expanded_before, _ = _safe_tree_inventory(
        record.session_root, include_operational=True, capture_bytes=False
    )
    _authority_snapshot, session_files = _safe_tree_inventory(
        record.session_root, include_operational=False, capture_bytes=True
    )
    quarantine_root = record.session_root / PurePosixPath(
        LEGACY_QUARANTINE_SESSION_RELATIVE
    )
    quarantine_before: dict[str, Any] | None = None
    if quarantine_root.exists() or quarantine_root.is_symlink():
        quarantine_before = _validate_session_legacy_quarantine(record.session_root)
        _quarantine_snapshot, quarantine_files = _safe_tree_inventory(
            quarantine_root,
            include_operational=True,
            capture_bytes=True,
        )
        if not quarantine_files:
            _fail("validated legacy quarantine has no files")
        expected_quarantine_paths = {".", *quarantine_files}
        for relative in quarantine_files:
            parent = PurePosixPath(relative).parent
            while parent.as_posix() != ".":
                expected_quarantine_paths.add(parent.as_posix())
                parent = parent.parent
        if set(_quarantine_snapshot) != expected_quarantine_paths:
            _fail(
                "legacy quarantine contains an empty or unmanifested directory",
                extra=sorted(set(_quarantine_snapshot) - expected_quarantine_paths),
            )
        for relative, data in quarantine_files.items():
            session_relative = f"{LEGACY_QUARANTINE_SESSION_RELATIVE}/{relative}"
            if session_relative in session_files:
                _fail("legacy quarantine collides with authoritative session payload")
            session_files[session_relative] = data
    payloads = {f"payload/{relative}": data for relative, data in session_files.items()}
    if "payload/session_metadata.json" not in payloads:
        _fail("expanded session lacks session_metadata.json")
    source_reference = {
        "project_uid": core.project_uid,
        "schema": SOURCE_REFERENCE_SCHEMA,
        "source_sha256": binding["source_sha256"],
    }
    source_reference_bytes = _canonical_json_bytes(source_reference)
    file_data: dict[str, bytes] = dict(payloads)
    file_data["source_reference.json"] = source_reference_bytes
    if len(file_data) + 3 > MAX_ENTRY_COUNT:
        _fail("archive entry count exceeds the contractual limit")
    for relative, data in file_data.items():
        member_name = f"{archive_root}/{relative}"
        _validate_portable_relative(member_name, field="archive_member")
        if len(data) > MAX_MEMBER_UNCOMPRESSED_BYTES:
            _fail("archive payload member exceeds the contractual limit", path=relative)
    uncompressed_total = sum(len(data) for data in file_data.values())
    if uncompressed_total > MAX_TOTAL_UNCOMPRESSED_BYTES:
        _fail("archive payload exceeds the contractual total-byte limit")

    records = [
        {"bytes": len(data), "path": relative, "sha256": hashlib.sha256(data).hexdigest()}
        for relative, data in sorted(file_data.items())
    ]
    descriptor = {
        "analysis_session_uid": record.analysis_session_uid,
        "archive_id": archive_id,
        "archive_profile_id": ARCHIVE_PROFILE_ID,
        "created_at": timestamp,
        "expanded_logical_bytes": sum(len(data) for data in payloads.values()),
        "files": records,
        "project_uid": core.project_uid,
        "schema": ARCHIVE_DESCRIPTOR_SCHEMA,
        "source_reference": {
            "project_uid": core.project_uid,
            "source_sha256": binding["source_sha256"],
        },
        "uncompressed_physical_bytes": uncompressed_total,
    }
    members: dict[str, bytes] = dict(file_data)
    members["archive_descriptor.json"] = _canonical_json_bytes(descriptor)
    all_names = sorted((*members, "MANIFEST_SHA256.txt", "PACKAGE_TREE.txt"))
    members["PACKAGE_TREE.txt"] = ("\n".join(all_names) + "\n").encode("utf-8")
    members["MANIFEST_SHA256.txt"] = b"".join(
        f"{hashlib.sha256(data).hexdigest()}  {len(data)}  {relative}\n".encode("utf-8")
        for relative, data in sorted(members.items())
    )

    stage = target.with_name(f"{target.name}.partial.{uuid.uuid4().hex}")
    if stage.exists() or stage.is_symlink():
        raise TransactionError("archive staging path already exists", details={"path": str(stage)})
    try:
        _write_archive(stage, archive_root, members)
        staged_validation = validate_session_archive(stage)
        if staged_validation.archive_root != archive_root:
            raise TransactionError("staged archive root changed unexpectedly")
        rename_file_no_replace(stage, target, error_type=TransactionError)
        final_validation = validate_session_archive(target)
        if final_validation.archive_sha256 != staged_validation.archive_sha256:
            raise TransactionError("published archive differs from verified staging bytes")
    except (OSError, zipfile.BadZipFile) as exc:
        raise TransactionError("archive build failed; staging is retained", details={"path": str(stage)}) from exc

    expanded_after, _ = _safe_tree_inventory(
        record.session_root, include_operational=True, capture_bytes=False
    )
    if expanded_before != expanded_after:
        raise TransactionError(
            "expanded session changed during archive build; archive is retained for review",
            details={"archive_path": str(target)},
        )
    if quarantine_before is not None:
        quarantine_after = _validate_session_legacy_quarantine(record.session_root)
        for field in (
            "inventory_sha256",
            "parent_binding",
            "policy_id",
            "quarantined_revisions",
            "root_manifest_sha256",
        ):
            if quarantine_after.get(field) != quarantine_before.get(field):
                raise TransactionError(
                    "legacy quarantine changed during archive build; archive is retained for review",
                    details={"field": field, "archive_path": str(target)},
                )
    return ArchiveBuildResult(
        archive_path=target,
        archive_sha256=final_validation.archive_sha256,
        archive_bytes=final_validation.archive_bytes,
        archive_root=archive_root,
        analysis_session_uid=record.analysis_session_uid,
        source_tree_retained=True,
    )


def _read_archive_member(archive_path: Path, relative: str) -> bytes:
    validation = validate_session_archive(archive_path)
    full_name = f"{validation.archive_root}/{relative}"
    with _stable_archive_handle(archive_path) as (handle, _size):
        try:
            with zipfile.ZipFile(handle, "r") as archive:
                info = archive.getinfo(full_name)
                return _read_member_bytes(archive, info)
        except (KeyError, zipfile.BadZipFile) as exc:
            raise ValidationError("validated archive member became unavailable", details={"path": relative}) from exc


def _validate_restorable_metadata(
    metadata_bytes: bytes,
    validation: ArchiveValidation,
) -> dict[str, Any]:
    metadata = _load_canonical_json(metadata_bytes, label="payload/session_metadata.json")
    if set(metadata) != SESSION_METADATA_FIELDS or metadata.get("schema") != "CTL_SESSION_METADATA_JSON_V1":
        _fail("archive session metadata is not a restorable schema-2 session")
    validate_human_id(metadata["analysis_session_id"], field="analysis_session_id")
    validate_human_id(metadata["image_id"], field="image_id")
    validate_canonical_uuid(metadata["analysis_session_uid"])
    validate_canonical_uuid(metadata["image_uid"])
    validate_canonical_uuid(metadata["project_uid"])
    _require_sha256(metadata["source_sha256"], "session_metadata.source_sha256")
    if (
        metadata["analysis_session_id"] != validation.analysis_session_id
        or metadata["analysis_session_uid"] != validation.analysis_session_uid
        or metadata["project_uid"] != validation.project_uid
        or metadata["source_sha256"] != validation.source_sha256
    ):
        _fail("archive root/descriptor/session metadata trust chain is inconsistent")
    return metadata


def _verify_source_blob(
    source_project_root: Path,
    validation: ArchiveValidation,
    metadata: Mapping[str, Any],
) -> SessionCore:
    validate_project(source_project_root)
    core = SessionCore(source_project_root)
    if core.project_uid != validation.project_uid:
        _fail("source project UID differs from archive source reference")
    registry = core._source_registry()
    blobs = [item for item in registry["blobs"] if item["source_sha256"] == validation.source_sha256]
    bindings = [
        item
        for item in registry["image_bindings"]
        if item["image_uid"] == metadata["image_uid"]
        and item["image_id"] == metadata["image_id"]
        and item["source_sha256"] == validation.source_sha256
    ]
    if len(blobs) != 1 or len(bindings) != 1:
        _fail("archive source/image identity is not present exactly once in the schema-2 source project")
    blob_path = source_project_root.joinpath(*blobs[0]["storage_relative_path"].split("/"))
    try:
        blob_bytes = stable_plain_bytes(blob_path, label="restore source blob")
    except PathSafetyError as exc:
        raise ValidationError("restore source blob is unsafe", details={"reason": str(exc)}) from exc
    if len(blob_bytes) != blobs[0]["byte_size"] or hashlib.sha256(blob_bytes).hexdigest() != validation.source_sha256:
        _fail("restore source blob bytes differ from archive source reference")
    return core


def _payload_record_map(validation: ArchiveValidation) -> dict[str, ArchiveFileRecord]:
    result: dict[str, ArchiveFileRecord] = {}
    for record in validation.payload_files:
        if not record.path.startswith("payload/"):
            _fail("archive payload record is outside payload/")
        relative = _validate_portable_relative(record.path[len("payload/") :], field="restore_relative_path")
        if relative in result:
            _fail("restore payload path is duplicated", relative_path=relative)
        result[relative] = record
    return result


def _assert_source_project_unchanged(source_root: Path, before: Mapping[str, str]) -> None:
    """Revalidate both source bytes and path identities after a restore attempt."""

    validate_project(source_root)
    if dict(before) != snapshot_tree(source_root):
        raise TransactionError("read-only source project changed during archive restore")


def _verify_restored_tree(target: Path, records: Mapping[str, ArchiveFileRecord]) -> str:
    _snapshot, files = _safe_tree_inventory(target, include_operational=True, capture_bytes=True)
    if set(files) != set(records):
        _fail(
            "restored tree is not the exact archived payload inventory",
            missing=sorted(set(records) - set(files)),
            extra=sorted(set(files) - set(records)),
        )
    tree_lines: list[str] = []
    for relative in sorted(records):
        data = files[relative]
        record = records[relative]
        digest = hashlib.sha256(data).hexdigest()
        if len(data) != record.byte_size or digest != record.sha256:
            _fail("restored file bytes differ from archive payload", relative_path=relative)
        tree_lines.append(f"{digest}  {len(data)}  {relative}\n")
    return hashlib.sha256("".join(tree_lines).encode("utf-8")).hexdigest()


def _receipt_path(target: Path) -> Path:
    return target.with_name(f".{target.name}.restore_receipt.json")


def _validate_receipt(
    receipt_path: Path,
    *,
    validation: ArchiveValidation,
    target_tree_sha256: str,
) -> dict[str, Any]:
    try:
        data = stable_plain_bytes(receipt_path, label="archive restore receipt")
    except PathSafetyError as exc:
        raise ValidationError("archive restore receipt is absent or unsafe", details={"reason": str(exc)}) from exc
    receipt = _load_canonical_json(data, label="archive restore receipt")
    expected_fields = {
        "analysis_session_id",
        "analysis_session_uid",
        "archive_file_name",
        "archive_root",
        "archive_sha256",
        "authority",
        "metadata_rewritten",
        "operational_origin",
        "project_uid",
        "restored_at",
        "schema",
        "source_sha256",
        "target_session_tree_sha256",
    }
    if set(receipt) != expected_fields:
        _fail("restore receipt field inventory is not closed")
    _require_timestamp(receipt["restored_at"], "restored_at")
    expected = {
        "analysis_session_id": validation.analysis_session_id,
        "analysis_session_uid": validation.analysis_session_uid,
        "archive_file_name": validation.archive_path.name,
        "archive_root": validation.archive_root,
        "archive_sha256": validation.archive_sha256,
        "authority": False,
        "metadata_rewritten": False,
        "operational_origin": "RESTORED_ARCHIVE",
        "project_uid": validation.project_uid,
        "schema": RESTORE_RECEIPT_SCHEMA,
        "source_sha256": validation.source_sha256,
        "target_session_tree_sha256": target_tree_sha256,
    }
    for field, value in expected.items():
        if receipt.get(field) != value:
            _fail("restore receipt does not bind the archive/target exactly", field=field)
    return receipt


def _stream_payload_to_stage(
    archive_path: Path,
    validation: ArchiveValidation,
    stage: Path,
    records: Mapping[str, ArchiveFileRecord],
) -> None:
    with _stable_archive_handle(archive_path) as (handle, archive_size):
        if _hash_open_file(handle, archive_size) != validation.archive_sha256:
            _fail("archive changed between validation and restore")
        try:
            with zipfile.ZipFile(handle, "r") as archive:
                for relative in sorted(records):
                    record = records[relative]
                    member_name = f"{validation.archive_root}/payload/{relative}"
                    info = archive.getinfo(member_name)
                    destination = stage.joinpath(*relative.split("/"))
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    digest = hashlib.sha256()
                    measured = 0
                    crc = 0
                    with archive.open(info, "r") as source, destination.open("xb") as output:
                        while True:
                            block = source.read(1024 * 1024)
                            if not block:
                                break
                            measured += len(block)
                            if measured > record.byte_size:
                                _fail("archive payload expanded beyond its declared size", path=record.path)
                            digest.update(block)
                            crc = zlib.crc32(block, crc)
                            output.write(block)
                        output.flush()
                        os.fsync(output.fileno())
                    if (
                        measured != record.byte_size
                        or digest.hexdigest() != record.sha256
                        or (crc & 0xFFFFFFFF) != info.CRC
                    ):
                        _fail("extracted payload differs from the validated archive", path=record.path)
                    try:
                        plain_file(destination, label="restored session file", single_link=True)
                    except PathSafetyError as exc:
                        raise ValidationError("restored output is linked, reparsed, hardlinked or special") from exc
        except (KeyError, zipfile.BadZipFile, RuntimeError, OSError, EOFError) as exc:
            if isinstance(exc, ValidationError):
                raise
            raise ValidationError("archive payload extraction failed closed", details={"reason": str(exc)}) from exc


def restore_session_archive(
    archive_path: os.PathLike[str] | str,
    *,
    source_project_root: os.PathLike[str] | str,
    destination_session_root: os.PathLike[str] | str,
    restored_at: str,
) -> RestoreResult:
    """Restore exact session bytes to a new root and publish an external receipt."""

    archive = Path(archive_path)
    validation = validate_session_archive(archive)
    metadata_bytes = _read_archive_member(archive, "payload/session_metadata.json")
    metadata = _validate_restorable_metadata(metadata_bytes, validation)
    source_root = Path(source_project_root)
    target = Path(destination_session_root)
    if not source_root.is_absolute() or not target.is_absolute():
        _fail("source project and destination session paths must be absolute")
    source_lexical = os.path.normcase(os.path.abspath(os.fspath(source_root)))
    target_lexical = os.path.normcase(os.path.abspath(os.fspath(target)))
    try:
        if os.path.commonpath([source_lexical, target_lexical]) == source_lexical:
            _fail("restored session root must be outside the read-only source project")
    except ValueError:
        pass
    if not _session_directory_matches_id(target.name, metadata["analysis_session_id"]):
        _fail("destination session root does not bind analysis_session_id", path=str(target))
    timestamp = _require_timestamp(restored_at, "restored_at")
    try:
        plain_directory(target.parent, label="restore destination parent")
    except PathSafetyError as exc:
        raise ValidationError("restore destination parent is unsafe", details={"reason": str(exc)}) from exc

    source_snapshot_before = snapshot_tree(source_root)
    _verify_source_blob(source_root, validation, metadata)
    records = _payload_record_map(validation)
    has_legacy_quarantine = bool(
        _quarantine_payload_records(validation.payload_files)
    )
    receipt = _receipt_path(target)

    if target.exists() or target.is_symlink():
        if not target.is_dir() or target.is_symlink():
            raise TransactionError("restore destination collision is not a plain directory")
        tree_sha = _verify_restored_tree(target, records)
        if has_legacy_quarantine:
            _validate_session_legacy_quarantine(target)
        _validate_receipt(receipt, validation=validation, target_tree_sha256=tree_sha)
        _assert_source_project_unchanged(source_root, source_snapshot_before)
        return RestoreResult(
            session_root=target,
            receipt_path=receipt,
            archive_sha256=validation.archive_sha256,
            analysis_session_uid=validation.analysis_session_uid,
            source_sha256=validation.source_sha256,
            published=False,
            result="IDEMPOTENT_VERIFIED",
        )
    if receipt.exists() or receipt.is_symlink():
        raise TransactionError("restore receipt collision exists without a published target")

    token = uuid.uuid4().hex
    stage = target.with_name(f"{target.name}.partial.{token}")
    receipt_stage = receipt.with_name(f"{receipt.name}.partial.{validation.archive_sha256[:16]}")
    if stage.exists() or stage.is_symlink() or receipt_stage.exists() or receipt_stage.is_symlink():
        raise TransactionError("restore staging collision exists; retained evidence requires review")
    stage.mkdir()
    for directory in sorted(STANDARD_SESSION_DIRECTORIES):
        (stage / directory).mkdir()
    _stream_payload_to_stage(archive, validation, stage, records)
    tree_sha = _verify_restored_tree(stage, records)
    restored_metadata = _load_canonical_json(
        stable_plain_bytes(stage / "session_metadata.json", label="restored session metadata"),
        label="restored session metadata",
    )
    if restored_metadata != metadata or stable_plain_bytes(
        stage / "session_metadata.json", label="restored session metadata"
    ) != metadata_bytes:
        _fail("restore changed session_metadata bytes or semantics")
    staged_quarantine: dict[str, Any] | None = None
    if has_legacy_quarantine:
        # Semantic validation is intentionally before either no-replace rename.
        staged_quarantine = _validate_session_legacy_quarantine(stage)
    receipt_value = {
        "analysis_session_id": validation.analysis_session_id,
        "analysis_session_uid": validation.analysis_session_uid,
        "archive_file_name": archive.name,
        "archive_root": validation.archive_root,
        "archive_sha256": validation.archive_sha256,
        "authority": False,
        "metadata_rewritten": False,
        "operational_origin": "RESTORED_ARCHIVE",
        "project_uid": validation.project_uid,
        "restored_at": timestamp,
        "schema": RESTORE_RECEIPT_SCHEMA,
        "source_sha256": validation.source_sha256,
        "target_session_tree_sha256": tree_sha,
    }
    _write_new_file(receipt_stage, _canonical_json_bytes(receipt_value))
    rename_directory_no_replace(stage, target, error_type=TransactionError)
    rename_file_no_replace(receipt_stage, receipt, error_type=TransactionError)
    final_tree_sha = _verify_restored_tree(target, records)
    if final_tree_sha != tree_sha:
        raise TransactionError("published restored session differs from verified staging")
    if staged_quarantine is not None:
        final_quarantine = _validate_session_legacy_quarantine(target)
        for field in (
            "inventory_sha256",
            "parent_binding",
            "policy_id",
            "quarantined_revisions",
            "root_manifest_sha256",
        ):
            if final_quarantine.get(field) != staged_quarantine.get(field):
                raise TransactionError(
                    "published restored quarantine differs from verified staging",
                    details={"field": field},
                )
    _validate_receipt(receipt, validation=validation, target_tree_sha256=final_tree_sha)
    _assert_source_project_unchanged(source_root, source_snapshot_before)
    return RestoreResult(
        session_root=target,
        receipt_path=receipt,
        archive_sha256=validation.archive_sha256,
        analysis_session_uid=validation.analysis_session_uid,
        source_sha256=validation.source_sha256,
        published=True,
        result="RESTORED_VERIFIED",
    )


__all__ = [
    "ARCHIVE_PROFILE_ID",
    "ArchiveBuildResult",
    "ArchiveFileRecord",
    "ArchiveValidation",
    "RestoreResult",
    "build_session_archive",
    "restore_session_archive",
    "validate_session_archive",
]
