"""Internal datatypes for generation and verification."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class FieldDef:
    """Represents a single pydantic model field."""

    name: str
    source_name: str
    annotation: str
    required: bool
    default: Any | None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ModelSchemaConfig:
    """Schema and config metadata for a generated model class."""

    docstring: str | None
    title: str | None
    extra_behavior: str | None
    schema_extra: dict[str, Any]
    additional_properties_annotation: str | None


@dataclass(frozen=True)
class ModelDef:
    """Represents a generated pydantic model class."""

    name: str
    is_root: bool
    root_annotation: str | None
    fields: tuple[FieldDef, ...]
    config: ModelSchemaConfig


@dataclass(frozen=True)
class SectionModel:
    """A generated file section with its models and root class."""

    section_name: str
    root_class_name: str
    models: tuple[ModelDef, ...]


@dataclass(frozen=True)
class VerificationItem:
    """A model schema comparison entry."""

    endpoint_name: str
    method: str
    section_name: str
    class_name: str
    source_schema: dict[str, Any]
    generated_module_path: str


@dataclass(frozen=True)
class OperationSpec:
    """Normalized operation metadata extracted from OpenAPI paths."""

    path: str
    method: str
    endpoint_name: str
    operation: dict[str, Any]
    path_item: dict[str, Any]


@dataclass(frozen=True)
class GenerationResult:
    """Generation output metadata."""

    output_dir: str
    verification_items: tuple[VerificationItem, ...]
    warnings: tuple[str, ...]
