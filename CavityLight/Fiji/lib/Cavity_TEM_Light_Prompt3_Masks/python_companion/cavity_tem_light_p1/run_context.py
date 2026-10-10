"""Closed authority selection for the shared RUN-v2 implementation.

Prompt 1 remains the default context of the reusable RUN writer/consumer.  A
native schema-2 RUN is enabled only by an explicit :class:`RunContractContext`
created from verified project and physical-session authorities.  Manifest
bytes are never used to select their own validator.
"""

from __future__ import annotations

import hashlib
import os
import re
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping

from .canonical_json import loads_canonical_json
from .errors import ValidationError
from .identity import (
    CTL_UUID_NAMESPACE_V1,
    confirmed_image_parent_component,
    derive_image_uid,
)
from .path_safety import PathSafetyError, lexical_absolute, stable_plain_bytes


P1_BRIDGE_ORIGINAL = "P1_BRIDGE_ORIGINAL"
P2_SCHEMA2_NATIVE = "P2_SCHEMA2_NATIVE"
NATIVE_SCHEMA2_ADAPTER_ID = "CTL_RUN_V2_SCHEMA2_NATIVE_ADAPTER_V1"
UNSUPPORTED_MIGRATION_CODE = "UNSUPPORTED_IN_P2A_MIGRATION_DEFERRED"
SESSION_PARENT_MISMATCH_CODE = "RUN_SESSION_PARENT_MISMATCH"
PHYSICAL_AUTHORITY_REQUIRED_CODE = "RUN_CONTEXT_PHYSICAL_AUTHORITY_REQUIRED"
PHYSICAL_AUTHORITY_CHANGED_CODE = "RUN_CONTEXT_PHYSICAL_AUTHORITY_CHANGED"
PHYSICAL_AUTHORITY_SOURCE = "PHYSICAL_VERIFIED"

_UUID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"
)
_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_P1_VALUES = {
    "project_schema_version": 1,
    "run_contract_version": 2,
    "source_project_schema_version": 1,
    "session_model_status": "LEGACY_SINGLE_SESSION_BRIDGE",
}
_P2_NATIVE_VALUES = {
    "project_schema_version": 2,
    "run_contract_version": 2,
    "source_project_schema_version": 2,
    "session_model_status": "NATIVE_MULTI_SESSION_V2",
}
# Copy-only R9 migration publishes a physical schema-2 project and session;
# its valid-prefix revision is therefore a native RUN parent.  The legacy
# source, legacy RUNs and legacy_quarantine never become RUN authorities.
_P2A_NATIVE_ORIGINS = frozenset(
    {"NEW_EMPTY", "CLONE_REVISION", "MIGRATED_LEGACY_BRIDGE"}
)
_P2_PROJECT_AUTHORITY_FIELDS = frozenset(
    {"created_at", "project_id", "project_schema_version", "project_uid", "schema"}
)
_P2_SESSION_AUTHORITY_FIELDS = frozenset(
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
_AUTHORITY_TOKEN = object()


class UnsupportedP2AMigrationError(ValidationError):
    """A schema-1/migrated RUN case whose semantics are deferred to P2C."""

    code = UNSUPPORTED_MIGRATION_CODE


class RunSessionParentMismatchError(ValidationError):
    """The RUN identity/control paths do not belong to the verified parent."""

    code = SESSION_PARENT_MISMATCH_CODE


class RunContextPhysicalAuthorityRequiredError(ValidationError):
    """A caller attempted to grant native authority without physical files."""

    code = PHYSICAL_AUTHORITY_REQUIRED_CODE


class RunContextPhysicalAuthorityChangedError(ValidationError):
    """A physically bound project/session authority changed after loading."""

    code = PHYSICAL_AUTHORITY_CHANGED_CODE


def _unsupported(message: str, **details: Any) -> None:
    raise UnsupportedP2AMigrationError(
        message,
        details={"code": UNSUPPORTED_MIGRATION_CODE, **details},
    )


def _parent_mismatch(message: str, **details: Any) -> None:
    raise RunSessionParentMismatchError(
        message,
        details={"code": SESSION_PARENT_MISMATCH_CODE, **details},
    )


def _physical_authority_required(message: str, **details: Any) -> None:
    raise RunContextPhysicalAuthorityRequiredError(
        message,
        details={"code": PHYSICAL_AUTHORITY_REQUIRED_CODE, **details},
    )


def _physical_authority_changed(message: str, **details: Any) -> None:
    raise RunContextPhysicalAuthorityChangedError(
        message,
        details={"code": PHYSICAL_AUTHORITY_CHANGED_CODE, **details},
    )


def _require_uuid(value: Any, field: str) -> str:
    if not isinstance(value, str) or _UUID_RE.fullmatch(value) is None:
        _parent_mismatch("verified RUN authority UUID is invalid", field=field, value=value)
    try:
        parsed = uuid.UUID(value)
    except ValueError:
        _parent_mismatch("verified RUN authority UUID is invalid", field=field, value=value)
    if str(parsed) != value:
        _parent_mismatch("verified RUN authority UUID is not canonical", field=field, value=value)
    return value


def _require_id(value: Any, field: str) -> str:
    if not isinstance(value, str) or _ID_RE.fullmatch(value) is None:
        _parent_mismatch("verified RUN authority identifier is invalid", field=field, value=value)
    return value


@dataclass(frozen=True, slots=True)
class RunContractContext:
    """Selected RUN contract plus its independently verified physical owner."""

    context_id: str
    adapter_id: str
    project_schema_version: int
    run_contract_version: int
    source_project_schema_version: int
    session_model_status: str
    project_migration: bool
    project_uid: str | None = None
    image_uid: str | None = None
    analysis_session_id: str | None = None
    analysis_session_uid: str | None = None
    project_root: Path | None = None
    physical_project_root: Path | None = None
    physical_parent_root: Path | None = None
    project_authority_sha256: str | None = None
    session_authority_sha256: str | None = None
    authority_source: str | None = None
    _verified_authority_token: object | None = field(default=None, repr=False, compare=False)

    @property
    def is_native_schema2(self) -> bool:
        return self.context_id == P2_SCHEMA2_NATIVE

    @property
    def contract_id(self) -> str:
        """Stable public name of the selected physical contract/adapter."""

        return self.adapter_id

    @property
    def manifest_values(self) -> dict[str, Any]:
        # Prompt 1 remains byte-exact and therefore does not gain the external
        # project_migration assertion.  The approved schema-2 correction makes
        # that fifth value explicit only in native P2 manifests.
        values = {
            "project_schema_version": self.project_schema_version,
            "run_contract_version": self.run_contract_version,
            "source_project_schema_version": self.source_project_schema_version,
            "session_model_status": self.session_model_status,
        }
        if self.is_native_schema2:
            # The correction authority makes this execution assertion an
            # explicit native-schema2 context value.  It is absent from the
            # byte-exact Prompt-1 default and therefore cannot change P1 bytes.
            values["project_migration"] = self.project_migration
        return values

    @property
    def object_table_overlay(self) -> dict[str, Any]:
        """The only four P1 table columns that the adapter may overlay."""

        return {
            "project_schema_version": self.project_schema_version,
            "run_contract_version": self.run_contract_version,
            "source_project_schema_version": self.source_project_schema_version,
            "session_model_status": self.session_model_status,
        }

    def revalidate_physical_authorities(self) -> None:
        """Reopen and reconcile the two authorities bound to a native context.

        The private token is deliberately insufficient: every native use is
        authorized again from the exact canonical ``project.json`` and
        ``session_metadata.json`` bytes whose hashes were captured by
        :func:`load_run_context`.
        """

        if self.is_native_schema2:
            _revalidate_native_authorities(self)

    def validate_manifest_owner(self, manifest: Mapping[str, Any]) -> None:
        for field, expected in self.manifest_values.items():
            if manifest.get(field) != expected:
                raise ValidationError(
                    "RUN manifest context differs from the selected authority",
                    details={
                        "adapter_id": self.adapter_id,
                        "field": field,
                        "expected": expected,
                        "actual": manifest.get(field),
                    },
                )
        if not self.is_native_schema2:
            return
        self.revalidate_physical_authorities()
        expected_owner = {
            "project_uid": self.project_uid,
            "image_uid": self.image_uid,
            "analysis_session_id": self.analysis_session_id,
            "analysis_session_uid": self.analysis_session_uid,
        }
        for field, expected in expected_owner.items():
            if expected is not None and manifest.get(field) != expected:
                _parent_mismatch(
                    "native schema-2 RUN does not match its verified physical parent",
                    field=field,
                    expected=expected,
                    actual=manifest.get(field),
                )

    def validate_control_paths(
        self,
        *,
        run_parent: os.PathLike[str] | str | None = None,
        resolution_root: os.PathLike[str] | str | None = None,
        current_pointer_path: os.PathLike[str] | str | None = None,
        registry_path: os.PathLike[str] | str | None = None,
        run_directory: os.PathLike[str] | str | None = None,
    ) -> None:
        """Bind every mutable/immutable RUN path to one physical session."""

        if not self.is_native_schema2:
            return
        self.revalidate_physical_authorities()
        if self.physical_parent_root is None:  # defensive after revalidation
            _physical_authority_required("native RUN context has no physical session root")
        owner = self.physical_parent_root
        checks: list[tuple[str, Path, Path]] = []
        if resolution_root is not None:
            checks.append(("resolution_root", Path(resolution_root), owner))
        if run_parent is not None:
            checks.append(("run_parent", Path(run_parent), owner / "runs"))
        if current_pointer_path is not None:
            checks.append(("current_pointer_path", Path(current_pointer_path), owner / "current_run.tsv"))
        if registry_path is not None:
            checks.append(("registry_path", Path(registry_path), owner / "run_registry.json"))
        if run_directory is not None:
            candidate = Path(run_directory)
            try:
                candidate.parent.relative_to(owner / "runs")
            except ValueError:
                _parent_mismatch(
                    "RUN directory is outside the verified session runs directory",
                    path=str(candidate),
                    owner=str(owner),
                )
            if candidate.parent != owner / "runs":
                _parent_mismatch(
                    "RUN directory must be an immediate child of the verified session runs directory",
                    path=str(candidate),
                    owner=str(owner),
                )
        for field, actual, expected in checks:
            try:
                actual_absolute = actual.absolute()
                expected_absolute = expected.absolute()
            except OSError as exc:
                _parent_mismatch("RUN control path cannot be resolved lexically", field=field, reason=str(exc))
            if actual_absolute != expected_absolute:
                _parent_mismatch(
                    "RUN control path belongs to a different physical session",
                    field=field,
                    expected=str(expected_absolute),
                    actual=str(actual_absolute),
                )


P1_RUN_CONTEXT = RunContractContext(
    context_id=P1_BRIDGE_ORIGINAL,
    adapter_id=P1_BRIDGE_ORIGINAL,
    project_schema_version=1,
    run_contract_version=2,
    source_project_schema_version=1,
    session_model_status="LEGACY_SINGLE_SESSION_BRIDGE",
    project_migration=False,
    _verified_authority_token=_AUTHORITY_TOKEN,
)


def normalize_run_context(run_context: RunContractContext | None) -> RunContractContext:
    if run_context is None:
        return P1_RUN_CONTEXT
    if not isinstance(run_context, RunContractContext):
        raise TypeError("run_context must be RunContractContext or None")
    if run_context.context_id == P1_BRIDGE_ORIGINAL:
        expected = _P1_VALUES
        expected_adapter = P1_BRIDGE_ORIGINAL
    elif run_context.context_id == P2_SCHEMA2_NATIVE:
        expected = _P2_NATIVE_VALUES
        expected_adapter = NATIVE_SCHEMA2_ADAPTER_ID
    else:
        raise ValidationError(
            "RUN context identifier is outside the closed adapter set",
            details={"context_id": run_context.context_id},
        )
    observed = {
        "project_schema_version": run_context.project_schema_version,
        "run_contract_version": run_context.run_contract_version,
        "source_project_schema_version": run_context.source_project_schema_version,
        "session_model_status": run_context.session_model_status,
    }
    if (
        observed != expected
        or run_context.project_migration is not False
        or run_context.adapter_id != expected_adapter
        or run_context._verified_authority_token is not _AUTHORITY_TOKEN
    ):
        raise ValidationError(
            "RUN context was not produced by a verified closed authority selection",
            details={"context_id": run_context.context_id, "adapter_id": run_context.adapter_id},
        )
    run_context.revalidate_physical_authorities()
    return run_context


def _validate_native_authority_values(
    project: Mapping[str, Any],
    parent: Mapping[str, Any],
) -> tuple[str, str, str, str, str]:
    """Validate the closed schema-2 values without granting authority."""

    if project.get("project_schema_version") != 2:
        _unsupported(
            "project authority is not native schema 2",
            project_schema_version=project.get("project_schema_version"),
        )
    project_uid = _require_uuid(project.get("project_uid"), "project_uid")
    if project.get("source_project_schema_version", 2) != 2:
        _unsupported(
            "source_project_schema_version=1 is deferred to P2C",
            source_project_schema_version=project.get("source_project_schema_version"),
        )
    if project.get("project_migration", False) is not False:
        _unsupported(
            "project_migration=true is deferred to P2C",
            project_migration=project.get("project_migration"),
        )
    if project.get("run_contract_version", 2) != 2:
        raise ValidationError("native schema-2 RUN contract version is not 2")
    if project.get("session_model_status", "NATIVE_MULTI_SESSION_V2") != "NATIVE_MULTI_SESSION_V2":
        _unsupported(
            "legacy session model cannot select the native schema-2 adapter",
            session_model_status=project.get("session_model_status"),
        )
    if project.get("schema") != "CTL_P2A_PROJECT_JSON_V1":
        _unsupported("schema-2 project authority is not native P2A", schema=project.get("schema"))

    if parent.get("project_uid") != project_uid:
        _parent_mismatch(
            "session project_uid differs from verified project",
            expected=project_uid,
            actual=parent.get("project_uid"),
        )
    if parent.get("project_schema_version", 2) != 2:
        _unsupported(
            "physical session parent is not native schema 2",
            project_schema_version=parent.get("project_schema_version"),
        )
    if parent.get("source_project_schema_version", 2) != 2:
        _unsupported(
            "physical session source schema is deferred to P2C",
            source_project_schema_version=parent.get("source_project_schema_version"),
        )
    if parent.get("project_migration", False) is not False:
        _unsupported("migrated physical session is deferred to P2C")
    if parent.get("run_contract_version", 2) != 2:
        raise ValidationError("physical session RUN contract version is not 2")
    if parent.get("session_model_status", "NATIVE_MULTI_SESSION_V2") != "NATIVE_MULTI_SESSION_V2":
        _unsupported(
            "legacy session model cannot be used as a native schema-2 RUN parent",
            session_model_status=parent.get("session_model_status"),
        )
    if parent.get("schema") != "CTL_SESSION_METADATA_JSON_V1":
        _unsupported(
            "physical session authority is not the native P2A profile",
            schema=parent.get("schema"),
        )
    origin = parent.get("origin_type")
    if origin not in _P2A_NATIVE_ORIGINS:
        _unsupported("session origin requires P2C migration semantics", origin_type=origin)

    session_id = _require_id(parent.get("analysis_session_id"), "analysis_session_id")
    session_uid = _require_uuid(parent.get("analysis_session_uid"), "analysis_session_uid")
    image_id = _require_id(parent.get("image_id"), "image_id")
    image_uid = _require_uuid(parent.get("image_uid"), "image_uid")
    return project_uid, image_id, image_uid, session_id, session_uid


def _read_native_authorities(
    project_root: os.PathLike[str] | str,
    physical_parent_root: os.PathLike[str] | str,
) -> tuple[Path, Path, bytes, bytes, dict[str, Any], dict[str, Any]]:
    """Read stable single-link canonical authorities and bind their tree."""

    project = lexical_absolute(project_root, label="RUN project authority root")
    parent = lexical_absolute(physical_parent_root, label="RUN physical session parent")
    relative = parent.relative_to(project)
    # Each stable read checks the entire lexical ancestor chain before and
    # after opening, requires a single-link regular file, and binds its path
    # and handle snapshots. Its existing ancestors must therefore be plain
    # directories. Separate directory/file prechecks only repeat that work.
    # Keep both physical reads on EVERY use; no authority result is cached.
    project_bytes = stable_plain_bytes(project / "project.json", label="RUN project authority")
    parent_bytes = stable_plain_bytes(
        parent / "session_metadata.json", label="RUN session authority"
    )
    project_value = loads_canonical_json(project_bytes)
    parent_value = loads_canonical_json(parent_bytes)
    if not isinstance(project_value, dict) or not isinstance(parent_value, dict):
        raise ValidationError("RUN adapter authorities must be canonical JSON objects")
    if set(project_value) != _P2_PROJECT_AUTHORITY_FIELDS:
        raise ValidationError("RUN project authority field inventory is not closed")
    if set(parent_value) != _P2_SESSION_AUTHORITY_FIELDS:
        raise ValidationError("RUN session authority field inventory is not closed")

    project_uid, image_id, image_uid, session_id, _session_uid = (
        _validate_native_authority_values(project_value, parent_value)
    )
    expected_labels = {
        0: "studies",
        2: "conditions",
        4: "specimens",
        6: "lamellae",
        8: "images",
        10: "sessions",
    }
    if len(relative.parts) != 12 or any(
        relative.parts[index] != expected for index, expected in expected_labels.items()
    ):
        _parent_mismatch(
            "physical session is outside the closed schema-2 hierarchy",
            project_uid=project_uid,
            relative_path=relative.as_posix(),
        )
    if relative.parts[9] != image_id:
        _parent_mismatch(
            "physical image directory differs from session image_id",
            expected=image_id,
            actual=relative.parts[9],
        )
    study_id = _require_id(relative.parts[1], "study_id")
    condition_id = _require_id(relative.parts[3], "condition_id")
    specimen_id = _require_id(relative.parts[5], "specimen_id")
    lamella_id = _require_id(relative.parts[7], "lamella_id")
    study_uid = str(
        uuid.uuid5(
            CTL_UUID_NAMESPACE_V1,
            f"p2a-study|{project_uid}|{project_uid}|{study_id}",
        )
    )
    condition_uid = str(
        uuid.uuid5(
            CTL_UUID_NAMESPACE_V1,
            f"p2a-condition|{project_uid}|{study_uid}|{condition_id}",
        )
    )
    specimen_uid = str(
        uuid.uuid5(
            CTL_UUID_NAMESPACE_V1,
            f"p2a-specimen|{project_uid}|{condition_uid}|{specimen_id}",
        )
    )
    lamella_uid = str(
        uuid.uuid5(
            CTL_UUID_NAMESPACE_V1,
            f"p2a-lamella|{project_uid}|{specimen_uid}|{lamella_id}",
        )
    )
    expected_image_uid = derive_image_uid(
        project_uid,
        confirmed_image_parent_component(study_uid, specimen_uid, lamella_uid),
        image_id,
    )
    if image_uid != expected_image_uid:
        _parent_mismatch(
            "physical image UID differs from the closed hierarchy identity",
            expected=expected_image_uid,
            actual=image_uid,
        )
    expected_session_name = f"SESSION_{session_id}"
    if relative.parts[11] != expected_session_name:
        _parent_mismatch(
            "physical session directory differs from analysis_session_id",
            expected=expected_session_name,
            actual=relative.parts[11],
        )
    return project, parent, project_bytes, parent_bytes, project_value, parent_value


def _native_context_from_physical_authorities(
    project: Path,
    parent: Path,
    project_bytes: bytes,
    parent_bytes: bytes,
    project_value: Mapping[str, Any],
    parent_value: Mapping[str, Any],
) -> RunContractContext:
    project_uid, _image_id, image_uid, session_id, session_uid = (
        _validate_native_authority_values(project_value, parent_value)
    )
    return RunContractContext(
        context_id=P2_SCHEMA2_NATIVE,
        adapter_id=NATIVE_SCHEMA2_ADAPTER_ID,
        project_schema_version=2,
        run_contract_version=2,
        source_project_schema_version=2,
        session_model_status="NATIVE_MULTI_SESSION_V2",
        project_migration=False,
        project_uid=project_uid,
        image_uid=image_uid,
        analysis_session_id=session_id,
        analysis_session_uid=session_uid,
        project_root=project,
        physical_project_root=project,
        physical_parent_root=parent,
        project_authority_sha256=hashlib.sha256(project_bytes).hexdigest(),
        session_authority_sha256=hashlib.sha256(parent_bytes).hexdigest(),
        authority_source=PHYSICAL_AUTHORITY_SOURCE,
        _verified_authority_token=_AUTHORITY_TOKEN,
    )


def _revalidate_native_authorities(context: RunContractContext) -> None:
    """Reject missing, swapped, unsafe, or changed native authorities."""

    if (
        context.authority_source != PHYSICAL_AUTHORITY_SOURCE
        or context.physical_project_root is None
        or context.physical_parent_root is None
        or context.project_root is None
        or not isinstance(context.project_authority_sha256, str)
        or _SHA256_RE.fullmatch(context.project_authority_sha256) is None
        or not isinstance(context.session_authority_sha256, str)
        or _SHA256_RE.fullmatch(context.session_authority_sha256) is None
    ):
        _physical_authority_required(
            "native schema-2 RUN context lacks verified physical authority bindings"
        )
    if context.project_root != context.physical_project_root:
        _physical_authority_changed(
            "native RUN project roots disagree",
            project_root=str(context.project_root),
            physical_project_root=str(context.physical_project_root),
        )

    try:
        project, parent, project_bytes, parent_bytes, project_value, parent_value = (
            _read_native_authorities(
                context.physical_project_root,
                context.physical_parent_root,
            )
        )
        project_uid, _image_id, image_uid, session_id, session_uid = (
            _validate_native_authority_values(project_value, parent_value)
        )
    except (PathSafetyError, ValueError, ValidationError) as exc:
        _physical_authority_changed(
            "native RUN physical authorities cannot be reopened and reconciled",
            cause=str(exc),
            cause_code=getattr(exc, "code", type(exc).__name__),
        )

    observed_project_sha256 = hashlib.sha256(project_bytes).hexdigest()
    observed_session_sha256 = hashlib.sha256(parent_bytes).hexdigest()
    expected = {
        "project_root": context.physical_project_root,
        "physical_parent_root": context.physical_parent_root,
        "project_uid": context.project_uid,
        "image_uid": context.image_uid,
        "analysis_session_id": context.analysis_session_id,
        "analysis_session_uid": context.analysis_session_uid,
        "project_authority_sha256": context.project_authority_sha256,
        "session_authority_sha256": context.session_authority_sha256,
    }
    observed = {
        "project_root": project,
        "physical_parent_root": parent,
        "project_uid": project_uid,
        "image_uid": image_uid,
        "analysis_session_id": session_id,
        "analysis_session_uid": session_uid,
        "project_authority_sha256": observed_project_sha256,
        "session_authority_sha256": observed_session_sha256,
    }
    for field, expected_value in expected.items():
        if observed[field] != expected_value:
            _physical_authority_changed(
                "native RUN physical authority binding changed after load",
                field=field,
                expected=str(expected_value),
                actual=str(observed[field]),
            )


def select_run_context(
    verified_project: Mapping[str, Any],
    verified_physical_parent: Mapping[str, Any] | None = None,
    *,
    project_root: os.PathLike[str] | str | None = None,
    physical_parent_root: os.PathLike[str] | str | None = None,
) -> RunContractContext:
    """Select only the mapping-backed P1 bridge context.

    Native schema 2 is deliberately impossible through this mapping API,
    even when a caller also supplies path strings.  :func:`load_run_context`
    is its sole public authority boundary.
    """

    if not isinstance(verified_project, Mapping):
        raise ValidationError("verified project authority must be an object")
    schema_version = verified_project.get("project_schema_version")
    if isinstance(schema_version, bool) or schema_version not in {1, 2}:
        raise ValidationError(
            "verified project schema version is unsupported",
            details={"project_schema_version": schema_version},
        )
    project_uid = _require_uuid(verified_project.get("project_uid"), "project_uid")
    checked_project_root = Path(project_root).absolute() if project_root is not None else None

    if schema_version == 1:
        if verified_project.get("run_contract_version", 2) != 2:
            raise ValidationError("schema-1 bridge RUN contract version is not 2")
        if verified_project.get("source_project_schema_version", 1) != 1:
            _unsupported("schema-1 project source context is not the P1 bridge")
        if verified_project.get(
            "session_model_status", "LEGACY_SINGLE_SESSION_BRIDGE"
        ) != "LEGACY_SINGLE_SESSION_BRIDGE":
            _unsupported("schema-1 project session model is not the P1 bridge")
        if verified_project.get("project_migration", False) is not False:
            _unsupported("schema-1 project migration is deferred to P2C")
        return RunContractContext(
            context_id=P1_BRIDGE_ORIGINAL,
            adapter_id=P1_BRIDGE_ORIGINAL,
            project_schema_version=1,
            run_contract_version=2,
            source_project_schema_version=1,
            session_model_status="LEGACY_SINGLE_SESSION_BRIDGE",
            project_migration=False,
            project_uid=project_uid,
            project_root=checked_project_root,
            _verified_authority_token=_AUTHORITY_TOKEN,
        )

    if not isinstance(verified_physical_parent, Mapping):
        _physical_authority_required(
            "native schema-2 RUN context requires physical project/session authorities"
        )
    # Preserve the existing closed migration diagnostics, but never turn even
    # a valid pair of caller mappings into native authority.
    _validate_native_authority_values(verified_project, verified_physical_parent)
    _physical_authority_required(
        "native schema-2 RUN context cannot be selected from caller mappings",
        project_root_supplied=project_root is not None,
        physical_parent_root_supplied=physical_parent_root is not None,
    )


def load_run_context(
    project_root: os.PathLike[str] | str,
    physical_parent_root: os.PathLike[str] | str,
) -> RunContractContext:
    """Read, hash, reconcile, and bind physical native RUN authorities."""

    try:
        project, parent, project_bytes, parent_bytes, project_value, parent_value = (
            _read_native_authorities(project_root, physical_parent_root)
        )
    except (PathSafetyError, ValueError) as exc:
        raise ValidationError(
            "RUN adapter authorities are absent, unsafe, or non-canonical",
            details={"cause": str(exc)},
        ) from exc
    context = _native_context_from_physical_authorities(
        project,
        parent,
        project_bytes,
        parent_bytes,
        project_value,
        parent_value,
    )
    # Reopen once before returning so a swap between initial load and context
    # construction is detected; every later use repeats the same check.
    context.revalidate_physical_authorities()
    return context


__all__ = [
    "NATIVE_SCHEMA2_ADAPTER_ID",
    "PHYSICAL_AUTHORITY_CHANGED_CODE",
    "PHYSICAL_AUTHORITY_REQUIRED_CODE",
    "PHYSICAL_AUTHORITY_SOURCE",
    "P1_BRIDGE_ORIGINAL",
    "P1_RUN_CONTEXT",
    "P2_SCHEMA2_NATIVE",
    "RunContractContext",
    "RunContextPhysicalAuthorityChangedError",
    "RunContextPhysicalAuthorityRequiredError",
    "RunSessionParentMismatchError",
    "UnsupportedP2AMigrationError",
    "load_run_context",
    "normalize_run_context",
    "select_run_context",
]
