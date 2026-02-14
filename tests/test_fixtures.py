"""Fixture-based OpenAPI validation tests."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from openapi_python_client.schema import OpenAPI
from pydantic import ValidationError

from openapi_to_pydantic_generator.json_types import JSONObject, JSONValue
from .fixture_helpers import fixture_dir, parametrize_fixtures

FIXTURE_DIR = fixture_dir()


def _load_yaml(path: Path) -> JSONObject:
    try:
        with path.open("r", encoding="utf-8") as handle:
            data = yaml.safe_load(handle)
    except yaml.YAMLError as exc:
        pytest.fail(f"Failed to parse YAML in {path}: {exc}")
    except OSError as exc:
        pytest.fail(f"Failed to read fixture {path}: {exc}")

    value: JSONValue = data
    if not isinstance(value, dict):
        pytest.fail(f"Fixture {path} must parse to a mapping, got {type(value)!r}")
    assert isinstance(value, dict)

    typed: dict[str, JSONValue] = {}
    for key, item in value.items():
        if not isinstance(key, str):
            pytest.fail(f"Fixture {path} has a non-string top-level key: {key!r}")
        item_value: JSONValue = item
        typed[key] = item_value
    return typed


def test_fixture_directory_exists() -> None:
    """Ensure the fixtures directory is present."""
    assert FIXTURE_DIR.is_dir(), f"Fixture directory not found: {FIXTURE_DIR}"


@parametrize_fixtures()
def test_fixture_is_valid_openapi(fixture_path: Path) -> None:
    """Validate each fixture using openapi-python-client's OpenAPI schema model."""
    data = _load_yaml(fixture_path)
    try:
        OpenAPI.model_validate(data)
    except ValidationError as exc:
        pytest.fail(f"OpenAPI validation failed for {fixture_path}:\n{exc}")
