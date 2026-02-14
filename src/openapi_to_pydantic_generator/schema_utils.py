"""Shared helpers for JSON-Schema shape operations."""

from __future__ import annotations

from typing import Any, Callable


def deep_copy_json(value: Any) -> Any:
    """Copy JSON-like values."""
    if isinstance(value, dict):
        return {key: deep_copy_json(item) for key, item in value.items()}
    if isinstance(value, list):
        return [deep_copy_json(item) for item in value]
    return value


def is_object_schema(schema: dict[str, Any]) -> bool:
    """Return True when schema behaves as an object schema."""
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
    schema: dict[str, Any],
    *,
    normalize_item: Callable[[dict[str, Any]], dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Merge object-only allOf chains into a single object schema when possible."""
    all_of = schema.get("allOf")
    if not isinstance(all_of, list) or not all_of:
        return schema

    merged = {key: value for key, value in schema.items() if key != "allOf"}
    child_schemas = _collect_mergeable_all_of_children(all_of, normalize_item=normalize_item)
    if child_schemas is None:
        return schema

    merged_properties: dict[str, Any] = {}
    merged_required: set[str] = set()
    additional_properties: Any = merged.get("additionalProperties")
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
        merged["required"] = sorted(merged_required)
    if additional_properties is not None:
        merged["additionalProperties"] = additional_properties
    return merged


def _collect_mergeable_all_of_children(
    all_of: list[Any],
    *,
    normalize_item: Callable[[dict[str, Any]], dict[str, Any]] | None,
) -> list[dict[str, Any]] | None:
    children: list[dict[str, Any]] = []
    for item in all_of:
        if not isinstance(item, dict):
            return None
        child_schema = deep_copy_json(item)
        if normalize_item is not None:
            child_schema = normalize_item(child_schema)
        merged_child = merge_all_of_schema(child_schema, normalize_item=normalize_item)
        if not is_object_schema(merged_child):
            return None
        children.append(merged_child)
    return children


def _merge_child_object_data(
    child_schema: dict[str, Any],
    *,
    merged_properties: dict[str, Any],
    merged_required: set[str],
) -> None:
    child_properties = child_schema.get("properties")
    if isinstance(child_properties, dict):
        merged_properties.update(deep_copy_json(child_properties))

    child_required = child_schema.get("required")
    if isinstance(child_required, list):
        for required_name in child_required:
            if isinstance(required_name, str):
                merged_required.add(required_name)
