"""Shared helpers for JSON-Schema shape operations."""

from __future__ import annotations

from collections.abc import Callable
from copy import deepcopy
from typing import Optional

from .json_types import JSONObject, JSONValue, MutableJSONObject


def is_object_schema(schema: JSONObject) -> bool:
    """Return whether a schema behaves as an object schema.

    Args:
        schema (JSONObject): Schema node to inspect.

    Returns:
        bool: Whether object modeling rules should apply.
    """
    schema_type = schema.get("type")
    if schema_type == "object":
        return True
    if isinstance(schema.get("properties"), dict):
        return True
    if "additionalProperties" in schema:
        return True
    all_of = schema.get("allOf")
    if isinstance(all_of, list) and all_of:
        return all(isinstance(item, dict) and is_object_schema(item) for item in all_of)
    return False


def merge_all_of_schema(
    schema: JSONObject,
    *,
    normalize_item: Optional[Callable[[MutableJSONObject], MutableJSONObject]] = None,
) -> MutableJSONObject:
    """Merge object-only `allOf` chains into one object schema when possible.

    Args:
        schema (JSONObject): Schema that may contain an `allOf` chain.
        normalize_item (Optional[Callable[[MutableJSONObject], MutableJSONObject]]):
            Optional normalization callback applied to each child before merge.

    Returns:
        MutableJSONObject: Merged object schema, or the original schema shape.
    """
    all_of = schema.get("allOf")
    if not isinstance(all_of, list) or not all_of:
        return deepcopy(dict(schema))

    merged: MutableJSONObject = {key: value for key, value in schema.items() if key != "allOf"}
    child_schemas = _collect_mergeable_all_of_children(all_of, normalize_item=normalize_item)
    if child_schemas is None:
        return deepcopy(dict(schema))

    merged_properties: MutableJSONObject = {}
    merged_required: set[str] = set()
    additional_properties: Optional[JSONValue] = merged.get("additionalProperties")
    for child_schema in child_schemas:
        _merge_child_object_data(
            child_schema,
            merged_properties=merged_properties,
            merged_required=merged_required,
        )
        if child_schema.get("additionalProperties") is False:
            additional_properties = False

    merged["type"] = "object"
    if merged_properties:
        merged["properties"] = merged_properties
    if merged_required:
        merged["required"] = list(sorted(merged_required))
    if additional_properties is not None:
        merged["additionalProperties"] = additional_properties
    return merged


def _collect_mergeable_all_of_children(
    all_of: list[JSONValue],
    *,
    normalize_item: Optional[Callable[[MutableJSONObject], MutableJSONObject]],
) -> Optional[list[MutableJSONObject]]:
    children: list[MutableJSONObject] = []
    for item in all_of:
        if not isinstance(item, dict):
            return None
        child_schema = deepcopy(item)
        if normalize_item is not None:
            child_schema = normalize_item(child_schema)
        merged_child = merge_all_of_schema(child_schema, normalize_item=normalize_item)
        if not is_object_schema(merged_child):
            return None
        children.append(merged_child)
    return children


def _merge_child_object_data(
    child_schema: JSONObject,
    *,
    merged_properties: MutableJSONObject,
    merged_required: set[str],
) -> None:
    child_properties = child_schema.get("properties")
    if isinstance(child_properties, dict):
        merged_properties.update(deepcopy(child_properties))

    child_required = child_schema.get("required")
    if isinstance(child_required, list):
        for required_name in child_required:
            if isinstance(required_name, str):
                merged_required.add(required_name)
