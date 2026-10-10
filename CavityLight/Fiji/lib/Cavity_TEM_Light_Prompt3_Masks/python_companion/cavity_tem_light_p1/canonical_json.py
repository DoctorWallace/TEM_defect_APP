"""Exact ``CTL_JSON_UTF8_LF_V1`` serialization.

The profile is intentionally smaller and stricter than general JSON.  It is
used for RUN manifests and for the subobjects covered by ``GEOMETRY_HASH_V1``.
The functions in this module never accept non-finite numbers and never repair
an already serialized document silently.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
import hashlib
import json
import math
import re
import unicodedata
from typing import Any, Mapping, Sequence

from .errors import ValidationError


PROFILE_ID = "CTL_JSON_UTF8_LF_V1"
_SURROGATE = re.compile("[\ud800-\udfff]")


class _ObjectPairs(list):
    """Marker used to distinguish JSON objects from JSON arrays while parsing."""


def _fail(message: str, *, path: str = "$", details: dict | None = None) -> None:
    payload = {"path": path}
    if details:
        payload.update(details)
    raise ValidationError(message, details=payload)


def _check_unicode(value: str, *, path: str) -> str:
    if _SURROGATE.search(value) is not None:
        _fail("isolated Unicode surrogate is forbidden", path=path)
    return unicodedata.normalize("NFC", value)


def _escape_string(value: str, *, path: str) -> str:
    value = _check_unicode(value, path=path)
    # The stdlib string encoder has exactly this profile's JSON escapes,
    # including lowercase control escapes and literal non-ASCII characters.
    # Keep our stricter Unicode/NFC checks and all number/ordering rules.
    return json.encoder.encode_basestring(value)


def _canonical_number(value: int | float | Decimal, *, path: str) -> str:
    if isinstance(value, bool):
        _fail("boolean is not a JSON number", path=path)
    if isinstance(value, int):
        return str(value)

    if isinstance(value, float):
        if not math.isfinite(value):
            _fail("non-finite JSON number", path=path)
        if value == 0.0 and math.copysign(1.0, value) < 0:
            _fail("negative zero is forbidden", path=path)
        decimal_value = Decimal(repr(value))
    elif isinstance(value, Decimal):
        decimal_value = value
    else:  # pragma: no cover - protected by the caller
        _fail("unsupported JSON number type", path=path)

    if not decimal_value.is_finite():
        _fail("non-finite JSON number", path=path)
    if decimal_value.is_zero() and decimal_value.is_signed():
        _fail("negative zero is forbidden", path=path)

    # ``f`` is deliberately used instead of Decimal's default rendering: the
    # canonical profile forbids exponent notation at every magnitude.
    rendered = format(decimal_value, "f")
    if "." in rendered:
        rendered = rendered.rstrip("0").rstrip(".")
    if rendered in {"", "-", "-0"}:
        _fail("invalid canonical JSON number", path=path)
    return rendered


def _sort_token(value: Any, fields: Sequence[str], *, path: str) -> tuple:
    if not isinstance(value, Mapping):
        _fail("ordered semantic array items must be objects", path=path)
    token: list[tuple[int, str]] = []
    for field in fields:
        if field not in value:
            _fail(
                "semantic ordering field is missing",
                path=path,
                details={"field": field},
            )
        component = value[field]
        # row/column can be absent in diagnostic schemas; explicit null sorts
        # before a present value but remains deterministic.
        if component is None:
            token.append((0, ""))
        elif isinstance(component, (str, int)) and not isinstance(component, bool):
            token.append((1, str(component)))
        else:
            _fail(
                "semantic ordering field must be string, integer, or null",
                path=path,
                details={"field": field},
            )
    return tuple(token)


_SEMANTIC_ARRAY_KEYS: dict[str, tuple[str, ...]] = {
    "files": ("relative_path",),
    "replicate_declarations": ("replicate_subject_level", "replicate_subject_id"),
    "density_intervals": ("density_metric_id",),
    "identity_provenance": ("owner_entity_key", "entity_type", "uid_field"),
    "errors": ("code", "path", "row", "column"),
    "warnings": ("code", "path", "row", "column"),
    "validation_errors": ("code", "path", "row", "column"),
    "validation_warnings": ("code", "path", "row", "column"),
}


def _validate_array_order(values: Sequence[Any], *, key: str | None, path: str) -> None:
    if key == "canonical_geometry":
        # Geometry vertex order is itself authoritative and must not be sorted.
        return
    fields = _SEMANTIC_ARRAY_KEYS.get(key or "")
    if fields is None:
        return
    tokens = [_sort_token(item, fields, path=f"{path}[{index}]") for index, item in enumerate(values)]
    if tokens != sorted(tokens):
        _fail(
            "semantic array is not in canonical order",
            path=path,
            details={"array_key": key},
        )
    if len(tokens) != len(set(tokens)):
        _fail(
            "semantic array contains duplicate ordering keys",
            path=path,
            details={"array_key": key},
        )


def _encode(value: Any, *, path: str, parent_key: str | None = None) -> str:
    if value is None:
        return "null"
    if value is True:
        return "true"
    if value is False:
        return "false"
    if isinstance(value, (int, float, Decimal)):
        return _canonical_number(value, path=path)
    if isinstance(value, str):
        return _escape_string(value, path=path)
    if isinstance(value, Mapping):
        normalized: dict[str, tuple[str, Any]] = {}
        for raw_key, item in value.items():
            if not isinstance(raw_key, str):
                _fail("JSON object keys must be strings", path=path)
            key = _check_unicode(raw_key, path=f"{path}.<key>")
            if key in normalized:
                _fail(
                    "JSON object keys collide after NFC normalization",
                    path=path,
                    details={"key": key},
                )
            normalized[key] = (raw_key, item)
        members: list[str] = []
        for key in sorted(normalized):
            _, item = normalized[key]
            child_path = f"{path}.{key}"
            members.append(
                _escape_string(key, path=f"{path}.<key>")
                + ":"
                + _encode(item, path=child_path, parent_key=key)
            )
        return "{" + ",".join(members) + "}"
    if isinstance(value, list):
        _validate_array_order(value, key=parent_key, path=path)
        return "[" + ",".join(
            _encode(item, path=f"{path}[{index}]") for index, item in enumerate(value)
        ) + "]"
    _fail(
        "unsupported value in canonical JSON",
        path=path,
        details={"python_type": type(value).__name__},
    )
    raise AssertionError("unreachable")


def canonical_json_bytes(value: Mapping[str, Any]) -> bytes:
    """Serialize a root object to exact ``CTL_JSON_UTF8_LF_V1`` bytes."""

    if not isinstance(value, Mapping):
        _fail("canonical JSON root must be an object")
    return (_encode(value, path="$") + "\n").encode("utf-8")


def canonical_json_sha256(value: Mapping[str, Any]) -> str:
    """Return SHA-256 of the final bytes, including the sole terminal LF."""

    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def canonical_subobject_bytes(value: Mapping[str, Any]) -> bytes:
    """Serialize a hash-domain root subobject with the profile's sole LF.

    ``GEOMETRY_HASH_V1`` explicitly covers a *root subobject* serialized with
    the full profile, including its one terminal LF, just like a RUN manifest.
    """

    return canonical_json_bytes(value)


def canonical_subobject_sha256(value: Mapping[str, Any]) -> str:
    return hashlib.sha256(canonical_subobject_bytes(value)).hexdigest()


def _reject_constant(token: str) -> None:
    _fail("non-finite JSON number", details={"token": token})


def _pairs_to_object(value: Any, *, path: str = "$") -> Any:
    if isinstance(value, _ObjectPairs):
        exact: set[str] = set()
        normalized: dict[str, Any] = {}
        for raw_key, raw_item in value:
            if raw_key in exact:
                _fail("duplicate JSON key", path=path, details={"key": raw_key})
            exact.add(raw_key)
            key = _check_unicode(raw_key, path=f"{path}.<key>")
            if key in normalized:
                _fail(
                    "JSON keys collide after NFC normalization",
                    path=path,
                    details={"key": key},
                )
            normalized[key] = _pairs_to_object(raw_item, path=f"{path}.{key}")
        return normalized
    if isinstance(value, list):
        return [_pairs_to_object(item, path=f"{path}[{index}]") for index, item in enumerate(value)]
    if isinstance(value, str):
        return _check_unicode(value, path=path)
    return value


def loads_canonical_json(data: bytes) -> dict[str, Any]:
    """Parse and validate exact canonical bytes, returning the root object.

    Validation is by strict parse followed by independent canonical
    serialization and byte comparison.  This rejects whitespace, BOM,
    non-canonical escapes/numbers, exponent notation, key order, missing or
    additional terminal newlines, and non-NFC input.
    """

    if not isinstance(data, bytes):
        _fail("canonical JSON input must be bytes")
    try:
        text = data.decode("utf-8", errors="strict")
    except UnicodeDecodeError as exc:
        _fail("canonical JSON is not valid UTF-8", details={"offset": exc.start})
    try:
        parsed = json.loads(
            text,
            object_pairs_hook=_ObjectPairs,
            parse_float=Decimal,
            parse_int=int,
            parse_constant=_reject_constant,
        )
    except ValidationError:
        raise
    except (json.JSONDecodeError, InvalidOperation, ValueError) as exc:
        _fail("invalid JSON", details={"reason": str(exc)})
    value = _pairs_to_object(parsed)
    if not isinstance(value, dict):
        _fail("canonical JSON root must be an object")
    if canonical_json_bytes(value) != data:
        _fail("bytes do not match CTL_JSON_UTF8_LF_V1")
    return value


def validate_canonical_json(data: bytes) -> None:
    """Raise :class:`ValidationError` unless *data* is exact profile output."""

    loads_canonical_json(data)


# Explicit aliases used by companion integrations.
dumps = canonical_json_bytes
loads = loads_canonical_json
