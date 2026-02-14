"""AST-based Python code generation for pydantic models."""

from __future__ import annotations

import ast
from collections.abc import Iterable
import textwrap
from typing import Optional

from .json_types import JSONValue
from .model_types import EndpointManifest, FieldDef, ModelDef, SectionModel

_TYPING_IMPORT_ORDER: tuple[str, ...] = (
    "Annotated",
    "Literal",
    "Optional",
    "Union",
)

_PYDANTIC_IMPORT_ORDER: tuple[str, ...] = (
    "BaseModel",
    "ConfigDict",
    "Field",
    "RootModel",
)


def render_section_module(section: SectionModel) -> str:
    """Render section models as Python source code using AST.

    Args:
        section (SectionModel): Section model definition to render.

    Returns:
        str: Generated Python source code for the section.
    """
    body: list[ast.stmt] = [
        ast.ImportFrom(module="__future__", names=[ast.alias(name="annotations")], level=0),
    ]
    body.extend(_build_imports(section))

    for model in section.models:
        body.append(_model_to_ast(model))

    module = ast.Module(body=body, type_ignores=[])
    ast.fix_missing_locations(module)
    return ast.unparse(module) + "\n"


def render_endpoint_init_module(manifest: EndpointManifest) -> str:
    """Render endpoint package ``__init__.py`` with manifest metadata.

    Args:
        manifest (EndpointManifest): Endpoint manifest payload.

    Returns:
        str: Generated Python source for endpoint package metadata.
    """
    docstring = _endpoint_manifest_docstring(manifest)
    body: list[ast.stmt] = [ast.Expr(value=ast.Constant(value=docstring))]
    module = ast.Module(body=body, type_ignores=[])
    ast.fix_missing_locations(module)
    return ast.unparse(module) + "\n"


def render_models_init_module(endpoint_manifests: list[EndpointManifest]) -> str:
    """Render root models package ``__init__.py`` documentation module.

    Args:
        endpoint_manifests (list[EndpointManifest]): Endpoint documentation payloads.

    Returns:
        str: Generated Python source for root models package documentation.
    """
    docstring = _models_index_docstring(endpoint_manifests)
    body: list[ast.stmt] = [ast.Expr(value=ast.Constant(value=docstring))]
    module = ast.Module(body=body, type_ignores=[])
    ast.fix_missing_locations(module)
    return ast.unparse(module) + "\n"


def _model_to_ast(model: ModelDef) -> ast.ClassDef:
    bases: list[ast.expr]
    if model.is_root:
        if model.root_annotation is None:
            raise ValueError(f"Root model {model.name} missing annotation")
        bases = [
            ast.Subscript(
                value=ast.Name(id="RootModel", ctx=ast.Load()),
                slice=_expr(model.root_annotation),
                ctx=ast.Load(),
            )
        ]
    else:
        bases = [ast.Name(id="BaseModel", ctx=ast.Load())]

    model_config = model.config
    class_body: list[ast.stmt] = []
    if model_config.docstring:
        class_body.append(ast.Expr(value=ast.Constant(value=model_config.docstring)))

    config_keywords: list[ast.keyword] = []
    if model_config.title:
        config_keywords.append(
            ast.keyword(arg="title", value=ast.Constant(value=model_config.title))
        )
    if model_config.extra_behavior:
        config_keywords.append(
            ast.keyword(arg="extra", value=ast.Constant(value=model_config.extra_behavior))
        )
    if model_config.schema_extra:
        config_keywords.append(
            ast.keyword(arg="json_schema_extra", value=_value_expr(model_config.schema_extra))
        )
    if config_keywords:
        class_body.append(
            ast.Assign(
                targets=[ast.Name(id="model_config", ctx=ast.Store())],
                value=ast.Call(
                    func=ast.Name(id="ConfigDict", ctx=ast.Load()),
                    args=[],
                    keywords=config_keywords,
                ),
            )
        )

    if not model.is_root:
        if model_config.additional_properties_annotation:
            class_body.append(
                ast.AnnAssign(
                    target=ast.Name(id="__pydantic_extra__", ctx=ast.Store()),
                    annotation=_expr(model_config.additional_properties_annotation),
                    value=ast.Call(
                        func=ast.Name(id="Field", ctx=ast.Load()),
                        args=[],
                        keywords=[ast.keyword(arg="init", value=ast.Constant(value=False))],
                    ),
                    simple=1,
                )
            )
        for field in model.fields:
            class_body.append(_field_to_ast(field))

    if not class_body:
        class_body.append(ast.Pass())

    return ast.ClassDef(
        name=model.name,
        bases=bases,
        keywords=[],
        body=class_body,
        decorator_list=[],
        type_params=[],
    )


def _field_to_ast(field: FieldDef) -> ast.AnnAssign:
    keywords: list[ast.keyword] = []
    if field.source_name != field.name:
        keywords.append(ast.keyword(arg="alias", value=ast.Constant(value=field.source_name)))

    metadata = dict(field.metadata)
    json_schema_extra = metadata.get("json_schema_extra")
    if not isinstance(json_schema_extra, dict):
        json_schema_extra = {}
    if "example" in metadata:
        json_schema_extra = dict(json_schema_extra)
        json_schema_extra["example"] = metadata.pop("example")
    if json_schema_extra:
        metadata["json_schema_extra"] = json_schema_extra

    for key, value in metadata.items():
        keywords.append(ast.keyword(arg=key, value=_value_expr(value)))

    if field.required and field.default is None:
        default_value: ast.expr = ast.Constant(value=Ellipsis)
    else:
        default_value = _value_expr(field.default)

    call = ast.Call(
        func=ast.Name(id="Field", ctx=ast.Load()),
        args=[default_value],
        keywords=keywords,
    )

    return ast.AnnAssign(
        target=ast.Name(id=field.name, ctx=ast.Store()),
        annotation=_expr(field.annotation),
        value=call,
        simple=1,
    )


def _expr(code: str) -> ast.expr:
    parsed = ast.parse(code, mode="eval")
    return parsed.body


def _value_expr(value: Optional[JSONValue]) -> ast.expr:
    parsed = ast.parse(repr(value), mode="eval")
    return parsed.body


def _build_imports(section: SectionModel) -> list[ast.stmt]:
    used_annotation_names = _collect_used_annotation_names(section)

    typing_imports = [name for name in _TYPING_IMPORT_ORDER if name in used_annotation_names]
    pydantic_imports = _collect_pydantic_imports(
        models=section.models,
        used_annotation_names=used_annotation_names,
    )

    imports: list[ast.stmt] = []
    if typing_imports:
        imports.append(
            ast.ImportFrom(
                module="typing",
                names=[ast.alias(name=name) for name in typing_imports],
                level=0,
            )
        )
    if pydantic_imports:
        imports.append(
            ast.ImportFrom(
                module="pydantic",
                names=[ast.alias(name=name) for name in pydantic_imports],
                level=0,
            )
        )
    return imports


def _collect_used_annotation_names(section: SectionModel) -> set[str]:
    names: set[str] = set()
    for annotation in _iter_annotation_exprs(section.models):
        names.update(_extract_loaded_names(annotation))
    return names


def _iter_annotation_exprs(models: tuple[ModelDef, ...]) -> Iterable[str]:
    for model in models:
        if model.root_annotation is not None:
            yield model.root_annotation
        if model.config.additional_properties_annotation is not None:
            yield model.config.additional_properties_annotation
        for field in model.fields:
            yield field.annotation


def _extract_loaded_names(expr_code: str) -> set[str]:
    parsed = ast.parse(expr_code, mode="eval")
    loaded_names: set[str] = set()
    for node in ast.walk(parsed):
        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load):
            loaded_names.add(node.id)
    return loaded_names


def _collect_pydantic_imports(
    *,
    models: tuple[ModelDef, ...],
    used_annotation_names: set[str],
) -> list[str]:
    needs_field = False
    needs_config = False
    for model in models:
        if model.fields or model.config.additional_properties_annotation is not None:
            needs_field = True
        if model.config.title or model.config.extra_behavior or model.config.schema_extra:
            needs_config = True

    requested: set[str] = set()
    if any(not model.is_root for model in models):
        requested.add("BaseModel")
    if any(model.is_root for model in models):
        requested.add("RootModel")
    if needs_field or "Field" in used_annotation_names:
        requested.add("Field")
    if needs_config:
        requested.add("ConfigDict")

    return [name for name in _PYDANTIC_IMPORT_ORDER if name in requested]


def _endpoint_manifest_docstring(manifest: EndpointManifest) -> str:
    lines: list[str] = [
        "Generated endpoint package documentation.",
        "",
        f"Endpoint module: .{manifest.endpoint_name}",
        "Original OpenAPI path(s):",
    ]
    for path in manifest.paths:
        lines.append(f"- {path}")
    lines.append("")
    lines.append("Operation and model usage map:")
    for operation in manifest.operations:
        lines.append(f"- {operation.method.upper()} {operation.path}")
        description = operation.summary or operation.description
        if description:
            lines.append(f"  summary: {description}")
        if not operation.sections:
            lines.append("  - no generated sections")
            continue
        for section in operation.sections:
            section_module = f".{manifest.endpoint_name}.{operation.method}.{section.section_name}"
            lines.append(f"  - section module: {section_module}")
            lines.append(f"    root model: {section.root_class_name}")
            lines.append("    models:")
            for model_name in section.model_names:
                lines.append(f"    - {model_name}")
    return "\n".join(lines)


def _models_index_docstring(endpoint_manifests: list[EndpointManifest]) -> str:
    lines: list[str] = [
        "Generated models package index for coding-agent navigation.",
        "",
        "Each endpoint package maps OpenAPI URL patterns to Python modules.",
        "Use this index to locate endpoint, method, and section modules quickly.",
        "",
        "Endpoint index:",
    ]
    for manifest in endpoint_manifests:
        lines.append(f"- module: .{manifest.endpoint_name}")
        lines.append("  paths:")
        for path in manifest.paths:
            lines.append(f"  - {path}")
        lines.append("  operations:")
        for operation in manifest.operations:
            summary = operation.summary or operation.description
            if summary:
                wrapped_summary = _wrap_summary(summary)
                lines.append(f"  - {operation.method.upper()} {operation.path}")
                for summary_line in wrapped_summary:
                    lines.append(f"    summary: {summary_line}")
            else:
                lines.append(f"  - {operation.method.upper()} {operation.path}")
    return "\n".join(lines)


def _wrap_summary(text: str) -> list[str]:
    wrapped = textwrap.wrap(text, width=84)
    return wrapped if wrapped else [text]
