"""Package entrypoint."""

from __future__ import annotations

from .cli import main

main.main(prog_name="openapi-to-pydantic-generator", standalone_mode=True)
