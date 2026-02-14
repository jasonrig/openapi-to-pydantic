"""Naming helpers for endpoint and Python identifiers."""

from __future__ import annotations

import keyword
import re
from collections import Counter

from .model_types import OperationSpec

_HTTP_METHODS: tuple[str, ...] = (
    "get",
    "put",
    "post",
    "delete",
    "patch",
    "head",
    "options",
    "trace",
)


_IDENTIFIER_SANITIZE_RE = re.compile(r"[^0-9a-zA-Z_]+")
_MULTIPLE_UNDERSCORES_RE = re.compile(r"_+")
_PATH_PARAM_RE = re.compile(r"^\{(?P<name>[^{}]+)\}$")


def sanitize_identifier(raw: str, *, lowercase: bool = True) -> str:
    """Convert arbitrary text into a valid Python identifier."""
    text = raw.lower() if lowercase else raw
    text = _IDENTIFIER_SANITIZE_RE.sub("_", text)
    text = _MULTIPLE_UNDERSCORES_RE.sub("_", text).strip("_")
    if not text:
        text = "root"
    if text[0].isdigit():
        text = f"x_{text}"
    if keyword.iskeyword(text):
        text = f"{text}_"
    return text


def path_to_endpoint_name(path: str) -> str:
    """Create endpoint name using the agreed path-based naming rules."""
    segments = [segment for segment in path.split("/") if segment]
    normalized_segments: list[str] = []
    for segment in segments:
        match = _PATH_PARAM_RE.match(segment)
        if match:
            param_name = sanitize_identifier(match.group("name"))
            normalized_segments.append(f"by_{param_name}")
            continue
        normalized_segments.append(sanitize_identifier(segment))

    endpoint_name = "__".join(segment for segment in normalized_segments if segment)
    endpoint_name = endpoint_name or "root"
    if endpoint_name[0].isdigit():
        endpoint_name = f"x_{endpoint_name}"
    return endpoint_name


def _operation_id_candidate(operation_id: str) -> str:
    return sanitize_identifier(operation_id)


def resolve_operations(
    raw_paths: dict[str, dict[str, object]],
) -> tuple[list[OperationSpec], list[str]]:
    """Extract operations and determine endpoint names with hybrid operationId fallback."""
    operations: list[tuple[str, str, dict[str, object], dict[str, object], str | None]] = []
    for path, path_item_untyped in raw_paths.items():
        if not isinstance(path_item_untyped, dict):
            continue
        path_item = path_item_untyped
        for method in _HTTP_METHODS:
            operation_untyped = path_item.get(method)
            if not isinstance(operation_untyped, dict):
                continue
            operation_id_raw = operation_untyped.get("operationId")
            operation_id: str | None = None
            if isinstance(operation_id_raw, str) and operation_id_raw.strip():
                operation_id = _operation_id_candidate(operation_id_raw.strip())
            operations.append((path, method, operation_untyped, path_item, operation_id))

    operation_ids = [item[4] for item in operations if item[4] is not None]
    counts = Counter(operation_ids)
    conflicting_ids = {name for name, count in counts.items() if count > 1}

    warnings: list[str] = []
    if conflicting_ids:
        joined = ", ".join(sorted(conflicting_ids))
        warnings.append(
            "Conflicting operationId values detected; using path-based naming for conflicts: "
            f"{joined}"
        )

    resolved: list[OperationSpec] = []
    for path, method, operation, path_item, operation_id in operations:
        if operation_id is not None and operation_id not in conflicting_ids:
            endpoint_name = operation_id
        else:
            endpoint_name = path_to_endpoint_name(path)
        resolved.append(
            OperationSpec(
                path=path,
                method=method,
                endpoint_name=endpoint_name,
                operation=operation,
                path_item=path_item,
            )
        )

    return resolved, warnings


def class_name(raw: str) -> str:
    """Convert a name to PascalCase class name."""
    clean = sanitize_identifier(raw)
    return "".join(part.capitalize() for part in clean.split("_") if part) or "Model"
