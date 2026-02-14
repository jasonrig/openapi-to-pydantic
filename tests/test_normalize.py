"""Unit tests for schema normalization helpers."""

from __future__ import annotations

from openapi_to_pydantic_generator.json_types import JSONValue
from openapi_to_pydantic_generator.normalize import normalize_generated_schema


def test_permissive_additional_properties_schema_normalizes_to_true() -> None:
    """Permissive any-JSON schemas should normalize to ``additionalProperties: true``."""
    schema: dict[str, JSONValue] = {
        "type": "object",
        "properties": {
            "value": {
                "type": "object",
                "additionalProperties": {
                    "anyOf": [
                        {
                            "type": "object",
                            "additionalProperties": {
                                "type": ["boolean", "integer", "null", "number", "string"]
                            },
                        },
                        {
                            "type": "array",
                            "items": {"type": ["boolean", "integer", "null", "number", "string"]},
                        },
                        {"type": "boolean"},
                        {"type": "integer"},
                        {"type": "null"},
                        {"type": "number"},
                        {"type": "string"},
                    ]
                },
            }
        },
    }

    normalized = normalize_generated_schema(schema)
    properties = normalized.get("properties")
    assert isinstance(properties, dict), normalized
    value = properties.get("value")
    assert isinstance(value, dict), normalized
    assert value.get("additionalProperties") is True, normalized


def test_typed_additional_properties_schema_is_not_collapsed() -> None:
    """Typed additional-properties schemas should remain explicit."""
    schema: dict[str, JSONValue] = {
        "type": "object",
        "properties": {
            "value": {
                "type": "object",
                "additionalProperties": {"type": "integer"},
            }
        },
    }

    normalized = normalize_generated_schema(schema)
    properties = normalized.get("properties")
    assert isinstance(properties, dict), normalized
    value = properties.get("value")
    assert isinstance(value, dict), normalized
    additional = value.get("additionalProperties")
    assert isinstance(additional, dict), normalized
    assert additional.get("type") == "integer", normalized
