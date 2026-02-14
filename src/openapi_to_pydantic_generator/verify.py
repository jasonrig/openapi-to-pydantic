"""Schema verification between source OpenAPI and generated pydantic models."""

from __future__ import annotations

import itertools
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType

from jsonschema.exceptions import SchemaError
from jsonschema.validators import validator_for
from pydantic import BaseModel

from .json_types import JSONValue
from .module_loading import load_module_from_path
from .model_types import VerificationItem
from .normalize import (
    Mismatch,
    normalize_generated_schema,
    normalize_source_schema,
    subset_mismatch,
)


@dataclass(frozen=True)
class VerificationMismatch:
    """One verification mismatch."""

    endpoint_name: str
    method: str
    section_name: str
    class_name: str
    path: str
    expected: JSONValue
    actual: JSONValue


@dataclass(frozen=True)
class VerificationReport:
    """Result of the verification phase."""

    verified_count: int
    mismatch_count: int
    mismatches: tuple[VerificationMismatch, ...]


def verify_models(
    *,
    items: list[VerificationItem],
    output_dir: Path,
) -> VerificationReport:
    """Verify generated model schemas against normalized source schemas.

    Args:
        items (list[VerificationItem]): Verification targets to compare.
        output_dir (Path): Root output directory containing generated modules.

    Returns:
        VerificationReport: Aggregate verification report with mismatch details.
    """
    mismatches: list[VerificationMismatch] = []

    for item in items:
        source_normalized = normalize_source_schema(item.source_schema)
        generated_class = _load_model_class(
            module_path=output_dir / item.generated_module_path,
            class_name=item.class_name,
        )
        generated_schema_value: JSONValue = generated_class.model_json_schema()
        if not isinstance(generated_schema_value, dict):
            raise RuntimeError(
                f"Generated schema must be a mapping for {item.class_name}: "
                f"{type(generated_schema_value)!r}"
            )
        generated_normalized = normalize_generated_schema(generated_schema_value)

        # Validate generated schema shape. Source schemas can carry OpenAPI-specific forms.
        try:
            validator_for(source_normalized).check_schema(source_normalized)
        except SchemaError:
            pass
        try:
            validator_for(generated_normalized).check_schema(generated_normalized)
        except SchemaError:
            pass

        mismatch = subset_mismatch(source_normalized, generated_normalized)
        if mismatch is not None:
            mismatches.append(
                _to_mismatch(
                    item=item,
                    mismatch=mismatch,
                )
            )

    return VerificationReport(
        verified_count=len(items),
        mismatch_count=len(mismatches),
        mismatches=tuple(mismatches),
    )


def format_report(report: VerificationReport) -> str:
    """Render a verification report as CLI output text.

    Args:
        report (VerificationReport): Verification report to format.

    Returns:
        str: Human-readable multiline report text.
    """
    lines = [
        f"Verified models: {report.verified_count}",
        f"Mismatches: {report.mismatch_count}",
    ]
    for mismatch in report.mismatches:
        lines.extend(
            [
                (
                    "- "
                    f"{mismatch.endpoint_name}.{mismatch.method}."
                    f"{mismatch.section_name}.{mismatch.class_name}"
                ),
                f"  path: {mismatch.path}",
                f"  expected: {short_repr(mismatch.expected)}",
                f"  actual: {short_repr(mismatch.actual)}",
            ]
        )
    return "\n".join(lines)


def _load_model_class(*, module_path: Path, class_name: str) -> type[BaseModel]:
    if not module_path.exists():
        raise RuntimeError(f"Generated module not found: {module_path}")

    module_name = f"generated_{abs(hash(str(module_path)))}_{next(_COUNTER)}"
    module = load_module_from_path(module_name=module_name, module_path=module_path)
    _rebuild_module_models(module=module)

    value = getattr(module, class_name, None)
    if not isinstance(value, type) or not issubclass(value, BaseModel):
        raise RuntimeError(f"Generated class {class_name} is missing or invalid in {module_path}")
    return value


def _to_mismatch(*, item: VerificationItem, mismatch: Mismatch) -> VerificationMismatch:
    return VerificationMismatch(
        endpoint_name=item.endpoint_name,
        method=item.method,
        section_name=item.section_name,
        class_name=item.class_name,
        path=mismatch.path,
        expected=mismatch.expected,
        actual=mismatch.actual,
    )


def short_repr(value: JSONValue, *, limit: int = 160) -> str:
    """Return a short representation for mismatch diagnostics.

    Args:
        value (JSONValue): Value to render.
        limit (int): Maximum output length.

    Returns:
        str: Truncated representation string.
    """
    text = repr(value)
    return text if len(text) <= limit else f"{text[: limit - 3]}..."


def _rebuild_module_models(*, module: ModuleType) -> None:
    model_types: list[type[BaseModel]] = []
    for value in module.__dict__.values():
        if not isinstance(value, type):
            continue
        if not issubclass(value, BaseModel):
            continue
        if value is BaseModel:
            continue
        if value.__module__ != module.__name__:
            continue
        model_types.append(value)

    for model_type in model_types:
        model_type.model_rebuild(_types_namespace=module.__dict__)


_COUNTER = itertools.count(1)
