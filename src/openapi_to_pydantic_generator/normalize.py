"""Schema normalization helpers for verification."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any


_ORDER_INSENSITIVE_KEYS = {"required", "enum", "allOf", "anyOf", "oneOf"}
_IGNORED_KEYS = {"$comment", "format"}


@dataclass(frozen=True)
class Mismatch:
    """Subset mismatch information."""

    path: str
    expected: Any
    actual: Any


def normalize_source_schema(schema: dict[str, Any], *, openapi_version: str) -> dict[str, Any]:
    """Normalize source schema from OpenAPI for comparison."""
    normalized = _deep_copy(schema)
    normalized = _normalize_nullable(normalized, openapi_version=openapi_version)
    return _as_dict(_normalize_structural(normalized))


def normalize_generated_schema(schema: dict[str, Any], *, openapi_version: str) -> dict[str, Any]:
    """Normalize pydantic-generated schema for comparison."""
    normalized = _deep_copy(schema)
    normalized = _inline_local_refs(normalized)
    if isinstance(normalized, dict):
        normalized.pop("$defs", None)
        normalized.pop("$schema", None)
    normalized = _normalize_nullable(normalized, openapi_version=openapi_version)
    return _as_dict(_normalize_structural(normalized))


def subset_mismatch(expected: Any, actual: Any, *, path: str = "$") -> Mismatch | None:
    """Return first mismatch where expected is not a subset of actual."""
    if isinstance(expected, dict):
        if not isinstance(actual, dict):
            return Mismatch(path=path, expected=expected, actual=actual)
        for key, expected_value in expected.items():
            if key not in actual:
                return Mismatch(path=f"{path}.{key}", expected=expected_value, actual=None)
            mismatch = subset_mismatch(
                expected_value,
                actual[key],
                path=f"{path}.{key}",
            )
            if mismatch is not None:
                return mismatch
        return None

    if isinstance(expected, list):
        if not isinstance(actual, list):
            return Mismatch(path=path, expected=expected, actual=actual)
        if len(expected) > len(actual):
            return Mismatch(path=path, expected=expected, actual=actual)

        # For normalized order-insensitive arrays, compare by index after sorting.
        for index, expected_item in enumerate(expected):
            mismatch = subset_mismatch(
                expected_item,
                actual[index],
                path=f"{path}[{index}]",
            )
            if mismatch is not None:
                return mismatch
        return None

    if expected != actual:
        return Mismatch(path=path, expected=expected, actual=actual)
    return None


def _normalize_nullable(node: Any, *, openapi_version: str) -> Any:
    if isinstance(node, list):
        return [_normalize_nullable(item, openapi_version=openapi_version) for item in node]
    if not isinstance(node, dict):
        return node

    normalized = {
        key: _normalize_nullable(value, openapi_version=openapi_version)
        for key, value in node.items()
    }
    if openapi_version.startswith("3.0") and normalized.get("nullable") is True:
        normalized.pop("nullable", None)
        schema_type = normalized.get("type")
        if isinstance(schema_type, str):
            normalized["type"] = sorted([schema_type, "null"])
        elif isinstance(schema_type, list):
            members = [member for member in schema_type if isinstance(member, str)]
            if "null" not in members:
                members.append("null")
            normalized["type"] = sorted(set(members))
        else:
            wrapped = {key: value for key, value in normalized.items() if key != "anyOf"}
            any_of = normalized.get("anyOf")
            options: list[Any] = []
            if isinstance(any_of, list):
                options.extend(any_of)
            else:
                options.append(wrapped)
            options.append({"type": "null"})
            normalized = {"anyOf": options}
    return normalized


def _normalize_structural(node: Any, *, parent_key: str | None = None) -> Any:
    if isinstance(node, list):
        normalized_list = [_normalize_structural(item) for item in node]
        if parent_key in _ORDER_INSENSITIVE_KEYS:
            return sorted(normalized_list, key=_canonical_json)
        return normalized_list

    if isinstance(node, dict):
        normalized_dict = {}
        for key, value in sorted(node.items()):
            if key in _IGNORED_KEYS:
                continue
            normalized_dict[key] = _normalize_structural(value, parent_key=key)

        if "oneOf" in normalized_dict and "anyOf" not in normalized_dict:
            normalized_dict["anyOf"] = normalized_dict.pop("oneOf")
        if (
            normalized_dict.get("type") == "object"
            and "additionalProperties" not in normalized_dict
        ):
            normalized_dict["additionalProperties"] = True
        if normalized_dict.get("required") == []:
            normalized_dict.pop("required")
        return normalized_dict

    return node


def _inline_local_refs(schema: Any) -> Any:
    if not isinstance(schema, dict):
        return schema
    defs_value = schema.get("$defs")
    defs: dict[str, Any]
    if isinstance(defs_value, dict):
        defs = {str(key): value for key, value in defs_value.items()}
    else:
        defs = {}
    return _resolve_ref_node(schema, defs=defs, stack=())


def _resolve_ref_node(node: Any, *, defs: dict[str, Any], stack: tuple[str, ...]) -> Any:
    if isinstance(node, list):
        return [_resolve_ref_node(item, defs=defs, stack=stack) for item in node]
    if not isinstance(node, dict):
        return node

    ref = node.get("$ref")
    if isinstance(ref, str) and ref.startswith("#/$defs/"):
        if ref in stack:
            raise ValueError(
                f"Cyclic local schema reference detected: {' -> '.join((*stack, ref))}"
            )
        key = ref.removeprefix("#/$defs/")
        target = defs.get(key)
        if target is None:
            raise ValueError(f"Missing local schema definition for {ref}")
        resolved = _resolve_ref_node(_deep_copy(target), defs=defs, stack=(*stack, ref))
        siblings = {k: v for k, v in node.items() if k != "$ref"}
        if not siblings:
            return resolved
        if not isinstance(resolved, dict):
            return resolved
        merged = _deep_copy(resolved)
        for key_name, key_value in siblings.items():
            merged[key_name] = _resolve_ref_node(key_value, defs=defs, stack=stack)
        return merged

    return {key: _resolve_ref_node(value, defs=defs, stack=stack) for key, value in node.items()}


def _deep_copy(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _deep_copy(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_deep_copy(item) for item in value]
    return value


def _canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _as_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    raise ValueError(f"Expected normalized schema object, got {type(value)!r}")
