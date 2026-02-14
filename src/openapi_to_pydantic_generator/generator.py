"""High-level generator orchestration."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .loader import (
    OpenAPILoadError,
    ensure_supported_version,
    get_openapi_version,
    load_openapi_document,
)
from .model_types import GenerationResult, VerificationItem
from .naming import resolve_operations
from .resolver import Resolver, SectionSchemas
from .schema_to_models import SchemaConverter
from .verify import VerificationReport, verify_models
from .writer import WriteError, create_output_layout, write_operation_sections


@dataclass(frozen=True)
class GenerationRun:
    """Generation result with optional verification report."""

    result: GenerationResult
    verification_report: VerificationReport | None


def run_generation(
    *,
    input_path: Path,
    output_dir: Path,
    verify: bool,
) -> GenerationRun:
    """Generate models from an OpenAPI document."""
    document = load_openapi_document(input_path)
    version = get_openapi_version(document)
    ensure_supported_version(version)

    raw_paths = document.get("paths")
    if not isinstance(raw_paths, dict):
        raise OpenAPILoadError("OpenAPI document missing 'paths' object")

    operations, warnings = resolve_operations(raw_paths)

    models_dir = create_output_layout(output_dir)
    resolver = Resolver(document)
    converter = SchemaConverter(version)

    verification_items: list[VerificationItem] = []

    for operation in operations:
        section_schemas = resolver.build_section_schemas(operation)
        sections, items = _build_operation_sections(
            operation=operation,
            section_schemas=section_schemas,
            converter=converter,
        )
        if sections:
            write_operation_sections(
                models_dir=models_dir,
                endpoint_name=operation.endpoint_name,
                method=operation.method,
                sections=sections,
            )
            verification_items.extend(items)

    result = GenerationResult(
        output_dir=str(output_dir),
        verification_items=tuple(verification_items),
        warnings=tuple(warnings),
    )

    if not verify:
        return GenerationRun(result=result, verification_report=None)

    report = verify_models(
        items=verification_items,
        output_dir=output_dir,
        openapi_version=version,
    )
    return GenerationRun(result=result, verification_report=report)


def _build_operation_sections(
    *,
    operation: Any,
    section_schemas: SectionSchemas,
    converter: SchemaConverter,
) -> tuple[list[Any], list[VerificationItem]]:
    sections: list[Any] = []
    items: list[VerificationItem] = []

    section_schema_map: list[tuple[str, str, dict[str, Any] | None]] = [
        ("url_params", "UrlParams", section_schemas.url_params),
        ("query_params", "QueryParams", section_schemas.query_params),
        ("headers", "Headers", section_schemas.headers),
        ("cookies", "Cookies", section_schemas.cookies),
        ("body", "Body", section_schemas.body),
    ]

    for section_name, root_class_name, schema in section_schema_map:
        if schema is None:
            continue
        section = converter.build_section_from_schema(
            section_name=section_name,
            root_class_name=root_class_name,
            schema=schema,
        )
        sections.append(section)
        items.append(
            VerificationItem(
                endpoint_name=operation.endpoint_name,
                method=operation.method,
                section_name=section_name,
                class_name=section.root_class_name,
                source_schema=schema,
                generated_module_path=str(
                    Path("models")
                    / operation.endpoint_name
                    / operation.method
                    / f"{section_name}.py"
                ),
            )
        )

    status_sections: list[tuple[str, str, dict[str, dict[str, Any]]]] = [
        ("response", "Response", section_schemas.response_schemas),
        ("errors", "Errors", section_schemas.error_schemas),
    ]
    for section_name, root_class_name, schemas_by_status in status_sections:
        if not schemas_by_status:
            continue
        section = converter.build_section_from_status_map(
            section_name=section_name,
            root_class_name=root_class_name,
            schemas_by_status=schemas_by_status,
        )
        sections.append(section)

        ordered_schemas = [schemas_by_status[key] for key in sorted(schemas_by_status)]
        if len(ordered_schemas) == 1:
            merged_source_schema = ordered_schemas[0]
        else:
            merged_source_schema = {"oneOf": ordered_schemas}
        items.append(
            VerificationItem(
                endpoint_name=operation.endpoint_name,
                method=operation.method,
                section_name=section_name,
                class_name=section.root_class_name,
                source_schema=merged_source_schema,
                generated_module_path=str(
                    Path("models")
                    / operation.endpoint_name
                    / operation.method
                    / f"{section_name}.py"
                ),
            ),
        )

    return sections, items


__all__ = [
    "GenerationRun",
    "run_generation",
    "OpenAPILoadError",
    "WriteError",
]
