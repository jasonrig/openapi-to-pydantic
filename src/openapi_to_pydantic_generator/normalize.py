"""Schema normalization helpers for verification."""

from __future__ import annotations

from copy import deepcopy
import json
import re
from dataclasses import dataclass
from typing import Any, Optional

from .schema_utils import merge_all_of_schema

_ORDER_INSENSITIVE_KEYS = {"required", "enum", "allOf", "anyOf", "oneOf"}
_IGNORED_KEYS = {"$comment", "$ref", "format"}


@dataclass(frozen=True)
class Mismatch:
    """Subset mismatch information."""

    path: str
    expected: Any
    actual: Any


def normalize_source_schema(schema: dict[str, Any]) -> dict[str, Any]:
    """Normalize source schema from OpenAPI for comparison."""
    normalized = deepcopy(schema)
    normalized = _normalize_nullable(normalized)
    normalized = _normalize_all_of(normalized)
    return _as_dict(_normalize_structural(normalized))


def normalize_generated_schema(schema: dict[str, Any]) -> dict[str, Any]:
    """Normalize pydantic-generated schema for comparison."""
    normalized = deepcopy(schema)
    normalized = _inline_local_refs(normalized)
    if isinstance(normalized, dict):
        normalized.pop("$defs", None)
        normalized.pop("$schema", None)
    normalized = _normalize_nullable(normalized)
    normalized = _normalize_all_of(normalized)
    return _as_dict(_normalize_structural(normalized))


def subset_mismatch(expected: Any, actual: Any, *, path: str = "$") -> Mismatch | None:
    """Return first mismatch where expected is not a subset of actual."""
    if isinstance(expected, dict):
        return _dict_subset_mismatch(expected, actual, path=path)

    if isinstance(expected, list):
        if not isinstance(actual, list) or len(expected) > len(actual):
            return Mismatch(path=path, expected=expected, actual=actual)
        return _list_subset_mismatch(expected, actual, path=path)

    if expected == actual:
        return None
    return Mismatch(path=path, expected=expected, actual=actual)


def _dict_subset_mismatch(
    expected: dict[str, Any],
    actual: Any,
    *,
    path: str,
) -> Mismatch | None:
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


def _normalize_nullable(node: Any) -> Any:
    if isinstance(node, list):
        return [_normalize_nullable(item) for item in node]
    if not isinstance(node, dict):
        return node

    normalized = {key: _normalize_nullable(value) for key, value in node.items()}
    if isinstance(normalized.get("nullable"), bool):
        nullable = normalized.pop("nullable")
    else:
        nullable = None

    if nullable is True:
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


def _normalize_structural(node: Any, *, parent_key: Optional[str] = None) -> Any:
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

        _collapse_singleton_any_of(normalized_dict)
        _collapse_nullable_any_of(normalized_dict)
        _normalize_type_list_forms(normalized_dict)
        _collapse_any_of_simple_types(normalized_dict)
        _normalize_const_enum(normalized_dict)
        _normalize_malformed_array_schema(normalized_dict)
        _normalize_required_properties(normalized_dict)
        _normalize_enum_type_conflict(normalized_dict)
        _drop_empty_all_of(normalized_dict)
        _drop_any_of_option_descriptions(normalized_dict)

        if isinstance(normalized_dict.get("description"), str):
            normalized_dict["description"] = _normalize_description(normalized_dict["description"])

        if (
            normalized_dict.get("type") == "object"
            and "additionalProperties" not in normalized_dict
        ):
            normalized_dict["additionalProperties"] = True
        if normalized_dict.get("required") == []:
            normalized_dict.pop("required")
        return normalized_dict

    return node


def _normalize_all_of(node: Any) -> Any:
    if isinstance(node, list):
        return [_normalize_all_of(item) for item in node]
    if not isinstance(node, dict):
        return node

    normalized = {key: _normalize_all_of(value) for key, value in node.items()}
    all_of = normalized.get("allOf")
    if not isinstance(all_of, list) or not all_of:
        return normalized
    if all(isinstance(item, dict) and not item for item in all_of):
        return {key: value for key, value in normalized.items() if key != "allOf"}
    return merge_all_of_schema(normalized)


_DESC_BULLET_SPACING = re.compile(r"\n[ \t]+\*")


def _normalize_description(value: str) -> str:
    lines = [line.rstrip() for line in value.splitlines()]
    collapsed = "\n".join(lines).strip()
    return _DESC_BULLET_SPACING.sub("\n*", collapsed)


def _collapse_any_of_simple_types(node: dict[str, Any]) -> None:
    any_of = node.get("anyOf")
    if not isinstance(any_of, list) or not any_of:
        return
    allowed_meta = {"default", "description", "title"}
    members: list[str] = []
    for option in any_of:
        if not isinstance(option, dict):
            return
        unknown_keys = set(option.keys()) - {"type"} - allowed_meta
        if unknown_keys:
            return
        option_type = option.get("type")
        if not isinstance(option_type, str):
            return
        members.append(option_type)
    node["type"] = sorted(set(members))
    node.pop("anyOf", None)


def _collapse_singleton_any_of(node: dict[str, Any]) -> None:
    any_of = node.get("anyOf")
    if not isinstance(any_of, list) or len(any_of) != 1:
        return
    option = any_of[0]
    if not isinstance(option, dict):
        return
    node.pop("anyOf", None)
    for key, value in option.items():
        node.setdefault(key, value)


def _collapse_nullable_any_of(node: dict[str, Any]) -> None:
    any_of = node.get("anyOf")
    if not isinstance(any_of, list) or len(any_of) != 2:
        return
    null_option: dict[str, Any] | None = None
    typed_option: dict[str, Any] | None = None
    for option in any_of:
        if not isinstance(option, dict):
            return
        if option.get("type") == "null" and len(option) == 1:
            null_option = option
            continue
        option_type = option.get("type")
        if isinstance(option_type, str) and "anyOf" not in option and "oneOf" not in option:
            typed_option = option
            continue
        return
    if null_option is None or typed_option is None:
        return

    node.pop("anyOf", None)
    option_type = typed_option.get("type")
    for key, value in typed_option.items():
        if key == "type":
            continue
        node.setdefault(key, value)
    if isinstance(option_type, str):
        node["type"] = sorted([option_type, "null"])


def _normalize_malformed_array_schema(node: dict[str, Any]) -> None:
    if node.get("type") != "array":
        return
    if "items" in node or "properties" not in node:
        return
    properties = node.pop("properties")
    if not isinstance(properties, dict):
        return
    item_schema: dict[str, Any] = {"type": "object", "properties": properties}
    required = node.pop("required", None)
    if isinstance(required, list):
        item_schema["required"] = required
    node["items"] = item_schema


def _drop_empty_all_of(node: dict[str, Any]) -> None:
    all_of = node.get("allOf")
    if not isinstance(all_of, list):
        return
    if all(isinstance(item, dict) and not item for item in all_of):
        node.pop("allOf", None)


def _drop_any_of_option_descriptions(node: dict[str, Any]) -> None:
    any_of = node.get("anyOf")
    if not isinstance(any_of, list):
        return
    for option in any_of:
        if not isinstance(option, dict):
            continue
        option.pop("description", None)


def _normalize_const_enum(node: dict[str, Any]) -> None:
    const_value = node.get("const")
    enum_value = node.get("enum")
    if const_value is not None and enum_value is None:
        node["enum"] = [const_value]
        node.pop("const", None)


def _normalize_type_list_forms(node: dict[str, Any]) -> None:
    schema_type = node.get("type")
    if not isinstance(schema_type, list):
        return
    members = [item for item in schema_type if isinstance(item, str)]
    if not members:
        node.pop("type", None)
        return
    if len(members) == 1:
        node["type"] = members[0]
        return
    node["type"] = sorted(set(members))


def _normalize_required_properties(node: dict[str, Any]) -> None:
    required = node.get("required")
    properties = node.get("properties")
    if not isinstance(required, list) or not isinstance(properties, dict):
        return
    filtered = [item for item in required if isinstance(item, str) and item in properties]
    if filtered:
        node["required"] = filtered
    else:
        node.pop("required", None)


def _normalize_enum_type_conflict(node: dict[str, Any]) -> None:
    enum_value = node.get("enum")
    schema_type = node.get("type")
    if not isinstance(enum_value, list) or not enum_value:
        return

    if (
        isinstance(schema_type, str)
        and schema_type in {"boolean", "integer", "number"}
        and all(isinstance(item, str) for item in enum_value)
    ):
        node["type"] = "string"
        return

    if schema_type != "object":
        return

    inferred_type: str | None = None
    if all(isinstance(item, str) for item in enum_value):
        inferred_type = "string"
    elif all(isinstance(item, bool) for item in enum_value):
        inferred_type = "boolean"
    elif all(isinstance(item, int) and not isinstance(item, bool) for item in enum_value):
        inferred_type = "integer"
    elif all(isinstance(item, (int, float)) and not isinstance(item, bool) for item in enum_value):
        inferred_type = "number"
    elif all(item is None for item in enum_value):
        inferred_type = "null"

    if inferred_type is not None:
        node["type"] = inferred_type


def _list_subset_mismatch(expected: list[Any], actual: list[Any], *, path: str) -> Mismatch | None:
    used_indexes: set[int] = set()

    def _backtrack(index: int) -> Mismatch | None:
        if index >= len(expected):
            return None
        expected_item = expected[index]
        best_mismatch: Mismatch | None = None
        for candidate_index, actual_item in enumerate(actual):
            if candidate_index in used_indexes:
                continue
            mismatch = subset_mismatch(
                expected_item,
                actual_item,
                path=f"{path}[{index}]",
            )
            if mismatch is not None:
                if best_mismatch is None:
                    best_mismatch = mismatch
                continue
            used_indexes.add(candidate_index)
            downstream = _backtrack(index + 1)
            if downstream is None:
                return None
            used_indexes.remove(candidate_index)
            if best_mismatch is None:
                best_mismatch = downstream

        return best_mismatch or Mismatch(
            path=f"{path}[{index}]",
            expected=expected_item,
            actual=None,
        )

    return _backtrack(0)


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
        resolved = _resolve_ref_node(deepcopy(target), defs=defs, stack=(*stack, ref))
        siblings = {k: v for k, v in node.items() if k != "$ref"}
        if not siblings:
            return resolved
        if not isinstance(resolved, dict):
            return resolved
        merged = deepcopy(resolved)
        for key_name, key_value in siblings.items():
            merged[key_name] = _resolve_ref_node(key_value, defs=defs, stack=stack)
        return merged

    return {key: _resolve_ref_node(value, defs=defs, stack=stack) for key, value in node.items()}


def _canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _as_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    raise ValueError(f"Expected normalized schema object, got {type(value)!r}")
