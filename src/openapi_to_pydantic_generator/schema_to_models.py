"""Convert resolved JSON schemas into model definitions."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel, RootModel

from .model_types import FieldDef, ModelDef, SectionModel
from .naming import class_name, sanitize_identifier


_DOC_FIELDS = {
    "title",
    "description",
    "example",
    "examples",
    "deprecated",
    "readOnly",
    "writeOnly",
    "xml",
    "externalDocs",
    "contentMediaType",
    "contentEncoding",
}

_BASEMODEL_RESERVED = set(dir(BaseModel))
_ROOTMODEL_RESERVED = set(dir(RootModel))
_BUILTIN_IDENTIFIER_RESERVED = {
    "bool",
    "bytes",
    "complex",
    "dict",
    "float",
    "frozenset",
    "int",
    "list",
    "set",
    "str",
    "tuple",
    "type",
}
_JSON_VALUE_ANNOTATION = (
    "str | int | float | bool | None | "
    "list[str | int | float | bool | None] | "
    "dict[str, str | int | float | bool | None]"
)


@dataclass
class _SectionContext:
    models: list[ModelDef] = field(default_factory=list)
    used_names: set[str] = field(default_factory=set)


class SchemaConverter:
    """Create pydantic model definitions from resolved schema nodes."""

    def __init__(self, openapi_version: str) -> None:
        self._openapi_version = openapi_version

    def build_section_from_schema(
        self,
        *,
        section_name: str,
        root_class_name: str,
        schema: dict[str, Any],
    ) -> SectionModel:
        """Build models for a single section schema."""
        context = _SectionContext()
        normalized_schema = self._normalize_nullable(deep_copy(schema))

        if self._is_object_schema(normalized_schema):
            root_name = self._unique_name(class_name(root_class_name), context)
            self._build_object_model(
                model_name=root_name,
                schema=normalized_schema,
                context=context,
            )
            root_class = root_name
        else:
            root_name = self._unique_name(class_name(root_class_name), context)
            annotation = self._schema_to_annotation(
                schema=normalized_schema,
                hint=f"{root_name}Value",
                context=context,
            )
            context.models.append(
                ModelDef(
                    name=root_name,
                    is_root=True,
                    root_annotation=annotation,
                    fields=(),
                    docstring=self._string_or_none(normalized_schema.get("description")),
                    title=self._string_or_none(normalized_schema.get("title")),
                    extra_behavior=None,
                    schema_extra=self._schema_extra(normalized_schema),
                    additional_properties_annotation=None,
                )
            )
            root_class = root_name

        return SectionModel(
            section_name=section_name,
            root_class_name=root_class,
            models=tuple(context.models),
        )

    def build_section_from_status_map(
        self,
        *,
        section_name: str,
        root_class_name: str,
        schemas_by_status: dict[str, dict[str, Any]],
    ) -> SectionModel:
        """Build models for response and error sections with multiple status codes."""
        context = _SectionContext()
        ordered_statuses = sorted(schemas_by_status)
        option_annotations: list[str] = []

        for status in ordered_statuses:
            schema = self._normalize_nullable(deep_copy(schemas_by_status[status]))
            status_model_name = self._unique_name(
                class_name(f"{root_class_name}_{status}"),
                context,
            )
            if self._is_object_schema(schema):
                self._build_object_model(
                    model_name=status_model_name,
                    schema=schema,
                    context=context,
                )
                option_annotations.append(status_model_name)
            else:
                annotation = self._schema_to_annotation(
                    schema=schema,
                    hint=f"{status_model_name}Value",
                    context=context,
                )
                context.models.append(
                    ModelDef(
                        name=status_model_name,
                        is_root=True,
                        root_annotation=annotation,
                        fields=(),
                        docstring=self._string_or_none(schema.get("description")),
                        title=self._string_or_none(schema.get("title")),
                        extra_behavior=None,
                        schema_extra=self._schema_extra(schema),
                        additional_properties_annotation=None,
                    )
                )
                option_annotations.append(status_model_name)

        union_annotation = self._make_union(option_annotations)
        root_name = self._unique_name(class_name(root_class_name), context)
        context.models.append(
            ModelDef(
                name=root_name,
                is_root=True,
                root_annotation=union_annotation,
                fields=(),
                docstring=None,
                title=None,
                extra_behavior=None,
                schema_extra={},
                additional_properties_annotation=None,
            )
        )

        return SectionModel(
            section_name=section_name,
            root_class_name=root_name,
            models=tuple(context.models),
        )

    def _build_object_model(
        self,
        *,
        model_name: str,
        schema: dict[str, Any],
        context: _SectionContext,
    ) -> str:
        merged = self._merge_all_of(schema)
        properties = merged.get("properties")
        required_names = (
            set(merged.get("required", [])) if isinstance(merged.get("required"), list) else set()
        )

        if not isinstance(properties, dict):
            properties = {}

        fields: list[FieldDef] = []
        used_field_names: set[str] = set()
        for source_name, raw_prop in properties.items():
            if not isinstance(source_name, str) or not isinstance(raw_prop, dict):
                continue
            prop_schema = self._normalize_nullable(deep_copy(raw_prop))
            field_name = self._field_name(source_name, used_field_names)
            used_field_names.add(field_name)

            annotation = self._schema_to_annotation(
                schema=prop_schema,
                hint=f"{model_name}_{source_name}",
                context=context,
            )

            required = source_name in required_names
            default_value: Any | None
            if "default" in prop_schema:
                default_value = prop_schema["default"] if not required else None
            else:
                default_value = None

            metadata = self._field_metadata(prop_schema)
            if required and "default" in prop_schema:
                schema_extra = metadata.get("json_schema_extra")
                if not isinstance(schema_extra, dict):
                    schema_extra = {}
                schema_extra["default"] = prop_schema["default"]
                metadata["json_schema_extra"] = schema_extra
            fields.append(
                FieldDef(
                    name=field_name,
                    source_name=source_name,
                    annotation=annotation,
                    required=required,
                    default=default_value,
                    metadata=metadata,
                )
            )

        additional_properties = merged.get("additionalProperties")
        extra_behavior: str | None
        additional_properties_annotation: str | None = None
        if isinstance(additional_properties, dict):
            additional_properties_annotation = f"dict[str, {_JSON_VALUE_ANNOTATION}]"

        if additional_properties is False:
            extra_behavior = "forbid"
        elif additional_properties is True or additional_properties is None:
            extra_behavior = "allow"
        else:
            extra_behavior = "allow"

        context.models.append(
            ModelDef(
                name=model_name,
                is_root=False,
                root_annotation=None,
                fields=tuple(fields),
                docstring=self._string_or_none(merged.get("description")),
                title=self._string_or_none(merged.get("title")),
                extra_behavior=extra_behavior,
                schema_extra=self._schema_extra(merged),
                additional_properties_annotation=additional_properties_annotation,
            )
        )
        return model_name

    def _field_name(self, source_name: str, used_names: set[str]) -> str:
        candidate = sanitize_identifier(source_name)
        if (
            candidate in _BASEMODEL_RESERVED
            or candidate in _ROOTMODEL_RESERVED
            or candidate in _BUILTIN_IDENTIFIER_RESERVED
        ):
            candidate = f"{candidate}_field"
        if candidate not in used_names:
            return candidate

        suffix = 2
        while f"{candidate}_{suffix}" in used_names:
            suffix += 1
        return f"{candidate}_{suffix}"

    def _field_metadata(self, schema: dict[str, Any]) -> dict[str, Any]:
        metadata: dict[str, Any] = {}
        for key in _DOC_FIELDS:
            if key in schema:
                metadata[key] = deep_copy(schema[key])

        extra: dict[str, Any] = {}
        for key in (
            "xml",
            "externalDocs",
            "contentMediaType",
            "contentEncoding",
            "readOnly",
            "writeOnly",
        ):
            if key in metadata:
                extra[key] = metadata.pop(key)

        if extra:
            metadata["json_schema_extra"] = extra
        return metadata

    def _schema_extra(self, schema: dict[str, Any]) -> dict[str, Any]:
        extra: dict[str, Any] = {}
        for key in (
            "xml",
            "externalDocs",
            "contentMediaType",
            "contentEncoding",
            "example",
            "examples",
        ):
            if key in schema:
                extra[key] = deep_copy(schema[key])
        return extra

    def _schema_to_annotation(
        self,
        *,
        schema: dict[str, Any],
        hint: str,
        context: _SectionContext,
    ) -> str:
        if "const" in schema:
            return f"Literal[{safe_literal(schema['const'])}]"

        enum = schema.get("enum")
        if isinstance(enum, list) and enum:
            literals = ", ".join(safe_literal(value) for value in enum)
            return f"Literal[{literals}]"

        one_of = schema.get("oneOf")
        if isinstance(one_of, list) and one_of:
            options = [
                self._schema_to_annotation(
                    schema=self._normalize_nullable(deep_copy(item))
                    if isinstance(item, dict)
                    else {},
                    hint=f"{hint}Option{index + 1}",
                    context=context,
                )
                for index, item in enumerate(one_of)
            ]
            union_annotation = self._make_union(options)
            discriminator = schema.get("discriminator")
            if isinstance(discriminator, dict):
                property_name = discriminator.get("propertyName")
                if (
                    isinstance(property_name, str)
                    and property_name
                    and self._is_discriminator_compatible(one_of, property_name)
                ):
                    return f"Annotated[{union_annotation}, Field(discriminator={safe_literal(property_name)})]"
            return union_annotation

        any_of = schema.get("anyOf")
        if isinstance(any_of, list) and any_of:
            options = [
                self._schema_to_annotation(
                    schema=self._normalize_nullable(deep_copy(item))
                    if isinstance(item, dict)
                    else {},
                    hint=f"{hint}Any{index + 1}",
                    context=context,
                )
                for index, item in enumerate(any_of)
            ]
            return self._make_union(options)

        all_of = schema.get("allOf")
        if isinstance(all_of, list) and all_of:
            merged = self._merge_all_of(schema)
            if self._is_object_schema(merged):
                nested_name = self._unique_name(class_name(hint), context)
                self._build_object_model(
                    model_name=nested_name,
                    schema=merged,
                    context=context,
                )
                return nested_name

            options = [
                self._schema_to_annotation(
                    schema=self._normalize_nullable(deep_copy(item))
                    if isinstance(item, dict)
                    else {},
                    hint=f"{hint}All{index + 1}",
                    context=context,
                )
                for index, item in enumerate(all_of)
            ]
            return self._make_union(options)

        schema_type = schema.get("type")
        if isinstance(schema_type, list):
            members = [
                self._schema_to_annotation(schema={"type": member}, hint=hint, context=context)
                for member in schema_type
            ]
            return self._make_union(members)

        if schema_type == "array":
            items = schema.get("items")
            item_schema = items if isinstance(items, dict) else {}
            item_annotation = self._schema_to_annotation(
                schema=self._normalize_nullable(deep_copy(item_schema)),
                hint=f"{hint}Item",
                context=context,
            )
            item_extra = self._schema_extra(item_schema)
            if item_extra:
                item_annotation = (
                    "Annotated["
                    f"{item_annotation}, "
                    f"Field(json_schema_extra={safe_literal(item_extra)})"
                    "]"
                )
            return f"list[{item_annotation}]"

        if schema_type == "object" or self._is_object_schema(schema):
            properties = schema.get("properties")
            if isinstance(properties, dict):
                nested_name = self._unique_name(class_name(hint), context)
                self._build_object_model(
                    model_name=nested_name,
                    schema=schema,
                    context=context,
                )
                return nested_name

            additional = schema.get("additionalProperties")
            if isinstance(additional, dict):
                value_annotation = self._schema_to_annotation(
                    schema=self._normalize_nullable(deep_copy(additional)),
                    hint=f"{hint}Additional",
                    context=context,
                )
                return f"dict[str, {value_annotation}]"
            if additional is False:
                nested_name = self._unique_name(class_name(hint), context)
                self._build_object_model(
                    model_name=nested_name,
                    schema={"type": "object", "properties": {}, "additionalProperties": False},
                    context=context,
                )
                return nested_name
            return f"dict[str, {_JSON_VALUE_ANNOTATION}]"

        primitive_map = {
            "string": "str",
            "integer": "int",
            "number": "float",
            "boolean": "bool",
            "null": "None",
        }
        if isinstance(schema_type, str) and schema_type in primitive_map:
            return primitive_map[schema_type]

        return _JSON_VALUE_ANNOTATION

    def _make_union(self, annotations: list[str]) -> str:
        deduped: list[str] = []
        for annotation in annotations:
            if annotation not in deduped:
                deduped.append(annotation)
        if not deduped:
            return _JSON_VALUE_ANNOTATION
        if len(deduped) == 1:
            return deduped[0]
        nullable = "None" in deduped
        members = [annotation for annotation in deduped if annotation != "None"]
        if nullable and len(members) == 1:
            return f"Optional[{members[0]}]"
        if nullable and len(members) > 1:
            return f"Optional[Union[{', '.join(members)}]]"
        return f"Union[{', '.join(deduped)}]"

    def _merge_all_of(self, schema: dict[str, Any]) -> dict[str, Any]:
        all_of = schema.get("allOf")
        if not isinstance(all_of, list) or not all_of:
            return schema

        merged = {key: value for key, value in schema.items() if key != "allOf"}
        merged_properties: dict[str, Any] = {}
        merged_required: set[str] = set()
        additional_properties: Any = merged.get("additionalProperties")

        can_merge_objects = True
        for item in all_of:
            if not isinstance(item, dict):
                can_merge_objects = False
                break
            normalized = self._normalize_nullable(deep_copy(item))
            child = self._merge_all_of(normalized)
            if not self._is_object_schema(child):
                can_merge_objects = False
                break
            child_properties = child.get("properties")
            if isinstance(child_properties, dict):
                merged_properties.update(deep_copy(child_properties))
            child_required = child.get("required")
            if isinstance(child_required, list):
                for required_name in child_required:
                    if isinstance(required_name, str):
                        merged_required.add(required_name)
            if child.get("additionalProperties") is False:
                additional_properties = False

        if not can_merge_objects:
            return schema

        merged["type"] = "object"
        merged["properties"] = merged_properties
        if merged_required:
            merged["required"] = sorted(merged_required)
        if additional_properties is not None:
            merged["additionalProperties"] = additional_properties
        return merged

    def _is_object_schema(self, schema: dict[str, Any]) -> bool:
        schema_type = schema.get("type")
        if schema_type == "object":
            return True
        if isinstance(schema.get("properties"), dict):
            return True
        all_of = schema.get("allOf")
        if isinstance(all_of, list) and all_of:
            return all(
                isinstance(item, dict)
                and (
                    item.get("type") == "object"
                    or isinstance(item.get("properties"), dict)
                    or isinstance(item.get("allOf"), list)
                )
                for item in all_of
            )
        return False

    def _is_discriminator_compatible(
        self,
        one_of: list[Any],
        property_name: str,
    ) -> bool:
        for option in one_of:
            if not isinstance(option, dict):
                return False
            props = option.get("properties")
            if not isinstance(props, dict):
                return False
            discriminator_schema = props.get(property_name)
            if not isinstance(discriminator_schema, dict):
                return False
            const_value = discriminator_schema.get("const")
            enum_value = discriminator_schema.get("enum")
            if const_value is not None:
                continue
            if isinstance(enum_value, list) and len(enum_value) == 1:
                continue
            return False
        return True

    def _normalize_nullable(self, schema: dict[str, Any]) -> dict[str, Any]:
        if self._openapi_version.startswith("3.0") and schema.get("nullable") is True:
            schema = deep_copy(schema)
            schema.pop("nullable", None)
            schema_type = schema.get("type")
            if isinstance(schema_type, str):
                schema["type"] = [schema_type, "null"]
            elif isinstance(schema_type, list):
                if "null" not in schema_type:
                    schema_type.append("null")
            else:
                original = deep_copy(schema)
                schema.clear()
                schema["anyOf"] = [original, {"type": "null"}]
        return schema

    def _unique_name(self, base_name: str, context: _SectionContext) -> str:
        if base_name not in context.used_names:
            context.used_names.add(base_name)
            return base_name
        suffix = 2
        while f"{base_name}{suffix}" in context.used_names:
            suffix += 1
        name = f"{base_name}{suffix}"
        context.used_names.add(name)
        return name

    @staticmethod
    def _string_or_none(value: Any) -> str | None:
        return value if isinstance(value, str) and value else None


def safe_literal(value: Any) -> str:
    """Return a safe literal representation for annotation contexts."""
    return repr(value)


def deep_copy(value: Any) -> Any:
    """Copy JSON-like values without importing the whole copy module repeatedly."""
    if isinstance(value, dict):
        return {key: deep_copy(item) for key, item in value.items()}
    if isinstance(value, list):
        return [deep_copy(item) for item in value]
    return value
