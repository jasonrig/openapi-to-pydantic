"""Command line interface for OpenAPI to pydantic generation."""

from __future__ import annotations

from pathlib import Path

import click

from .generator import run_generation
from .verify import format_report


class VerificationMismatchError(RuntimeError):
    """Raised when verification finds schema mismatches."""


def _run_cli(input_path: Path, output_path: Path, verify: bool) -> None:
    """Run CLI."""
    run = run_generation(
        input_path=input_path,
        output_dir=output_path,
        verify=verify,
    )

    for warning in run.result.warnings:
        click.echo(f"Warning: {warning}", err=True)

    if run.verification_report is not None:
        click.echo(format_report(run.verification_report))
        if run.verification_report.mismatch_count > 0:
            mismatch_count = run.verification_report.mismatch_count
            raise VerificationMismatchError(
                f"Verification failed with {mismatch_count} schema mismatches."
            )


main = click.Command(
    name="openapi-to-pydantic-generator",
    help="Generate endpoint-scoped pydantic models from OpenAPI YAML",
    callback=_run_cli,
    params=[
        click.Option(
            ["--input", "input_path"],
            required=True,
            type=click.Path(path_type=Path, dir_okay=False, readable=True),
            help="Path to an OpenAPI YAML file",
        ),
        click.Option(
            ["--output", "output_path"],
            required=True,
            type=click.Path(path_type=Path, file_okay=False),
            help="Output directory for generated packages",
        ),
        click.Option(
            ["--verify"],
            is_flag=True,
            help="Run schema equivalence verification against generated models",
        ),
    ],
)
