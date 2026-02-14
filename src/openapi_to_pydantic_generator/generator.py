"""High-level generator orchestration."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from .json_types import MutableJSONObject, JSONObject, JSONValue
from .loader import (
    OpenAPILoadError,
    ensure_supported_version,
    get_openapi_version,
    load_openapi_document,
)
from .model_types import (
    EndpointManifest,
    GenerationResult,
    OperationManifestEntry,
    OperationSpec,
    SectionManifestEntry,
    SectionModel,
    VerificationItem,
)
from .naming import resolve_operations
from .resolver import Resolver, SectionSchemas
from .schema_to_models import SchemaConverter
from .verify import VerificationReport, verify_models
from .writer import (
    WriteError,
    create_output_layout,
    format_generated_tree,
    write_endpoint_manifest,
    write_models_index,
    write_operation_sections,
)


@dataclass(frozen=True)
class GenerationRun:
    """Generation result with optional verification report."""

    result: GenerationResult
    verification_report: Optional[VerificationReport]


def run_generation(
    *,
    input_path: Path,
    output_dir: Path,
    verify: bool,
) -> GenerationRun:
    """Generate endpoint-scoped models from an OpenAPI document.

    Args:
        input_path (Path): Path to the input OpenAPI document.
        output_dir (Path): Directory where generated files are written.
        verify (bool): Whether to run schema verification after generation.

    Returns:
        GenerationRun: Generation metadata and optional verification report.
    """
    operations, warnings, resolver, converter, models_dir = _prepare_generation(
        input_path=input_path,
        output_dir=output_dir,
    )

    verification_items, endpoint_manifests = _generate_operations(
        operations=operations,
        resolver=resolver,
        converter=converter,
        models_dir=models_dir,
    )
    for endpoint_manifest in endpoint_manifests:
        write_endpoint_manifest(
            models_dir=models_dir,
            manifest=endpoint_manifest,
        )
    write_models_index(
        models_dir=models_dir,
        endpoint_manifests=endpoint_manifests,
    )

    format_generated_tree(models_dir=models_dir)

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
    )
    return GenerationRun(result=result, verification_report=report)


def _prepare_generation(
    *,
    input_path: Path,
    output_dir: Path,
) -> tuple[list[OperationSpec], list[str], Resolver, SchemaConverter, Path]:
    document = load_openapi_document(input_path)
    version = get_openapi_version(document)
    ensure_supported_version(version)
    path_map = _load_path_map(document)
    operations, warnings = resolve_operations(path_map)
    models_dir = create_output_layout(output_dir)
    resolver = Resolver(document)
    converter = SchemaConverter(version)
    return operations, warnings, resolver, converter, models_dir


def _load_path_map(document: JSONObject) -> dict[str, JSONObject]:
    raw_paths = document.get("paths")
    if not isinstance(raw_paths, dict):
        raise OpenAPILoadError("OpenAPI document missing 'paths' object")

    path_map: dict[str, JSONObject] = {}
    for path, path_item in raw_paths.items():
        if isinstance(path, str) and isinstance(path_item, dict):
            path_map[path] = path_item
    return path_map


def _generate_operations(
    *,
    operations: list[OperationSpec],
    resolver: Resolver,
    converter: SchemaConverter,
    models_dir: Path,
) -> tuple[list[VerificationItem], list[EndpointManifest]]:
    verification_items: list[VerificationItem] = []
    endpoint_paths_by_name: dict[str, list[str]] = {}
    endpoint_operations_by_name: dict[str, list[OperationManifestEntry]] = {}
    for operation in operations:
        section_schemas = resolver.build_section_schemas(operation)
        sections, items = _build_operation_sections(
            operation=operation,
            section_schemas=section_schemas,
            converter=converter,
        )
        if not sections:
            continue
        write_operation_sections(
            models_dir=models_dir,
            endpoint_name=operation.endpoint_name,
            method=operation.method,
            sections=sections,
        )
        verification_items.extend(items)
        _record_endpoint_manifest(
            operation=operation,
            sections=sections,
            endpoint_paths_by_name=endpoint_paths_by_name,
            endpoint_operations_by_name=endpoint_operations_by_name,
        )
    endpoint_manifests = [
        EndpointManifest(
            endpoint_name=endpoint_name,
            paths=tuple(endpoint_paths_by_name.get(endpoint_name, [])),
            operations=tuple(operation_entries),
        )
        for endpoint_name, operation_entries in endpoint_operations_by_name.items()
    ]
    endpoint_manifests.sort(key=lambda item: item.endpoint_name)
    return verification_items, endpoint_manifests


def _build_operation_sections(
    *,
    operation: OperationSpec,
    section_schemas: SectionSchemas,
    converter: SchemaConverter,
) -> tuple[list[SectionModel], list[VerificationItem]]:
    sections: list[SectionModel] = []
    items: list[VerificationItem] = []

    _append_simple_sections(
        operation=operation,
        section_schemas=section_schemas,
        converter=converter,
        sections=sections,
        items=items,
    )
    _append_status_sections(
        operation=operation,
        section_schemas=section_schemas,
        converter=converter,
        sections=sections,
        items=items,
    )

    return sections, items


def _append_simple_sections(
    *,
    operation: OperationSpec,
    section_schemas: SectionSchemas,
    converter: SchemaConverter,
    sections: list[SectionModel],
    items: list[VerificationItem],
) -> None:
    section_schema_map: list[tuple[str, str, Optional[MutableJSONObject]]] = [
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


def _append_status_sections(
    *,
    operation: OperationSpec,
    section_schemas: SectionSchemas,
    converter: SchemaConverter,
    sections: list[SectionModel],
    items: list[VerificationItem],
) -> None:
    status_sections: list[tuple[str, str, dict[str, MutableJSONObject]]] = [
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
        merged_source_schema: MutableJSONObject
        if len(ordered_schemas) == 1:
            merged_source_schema = ordered_schemas[0]
        else:
            one_of_values: list[JSONValue] = list(ordered_schemas)
            merged_source_schema = {"oneOf": one_of_values}
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


def _record_endpoint_manifest(
    *,
    operation: OperationSpec,
    sections: list[SectionModel],
    endpoint_paths_by_name: dict[str, list[str]],
    endpoint_operations_by_name: dict[str, list[OperationManifestEntry]],
) -> None:
    paths = endpoint_paths_by_name.setdefault(operation.endpoint_name, [])
    if operation.path not in paths:
        paths.append(operation.path)

    section_entries = tuple(
        SectionManifestEntry(
            section_name=section.section_name,
            root_class_name=section.root_class_name,
            model_names=tuple(model.name for model in section.models),
        )
        for section in sections
    )
    endpoint_operations_by_name.setdefault(operation.endpoint_name, []).append(
        OperationManifestEntry(
            method=operation.method,
            path=operation.path,
            summary=_string_or_none(operation.operation.get("summary")),
            description=_string_or_none(operation.operation.get("description")),
            sections=section_entries,
        ),
    )


def _string_or_none(value: JSONValue) -> Optional[str]:
    if isinstance(value, str):
        stripped = value.strip()
        if stripped:
            return stripped
    return None


__all__ = [
    "GenerationRun",
    "run_generation",
    "OpenAPILoadError",
    "WriteError",
]
