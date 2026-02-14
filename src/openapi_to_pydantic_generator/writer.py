"""Filesystem writers for generated model packages."""

from __future__ import annotations

from pathlib import Path

from .codegen_ast import render_section_module
from .model_types import SectionModel


class WriteError(RuntimeError):
    """Raised when output files cannot be written."""


def create_output_layout(output_dir: Path) -> Path:
    """Create output directory and root models package."""
    if output_dir.exists():
        raise WriteError(f"Output directory already exists: {output_dir}")

    models_dir = output_dir / "models"
    models_dir.mkdir(parents=True, exist_ok=False)
    _write_file(models_dir / "__init__.py", "")
    return models_dir


def write_operation_sections(
    *,
    models_dir: Path,
    endpoint_name: str,
    method: str,
    sections: list[SectionModel],
) -> None:
    """Write section modules for one endpoint method."""
    endpoint_dir = models_dir / endpoint_name
    method_dir = endpoint_dir / method
    endpoint_dir.mkdir(parents=True, exist_ok=True)
    method_dir.mkdir(parents=True, exist_ok=True)

    _write_file(endpoint_dir / "__init__.py", "")
    _write_file(method_dir / "__init__.py", "")

    for section in sections:
        path = method_dir / f"{section.section_name}.py"
        source = render_section_module(section)
        _write_file(path, source)


def _write_file(path: Path, content: str) -> None:
    try:
        path.write_text(content, encoding="utf-8")
    except OSError as exc:
        raise WriteError(f"Failed to write file {path}: {exc}") from exc
