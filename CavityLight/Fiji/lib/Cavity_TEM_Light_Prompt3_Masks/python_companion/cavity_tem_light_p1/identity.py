"""Closed Prompt-1 identity recipes and provenance validation."""

from __future__ import annotations

from datetime import datetime
import hashlib
import re
import unicodedata
import uuid
from typing import Any, Mapping, Sequence

from .errors import ValidationError


CTL_UUID_NAMESPACE_ORIGIN = "urn:cavity-tem-light:identity:v1"
CTL_UUID_NAMESPACE_V1 = uuid.UUID("07eb0a06-53cb-5be4-8f61-7b52038d4706")
UUID_NAMESPACE_VERSION = "CTL_UUID_NAMESPACE_V1"
UUID_NAME_ENCODING = "UTF8_PIPE_V1"
IDENTITY_PROVENANCE_COVERAGE_VERSION = "IDENTITY_PROVENANCE_COVERAGE_V1"

UUID_METHODS = frozenset(
    {
        "UUIDV4_RANDOM",
        "UUIDV5_CTL_LEGACY_V1",
        "PRESERVED",
        "NOT_ASSIGNED_UNKNOWN",
    }
)
TEMPLATE_IDS = frozenset(
    {
        "PROJECT_UID_V1",
        "IMAGE_UID_V1",
        "SESSION_UID_V1",
        "REVISION_UID_V1",
        "OBJECT_UID_V1",
    }
)

HUMAN_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$", re.ASCII)
CAVITY_ID_PATTERN = re.compile(r"^CAV_[0-9]{6}$", re.ASCII)
SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$", re.ASCII)
RFC3339_UTC_PATTERN = re.compile(
    r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(?:\.[0-9]{0,5}[1-9])?Z$",
    re.ASCII,
)

IDENTITY_UID_FIELDS: dict[str, str] = {
    "project": "project_uid",
    "study": "study_uid",
    "specimen": "specimen_uid",
    "lamella": "lamella_uid",
    "image": "image_uid",
    "analysis_session": "analysis_session_uid",
    "revision": "revision_uid",
    "run": "run_uid",
    "object": "object_uuid",
    "candidate": "candidate_uuid",
}

_ENTITY_TEMPLATES = {
    "project": "PROJECT_UID_V1",
    "image": "IMAGE_UID_V1",
    "analysis_session": "SESSION_UID_V1",
    "revision": "REVISION_UID_V1",
    "object": "OBJECT_UID_V1",
}
_IDENTITY_SENTINELS = frozenset({"UNKNOWN", "NOT_APPLICABLE", "NA"})
_WINDOWS_RESERVED = frozenset(
    {"CON", "PRN", "AUX", "NUL"}
    | {f"COM{number}" for number in range(1, 10)}
    | {f"LPT{number}" for number in range(1, 10)}
)


def _fail(message: str, **details: Any) -> None:
    raise ValidationError(message, details=details)


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _check_bytes(value: bytes, *, field: str) -> None:
    if not isinstance(value, bytes):
        _fail("identity evidence must be bytes", field=field)


def validate_human_id(value: str, *, field: str = "identifier") -> str:
    """Validate the closed ASCII human-ID grammar without sanitizing it."""

    if not isinstance(value, str) or HUMAN_ID_PATTERN.fullmatch(value) is None:
        _fail("invalid human identifier", field=field, value=value)
    if value in _IDENTITY_SENTINELS:
        _fail("identity sentinel cannot be used as a real identifier", field=field, value=value)
    if ".." in value or value.endswith((".", " ")):
        _fail("unsafe human identifier", field=field, value=value)
    windows_basename = value.split(".", 1)[0].upper()
    if windows_basename in _WINDOWS_RESERVED:
        _fail("reserved Windows device name", field=field, value=value)
    return value


def validate_cavity_id(value: str) -> str:
    if not isinstance(value, str) or CAVITY_ID_PATTERN.fullmatch(value) is None:
        _fail("invalid cavity_id", value=value)
    if value == "CAV_000000":
        _fail("cavity_id sequence starts at CAV_000001", value=value)
    return value


def next_cavity_id(previous_ids: Sequence[str]) -> str:
    """Return the next never-reused session-local cavity ID.

    Gaps are intentionally not filled.  A duplicate or malformed historical ID
    fails closed because reuse history would otherwise be ambiguous.
    """

    seen: set[str] = set()
    maximum = 0
    for value in previous_ids:
        validate_cavity_id(value)
        if value in seen:
            _fail("duplicate historical cavity_id", value=value)
        seen.add(value)
        maximum = max(maximum, int(value[4:]))
    if maximum >= 999999:
        _fail("cavity_id namespace exhausted")
    return f"CAV_{maximum + 1:06d}"


def validate_candidate_object_identity(
    *,
    candidate_uuid: str,
    candidate_id: str,
    object_uuid_value: str | None = None,
    cavity_id: str | None = None,
) -> None:
    """Keep proposal identity separate from any accepted object identity."""

    validate_canonical_uuid(candidate_uuid)
    validate_human_id(candidate_id, field="candidate_id")
    if (object_uuid_value is None) != (cavity_id is None):
        _fail("object_uuid and cavity_id must be assigned together")
    if object_uuid_value is not None:
        validate_canonical_uuid(object_uuid_value)
        validate_cavity_id(cavity_id)
        if object_uuid_value == candidate_uuid:
            _fail("candidate_uuid cannot be reused as object_uuid")


def validate_canonical_relative_path(value: str) -> str:
    """Validate a portable NFC POSIX path used as identity evidence."""

    if not isinstance(value, str) or not value:
        _fail("registry relative path is empty")
    if any(0xD800 <= ord(char) <= 0xDFFF for char in value):
        _fail("registry relative path contains an isolated Unicode surrogate")
    if unicodedata.normalize("NFC", value) != value:
        _fail("registry relative path is not NFC", value=value)
    if "\\" in value or "\x00" in value or value.startswith("/"):
        _fail("registry path is not canonical relative POSIX", value=value)
    if re.match(r"^[A-Za-z]:", value) or "://" in value:
        _fail("registry path cannot contain drive or URI root", value=value)
    parts = value.split("/")
    if any(part in {"", ".", ".."} or part.endswith((".", " ")) for part in parts):
        _fail("registry path contains unsafe segment", value=value)
    return value


def validate_canonical_uuid(value: str, *, expected_version: int | None = None) -> str:
    if not isinstance(value, str):
        _fail("UUID must be a string", value=value)
    try:
        parsed = uuid.UUID(value)
    except (ValueError, AttributeError, TypeError):
        _fail("invalid UUID", value=value)
    if str(parsed) != value:
        _fail("UUID is not lowercase canonical form", value=value)
    if expected_version is not None and parsed.version != expected_version:
        _fail("UUID version mismatch", value=value, expected_version=expected_version)
    return value


def _uuid5_name(name: str) -> str:
    # All recipe components are already validated ASCII/canonical UUID or
    # lowercase digest, so the UTF-8 bytes are unambiguous and are not NFC- or
    # case-normalized here.
    if not isinstance(name, str) or "\n" in name or "\r" in name or "\x00" in name:
        _fail("invalid UUIDv5 name")
    return str(uuid.uuid5(CTL_UUID_NAMESPACE_V1, name))


def validate_namespace_constant() -> None:
    expected = uuid.uuid5(uuid.NAMESPACE_URL, CTL_UUID_NAMESPACE_ORIGIN)
    if expected != CTL_UUID_NAMESPACE_V1:
        _fail(
            "CTL UUID namespace constant does not match its normative origin",
            expected=str(expected),
            observed=str(CTL_UUID_NAMESPACE_V1),
        )


def legacy_project_identity_token(descriptor_exact_bytes: bytes, project_id: str) -> str:
    _check_bytes(descriptor_exact_bytes, field="descriptor_exact_bytes")
    validate_human_id(project_id, field="project_id")
    return _sha256(descriptor_exact_bytes + b"\x00" + project_id.encode("ascii"))


def reconcile_legacy_project_identity_tokens(expected_token: str, observed_token: str) -> str:
    for field, value in (("expected_token", expected_token), ("observed_token", observed_token)):
        if not isinstance(value, str) or SHA256_PATTERN.fullmatch(value) is None:
            _fail("invalid legacy project identity token", field=field, value=value)
    if expected_token != observed_token:
        _fail(
            "copies claiming one project have conflicting origin tokens",
            expected=expected_token,
            observed=observed_token,
        )
    return expected_token


def project_uid_name(project_token: str, project_id: str) -> str:
    if SHA256_PATTERN.fullmatch(project_token or "") is None:
        _fail("invalid legacy project token", token=project_token)
    validate_human_id(project_id, field="project_id")
    return f"project|{project_token}|{project_id}"


def derive_project_uid(descriptor_exact_bytes: bytes, project_id: str) -> str:
    token = legacy_project_identity_token(descriptor_exact_bytes, project_id)
    return _uuid5_name(project_uid_name(token, project_id))


def legacy_image_parent_identity_token(
    canonical_registry_relative_path: str,
    data_row_ordinal_1_based: int,
    registry_row_exact_bytes: bytes,
) -> str:
    validate_canonical_relative_path(canonical_registry_relative_path)
    if not isinstance(data_row_ordinal_1_based, int) or isinstance(data_row_ordinal_1_based, bool) or data_row_ordinal_1_based < 1:
        _fail("registry data row ordinal must be a positive integer")
    _check_bytes(registry_row_exact_bytes, field="registry_row_exact_bytes")
    payload = (
        b"LEGACY_IMAGE_PARENT_TOKEN_V1\x00"
        + canonical_registry_relative_path.encode("utf-8")
        + b"\x00"
        + str(data_row_ordinal_1_based).encode("ascii")
        + b"\x00"
        + registry_row_exact_bytes
    )
    return _sha256(payload)


def confirmed_image_parent_component(study_uid: str, specimen_uid: str, lamella_uid: str) -> str:
    for field, value in (
        ("study_uid", study_uid),
        ("specimen_uid", specimen_uid),
        ("lamella_uid", lamella_uid),
    ):
        validate_canonical_uuid(value)
    return f"uids|{study_uid}|{specimen_uid}|{lamella_uid}"


def legacy_image_parent_component(token: str) -> str:
    if SHA256_PATTERN.fullmatch(token or "") is None:
        _fail("invalid legacy image parent token", token=token)
    return f"token|{token}"


def resolve_image_parent_identity_component(
    *,
    study_uid: str = "UNKNOWN",
    specimen_uid: str = "UNKNOWN",
    lamella_uid: str = "UNKNOWN",
    legacy_parent_tokens: Sequence[str] = (),
) -> str:
    """Resolve the frozen confirmed-UID-or-source-token parent alternative.

    Complete confirmed ancestry uses ``uids|...``.  Any unavailable ancestry
    requires exactly one reconciled legacy token; absence or conflicting token
    evidence is ``BLOCKED_REVIEW`` represented by a structured validation error.
    """

    uid_values = (study_uid, specimen_uid, lamella_uid)
    for field, value in zip(("study_uid", "specimen_uid", "lamella_uid"), uid_values):
        if value != "UNKNOWN":
            validate_canonical_uuid(value)
        elif not isinstance(value, str):  # defensive: reject None without leaking AttributeError
            _fail("unconfirmed parent UID must be the exact UNKNOWN sentinel", field=field)
    if all(value != "UNKNOWN" for value in uid_values):
        return confirmed_image_parent_component(*uid_values)
    if isinstance(legacy_parent_tokens, (str, bytes)) or not isinstance(
        legacy_parent_tokens, Sequence
    ):
        _fail("legacy parent tokens must be a sequence")
    normalized: list[str] = []
    for token in legacy_parent_tokens:
        legacy_image_parent_component(token)
        normalized.append(token)
    unique = set(normalized)
    if len(unique) != 1:
        _fail(
            "legacy image parent evidence is absent or conflicting",
            review_status="BLOCKED_REVIEW",
            token_count=len(normalized),
            unique_token_count=len(unique),
        )
    return legacy_image_parent_component(next(iter(unique)))


def image_uid_name(project_uid: str, image_parent_identity_component: str, image_id: str) -> str:
    validate_canonical_uuid(project_uid)
    validate_human_id(image_id, field="image_id")
    if not isinstance(image_parent_identity_component, str):
        _fail("image parent identity component must be a string")
    if image_parent_identity_component.startswith("token|"):
        legacy_image_parent_component(image_parent_identity_component[6:])
    elif image_parent_identity_component.startswith("uids|"):
        parts = image_parent_identity_component.split("|")
        if len(parts) != 4:
            _fail("invalid confirmed image parent component")
        confirmed_image_parent_component(*parts[1:])
    else:
        _fail("image parent identity component is neither confirmed nor legacy")
    return f"image|{project_uid}|{image_parent_identity_component}|{image_id}"


def derive_image_uid(project_uid: str, image_parent_identity_component: str, image_id: str) -> str:
    return _uuid5_name(image_uid_name(project_uid, image_parent_identity_component, image_id))


def synthesize_legacy_session_id(image_uid: str) -> str:
    validate_canonical_uuid(image_uid)
    result = "LEGACY_SESSION_" + image_uid.replace("-", "")
    validate_human_id(result, field="analysis_session_id")
    if len(result) != 47:
        _fail("synthesized legacy session ID has unexpected length")
    return result


def resolve_bridge_session_id(image_uid: str, legacy_analysis_session_id: str | None) -> dict[str, str]:
    """Preserve a valid source ID or synthesize only when it is absent."""

    if legacy_analysis_session_id is not None:
        validate_human_id(legacy_analysis_session_id, field="legacy_analysis_session_id")
        return {
            "analysis_session_id": legacy_analysis_session_id,
            "analysis_session_id_origin": "PRESERVED_LEGACY",
            "legacy_analysis_session_id": legacy_analysis_session_id,
            "legacy_analysis_session_identity_component": legacy_analysis_session_id,
            "legacy_analysis_session_identity_component_origin": "PRESERVED_LEGACY",
        }
    synthesized = synthesize_legacy_session_id(image_uid)
    return {
        "analysis_session_id": synthesized,
        "analysis_session_id_origin": "SYNTHESIZED_LEGACY_IMAGE_UID_V1",
        "legacy_analysis_session_id": "NOT_APPLICABLE",
        "legacy_analysis_session_identity_component": synthesized,
        "legacy_analysis_session_identity_component_origin": "SYNTHESIZED_LEGACY_IMAGE_UID_V1",
    }


def session_uid_name(project_uid: str, image_uid: str, analysis_session_id: str) -> str:
    validate_canonical_uuid(project_uid)
    validate_canonical_uuid(image_uid)
    validate_human_id(analysis_session_id, field="analysis_session_id")
    return f"legacy-session|{project_uid}|{image_uid}|{analysis_session_id}"


def derive_session_uid(project_uid: str, image_uid: str, analysis_session_id: str) -> str:
    return _uuid5_name(session_uid_name(project_uid, image_uid, analysis_session_id))


def revision_uid_name(
    project_uid: str,
    image_uid: str,
    analysis_session_uid: str,
    revision_id: str,
) -> str:
    validate_canonical_uuid(project_uid)
    validate_canonical_uuid(image_uid)
    validate_canonical_uuid(analysis_session_uid)
    validate_human_id(revision_id, field="revision_id")
    return f"revision|{project_uid}|{image_uid}|{analysis_session_uid}|{revision_id}"


def derive_revision_uid(
    project_uid: str,
    image_uid: str,
    analysis_session_uid: str,
    revision_id: str,
) -> str:
    return _uuid5_name(revision_uid_name(project_uid, image_uid, analysis_session_uid, revision_id))


def object_uuid_name(
    project_uid: str,
    image_uid: str,
    legacy_analysis_session_identity_component: str,
    cavity_id: str,
) -> str:
    validate_canonical_uuid(project_uid)
    validate_canonical_uuid(image_uid)
    validate_human_id(
        legacy_analysis_session_identity_component,
        field="legacy_analysis_session_identity_component",
    )
    validate_cavity_id(cavity_id)
    # Deliberately no ``object|`` prefix and no analysis_session_uid.
    return f"{project_uid}|{image_uid}|{legacy_analysis_session_identity_component}|{cavity_id}"


def derive_object_uuid(
    project_uid: str,
    image_uid: str,
    legacy_analysis_session_identity_component: str,
    cavity_id: str,
) -> str:
    return _uuid5_name(
        object_uuid_name(
            project_uid,
            image_uid,
            legacy_analysis_session_identity_component,
            cavity_id,
        )
    )


object_uuid = derive_object_uuid


def new_uuid4_identity() -> str:
    """Create a canonical UUIDv4 for a genuinely new v2 identity."""

    result = str(uuid.uuid4())
    validate_canonical_uuid(result, expected_version=4)
    return result


def compute_legacy_identity_bundle(
    *,
    descriptor_exact_bytes: bytes,
    project_id: str,
    canonical_registry_relative_path: str,
    data_row_ordinal_1_based: int,
    registry_row_exact_bytes: bytes,
    image_id: str,
    legacy_analysis_session_id: str | None,
    revision_id: str,
    cavity_id: str,
) -> dict[str, str]:
    """Compute the complete byte-exact legacy bridge chain."""

    project_token = legacy_project_identity_token(descriptor_exact_bytes, project_id)
    project_name = project_uid_name(project_token, project_id)
    project_uid = _uuid5_name(project_name)
    image_token = legacy_image_parent_identity_token(
        canonical_registry_relative_path,
        data_row_ordinal_1_based,
        registry_row_exact_bytes,
    )
    parent = legacy_image_parent_component(image_token)
    image_name = image_uid_name(project_uid, parent, image_id)
    image_uid = _uuid5_name(image_name)
    session = resolve_bridge_session_id(image_uid, legacy_analysis_session_id)
    session_name = session_uid_name(project_uid, image_uid, session["analysis_session_id"])
    analysis_session_uid = _uuid5_name(session_name)
    revision_name = revision_uid_name(project_uid, image_uid, analysis_session_uid, revision_id)
    revision_uid = _uuid5_name(revision_name)
    object_name = object_uuid_name(
        project_uid,
        image_uid,
        session["legacy_analysis_session_identity_component"],
        cavity_id,
    )
    result = {
        "legacy_project_identity_token": project_token,
        "project_uid_name": project_name,
        "project_uid": project_uid,
        "legacy_image_parent_identity_token": image_token,
        "image_parent_identity_component": parent,
        "image_uid_name": image_name,
        "image_uid": image_uid,
        **session,
        "analysis_session_uid_name": session_name,
        "analysis_session_uid": analysis_session_uid,
        "revision_uid_name": revision_name,
        "revision_uid": revision_uid,
        "object_uuid_name": object_name,
        "object_uuid": _uuid5_name(object_name),
    }
    return result


def _validate_sha_or_na(value: Any, *, field: str, required: bool) -> None:
    if required:
        if not isinstance(value, str) or SHA256_PATTERN.fullmatch(value) is None:
            _fail("required SHA-256 provenance field is invalid", field=field, value=value)
    elif value != "NOT_APPLICABLE":
        _fail("inapplicable provenance field must be NOT_APPLICABLE", field=field, value=value)


def _validate_recorded_at(value: Any) -> None:
    if not isinstance(value, str) or RFC3339_UTC_PATTERN.fullmatch(value) is None:
        _fail("provenance timestamp must be RFC3339 UTC Z", value=value)
    try:
        body = value[:-1]
        if "." in body:
            whole_seconds, fraction = body.split(".", 1)
            # Python 3.10 accepts only millisecond or microsecond fractions in
            # ``fromisoformat``.  The contract accepts every canonical
            # precision from one through six digits, so pad only for parsing;
            # the original byte spelling remains the provenance authority.
            parse_value = whole_seconds + "." + fraction.ljust(6, "0") + "+00:00"
        else:
            parse_value = body + "+00:00"
        datetime.fromisoformat(parse_value)
    except ValueError:
        _fail("invalid provenance timestamp", value=value)


def make_uuid5_provenance(
    *,
    owner_entity_key: str,
    entity_type: str,
    uid_value: str,
    name_template_id: str,
    name_utf8: bytes,
    source_identity_evidence: bytes,
    recorded_at: str,
) -> dict[str, str]:
    """Build, but do not silently weaken, a deterministic provenance row."""

    _check_bytes(name_utf8, field="name_utf8")
    _check_bytes(source_identity_evidence, field="source_identity_evidence")
    try:
        exact_name = name_utf8.decode("utf-8", errors="strict")
    except UnicodeDecodeError:
        _fail("UUIDv5 name evidence is not valid UTF-8")
    if _uuid5_name(exact_name) != uid_value:
        _fail("UUIDv5 value does not match the supplied exact name bytes")
    row = {
        "owner_entity_key": owner_entity_key,
        "coverage_map_version": IDENTITY_PROVENANCE_COVERAGE_VERSION,
        "entity_type": entity_type,
        "uid_field": IDENTITY_UID_FIELDS.get(entity_type, ""),
        "uid_value": uid_value,
        "uuid_generation_method": "UUIDV5_CTL_LEGACY_V1",
        "uuid_namespace_version": UUID_NAMESPACE_VERSION,
        "uuid_namespace_uuid": str(CTL_UUID_NAMESPACE_V1),
        "uuid_name_template_id": name_template_id,
        "uuid_name_utf8_sha256": _sha256(name_utf8),
        "source_identity_evidence_sha256": _sha256(source_identity_evidence),
        "recorded_at": recorded_at,
    }
    validate_provenance_row(row)
    return row


def validate_provenance_row(row: Mapping[str, Any]) -> None:
    required = {
        "owner_entity_key",
        "coverage_map_version",
        "entity_type",
        "uid_field",
        "uid_value",
        "uuid_generation_method",
        "uuid_namespace_version",
        "uuid_namespace_uuid",
        "uuid_name_template_id",
        "uuid_name_utf8_sha256",
        "source_identity_evidence_sha256",
        "recorded_at",
    }
    if not isinstance(row, Mapping) or set(row) != required:
        _fail(
            "identity provenance row has wrong schema",
            missing=sorted(required - set(row)) if isinstance(row, Mapping) else sorted(required),
            extra=sorted(set(row) - required) if isinstance(row, Mapping) else [],
        )
    if not isinstance(row["owner_entity_key"], str) or not row["owner_entity_key"]:
        _fail("owner_entity_key must be non-empty")
    if row["coverage_map_version"] != IDENTITY_PROVENANCE_COVERAGE_VERSION:
        _fail("identity provenance coverage version mismatch")
    entity_type = row["entity_type"]
    if entity_type not in IDENTITY_UID_FIELDS:
        _fail("unknown identity provenance entity type", entity_type=entity_type)
    if row["uid_field"] != IDENTITY_UID_FIELDS[entity_type]:
        _fail("identity provenance entity/UID-field pair mismatch", entity_type=entity_type)
    method = row["uuid_generation_method"]
    if method not in UUID_METHODS:
        _fail("unknown UUID generation method", method=method)
    _validate_recorded_at(row["recorded_at"])

    if method == "NOT_ASSIGNED_UNKNOWN":
        if row["uid_value"] != "UNKNOWN":
            _fail("NOT_ASSIGNED_UNKNOWN requires uid_value UNKNOWN")
        for field in (
            "uuid_namespace_version",
            "uuid_namespace_uuid",
            "uuid_name_template_id",
            "uuid_name_utf8_sha256",
            "source_identity_evidence_sha256",
        ):
            if row[field] != "NOT_APPLICABLE":
                _fail("unknown UID provenance field must be NOT_APPLICABLE", field=field)
        return

    expected_version = 4 if method == "UUIDV4_RANDOM" else (5 if method == "UUIDV5_CTL_LEGACY_V1" else None)
    validate_canonical_uuid(row["uid_value"], expected_version=expected_version)
    if method == "UUIDV5_CTL_LEGACY_V1":
        if entity_type not in _ENTITY_TEMPLATES:
            _fail("entity has no closed legacy UUIDv5 template", entity_type=entity_type)
        if row["uuid_namespace_version"] != UUID_NAMESPACE_VERSION:
            _fail("UUIDv5 provenance namespace version mismatch")
        if row["uuid_namespace_uuid"] != str(CTL_UUID_NAMESPACE_V1):
            _fail("UUIDv5 provenance namespace UUID mismatch")
        if row["uuid_name_template_id"] != _ENTITY_TEMPLATES[entity_type]:
            _fail("UUIDv5 provenance template mismatch", entity_type=entity_type)
        _validate_sha_or_na(row["uuid_name_utf8_sha256"], field="uuid_name_utf8_sha256", required=True)
        _validate_sha_or_na(
            row["source_identity_evidence_sha256"],
            field="source_identity_evidence_sha256",
            required=True,
        )
    elif method == "PRESERVED":
        for field in ("uuid_namespace_version", "uuid_namespace_uuid", "uuid_name_template_id", "uuid_name_utf8_sha256"):
            if row[field] != "NOT_APPLICABLE":
                _fail("preserved UID has inapplicable recipe metadata", field=field)
        _validate_sha_or_na(
            row["source_identity_evidence_sha256"],
            field="source_identity_evidence_sha256",
            required=True,
        )
    else:  # UUIDV4_RANDOM
        for field in (
            "uuid_namespace_version",
            "uuid_namespace_uuid",
            "uuid_name_template_id",
            "uuid_name_utf8_sha256",
            "source_identity_evidence_sha256",
        ):
            if row[field] != "NOT_APPLICABLE":
                _fail("UUIDv4 provenance recipe metadata must be NOT_APPLICABLE", field=field)


def validate_identity_provenance(
    rows: Sequence[Mapping[str, Any]],
    owner_uid_values: Mapping[str, str],
    *,
    owner_entity_keys: Mapping[str, str] | None = None,
) -> None:
    """Require exact coverage of the ten normative UID owner types."""

    expected_types = set(IDENTITY_UID_FIELDS)
    if set(owner_uid_values) != expected_types:
        _fail(
            "owner UID map must cover exactly ten normative entity types",
            missing=sorted(expected_types - set(owner_uid_values)),
            extra=sorted(set(owner_uid_values) - expected_types),
        )
    if owner_entity_keys is not None and set(owner_entity_keys) != expected_types:
        _fail("owner entity-key map does not have exact coverage")
    if not isinstance(rows, Sequence) or isinstance(rows, (str, bytes)) or len(rows) != len(expected_types):
        _fail("identity_provenance must contain exactly ten rows")
    observed: set[str] = set()
    compound_keys: set[tuple[str, str, str]] = set()
    observed_order: list[tuple[str, str, str]] = []
    for row in rows:
        validate_provenance_row(row)
        entity_type = row["entity_type"]
        if entity_type in observed:
            _fail("duplicate identity provenance entity type", entity_type=entity_type)
        observed.add(entity_type)
        compound = (row["owner_entity_key"], entity_type, row["uid_field"])
        if compound in compound_keys:
            _fail("duplicate identity provenance owner key", key=compound)
        compound_keys.add(compound)
        observed_order.append(compound)
        if row["uid_value"] != owner_uid_values[entity_type]:
            _fail("identity provenance value disagrees with owner", entity_type=entity_type)
        if owner_entity_keys is not None and row["owner_entity_key"] != owner_entity_keys[entity_type]:
            _fail("identity provenance owner key disagrees with owner", entity_type=entity_type)
    if observed != expected_types:
        _fail("identity provenance coverage is incomplete", missing=sorted(expected_types - observed))
    if observed_order != sorted(observed_order):
        _fail("identity provenance rows are not in canonical semantic order")


validate_namespace_constant()
