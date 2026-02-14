"""AST-based Python code generation for pydantic models."""

from __future__ import annotations

import ast
from typing import Any

from .model_types import FieldDef, ModelDef, SectionModel


def render_section_module(section: SectionModel) -> str:
    """Render section models as Python source code using AST."""
    body: list[ast.stmt] = [
        ast.ImportFrom(module="__future__", names=[ast.alias(name="annotations")], level=0),
        ast.ImportFrom(
            module="typing",
            names=[
                ast.alias(name="Any"),
                ast.alias(name="Annotated"),
                ast.alias(name="Literal"),
                ast.alias(name="Optional"),
                ast.alias(name="Union"),
            ],
            level=0,
        ),
        ast.ImportFrom(
            module="pydantic",
            names=[
                ast.alias(name="BaseModel"),
                ast.alias(name="ConfigDict"),
                ast.alias(name="Field"),
                ast.alias(name="RootModel"),
            ],
            level=0,
        ),
    ]

    for model in section.models:
        body.append(_model_to_ast(model))

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


def _value_expr(value: Any) -> ast.expr:
    parsed = ast.parse(repr(value), mode="eval")
    return parsed.body
