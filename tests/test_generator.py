"""Integration tests for generator behavior."""

from __future__ import annotations

import ast
import subprocess
import sys
from pathlib import Path

import pytest

from openapi_to_pydantic_generator.generator import WriteError, run_generation
from openapi_to_pydantic_generator.naming import path_to_endpoint_name
from .fixture_helpers import iter_fixture_paths, parametrize_fixtures

_INLINE_OPENAPI_PATH = "/users/{user_id}/posts"
_INLINE_OPENAPI_SPEC = """
openapi: 3.1.0
info:
  title: Inline Test API
  version: 1.0.0
paths:
  /users/{user_id}/posts:
    get:
      summary: List posts for a user.
      parameters:
        - in: path
          name: user_id
          required: true
          schema:
            type: string
        - in: query
          name: limit
          required: false
          schema:
            type: integer
      responses:
        "200":
          description: ok
          content:
            application/json:
              schema:
                type: object
                properties:
                  posts:
                    type: array
                    items:
                      type: object
                      properties:
                        id:
                          type: string
    post:
      description: Create a post for the user.
      requestBody:
        required: true
        content:
          application/json:
            schema:
              type: object
              properties:
                payload:
                  type: object
                  properties:
                    title:
                      type: string
      responses:
        "201":
          description: created
          content:
            application/json:
              schema:
                type: object
                properties:
                  id:
                    type: string
"""


def _write_inline_openapi_spec(path: Path) -> None:
    path.write_text(_INLINE_OPENAPI_SPEC, encoding="utf-8")


def _module_docstring(path: Path) -> str:
    source = path.read_text(encoding="utf-8")
    parsed = ast.parse(source)
    docstring = ast.get_docstring(parsed)
    if docstring is None:
        raise RuntimeError(f"Module docstring missing: {path}")
    return docstring


def _class_names_from_section_module(section_module_path: Path) -> list[str]:
    section_module_source = section_module_path.read_text(encoding="utf-8")
    parsed = ast.parse(section_module_source)
    return [node.name for node in parsed.body if isinstance(node, ast.ClassDef)]


def _assert_endpoint_docstring_matches_generated_modules(
    *,
    endpoint_docstring: str,
    output_dir: Path,
    endpoint_name: str,
) -> None:
    endpoint_dir = output_dir / "models" / endpoint_name
    for method_dir in sorted(path for path in endpoint_dir.iterdir() if path.is_dir()):
        method = method_dir.name
        assert f"- {method.upper()} {_INLINE_OPENAPI_PATH}" in endpoint_docstring
        for section_path in sorted(method_dir.glob("*.py")):
            if section_path.name == "__init__.py":
                continue
            section_name = section_path.stem
            section_module = f".{endpoint_name}.{method}.{section_name}"
            assert section_module in endpoint_docstring
            class_names = _class_names_from_section_module(section_path)
            assert class_names, section_path
            for class_name in class_names:
                assert class_name in endpoint_docstring


@parametrize_fixtures()
def test_generation_smoke(fixture_path: Path, tmp_path: Path) -> None:
    """Each fixture should generate a models tree without crashing."""
    output_dir = tmp_path / fixture_path.stem
    run = run_generation(
        input_path=fixture_path,
        output_dir=output_dir,
        verify=False,
    )

    assert Path(run.result.output_dir) == output_dir
    assert (output_dir / "models").is_dir()


@parametrize_fixtures()
def test_generation_with_verification(fixture_path: Path, tmp_path: Path) -> None:
    """Verification should complete and return a report for known fixtures."""
    output_dir = tmp_path / f"{fixture_path.stem}_verified"
    run = run_generation(
        input_path=fixture_path,
        output_dir=output_dir,
        verify=True,
    )
    report = run.verification_report
    assert report is not None
    assert report.verified_count > 0
    if report.mismatch_count > 0:
        preview = "\n".join(
            (
                f"{m.path} :: "
                f"{m.endpoint_name}.{m.method}.{m.section_name}.{m.class_name} | "
                f"expected={m.expected!r} actual={m.actual!r}"
            )
            for m in report.mismatches[:8]
        )
        pytest.fail(
            f"Verification mismatches for {fixture_path.name}: "
            f"{report.mismatch_count}/{report.verified_count}\n{preview}"
        )


def test_output_directory_must_not_exist(tmp_path: Path) -> None:
    """Generator refuses to write into pre-existing output directories."""
    fixture_path = iter_fixture_paths()[0]
    output_dir = tmp_path / "existing"
    output_dir.mkdir(parents=True)

    with pytest.raises(WriteError):
        run_generation(
            input_path=fixture_path,
            output_dir=output_dir,
            verify=False,
        )


def test_generation_invokes_ruff_formatting(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Generation should run ruff formatting on emitted model files."""
    fixture_path = iter_fixture_paths()[0]
    output_dir = tmp_path / "formatted"
    captured: dict[str, Path] = {}

    def _fake_format(*, models_dir: Path) -> None:
        captured["models_dir"] = models_dir

    monkeypatch.setattr(
        "openapi_to_pydantic_generator.generator.format_generated_tree",
        _fake_format,
    )

    run_generation(
        input_path=fixture_path,
        output_dir=output_dir,
        verify=False,
    )
    assert "models_dir" in captured, f"ruff formatting hook was not called: {captured!r}"
    assert captured["models_dir"] == output_dir / "models"


def test_cli_help_screen() -> None:
    """Running the CLI help should succeed and print usage information."""
    result = subprocess.run(
        [sys.executable, "-m", "openapi_to_pydantic_generator", "--help"],
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    assert "usage:" in result.stdout.lower()


def test_generated_modules_pass_ruff_check(tmp_path: Path) -> None:
    """Generated modules should pass all ruff checks."""
    fixture_path = iter_fixture_paths()[0]
    output_dir = tmp_path / "no_unused_imports"
    run_generation(
        input_path=fixture_path,
        output_dir=output_dir,
        verify=False,
    )

    lint = subprocess.run(
        [
            sys.executable,
            "-m",
            "ruff",
            "check",
            "--ignore",
            "D100,D101,D102,D103,D104,D205,D301,D415,E501",
            str(output_dir / "models"),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    details = f"{lint.stdout}\n{lint.stderr}".strip()
    assert lint.returncode == 0, details


def test_generated_package_docstrings_include_navigation_context(tmp_path: Path) -> None:
    """Generated package docstrings should map URL patterns to modules and models."""
    spec_path = tmp_path / "inline_openapi.yaml"
    _write_inline_openapi_spec(spec_path)

    output_dir = tmp_path / "generated"
    run_generation(
        input_path=spec_path,
        output_dir=output_dir,
        verify=False,
    )

    endpoint_name = path_to_endpoint_name(_INLINE_OPENAPI_PATH)
    endpoint_init = output_dir / "models" / endpoint_name / "__init__.py"
    endpoint_docstring = _module_docstring(endpoint_init)
    assert _INLINE_OPENAPI_PATH in endpoint_docstring
    assert "Operation and model usage map:" in endpoint_docstring
    assert f"- GET {_INLINE_OPENAPI_PATH}" in endpoint_docstring
    assert f"- POST {_INLINE_OPENAPI_PATH}" in endpoint_docstring
    assert "List posts for a user." in endpoint_docstring
    assert "Create a post for the user." in endpoint_docstring
    _assert_endpoint_docstring_matches_generated_modules(
        endpoint_docstring=endpoint_docstring,
        output_dir=output_dir,
        endpoint_name=endpoint_name,
    )

    root_init = output_dir / "models" / "__init__.py"
    root_docstring = _module_docstring(root_init)
    assert f"module: .{endpoint_name}" in root_docstring
    assert _INLINE_OPENAPI_PATH in root_docstring
    assert "List posts for a user." in root_docstring
