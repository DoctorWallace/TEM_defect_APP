"""Immutable ROI revision publication and verification for Prompt 1."""

from __future__ import annotations

import io
import os
import re
import stat
import uuid
import zipfile
from dataclasses import dataclass
from decimal import Decimal
from datetime import datetime
from pathlib import Path, PurePosixPath
from typing import Any, Callable, Mapping

from .canonical_json import PROFILE_ID, canonical_json_bytes, loads_canonical_json
from .critical_io import (
    AtomicMoveProof,
    CriticalWriteResult,
    RETENTION_POLICY,
    critical_replace,
    fsync_directory,
    sha256_bytes,
    sha256_file,
    utc_now_z,
    write_new_file,
)
from .errors import TransactionError, ValidationError
from .path_safety import (
    PathSafetyError,
    is_reparse_or_link,
    lexical_absolute,
    plain_directory,
    plain_file,
    stable_plain_bytes,
)
from .run_consumer import validate_relative_path
from .run_transaction import DirectoryPublishResult, publish_directory_no_replace


REVISION_CONTROL_SET = frozenset({"revision_manifest.json", "REVISION_SHA256.txt", "COMPLETE"})
REVISION_ROI_NAME = "cavity_rois.zip"
SHA_RE = re.compile(r"^[0-9a-f]{64}$")
UUID_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")
ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
UTC_Z_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d*[1-9])?Z$")

FaultHook = Callable[[str, Mapping[str, Any]], None]


@dataclass(frozen=True)
class RevisionBinding:
    project_uid: str
    image_uid: str
    analysis_session_uid: str
    revision_id: str
    revision_uid: str
    parent_revision_id: str
    source_sha256: str
    master_pixel_sha256: str


@dataclass(frozen=True)
class VerifiedRevision:
    path: Path
    manifest: dict[str, Any]
    manifest_sha256: str
    marker: dict[str, str]


@dataclass(frozen=True)
class PublishedRevision:
    path: Path
    verified: VerifiedRevision
    directory_atomic_move_capability: str
    pointer_write: CriticalWriteResult | None
    retention_policy: str = RETENTION_POLICY


@dataclass(frozen=True)
class VerifiedRevisionPointer:
    path: Path
    pointer: dict[str, Any]
    pointer_sha256: str
    target: VerifiedRevision


def _require_binding(binding: RevisionBinding) -> None:
    for field in ("project_uid", "image_uid", "analysis_session_uid", "revision_uid"):
        value = getattr(binding, field)
        if not UUID_RE.fullmatch(value) or str(uuid.UUID(value)) != value:
            raise ValidationError("revision UUID is not canonical", details={"field": field, "value": value})
    if not ID_RE.fullmatch(binding.revision_id) or binding.revision_id in {".", "..", "UNKNOWN", "NOT_APPLICABLE"}:
        raise ValidationError("revision_id is not canonical")
    if binding.parent_revision_id != "NOT_APPLICABLE" and not ID_RE.fullmatch(binding.parent_revision_id):
        raise ValidationError("parent_revision_id is invalid")
    for field in ("source_sha256", "master_pixel_sha256"):
        if not SHA_RE.fullmatch(getattr(binding, field)):
            raise ValidationError("revision source/master hash is invalid", details={"field": field})


def _validate_utc_z(value: Any, *, field: str) -> str:
    if not isinstance(value, str) or not UTC_Z_RE.fullmatch(value):
        raise ValidationError("revision timestamp is not canonical UTC Z", details={"field": field, "value": value})
    base, separator, fraction = value[:-1].partition(".")
    try:
        datetime.strptime(base, "%Y-%m-%dT%H:%M:%S")
    except ValueError as exc:
        raise ValidationError("revision timestamp is not a real calendar time", details={"field": field}) from exc
    if separator and (not fraction.isdigit() or len(fraction) > 6):
        raise ValidationError("revision fractional second is invalid", details={"field": field})
    return value


def _is_link_or_reparse(path: Path) -> bool:
    try:
        return is_reparse_or_link(path)
    except PathSafetyError as exc:
        raise ValidationError(
            "native revision path identity could not be established",
            details={"path": str(path), "cause": str(exc)},
        ) from exc


def _validate_roi_zip(data: bytes) -> None:
    try:
        with zipfile.ZipFile(io.BytesIO(data), "r") as archive:
            seen: set[str] = set()
            seen_folded: set[str] = set()
            for info in archive.infolist():
                name = info.filename
                if info.is_dir():
                    raise ValidationError("ROI ZIP may not contain directory entries", details={"entry": name})
                validate_relative_path(name, stage="REVISION_ZIP")
                folded = name.casefold()
                if name in seen or folded in seen_folded:
                    raise ValidationError("ROI ZIP contains duplicate/case-colliding entry", details={"entry": name})
                seen.add(name)
                seen_folded.add(folded)
                unix_mode = (info.external_attr >> 16) & 0xFFFF
                if stat.S_ISLNK(unix_mode):
                    raise ValidationError("ROI ZIP contains a symlink", details={"entry": name})
            bad = archive.testzip()
            if bad is not None:
                raise ValidationError("ROI ZIP CRC failed", details={"entry": bad})
    except zipfile.BadZipFile as exc:
        raise ValidationError("ROI authority is not a valid ZIP") from exc


def _revision_sidecar(manifest_sha256: str) -> bytes:
    if not SHA_RE.fullmatch(manifest_sha256):
        raise ValidationError("revision manifest SHA-256 is invalid")
    return f"{manifest_sha256}  revision_manifest.json\n".encode("ascii")


def _parse_revision_sidecar(data: bytes) -> str:
    try:
        text = data.decode("ascii")
    except UnicodeDecodeError as exc:
        raise ValidationError("revision sidecar is not ASCII") from exc
    match = re.fullmatch(r"([0-9a-f]{64})  revision_manifest\.json\n", text)
    if match is None:
        raise ValidationError("revision sidecar format is invalid")
    return match.group(1)


def _revision_marker(binding: RevisionBinding, manifest_sha256: str, roi_zip_sha256: str, completed_at: str) -> bytes:
    _validate_utc_z(completed_at, field="completed_at")
    rows = (
        ("marker_version", "1"),
        ("revision_id", binding.revision_id),
        ("revision_uid", binding.revision_uid),
        ("project_uid", binding.project_uid),
        ("image_uid", binding.image_uid),
        ("analysis_session_uid", binding.analysis_session_uid),
        ("revision_manifest_sha256", manifest_sha256),
        ("roi_zip_sha256", roi_zip_sha256),
        ("source_sha256", binding.source_sha256),
        ("master_pixel_sha256", binding.master_pixel_sha256),
        ("completed_at", completed_at),
    )
    return ("".join(f"{key}\t{value}\n" for key, value in rows)).encode("ascii")


def _parse_revision_marker(data: bytes) -> dict[str, str]:
    try:
        text = data.decode("ascii")
    except UnicodeDecodeError as exc:
        raise ValidationError("revision marker is not ASCII") from exc
    if b"\r" in data or not data.endswith(b"\n"):
        raise ValidationError("revision marker newline profile is invalid")
    expected = (
        "marker_version",
        "revision_id",
        "revision_uid",
        "project_uid",
        "image_uid",
        "analysis_session_uid",
        "revision_manifest_sha256",
        "roi_zip_sha256",
        "source_sha256",
        "master_pixel_sha256",
        "completed_at",
    )
    lines = text.splitlines()
    if len(lines) != len(expected):
        raise ValidationError("revision marker field count is invalid")
    result: dict[str, str] = {}
    for key, line in zip(expected, lines):
        if line.count("\t") != 1:
            raise ValidationError("revision marker line is invalid", details={"line": line})
        actual, value = line.split("\t")
        if actual != key or not value:
            raise ValidationError("revision marker order/value is invalid", details={"expected": key, "actual": actual})
        result[key] = value
    if result["marker_version"] != "1":
        raise ValidationError("revision marker version/time is invalid")
    _validate_utc_z(result["completed_at"], field="completed_at")
    for field in ("revision_uid", "project_uid", "image_uid", "analysis_session_uid"):
        if not UUID_RE.fullmatch(result[field]):
            raise ValidationError("revision marker UUID is invalid", details={"field": field})
    for field in ("revision_manifest_sha256", "roi_zip_sha256", "source_sha256", "master_pixel_sha256"):
        if not SHA_RE.fullmatch(result[field]):
            raise ValidationError("revision marker hash is invalid", details={"field": field})
    return result


def _enumerate_revision(path: Path) -> set[str]:
    result: set[str] = set()

    def visit(directory: Path) -> None:
        try:
            entries = sorted(os.scandir(directory), key=lambda entry: entry.name)
        except OSError as exc:
            raise ValidationError("revision cannot be enumerated", details={"path": str(directory)}) from exc
        if directory != path and not entries:
            raise ValidationError("revision contains an empty directory", details={"path": str(directory)})
        for entry in entries:
            item = Path(entry.path)
            try:
                if is_reparse_or_link(item):
                    raise PathSafetyError(f"linked/reparse entry: {item}")
                if entry.is_dir(follow_symlinks=False):
                    plain_directory(item, label="revision directory")
                    visit(item)
                    continue
                plain_file(item, label="revision immutable file", single_link=True)
            except PathSafetyError as exc:
                raise ValidationError(
                    "revision contains an unsafe entry",
                    details={"path": str(item), "cause": str(exc)},
                ) from exc
            relative = item.relative_to(path).as_posix()
            validate_relative_path(relative, stage="REVISION_INVENTORY")
            result.add(relative)

    visit(path)
    return result


def _validate_revision_manifest(manifest: Mapping[str, Any]) -> None:
    exact = {
        "descriptor_type": "revision",
        "revision_contract_version": 1,
        "revision_state": "COMPLETE",
        "serialization_profile": PROFILE_ID,
    }
    for field, expected in exact.items():
        if manifest.get(field) != expected:
            raise ValidationError("revision manifest field is invalid", details={"field": field})
    if "revision_manifest_sha256" in manifest:
        raise ValidationError("revision manifest must not contain its own hash")
    binding = RevisionBinding(
        project_uid=str(manifest.get("project_uid")),
        image_uid=str(manifest.get("image_uid")),
        analysis_session_uid=str(manifest.get("analysis_session_uid")),
        revision_id=str(manifest.get("revision_id")),
        revision_uid=str(manifest.get("revision_uid")),
        parent_revision_id=str(manifest.get("parent_revision_id")),
        source_sha256=str(manifest.get("source_sha256")),
        master_pixel_sha256=str(manifest.get("master_pixel_sha256")),
    )
    _require_binding(binding)
    if not SHA_RE.fullmatch(str(manifest.get("roi_zip_sha256"))):
        raise ValidationError("revision ROI hash is invalid")
    files = manifest.get("files")
    if not isinstance(files, list) or not files:
        raise ValidationError("revision files inventory is absent")
    previous = ""
    seen: set[str] = set()
    for record in files:
        if not isinstance(record, dict) or set(record) != {"relative_path", "bytes", "sha256", "media_type", "authority_role"}:
            raise ValidationError("revision file record fields are invalid")
        relative = validate_relative_path(record["relative_path"], stage="REVISION_MANIFEST")
        if relative in REVISION_CONTROL_SET or relative in seen or (previous and relative < previous):
            raise ValidationError("revision files is duplicated/unsorted or contains a control")
        seen.add(relative)
        previous = relative
        size = record["bytes"]
        if (
            isinstance(size, bool)
            or not isinstance(size, (int, Decimal))
            or size != int(size)
            or size < 0
            or not SHA_RE.fullmatch(record["sha256"])
        ):
            raise ValidationError("revision file hash/size record is invalid")
    if REVISION_ROI_NAME not in seen:
        raise ValidationError("revision files omits cavity_rois.zip")


def verify_revision(
    revision_path: os.PathLike[str] | str,
    *,
    source_path: os.PathLike[str] | str | None = None,
    master_pixel_bytes: bytes | None = None,
) -> VerifiedRevision:
    try:
        path = plain_directory(revision_path, label="revision directory")
    except PathSafetyError as exc:
        raise ValidationError("revision path is unsafe", details={"cause": str(exc)}) from exc
    if path.name.endswith(".partial") or not path.name.startswith("REV_"):
        raise ValidationError("revision path is not a published final directory")
    actual = _enumerate_revision(path)
    if not REVISION_CONTROL_SET.issubset(actual):
        raise ValidationError("revision control set is incomplete")
    try:
        marker_bytes = stable_plain_bytes(path / "COMPLETE", label="revision COMPLETE marker")
        sidecar_bytes = stable_plain_bytes(path / "REVISION_SHA256.txt", label="revision SHA-256 sidecar")
        manifest_bytes = stable_plain_bytes(path / "revision_manifest.json", label="revision manifest")
    except PathSafetyError as exc:
        raise ValidationError(
            "revision control bytes cannot be read safely",
            details={"cause": str(exc)},
        ) from exc
    marker = _parse_revision_marker(marker_bytes)
    sidecar_hash = _parse_revision_sidecar(sidecar_bytes)
    if marker["revision_manifest_sha256"] != sidecar_hash:
        raise ValidationError("revision marker and sidecar disagree")
    manifest_path = path / "revision_manifest.json"
    if sha256_bytes(manifest_bytes) != sidecar_hash:
        raise ValidationError("revision manifest hash differs from controls")
    manifest = loads_canonical_json(manifest_bytes)
    _validate_revision_manifest(manifest)
    for field in ("revision_id", "revision_uid", "project_uid", "image_uid", "analysis_session_uid", "roi_zip_sha256", "source_sha256", "master_pixel_sha256"):
        if marker[field] != str(manifest[field]):
            raise ValidationError("revision marker/manifest identity mismatch", details={"field": field})
    if path.name != f"REV_{manifest['revision_id']}":
        raise ValidationError("revision directory name differs from revision_id")
    files = manifest["files"]
    expected = set(REVISION_CONTROL_SET) | {str(item["relative_path"]) for item in files}
    if actual != expected:
        raise ValidationError("revision directory inventory is not exact", details={"missing": sorted(expected - actual), "extra": sorted(actual - expected)})
    payload_bytes: dict[str, bytes] = {}
    for record in files:
        payload = path.joinpath(*Path(record["relative_path"]).parts)
        try:
            data = stable_plain_bytes(payload, label=f"revision payload {record['relative_path']}")
        except PathSafetyError as exc:
            raise ValidationError(
                "revision payload cannot be read safely",
                details={"relative_path": record["relative_path"], "cause": str(exc)},
            ) from exc
        if len(data) != int(record["bytes"]) or sha256_bytes(data) != record["sha256"]:
            raise ValidationError("revision payload differs from manifest", details={"relative_path": record["relative_path"]})
        payload_bytes[str(record["relative_path"])] = data
    roi_bytes = payload_bytes[REVISION_ROI_NAME]
    if sha256_bytes(roi_bytes) != manifest["roi_zip_sha256"]:
        raise ValidationError("revision ROI ZIP hash mismatch")
    _validate_roi_zip(roi_bytes)
    if source_path is not None:
        try:
            checked_source = plain_file(source_path, label="revision source", single_link=True)
        except PathSafetyError as exc:
            raise ValidationError("live source path is unsafe", details={"cause": str(exc)}) from exc
        if sha256_file(checked_source) != manifest["source_sha256"]:
            raise ValidationError("live source bytes differ from revision binding")
    if master_pixel_bytes is not None and sha256_bytes(master_pixel_bytes) != manifest["master_pixel_sha256"]:
        raise ValidationError("live master pixel bytes differ from revision binding")
    return VerifiedRevision(path=path, manifest=manifest, manifest_sha256=sidecar_hash, marker=marker)


def _validate_revision_pointer_value(value: Mapping[str, Any]) -> None:
    required = {
        "pointer_version",
        "project_uid",
        "image_uid",
        "analysis_session_uid",
        "revision_id",
        "revision_uid",
        "relative_path",
        "revision_manifest_sha256",
        "generation",
        "updated_at",
    }
    if set(value) != required or value["pointer_version"] != 1:
        raise ValidationError("current revision pointer fields/version are invalid")
    validate_relative_path(value["relative_path"], stage="REVISION_POINTER")
    if str(value["relative_path"]).lower().endswith(".partial"):
        raise ValidationError("current revision pointer may not address a partial")
    for field in ("project_uid", "image_uid", "analysis_session_uid", "revision_uid"):
        item = value[field]
        if not isinstance(item, str) or not UUID_RE.fullmatch(item) or str(uuid.UUID(item)) != item:
            raise ValidationError("current revision pointer UUID is invalid", details={"field": field})
    if not isinstance(value["revision_id"], str) or not ID_RE.fullmatch(value["revision_id"]):
        raise ValidationError("current revision pointer ID is invalid")
    if not SHA_RE.fullmatch(value["revision_manifest_sha256"]):
        raise ValidationError("current revision pointer hash is invalid")
    generation = value["generation"]
    if isinstance(generation, bool) or not isinstance(generation, (int, Decimal)) or generation != int(generation) or generation < 1:
        raise ValidationError("current revision pointer generation is invalid")
    _validate_utc_z(value["updated_at"], field="updated_at")


def _validate_revision_pointer(path: Path) -> None:
    try:
        raw = stable_plain_bytes(path, label="current revision pointer")
    except PathSafetyError as exc:
        raise ValidationError("current revision pointer path is unsafe", details={"cause": str(exc)}) from exc
    _validate_revision_pointer_value(loads_canonical_json(raw))


def verify_revision_pointer(
    pointer_path: os.PathLike[str] | str,
    *,
    project_root: os.PathLike[str] | str,
    source_path: os.PathLike[str] | str | None = None,
) -> VerifiedRevisionPointer:
    """Verify a current-revision pointer and the immutable target it names.

    Historical loading may select a revision other than this target, but the
    current pointer must still be internally coherent and is never advanced by
    the read-only load operation.
    """

    try:
        root = plain_directory(project_root, label="revision project root")
        pointer_path_resolved = plain_file(
            pointer_path,
            label="current revision pointer",
            single_link=True,
        )
    except PathSafetyError as exc:
        raise ValidationError("revision pointer path is unsafe", details={"cause": str(exc)}) from exc
    try:
        pointer_path_resolved.relative_to(root)
    except ValueError as exc:
        raise ValidationError("current revision pointer escapes project root") from exc
    try:
        pointer_bytes = stable_plain_bytes(
            pointer_path_resolved,
            label="current revision pointer",
        )
    except PathSafetyError as exc:
        raise ValidationError("current revision pointer changed during verification") from exc
    _validate_revision_pointer_value(loads_canonical_json(pointer_bytes))
    pointer = dict(loads_canonical_json(pointer_bytes))
    relative = validate_relative_path(pointer["relative_path"], stage="REVISION_POINTER")
    target = root.joinpath(*PurePosixPath(relative).parts)
    try:
        target.relative_to(root)
    except ValueError as exc:
        raise ValidationError("current revision target escapes project root") from exc
    verified = verify_revision(target, source_path=source_path)
    expected = {
        "project_uid": verified.manifest["project_uid"],
        "image_uid": verified.manifest["image_uid"],
        "analysis_session_uid": verified.manifest["analysis_session_uid"],
        "revision_id": verified.manifest["revision_id"],
        "revision_uid": verified.manifest["revision_uid"],
        "revision_manifest_sha256": verified.manifest_sha256,
    }
    for field, value in expected.items():
        if pointer[field] != value:
            raise ValidationError(
                "current revision pointer and target do not reconcile",
                details={"field": field},
            )
    if target.relative_to(root).as_posix() != relative:
        raise ValidationError("current revision pointer path is not canonical")
    try:
        pointer_after = stable_plain_bytes(
            pointer_path_resolved,
            label="current revision pointer",
        )
    except PathSafetyError as exc:
        raise ValidationError("current revision pointer changed during target verification") from exc
    if pointer_after != pointer_bytes:
        raise ValidationError("current revision pointer changed during target verification")
    return VerifiedRevisionPointer(
        path=pointer_path_resolved,
        pointer=pointer,
        pointer_sha256=sha256_bytes(pointer_bytes),
        target=verified,
    )


def publish_revision(
    revision_parent: os.PathLike[str] | str,
    *,
    binding: RevisionBinding,
    roi_zip_bytes: bytes,
    metadata: Mapping[str, Any] | None = None,
    current_pointer_path: os.PathLike[str] | str | None = None,
    project_root: os.PathLike[str] | str | None = None,
    atomic_capability: str = "UNKNOWN",
    atomic_proof: AtomicMoveProof | None = None,
    on_published: Callable[[VerifiedRevision], None] | None = None,
    _fault: FaultHook | None = None,
) -> PublishedRevision:
    """Publish all revision artifacts before updating pointers or live globals."""

    _require_binding(binding)
    _validate_roi_zip(roi_zip_bytes)
    try:
        parent = plain_directory(revision_parent, label="revision parent")
    except PathSafetyError as exc:
        raise TransactionError("revision parent is unsafe", details={"cause": str(exc)}) from exc
    root: Path | None = None
    pointer_path: Path | None = None
    old_generation = 0
    expected_pointer_sha256 = "NOT_APPLICABLE"
    if current_pointer_path is not None:
        if project_root is None:
            raise TransactionError("project_root is required with current revision pointer")
        try:
            root = plain_directory(project_root, label="revision project root")
            parent.relative_to(root)
            pointer_path = lexical_absolute(
                current_pointer_path,
                label="current revision pointer",
            )
            if pointer_path.exists() or pointer_path.is_symlink():
                pointer_path = plain_file(
                    pointer_path,
                    label="current revision pointer",
                    single_link=True,
                )
                old_pointer_bytes = stable_plain_bytes(
                    pointer_path,
                    label="current revision pointer caller snapshot",
                )
                expected_pointer_sha256 = sha256_bytes(old_pointer_bytes)
                old_pointer = loads_canonical_json(old_pointer_bytes)
                _validate_revision_pointer_value(old_pointer)
                if old_pointer["analysis_session_uid"] != binding.analysis_session_uid:
                    raise TransactionError("revision pointer belongs to another session")
                old_generation = int(old_pointer["generation"])
            else:
                plain_directory(
                    pointer_path.parent,
                    label="current revision pointer parent",
                )
            pointer_path.relative_to(root)
        except (PathSafetyError, ValueError) as exc:
            raise TransactionError(
                "current revision pointer path is unsafe",
                details={"cause": str(exc)},
            ) from exc
    partial = parent / f"REV_{binding.revision_id}.partial"
    final = parent / f"REV_{binding.revision_id}"
    if partial.exists() or partial.is_symlink() or final.exists() or final.is_symlink():
        raise TransactionError("revision identity already exists")
    partial.mkdir()
    fsync_directory(parent)
    if _fault:
        _fault("REV_PARTIAL_CREATED", {"partial": str(partial)})
    try:
        payloads: dict[str, tuple[bytes, str, str]] = {
            REVISION_ROI_NAME: (roi_zip_bytes, "application/zip", "REVISION_AUTHORITY")
        }
        if metadata is not None:
            payloads["revision_metadata.json"] = (
                canonical_json_bytes(dict(metadata)),
                "application/json; charset=utf-8",
                "REVISION_AUTHORITY",
            )
        records: list[dict[str, Any]] = []
        for relative, (data, media_type, role) in sorted(payloads.items()):
            write_new_file(partial / relative, data)
            records.append(
                {
                    "relative_path": relative,
                    "bytes": len(data),
                    "sha256": sha256_bytes(data),
                    "media_type": media_type,
                    "authority_role": role,
                }
            )
            if _fault:
                _fault(f"REV_PAYLOAD_WRITTEN:{relative}", {"partial": str(partial)})
        roi_hash = sha256_bytes(roi_zip_bytes)
        completed_at = utc_now_z()
        manifest = {
            "descriptor_type": "revision",
            "revision_contract_version": 1,
            "revision_state": "COMPLETE",
            "serialization_profile": PROFILE_ID,
            "project_uid": binding.project_uid,
            "image_uid": binding.image_uid,
            "analysis_session_uid": binding.analysis_session_uid,
            "revision_id": binding.revision_id,
            "revision_uid": binding.revision_uid,
            "parent_revision_id": binding.parent_revision_id,
            "source_sha256": binding.source_sha256,
            "master_pixel_sha256": binding.master_pixel_sha256,
            "roi_zip_sha256": roi_hash,
            "published_at": completed_at,
            "files": records,
        }
        _validate_revision_manifest(manifest)
        manifest_bytes = canonical_json_bytes(manifest)
        manifest_hash = sha256_bytes(manifest_bytes)
        write_new_file(partial / "revision_manifest.json", manifest_bytes)
        write_new_file(partial / "REVISION_SHA256.txt", _revision_sidecar(manifest_hash))
        write_new_file(partial / "COMPLETE", _revision_marker(binding, manifest_hash, roi_hash, completed_at))
        if _fault:
            _fault("REV_COMPLETE_STAGED", {"partial": str(partial), "revision_manifest_sha256": manifest_hash})

        # The normal verifier rejects .partial by design.  Move without replace,
        # then verify immediately; no pointer/global has moved yet.
        directory_result: DirectoryPublishResult = publish_directory_no_replace(
            partial,
            final,
            verifier=lambda candidate: verify_revision(candidate),
            atomic_capability=atomic_capability,
            atomic_proof=atomic_proof,
        )
        verified = verify_revision(directory_result.final_path)
        pointer_write: CriticalWriteResult | None = None
        if current_pointer_path is not None:
            if root is None or pointer_path is None:
                raise TransactionError("revision pointer preflight state is unavailable")
            relative = verified.path.relative_to(root).as_posix()
            validate_relative_path(relative, stage="REVISION_POINTER")
            pointer = {
                "pointer_version": 1,
                "project_uid": binding.project_uid,
                "image_uid": binding.image_uid,
                "analysis_session_uid": binding.analysis_session_uid,
                "revision_id": binding.revision_id,
                "revision_uid": binding.revision_uid,
                "relative_path": relative,
                "revision_manifest_sha256": verified.manifest_sha256,
                "generation": old_generation + 1,
                "updated_at": utc_now_z(),
            }
            pointer_write = critical_replace(
                pointer_path,
                canonical_json_bytes(pointer),
                validator=_validate_revision_pointer,
                atomic_capability=atomic_capability,
                atomic_proof=atomic_proof,
                transaction_id=f"revision_pointer_{old_generation + 1}",
                expected_target_sha256=expected_pointer_sha256,
            )
            if pointer_write.journal_state != "COMMITTED":
                raise TransactionError("revision pointer update rolled back")
        if on_published is not None:
            on_published(verified)
        return PublishedRevision(
            path=verified.path,
            verified=verified,
            directory_atomic_move_capability=directory_result.atomic_move_capability,
            pointer_write=pointer_write,
        )
    except BaseException:
        # Fail-closed: retained partial/final evidence is never auto-deleted and
        # callback/global advancement happens only after complete verification.
        raise


def make_revision_verifier(
    revision_path: os.PathLike[str] | str,
    *,
    source_path: os.PathLike[str] | str | None = None,
    master_pixel_bytes: bytes | None = None,
) -> Callable[[Mapping[str, Any]], bool]:
    """Build the RUN consumer's revision/source/master reconciliation hook."""

    def verify_run_binding(run_manifest: Mapping[str, Any]) -> bool:
        verified = verify_revision(
            revision_path,
            source_path=source_path,
            master_pixel_bytes=master_pixel_bytes,
        )
        expected = {
            "project_uid": verified.manifest["project_uid"],
            "image_uid": verified.manifest["image_uid"],
            "analysis_session_uid": verified.manifest["analysis_session_uid"],
            "revision_id": verified.manifest["revision_id"],
            "revision_uid": verified.manifest["revision_uid"],
            "source_sha256": verified.manifest["source_sha256"],
            "master_pixel_sha256": verified.manifest["master_pixel_sha256"],
            "roi_zip_sha256": verified.manifest["roi_zip_sha256"],
            "revision_manifest_sha256": verified.manifest_sha256,
        }
        for field, value in expected.items():
            if run_manifest.get(field) != value:
                raise ValidationError("RUN and immutable revision do not reconcile", details={"field": field})
        return True

    return verify_run_binding


def make_working_state(
    revision: VerifiedRevision,
    *,
    working_state_id: str,
    operator_id: str,
    reason: str,
) -> dict[str, Any]:
    """Create mutable working-state metadata without changing the revision."""

    if not ID_RE.fullmatch(working_state_id) or working_state_id in {revision.manifest["revision_id"], revision.manifest["revision_uid"]}:
        raise ValidationError("working_state_id must be valid and distinct from revision identity")
    if not operator_id.strip() or not reason.strip():
        raise ValidationError("working-state audit requires operator and reason")
    created_at = utc_now_z()
    return {
        "descriptor_type": "working_state",
        "working_state_id": working_state_id,
        "base_revision_id": revision.manifest["revision_id"],
        "base_revision_uid": revision.manifest["revision_uid"],
        "base_revision_manifest_sha256": revision.manifest_sha256,
        "project_uid": revision.manifest["project_uid"],
        "image_uid": revision.manifest["image_uid"],
        "analysis_session_uid": revision.manifest["analysis_session_uid"],
        "created_at": created_at,
        "audit": {
            "event_type": "WORKING_STATE_CREATED_FROM_REVISION",
            "operator_id": operator_id,
            "reason": reason,
            "event_at": created_at,
        },
    }
