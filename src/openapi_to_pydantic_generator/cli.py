"""Command line interface for OpenAPI to pydantic generation."""

from __future__ import annotations

import argparse
from pathlib import Path

from .generator import OpenAPILoadError, WriteError, run_generation
from .verify import format_report


class CLIError(RuntimeError):
    """Raised when CLI execution fails."""


def build_parser() -> argparse.ArgumentParser:
    """Build the CLI parser."""
    parser = argparse.ArgumentParser(
        prog="openapi-to-pydantic-generator",
        description="Generate endpoint-scoped pydantic models from OpenAPI YAML",
    )
    parser.add_argument("--input", required=True, help="Path to an OpenAPI YAML file")
    parser.add_argument("--output", required=True, help="Output directory for generated packages")
    parser.add_argument(
        "--verify",
        action="store_true",
        help="Run schema equivalence verification against generated models",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """Run CLI and return process exit code."""
    parser = build_parser()
    args = parser.parse_args(argv)

    input_path = Path(args.input)
    output_path = Path(args.output)

    try:
        run = run_generation(
            input_path=input_path,
            output_dir=output_path,
            verify=bool(args.verify),
        )
    except (OpenAPILoadError, WriteError, CLIError) as exc:
        parser.error(str(exc))
        return 2

    for warning in run.result.warnings:
        print(f"Warning: {warning}")

    if run.verification_report is not None:
        print(format_report(run.verification_report))
        if run.verification_report.mismatch_count > 0:
            return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
