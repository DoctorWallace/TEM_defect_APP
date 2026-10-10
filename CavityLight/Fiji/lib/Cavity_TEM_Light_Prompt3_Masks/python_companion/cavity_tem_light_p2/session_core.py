"""Approved Prompt-2A storage, identity, pointer and clone core.

The module has no Fiji dependency and never discovers authority using dates,
directory mtimes, lexical order, ``latest`` names or the highest identifier.
Every selection and clone source is explicit.  Mutable pointers use caller
snapshots (generation plus exact SHA-256) and retain a session-scoped journal.

The ten approved physical profiles in ``contract_supplement_p2`` remain input
contracts.  This module materialises the nested records that those profiles
type as ``object``/``array`` under implementation-local schema identifiers;
it does not edit or reinterpret the approved profile bytes.
"""

from __future__ import annotations

import base64
import binascii
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
import subprocess
import unicodedata
import uuid
from typing import Any, Callable, Iterable, Mapping, Sequence

from cavity_tem_light_p1.canonical_json import canonical_json_bytes, loads_canonical_json
from cavity_tem_light_p1.errors import StaleContextError, TransactionError, ValidationError
from cavity_tem_light_p1.identity import (
    CTL_UUID_NAMESPACE_V1,
    confirmed_image_parent_component,
    derive_image_uid,
    new_uuid4_identity,
    validate_canonical_uuid,
    validate_cavity_id,
    validate_human_id,
)
from cavity_tem_light_p1.object_table_profile import load_object_table_profile
from cavity_tem_light_p1.path_safety import (
    PathSafetyError,
    is_reparse_or_link,
    plain_directory,
    plain_file,
    rename_directory_no_replace,
    stable_plain_bytes,
)
from cavity_tem_light_p1.run_consumer import load_current_run, verify_run_directory
from cavity_tem_light_p1.run_context import load_run_context
from cavity_tem_light_p1.run_disposition import (
    DISPOSITION_SCHEMA,
    is_run_disposition_file_name,
    validate_run_disposition_directory,
)
from cavity_tem_light_p1.run_transaction import (
    PayloadSpec,
    RunRegistry,
    ValidationEvidence,
    publish_run as publish_p1_run,
)


SESSION_REGISTRY_FIELDS = (
    "registry_version",
    "project_uid",
    "image_uid",
    "analysis_session_uid",
    "analysis_session_id",
    "relative_path",
    "session_metadata_sha256",
    "origin_type",
    "lifecycle",
    "canonical_role",
    "operator_status",
    "restricted_evidence_ref_sha256",
    "created_at",
    "updated_at",
    "generation",
    "object_count",
    "revision_count",
    "run_count",
    "logical_bytes",
    "physical_bytes",
    "compressed_bytes_status",
    "compressed_bytes",
    "integrity_status",
)
CURRENT_SESSION_FIELDS = (
    "pointer_version",
    "project_uid",
    "image_uid",
    "analysis_session_uid",
    "analysis_session_id",
    "relative_path",
    "session_metadata_sha256",
    "session_registry_sha256",
    "generation",
    "updated_at",
)
CURRENT_REVISION_FIELDS = (
    "pointer_version",
    "project_uid",
    "image_uid",
    "analysis_session_uid",
    "revision_uid",
    "revision_id",
    "relative_path",
    "revision_manifest_sha256",
    "generation",
    "updated_at",
)
CURRENT_RUN_FIELDS = (
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
SESSION_METADATA_FIELDS = frozenset(
    {
        "analysis_session_id",
        "analysis_session_uid",
        "canonical_role",
        "clone_provenance_sha256",
        "clone_provenance_status",
        "created_at",
        "generation",
        "image_id",
        "image_uid",
        "lifecycle",
        "master_pixel_hash_method",
        "master_pixel_hash_status",
        "master_pixel_sha256",
        "origin_type",
        "project_uid",
        "restricted_evidence_ref_sha256",
        "restricted_evidence_status",
        "schema",
        "source_sha256",
        "updated_at",
        "working_state_id",
        "working_state_sha256",
    }
)

SESSION_REGISTRY_HEADER = "\t".join(SESSION_REGISTRY_FIELDS) + "\n"
CURRENT_SESSION_HEADER = "\t".join(CURRENT_SESSION_FIELDS) + "\n"
CURRENT_REVISION_HEADER = "\t".join(CURRENT_REVISION_FIELDS) + "\n"
CURRENT_RUN_HEADER = "\t".join(CURRENT_RUN_FIELDS) + "\n"

APPROVED_PROFILE_HASHES = {
    "CTL_SCHEMA_V2_STORAGE_PROFILE_V1": "7268894d948c643e5eb7624163929f364599a80e1e404de1f58a3082604fd1bb",
    "CTL_SESSION_REGISTRY_TSV_V1": "0dd0f4891510d81cd047817e565cc46481aafbbd15387b63787dfa4004f60763",
    "CTL_SESSION_METADATA_JSON_V1": "7722b33409673f7b503f88cbc331dbb814f753b3786623398437404508762f67",
    "CTL_CURRENT_SESSION_TSV_V1": "3dc18da9b258aec7e9127cc6d7adc1a0f1d41e72362685017c9ed50b114117f9",
    "CTL_CURRENT_REVISION_TSV_V1": "5f83eb86b1cb8e9e7799999355882735e1e6ed69309c6fa479bccd15977c2e36",
    "CTL_SESSION_CLONE_PROVENANCE_V1": "fa3ce99a3bd3a5dd53a7b514d0e3c95855743a01deed5933189ecc2a64d3da84",
    "CTL_SOURCE_REGISTRY_V1": "a6afa5644b7b17944d5df035eb87f059c8656935d85a649376f12505de86013e",
    "CTL_MIGRATION_MANIFEST_V1": "d75ffaf20f8b41c8c3bbc8f4b72a92625b3b7efad18d76e1b563a55964e92bd9",
    "CTL_SESSION_ARCHIVE_V1": "457b13f1e81f6af76aa14662a1200209cba8d745991964870532b5fbbe8c4ed2",
    "CTL_RESTRICTED_EVIDENCE_SPLIT_V1": "b724c1aa01ce26d17eb436dea1bd1247c547a477f62b6978d0d63d2cb9342f19",
}
APPROVED_PROFILE_INDEX_SHA256 = "b211879ab533010982f4a55af5b8e9e750db51db84ee65ceac08be4bf5664574"
APPROVED_ADDENDUM_SHA256 = "f78ef1274ad18381c67254e4d4c589f50c67018120831cf9a7b99037daba361c"
APPROVED_SUPPLEMENT_SHA256 = "2cbbdf2443062342aab23021fb17d2e7c9bfcbc183b5a94f2830c74c5c6c7ddf"
APPROVED_APPROVAL_RECORD_SHA256 = "068ea44927e87317d18c0e5d5a8be5f30ebddac70d8d8d13126d8d20b64a0d6f"
EFFECTIVE_CONTRACT_RECORD_SHA256 = "6cc70963688e8a094ae6e597809de595cc569a4d753e666fefdd02ce0379abbe"
CORRECTION_APPROVAL_RECORD_SHA256 = "bc0057f2834570e1212bb8158f89d24f7961d7ffd904a3b316499ce2abbebe90"
CORRECTION_INDEX_SHA256 = "ee324af4d902734c555713ae997b0dfa50258e0e95a59a38a55ba203df4ff0ed"
CORRECTION_ADDENDUM_SHA256 = "055977402dea12ca81ffda7431b586a4cb2d22a0d53f550f73363b9da635006f"
CORRECTION_ORACLE_INDEX_SHA256 = "966d9a56d9288e16cf288e5347124d2a407449ec2a6b2f32a7a3de13ed536812"
CORRECTION_PROFILE_FILES = {
    "CTL_RUN_V2_SCHEMA2_NATIVE_ADAPTER_V1": (
        "70bc666aeb052d14d5f7653ce4d8c00ab31fbddfba6146e045254bb98b0ca35a",
        "7f64bf00eefb1b336d9068fb417215370f41cd11f0e3735b8c3adc0286f7ad1a",
    ),
    "CTL_SESSION_CLONE_PROVENANCE_V2": (
        "800c65e92d30c07b21854af039fab9c10f29b86fdf5fb27c7e60a5c50a2674cf",
        "3aa658739cd2dbeb184f4a61558ef83bf1608d0693d0cacb5cf99790667617a6",
    ),
}

SHA_RE = re.compile(r"^[0-9a-f]{64}$", re.ASCII)
RFC3339_Z_RE = re.compile(
    r"^[0-9]{4}-(?:0[1-9]|1[0-2])-(?:0[1-9]|[12][0-9]|3[01])T"
    r"(?:[01][0-9]|2[0-3]):[0-5][0-9]:[0-5][0-9](?:\.[0-9]{1,6})?Z$",
    re.ASCII,
)
FORBIDDEN_PATH_NAMES = frozenset(
    {"CON", "PRN", "AUX", "NUL"}
    | {f"COM{index}" for index in range(1, 10)}
    | {f"LPT{index}" for index in range(1, 10)}
)
ORIGIN_TYPES = frozenset(
    {"NEW_EMPTY", "CLONE_REVISION", "MIGRATED_LEGACY_BRIDGE", "RESTORED_ARCHIVE"}
)
LIFECYCLES = frozenset({"CURRENT", "HISTORICAL", "ARCHIVED", "QUARANTINED"})
CANONICAL_ROLES = frozenset({"CANONICAL", "NON_CANONICAL"})
MASTER_STATUSES = frozenset({"VERIFIED", "NOT_VERIFIED", "UNKNOWN"})
CLONE_REVIEW_DECISIONS = frozenset(
    {"pending", "accept", "adjust_and_accept", "mark_uncertain", "mark_possible_artifact", "reject"}
)
CLONE_LINK_STATUSES = frozenset(
    {"LINKED_OBJECT", "NOT_APPLICABLE_PENDING", "NOT_APPLICABLE_REJECTED"}
)
CLONE_PROVENANCE_V3_SCHEMA = "CTL_SESSION_CLONE_PROVENANCE_V3"
CLONE_GEOMETRY_IDENTITY_MODE = "PRESERVED_EXACT_FROM_EXPLICIT_REVISION"
CLONE_GEOMETRY_IDENTITY_DISPOSITION = "PRESERVED_EXACT_SCIENTIFIC_IDENTITY"
P3_GEOMETRY_TYPES = frozenset({"analysis_mask", "exclusion", "surface"})
P3_GEOMETRY_REQUIRED_FIELDS = frozenset(
    {
        "bounds",
        "coordinates",
        "geometry_id",
        "geometry_schema",
        "geometry_type",
        "geometry_uid",
        "labels",
        "roi_bytes_base64",
        "roi_bytes_sha256",
        "source_roi_sha256",
    }
)
P3_GEOMETRY_FIELDS = P3_GEOMETRY_REQUIRED_FIELDS | {"geometry_sha256"}
SOURCE_REGISTRY_JOURNAL_SCHEMA = "CTL_P2A_SOURCE_REGISTRY_JOURNAL_V1"
SOURCE_REGISTRY_JOURNAL_STATES = frozenset(
    {
        "PREPARED",
        "RECOVERY_REQUIRED",
        "IMAGE_PUBLISHED_PENDING_REGISTRY",
        "REGISTRY_PUBLISHED_PENDING_COMMIT",
        "COMMITTED",
        "COMMITTED_RECOVERED",
        "ROLLED_BACK",
        "ROLLED_BACK_RECOVERED",
        "BLOCKED_RECOVERY",
    }
)
SOURCE_REGISTRY_JOURNAL_PENDING_STATES = frozenset(
    {
        "PREPARED",
        "RECOVERY_REQUIRED",
        "IMAGE_PUBLISHED_PENDING_REGISTRY",
        "REGISTRY_PUBLISHED_PENDING_COMMIT",
    }
)
SOURCE_REGISTRY_JOURNAL_RECOVERY_ACTIONS = frozenset(
    {
        "RECOVERY_REQUIRED",
        "NONE",
        "QUARANTINE_UNREGISTERED_IMAGE",
        "FINALIZE_ROLLED_BACK",
        "FINALIZE_COMMITTED",
        "BLOCKED_NO_MUTATION",
    }
)
SOURCE_REGISTRY_JOURNAL_FIELDS = frozenset(
    {
        "blob_partial_relative_path",
        "blob_recovery_relative_path",
        "blob_relative_path",
        "blob_was_preexisting",
        "created_at",
        "image_binding_sha256",
        "image_descriptor_sha256",
        "image_id",
        "image_partial_relative_path",
        "image_relative_path",
        "image_uid",
        "image_was_published",
        "new_registry_sha256",
        "observed_registry_sha256",
        "old_registry_sha256",
        "parent_scope_key",
        "project_uid",
        "quarantine_relative_path",
        "recovery_action",
        "registry_was_replaced",
        "schema",
        "source_byte_size",
        "source_sha256",
        "state",
        "transaction_id",
        "updated_at",
    }
)

FaultHook = Callable[[str, Mapping[str, Any]], None]


@dataclass(frozen=True)
class ImageBinding:
    project_uid: str
    image_uid: str
    image_id: str
    parent_scope_key: str
    source_sha256: str
    image_root: Path
    alias_reused: bool


@dataclass(frozen=True)
class SessionRecord:
    project_uid: str
    image_uid: str
    analysis_session_uid: str
    analysis_session_id: str
    session_root: Path
    generation: int


@dataclass(frozen=True)
class SelectionResult:
    result: str
    scientific_mutations: int
    roi_manager_changes: int
    disk_writes: str
    previous_session_uid: str | None
    selected_session_uid: str | None
    generation: int


@dataclass(frozen=True)
class PublishedRevision:
    revision_id: str
    revision_uid: str
    revision_manifest_sha256: str
    revision_root: Path
    generation: int


@dataclass(frozen=True)
class PublishedRun:
    run_id: str
    run_uid: str
    run_manifest_sha256: str
    run_root: Path
    generation: int


@dataclass(frozen=True)
class CloneResult:
    session: SessionRecord
    genesis_revision: PublishedRevision
    clone_provenance_sha256: str
    object_mappings: tuple[dict[str, Any], ...]
    candidate_mappings: tuple[dict[str, Any], ...]
    geometry_mappings: tuple[dict[str, Any], ...]


@dataclass(frozen=True)
class ProjectValidation:
    project_uid: str
    image_count: int
    session_count: int
    revision_count: int
    run_count: int
    artifact_count: int
    result: str = "PASS"


def utc_now_z() -> str:
    value = datetime.now(timezone.utc)
    fraction = f"{value.microsecond:06d}".rstrip("0")
    base = value.strftime("%Y-%m-%dT%H:%M:%S")
    return f"{base}.{fraction}Z" if fraction else f"{base}Z"


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: os.PathLike[str] | str) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _require_sha(value: Any, field: str) -> str:
    if not isinstance(value, str) or not SHA_RE.fullmatch(value):
        raise ValidationError("invalid SHA-256", details={"field": field, "value": value})
    return value


def _require_timestamp(value: Any, field: str = "timestamp") -> str:
    if not isinstance(value, str) or not RFC3339_Z_RE.fullmatch(value):
        raise ValidationError("timestamp is not canonical RFC3339 UTC-Z", details={"field": field})
    base = value[:-1].split(".", 1)[0]
    try:
        datetime.strptime(base, "%Y-%m-%dT%H:%M:%S")
    except ValueError as exc:
        raise ValidationError("timestamp is not a real calendar time", details={"field": field}) from exc
    fraction = value[:-1].partition(".")[2]
    if fraction and fraction.endswith("0"):
        raise ValidationError("timestamp has redundant fractional zero", details={"field": field})
    return value


def _require_uuid(value: Any, field: str, *, version: int | None = None) -> str:
    if not isinstance(value, str):
        raise ValidationError("UUID must be a string", details={"field": field})
    validate_canonical_uuid(value, expected_version=version)
    return value


def _clone_reject(code: str, message: str, **details: Any) -> None:
    raise ValidationError(message, details={"code": code, **details})


def _entity_record_sha256(value: Mapping[str, Any], hash_field: str) -> str:
    return sha256_bytes(canonical_json_bytes({key: item for key, item in value.items() if key != hash_field}))


def _candidate_link_status(candidate: Mapping[str, Any], *, prefix: str) -> tuple[str, str | None]:
    if "object_uuid" not in candidate:
        _clone_reject("CLONE_CANDIDATE_OBJECT_LINK_ABSENT", "candidate object link is absent", field=prefix)
    review_status = candidate.get("review_status")
    review_decision = candidate.get("review_decision")
    object_uuid = candidate.get("object_uuid")
    if review_decision not in CLONE_REVIEW_DECISIONS:
        _clone_reject(
            "CLONE_REVIEW_DECISION",
            "candidate review decision is outside the approved closed vocabulary",
            field=prefix,
        )
    if review_decision == "pending":
        if review_status != "pending" or object_uuid is not None:
            _clone_reject("CLONE_NULLABILITY", "pending candidate has an invalid status or object link", field=prefix)
        return "NOT_APPLICABLE_PENDING", None
    if review_decision == "reject":
        if review_status != "reviewed" or object_uuid is not None:
            _clone_reject("CLONE_NULLABILITY", "rejected candidate has an invalid status or object link", field=prefix)
        return "NOT_APPLICABLE_REJECTED", None
    if review_status != "reviewed" or object_uuid is None:
        _clone_reject("CLONE_NULLABILITY", "accepted/reviewed candidate lacks its linked object", field=prefix)
    return "LINKED_OBJECT", _require_uuid(object_uuid, f"{prefix}.object_uuid", version=4)


MANUAL_CANDIDATE_SCHEMA = "CTL_P7_MANUAL_CANDIDATE_V1"
MANUAL_PROPOSAL_GEOMETRY_SCHEMA = "CTL_P7_CIRCLE_PROPOSAL_V1"
MANUAL_CANDIDATE_CLASSES = {
    "accept": "confirmed", "adjust_and_accept": "confirmed",
    "mark_uncertain": "uncertain", "mark_possible_artifact": "possible_artifact",
}


def _manual_decimal(value: Any, field: str) -> Decimal:
    if isinstance(value, bool) or not isinstance(value, (int, float, str, Decimal)):
        raise ValidationError("Manual candidate coordinate is not numeric", details={"field": field})
    try:
        result = Decimal(str(value))
    except InvalidOperation as exc:
        raise ValidationError("Manual candidate coordinate is invalid", details={"field": field}) from exc
    if not result.is_finite():
        raise ValidationError("Manual candidate coordinate is not finite", details={"field": field})
    return result


def _manual_circle(value: Any, expected_sha: Any, view: Mapping[str, Any]) -> None:
    fields = {"schema", "center_x_px", "center_y_px", "diameter_px"}
    if not isinstance(value, Mapping) or set(value) != fields or value["schema"] != MANUAL_PROPOSAL_GEOMETRY_SCHEMA:
        raise ValidationError("Manual candidate requires the closed circle proposal schema")
    _require_sha(expected_sha, "manual_geometry_sha256")
    if sha256_bytes(canonical_json_bytes(value)) != expected_sha:
        raise ValidationError("Manual candidate geometry hash differs")
    x, y, diameter = (_manual_decimal(value[key], key) for key in ("center_x_px", "center_y_px", "diameter_px"))
    width, height = (_manual_decimal(view[key], key) for key in ("width_px", "height_px"))
    radius = diameter / 2
    if diameter <= 0 or x - radius < 0 or y - radius < 0 or x + radius > width or y + radius > height:
        raise ValidationError("Manual candidate circle is outside its original image")


def validate_manual_candidate(candidate: Mapping[str, Any], cavity_object: Mapping[str, Any] | None) -> None:
    """Validate only the additive manual profile; historical candidates stay readable.

    This profile describes an operator's visual proposal, never an algorithmic
    detection or a measurement of filtered pixels. The sealed legacy dictionary
    and previously published revisions are unchanged.
    """
    if candidate.get("candidate_schema") != MANUAL_CANDIDATE_SCHEMA:
        return
    zero_flags = {f"{prefix}{endpoint}{suffix}" for endpoint in ("count", "size", "position")
                  for prefix, suffix in (("", "_valid"), ("primary_", "_included"), ("sensitivity_", "_included"))}
    required = {"candidate_id", "candidate_uuid", "identity_provenance", "review_status", "review_decision",
                "object_uuid", "cavity_id", "accepted_cavity_class", "proposed_geometry", "proposed_geometry_sha256",
                "final_geometry", "final_geometry_sha256", "measurement_source", "view_id", "recipe_sha256",
                "source_sha256", "master_pixel_sha256", "source_view", "proposal_operator_id", "created_at",
                "reviewed_by", "reviewed_at", *zero_flags}
    if not required.issubset(candidate):
        raise ValidationError("Manual candidate fields are missing", details={"missing": sorted(required - set(candidate))})
    _require_uuid(candidate["candidate_uuid"], "candidate_uuid", version=4)
    # Cloning preserves the human proposal ID while assigning fresh UUIDs.
    if not isinstance(candidate["candidate_id"], str) or not candidate["candidate_id"].startswith("CAND_"):
        raise ValidationError("Manual candidate ID must use CAND_ plus its original UUID")
    _require_uuid(candidate["candidate_id"][5:], "candidate_id source UUID", version=4)
    if candidate["measurement_source"] != "manual_proposal" or any(type(candidate[name]) is not int or candidate[name] != 0 for name in zero_flags):
        raise ValidationError("Manual candidates must remain excluded from all measurements and estimands")
    source = candidate["source_view"]
    if not isinstance(source, Mapping) or set(source) != {"record", "record_sha256"} or not isinstance(source["record"], Mapping):
        raise ValidationError("Manual candidate source view envelope is invalid")
    view = source["record"]
    if sha256_bytes(canonical_json_bytes(view)) != _require_sha(source["record_sha256"], "source_view.record_sha256"):
        raise ValidationError("Manual candidate source view hash differs")
    if view.get("image_role") != "DERIVED_VIEW_CANDIDATE" or view.get("geometry_preserved") not in (True, 1):
        raise ValidationError("Manual proposal must originate from a geometry-preserving candidate view")
    for name in ("source_sha256", "master_pixel_sha256", "recipe_sha256"):
        if _require_sha(candidate[name], name) != view.get(name):
            raise ValidationError("Manual candidate source binding differs", details={"field": name})
    if candidate["view_id"] != view.get("view_id") or view.get("master_pixel_sha256_after") != view.get("master_pixel_sha256"):
        raise ValidationError("Manual candidate view identity or original-pixel evidence differs")
    if sha256_bytes(canonical_json_bytes(view.get("filter_recipe"))) != candidate["recipe_sha256"]:
        raise ValidationError("Manual candidate filter recipe hash differs")
    for field in ("project_uid", "image_uid", "analysis_session_uid", "revision_uid"):
        _require_uuid(view.get(field), "source_view." + field)
    for field in ("width_px", "height_px", "scale_x_nm_px", "scale_y_nm_px"):
        if _manual_decimal(view.get(field), field) <= 0:
            raise ValidationError("Manual candidate source view geometry is invalid")
    _manual_circle(candidate["proposed_geometry"], candidate["proposed_geometry_sha256"], view)
    created = _require_timestamp(candidate["created_at"], "candidate.created_at")
    for key in ("proposal_operator_id",):
        if candidate[key] != "UNKNOWN":
            validate_human_id(candidate[key], field=key)
    status, linked_uuid = _candidate_link_status(candidate, prefix="manual_candidate")
    if candidate["review_decision"] == "pending":
        if candidate["reviewed_by"] is not None or candidate["reviewed_at"] is not None:
            raise ValidationError("Pending manual candidate cannot have a review audit")
    else:
        reviewed = _require_timestamp(candidate["reviewed_at"], "candidate.reviewed_at")
        if datetime.fromisoformat(reviewed.replace("Z", "+00:00")) < datetime.fromisoformat(created.replace("Z", "+00:00")):
            raise ValidationError("Manual candidate review precedes its creation")
        if candidate["reviewed_by"] != "UNKNOWN":
            validate_human_id(candidate["reviewed_by"], field="reviewed_by")
    if status != "LINKED_OBJECT":
        if cavity_object is not None or any(candidate[key] is not None for key in ("cavity_id", "accepted_cavity_class", "final_geometry", "final_geometry_sha256")):
            raise ValidationError("Pending or rejected manual candidate cannot create an object")
        return
    if cavity_object is None or cavity_object.get("object_uuid") != linked_uuid or cavity_object.get("candidate_uuid") != candidate["candidate_uuid"]:
        raise ValidationError("Manual candidate lacks its reciprocal reviewed object")
    expected_class = MANUAL_CANDIDATE_CLASSES[candidate["review_decision"]]
    if candidate["accepted_cavity_class"] != expected_class or candidate["cavity_id"] != cavity_object.get("cavity_id"):
        raise ValidationError("Manual candidate classification or cavity link differs")
    _manual_circle(candidate["final_geometry"], candidate["final_geometry_sha256"], view)
    if candidate["review_decision"] == "accept" and candidate["final_geometry"] != candidate["proposed_geometry"]:
        raise ValidationError("An adjusted manual candidate must record adjust_and_accept")
    geometry = cavity_object.get("geometry")
    if not isinstance(geometry, Mapping):
        raise ValidationError("Manual candidate object geometry is absent")
    for key, expected in (("cavity_class", expected_class), ("review_status", "reviewed"), ("measurement_source", "manual")):
        values = [container[key] for container in (cavity_object, geometry) if key in container]
        if not values or any(value != expected for value in values):
            raise ValidationError("Manual candidate object review semantics differ", details={"field": key})
    for key in ("candidate_id", "view_id", "recipe_sha256", "proposed_geometry_sha256", "final_geometry_sha256"):
        if cavity_object.get(key) != candidate[key]:
            raise ValidationError("Manual candidate object trace differs", details={"field": key})
    # final_geometry is the historical acceptance decision. Later manual edits
    # change the object's current geometry, not that past review audit.


def _validate_clone_provenance_v2(
    provenance: Mapping[str, Any],
    source_manifest: Mapping[str, Any],
    destination_manifest: Mapping[str, Any],
) -> None:
    """Validate complete V2 clone provenance before a destination is published.

    This is intentionally a pure, importable validator.  It binds both mapping
    collections to the exact immutable source and generated destination revision
    manifests, including record hashes and reciprocal candidate/object links.
    """

    root_keys = {
        "candidate_mappings", "clone_mode", "clone_transaction_id", "created_at",
        "destination", "object_mappings", "schema", "source",
    }
    object_mapping_keys = {
        "cavity_id_destination", "cavity_id_source", "destination_object_sha256",
        "destination_object_uuid", "source_object_sha256", "source_object_uuid",
    }
    candidate_mapping_keys = {
        "destination_candidate_id", "destination_candidate_sha256", "destination_candidate_uuid",
        "destination_object_link_status", "destination_object_uuid", "destination_review_decision",
        "destination_review_status", "source_candidate_id", "source_candidate_sha256",
        "source_candidate_uuid", "source_object_link_status", "source_object_uuid",
        "source_review_decision", "source_review_status",
    }
    source_keys = {
        "candidate_count", "candidate_uuids", "object_count", "object_uuids", "revision_id",
        "revision_manifest_sha256", "revision_uid", "session_id", "session_uid",
    }
    destination_keys = {
        "genesis_revision_id", "genesis_revision_manifest_sha256", "genesis_revision_uid",
        "identity_provenance_mode", "session_id", "session_uid", "working_state_id",
    }
    if not isinstance(provenance, Mapping) or set(provenance) != root_keys:
        _clone_reject("CLONE_ROOT_INVENTORY", "clone provenance V2 has an incorrect closed root inventory")
    if provenance.get("schema") != "CTL_SESSION_CLONE_PROVENANCE_V2":
        _clone_reject("CLONE_SCHEMA", "clone provenance does not select V2")
    if provenance.get("clone_mode") != "COPY_TO_NEW_SESSION_WITH_NEW_GENESIS_REVISION":
        _clone_reject("CLONE_MODE", "clone mode is not approved")
    _safe_component(provenance.get("clone_transaction_id"), "clone_transaction_id")
    created_at = _require_timestamp(provenance.get("created_at"), "clone.created_at")

    source_context = provenance.get("source")
    destination_context = provenance.get("destination")
    if not isinstance(source_context, Mapping) or set(source_context) != source_keys:
        _clone_reject("CLONE_SOURCE_CONTEXT", "clone source context has an incorrect closed inventory")
    if not isinstance(destination_context, Mapping) or set(destination_context) != destination_keys:
        if isinstance(destination_context, Mapping) and "candidate_uuid" in destination_context:
            _clone_reject("CLONE_SINGULAR_CANDIDATE_FORBIDDEN", "destination.candidate_uuid is forbidden in V2")
        _clone_reject("CLONE_DESTINATION_CONTEXT", "clone destination context has an incorrect closed inventory")
    if "candidate_uuid" in destination_context:
        _clone_reject("CLONE_SINGULAR_CANDIDATE_FORBIDDEN", "destination.candidate_uuid is forbidden in V2")
    _safe_component(source_context.get("session_id"), "source.session_id")
    _safe_component(destination_context.get("session_id"), "destination.session_id")
    source_session_uid = _require_uuid(source_context.get("session_uid"), "source.session_uid")
    destination_session_uid = _require_uuid(
        destination_context.get("session_uid"), "destination.session_uid", version=4
    )
    if destination_session_uid == source_session_uid:
        _clone_reject("CLONE_DESTINATION_CONTEXT", "destination session reuses the source session UUID")
    if destination_context.get("identity_provenance_mode") != "RECONSTRUCTED":
        _clone_reject("CLONE_DESTINATION_CONTEXT", "destination identity provenance was not reconstructed")
    if destination_context.get("working_state_id") != "WORKING_000001":
        _clone_reject("CLONE_DESTINATION_CONTEXT", "clone genesis working state ID differs")

    if not isinstance(source_manifest, Mapping) or not isinstance(destination_manifest, Mapping):
        _clone_reject("CLONE_MANIFEST_TYPE", "source and destination revision manifests must be objects")
    if source_manifest.get("schema") != "CTL_P2A_REVISION_MANIFEST_V1" or destination_manifest.get("schema") != "CTL_P2A_REVISION_MANIFEST_V1":
        _clone_reject("CLONE_REVISION_SCHEMA", "clone revision manifest schema differs")
    source_manifest_sha = sha256_bytes(canonical_json_bytes(dict(source_manifest)))
    destination_manifest_sha = sha256_bytes(canonical_json_bytes(dict(destination_manifest)))
    if (
        source_context.get("revision_id") != source_manifest.get("revision_id")
        or source_context.get("revision_uid") != source_manifest.get("revision_uid")
        or source_context.get("revision_manifest_sha256") != source_manifest_sha
        or source_context.get("session_uid") != source_manifest.get("analysis_session_uid")
    ):
        _clone_reject("CLONE_SOURCE_CONTEXT", "clone source is not bound to the explicit immutable revision")
    if (
        destination_context.get("genesis_revision_id") != destination_manifest.get("revision_id")
        or destination_context.get("genesis_revision_uid") != destination_manifest.get("revision_uid")
        or destination_context.get("genesis_revision_manifest_sha256") != destination_manifest_sha
        or destination_context.get("session_uid") != destination_manifest.get("analysis_session_uid")
    ):
        _clone_reject("CLONE_DESTINATION_CONTEXT", "clone destination is not bound to its genesis revision")
    _require_uuid(source_manifest.get("revision_uid"), "source.revision_uid", version=4)
    _require_uuid(destination_manifest.get("revision_uid"), "destination.revision_uid", version=4)
    if destination_manifest.get("parent_revision_id") != "NOT_APPLICABLE":
        _clone_reject("CLONE_GENESIS_PARENT", "clone genesis revision has a parent")
    if destination_manifest.get("created_at") != created_at:
        _clone_reject("CLONE_DESTINATION_CONTEXT", "clone timestamp and genesis timestamp differ")
    for field in ("project_uid", "image_uid", "source_sha256"):
        if source_manifest.get(field) != destination_manifest.get(field):
            _clone_reject("CLONE_SCIENTIFIC_SCOPE", "clone changed its project/image/source scope", field=field)

    source_objects_raw = source_manifest.get("objects")
    destination_objects_raw = destination_manifest.get("objects")
    source_candidates_raw = source_manifest.get("candidates")
    destination_candidates_raw = destination_manifest.get("candidates")
    if not all(
        isinstance(value, list)
        for value in (source_objects_raw, destination_objects_raw, source_candidates_raw, destination_candidates_raw)
    ):
        _clone_reject("CLONE_ENTITY_COLLECTION", "revision entity collections must be arrays")

    def entity_index(items: Sequence[Any], key: str, domain: str) -> dict[str, Mapping[str, Any]]:
        result: dict[str, Mapping[str, Any]] = {}
        for item in items:
            if not isinstance(item, Mapping):
                _clone_reject("CLONE_ENTITY_TYPE", "clone entity is not an object", domain=domain)
            identifier = _require_uuid(item.get(key), f"{domain}.{key}", version=4)
            if identifier in result:
                _clone_reject("CLONE_SOURCE_UUID_DUPLICATE", "revision entity UUID repeats", domain=domain)
            result[identifier] = item
        return result

    source_objects = entity_index(source_objects_raw, "object_uuid", "source_object")
    destination_objects = entity_index(destination_objects_raw, "object_uuid", "destination_object")
    source_candidates = entity_index(source_candidates_raw, "candidate_uuid", "source_candidate")
    destination_candidates = entity_index(destination_candidates_raw, "candidate_uuid", "destination_candidate")
    source_uuid_set = set(source_objects) | set(source_candidates)
    if len(source_uuid_set) != len(source_objects) + len(source_candidates):
        _clone_reject("CLONE_SOURCE_UUID_DUPLICATE", "source object/candidate UUID domains overlap")

    expected_source_object_uuids = sorted(source_objects)
    expected_source_candidate_uuids = sorted(source_candidates)
    if (
        source_context.get("object_count") != len(expected_source_object_uuids)
        or source_context.get("object_uuids") != expected_source_object_uuids
    ):
        _clone_reject("CLONE_OBJECT_COVERAGE", "source object inventory is incomplete or non-canonical")
    if (
        source_context.get("candidate_count") != len(expected_source_candidate_uuids)
        or source_context.get("candidate_uuids") != expected_source_candidate_uuids
    ):
        _clone_reject("CLONE_CANDIDATE_COVERAGE", "source candidate inventory is incomplete or non-canonical")

    object_mappings = provenance.get("object_mappings")
    candidate_mappings = provenance.get("candidate_mappings")
    if not isinstance(object_mappings, list) or not isinstance(candidate_mappings, list):
        _clone_reject("CLONE_MAPPING_TYPE", "clone mappings must be arrays")
    if any(not isinstance(item, Mapping) or set(item) != object_mapping_keys for item in object_mappings):
        _clone_reject("CLONE_OBJECT_KEYS", "object mapping keys differ from V2")
    if any(not isinstance(item, Mapping) or set(item) != candidate_mapping_keys for item in candidate_mappings):
        _clone_reject("CLONE_CANDIDATE_KEYS", "candidate mapping keys differ from V2")
    if [item["source_object_uuid"] for item in object_mappings] != sorted(source_objects):
        _clone_reject("CLONE_OBJECT_COVERAGE", "object mappings do not cover the source inventory exactly")
    if [item["source_candidate_uuid"] for item in candidate_mappings] != sorted(source_candidates):
        _clone_reject("CLONE_CANDIDATE_COVERAGE", "candidate mappings do not cover the source inventory exactly")

    declared_destination_uuids = [
        _require_uuid(item["destination_object_uuid"], "destination_object_uuid", version=4)
        for item in object_mappings
    ] + [
        _require_uuid(item["destination_candidate_uuid"], "destination_candidate_uuid", version=4)
        for item in candidate_mappings
    ]
    if len(declared_destination_uuids) != len(set(declared_destination_uuids)):
        _clone_reject("CLONE_DESTINATION_UUID_DUPLICATE", "destination UUID repeats across mapping domains")
    if set(declared_destination_uuids) & source_uuid_set:
        _clone_reject("CLONE_SOURCE_UUID_REUSED", "destination UUID reuses a source UUID")
    declared_destination_candidate_ids = [item["destination_candidate_id"] for item in candidate_mappings]
    if len(declared_destination_candidate_ids) != len(set(declared_destination_candidate_ids)):
        _clone_reject("CLONE_CANDIDATE_ID_COLLISION", "destination candidate_id repeats")

    object_map: dict[str, str] = {}
    destination_uuid_list: list[str] = []
    expected_provenance = {
        "created_at": created_at,
        "generation_method": "UUIDV4_RANDOM",
        "schema": "CTL_P2A_RECONSTRUCTED_IDENTITY_PROVENANCE_V1",
    }
    for mapping in object_mappings:
        source_uuid = _require_uuid(mapping["source_object_uuid"], "source_object_uuid", version=4)
        destination_uuid = _require_uuid(mapping["destination_object_uuid"], "destination_object_uuid", version=4)
        source_object = source_objects[source_uuid]
        destination_object = destination_objects.get(destination_uuid)
        if destination_object is None:
            _clone_reject("CLONE_OBJECT_COVERAGE", "mapped destination object is absent")
        if mapping["source_object_sha256"] != source_object.get("object_sha256") or mapping["source_object_sha256"] != _entity_record_sha256(source_object, "object_sha256"):
            _clone_reject("CLONE_OBJECT_HASH", "source object hash does not bind its record")
        if mapping["destination_object_sha256"] != destination_object.get("object_sha256") or mapping["destination_object_sha256"] != _entity_record_sha256(destination_object, "object_sha256"):
            _clone_reject("CLONE_OBJECT_HASH", "destination object hash does not bind its record")
        if mapping["cavity_id_source"] != source_object.get("cavity_id") or mapping["cavity_id_destination"] != destination_object.get("cavity_id") or mapping["cavity_id_source"] != mapping["cavity_id_destination"]:
            _clone_reject("CLONE_CAVITY_ID", "clone changed or misbound cavity_id")
        if destination_object.get("identity_provenance") != expected_provenance:
            _clone_reject("CLONE_IDENTITY_PROVENANCE", "destination object identity provenance was not rebuilt")
        source_scientific = {
            key: value for key, value in source_object.items()
            if key not in {"candidate_uuid", "identity_provenance", "object_sha256", "object_uuid"}
        }
        destination_scientific = {
            key: value for key, value in destination_object.items()
            if key not in {"candidate_uuid", "identity_provenance", "object_sha256", "object_uuid"}
        }
        if source_scientific != destination_scientific:
            _clone_reject("CLONE_OBJECT_SEMANTICS", "clone changed non-identity object fields")
        object_map[source_uuid] = destination_uuid
        destination_uuid_list.append(destination_uuid)
    if set(object_map.values()) != set(destination_objects):
        _clone_reject("CLONE_OBJECT_COVERAGE", "destination object coverage is not exact")

    candidate_map: dict[str, str] = {}
    candidate_ids: set[str] = set()
    for mapping in candidate_mappings:
        source_uuid = _require_uuid(mapping["source_candidate_uuid"], "source_candidate_uuid", version=4)
        destination_uuid = _require_uuid(mapping["destination_candidate_uuid"], "destination_candidate_uuid", version=4)
        source_candidate = source_candidates[source_uuid]
        destination_candidate = destination_candidates.get(destination_uuid)
        if destination_candidate is None:
            _clone_reject("CLONE_CANDIDATE_COVERAGE", "mapped destination candidate is absent")
        source_id = _safe_component(mapping["source_candidate_id"], "source_candidate_id")
        destination_id = _safe_component(mapping["destination_candidate_id"], "destination_candidate_id")
        if source_id != source_candidate.get("candidate_id") or destination_id != destination_candidate.get("candidate_id") or source_id != destination_id:
            _clone_reject("CLONE_CANDIDATE_ID", "clone changed or misbound candidate_id")
        if destination_id in candidate_ids:
            _clone_reject("CLONE_CANDIDATE_ID_COLLISION", "destination candidate_id repeats")
        candidate_ids.add(destination_id)
        if mapping["source_candidate_sha256"] != source_candidate.get("candidate_sha256") or mapping["source_candidate_sha256"] != _entity_record_sha256(source_candidate, "candidate_sha256"):
            _clone_reject("CLONE_CANDIDATE_HASH", "source candidate hash does not bind its record")
        if mapping["destination_candidate_sha256"] != destination_candidate.get("candidate_sha256") or mapping["destination_candidate_sha256"] != _entity_record_sha256(destination_candidate, "candidate_sha256"):
            _clone_reject("CLONE_CANDIDATE_HASH", "destination candidate hash does not bind its record")
        if destination_candidate.get("identity_provenance") != expected_provenance:
            _clone_reject("CLONE_IDENTITY_PROVENANCE", "destination candidate identity provenance was not rebuilt")
        source_scientific = {
            key: value for key, value in source_candidate.items()
            if key not in {"candidate_sha256", "candidate_uuid", "identity_provenance", "object_uuid"}
        }
        destination_scientific = {
            key: value for key, value in destination_candidate.items()
            if key not in {"candidate_sha256", "candidate_uuid", "identity_provenance", "object_uuid"}
        }
        if source_scientific != destination_scientific:
            _clone_reject("CLONE_CANDIDATE_SEMANTICS", "clone changed non-identity candidate fields")
        source_link_status, source_object_uuid = _candidate_link_status(source_candidate, prefix="source_candidate")
        destination_link_status, destination_object_uuid = _candidate_link_status(
            destination_candidate, prefix="destination_candidate"
        )
        if (
            mapping["source_review_status"] != source_candidate.get("review_status")
            or mapping["destination_review_status"] != destination_candidate.get("review_status")
            or mapping["source_review_decision"] != source_candidate.get("review_decision")
            or mapping["destination_review_decision"] != destination_candidate.get("review_decision")
            or mapping["source_object_link_status"] != source_link_status
            or mapping["destination_object_link_status"] != destination_link_status
            or source_link_status != destination_link_status
            or mapping["source_object_uuid"] != source_object_uuid
            or mapping["destination_object_uuid"] != destination_object_uuid
        ):
            _clone_reject("CLONE_REVIEW_SEMANTICS", "candidate review/link semantics changed or are misbound")
        if source_link_status == "LINKED_OBJECT":
            if object_map.get(source_object_uuid) != destination_object_uuid:
                _clone_reject("CLONE_LINKED_OBJECT_MISSING", "candidate linked object mapping is absent")
            if source_objects[source_object_uuid].get("candidate_uuid") != source_uuid or destination_objects[destination_object_uuid].get("candidate_uuid") != destination_uuid:
                _clone_reject("CLONE_LINKED_OBJECT_MISSING", "candidate/object reciprocal link is invalid")
        candidate_map[source_uuid] = destination_uuid
        destination_uuid_list.append(destination_uuid)
    if set(candidate_map.values()) != set(destination_candidates):
        _clone_reject("CLONE_CANDIDATE_COVERAGE", "destination candidate coverage is not exact")

    for mapping in object_mappings:
        source_object = source_objects[mapping["source_object_uuid"]]
        destination_object = destination_objects[mapping["destination_object_uuid"]]
        source_candidate_uuid = source_object.get("candidate_uuid")
        destination_candidate_uuid = destination_object.get("candidate_uuid")
        if source_candidate_uuid is None:
            if destination_candidate_uuid is not None:
                _clone_reject("CLONE_MANUAL_OBJECT_LINK", "manual object acquired a candidate during clone")
        elif candidate_map.get(source_candidate_uuid) != destination_candidate_uuid:
            _clone_reject("CLONE_LINKED_OBJECT_MISSING", "object candidate link is not mapped 1:1")

    if destination_uuid_list != declared_destination_uuids:
        _clone_reject("CLONE_MAPPING_ORDER", "validated mapping UUID order changed unexpectedly")


def _clone_geometry_index(
    manifest: Mapping[str, Any],
    *,
    domain: str,
) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]]]:
    """Validate the closed geometry records used by clone provenance V3.

    Published revision validation performs the same checks through
    ``SessionCore._normalize_revision_geometries``.  This pure helper keeps the
    provenance validator independently fail-closed when it is called directly
    by focused tests or pre-publication code.
    """

    raw_geometries = manifest.get("geometries")
    if not isinstance(raw_geometries, list):
        _clone_reject(
            "CLONE_GEOMETRY_COLLECTION",
            "geometry-aware clone revision does not contain a geometry array",
            domain=domain,
        )
    normalized: list[dict[str, Any]] = []
    by_uid: dict[str, dict[str, Any]] = {}
    geometry_ids: set[str] = set()
    for index, raw in enumerate(raw_geometries):
        if not isinstance(raw, Mapping) or set(raw) != P3_GEOMETRY_FIELDS:
            _clone_reject(
                "CLONE_GEOMETRY_INVENTORY",
                "clone geometry record has an incorrect closed inventory",
                domain=domain,
                index=index,
            )
        value = dict(raw)
        geometry_uid = _require_uuid(
            value.get("geometry_uid"),
            f"{domain}.geometries[{index}].geometry_uid",
            version=4,
        )
        geometry_id = _safe_component(
            value.get("geometry_id"),
            f"{domain}.geometries[{index}].geometry_id",
        )
        geometry_type = value.get("geometry_type")
        if geometry_type not in P3_GEOMETRY_TYPES:
            _clone_reject(
                "CLONE_GEOMETRY_TYPE",
                "clone geometry type is outside the closed vocabulary",
                domain=domain,
                index=index,
            )
        _safe_component(
            value.get("geometry_schema"),
            f"{domain}.geometries[{index}].geometry_schema",
        )
        if geometry_uid in by_uid or geometry_id in geometry_ids:
            _clone_reject(
                "CLONE_GEOMETRY_IDENTITY_COLLISION",
                "clone geometry ID or UUID repeats",
                domain=domain,
                index=index,
            )
        encoded_roi = value.get("roi_bytes_base64")
        if not isinstance(encoded_roi, str):
            _clone_reject(
                "CLONE_GEOMETRY_ROI_BYTES",
                "clone geometry ROI is not base64 text",
                domain=domain,
                index=index,
            )
        try:
            roi_bytes = base64.b64decode(encoded_roi.encode("ascii"), validate=True)
        except (UnicodeEncodeError, binascii.Error, ValueError):
            _clone_reject(
                "CLONE_GEOMETRY_ROI_BYTES",
                "clone geometry ROI is not canonical base64",
                domain=domain,
                index=index,
            )
        if (
            base64.b64encode(roi_bytes).decode("ascii") != encoded_roi
            or len(roi_bytes) < 4
            or roi_bytes[:4] != b"Iout"
        ):
            _clone_reject(
                "CLONE_GEOMETRY_ROI_BYTES",
                "clone geometry ROI bytes are not canonical ImageJ ROI bytes",
                domain=domain,
                index=index,
            )
        observed_roi_sha = sha256_bytes(roi_bytes)
        if (
            _require_sha(
                value.get("roi_bytes_sha256"),
                f"{domain}.geometries[{index}].roi_bytes_sha256",
            )
            != observed_roi_sha
            or _require_sha(
                value.get("source_roi_sha256"),
                f"{domain}.geometries[{index}].source_roi_sha256",
            )
            != observed_roi_sha
        ):
            _clone_reject(
                "CLONE_GEOMETRY_ROI_HASH",
                "clone geometry ROI hashes do not bind the exact ROI bytes",
                domain=domain,
                index=index,
            )
        if _require_sha(
            value.get("geometry_sha256"),
            f"{domain}.geometries[{index}].geometry_sha256",
        ) != _entity_record_sha256(value, "geometry_sha256"):
            _clone_reject(
                "CLONE_GEOMETRY_HASH",
                "clone geometry hash does not bind its canonical record",
                domain=domain,
                index=index,
            )
        if not isinstance(value.get("bounds"), Mapping):
            _clone_reject(
                "CLONE_GEOMETRY_DERIVED_FIELDS",
                "clone geometry bounds are not an object",
                domain=domain,
                index=index,
            )
        for field in ("coordinates", "labels"):
            if not isinstance(value.get(field), (Mapping, list)):
                _clone_reject(
                    "CLONE_GEOMETRY_DERIVED_FIELDS",
                    "clone geometry derived field has an invalid container",
                    domain=domain,
                    field=field,
                    index=index,
                )
        # Canonical JSON round-trip validates the nested derived containers and
        # exact numeric/text profile without assigning them scientific meaning.
        value = loads_canonical_json(canonical_json_bytes(value))
        normalized.append(value)
        by_uid[geometry_uid] = value
        geometry_ids.add(geometry_id)
    if [item["geometry_uid"] for item in normalized] != sorted(by_uid):
        _clone_reject(
            "CLONE_GEOMETRY_ORDER",
            "clone geometry records are not sorted by geometry UUID",
            domain=domain,
        )
    return normalized, by_uid


def _validate_clone_provenance_v3(
    provenance: Mapping[str, Any],
    source_manifest: Mapping[str, Any],
    destination_manifest: Mapping[str, Any],
) -> None:
    """Validate an implementation-local, exact-preserve geometry clone.

    V3 does not alter the approved V2 contract.  It reuses V2's exact entity
    rules through in-memory V1 views, while independently binding the physical
    V2 manifests and requiring every scientific geometry record and identity to
    remain byte-semantically identical in the new session.
    """

    root_keys = {
        "candidate_mappings",
        "clone_mode",
        "clone_transaction_id",
        "created_at",
        "destination",
        "geometry_mappings",
        "object_mappings",
        "schema",
        "source",
    }
    source_keys_v2 = {
        "candidate_count",
        "candidate_uuids",
        "object_count",
        "object_uuids",
        "revision_id",
        "revision_manifest_sha256",
        "revision_uid",
        "session_id",
        "session_uid",
    }
    destination_keys_v2 = {
        "genesis_revision_id",
        "genesis_revision_manifest_sha256",
        "genesis_revision_uid",
        "identity_provenance_mode",
        "session_id",
        "session_uid",
        "working_state_id",
    }
    geometry_context_keys = {
        "geometry_count",
        "geometry_set_sha256",
        "geometry_uids",
    }
    mapping_keys = {
        "destination_geometry_id",
        "destination_geometry_roi_bytes_sha256",
        "destination_geometry_schema",
        "destination_geometry_sha256",
        "destination_geometry_source_roi_sha256",
        "destination_geometry_type",
        "destination_geometry_uid",
        "identity_disposition",
        "source_geometry_id",
        "source_geometry_roi_bytes_sha256",
        "source_geometry_schema",
        "source_geometry_sha256",
        "source_geometry_source_roi_sha256",
        "source_geometry_type",
        "source_geometry_uid",
    }
    if not isinstance(provenance, Mapping) or set(provenance) != root_keys:
        _clone_reject(
            "CLONE_ROOT_INVENTORY",
            "clone provenance V3 has an incorrect closed root inventory",
        )
    if provenance.get("schema") != CLONE_PROVENANCE_V3_SCHEMA:
        _clone_reject("CLONE_SCHEMA", "clone provenance does not select V3")
    source_context = provenance.get("source")
    destination_context = provenance.get("destination")
    if (
        not isinstance(source_context, Mapping)
        or set(source_context) != source_keys_v2 | geometry_context_keys
    ):
        _clone_reject(
            "CLONE_SOURCE_CONTEXT",
            "clone V3 source context has an incorrect closed inventory",
        )
    if (
        not isinstance(destination_context, Mapping)
        or set(destination_context)
        != destination_keys_v2 | geometry_context_keys | {"geometry_identity_mode"}
    ):
        _clone_reject(
            "CLONE_DESTINATION_CONTEXT",
            "clone V3 destination context has an incorrect closed inventory",
        )
    if destination_context.get("geometry_identity_mode") != CLONE_GEOMETRY_IDENTITY_MODE:
        _clone_reject(
            "CLONE_GEOMETRY_IDENTITY_MODE",
            "clone V3 does not select exact-preserve geometry identity",
        )
    if (
        not isinstance(source_manifest, Mapping)
        or not isinstance(destination_manifest, Mapping)
        or source_manifest.get("schema") != "CTL_P2A_REVISION_MANIFEST_V2"
        or destination_manifest.get("schema") != "CTL_P2A_REVISION_MANIFEST_V2"
    ):
        _clone_reject(
            "CLONE_REVISION_SCHEMA",
            "clone provenance V3 requires source and destination revision manifest V2",
        )

    source_manifest_sha = sha256_bytes(canonical_json_bytes(dict(source_manifest)))
    destination_manifest_sha = sha256_bytes(canonical_json_bytes(dict(destination_manifest)))
    if (
        source_context.get("revision_manifest_sha256") != source_manifest_sha
        or source_context.get("revision_id") != source_manifest.get("revision_id")
        or source_context.get("revision_uid") != source_manifest.get("revision_uid")
        or source_context.get("session_uid") != source_manifest.get("analysis_session_uid")
    ):
        _clone_reject(
            "CLONE_SOURCE_CONTEXT",
            "clone V3 source is not bound to the explicit immutable revision",
        )
    if (
        destination_context.get("genesis_revision_manifest_sha256")
        != destination_manifest_sha
        or destination_context.get("genesis_revision_id")
        != destination_manifest.get("revision_id")
        or destination_context.get("genesis_revision_uid")
        != destination_manifest.get("revision_uid")
        or destination_context.get("session_uid")
        != destination_manifest.get("analysis_session_uid")
    ):
        _clone_reject(
            "CLONE_DESTINATION_CONTEXT",
            "clone V3 destination is not bound to its genesis revision",
        )

    source_geometries, source_by_uid = _clone_geometry_index(
        source_manifest, domain="source"
    )
    destination_geometries, destination_by_uid = _clone_geometry_index(
        destination_manifest, domain="destination"
    )
    if source_geometries != destination_geometries:
        _clone_reject(
            "CLONE_GEOMETRY_SEMANTICS",
            "clone changed a scientific geometry record or identity",
        )
    source_geometry_uids = sorted(source_by_uid)
    destination_geometry_uids = sorted(destination_by_uid)
    source_set_sha = sha256_bytes(
        canonical_json_bytes({"geometries": source_geometries})
    )
    destination_set_sha = sha256_bytes(
        canonical_json_bytes({"geometries": destination_geometries})
    )
    if (
        source_context.get("geometry_count") != len(source_geometries)
        or source_context.get("geometry_uids") != source_geometry_uids
        or _require_sha(
            source_context.get("geometry_set_sha256"),
            "source.geometry_set_sha256",
        )
        != source_set_sha
        or destination_context.get("geometry_count") != len(destination_geometries)
        or destination_context.get("geometry_uids") != destination_geometry_uids
        or _require_sha(
            destination_context.get("geometry_set_sha256"),
            "destination.geometry_set_sha256",
        )
        != destination_set_sha
        or source_set_sha != destination_set_sha
    ):
        _clone_reject(
            "CLONE_GEOMETRY_COVERAGE",
            "clone geometry context does not exactly cover the bound manifests",
        )

    mappings = provenance.get("geometry_mappings")
    if not isinstance(mappings, list) or len(mappings) != len(source_geometries):
        _clone_reject(
            "CLONE_GEOMETRY_COVERAGE",
            "clone geometry mapping cardinality is not exact",
        )
    observed_source_uids: list[str] = []
    observed_destination_uids: set[str] = set()
    for index, raw_mapping in enumerate(mappings):
        if not isinstance(raw_mapping, Mapping) or set(raw_mapping) != mapping_keys:
            _clone_reject(
                "CLONE_GEOMETRY_MAPPING_INVENTORY",
                "clone geometry mapping has an incorrect closed inventory",
                index=index,
            )
        mapping = dict(raw_mapping)
        source_uid = _require_uuid(
            mapping.get("source_geometry_uid"),
            f"geometry_mappings[{index}].source_geometry_uid",
            version=4,
        )
        destination_uid = _require_uuid(
            mapping.get("destination_geometry_uid"),
            f"geometry_mappings[{index}].destination_geometry_uid",
            version=4,
        )
        source_geometry = source_by_uid.get(source_uid)
        destination_geometry = destination_by_uid.get(destination_uid)
        if source_geometry is None or destination_geometry is None:
            _clone_reject(
                "CLONE_GEOMETRY_COVERAGE",
                "clone geometry mapping refers to an absent record",
                index=index,
            )
        expected_mapping = {
            "destination_geometry_id": destination_geometry["geometry_id"],
            "destination_geometry_roi_bytes_sha256": destination_geometry[
                "roi_bytes_sha256"
            ],
            "destination_geometry_schema": destination_geometry["geometry_schema"],
            "destination_geometry_sha256": destination_geometry["geometry_sha256"],
            "destination_geometry_source_roi_sha256": destination_geometry[
                "source_roi_sha256"
            ],
            "destination_geometry_type": destination_geometry["geometry_type"],
            "destination_geometry_uid": destination_geometry["geometry_uid"],
            "identity_disposition": CLONE_GEOMETRY_IDENTITY_DISPOSITION,
            "source_geometry_id": source_geometry["geometry_id"],
            "source_geometry_roi_bytes_sha256": source_geometry["roi_bytes_sha256"],
            "source_geometry_schema": source_geometry["geometry_schema"],
            "source_geometry_sha256": source_geometry["geometry_sha256"],
            "source_geometry_source_roi_sha256": source_geometry[
                "source_roi_sha256"
            ],
            "source_geometry_type": source_geometry["geometry_type"],
            "source_geometry_uid": source_geometry["geometry_uid"],
        }
        if mapping != expected_mapping or source_uid != destination_uid:
            _clone_reject(
                "CLONE_GEOMETRY_SEMANTICS",
                "clone geometry mapping is not exact-preserve",
                index=index,
            )
        observed_source_uids.append(source_uid)
        if destination_uid in observed_destination_uids:
            _clone_reject(
                "CLONE_GEOMETRY_COVERAGE",
                "clone destination geometry mapping repeats",
                index=index,
            )
        observed_destination_uids.add(destination_uid)
    if (
        observed_source_uids != source_geometry_uids
        or observed_destination_uids != set(destination_geometry_uids)
    ):
        _clone_reject(
            "CLONE_GEOMETRY_MAPPING_ORDER",
            "clone geometry mappings are incomplete or non-canonical",
        )

    # Geometry UUID reuse is deliberate only across the exact source/destination
    # geometry pair.  It must not collide with any other scientific identity.
    source_non_geometry_uids = {
        _require_uuid(source_manifest.get("project_uid"), "source.project_uid"),
        _require_uuid(source_manifest.get("image_uid"), "source.image_uid"),
        _require_uuid(
            source_manifest.get("analysis_session_uid"), "source.analysis_session_uid"
        ),
        _require_uuid(source_manifest.get("revision_uid"), "source.revision_uid", version=4),
    } | {
        _require_uuid(item.get("object_uuid"), "source.object_uuid", version=4)
        for item in source_manifest.get("objects", [])
    } | {
        _require_uuid(item.get("candidate_uuid"), "source.candidate_uuid", version=4)
        for item in source_manifest.get("candidates", [])
    }
    destination_non_geometry_uids = {
        _require_uuid(destination_manifest.get("project_uid"), "destination.project_uid"),
        _require_uuid(destination_manifest.get("image_uid"), "destination.image_uid"),
        _require_uuid(
            destination_manifest.get("analysis_session_uid"),
            "destination.analysis_session_uid",
        ),
        _require_uuid(
            destination_manifest.get("revision_uid"),
            "destination.revision_uid",
            version=4,
        ),
    } | {
        _require_uuid(item.get("object_uuid"), "destination.object_uuid", version=4)
        for item in destination_manifest.get("objects", [])
    } | {
        _require_uuid(
            item.get("candidate_uuid"), "destination.candidate_uuid", version=4
        )
        for item in destination_manifest.get("candidates", [])
    }
    if set(source_geometry_uids) & (
        source_non_geometry_uids | destination_non_geometry_uids
    ):
        _clone_reject(
            "CLONE_GEOMETRY_IDENTITY_COLLISION",
            "preserved geometry UUID collides with a non-geometry identity",
        )

    # Reuse every approved V2 rule for the reconstructed object/candidate
    # domains without modifying the V2 validator or writing synthetic bytes.
    source_entity_manifest = dict(source_manifest)
    destination_entity_manifest = dict(destination_manifest)
    source_entity_manifest.pop("geometries", None)
    destination_entity_manifest.pop("geometries", None)
    source_entity_manifest["schema"] = "CTL_P2A_REVISION_MANIFEST_V1"
    destination_entity_manifest["schema"] = "CTL_P2A_REVISION_MANIFEST_V1"
    entity_provenance = {
        key: provenance[key]
        for key in {
            "candidate_mappings",
            "clone_mode",
            "clone_transaction_id",
            "created_at",
            "destination",
            "object_mappings",
            "schema",
            "source",
        }
    }
    entity_provenance["schema"] = "CTL_SESSION_CLONE_PROVENANCE_V2"
    entity_provenance["source"] = {
        key: source_context[key] for key in source_keys_v2
    }
    entity_provenance["destination"] = {
        key: destination_context[key] for key in destination_keys_v2
    }
    entity_provenance["source"]["revision_manifest_sha256"] = sha256_bytes(
        canonical_json_bytes(source_entity_manifest)
    )
    entity_provenance["destination"][
        "genesis_revision_manifest_sha256"
    ] = sha256_bytes(canonical_json_bytes(destination_entity_manifest))
    _validate_clone_provenance_v2(
        entity_provenance,
        source_entity_manifest,
        destination_entity_manifest,
    )


def _validate_clone_provenance(
    provenance: Mapping[str, Any],
    source_manifest: Mapping[str, Any],
    destination_manifest: Mapping[str, Any],
) -> None:
    schema = provenance.get("schema") if isinstance(provenance, Mapping) else None
    if schema == "CTL_SESSION_CLONE_PROVENANCE_V2":
        _validate_clone_provenance_v2(
            provenance, source_manifest, destination_manifest
        )
        return
    if schema == CLONE_PROVENANCE_V3_SCHEMA:
        _validate_clone_provenance_v3(
            provenance, source_manifest, destination_manifest
        )
        return
    _clone_reject("CLONE_SCHEMA", "clone provenance schema is unsupported")


def _require_nonnegative(value: Any, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValidationError("expected non-negative integer", details={"field": field})
    return value


def _require_positive(value: Any, field: str) -> int:
    result = _require_nonnegative(value, field)
    if result < 1:
        raise ValidationError("expected positive integer", details={"field": field})
    return result


def _safe_component(value: str, field: str) -> str:
    validate_human_id(value, field=field)
    return value


def _session_directory_names(session_id: str) -> tuple[str, str]:
    """Return the preferred and case-fold-disambiguated physical names.

    ``analysis_session_id`` is an explicitly case-sensitive human identity,
    while the supported Windows filesystem is normally case-insensitive.  A
    deterministic suffix is therefore used only when another session's
    preferred directory name collides under Unicode case-folding.  The human
    ID stored in every authority remains byte-exact and is never sanitised or
    renamed.
    """

    checked = _safe_component(session_id, "analysis_session_id")
    preferred = f"SESSION_{checked}"
    discriminator = sha256_bytes(checked.encode("utf-8"))[:12]
    return preferred, f"{preferred}~CASE_{discriminator}"


def _session_directory_matches_id(directory_name: str, session_id: str) -> bool:
    preferred, disambiguated = _session_directory_names(session_id)
    return directory_name in {preferred, disambiguated}


def _choose_new_session_directory(sessions_root: Path, session_id: str) -> Path:
    """Choose a no-replace physical root for a new case-sensitive session ID."""

    preferred, disambiguated = _session_directory_names(session_id)
    entries = [entry.name for entry in sessions_root.iterdir()]
    preferred_partial = preferred + ".partial."
    disambiguated_partial = disambiguated + ".partial."
    if preferred in entries or any(name.startswith(preferred_partial) for name in entries):
        raise TransactionError("analysis_session_id already has a final or retained partial")
    folded = preferred.casefold()
    folded_partial = preferred_partial.casefold()
    if any(name.casefold().startswith(folded_partial) for name in entries):
        raise TransactionError("case-colliding session has a retained partial")
    case_colliders = [name for name in entries if name.casefold() == folded]
    if not case_colliders:
        return sessions_root / preferred
    if any(
        name.casefold() == disambiguated.casefold()
        or name.casefold().startswith(disambiguated_partial.casefold())
        for name in entries
    ):
        raise TransactionError("analysis_session_id disambiguated path already exists")
    return sessions_root / disambiguated


def _portable_relative(value: Any, field: str = "relative_path") -> str:
    if not isinstance(value, str) or not value or value != unicodedata.normalize("NFC", value):
        raise ValidationError("relative path is absent or non-NFC", details={"field": field})
    if len(value) > 240 or "\\" in value or ":" in value or value.startswith("/"):
        raise ValidationError("relative path is not portable", details={"field": field, "value": value})
    parts = value.split("/")
    if len(parts) > 32 or any(not part or part in {".", ".."} for part in parts):
        raise ValidationError("relative path has unsafe components", details={"field": field})
    for part in parts:
        if part.endswith((".", " ")) or part.split(".", 1)[0].upper() in FORBIDDEN_PATH_NAMES:
            raise ValidationError("relative path has a Windows-reserved component", details={"field": field})
        if any(ord(char) < 0x20 or ord(char) == 0x7F for char in part):
            raise ValidationError("relative path has a control codepoint", details={"field": field})
    if PurePosixPath(value).as_posix() != value:
        raise ValidationError("relative path is not canonical", details={"field": field})
    return value


def _contained(root: Path, relative: str) -> Path:
    checked = _portable_relative(relative)
    candidate = root.joinpath(*checked.split("/"))
    try:
        candidate.resolve(strict=False).relative_to(root.resolve(strict=True))
    except (OSError, ValueError) as exc:
        raise ValidationError("path escapes its authority root", details={"relative_path": relative}) from exc
    return candidate


def _tsv_bytes(fields: Sequence[str], rows: Sequence[Mapping[str, Any]]) -> bytes:
    lines = ["\t".join(fields)]
    for row in rows:
        if set(row) != set(fields):
            raise ValidationError(
                "TSV row has an incorrect closed field set",
                details={"missing": sorted(set(fields) - set(row)), "extra": sorted(set(row) - set(fields))},
            )
        values: list[str] = []
        for field in fields:
            raw = row[field]
            value = "" if raw is None else str(raw)
            if any(codepoint in value for codepoint in ("\t", "\r", "\n", "\x00")):
                raise ValidationError("TSV value contains a forbidden codepoint", details={"field": field})
            if value != unicodedata.normalize("NFC", value):
                raise ValidationError("TSV value is not NFC", details={"field": field})
            values.append(value)
        lines.append("\t".join(values))
    return ("\n".join(lines) + "\n").encode("utf-8")


def _parse_tsv(data: bytes, fields: Sequence[str], *, allow_header_only: bool) -> list[dict[str, str]]:
    if data.startswith(b"\xef\xbb\xbf") or b"\r" in data or b"\x00" in data or not data.endswith(b"\n"):
        raise ValidationError("TSV bytes violate UTF-8/LF profile")
    try:
        text = data.decode("utf-8", errors="strict")
    except UnicodeDecodeError as exc:
        raise ValidationError("TSV is not UTF-8") from exc
    lines = text[:-1].split("\n")
    if not lines or lines[0] != "\t".join(fields):
        raise ValidationError("TSV header differs from approved profile")
    if not allow_header_only and len(lines) != 2:
        raise ValidationError("TSV must have exactly one data row")
    rows: list[dict[str, str]] = []
    for line in lines[1:]:
        values = line.split("\t")
        if len(values) != len(fields):
            raise ValidationError("TSV row width differs from approved profile")
        rows.append(dict(zip(fields, values)))
    return rows


def _canonical_read(path: Path) -> dict[str, Any]:
    try:
        raw = stable_plain_bytes(path, label="canonical JSON authority")
    except PathSafetyError as exc:
        raise ValidationError(
            "canonical JSON authority is not a stable plain single-link file",
            details={"path": str(path), "reason": str(exc)},
        ) from exc
    return loads_canonical_json(raw)


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


def _write_new(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as handle:
        handle.write(data)
        handle.flush()
        os.fsync(handle.fileno())
    _fsync_directory(path.parent)
    if sha256_file(path) != sha256_bytes(data):
        raise TransactionError("new file failed post-write verification", details={"path": str(path)})


def _replace_exact(path: Path, data: bytes, *, expected_sha256: str, token: str) -> None:
    observed = sha256_file(path) if path.exists() else "NOT_APPLICABLE"
    if observed != expected_sha256:
        raise TransactionError(
            "caller snapshot CAS mismatch",
            details={"path": str(path), "expected_sha256": expected_sha256, "observed_sha256": observed},
        )
    temp = path.with_name(f".{path.name}.{token}.tmp")
    if temp.exists():
        raise TransactionError("transaction temp already exists", details={"path": str(temp)})
    _write_new(temp, data)
    os.replace(temp, path)
    _fsync_directory(path.parent)
    if sha256_file(path) != sha256_bytes(data):
        raise TransactionError("critical replace failed post-write verification", details={"path": str(path)})


def _restore_exact(
    path: Path,
    old_data: bytes | None,
    token: str,
    *,
    expected_owned_sha256: str | None = None,
) -> None:
    """Restore only bytes demonstrably published by this transaction.

    A concurrent third-party value is never overwritten.  If the old state is
    already present the function is idempotent.
    """

    observed = sha256_file(path) if path.exists() else "NOT_APPLICABLE"
    old_sha = "NOT_APPLICABLE" if old_data is None else sha256_bytes(old_data)
    if observed == old_sha:
        return
    if expected_owned_sha256 is not None and observed != expected_owned_sha256:
        raise TransactionError(
            "rollback refused to overwrite a concurrent commit",
            details={
                "path": str(path),
                "expected_owned_sha256": expected_owned_sha256,
                "observed_sha256": observed,
            },
        )
    if old_data is None:
        if path.exists():
            path.unlink()
            _fsync_directory(path.parent)
        return
    temp = path.with_name(f".{path.name}.{token}.rollback.tmp")
    if temp.exists():
        temp.unlink()
    _write_new(temp, old_data)
    os.replace(temp, path)
    _fsync_directory(path.parent)
    if path.read_bytes() != old_data:
        raise TransactionError("rollback verification failed", details={"path": str(path)})


def _journaled_replace(
    path: Path,
    data: bytes,
    *,
    expected_sha256: str,
    journal_dir: Path,
    scope: Mapping[str, Any],
    generation: int,
    updated_at: str,
    transaction_kind: str,
    _fault: FaultHook | None = None,
) -> Path:
    """Replace one mutable control with a retained session-scoped journal."""

    token = f"{transaction_kind}_{generation}_{uuid.uuid4().hex}"
    journal_path = journal_dir / f"JOURNAL_{token}.json"
    old_data = path.read_bytes() if path.exists() else None
    journal = {
        "created_at": updated_at,
        "generation": generation,
        "new_target_sha256": sha256_bytes(data),
        "old_target_sha256": "NOT_APPLICABLE" if old_data is None else sha256_bytes(old_data),
        "schema": "CTL_P2A_SCOPED_CONTROL_JOURNAL_V1",
        "scope": dict(scope),
        "state": "PREPARED",
        "target_name": path.name,
        "transaction_kind": transaction_kind,
    }
    _write_new(journal_path, canonical_json_bytes(journal))
    published = False
    try:
        _replace_exact(path, data, expected_sha256=expected_sha256, token=token)
        published = True
        _call_fault(_fault, f"{transaction_kind.upper()}_CONTROL_REPLACED", {"generation": generation})
        journal["state"] = "COMMITTED"
        _replace_exact(
            journal_path,
            canonical_json_bytes(journal),
            expected_sha256=sha256_file(journal_path),
            token=f"{token}_journal_commit",
        )
    except BaseException:
        if published:
            _restore_exact(
                path,
                old_data,
                token,
                expected_owned_sha256=sha256_bytes(data),
            )
        journal["state"] = "ROLLED_BACK"
        journal["rollback_verified"] = True
        _replace_exact(
            journal_path,
            canonical_json_bytes(journal),
            expected_sha256=sha256_file(journal_path),
            token=f"{token}_journal_rollback",
        )
        raise
    return journal_path


def _call_fault(hook: FaultHook | None, stage: str, evidence: Mapping[str, Any]) -> None:
    if hook is not None:
        hook(stage, evidence)


def snapshot_tree(root: os.PathLike[str] | str, *, exclude_relative: Iterable[str] = ()) -> dict[str, str]:
    base = Path(root)
    excluded = {_portable_relative(value) for value in exclude_relative}
    result: dict[str, str] = {}
    for path in sorted(base.rglob("*"), key=lambda item: item.relative_to(base).as_posix()):
        relative = path.relative_to(base).as_posix()
        if relative == ".git" or relative.startswith(".git/") or relative in excluded:
            continue
        if path.is_symlink():
            raise ValidationError("snapshot refuses symbolic links", details={"relative_path": relative})
        if path.is_file():
            result[relative] = sha256_file(path)
    return result


def _is_excluded_operational_path(relative_parts: Sequence[str]) -> bool:
    """Return true for non-authoritative retained/partial transaction evidence."""

    if any(".partial." in part or part.endswith(".partial") for part in relative_parts):
        return True
    if any(part in {"autosave", "journals", "recovery"} for part in relative_parts):
        return True
    name = relative_parts[-1] if relative_parts else ""
    return (
        name.startswith(".")
        or name.endswith(".transaction.json")
        or name.endswith(".journal.json")
        or ".backup." in name
        or ".quarantine" in name
        or name.endswith(".tmp")
    )


def _assert_safe_published_tree(root: Path) -> None:
    """Reject links, reparse points, hardlinks and special published entries."""

    try:
        plain_directory(root, label="published project root")
    except PathSafetyError as exc:
        raise ValidationError("project root is unsafe", details={"reason": str(exc)}) from exc
    pending = [root]
    while pending:
        directory = pending.pop()
        try:
            entries = list(os.scandir(directory))
        except OSError as exc:
            raise ValidationError(
                "published project tree cannot be enumerated",
                details={"path": str(directory), "reason": str(exc)},
            ) from exc
        for entry in entries:
            path = Path(entry.path)
            parts = path.relative_to(root).parts
            if _is_excluded_operational_path(parts) and any(
                ".partial." in part or part.endswith(".partial") for part in parts
            ):
                # Retained partials are recovery evidence, never authority.
                continue
            relative = PurePosixPath(*parts).as_posix()
            try:
                if is_reparse_or_link(path):
                    raise PathSafetyError("link/reparse point")
                if entry.is_dir(follow_symlinks=False):
                    plain_directory(path, label="published project directory")
                    pending.append(path)
                elif entry.is_file(follow_symlinks=False):
                    plain_file(path, label="published project file", single_link=True)
                else:
                    raise PathSafetyError("non-regular filesystem entry")
            except PathSafetyError as exc:
                raise ValidationError(
                    "published project contains a linked, reparsed, hardlinked or special entry",
                    details={"relative_path": relative, "reason": str(exc)},
                ) from exc


def _approved_logical_bytes(path: Path) -> tuple[bytes, str]:
    """Return the approved LF bytes across a Git CRLF checkout filter.

    The contract sidecars bind repository/candidate LF bytes.  Windows Git may
    materialise text authorities as CRLF while reporting a clean worktree.
    Only an all-CRLF transport conversion is accepted; a lone or mixed CR is
    rejected.
    """

    raw = path.read_bytes()
    transport = "LF_EXACT"
    if b"\r" in raw and b"\r" not in raw.replace(b"\r\n", b""):
        raw = raw.replace(b"\r\n", b"\n")
        transport = "GIT_CRLF_CHECKOUT_NORMALIZED_TO_APPROVED_LF"
    if b"\r" in raw:
        raise ValidationError("approved contract contains a non-transport CR", details={"path": str(path)})
    return raw, transport


def verify_approved_contract(repository_root: os.PathLike[str] | str) -> dict[str, Any]:
    """Verify the approved record, index and immutable profile identities."""

    root = Path(repository_root)
    supplement = root / "contract_supplement_p2"
    approval_path = supplement / "approval" / "P2_ENTRY_APPROVAL_RECORD.json"
    approval_sidecar = approval_path.with_suffix(approval_path.suffix + ".sha256")
    if not approval_path.is_file() or not approval_sidecar.is_file():
        raise ValidationError("approved P2 entry record or sidecar is absent")
    approval_bytes, approval_transport = _approved_logical_bytes(approval_path)
    approval = loads_canonical_json(approval_bytes)
    if approval_sidecar.read_text(encoding="ascii").split()[0] != sha256_bytes(approval_bytes):
        raise ValidationError("approved P2 entry record sidecar mismatch")
    if approval.get("approval_status") != "APPROVED" or approval.get("approved_by") != "Marcelo":
        raise ValidationError("P2 entry record is not Marcelo's approval")
    if approval.get("prompt2_implementation_authorized") is not True:
        raise ValidationError("P2 implementation is not authorized")
    index_path = supplement / "PROFILE_INDEX.json"
    index_bytes, index_transport = _approved_logical_bytes(index_path)
    if sha256_bytes(index_bytes) != APPROVED_PROFILE_INDEX_SHA256:
        raise ValidationError("approved profile index physical hash mismatch")
    index = loads_canonical_json(index_bytes)
    indexed = {item["profile_id"]: item["profile_sha256"] for item in index["profiles"]}
    if indexed != APPROVED_PROFILE_HASHES:
        raise ValidationError("approved internal profile hash inventory mismatch")
    physical_hashes: dict[str, str] = {}
    for profile_id, expected_internal in sorted(APPROVED_PROFILE_HASHES.items()):
        path = supplement / "profiles" / f"{profile_id}.json"
        sidecar = path.with_suffix(path.suffix + ".sha256")
        raw, transport = _approved_logical_bytes(path)
        physical = sha256_bytes(raw)
        if sidecar.read_text(encoding="ascii").split()[0] != physical:
            raise ValidationError("profile physical sidecar mismatch", details={"profile_id": profile_id})
        profile = loads_canonical_json(raw)
        if profile.get("profile_sha256") != expected_internal:
            raise ValidationError("profile internal identity mismatch", details={"profile_id": profile_id})
        physical_hashes[profile_id] = physical
    approval_profiles = approval.get("profile_hashes")
    if not isinstance(approval_profiles, dict) or approval_profiles != APPROVED_PROFILE_HASHES:
        raise ValidationError("approval record does not bind the ten profiles")
    if approval.get("profile_index_sha256") != APPROVED_PROFILE_INDEX_SHA256:
        raise ValidationError("approval record profile-index binding mismatch")
    if approval.get("addendum_sha256") != APPROVED_ADDENDUM_SHA256:
        raise ValidationError("approval record addendum binding mismatch")
    if approval.get("supplement_build_sha256") != APPROVED_SUPPLEMENT_SHA256:
        raise ValidationError("approval record supplement binding mismatch")

    correction_root = root / "contract_supplement_p2_correction"
    correction_approval_path = (
        correction_root / "approval" / "P2_CONTRACT_CORRECTION_APPROVAL_RECORD.json"
    )
    correction_approval_bytes, correction_approval_transport = _approved_logical_bytes(
        correction_approval_path
    )
    if sha256_bytes(correction_approval_bytes) != CORRECTION_APPROVAL_RECORD_SHA256:
        raise ValidationError("correction approval record physical hash mismatch")
    correction_sidecar_bytes, _ = _approved_logical_bytes(
        correction_approval_path.with_suffix(correction_approval_path.suffix + ".sha256")
    )
    if correction_sidecar_bytes != (
        f"{CORRECTION_APPROVAL_RECORD_SHA256}  "
        "P2_CONTRACT_CORRECTION_APPROVAL_RECORD.json\n"
    ).encode("ascii"):
        raise ValidationError("correction approval record sidecar mismatch")
    correction_approval = loads_canonical_json(correction_approval_bytes)

    correction_index_path = correction_root / "EFFECTIVE_CONTRACT_INDEX.json"
    correction_index_bytes, correction_index_transport = _approved_logical_bytes(
        correction_index_path
    )
    if sha256_bytes(correction_index_bytes) != CORRECTION_INDEX_SHA256:
        raise ValidationError("effective correction index physical hash mismatch")
    correction_index = loads_canonical_json(correction_index_bytes)

    addendum_path = root / "docs" / "contracts" / "CTL_P2_CONTRACT_CORRECTION_ADDENDUM_V1.md"
    addendum_bytes, _ = _approved_logical_bytes(addendum_path)
    if sha256_bytes(addendum_bytes) != CORRECTION_ADDENDUM_SHA256:
        raise ValidationError("correction addendum physical hash mismatch")

    oracle_path = correction_root / "tests" / "TEST_ORACLE_INDEX.json"
    oracle_bytes, _ = _approved_logical_bytes(oracle_path)
    if sha256_bytes(oracle_bytes) != CORRECTION_ORACLE_INDEX_SHA256:
        raise ValidationError("correction oracle index physical hash mismatch")
    oracle = loads_canonical_json(oracle_bytes)
    records = oracle.get("records")
    if (
        oracle.get("schema") != "CTL_P2_CONTRACT_CORRECTION_TEST_ORACLE_INDEX_V1"
        or oracle.get("golden_count") != 17
        or not isinstance(records, list)
        or len(records) != 17
    ):
        raise ValidationError("correction oracle inventory mismatch")
    golden_ids: set[str] = set()
    for record in records:
        if not isinstance(record, dict) or not isinstance(record.get("golden_id"), str):
            raise ValidationError("correction oracle record is invalid")
        golden_id = record["golden_id"]
        if golden_id in golden_ids:
            raise ValidationError("correction oracle golden ID is duplicated")
        golden_ids.add(golden_id)
        for path_field, hash_field in (
            ("descriptor_path", "descriptor_sha256"),
            ("fixture_path", "fixture_sha256"),
        ):
            relative = _portable_relative(record.get(path_field), path_field)
            expected_hash = _require_sha(record.get(hash_field), hash_field)
            raw, _ = _approved_logical_bytes(_contained(correction_root, relative))
            if sha256_bytes(raw) != expected_hash:
                raise ValidationError(
                    "correction golden physical hash mismatch",
                    details={"golden_id": golden_id, "path_field": path_field},
                )

    indexed_profiles = correction_index.get("profiles")
    if not isinstance(indexed_profiles, list) or len(indexed_profiles) != 2:
        raise ValidationError("correction profile index inventory mismatch")
    indexed_by_id = {
        item.get("profile_id"): item for item in indexed_profiles if isinstance(item, dict)
    }
    if set(indexed_by_id) != set(CORRECTION_PROFILE_FILES):
        raise ValidationError("correction profile index IDs mismatch")
    correction_physical_hashes: dict[str, str] = {}
    correction_logical_hashes: dict[str, str] = {}
    for profile_id, (expected_file_hash, expected_profile_hash) in sorted(
        CORRECTION_PROFILE_FILES.items()
    ):
        path = correction_root / "profiles" / f"{profile_id}.json"
        raw, _ = _approved_logical_bytes(path)
        file_hash = sha256_bytes(raw)
        if file_hash != expected_file_hash:
            raise ValidationError(
                "correction profile physical hash mismatch",
                details={"profile_id": profile_id},
            )
        sidecar_raw, _ = _approved_logical_bytes(path.with_suffix(path.suffix + ".sha256"))
        if sidecar_raw != f"{file_hash}  {path.name}\n".encode("ascii"):
            raise ValidationError(
                "correction profile sidecar mismatch", details={"profile_id": profile_id}
            )
        profile = loads_canonical_json(raw)
        if profile.get("profile_id") != profile_id or profile.get("profile_sha256") != expected_profile_hash:
            raise ValidationError(
                "correction profile logical identity mismatch", details={"profile_id": profile_id}
            )
        indexed = indexed_by_id[profile_id]
        if (
            indexed.get("file_sha256") != expected_file_hash
            or indexed.get("profile_sha256") != expected_profile_hash
        ):
            raise ValidationError(
                "correction index/profile binding mismatch", details={"profile_id": profile_id}
            )
        correction_physical_hashes[profile_id] = file_hash
        correction_logical_hashes[profile_id] = expected_profile_hash

    if (
        correction_index.get("schema") != "CTL_P2_EFFECTIVE_CONTRACT_INDEX_V2"
        or correction_index.get("golden_count") != 17
        or correction_approval.get("schema")
        != "CTL_P2_CONTRACT_CORRECTION_APPROVAL_RECORD_V1"
        or correction_approval.get("approval_status") != "APPROVED"
        or correction_approval.get("approved_by") != "Marcelo"
        or correction_approval.get("prompt2a_implementation_authorized") is not True
        or correction_approval.get("effective_contract_index_sha256")
        != CORRECTION_INDEX_SHA256
        or correction_approval.get("addendum_sha256") != CORRECTION_ADDENDUM_SHA256
        or correction_approval.get("test_oracle_index_sha256")
        != CORRECTION_ORACLE_INDEX_SHA256
        or correction_approval.get("profile_hashes") != correction_logical_hashes
        or correction_approval.get("profile_file_hashes") != correction_physical_hashes
    ):
        raise ValidationError("correction approval bindings mismatch")

    effective_path = root / "approval" / "P2_EFFECTIVE_CONTRACT_RECORD_V2.json"
    effective_bytes, effective_transport = _approved_logical_bytes(effective_path)
    if sha256_bytes(effective_bytes) != EFFECTIVE_CONTRACT_RECORD_SHA256:
        raise ValidationError("effective contract record physical hash mismatch")
    effective_sidecar_bytes, _ = _approved_logical_bytes(
        effective_path.with_suffix(effective_path.suffix + ".sha256")
    )
    if effective_sidecar_bytes != (
        f"{EFFECTIVE_CONTRACT_RECORD_SHA256}  P2_EFFECTIVE_CONTRACT_RECORD_V2.json\n"
    ).encode("ascii"):
        raise ValidationError("effective contract record sidecar mismatch")
    effective = loads_canonical_json(effective_bytes)
    correction_binding = effective.get("correction")
    base_binding = effective.get("base_p2_supplement")
    if (
        effective.get("schema") != "CTL_P2_EFFECTIVE_CONTRACT_RECORD_V2"
        or effective.get("status")
        != "APPROVED_FOR_INTERNAL_TECHNICAL_PREVIEW_DEVELOPMENT"
        or effective.get("prompt2a_implementation_authorized") is not True
        or not isinstance(correction_binding, dict)
        or correction_binding.get("approval_record_sha256")
        != CORRECTION_APPROVAL_RECORD_SHA256
        or correction_binding.get("effective_contract_index_sha256")
        != CORRECTION_INDEX_SHA256
        or correction_binding.get("addendum_sha256") != CORRECTION_ADDENDUM_SHA256
        or correction_binding.get("test_oracle_index_sha256")
        != CORRECTION_ORACLE_INDEX_SHA256
        or correction_binding.get("profile_hashes") != correction_logical_hashes
        or not isinstance(base_binding, dict)
        or base_binding.get("approval_record_sha256") != APPROVED_APPROVAL_RECORD_SHA256
        or base_binding.get("profile_index_sha256") != APPROVED_PROFILE_INDEX_SHA256
        or base_binding.get("supplement_build_sha256") != APPROVED_SUPPLEMENT_SHA256
    ):
        raise ValidationError("effective contract record bindings mismatch")
    return {
        "result": "PASS",
        "approval_record_sha256": sha256_bytes(approval_bytes),
        "approval_transport": approval_transport,
        "profile_index_sha256": APPROVED_PROFILE_INDEX_SHA256,
        "profile_index_transport": index_transport,
        "physical_profile_hashes": physical_hashes,
        "profile_count": len(physical_hashes),
        "correction_approval_transport": correction_approval_transport,
        "correction_index_transport": correction_index_transport,
        "correction_physical_profile_hashes": correction_physical_hashes,
        "correction_profile_count": len(correction_physical_hashes),
        "effective_contract_record_sha256": EFFECTIVE_CONTRACT_RECORD_SHA256,
        "effective_contract_transport": effective_transport,
    }


def _project_descriptor(project_uid: str, project_id: str, created_at: str) -> dict[str, Any]:
    return {
        "created_at": created_at,
        "project_id": project_id,
        "project_schema_version": 2,
        "project_uid": project_uid,
        "schema": "CTL_P2A_PROJECT_JSON_V1",
    }


def _empty_source_registry(project_uid: str, updated_at: str) -> dict[str, Any]:
    return {
        "blobs": [],
        "image_bindings": [],
        "project_uid": project_uid,
        "schema": "CTL_SOURCE_REGISTRY_V1",
        "updated_at": updated_at,
    }


def create_project(
    root: os.PathLike[str] | str,
    *,
    project_uid: str,
    project_id: str,
    created_at: str | None = None,
) -> "SessionCore":
    """Create one schema-v2 project at a new exact root."""

    uid = _require_uuid(project_uid, "project_uid")
    identifier = _safe_component(project_id, "project_id")
    timestamp = _require_timestamp(created_at or utc_now_z(), "created_at")
    target = Path(root)
    if target.exists() or target.is_symlink():
        raise TransactionError("schema-v2 project root must be new", details={"path": str(target)})
    if not target.parent.is_dir():
        raise TransactionError("schema-v2 project parent does not exist", details={"path": str(target.parent)})
    partial = target.with_name(f".{target.name}.partial.{uuid.uuid4().hex}")
    partial.mkdir()
    try:
        (partial / "controls").mkdir()
        (partial / "sources" / "blobs").mkdir(parents=True)
        (partial / "studies").mkdir()
        _write_new(partial / "project.json", canonical_json_bytes(_project_descriptor(uid, identifier, timestamp)))
        _write_new(
            partial / "controls" / "source_registry.json",
            canonical_json_bytes(_empty_source_registry(uid, timestamp)),
        )
        os.rename(partial, target)
        _fsync_directory(target.parent)
    except BaseException:
        # A never-published project partial contains no user source and is safe
        # to retain as evidence; automatic recursive deletion is intentionally
        # avoided under OD-17.
        raise
    core = SessionCore(target)
    core.refresh_storage_manifest()
    return core


class SessionCore:
    """Storage service bound to one already-created schema-v2 project."""

    def __init__(self, project_root: os.PathLike[str] | str):
        self.root = Path(project_root)
        if not self.root.is_dir() or self.root.is_symlink():
            raise ValidationError("project root is absent or unsafe")
        project = _canonical_read(self.root / "project.json")
        if set(project) != {"created_at", "project_id", "project_schema_version", "project_uid", "schema"}:
            raise ValidationError("project descriptor field inventory is not closed")
        if project["project_schema_version"] != 2 or project["schema"] != "CTL_P2A_PROJECT_JSON_V1":
            raise ValidationError("project descriptor is not schema v2")
        self.project_uid = _require_uuid(project["project_uid"], "project_uid")
        self.project_id = _safe_component(project["project_id"], "project_id")

    @classmethod
    def create(cls, root: os.PathLike[str] | str, **kwargs: Any) -> "SessionCore":
        return create_project(root, **kwargs)

    @property
    def source_registry_path(self) -> Path:
        return self.root / "controls" / "source_registry.json"

    @property
    def _source_registry_lock_path(self) -> Path:
        return self.root / "controls" / ".source_registry_cas.lock"

    @property
    def _source_registry_journal_root(self) -> Path:
        return self.root / "controls" / "journals"

    @contextmanager
    def _source_registry_writer_lock(self) -> Iterable[None]:
        """Serialize every cooperative source-registry snapshot/CAS sequence.

        The one-byte lock file is stable operational state excluded from the
        published authority inventory.  The operating-system lock is released
        automatically on process termination, so a crash cannot leave a stale
        logical owner that another process might silently override.
        """

        path = self._source_registry_lock_path
        if not path.exists() and not path.is_symlink():
            try:
                _write_new(path, b"\x00")
            except FileExistsError:
                pass
        try:
            checked = plain_file(path, label="source registry writer lock", single_link=True)
        except PathSafetyError as exc:
            raise ValidationError(
                "source registry writer lock is unsafe",
                details={"path": str(path), "reason": str(exc)},
            ) from exc
        handle = checked.open("r+b", buffering=0)
        acquired = False
        try:
            if os.name == "nt":
                import msvcrt

                handle.seek(0)
                try:
                    msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
                except OSError as exc:
                    raise TransactionError(
                        "source registry writer CAS is already active",
                        details={"path": str(path)},
                    ) from exc
            else:
                import fcntl

                try:
                    fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                except OSError as exc:
                    raise TransactionError(
                        "source registry writer CAS is already active",
                        details={"path": str(path)},
                    ) from exc
            acquired = True
            yield
        finally:
            if acquired:
                if os.name == "nt":
                    import msvcrt

                    handle.seek(0)
                    msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    import fcntl

                    fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
            handle.close()

    def _source_registry_snapshot(self) -> tuple[dict[str, Any], bytes, str]:
        """Return registry value and digest derived from one stable byte read."""

        try:
            raw = stable_plain_bytes(
                self.source_registry_path,
                label="source registry snapshot authority",
            )
        except PathSafetyError as exc:
            raise ValidationError(
                "source registry is not a stable plain single-link file",
                details={"path": str(self.source_registry_path), "reason": str(exc)},
            ) from exc
        value = loads_canonical_json(raw)
        self._validate_source_registry(value, verify_blobs=True, verify_descriptors=True)
        return dict(value), raw, sha256_bytes(raw)

    def _source_registry(self) -> dict[str, Any]:
        value, _, _ = self._source_registry_snapshot()
        return value

    def _replace_source_registry_locked(
        self,
        data: bytes,
        *,
        expected_sha256: str,
        token: str,
    ) -> None:
        """Replace the registry under the project writer lock with two CAS checks."""

        try:
            observed_bytes = stable_plain_bytes(
                self.source_registry_path,
                label="source registry CAS authority",
            )
        except PathSafetyError as exc:
            raise TransactionError(
                "source registry CAS authority is unsafe",
                details={"path": str(self.source_registry_path), "reason": str(exc)},
            ) from exc
        observed_sha = sha256_bytes(observed_bytes)
        if observed_sha != expected_sha256:
            raise TransactionError(
                "source registry CAS mismatch",
                details={
                    "expected_sha256": expected_sha256,
                    "observed_sha256": observed_sha,
                    "source_registry_cas_mismatch": True,
                },
            )
        temp = self.source_registry_path.with_name(
            f".{self.source_registry_path.name}.{token}.tmp"
        )
        if temp.exists() or temp.is_symlink():
            raise TransactionError(
                "source registry CAS temp already exists",
                details={"path": str(temp)},
            )
        _write_new(temp, data)
        try:
            rechecked = stable_plain_bytes(
                self.source_registry_path,
                label="source registry CAS recheck authority",
            )
        except PathSafetyError as exc:
            raise TransactionError(
                "source registry CAS recheck is unsafe",
                details={"path": str(self.source_registry_path), "reason": str(exc)},
            ) from exc
        rechecked_sha = sha256_bytes(rechecked)
        if rechecked_sha != expected_sha256:
            raise TransactionError(
                "source registry CAS changed before replace",
                details={
                    "expected_sha256": expected_sha256,
                    "observed_sha256": rechecked_sha,
                    "source_registry_cas_mismatch": True,
                },
            )
        os.replace(temp, self.source_registry_path)
        _fsync_directory(self.source_registry_path.parent)
        published = stable_plain_bytes(
            self.source_registry_path,
            label="published source registry authority",
        )
        if published != data:
            raise TransactionError("source registry CAS failed post-write verification")

    def _source_registry_journal_paths(self) -> list[Path]:
        root = self._source_registry_journal_root
        if not root.exists() and not root.is_symlink():
            return []
        try:
            checked = plain_directory(root, label="source registry journal root")
        except PathSafetyError as exc:
            raise ValidationError(
                "source registry journal root is unsafe",
                details={"path": str(root), "reason": str(exc)},
            ) from exc
        paths: list[Path] = []
        for entry in sorted(checked.iterdir(), key=lambda item: item.name):
            if re.fullmatch(r"JOURNAL_source_registry_[0-9a-f]{32}\.json", entry.name):
                try:
                    paths.append(
                        plain_file(
                            entry,
                            label="source registry transaction journal",
                            single_link=True,
                        )
                    )
                except PathSafetyError as exc:
                    raise ValidationError(
                        "source registry journal is unsafe",
                        details={"path": str(entry), "reason": str(exc)},
                    ) from exc
                continue
            if (
                entry.name.startswith(".JOURNAL_source_registry_")
                and entry.name.endswith(".tmp")
                and entry.is_file()
                and not entry.is_symlink()
            ):
                # A process may stop after flushing an atomic journal update but
                # before replacing the journal.  The authoritative journal still
                # determines recovery; the retained temp is operational evidence.
                try:
                    plain_file(
                        entry,
                        label="retained source journal update temp",
                        single_link=True,
                    )
                except PathSafetyError as exc:
                    raise ValidationError(
                        "retained source journal update temp is unsafe",
                        details={"path": str(entry), "reason": str(exc)},
                    ) from exc
                continue
            raise ValidationError(
                "source registry journal directory contains an unknown entry",
                details={"path": str(entry)},
            )
        return paths

    def _validate_source_registry_journal(
        self,
        path: Path,
        value: Mapping[str, Any],
    ) -> dict[str, Any]:
        if not isinstance(value, Mapping) or set(value) != SOURCE_REGISTRY_JOURNAL_FIELDS:
            raise ValidationError(
                "source registry journal field inventory is not closed",
                details={"path": str(path)},
            )
        journal = dict(value)
        transaction_id = journal.get("transaction_id")
        if (
            not isinstance(transaction_id, str)
            or re.fullmatch(r"source_registry_[0-9a-f]{32}", transaction_id) is None
            or path.name != f"JOURNAL_{transaction_id}.json"
        ):
            raise ValidationError("source registry journal transaction identity is invalid")
        state = journal.get("state")
        recovery_action = journal.get("recovery_action")
        if (
            journal.get("schema") != SOURCE_REGISTRY_JOURNAL_SCHEMA
            or journal.get("project_uid") != self.project_uid
            or state not in SOURCE_REGISTRY_JOURNAL_STATES
            or recovery_action not in SOURCE_REGISTRY_JOURNAL_RECOVERY_ACTIONS
        ):
            raise ValidationError("source registry journal project/schema/state mismatch")
        _require_timestamp(journal.get("created_at"), "source_journal.created_at")
        _require_timestamp(journal.get("updated_at"), "source_journal.updated_at")
        image_uid = _require_uuid(journal.get("image_uid"), "source_journal.image_uid")
        image_id = _safe_component(journal.get("image_id"), "source_journal.image_id")
        parent_scope = _portable_relative(
            journal.get("parent_scope_key"),
            "source_journal.parent_scope_key",
        )
        if len(PurePosixPath(parent_scope).parts) != 5 or not parent_scope.startswith(
            f"{self.project_uid}/"
        ):
            raise ValidationError("source registry journal parent scope is invalid")
        source_sha = _require_sha(journal.get("source_sha256"), "source_journal.source_sha256")
        _require_sha(
            journal.get("image_binding_sha256"),
            "source_journal.image_binding_sha256",
        )
        _require_sha(
            journal.get("image_descriptor_sha256"),
            "source_journal.image_descriptor_sha256",
        )
        old_registry_sha = _require_sha(
            journal.get("old_registry_sha256"),
            "source_journal.old_registry_sha256",
        )
        new_registry_sha = _require_sha(
            journal.get("new_registry_sha256"),
            "source_journal.new_registry_sha256",
        )
        observed_registry_sha = _require_sha(
            journal.get("observed_registry_sha256"),
            "source_journal.observed_registry_sha256",
        )
        if old_registry_sha == new_registry_sha:
            raise ValidationError("source registry journal does not describe a registry mutation")
        if state in {
            "PREPARED",
            "RECOVERY_REQUIRED",
            "IMAGE_PUBLISHED_PENDING_REGISTRY",
        } and observed_registry_sha != old_registry_sha:
            raise ValidationError("pre-CAS source journal has an impossible observed registry hash")
        if (
            state == "REGISTRY_PUBLISHED_PENDING_COMMIT"
            and observed_registry_sha != new_registry_sha
        ):
            raise ValidationError("post-CAS source journal has an impossible observed registry hash")
        _require_nonnegative(journal.get("source_byte_size"), "source_journal.source_byte_size")
        for field in (
            "blob_was_preexisting",
            "image_was_published",
            "registry_was_replaced",
        ):
            if not isinstance(journal.get(field), bool):
                raise ValidationError(
                    "source registry journal boolean field is invalid",
                    details={"field": field},
                )
        image_relative = _portable_relative(
            journal.get("image_relative_path"),
            "source_journal.image_relative_path",
        )
        partial_relative = _portable_relative(
            journal.get("image_partial_relative_path"),
            "source_journal.image_partial_relative_path",
        )
        blob_relative = _portable_relative(
            journal.get("blob_relative_path"),
            "source_journal.blob_relative_path",
        )
        expected_source_relative = f"sources/blobs/{source_sha[:2]}/{source_sha}/source.bin"
        if blob_relative != expected_source_relative:
            raise ValidationError("source registry journal blob path is not derived from SHA-256")
        final_parts = PurePosixPath(image_relative)
        partial_parts = PurePosixPath(partial_relative)
        if final_parts.name != image_id:
            raise ValidationError("source registry journal image path/id mismatch")
        image_parts = final_parts.parts
        parent_parts = PurePosixPath(parent_scope).parts
        if (
            len(image_parts) != 10
            or image_parts[0] != "studies"
            or image_parts[2] != "conditions"
            or image_parts[4] != "specimens"
            or image_parts[6] != "lamellae"
            or image_parts[8] != "images"
            or parent_parts[1:] != (
                image_parts[1],
                image_parts[3],
                image_parts[5],
                image_parts[7],
            )
        ):
            raise ValidationError("source registry journal image path/parent mismatch")
        transaction_nonce = transaction_id.removeprefix("source_registry_")
        expected_partial_name = f".{final_parts.name}.partial.{transaction_nonce}"
        if partial_parts.parent != final_parts.parent or partial_parts.name != expected_partial_name:
            raise ValidationError("source registry journal partial path is not derived exactly")
        blob_partial_relative = journal.get("blob_partial_relative_path")
        if journal["blob_was_preexisting"]:
            if blob_partial_relative is not None:
                raise ValidationError("pre-existing source blob declares a staging partial")
        else:
            blob_partial_relative = _portable_relative(
                blob_partial_relative,
                "source_journal.blob_partial_relative_path",
            )
            blob_parts = PurePosixPath(blob_relative)
            blob_partial_parts = PurePosixPath(blob_partial_relative)
            expected_blob_partial = f".{blob_parts.name}.partial.{transaction_nonce}"
            if (
                blob_partial_parts.parent != blob_parts.parent
                or blob_partial_parts.name != expected_blob_partial
            ):
                raise ValidationError("source registry blob partial path is not derived exactly")
        blob_recovery_relative = journal.get("blob_recovery_relative_path")
        if blob_recovery_relative is not None:
            blob_recovery_relative = _portable_relative(
                blob_recovery_relative,
                "source_journal.blob_recovery_relative_path",
            )
            expected_blob_recovery = (
                f"controls/recovery/source_registry/{transaction_id}/source.bin"
            )
            if blob_recovery_relative != expected_blob_recovery:
                raise ValidationError("source registry blob recovery path is not derived exactly")
        quarantine_relative = journal.get("quarantine_relative_path")
        if quarantine_relative is not None:
            quarantine_relative = _portable_relative(
                quarantine_relative,
                "source_journal.quarantine_relative_path",
            )
            quarantine_parts = PurePosixPath(quarantine_relative)
            expected_quarantine_name = f".{final_parts.name}.{transaction_id}.quarantine"
            if (
                quarantine_parts.parent != final_parts.parent
                or quarantine_parts.name != expected_quarantine_name
            ):
                raise ValidationError("source registry journal quarantine path is not derived exactly")
        pending_actions = {
            "PREPARED": "RECOVERY_REQUIRED",
            "RECOVERY_REQUIRED": "RECOVERY_REQUIRED",
            "IMAGE_PUBLISHED_PENDING_REGISTRY": "RECOVERY_REQUIRED",
            "REGISTRY_PUBLISHED_PENDING_COMMIT": "RECOVERY_REQUIRED",
        }
        if state in pending_actions and recovery_action != pending_actions[state]:
            raise ValidationError("pending source journal lacks RECOVERY_REQUIRED action")
        if state in {"PREPARED", "RECOVERY_REQUIRED"} and (
            journal["image_was_published"] or journal["registry_was_replaced"]
        ):
            raise ValidationError("pre-publication source journal flags are inconsistent")
        if state == "IMAGE_PUBLISHED_PENDING_REGISTRY" and (
            not journal["image_was_published"] or journal["registry_was_replaced"]
        ):
            raise ValidationError("pre-CAS source journal flags are inconsistent")
        if state == "REGISTRY_PUBLISHED_PENDING_COMMIT" and (
            not journal["image_was_published"] or not journal["registry_was_replaced"]
        ):
            raise ValidationError("post-CAS source journal flags are inconsistent")
        if state in {"COMMITTED", "COMMITTED_RECOVERED"}:
            expected_action = "NONE" if state == "COMMITTED" else "FINALIZE_COMMITTED"
            if (
                recovery_action != expected_action
                or not journal["image_was_published"]
                or not journal["registry_was_replaced"]
                or observed_registry_sha != new_registry_sha
                or quarantine_relative is not None
                or blob_recovery_relative is not None
            ):
                raise ValidationError("committed source journal outcome is inconsistent")
        if state in {"ROLLED_BACK", "ROLLED_BACK_RECOVERED"}:
            if observed_registry_sha == new_registry_sha:
                raise ValidationError("rolled-back source journal still observes its new registry")
            if recovery_action not in {
                "QUARANTINE_UNREGISTERED_IMAGE",
                "FINALIZE_ROLLED_BACK",
            }:
                raise ValidationError("rolled-back source journal action is invalid")
            if recovery_action == "QUARANTINE_UNREGISTERED_IMAGE" and (
                not journal["image_was_published"] or quarantine_relative is None
            ):
                raise ValidationError("rolled-back source journal lacks quarantine evidence")
            if recovery_action == "FINALIZE_ROLLED_BACK" and quarantine_relative is not None:
                raise ValidationError("rollback without image unexpectedly declares quarantine")
            if journal["image_was_published"] != (quarantine_relative is not None):
                raise ValidationError("rolled-back source journal image evidence is ambiguous")
        if state == "BLOCKED_RECOVERY" and recovery_action != "BLOCKED_NO_MUTATION":
            raise ValidationError("blocked source journal action is invalid")
        journal["image_uid"] = image_uid
        journal["image_id"] = image_id
        journal["parent_scope_key"] = parent_scope
        journal["image_relative_path"] = image_relative
        journal["image_partial_relative_path"] = partial_relative
        journal["blob_relative_path"] = blob_relative
        journal["blob_partial_relative_path"] = blob_partial_relative
        journal["blob_recovery_relative_path"] = blob_recovery_relative
        journal["quarantine_relative_path"] = quarantine_relative
        return journal

    def _load_source_registry_journal(self, path: Path) -> dict[str, Any]:
        return self._validate_source_registry_journal(path, _canonical_read(path))

    def _source_registry_contains_journal_binding(
        self,
        registry: Mapping[str, Any],
        journal: Mapping[str, Any],
    ) -> bool:
        matches = [
            item
            for item in registry.get("image_bindings", [])
            if isinstance(item, Mapping) and item.get("image_uid") == journal["image_uid"]
        ]
        if len(matches) != 1:
            return False
        binding = matches[0]
        return (
            sha256_bytes(canonical_json_bytes(dict(binding)))
            == journal["image_binding_sha256"]
            and binding.get("image_relative_path") == journal["image_relative_path"]
            and binding.get("source_sha256") == journal["source_sha256"]
        )

    def _update_source_registry_journal(
        self,
        path: Path,
        *,
        state: str,
        observed_registry_sha256: str,
        image_was_published: bool,
        registry_was_replaced: bool,
        recovery_action: str,
        quarantine_relative_path: str | None,
        blob_recovery_relative_path: str | None,
        updated_at: str,
    ) -> dict[str, Any]:
        if state not in SOURCE_REGISTRY_JOURNAL_STATES:
            raise ValidationError("source registry journal transition target is invalid")
        current = self._load_source_registry_journal(path)
        if current["state"] == state:
            return current
        terminal_states = {
            "COMMITTED",
            "COMMITTED_RECOVERED",
            "ROLLED_BACK",
            "ROLLED_BACK_RECOVERED",
            "BLOCKED_RECOVERY",
        }
        if current["state"] in terminal_states:
            raise ValidationError("source registry journal terminal state cannot transition")
        allowed_targets = {
            "PREPARED": {
                "RECOVERY_REQUIRED",
                "IMAGE_PUBLISHED_PENDING_REGISTRY",
                "COMMITTED_RECOVERED",
                "ROLLED_BACK_RECOVERED",
                "BLOCKED_RECOVERY",
            },
            "RECOVERY_REQUIRED": {
                "COMMITTED_RECOVERED",
                "ROLLED_BACK_RECOVERED",
                "BLOCKED_RECOVERY",
            },
            "IMAGE_PUBLISHED_PENDING_REGISTRY": {
                "REGISTRY_PUBLISHED_PENDING_COMMIT",
                "COMMITTED_RECOVERED",
                "ROLLED_BACK_RECOVERED",
                "BLOCKED_RECOVERY",
            },
            "REGISTRY_PUBLISHED_PENDING_COMMIT": {
                "COMMITTED",
                "COMMITTED_RECOVERED",
                "ROLLED_BACK_RECOVERED",
                "BLOCKED_RECOVERY",
            },
        }
        if state not in allowed_targets.get(current["state"], set()):
            raise ValidationError(
                "source registry journal transition is not allowed",
                details={"from": current["state"], "to": state},
            )
        updated = dict(current)
        updated["state"] = state
        updated["observed_registry_sha256"] = _require_sha(
            observed_registry_sha256,
            "source_journal.observed_registry_sha256",
        )
        if not isinstance(image_was_published, bool) or not isinstance(
            registry_was_replaced, bool
        ):
            raise ValidationError("source registry journal transition flags are invalid")
        if recovery_action not in SOURCE_REGISTRY_JOURNAL_RECOVERY_ACTIONS:
            raise ValidationError("source registry journal recovery action is invalid")
        updated["image_was_published"] = image_was_published
        updated["registry_was_replaced"] = registry_was_replaced
        updated["recovery_action"] = recovery_action
        updated["quarantine_relative_path"] = quarantine_relative_path
        updated["blob_recovery_relative_path"] = blob_recovery_relative_path
        updated["updated_at"] = _require_timestamp(updated_at, "source_journal.updated_at")
        self._validate_source_registry_journal(path, updated)
        data = canonical_json_bytes(updated)
        _replace_exact(
            path,
            data,
            expected_sha256=sha256_file(path),
            token=f"source_journal_{uuid.uuid4().hex}",
        )
        return self._load_source_registry_journal(path)

    def _unregistered_source_image_is_owned(
        self,
        root: Path,
        journal: Mapping[str, Any],
    ) -> bool:
        """Prove exact ownership of the pre-session image tree before moving it."""

        try:
            checked = plain_directory(root, label="journal-owned source image root")
            entries = {entry.name: entry for entry in checked.iterdir()}
            if set(entries) != {"image.json", "sessions"}:
                return False
            descriptor = stable_plain_bytes(
                entries["image.json"],
                label="journal-owned source image descriptor",
            )
            if sha256_bytes(descriptor) != journal["image_descriptor_sha256"]:
                return False
            sessions = plain_directory(
                entries["sessions"],
                label="journal-owned source image sessions root",
            )
            session_entries = {entry.name: entry for entry in sessions.iterdir()}
            if set(session_entries) != {"session_registry.tsv"}:
                return False
            registry_bytes = stable_plain_bytes(
                session_entries["session_registry.tsv"],
                label="journal-owned empty session registry",
            )
            return registry_bytes == SESSION_REGISTRY_HEADER.encode("utf-8")
        except (OSError, PathSafetyError, ValidationError):
            return False

    def _quarantine_unregistered_source_image(
        self,
        journal: Mapping[str, Any],
    ) -> str | None:
        final = _contained(self.root, journal["image_relative_path"])
        final_relative = PurePosixPath(journal["image_relative_path"])
        quarantine_relative = (
            final_relative.parent
            / f".{final_relative.name}.{journal['transaction_id']}.quarantine"
        ).as_posix()
        quarantine = _contained(self.root, quarantine_relative)
        if not final.exists() and not final.is_symlink():
            if quarantine.exists() or quarantine.is_symlink():
                if not self._unregistered_source_image_is_owned(quarantine, journal):
                    raise ValidationError(
                        "existing source image quarantine is not owned by the journal"
                    )
                return quarantine_relative
            return None
        if not self._unregistered_source_image_is_owned(final, journal):
            raise ValidationError(
                "unregistered source image ownership cannot be proven",
                details={"path": str(final)},
            )
        rename_directory_no_replace(final, quarantine, error_type=TransactionError)
        if not self._unregistered_source_image_is_owned(quarantine, journal):
            raise ValidationError("quarantined source image failed ownership verification")
        return quarantine_relative

    def _recover_unregistered_source_blob(
        self,
        journal: Mapping[str, Any],
        registry: Mapping[str, Any],
    ) -> str | None:
        """Retain a transaction-owned unregistered blob outside authority paths."""

        if journal["blob_was_preexisting"]:
            return None
        if any(
            item.get("source_sha256") == journal["source_sha256"]
            for item in registry.get("blobs", [])
            if isinstance(item, Mapping)
        ):
            return None
        blob = _contained(self.root, journal["blob_relative_path"])
        recovery_relative = (
            f"controls/recovery/source_registry/{journal['transaction_id']}/source.bin"
        )
        recovery = _contained(self.root, recovery_relative)
        if not blob.exists() and not blob.is_symlink():
            if recovery.exists() or recovery.is_symlink():
                payload = stable_plain_bytes(recovery, label="recovered source blob evidence")
                if (
                    len(payload) != journal["source_byte_size"]
                    or sha256_bytes(payload) != journal["source_sha256"]
                ):
                    raise ValidationError("recovered source blob evidence identity mismatch")
                return recovery_relative
            return None
        payload = stable_plain_bytes(blob, label="unregistered transaction-owned source blob")
        if (
            len(payload) != journal["source_byte_size"]
            or sha256_bytes(payload) != journal["source_sha256"]
        ):
            raise ValidationError("unregistered source blob ownership cannot be proven")
        if recovery.exists() or recovery.is_symlink():
            raise ValidationError("source blob recovery destination already exists")
        recovery.parent.mkdir(parents=True, exist_ok=True)
        os.rename(blob, recovery)
        _fsync_directory(blob.parent)
        _fsync_directory(recovery.parent)
        recovered = stable_plain_bytes(recovery, label="recovered source blob evidence")
        if recovered != payload:
            raise ValidationError("source blob recovery move failed verification")
        return recovery_relative

    def _validate_source_tree_coverage(self, registry: Mapping[str, Any]) -> None:
        declared = {
            _contained(self.root, binding["image_relative_path"])
            for binding in registry.get("image_bindings", [])
        }
        actual: set[Path] = set()
        studies_root = self.root / "studies"
        if studies_root.is_dir() and not studies_root.is_symlink():
            for images_root in studies_root.rglob("images"):
                if not images_root.is_dir() or images_root.is_symlink():
                    continue
                relative_parts = images_root.relative_to(self.root).parts
                if _is_excluded_operational_path(relative_parts):
                    continue
                for child in images_root.iterdir():
                    if not child.is_dir() or child.is_symlink():
                        continue
                    child_parts = child.relative_to(self.root).parts
                    if _is_excluded_operational_path(child_parts):
                        continue
                    actual.add(child)
        if actual != declared:
            raise ValidationError(
                "source registry does not exactly cover final image directories",
                details={
                    "unregistered": sorted(str(path) for path in actual - declared),
                    "missing": sorted(str(path) for path in declared - actual),
                },
            )

    def _validate_source_blob_coverage(self, registry: Mapping[str, Any]) -> None:
        declared = {
            _contained(self.root, blob["storage_relative_path"])
            for blob in registry.get("blobs", [])
        }
        actual: set[Path] = set()
        blobs_root = self.root / "sources" / "blobs"
        if blobs_root.is_dir() and not blobs_root.is_symlink():
            for path in blobs_root.rglob("source.bin"):
                relative_parts = path.relative_to(self.root).parts
                if _is_excluded_operational_path(relative_parts):
                    continue
                if path.is_file() and not path.is_symlink():
                    actual.add(path)
        if actual != declared:
            raise ValidationError(
                "source registry does not exactly cover authoritative source blobs",
                details={
                    "unregistered": sorted(str(path) for path in actual - declared),
                    "missing": sorted(str(path) for path in declared - actual),
                },
            )

    def _validate_source_registry_journals(
        self,
        registry: Mapping[str, Any],
        *,
        allow_pending: bool,
    ) -> None:
        for path in self._source_registry_journal_paths():
            journal = self._load_source_registry_journal(path)
            state = journal["state"]
            binding_present = self._source_registry_contains_journal_binding(registry, journal)
            final = _contained(self.root, journal["image_relative_path"])
            partial = _contained(self.root, journal["image_partial_relative_path"])
            blob = _contained(self.root, journal["blob_relative_path"])
            blob_partial_relative = journal["blob_partial_relative_path"]
            if blob_partial_relative is not None:
                blob_partial = _contained(self.root, blob_partial_relative)
                try:
                    blob_partial_bytes = stable_plain_bytes(
                        blob_partial,
                        label="journaled staged source blob",
                    )
                except PathSafetyError as exc:
                    raise ValidationError(
                        "source registry staged blob is absent or unsafe",
                        details={"path": str(blob_partial), "reason": str(exc)},
                    ) from exc
                if (
                    len(blob_partial_bytes) != journal["source_byte_size"]
                    or sha256_bytes(blob_partial_bytes) != journal["source_sha256"]
                ):
                    raise ValidationError("source registry staged blob identity mismatch")
            if partial.exists() or partial.is_symlink():
                try:
                    plain_directory(partial, label="retained source image partial")
                except PathSafetyError as exc:
                    raise ValidationError(
                        "retained source image partial is unsafe",
                        details={"path": str(partial), "reason": str(exc)},
                    ) from exc
            if state in SOURCE_REGISTRY_JOURNAL_PENDING_STATES and not allow_pending:
                raise ValidationError(
                    "source registry transaction requires recovery before validation",
                    details={"journal": str(path), "state": state},
                )
            if state == "BLOCKED_RECOVERY":
                raise ValidationError(
                    "source registry transaction is blocked for manual recovery",
                    details={"journal": str(path), "state": state},
                )
            if state in {"COMMITTED", "COMMITTED_RECOVERED"}:
                if not binding_present:
                    raise ValidationError("committed source journal lacks its registry binding")
                try:
                    plain_directory(final, label="committed source image root")
                except PathSafetyError as exc:
                    raise ValidationError(
                        "committed source journal image root is absent or unsafe",
                        details={"path": str(final), "reason": str(exc)},
                    ) from exc
                descriptor_bytes = stable_plain_bytes(
                    final / "image.json",
                    label="committed journal image descriptor",
                )
                if sha256_bytes(descriptor_bytes) != journal["image_descriptor_sha256"]:
                    raise ValidationError("committed source journal descriptor identity mismatch")
                blob_bytes = stable_plain_bytes(blob, label="committed journal source blob")
                if (
                    len(blob_bytes) != journal["source_byte_size"]
                    or sha256_bytes(blob_bytes) != journal["source_sha256"]
                ):
                    raise ValidationError("committed source journal blob identity mismatch")
            elif state in {"ROLLED_BACK", "ROLLED_BACK_RECOVERED"}:
                if binding_present:
                    raise ValidationError("rolled-back source journal still has an active binding")
                if final.exists() or final.is_symlink():
                    raise ValidationError("rolled-back source journal left an unregistered final image")
                quarantine_relative = journal["quarantine_relative_path"]
                if quarantine_relative is not None:
                    quarantine = _contained(self.root, quarantine_relative)
                    if not self._unregistered_source_image_is_owned(quarantine, journal):
                        raise ValidationError(
                            "source registry quarantine evidence is absent, unsafe or unowned",
                            details={"path": str(quarantine)},
                        )
                blob_recovery_relative = journal["blob_recovery_relative_path"]
                registry_has_blob = any(
                    item.get("source_sha256") == journal["source_sha256"]
                    for item in registry.get("blobs", [])
                    if isinstance(item, Mapping)
                )
                if blob_recovery_relative is not None:
                    recovered_blob = _contained(self.root, blob_recovery_relative)
                    recovered_bytes = stable_plain_bytes(
                        recovered_blob,
                        label="rolled-back source blob evidence",
                    )
                    if (
                        len(recovered_bytes) != journal["source_byte_size"]
                        or sha256_bytes(recovered_bytes) != journal["source_sha256"]
                        or registry_has_blob
                    ):
                        raise ValidationError("rolled-back source blob evidence is inconsistent")
                elif not journal["blob_was_preexisting"] and blob.exists() and not registry_has_blob:
                    raise ValidationError("rolled-back source journal left an authoritative orphan blob")

    def _reconcile_source_registry_journals(
        self,
        *,
        refresh_manifest: bool = True,
        concurrent_rollback_transaction_id: str | None = None,
        _source_lock_held: bool = False,
    ) -> None:
        if not _source_lock_held:
            with self._source_registry_writer_lock():
                self._reconcile_source_registry_journals(
                    refresh_manifest=refresh_manifest,
                    concurrent_rollback_transaction_id=concurrent_rollback_transaction_id,
                    _source_lock_held=True,
                )
            return
        reconciled_authority = False
        journal_paths = self._source_registry_journal_paths()
        for path in journal_paths:
            journal = self._load_source_registry_journal(path)
            if journal["state"] == "BLOCKED_RECOVERY":
                raise ValidationError(
                    "source registry recovery is blocked without automatic mutation",
                    details={"journal": str(path)},
                )
            if journal["state"] not in SOURCE_REGISTRY_JOURNAL_PENDING_STATES:
                continue
            try:
                registry, _, registry_sha = self._source_registry_snapshot()
            except ValidationError as exc:
                try:
                    observed_bytes = stable_plain_bytes(
                        self.source_registry_path,
                        label="blocked source registry recovery observation",
                    )
                except PathSafetyError:
                    raise exc
                registry_sha = sha256_bytes(observed_bytes)
                self._update_source_registry_journal(
                    path,
                    state="BLOCKED_RECOVERY",
                    observed_registry_sha256=registry_sha,
                    image_was_published=journal["image_was_published"],
                    registry_was_replaced=journal["registry_was_replaced"],
                    recovery_action="BLOCKED_NO_MUTATION",
                    quarantine_relative_path=journal["quarantine_relative_path"],
                    blob_recovery_relative_path=journal["blob_recovery_relative_path"],
                    updated_at=utc_now_z(),
                )
                raise ValidationError(
                    "source registry recovery is blocked by invalid registry bytes",
                    details={"journal": str(path), "reason": str(exc)},
                ) from exc
            binding_present = self._source_registry_contains_journal_binding(registry, journal)
            image_uid_claimed = any(
                isinstance(item, Mapping) and item.get("image_uid") == journal["image_uid"]
                for item in registry.get("image_bindings", [])
            )
            if registry_sha == journal["new_registry_sha256"]:
                final = _contained(self.root, journal["image_relative_path"])
                if not binding_present:
                    self._update_source_registry_journal(
                        path,
                        state="BLOCKED_RECOVERY",
                        observed_registry_sha256=registry_sha,
                        image_was_published=journal["image_was_published"],
                        registry_was_replaced=journal["registry_was_replaced"],
                        recovery_action="BLOCKED_NO_MUTATION",
                        quarantine_relative_path=journal["quarantine_relative_path"],
                        blob_recovery_relative_path=journal["blob_recovery_relative_path"],
                        updated_at=utc_now_z(),
                    )
                    raise ValidationError("source journal new registry lacks its exact binding")
                try:
                    plain_directory(final, label="recovered committed source image root")
                except PathSafetyError as exc:
                    raise ValidationError(
                        "source registry commit cannot be reconciled to its image root",
                        details={"path": str(final), "reason": str(exc)},
                    ) from exc
                self._update_source_registry_journal(
                    path,
                    state="COMMITTED_RECOVERED",
                    observed_registry_sha256=registry_sha,
                    image_was_published=True,
                    registry_was_replaced=True,
                    recovery_action="FINALIZE_COMMITTED",
                    quarantine_relative_path=None,
                    blob_recovery_relative_path=None,
                    updated_at=utc_now_z(),
                )
                reconciled_authority = True
                continue
            is_old = registry_sha == journal["old_registry_sha256"]
            is_observed_cas_mismatch = (
                concurrent_rollback_transaction_id == journal["transaction_id"]
            )
            if not is_old and not is_observed_cas_mismatch:
                self._update_source_registry_journal(
                    path,
                    state="BLOCKED_RECOVERY",
                    observed_registry_sha256=registry_sha,
                    image_was_published=journal["image_was_published"],
                    registry_was_replaced=journal["registry_was_replaced"],
                    recovery_action="BLOCKED_NO_MUTATION",
                    quarantine_relative_path=journal["quarantine_relative_path"],
                    blob_recovery_relative_path=journal["blob_recovery_relative_path"],
                    updated_at=utc_now_z(),
                )
                raise ValidationError(
                    "source registry has a third state; recovery is blocked without mutation",
                    details={"journal": str(path), "observed_registry_sha256": registry_sha},
                )
            if image_uid_claimed:
                self._update_source_registry_journal(
                    path,
                    state="BLOCKED_RECOVERY",
                    observed_registry_sha256=registry_sha,
                    image_was_published=journal["image_was_published"],
                    registry_was_replaced=journal["registry_was_replaced"],
                    recovery_action="BLOCKED_NO_MUTATION",
                    quarantine_relative_path=journal["quarantine_relative_path"],
                    blob_recovery_relative_path=journal["blob_recovery_relative_path"],
                    updated_at=utc_now_z(),
                )
                raise ValidationError(
                    "source registry claims the journal image UID with different bytes"
                )
            quarantine_relative = journal["quarantine_relative_path"]
            blob_recovery_relative = journal["blob_recovery_relative_path"]
            try:
                quarantine_relative = self._quarantine_unregistered_source_image(journal)
                blob_recovery_relative = self._recover_unregistered_source_blob(
                    journal,
                    registry,
                )
            except (OSError, PathSafetyError, TransactionError, ValidationError) as exc:
                self._update_source_registry_journal(
                    path,
                    state="BLOCKED_RECOVERY",
                    observed_registry_sha256=registry_sha,
                    image_was_published=journal["image_was_published"],
                    registry_was_replaced=journal["registry_was_replaced"],
                    recovery_action="BLOCKED_NO_MUTATION",
                    quarantine_relative_path=quarantine_relative,
                    blob_recovery_relative_path=blob_recovery_relative,
                    updated_at=utc_now_z(),
                )
                raise ValidationError(
                    "source registry rollback ownership could not be proven",
                    details={"journal": str(path), "reason": str(exc)},
                ) from exc
            image_was_published = (
                journal["image_was_published"] or quarantine_relative is not None
            )
            if journal["image_was_published"] and quarantine_relative is None:
                self._update_source_registry_journal(
                    path,
                    state="BLOCKED_RECOVERY",
                    observed_registry_sha256=registry_sha,
                    image_was_published=True,
                    registry_was_replaced=journal["registry_was_replaced"],
                    recovery_action="BLOCKED_NO_MUTATION",
                    quarantine_relative_path=None,
                    blob_recovery_relative_path=blob_recovery_relative,
                    updated_at=utc_now_z(),
                )
                raise ValidationError("published source image evidence is missing during rollback")
            self._update_source_registry_journal(
                path,
                state="ROLLED_BACK_RECOVERED",
                observed_registry_sha256=registry_sha,
                image_was_published=image_was_published,
                registry_was_replaced=journal["registry_was_replaced"],
                recovery_action=(
                    "QUARANTINE_UNREGISTERED_IMAGE"
                    if quarantine_relative is not None
                    else "FINALIZE_ROLLED_BACK"
                ),
                quarantine_relative_path=quarantine_relative,
                blob_recovery_relative_path=blob_recovery_relative,
                updated_at=utc_now_z(),
            )
            # Deterministic parent descriptors may have been published after
            # PREPARED even when the image rename did not occur.  Refreshing the
            # closed authority inventory is therefore required for every resolved
            # pending source journal, not only for a quarantined final image.
            reconciled_authority = True
        registry = self._source_registry()
        self._validate_source_registry_journals(registry, allow_pending=False)
        self._validate_source_tree_coverage(registry)
        self._validate_source_blob_coverage(registry)
        # A crash can occur after the journal reaches a terminal state but
        # before the closed storage manifest is refreshed.  The presence of any
        # source journal therefore triggers an idempotent manifest reconciliation
        # before the next mutation, even when no journal was pending on entry.
        if refresh_manifest and (reconciled_authority or journal_paths):
            self.refresh_storage_manifest(_source_recovery_checked=True)

    def _validate_source_registry(
        self,
        value: Mapping[str, Any],
        *,
        verify_blobs: bool,
        verify_descriptors: bool,
    ) -> None:
        if set(value) != {"blobs", "image_bindings", "project_uid", "schema", "updated_at"}:
            raise ValidationError("source registry top-level inventory is not closed")
        if value["schema"] != "CTL_SOURCE_REGISTRY_V1" or value["project_uid"] != self.project_uid:
            raise ValidationError("source registry project/schema mismatch")
        _require_timestamp(value["updated_at"], "source_registry.updated_at")
        blobs = value["blobs"]
        bindings = value["image_bindings"]
        if not isinstance(blobs, list) or not isinstance(bindings, list):
            raise ValidationError("source registry arrays are absent")
        if [item.get("source_sha256") for item in blobs] != sorted(item.get("source_sha256") for item in blobs):
            raise ValidationError("source blobs are not sorted")
        if [item.get("image_uid") for item in bindings] != sorted(item.get("image_uid") for item in bindings):
            raise ValidationError("image bindings are not sorted")
        blob_map: dict[str, Mapping[str, Any]] = {}
        for blob in blobs:
            if not isinstance(blob, dict) or set(blob) != {
                "byte_size", "reference_count", "source_sha256", "storage_relative_path"
            }:
                raise ValidationError("source blob record inventory is invalid")
            digest = _require_sha(blob["source_sha256"], "blob.source_sha256")
            _require_nonnegative(blob["byte_size"], "blob.byte_size")
            _require_positive(blob["reference_count"], "blob.reference_count")
            expected_relative = f"sources/blobs/{digest[:2]}/{digest}/source.bin"
            if blob["storage_relative_path"] != expected_relative or digest in blob_map:
                raise ValidationError("source blob identity/path collision")
            if verify_blobs:
                path = _contained(self.root, expected_relative)
                try:
                    payload = stable_plain_bytes(path, label="immutable source blob")
                except PathSafetyError as exc:
                    raise ValidationError(
                        "source blob is absent, linked, reparsed or hardlinked",
                        details={"path": str(path), "reason": str(exc)},
                    ) from exc
                if len(payload) != blob["byte_size"] or sha256_bytes(payload) != digest:
                    raise ValidationError("source blob bytes differ from registry")
            blob_map[digest] = blob
        image_uids: set[str] = set()
        parent_ids: set[tuple[str, str]] = set()
        counts = {digest: 0 for digest in blob_map}
        required_binding = {
            "condition_id",
            "identity_provenance_sha256",
            "image_id",
            "image_relative_path",
            "image_uid",
            "lamella_id",
            "master_pixel_hash_method",
            "master_pixel_hash_status",
            "master_pixel_sha256",
            "parent_scope_key",
            "source_file_name",
            "source_sha256",
            "specimen_id",
            "study_id",
        }
        for binding in bindings:
            if not isinstance(binding, dict) or set(binding) != required_binding:
                raise ValidationError("image binding inventory is invalid")
            study_id = _safe_component(binding["study_id"], "study_id")
            condition_id = _safe_component(binding["condition_id"], "condition_id")
            specimen_id = _safe_component(binding["specimen_id"], "specimen_id")
            lamella_id = _safe_component(binding["lamella_id"], "lamella_id")
            image_uid = _require_uuid(binding["image_uid"], "image_uid")
            image_id = _safe_component(binding["image_id"], "image_id")
            parent = _portable_relative(binding["parent_scope_key"], "parent_scope_key")
            digest = _require_sha(binding["source_sha256"], "image.source_sha256")
            _require_sha(binding["identity_provenance_sha256"], "identity_provenance_sha256")
            status = binding["master_pixel_hash_status"]
            if status not in MASTER_STATUSES:
                raise ValidationError("master pixel status is invalid")
            if status == "VERIFIED":
                _require_sha(binding["master_pixel_sha256"], "master_pixel_sha256")
            elif binding["master_pixel_sha256"] is not None:
                raise ValidationError("unverified master pixel hash must be null")
            if image_uid in image_uids or (parent, image_id) in parent_ids or digest not in blob_map:
                raise ValidationError("image UID/parent binding collision")
            expected_rel = self._image_relative(
                study_id, condition_id, specimen_id, lamella_id, image_id,
            )
            if binding["image_relative_path"] != expected_rel:
                raise ValidationError("image binding physical path mismatch")
            expected_parent = (
                f"{self.project_uid}/{study_id}/{condition_id}/{specimen_id}/{lamella_id}"
            )
            if parent != expected_parent:
                raise ValidationError("image binding parent scope is not derived exactly")
            study_uid = self._hierarchy_uuid("study", self.project_uid, study_id)
            condition_uid = self._hierarchy_uuid("condition", study_uid, condition_id)
            specimen_uid = self._hierarchy_uuid("specimen", condition_uid, specimen_id)
            lamella_uid = self._hierarchy_uuid("lamella", specimen_uid, lamella_id)
            parent_component = confirmed_image_parent_component(
                study_uid, specimen_uid, lamella_uid
            )
            expected_image_uid = derive_image_uid(
                self.project_uid, parent_component, image_id
            )
            if image_uid != expected_image_uid:
                raise ValidationError("image UID is not derived from the registered parent scope")
            if verify_descriptors:
                image_root = _contained(self.root, expected_rel)
                descriptor = _canonical_read(image_root / "image.json")
                expected_descriptor_keys = {
                    "condition_uid", "created_at", "identity_provenance",
                    "identity_provenance_sha256", "image_id", "image_uid",
                    "lamella_uid", "project_uid", "schema", "source_sha256",
                    "specimen_uid", "study_uid",
                }
                if set(descriptor) != expected_descriptor_keys:
                    raise ValidationError("image descriptor field inventory is not closed")
                _require_timestamp(descriptor.get("created_at"), "image.created_at")
                provenance = descriptor.get("identity_provenance")
                if not isinstance(provenance, dict):
                    raise ValidationError("image identity provenance is not an object")
                provenance_sha = sha256_bytes(canonical_json_bytes(provenance))
                if (
                    descriptor.get("schema") != "CTL_P2A_IMAGE_JSON_V1"
                    or descriptor.get("project_uid") != self.project_uid
                    or descriptor.get("study_uid") != study_uid
                    or descriptor.get("condition_uid") != condition_uid
                    or descriptor.get("specimen_uid") != specimen_uid
                    or descriptor.get("lamella_uid") != lamella_uid
                    or descriptor.get("image_id") != image_id
                    or descriptor.get("image_uid") != image_uid
                    or descriptor.get("source_sha256") != digest
                    or descriptor.get("identity_provenance_sha256") != provenance_sha
                    or binding["identity_provenance_sha256"] != provenance_sha
                ):
                    raise ValidationError("image descriptor/provenance/parent identity mismatch")
                hierarchy = (
                    (
                        self.root / "studies" / study_id / "study.json",
                        {
                            "project_uid": self.project_uid,
                            "schema": "CTL_P2A_STUDY_JSON_V1",
                            "study_id": study_id,
                            "study_uid": study_uid,
                        },
                    ),
                    (
                        self.root / "studies" / study_id / "conditions" / condition_id / "condition.json",
                        {
                            "study_uid": study_uid,
                            "schema": "CTL_P2A_CONDITION_JSON_V1",
                            "condition_id": condition_id,
                            "condition_uid": condition_uid,
                        },
                    ),
                    (
                        self.root / "studies" / study_id / "conditions" / condition_id
                        / "specimens" / specimen_id / "specimen.json",
                        {
                            "condition_uid": condition_uid,
                            "schema": "CTL_P2A_SPECIMEN_JSON_V1",
                            "specimen_id": specimen_id,
                            "specimen_uid": specimen_uid,
                        },
                    ),
                    (
                        self.root / "studies" / study_id / "conditions" / condition_id
                        / "specimens" / specimen_id / "lamellae" / lamella_id
                        / "lamella.json",
                        {
                            "specimen_uid": specimen_uid,
                            "schema": "CTL_P2A_LAMELLA_JSON_V1",
                            "lamella_id": lamella_id,
                            "lamella_uid": lamella_uid,
                        },
                    ),
                )
                for descriptor_path, expected_identity in hierarchy:
                    parent_descriptor = _canonical_read(descriptor_path)
                    _require_timestamp(parent_descriptor.get("created_at"), "parent.created_at")
                    observed_identity = {
                        key: item
                        for key, item in parent_descriptor.items()
                        if key != "created_at"
                    }
                    if observed_identity != expected_identity:
                        raise ValidationError(
                            "hierarchy descriptor does not match source parent identity",
                            details={"path": str(descriptor_path)},
                        )
            image_uids.add(image_uid)
            parent_ids.add((parent, image_id))
            counts[digest] += 1
        for digest, count in counts.items():
            if blob_map[digest]["reference_count"] != count:
                raise ValidationError("source blob reference_count is not derived exactly")

    def _image_relative(
        self, study_id: str, condition_id: str, specimen_id: str, lamella_id: str, image_id: str
    ) -> str:
        values = [
            _safe_component(study_id, "study_id"),
            _safe_component(condition_id, "condition_id"),
            _safe_component(specimen_id, "specimen_id"),
            _safe_component(lamella_id, "lamella_id"),
            _safe_component(image_id, "image_id"),
        ]
        return (
            f"studies/{values[0]}/conditions/{values[1]}/specimens/{values[2]}/"
            f"lamellae/{values[3]}/images/{values[4]}"
        )

    def _hierarchy_uuid(self, kind: str, parent_uid: str, identifier: str) -> str:
        return str(uuid.uuid5(CTL_UUID_NAMESPACE_V1, f"p2a-{kind}|{self.project_uid}|{parent_uid}|{identifier}"))

    def _ensure_descriptor(
        self, path: Path, *, kind: str, identifier_field: str, identifier: str,
        uid_field: str, uid_value: str, parent_field: str, parent_value: str, created_at: str,
    ) -> None:
        value = {
            "created_at": created_at,
            identifier_field: identifier,
            parent_field: parent_value,
            "schema": f"CTL_P2A_{kind.upper()}_JSON_V1",
            uid_field: uid_value,
        }
        data = canonical_json_bytes(value)
        if path.exists():
            existing = _canonical_read(path)
            # created_at is the creation time of the already-existing parent,
            # not the registration time of each later child image.
            expected_identity = {key: item for key, item in value.items() if key != "created_at"}
            observed_identity = {key: item for key, item in existing.items() if key != "created_at"}
            if observed_identity != expected_identity:
                raise ValidationError("hierarchy descriptor identity collision", details={"path": str(path)})
            _require_timestamp(existing.get("created_at"), f"{kind}.created_at")
            return
        _write_new(path, data)

    def register_source_image(
        self,
        source_bytes: bytes,
        *,
        study_id: str,
        condition_id: str,
        specimen_id: str,
        lamella_id: str,
        image_id: str,
        identity_provenance: Mapping[str, Any],
        source_file_name: str,
        master_pixel_hash_method: str,
        master_pixel_hash_status: str,
        master_pixel_sha256: str | None,
        updated_at: str | None = None,
        _fault: FaultHook | None = None,
    ) -> ImageBinding:
        with self._source_registry_writer_lock():
            return self._register_source_image_locked(
                source_bytes,
                study_id=study_id,
                condition_id=condition_id,
                specimen_id=specimen_id,
                lamella_id=lamella_id,
                image_id=image_id,
                identity_provenance=identity_provenance,
                source_file_name=source_file_name,
                master_pixel_hash_method=master_pixel_hash_method,
                master_pixel_hash_status=master_pixel_hash_status,
                master_pixel_sha256=master_pixel_sha256,
                updated_at=updated_at,
                _fault=_fault,
            )

    def _register_source_image_locked(
        self,
        source_bytes: bytes,
        *,
        study_id: str,
        condition_id: str,
        specimen_id: str,
        lamella_id: str,
        image_id: str,
        identity_provenance: Mapping[str, Any],
        source_file_name: str,
        master_pixel_hash_method: str,
        master_pixel_hash_status: str,
        master_pixel_sha256: str | None,
        updated_at: str | None = None,
        _fault: FaultHook | None = None,
    ) -> ImageBinding:
        if not isinstance(source_bytes, bytes):
            raise ValidationError("source_bytes must be immutable bytes")
        timestamp = _require_timestamp(updated_at or utc_now_z(), "updated_at")
        ids = tuple(
            _safe_component(value, field)
            for value, field in (
                (study_id, "study_id"), (condition_id, "condition_id"),
                (specimen_id, "specimen_id"), (lamella_id, "lamella_id"), (image_id, "image_id")
            )
        )
        study_id, condition_id, specimen_id, lamella_id, image_id = ids
        if not source_file_name or Path(source_file_name).name != source_file_name or any(
            char in source_file_name for char in ("/", "\\", "\x00", "\r", "\n")
        ):
            raise ValidationError("source_file_name must be a portable basename")
        if not isinstance(identity_provenance, Mapping) or not identity_provenance:
            raise ValidationError("identity provenance must be an explicit non-empty object")
        provenance_sha = sha256_bytes(canonical_json_bytes(dict(identity_provenance)))
        if master_pixel_hash_status not in MASTER_STATUSES:
            raise ValidationError("master pixel hash status is invalid")
        if master_pixel_hash_status == "VERIFIED":
            master_pixel_sha256 = _require_sha(master_pixel_sha256, "master_pixel_sha256")
        elif master_pixel_sha256 is not None:
            raise ValidationError("unverified master pixel hash must be null")
        _safe_component(master_pixel_hash_method, "master_pixel_hash_method")

        # No source, hierarchy, image or registry mutation may begin while an
        # earlier project-scoped source transaction is unresolved.
        self._reconcile_source_registry_journals(_source_lock_held=True)
        digest = sha256_bytes(source_bytes)
        registry, _, registry_snapshot_hash = self._source_registry_snapshot()
        parent_scope = f"{self.project_uid}/{study_id}/{condition_id}/{specimen_id}/{lamella_id}"
        for existing in registry["image_bindings"]:
            if existing["parent_scope_key"] == parent_scope and existing["image_id"] == image_id:
                exact = (
                    existing["identity_provenance_sha256"] == provenance_sha
                    and existing["source_sha256"] == digest
                    and existing["master_pixel_hash_method"] == master_pixel_hash_method
                    and existing["master_pixel_hash_status"] == master_pixel_hash_status
                    and existing["master_pixel_sha256"] == master_pixel_sha256
                    and existing["source_file_name"] == source_file_name
                )
                if not exact:
                    raise ValidationError(
                        "alias reconciliation requires exact parent, image_id and provenance",
                        details={"image_uid": existing["image_uid"]},
                    )
                return ImageBinding(
                    self.project_uid,
                    existing["image_uid"],
                    image_id,
                    parent_scope,
                    digest,
                    _contained(self.root, existing["image_relative_path"]),
                    True,
                )

        study_uid = self._hierarchy_uuid("study", self.project_uid, study_id)
        condition_uid = self._hierarchy_uuid("condition", study_uid, condition_id)
        specimen_uid = self._hierarchy_uuid("specimen", condition_uid, specimen_id)
        lamella_uid = self._hierarchy_uuid("lamella", specimen_uid, lamella_id)
        parent_component = confirmed_image_parent_component(study_uid, specimen_uid, lamella_uid)
        image_uid = derive_image_uid(self.project_uid, parent_component, image_id)
        image_relative = self._image_relative(study_id, condition_id, specimen_id, lamella_id, image_id)
        image_root = _contained(self.root, image_relative)
        transaction_nonce = uuid.uuid4().hex
        transaction_id = f"source_registry_{transaction_nonce}"
        blob_relative = f"sources/blobs/{digest[:2]}/{digest}/source.bin"
        blob_path = _contained(self.root, blob_relative)
        registered_blob = next(
            (
                item
                for item in registry["blobs"]
                if item["source_sha256"] == digest
            ),
            None,
        )
        blob_was_preexisting = registered_blob is not None
        blob_partial: Path | None = None
        if blob_was_preexisting:
            existing_blob = stable_plain_bytes(blob_path, label="existing immutable source blob")
            if existing_blob != source_bytes:
                raise ValidationError("existing immutable source blob collision")
        else:
            if blob_path.exists() or blob_path.is_symlink():
                raise ValidationError("unregistered canonical source blob blocks registration")
            blob_partial = blob_path.parent / f".source.bin.partial.{transaction_nonce}"
            _write_new(blob_partial, source_bytes)
            staged_blob = stable_plain_bytes(blob_partial, label="staged immutable source blob")
            if staged_blob != source_bytes:
                raise TransactionError("staged source blob failed exact verification")

        study_root = self.root / "studies" / study_id
        condition_root = study_root / "conditions" / condition_id
        specimen_root = condition_root / "specimens" / specimen_id
        lamella_root = specimen_root / "lamellae" / lamella_id
        image_root.parent.mkdir(parents=True, exist_ok=True)
        image_descriptor = {
            "condition_uid": condition_uid,
            "created_at": timestamp,
            "identity_provenance": dict(identity_provenance),
            "identity_provenance_sha256": provenance_sha,
            "image_id": image_id,
            "image_uid": image_uid,
            "lamella_uid": lamella_uid,
            "project_uid": self.project_uid,
            "schema": "CTL_P2A_IMAGE_JSON_V1",
            "source_sha256": digest,
            "specimen_uid": specimen_uid,
            "study_uid": study_uid,
        }
        image_partial = image_root.parent / f".{image_id}.partial.{transaction_nonce}"
        if image_root.exists() or image_root.is_symlink():
            raise ValidationError("image physical identity already exists without an exact alias")
        image_partial.mkdir()
        image_descriptor_bytes = canonical_json_bytes(image_descriptor)
        _write_new(image_partial / "image.json", image_descriptor_bytes)
        sessions_root = image_partial / "sessions"
        sessions_root.mkdir()
        _write_new(sessions_root / "session_registry.tsv", SESSION_REGISTRY_HEADER.encode("utf-8"))

        blobs = {item["source_sha256"]: dict(item) for item in registry["blobs"]}
        blobs.setdefault(
            digest,
            {
                "byte_size": len(source_bytes),
                "reference_count": 0,
                "source_sha256": digest,
                "storage_relative_path": blob_relative,
            },
        )
        binding = {
            "condition_id": condition_id,
            "identity_provenance_sha256": provenance_sha,
            "image_id": image_id,
            "image_relative_path": image_relative,
            "image_uid": image_uid,
            "lamella_id": lamella_id,
            "master_pixel_hash_method": master_pixel_hash_method,
            "master_pixel_hash_status": master_pixel_hash_status,
            "master_pixel_sha256": master_pixel_sha256,
            "parent_scope_key": parent_scope,
            "source_file_name": source_file_name,
            "source_sha256": digest,
            "specimen_id": specimen_id,
            "study_id": study_id,
        }
        registry["image_bindings"].append(binding)
        registry["image_bindings"].sort(key=lambda item: item["image_uid"])
        for item in blobs.values():
            item["reference_count"] = sum(
                candidate["source_sha256"] == item["source_sha256"]
                for candidate in registry["image_bindings"]
            )
        registry["blobs"] = [blobs[key] for key in sorted(blobs)]
        registry["updated_at"] = timestamp
        self._validate_source_registry(
            registry,
            verify_blobs=blob_was_preexisting,
            verify_descriptors=False,
        )
        registry_bytes = canonical_json_bytes(registry)
        journal_root = self._source_registry_journal_root
        controls_root = plain_directory(
            self.root / "controls",
            label="source registry controls root",
        )
        if not journal_root.exists() and not journal_root.is_symlink():
            journal_root.mkdir(exist_ok=True)
            _fsync_directory(controls_root)
        try:
            journal_root = plain_directory(
                journal_root,
                label="source registry journal root",
            )
        except PathSafetyError as exc:
            raise ValidationError(
                "source registry journal root is unsafe",
                details={"path": str(journal_root), "reason": str(exc)},
            ) from exc
        journal_path = journal_root / f"JOURNAL_{transaction_id}.json"
        journal = {
            "blob_partial_relative_path": (
                None if blob_partial is None else blob_partial.relative_to(self.root).as_posix()
            ),
            "blob_recovery_relative_path": None,
            "blob_relative_path": blob_relative,
            "blob_was_preexisting": blob_was_preexisting,
            "created_at": timestamp,
            "image_binding_sha256": sha256_bytes(canonical_json_bytes(binding)),
            "image_descriptor_sha256": sha256_bytes(image_descriptor_bytes),
            "image_id": image_id,
            "image_partial_relative_path": image_partial.relative_to(self.root).as_posix(),
            "image_relative_path": image_relative,
            "image_uid": image_uid,
            "image_was_published": False,
            "new_registry_sha256": sha256_bytes(registry_bytes),
            "observed_registry_sha256": registry_snapshot_hash,
            "old_registry_sha256": registry_snapshot_hash,
            "parent_scope_key": parent_scope,
            "project_uid": self.project_uid,
            "quarantine_relative_path": None,
            "recovery_action": "RECOVERY_REQUIRED",
            "registry_was_replaced": False,
            "schema": SOURCE_REGISTRY_JOURNAL_SCHEMA,
            "source_byte_size": len(source_bytes),
            "source_sha256": digest,
            "state": "PREPARED",
            "transaction_id": transaction_id,
            "updated_at": timestamp,
        }
        _write_new(journal_path, canonical_json_bytes(journal))
        try:
            _call_fault(
                _fault,
                "SOURCE_REGISTRY_JOURNAL_PREPARED",
                {"image_uid": image_uid, "transaction_id": transaction_id},
            )
        except BaseException:
            self._update_source_registry_journal(
                journal_path,
                state="RECOVERY_REQUIRED",
                observed_registry_sha256=registry_snapshot_hash,
                image_was_published=False,
                registry_was_replaced=False,
                recovery_action="RECOVERY_REQUIRED",
                quarantine_relative_path=None,
                blob_recovery_relative_path=None,
                updated_at=timestamp,
            )
            raise
        try:
            if not blob_was_preexisting:
                _write_new(blob_path, source_bytes)
                published_blob = stable_plain_bytes(
                    blob_path,
                    label="published immutable source blob",
                )
                if published_blob != source_bytes:
                    raise TransactionError("published source blob failed exact verification")
            self._ensure_descriptor(
                study_root / "study.json", kind="study", identifier_field="study_id", identifier=study_id,
                uid_field="study_uid", uid_value=study_uid, parent_field="project_uid", parent_value=self.project_uid,
                created_at=timestamp,
            )
            self._ensure_descriptor(
                condition_root / "condition.json", kind="condition", identifier_field="condition_id", identifier=condition_id,
                uid_field="condition_uid", uid_value=condition_uid, parent_field="study_uid", parent_value=study_uid,
                created_at=timestamp,
            )
            self._ensure_descriptor(
                specimen_root / "specimen.json", kind="specimen", identifier_field="specimen_id", identifier=specimen_id,
                uid_field="specimen_uid", uid_value=specimen_uid, parent_field="condition_uid", parent_value=condition_uid,
                created_at=timestamp,
            )
            self._ensure_descriptor(
                lamella_root / "lamella.json", kind="lamella", identifier_field="lamella_id", identifier=lamella_id,
                uid_field="lamella_uid", uid_value=lamella_uid, parent_field="specimen_uid", parent_value=specimen_uid,
                created_at=timestamp,
            )
            rename_directory_no_replace(image_partial, image_root, error_type=TransactionError)
            self._update_source_registry_journal(
                journal_path,
                state="IMAGE_PUBLISHED_PENDING_REGISTRY",
                observed_registry_sha256=registry_snapshot_hash,
                image_was_published=True,
                registry_was_replaced=False,
                recovery_action="RECOVERY_REQUIRED",
                quarantine_relative_path=None,
                blob_recovery_relative_path=None,
                updated_at=timestamp,
            )
            _call_fault(
                _fault,
                "SOURCE_IMAGE_PUBLISHED",
                {"image_uid": image_uid, "transaction_id": transaction_id},
            )
            self._replace_source_registry_locked(
                registry_bytes,
                expected_sha256=registry_snapshot_hash,
                token=transaction_id,
            )
            _call_fault(
                _fault,
                "SOURCE_REGISTRY_CAS_PUBLISHED",
                {
                    "image_uid": image_uid,
                    "new_registry_sha256": sha256_bytes(registry_bytes),
                    "transaction_id": transaction_id,
                },
            )
            self._update_source_registry_journal(
                journal_path,
                state="REGISTRY_PUBLISHED_PENDING_COMMIT",
                observed_registry_sha256=sha256_bytes(registry_bytes),
                image_was_published=True,
                registry_was_replaced=True,
                recovery_action="RECOVERY_REQUIRED",
                quarantine_relative_path=None,
                blob_recovery_relative_path=None,
                updated_at=timestamp,
            )
        except BaseException as exc:
            # Resolve only against the journal's old/new registry hashes and its
            # exact binding.  A third-party registry value is never overwritten.
            cas_mismatch = (
                isinstance(exc, TransactionError)
                and exc.details.get("source_registry_cas_mismatch") is True
            )
            self._reconcile_source_registry_journals(
                concurrent_rollback_transaction_id=(transaction_id if cas_mismatch else None),
                _source_lock_held=True,
            )
            raise
        self._source_registry()
        self._update_source_registry_journal(
            journal_path,
            state="COMMITTED",
            observed_registry_sha256=sha256_bytes(registry_bytes),
            image_was_published=True,
            registry_was_replaced=True,
            recovery_action="NONE",
            quarantine_relative_path=None,
            blob_recovery_relative_path=None,
            updated_at=timestamp,
        )
        self.refresh_storage_manifest(_source_recovery_checked=True)
        _call_fault(
            _fault,
            "SOURCE_REGISTRY_JOURNAL_COMMITTED",
            {"image_uid": image_uid, "transaction_id": transaction_id},
        )
        return ImageBinding(self.project_uid, image_uid, image_id, parent_scope, digest, image_root, False)

    def _binding(self, image_uid: str) -> dict[str, Any]:
        checked = _require_uuid(image_uid, "image_uid")
        matches = [item for item in self._source_registry()["image_bindings"] if item["image_uid"] == checked]
        if len(matches) != 1:
            raise ValidationError("explicit image_uid does not identify exactly one image")
        return matches[0]

    def _image_root(self, image_uid: str) -> Path:
        return _contained(self.root, self._binding(image_uid)["image_relative_path"])

    def _session_root(self, image_uid: str, session_id: str) -> Path:
        checked = _safe_component(session_id, "analysis_session_id")
        matches = [
            row for row in self._read_registry(image_uid)
            if row["analysis_session_id"] == checked
        ]
        if len(matches) > 1:
            raise ValidationError("analysis_session_id is not unique under image")
        image_root = self._image_root(image_uid)
        if matches:
            return _contained(image_root, matches[0]["relative_path"])
        return _choose_new_session_directory(image_root / "sessions", checked)

    def _registry_path(self, image_uid: str) -> Path:
        return self._image_root(image_uid) / "sessions" / "session_registry.tsv"

    def _current_session_path(self, image_uid: str) -> Path:
        return self._image_root(image_uid) / "sessions" / "current_session.tsv"

    def _read_registry(self, image_uid: str) -> list[dict[str, Any]]:
        rows = _parse_tsv(
            stable_plain_bytes(
                self._registry_path(image_uid), label="session registry authority"
            ),
            SESSION_REGISTRY_FIELDS,
            allow_header_only=True,
        )
        converted: list[dict[str, Any]] = []
        for row in rows:
            value: dict[str, Any] = dict(row)
            for field in (
                "registry_version", "generation", "object_count", "revision_count", "run_count",
                "logical_bytes", "physical_bytes",
            ):
                try:
                    value[field] = int(value[field])
                except ValueError as exc:
                    raise ValidationError("registry integer is invalid", details={"field": field}) from exc
            value["compressed_bytes"] = None if value["compressed_bytes"] == "" else int(value["compressed_bytes"])
            value["restricted_evidence_ref_sha256"] = (
                None if value["restricted_evidence_ref_sha256"] == "" else value["restricted_evidence_ref_sha256"]
            )
            converted.append(value)
        self._validate_registry_rows(image_uid, converted)
        return converted

    def _validate_registry_rows(self, image_uid: str, rows: Sequence[Mapping[str, Any]]) -> None:
        if [row["analysis_session_uid"] for row in rows] != sorted(row["analysis_session_uid"] for row in rows):
            raise ValidationError("session registry is not sorted by session UID")
        uids: set[str] = set()
        ids: set[str] = set()
        paths: set[str] = set()
        current = 0
        canonical = 0
        generation_values: set[int] = set()
        for row in rows:
            if row["registry_version"] != 1 or row["project_uid"] != self.project_uid or row["image_uid"] != image_uid:
                raise ValidationError("session registry scope mismatch")
            uid = _require_uuid(row["analysis_session_uid"], "analysis_session_uid")
            sid = _safe_component(row["analysis_session_id"], "analysis_session_id")
            relative = _portable_relative(row["relative_path"])
            relative_parts = PurePosixPath(relative).parts
            if (
                len(relative_parts) != 2
                or relative_parts[0] != "sessions"
                or not _session_directory_matches_id(relative_parts[1], sid)
            ):
                raise ValidationError("session registry relative path does not bind its ID")
            _require_sha(row["session_metadata_sha256"], "session_metadata_sha256")
            if row["origin_type"] not in ORIGIN_TYPES or row["lifecycle"] not in LIFECYCLES:
                raise ValidationError("session registry origin/lifecycle is invalid")
            if row["canonical_role"] not in CANONICAL_ROLES:
                raise ValidationError("session registry canonical role is invalid")
            if row["operator_status"] not in {"RESTRICTED_REFERENCE", "UNKNOWN"}:
                raise ValidationError("session registry operator status is invalid")
            if row["operator_status"] == "RESTRICTED_REFERENCE":
                _require_sha(row["restricted_evidence_ref_sha256"], "restricted_evidence_ref_sha256")
            elif row["restricted_evidence_ref_sha256"] is not None:
                raise ValidationError("unknown operator must not carry restricted reference")
            _require_timestamp(row["created_at"], "created_at")
            _require_timestamp(row["updated_at"], "updated_at")
            generation_values.add(_require_positive(row["generation"], "generation"))
            for field in ("object_count", "revision_count", "run_count", "logical_bytes", "physical_bytes"):
                _require_nonnegative(row[field], field)
            if row["compressed_bytes_status"] not in {"KNOWN", "NOT_APPLICABLE", "UNKNOWN"}:
                raise ValidationError("compressed bytes status is invalid")
            if row["compressed_bytes_status"] == "KNOWN":
                _require_nonnegative(row["compressed_bytes"], "compressed_bytes")
            elif row["compressed_bytes"] is not None:
                raise ValidationError("unknown compressed bytes must be empty")
            if row["integrity_status"] not in {"VERIFIED", "NOT_VERIFIED", "QUARANTINED", "BLOCKED_REVIEW"}:
                raise ValidationError("integrity status is invalid")
            if uid in uids or sid in ids or relative in paths:
                raise ValidationError("session registry primary/unique key collision")
            uids.add(uid); ids.add(sid); paths.add(relative)
            current += row["lifecycle"] == "CURRENT"
            canonical += row["canonical_role"] == "CANONICAL"
        if current > 1 or canonical > 1 or len(generation_values) > 1:
            raise ValidationError("session registry current/canonical/generation invariant failed")

    def _metadata(self, session_root: Path) -> dict[str, Any]:
        value = _canonical_read(session_root / "session_metadata.json")
        self._validate_metadata(value, session_root)
        return value

    def _validate_metadata(
        self,
        value: Mapping[str, Any],
        session_root: Path,
        *,
        expected_working_bytes: bytes | None = None,
    ) -> None:
        if set(value) != SESSION_METADATA_FIELDS or value["schema"] != "CTL_SESSION_METADATA_JSON_V1":
            raise ValidationError("session metadata closed field inventory mismatch")
        if value["project_uid"] != self.project_uid:
            raise ValidationError("session metadata project mismatch")
        sid = _safe_component(value["analysis_session_id"], "analysis_session_id")
        if not _session_directory_matches_id(session_root.name, sid):
            raise ValidationError("session metadata ID/path mismatch")
        _require_uuid(value["analysis_session_uid"], "analysis_session_uid")
        _require_uuid(value["image_uid"], "image_uid")
        _safe_component(value["image_id"], "image_id")
        if value["canonical_role"] not in CANONICAL_ROLES or value["lifecycle"] not in LIFECYCLES:
            raise ValidationError("session metadata role/lifecycle is invalid")
        if value["origin_type"] not in ORIGIN_TYPES:
            raise ValidationError("session metadata origin is outside P2A")
        status = value["clone_provenance_status"]
        if value["origin_type"] == "CLONE_REVISION":
            if status != "VERIFIED":
                raise ValidationError("clone session provenance is not VERIFIED")
            expected_clone_sha = _require_sha(
                value["clone_provenance_sha256"], "clone_provenance_sha256"
            )
            clone_path = session_root / "clone_provenance.json"
            if not clone_path.is_file() or clone_path.is_symlink() or sha256_file(clone_path) != expected_clone_sha:
                raise ValidationError("clone provenance bytes do not match session metadata")
            clone_provenance = _canonical_read(clone_path)
            destination = clone_provenance.get("destination")
            source_context = clone_provenance.get("source")
            if (
                clone_provenance.get("schema")
                not in {"CTL_SESSION_CLONE_PROVENANCE_V2", CLONE_PROVENANCE_V3_SCHEMA}
                or not isinstance(destination, Mapping)
                or not isinstance(source_context, Mapping)
                or "candidate_uuid" in destination
                or destination.get("session_id") != sid
                or destination.get("session_uid") != value["analysis_session_uid"]
            ):
                raise ValidationError("clone provenance destination/session binding is invalid")
            source_session_id = _safe_component(source_context.get("session_id"), "source.session_id")
            source_revision_id = _safe_component(source_context.get("revision_id"), "source.revision_id")
            source_session_root = self._session_root(value["image_uid"], source_session_id)
            if not source_session_root.is_dir() or source_session_root.is_symlink():
                raise ValidationError("clone provenance source session is absent or unsafe")
            source_record = SessionRecord(
                self.project_uid,
                value["image_uid"],
                _require_uuid(source_context.get("session_uid"), "source.session_uid"),
                source_session_id,
                source_session_root,
                0,
            )
            source_manifest = self._verify_revision(
                source_record, source_session_root / "revisions" / f"REV_{source_revision_id}"
            )
            destination_revision_id = _safe_component(
                destination.get("genesis_revision_id"), "destination.genesis_revision_id"
            )
            destination_record = SessionRecord(
                self.project_uid,
                value["image_uid"],
                value["analysis_session_uid"],
                sid,
                session_root,
                0,
            )
            destination_manifest = self._verify_revision(
                destination_record,
                session_root / "revisions" / f"REV_{destination_revision_id}",
            )
            _validate_clone_provenance(
                clone_provenance, source_manifest, destination_manifest
            )
        elif status != "NOT_APPLICABLE" or value["clone_provenance_sha256"] is not None:
            raise ValidationError("non-clone session has clone provenance")
        _require_timestamp(value["created_at"], "created_at")
        _require_timestamp(value["updated_at"], "updated_at")
        _require_positive(value["generation"], "generation")
        _require_sha(value["source_sha256"], "source_sha256")
        _safe_component(value["working_state_id"], "working_state_id")
        _require_sha(value["working_state_sha256"], "working_state_sha256")
        if value["master_pixel_hash_status"] not in MASTER_STATUSES:
            raise ValidationError("session metadata master status is invalid")
        if value["master_pixel_hash_status"] == "VERIFIED":
            _require_sha(value["master_pixel_sha256"], "master_pixel_sha256")
        elif value["master_pixel_sha256"] is not None:
            raise ValidationError("session metadata unverified master hash must be null")
        if value["restricted_evidence_status"] not in {"VERIFIED_REFERENCE", "UNKNOWN", "NOT_APPLICABLE"}:
            raise ValidationError("restricted evidence status is invalid")
        if value["restricted_evidence_status"] == "VERIFIED_REFERENCE":
            _require_sha(value["restricted_evidence_ref_sha256"], "restricted_evidence_ref_sha256")
        elif value["restricted_evidence_ref_sha256"] is not None:
            raise ValidationError("restricted reference must be null unless verified")
        working_path = session_root / "working" / "working_state.json"
        observed_working_sha = (
            sha256_bytes(expected_working_bytes)
            if expected_working_bytes is not None
            else (sha256_file(working_path) if working_path.is_file() else "NOT_APPLICABLE")
        )
        if observed_working_sha != value["working_state_sha256"]:
            raise ValidationError("session working state hash mismatch")

    def _session_stats(
        self,
        session_root: Path,
        *,
        byte_overrides: Mapping[Path, bytes] | None = None,
    ) -> dict[str, int]:
        """Derive registry counters from published, non-operational authority.

        Journals, recovery material, autosaves and every path with a partial
        component are intentionally excluded.  Besides making the counters
        reproducible, this avoids the circular condition in which writing the
        registry journal would itself invalidate the byte count being
        committed.  ``byte_overrides`` lets a multi-file transaction calculate
        its future row before its first mutation.
        """

        overrides = dict(byte_overrides or {})
        revisions = [
            path
            for path in (session_root / "revisions").iterdir()
            if path.is_dir() and not path.is_symlink() and ".partial." not in path.name
        ]
        runs = [
            path
            for path in (session_root / "runs").iterdir()
            if path.is_dir() and not path.is_symlink() and ".partial." not in path.name
        ]
        working_path = session_root / "working" / "working_state.json"
        working_bytes = overrides.get(working_path)
        working = (
            loads_canonical_json(working_bytes)
            if working_bytes is not None
            else _canonical_read(working_path)
        )
        objects = working.get("objects")
        if not isinstance(objects, list):
            raise ValidationError("working state object inventory is invalid")
        object_count = len(objects)
        logical = 0
        for path in session_root.rglob("*"):
            if not path.is_file():
                continue
            relative_parts = path.relative_to(session_root).parts
            if (
                any(".partial." in part for part in relative_parts)
                or any(part in {"autosave", "journals", "recovery"} for part in relative_parts)
            ):
                continue
            logical += len(overrides[path]) if path in overrides else path.stat().st_size
        return {
            "object_count": object_count,
            "revision_count": len(revisions),
            "run_count": len(runs),
            "logical_bytes": logical,
            "physical_bytes": logical,
        }

    def _make_registry_row(
        self, binding: Mapping[str, Any], metadata: Mapping[str, Any], session_root: Path,
        *, generation: int, lifecycle: str, stats: Mapping[str, int] | None = None,
    ) -> dict[str, Any]:
        measured = dict(stats) if stats is not None else self._session_stats(session_root)
        return {
            "registry_version": 1,
            "project_uid": self.project_uid,
            "image_uid": binding["image_uid"],
            "analysis_session_uid": metadata["analysis_session_uid"],
            "analysis_session_id": metadata["analysis_session_id"],
            "relative_path": f"sessions/{session_root.name}",
            "session_metadata_sha256": sha256_file(session_root / "session_metadata.json"),
            "origin_type": metadata["origin_type"],
            "lifecycle": lifecycle,
            "canonical_role": metadata["canonical_role"],
            "operator_status": "UNKNOWN",
            "restricted_evidence_ref_sha256": None,
            "created_at": metadata["created_at"],
            "updated_at": metadata["updated_at"],
            "generation": generation,
            **measured,
            "compressed_bytes_status": "NOT_APPLICABLE",
            "compressed_bytes": None,
            "integrity_status": "VERIFIED",
        }

    def _plan_session_registry_refresh(
        self,
        image_uid: str,
        updated_at: str,
        *,
        metadata_overrides: Mapping[Path, bytes] | None = None,
        byte_overrides: Mapping[Path, bytes] | None = None,
    ) -> tuple[bytes, bytes, int, str, bytes, bytes]:
        """Build future session registry/current pointer bytes without writes."""

        current, old_generation, old_registry_hash = self._selection_snapshot(image_uid)
        if current is None:
            raise TransactionError("cannot refresh registry without explicit current session")
        binding = self._binding(image_uid)
        rows = self._read_registry(image_uid)
        generation = old_generation + 1
        metadata_map = dict(metadata_overrides or {})
        size_map = dict(byte_overrides or {})
        new_rows: list[dict[str, Any]] = []
        for row in rows:
            session_root = _contained(self._image_root(image_uid), row["relative_path"])
            metadata_path = session_root / "session_metadata.json"
            metadata_bytes = metadata_map.get(metadata_path)
            metadata = (
                loads_canonical_json(metadata_bytes)
                if metadata_bytes is not None
                else self._metadata(session_root)
            )
            self._validate_metadata(
                metadata,
                session_root,
                expected_working_bytes=size_map.get(
                    session_root / "working" / "working_state.json"
                ),
            )
            stats = self._session_stats(session_root, byte_overrides=size_map)
            new_row = self._make_registry_row(
                binding,
                metadata,
                session_root,
                generation=generation,
                lifecycle=row["lifecycle"],
                stats=stats,
            )
            if metadata_bytes is not None:
                new_row["session_metadata_sha256"] = sha256_bytes(metadata_bytes)
            new_rows.append(new_row)
        new_rows.sort(key=lambda row: row["analysis_session_uid"])
        self._validate_registry_rows(image_uid, new_rows)
        registry_bytes = _tsv_bytes(SESSION_REGISTRY_FIELDS, new_rows)
        current_row = next(
            row
            for row in new_rows
            if row["analysis_session_uid"] == current["analysis_session_uid"]
        )
        pointer = dict(current)
        pointer["pointer_version"] = 1
        pointer["generation"] = generation
        pointer["session_metadata_sha256"] = current_row["session_metadata_sha256"]
        pointer["session_registry_sha256"] = sha256_bytes(registry_bytes)
        pointer["updated_at"] = updated_at
        pointer_bytes = _tsv_bytes(CURRENT_SESSION_FIELDS, [pointer])
        registry_path = self._registry_path(image_uid)
        pointer_path = self._current_session_path(image_uid)
        old_registry = stable_plain_bytes(registry_path, label="session registry snapshot")
        old_pointer = stable_plain_bytes(pointer_path, label="current session snapshot")
        if sha256_bytes(old_registry) != old_registry_hash:
            raise StaleContextError("session registry changed during refresh planning")
        return (
            registry_bytes,
            pointer_bytes,
            generation,
            old_registry_hash,
            old_registry,
            old_pointer,
        )

    def _read_current_session(self, image_uid: str) -> dict[str, Any] | None:
        path = self._current_session_path(image_uid)
        if not path.exists():
            return None
        rows = _parse_tsv(
            stable_plain_bytes(path, label="current session pointer"),
            CURRENT_SESSION_FIELDS,
            allow_header_only=False,
        )
        row: dict[str, Any] = dict(rows[0])
        row["pointer_version"] = int(row["pointer_version"])
        row["generation"] = int(row["generation"])
        return row

    def session_by_uid(self, image_uid: str, session_uid: str) -> SessionRecord:
        checked = _require_uuid(session_uid, "analysis_session_uid")
        rows = [row for row in self._read_registry(image_uid) if row["analysis_session_uid"] == checked]
        if len(rows) != 1:
            raise ValidationError("explicit session UID does not identify exactly one session")
        row = rows[0]
        return SessionRecord(
            self.project_uid, image_uid, checked, row["analysis_session_id"],
            _contained(self._image_root(image_uid), row["relative_path"]), row["generation"],
        )

    def session_by_id(self, image_uid: str, session_id: str) -> SessionRecord:
        checked = _safe_component(session_id, "analysis_session_id")
        rows = [row for row in self._read_registry(image_uid) if row["analysis_session_id"] == checked]
        if len(rows) != 1:
            raise ValidationError("explicit session ID does not identify exactly one session")
        return self.session_by_uid(image_uid, rows[0]["analysis_session_uid"])

    def _identity_uuid_inventory(self) -> set[str]:
        """Return the UUID identity domain of all published P2A authority.

        The inventory deliberately ignores every retained partial.  It is used
        only as a collision guard for identities that the current operation is
        required to create afresh; it does not infer selection or authority.
        """

        identities: set[str] = {self.project_uid}
        registry = self._source_registry()
        for binding in registry["image_bindings"]:
            identities.add(_require_uuid(binding["image_uid"], "image_uid"))
            image_root = _contained(self.root, binding["image_relative_path"])
            image_descriptor = _canonical_read(image_root / "image.json")
            for field in ("study_uid", "condition_uid", "specimen_uid", "lamella_uid", "image_uid"):
                value = image_descriptor.get(field)
                if value is not None:
                    identities.add(_require_uuid(value, field))
            for row in self._read_registry(binding["image_uid"]):
                identities.add(
                    _require_uuid(row["analysis_session_uid"], "analysis_session_uid")
                )
                session_root = _contained(image_root, row["relative_path"])
                for revision_root in (session_root / "revisions").iterdir():
                    if (
                        not revision_root.is_dir()
                        or revision_root.is_symlink()
                        or ".partial." in revision_root.name
                    ):
                        continue
                    manifest = _canonical_read(revision_root / "revision_manifest.json")
                    identities.add(_require_uuid(manifest.get("revision_uid"), "revision_uid"))
                    for item in manifest.get("objects", []):
                        identities.add(_require_uuid(item.get("object_uuid"), "object_uuid"))
                    for item in manifest.get("candidates", []):
                        identities.add(
                            _require_uuid(item.get("candidate_uuid"), "candidate_uuid")
                        )
                    for item in manifest.get("geometries", []):
                        identities.add(
                            _require_uuid(item.get("geometry_uid"), "geometry_uid", version=4)
                        )
                for run_root in (session_root / "runs").iterdir():
                    if (
                        not run_root.is_dir()
                        or run_root.is_symlink()
                        or ".partial." in run_root.name
                        or ".quarantine" in run_root.name
                    ):
                        continue
                    manifest = _canonical_read(run_root / "run_manifest.json")
                    identities.add(_require_uuid(manifest.get("run_uid"), "run_uid"))
        return identities

    def _working_state(
        self, *, session_uid: str, working_state_id: str, source_revision_sha256: str | None,
        objects: Sequence[Mapping[str, Any]], candidates: Sequence[Mapping[str, Any]], created_at: str,
        geometries: Sequence[Mapping[str, Any]] | None = None,
    ) -> dict[str, Any]:
        working = {
            "analysis_session_uid": session_uid,
            "base_revision_manifest_sha256": source_revision_sha256,
            "candidates": [dict(item) for item in candidates],
            "created_at": created_at,
            "generation": 1,
            "objects": [dict(item) for item in objects],
            "schema": "CTL_P2A_WORKING_STATE_V1",
            "working_state_id": working_state_id,
        }
        if geometries is not None:
            working["geometries"] = self._normalize_revision_geometries(geometries)
            working["schema"] = "CTL_P2A_WORKING_STATE_V2"
        return working

    def _new_session_partial(
        self,
        binding: Mapping[str, Any],
        *,
        session_id: str,
        session_uid: str,
        origin_type: str,
        canonical_role: str,
        created_at: str,
        clone_provenance: Mapping[str, Any] | None,
        working_objects: Sequence[Mapping[str, Any]],
        working_candidates: Sequence[Mapping[str, Any]],
        base_revision_sha256: str | None,
        working_geometries: Sequence[Mapping[str, Any]] | None = None,
    ) -> tuple[Path, dict[str, Any]]:
        image_root = _contained(self.root, binding["image_relative_path"])
        sessions_root = image_root / "sessions"
        final = _choose_new_session_directory(sessions_root, session_id)
        partial = sessions_root / f"{final.name}.partial.{uuid.uuid4().hex}"
        partial.mkdir()
        for name in ("working", "autosave", "journals", "recovery", "revisions", "runs"):
            (partial / name).mkdir()
        working_state_id = "WORKING_000001"
        working = self._working_state(
            session_uid=session_uid,
            working_state_id=working_state_id,
            source_revision_sha256=base_revision_sha256,
            objects=working_objects,
            candidates=working_candidates,
            created_at=created_at,
            geometries=working_geometries,
        )
        working_bytes = canonical_json_bytes(working)
        _write_new(partial / "working" / "working_state.json", working_bytes)
        _write_new(partial / "current_revision.tsv", CURRENT_REVISION_HEADER.encode("utf-8"))
        clone_sha: str | None = None
        clone_status = "NOT_APPLICABLE"
        if clone_provenance is not None:
            clone_bytes = canonical_json_bytes(dict(clone_provenance))
            clone_sha = sha256_bytes(clone_bytes)
            clone_status = "VERIFIED"
            _write_new(partial / "clone_provenance.json", clone_bytes)
        metadata = {
            "analysis_session_id": session_id,
            "analysis_session_uid": session_uid,
            "canonical_role": canonical_role,
            "clone_provenance_sha256": clone_sha,
            "clone_provenance_status": clone_status,
            "created_at": created_at,
            "generation": 1,
            "image_id": binding["image_id"],
            "image_uid": binding["image_uid"],
            "lifecycle": "CURRENT",
            "master_pixel_hash_method": binding["master_pixel_hash_method"],
            "master_pixel_hash_status": binding["master_pixel_hash_status"],
            "master_pixel_sha256": binding["master_pixel_sha256"],
            "origin_type": origin_type,
            "project_uid": self.project_uid,
            "restricted_evidence_ref_sha256": None,
            "restricted_evidence_status": "UNKNOWN",
            "schema": "CTL_SESSION_METADATA_JSON_V1",
            "source_sha256": binding["source_sha256"],
            "updated_at": created_at,
            "working_state_id": working_state_id,
            "working_state_sha256": sha256_bytes(working_bytes),
        }
        _write_new(partial / "session_metadata.json", canonical_json_bytes(metadata))
        return partial, metadata

    def create_empty_session(
        self,
        image_uid: str,
        *,
        analysis_session_id: str,
        canonical_role: str | None = None,
        created_at: str | None = None,
        expected_current_generation: int | None = None,
        expected_registry_sha256: str | None = None,
        _fault: FaultHook | None = None,
    ) -> SessionRecord:
        self._reconcile_source_registry_journals()
        binding = self._binding(image_uid)
        session_id = _safe_component(analysis_session_id, "analysis_session_id")
        timestamp = _require_timestamp(created_at or utc_now_z(), "created_at")
        rows = self._read_registry(image_uid)
        if any(row["analysis_session_id"] == session_id for row in rows):
            raise ValidationError("analysis_session_id is already used under image")
        role = canonical_role or ("CANONICAL" if not rows else "NON_CANONICAL")
        if role not in CANONICAL_ROLES:
            raise ValidationError("canonical_role is invalid")
        if role == "CANONICAL" and any(row["canonical_role"] == "CANONICAL" for row in rows):
            raise ValidationError("image already has a canonical session")
        _current, snapshot_generation, snapshot_registry_sha = self._selection_snapshot(
            image_uid
        )
        if (
            expected_current_generation is not None
            and expected_current_generation != snapshot_generation
        ):
            raise StaleContextError("current session generation changed")
        if (
            expected_registry_sha256 is not None
            and expected_registry_sha256 != snapshot_registry_sha
        ):
            raise StaleContextError("session registry changed")
        session_uid = _require_uuid(new_uuid4_identity(), "analysis_session_uid", version=4)
        partial, _ = self._new_session_partial(
            binding,
            session_id=session_id,
            session_uid=session_uid,
            origin_type="NEW_EMPTY",
            canonical_role=role,
            created_at=timestamp,
            clone_provenance=None,
            working_objects=(),
            working_candidates=(),
            base_revision_sha256=None,
        )
        final = partial.parent / partial.name.split(".partial.", 1)[0]
        _current_before_publish, observed_generation, observed_registry_sha = (
            self._selection_snapshot(image_uid)
        )
        if (
            observed_generation != snapshot_generation
            or observed_registry_sha != snapshot_registry_sha
        ):
            raise StaleContextError("session selection authority changed during staging")
        rename_directory_no_replace(partial, final, error_type=TransactionError)
        self._select_published_session(
            binding,
            final,
            expected_current_generation=snapshot_generation,
            expected_registry_sha256=snapshot_registry_sha,
            created_at=timestamp,
            _fault=_fault,
        )
        self.refresh_storage_manifest()
        current = self._read_current_session(image_uid)
        assert current is not None
        return SessionRecord(self.project_uid, image_uid, session_uid, session_id, final, current["generation"])

    def _selection_snapshot(self, image_uid: str) -> tuple[dict[str, Any] | None, int, str]:
        current = self._read_current_session(image_uid)
        generation = 0 if current is None else int(current["generation"])
        return current, generation, sha256_file(self._registry_path(image_uid))

    def _select_published_session(
        self,
        binding: Mapping[str, Any],
        target_root: Path,
        *,
        expected_current_generation: int | None,
        expected_registry_sha256: str | None,
        created_at: str,
        _fault: FaultHook | None,
    ) -> SelectionResult:
        image_uid = binding["image_uid"]
        current, old_generation, registry_hash = self._selection_snapshot(image_uid)
        if expected_current_generation is not None and expected_current_generation != old_generation:
            raise StaleContextError("current session generation changed")
        if expected_registry_sha256 is not None and expected_registry_sha256 != registry_hash:
            raise StaleContextError("session registry changed")
        target_metadata = self._metadata(target_root)
        rows = self._read_registry(image_uid)
        existing = {row["analysis_session_uid"]: dict(row) for row in rows}
        new_generation = old_generation + 1
        metadata_updates: list[tuple[Path, bytes, bytes]] = []
        for row in rows:
            session_root = _contained(self._image_root(image_uid), row["relative_path"])
            metadata = self._metadata(session_root)
            lifecycle = "CURRENT" if row["analysis_session_uid"] == target_metadata["analysis_session_uid"] else "HISTORICAL"
            if metadata["lifecycle"] != lifecycle:
                old_bytes = (session_root / "session_metadata.json").read_bytes()
                metadata["lifecycle"] = lifecycle
                metadata["generation"] += 1
                metadata["updated_at"] = created_at
                metadata_updates.append((session_root / "session_metadata.json", old_bytes, canonical_json_bytes(metadata)))
        # A newly published target already says CURRENT.  Existing targets were
        # handled exactly once by the registry loop above.

        # Calculate hashes from the exact staged metadata bytes.
        staged_metadata = {path.parent: data for path, _old, data in metadata_updates}
        target_metadata_bytes = staged_metadata.get(target_root, (target_root / "session_metadata.json").read_bytes())
        new_rows: list[dict[str, Any]] = []
        roots_by_uid = {
            row["analysis_session_uid"]: _contained(self._image_root(image_uid), row["relative_path"])
            for row in rows
        }
        roots_by_uid[target_metadata["analysis_session_uid"]] = target_root
        for uid, session_root in roots_by_uid.items():
            metadata_path = session_root / "session_metadata.json"
            metadata_bytes = staged_metadata.get(
                session_root,
                stable_plain_bytes(metadata_path, label="session metadata selection snapshot"),
            )
            metadata = loads_canonical_json(metadata_bytes)
            lifecycle = "CURRENT" if uid == target_metadata["analysis_session_uid"] else "HISTORICAL"
            row = self._make_registry_row(
                binding,
                metadata,
                session_root,
                generation=new_generation,
                lifecycle=lifecycle,
                stats=self._session_stats(
                    session_root,
                    byte_overrides={metadata_path: metadata_bytes},
                ),
            )
            row["session_metadata_sha256"] = sha256_bytes(metadata_bytes)
            new_rows.append(row)
        new_rows.sort(key=lambda row: row["analysis_session_uid"])
        self._validate_registry_rows(image_uid, new_rows)
        registry_bytes = _tsv_bytes(SESSION_REGISTRY_FIELDS, new_rows)
        pointer = {
            "pointer_version": 1,
            "project_uid": self.project_uid,
            "image_uid": image_uid,
            "analysis_session_uid": target_metadata["analysis_session_uid"],
            "analysis_session_id": target_metadata["analysis_session_id"],
            "relative_path": f"sessions/{target_root.name}",
            "session_metadata_sha256": sha256_bytes(target_metadata_bytes),
            "session_registry_sha256": sha256_bytes(registry_bytes),
            "generation": new_generation,
            "updated_at": created_at,
        }
        pointer_bytes = _tsv_bytes(CURRENT_SESSION_FIELDS, [pointer])
        registry_path = self._registry_path(image_uid)
        pointer_path = self._current_session_path(image_uid)
        old_registry = registry_path.read_bytes()
        old_pointer = pointer_path.read_bytes() if pointer_path.exists() else None
        token = f"session_select_{new_generation}_{uuid.uuid4().hex}"
        journal_path = target_root / "journals" / f"JOURNAL_{token}.json"
        journal = {
            "analysis_session_uid": target_metadata["analysis_session_uid"],
            "created_at": created_at,
            "new_generation": new_generation,
            "new_pointer_sha256": sha256_bytes(pointer_bytes),
            "new_registry_sha256": sha256_bytes(registry_bytes),
            "old_generation": old_generation,
            "old_pointer_sha256": "NOT_APPLICABLE" if old_pointer is None else sha256_bytes(old_pointer),
            "old_registry_sha256": sha256_bytes(old_registry),
            "schema": "CTL_P2A_SESSION_SELECTION_JOURNAL_V1",
            "state": "PREPARED",
        }
        _write_new(journal_path, canonical_json_bytes(journal))
        written_metadata: list[tuple[Path, bytes]] = []
        registry_published = False
        pointer_published = False
        try:
            for index, (path, old_bytes, new_bytes) in enumerate(metadata_updates):
                _replace_exact(path, new_bytes, expected_sha256=sha256_bytes(old_bytes), token=f"{token}_metadata_{index}")
                written_metadata.append((path, old_bytes))
            _call_fault(_fault, "SESSION_METADATA_STAGED", {"generation": new_generation})
            _replace_exact(registry_path, registry_bytes, expected_sha256=registry_hash, token=f"{token}_registry")
            registry_published = True
            _call_fault(_fault, "SESSION_REGISTRY_REPLACED", {"generation": new_generation})
            _replace_exact(
                pointer_path,
                pointer_bytes,
                expected_sha256="NOT_APPLICABLE" if old_pointer is None else sha256_bytes(old_pointer),
                token=f"{token}_pointer",
            )
            pointer_published = True
            _call_fault(_fault, "CURRENT_SESSION_REPLACED", {"generation": new_generation})
            if sha256_file(registry_path) != pointer["session_registry_sha256"]:
                raise TransactionError("new current session and registry do not agree")
            journal["state"] = "COMMITTED"
            _replace_exact(
                journal_path, canonical_json_bytes(journal),
                expected_sha256=sha256_file(journal_path), token=f"{token}_journal_commit",
            )
        except BaseException:
            rollback_error: BaseException | None = None
            try:
                if pointer_published:
                    _restore_exact(
                        pointer_path,
                        old_pointer,
                        f"{token}_pointer",
                        expected_owned_sha256=sha256_bytes(pointer_bytes),
                    )
                if registry_published:
                    _restore_exact(
                        registry_path,
                        old_registry,
                        f"{token}_registry",
                        expected_owned_sha256=sha256_bytes(registry_bytes),
                    )
                for index, (path, old_bytes) in enumerate(reversed(written_metadata)):
                    new_bytes = next(
                        candidate_new
                        for candidate_path, _candidate_old, candidate_new in metadata_updates
                        if candidate_path == path
                    )
                    _restore_exact(
                        path,
                        old_bytes,
                        f"{token}_metadata_{index}",
                        expected_owned_sha256=sha256_bytes(new_bytes),
                    )
                journal["state"] = "ROLLED_BACK"
                journal["rollback_verified"] = True
                _replace_exact(
                    journal_path, canonical_json_bytes(journal),
                    expected_sha256=sha256_file(journal_path), token=f"{token}_journal_rollback",
                )
            except BaseException as exc:
                rollback_error = exc
            if rollback_error is not None:
                raise TransactionError("selection failed and rollback could not be verified") from rollback_error
            raise
        return SelectionResult(
            "SELECTED", 0, 0, "CONTROL_AND_AUDIT_ONLY",
            None if current is None else current["analysis_session_uid"],
            target_metadata["analysis_session_uid"], new_generation,
        )

    def select_session(
        self,
        image_uid: str,
        *,
        analysis_session_id: str | None = None,
        analysis_session_uid: str | None = None,
        expected_current_generation: int,
        expected_registry_sha256: str,
        cancel: bool = False,
        stale_context: bool = False,
        event_at: str | None = None,
        external_audit_root: os.PathLike[str] | str | None = None,
        _fault: FaultHook | None = None,
    ) -> SelectionResult:
        current = self._read_current_session(image_uid)
        previous_uid = None if current is None else current["analysis_session_uid"]
        if cancel:
            return SelectionResult("SELECTION_CANCELLED", 0, 0, "NONE", previous_uid, previous_uid, expected_current_generation)
        if stale_context:
            return self.cancel_stale_context(
                image_uid,
                expected_generation=expected_current_generation,
                external_audit_root=external_audit_root,
                event_at=event_at,
            )
        if (analysis_session_id is None) == (analysis_session_uid is None):
            raise ValidationError("selection requires exactly one explicit session ID or UID")
        record = (
            self.session_by_id(image_uid, analysis_session_id)
            if analysis_session_id is not None
            else self.session_by_uid(image_uid, str(analysis_session_uid))
        )
        if current is not None and current["analysis_session_uid"] == record.analysis_session_uid:
            if current["generation"] != expected_current_generation or sha256_file(self._registry_path(image_uid)) != expected_registry_sha256:
                raise StaleContextError("selection caller snapshot is stale")
            return SelectionResult("ALREADY_SELECTED", 0, 0, "NONE", previous_uid, previous_uid, current["generation"])
        self._reconcile_source_registry_journals()
        return self._select_published_session(
            self._binding(image_uid),
            record.session_root,
            expected_current_generation=expected_current_generation,
            expected_registry_sha256=expected_registry_sha256,
            created_at=_require_timestamp(event_at or utc_now_z(), "event_at"),
            _fault=_fault,
        )

    def cancel_stale_context(
        self,
        image_uid: str,
        *,
        expected_generation: int,
        external_audit_root: os.PathLike[str] | str | None,
        event_at: str | None = None,
    ) -> SelectionResult:
        """Return the exact approved stale result and write only external audit."""

        current = self._read_current_session(image_uid)
        previous_uid = None if current is None else current["analysis_session_uid"]
        if external_audit_root is not None:
            audit_root = Path(external_audit_root)
            if not audit_root.is_dir() or audit_root.resolve() == self.root.resolve() or self.root.resolve() in audit_root.resolve().parents:
                raise ValidationError("stale audit root must be an existing external directory")
            timestamp = _require_timestamp(event_at or utc_now_z(), "event_at")
            event = {
                "event_at": timestamp,
                "expected_generation": expected_generation,
                "image_uid": image_uid,
                "observed_generation": 0 if current is None else current["generation"],
                "result": "STALE_CONTEXT_CANCELLED",
                "schema": "CTL_P2A_EXTERNAL_AUDIT_EVENT_V1",
            }
            _write_new(audit_root / f"STALE_{uuid.uuid4().hex}.json", canonical_json_bytes(event))
            disk_writes = "audit_event_only"
        else:
            disk_writes = "audit_event_only"
        return SelectionResult(
            "STALE_CONTEXT_CANCELLED", 0, 0, disk_writes,
            previous_uid, previous_uid, 0 if current is None else current["generation"],
        )

    def update_working_state(
        self,
        image_uid: str,
        session_uid: str,
        *,
        objects: Sequence[Mapping[str, Any]],
        candidates: Sequence[Mapping[str, Any]],
        expected_working_sha256: str,
        geometries: Sequence[Mapping[str, Any]] | None = None,
        bind_base_revision_manifest_sha256: str | None = None,
        updated_at: str | None = None,
    ) -> str:
        self._reconcile_source_registry_journals()
        record = self.session_by_uid(image_uid, session_uid)
        path = record.session_root / "working" / "working_state.json"
        old_working_bytes = stable_plain_bytes(path, label="working state caller snapshot")
        observed_working_sha = sha256_bytes(old_working_bytes)
        if observed_working_sha != expected_working_sha256:
            raise StaleContextError("working state caller snapshot is stale")
        old = loads_canonical_json(old_working_bytes)
        if any(item.get("candidate_schema") == MANUAL_CANDIDATE_SCHEMA for item in [*old.get("candidates", []), *candidates]):
            # A rejected review must not leave an invalid working state behind
            # before the later immutable revision publication performs its checks.
            self._normalize_revision_entities(objects, candidates)
            binding = self._binding(image_uid)
            for candidate in candidates:
                if candidate.get("candidate_schema") != MANUAL_CANDIDATE_SCHEMA:
                    continue
                view = candidate["source_view"]["record"]
                if (candidate["source_sha256"] != binding["source_sha256"]
                        or candidate["master_pixel_sha256"] != binding["master_pixel_sha256"]
                        or view["image_uid"] != image_uid or view["project_uid"] != self.project_uid):
                    raise ValidationError("Manual candidate does not belong to this project's original image")
        timestamp = _require_timestamp(updated_at or utc_now_z(), "updated_at")
        new = dict(old)
        new["objects"] = [dict(item) for item in objects]
        new["candidates"] = [dict(item) for item in candidates]
        working_schema = old.get("schema")
        if working_schema == "CTL_P2A_WORKING_STATE_V1":
            if "geometries" in old:
                raise ValidationError("working state V1 cannot contain geometries")
        elif working_schema == "CTL_P2A_WORKING_STATE_V2":
            old_geometries = old.get("geometries")
            if not isinstance(old_geometries, list):
                raise ValidationError("working state V2 geometry inventory is invalid")
            normalized_old_geometries = self._normalize_revision_geometries(old_geometries)
            if normalized_old_geometries != old_geometries:
                raise ValidationError("working state geometry hash/order is not canonical")
        else:
            raise ValidationError("working state schema is unsupported")
        if geometries is not None:
            new["geometries"] = self._normalize_revision_geometries(geometries)
            new["schema"] = "CTL_P2A_WORKING_STATE_V2"
        if bind_base_revision_manifest_sha256 is not None:
            new["base_revision_manifest_sha256"] = _require_sha(
                bind_base_revision_manifest_sha256,
                "bind_base_revision_manifest_sha256",
            )
        new["generation"] = _require_positive(old["generation"], "working.generation") + 1
        new["updated_at"] = timestamp
        working_bytes = canonical_json_bytes(new)
        metadata_path = record.session_root / "session_metadata.json"
        old_metadata_bytes = stable_plain_bytes(metadata_path, label="session metadata snapshot")
        old_meta_hash = sha256_bytes(old_metadata_bytes)
        metadata = loads_canonical_json(old_metadata_bytes)
        metadata["working_state_sha256"] = sha256_bytes(working_bytes)
        metadata["generation"] += 1
        metadata["updated_at"] = timestamp
        metadata_bytes = canonical_json_bytes(metadata)
        registry_bytes, pointer_bytes, generation, old_registry_hash, old_registry, old_pointer = (
            self._plan_session_registry_refresh(
                image_uid,
                timestamp,
                metadata_overrides={metadata_path: metadata_bytes},
                byte_overrides={path: working_bytes, metadata_path: metadata_bytes},
            )
        )
        registry_path = self._registry_path(image_uid)
        pointer_path = self._current_session_path(image_uid)
        token = f"working_state_{generation}_{uuid.uuid4().hex}"
        journal_path = record.session_root / "journals" / f"JOURNAL_{token}.json"
        targets = (
            (path, old_working_bytes, working_bytes, observed_working_sha, "working"),
            (metadata_path, old_metadata_bytes, metadata_bytes, old_meta_hash, "metadata"),
            (registry_path, old_registry, registry_bytes, old_registry_hash, "registry"),
            (
                pointer_path,
                old_pointer,
                pointer_bytes,
                sha256_bytes(old_pointer),
                "current_session",
            ),
        )
        journal = {
            "analysis_session_uid": session_uid,
            "created_at": timestamp,
            "generation": generation,
            "schema": "CTL_P2A_WORKING_STATE_TRANSACTION_JOURNAL_V1",
            "state": "PREPARED",
            "targets": [
                {
                    "name": label,
                    "new_sha256": sha256_bytes(new_bytes),
                    "old_sha256": old_sha,
                    "relative_path": target.relative_to(record.session_root).as_posix()
                    if record.session_root in target.parents
                    else target.relative_to(self.root).as_posix(),
                }
                for target, _old_bytes, new_bytes, old_sha, label in targets
            ],
        }
        _write_new(journal_path, canonical_json_bytes(journal))
        written: list[tuple[Path, bytes, bytes, str]] = []
        try:
            for target, old_bytes, new_bytes, old_sha, label in targets:
                _replace_exact(
                    target,
                    new_bytes,
                    expected_sha256=old_sha,
                    token=f"{token}_{label}",
                )
                written.append((target, old_bytes, new_bytes, label))
            journal["state"] = "COMMITTED"
            _replace_exact(
                journal_path,
                canonical_json_bytes(journal),
                expected_sha256=sha256_file(journal_path),
                token=f"{token}_journal_commit",
            )
        except BaseException:
            rollback_error: BaseException | None = None
            try:
                for target, old_bytes, new_bytes, label in reversed(written):
                    _restore_exact(
                        target,
                        old_bytes,
                        f"{token}_{label}",
                        expected_owned_sha256=sha256_bytes(new_bytes),
                    )
                journal["state"] = "ROLLED_BACK"
                journal["rollback_verified"] = True
                _replace_exact(
                    journal_path,
                    canonical_json_bytes(journal),
                    expected_sha256=sha256_file(journal_path),
                    token=f"{token}_journal_rollback",
                )
            except BaseException as exc:
                rollback_error = exc
            if rollback_error is not None:
                raise TransactionError(
                    "working-state transaction failed and rollback could not be verified"
                ) from rollback_error
            raise
        return sha256_bytes(working_bytes)

    def _normalize_revision_entities(
        self, objects: Sequence[Mapping[str, Any]], candidates: Sequence[Mapping[str, Any]]
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        normalized_objects: list[dict[str, Any]] = []
        object_ids: set[str] = set()
        cavity_ids: set[str] = set()
        object_by_candidate: dict[str, str] = {}
        for raw in objects:
            value = dict(raw)
            required = {"candidate_uuid", "cavity_id", "identity_provenance", "object_uuid"}
            if not required.issubset(value):
                raise ValidationError("revision object lacks identity fields")
            object_uuid = _require_uuid(value["object_uuid"], "object_uuid", version=4)
            candidate_uuid = value["candidate_uuid"]
            if candidate_uuid is not None:
                candidate_uuid = _require_uuid(candidate_uuid, "candidate_uuid", version=4)
            cavity_id = validate_cavity_id(value["cavity_id"])
            if object_uuid in object_ids or cavity_id in cavity_ids or not isinstance(value["identity_provenance"], Mapping):
                raise ValidationError("revision object identity collision or provenance absence")
            if candidate_uuid is not None and candidate_uuid in object_by_candidate:
                raise ValidationError("multiple revision objects reference the same candidate")
            value_without_hash = {key: item for key, item in value.items() if key != "object_sha256"}
            value["object_sha256"] = sha256_bytes(canonical_json_bytes(value_without_hash))
            object_ids.add(object_uuid); cavity_ids.add(cavity_id)
            if candidate_uuid is not None:
                object_by_candidate[candidate_uuid] = object_uuid
            normalized_objects.append(value)
        normalized_objects.sort(key=lambda item: item["object_uuid"])
        normalized_candidates: list[dict[str, Any]] = []
        candidate_uuids: set[str] = set()
        candidate_ids: set[str] = set()
        for raw in candidates:
            value = dict(raw)
            required = {
                "candidate_id", "candidate_uuid", "identity_provenance", "object_uuid",
                "review_decision", "review_status",
            }
            if not required.issubset(value):
                raise ValidationError("revision candidate lacks identity fields")
            candidate_uuid = _require_uuid(value["candidate_uuid"], "candidate_uuid", version=4)
            candidate_id = _safe_component(value["candidate_id"], "candidate_id")
            if (
                candidate_uuid in candidate_uuids
                or candidate_id in candidate_ids
                or not isinstance(value["identity_provenance"], Mapping)
            ):
                raise ValidationError("revision candidate identity collision")
            _link_status, object_uuid = _candidate_link_status(value, prefix=f"candidate.{candidate_id}")
            if object_uuid is not None and object_by_candidate.get(candidate_uuid) != object_uuid:
                raise ValidationError("revision candidate/object reciprocal link mismatch")
            value["candidate_sha256"] = _entity_record_sha256(value, "candidate_sha256")
            candidate_uuids.add(candidate_uuid); candidate_ids.add(candidate_id)
            normalized_candidates.append(value)
        normalized_candidates.sort(key=lambda item: item["candidate_uuid"])
        if object_ids & candidate_uuids:
            raise ValidationError("revision object and candidate UUID domains overlap")
        referenced = {item["candidate_uuid"] for item in normalized_objects if item["candidate_uuid"] is not None}
        if not referenced.issubset(candidate_uuids):
            raise ValidationError("revision object references an absent candidate")
        candidate_by_uuid = {item["candidate_uuid"]: item for item in normalized_candidates}
        for candidate_uuid, object_uuid in object_by_candidate.items():
            candidate = candidate_by_uuid.get(candidate_uuid)
            if candidate is None or candidate.get("object_uuid") != object_uuid:
                raise ValidationError("revision object/candidate reciprocal link mismatch")
        object_by_uuid = {item["object_uuid"]: item for item in normalized_objects}
        for candidate in normalized_candidates:
            validate_manual_candidate(candidate, object_by_uuid.get(candidate.get("object_uuid")))
        return normalized_objects, normalized_candidates

    def _normalize_revision_geometries(
        self, geometries: Sequence[Mapping[str, Any]]
    ) -> list[dict[str, Any]]:
        """Return the closed, deterministic Prompt-3 scientific geometry set.

        ROI bytes remain the authority.  Coordinates, bounds and labels are
        canonical derived fields retained byte-exactly by the JSON profile;
        their inner scientific schemas are selected by ``geometry_schema`` and
        are deliberately not reinterpreted here.
        """

        if isinstance(geometries, (str, bytes, bytearray)) or not isinstance(
            geometries, Sequence
        ):
            raise ValidationError("revision geometries must be an array")

        def canonical_container(
            value: Any,
            field: str,
            *,
            allow_array: bool,
        ) -> dict[str, Any] | list[Any]:
            if isinstance(value, Mapping):
                candidate: dict[str, Any] | list[Any] = dict(value)
            elif allow_array and isinstance(value, list):
                candidate = list(value)
            else:
                raise ValidationError(
                    "geometry derived field has an invalid container",
                    details={"field": field},
                )
            # Round-trip through the exact profile to reject unsupported JSON,
            # non-finite numbers, negative zero, non-NFC text and key aliases.
            return loads_canonical_json(canonical_json_bytes({"value": candidate}))["value"]

        normalized: list[dict[str, Any]] = []
        geometry_uids: set[str] = set()
        geometry_ids: set[str] = set()
        for index, raw in enumerate(geometries):
            if not isinstance(raw, Mapping):
                raise ValidationError(
                    "revision geometry is not an object", details={"index": index}
                )
            value = dict(raw)
            if any(not isinstance(key, str) for key in value):
                raise ValidationError(
                    "revision geometry field names must be strings", details={"index": index}
                )
            fields = set(value)
            if not P3_GEOMETRY_REQUIRED_FIELDS.issubset(fields) or not fields.issubset(
                P3_GEOMETRY_FIELDS
            ):
                raise ValidationError(
                    "revision geometry has an incorrect closed field inventory",
                    details={
                        "index": index,
                        "missing": sorted(P3_GEOMETRY_REQUIRED_FIELDS - fields),
                        "extra": sorted(fields - P3_GEOMETRY_FIELDS),
                    },
                )

            geometry_uid = _require_uuid(
                value["geometry_uid"], f"geometries[{index}].geometry_uid", version=4
            )
            geometry_id = _safe_component(
                value["geometry_id"], f"geometries[{index}].geometry_id"
            )
            geometry_type = value["geometry_type"]
            if not isinstance(geometry_type, str) or geometry_type not in P3_GEOMETRY_TYPES:
                raise ValidationError(
                    "revision geometry type is outside the closed vocabulary",
                    details={"index": index, "geometry_type": geometry_type},
                )
            geometry_schema = _safe_component(
                value["geometry_schema"], f"geometries[{index}].geometry_schema"
            )
            if geometry_uid in geometry_uids or geometry_id in geometry_ids:
                raise ValidationError(
                    "revision geometry identity collision",
                    details={"geometry_id": geometry_id, "geometry_uid": geometry_uid},
                )

            encoded_roi = value["roi_bytes_base64"]
            if not isinstance(encoded_roi, str):
                raise ValidationError(
                    "revision geometry ROI bytes are not base64 text",
                    details={"index": index},
                )
            try:
                roi_bytes = base64.b64decode(encoded_roi.encode("ascii"), validate=True)
            except (UnicodeEncodeError, binascii.Error, ValueError) as exc:
                raise ValidationError(
                    "revision geometry ROI bytes are not canonical base64",
                    details={"index": index},
                ) from exc
            if base64.b64encode(roi_bytes).decode("ascii") != encoded_roi:
                raise ValidationError(
                    "revision geometry ROI bytes are not canonical base64",
                    details={"index": index},
                )
            if len(roi_bytes) < 4 or roi_bytes[:4] != b"Iout":
                raise ValidationError(
                    "revision geometry ROI does not have the ImageJ Iout header",
                    details={"index": index},
                )
            observed_roi_sha = sha256_bytes(roi_bytes)
            declared_roi_sha = _require_sha(
                value["roi_bytes_sha256"], f"geometries[{index}].roi_bytes_sha256"
            )
            source_roi_sha = _require_sha(
                value["source_roi_sha256"], f"geometries[{index}].source_roi_sha256"
            )
            if declared_roi_sha != observed_roi_sha or source_roi_sha != observed_roi_sha:
                raise ValidationError(
                    "revision geometry ROI hash does not bind its exact bytes",
                    details={"index": index, "observed_roi_sha256": observed_roi_sha},
                )

            value["geometry_uid"] = geometry_uid
            value["geometry_id"] = geometry_id
            value["geometry_type"] = geometry_type
            value["geometry_schema"] = geometry_schema
            value["roi_bytes_base64"] = encoded_roi
            value["roi_bytes_sha256"] = declared_roi_sha
            value["source_roi_sha256"] = source_roi_sha
            value["coordinates"] = canonical_container(
                value["coordinates"], f"geometries[{index}].coordinates", allow_array=True
            )
            value["bounds"] = canonical_container(
                value["bounds"], f"geometries[{index}].bounds", allow_array=False
            )
            value["labels"] = canonical_container(
                value["labels"], f"geometries[{index}].labels", allow_array=True
            )

            expected_geometry_sha = _entity_record_sha256(value, "geometry_sha256")
            supplied_geometry_sha = value.get("geometry_sha256")
            if supplied_geometry_sha is not None and _require_sha(
                supplied_geometry_sha, f"geometries[{index}].geometry_sha256"
            ) != expected_geometry_sha:
                raise ValidationError(
                    "revision geometry hash does not bind its canonical record",
                    details={"index": index, "expected_geometry_sha256": expected_geometry_sha},
                )
            value["geometry_sha256"] = expected_geometry_sha
            geometry_uids.add(geometry_uid)
            geometry_ids.add(geometry_id)
            normalized.append(value)

        normalized.sort(key=lambda item: item["geometry_uid"])
        return normalized

    def geometry_set_sha256(self, geometries: Sequence[Mapping[str, Any]]) -> str:
        """Hash the canonical normalized geometry array in a named JSON domain."""

        normalized = self._normalize_revision_geometries(geometries)
        return sha256_bytes(canonical_json_bytes({"geometries": normalized}))

    def _revision_manifest(
        self,
        *,
        record: SessionRecord,
        revision_id: str,
        revision_uid: str,
        parent_revision_id: str,
        objects: Sequence[Mapping[str, Any]],
        candidates: Sequence[Mapping[str, Any]],
        created_at: str,
        source_sha256: str,
        identity_provenance: Sequence[Mapping[str, Any]],
        geometries: Sequence[Mapping[str, Any]] | None = None,
    ) -> dict[str, Any]:
        normalized_objects, normalized_candidates = self._normalize_revision_entities(objects, candidates)
        for candidate in normalized_candidates:
            if candidate.get("candidate_schema") == MANUAL_CANDIDATE_SCHEMA:
                view = candidate["source_view"]["record"]
                if candidate["source_sha256"] != source_sha256 or view["image_uid"] != record.image_uid or view["project_uid"] != self.project_uid:
                    raise ValidationError("Manual candidate revision source authority differs")
        manifest = {
            "analysis_session_uid": record.analysis_session_uid,
            "candidates": normalized_candidates,
            "created_at": created_at,
            # The P1 canonical serializer reserves the array key
            # ``identity_provenance`` for its ten-owner legacy coverage map.
            # P2A revision provenance is a distinct internal record and must
            # not be misinterpreted as that legacy array profile.
            "revision_identity_provenance": [dict(item) for item in identity_provenance],
            "image_uid": record.image_uid,
            "objects": normalized_objects,
            "parent_revision_id": parent_revision_id,
            "project_uid": self.project_uid,
            "revision_id": revision_id,
            "revision_uid": revision_uid,
            "schema": "CTL_P2A_REVISION_MANIFEST_V1",
            "source_sha256": source_sha256,
        }
        if geometries is not None:
            normalized_geometries = self._normalize_revision_geometries(geometries)
            entity_uids = {
                item["object_uuid"] for item in normalized_objects
            } | {item["candidate_uuid"] for item in normalized_candidates}
            geometry_uids = {item["geometry_uid"] for item in normalized_geometries}
            if entity_uids & geometry_uids:
                raise ValidationError("revision geometry UUID collides with an object/candidate UUID")
            manifest["geometries"] = normalized_geometries
            manifest["schema"] = "CTL_P2A_REVISION_MANIFEST_V2"
        return manifest

    def _verify_revision(
        self,
        record: SessionRecord,
        revision_root: Path,
        *,
        allow_partial: bool = False,
    ) -> dict[str, Any]:
        if revision_root.parent != record.session_root / "revisions" or not revision_root.name.startswith("REV_"):
            raise ValidationError("revision is outside its owning session")
        try:
            plain_directory(revision_root, label="revision directory")
        except PathSafetyError as exc:
            raise ValidationError("revision directory is unsafe", details={"reason": str(exc)}) from exc
        expected = {"COMPLETE", "REVISION_SHA256.txt", "revision_manifest.json"}
        if {path.name for path in revision_root.iterdir()} != expected:
            raise ValidationError("revision inventory is not closed")
        manifest_bytes = stable_plain_bytes(
            revision_root / "revision_manifest.json", label="revision manifest"
        )
        manifest = loads_canonical_json(manifest_bytes)
        digest = sha256_bytes(manifest_bytes)
        if stable_plain_bytes(
            revision_root / "REVISION_SHA256.txt", label="revision sidecar"
        ) != f"{digest}  revision_manifest.json\n".encode("ascii"):
            raise ValidationError("revision sidecar mismatch")
        marker = loads_canonical_json(
            stable_plain_bytes(revision_root / "COMPLETE", label="revision COMPLETE")
        )
        if marker != {
            "analysis_session_uid": record.analysis_session_uid,
            "revision_manifest_sha256": digest,
            "revision_uid": manifest.get("revision_uid"),
            "schema": "CTL_P2A_REVISION_COMPLETE_V1",
        }:
            raise ValidationError("revision COMPLETE marker mismatch")
        manifest_schema = manifest.get("schema")
        if manifest_schema not in {
            "CTL_P2A_REVISION_MANIFEST_V1",
            "CTL_P2A_REVISION_MANIFEST_V2",
        } or manifest.get("project_uid") != self.project_uid:
            raise ValidationError("revision manifest schema/project mismatch")
        if manifest_schema == "CTL_P2A_REVISION_MANIFEST_V1":
            if "geometries" in manifest:
                raise ValidationError("revision manifest V1 cannot contain geometries")
            manifest_geometries: Sequence[Mapping[str, Any]] = []
        else:
            if not isinstance(manifest.get("geometries"), list):
                raise ValidationError("revision manifest V2 geometry inventory is invalid")
            manifest_geometries = manifest["geometries"]
        if manifest.get("image_uid") != record.image_uid or manifest.get("analysis_session_uid") != record.analysis_session_uid:
            raise ValidationError("revision manifest session scope mismatch")
        expected_name = f"REV_{manifest.get('revision_id')}"
        valid_name = revision_root.name == expected_name
        if allow_partial:
            valid_name = valid_name or re.fullmatch(
                re.escape(expected_name) + r"\.partial\.[0-9a-f]{32}", revision_root.name
            ) is not None
        if not valid_name:
            raise ValidationError("revision path/ID mismatch")
        _require_uuid(manifest.get("revision_uid"), "revision_uid", version=4)
        _require_sha(manifest.get("source_sha256"), "source_sha256")
        _require_timestamp(manifest.get("created_at"), "created_at")
        normalized_objects, normalized_candidates = self._normalize_revision_entities(
            manifest.get("objects", []), manifest.get("candidates", [])
        )
        if normalized_objects != manifest.get("objects") or normalized_candidates != manifest.get("candidates"):
            raise ValidationError("revision entity hash/order is not canonical")
        normalized_geometries = self._normalize_revision_geometries(manifest_geometries)
        if normalized_geometries != list(manifest_geometries):
            raise ValidationError("revision geometry hash/order is not canonical")
        entity_uids = {
            item["object_uuid"] for item in normalized_objects
        } | {item["candidate_uuid"] for item in normalized_candidates}
        if entity_uids & {item["geometry_uid"] for item in normalized_geometries}:
            raise ValidationError("revision geometry UUID collides with an object/candidate UUID")
        return manifest

    def publish_revision(
        self,
        image_uid: str,
        session_uid: str,
        *,
        revision_id: str,
        objects: Sequence[Mapping[str, Any]],
        candidates: Sequence[Mapping[str, Any]],
        identity_provenance: Sequence[Mapping[str, Any]],
        geometries: Sequence[Mapping[str, Any]] | None = None,
        revision_uid: str | None = None,
        parent_revision_id: str = "NOT_APPLICABLE",
        expected_pointer_sha256: str | None = None,
        created_at: str | None = None,
        _fault: FaultHook | None = None,
    ) -> PublishedRevision:
        self._reconcile_source_registry_journals()
        record = self.session_by_uid(image_uid, session_uid)
        pointer_path = record.session_root / "current_revision.tsv"
        old_pointer_bytes = stable_plain_bytes(
            pointer_path, label="current revision caller snapshot"
        )
        observed_pointer_sha = sha256_bytes(old_pointer_bytes)
        if expected_pointer_sha256 is None:
            raise ValidationError("current revision caller snapshot SHA-256 is required")
        if expected_pointer_sha256 != observed_pointer_sha:
            raise StaleContextError("current revision pointer caller snapshot is stale")
        old_rows = _parse_tsv(
            old_pointer_bytes, CURRENT_REVISION_FIELDS, allow_header_only=True
        )
        if len(old_rows) > 1:
            raise ValidationError("current revision pointer has multiple rows")
        rid = _safe_component(revision_id, "revision_id")
        ruid = _require_uuid(revision_uid or new_uuid4_identity(), "revision_uid", version=4)
        if ruid in self._identity_uuid_inventory():
            raise ValidationError("revision_uid is already present in the project")
        if parent_revision_id != "NOT_APPLICABLE":
            _safe_component(parent_revision_id, "parent_revision_id")
        if not old_rows and parent_revision_id != "NOT_APPLICABLE":
            raise ValidationError("first revision cannot declare a parent")
        if old_rows:
            if parent_revision_id == "NOT_APPLICABLE":
                raise ValidationError("non-genesis revision requires its current parent")
            current_parent = old_rows[0]
            if current_parent["revision_id"] != parent_revision_id:
                raise StaleContextError("revision parent is not the current immutable revision")
            parent_root = _contained(record.session_root, current_parent["relative_path"])
            parent_manifest = self._verify_revision(record, parent_root)
            if (
                parent_manifest["revision_uid"] != current_parent["revision_uid"]
                or sha256_file(parent_root / "revision_manifest.json")
                != current_parent["revision_manifest_sha256"]
            ):
                raise ValidationError("revision parent pointer does not bind its immutable revision")
        timestamp = _require_timestamp(created_at or utc_now_z(), "created_at")
        binding = self._binding(image_uid)
        manifest = self._revision_manifest(
            record=record,
            revision_id=rid,
            revision_uid=ruid,
            parent_revision_id=parent_revision_id,
            objects=objects,
            candidates=candidates,
            created_at=timestamp,
            source_sha256=binding["source_sha256"],
            identity_provenance=identity_provenance,
            geometries=geometries,
        )
        manifest_bytes = canonical_json_bytes(manifest)
        manifest_sha = sha256_bytes(manifest_bytes)
        revisions_root = record.session_root / "revisions"
        final = revisions_root / f"REV_{rid}"
        partial = revisions_root / f"REV_{rid}.partial.{uuid.uuid4().hex}"
        if final.exists() or any(revisions_root.glob(f"REV_{rid}.partial.*")):
            raise TransactionError("revision_id already exists or has retained partial")
        partial.mkdir()
        _write_new(partial / "revision_manifest.json", manifest_bytes)
        _write_new(partial / "REVISION_SHA256.txt", f"{manifest_sha}  revision_manifest.json\n".encode("ascii"))
        marker = {
            "analysis_session_uid": record.analysis_session_uid,
            "revision_manifest_sha256": manifest_sha,
            "revision_uid": ruid,
            "schema": "CTL_P2A_REVISION_COMPLETE_V1",
        }
        _write_new(partial / "COMPLETE", canonical_json_bytes(marker))
        self._verify_revision(record, partial, allow_partial=True)
        _call_fault(_fault, "REVISION_BEFORE_PUBLISH", {"revision_uid": ruid})
        rename_directory_no_replace(partial, final, error_type=TransactionError)
        _fsync_directory(revisions_root)
        self._verify_revision(record, final)
        _call_fault(_fault, "REVISION_BEFORE_POINTER", {"revision_uid": ruid})
        old_generation = 0 if not old_rows else int(old_rows[0]["generation"])
        pointer = {
            "pointer_version": 1,
            "project_uid": self.project_uid,
            "image_uid": image_uid,
            "analysis_session_uid": session_uid,
            "revision_uid": ruid,
            "revision_id": rid,
            "relative_path": f"revisions/REV_{rid}",
            "revision_manifest_sha256": manifest_sha,
            "generation": old_generation + 1,
            "updated_at": timestamp,
        }
        pointer_bytes = _tsv_bytes(CURRENT_REVISION_FIELDS, [pointer])
        try:
            _journaled_replace(
                pointer_path,
                pointer_bytes,
                expected_sha256=observed_pointer_sha,
                journal_dir=record.session_root / "journals",
                scope={
                    "analysis_session_uid": session_uid,
                    "image_uid": image_uid,
                    "project_uid": self.project_uid,
                },
                generation=old_generation + 1,
                updated_at=timestamp,
                transaction_kind="revision_pointer",
                _fault=_fault,
            )
        except TransactionError as exc:
            details = exc.details
            if (
                str(exc) == "caller snapshot CAS mismatch"
                and details.get("path") == str(pointer_path)
                and details.get("expected_sha256") == observed_pointer_sha
                and details.get("observed_sha256") != observed_pointer_sha
            ):
                raise StaleContextError(
                    "current revision pointer changed after preflight",
                    details={
                        "path": str(pointer_path),
                        "expected_sha256": observed_pointer_sha,
                        "observed_sha256": details["observed_sha256"],
                    },
                ) from exc
            raise
        self._refresh_session_registry(image_uid, timestamp)
        self.refresh_storage_manifest()
        return PublishedRevision(rid, ruid, manifest_sha, final, old_generation + 1)

    def _refresh_session_registry(self, image_uid: str, updated_at: str) -> None:
        (
            registry_bytes,
            pointer_bytes,
            generation,
            old_registry_hash,
            old_registry,
            old_pointer,
        ) = self._plan_session_registry_refresh(image_uid, updated_at)
        registry_path = self._registry_path(image_uid)
        pointer_path = self._current_session_path(image_uid)
        token = f"registry_refresh_{uuid.uuid4().hex}"
        current = self._read_current_session(image_uid)
        assert current is not None
        journal_path = (
            self.session_by_uid(image_uid, current["analysis_session_uid"]).session_root
            / "journals"
            / f"JOURNAL_{token}.json"
        )
        journal = {
            "analysis_session_uid": current["analysis_session_uid"],
            "created_at": updated_at,
            "generation": generation,
            "new_pointer_sha256": sha256_bytes(pointer_bytes),
            "new_registry_sha256": sha256_bytes(registry_bytes),
            "old_pointer_sha256": sha256_bytes(old_pointer),
            "old_registry_sha256": old_registry_hash,
            "schema": "CTL_P2A_SESSION_REGISTRY_REFRESH_JOURNAL_V1",
            "state": "PREPARED",
        }
        _write_new(journal_path, canonical_json_bytes(journal))
        registry_published = False
        pointer_published = False
        try:
            _replace_exact(registry_path, registry_bytes, expected_sha256=old_registry_hash, token=f"{token}_registry")
            registry_published = True
            _replace_exact(pointer_path, pointer_bytes, expected_sha256=sha256_bytes(old_pointer), token=f"{token}_pointer")
            pointer_published = True
            journal["state"] = "COMMITTED"
            _replace_exact(
                journal_path,
                canonical_json_bytes(journal),
                expected_sha256=sha256_file(journal_path),
                token=f"{token}_journal_commit",
            )
        except BaseException:
            rollback_error: BaseException | None = None
            try:
                if pointer_published:
                    _restore_exact(
                        pointer_path,
                        old_pointer,
                        f"{token}_pointer",
                        expected_owned_sha256=sha256_bytes(pointer_bytes),
                    )
                if registry_published:
                    _restore_exact(
                        registry_path,
                        old_registry,
                        f"{token}_registry",
                        expected_owned_sha256=sha256_bytes(registry_bytes),
                    )
                journal["state"] = "ROLLED_BACK"
                journal["rollback_verified"] = True
                _replace_exact(
                    journal_path,
                    canonical_json_bytes(journal),
                    expected_sha256=sha256_file(journal_path),
                    token=f"{token}_journal_rollback",
                )
            except BaseException as exc:
                rollback_error = exc
            if rollback_error is not None:
                raise TransactionError(
                    "registry refresh failed and rollback could not be verified"
                ) from rollback_error
            raise

    def publish_run(
        self,
        image_uid: str,
        session_uid: str,
        *,
        run_id: str,
        payload: Mapping[str, Any],
        run_uid: str | None = None,
        created_at: str | None = None,
        _fault: FaultHook | None = None,
        _staged_run_validator: Callable[[Any], Any] | None = None,
    ) -> PublishedRun:
        self._reconcile_source_registry_journals()
        record = self.session_by_uid(image_uid, session_uid)
        rid = _safe_component(run_id, "run_id")
        ruid = _require_uuid(run_uid or new_uuid4_identity(), "run_uid", version=4)
        if ruid in self._identity_uuid_inventory():
            raise ValidationError("run_uid is already present in the project")
        timestamp = _require_timestamp(created_at or utc_now_z(), "created_at")
        if not isinstance(payload, Mapping):
            raise ValidationError("native RUN payload request must be an object")
        revision_pointer_path = record.session_root / "current_revision.tsv"
        revision_rows = _parse_tsv(
            stable_plain_bytes(
                revision_pointer_path, label="native RUN current revision pointer"
            ),
            CURRENT_REVISION_FIELDS,
            allow_header_only=True,
        )
        if len(revision_rows) != 1:
            raise ValidationError("native RUN requires exactly one explicit current revision")
        revision_pointer = revision_rows[0]
        revision_root = _contained(record.session_root, revision_pointer["relative_path"])
        revision_manifest = self._verify_revision(record, revision_root)
        revision_manifest_sha = sha256_file(revision_root / "revision_manifest.json")
        if (
            revision_manifest["revision_uid"] != revision_pointer["revision_uid"]
            or revision_manifest["revision_id"] != revision_pointer["revision_id"]
            or revision_manifest_sha != revision_pointer["revision_manifest_sha256"]
        ):
            raise ValidationError("native RUN revision pointer trust chain mismatch")
        binding = self._binding(image_uid)
        if binding["master_pixel_hash_status"] != "VERIFIED":
            raise ValidationError("native RUN requires a verified master pixel SHA-256")
        roi_zip_sha = _require_sha(payload.get("roi_zip_sha256"), "roi_zip_sha256")
        n_count = _require_nonnegative(payload.get("N_count_valid"), "N_count_valid")
        n_size = _require_nonnegative(payload.get("N_size_valid", n_count), "N_size_valid")
        n_position = _require_nonnegative(
            payload.get("N_position_valid", n_count), "N_position_valid"
        )
        table_value = payload.get("cavity_objects_tsv")
        if table_value is None and n_count == n_size == n_position == 0:
            table_bytes = load_object_table_profile().header_bytes
        elif isinstance(table_value, bytes):
            table_bytes = table_value
        else:
            raise ValidationError(
                "non-empty native RUN requires explicit cavity_objects_tsv authority bytes"
            )
        net_area_nm2 = payload.get("net_area_nm2")
        if net_area_nm2 is None:
            raise ValidationError("native RUN requires explicit net_area_nm2")
        bin_contract = payload.get("bin_contract")
        if not isinstance(bin_contract, Mapping):
            raise ValidationError("native RUN requires an explicit bin_contract object")
        manifest_fields = {
            "analysis_session_id": record.analysis_session_id,
            "analysis_session_uid": record.analysis_session_uid,
            "bin_contract": dict(bin_contract),
            "density_N_per_m3_nominal": payload.get("density_N_per_m3_nominal"),
            "density_N_per_m3_nominal_status": payload.get(
                "density_N_per_m3_nominal_status", "NOT_APPLICABLE"
            ),
            "density_N_per_um2": payload.get("density_N_per_um2", 0),
            "density_ci_status": "NOT_COMPUTED",
            "density_intervals": [],
            "image_uid": image_uid,
            "master_pixel_sha256": binding["master_pixel_sha256"],
            "mean_size_nm": payload.get("mean_size_nm"),
            "mean_size_nm_status": payload.get(
                "mean_size_nm_status", "UNDEFINED" if n_size == 0 else "KNOWN"
            ),
            "N_count_valid": n_count,
            "N_position_valid": n_position,
            "N_size_valid": n_size,
            "net_area_nm2": net_area_nm2,
            "project_uid": self.project_uid,
            "revision_id": revision_manifest["revision_id"],
            "revision_manifest_sha256": revision_manifest_sha,
            "revision_uid": revision_manifest["revision_uid"],
            "roi_zip_sha256": roi_zip_sha,
            "run_id": rid,
            "run_uid": ruid,
            "source_sha256": binding["source_sha256"],
            "zero_event_status": "ZERO_EVENTS_VALID" if n_count == 0 else "EVENTS_PRESENT",
        }
        validation_fingerprint = sha256_bytes(
            canonical_json_bytes(
                {
                    "adapter": "CTL_RUN_V2_SCHEMA2_NATIVE_ADAPTER_V1",
                    "manifest_request": manifest_fields,
                    "object_table_sha256": sha256_bytes(table_bytes),
                }
            )
        )
        validation = ValidationEvidence(
            status="PASS",
            validated_at=timestamp,
            fingerprint_sha256=validation_fingerprint,
        )
        context = load_run_context(self.root, record.session_root)
        token = f"native_run_{rid}_{uuid.uuid4().hex}"
        journal_path = record.session_root / "journals" / f"JOURNAL_{token}.json"
        journal = {
            "analysis_session_uid": session_uid,
            "created_at": timestamp,
            "run_id": rid,
            "run_uid": ruid,
            "schema": "CTL_P2A_NATIVE_RUN_WRAPPER_JOURNAL_V1",
            "state": "PREPARED",
        }
        _write_new(journal_path, canonical_json_bytes(journal))

        def adapter_fault(stage: str, evidence: Mapping[str, Any]) -> None:
            if stage == "VERIFIED_STAGED":
                _call_fault(_fault, "RUN_BEFORE_PUBLISH", evidence)
            elif stage == "AFTER_COMPLETE_BEFORE_RENAME":
                if _staged_run_validator is not None:
                    partial = Path(str(evidence.get("partial", "")))
                    try:
                        partial.resolve(strict=True).relative_to(
                            record.session_root.resolve(strict=True)
                        )
                    except (OSError, ValueError) as exc:
                        raise ValidationError(
                            "native RUN staged path escapes its session"
                        ) from exc
                    staged = verify_run_directory(
                        partial,
                        allow_partial=True,
                        run_context=context,
                    )
                    outcome = _staged_run_validator(staged)
                    if outcome is False:
                        raise ValidationError(
                            "native RUN staged scientific validator returned false"
                        )
                _call_fault(
                    _fault,
                    "RUN_STAGED_COMPLETE_BEFORE_PUBLISH",
                    evidence,
                )
            elif stage == "AFTER_RENAME_BEFORE_POINTER":
                _call_fault(_fault, "RUN_BEFORE_POINTER", evidence)

        try:
            published = publish_p1_run(
                record.session_root / "runs",
                project_root=record.session_root,
                current_pointer_path=record.session_root / "current_run.tsv",
                registry_path=record.session_root / "run_registry.json",
                run_id=rid,
                run_uid=ruid,
                payloads={
                    "cavity_objects.tsv": PayloadSpec(
                        table_bytes,
                        "text/tab-separated-values; charset=utf-8",
                        "OBJECT_TABLE_AUTHORITY",
                    )
                },
                manifest_fields=manifest_fields,
                validation=validation,
                run_context=context,
                _fault=adapter_fault,
            )
            journal["state"] = "COMMITTED"
            journal["run_manifest_sha256"] = published.manifest_sha256
            _replace_exact(
                journal_path,
                canonical_json_bytes(journal),
                expected_sha256=sha256_file(journal_path),
                token=f"{token}_journal_commit",
            )
        except BaseException:
            final = record.session_root / "runs" / f"RUN_{rid}"
            partials = list((record.session_root / "runs").glob(f"RUN_{rid}.partial.*"))
            journal["state"] = (
                "PUBLISHED_UNPOINTED" if final.is_dir() else "FAILED_PARTIAL_RETAINED"
            )
            journal["retained_partial_count"] = len(partials)
            _replace_exact(
                journal_path,
                canonical_json_bytes(journal),
                expected_sha256=sha256_file(journal_path),
                token=f"{token}_journal_failure",
            )
            raise
        self._refresh_session_registry(image_uid, timestamp)
        self.refresh_storage_manifest()
        return PublishedRun(
            rid,
            ruid,
            published.manifest_sha256,
            published.run_path,
            published.pointer.generation,
        )

    def clone_revision_to_session(
        self,
        image_uid: str,
        *,
        source_session_uid: str,
        source_revision_uid: str,
        source_revision_manifest_sha256: str,
        destination_session_id: str,
        clone_transaction_id: str | None = None,
        created_at: str | None = None,
        uuid_factory: Callable[[], str] = new_uuid4_identity,
        _fault: FaultHook | None = None,
    ) -> CloneResult:
        self._reconcile_source_registry_journals()
        source = self.session_by_uid(image_uid, source_session_uid)
        _current_snapshot, snapshot_generation, snapshot_registry_sha = (
            self._selection_snapshot(image_uid)
        )
        source_revision_uid = _require_uuid(source_revision_uid, "source_revision_uid", version=4)
        source_revision_manifest_sha256 = _require_sha(
            source_revision_manifest_sha256, "source_revision_manifest_sha256"
        )
        pointer_rows = _parse_tsv(
            (source.session_root / "current_revision.tsv").read_bytes(), CURRENT_REVISION_FIELDS,
            allow_header_only=True,
        )
        matches = [
            row for row in pointer_rows
            if row["revision_uid"] == source_revision_uid
            and row["revision_manifest_sha256"] == source_revision_manifest_sha256
        ]
        if len(matches) != 1:
            # Explicit historical revisions may be selected by exact UID/hash;
            # scan manifests for equality, never by date/name preference.
            matches = []
            for revision_root in (source.session_root / "revisions").iterdir():
                if not revision_root.is_dir() or ".partial." in revision_root.name:
                    continue
                manifest = self._verify_revision(source, revision_root)
                digest = sha256_file(revision_root / "revision_manifest.json")
                if manifest["revision_uid"] == source_revision_uid and digest == source_revision_manifest_sha256:
                    matches.append(
                        {
                            "revision_id": manifest["revision_id"],
                            "relative_path": revision_root.relative_to(source.session_root).as_posix(),
                        }
                    )
        if len(matches) != 1:
            raise ValidationError("explicit revision UID/hash does not identify exactly one immutable revision")
        source_revision_root = _contained(source.session_root, matches[0]["relative_path"])
        source_manifest_bytes_before = stable_plain_bytes(
            source_revision_root / "revision_manifest.json",
            label="clone source revision manifest",
        )
        source_manifest = self._verify_revision(source, source_revision_root)
        if sha256_bytes(source_manifest_bytes_before) != source_revision_manifest_sha256:
            raise ValidationError("source revision hash changed during clone preflight")
        source_geometries: list[dict[str, Any]] | None = None
        if source_manifest.get("schema") == "CTL_P2A_REVISION_MANIFEST_V2":
            source_geometries = self._normalize_revision_geometries(
                source_manifest.get("geometries", [])
            )
            if source_geometries != source_manifest.get("geometries"):
                raise ValidationError("clone source geometry inventory is not canonical")
        destination_id = _safe_component(destination_session_id, "destination_session_id")
        registry_rows = self._read_registry(image_uid)
        if any(row["analysis_session_id"] == destination_id for row in registry_rows):
            raise ValidationError("destination session ID already exists")
        sessions_root = self._image_root(image_uid) / "sessions"
        try:
            _choose_new_session_directory(sessions_root, destination_id)
        except TransactionError as exc:
            raise ValidationError(
                "destination session ID has a final or retained partial"
            ) from exc
        timestamp = _require_timestamp(created_at or utc_now_z(), "created_at")
        destination_uid = _require_uuid(new_uuid4_identity(), "destination_session_uid", version=4)
        genesis_revision_uid = _require_uuid(uuid_factory(), "genesis_revision_uid", version=4)
        source_candidates = {item["candidate_uuid"]: item for item in source_manifest["candidates"]}
        source_objects = {item["object_uuid"]: item for item in source_manifest["objects"]}
        source_geometry_uids = {
            item["geometry_uid"] for item in (source_geometries or [])
        }
        source_mapping_uuids = set(source_candidates) | set(source_objects)
        source_identity_uuids = source_mapping_uuids | source_geometry_uids | {
            self.project_uid,
            image_uid,
            source.analysis_session_uid,
            source_revision_uid,
        }
        forbidden_existing_uuids = source_identity_uuids | self._identity_uuid_inventory()
        if destination_uid in forbidden_existing_uuids:
            raise ValidationError("destination session UUID reuses an existing/source identity")
        generated_uuids = {destination_uid}
        if genesis_revision_uid in forbidden_existing_uuids or genesis_revision_uid in generated_uuids:
            raise ValidationError("destination genesis revision UUID reuses an existing/source identity")
        generated_uuids.add(genesis_revision_uid)

        reconstructed_provenance = {
            "created_at": timestamp,
            "generation_method": "UUIDV4_RANDOM",
            "schema": "CTL_P2A_RECONSTRUCTED_IDENTITY_PROVENANCE_V1",
        }
        candidate_uuid_map: dict[str, str] = {}
        for source_candidate in source_manifest["candidates"]:
            source_candidate_uuid = source_candidate["candidate_uuid"]
            destination_candidate_uuid = _require_uuid(
                uuid_factory(), "destination_candidate_uuid", version=4
            )
            if destination_candidate_uuid in forbidden_existing_uuids or destination_candidate_uuid in generated_uuids:
                raise ValidationError("destination candidate UUID is reused or collides across domains")
            generated_uuids.add(destination_candidate_uuid)
            candidate_uuid_map[source_candidate_uuid] = destination_candidate_uuid

        object_uuid_map: dict[str, str] = {}
        destination_objects: list[dict[str, Any]] = []
        object_mappings: list[dict[str, Any]] = []
        cavity_ids: set[str] = set()
        for source_object in source_manifest["objects"]:
            cavity_id = validate_cavity_id(source_object["cavity_id"])
            if cavity_id in cavity_ids:
                raise ValidationError("clone cavity_id collision; silent renumbering is forbidden")
            cavity_ids.add(cavity_id)
            source_candidate_uuid = source_object["candidate_uuid"]
            if source_candidate_uuid is not None and source_candidate_uuid not in source_candidates:
                raise ValidationError("clone source object candidate is absent")
            destination_candidate_uuid = (
                None if source_candidate_uuid is None else candidate_uuid_map[source_candidate_uuid]
            )
            destination_object_uuid = _require_uuid(uuid_factory(), "destination_object_uuid", version=4)
            if destination_object_uuid in forbidden_existing_uuids or destination_object_uuid in generated_uuids:
                raise ValidationError("destination object UUID is reused or collides across domains")
            generated_uuids.add(destination_object_uuid)
            object_uuid_map[source_object["object_uuid"]] = destination_object_uuid
            destination = {
                key: value for key, value in source_object.items()
                if key not in {"object_sha256", "identity_provenance", "object_uuid", "candidate_uuid"}
            }
            destination.update(
                {
                    "candidate_uuid": destination_candidate_uuid,
                    "cavity_id": cavity_id,
                    "identity_provenance": reconstructed_provenance,
                    "object_uuid": destination_object_uuid,
                }
            )
            destination_hash = _entity_record_sha256(destination, "object_sha256")
            destination["object_sha256"] = destination_hash
            object_mappings.append(
                {
                    "cavity_id_destination": cavity_id,
                    "cavity_id_source": cavity_id,
                    "destination_object_sha256": destination_hash,
                    "destination_object_uuid": destination_object_uuid,
                    "source_object_sha256": source_object["object_sha256"],
                    "source_object_uuid": source_object["object_uuid"],
                }
            )
            destination_objects.append(destination)
        object_mappings.sort(key=lambda item: item["source_object_uuid"])
        destination_objects.sort(key=lambda item: item["object_uuid"])

        destination_candidates: list[dict[str, Any]] = []
        candidate_mappings: list[dict[str, Any]] = []
        candidate_ids: set[str] = set()
        for source_candidate in source_manifest["candidates"]:
            source_candidate_uuid = source_candidate["candidate_uuid"]
            candidate_id = _safe_component(source_candidate["candidate_id"], "candidate_id")
            if candidate_id in candidate_ids:
                raise ValidationError("clone candidate_id collision; silent renumbering is forbidden")
            candidate_ids.add(candidate_id)
            source_link_status, source_object_uuid = _candidate_link_status(
                source_candidate, prefix=f"source_candidate.{candidate_id}"
            )
            destination_object_uuid = (
                None if source_object_uuid is None else object_uuid_map.get(source_object_uuid)
            )
            if source_link_status == "LINKED_OBJECT" and destination_object_uuid is None:
                raise ValidationError("clone candidate links an absent source object")
            destination_candidate_uuid = candidate_uuid_map[source_candidate_uuid]
            destination = {
                key: value for key, value in source_candidate.items()
                if key not in {"candidate_sha256", "candidate_uuid", "identity_provenance", "object_uuid"}
            }
            destination.update(
                {
                    "candidate_id": candidate_id,
                    "candidate_uuid": destination_candidate_uuid,
                    "identity_provenance": reconstructed_provenance,
                    "object_uuid": destination_object_uuid,
                }
            )
            destination_hash = _entity_record_sha256(destination, "candidate_sha256")
            destination["candidate_sha256"] = destination_hash
            destination_candidates.append(destination)
            candidate_mappings.append(
                {
                    "destination_candidate_id": candidate_id,
                    "destination_candidate_sha256": destination_hash,
                    "destination_candidate_uuid": destination_candidate_uuid,
                    "destination_object_link_status": source_link_status,
                    "destination_object_uuid": destination_object_uuid,
                    "destination_review_decision": source_candidate["review_decision"],
                    "destination_review_status": source_candidate["review_status"],
                    "source_candidate_id": candidate_id,
                    "source_candidate_sha256": source_candidate["candidate_sha256"],
                    "source_candidate_uuid": source_candidate_uuid,
                    "source_object_link_status": source_link_status,
                    "source_object_uuid": source_object_uuid,
                    "source_review_decision": source_candidate["review_decision"],
                    "source_review_status": source_candidate["review_status"],
                }
            )
        candidate_mappings.sort(key=lambda item: item["source_candidate_uuid"])
        destination_candidates.sort(key=lambda item: item["candidate_uuid"])

        destination_geometries = (
            None
            if source_geometries is None
            else [dict(item) for item in source_geometries]
        )
        geometry_mappings: list[dict[str, Any]] = []
        for source_geometry in source_geometries or []:
            geometry_mappings.append(
                {
                    "destination_geometry_id": source_geometry["geometry_id"],
                    "destination_geometry_roi_bytes_sha256": source_geometry[
                        "roi_bytes_sha256"
                    ],
                    "destination_geometry_schema": source_geometry["geometry_schema"],
                    "destination_geometry_sha256": source_geometry["geometry_sha256"],
                    "destination_geometry_source_roi_sha256": source_geometry[
                        "source_roi_sha256"
                    ],
                    "destination_geometry_type": source_geometry["geometry_type"],
                    "destination_geometry_uid": source_geometry["geometry_uid"],
                    "identity_disposition": CLONE_GEOMETRY_IDENTITY_DISPOSITION,
                    "source_geometry_id": source_geometry["geometry_id"],
                    "source_geometry_roi_bytes_sha256": source_geometry[
                        "roi_bytes_sha256"
                    ],
                    "source_geometry_schema": source_geometry["geometry_schema"],
                    "source_geometry_sha256": source_geometry["geometry_sha256"],
                    "source_geometry_source_roi_sha256": source_geometry[
                        "source_roi_sha256"
                    ],
                    "source_geometry_type": source_geometry["geometry_type"],
                    "source_geometry_uid": source_geometry["geometry_uid"],
                }
            )
        geometry_mappings.sort(key=lambda item: item["source_geometry_uid"])

        binding = self._binding(image_uid)
        destination_record = SessionRecord(
            self.project_uid, image_uid, destination_uid, destination_id,
            self._session_root(image_uid, destination_id), 0,
        )
        genesis_manifest = self._revision_manifest(
            record=destination_record,
            revision_id="REV_000001",
            revision_uid=genesis_revision_uid,
            parent_revision_id="NOT_APPLICABLE",
            objects=destination_objects,
            candidates=destination_candidates,
            created_at=timestamp,
            source_sha256=binding["source_sha256"],
            identity_provenance=[
                {
                    "created_at": timestamp,
                    "generation_method": "RECONSTRUCTED",
                    "owner": "DESTINATION_GENESIS_REVISION",
                }
            ],
            geometries=destination_geometries,
        )
        genesis_manifest_bytes = canonical_json_bytes(genesis_manifest)
        genesis_sha = sha256_bytes(genesis_manifest_bytes)
        if clone_transaction_id is None:
            clone_transaction_id = "CLONE_" + uuid.uuid4().hex.upper()
        else:
            clone_transaction_id = _safe_component(clone_transaction_id, "clone_transaction_id")
        clone_provenance = {
            "candidate_mappings": candidate_mappings,
            "clone_mode": "COPY_TO_NEW_SESSION_WITH_NEW_GENESIS_REVISION",
            "clone_transaction_id": clone_transaction_id,
            "created_at": timestamp,
            "destination": {
                "genesis_revision_id": "REV_000001",
                "genesis_revision_manifest_sha256": genesis_sha,
                "genesis_revision_uid": genesis_revision_uid,
                "identity_provenance_mode": "RECONSTRUCTED",
                "session_id": destination_id,
                "session_uid": destination_uid,
                "working_state_id": "WORKING_000001",
            },
            "object_mappings": object_mappings,
            "schema": "CTL_SESSION_CLONE_PROVENANCE_V2",
            "source": {
                "candidate_count": len(source_candidates),
                "candidate_uuids": sorted(source_candidates),
                "object_count": len(source_objects),
                "object_uuids": sorted(source_objects),
                "revision_id": source_manifest["revision_id"],
                "revision_manifest_sha256": source_revision_manifest_sha256,
                "revision_uid": source_revision_uid,
                "session_id": source.analysis_session_id,
                "session_uid": source.analysis_session_uid,
            },
        }
        if source_geometries is not None:
            source_geometry_set_sha = self.geometry_set_sha256(source_geometries)
            destination_geometry_set_sha = self.geometry_set_sha256(
                destination_geometries or []
            )
            clone_provenance["schema"] = CLONE_PROVENANCE_V3_SCHEMA
            clone_provenance["geometry_mappings"] = geometry_mappings
            clone_provenance["source"].update(
                {
                    "geometry_count": len(source_geometries),
                    "geometry_set_sha256": source_geometry_set_sha,
                    "geometry_uids": sorted(source_geometry_uids),
                }
            )
            clone_provenance["destination"].update(
                {
                    "geometry_count": len(destination_geometries or []),
                    "geometry_identity_mode": CLONE_GEOMETRY_IDENTITY_MODE,
                    "geometry_set_sha256": destination_geometry_set_sha,
                    "geometry_uids": sorted(
                        item["geometry_uid"] for item in (destination_geometries or [])
                    ),
                }
            )
        _validate_clone_provenance(
            clone_provenance, source_manifest, genesis_manifest
        )
        if stable_plain_bytes(
            source_revision_root / "revision_manifest.json",
            label="clone source revision manifest",
        ) != source_manifest_bytes_before:
            raise TransactionError("clone source revision changed before destination staging")
        partial, _metadata = self._new_session_partial(
            binding,
            session_id=destination_id,
            session_uid=destination_uid,
            origin_type="CLONE_REVISION",
            canonical_role="NON_CANONICAL",
            created_at=timestamp,
            clone_provenance=clone_provenance,
            working_objects=destination_objects,
            working_candidates=destination_candidates,
            base_revision_sha256=genesis_sha,
            working_geometries=destination_geometries,
        )
        clone_journal = {
            "clone_transaction_id": clone_transaction_id,
            "destination_session_uid": destination_uid,
            "genesis_revision_manifest_sha256": genesis_sha,
            "schema": "CTL_P2A_CLONE_PREPUBLICATION_JOURNAL_V1",
            "source_revision_manifest_sha256": source_revision_manifest_sha256,
            "state": "PREPARED",
        }
        clone_journal_path = partial / "journals" / f"JOURNAL_clone_{clone_transaction_id}.json"
        _write_new(clone_journal_path, canonical_json_bytes(clone_journal))
        revision_root = partial / "revisions" / "REV_REV_000001"
        revision_root.mkdir()
        _write_new(revision_root / "revision_manifest.json", genesis_manifest_bytes)
        _write_new(revision_root / "REVISION_SHA256.txt", f"{genesis_sha}  revision_manifest.json\n".encode("ascii"))
        _write_new(
            revision_root / "COMPLETE",
            canonical_json_bytes(
                {
                    "analysis_session_uid": destination_uid,
                    "revision_manifest_sha256": genesis_sha,
                    "revision_uid": genesis_revision_uid,
                    "schema": "CTL_P2A_REVISION_COMPLETE_V1",
                }
            ),
        )
        revision_pointer = {
            "pointer_version": 1,
            "project_uid": self.project_uid,
            "image_uid": image_uid,
            "analysis_session_uid": destination_uid,
            "revision_uid": genesis_revision_uid,
            "revision_id": "REV_000001",
            "relative_path": "revisions/REV_REV_000001",
            "revision_manifest_sha256": genesis_sha,
            "generation": 1,
            "updated_at": timestamp,
        }
        # Replace the header-only file while the destination remains .partial.
        partial_pointer = partial / "current_revision.tsv"
        _replace_exact(
            partial_pointer,
            _tsv_bytes(CURRENT_REVISION_FIELDS, [revision_pointer]),
            expected_sha256=sha256_file(partial_pointer),
            token=f"clone_revision_pointer_{uuid.uuid4().hex}",
        )
        partial_record = SessionRecord(
            self.project_uid, image_uid, destination_uid, destination_id, partial, 0,
        )
        verified_genesis = self._verify_revision(partial_record, revision_root)
        verified_provenance = _canonical_read(partial / "clone_provenance.json")
        _validate_clone_provenance(
            verified_provenance, source_manifest, verified_genesis
        )
        working = _canonical_read(partial / "working" / "working_state.json")
        expected_working_schema = (
            "CTL_P2A_WORKING_STATE_V1"
            if source_geometries is None
            else "CTL_P2A_WORKING_STATE_V2"
        )
        geometry_state_differs = (
            "geometries" in working
            if source_geometries is None
            else working.get("geometries") != verified_genesis.get("geometries")
        )
        if (
            working.get("schema") != expected_working_schema
            or working.get("base_revision_manifest_sha256") != genesis_sha
            or working.get("objects") != verified_genesis["objects"]
            or working.get("candidates") != verified_genesis["candidates"]
            or geometry_state_differs
        ):
            raise ValidationError("clone destination working state differs from verified genesis")
        if stable_plain_bytes(
            source_revision_root / "revision_manifest.json",
            label="clone source revision manifest",
        ) != source_manifest_bytes_before:
            raise TransactionError("clone source revision changed during destination staging")
        _current_before_publish, observed_generation, observed_registry_sha = (
            self._selection_snapshot(image_uid)
        )
        if (
            observed_generation != snapshot_generation
            or observed_registry_sha != snapshot_registry_sha
        ):
            raise StaleContextError("session selection authority changed during clone staging")
        clone_journal["state"] = "VERIFIED_READY_TO_PUBLISH"
        _replace_exact(
            clone_journal_path,
            canonical_json_bytes(clone_journal),
            expected_sha256=sha256_file(clone_journal_path),
            token=f"clone_journal_{uuid.uuid4().hex}",
        )
        _call_fault(_fault, "CLONE_DESTINATION_VERIFIED_PARTIAL", {"destination_session_uid": destination_uid})
        final = partial.parent / partial.name.split(".partial.", 1)[0]
        rename_directory_no_replace(partial, final, error_type=TransactionError)
        _fsync_directory(final.parent)
        final_record = SessionRecord(self.project_uid, image_uid, destination_uid, destination_id, final, 0)
        self._verify_revision(final_record, final / "revisions" / "REV_REV_000001")
        if sha256_bytes(source_manifest_bytes_before) != sha256_file(source_revision_root / "revision_manifest.json"):
            raise TransactionError("clone mutated source revision")
        final_clone_journal_path = final / "journals" / clone_journal_path.name
        clone_journal["state"] = "DESTINATION_PUBLISHED_UNSELECTED"
        _replace_exact(
            final_clone_journal_path,
            canonical_json_bytes(clone_journal),
            expected_sha256=sha256_file(final_clone_journal_path),
            token=f"clone_published_{uuid.uuid4().hex}",
        )
        self._select_published_session(
            binding, final,
            expected_current_generation=snapshot_generation,
            expected_registry_sha256=snapshot_registry_sha,
            created_at=timestamp,
            _fault=_fault,
        )
        clone_journal["state"] = "COMMITTED"
        _replace_exact(
            final_clone_journal_path,
            canonical_json_bytes(clone_journal),
            expected_sha256=sha256_file(final_clone_journal_path),
            token=f"clone_committed_{uuid.uuid4().hex}",
        )
        self.refresh_storage_manifest()
        current = self._read_current_session(image_uid)
        assert current is not None
        result_record = SessionRecord(
            self.project_uid, image_uid, destination_uid, destination_id, final, current["generation"]
        )
        return CloneResult(
            result_record,
            PublishedRevision("REV_000001", genesis_revision_uid, genesis_sha, final / "revisions" / "REV_REV_000001", 1),
            sha256_file(final / "clone_provenance.json"),
            tuple(object_mappings),
            tuple(candidate_mappings),
            tuple(geometry_mappings),
        )

    def refresh_storage_manifest(self, *, _source_recovery_checked: bool = False) -> None:
        if not _source_recovery_checked:
            self._reconcile_source_registry_journals(refresh_manifest=False)
        artifacts: list[dict[str, Any]] = []
        profile_by_name = {
            "project.json": "CTL_P2A_PROJECT_JSON_V1",
            "source_registry.json": "CTL_SOURCE_REGISTRY_V1",
            "source.bin": "CTL_IMMUTABLE_SOURCE_BLOB_V1",
            "study.json": "CTL_P2A_STUDY_JSON_V1",
            "condition.json": "CTL_P2A_CONDITION_JSON_V1",
            "specimen.json": "CTL_P2A_SPECIMEN_JSON_V1",
            "lamella.json": "CTL_P2A_LAMELLA_JSON_V1",
            "image.json": "CTL_P2A_IMAGE_JSON_V1",
            "session_registry.tsv": "CTL_SESSION_REGISTRY_TSV_V1",
            "current_session.tsv": "CTL_CURRENT_SESSION_TSV_V1",
            "session_metadata.json": "CTL_SESSION_METADATA_JSON_V1",
            "current_revision.tsv": "CTL_CURRENT_REVISION_TSV_V1",
            "current_run.tsv": "P1_TEN_COLUMN_CURRENT_RUN_TSV_LITERAL",
            "run_registry.json": "P1_RUN_REGISTRY_V1",
            "run_manifest.json": "CTL_RUN_V2_SCHEMA2_NATIVE_ADAPTER_V1",
            "cavity_objects.tsv": "CTL_CAVITY_OBJECTS_TSV_PROFILE_V1",
            "REVISION_SHA256.txt": "SHA256_SIDECAR",
            "RUN_SHA256.txt": "SHA256_SIDECAR",
            "COMPLETE": "IMMUTABLE_COMPLETE_MARKER",
        }
        schema_profiles_by_name = {
            "clone_provenance.json": {
                "CTL_SESSION_CLONE_PROVENANCE_V2",
                CLONE_PROVENANCE_V3_SCHEMA,
            },
            "working_state.json": {
                "CTL_P2A_WORKING_STATE_V1",
                "CTL_P2A_WORKING_STATE_V2",
            },
            "revision_manifest.json": {
                "CTL_P2A_REVISION_MANIFEST_V1",
                "CTL_P2A_REVISION_MANIFEST_V2",
            },
        }
        ignored_names = {"schema_v2_storage_manifest.json"}
        for path in sorted(self.root.rglob("*"), key=lambda item: item.relative_to(self.root).as_posix()):
            if not path.is_file() or path.name in ignored_names:
                continue
            relative_parts = path.relative_to(self.root).parts
            if _is_excluded_operational_path(relative_parts):
                continue
            relative = path.relative_to(self.root).as_posix()
            allowed_schema_profiles = schema_profiles_by_name.get(path.name)
            if allowed_schema_profiles is not None:
                value = _canonical_read(path)
                profile = value.get("schema") if isinstance(value, Mapping) else None
                if profile not in allowed_schema_profiles:
                    raise ValidationError(
                        "schema-bearing authority file selects an unsupported profile",
                        details={"relative_path": relative, "profile_id": profile},
                    )
            else:
                profile = profile_by_name.get(path.name)
            if (
                profile is None
                and len(relative_parts) >= 2
                and relative_parts[-2] == "run_dispositions"
                and is_run_disposition_file_name(path.name)
            ):
                profile = DISPOSITION_SCHEMA
            if profile is None:
                raise ValidationError("undeclared authority file blocks storage manifest", details={"relative_path": relative})
            artifacts.append({"authority": True, "path": relative, "profile_id": profile})
        manifest = {
            "artifacts": artifacts,
            "project_schema_version": 2,
            "project_uid": self.project_uid,
            "schema": "CTL_SCHEMA_V2_STORAGE_MANIFEST_V1",
            "storage_profile_id": "CTL_SCHEMA_V2_STORAGE_PROFILE_V1",
        }
        data = canonical_json_bytes(manifest)
        path = self.root / "schema_v2_storage_manifest.json"
        if not path.exists():
            _write_new(path, data)
        elif path.read_bytes() != data:
            _replace_exact(
                path, data, expected_sha256=sha256_file(path),
                token=f"storage_manifest_{uuid.uuid4().hex}",
            )


def _validate_pointer_coherence(core: SessionCore, binding: Mapping[str, Any]) -> tuple[int, int, int]:
    image_uid = binding["image_uid"]
    image_root = _contained(core.root, binding["image_relative_path"])
    rows = core._read_registry(image_uid)
    sessions_root = image_root / "sessions"
    declared_session_roots = {
        _contained(image_root, row["relative_path"]): row for row in rows
    }
    actual_session_roots: set[Path] = set()
    for path in sessions_root.iterdir():
        if not path.is_dir() or path.is_symlink():
            continue
        if ".partial." in path.name:
            continue
        if not path.name.startswith("SESSION_"):
            raise ValidationError(
                "undeclared final directory exists under sessions",
                details={"name": path.name},
            )
        actual_session_roots.add(path)
    if actual_session_roots != set(declared_session_roots):
        raise ValidationError(
            "session registry does not exactly cover final session directories",
            details={
                "missing": sorted(str(path) for path in actual_session_roots - set(declared_session_roots)),
                "extra": sorted(str(path) for path in set(declared_session_roots) - actual_session_roots),
            },
        )
    current = core._read_current_session(image_uid)
    current_rows = [row for row in rows if row["lifecycle"] == "CURRENT"]
    if (current is None) != (len(current_rows) == 0) or len(current_rows) > 1:
        raise ValidationError("current session pointer/registry cardinality mismatch")
    if current is not None:
        row = current_rows[0]
        if current["pointer_version"] != 1 or current["project_uid"] != core.project_uid or current["image_uid"] != image_uid:
            raise ValidationError("current session pointer scope mismatch")
        for field in ("analysis_session_uid", "analysis_session_id", "relative_path", "session_metadata_sha256"):
            if current[field] != str(row[field]):
                raise ValidationError("current session pointer/registry identity mismatch", details={"field": field})
        if current["generation"] != row["generation"] or current["session_registry_sha256"] != sha256_file(core._registry_path(image_uid)):
            raise ValidationError("current session pointer/registry generation or hash mismatch")
        _require_timestamp(current["updated_at"], "current_session.updated_at")
        session_root = _contained(image_root, current["relative_path"])
        if not _session_directory_matches_id(
            session_root.name, current["analysis_session_id"]
        ):
            raise ValidationError("current session relative path does not bind ID")
    session_count = revision_count = run_count = 0
    for row in rows:
        session_root = _contained(image_root, row["relative_path"])
        metadata = core._metadata(session_root)
        if metadata["analysis_session_uid"] != row["analysis_session_uid"] or metadata["image_uid"] != image_uid:
            raise ValidationError("session metadata/registry identity mismatch")
        if sha256_file(session_root / "session_metadata.json") != row["session_metadata_sha256"]:
            raise ValidationError("session metadata/registry hash mismatch")
        if (
            metadata["lifecycle"] != row["lifecycle"]
            or metadata["canonical_role"] != row["canonical_role"]
            or metadata["source_sha256"] != binding["source_sha256"]
        ):
            raise ValidationError("session metadata/registry/source semantics mismatch")
        for required_dir in ("working", "autosave", "journals", "recovery", "revisions", "runs"):
            path = session_root / required_dir
            if not path.is_dir() or path.is_symlink():
                raise ValidationError("session root is incomplete", details={"directory": required_dir})

        revision_roots = sorted(
            (
                path
                for path in (session_root / "revisions").iterdir()
                if path.is_dir()
                and not path.is_symlink()
                and not _is_excluded_operational_path(
                    path.relative_to(session_root).parts
                )
            ),
            key=lambda path: path.name,
        )
        record = SessionRecord(
            core.project_uid,
            image_uid,
            row["analysis_session_uid"],
            row["analysis_session_id"],
            session_root,
            row["generation"],
        )
        revisions_by_id: dict[str, tuple[dict[str, Any], Path, str]] = {}
        revisions_by_uid: dict[str, tuple[dict[str, Any], Path, str]] = {}
        for revision_root in revision_roots:
            manifest = core._verify_revision(record, revision_root)
            digest = sha256_file(revision_root / "revision_manifest.json")
            revision_id = manifest["revision_id"]
            revision_uid = manifest["revision_uid"]
            if revision_id in revisions_by_id or revision_uid in revisions_by_uid:
                raise ValidationError("revision identity repeats inside a session")
            if manifest["source_sha256"] != binding["source_sha256"]:
                raise ValidationError("historical revision source binding mismatch")
            revisions_by_id[revision_id] = (manifest, revision_root, digest)
            revisions_by_uid[revision_uid] = (manifest, revision_root, digest)
        if revisions_by_id:
            genesis = [
                manifest
                for manifest, _path, _digest in revisions_by_id.values()
                if manifest["parent_revision_id"] == "NOT_APPLICABLE"
            ]
            if len(genesis) != 1:
                raise ValidationError("revision history must contain exactly one genesis")
            for manifest, _path, _digest in revisions_by_id.values():
                parent_id = manifest["parent_revision_id"]
                if parent_id != "NOT_APPLICABLE" and parent_id not in revisions_by_id:
                    raise ValidationError("revision history references an absent parent")
                visited: set[str] = set()
                cursor = manifest
                while cursor["parent_revision_id"] != "NOT_APPLICABLE":
                    parent_id = cursor["parent_revision_id"]
                    if parent_id in visited:
                        raise ValidationError("revision history contains a cycle")
                    visited.add(parent_id)
                    cursor = revisions_by_id[parent_id][0]
        revision_rows = _parse_tsv(
            stable_plain_bytes(
                session_root / "current_revision.tsv",
                label="current revision pointer",
            ),
            CURRENT_REVISION_FIELDS,
            allow_header_only=True,
        )
        if len(revision_rows) > 1:
            raise ValidationError("current revision pointer has multiple rows")
        if bool(revision_rows) != bool(revisions_by_id):
            raise ValidationError("current revision pointer/history cardinality mismatch")
        if revision_rows:
            pointer = revision_rows[0]
            if pointer["project_uid"] != core.project_uid or pointer["image_uid"] != image_uid or pointer["analysis_session_uid"] != row["analysis_session_uid"]:
                raise ValidationError("current revision scope mismatch")
            _require_positive(int(pointer["generation"]), "revision_pointer.generation")
            _require_timestamp(pointer["updated_at"], "revision_pointer.updated_at")
            revision_root = _contained(session_root, pointer["relative_path"])
            manifest = core._verify_revision(record, revision_root)
            if (
                manifest["revision_uid"] != pointer["revision_uid"]
                or manifest["revision_id"] != pointer["revision_id"]
                or sha256_file(revision_root / "revision_manifest.json")
                != pointer["revision_manifest_sha256"]
            ):
                raise ValidationError("current revision pointer target mismatch")

        pointer_path = session_root / "current_run.tsv"
        run_registry_path = session_root / "run_registry.json"
        if pointer_path.exists() != run_registry_path.exists():
            raise ValidationError("RUN pointer and registry must be jointly absent or present")
        run_roots = sorted(
            (
                path
                for path in (session_root / "runs").iterdir()
                if path.is_dir()
                and not path.is_symlink()
                and not _is_excluded_operational_path(
                    path.relative_to(session_root).parts
                )
            ),
            key=lambda path: path.name,
        )
        verified_runs: dict[str, Any] = {}
        current_run: Any | None = None
        if not pointer_path.exists():
            if run_roots:
                raise ValidationError("final RUN exists without its P1 registry/pointer controls")
        else:
            run_context = load_run_context(core.root, session_root)
            registry_value = RunRegistry(run_registry_path).load()
            registry_records = registry_value["runs"]
            expected_run_paths = {
                _contained(session_root, item["relative_path"]): item
                for item in registry_records
            }
            if set(run_roots) != set(expected_run_paths):
                raise ValidationError("RUN registry does not exactly cover final RUN directories")

            def verify_revision_binding(run_manifest: Mapping[str, Any]) -> bool:
                match = revisions_by_uid.get(str(run_manifest.get("revision_uid")))
                if match is None:
                    raise ValidationError("RUN references an absent immutable revision")
                revision_manifest, _revision_root, revision_digest = match
                if (
                    revision_manifest["revision_id"] != run_manifest.get("revision_id")
                    or revision_digest != run_manifest.get("revision_manifest_sha256")
                    or run_manifest.get("source_sha256") != binding["source_sha256"]
                    or run_manifest.get("master_pixel_sha256") != binding["master_pixel_sha256"]
                ):
                    raise ValidationError("RUN revision/master/source trust chain mismatch")
                return True

            for run_root in run_roots:
                verified = verify_run_directory(
                    run_root,
                    registry_path=run_registry_path,
                    revision_verifier=verify_revision_binding,
                    run_context=run_context,
                )
                if verified.manifest["run_uid"] in verified_runs:
                    raise ValidationError("RUN UUID repeats inside a session")
                verified_runs[verified.manifest["run_uid"]] = verified
            current_run = load_current_run(
                session_root,
                pointer_path,
                registry_path=run_registry_path,
                revision_verifier=verify_revision_binding,
                run_context=run_context,
            )
            if current_run.manifest["run_uid"] not in verified_runs:
                raise ValidationError("current RUN pointer target is outside verified history")

        dispositions = validate_run_disposition_directory(
            session_root,
            verified_runs.values(),
        )
        disposed_run_uids = {item.run_uid for item in dispositions}
        if current_run is not None and current_run.run_uid in disposed_run_uids:
            raise ValidationError(
                "current RUN is scientifically invalidated by an external disposition",
                details={"run_uid": current_run.run_uid},
            )

        measured = core._session_stats(session_root)
        for field in ("object_count", "revision_count", "run_count", "logical_bytes", "physical_bytes"):
            if row[field] != measured[field]:
                raise ValidationError(
                    "session registry derived counter mismatch",
                    details={"field": field, "expected": measured[field], "actual": row[field]},
                )
        session_count += 1
        revision_count += len(revision_roots)
        run_count += len(run_roots)
    return session_count, revision_count, run_count


def validate_project(project_root: os.PathLike[str] | str) -> ProjectValidation:
    """Read-only full P2A project validator.

    The function deliberately performs no recovery, manifest refresh, timestamp
    update or cache write.  Callers can hash the tree before and after and will
    obtain byte-identical snapshots.
    """

    core = SessionCore(project_root)
    _assert_safe_published_tree(core.root)
    before = snapshot_tree(core.root)
    registry = core._source_registry()
    core._validate_source_registry_journals(registry, allow_pending=False)
    core._validate_source_tree_coverage(registry)
    core._validate_source_blob_coverage(registry)
    images = sessions = revisions = runs = 0
    for binding in registry["image_bindings"]:
        image_root = _contained(core.root, binding["image_relative_path"])
        descriptor = _canonical_read(image_root / "image.json")
        if descriptor.get("image_uid") != binding["image_uid"] or descriptor.get("source_sha256") != binding["source_sha256"]:
            raise ValidationError("image descriptor/source binding mismatch")
        counts = _validate_pointer_coherence(core, binding)
        images += 1
        sessions += counts[0]; revisions += counts[1]; runs += counts[2]
    manifest_path = core.root / "schema_v2_storage_manifest.json"
    manifest = _canonical_read(manifest_path)
    if set(manifest) != {"artifacts", "project_schema_version", "project_uid", "schema", "storage_profile_id"}:
        raise ValidationError("storage manifest top-level inventory mismatch")
    if manifest["project_schema_version"] != 2 or manifest["project_uid"] != core.project_uid:
        raise ValidationError("storage manifest project identity mismatch")
    if manifest["schema"] != "CTL_SCHEMA_V2_STORAGE_MANIFEST_V1" or manifest["storage_profile_id"] != "CTL_SCHEMA_V2_STORAGE_PROFILE_V1":
        raise ValidationError("storage manifest profile identity mismatch")
    listed = [item["path"] for item in manifest["artifacts"]]
    if listed != sorted(listed) or len(listed) != len(set(listed)):
        raise ValidationError("storage manifest artifacts are unsorted or duplicated")
    for item in manifest["artifacts"]:
        if set(item) != {"authority", "path", "profile_id"} or item["authority"] is not True:
            raise ValidationError("storage manifest artifact binding is invalid")
        path = _contained(core.root, item["path"])
        try:
            plain_file(path, label="storage manifest authority", single_link=True)
        except PathSafetyError as exc:
            raise ValidationError("storage manifest declares absent/unsafe authority")
    # Independent reconstruction of the closed, non-journal authority inventory.
    actual = []
    for path in sorted(core.root.rglob("*"), key=lambda item: item.relative_to(core.root).as_posix()):
        if not path.is_file() or path.name == "schema_v2_storage_manifest.json":
            continue
        relative_parts = path.relative_to(core.root).parts
        if _is_excluded_operational_path(relative_parts):
            continue
        relative = path.relative_to(core.root).as_posix()
        actual.append(relative)
    if listed != actual:
        raise ValidationError(
            "storage manifest is not the exact closed authority inventory",
            details={"missing": sorted(set(actual) - set(listed)), "extra": sorted(set(listed) - set(actual))},
        )
    after = snapshot_tree(core.root)
    if before != after:
        raise ValidationError("read-only project validator mutated its input")
    return ProjectValidation(core.project_uid, images, sessions, revisions, runs, len(listed))
