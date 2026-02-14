"""Integration tests for generator behavior."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from openapi_to_pydantic_generator.generator import WriteError, run_generation
from .fixture_helpers import iter_fixture_paths, parametrize_fixtures


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
    assert report.mismatch_count <= report.verified_count


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
