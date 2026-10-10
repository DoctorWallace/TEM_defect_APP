"""Fail-closed path identity and no-replace publication primitives.

Prompt 1 must not treat ``Path.resolve`` or CPython's cached stat fields as a
security boundary.  In particular, Windows sync providers can expose custom
reparse tags to the operating system while ``st_file_attributes`` remains
incomplete.  This module is the one stdlib-only implementation used by the
runtime writers and consumers.

The Windows probe deliberately combines three independent observations:
``FileAttributeTagInfo``, ``FSCTL_GET_REPARSE_POINT`` and the trusted
``System32\\fsutil.exe``. On paths beyond fsutil's MAX_PATH handling, a fresh
extended-path handle performs that control query directly; no DOS aliases or
filesystem links are introduced. Ambiguity is an error. Directory publication uses
an operating-system no-replace primitive; a preceding existence check is only
diagnostic and is never the exclusivity mechanism.
"""

from __future__ import annotations

import ctypes
import errno
import functools
import os
import re
import stat
import subprocess
from pathlib import Path
from typing import Any, Type


FILE_ATTRIBUTE_REPARSE_POINT = 0x400


class PathSafetyError(RuntimeError):
    """The requested path operation cannot be proven safe."""


def lexical_absolute(raw: os.PathLike[str] | str, *, label: str = "path") -> Path:
    """Return an absolute lexical path without following an existing link."""

    path = Path(raw)
    if not path.is_absolute():
        raise PathSafetyError(f"{label} must be an explicit absolute path: {path}")
    return Path(os.path.abspath(os.fspath(path)))


def _trusted_system_fsutil() -> Path:
    if os.name != "nt":
        raise PathSafetyError("fsutil is only available on Windows")
    from ctypes import wintypes

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    get_system_directory = kernel32.GetSystemDirectoryW
    get_system_directory.argtypes = [wintypes.LPWSTR, wintypes.UINT]
    get_system_directory.restype = wintypes.UINT
    buffer = ctypes.create_unicode_buffer(32768)
    length = get_system_directory(buffer, len(buffer))
    if length == 0 or length >= len(buffer):
        raise PathSafetyError(
            f"GetSystemDirectoryW failed during reparse probe: winerror={ctypes.get_last_error()}"
        )
    executable = Path(buffer.value) / "fsutil.exe"
    if not executable.is_file():
        raise PathSafetyError(f"trusted system fsutil is absent: {executable}")
    return executable


@functools.lru_cache(maxsize=4096)
def _windows_fsutil_reparse_tag_cached(path_text: str, stat_identity: tuple[int, ...]) -> int:
    # ``stat_identity`` is intentionally part of the key: replacement or
    # metadata mutation invalidates the observation without trusting path text
    # alone.  The value is unused otherwise.
    del stat_identity
    path = Path(path_text)
    executable = _trusted_system_fsutil()
    try:
        completed = subprocess.run(
            [str(executable), "reparsepoint", "query", str(path)],
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            timeout=30,
        )
    except subprocess.TimeoutExpired as exc:
        raise PathSafetyError(f"trusted fsutil reparse query timed out for {path}") from exc
    except OSError as exc:
        raise PathSafetyError(f"trusted fsutil reparse query failed for {path}: {exc}") from exc
    output = completed.stdout + b"\n" + completed.stderr
    return _parse_fsutil_reparse_output(output, completed.returncode, path)


def _parse_fsutil_reparse_output(output: bytes, returncode: int, path: Path) -> int:
    """Parse only the two closed outcomes of ``fsutil reparsepoint query``."""

    # A replacement character means the console bytes could not be decoded
    # deterministically.  Do not let a recognisable 4390 phrase elsewhere in
    # the damaged output turn that ambiguity into a negative reparse result.
    if (
        not output.strip()
        or b"\xef\xbf\xbd" in output
        or b"\xff\xfd" in output
        or b"\xfd\xff" in output
    ):
        raise PathSafetyError(f"empty fsutil reparse query result for {path}")
    matches = re.findall(rb"(?i)0x([0-9a-f]{8})", output)
    unique = {int(item, 16) for item in matches}
    # A tag is a positive result only for a successful query.  Diagnostics
    # such as HRESULTs on access-denied paths can also contain one 0x........
    # token and must never be mistaken for a reparse tag.
    if len(unique) == 1 and returncode == 0:
        return unique.pop()
    no_reparse_code = re.search(rb"(?<![0-9])4390(?![0-9])", output)
    no_reparse_phrase = re.search(
        rb"(?i)not\s+(?:a\s+)?reparse\s+point|no\s+es\s+un\s+punto",
        output,
    )
    if not unique and returncode != 0 and no_reparse_code and no_reparse_phrase:
        return 0
    excerpt = output[:512].decode("utf-8", "backslashreplace")
    raise PathSafetyError(
        f"ambiguous fsutil reparse query for {path} (exit={returncode}): {excerpt}"
    )


def windows_fsutil_reparse_tag(path: Path) -> int:
    """Return a closed reparse cross-check, using a fresh native long-path handle.

    ``0`` means Win32 error 4390 (the object is not a reparse point).  No
    locale-dependent success text is trusted; the tag or the numeric error is
    required.
    """

    if os.name != "nt":
        return 0
    if _windows_needs_long_path_query(path):
        # fsutil expands even extended/relative names into a MAX_PATH buffer
        # on the supported Windows installation. Never reinterpret ERROR_PATH_
        # NOT_FOUND as a plain node or skip the cross-check: open the exact
        # lexical node again and perform the filesystem control independently.
        return _windows_long_path_reparse_tag(path)
    try:
        info = path.stat(follow_symlinks=False)
    except OSError as exc:
        raise PathSafetyError(f"cannot stat path before fsutil query: {path}: {exc}") from exc
    base_identity = (
        int(info.st_dev),
        int(info.st_ino),
        int(info.st_mode),
        int(getattr(info, "st_file_attributes", 0)),
        int(getattr(info, "st_reparse_tag", 0)),
    )
    # Creating children changes a directory timestamp, not its reparse
    # identity.  The stable device/file-id tuple invalidates replacement while
    # allowing one trusted fsutil observation to cover a transaction's many
    # child writes.  Regular-file keys retain size and timestamps.
    identity = base_identity if stat.S_ISDIR(info.st_mode) else base_identity + (
        int(info.st_size),
        int(info.st_mtime_ns),
        int(info.st_ctime_ns),
    )
    return _windows_fsutil_reparse_tag_cached(
        os.path.normcase(os.path.abspath(os.fspath(path))),
        identity,
    )


def _windows_needs_long_path_query(path: os.PathLike[str] | str) -> bool:
    return len(os.path.abspath(os.fspath(path))) >= 260


def _windows_extended_path(path: os.PathLike[str] | str) -> str:
    """Build Win32 extended drive/UNC syntax without resolving any links."""
    value = os.path.abspath(os.fspath(path))
    if value.startswith("\\\\?\\"):
        return value
    if value.startswith("\\\\.\\"):
        raise PathSafetyError("device namespace is not a filesystem path")
    if value.startswith("\\\\"):
        return "\\\\?\\UNC\\" + value[2:]
    return "\\\\?\\" + value


def _windows_long_path_reparse_tag(path: os.PathLike[str] | str) -> int:
    """Perform FSCTL_GET_REPARSE_POINT on a second, fresh no-follow handle.

    Only ERROR_NOT_A_REPARSE_POINT (4390) is a negative. Returned tags remain
    positive evidence; missing paths, access errors, malformed buffers and
    handle-close failures reject the operation. The caller still checks its
    original FileAttributeTagInfo/FSCTL observations and complete path chain.
    """
    _attributes, dword, create_file, _information, control, close_handle = _windows_probe_api()
    handle = create_file(_windows_extended_path(path), 0, 0x1 | 0x2 | 0x4,
                         None, 3, 0x02000000 | 0x00200000, None)
    if handle == ctypes.c_void_p(-1).value:
        raise PathSafetyError(f"long-path cross-check CreateFileW failed for {path}: winerror={ctypes.get_last_error()}")
    try:
        buffer = ctypes.create_string_buffer(16 * 1024)
        returned = dword(0)
        if control(handle, 0x000900A8, None, 0, buffer, len(buffer), ctypes.byref(returned), None):
            if returned.value < 8 or returned.value > len(buffer):
                raise PathSafetyError(f"malformed long-path reparse buffer for {path}")
            tag = int.from_bytes(buffer.raw[:4], "little", signed=False)
            if tag == 0:
                raise PathSafetyError(f"empty long-path reparse tag for {path}")
            return tag
        error = ctypes.get_last_error()
        if error == 4390:
            return 0
        raise PathSafetyError(f"long-path cross-check FSCTL_GET_REPARSE_POINT failed for {path}: winerror={error}")
    finally:
        if not close_handle(handle):
            raise PathSafetyError(f"CloseHandle failed after long-path cross-check for {path}: winerror={ctypes.get_last_error()}")


@functools.lru_cache(maxsize=1)
def _windows_probe_api():
    """Bind immutable Win32 function signatures once, never path observations.

    Each probe below still opens a new handle and performs both native queries,
    the fsutil cross-check, and CloseHandle. Only DLL/type preparation is reused.
    """
    from ctypes import wintypes

    class FILE_ATTRIBUTE_TAG_INFO(ctypes.Structure):
        _fields_ = [("FileAttributes", wintypes.DWORD), ("ReparseTag", wintypes.DWORD)]

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    create_file = kernel32.CreateFileW
    create_file.argtypes = [
        wintypes.LPCWSTR,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.LPVOID,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.HANDLE,
    ]
    create_file.restype = wintypes.HANDLE
    get_information = kernel32.GetFileInformationByHandleEx
    get_information.argtypes = [wintypes.HANDLE, ctypes.c_int, wintypes.LPVOID, wintypes.DWORD]
    get_information.restype = wintypes.BOOL
    device_io_control = kernel32.DeviceIoControl
    device_io_control.argtypes = [
        wintypes.HANDLE,
        wintypes.DWORD,
        wintypes.LPVOID,
        wintypes.DWORD,
        wintypes.LPVOID,
        wintypes.DWORD,
        ctypes.POINTER(wintypes.DWORD),
        wintypes.LPVOID,
    ]
    device_io_control.restype = wintypes.BOOL
    close_handle = kernel32.CloseHandle
    close_handle.argtypes = [wintypes.HANDLE]
    close_handle.restype = wintypes.BOOL
    return (FILE_ATTRIBUTE_TAG_INFO, wintypes.DWORD, create_file,
            get_information, device_io_control, close_handle)


def native_path_identity(path: os.PathLike[str] | str) -> dict[str, Any]:
    """Return native link/reparse identity for one existing lexical path."""

    candidate = Path(path)
    if not candidate.exists() and not candidate.is_symlink():
        raise PathSafetyError(f"native path identity target is absent: {candidate}")
    if os.name != "nt":
        info = candidate.lstat()
        attributes = int(getattr(info, "st_file_attributes", 0))
        tag = int(getattr(info, "st_reparse_tag", 0))
        return {
            "file_attributes": attributes,
            "fsutil_reparse_tag": 0,
            "fsutil_cross_checked": False,
            "is_reparse": stat.S_ISLNK(info.st_mode)
            or bool(attributes & FILE_ATTRIBUTE_REPARSE_POINT)
            or tag != 0,
            "method": "POSIX_LSTAT_WITH_OPTIONAL_WINDOWS_FIELDS",
            "reparse_tag": tag,
        }

    (attribute_tag_info, dword, create_file, get_information,
     device_io_control, close_handle) = _windows_probe_api()

    share = 0x1 | 0x2 | 0x4
    flags = 0x02000000 | 0x00200000  # BACKUP_SEMANTICS | OPEN_REPARSE_POINT
    native_name = _windows_extended_path(candidate) if _windows_needs_long_path_query(candidate) else str(candidate)
    handle = create_file(native_name, 0, share, None, 3, flags, None)
    invalid_handle = ctypes.c_void_p(-1).value
    if handle == invalid_handle:
        raise PathSafetyError(
            f"CreateFileW reparse probe failed for {candidate}: winerror={ctypes.get_last_error()}"
        )
    close_error: int | None = None
    try:
        identity = attribute_tag_info()
        if not get_information(handle, 9, ctypes.byref(identity), ctypes.sizeof(identity)):
            raise PathSafetyError(
                f"FileAttributeTagInfo probe failed for {candidate}: winerror={ctypes.get_last_error()}"
            )
        attributes = int(identity.FileAttributes)
        attribute_tag = int(identity.ReparseTag)

        buffer = ctypes.create_string_buffer(16 * 1024)
        returned = dword(0)
        if device_io_control(
            handle,
            0x000900A8,  # FSCTL_GET_REPARSE_POINT
            None,
            0,
            buffer,
            len(buffer),
            ctypes.byref(returned),
            None,
        ):
            if returned.value < 8:
                raise PathSafetyError(f"truncated native reparse buffer for {candidate}")
            fsctl_tag = int.from_bytes(buffer.raw[:4], "little", signed=False)
        else:
            error = ctypes.get_last_error()
            if error == 4390:  # ERROR_NOT_A_REPARSE_POINT
                fsctl_tag = 0
            else:
                raise PathSafetyError(
                    f"FSCTL_GET_REPARSE_POINT failed for {candidate}: winerror={error}"
                )

        if attribute_tag and fsctl_tag and attribute_tag != fsctl_tag:
            raise PathSafetyError(
                f"inconsistent native reparse tags for {candidate}: "
                f"attribute=0x{attribute_tag:08x} fsctl=0x{fsctl_tag:08x}"
            )
        native_tag = fsctl_tag or attribute_tag
        # The custom Psync failure mode is a provider-root directory whose tag
        # is hidden from both ordinary handle probes.  Every leaf operation
        # checks its complete directory chain, so cross-check every directory
        # with trusted fsutil.  A regular leaf already reported as reparse is
        # also cross-checked; ordinary regular leaves avoid spawning a process
        # on every journal transition while still receiving both native handle
        # probes and the cross-checked ancestor chain. Long paths use a fresh
        # no-follow native handle because fsutil cannot open them reliably.
        is_directory = bool(attributes & 0x10)
        fsutil_cross_checked = is_directory or native_tag != 0 or bool(
            attributes & FILE_ATTRIBUTE_REPARSE_POINT
        )
        fsutil_tag = windows_fsutil_reparse_tag(candidate) if fsutil_cross_checked else 0
        long_path_cross_checked = fsutil_cross_checked and _windows_needs_long_path_query(candidate)
        if native_tag and fsutil_tag and native_tag != fsutil_tag:
            raise PathSafetyError(
                f"native/fsutil reparse-tag mismatch for {candidate}: "
                f"native=0x{native_tag:08x} fsutil=0x{fsutil_tag:08x}"
            )
        tag = fsutil_tag or native_tag
        return {
            "file_attributes": attributes,
            "fsutil_reparse_tag": 0 if long_path_cross_checked else fsutil_tag,
            "fsutil_cross_checked": fsutil_cross_checked and not long_path_cross_checked,
            "long_path_reparse_tag": fsutil_tag if long_path_cross_checked else 0,
            "long_path_cross_checked": long_path_cross_checked,
            "is_reparse": bool(attributes & FILE_ATTRIBUTE_REPARSE_POINT) or tag != 0,
            "method": "WIN32_FRESH_LONG_PATH_FSCTL_AND_FILE_ATTRIBUTE_TAG_INFO" if long_path_cross_checked else "WIN32_FSUTIL_FSCTL_AND_FILE_ATTRIBUTE_TAG_INFO",
            "reparse_tag": tag,
        }
    finally:
        if not close_handle(handle):
            close_error = ctypes.get_last_error()
        if close_error is not None:
            raise PathSafetyError(
                f"CloseHandle failed after reparse probe for {candidate}: winerror={close_error}"
            )


def is_reparse_or_link(path: os.PathLike[str] | str) -> bool:
    return bool(native_path_identity(path)["is_reparse"])


def reject_reparse_chain(
    raw: os.PathLike[str] | str,
    *,
    label: str = "path",
    must_exist: bool = True,
) -> Path:
    """Check every lexical component up to the volume/root, without resolve."""

    path = lexical_absolute(raw, label=label)
    if must_exist and not path.exists() and not path.is_symlink():
        raise PathSafetyError(f"{label} is absent: {path}")
    cursor = path if must_exist or path.exists() or path.is_symlink() else path.parent
    while True:
        if cursor.exists() or cursor.is_symlink():
            if is_reparse_or_link(cursor):
                raise PathSafetyError(f"{label} path chain contains link/reparse: {cursor}")
        parent = cursor.parent
        if parent == cursor:
            break
        cursor = parent
    return path


def assert_single_link(path: os.PathLike[str] | str, *, label: str = "file") -> None:
    info = Path(path).stat(follow_symlinks=False)
    if info.st_nlink != 1:
        raise PathSafetyError(
            f"{label} must have exactly one hardlink: {path} (st_nlink={info.st_nlink})"
        )


def plain_file(
    raw: os.PathLike[str] | str,
    *,
    label: str = "file",
    single_link: bool = True,
) -> Path:
    path = reject_reparse_chain(raw, label=label, must_exist=True)
    info = path.stat(follow_symlinks=False)
    if not stat.S_ISREG(info.st_mode):
        raise PathSafetyError(f"{label} is not a regular file: {path}")
    if single_link:
        assert_single_link(path, label=label)
    return path


def _file_snapshot(info: os.stat_result) -> tuple[int, ...]:
    """Return fields that bind a path and an opened file to the same bytes."""

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


def _cross_handle_binding(snapshot: tuple[int, ...]) -> tuple[int, ...]:
    """Bind path and handle identity without Windows' ctime representation.

    CPython 3.12 on Windows can report the same NTFS change time with slightly
    different nanosecond values through ``Path.stat`` and ``os.fstat``.  The
    complete ctime remains mutation-sensitive within each observation domain;
    only the cross-domain comparison omits that one field.
    """

    # _file_snapshot field 6 is st_ctime_ns.  Every other identity, byte-size
    # and mutation-sensitive field remains in the cross-handle binding.
    return snapshot[:6] + snapshot[7:]


def stable_plain_bytes(
    raw: os.PathLike[str] | str,
    *,
    label: str = "file",
) -> bytes:
    """Read one plain single-link file and reject swaps or in-place mutation.

    The lexical chain is checked both before and after opening.  The opened
    Full path snapshots must remain equal to each other, as must full handle
    snapshots.  Cross-domain identity/size/mutation fields must also agree,
    except for CPython/Windows' alternate representation of the same NTFS
    change time.  This closes the common ``check path; reopen path`` race for
    mutable controls and immutable authorities without hiding ctime mutation
    inside either observation domain.
    """

    try:
        checked = plain_file(raw, label=label, single_link=True)
        before_path = checked.stat(follow_symlinks=False)
        before_path_snapshot = _file_snapshot(before_path)
        with checked.open("rb") as handle:
            opened_before = os.fstat(handle.fileno())
            opened_before_snapshot = _file_snapshot(opened_before)
            if _cross_handle_binding(opened_before_snapshot) != _cross_handle_binding(
                before_path_snapshot
            ):
                raise PathSafetyError(f"{label} changed between path check and open: {checked}")
            chunks: list[bytes] = []
            while True:
                block = handle.read(1024 * 1024)
                if not block:
                    break
                chunks.append(block)
            opened_after = os.fstat(handle.fileno())
            opened_after_snapshot = _file_snapshot(opened_after)
        checked_after = plain_file(raw, label=label, single_link=True)
        after_path = checked_after.stat(follow_symlinks=False)
        after_path_snapshot = _file_snapshot(after_path)
    except PathSafetyError:
        raise
    except OSError as exc:
        raise PathSafetyError(f"{label} cannot be read safely: {raw}: {exc}") from exc
    if (
        before_path_snapshot != after_path_snapshot
        or opened_before_snapshot != opened_after_snapshot
        or len(
            {
                _cross_handle_binding(snapshot)
                for snapshot in (
                    before_path_snapshot,
                    opened_before_snapshot,
                    opened_after_snapshot,
                    after_path_snapshot,
                )
            }
        )
        != 1
    ):
        raise PathSafetyError(f"{label} changed while it was read: {checked}")
    data = b"".join(chunks)
    if len(data) != int(after_path.st_size):
        raise PathSafetyError(f"{label} byte count changed while it was read: {checked}")
    return data


def plain_directory(raw: os.PathLike[str] | str, *, label: str = "directory") -> Path:
    path = reject_reparse_chain(raw, label=label, must_exist=True)
    info = path.stat(follow_symlinks=False)
    if not stat.S_ISDIR(info.st_mode):
        raise PathSafetyError(f"{label} is not a directory: {path}")
    return path


def _raise_as(error_type: Type[Exception], message: str, exc: BaseException | None = None) -> None:
    error = error_type(message)
    if exc is None:
        raise error
    raise error from exc


def _native_rename_no_replace(src: Path, dst: Path) -> None:
    if os.name == "nt":
        from ctypes import wintypes

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        move_file_ex = kernel32.MoveFileExW
        move_file_ex.argtypes = [wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.DWORD]
        move_file_ex.restype = wintypes.BOOL
        # MOVEFILE_WRITE_THROUGH only.  MOVEFILE_REPLACE_EXISTING is
        # intentionally absent, so a destination created in the race wins.
        if not move_file_ex(_windows_extended_path(src), _windows_extended_path(dst), 0x00000008):
            error = ctypes.get_last_error()
            raise OSError(error, f"MoveFileExW no-replace failed (winerror={error})", str(dst))
    elif os.name == "posix" and "linux" in os.sys.platform:
        libc = ctypes.CDLL(None, use_errno=True)
        renameat2 = getattr(libc, "renameat2", None)
        if renameat2 is None:
            raise OSError(errno.ENOSYS, "renameat2 is unavailable")
        renameat2.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_uint]
        renameat2.restype = ctypes.c_int
        result = renameat2(-100, os.fsencode(src), -100, os.fsencode(dst), 1)
        if result != 0:
            code = ctypes.get_errno()
            raise OSError(code, os.strerror(code), str(dst))
    else:
        raise OSError(errno.ENOTSUP, "no-replace rename is unsupported on this platform")


def rename_directory_no_replace(
    source: os.PathLike[str] | str,
    destination: os.PathLike[str] | str,
    *,
    error_type: Type[Exception] = PathSafetyError,
) -> None:
    """Rename one sibling directory using a real no-replace primitive."""

    try:
        src = plain_directory(source, label="rename source")
        dst = lexical_absolute(destination, label="rename destination")
        reject_reparse_chain(dst, label="rename destination", must_exist=False)
        if src.parent != dst.parent:
            raise PathSafetyError("no-replace directory rename requires sibling paths")
        if dst.exists() or dst.is_symlink():
            raise FileExistsError(errno.EEXIST, "destination already exists", str(dst))

        _native_rename_no_replace(src, dst)

        # Re-open the result through the same strong identity boundary.
        plain_directory(dst, label="renamed destination")
        if src.exists() or src.is_symlink():
            raise PathSafetyError("no-replace rename left the source present")
    except BaseException as exc:
        if isinstance(exc, error_type):
            raise
        _raise_as(error_type, f"directory no-replace rename failed: {exc}", exc)


def rename_file_no_replace(
    source: os.PathLike[str] | str,
    destination: os.PathLike[str] | str,
    *,
    error_type: Type[Exception] = PathSafetyError,
) -> None:
    """Rename one sibling single-link regular file without replacement."""

    try:
        src = plain_file(source, label="rename source file", single_link=True)
        dst = lexical_absolute(destination, label="rename destination file")
        reject_reparse_chain(dst, label="rename destination file", must_exist=False)
        if src.parent != dst.parent:
            raise PathSafetyError("no-replace file rename requires sibling paths")
        if dst.exists() or dst.is_symlink():
            raise FileExistsError(errno.EEXIST, "destination already exists", str(dst))
        _native_rename_no_replace(src, dst)
        plain_file(dst, label="renamed destination file", single_link=True)
        if src.exists() or src.is_symlink():
            raise PathSafetyError("no-replace file rename left the source present")
    except BaseException as exc:
        if isinstance(exc, error_type):
            raise
        _raise_as(error_type, f"file no-replace rename failed: {exc}", exc)


__all__ = [
    "FILE_ATTRIBUTE_REPARSE_POINT",
    "PathSafetyError",
    "assert_single_link",
    "is_reparse_or_link",
    "lexical_absolute",
    "native_path_identity",
    "plain_directory",
    "plain_file",
    "reject_reparse_chain",
    "rename_directory_no_replace",
    "rename_file_no_replace",
    "stable_plain_bytes",
    "windows_fsutil_reparse_tag",
]
