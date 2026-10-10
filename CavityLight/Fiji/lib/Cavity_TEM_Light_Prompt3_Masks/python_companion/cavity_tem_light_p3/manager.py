"""Closed Prompt-3 bridge over the accepted Prompt-2 vertical manager."""

from __future__ import annotations

from dataclasses import asdict
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Mapping, Sequence
import argparse
import base64
from decimal import Decimal
import hashlib
import os
import sys
import uuid

from cavity_tem_light_p1.canonical_json import canonical_json_bytes, loads_canonical_json
from cavity_tem_light_p1.errors import StaleContextError, TransactionError, ValidationError
from cavity_tem_light_p1.path_safety import (
    PathSafetyError, plain_directory, plain_file, rename_file_no_replace, stable_plain_bytes,
)
from cavity_tem_light_p1.run_disposition import find_run_disposition
from cavity_tem_light_p2 import vertical_manager as p2
from cavity_tem_light_p2.session_core import (
    CURRENT_REVISION_FIELDS,
    SessionCore,
    _replace_exact,
    _require_timestamp,
    _write_new,
    _validate_clone_provenance,
    sha256_file,
    snapshot_tree,
    utc_now_z,
)

from .mask_visibility import (
    _positive_int,
    area_cache_for_run,
    commit_analysis_area_cache,
    prepare_geometry_state,
    set_display_mode,
)
from .run_disposition import (
    _verified_session_runs,
    publish_run_disposition,
    publish_run_disposition_request,
)
from .run_recovery import reconcile_failed_run_reservation_request
from .onboarding import (
    create_project as p3_create_project,
    register_source_image as p3_register_source_image,
    source_image_context as p3_source_image_context,
)
from .run_science import ScientificScaleMismatch, verify_run_scientific_scale
from .spatial_scale import (
    decimal_text,
    normalize_spatial_calibration,
    revision_legacy_scale,
    scales_agree,
    transient_physical_objects,
    validate_revision_scale_snapshot,
    verify_spatial_scale_provenance,
)


REQUEST_SCHEMA = "CTL_P3_MASKS_BRIDGE_REQUEST_V1"
RESPONSE_SCHEMA = "CTL_P3_MASKS_BRIDGE_RESPONSE_V1"


def _mapping(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValidationError(f"{label} must be an object")
    return value


def _augment_geometry_state(
    result: dict[str, Any], arguments: Mapping[str, Any], session_uid: str | None
) -> dict[str, Any]:
    if session_uid is None or not isinstance(arguments.get("image_context"), Mapping):
        result["geometry_state"] = None
        return result
    request = {
        "analysis_session_uid": session_uid,
        "image_context": dict(arguments["image_context"]),
        "image_uid": str(arguments["image_uid"]),
        "project_root": arguments["project_root"],
    }
    result["geometry_state"] = prepare_geometry_state(request)
    return result


def _verified_clone_roi_identity_bridge(
    project_root: str | Path,
    image_uid: str,
    session_uid: str,
    objects: Sequence[Any],
) -> dict[str, Any] | None:
    """Expose the narrow, verified identity bridge required by clone payloads.

    Clone provenance V2/V3 deliberately assigns new destination object UUIDs
    while preserving every non-identity object field.  For ImageJ-backed
    objects that includes the immutable source ROI bytes, whose embedded
    ``Object_uuid`` therefore remains the source UUID.  The bridge is a
    transient response-only view of the already approved 1:1 provenance; it
    never rewrites a revision, working state, or ROI payload on disk.
    """

    core = SessionCore(project_root)
    record = core.session_by_uid(str(image_uid), str(session_uid))
    metadata_path = record.session_root / "session_metadata.json"
    metadata = loads_canonical_json(
        stable_plain_bytes(metadata_path, label="clone session metadata")
    )
    if metadata.get("clone_provenance_status") != "VERIFIED":
        return None

    clone_path = record.session_root / "clone_provenance.json"
    clone_bytes = stable_plain_bytes(clone_path, label="clone provenance")
    clone_sha = hashlib.sha256(clone_bytes).hexdigest()
    if clone_sha != metadata.get("clone_provenance_sha256"):
        raise ValidationError("clone ROI identity bridge provenance hash mismatch")
    provenance = loads_canonical_json(clone_bytes)
    source_context = _mapping(provenance.get("source"), "clone source")
    destination_context = _mapping(
        provenance.get("destination"), "clone destination"
    )
    if (
        destination_context.get("session_uid") != record.analysis_session_uid
        or destination_context.get("session_id") != record.analysis_session_id
    ):
        raise ValidationError("clone ROI identity bridge destination mismatch")

    source = core.session_by_uid(
        str(image_uid), str(source_context.get("session_uid"))
    )
    source_uid = p2._require_uuid4(
        source_context.get("revision_uid"), "clone source revision_uid"
    )
    source_sha = p2._require_sha(
        source_context.get("revision_manifest_sha256"),
        "clone source revision_manifest_sha256",
    )
    source_matches: list[dict[str, Any]] = []
    for revision_root in (source.session_root / "revisions").iterdir():
        if (
            not revision_root.is_dir()
            or revision_root.is_symlink()
            or ".partial." in revision_root.name
        ):
            continue
        manifest = core._verify_revision(source, revision_root)
        if (
            manifest.get("revision_uid") == source_uid
            and sha256_file(revision_root / "revision_manifest.json") == source_sha
        ):
            source_matches.append(manifest)
    if len(source_matches) != 1:
        raise ValidationError("clone ROI identity bridge source is not unique")

    genesis_id = p2._require_id(
        destination_context.get("genesis_revision_id"),
        "clone destination genesis_revision_id",
    )
    genesis_root = record.session_root / "revisions" / f"REV_{genesis_id}"
    genesis = core._verify_revision(record, genesis_root)
    genesis_sha = p2._require_sha(
        destination_context.get("genesis_revision_manifest_sha256"),
        "clone destination genesis_revision_manifest_sha256",
    )
    if sha256_file(genesis_root / "revision_manifest.json") != genesis_sha:
        raise ValidationError("clone ROI identity bridge genesis hash mismatch")
    _validate_clone_provenance(provenance, source_matches[0], genesis)

    working_by_uuid: dict[str, Mapping[str, Any]] = {}
    for index, raw in enumerate(objects):
        item = _mapping(raw, f"working objects[{index}]")
        destination_uuid = p2._require_uuid4(
            item.get("object_uuid"), f"working objects[{index}].object_uuid"
        )
        if destination_uuid in working_by_uuid:
            raise ValidationError("clone ROI identity bridge working UUID repeats")
        working_by_uuid[destination_uuid] = item

    source_by_uuid = {
        str(item["object_uuid"]): item for item in source_matches[0]["objects"]
    }
    mappings: list[dict[str, str]] = []
    for index, raw in enumerate(provenance.get("object_mappings", [])):
        mapping = _mapping(raw, f"clone object_mappings[{index}]")
        source_object_uuid = p2._require_uuid4(
            mapping.get("source_object_uuid"), "clone source_object_uuid"
        )
        destination_object_uuid = p2._require_uuid4(
            mapping.get("destination_object_uuid"), "clone destination_object_uuid"
        )
        current = working_by_uuid.get(destination_object_uuid)
        if current is None:
            continue
        source_object = source_by_uuid.get(source_object_uuid)
        if source_object is None:
            raise ValidationError("clone ROI identity bridge source object is absent")
        cavity_id = str(mapping.get("cavity_id_destination") or "")
        if (
            cavity_id != mapping.get("cavity_id_source")
            or cavity_id != current.get("cavity_id")
            or cavity_id != source_object.get("cavity_id")
        ):
            raise ValidationError("clone ROI identity bridge cavity identity mismatch")
        roi_sha = source_object.get("roi_bytes_sha256")
        if roi_sha is None:
            continue
        roi_sha = p2._require_sha(roi_sha, "clone source roi_bytes_sha256")
        # Only the byte-exact inherited payload needs the transient bridge.
        # A later, destination-native ROI payload validates directly in Fiji.
        if current.get("roi_bytes_sha256") != roi_sha:
            continue
        mappings.append(
            {
                "cavity_id": cavity_id,
                "destination_object_uuid": destination_object_uuid,
                "source_object_uuid": source_object_uuid,
                "source_roi_bytes_sha256": roi_sha,
            }
        )
    mappings.sort(key=lambda item: item["destination_object_uuid"])
    return {
        "analysis_session_uid": record.analysis_session_uid,
        "destination_genesis_revision_uid": p2._require_uuid4(
            destination_context.get("genesis_revision_uid"),
            "clone destination genesis_revision_uid",
        ),
        "mappings": mappings,
        "schema": "CTL_P3_CLONE_ROI_IDENTITY_BRIDGE_V1",
        "source_revision_uid": source_uid,
    }


def _augment_clone_roi_identity_bridge(
    result: dict[str, Any], arguments: Mapping[str, Any], session_uid: str | None
) -> dict[str, Any]:
    if session_uid is None:
        result["clone_roi_identity_bridge"] = None
        return result
    result["clone_roi_identity_bridge"] = _verified_clone_roi_identity_bridge(
        arguments["project_root"],
        str(arguments["image_uid"]),
        str(session_uid),
        p2._require_sequence(result.get("objects", []), "objects"),
    )
    return result


def select_session(arguments: Mapping[str, Any]) -> dict[str, Any]:
    result = p2.select_session(arguments)
    selection = result.get("selection")
    selected_uid = (
        selection.get("selected_session_uid")
        if isinstance(selection, Mapping)
        else None
    )
    _augment_clone_roi_identity_bridge(result, arguments, selected_uid)
    return _augment_geometry_state(result, arguments, selected_uid)


def create_session(arguments: Mapping[str, Any]) -> dict[str, Any]:
    # A brand-new empty session has no current revision; geometry state starts
    # after its first explicit save rather than inventing an implicit revision.
    result = p2.create_session(arguments)
    result["clone_roi_identity_bridge"] = None
    result["geometry_state"] = None
    return result


def _source_revision_manifest(arguments: Mapping[str, Any]) -> dict[str, Any]:
    core = SessionCore(arguments["project_root"])
    image_uid = str(arguments["image_uid"])
    source = core.session_by_uid(image_uid, str(arguments["source_session_uid"]))
    expected_uid = p2._require_uuid4(arguments["source_revision_uid"], "source_revision_uid")
    expected_sha = p2._require_sha(
        arguments["source_revision_manifest_sha256"],
        "source_revision_manifest_sha256",
    )
    matches: list[dict[str, Any]] = []
    for path in (source.session_root / "revisions").iterdir():
        if not path.is_dir() or path.is_symlink() or ".partial." in path.name:
            continue
        manifest = core._verify_revision(source, path)
        if (
            manifest["revision_uid"] == expected_uid
            and sha256_file(path / "revision_manifest.json") == expected_sha
        ):
            matches.append(manifest)
    if len(matches) != 1:
        raise ValidationError("Prompt-3 clone source revision is not unique")
    return matches[0]


def clone_revision(arguments: Mapping[str, Any]) -> dict[str, Any]:
    # Keep the exact source UID/hash selector.  The P2 adapter dispatches V1
    # revisions through the historical V2 clone profile and Prompt-3 V2
    # revisions through the implementation-local V3 profile that preserves
    # every scientific geometry record and identity byte-exactly.
    _source_revision_manifest(arguments)
    result = p2.clone_revision(arguments)
    session = _mapping(result.get("session"), "clone result session")
    _augment_clone_roi_identity_bridge(
        result,
        arguments,
        str(session.get("analysis_session_uid")),
    )
    result["geometry_state"] = None
    return result


def save_revision(arguments: Mapping[str, Any]) -> dict[str, Any]:
    core = SessionCore(arguments["project_root"])
    image_uid = str(arguments["image_uid"])
    session_uid = str(arguments["analysis_session_uid"])
    record = p2._active_record(core, image_uid, session_uid)
    objects, candidates = p2._normalize_entities(
        record,
        p2._require_sequence(arguments.get("objects", []), "objects"),
        p2._require_sequence(arguments.get("candidates", []), "candidates"),
    )
    if arguments.get("image_context") is not None:
        binding = core._binding(image_uid)
        validate_revision_scale_snapshot(
            {"project_uid": core.project_uid, "image_uid": image_uid,
             "source_sha256": binding["source_sha256"], "objects": objects, "candidates": candidates},
            source_binding=binding, image_context=_mapping(arguments["image_context"], "image_context"),
        )
    if "geometries" not in arguments:
        raise ValidationError(
            "Prompt-3 save_revision requires an explicit geometries array"
        )
    geometries = core._normalize_revision_geometries(
        p2._require_sequence(arguments["geometries"], "geometries")
    )
    expected_working = p2._require_sha(
        arguments["expected_working_sha256"], "expected_working_sha256"
    )
    expected_pointer = p2._require_sha(
        arguments["expected_revision_pointer_sha256"],
        "expected_revision_pointer_sha256",
    )
    pointer_path = record.session_root / "current_revision.tsv"
    if sha256_file(pointer_path) != expected_pointer:
        raise StaleContextError("Prompt-3 revision pointer snapshot is stale")
    working_path = record.session_root / "working" / "working_state.json"
    if sha256_file(working_path) != expected_working:
        raise StaleContextError("Prompt-3 working-state snapshot is stale")

    # Stable geometry IDs/UUIDs/types cannot silently change, including after
    # a delete-and-reintroduce sequence.  Only verified immutable revisions in
    # this exact session participate; operational and quarantine paths do not.
    parent = p2._read_pointer(pointer_path, CURRENT_REVISION_FIELDS)
    historical_by_id: dict[str, tuple[str, str]] = {}
    historical_by_uid: dict[str, tuple[str, str]] = {}
    for revision_root in (record.session_root / "revisions").iterdir():
        if (
            not revision_root.is_dir()
            or revision_root.is_symlink()
            or ".partial." in revision_root.name
        ):
            continue
        historical_manifest = core._verify_revision(record, revision_root)
        for previous in historical_manifest.get("geometries", []):
            by_id = (previous["geometry_uid"], previous["geometry_type"])
            by_uid = (previous["geometry_id"], previous["geometry_type"])
            if previous["geometry_id"] in historical_by_id and historical_by_id[
                previous["geometry_id"]
            ] != by_id:
                raise ValidationError("Prompt-3 geometry ID history is inconsistent")
            if previous["geometry_uid"] in historical_by_uid and historical_by_uid[
                previous["geometry_uid"]
            ] != by_uid:
                raise ValidationError("Prompt-3 geometry UUID history is inconsistent")
            historical_by_id[previous["geometry_id"]] = by_id
            historical_by_uid[previous["geometry_uid"]] = by_uid
    for geometry in geometries:
        prior_by_id = historical_by_id.get(geometry["geometry_id"])
        prior_by_uid = historical_by_uid.get(geometry["geometry_uid"])
        if prior_by_id is not None and prior_by_id != (
            geometry["geometry_uid"],
            geometry["geometry_type"],
        ):
            raise ValidationError(
                "Prompt-3 geometry ID cannot silently change scientific UUID or type"
            )
        if prior_by_uid is not None and prior_by_uid != (
            geometry["geometry_id"],
            geometry["geometry_type"],
        ):
            raise ValidationError(
                "Prompt-3 geometry UUID cannot silently change scientific ID or type"
            )

    revision_id = (
        p2._require_id(arguments["revision_id"], "revision_id")
        if arguments.get("revision_id") is not None
        else p2._next_revision_id(record)
    )
    revisions_root = record.session_root / "revisions"
    if (revisions_root / f"REV_{revision_id}").exists() or any(
        revisions_root.glob(f"REV_{revision_id}.partial.*")
    ):
        raise TransactionError("Prompt-3 revision ID already exists or has a retained partial")
    roi_zip_sha = p2._require_sha(arguments["roi_zip_sha256"], "roi_zip_sha256")
    geometry_set_sha = core.geometry_set_sha256(geometries)

    # No caller-controlled validation remains after the working-state commit;
    # publish_revision still performs its own pointer CAS immediately below.
    working_sha = core.update_working_state(
        image_uid,
        session_uid,
        objects=objects,
        candidates=candidates,
        geometries=geometries,
        expected_working_sha256=expected_working,
    )
    if sha256_file(pointer_path) != expected_pointer:
        # The working-state transaction is independently valid but publication
        # must never attach it to a revision parent selected by a stale caller.
        raise StaleContextError("Prompt-3 revision pointer changed after working-state commit")
    published = core.publish_revision(
        image_uid,
        session_uid,
        revision_id=revision_id,
        objects=objects,
        candidates=candidates,
        geometries=geometries,
        identity_provenance=[
            {
                "owner": "ACTIVE_SESSION_FIJI_ROI_SNAPSHOT",
                "roi_zip_sha256": roi_zip_sha,
            },
            {
                "geometry_count": len(geometries),
                "geometry_set_sha256": geometry_set_sha,
                "owner": "P3_SCIENTIFIC_GEOMETRY_COLLECTION",
                "status": "REVISION_AUTHORITY",
            },
        ],
        parent_revision_id=(
            "NOT_APPLICABLE" if parent is None else parent["revision_id"]
        ),
        expected_pointer_sha256=expected_pointer,
    )
    result = {
        "working_state_sha256": working_sha,
        "revision": p2._jsonable(asdict(published)),
        "project": p2.inspect_project(core.root),
    }
    return _augment_geometry_state(result, arguments, session_uid)


def publish_run(arguments: Mapping[str, Any]) -> dict[str, Any]:
    cache, geometry_state = area_cache_for_run(arguments)
    core = SessionCore(arguments["project_root"])
    image_uid = str(arguments["image_uid"])
    session_uid = str(arguments["analysis_session_uid"])
    record = p2._active_record(core, image_uid, session_uid)
    pointer = p2._read_pointer(
        record.session_root / "current_revision.tsv", CURRENT_REVISION_FIELDS
    )
    if pointer is None:
        raise ValidationError("Prompt-3 RUN requires an explicit current revision")
    revision_root = p2._contained(record.session_root, pointer["relative_path"])
    revision_manifest = core._verify_revision(record, revision_root)
    evidence = geometry_state["spatial_calibration_evidence"]
    calibration = {
        "scale_x_nm_px": evidence["scale_x_nm_px"],
        "scale_y_nm_px": evidence["scale_y_nm_px"],
        "source_height_px": evidence["height"],
        "source_width_px": evidence["width"],
    }
    transient_objects = transient_physical_objects(
        revision_manifest["objects"], calibration
    )
    forwarded = dict(arguments)
    image_context = dict(_mapping(arguments.get("image_context"), "image_context"))
    # The verified evidence is the single canonical scale representation used
    # by both the transient physical conversion and the P2 RUN assembler.  A
    # JavaScript Number may serialize the same Fiji value with one additional
    # decimal digit; forwarding that spelling would round-trip exact pixel
    # bounds through nm and can move an x=0 edge by ~1e-14 px.
    image_context["scale_x_nm_px"] = evidence["scale_x_nm_px"]
    image_context["scale_y_nm_px"] = evidence["scale_y_nm_px"]
    area_input = geometry_state["area_input"]
    image_context["net_area_nm2"] = cache["net_area_nm2"]
    image_context["use_whole_image"] = 1 if area_input["use_whole_image"] else 0
    image_context["image_mode"] = area_input["image_mode"]
    forwarded["image_context"] = image_context
    staged_verification: dict[str, Any] = {}

    def verify_before_publication(staged_run: Any) -> bool:
        staged_verification.update(
            verify_run_scientific_scale(
                staged_run,
                revision_manifest=revision_manifest,
                calibration=calibration,
                valid_pixel_count=int(cache["valid_pixel_count"]),
            )
        )
        return True

    result = p2.publish_run(
        forwarded,
        _verified_revision_objects_override=transient_objects,
        _staged_run_validator=verify_before_publication,
    )
    verified_runs, _registry, current = _verified_session_runs(core, record)
    published_run_id = str(result["run"]["run_id"])
    verified = verified_runs.get(published_run_id)
    if verified is None or current.run_uid != verified.run_uid:
        raise TransactionError(
            "Prompt-3 published RUN cannot be reconciled with the physical current pointer"
        )
    scientific_verification = verify_run_scientific_scale(
        verified,
        revision_manifest=revision_manifest,
        calibration=calibration,
        valid_pixel_count=int(cache["valid_pixel_count"]),
    )
    if scientific_verification != staged_verification:
        raise TransactionError(
            "Prompt-3 staged and published scientific verification differ"
        )
    result.update(
        {
            "analysis_area_cache_sha256": geometry_state[
                "analysis_area_cache_sha256"
            ],
            "area_input_fingerprint_sha256": area_input[
                "input_fingerprint_sha256"
            ],
            "geometry_set_sha256": area_input["geometry_set_sha256"],
            "scientific_scale_verification": scientific_verification,
            "visibility_independent": True,
        }
    )
    return result


def scale_preflight_no_write(arguments: Mapping[str, Any]) -> dict[str, Any]:
    """Recompute the closed scale/area prediction without project writes."""

    core = SessionCore(arguments["project_root"])
    before = snapshot_tree(core.root)
    raw_context = _mapping(arguments.get("image_context"), "image_context")
    registry = core._source_registry()
    expected_source = arguments.get("expected_source_sha256")
    master = raw_context.get("master_pixel_evidence")
    if expected_source is None and isinstance(master, Mapping):
        expected_source = master.get("source_sha256")
    requested_image_uid = arguments.get("image_uid")
    if requested_image_uid is not None:
        image_uid = str(requested_image_uid)
        binding = core._binding(image_uid)
    else:
        candidates = list(registry["image_bindings"])
        if expected_source is not None:
            candidates = [
                item
                for item in candidates
                if item.get("source_sha256") == str(expected_source)
            ]
        if len(candidates) != 1:
            raise ValidationError(
                "Prompt-3 scale preflight cannot resolve exactly one physical image"
            )
        image_uid = str(candidates[0]["image_uid"])
        binding = candidates[0]
    if expected_source is not None and binding["source_sha256"] != str(expected_source):
        raise ValidationError("Prompt-3 scale preflight source identity differs")
    expected_source_bytes = arguments.get("expected_source_bytes")
    source_blobs = [
        item
        for item in registry["blobs"]
        if item["source_sha256"] == binding["source_sha256"]
    ]
    if len(source_blobs) != 1:
        raise ValidationError("Prompt-3 scale preflight source blob is not unique")
    if expected_source_bytes is not None:
        claimed_source_bytes = _positive_int(
            expected_source_bytes, "expected_source_bytes"
        )
        if claimed_source_bytes != int(source_blobs[0]["byte_size"]):
            raise ValidationError("Prompt-3 scale preflight source byte size differs")
    current_session = core._read_current_session(image_uid)
    if current_session is None:
        raise ValidationError("Prompt-3 scale preflight requires a current session")
    requested_session_uid = arguments.get("analysis_session_uid")
    session_uid = str(
        current_session["analysis_session_uid"]
        if requested_session_uid is None
        else requested_session_uid
    )
    if session_uid != current_session["analysis_session_uid"]:
        raise StaleContextError("Prompt-3 scale preflight session selection is stale")
    record = p2._active_record(core, image_uid, session_uid)
    pointer = p2._read_pointer(
        record.session_root / "current_revision.tsv", CURRENT_REVISION_FIELDS
    )
    if pointer is None:
        raise ValidationError("Prompt-3 scale preflight requires a current revision")
    expected_pointer = arguments.get("expected_revision_pointer_sha256")
    pointer_sha = sha256_file(record.session_root / "current_revision.tsv")
    if expected_pointer is not None and str(expected_pointer) != pointer_sha:
        raise StaleContextError("Prompt-3 scale preflight revision pointer is stale")
    revision_root = p2._contained(record.session_root, pointer["relative_path"])
    revision = core._verify_revision(record, revision_root)
    revision_sha = sha256_file(revision_root / "revision_manifest.json")
    provenance = verify_spatial_scale_provenance(
        core=core,
        record=record,
        revision_manifest=revision,
        revision_manifest_sha256=revision_sha,
        image_context=raw_context,
    )
    calibration = provenance["calibration"]
    valid_pixels = _positive_int(
        arguments.get("valid_pixel_count"), "valid_pixel_count"
    )
    width = int(provenance["evidence"]["width"])
    height = int(provenance["evidence"]["height"])
    if valid_pixels > width * height:
        raise ValidationError("valid_pixel_count is outside the verified image domain")
    scale_x = Decimal(calibration["scale_x_nm_px"])
    scale_y = Decimal(calibration["scale_y_nm_px"])
    predicted_area = Decimal(valid_pixels) * scale_x * scale_y
    revision_pair = revision_legacy_scale(revision, label="scale_preflight_revision")
    if revision_pair is None:
        raise ValidationError("current revision has no scale provenance")
    result = {
        "analysis_session_uid": session_uid,
        "factor_x_to_nm": calibration["factor_x_to_nm"],
        "factor_y_to_nm": calibration["factor_y_to_nm"],
        "image_uid": image_uid,
        "predicted_net_area_nm2": decimal_text(predicted_area),
        "raw_pixel_height": calibration["raw_pixel_height"],
        "raw_pixel_width": calibration["raw_pixel_width"],
        "raw_x_unit": calibration["raw_x_unit"],
        "raw_y_unit": calibration["raw_y_unit"],
        "result": "PASS",
        "revision_id": str(revision["revision_id"]),
        "revision_manifest_sha256": revision_sha,
        "revision_scale_x_nm_px": decimal_text(revision_pair[0]),
        "revision_scale_y_nm_px": decimal_text(revision_pair[1]),
        "scale_x_nm_px": calibration["scale_x_nm_px"],
        "scale_y_nm_px": calibration["scale_y_nm_px"],
        "source_bytes": int(source_blobs[0]["byte_size"]),
        "source_sha256": binding["source_sha256"],
        "spatial_calibration_evidence_sha256": provenance["evidence_sha256"],
        "valid_pixels": valid_pixels,
        "writes": 0,
    }
    if snapshot_tree(core.root) != before:
        raise TransactionError("Prompt-3 scale preflight mutated the project")
    return result


def _scale_verification_context(
    arguments: Mapping[str, Any],
) -> tuple[
    SessionCore,
    Any,
    dict[str, Any],
    dict[str, Any],
    dict[str, Any],
]:
    core = SessionCore(arguments["project_root"])
    image_uid = str(arguments["image_uid"])
    session_uid = str(arguments["analysis_session_uid"])
    record = p2._active_record(core, image_uid, session_uid)
    geometry_state = prepare_geometry_state(arguments)
    pointer = p2._read_pointer(
        record.session_root / "current_revision.tsv", CURRENT_REVISION_FIELDS
    )
    if pointer is None:
        raise ValidationError("Prompt-3 scale verification requires a current revision")
    revision_root = p2._contained(record.session_root, pointer["relative_path"])
    revision_manifest = core._verify_revision(record, revision_root)
    evidence = dict(geometry_state["spatial_calibration_evidence"])
    calibration = {
        "scale_x_nm_px": evidence["scale_x_nm_px"],
        "scale_y_nm_px": evidence["scale_y_nm_px"],
        "source_height_px": evidence["height"],
        "source_width_px": evidence["width"],
    }
    return core, record, geometry_state, revision_manifest, calibration


def inspect_run_scientific_scale(arguments: Mapping[str, Any]) -> dict[str, Any]:
    """Report physical PASS separately from scientific scale validity."""

    required = {
        "analysis_session_uid",
        "image_context",
        "image_uid",
        "project_root",
        "run_id",
    }
    if set(arguments) != required:
        raise ValidationError(
            "Prompt-3 scientific RUN inspection field inventory is not closed"
        )
    core, record, state, revision, calibration = _scale_verification_context(
        arguments
    )
    verified, _registry, _current = _verified_session_runs(core, record)
    run_id = p2._require_id(arguments["run_id"], "run_id")
    run = verified.get(run_id)
    if run is None:
        raise ValidationError("Prompt-3 scientific RUN inspection target is absent")
    disposition = find_run_disposition(run, session_root=record.session_root)
    cache = state.get("analysis_area_cache")
    valid_pixel_count = (
        int(cache["valid_pixel_count"])
        if isinstance(cache, Mapping)
        and state.get("analysis_area_cache_status")
        in {"HIT", "REBOUND_WITHOUT_RASTER_RECALCULATION"}
        else None
    )
    try:
        report = verify_run_scientific_scale(
            run,
            revision_manifest=revision,
            calibration=calibration,
            valid_pixel_count=valid_pixel_count,
        )
        scientific_status = "PASS"
        error = None
    except ScientificScaleMismatch as exc:
        report = None
        scientific_status = "FAIL"
        error = {
            "code": exc.code,
            "details": exc.details,
            "message": str(exc),
        }
    return {
        "physical_hash_chain": "PASS",
        "physical_publication_chain": "PASS",
        "scientific_disposition": (
            None if disposition is None else dict(disposition.value)
        ),
        "scientific_disposition_sha256": (
            None if disposition is None else disposition.sha256
        ),
        "run_id": run.run_id,
        "run_manifest_sha256": run.manifest_sha256,
        "run_uid": run.run_uid,
        "scientific_scale_error": error,
        "scientific_scale_report": report,
        "scientific_scale_validity": scientific_status,
    }


def _run_scale_pair(run: Any) -> tuple[Decimal, Decimal]:
    pairs = {
        (
            Decimal(str(row["scale_x_nm_px"])),
            Decimal(str(row["scale_y_nm_px"])),
        )
        for row in run.object_rows
    }
    if len(pairs) != 1:
        raise ValidationError("Prompt-3 disposition target mixes spatial scales")
    return next(iter(pairs))


def publish_scale_disposition(arguments: Mapping[str, Any]) -> dict[str, Any]:
    """Build the approved RUN2→RUN3 record from verified physical evidence."""

    required = {
        "analysis_session_uid",
        "image_context",
        "image_uid",
        "invalidated_run_id",
        "project_root",
        "replacement_run_id",
    }
    if set(arguments) != required:
        raise ValidationError(
            "Prompt-3 scale-disposition request field inventory is not closed"
        )
    core, record, state, revision, calibration = _scale_verification_context(
        arguments
    )
    verified, _registry, current = _verified_session_runs(core, record)
    invalidated_id = p2._require_id(
        arguments["invalidated_run_id"], "invalidated_run_id"
    )
    replacement_id = p2._require_id(
        arguments["replacement_run_id"], "replacement_run_id"
    )
    invalidated = verified.get(invalidated_id)
    replacement = verified.get(replacement_id)
    if invalidated is None or replacement is None:
        raise ValidationError("Prompt-3 disposition references an absent RUN")
    if current.run_uid != replacement.run_uid:
        raise ValidationError("Prompt-3 disposition replacement is not current")
    stored_x, stored_y = _run_scale_pair(invalidated)
    correct_x = Decimal(str(calibration["scale_x_nm_px"]))
    correct_y = Decimal(str(calibration["scale_y_nm_px"]))
    if scales_agree(stored_x, correct_x) and scales_agree(stored_y, correct_y):
        raise ValidationError(
            "Prompt-3 disposition target is not invalid by spatial scale"
        )
    try:
        verify_run_scientific_scale(
            invalidated,
            revision_manifest=revision,
            calibration=calibration,
        )
    except ScientificScaleMismatch as invalidated_error:
        invalidated_report = {
            "code": invalidated_error.code,
            "details": invalidated_error.details,
            "message": str(invalidated_error),
        }
    else:
        raise ValidationError(
            "Prompt-3 disposition target unexpectedly passed scientific verification"
        )
    cache = state.get("analysis_area_cache")
    if not isinstance(cache, Mapping) or state.get(
        "analysis_area_cache_status"
    ) not in {"HIT", "REBOUND_WITHOUT_RASTER_RECALCULATION"}:
        raise ValidationError(
            "Prompt-3 disposition requires the corrected verified area cache"
        )
    replacement_report = verify_run_scientific_scale(
        replacement,
        revision_manifest=revision,
        calibration=calibration,
        valid_pixel_count=int(cache["valid_pixel_count"]),
    )
    factor_x = correct_x / stored_x
    factor_y = correct_y / stored_y
    if not scales_agree(factor_x, factor_y):
        raise ValidationError(
            "Prompt-3 disposition has no single reconciled linear error factor"
        )
    evidence = state["spatial_calibration_evidence"]
    disposition = {
        "affected_outputs": [
            "AREA_DENOMINATOR",
            "CAVITY_CENTER_COORDINATES",
            "CAVITY_DIAMETERS",
            "CAVITY_PROJECTED_AREAS",
            "COMBINED_ANALYSIS",
            "RUN_STATISTICS",
        ],
        "analysis_session_uid": invalidated.manifest["analysis_session_uid"],
        "area_factor_error": decimal_text(factor_x * factor_y),
        "correct_scale_x_nm_px": decimal_text(correct_x),
        "correct_scale_y_nm_px": decimal_text(correct_y),
        "created_at": utc_now_z(),
        "disposition": "INVALIDATED_AND_SUPERSEDED",
        "image_uid": invalidated.manifest["image_uid"],
        "immutable_run_preserved": True,
        "linear_factor_error": decimal_text(factor_x),
        "policy_id": "CTL_RUN_SCALE_PROVENANCE_DISPOSITION_V1",
        "project_uid": invalidated.manifest["project_uid"],
        "raw_fiji_pixel_height": evidence["raw_pixel_height"],
        "raw_fiji_pixel_width": evidence["raw_pixel_width"],
        "raw_x_unit": evidence["raw_x_unit"],
        "raw_y_unit": evidence["raw_y_unit"],
        "reason_code": "SPATIAL_SCALE_UNIT_MISLABELLED_AS_NM",
        "replacement_run_id": replacement.run_id,
        "replacement_run_manifest_sha256": replacement.manifest_sha256,
        "replacement_run_uid": replacement.run_uid,
        "revision_id": invalidated.manifest["revision_id"],
        "revision_uid": invalidated.manifest["revision_uid"],
        "run_id": invalidated.run_id,
        "run_manifest_sha256": invalidated.manifest_sha256,
        "run_uid": invalidated.run_uid,
        "schema": "CTL_RUN_SCIENTIFIC_DISPOSITION_V1",
        "scientific_use_allowed": False,
        "source_sha256": invalidated.manifest["source_sha256"],
        "stored_scale_x_nm_px": decimal_text(stored_x),
        "stored_scale_y_nm_px": decimal_text(stored_y),
    }
    result = publish_run_disposition(
        arguments["project_root"],
        image_uid=str(arguments["image_uid"]),
        analysis_session_uid=str(arguments["analysis_session_uid"]),
        disposition_value=disposition,
    )
    result["invalidated_run_scientific_verification"] = invalidated_report
    result["replacement_run_scientific_verification"] = replacement_report
    return result


DRAFT_SCHEMA = "CTL_P6_RECOVERABLE_DRAFT_V1"
DRAFT_ENVELOPE_SCHEMA = "CTL_P6_DRAFT_ENVELOPE_V1"
DRAFT_POINTER_SCHEMA = "CTL_P6_DRAFT_POINTER_V1"
DRAFT_MAX_BYTES = 64 * 1024 * 1024
DRAFT_HISTORY_MAX_BYTES = 1024 * 1024 * 1024
DRAFT_MAX_ENTITIES = 100000


def _draft_root(record: Any, *, create: bool = False) -> Path | None:
    """Drafts are operational recovery evidence, never revision authority."""
    root = record.session_root / "autosave" / "prompt6"
    try:
        plain_directory(record.session_root / "autosave", label="draft autosave parent")
        if not root.exists() and not root.is_symlink():
            if not create:
                return None
            root.mkdir(exist_ok=True)
        plain_directory(root, label="draft recovery directory")
    except PathSafetyError as exc:
        raise ValidationError("Draft recovery directory is unsafe", details={"reason": str(exc)}) from exc
    return root


@contextmanager
def _draft_writer_lock(root: Path):
    """An OS lock serializes draft pointer CAS; process exit releases it."""
    path = root / ".draft_writer.lock"
    if not path.exists() and not path.is_symlink():
        try:
            _write_new(path, b"\x00")
        except FileExistsError:
            pass
    try:
        checked = plain_file(path, label="draft writer lock", single_link=True)
    except PathSafetyError as exc:
        raise ValidationError("Draft writer lock is unsafe", details={"reason": str(exc)}) from exc
    handle = checked.open("r+b", buffering=0)
    acquired = False
    try:
        try:
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            raise TransactionError("Another draft operation is active") from exc
        acquired = True
        yield
    finally:
        if acquired:
            if os.name == "nt":
                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        handle.close()


def _draft_envelope(payload: Mapping[str, Any]) -> bytes:
    payload_bytes = canonical_json_bytes(dict(payload))
    data = canonical_json_bytes({
        "payload": dict(payload),
        "payload_sha256": hashlib.sha256(payload_bytes).hexdigest(),
        "schema": DRAFT_ENVELOPE_SCHEMA,
    })
    if len(data) > DRAFT_MAX_BYTES:
        raise ValidationError("Draft exceeds the 64 MiB snapshot limit")
    return data


def _draft_read(path: Path) -> tuple[dict[str, Any], str]:
    try:
        checked = plain_file(path, label="draft recovery file", single_link=True)
        if checked.stat().st_size > DRAFT_MAX_BYTES:
            raise ValidationError("Draft exceeds the 64 MiB snapshot limit")
        data = stable_plain_bytes(checked, label="draft recovery file")
    except PathSafetyError as exc:
        raise ValidationError("Draft recovery file is unsafe", details={"reason": str(exc)}) from exc
    envelope = loads_canonical_json(data)
    if not isinstance(envelope, dict) or set(envelope) != {"schema", "payload", "payload_sha256"}:
        raise ValidationError("Draft envelope fields are invalid")
    if envelope["schema"] != DRAFT_ENVELOPE_SCHEMA or not isinstance(envelope["payload"], dict):
        raise ValidationError("Draft envelope schema is invalid")
    if hashlib.sha256(canonical_json_bytes(envelope["payload"])).hexdigest() != envelope["payload_sha256"]:
        raise ValidationError("Draft checksum mismatch; recovery evidence was retained")
    return envelope["payload"], hashlib.sha256(data).hexdigest()


def _draft_context(arguments: Mapping[str, Any], *, verify_revision: bool = False):
    core = SessionCore(arguments["project_root"])
    image_uid = str(arguments["image_uid"])
    session_uid = str(arguments["analysis_session_uid"])
    record = p2._active_record(core, image_uid, session_uid)
    source = core._binding(image_uid)
    raw = _mapping(arguments.get("image_context"), "image_context")
    master = _mapping(raw.get("master_pixel_evidence"), "master_pixel_evidence")
    calibration = normalize_spatial_calibration(raw)
    width = _positive_int(raw.get("width_px"), "width_px")
    height = _positive_int(raw.get("height_px"), "height_px")
    bit_depth = _positive_int(raw.get("bit_depth"), "bit_depth")
    if bit_depth not in {8, 16, 24, 32} or source["master_pixel_hash_status"] != "VERIFIED":
        raise ValidationError("Draft requires a verified source/master image")
    if (
        master.get("sha256") != source["master_pixel_sha256"]
        or master.get("source_sha256") != source["source_sha256"]
        or master.get("width") != width or master.get("height") != height
        or master.get("bit_depth") != bit_depth
    ):
        raise ValidationError("Draft image source/master identity differs")
    working_sha = p2._require_sha(arguments["expected_working_sha256"], "expected_working_sha256")
    pointer_sha = p2._require_sha(arguments["expected_revision_pointer_sha256"], "expected_revision_pointer_sha256")
    pointer_path = record.session_root / "current_revision.tsv"
    if sha256_file(record.session_root / "working" / "working_state.json") != working_sha:
        raise StaleContextError("Draft working-state snapshot is stale")
    if sha256_file(pointer_path) != pointer_sha:
        raise StaleContextError("Draft revision pointer snapshot is stale")
    pointer = p2._read_pointer(pointer_path, CURRENT_REVISION_FIELDS)
    revision_uid = None
    revision_sha = None
    if pointer is not None:
        revision_root = p2._contained(record.session_root, pointer["relative_path"])
        manifest_bytes = stable_plain_bytes(revision_root / "revision_manifest.json", label="draft base revision")
        revision_sha = hashlib.sha256(manifest_bytes).hexdigest()
        if revision_sha != pointer["revision_manifest_sha256"]:
            raise ValidationError("Draft base revision manifest hash differs")
        revision = loads_canonical_json(manifest_bytes)
        revision_uid = revision["revision_uid"]
        if verify_revision:
            revision = core._verify_revision(record, revision_root)
            verify_spatial_scale_provenance(
                core=core, record=record, revision_manifest=revision,
                revision_manifest_sha256=revision_sha, image_context=raw,
            )
    # Autosave receives the context already verified during session loading.
    # It checks source/master claims and normalized scale without walking every
    # historical revision again. Explicit recovery verifies that chain above.
    binding = {
        "project_uid": core.project_uid, "image_uid": image_uid,
        "analysis_session_uid": session_uid,
        "source_sha256": source["source_sha256"],
        "master_pixel_sha256": source["master_pixel_sha256"],
        "master_pixel_hash_method": source["master_pixel_hash_method"],
        "width_px": width, "height_px": height, "bit_depth": bit_depth,
        "scale_x_nm_px": calibration["scale_x_nm_px"],
        "scale_y_nm_px": calibration["scale_y_nm_px"],
        "normalization_rule_id": calibration["normalization_rule_id"],
        "expected_working_sha256": working_sha,
        "expected_revision_pointer_sha256": pointer_sha,
        "revision_uid": revision_uid, "revision_manifest_sha256": revision_sha,
    }
    _assert_draft_base(core, record, binding)
    return core, record, binding


def _assert_draft_base(core: SessionCore, record: Any, binding: Mapping[str, Any]) -> None:
    p2._active_record(core, record.image_uid, record.analysis_session_uid)
    if (
        sha256_file(record.session_root / "working" / "working_state.json") != binding["expected_working_sha256"]
        or sha256_file(record.session_root / "current_revision.tsv") != binding["expected_revision_pointer_sha256"]
    ):
        raise StaleContextError("Draft base changed during the operation")


def _draft_snapshot(arguments: Mapping[str, Any], core: SessionCore, record: Any) -> dict[str, Any]:
    snapshot = {}
    for name in ("objects", "candidates", "geometries"):
        sequence = p2._require_sequence(arguments[name], name)
        if len(sequence) > DRAFT_MAX_ENTITIES:
            raise ValidationError("Draft entity count exceeds the recovery limit")
        snapshot[name] = [dict(_mapping(item, name)) for item in sequence]
    snapshot["roi_zip_sha256"] = p2._require_sha(arguments["roi_zip_sha256"], "roi_zip_sha256")
    # UI fingerprint is informative. The envelope independently hashes every
    # snapshot field, including candidates, properties and base identity.
    snapshot["snapshot_sha256"] = p2._require_sha(arguments["snapshot_sha256"], "snapshot_sha256")
    normalized_objects, normalized_candidates = p2._normalize_entities(record, snapshot["objects"], snapshot["candidates"])
    core._normalize_revision_entities(normalized_objects, normalized_candidates)
    core._normalize_revision_geometries(snapshot["geometries"])
    for item in snapshot["objects"]:
        if "roi_bytes_base64" in item:
            try:
                roi_bytes = base64.b64decode(item["roi_bytes_base64"], validate=True)
            except (ValueError, TypeError) as exc:
                raise ValidationError("Draft ROI bytes are invalid") from exc
            if not roi_bytes or hashlib.sha256(roi_bytes).hexdigest() != item.get("roi_bytes_sha256"):
                raise ValidationError("Draft ROI checksum mismatch")
            if "roi_bytes" in item and item["roi_bytes"] != len(roi_bytes):
                raise ValidationError("Draft ROI byte count differs")
    # Preserve exactly the editor snapshot: in particular do not assign new
    # scientific UUIDs merely because unsaved work was copied for recovery.
    return loads_canonical_json(canonical_json_bytes(snapshot))


def _draft_current(root: Path, scope: Mapping[str, str]) -> tuple[dict[str, Any] | None, str]:
    path = root / "current.json"
    if not path.exists() and not path.is_symlink():
        return None, "NOT_APPLICABLE"
    pointer, digest = _draft_read(path)
    if set(pointer) != {"schema", "authority", "scope", "draft_status", "draft_id", "draft_sha256", "updated_at"}:
        raise ValidationError("Draft pointer fields are invalid")
    if pointer["schema"] != DRAFT_POINTER_SCHEMA or pointer["authority"] is not False or pointer["scope"] != dict(scope):
        raise ValidationError("Draft pointer scope/schema differs")
    if pointer["draft_status"] not in {"ACTIVE", "DISCARDED"}:
        raise ValidationError("Draft pointer state is invalid")
    p2._require_uuid4(pointer["draft_id"], "draft_id")
    p2._require_sha(pointer["draft_sha256"], "draft_sha256")
    _require_timestamp(pointer["updated_at"], "updated_at")
    return pointer, digest


def _draft_scope(core: SessionCore, record: Any) -> dict[str, str]:
    return {"project_uid": core.project_uid, "image_uid": record.image_uid,
            "analysis_session_uid": record.analysis_session_uid}


def _draft_payload(root: Path, pointer: Mapping[str, Any], scope: Mapping[str, str]) -> dict[str, Any]:
    draft, digest = _draft_read(root / ("draft_" + pointer["draft_id"] + ".json"))
    if digest != pointer["draft_sha256"]:
        raise ValidationError("Draft file checksum differs from its pointer")
    if set(draft) != {"schema", "authority", "draft_id", "saved_at", "base_binding", "snapshot"}:
        raise ValidationError("Draft payload fields are invalid")
    if draft["schema"] != DRAFT_SCHEMA or draft["authority"] is not False or draft["draft_id"] != pointer["draft_id"]:
        raise ValidationError("Draft payload schema/identity differs")
    _require_timestamp(draft["saved_at"], "saved_at")
    binding = _mapping(draft["base_binding"], "draft base binding")
    if any(binding.get(key) != value for key, value in scope.items()):
        raise ValidationError("Draft belongs to another project/image/session")
    snapshot = _mapping(draft["snapshot"], "draft snapshot")
    if set(snapshot) != {"objects", "candidates", "geometries", "roi_zip_sha256", "snapshot_sha256"}:
        raise ValidationError("Draft snapshot fields are invalid")
    return draft


def _draft_replace_pointer(root: Path, pointer: Mapping[str, Any], expected_sha: str) -> None:
    data = _draft_envelope(pointer)
    path = root / "current.json"
    if expected_sha == "NOT_APPLICABLE":
        _draft_publish_new(path, data)
    else:
        _replace_exact(path, data, expected_sha256=expected_sha, token="draft_" + uuid.uuid4().hex)


def _draft_publish_new(path: Path, data: bytes) -> None:
    partial = path.with_name("." + path.name + ".partial." + uuid.uuid4().hex)
    _write_new(partial, data)
    rename_file_no_replace(partial, path, error_type=TransactionError)
    if sha256_file(path) != hashlib.sha256(data).hexdigest():
        raise TransactionError("Draft publication failed post-write verification")


def save_draft(arguments: Mapping[str, Any]) -> dict[str, Any]:
    core, record, binding = _draft_context(arguments)
    snapshot = _draft_snapshot(arguments, core, record)
    root = _draft_root(record, create=True)
    scope = _draft_scope(core, record)
    with _draft_writer_lock(root):
        current, current_sha = _draft_current(root, scope)
        if current is not None and current["draft_status"] == "ACTIVE":
            previous = _draft_payload(root, current, scope)
            if previous["base_binding"] == binding and previous["snapshot"] == snapshot:
                _assert_draft_base(core, record, binding)
                return {"draft_status": "UNCHANGED", "draft_id": previous["draft_id"],
                        "draft_sha256": current["draft_sha256"], "saved_at": previous["saved_at"]}
        draft = {"schema": DRAFT_SCHEMA, "authority": False, "draft_id": str(uuid.uuid4()),
                 "saved_at": utc_now_z(), "base_binding": binding, "snapshot": snapshot}
        data = _draft_envelope(draft)
        history_size = 0
        for retained in root.iterdir():
            try:
                history_size += plain_file(retained, label="retained draft", single_link=True).stat().st_size
            except PathSafetyError as exc:
                raise ValidationError("Retained draft path is unsafe") from exc
        if history_size + len(data) > DRAFT_HISTORY_MAX_BYTES:
            raise ValidationError("Draft history reached its 1 GiB limit; retained drafts require explicit review before more copies can be stored")
        _assert_draft_base(core, record, binding)
        draft_sha = hashlib.sha256(data).hexdigest()
        # Unique immutable payload first. A crash leaves diagnostic evidence,
        # while the prior complete payload remains reachable from current.json.
        _draft_publish_new(root / ("draft_" + draft["draft_id"] + ".json"), data)
        _assert_draft_base(core, record, binding)
        _draft_replace_pointer(root, {
            "schema": DRAFT_POINTER_SCHEMA, "authority": False, "scope": scope,
            "draft_status": "ACTIVE", "draft_id": draft["draft_id"],
            "draft_sha256": draft_sha, "updated_at": draft["saved_at"],
        }, current_sha)
        return {"draft_status": "SAVED", "draft_id": draft["draft_id"],
                "draft_sha256": draft_sha, "saved_at": draft["saved_at"]}


def load_draft(arguments: Mapping[str, Any]) -> dict[str, Any]:
    core, record, binding = _draft_context(arguments)
    root = _draft_root(record)
    if root is None:
        return {"draft_status": "MISSING"}
    scope = _draft_scope(core, record)
    summary = {}
    try:
        pointer, pointer_sha = _draft_current(root, scope)
        if pointer is None:
            return {"draft_status": "MISSING"}
        summary = {"draft_id": pointer["draft_id"], "draft_sha256": pointer["draft_sha256"]}
        if pointer["draft_status"] == "DISCARDED":
            return {"draft_status": "DISCARDED", **summary}
        draft = _draft_payload(root, pointer, scope)
        summary["saved_at"] = draft["saved_at"]
        if draft["base_binding"] != binding:
            return {"draft_status": "STALE", "reason": "The working state, revision, image or scale differs from the retained draft", **summary}
        # Missing/stale probes never walk the revision/scale history. The full
        # verification is reserved for a compatible payload offered to restore.
        core, record, verified_binding = _draft_context(arguments, verify_revision=True)
        if verified_binding != binding:
            raise StaleContextError("Draft context changed during recovery verification")
        _draft_snapshot(draft["snapshot"], core, record)
        if sha256_file(root / "current.json") != pointer_sha:
            raise StaleContextError("Draft pointer changed during recovery read")
        _assert_draft_base(core, record, binding)
        return {"draft_status": "AVAILABLE", "draft": draft, **summary}
    except (ValidationError, OSError, ValueError, TypeError, KeyError) as exc:
        return {"draft_status": "CORRUPT", "reason": str(exc), **summary}


def discard_draft(arguments: Mapping[str, Any]) -> dict[str, Any]:
    core = SessionCore(arguments["project_root"])
    record = p2._active_record(core, str(arguments["image_uid"]), str(arguments["analysis_session_uid"]))
    draft_id = p2._require_uuid4(arguments["draft_id"], "draft_id")
    expected_sha = p2._require_sha(arguments["expected_draft_sha256"], "expected_draft_sha256")
    root = _draft_root(record)
    if root is None:
        raise StaleContextError("No draft remains to discard")
    with _draft_writer_lock(root):
        pointer, pointer_sha = _draft_current(root, _draft_scope(core, record))
        if pointer is None or pointer["draft_id"] != draft_id or pointer["draft_sha256"] != expected_sha:
            raise StaleContextError("Draft changed before discard; no recovery evidence was removed")
        if pointer["draft_status"] != "DISCARDED":
            tombstone = dict(pointer)
            tombstone["draft_status"] = "DISCARDED"
            tombstone["updated_at"] = utc_now_z()
            _draft_publish_new(root / ("discard_" + str(uuid.uuid4()) + ".json"), _draft_envelope(tombstone))
            p2._active_record(core, record.image_uid, record.analysis_session_uid)
            _draft_replace_pointer(root, tombstone, pointer_sha)
        return {"draft_status": "DISCARDED", "draft_id": draft_id, "draft_sha256": expected_sha,
                "retention_policy": "RETAIN_NO_AUTOMATIC_DELETE"}


_OPERATIONS = dict(p2._OPERATIONS)
_OPERATIONS.update(
    {
        "p3_create_project": p3_create_project,
        "p3_register_source_image": p3_register_source_image,
        "p3_source_image_context": p3_source_image_context,
        "clone_revision": clone_revision,
        "commit_analysis_area_cache": commit_analysis_area_cache,
        "create_session": create_session,
        "save_draft": save_draft,
        "load_draft": load_draft,
        "discard_draft": discard_draft,
        "get_geometry_state": prepare_geometry_state,
        "inspect_run_scientific_scale": inspect_run_scientific_scale,
        "publish_run": publish_run,
        "reconcile_failed_run_reservation": reconcile_failed_run_reservation_request,
        "scale_preflight_no_write": scale_preflight_no_write,
        "publish_run_disposition": publish_run_disposition_request,
        "publish_scale_disposition": publish_scale_disposition,
        "save_revision": save_revision,
        "select_session": select_session,
        "set_display_mode": set_display_mode,
    }
)


def execute_request(request: Mapping[str, Any]) -> dict[str, Any]:
    if set(request) != {"arguments", "operation", "request_id", "schema"}:
        raise ValidationError("Prompt-3 bridge request field inventory is not closed")
    if request["schema"] != REQUEST_SCHEMA:
        raise ValidationError("Prompt-3 bridge request schema is not supported")
    request_id = p2._require_uuid4(request["request_id"], "request_id")
    operation = str(request["operation"])
    if operation == "cancel":
        return {
            "errors": [],
            "operation": operation,
            "request_id": request_id,
            "result": {
                "disk_writes": "RESPONSE_ONLY_OUTSIDE_PROJECT",
                "scientific_mutations": 0,
            },
            "schema": RESPONSE_SCHEMA,
            "status": "CANCELLED",
            "warnings": [],
        }
    handler = _OPERATIONS.get(operation)
    if handler is None:
        raise ValidationError("Prompt-3 bridge operation is not supported")
    result = handler(_mapping(request["arguments"], "arguments"))
    return {
        "errors": [],
        "operation": operation,
        "request_id": request_id,
        "result": result,
        "schema": RESPONSE_SCHEMA,
        "status": "PASS",
        "warnings": [],
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Cavity TEM Light Prompt-3 masks bridge")
    parser.add_argument("--request", required=True)
    parser.add_argument("--request-sha256", required=True)
    parser.add_argument("--response", required=True)
    args = parser.parse_args(argv)
    request_path = Path(args.request)
    response_path = Path(args.response)
    request_bytes = stable_plain_bytes(request_path, label="Prompt-3 bridge request")
    expected = p2._require_sha(args.request_sha256, "request_sha256")
    if hashlib.sha256(request_bytes).hexdigest() != expected:
        raise StaleContextError("Prompt-3 bridge request SHA-256 mismatch")
    request = loads_canonical_json(request_bytes)
    p2._outside_project(response_path, request)
    try:
        response = execute_request(request)
        code = 0
    except (ValidationError, StaleContextError, TransactionError) as exc:
        response = {
            "errors": [
                {
                    "code": getattr(exc, "code", exc.__class__.__name__),
                    "column": getattr(exc, "details", {}).get("column"),
                    "details": getattr(exc, "details", {}),
                    "message": str(exc),
                    "path": getattr(exc, "details", {}).get("path"),
                    "row": getattr(exc, "details", {}).get("row"),
                }
            ],
            "operation": request.get("operation", "UNKNOWN")
            if isinstance(request, Mapping)
            else "UNKNOWN",
            "request_id": request.get("request_id", "UNKNOWN")
            if isinstance(request, Mapping)
            else "UNKNOWN",
            "result": {},
            "schema": RESPONSE_SCHEMA,
            "status": "ERROR",
            "warnings": [],
        }
        code = 2
    except Exception as exc:  # closed last-resort envelope
        response = {
            "errors": [
                {
                    "code": "INTERNAL_ERROR_REINSPECT_REQUIRED",
                    "column": None,
                    "details": {"exception_type": type(exc).__name__},
                    "message": "unexpected Prompt-3 bridge failure; re-inspect physical state",
                    "path": None,
                    "row": None,
                }
            ],
            "operation": request.get("operation", "UNKNOWN")
            if isinstance(request, Mapping)
            else "UNKNOWN",
            "request_id": request.get("request_id", "UNKNOWN")
            if isinstance(request, Mapping)
            else "UNKNOWN",
            "result": {},
            "schema": RESPONSE_SCHEMA,
            "status": "ERROR",
            "warnings": [],
        }
        code = 3
    p2._write_new_response(response_path, canonical_json_bytes(response))
    return code


if __name__ == "__main__":
    sys.exit(main())


__all__ = [
    "REQUEST_SCHEMA",
    "RESPONSE_SCHEMA",
    "clone_revision",
    "commit_analysis_area_cache",
    "execute_request",
    "prepare_geometry_state",
    "inspect_run_scientific_scale",
    "publish_run",
    "publish_scale_disposition",
    "save_revision",
    "select_session",
    "set_display_mode",
]
