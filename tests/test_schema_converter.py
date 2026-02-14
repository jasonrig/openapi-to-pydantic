"""Unit tests for schema conversion behavior."""

from __future__ import annotations

import importlib.util
import itertools
import tempfile
from pathlib import Path
from typing import Any, TypeGuard

from pydantic import BaseModel, RootModel

from openapi_to_pydantic_generator.codegen_ast import render_section_module
from openapi_to_pydantic_generator.schema_to_models import SchemaConverter


def _build_model_schema(*, schema: dict[str, Any], section_name: str = "body") -> dict[str, Any]:
    converter = SchemaConverter("3.1.0")
    section = converter.build_section_from_schema(
        section_name=section_name,
        root_class_name="Body",
        schema=schema,
    )
    source = render_section_module(section)
    with tempfile.TemporaryDirectory() as temp_dir:
        module_path = Path(temp_dir) / "generated_section.py"
        module_path.write_text(source, encoding="utf-8")
        module_name = f"generated_test_{next(_COUNTER)}"
        spec = importlib.util.spec_from_file_location(module_name, module_path)
        if spec is None or spec.loader is None:
            raise RuntimeError(f"Unable to import generated test module from {module_path}")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        value = getattr(module, section.root_class_name, None)
        if not _is_base_model_type(value):
            raise RuntimeError(
                f"Generated class {section.root_class_name} missing in {module_path}"
            )
        value.model_rebuild(_types_namespace=module.__dict__)
        schema_output = value.model_json_schema()
        if not isinstance(schema_output, dict):
            raise RuntimeError(
                f"Generated model JSON schema must be a mapping, got {type(schema_output)!r}"
            )
        return schema_output


def test_reserved_pydantic_member_names_are_rewritten() -> None:
    """Field names must not shadow BaseModel or RootModel attributes."""
    converter = SchemaConverter("3.1.0")
    section = converter.build_section_from_schema(
        section_name="body",
        root_class_name="Body",
        schema={
            "type": "object",
            "properties": {
                "model_dump": {"type": "string"},
                "model_fields": {"type": "integer"},
                "root": {"type": "string"},
            },
            "required": ["model_dump", "model_fields", "root"],
            "additionalProperties": False,
        },
    )
    root_model = next(model for model in section.models if model.name == section.root_class_name)
    reserved = set(dir(BaseModel)) | set(dir(RootModel))
    generated_names = {field.name for field in root_model.fields}

    assert not generated_names & reserved
    mapping = {field.source_name: field.name for field in root_model.fields}
    assert mapping == {
        "model_dump": "model_dump_field",
        "model_fields": "model_fields_field",
        "root": "root",
    }


def test_object_additional_properties_uses_schema_annotation() -> None:
    """`additionalProperties` schema should carry its value type into generated schema."""
    generated = _build_model_schema(
        schema={
            "type": "object",
            "additionalProperties": {"type": "integer"},
        }
    )
    additional = generated.get("additionalProperties")
    assert isinstance(additional, dict), f"Expected object additionalProperties, got: {generated!r}"
    assert additional.get("type") == "integer", (
        f"Expected integer additionalProperties, got: {additional!r}"
    )


def test_field_constraints_are_preserved_in_generated_schema() -> None:
    """Validation keywords like maximum should appear in generated schema."""
    generated = _build_model_schema(
        schema={
            "type": "object",
            "properties": {
                "limit": {"type": "integer", "maximum": 250},
            },
            "required": ["limit"],
            "additionalProperties": False,
        }
    )
    properties = generated.get("properties")
    assert isinstance(properties, dict), f"Missing properties in schema: {generated!r}"
    limit = properties.get("limit")
    assert isinstance(limit, dict), f"Missing limit property in schema: {generated!r}"
    assert limit.get("maximum") == 250, f"Expected maximum=250 for limit, got: {limit!r}"


def test_generated_source_prefers_optional_over_pipe_none() -> None:
    """Generated type annotations should not use `| None` style."""
    converter = SchemaConverter("3.1.0")
    section = converter.build_section_from_schema(
        section_name="body",
        root_class_name="Body",
        schema={
            "type": "object",
            "properties": {
                "payload": {"type": "object"},
            },
            "required": ["payload"],
            "additionalProperties": False,
        },
    )
    source = render_section_module(section)
    assert "| None" not in source


_COUNTER = itertools.count(1)


def _is_base_model_type(value: object) -> TypeGuard[type[BaseModel]]:
    return isinstance(value, type) and issubclass(value, BaseModel)
