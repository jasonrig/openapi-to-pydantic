"""OpenAPI document loading and basic validation."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from openapi_python_client.schema import OpenAPI
from pydantic import ValidationError


class OpenAPILoadError(RuntimeError):
    """Raised when a source OpenAPI document cannot be loaded."""


def load_openapi_document(path: Path) -> dict[str, Any]:
    """Load and validate an OpenAPI document from YAML."""
    try:
        with path.open("r", encoding="utf-8") as handle:
            payload = yaml.safe_load(handle)
    except OSError as exc:
        raise OpenAPILoadError(f"Failed to read OpenAPI file {path}: {exc}") from exc
    except yaml.YAMLError as exc:
        raise OpenAPILoadError(f"Failed to parse YAML in {path}: {exc}") from exc

    if not isinstance(payload, dict):
        raise OpenAPILoadError(
            f"OpenAPI document must deserialize to a mapping, got {type(payload)!r}"
        )

    try:
        OpenAPI.model_validate(payload)
    except ValidationError as exc:
        raise OpenAPILoadError(f"OpenAPI schema validation failed for {path}: {exc}") from exc

    return payload


def get_openapi_version(document: dict[str, Any]) -> str:
    """Return the declared OpenAPI version string."""
    version = document.get("openapi")
    if not isinstance(version, str) or not version.strip():
        raise OpenAPILoadError("Missing or invalid 'openapi' version field")
    return version.strip()


def ensure_supported_version(version: str) -> None:
    """Validate that the input version is OpenAPI v3+."""
    major_text = version.split(".", maxsplit=1)[0]
    try:
        major = int(major_text)
    except ValueError as exc:
        raise OpenAPILoadError(f"Unable to parse OpenAPI version: {version}") from exc
    if major < 3:
        raise OpenAPILoadError(f"Unsupported OpenAPI version {version}; only v3+ is supported")
