"""Internal datatypes for generation and verification."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from .json_types import JSONValue, MutableJSONObject, JSONObject


@dataclass(frozen=True)
class FieldDef:
    """Represents a single pydantic model field."""

    name: str
    source_name: str
    annotation: str
    required: bool
    default: Optional[JSONValue]
    metadata: MutableJSONObject = field(default_factory=dict)


@dataclass(frozen=True)
class ModelSchemaConfig:
    """Schema and config metadata for a generated model class."""

    docstring: Optional[str]
    title: Optional[str]
    extra_behavior: Optional[str]
    schema_extra: MutableJSONObject
    additional_properties_annotation: Optional[str]


@dataclass(frozen=True)
class ModelDef:
    """Represents a generated pydantic model class."""

    name: str
    is_root: bool
    root_annotation: Optional[str]
    fields: tuple[FieldDef, ...]
    config: ModelSchemaConfig


@dataclass(frozen=True)
class SectionModel:
    """A generated file section with its models and root class."""

    section_name: str
    root_class_name: str
    models: tuple[ModelDef, ...]


@dataclass(frozen=True)
class SectionManifestEntry:
    """Manifest entry describing model usage for one generated section module."""

    section_name: str
    root_class_name: str
    model_names: tuple[str, ...]


@dataclass(frozen=True)
class OperationManifestEntry:
    """Manifest entry describing generated section models for one HTTP method."""

    method: str
    path: str
    summary: Optional[str]
    description: Optional[str]
    sections: tuple[SectionManifestEntry, ...]


@dataclass(frozen=True)
class EndpointManifest:
    """Documentation payload for one generated endpoint package."""

    endpoint_name: str
    paths: tuple[str, ...]
    operations: tuple[OperationManifestEntry, ...]


@dataclass(frozen=True)
class VerificationItem:
    """A model schema comparison entry."""

    endpoint_name: str
    method: str
    section_name: str
    class_name: str
    source_schema: JSONObject
    generated_module_path: str


@dataclass(frozen=True)
class OperationSpec:
    """Normalized operation metadata extracted from OpenAPI paths."""

    path: str
    method: str
    endpoint_name: str
    operation: JSONObject
    path_item: JSONObject


@dataclass(frozen=True)
class GenerationResult:
    """Generation output metadata."""

    output_dir: str
    verification_items: tuple[VerificationItem, ...]
    warnings: tuple[str, ...]
