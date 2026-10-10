"""Read-only R9 inspection and copy-only migration into the approved P2A core.

The adapter deliberately has no Fiji dependency.  Fiji is responsible for
exporting every legacy ROI as an explicit, independently hashed record; this
module verifies that export against the immutable legacy ZIP before creating
schema-v2 objects.  Legacy pointers are observations only and legacy RUNs are
never migrated.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import io
import json
import math
import os
from pathlib import Path, PurePosixPath
import stat
import unicodedata
import uuid
import zipfile
from typing import Any, Callable, Mapping, Sequence

from cavity_tem_light_p1.canonical_json import canonical_json_bytes, loads_canonical_json
from cavity_tem_light_p1.errors import TransactionError, ValidationError
from cavity_tem_light_p1.identity import validate_cavity_id, validate_human_id
from cavity_tem_light_p1.path_safety import rename_directory_no_replace
from cavity_tem_light_p2.session_core import SessionCore, create_project, validate_project


MIGRATION_SCHEMA = "CTL_MIGRATION_MANIFEST_V1"
SNAPSHOT_SCHEMA = "CTL_LEGACY_TREE_SNAPSHOT_V1"
INSPECTION_SCHEMA = "CTL_LEGACY_PROJECT_INSPECTION_V1"
PLAN_SCHEMA = "CTL_LEGACY_MIGRATION_PLAN_V1"
JOURNAL_SCHEMA = "CTL_LEGACY_MIGRATION_JOURNAL_V1"
ADAPTER_ID = "CTL_R9_TO_V2_COPY_ADAPTER"
ADAPTER_VERSION = "1"
SESSION_ORIGIN = "MIGRATED_LEGACY_BRIDGE"
BLOCKED_REVIEW = "BLOCKED_REVIEW"
QUARANTINE_POLICY_ID = "CTL_R9_MIGRATION_CONSISTENT_PREFIX_WITH_LEGACY_QUARANTINE_V1"
QUARANTINE_EVIDENCE_SCHEMA = "CTL_R9_MIGRATION_EVIDENCE_V1"
QUARANTINE_MANIFEST_SCHEMA = "CTL_R9_LEGACY_QUARANTINE_MANIFEST_V1"
QUARANTINE_STATUS_SCHEMA = "CTL_R9_LEGACY_QUARANTINE_STATUS_V1"
QUARANTINE_CONFLICTS_SCHEMA = "CTL_R9_LEGACY_CONFLICTS_V1"
PARTIAL_MIGRATION_STATUS = "PARTIAL_WITH_LEGACY_QUARANTINE"
STRICTLY_VALID = "STRICTLY_VALID"
QUARANTINED = "QUARANTINED_IDENTITY_CONFLICT"
_REPARSE_ATTRIBUTE = 0x400
_SHA_RE = __import__("re").compile(r"^[0-9a-f]{64}$", __import__("re").ASCII)
_CAVITY_ENTRY_RE = __import__("re").compile(r"^(CAV_[0-9]{6})\.roi$", __import__("re").ASCII)

FaultHook = Callable[[str, Mapping[str, Any]], None]


@dataclass(frozen=True)
class MigrationResult:
    target_root: Path
    manifest_path: Path
    manifest_sha256: str
    idempotency_key: str
    migration_id: str
    project_uid: str
    image_uid: str
    analysis_session_uid: str
    revision_ids: tuple[str, ...]
    blocked_images: tuple[dict[str, Any], ...]
    source_unchanged: bool
    idempotent_replay: bool
    manifest_location: str = "ADJACENT_SIDECAR_OUTSIDE_CLOSED_P2A_INVENTORY"
    migration_status: str = "COMPLETE"
    editable_baseline_revision: str | None = None
    quarantined_revision_ids: tuple[str, ...] = ()
    quarantine_root: Path | None = None


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def adapter_sha256() -> str:
    """Return the SHA-256 of the exact adapter source bytes being executed."""

    return _sha256_file(Path(__file__))


def _require_sha(value: Any, field: str) -> str:
    if not isinstance(value, str) or _SHA_RE.fullmatch(value) is None:
        raise ValidationError("invalid SHA-256", details={"field": field, "value": value})
    return value


def _require_plain_directory(path: Path, label: str) -> Path:
    if not path.is_dir() or path.is_symlink():
        raise ValidationError(f"{label} must be a plain directory", details={"path": str(path)})
    info = path.lstat()
    if getattr(info, "st_file_attributes", 0) & _REPARSE_ATTRIBUTE:
        raise ValidationError(f"{label} must not be a reparse point", details={"path": str(path)})
    return path


def _entry_kind(path: Path, info: os.stat_result) -> tuple[str, bool, str | None]:
    is_reparse = bool(getattr(info, "st_file_attributes", 0) & _REPARSE_ATTRIBUTE)
    if stat.S_ISLNK(info.st_mode):
        kind = "symlink"
    elif stat.S_ISREG(info.st_mode):
        kind = "file"
    elif stat.S_ISDIR(info.st_mode):
        kind = "directory"
    else:
        kind = "special"
    is_link = kind == "symlink" or is_reparse
    target: str | None = None
    if is_link:
        try:
            target = os.readlink(path)
        except OSError:
            target = "UNAVAILABLE"
    return kind, is_link, target


def _portable_relative(value: str) -> str:
    if not isinstance(value, str) or value != unicodedata.normalize("NFC", value):
        raise ValidationError("relative path is not NFC text")
    if "\\" in value or "\x00" in value or "\r" in value or "\n" in value:
        raise ValidationError("relative path is not portable", details={"path": value})
    parsed = PurePosixPath(value)
    if parsed.is_absolute() or not parsed.parts or any(part in {"", ".", ".."} for part in parsed.parts):
        raise ValidationError("relative path is not contained", details={"path": value})
    return value


def snapshot_legacy_tree(root: os.PathLike[str] | str) -> dict[str, Any]:
    """Hash a legacy tree without following links and include empty directories.

    Timestamps are intentionally excluded: reading a file can update access
    metadata on some filesystems.  The snapshot nevertheless binds every
    relative name, physical kind, link/reparse fact, link count, byte size and
    regular-file SHA-256.
    """

    base = _require_plain_directory(Path(root), "legacy project root")
    entries: list[dict[str, Any]] = []
    folded: dict[str, str] = {}
    for path in sorted(base.rglob("*"), key=lambda item: item.relative_to(base).as_posix()):
        relative = _portable_relative(unicodedata.normalize("NFC", path.relative_to(base).as_posix()))
        collision_key = relative.casefold()
        if collision_key in folded and folded[collision_key] != relative:
            raise ValidationError(
                "legacy tree contains a case-fold path collision",
                details={"first": folded[collision_key], "second": relative},
            )
        folded[collision_key] = relative
        before = path.lstat()
        kind, is_link, link_target = _entry_kind(path, before)
        digest: str | None = None
        size = before.st_size if kind == "file" else 0
        if kind == "file" and not is_link:
            digest = _sha256_file(path)
        after = path.lstat()
        if (
            before.st_mode,
            before.st_size,
            getattr(before, "st_dev", 0),
            getattr(before, "st_ino", 0),
            getattr(before, "st_nlink", 0),
        ) != (
            after.st_mode,
            after.st_size,
            getattr(after, "st_dev", 0),
            getattr(after, "st_ino", 0),
            getattr(after, "st_nlink", 0),
        ):
            raise ValidationError("legacy entry changed while it was being hashed", details={"path": relative})
        entries.append(
            {
                "is_link_or_reparse": is_link,
                "link_count": int(getattr(after, "st_nlink", 0)),
                "link_target": link_target,
                "path": relative,
                "sha256": digest,
                "size": int(size),
                "type": kind,
            }
        )
    inventory_sha = _sha256_bytes(canonical_json_bytes({"entries": entries}))
    return {
        "entries": entries,
        "entry_count": len(entries),
        "inventory_sha256": inventory_sha,
        "schema": SNAPSHOT_SCHEMA,
    }


def _read_stable_bytes(path: Path, *, label: str) -> bytes:
    try:
        before = path.lstat()
    except FileNotFoundError as exc:
        raise ValidationError(f"{label} is absent", details={"path": str(path)}) from exc
    kind, is_link, _target = _entry_kind(path, before)
    if kind != "file" or is_link or getattr(before, "st_nlink", 1) != 1:
        raise ValidationError(f"{label} is not a single-link plain file", details={"path": str(path)})
    data = path.read_bytes()
    after = path.lstat()
    if (before.st_size, before.st_mtime_ns, before.st_ino, before.st_dev) != (
        after.st_size,
        after.st_mtime_ns,
        after.st_ino,
        after.st_dev,
    ) or len(data) != after.st_size:
        raise ValidationError(f"{label} changed during read", details={"path": str(path)})
    return data


def _decode_legacy_text(data: bytes, *, label: str) -> str:
    """Decode historical R8/R9 text without changing the source bytes.

    R9 projects produced on Windows exist in both UTF-8 (optionally with a
    BOM) and Windows-1252.  The order is closed and deterministic: UTF-8-SIG
    is attempted first, then strict Windows-1252.  No replacement characters
    or locale-dependent codec are permitted.
    """

    try:
        return data.decode("utf-8-sig")
    except UnicodeDecodeError:
        try:
            return data.decode("cp1252", errors="strict")
        except UnicodeDecodeError as exc:
            raise ValidationError(
                f"{label} is neither UTF-8-SIG nor Windows-1252"
            ) from exc


def _read_key_value_tsv(path: Path, *, label: str) -> dict[str, str]:
    text = _decode_legacy_text(_read_stable_bytes(path, label=label), label=label)
    result: dict[str, str] = {}
    for line_number, line in enumerate(text.splitlines(), 1):
        if not line:
            continue
        parts = line.split("\t")
        if len(parts) != 2 or not parts[0] or parts[0] in result:
            raise ValidationError(
                f"{label} is not a closed key/value TSV",
                details={"line": line_number},
            )
        result[parts[0]] = parts[1]
    return result


def _read_table_tsv(path: Path, *, label: str) -> tuple[list[str], list[dict[str, str]]]:
    text = _decode_legacy_text(_read_stable_bytes(path, label=label), label=label)
    reader = csv.DictReader(io.StringIO(text), delimiter="\t")
    fields = reader.fieldnames
    if not fields or len(fields) != len(set(fields)) or any(not field for field in fields):
        raise ValidationError(f"{label} has an invalid header")
    rows: list[dict[str, str]] = []
    for line_number, row in enumerate(reader, 2):
        if None in row or any(value is None for value in row.values()):
            raise ValidationError(f"{label} row width mismatch", details={"line": line_number})
        rows.append(dict(row))
    return list(fields), rows


def _legacy_source_file(image_root: Path, expected_sha256: str) -> tuple[Path, str, int]:
    source_root = _require_plain_directory(image_root / "source", "legacy image source directory")
    candidates = list(source_root.iterdir())
    if len(candidates) != 1:
        raise ValidationError("legacy source directory must contain exactly one entry")
    source = candidates[0]
    data = _read_stable_bytes(source, label="legacy immutable source")
    digest = _sha256_bytes(data)
    if digest != _require_sha(expected_sha256, "legacy image sha256"):
        raise ValidationError("legacy source SHA-256 does not match images.tsv")
    return source, digest, len(data)


def _inspect_revision(
    project_root: Path,
    image_id: str,
    source_sha256: str,
    revision_root: Path,
) -> dict[str, Any]:
    relative_root = revision_root.relative_to(project_root).as_posix()
    if revision_root.is_symlink() or not revision_root.is_dir():
        return {
            "reason": "REVISION_DIRECTORY_UNSAFE",
            "relative_path": relative_root,
            "revision_id": revision_root.name,
            "status": BLOCKED_REVIEW,
        }
    manifest_path = revision_root / "revision_manifest.tsv"
    roi_zip_path = revision_root / "cavity_rois.zip"
    if not manifest_path.is_file() or not roi_zip_path.is_file():
        return {
            "reason": "REVISION_EVIDENCE_INCOMPLETE",
            "relative_path": relative_root,
            "revision_id": revision_root.name,
            "status": BLOCKED_REVIEW,
        }
    manifest = _read_key_value_tsv(manifest_path, label="legacy revision manifest")
    required = {
        "revision_id",
        "image_id",
        "source_sha256",
        "roi_zip_sha256",
        "roi_count",
        "created_ms",
        "parent_revision",
    }
    if not required.issubset(manifest):
        raise ValidationError("legacy revision manifest lacks required evidence")
    if manifest["revision_id"] != revision_root.name or manifest["image_id"] != image_id:
        raise ValidationError("legacy revision path/identity mismatch")
    if manifest["source_sha256"] != source_sha256:
        raise ValidationError("legacy revision source binding mismatch")
    roi_zip_bytes = _read_stable_bytes(roi_zip_path, label="legacy ROI ZIP")
    roi_zip_sha = _sha256_bytes(roi_zip_bytes)
    if roi_zip_sha != _require_sha(manifest["roi_zip_sha256"], "roi_zip_sha256"):
        raise ValidationError("legacy ROI ZIP hash mismatch")
    try:
        roi_count = int(manifest["roi_count"])
        created_ms = int(manifest["created_ms"])
    except ValueError as exc:
        raise ValidationError("legacy revision numeric field is invalid") from exc
    if roi_count < 0 or created_ms < 0:
        raise ValidationError("legacy revision numeric field is negative")
    return {
        "created_ms": created_ms,
        "manifest_relative_path": manifest_path.relative_to(project_root).as_posix(),
        "parent_revision": manifest["parent_revision"] or "NOT_APPLICABLE",
        "relative_path": relative_root,
        "revision_id": manifest["revision_id"],
        "roi_count": roi_count,
        "roi_zip_relative_path": roi_zip_path.relative_to(project_root).as_posix(),
        "roi_zip_sha256": roi_zip_sha,
        "status": "VERIFIED",
    }


def inspect_legacy_project(root: os.PathLike[str] | str) -> dict[str, Any]:
    """Inspect one schema-1 project and prove that inspection is read-only."""

    project_root = _require_plain_directory(Path(root), "legacy project root")
    before = snapshot_legacy_tree(project_root)
    unsafe = [
        entry
        for entry in before["entries"]
        if entry["type"] not in {"file", "directory"}
        or entry["is_link_or_reparse"]
        or (entry["type"] == "file" and entry["link_count"] != 1)
    ]
    if unsafe:
        raise ValidationError("legacy project contains link, reparse, hardlink or special entries")

    descriptor = _read_key_value_tsv(
        project_root / "cavity_light_project.tsv", label="legacy project descriptor"
    )
    if descriptor.get("schema_version") != "1" or descriptor.get("descriptor_type") != "cavity_tem_light_project":
        raise ValidationError("source is not an unambiguous schema-1 Cavity TEM Light project")
    project_id = validate_human_id(descriptor.get("project_id", ""), field="legacy project_id")
    project_uid = descriptor.get("project_uid", "")
    try:
        if str(uuid.UUID(project_uid)) != project_uid:
            raise ValueError
    except (ValueError, AttributeError) as exc:
        raise ValidationError("legacy project_uid is not canonical") from exc

    headers, image_rows = _read_table_tsv(project_root / "images.tsv", label="legacy image registry")
    required_headers = {
        "image_id",
        "stored_path",
        "sha256",
        "sample_name",
        "condition",
        "current_revision",
        "current_run",
    }
    if not required_headers.issubset(headers):
        raise ValidationError("legacy image registry lacks required columns")
    seen_ids: set[str] = set()
    images: list[dict[str, Any]] = []
    for row in image_rows:
        image_id = validate_human_id(row["image_id"], field="legacy image_id")
        if image_id in seen_ids:
            raise ValidationError("legacy image_id is duplicated")
        seen_ids.add(image_id)
        image_root = _require_plain_directory(project_root / "images" / image_id, "legacy image root")
        metadata = _read_key_value_tsv(image_root / "image_metadata.tsv", label="legacy image metadata")
        if metadata.get("schema_version") != "1" or metadata.get("image_id") != image_id:
            raise ValidationError("legacy image metadata identity mismatch")
        source, source_sha, source_size = _legacy_source_file(image_root, row["sha256"])
        if metadata.get("source_sha256") != source_sha:
            raise ValidationError("legacy image metadata source binding mismatch")
        revisions_root = _require_plain_directory(image_root / "roi_sessions", "legacy revision root")
        revisions = [
            _inspect_revision(project_root, image_id, source_sha, child)
            for child in sorted(revisions_root.iterdir(), key=lambda item: item.name)
        ]
        blocked = [item for item in revisions if item["status"] == BLOCKED_REVIEW]
        status = BLOCKED_REVIEW if not revisions or blocked else "VERIFIED"
        current_pointer_path = image_root / "current_revision.txt"
        current_pointer = None
        if current_pointer_path.exists():
            current_pointer = _decode_legacy_text(
                _read_stable_bytes(current_pointer_path, label="legacy current revision observation"),
                label="legacy current revision observation",
            ).strip()
        images.append(
            {
                "condition": row["condition"],
                "current_revision_observed_non_authoritative": row["current_revision"],
                "current_revision_txt_observed_non_authoritative": current_pointer,
                "image_id": image_id,
                "legacy_run_migration": "DEFERRED_NOT_MIGRATED",
                "legacy_run_observed_non_authoritative": row["current_run"],
                "metadata_relative_path": (image_root / "image_metadata.tsv").relative_to(project_root).as_posix(),
                "revisions": revisions,
                "sample_name": row["sample_name"],
                "source_file_name": source.name,
                "source_relative_path": source.relative_to(project_root).as_posix(),
                "source_sha256": source_sha,
                "source_size": source_size,
                "status": status,
            }
        )
    images.sort(key=lambda item: item["image_id"])
    after = snapshot_legacy_tree(project_root)
    if before != after:
        raise ValidationError("legacy inspection mutated its source")
    return {
        "images": images,
        "project_id": project_id,
        "project_schema_version": 1,
        "project_uid": project_uid,
        "read_only": True,
        "schema": INSPECTION_SCHEMA,
        "snapshot": before,
        "text_decoding_policy": "UTF8_SIG_THEN_WINDOWS_1252_STRICT",
    }


def _zip_entry_map(zip_path: Path) -> dict[str, bytes]:
    archive_bytes = _read_stable_bytes(zip_path, label="legacy ROI ZIP")
    try:
        with zipfile.ZipFile(io.BytesIO(archive_bytes), "r") as archive:
            result: dict[str, bytes] = {}
            folded: dict[str, str] = {}
            infos = archive.infolist()
            if len(infos) > 100_000:
                raise ValidationError("legacy ROI ZIP exceeds the entry limit")
            for info in infos:
                if info.is_dir():
                    raise ValidationError("legacy ROI ZIP contains a directory entry")
                name = _portable_relative(unicodedata.normalize("NFC", info.filename))
                if name != info.filename:
                    raise ValidationError("legacy ROI ZIP entry is not canonical NFC")
                folded_name = name.casefold()
                if name in result or (folded_name in folded and folded[folded_name] != name):
                    raise ValidationError("legacy ROI ZIP contains duplicate/colliding names")
                folded[folded_name] = name
                if info.flag_bits & 0x1:
                    raise ValidationError("legacy ROI ZIP contains encrypted data")
                data = archive.read(info)
                if len(data) != info.file_size:
                    raise ValidationError("legacy ROI ZIP entry size mismatch")
                result[name] = data
    except zipfile.BadZipFile as exc:
        raise ValidationError("legacy ROI ZIP is invalid") from exc
    return result


def _finite_number(value: Any, field: str, *, positive: bool = False) -> int | float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValidationError("ROI export numeric field is invalid", details={"field": field})
    if positive and value <= 0:
        raise ValidationError("ROI export numeric field must be positive", details={"field": field})
    return value


def _normalize_roi_records(
    records: Sequence[Mapping[str, Any]],
    *,
    zip_entries: Mapping[str, bytes],
    expected_count: int,
) -> list[dict[str, Any]]:
    if isinstance(records, (str, bytes)) or not isinstance(records, Sequence):
        raise ValidationError("ROI export must be an explicit record sequence")
    normalized: list[dict[str, Any]] = []
    seen_entries: set[str] = set()
    seen_cavity_ids: set[str] = set()
    cavity_fields = {
        "bounds",
        "center",
        "cavity_id",
        "diameter",
        "entry_name",
        "entry_sha256",
        "properties",
    }
    metadata_fields = {"entry_name", "entry_sha256", "properties", "record_type"}
    for index, raw in enumerate(records):
        if not isinstance(raw, Mapping):
            raise ValidationError("ROI export record inventory is not closed", details={"index": index})
        field_set = frozenset(raw)
        if field_set not in {frozenset(cavity_fields), frozenset(metadata_fields)}:
            raise ValidationError("ROI export record inventory is not closed", details={"index": index})
        name = _portable_relative(str(raw["entry_name"]))
        if name in seen_entries:
            raise ValidationError("ROI export contains a duplicate entry")
        if name not in zip_entries:
            raise ValidationError("ROI export references an absent ZIP entry", details={"entry_name": name})
        digest = _require_sha(raw["entry_sha256"], "entry_sha256")
        if digest != _sha256_bytes(zip_entries[name]):
            raise ValidationError("ROI export entry hash mismatch", details={"entry_name": name})
        if not isinstance(raw["properties"], Mapping):
            raise ValidationError("ROI properties must be an explicit object")
        properties = loads_canonical_json(canonical_json_bytes(dict(raw["properties"])))
        if set(raw) == metadata_fields:
            if raw["record_type"] != "SESSION_METADATA":
                raise ValidationError("non-cavity ROI record_type is not SESSION_METADATA")
            folded_properties = {
                str(key).casefold(): str(value).strip().casefold()
                for key, value in properties.items()
            }
            observed_type = folded_properties.get(
                "type", folded_properties.get("object_type", "")
            )
            if observed_type not in {"session_metadata", "cavity_session_metadata"}:
                raise ValidationError(
                    "SESSION_METADATA ROI lacks explicit metadata type evidence"
                )
            normalized.append(
                {
                    "entry_name": name,
                    "entry_sha256": digest,
                    "properties": properties,
                    "record_type": "SESSION_METADATA",
                }
            )
            seen_entries.add(name)
            continue
        cavity_id = validate_cavity_id(raw["cavity_id"])
        if cavity_id in seen_cavity_ids:
            raise ValidationError("ROI export contains duplicate cavity identity")
        bounds = raw["bounds"]
        center = raw["center"]
        if not isinstance(bounds, Mapping) or set(bounds) != {"height", "width", "x", "y"}:
            raise ValidationError("ROI bounds inventory is invalid")
        if not isinstance(center, Mapping) or set(center) != {"x", "y"}:
            raise ValidationError("ROI center inventory is invalid")
        checked_bounds = {
            "height": _finite_number(bounds["height"], "bounds.height", positive=True),
            "width": _finite_number(bounds["width"], "bounds.width", positive=True),
            "x": _finite_number(bounds["x"], "bounds.x"),
            "y": _finite_number(bounds["y"], "bounds.y"),
        }
        checked_center = {
            "x": _finite_number(center["x"], "center.x"),
            "y": _finite_number(center["y"], "center.y"),
        }
        diameter = _finite_number(raw["diameter"], "diameter", positive=True)
        normalized.append(
            {
                "bounds": checked_bounds,
                "center": checked_center,
                "cavity_id": cavity_id,
                "diameter": diameter,
                "entry_name": name,
                "entry_sha256": digest,
                "properties": properties,
                "record_type": "CAVITY",
            }
        )
        seen_entries.add(name)
        seen_cavity_ids.add(cavity_id)
    if len(normalized) != expected_count or set(zip_entries) != seen_entries:
        raise ValidationError(
            "ROI export does not cover the ZIP and legacy manifest exactly",
            details={
                "expected_count": expected_count,
                "export_count": len(normalized),
                "missing_entries": sorted(set(zip_entries) - seen_entries),
                "extra_entries": sorted(seen_entries - set(zip_entries)),
            },
        )
    normalized.sort(key=lambda item: item["entry_name"])
    return normalized


def _property_value(
    properties: Mapping[str, Any], names: Sequence[str]
) -> tuple[str, bool]:
    """Return one case-insensitive property value without resolving conflicts."""

    wanted = {name.casefold() for name in names}
    values = [
        str(value).strip()
        for key, value in properties.items()
        if str(key).casefold() in wanted
    ]
    if not values:
        return "", False
    return values[0], any(value != values[0] for value in values[1:])


def _resolve_physical_revision_chain(revisions: Sequence[Mapping[str, Any]]) -> list[str]:
    """Resolve the complete transport-verified chain without pointer heuristics."""

    if not revisions or any(item.get("status") != "VERIFIED" for item in revisions):
        raise ValidationError("legacy revision transport chain is not fully verifiable")
    by_id: dict[str, Mapping[str, Any]] = {}
    children: dict[str, str] = {}
    roots: list[str] = []
    for item in revisions:
        revision_id = validate_human_id(item.get("revision_id", ""), field="legacy revision_id")
        if revision_id in by_id:
            raise ValidationError("legacy revision identity is duplicated")
        by_id[revision_id] = item
    for revision_id, item in by_id.items():
        parent = item.get("parent_revision")
        if parent == "NOT_APPLICABLE":
            roots.append(revision_id)
            continue
        if parent not in by_id:
            raise ValidationError("legacy revision parent is absent", details={"revision_id": revision_id})
        if parent in children:
            raise ValidationError("legacy revision chain is forked", details={"parent_revision": parent})
        children[str(parent)] = revision_id
    if len(roots) != 1:
        raise ValidationError("legacy revision chain does not have one root")
    chain: list[str] = []
    cursor: str | None = roots[0]
    while cursor is not None:
        if cursor in chain:
            raise ValidationError("legacy revision chain contains a cycle")
        chain.append(cursor)
        cursor = children.get(cursor)
    if len(chain) != len(by_id):
        raise ValidationError("legacy revision chain is not complete")
    return chain


def _legacy_file_inventory(snapshot: Mapping[str, Any]) -> list[dict[str, Any]]:
    return [
        {"bytes": int(item["size"]), "path": item["path"], "sha256": item["sha256"]}
        for item in snapshot["entries"]
        if item["type"] == "file"
    ]


def _legacy_java_snapshot_sha256(snapshot: Mapping[str, Any]) -> str:
    rows: list[str] = []
    for item in snapshot["entries"]:
        if item["type"] == "directory":
            rows.append(f"D|{item['path']}")
        elif item["type"] == "file":
            rows.append(f"F|{item['path']}|{item['size']}|{item['sha256']}")
        else:
            raise ValidationError("legacy snapshot contains an unsupported entry")
    rows.sort()
    return _sha256_bytes(("\n".join(rows) + "\n").encode("utf-8"))


def _closed_observation(
    raw: Mapping[str, Any], *, zip_entries: Mapping[str, bytes]
) -> dict[str, Any]:
    fields = {"bounds", "entry_name", "entry_sha256", "geometry_type", "properties", "roi_name"}
    if not isinstance(raw, Mapping) or set(raw) != fields:
        raise ValidationError("legacy ROI observation inventory is not closed")
    name = _portable_relative(str(raw["entry_name"]))
    if "/" in name or name not in zip_entries:
        raise ValidationError("legacy ROI observation references an absent/non-flat ZIP entry")
    digest = _require_sha(raw["entry_sha256"], "legacy observation entry_sha256")
    if digest != _sha256_bytes(zip_entries[name]):
        raise ValidationError("legacy ROI observation hash does not match the ZIP entry")
    properties_raw = raw["properties"]
    if not isinstance(properties_raw, Mapping):
        raise ValidationError("legacy ROI observation properties are not an object")
    properties = loads_canonical_json(canonical_json_bytes(dict(properties_raw)))
    bounds_raw = raw["bounds"]
    if not isinstance(bounds_raw, Mapping) or set(bounds_raw) != {"height", "width", "x", "y"}:
        raise ValidationError("legacy ROI observation bounds inventory is invalid")
    bounds: dict[str, int | float] = {}
    for field in ("height", "width", "x", "y"):
        bounds[field] = _finite_number(bounds_raw[field], f"bounds.{field}")
    geometry_type = str(raw["geometry_type"]).strip()
    roi_name = str(raw["roi_name"]).strip()
    if not geometry_type or not roi_name:
        raise ValidationError("legacy ROI observation lacks geometry type or internal ROI name")
    return {
        "bounds": bounds,
        "entry_name": name,
        "entry_sha256": digest,
        "geometry_type": geometry_type,
        "properties": properties,
        "roi_name": roi_name,
    }


def _assess_revision_observations(
    revision: Mapping[str, Any], observations: Sequence[Mapping[str, Any]], *, zip_path: Path
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Classify one revision without repairing names, roles or identities."""

    if isinstance(observations, (str, bytes)) or not isinstance(observations, Sequence):
        raise ValidationError("legacy revision observations must be an explicit sequence")
    zip_entries = _zip_entry_map(zip_path)
    if len(observations) != revision["roi_count"] or len(zip_entries) != revision["roi_count"]:
        raise ValidationError("legacy revision observation count does not bind manifest and ZIP")
    seen_entries: set[str] = set()
    normalized: list[dict[str, Any]] = []
    report_rows: list[dict[str, Any]] = []
    cavity_groups: dict[str, list[str]] = {}
    metadata_typed_entries: list[str] = []
    cavity_typed_count = 0
    for raw in observations:
        item = _closed_observation(raw, zip_entries=zip_entries)
        entry_name = item["entry_name"]
        if entry_name in seen_entries:
            raise ValidationError("legacy ROI observations contain a duplicate entry")
        seen_entries.add(entry_name)
        properties = item["properties"]
        observed_type_raw, type_alias_conflict = _property_value(properties, ("Type", "Object_type"))
        observed_type = observed_type_raw.casefold()
        cavity_id, cavity_alias_conflict = _property_value(properties, ("Cavity_id",))
        cavity_serial, serial_alias_conflict = _property_value(properties, ("Cavity_serial",))
        diameter_raw, diameter_alias_conflict = _property_value(
            properties, ("Equivalent_diameter_nm", "Diameter_nm")
        )
        conflicts: list[str] = []
        if type_alias_conflict or cavity_alias_conflict or serial_alias_conflict or diameter_alias_conflict:
            conflicts.append("ROI_PROPERTY_ALIASES_CONFLICT")
        bounds = item["bounds"]
        geometry_valid = bounds["width"] > 0 and bounds["height"] > 0
        if not geometry_valid:
            conflicts.append("GEOMETRY_BOUNDS_INVALID")
        metadata_type = observed_type in {"session_metadata", "cavity_session_metadata"}
        cavity_match = _CAVITY_ENTRY_RE.fullmatch(entry_name)
        if metadata_type:
            metadata_typed_entries.append(entry_name)
            if entry_name != "CAVITY_SESSION_METADATA.roi":
                conflicts.extend(("SCIENTIFIC_ROI_CLASSIFIED_AS_METADATA", "METADATA_PHYSICAL_NAME_MISMATCH"))
            if item["roi_name"] != "CAVITY_SESSION_METADATA":
                conflicts.append("METADATA_INTERNAL_NAME_MISMATCH")
            normalized_record: dict[str, Any] = {
                "entry_name": entry_name,
                "entry_sha256": item["entry_sha256"],
                "properties": properties,
                "record_type": "SESSION_METADATA",
            }
        else:
            cavity_typed_count += observed_type == "cavity"
            if observed_type != "cavity":
                conflicts.append("CAVITY_TYPE_MISMATCH")
            if cavity_match is None:
                conflicts.append("CAVITY_PHYSICAL_NAME_INVALID")
                expected_id = None
            else:
                expected_id = cavity_match.group(1)
            if _CAVITY_ENTRY_RE.fullmatch(f"{cavity_id}.roi") is None:
                conflicts.append("CAVITY_ID_MISSING_OR_INVALID")
            else:
                cavity_groups.setdefault(cavity_id, []).append(entry_name)
            if expected_id is not None and cavity_id != expected_id:
                conflicts.append("PHYSICAL_NAME_CAVITY_ID_DIVERGENCE")
            if expected_id is not None and item["roi_name"] != expected_id:
                conflicts.append("PHYSICAL_NAME_ROI_NAME_DIVERGENCE")
            try:
                diameter = float(diameter_raw)
                if not math.isfinite(diameter) or diameter <= 0:
                    raise ValueError
            except (TypeError, ValueError):
                diameter = 0.0
                conflicts.append("CAVITY_DIAMETER_INVALID")
            normalized_record = {
                "bounds": bounds,
                "center": {
                    "x": bounds["x"] + bounds["width"] / 2,
                    "y": bounds["y"] + bounds["height"] / 2,
                },
                "cavity_id": cavity_id,
                "diameter": diameter,
                "entry_name": entry_name,
                "entry_sha256": item["entry_sha256"],
                "properties": properties,
            }
        normalized.append(normalized_record)
        report_rows.append(
            {
                "Cavity_id": cavity_id or None,
                "Cavity_serial": cavity_serial or None,
                "Type": observed_type_raw or None,
                "bounds": bounds,
                "conflict_codes": sorted(set(conflicts)),
                "geometry_type": item["geometry_type"],
                "revision_id": revision["revision_id"],
                "roi_name": item["roi_name"],
                "roi_path_name": entry_name,
                "selected_migration_action": "PENDING_REVISION_CLASSIFICATION",
                "sha256": item["entry_sha256"],
            }
        )
    if set(zip_entries) != seen_entries:
        raise ValidationError("legacy observations do not cover the ROI ZIP exactly")
    duplicate_groups = [
        {"Cavity_id": cavity_id, "entries": sorted(entries)}
        for cavity_id, entries in sorted(cavity_groups.items())
        if len(entries) > 1
    ]
    duplicate_entries = {entry for group in duplicate_groups for entry in group["entries"]}
    for row in report_rows:
        if row["roi_path_name"] in duplicate_entries:
            row["conflict_codes"] = sorted(set((*row["conflict_codes"], "DUPLICATE_CAVITY_ID")))
    if len(metadata_typed_entries) != 1:
        for row in report_rows:
            row["conflict_codes"] = sorted(
                set((*row["conflict_codes"], "SESSION_METADATA_COUNT_NOT_ONE"))
            )
    all_conflicts = sorted({code for row in report_rows for code in row["conflict_codes"]})
    intrinsic_status = STRICTLY_VALID if not all_conflicts else QUARANTINED
    for row in report_rows:
        row["selected_migration_action"] = (
            "CONVERT_VERIFIED_CAVITY_OR_EXCLUDE_CANONICAL_METADATA"
            if intrinsic_status == STRICTLY_VALID
            else "QUARANTINE_NO_CONVERSION"
        )
        if intrinsic_status != STRICTLY_VALID:
            row["conflict_codes"] = sorted(
                set((*row["conflict_codes"], "REVISION_QUARANTINED_AS_UNIT"))
            )
    assessment = {
        "cavity_typed_count": cavity_typed_count,
        "conflict_codes": all_conflicts,
        "duplicate_groups": duplicate_groups,
        "intrinsic_status": intrinsic_status,
        "metadata_typed_entries": sorted(metadata_typed_entries),
        "parent_revision": revision["parent_revision"],
        "records": sorted(report_rows, key=lambda row: row["roi_path_name"]),
        "revision_id": revision["revision_id"],
        "roi_count": revision["roi_count"],
        "roi_zip_sha256": revision["roi_zip_sha256"],
        "unique_cavity_ids": len(cavity_groups),
    }
    normalized.sort(key=lambda item: item["entry_name"])
    return assessment, normalized


def _plan_quarantined_prefix(
    inspection: Mapping[str, Any],
    selected: Mapping[str, Any],
    *,
    source_root: Path,
    migration_evidence: Mapping[str, Any],
    master_pixel_evidence: Mapping[str, Any],
) -> dict[str, Any]:
    expected_fields = {
        "automatic_identity_repair",
        "image_id",
        "legacy_file_inventory",
        "legacy_snapshot_sha256",
        "policy_id",
        "revision_chain",
        "revision_manifests",
        "revision_observations",
        "schema",
        "scientific_validation",
        "source_binding",
        "text_decodings",
    }
    if not isinstance(migration_evidence, Mapping) or set(migration_evidence) != expected_fields:
        raise ValidationError("R9 quarantine migration evidence inventory is not closed")
    if (
        migration_evidence["schema"] != QUARANTINE_EVIDENCE_SCHEMA
        or migration_evidence["policy_id"] != QUARANTINE_POLICY_ID
        or migration_evidence["automatic_identity_repair"] is not False
        or migration_evidence["scientific_validation"] is not False
        or migration_evidence["image_id"] != selected["image_id"]
    ):
        raise ValidationError("R9 quarantine migration evidence policy binding failed")
    physical_chain = _resolve_physical_revision_chain(selected["revisions"])
    if migration_evidence["revision_chain"] != physical_chain:
        raise ValidationError("R9 quarantine evidence does not bind the complete physical chain")
    expected_inventory = _legacy_file_inventory(inspection["snapshot"])
    if migration_evidence["legacy_file_inventory"] != expected_inventory:
        raise ValidationError("R9 quarantine evidence does not bind the complete legacy file inventory")
    if migration_evidence["legacy_snapshot_sha256"] != _legacy_java_snapshot_sha256(inspection["snapshot"]):
        raise ValidationError("R9 quarantine evidence legacy snapshot digest mismatch")
    source_binding = migration_evidence["source_binding"]
    if not isinstance(source_binding, Mapping) or set(source_binding) != {
        "image_id", "source_file_name", "source_sha256"
    } or source_binding != {
        "image_id": selected["image_id"],
        "source_file_name": selected["source_file_name"],
        "source_sha256": selected["source_sha256"],
    }:
        raise ValidationError("R9 quarantine evidence source binding failed")
    decoding_rows = migration_evidence["text_decodings"]
    if not isinstance(decoding_rows, list):
        raise ValidationError("R9 quarantine text decoding evidence is not a list")
    decoding_fields = {
        "byte_size", "charset", "fallback_used", "label", "policy",
        "relative_path", "roundtrip_exact", "sha256",
    }
    source_files = {
        item["path"]: item for item in expected_inventory
    }
    required_decoding_paths = {
        "cavity_light_project.tsv",
        "images.tsv",
        selected["metadata_relative_path"],
        *(item["manifest_relative_path"] for item in selected["revisions"]),
    }
    observed_decoding_paths: set[str] = set()
    for row in decoding_rows:
        if not isinstance(row, Mapping) or set(row) != decoding_fields:
            raise ValidationError("R9 quarantine text decoding record is not closed")
        relative = _portable_relative(str(row["relative_path"]))
        if relative in observed_decoding_paths or relative not in source_files:
            raise ValidationError("R9 quarantine text decoding path is duplicated or absent")
        observed_decoding_paths.add(relative)
        source_record = source_files[relative]
        if (
            row["byte_size"] != source_record["bytes"]
            or row["sha256"] != source_record["sha256"]
            or row["policy"] != "STRICT_UTF8_ROUNDTRIP_ELSE_WINDOWS_1252_ROUNDTRIP_V1"
            or row["roundtrip_exact"] is not True
            or row["charset"] not in {"UTF-8", "windows-1252"}
            or row["fallback_used"] is not (row["charset"] == "windows-1252")
            or not str(row["label"]).strip()
        ):
            raise ValidationError("R9 quarantine text decoding evidence binding failed")
    if observed_decoding_paths != required_decoding_paths:
        raise ValidationError("R9 quarantine text decoding evidence coverage mismatch")
    manifests = migration_evidence["revision_manifests"]
    observations = migration_evidence["revision_observations"]
    if not isinstance(manifests, Mapping) or not isinstance(observations, Mapping):
        raise ValidationError("R9 quarantine revision evidence is not a mapping")
    if set(manifests) != set(physical_chain) or set(observations) != set(physical_chain):
        raise ValidationError("R9 quarantine revision evidence does not cover the chain exactly")
    physical_by_id = {item["revision_id"]: item for item in selected["revisions"]}
    valid_revisions: list[dict[str, Any]] = []
    assessments: list[dict[str, Any]] = []
    first_invalid: str | None = None
    quarantined: list[dict[str, Any]] = []
    for revision_id in physical_chain:
        revision = physical_by_id[revision_id]
        expected_manifest = {
            "created_ms": revision["created_ms"],
            "parent_revision": revision["parent_revision"],
            "revision_id": revision_id,
            "roi_count": revision["roi_count"],
            "roi_zip_sha256": revision["roi_zip_sha256"],
        }
        if manifests[revision_id] != expected_manifest:
            raise ValidationError("R9 quarantine revision manifest evidence mismatch", details={"revision_id": revision_id})
        zip_path = source_root / PurePosixPath(revision["roi_zip_relative_path"])
        assessment, normalized = _assess_revision_observations(
            revision, observations[revision_id], zip_path=zip_path
        )
        if first_invalid is None and assessment["intrinsic_status"] == STRICTLY_VALID:
            assessment["status"] = STRICTLY_VALID
            assessment["selected_migration_action"] = "MIGRATE_AS_EDITABLE_PREFIX"
            valid_revisions.append({**revision, "roi_records": normalized})
        else:
            if first_invalid is None:
                first_invalid = revision_id
                assessment["status"] = QUARANTINED
            else:
                assessment["status"] = "QUARANTINED_DESCENDANT_OF_FIRST_INVALID"
                assessment["conflict_codes"] = sorted(
                    set((*assessment["conflict_codes"], "DESCENDANT_OF_FIRST_INVALID_REVISION"))
                )
                for row in assessment["records"]:
                    row["conflict_codes"] = sorted(
                        set((*row["conflict_codes"], "DESCENDANT_OF_FIRST_INVALID_REVISION"))
                    )
                    row["selected_migration_action"] = "QUARANTINE_NO_CONVERSION"
            assessment["selected_migration_action"] = "QUARANTINE_NO_CONVERSION"
            prefix = revision["relative_path"] + "/"
            assessment["payload_files"] = [
                {"bytes": int(item["size"]), "path": item["path"][len(prefix):], "sha256": item["sha256"]}
                for item in inspection["snapshot"]["entries"]
                if item["type"] == "file" and item["path"].startswith(prefix)
            ]
            assessment["source_revision_relative_path"] = revision["relative_path"]
            quarantined.append(assessment)
        assessments.append(assessment)
    if not valid_revisions:
        raise ValidationError("BLOCKED_NO_STRICTLY_VALID_LEGACY_REVISION")
    if not quarantined:
        raise ValidationError("quarantine policy was requested but no invalid revision was demonstrated")
    valid_prefix = [item["revision_id"] for item in valid_revisions]
    if physical_chain[: len(valid_prefix)] != valid_prefix:
        raise ValidationError("valid legacy revisions are not one contiguous prefix")
    master = _master_pixel_evidence(master_pixel_evidence)
    blocked = [
        {"image_id": item["image_id"], "reason": "INCOMPLETE_LEGACY_REVISION_EVIDENCE", "status": BLOCKED_REVIEW}
        for item in inspection["images"]
        if item["image_id"] != selected["image_id"] and item["status"] == BLOCKED_REVIEW
    ]
    return {
        "blocked_images": blocked,
        "legacy_revision_chain": physical_chain,
        "legacy_run_policy": "DO_NOT_MIGRATE",
        "master_pixel_evidence": master,
        "migration_status": PARTIAL_MIGRATION_STATUS,
        "policy_id": QUARANTINE_POLICY_ID,
        "project_id": inspection["project_id"],
        "project_uid": inspection["project_uid"],
        "quarantined_revisions": quarantined,
        "revision_assessments": assessments,
        "revision_chain": valid_prefix,
        "revisions": valid_revisions,
        "schema": PLAN_SCHEMA,
        "selected_image": {
            key: selected[key]
            for key in (
                "condition", "image_id", "sample_name", "source_file_name",
                "source_relative_path", "source_sha256", "source_size",
            )
        },
        "source_snapshot": inspection["snapshot"],
        "text_decoding_policy": inspection["text_decoding_policy"],
    }


def _master_pixel_evidence(value: Mapping[str, Any]) -> dict[str, str]:
    if not isinstance(value, Mapping) or set(value) != {"hash", "method", "status"}:
        raise ValidationError("master pixel evidence inventory is not closed")
    if value["status"] != "VERIFIED":
        raise ValidationError("positive migration requires independently VERIFIED master pixel evidence")
    method = validate_human_id(value["method"], field="master pixel method")
    return {"hash": _require_sha(value["hash"], "master pixel hash"), "method": method, "status": "VERIFIED"}


def plan_legacy_migration(
    source_root: os.PathLike[str] | str,
    *,
    image_id: str,
    revision_chain: Sequence[str] | None = None,
    roi_exports: Mapping[str, Sequence[Mapping[str, Any]]] | None = None,
    migration_evidence: Mapping[str, Any] | None = None,
    master_pixel_evidence: Mapping[str, Any],
) -> dict[str, Any]:
    """Build an explicit plan; no current/latest/mtime selection is allowed."""

    inspection = inspect_legacy_project(source_root)
    selected_id = validate_human_id(image_id, field="selected legacy image_id")
    matches = [item for item in inspection["images"] if item["image_id"] == selected_id]
    if len(matches) != 1:
        raise ValidationError("explicit image_id does not identify exactly one legacy image")
    selected = matches[0]
    if selected["status"] != "VERIFIED":
        raise ValidationError("explicit legacy image is not fully verifiable")
    if migration_evidence is not None:
        if revision_chain is not None or roi_exports is not None:
            raise ValidationError("quarantine migration evidence cannot be mixed with legacy ROI arguments")
        return _plan_quarantined_prefix(
            inspection,
            selected,
            source_root=Path(source_root),
            migration_evidence=migration_evidence,
            master_pixel_evidence=master_pixel_evidence,
        )
    if revision_chain is None or roi_exports is None:
        raise ValidationError("complete migration requires explicit revision_chain and roi_exports")
    chain = list(revision_chain)
    if not chain or len(chain) != len(set(chain)):
        raise ValidationError("revision_chain must be explicit, non-empty and duplicate-free")
    for value in chain:
        validate_human_id(value, field="legacy revision_id")
    verified = {item["revision_id"]: item for item in selected["revisions"] if item["status"] == "VERIFIED"}
    if set(chain) != set(verified) or len(chain) != len(verified):
        raise ValidationError("explicit revision_chain must cover all verified legacy revisions exactly")
    previous = "NOT_APPLICABLE"
    planned_revisions: list[dict[str, Any]] = []
    if set(roi_exports) != set(chain):
        raise ValidationError("ROI export mapping must cover the explicit revision chain exactly")
    base = Path(source_root)
    for revision_id in chain:
        revision = verified[revision_id]
        if revision["parent_revision"] != previous:
            raise ValidationError(
                "explicit revision_chain conflicts with the signed legacy parent chain",
                details={"revision_id": revision_id, "expected_parent": previous},
            )
        zip_path = base / PurePosixPath(revision["roi_zip_relative_path"])
        entries = _zip_entry_map(zip_path)
        records = _normalize_roi_records(
            roi_exports[revision_id], zip_entries=entries, expected_count=revision["roi_count"]
        )
        planned_revisions.append({**revision, "roi_records": records})
        previous = revision_id
    master = _master_pixel_evidence(master_pixel_evidence)
    blocked = [
        {
            "image_id": item["image_id"],
            "reason": "INCOMPLETE_LEGACY_REVISION_EVIDENCE",
            "status": BLOCKED_REVIEW,
        }
        for item in inspection["images"]
        if item["image_id"] != selected_id and item["status"] == BLOCKED_REVIEW
    ]
    return {
        "blocked_images": blocked,
        "legacy_revision_chain": chain,
        "legacy_run_policy": "DO_NOT_MIGRATE",
        "master_pixel_evidence": master,
        "migration_status": "COMPLETE",
        "policy_id": "CTL_R9_MIGRATION_COMPLETE_EXPLICIT_CHAIN_V1",
        "project_id": inspection["project_id"],
        "project_uid": inspection["project_uid"],
        "quarantined_revisions": [],
        "revision_assessments": [
            {
                "revision_id": item["revision_id"],
                "status": STRICTLY_VALID,
                "selected_migration_action": "MIGRATE_AS_EDITABLE_PREFIX",
            }
            for item in planned_revisions
        ],
        "revision_chain": chain,
        "revisions": planned_revisions,
        "schema": PLAN_SCHEMA,
        "selected_image": {
            key: selected[key]
            for key in (
                "condition",
                "image_id",
                "sample_name",
                "source_file_name",
                "source_relative_path",
                "source_sha256",
                "source_size",
            )
        },
        "source_snapshot": inspection["snapshot"],
        "text_decoding_policy": inspection["text_decoding_policy"],
    }


def _uuid4_from_material(material: str) -> str:
    raw = bytearray(hashlib.sha256(material.encode("utf-8")).digest()[:16])
    raw[6] = (raw[6] & 0x0F) | 0x40
    raw[8] = (raw[8] & 0x3F) | 0x80
    return str(uuid.UUID(bytes=bytes(raw)))


def _timestamp_from_milliseconds(value: int) -> str:
    converted = datetime.fromtimestamp(value / 1000.0, timezone.utc)
    base = converted.strftime("%Y-%m-%dT%H:%M:%S")
    fraction = f"{converted.microsecond:06d}".rstrip("0")
    return f"{base}.{fraction}Z" if fraction else f"{base}Z"


def _write_new(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with path.open("xb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
    except FileExistsError as exc:
        raise TransactionError("migration authority already exists", details={"path": str(path)}) from exc


def _replace_journal(path: Path, value: Mapping[str, Any]) -> None:
    data = canonical_json_bytes(dict(value))
    if not path.exists():
        _write_new(path, data)
        return
    token = uuid.uuid4().hex
    temporary = path.with_name(f".{path.name}.partial.{token}")
    _write_new(temporary, data)
    os.replace(temporary, path)


def _read_canonical(path: Path, *, label: str) -> dict[str, Any]:
    data = _read_stable_bytes(path, label=label)
    value = loads_canonical_json(data)
    if not isinstance(value, dict) or canonical_json_bytes(value) != data:
        raise ValidationError(f"{label} is not canonical JSON")
    return value


def _quarantine_root(session_root: Path) -> Path:
    """Return the non-authoritative quarantine owned by one migrated session."""

    return session_root / "recovery" / "legacy_quarantine"


def _inventory_manifest_bytes(files: Mapping[str, bytes]) -> bytes:
    return b"".join(
        f"{_sha256_bytes(data)}  {len(data)}  {relative}\n".encode("utf-8")
        for relative, data in sorted(files.items())
    )


def _parse_inventory_manifest(data: bytes) -> dict[str, tuple[int, str]]:
    try:
        text = data.decode("utf-8", errors="strict")
    except UnicodeDecodeError as exc:
        raise ValidationError("quarantine manifest is not UTF-8") from exc
    if "\r" in text or not text.endswith("\n"):
        raise ValidationError("quarantine manifest is not canonical LF text")
    records: dict[str, tuple[int, str]] = {}
    for line in text.splitlines():
        parts = line.split("  ")
        if len(parts) != 3:
            raise ValidationError("quarantine manifest row is malformed")
        digest = _require_sha(parts[0], "quarantine manifest sha256")
        try:
            size = int(parts[1])
        except ValueError as exc:
            raise ValidationError("quarantine manifest byte count is malformed") from exc
        relative = _portable_relative(parts[2])
        if size < 0 or relative in records:
            raise ValidationError("quarantine manifest path/size is invalid")
        records[relative] = (size, digest)
    return records


def _quarantine_files(root: Path) -> dict[str, bytes]:
    snapshot = snapshot_legacy_tree(root)
    unsafe = [
        item
        for item in snapshot["entries"]
        if item["type"] not in {"file", "directory"}
        or item["is_link_or_reparse"]
        or (item["type"] == "file" and item["link_count"] != 1)
    ]
    if unsafe:
        raise ValidationError("legacy quarantine contains an unsafe physical entry")
    return {
        item["path"]: _read_stable_bytes(root / PurePosixPath(item["path"]), label="legacy quarantine file")
        for item in snapshot["entries"]
        if item["type"] == "file"
    }


def validate_legacy_quarantine(
    session_root: os.PathLike[str] | str,
    *,
    expected_idempotency_key: str | None = None,
    expected_migration_id: str | None = None,
) -> dict[str, Any]:
    """Validate one session-owned quarantine without mutating its project."""

    session = Path(session_root)
    root = _quarantine_root(session)
    files = _quarantine_files(root)
    root_manifest_name = "MANIFEST_SHA256.txt"
    if root_manifest_name not in files:
        raise ValidationError("legacy quarantine lacks its root manifest")
    records = _parse_inventory_manifest(files[root_manifest_name])
    observed = {name: raw for name, raw in files.items() if name != root_manifest_name}
    if set(records) != set(observed):
        raise ValidationError("legacy quarantine root manifest inventory mismatch")
    for relative, (size, digest) in records.items():
        if len(observed[relative]) != size or _sha256_bytes(observed[relative]) != digest:
            raise ValidationError("legacy quarantine root manifest binding mismatch", details={"path": relative})
    status_path = root / "MIGRATION_STATUS.json"
    status = _read_canonical(status_path, label="legacy quarantine migration status")
    required = {
        "authority_role", "automatic_identity_repair", "canonical_session_role",
        "analysis_session_uid", "editable", "editable_baseline_revision", "idempotency_key",
        "image_id", "image_uid",
        "legacy_bytes_preserved", "legacy_revision_chain", "migration_id",
        "migration_status", "object_level_migration_complete", "policy_id",
        "project_uid",
        "quarantined_revision_count", "quarantined_revisions", "reconciliation_required",
        "run_input_role", "schema", "scientific_equivalence_to_latest_legacy_revision",
        "source_sha256", "statistics_role", "valid_revision_prefix",
    }
    if set(status) != required or status["schema"] != QUARANTINE_STATUS_SCHEMA:
        raise ValidationError("legacy quarantine migration status inventory mismatch")
    if (
        status["policy_id"] != QUARANTINE_POLICY_ID
        or status["migration_status"] != PARTIAL_MIGRATION_STATUS
        or status["authority_role"] != "LEGACY_EVIDENCE_ONLY"
        or status["editable"] is not False
        or status["statistics_role"] != "FORBIDDEN"
        or status["run_input_role"] != "FORBIDDEN"
        or status["canonical_session_role"] != "FORBIDDEN"
        or status["automatic_identity_repair"] is not False
        or status["legacy_bytes_preserved"] is not True
        or status["object_level_migration_complete"] is not False
        or status["scientific_equivalence_to_latest_legacy_revision"] is not False
        or status["reconciliation_required"] is not True
    ):
        raise ValidationError("legacy quarantine policy semantics mismatch")
    if expected_idempotency_key is not None and status["idempotency_key"] != expected_idempotency_key:
        raise ValidationError("legacy quarantine idempotency binding mismatch")
    if expected_migration_id is not None and status["migration_id"] != expected_migration_id:
        raise ValidationError("legacy quarantine migration identity mismatch")
    metadata = _read_canonical(session / "session_metadata.json", label="quarantine parent session metadata")
    parent_binding = {
        "analysis_session_uid": metadata.get("analysis_session_uid"),
        "image_id": metadata.get("image_id"),
        "image_uid": metadata.get("image_uid"),
        "project_uid": metadata.get("project_uid"),
        "source_sha256": metadata.get("source_sha256"),
    }
    if any(status[field] != value for field, value in parent_binding.items()):
        raise ValidationError("legacy quarantine is not bound to its physical parent session")
    valid_prefix = status["valid_revision_prefix"]
    full_chain = status["legacy_revision_chain"]
    if (
        not isinstance(valid_prefix, list)
        or not valid_prefix
        or not isinstance(full_chain, list)
        or full_chain[: len(valid_prefix)] != valid_prefix
        or status["editable_baseline_revision"] != valid_prefix[-1]
    ):
        raise ValidationError("legacy quarantine valid-prefix binding is invalid")
    if "R9_LEGACY_CONFLICTS.json" not in files:
        raise ValidationError("legacy quarantine lacks its conflict report")
    conflicts = loads_canonical_json(files["R9_LEGACY_CONFLICTS.json"])
    conflict_fields = {
        "analysis_session_uid", "automatic_mapping_proposed", "editable_baseline_revision",
        "image_id", "image_uid", "migration_id", "policy_id", "project_uid",
        "quarantined_revisions", "schema", "selected_migration_action", "source_sha256",
    }
    if (
        not isinstance(conflicts, dict)
        or set(conflicts) != conflict_fields
        or canonical_json_bytes(conflicts) != files["R9_LEGACY_CONFLICTS.json"]
        or conflicts["schema"] != QUARANTINE_CONFLICTS_SCHEMA
        or conflicts["policy_id"] != QUARANTINE_POLICY_ID
        or conflicts["migration_id"] != status["migration_id"]
        or conflicts["editable_baseline_revision"] != status["editable_baseline_revision"]
        or conflicts["automatic_mapping_proposed"] is not False
        or conflicts["selected_migration_action"] != "QUARANTINE_NO_CONVERSION"
        or any(conflicts[field] != value for field, value in parent_binding.items())
    ):
        raise ValidationError("legacy quarantine conflict report binding is invalid")
    quarantined_ids = status["quarantined_revisions"]
    if (
        not isinstance(quarantined_ids, list)
        or len(quarantined_ids) != status["quarantined_revision_count"]
        or not quarantined_ids
    ):
        raise ValidationError("legacy quarantine revision count is invalid")
    if full_chain[len(valid_prefix) :] != quarantined_ids:
        raise ValidationError("legacy quarantine tail is not the exact suffix after the valid prefix")
    conflict_ids = [item.get("revision_id") for item in conflicts["quarantined_revisions"]]
    if conflict_ids != quarantined_ids:
        raise ValidationError("legacy conflict report does not cover the quarantine tail exactly")
    for revision_id in quarantined_ids:
        validate_human_id(revision_id, field="quarantined revision_id")
        prefix = f"{revision_id}/"
        revision_files = {
            name[len(prefix):]: raw for name, raw in files.items() if name.startswith(prefix)
        }
        required_names = {"CONFLICT_REPORT.json", "MANIFEST_SHA256.txt", "QUARANTINE_MANIFEST.json"}
        if not required_names.issubset(revision_files):
            raise ValidationError("quarantined revision lacks its control files")
        revision_records = _parse_inventory_manifest(revision_files["MANIFEST_SHA256.txt"])
        revision_observed = {
            name: raw for name, raw in revision_files.items() if name != "MANIFEST_SHA256.txt"
        }
        if set(revision_records) != set(revision_observed):
            raise ValidationError("quarantined revision manifest inventory mismatch")
        for relative, (size, digest) in revision_records.items():
            if len(revision_observed[relative]) != size or _sha256_bytes(revision_observed[relative]) != digest:
                raise ValidationError("quarantined revision byte binding mismatch", details={"path": relative})
        manifest = loads_canonical_json(revision_files["QUARANTINE_MANIFEST.json"])
        manifest_fields = {
            "analysis_session_uid", "authority_role", "canonical_session_role",
            "conversion_status", "editable", "image_uid", "payload_files",
            "migration_id", "project_uid", "reconciliation_required", "revision_id", "run_input_role",
            "schema", "selected_migration_action", "source_sha256", "statistics_role",
        }
        if (
            not isinstance(manifest, dict)
            or set(manifest) != manifest_fields
            or canonical_json_bytes(manifest) != revision_files["QUARANTINE_MANIFEST.json"]
            or manifest.get("schema") != QUARANTINE_MANIFEST_SCHEMA
            or manifest.get("revision_id") != revision_id
            or manifest.get("authority_role") != "LEGACY_EVIDENCE_ONLY"
            or manifest.get("conversion_status") != "NOT_CONVERTED_IDENTITY_CONFLICT"
            or manifest.get("editable") is not False
            or manifest.get("migration_id") != status["migration_id"]
            or any(manifest.get(field) != value for field, value in parent_binding.items() if field != "image_id")
        ):
            raise ValidationError("quarantined revision manifest semantics mismatch")
        payload_records = manifest.get("payload_files")
        if not isinstance(payload_records, list):
            raise ValidationError("quarantined revision payload inventory is invalid")
        expected_payload = {
            f"payload/{record['path']}": (record["bytes"], record["sha256"])
            for record in payload_records
        }
        observed_payload = {
            name: (len(raw), _sha256_bytes(raw))
            for name, raw in revision_observed.items()
            if name.startswith("payload/")
        }
        if expected_payload != observed_payload:
            raise ValidationError("quarantined legacy payload is not byte-exact")
    return {
        "conflict_report_path": str(root / "R9_LEGACY_CONFLICTS.json"),
        "editable_baseline_revision": status["editable_baseline_revision"],
        "inventory_sha256": snapshot_legacy_tree(root)["inventory_sha256"],
        "legacy_bytes_preserved": status["legacy_bytes_preserved"],
        "migration_status": status["migration_status"],
        "object_level_migration_complete": status["object_level_migration_complete"],
        "parent_binding": parent_binding,
        "policy_id": status["policy_id"],
        "quarantine_root": str(root),
        "quarantined_revision_count": status["quarantined_revision_count"],
        "quarantined_revisions": list(quarantined_ids),
        "root_manifest_sha256": _sha256_bytes(files[root_manifest_name]),
        "scientific_equivalence_to_latest_legacy_revision": status[
            "scientific_equivalence_to_latest_legacy_revision"
        ],
        "status": "VERIFIED",
        "warning": (
            "Migración parcial segura. La revisión legacy más reciente contiene conflictos "
            "de identidad y se conserva íntegra en cuarentena. La sesión editable parte de "
            f"{status['editable_baseline_revision']}."
        ),
    }


def inspect_migration_limitation(
    session_root: os.PathLike[str] | str,
) -> dict[str, Any] | None:
    """Return one session's persistent limitation, or ``None`` when absent."""

    session = Path(session_root)
    root = _quarantine_root(session)
    if not root.exists() and not root.is_symlink():
        return None
    return validate_legacy_quarantine(session)


def _quarantine_report_markdown(plan: Mapping[str, Any]) -> bytes:
    lines = [
        "# Cuarentena legacy R9",
        "",
        f"POLICY_ID={QUARANTINE_POLICY_ID}",
        f"MIGRATION_STATUS={PARTIAL_MIGRATION_STATUS}",
        f"EDITABLE_BASELINE_REVISION={plan['revision_chain'][-1]}",
        "AUTHORITY_ROLE=LEGACY_EVIDENCE_ONLY",
        "AUTOMATIC_IDENTITY_REPAIR=false",
        "RUN_INPUT_ROLE=FORBIDDEN",
        "STATISTICS_ROLE=FORBIDDEN",
        "",
        "Las revisiones enumeradas a continuación se conservan byte a byte y no se convierten en objetos schema 2.",
        "",
    ]
    for item in plan["quarantined_revisions"]:
        lines.append(f"- {item['revision_id']}: {item['status']}; action=QUARANTINE_NO_CONVERSION")
    lines.extend(
        [
            "",
            "Una reconciliación futura exige un mapping independiente, explícito y sellado.",
            "La cuarentena no puede utilizarse en working state, current_revision, RUN ni estadística.",
            "",
        ]
    )
    return "\n".join(lines).encode("utf-8")


def _build_legacy_quarantine(
    source_root: Path,
    session_root: Path,
    *,
    plan: Mapping[str, Any],
    idempotency_key: str,
    migration_id: str,
    parent_binding: Mapping[str, str],
) -> dict[str, Any]:
    expected_parent_fields = {
        "analysis_session_uid", "image_id", "image_uid", "project_uid", "source_sha256"
    }
    if set(parent_binding) != expected_parent_fields:
        raise ValidationError("legacy quarantine parent binding inventory is not closed")
    root = _quarantine_root(session_root)
    if root.exists() or root.is_symlink():
        return validate_legacy_quarantine(
            session_root,
            expected_idempotency_key=idempotency_key,
            expected_migration_id=migration_id,
        )
    root.mkdir(parents=True)
    conflict_assessments: list[dict[str, Any]] = []
    for assessment_value in plan["quarantined_revisions"]:
        assessment = dict(assessment_value)
        revision_id = assessment["revision_id"]
        revision_root = root / revision_id
        payload_root = revision_root / "payload"
        payload_root.mkdir(parents=True)
        payload_files = list(assessment.pop("payload_files"))
        source_revision_relative = assessment.pop("source_revision_relative_path")
        revision_content: dict[str, bytes] = {}
        for record in payload_files:
            source_path = source_root / PurePosixPath(source_revision_relative) / PurePosixPath(record["path"])
            data = _read_stable_bytes(source_path, label="quarantined legacy revision payload")
            if len(data) != record["bytes"] or _sha256_bytes(data) != record["sha256"]:
                raise ValidationError("legacy revision changed before quarantine copy")
            relative = f"payload/{record['path']}"
            _write_new(revision_root / PurePosixPath(relative), data)
            revision_content[relative] = data
        conflict_bytes = canonical_json_bytes(assessment)
        _write_new(revision_root / "CONFLICT_REPORT.json", conflict_bytes)
        revision_content["CONFLICT_REPORT.json"] = conflict_bytes
        manifest = {
            "analysis_session_uid": parent_binding["analysis_session_uid"],
            "authority_role": "LEGACY_EVIDENCE_ONLY",
            "canonical_session_role": "FORBIDDEN",
            "conversion_status": "NOT_CONVERTED_IDENTITY_CONFLICT",
            "editable": False,
            "image_uid": parent_binding["image_uid"],
            "migration_id": migration_id,
            "payload_files": payload_files,
            "project_uid": parent_binding["project_uid"],
            "reconciliation_required": True,
            "revision_id": revision_id,
            "run_input_role": "FORBIDDEN",
            "schema": QUARANTINE_MANIFEST_SCHEMA,
            "selected_migration_action": "QUARANTINE_NO_CONVERSION",
            "source_sha256": parent_binding["source_sha256"],
            "statistics_role": "FORBIDDEN",
        }
        manifest_bytes = canonical_json_bytes(manifest)
        _write_new(revision_root / "QUARANTINE_MANIFEST.json", manifest_bytes)
        revision_content["QUARANTINE_MANIFEST.json"] = manifest_bytes
        revision_manifest_bytes = _inventory_manifest_bytes(revision_content)
        _write_new(revision_root / "MANIFEST_SHA256.txt", revision_manifest_bytes)
        conflict_assessments.append(assessment)
    status = {
        "analysis_session_uid": parent_binding["analysis_session_uid"],
        "authority_role": "LEGACY_EVIDENCE_ONLY",
        "automatic_identity_repair": False,
        "canonical_session_role": "FORBIDDEN",
        "editable": False,
        "editable_baseline_revision": plan["revision_chain"][-1],
        "idempotency_key": idempotency_key,
        "image_id": plan["selected_image"]["image_id"],
        "image_uid": parent_binding["image_uid"],
        "legacy_bytes_preserved": True,
        "legacy_revision_chain": list(plan["legacy_revision_chain"]),
        "migration_id": migration_id,
        "migration_status": PARTIAL_MIGRATION_STATUS,
        "object_level_migration_complete": False,
        "policy_id": QUARANTINE_POLICY_ID,
        "project_uid": parent_binding["project_uid"],
        "quarantined_revision_count": len(plan["quarantined_revisions"]),
        "quarantined_revisions": [item["revision_id"] for item in plan["quarantined_revisions"]],
        "reconciliation_required": True,
        "run_input_role": "FORBIDDEN",
        "schema": QUARANTINE_STATUS_SCHEMA,
        "scientific_equivalence_to_latest_legacy_revision": False,
        "source_sha256": parent_binding["source_sha256"],
        "statistics_role": "FORBIDDEN",
        "valid_revision_prefix": list(plan["revision_chain"]),
    }
    conflicts = {
        "analysis_session_uid": parent_binding["analysis_session_uid"],
        "automatic_mapping_proposed": False,
        "editable_baseline_revision": plan["revision_chain"][-1],
        "image_id": plan["selected_image"]["image_id"],
        "image_uid": parent_binding["image_uid"],
        "migration_id": migration_id,
        "policy_id": QUARANTINE_POLICY_ID,
        "project_uid": parent_binding["project_uid"],
        "quarantined_revisions": conflict_assessments,
        "schema": QUARANTINE_CONFLICTS_SCHEMA,
        "selected_migration_action": "QUARANTINE_NO_CONVERSION",
        "source_sha256": parent_binding["source_sha256"],
    }
    _write_new(root / "MIGRATION_STATUS.json", canonical_json_bytes(status))
    _write_new(root / "R9_LEGACY_CONFLICTS.json", canonical_json_bytes(conflicts))
    _write_new(root / "R9_LEGACY_QUARANTINE_REPORT.md", _quarantine_report_markdown(plan))
    root_content = {
        relative: raw
        for relative, raw in _quarantine_files(root).items()
        if relative != "MANIFEST_SHA256.txt"
    }
    _write_new(root / "MANIFEST_SHA256.txt", _inventory_manifest_bytes(root_content))
    return validate_legacy_quarantine(
        session_root,
        expected_idempotency_key=idempotency_key,
        expected_migration_id=migration_id,
    )


def _call_fault(hook: FaultHook | None, stage: str, evidence: Mapping[str, Any]) -> None:
    if hook is not None:
        hook(stage, evidence)


def _entities_for_revision(
    records: Sequence[Mapping[str, Any]], *, idempotency_key: str, revision_id: str
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    objects: list[dict[str, Any]] = []
    candidates: list[dict[str, Any]] = []
    for record in records:
        if record.get("record_type", "CAVITY") == "SESSION_METADATA":
            # This entry is part of the verified legacy ROI ZIP inventory and
            # remains bound by the source snapshot/ZIP SHA in migration
            # provenance.  It is deliberately not promoted to a scientific
            # cavity, candidate or object.
            continue
        material = f"{idempotency_key}|{revision_id}|{record['cavity_id']}|{record['entry_sha256']}"
        candidate_uid = _uuid4_from_material(material + "|candidate")
        object_uid = _uuid4_from_material(material + "|object")
        identity = {
            "generation_method": "DETERMINISTIC_UUIDV4_FROM_VERIFIED_LEGACY_ROI",
            "legacy_entry_name": record["entry_name"],
            "legacy_entry_sha256": record["entry_sha256"],
            "legacy_revision_id": revision_id,
        }
        candidate = {
            "candidate_id": f"MIG_{record['entry_sha256'][:20]}",
            "candidate_uuid": candidate_uid,
            "identity_provenance": identity,
            "object_uuid": object_uid,
            "review_decision": "accept",
            "review_status": "reviewed",
        }
        cavity_object: dict[str, Any] = {
            "bounds": dict(record["bounds"]),
            "candidate_uuid": candidate_uid,
            "cavity_id": record["cavity_id"],
            "center": dict(record["center"]),
            "diameter_nm": record["diameter"],
            "geometry": {
                "center_x_px": record["center"]["x"],
                "center_y_px": record["center"]["y"],
                "diameter_nm": record["diameter"],
                "height_px": record["bounds"]["height"],
                "width_px": record["bounds"]["width"],
            },
            "identity_provenance": identity,
            "legacy_properties": dict(record["properties"]),
            "object_uuid": object_uid,
        }
        for field in ("class", "depth_nm", "inclusion"):
            if field in record["properties"]:
                cavity_object[field] = record["properties"][field]
        candidates.append(candidate)
        objects.append(cavity_object)
    return objects, candidates


def _manifest_paths(target: Path) -> tuple[Path, Path]:
    manifest = target.with_name(f"{target.name}.migration_manifest.json")
    return manifest, manifest.with_suffix(manifest.suffix + ".sha256")


def _journal_path(target: Path, idempotency_key: str) -> Path:
    return target.parent / f".{target.name}.migration.{idempotency_key}.journal.json"


def _migration_result(
    target: Path,
    manifest_path: Path,
    manifest: Mapping[str, Any],
    *,
    idempotent_replay: bool,
) -> MigrationResult:
    target_info = manifest["target"]
    quarantined_ids = tuple(target_info.get("quarantined_revision_ids", ()))
    return MigrationResult(
        target_root=target,
        manifest_path=manifest_path,
        manifest_sha256=_sha256_file(manifest_path),
        idempotency_key=manifest["idempotency_key"],
        migration_id=manifest["migration_id"],
        project_uid=target_info["project_uid"],
        image_uid=target_info["image_uid"],
        analysis_session_uid=target_info["analysis_session_uid"],
        revision_ids=tuple(target_info["revision_ids"]),
        blocked_images=tuple(dict(item) for item in manifest["warnings"] if item.get("status") == BLOCKED_REVIEW),
        source_unchanged=True,
        idempotent_replay=idempotent_replay,
        migration_status=str(target_info.get("migration_classification", "COMPLETE")),
        editable_baseline_revision=target_info.get("editable_baseline_revision"),
        quarantined_revision_ids=quarantined_ids,
        quarantine_root=(
            target / PurePosixPath(target_info["legacy_quarantine"]["relative_path"])
            if quarantined_ids
            else None
        ),
    )


def migrate_legacy_project_by_copy(
    source_root: os.PathLike[str] | str,
    target_root: os.PathLike[str] | str,
    *,
    image_id: str,
    revision_chain: Sequence[str] | None = None,
    roi_exports: Mapping[str, Sequence[Mapping[str, Any]]] | None = None,
    migration_evidence: Mapping[str, Any] | None = None,
    master_pixel_evidence: Mapping[str, Any],
    created_at: str,
    target_project_uid: str | None = None,
    target_project_id: str | None = None,
    analysis_session_id: str | None = None,
    idempotency_key: str | None = None,
    _fault: FaultHook | None = None,
) -> MigrationResult:
    """Migrate one explicitly selected verified image by copy into a new root.

    The migration manifest is an adjacent sidecar because placing it in the
    project would violate P2A's closed storage-manifest inventory.  The sidecar
    is bound to the target project, image, session, revisions and final journal.
    """

    source = _require_plain_directory(Path(source_root), "legacy project root")
    target = Path(target_root)
    _require_plain_directory(target.parent, "migration target parent")
    if source.resolve() == target.resolve() or source.resolve() in target.resolve(strict=False).parents:
        raise ValidationError("migration target must be outside the read-only source")
    plan = plan_legacy_migration(
        source,
        image_id=image_id,
        revision_chain=revision_chain,
        roi_exports=roi_exports,
        migration_evidence=migration_evidence,
        master_pixel_evidence=master_pixel_evidence,
    )
    source_before = plan["source_snapshot"]
    adapter_digest = adapter_sha256()
    plan_hash = _sha256_bytes(canonical_json_bytes(plan))
    key_material = {
        "adapter_sha256": adapter_digest,
        "plan_sha256": plan_hash,
        "source_inventory_sha256": source_before["inventory_sha256"],
        "target_name": target.name,
        "target_parent_sha256": _sha256_bytes(str(target.parent.resolve()).encode("utf-8")),
    }
    identity_seed = _sha256_bytes(canonical_json_bytes(key_material))
    project_uid = target_project_uid or _uuid4_from_material(identity_seed + "|project")
    try:
        if str(uuid.UUID(project_uid)) != project_uid:
            raise ValueError
    except (ValueError, AttributeError) as exc:
        raise ValidationError("target_project_uid is not canonical") from exc
    project_id = target_project_id or f"P2_MIGRATED_{identity_seed[:12]}"
    validate_human_id(project_id, field="target_project_id")
    session_id = analysis_session_id or f"MIG_{identity_seed[:8]}"
    validate_human_id(session_id, field="analysis_session_id")
    key_material["analysis_session_id"] = session_id
    key_material["target_project_id"] = project_id
    key_material["target_project_uid"] = project_uid
    computed_key = _sha256_bytes(canonical_json_bytes(key_material))
    if idempotency_key is not None and _require_sha(idempotency_key, "idempotency_key") != computed_key:
        raise ValidationError("caller idempotency_key does not match the exact migration inputs")
    key = computed_key
    migration_id = f"MIGRATION_{key[:16].upper()}"
    # The P2A core creates deeper transaction partials of its own.  Keep this
    # outer token compact so those fail-closed paths remain Win32-addressable.
    partial = target.parent / f".{target.name}.partial.{key[:8]}"
    journal_path = _journal_path(target, key)
    manifest_path, manifest_sidecar = _manifest_paths(target)

    # Exact completed replay: do not mutate either tree or the sidecars.
    if target.exists() or target.is_symlink():
        if not target.is_dir() or target.is_symlink() or not manifest_path.is_file() or not manifest_sidecar.is_file():
            # A verified staged journal can recover the narrow crash window
            # between target publication and adjacent manifest publication.
            recoverable = journal_path.is_file() and not manifest_path.exists() and not manifest_sidecar.exists()
            if not recoverable:
                raise TransactionError("migration target already exists without exact committed authority")
        else:
            manifest = _read_canonical(manifest_path, label="migration manifest")
            manifest_bytes = manifest_path.read_bytes()
            expected_sidecar = f"{_sha256_bytes(manifest_bytes)}  {manifest_path.name}\n".encode("ascii")
            if _read_stable_bytes(manifest_sidecar, label="migration manifest SHA sidecar") != expected_sidecar:
                raise ValidationError("migration manifest SHA sidecar mismatch")
            if (
                manifest.get("schema") != MIGRATION_SCHEMA
                or manifest.get("idempotency_key") != key
                or manifest.get("adapter", {}).get("adapter_sha256") != adapter_digest
                or manifest.get("source", {}).get("inventory_sha256") != source_before["inventory_sha256"]
            ):
                raise TransactionError("existing migration does not match exact idempotency authority")
            validate_project(target)
            target_info = manifest.get("target", {})
            quarantined_ids = target_info.get("quarantined_revision_ids", [])
            if quarantined_ids:
                expected_quarantine = target_info.get("legacy_quarantine", {})
                session_relative = expected_quarantine.get("session_root_relative_path")
                if not isinstance(session_relative, str):
                    raise TransactionError("existing migration quarantine session path is absent")
                quarantine = validate_legacy_quarantine(
                    target / PurePosixPath(session_relative),
                    expected_idempotency_key=key,
                    expected_migration_id=manifest.get("migration_id"),
                )
                if (
                    quarantine["root_manifest_sha256"]
                    != expected_quarantine.get("root_manifest_sha256")
                    or quarantine["inventory_sha256"]
                    != expected_quarantine.get("inventory_sha256")
                ):
                    raise TransactionError("existing migration quarantine authority mismatch")
            if snapshot_legacy_tree(source) != source_before:
                raise ValidationError("legacy source changed during idempotent replay")
            return _migration_result(target, manifest_path, manifest, idempotent_replay=True)

    journal: dict[str, Any]
    if journal_path.exists():
        journal = _read_canonical(journal_path, label="migration journal")
        if (
            journal.get("schema") != JOURNAL_SCHEMA
            or journal.get("idempotency_key") != key
            or journal.get("adapter_sha256") != adapter_digest
            or journal.get("source_inventory_sha256") != source_before["inventory_sha256"]
            or journal.get("target_name") != target.name
            or journal.get("partial_name") != partial.name
            or journal.get("target_project_uid") != project_uid
        ):
            raise TransactionError("retained migration journal does not match exact inputs")
        if target.exists() and journal.get("checkpoint") != "VERIFIED_STAGED":
            raise TransactionError("published target lacks a verified staged journal")
        created = journal["created_at"]
        journal["migration_status"] = "COPYING"
        journal["last_error"] = None
        _replace_journal(journal_path, journal)
    else:
        if target.exists() or partial.exists() or partial.is_symlink():
            raise TransactionError("new migration target or deterministic partial already exists")
        # SessionCore validates this timestamp when it creates the project.
        created = created_at
        journal = {
            "adapter_sha256": adapter_digest,
            "checkpoint": "PLANNED",
            "completed_revisions": [],
            "created_at": created,
            "idempotency_key": key,
            "last_error": None,
            "mapping_journal": [],
            "migration_id": migration_id,
            "migration_status": "PLANNED",
            "partial_name": partial.name,
            "schema": JOURNAL_SCHEMA,
            "source_inventory_sha256": source_before["inventory_sha256"],
            "target_name": target.name,
            "target_project_uid": project_uid,
        }
        _replace_journal(journal_path, journal)

    try:
        _call_fault(_fault, "MIGRATION_PLANNED", {"migration_id": migration_id})
        if journal["checkpoint"] == "PLANNED":
            create_project(partial, project_uid=project_uid, project_id=project_id, created_at=created)
            journal["checkpoint"] = "PROJECT_CREATED"
            journal["migration_status"] = "COPYING"
            _replace_journal(journal_path, journal)
        core = SessionCore(partial if partial.exists() else target)
        _call_fault(_fault, "PROJECT_CREATED", {"project_uid": project_uid})

        selected = plan["selected_image"]
        checkpoint = journal["checkpoint"]
        if checkpoint == "PROJECT_CREATED":
            source_path = source / PurePosixPath(selected["source_relative_path"])
            source_bytes = _read_stable_bytes(source_path, label="legacy source selected for copy")
            if _sha256_bytes(source_bytes) != selected["source_sha256"]:
                raise ValidationError("selected legacy source changed after planning")
            identity_provenance = {
                "field_status": {
                    "condition_id": "NOT_VERIFIED",
                    "lamella_id": "NOT_VERIFIED",
                    "specimen_id": "NOT_VERIFIED",
                    "study_id": "NOT_VERIFIED",
                },
                "legacy_condition_observed": selected["condition"],
                "legacy_image_id": selected["image_id"],
                "legacy_project_uid": plan["project_uid"],
                "legacy_sample_observed": selected["sample_name"],
                "method": "EXPLICIT_LEGACY_COPY_MAPPING_V1",
                "source_sha256": selected["source_sha256"],
            }
            binding_record = core.register_source_image(
                source_bytes,
                # Compact physical sentinels keep the supported Win32 path
                # below legacy MAX_PATH while provenance carries the exact
                # NOT_VERIFIED semantics; they never pretend to be science.
                study_id="LS_NV",
                condition_id="LC_NV",
                specimen_id="LSP_NV",
                lamella_id="LL_NV",
                image_id=selected["image_id"],
                identity_provenance=identity_provenance,
                source_file_name=selected["source_file_name"],
                master_pixel_hash_method=plan["master_pixel_evidence"]["method"],
                master_pixel_hash_status="VERIFIED",
                master_pixel_sha256=plan["master_pixel_evidence"]["hash"],
                updated_at=created,
            )
            journal["checkpoint"] = "SOURCE_REGISTERED"
            journal["image_uid"] = binding_record.image_uid
            journal["mapping_journal"].append(
                {
                    "source": selected["source_relative_path"],
                    "source_sha256": selected["source_sha256"],
                    "status": "VERIFIED_COPIED",
                    "target": f"source_registry:{binding_record.image_uid}",
                }
            )
            _replace_journal(journal_path, journal)
        binding = core._binding(journal["image_uid"])
        _call_fault(_fault, "SOURCE_REGISTERED", {"image_uid": binding["image_uid"]})

        if journal["checkpoint"] == "SOURCE_REGISTERED":
            current, generation, registry_sha = core._selection_snapshot(binding["image_uid"])
            if current is not None:
                raise TransactionError("new migrated image unexpectedly already has a current session")
            session_uid = _uuid4_from_material(key + "|session")
            session_partial, _metadata = core._new_session_partial(
                binding,
                session_id=session_id,
                session_uid=session_uid,
                origin_type=SESSION_ORIGIN,
                canonical_role="CANONICAL",
                created_at=created,
                clone_provenance=None,
                working_objects=(),
                working_candidates=(),
                base_revision_sha256=None,
            )
            session_final = session_partial.parent / session_partial.name.split(".partial.", 1)[0]
            rename_directory_no_replace(session_partial, session_final, error_type=TransactionError)
            core._select_published_session(
                binding,
                session_final,
                expected_current_generation=generation,
                expected_registry_sha256=registry_sha,
                created_at=created,
                _fault=None,
            )
            core.refresh_storage_manifest()
            journal["analysis_session_uid"] = session_uid
            journal["checkpoint"] = "SESSION_PUBLISHED"
            journal["mapping_journal"].append(
                {
                    "source": f"legacy_session:{selected['image_id']}",
                    "status": "MIGRATED_LEGACY_BRIDGE",
                    "target": f"analysis_session:{session_uid}",
                }
            )
            _replace_journal(journal_path, journal)
        session_uid = journal["analysis_session_uid"]
        _call_fault(_fault, "SESSION_PUBLISHED", {"analysis_session_uid": session_uid})

        completed = list(journal["completed_revisions"])
        expected_prefix = [item["revision_id"] for item in plan["revisions"][: len(completed)]]
        if completed != expected_prefix:
            raise TransactionError("migration revision journal is not an exact plan prefix")
        for revision in plan["revisions"][len(completed) :]:
            objects, candidates = _entities_for_revision(
                revision["roi_records"], idempotency_key=key, revision_id=revision["revision_id"]
            )
            record = core.session_by_uid(binding["image_uid"], session_uid)
            pointer_sha = _sha256_file(record.session_root / "current_revision.tsv")
            revision_uid = _uuid4_from_material(key + "|revision|" + revision["revision_id"])
            core.publish_revision(
                binding["image_uid"],
                session_uid,
                revision_id=revision["revision_id"],
                objects=objects,
                candidates=candidates,
                identity_provenance=(
                    {
                        "legacy_revision_id": revision["revision_id"],
                        "legacy_roi_zip_sha256": revision["roi_zip_sha256"],
                        "migration_id": migration_id,
                        "status": "VERIFIED_EXPLICIT_FIJI_EXPORT",
                    },
                ),
                revision_uid=revision_uid,
                parent_revision_id=revision["parent_revision"],
                expected_pointer_sha256=pointer_sha,
                created_at=_timestamp_from_milliseconds(revision["created_ms"]),
            )
            completed.append(revision["revision_id"])
            journal["completed_revisions"] = list(completed)
            journal["checkpoint"] = "REVISION_CHAIN_COPYING"
            journal["mapping_journal"].append(
                {
                    "roi_count": revision["roi_count"],
                    "source": revision["roi_zip_relative_path"],
                    "source_sha256": revision["roi_zip_sha256"],
                    "status": "VERIFIED_EXPLICIT_FIJI_EXPORT",
                    "target": f"revision:{revision['revision_id']}",
                }
            )
            _replace_journal(journal_path, journal)
            _call_fault(
                _fault,
                "REVISION_PUBLISHED",
                {"revision_id": revision["revision_id"], "revision_count": len(completed)},
            )

        if completed != list(plan["revision_chain"]):
            raise TransactionError("migration did not publish the exact revision chain")

        # A migrated session is immediately editable from the last member of
        # the strictly valid prefix.  Publishing immutable revisions alone is
        # insufficient: a newly-created session starts with an empty working
        # state, and session selection reads that working state rather than
        # implicitly loading current_revision.tsv.  Seed it from the exact,
        # already-verified final prefix revision.  This is a byte-authority
        # transfer inside schema 2, not an identity inference.
        baseline_revision = plan["revisions"][-1]
        baseline_revision_id = baseline_revision["revision_id"]
        planned_objects, planned_candidates = _entities_for_revision(
            baseline_revision["roi_records"],
            idempotency_key=key,
            revision_id=baseline_revision_id,
        )
        baseline_record = core.session_by_uid(binding["image_uid"], session_uid)
        baseline_revision_root = (
            baseline_record.session_root
            / "revisions"
            / f"REV_{baseline_revision_id}"
        )
        baseline_manifest = core._verify_revision(
            baseline_record, baseline_revision_root
        )
        baseline_manifest_sha = _sha256_file(
            baseline_revision_root / "revision_manifest.json"
        )
        expected_objects, expected_candidates = core._normalize_revision_entities(
            planned_objects, planned_candidates
        )
        if (
            baseline_manifest.get("revision_id") != baseline_revision_id
            or canonical_json_bytes(
                {
                    "candidates": baseline_manifest.get("candidates"),
                    "objects": baseline_manifest.get("objects"),
                }
            )
            != canonical_json_bytes(
                {"candidates": expected_candidates, "objects": expected_objects}
            )
        ):
            raise TransactionError(
                "editable baseline revision differs from the exact valid-prefix plan"
            )
        baseline_objects = list(baseline_manifest["objects"])
        baseline_candidates = list(baseline_manifest["candidates"])
        working_path = baseline_record.session_root / "working" / "working_state.json"
        pristine_working = core._working_state(
            session_uid=session_uid,
            working_state_id="WORKING_000001",
            source_revision_sha256=None,
            objects=(),
            candidates=(),
            created_at=created,
        )
        seeded_working = dict(pristine_working)
        seeded_working["base_revision_manifest_sha256"] = baseline_manifest_sha
        seeded_working["objects"] = baseline_objects
        seeded_working["candidates"] = baseline_candidates
        seeded_working["generation"] = 2
        seeded_working["updated_at"] = created
        working = _read_canonical(working_path, label="migrated editable working state")
        if working == pristine_working:
            seeded_sha = core.update_working_state(
                binding["image_uid"],
                session_uid,
                objects=baseline_objects,
                candidates=baseline_candidates,
                expected_working_sha256=_sha256_file(working_path),
                bind_base_revision_manifest_sha256=baseline_manifest_sha,
                updated_at=created,
            )
            working = _read_canonical(
                working_path, label="seeded migrated editable working state"
            )
            if working != seeded_working or seeded_sha != _sha256_file(working_path):
                raise TransactionError("seeded working state is not exact")
        elif working == seeded_working:
            seeded_sha = _sha256_file(working_path)
        else:
            raise TransactionError(
                "migrated working state is neither pristine nor the exact editable baseline"
            )
        _call_fault(
            _fault,
            "WORKING_BASELINE_COMMITTED",
            {
                "analysis_session_uid": session_uid,
                "revision_id": baseline_revision_id,
                "working_state_sha256": seeded_sha,
            },
        )
        expected_baseline_mapping = {
            "candidate_count": len(baseline_candidates),
            "object_count": len(baseline_objects),
            "revision_manifest_sha256": baseline_manifest_sha,
            "source": f"revision:{baseline_revision_id}",
            "status": "VERIFIED_EXACT_WORKING_BASELINE",
            "target": f"working_state:{session_uid}",
            "working_state_sha256": seeded_sha,
        }
        baseline_mappings = [
            item
            for item in journal["mapping_journal"]
            if item.get("status") == "VERIFIED_EXACT_WORKING_BASELINE"
        ]
        if journal["checkpoint"] == "REVISION_CHAIN_COPYING":
            if baseline_mappings:
                raise TransactionError("working baseline mapping precedes its checkpoint")
            journal["checkpoint"] = "WORKING_BASELINE_SEEDED"
            journal["mapping_journal"].append(expected_baseline_mapping)
            _replace_journal(journal_path, journal)
        elif journal["checkpoint"] in {"WORKING_BASELINE_SEEDED", "VERIFIED_STAGED"}:
            if baseline_mappings != [expected_baseline_mapping]:
                raise TransactionError("working baseline checkpoint mapping is not exact")
        else:
            raise TransactionError("migration checkpoint cannot bind the editable baseline")
        _call_fault(
            _fault,
            "WORKING_BASELINE_SEEDED",
            {
                "analysis_session_uid": session_uid,
                "candidate_count": len(baseline_candidates),
                "object_count": len(baseline_objects),
                "revision_id": baseline_revision_id,
                "revision_manifest_sha256": baseline_manifest_sha,
                "working_state_sha256": seeded_sha,
            },
        )
        staged_root = partial if partial.exists() else target
        migrated_record = core.session_by_uid(binding["image_uid"], session_uid)
        session_root_relative = migrated_record.session_root.relative_to(staged_root).as_posix()
        quarantine_relative = f"{session_root_relative}/recovery/legacy_quarantine"
        quarantine_validation: dict[str, Any] | None = None
        if plan["quarantined_revisions"]:
            quarantine_validation = _build_legacy_quarantine(
                source,
                migrated_record.session_root,
                plan=plan,
                idempotency_key=key,
                migration_id=migration_id,
                parent_binding={
                    "analysis_session_uid": session_uid,
                    "image_id": selected["image_id"],
                    "image_uid": binding["image_uid"],
                    "project_uid": project_uid,
                    "source_sha256": selected["source_sha256"],
                },
            )
            journal["quarantine_inventory_sha256"] = quarantine_validation["inventory_sha256"]
            journal["quarantine_root_manifest_sha256"] = quarantine_validation["root_manifest_sha256"]
            journal["quarantined_revisions"] = list(quarantine_validation["quarantined_revisions"])
            _replace_journal(journal_path, journal)
            _call_fault(
                _fault,
                "LEGACY_QUARANTINE_VERIFIED",
                {
                    "quarantined_revision_count": quarantine_validation["quarantined_revision_count"],
                    "root_manifest_sha256": quarantine_validation["root_manifest_sha256"],
                },
            )
        core.refresh_storage_manifest()
        validation = validate_project(staged_root)
        if validation.image_count != 1 or validation.session_count != 1 or validation.revision_count != len(completed):
            raise ValidationError("staged migration validation counts are not exact")
        source_after = snapshot_legacy_tree(source)
        if source_after != source_before:
            raise ValidationError("legacy source changed during migration")
        journal["checkpoint"] = "VERIFIED_STAGED"
        journal["migration_status"] = "VERIFIED_STAGED"
        journal["last_error"] = None
        _replace_journal(journal_path, journal)
        _call_fault(_fault, "VERIFIED_STAGED", {"migration_id": migration_id})
        journal_bytes = _read_stable_bytes(journal_path, label="verified migration journal")
        journal_sha = _sha256_bytes(journal_bytes)

        manifest: dict[str, Any] = {
            "adapter": {
                "adapter_id": ADAPTER_ID,
                "adapter_sha256": adapter_digest,
                "adapter_version": ADAPTER_VERSION,
                "support": {"R5_R7": "UNTESTED", "R8_R9": "VERIFIED_EXPLICIT_COPY_ONLY"},
            },
            "created_at": created,
            "field_mapping": [
                {"source_field": "legacy.source_sha256", "status": "EXPLICIT", "target_field": "source_registry.source_sha256"},
                {"source_field": "legacy.image_id", "status": "EXPLICIT", "target_field": "image_id"},
                {
                    "source_field": (
                        "legacy.valid_revision_prefix"
                        if plan["quarantined_revisions"]
                        else "legacy.revision_chain"
                    ),
                    "status": (
                        "EXPLICIT_CONSISTENT_PREFIX_ONLY"
                        if plan["quarantined_revisions"]
                        else "EXPLICIT"
                    ),
                    "target_field": "session.revisions",
                },
                *(
                    [
                        {
                            "source_field": "legacy.quarantined_tail",
                            "status": "LEGACY_EVIDENCE_ONLY_NOT_CONVERTED",
                            "target_field": "session.recovery.legacy_quarantine",
                        }
                    ]
                    if plan["quarantined_revisions"]
                    else []
                ),
                {"source_field": "legacy.current_revision.txt", "status": "OBSERVED_NON_AUTHORITATIVE_NOT_MIGRATED", "target_field": "NONE"},
                {"source_field": "legacy.current_run", "status": "DEFERRED_NOT_MIGRATED", "target_field": "NONE"},
                {"source_field": "legacy.text_encoding", "status": plan["text_decoding_policy"], "target_field": "UTF8_CANONICAL_OUTPUT"},
            ],
            "idempotency_key": key,
            "inferences": [
                {"field": field, "status": "NOT_VERIFIED", "value": None}
                for field in ("study_id", "condition_id", "specimen_id", "lamella_id")
            ],
            "journal": {"checkpoint": "VERIFIED_STAGED", "journal_sha256": journal_sha},
            "migration_id": migration_id,
            "migration_status": "COMMITTED",
            "schema": MIGRATION_SCHEMA,
            "source": {
                "entry_count": source_before["entry_count"],
                "inventory_sha256": source_before["inventory_sha256"],
                "project_schema_version": 1,
                "read_only": True,
                "root_alias": f"LEGACY_SOURCE_{source_before['inventory_sha256'][:12].upper()}",
                "text_decoding_policy": plan["text_decoding_policy"],
            },
            "target": {
                "analysis_session_uid": session_uid,
                "image_uid": binding["image_uid"],
                "is_new_copy": True,
                "manifest_location": "ADJACENT_SIDECAR_OUTSIDE_CLOSED_P2A_INVENTORY",
                "migration_classification": plan["migration_status"],
                "migration_policy": {
                    "policy_id": plan["policy_id"],
                    "revision_dispositions": [
                        {
                            "revision_id": item["revision_id"],
                            "selected_migration_action": item["selected_migration_action"],
                            "status": item["status"],
                        }
                        for item in plan["revision_assessments"]
                    ],
                },
                "editable_baseline_revision": completed[-1],
                "legacy_bytes_preserved": bool(plan["quarantined_revisions"]),
                "legacy_quarantine": (
                    None
                    if quarantine_validation is None
                    else {
                        "authority_role": "LEGACY_EVIDENCE_ONLY",
                        "inventory_sha256": quarantine_validation["inventory_sha256"],
                        "relative_path": quarantine_relative,
                        "root_manifest_sha256": quarantine_validation["root_manifest_sha256"],
                        "session_root_relative_path": session_root_relative,
                    }
                ),
                "legacy_revision_chain": list(plan["legacy_revision_chain"]),
                "object_level_migration_complete": not bool(plan["quarantined_revisions"]),
                "project_schema_version": 2,
                "project_uid": project_uid,
                "quarantined_revision_ids": [
                    item["revision_id"] for item in plan["quarantined_revisions"]
                ],
                "revision_ids": list(completed),
                "root_alias": f"V2_TARGET_{key[:12].upper()}",
                "scientific_equivalence_to_latest_legacy_revision": False,
            },
            # The shared canonical serializer gives every ``warnings`` array a
            # stable (code, path, row, column) order.  Keep those generic
            # ordering fields while retaining migration-specific evidence.
            "warnings": sorted(
                [
                    *[
                        {
                            "code": item["reason"],
                            "column": None,
                            "image_id": item["image_id"],
                            "path": f"legacy_image:{item['image_id']}",
                            "reason": item["reason"],
                            "row": None,
                            "status": item["status"],
                        }
                        for item in plan["blocked_images"]
                    ],
                    {
                        "code": "LEGACY_RUN_MIGRATION_DEFERRED_TO_P2C",
                        "column": None,
                        "path": "legacy_run",
                        "reason": "LEGACY_RUN_MIGRATION_DEFERRED_TO_P2C",
                        "row": None,
                        "status": "NOT_MIGRATED",
                    },
                    {
                        "code": "HIERARCHY_FIELDS_NOT_DEMONSTRABLE_FROM_R9_EVIDENCE",
                        "column": None,
                        "path": "legacy_hierarchy",
                        "reason": "HIERARCHY_FIELDS_NOT_DEMONSTRABLE_FROM_R9_EVIDENCE",
                        "row": None,
                        "status": "NOT_VERIFIED",
                    },
                    *(
                        [
                            {
                                "code": "PARTIAL_WITH_LEGACY_QUARANTINE",
                                "column": None,
                                "path": quarantine_relative,
                                "reason": "LATEST_LEGACY_REVISION_NOT_CONVERTED_IDENTITY_CONFLICT",
                                "row": None,
                                "status": "LIMITATION_VISIBLE_IN_UI",
                            }
                        ]
                        if plan["quarantined_revisions"]
                        else []
                    ),
                ],
                key=lambda item: (item["code"], item["path"]),
            ),
        }
        manifest_bytes = canonical_json_bytes(manifest)
        manifest_sha = _sha256_bytes(manifest_bytes)
        if partial.exists():
            rename_directory_no_replace(partial, target, error_type=TransactionError)
        validate_project(target)
        if plan["quarantined_revisions"]:
            final_quarantine = validate_legacy_quarantine(
                target / PurePosixPath(session_root_relative),
                expected_idempotency_key=key,
                expected_migration_id=migration_id,
            )
            if (
                quarantine_validation is None
                or final_quarantine["inventory_sha256"] != quarantine_validation["inventory_sha256"]
                or final_quarantine["root_manifest_sha256"] != quarantine_validation["root_manifest_sha256"]
            ):
                raise TransactionError("published legacy quarantine differs from verified staging")
        if snapshot_legacy_tree(source) != source_before:
            raise ValidationError("legacy source changed at migration commit")
        _write_new(manifest_path, manifest_bytes)
        _write_new(manifest_sidecar, f"{manifest_sha}  {manifest_path.name}\n".encode("ascii"))
        return _migration_result(target, manifest_path, manifest, idempotent_replay=False)
    except BaseException as exc:
        if journal_path.exists() and not manifest_path.exists():
            try:
                retained = _read_canonical(journal_path, label="migration journal after failure")
                retained["last_error"] = type(exc).__name__
                retained["migration_status"] = "FAILED_PARTIAL"
                _replace_journal(journal_path, retained)
            except BaseException:
                pass
        if snapshot_legacy_tree(source) != source_before:
            raise TransactionError("migration failed and the read-only source changed") from exc
        raise
