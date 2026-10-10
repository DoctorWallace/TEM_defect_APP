#!/usr/bin/env python3
"""Narrow Fiji-to-Python entry point for Cavity TEM Light Prompt 1.

The Fiji macro invokes this file with an argv vector through Java
``ProcessBuilder``.  This file performs no interpreter, package, project, or
response-path discovery and has no legacy fallback.  Product behaviour lives
in ``cavity_tem_light_p1.cli.handle_fiji_request``.
"""

from __future__ import annotations

import argparse
import ctypes
import datetime as dt
import hashlib
import json
import os
import re
import stat
import subprocess
import sys
import unicodedata
from pathlib import Path
from pathlib import PurePosixPath
from typing import Any


REQUEST_SCHEMA = "CTL_IJM_BRIDGE_REQUEST_V1"
RESPONSE_SCHEMA = "CTL_IJM_BRIDGE_RESPONSE_V1"
RUNTIME_MANIFEST_SCHEMA = "CTL_P1_RUNTIME_MANIFEST_V1"
RUNTIME_INVENTORY_PROFILE = "CTL_P1_RUNTIME_CLOSED_INVENTORY_V1"
RUNTIME_MANIFEST_NAME = "CTL_P1_RUNTIME_MANIFEST.json"
CANDIDATE_ID = "Cavity_TEM_Light_v1_2_0_R10_DEV01"
EXPECTED_FIJI_RUNTIME_SHA256 = "c3ae8f63744a6532cb8b291d47acb2d1dac3fb0cd06f7bcc0c8827b0c67f8fa5"
SHA_RE = re.compile(r"[0-9a-f]{64}\Z", re.ASCII)
RFC3339_UTC_RE = re.compile(
    r"[0-9]{4}-(?:0[1-9]|1[0-2])-(?:0[1-9]|[12][0-9]|3[01])T"
    r"(?:[01][0-9]|2[0-3]):[0-5][0-9]:[0-5][0-9](?:\.[0-9]{1,6})?Z\Z",
    re.ASCII,
)
HERE = Path(os.path.abspath(__file__)).parent

EXPECTED_CLAIM_BOUNDARY = {
    "P2_FULL_SUPPLEMENT_READY": False,
    "fiji_real_executed": False,
    "final_version": False,
    "functional_release": False,
    "global_release": False,
    "installer_executed": False,
    "prompt2_started": False,
    "public_distribution_ready": False,
    "r10_final_status": "NOT_GRANTED",
    "scientific_validation": False,
    "test_pass_assigned": False,
}
EXPECTED_JNA = {
    "jars/jna-5.14.0.jar": {
        "bytes": 1_878_533,
        "sha256": "34ed1e1f27fa896bca50dbc4e99cf3732967cec387a7a0d5e3486c09673fe8c6",
    },
    "jars/jna-platform-5.14.0.jar": {
        "bytes": 1_369_287,
        "sha256": "ae4caceb3840730c2537f9b7fb55a01baba580286b4122951488bcee558c2449",
    },
}
EXPECTED_ICONS = {
    "cavity_add.png",
    "cavity_measure.png",
    "cavity_select.png",
    "cavity_studio.png",
    "cavity_zoom.png",
}
_WINDOWS_PLAIN_DIRECTORY_CACHE: dict[tuple[str, int, int, int, int, int], bool] = {}


class BridgeInputError(Exception):
    """An invocation or request violates the narrow bridge contract."""


def _valid_rfc3339_utc(value: Any) -> bool:
    if not isinstance(value, str) or RFC3339_UTC_RE.fullmatch(value) is None:
        return False
    try:
        dt.datetime.strptime(
            value,
            "%Y-%m-%dT%H:%M:%S.%fZ" if "." in value else "%Y-%m-%dT%H:%M:%SZ",
        )
    except ValueError:
        return False
    return True


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="ctl_p1_bridge.py",
        description="Fail-closed Fiji bridge for the Prompt-1 companion.",
    )
    parser.add_argument("--request")
    parser.add_argument("--request-sha256")
    parser.add_argument("--response")
    parser.add_argument("--runtime-manifest-sha256", required=True)
    parser.add_argument("--verify-runtime-root")
    parser.add_argument("--manifest-only", action="store_true")
    return parser


def _absolute_path(raw: str, label: str) -> Path:
    path = Path(raw)
    if not path.is_absolute():
        raise BridgeInputError(f"{label} must be absolute")
    return Path(os.path.abspath(os.fspath(path)))


_FILE_SNAPSHOT_FIELDS = (
    "st_dev",
    "st_ino",
    "st_mode",
    "st_nlink",
    "st_size",
    "st_mtime_ns",
    "st_ctime_ns",
    "st_file_attributes",
    "st_reparse_tag",
)
_WINDOWS_PATH_HANDLE_FIELDS = (
    "st_dev",
    "st_ino",
    "st_nlink",
    "st_size",
    "st_mtime_ns",
    "st_file_attributes",
    "st_reparse_tag",
)
_FILE_SNAPSHOT_INDEX = {
    name: index for index, name in enumerate(_FILE_SNAPSHOT_FIELDS)
}


def _file_snapshot(info: os.stat_result) -> tuple[int, ...]:
    """Identity and mutation-sensitive fields shared by path and open handle."""

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


def _cross_handle_field_names() -> tuple[str, ...]:
    """Return the explicit path-to-handle binding profile for this platform."""

    if os.name == "nt":
        return _WINDOWS_PATH_HANDLE_FIELDS
    return _FILE_SNAPSHOT_FIELDS


def _snapshot_mismatch_fields(
    left: tuple[int, ...],
    right: tuple[int, ...],
    *,
    cross_domain: bool,
) -> tuple[str, ...]:
    if len(left) != len(_FILE_SNAPSHOT_FIELDS) or len(right) != len(
        _FILE_SNAPSHOT_FIELDS
    ):
        raise AssertionError("file snapshot shape changed")
    fields = _cross_handle_field_names() if cross_domain else _FILE_SNAPSHOT_FIELDS
    return tuple(
        name
        for name in fields
        if left[_FILE_SNAPSHOT_INDEX[name]] != right[_FILE_SNAPSHOT_INDEX[name]]
    )


def _cross_handle_binding(snapshot: tuple[int, ...]) -> tuple[int, ...]:
    """Bind Windows path/handle views by physical identity, size and safety."""

    if len(snapshot) != len(_FILE_SNAPSHOT_FIELDS):
        raise AssertionError("file snapshot shape changed")
    return tuple(
        snapshot[_FILE_SNAPSHOT_INDEX[name]] for name in _cross_handle_field_names()
    )


def _stable_plain_read(path: Path, label: str, *, retain: bool) -> tuple[bytes | None, str]:
    """Read/hash one single-link file while binding the opened handle identity.

    This module must establish the runtime tree before adding it to
    ``sys.path``, so it intentionally implements this primitive locally and
    imports nothing from the as-yet-untrusted companion package.  Full
    snapshots remain mutation-sensitive within the path and handle domains.
    On Windows only, cross-domain comparison omits ``st_mode`` and
    ``st_ctime_ns`` because the Stage-1C probe demonstrated that CPython 3.12
    represents those fields differently for the same configured Python file.
    Physical identity, link count, size, mtime, attributes and reparse tag
    remain bound across path and handle views.
    """

    checked = _plain_file(path, label)
    try:
        before_path = checked.stat(follow_symlinks=False)
        before_path_snapshot = _file_snapshot(before_path)
        digest = hashlib.sha256()
        chunks: list[bytes] | None = [] if retain else None
        byte_count = 0
        with checked.open("rb") as stream:
            opened_before = os.fstat(stream.fileno())
            opened_before_snapshot = _file_snapshot(opened_before)
            opening_mismatches = _snapshot_mismatch_fields(
                before_path_snapshot,
                opened_before_snapshot,
                cross_domain=True,
            )
            if opening_mismatches:
                raise BridgeInputError(
                    f"{label} changed between path check and open; "
                    f"mismatching_fields={','.join(opening_mismatches)}"
                )
            while True:
                block = stream.read(1024 * 1024)
                if not block:
                    break
                byte_count += len(block)
                digest.update(block)
                if chunks is not None:
                    chunks.append(block)
            opened_after = os.fstat(stream.fileno())
            opened_after_snapshot = _file_snapshot(opened_after)
        checked_after = _plain_file(path, label)
        after_path = checked_after.stat(follow_symlinks=False)
        after_path_snapshot = _file_snapshot(after_path)
    except BridgeInputError:
        raise
    except OSError as exc:
        raise BridgeInputError(f"{label} cannot be read safely") from exc
    mutation_fields = {
        f"path_domain.{name}"
        for name in _snapshot_mismatch_fields(
            before_path_snapshot,
            after_path_snapshot,
            cross_domain=False,
        )
    }
    mutation_fields.update(
        f"handle_domain.{name}"
        for name in _snapshot_mismatch_fields(
            opened_before_snapshot,
            opened_after_snapshot,
            cross_domain=False,
        )
    )
    mutation_fields.update(
        f"path_handle_after.{name}"
        for name in _snapshot_mismatch_fields(
            after_path_snapshot,
            opened_after_snapshot,
            cross_domain=True,
        )
    )
    if byte_count != int(after_path.st_size):
        mutation_fields.add("bytes_read_vs_st_size")
    if mutation_fields:
        raise BridgeInputError(
            f"{label} changed while it was read; "
            f"mismatching_fields={','.join(sorted(mutation_fields))}"
        )
    return (b"".join(chunks) if chunks is not None else None), digest.hexdigest()


def _stable_plain_bytes(path: Path, label: str) -> bytes:
    raw, _ = _stable_plain_read(path, label, retain=True)
    if raw is None:  # pragma: no cover - closed by retain=True.
        raise AssertionError("stable byte read did not retain bytes")
    return raw


def _sha256_file(path: Path) -> str:
    _, digest = _stable_plain_read(path, "hashed single-link file", retain=False)
    return digest


def _windows_fsutil_tag(path: Path) -> int:
    if os.name != "nt":
        return 0
    from ctypes import wintypes

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    get_system_directory = kernel32.GetSystemDirectoryW
    get_system_directory.argtypes = [wintypes.LPWSTR, wintypes.UINT]
    get_system_directory.restype = wintypes.UINT
    buffer = ctypes.create_unicode_buffer(32768)
    length = get_system_directory(buffer, len(buffer))
    if length == 0 or length >= len(buffer):
        raise BridgeInputError("trusted Windows system directory cannot be established")
    fsutil = Path(buffer.value) / "fsutil.exe"
    if not fsutil.is_file():
        raise BridgeInputError("trusted System32 fsutil.exe is absent")
    try:
        completed = subprocess.run(
            [str(fsutil), "reparsepoint", "query", str(path)],
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            timeout=30,
        )
    except subprocess.TimeoutExpired as exc:
        raise BridgeInputError(f"trusted fsutil reparse query timed out for {path}") from exc
    except OSError as exc:
        raise BridgeInputError(f"trusted fsutil reparse query failed for {path}") from exc
    output = completed.stdout + b"\n" + completed.stderr
    if (
        not output.strip()
        or b"\xef\xbf\xbd" in output
        or b"\xff\xfd" in output
        or b"\xfd\xff" in output
    ):
        raise BridgeInputError(f"ambiguous trusted fsutil encoding/result for {path}")
    tags = {int(value, 16) for value in re.findall(rb"(?i)0x([0-9a-f]{8})", output)}
    if len(tags) == 1 and completed.returncode == 0:
        return tags.pop()
    if (
        not tags
        and completed.returncode != 0
        and re.search(rb"(?<![0-9])4390(?![0-9])", output)
        and re.search(
            rb"(?i)not\s+(?:a\s+)?reparse\s+point|no\s+es\s+un\s+punto",
            output,
        )
    ):
        return 0
    raise BridgeInputError(f"ambiguous trusted fsutil reparse result for {path}")


def _native_is_reparse(path: Path) -> bool:
    if os.name != "nt":
        info = path.lstat()
        return stat.S_ISLNK(info.st_mode) or bool(getattr(info, "st_file_attributes", 0) & 0x400)

    from ctypes import wintypes

    # The bridge verifies a closed tree before it may import the companion.
    # Re-running System32 fsutil for every file ancestor is both needlessly
    # expensive and a practical timeout risk.  Reuse only a *plain directory*
    # observation and bind it to the lexical path plus CPython's native volume
    # and file-id identity; a path-only cache is never trusted.  If the platform
    # cannot expose a usable file id, no cache entry is created.
    try:
        preliminary = path.stat(follow_symlinks=False)
    except OSError as exc:
        raise BridgeInputError(f"native path identity is unavailable: {path}") from exc
    cache_key: tuple[str, int, int, int, int, int] | None = None
    if stat.S_ISDIR(preliminary.st_mode) and int(preliminary.st_ino) != 0:
        cache_key = (
            os.path.normcase(os.path.abspath(os.fspath(path))),
            int(preliminary.st_dev),
            int(preliminary.st_ino),
            int(preliminary.st_mode),
            int(getattr(preliminary, "st_file_attributes", 0)),
            int(getattr(preliminary, "st_reparse_tag", 0)),
        )
        if _WINDOWS_PLAIN_DIRECTORY_CACHE.get(cache_key) is True:
            return False

    class FILE_ATTRIBUTE_TAG_INFO(ctypes.Structure):
        _fields_ = [("FileAttributes", wintypes.DWORD), ("ReparseTag", wintypes.DWORD)]

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    create_file = kernel32.CreateFileW
    create_file.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, wintypes.LPVOID, wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]
    create_file.restype = wintypes.HANDLE
    get_info = kernel32.GetFileInformationByHandleEx
    get_info.argtypes = [wintypes.HANDLE, ctypes.c_int, wintypes.LPVOID, wintypes.DWORD]
    get_info.restype = wintypes.BOOL
    ioctl = kernel32.DeviceIoControl
    ioctl.argtypes = [wintypes.HANDLE, wintypes.DWORD, wintypes.LPVOID, wintypes.DWORD, wintypes.LPVOID, wintypes.DWORD, ctypes.POINTER(wintypes.DWORD), wintypes.LPVOID]
    ioctl.restype = wintypes.BOOL
    close = kernel32.CloseHandle
    close.argtypes = [wintypes.HANDLE]
    close.restype = wintypes.BOOL
    handle = create_file(str(path), 0, 0x1 | 0x2 | 0x4, None, 3, 0x02000000 | 0x00200000, None)
    if handle == ctypes.c_void_p(-1).value:
        raise BridgeInputError(f"CreateFileW path probe failed: {path}")
    try:
        identity = FILE_ATTRIBUTE_TAG_INFO()
        if not get_info(handle, 9, ctypes.byref(identity), ctypes.sizeof(identity)):
            raise BridgeInputError(f"FileAttributeTagInfo path probe failed: {path}")
        raw = ctypes.create_string_buffer(16 * 1024)
        returned = wintypes.DWORD(0)
        if ioctl(handle, 0x000900A8, None, 0, raw, len(raw), ctypes.byref(returned), None):
            if returned.value < 8:
                raise BridgeInputError(f"truncated FSCTL reparse response: {path}")
            fsctl_tag = int.from_bytes(raw.raw[:4], "little")
        else:
            error = ctypes.get_last_error()
            if error != 4390:
                raise BridgeInputError(f"FSCTL reparse path probe failed: {path}; winerror={error}")
            fsctl_tag = 0
        attribute_tag = int(identity.ReparseTag)
        if attribute_tag and fsctl_tag and attribute_tag != fsctl_tag:
            raise BridgeInputError(f"native reparse tag disagreement: {path}")
        native_tag = attribute_tag or fsctl_tag
        # Cross-check every directory: that catches the observed custom Psync
        # provider root even when both native tag fields are zero.
        directory = bool(int(identity.FileAttributes) & 0x10)
        fsutil_tag = _windows_fsutil_tag(path) if directory or native_tag else 0
        if native_tag and fsutil_tag and native_tag != fsutil_tag:
            raise BridgeInputError(f"native/fsutil reparse tag disagreement: {path}")
        result = bool(int(identity.FileAttributes) & 0x400) or bool(native_tag or fsutil_tag)
        if not result and cache_key is not None:
            _WINDOWS_PLAIN_DIRECTORY_CACHE[cache_key] = True
        return result
    finally:
        if not close(handle):
            raise BridgeInputError(f"CloseHandle failed after path probe: {path}")


def _reject_chain(path: Path, label: str, *, must_exist: bool = True) -> Path:
    candidate = _absolute_path(str(path), label)
    if must_exist and not candidate.exists() and not candidate.is_symlink():
        raise BridgeInputError(f"{label} is absent")
    cursor = candidate if must_exist or candidate.exists() or candidate.is_symlink() else candidate.parent
    while True:
        if cursor.exists() or cursor.is_symlink():
            if _native_is_reparse(cursor):
                raise BridgeInputError(f"{label} chain contains link/reparse: {cursor}")
        parent = cursor.parent
        if parent == cursor:
            break
        cursor = parent
    return candidate


def _plain_directory(path: Path, label: str) -> Path:
    candidate = _reject_chain(path, label)
    if not candidate.is_dir():
        raise BridgeInputError(f"{label} is not a directory")
    return candidate


def _plain_file(path: Path, label: str) -> Path:
    candidate = _reject_chain(path, label)
    info = candidate.stat(follow_symlinks=False)
    if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
        raise BridgeInputError(f"{label} is not a regular single-link file")
    return candidate


def _safe_runtime_relative(value: Any) -> str:
    if not isinstance(value, str) or not value or "\\" in value or "\x00" in value:
        raise BridgeInputError("runtime manifest path is malformed")
    if unicodedata.normalize("NFC", value) != value:
        raise BridgeInputError("runtime manifest path is not NFC")
    pure = PurePosixPath(value)
    if pure.is_absolute() or str(pure) != value or any(part in {"", ".", ".."} or ":" in part for part in pure.parts):
        raise BridgeInputError("runtime manifest path is unsafe")
    return value


def _canonical_manifest_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False) + "\n").encode("utf-8")


def _verify_runtime_manifest(runtime_root: Path, expected_hash: str) -> dict[str, Any]:
    if SHA_RE.fullmatch(expected_hash or "") is None:
        raise BridgeInputError("expected runtime manifest SHA-256 is malformed")
    root = _plain_directory(runtime_root, "runtime root")
    manifest_path = root / RUNTIME_MANIFEST_NAME
    raw = _stable_plain_bytes(manifest_path, "runtime manifest")
    if hashlib.sha256(raw).hexdigest() != expected_hash:
        raise BridgeInputError("runtime manifest SHA-256 mismatch")
    if raw.startswith(b"\xef\xbb\xbf") or b"\r" in raw or not raw.endswith(b"\n"):
        raise BridgeInputError("runtime manifest encoding profile is invalid")
    try:
        value = json.loads(raw.decode("utf-8", "strict"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise BridgeInputError("runtime manifest JSON is invalid") from exc
    if raw != _canonical_manifest_bytes(value):
        raise BridgeInputError("runtime manifest is not canonical JSON")
    expected_keys = {"candidate_id", "file_count", "files", "inventory_profile", "manifest_self_included", "manifest_self_relative_path", "schema"}
    if not isinstance(value, dict) or set(value) != expected_keys:
        raise BridgeInputError("runtime manifest fields are not exact")
    if value.get("schema") != RUNTIME_MANIFEST_SCHEMA or value.get("candidate_id") != CANDIDATE_ID or value.get("inventory_profile") != RUNTIME_INVENTORY_PROFILE:
        raise BridgeInputError("runtime manifest identity/profile mismatch")
    if value.get("manifest_self_included") is not False or value.get("manifest_self_relative_path") != RUNTIME_MANIFEST_NAME:
        raise BridgeInputError("runtime manifest self-exclusion is invalid")
    files = value.get("files")
    if not isinstance(files, list) or type(value.get("file_count")) is not int or value["file_count"] != len(files):
        raise BridgeInputError("runtime manifest file_count mismatch")
    expected_files: dict[str, tuple[int, str]] = {}
    previous = ""
    expected_directories: set[str] = set()
    for record in files:
        if not isinstance(record, dict) or set(record) != {"bytes", "path", "sha256"}:
            raise BridgeInputError("runtime manifest file record fields are not exact")
        relative = _safe_runtime_relative(record["path"])
        if relative == RUNTIME_MANIFEST_NAME or relative in expected_files or (previous and relative < previous):
            raise BridgeInputError("runtime manifest inventory is self-referential, duplicated or unsorted")
        size = record["bytes"]
        digest = record["sha256"]
        if type(size) is not int or size < 0 or not isinstance(digest, str) or SHA_RE.fullmatch(digest) is None:
            raise BridgeInputError("runtime manifest size/hash record is invalid")
        expected_files[relative] = (size, digest)
        previous = relative
        parts = PurePosixPath(relative).parts
        for index in range(1, len(parts)):
            expected_directories.add(PurePosixPath(*parts[:index]).as_posix())

    actual_files: set[str] = set()
    actual_directories: set[str] = set()

    def visit(directory: Path) -> None:
        for entry in sorted(os.scandir(directory), key=lambda item: item.name):
            path = Path(entry.path)
            relative = path.relative_to(root).as_posix()
            if relative == RUNTIME_MANIFEST_NAME:
                continue
            if entry.is_dir(follow_symlinks=False):
                _plain_directory(path, "runtime inventory directory")
                actual_directories.add(relative)
                visit(path)
                continue
            _safe_runtime_relative(relative)
            actual_files.add(relative)
            if relative not in expected_files:
                raise BridgeInputError(f"runtime inventory contains undeclared file: {relative}")
            size, digest = expected_files[relative]
            raw_file = _stable_plain_bytes(path, f"runtime inventory file {relative}")
            if len(raw_file) != size or hashlib.sha256(raw_file).hexdigest() != digest:
                raise BridgeInputError(f"runtime inventory hash/size mismatch: {relative}")

    visit(root)
    if actual_files != set(expected_files) or actual_directories != expected_directories:
        raise BridgeInputError("runtime inventory file/directory closure mismatch")
    return value


def _read_json_plain(path: Path, label: str) -> tuple[dict[str, Any], bytes]:
    raw = _stable_plain_bytes(path, label)
    if raw.startswith(b"\xef\xbb\xbf") or b"\x00" in raw:
        raise BridgeInputError(f"{label} encoding is invalid")
    try:
        value = json.loads(raw.decode("utf-8", "strict"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise BridgeInputError(f"{label} JSON is invalid") from exc
    if not isinstance(value, dict):
        raise BridgeInputError(f"{label} root is not an object")
    return value, raw


def _valid_native_identity(value: Any, *, require_nlink: bool = False) -> bool:
    keys = {
        "file_attributes",
        "fsutil_cross_checked",
        "fsutil_reparse_tag",
        "is_reparse",
        "method",
        "reparse_tag",
    }
    if require_nlink:
        keys.add("nlink")
    if not isinstance(value, dict) or set(value) != keys:
        return False
    if (
        type(value.get("file_attributes")) is not int
        or value["file_attributes"] < 0
        or value["file_attributes"] & 0x400 != 0
        or type(value.get("fsutil_reparse_tag")) is not int
        or value["fsutil_reparse_tag"] != 0
        or type(value.get("reparse_tag")) is not int
        or value["reparse_tag"] != 0
        or type(value.get("fsutil_cross_checked")) is not bool
        or value.get("is_reparse") is not False
        or value.get("method")
        not in {
            "POSIX_LSTAT_WITH_OPTIONAL_WINDOWS_FIELDS",
            "WIN32_FSUTIL_FSCTL_AND_FILE_ATTRIBUTE_TAG_INFO",
        }
        or (
            value.get("method") == "POSIX_LSTAT_WITH_OPTIONAL_WINDOWS_FIELDS"
            and value["fsutil_cross_checked"] is not False
        )
    ):
        return False
    return not require_nlink or type(value.get("nlink")) is int and value["nlink"] == 1


def _valid_claim_boundary(value: Any) -> bool:
    return isinstance(value, dict) and value == EXPECTED_CLAIM_BOUNDARY


def _valid_staging_path_safety(value: Any) -> bool:
    if not isinstance(value, dict) or set(value) != {
        "evidence_root",
        "fiji_jna_artifacts",
        "fiji_root",
        "probe",
        "python_executable",
        "source_root",
    }:
        return False
    roots = (value.get("evidence_root"), value.get("fiji_root"), value.get("source_root"))
    return (
        value.get("probe") == "native_path_identity"
        and value.get("fiji_jna_artifacts") == EXPECTED_JNA
        and all(_valid_native_identity(item) for item in roots)
        and all(
            item.get("method") != "WIN32_FSUTIL_FSCTL_AND_FILE_ATTRIBUTE_TAG_INFO"
            or item.get("fsutil_cross_checked") is True
            for item in roots
        )
        and _valid_native_identity(value.get("python_executable"), require_nlink=True)
    )


def _valid_profile_binding(value: Any, manifest: dict[str, Any]) -> bool:
    if not isinstance(value, dict) or set(value) != {
        "column_count",
        "header_sha256",
        "identity_provenance_column",
        "profile_sha256",
        "runtime_sha256",
    }:
        return False
    lookup = {record["path"]: record for record in manifest["files"]}
    profile = lookup.get("data/CTL_CAVITY_OBJECTS_TSV_PROFILE_V1.json", {})
    header = lookup.get("data/cavity_objects_header.tsv", {})
    return (
        type(value.get("column_count")) is int
        and value["column_count"] == 234
        and type(value.get("identity_provenance_column")) is int
        and value["identity_provenance_column"] == 116
        and value.get("profile_sha256") == profile.get("sha256")
        and value.get("header_sha256") == header.get("sha256")
        and value.get("runtime_sha256") == EXPECTED_FIJI_RUNTIME_SHA256
    )


def _verify_runtime_binding(runtime_root: Path, manifest: dict[str, Any], manifest_hash: str) -> dict[str, Any]:
    package_root = _plain_directory(runtime_root.parent, "installed package root")
    config, config_raw = _read_json_plain(package_root / "p1_runtime_config.json", "runtime config")
    required = {
        "binding_record_relative_path", "binding_record_schema", "bridge_relative_path",
        "candidate_id", "created_at", "installation_root", "python_executable",
        "python_executable_sha256", "python_version", "runtime_file_count",
        "runtime_inventory_profile", "runtime_manifest_relative_path",
        "runtime_manifest_sha256", "schema",
    }
    staging_optional = {
        "campaign_harness_bytes", "campaign_harness_relative_path",
        "campaign_harness_sha256",
        "case_assembler_bytes", "case_assembler_relative_path", "case_assembler_sha256",
        "implementation_branch", "implementation_commit", "install_mode",
        "pixel_probe_relative_path", "public_distribution_ready",
    }
    if set(config) not in (required, required | staging_optional):
        raise BridgeInputError("runtime config fields are not closed")
    if config.get("schema") != "CTL_P1_RUNTIME_CONFIG_V2" or config.get("candidate_id") != CANDIDATE_ID:
        raise BridgeInputError("runtime config schema/candidate mismatch")
    if (
        not _valid_rfc3339_utc(config.get("created_at"))
        or config.get("python_version")
        != ".".join(str(component) for component in sys.version_info[:3])
    ):
        raise BridgeInputError("runtime config time/Python identity mismatch")
    if config.get("bridge_relative_path") != "python_companion/ctl_p1_bridge.py" or config.get("runtime_manifest_relative_path") != f"python_companion/{RUNTIME_MANIFEST_NAME}":
        raise BridgeInputError("runtime config fixed layout mismatch")
    if config.get("runtime_manifest_sha256") != manifest_hash or config.get("runtime_inventory_profile") != RUNTIME_INVENTORY_PROFILE or config.get("runtime_file_count") != manifest["file_count"]:
        raise BridgeInputError("runtime config inventory binding mismatch")
    staging_mode = set(config) == required | staging_optional
    expected_record_schema = (
        "CTL_P1_FIJI_CAMPAIGN_STAGING_V1" if staging_mode else "CTL_P1_INSTALL_RECORD_V2"
    )
    expected_record_relative = "campaign_staging_record.json" if staging_mode else "install_record.json"
    if (
        config.get("binding_record_schema") != expected_record_schema
        or config.get("binding_record_relative_path") != expected_record_relative
    ):
        raise BridgeInputError("runtime config binding-record schema/mode mismatch")
    if staging_mode and (
        config.get("install_mode") != "STAGING_NOT_PRODUCTION_INSTALLER"
        or config.get("public_distribution_ready") is not False
        or not isinstance(config.get("implementation_branch"), str)
        or re.fullmatch(r"[-A-Za-z0-9._/]{1,255}", config["implementation_branch"]) is None
        or not isinstance(config.get("implementation_commit"), str)
        or re.fullmatch(r"[0-9a-f]{40}", config["implementation_commit"]) is None
        or config.get("pixel_probe_relative_path") != "campaign_tools/CTL_MASTER_PIXEL_SHA256_V1_INDEPENDENT.js"
        or config.get("campaign_harness_relative_path")
        != "campaign_tools/P1_FIJI_REAL_HARNESS.ijm"
        or not isinstance(config.get("campaign_harness_sha256"), str)
        or re.fullmatch(r"[0-9a-f]{64}", config["campaign_harness_sha256"]) is None
        or type(config.get("campaign_harness_bytes")) is not int
        or config["campaign_harness_bytes"] <= 0
        or config.get("case_assembler_relative_path") != "campaign_tools/assemble_prompt1_fiji_case.py"
        or not isinstance(config.get("case_assembler_sha256"), str)
        or re.fullmatch(r"[0-9a-f]{64}", config["case_assembler_sha256"]) is None
        or type(config.get("case_assembler_bytes")) is not int
        or config["case_assembler_bytes"] <= 0
    ):
        raise BridgeInputError("runtime staging config identity/no-claims mismatch")
    configured_root = _absolute_path(str(config.get("installation_root", "")), "configured installation_root")
    if configured_root != package_root:
        raise BridgeInputError("runtime config installation_root mismatch")
    python_text = config.get("python_executable")
    if not isinstance(python_text, str) or not Path(python_text).is_absolute():
        raise BridgeInputError("configured Python is lexically relative")
    python = _plain_file(_absolute_path(python_text, "configured Python"), "configured Python")
    if not os.path.samefile(python, sys.executable):
        raise BridgeInputError("running Python differs from configured Python")
    if config.get("python_executable_sha256") != _sha256_file(python):
        raise BridgeInputError("configured Python hash mismatch")
    record_relative = _safe_runtime_relative(config.get("binding_record_relative_path"))
    if "/" in record_relative:
        raise BridgeInputError("binding record must be a package-root direct child")
    record, _ = _read_json_plain(package_root / record_relative, "runtime binding record")
    if record.get("schema") != config.get("binding_record_schema") or record.get("candidate_id") != CANDIDATE_ID:
        raise BridgeInputError("runtime binding record schema/candidate mismatch")
    installer_record_keys = {
        "bridge_sha256", "candidate_id", "icon_sha256", "install_state", "installed_at",
        "package_manifest_sha256", "python_executable_sha256", "runtime_config_sha256",
        "runtime_file_count", "runtime_files", "runtime_inventory_profile",
        "runtime_manifest_sha256", "schema", "toolset_name", "toolset_sha256",
        "validation_evidence_external",
    }
    staging_record_keys = {
        "candidate_id", "campaign_harness_bytes", "campaign_harness_relative_path",
        "campaign_harness_sha256", "case_assembler_bytes", "case_assembler_relative_path",
        "case_assembler_sha256", "claim_boundary", "classification",
        "implementation_branch", "implementation_commit", "install_mode", "path_safety",
        "pixel_probe_sha256", "profile_header_runtime", "python_executable_sha256",
        "runtime_config_sha256", "runtime_file_count", "runtime_files",
        "runtime_inventory_profile", "runtime_manifest_sha256", "schema", "transaction_id",
    }
    if set(record) != (staging_record_keys if staging_mode else installer_record_keys):
        raise BridgeInputError("runtime binding record fields are not closed for its mode")
    if not staging_mode and (
        record.get("install_state") != "COMMITTED"
        or not _valid_rfc3339_utc(record.get("installed_at"))
        or not isinstance(record.get("bridge_sha256"), str)
        or SHA_RE.fullmatch(record["bridge_sha256"]) is None
        or record["bridge_sha256"] != _sha256_file(runtime_root / "ctl_p1_bridge.py")
        or not isinstance(record.get("validation_evidence_external"), str)
        or not Path(record["validation_evidence_external"]).is_absolute()
    ):
        raise BridgeInputError("runtime install record identity is invalid")
    if staging_mode and (
        record.get("install_mode") != config.get("install_mode")
        or record.get("implementation_branch") != config.get("implementation_branch")
        or record.get("implementation_commit") != config.get("implementation_commit")
        or record.get("classification") != "RESTRICTED_LOCAL_CAMPAIGN_EVIDENCE"
        or record.get("campaign_harness_relative_path")
        != config.get("campaign_harness_relative_path")
        or record.get("campaign_harness_sha256") != config.get("campaign_harness_sha256")
        or record.get("campaign_harness_bytes") != config.get("campaign_harness_bytes")
        or record.get("case_assembler_relative_path") != config.get("case_assembler_relative_path")
        or record.get("case_assembler_sha256") != config.get("case_assembler_sha256")
        or record.get("case_assembler_bytes") != config.get("case_assembler_bytes")
        or not isinstance(record.get("pixel_probe_sha256"), str)
        or re.fullmatch(r"[0-9a-f]{64}", record["pixel_probe_sha256"]) is None
        or not _valid_claim_boundary(record.get("claim_boundary"))
        or not _valid_profile_binding(record.get("profile_header_runtime"), manifest)
        or not _valid_staging_path_safety(record.get("path_safety"))
        or not isinstance(record.get("transaction_id"), str)
        or re.fullmatch(r"[A-Z0-9][A-Z0-9_-]{0,63}", record["transaction_id"]) is None
    ):
        raise BridgeInputError("runtime staging record identity mismatch")
    expected_record = {
        "runtime_manifest_sha256": manifest_hash,
        "runtime_inventory_profile": RUNTIME_INVENTORY_PROFILE,
        "runtime_file_count": manifest["file_count"],
        "runtime_config_sha256": hashlib.sha256(config_raw).hexdigest(),
        "python_executable_sha256": config["python_executable_sha256"],
        "runtime_files": manifest["files"],
    }
    for field, expected in expected_record.items():
        if record.get(field) != expected:
            raise BridgeInputError(f"runtime binding record mismatch: {field}")
    campaign_tools = package_root / "campaign_tools"
    if staging_mode:
        checked_tools = _plain_directory(campaign_tools, "campaign tools directory")
        expected_tools = {
            "CTL_MASTER_PIXEL_SHA256_V1_INDEPENDENT.js",
            "P1_FIJI_REAL_HARNESS.ijm",
            "assemble_prompt1_fiji_case.py",
        }
        entries = {entry.name for entry in checked_tools.iterdir()}
        if entries != expected_tools:
            raise BridgeInputError("campaign tools inventory is not closed")
        probe = _plain_file(
            checked_tools / "CTL_MASTER_PIXEL_SHA256_V1_INDEPENDENT.js",
            "independent pixel probe",
        )
        assembler = _plain_file(
            checked_tools / "assemble_prompt1_fiji_case.py",
            "campaign case assembler",
        )
        harness = _plain_file(
            checked_tools / "P1_FIJI_REAL_HARNESS.ijm",
            "Fiji-real campaign harness",
        )
        if _sha256_file(probe) != record["pixel_probe_sha256"]:
            raise BridgeInputError("independent pixel probe hash mismatch")
        if (
            assembler.stat().st_size != config["case_assembler_bytes"]
            or _sha256_file(assembler) != config["case_assembler_sha256"]
        ):
            raise BridgeInputError("campaign case assembler hash/size mismatch")
        if (
            harness.stat().st_size != config["campaign_harness_bytes"]
            or _sha256_file(harness) != config["campaign_harness_sha256"]
        ):
            raise BridgeInputError("Fiji-real campaign harness hash/size mismatch")
    elif campaign_tools.exists() or campaign_tools.is_symlink():
        raise BridgeInputError("production install contains undeclared campaign tools")
    else:
        fiji_root = _plain_directory(package_root.parent.parent, "installed Fiji root")
        toolset_root = _plain_directory(fiji_root / "macros" / "toolsets", "installed toolset root")
        if (
            record.get("toolset_name") != f"{CANDIDATE_ID}.ijm"
            or not isinstance(record.get("toolset_sha256"), str)
            or SHA_RE.fullmatch(record["toolset_sha256"]) is None
        ):
            raise BridgeInputError("production toolset binding is malformed")
        toolset = _plain_file(toolset_root / record["toolset_name"], "installed toolset")
        if _sha256_file(toolset) != record["toolset_sha256"]:
            raise BridgeInputError("installed toolset hash mismatch")
        icons = record.get("icon_sha256")
        if not isinstance(icons, dict) or set(icons) != EXPECTED_ICONS:
            raise BridgeInputError("installed icon inventory is not closed")
        for name, expected_hash in icons.items():
            if not isinstance(expected_hash, str) or SHA_RE.fullmatch(expected_hash) is None:
                raise BridgeInputError(f"installed icon hash is malformed: {name}")
            if _sha256_file(_plain_file(toolset_root / name, f"installed icon {name}")) != expected_hash:
                raise BridgeInputError(f"installed icon hash mismatch: {name}")
        package_manifest = _plain_file(
            package_root / "package_manifest.sha256.txt", "installed package manifest"
        )
        if (
            not isinstance(record.get("package_manifest_sha256"), str)
            or SHA_RE.fullmatch(record["package_manifest_sha256"]) is None
            or _sha256_file(package_manifest) != record["package_manifest_sha256"]
        ):
            raise BridgeInputError("installed package manifest hash mismatch")
    return config


def _is_within(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def _read_request(path: Path, expected_sha256: str) -> dict[str, Any]:
    if SHA_RE.fullmatch(expected_sha256 or "") is None:
        raise BridgeInputError("--request-sha256 must be lowercase SHA-256")
    raw = _stable_plain_bytes(path, "request")
    if hashlib.sha256(raw).hexdigest() != expected_sha256:
        raise BridgeInputError("request identity/SHA-256 changed or differs from argv")
    if raw.startswith(b"\xef\xbb\xbf") or b"\x00" in raw or b"\r" in raw:
        raise BridgeInputError("request must be UTF-8 without BOM/NUL/CR")
    try:
        value = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise BridgeInputError(f"request JSON is invalid: {exc}") from exc
    if not isinstance(value, dict):
        raise BridgeInputError("request root must be an object")
    if value.get("schema") != REQUEST_SCHEMA:
        raise BridgeInputError("request schema mismatch")
    return value


def _validated_paths(
    request_path: Path,
    response_path: Path,
    request: dict[str, Any],
) -> tuple[Path, Path, Path]:
    policy = request.get("response_policy")
    if not isinstance(policy, dict):
        raise BridgeInputError("response_policy object is required")
    temporary_raw = policy.get("temporary_root")
    if not isinstance(temporary_raw, str) or not temporary_raw:
        raise BridgeInputError("response_policy.temporary_root is required")
    temporary_root = _plain_directory(_absolute_path(temporary_raw, "temporary_root"), "temporary_root")

    request_real = _plain_file(request_path, "request")
    response_parent = _plain_directory(response_path.parent, "response parent")
    response_real = response_parent / response_path.name
    if request_real.parent != temporary_root or response_parent != temporary_root:
        raise BridgeInputError("request and response must be direct children of temporary_root")
    if not _is_within(request_real, temporary_root) or not _is_within(response_real, temporary_root):
        raise BridgeInputError("request/response escape temporary_root")
    if response_real.suffix.lower() != ".json":
        raise BridgeInputError("response must have .json suffix")
    if response_real.exists() or response_real.is_symlink():
        raise BridgeInputError("response target must not pre-exist")
    if request_real == response_real:
        raise BridgeInputError("request and response must differ")

    forbidden_roots: list[str] = []
    for key in ("project_root", "signed_package_root"):
        value = request.get(key)
        if isinstance(value, str) and value:
            forbidden_roots.append(value)
    extra = request.get("forbidden_response_roots", [])
    if isinstance(extra, list):
        forbidden_roots.extend(value for value in extra if isinstance(value, str) and value)
    for raw_root in forbidden_roots:
        root = _absolute_path(raw_root, "forbidden response root")
        if _is_within(response_real, root):
            raise BridgeInputError("response must remain external to project/signed roots")
    return request_real, response_real, temporary_root


def _response_bytes(response: dict[str, Any]) -> bytes:
    return (
        json.dumps(
            response,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
        + b"\n"
    )


def _write_exclusive(path: Path, response: dict[str, Any]) -> None:
    _plain_directory(path.parent, "response parent")
    _reject_chain(path, "response", must_exist=False)
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    descriptor = os.open(path, flags, 0o600)
    try:
        with os.fdopen(descriptor, "wb", closefd=True) as stream:
            stream.write(_response_bytes(response))
            stream.flush()
            os.fsync(stream.fileno())
        _plain_file(path, "response")
    except Exception:
        try:
            path.unlink(missing_ok=True)
        except OSError:
            pass
        raise


def _failure_response(
    request: dict[str, Any] | None,
    code: str,
    message: str,
) -> dict[str, Any]:
    return {
        "schema": RESPONSE_SCHEMA,
        "request_id": (request or {}).get("request_id", "NOT_AVAILABLE"),
        "operation": (request or {}).get("operation", "NOT_AVAILABLE"),
        "phase": (request or {}).get("phase", "NOT_AVAILABLE"),
        "status": "FAIL",
        "result": None,
        "errors": [{"code": code, "message": message}],
        "warnings": [],
    }


def _validate_handler_response(
    request: dict[str, Any], response: Any
) -> dict[str, Any]:
    if not isinstance(response, dict):
        raise BridgeInputError("handler response root must be an object")
    if response.get("schema") != RESPONSE_SCHEMA:
        raise BridgeInputError("handler response schema mismatch")
    for key in ("request_id", "operation", "phase"):
        if response.get(key) != request.get(key):
            raise BridgeInputError(f"handler response {key} mismatch")
    if response.get("status") not in {"PASS", "FAIL"}:
        raise BridgeInputError("handler response status must be PASS or FAIL")
    if not isinstance(response.get("errors"), list):
        raise BridgeInputError("handler response errors must be an array")
    if not isinstance(response.get("warnings", []), list):
        raise BridgeInputError("handler response warnings must be an array")
    if response["status"] == "PASS" and response["errors"]:
        raise BridgeInputError("PASS handler response cannot contain errors")
    if response["status"] == "FAIL" and not response["errors"]:
        raise BridgeInputError("FAIL handler response requires structured errors")
    # Force canonical serialization now so NaN/Infinity fail before opening output.
    _response_bytes(response)
    return response


def main(argv: list[str] | None = None) -> int:
    request: dict[str, Any] | None = None
    response_path: Path | None = None
    output_validated = False
    try:
        args = _parser().parse_args(argv)
        expected_manifest_hash = args.runtime_manifest_sha256
        if SHA_RE.fullmatch(expected_manifest_hash or "") is None:
            raise BridgeInputError("--runtime-manifest-sha256 must be lowercase SHA-256")
        if args.verify_runtime_root is not None:
            if args.request is not None or args.response is not None:
                raise BridgeInputError("verification mode does not accept request/response")
            runtime_root = _absolute_path(args.verify_runtime_root, "verification runtime root")
            manifest = _verify_runtime_manifest(runtime_root, expected_manifest_hash)
            if not args.manifest_only:
                _verify_runtime_binding(runtime_root, manifest, expected_manifest_hash)
            print(
                json.dumps(
                    {
                        "candidate_id": CANDIDATE_ID,
                        "file_count": manifest["file_count"],
                        "inventory_profile": RUNTIME_INVENTORY_PROFILE,
                        "runtime_manifest_sha256": expected_manifest_hash,
                        "status": "VERIFIED",
                    },
                    sort_keys=True,
                    separators=(",", ":"),
                )
            )
            return 0
        if args.manifest_only:
            raise BridgeInputError("--manifest-only requires --verify-runtime-root")
        if args.request is None or args.request_sha256 is None or args.response is None:
            raise BridgeInputError(
                "normal bridge mode requires --request, --request-sha256 and --response"
            )

        manifest = _verify_runtime_manifest(HERE, expected_manifest_hash)
        _verify_runtime_binding(HERE, manifest, expected_manifest_hash)
        request_path = _absolute_path(args.request, "request")
        response_path = _absolute_path(args.response, "response")
        request = _read_request(request_path, args.request_sha256)
        _, response_path, _ = _validated_paths(request_path, response_path, request)
        output_validated = True

        # The complete companion inventory and installed binding were verified
        # before this first sys.path mutation/import.
        sys.path.insert(0, str(HERE))
        from cavity_tem_light_p1.cli import handle_fiji_request

        response = _validate_handler_response(request, handle_fiji_request(request))
        _write_exclusive(response_path, response)
        return 0 if response["status"] == "PASS" else 1
    except SystemExit:
        raise
    except Exception as exc:  # No traceback or partial scientific result escapes.
        message = str(exc) or exc.__class__.__name__
        failure = _failure_response(request, "FIJI_BRIDGE_FAIL_CLOSED", message)
        if output_validated and response_path is not None:
            try:
                if response_path.is_absolute() and response_path.parent.is_dir() and not response_path.exists():
                    _write_exclusive(response_path, failure)
            except Exception:
                pass
        print(f"FIJI_BRIDGE_FAIL_CLOSED: {message}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
