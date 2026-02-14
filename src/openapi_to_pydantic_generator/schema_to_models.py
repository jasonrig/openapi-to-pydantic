"""Convert resolved JSON schemas into model definitions."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel, RootModel

from .model_types import FieldDef, ModelDef, ModelSchemaConfig, SectionModel
from .naming import class_name, sanitize_identifier
from .schema_utils import is_object_schema, merge_all_of_schema


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
    "Optional[Union["
    "str, int, float, bool, "
    "list[Optional[Union[str, int, float, bool]]], "
    "dict[str, Optional[Union[str, int, float, bool]]]"
    "]]"
)
_PYDANTIC_EXTRA_VALUE_ANNOTATION = (
    "str | int | float | bool | None | "
    "list[str | int | float | bool | None] | "
    "dict[str, str | int | float | bool | None]"
)
_FIELD_STRUCTURAL_KEYS = {
    "$ref",
    "type",
    "properties",
    "required",
    "items",
    "additionalProperties",
    "allOf",
    "anyOf",
    "oneOf",
    "discriminator",
    "nullable",
    "title",
    "default",
    "enum",
    "const",
}
_MODEL_STRUCTURAL_KEYS = {
    "$ref",
    "type",
    "properties",
    "required",
    "items",
    "additionalProperties",
    "allOf",
    "anyOf",
    "oneOf",
    "discriminator",
    "nullable",
    "title",
    "description",
    "default",
    "enum",
    "const",
}


@dataclass
class _SectionContext:
    models: list[ModelDef] = field(default_factory=list)
    used_names: set[str] = field(default_factory=set)


@dataclass(frozen=True)
class _PropertySpec:
    source_name: str
    raw_schema: dict[str, Any]
    required: bool


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
                    config=ModelSchemaConfig(
                        docstring=self._string_or_none(normalized_schema.get("description")),
                        title=self._string_or_none(normalized_schema.get("title")),
                        extra_behavior=None,
                        schema_extra=self._schema_extra(normalized_schema),
                        additional_properties_annotation=None,
                    ),
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

        if len(ordered_statuses) == 1:
            status = ordered_statuses[0]
            schema = self._normalize_nullable(deep_copy(schemas_by_status[status]))
            root_name = self._unique_name(class_name(root_class_name), context)
            if self._is_object_schema(schema):
                self._build_object_model(
                    model_name=root_name,
                    schema=schema,
                    context=context,
                )
            else:
                annotation = self._schema_to_annotation(
                    schema=schema,
                    hint=f"{root_name}Value",
                    context=context,
                )
                context.models.append(
                    ModelDef(
                        name=root_name,
                        is_root=True,
                        root_annotation=annotation,
                        fields=(),
                        config=ModelSchemaConfig(
                            docstring=self._string_or_none(schema.get("description")),
                            title=self._string_or_none(schema.get("title")),
                            extra_behavior=None,
                            schema_extra=self._schema_extra(schema),
                            additional_properties_annotation=None,
                        ),
                    )
                )
            return SectionModel(
                section_name=section_name,
                root_class_name=root_name,
                models=tuple(context.models),
            )

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
                        config=ModelSchemaConfig(
                            docstring=self._string_or_none(schema.get("description")),
                            title=self._string_or_none(schema.get("title")),
                            extra_behavior=None,
                            schema_extra=self._schema_extra(schema),
                            additional_properties_annotation=None,
                        ),
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
                config=ModelSchemaConfig(
                    docstring=None,
                    title=None,
                    extra_behavior=None,
                    schema_extra={},
                    additional_properties_annotation=None,
                ),
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
        fields = self._build_model_fields(model_name=model_name, schema=merged, context=context)
        config = self._object_model_config(merged)

        context.models.append(
            ModelDef(
                name=model_name,
                is_root=False,
                root_annotation=None,
                fields=tuple(fields),
                config=config,
            )
        )
        return model_name

    def _build_model_fields(
        self,
        *,
        model_name: str,
        schema: dict[str, Any],
        context: _SectionContext,
    ) -> list[FieldDef]:
        properties = schema.get("properties")
        if not isinstance(properties, dict):
            return []

        required_names = (
            set(schema.get("required", [])) if isinstance(schema.get("required"), list) else set()
        )
        fields: list[FieldDef] = []
        used_field_names: set[str] = set()
        for source_name, raw_prop in properties.items():
            if not isinstance(source_name, str) or not isinstance(raw_prop, dict):
                continue
            prop = _PropertySpec(
                source_name=source_name,
                raw_schema=raw_prop,
                required=source_name in required_names,
            )
            model_field = self._build_model_field(
                model_name=model_name,
                prop=prop,
                context=context,
                used_field_names=used_field_names,
            )
            if model_field is not None:
                fields.append(model_field)
        return fields

    def _build_model_field(
        self,
        *,
        model_name: str,
        prop: _PropertySpec,
        context: _SectionContext,
        used_field_names: set[str],
    ) -> FieldDef | None:
        prop_schema = self._normalize_nullable(deep_copy(prop.raw_schema))
        field_name = self._field_name(prop.source_name, used_field_names)
        used_field_names.add(field_name)
        annotation = self._schema_to_annotation(
            schema=prop_schema,
            hint=f"{model_name}_{prop.source_name}",
            context=context,
        )

        metadata = self._field_metadata(prop_schema)
        if prop.required and "default" in prop_schema:
            schema_extra = metadata.get("json_schema_extra")
            if not isinstance(schema_extra, dict):
                schema_extra = {}
            schema_extra["default"] = prop_schema["default"]
            metadata["json_schema_extra"] = schema_extra

        return FieldDef(
            name=field_name,
            source_name=prop.source_name,
            annotation=annotation,
            required=prop.required,
            default=self._field_default(prop_schema, required=prop.required),
            metadata=metadata,
        )

    @staticmethod
    def _field_default(schema: dict[str, Any], *, required: bool) -> Any | None:
        if "default" not in schema:
            return None
        if required:
            return None
        return schema["default"]

    def _object_model_config(self, schema: dict[str, Any]) -> ModelSchemaConfig:
        additional_properties = schema.get("additionalProperties")
        additional_properties_annotation: str | None = None
        if isinstance(additional_properties, dict):
            additional_properties_annotation = f"dict[str, {_PYDANTIC_EXTRA_VALUE_ANNOTATION}]"

        if additional_properties is False:
            extra_behavior = "forbid"
        else:
            extra_behavior = "allow"

        schema_extra = self._schema_extra(schema)
        if isinstance(additional_properties, dict):
            schema_extra["additionalProperties"] = sanitize_json_schema_extra(
                deep_copy(additional_properties)
            )

        return ModelSchemaConfig(
            docstring=self._string_or_none(schema.get("description")),
            title=self._string_or_none(schema.get("title")),
            extra_behavior=extra_behavior,
            schema_extra=schema_extra,
            additional_properties_annotation=additional_properties_annotation,
        )

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

        passthrough = self._passthrough_schema_extra(
            schema=schema,
            structural_keys=_FIELD_STRUCTURAL_KEYS,
        )
        extra.update(passthrough)
        if isinstance(schema.get("items"), dict):
            extra["items"] = sanitize_json_schema_extra(deep_copy(schema["items"]))
        if isinstance(schema.get("additionalProperties"), dict):
            extra["additionalProperties"] = sanitize_json_schema_extra(
                deep_copy(schema["additionalProperties"])
            )

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
            "readOnly",
            "writeOnly",
            "deprecated",
        ):
            if key in schema:
                extra[key] = sanitize_json_schema_extra(deep_copy(schema[key]))

        passthrough = self._passthrough_schema_extra(
            schema=schema,
            structural_keys=_MODEL_STRUCTURAL_KEYS,
        )
        extra.update(passthrough)
        return extra

    @staticmethod
    def _passthrough_schema_extra(
        *,
        schema: dict[str, Any],
        structural_keys: set[str],
    ) -> dict[str, Any]:
        passthrough: dict[str, Any] = {}
        for key, value in schema.items():
            if key in _DOC_FIELDS:
                continue
            if key in structural_keys:
                continue
            passthrough[key] = sanitize_json_schema_extra(deep_copy(value))
        return passthrough

    def _schema_to_annotation(
        self,
        *,
        schema: dict[str, Any],
        hint: str,
        context: _SectionContext,
    ) -> str:
        annotation = self._annotation_from_type_list(schema=schema, hint=hint, context=context)
        if annotation is None:
            annotation = self._annotation_from_literal(schema=schema)
        if annotation is None:
            annotation = self._annotation_from_combinators(
                schema=schema,
                hint=hint,
                context=context,
            )
        if annotation is not None:
            return annotation

        schema_type = schema.get("type")
        if schema_type == "array":
            annotation = self._annotation_for_array(schema=schema, hint=hint, context=context)
        elif schema_type == "object" or self._is_object_schema(schema):
            annotation = self._annotation_for_object(schema=schema, hint=hint, context=context)
        else:
            primitive_map = {
                "string": "str",
                "integer": "int",
                "number": "float",
                "boolean": "bool",
                "null": "None",
            }
            annotation = (
                primitive_map[schema_type]
                if isinstance(schema_type, str) and schema_type in primitive_map
                else _JSON_VALUE_ANNOTATION
            )
        return annotation

    def _annotation_from_type_list(
        self,
        *,
        schema: dict[str, Any],
        hint: str,
        context: _SectionContext,
    ) -> str | None:
        schema_type = schema.get("type")
        if not isinstance(schema_type, list):
            return None
        members: list[str] = []
        for member in schema_type:
            if not isinstance(member, str):
                continue
            if member == "null":
                members.append("None")
                continue
            member_schema = deep_copy(schema)
            member_schema["type"] = member
            members.append(
                self._schema_to_annotation(
                    schema=member_schema,
                    hint=hint,
                    context=context,
                )
            )
        return self._make_union(members)

    @staticmethod
    def _annotation_from_literal(*, schema: dict[str, Any]) -> str | None:
        if "const" in schema:
            return f"Literal[{safe_literal(schema['const'])}]"
        enum = schema.get("enum")
        if isinstance(enum, list) and enum:
            literals = ", ".join(safe_literal(value) for value in enum)
            return f"Literal[{literals}]"
        return None

    def _annotation_from_combinators(
        self,
        *,
        schema: dict[str, Any],
        hint: str,
        context: _SectionContext,
    ) -> str | None:
        one_of = schema.get("oneOf")
        if isinstance(one_of, list) and one_of:
            union_annotation = self._union_from_schema_list(
                schemas=one_of,
                hint_prefix=f"{hint}Option",
                context=context,
            )
            return self._apply_discriminator(
                schema=schema,
                one_of=one_of,
                union_annotation=union_annotation,
            )

        any_of = schema.get("anyOf")
        if isinstance(any_of, list) and any_of:
            return self._union_from_schema_list(
                schemas=any_of,
                hint_prefix=f"{hint}Any",
                context=context,
            )

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
            return self._union_from_schema_list(
                schemas=all_of,
                hint_prefix=f"{hint}All",
                context=context,
            )
        return None

    def _union_from_schema_list(
        self,
        *,
        schemas: list[Any],
        hint_prefix: str,
        context: _SectionContext,
    ) -> str:
        options: list[str] = []
        for index, item in enumerate(schemas):
            item_schema = (
                self._normalize_nullable(deep_copy(item)) if isinstance(item, dict) else {}
            )
            options.append(
                self._schema_to_annotation(
                    schema=item_schema,
                    hint=f"{hint_prefix}{index + 1}",
                    context=context,
                )
            )
        return self._make_union(options)

    def _apply_discriminator(
        self,
        *,
        schema: dict[str, Any],
        one_of: list[Any],
        union_annotation: str,
    ) -> str:
        discriminator = schema.get("discriminator")
        if not isinstance(discriminator, dict):
            return union_annotation

        property_name = discriminator.get("propertyName")
        if (
            isinstance(property_name, str)
            and property_name
            and self._is_discriminator_compatible(one_of, property_name)
        ):
            return (
                f"Annotated[{union_annotation}, Field(discriminator={safe_literal(property_name)})]"
            )
        return union_annotation

    def _annotation_for_array(
        self,
        *,
        schema: dict[str, Any],
        hint: str,
        context: _SectionContext,
    ) -> str:
        items = schema.get("items")
        if isinstance(items, dict):
            item_schema = items
        else:
            item_schema = {}
            properties = schema.get("properties")
            if isinstance(properties, dict):
                item_schema = {"type": "object", "properties": deep_copy(properties)}
                required = schema.get("required")
                if isinstance(required, list):
                    item_schema["required"] = [item for item in required if isinstance(item, str)]

        item_annotation = self._schema_to_annotation(
            schema=self._normalize_nullable(deep_copy(item_schema)),
            hint=f"{hint}Item",
            context=context,
        )
        item_extra = self._schema_extra(item_schema)
        if item_extra:
            item_annotation = (
                f"Annotated[{item_annotation}, Field(json_schema_extra={safe_literal(item_extra)})]"
            )
        return f"list[{item_annotation}]"

    def _annotation_for_object(
        self,
        *,
        schema: dict[str, Any],
        hint: str,
        context: _SectionContext,
    ) -> str:
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
        return "dict[str, Any]"

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
        return merge_all_of_schema(
            schema,
            normalize_item=self._normalize_nullable,
        )

    def _is_object_schema(self, schema: dict[str, Any]) -> bool:
        return is_object_schema(schema)

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


def sanitize_json_schema_extra(value: Any) -> Any:
    """Drop external refs in json_schema_extra payloads to keep pydantic schema generation valid."""
    if isinstance(value, dict):
        sanitized: dict[str, Any] = {}
        for key, item in value.items():
            if key == "$ref":
                continue
            sanitized[key] = sanitize_json_schema_extra(item)
        return sanitized
    if isinstance(value, list):
        return [sanitize_json_schema_extra(item) for item in value]
    return value
