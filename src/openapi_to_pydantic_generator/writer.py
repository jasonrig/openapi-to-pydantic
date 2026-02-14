"""Filesystem writers for generated model packages."""

from __future__ import annotations

from pathlib import Path
import subprocess
import sys

from .codegen_ast import (
    render_endpoint_init_module,
    render_models_init_module,
    render_section_module,
)
from .model_types import EndpointManifest, SectionModel

_GENERATED_RUFF_IGNORE_CODES: tuple[str, ...] = (
    "D100",
    "D101",
    "D102",
    "D103",
    "D104",
    "D205",
    "D301",
    "D415",
    "E501",
)


class WriteError(RuntimeError):
    """Raised when output files cannot be written."""


def create_output_layout(output_dir: Path) -> Path:
    """Create output directory and root models package.

    Args:
        output_dir (Path): Root output directory to create.

    Returns:
        Path: Path to the created `models` directory.
    """
    if output_dir.exists():
        raise WriteError(f"Output directory already exists: {output_dir}")

    models_dir = output_dir / "models"
    models_dir.mkdir(parents=True, exist_ok=False)
    _write_file(models_dir / "__init__.py", '"""Generated models package."""\n')
    return models_dir


def write_operation_sections(
    *,
    models_dir: Path,
    endpoint_name: str,
    method: str,
    sections: list[SectionModel],
) -> None:
    """Write section modules for one endpoint method.

    Args:
        models_dir (Path): Root generated models directory.
        endpoint_name (str): Endpoint package name.
        method (str): HTTP method name.
        sections (list[SectionModel]): Section models to render and write.
    """
    endpoint_dir = models_dir / endpoint_name
    method_dir = endpoint_dir / method
    endpoint_dir.mkdir(parents=True, exist_ok=True)
    method_dir.mkdir(parents=True, exist_ok=True)

    _write_file(
        method_dir / "__init__.py",
        (f'"""Generated sections for endpoint "{endpoint_name}" method "{method.upper()}"."""\n'),
    )

    for section in sections:
        path = method_dir / f"{section.section_name}.py"
        source = render_section_module(section)
        _write_file(path, source)


def write_endpoint_manifest(*, models_dir: Path, manifest: EndpointManifest) -> None:
    """Write endpoint package ``__init__.py`` with manifest metadata.

    Args:
        models_dir (Path): Root generated models directory.
        manifest (EndpointManifest): Endpoint manifest payload.
    """
    endpoint_dir = models_dir / manifest.endpoint_name
    endpoint_dir.mkdir(parents=True, exist_ok=True)
    source = render_endpoint_init_module(manifest)
    _write_file(endpoint_dir / "__init__.py", source)


def write_models_index(*, models_dir: Path, endpoint_manifests: list[EndpointManifest]) -> None:
    """Write root models package ``__init__.py`` with endpoint index documentation.

    Args:
        models_dir (Path): Root generated models directory.
        endpoint_manifests (list[EndpointManifest]): Endpoint documentation payloads.
    """
    source = render_models_init_module(endpoint_manifests)
    _write_file(models_dir / "__init__.py", source)


def format_generated_tree(*, models_dir: Path) -> None:
    """Run Ruff auto-fixes and formatter against generated model files.

    Args:
        models_dir (Path): Generated models directory to format.
    """
    _run_ruff(models_dir=models_dir, args=("format", str(models_dir)))
    _run_ruff(
        models_dir=models_dir,
        args=(
            "check",
            "--fix",
            "--ignore",
            ",".join(_GENERATED_RUFF_IGNORE_CODES),
            str(models_dir),
        ),
    )
    _run_ruff(models_dir=models_dir, args=("format", str(models_dir)))


def _run_ruff(*, models_dir: Path, args: tuple[str, ...]) -> None:
    command = [sys.executable, "-m", "ruff", *args]
    command_desc = " ".join(args)
    try:
        subprocess.run(
            command,
            check=True,
            capture_output=True,
            text=True,
        )
    except OSError as exc:
        raise WriteError(f"Failed to execute ruff {command_desc} for {models_dir}: {exc}") from exc
    except subprocess.CalledProcessError as exc:
        error_text = exc.stderr.strip() or exc.stdout.strip() or str(exc)
        raise WriteError(f"ruff {command_desc} failed for {models_dir}: {error_text}") from exc


def _write_file(path: Path, content: str) -> None:
    try:
        path.write_text(content, encoding="utf-8")
    except OSError as exc:
        raise WriteError(f"Failed to write file {path}: {exc}") from exc
