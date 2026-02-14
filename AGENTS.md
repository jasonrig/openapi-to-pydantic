# AGENTS.md

## Purpose
- Build and maintain an OpenAPI-to-Pydantic generator with deterministic, test-driven behavior.
- Prioritize correctness, readability, and maintainability over clever shortcuts.

## Project Scope
- Support OpenAPI `3.x` and above.
- Generate endpoint-scoped Pydantic models from OpenAPI schemas.
- Preserve schema intent in generated models (including nullability/default handling).
- Verify generated schema behavior against normalized source schemas.

## Core Workflow
- Use the test harness first; avoid one-off scripts unless a test cannot provide the needed signal.
- Add/adjust tests when behavior changes.
- Keep changes small and logically grouped.
- Commit frequently at stable checkpoints.

## Non-Negotiable Rules
- Never modify fixtures to make tests pass.
- Never manually edit generated artifacts.
- Never bypass pre-commit hooks.
- Never suppress lint/type issues without explicit approval.
- Do not use `Any` or `object` as a shortcut type.
- Prefer `Optional[T]` over `T | None`.

## Code Generation Rules
- Generate Python code via `ast` (no handwritten source-template hacks for model modules).
- Keep generated package docs useful for humans and coding agents:
  - Endpoint package `__init__.py` must document original paths and per-method/per-section model usage.
  - Root `models/__init__.py` must provide a package-level index.
  - Use relative module notation in docs (for example, `.users.get.response`).
- Run Ruff on generated output as part of generation.

## Typing and Style
- All new code must be fully type-annotated.
- Use `Mapping` where mutable dictionary behavior is not required.
- Keep functions focused and names explicit.
- Follow Google-style docstrings in `src/`.
- Public interfaces should document arguments; keep docstrings synchronized with signatures.

## Tooling
- Use `uv` for all dependency and execution tasks.
- Recommended local gate order:
  1. `uv run pre-commit run --all-files`
  2. `uv run pytest -q`
- If running individual tools, use:
  - `uv run ruff check .`
  - `uv run ruff format .`
  - `uv run mypy src tests`
  - `uv run pylint src tests`
  - `uv run pydoclint --style=google src`

## Testing Strategy
- Fixture discovery is automatic from `tests/fixtures/openapi_specs`.
- Treat fixture verification failures as product regressions unless proven to be invalid fixture data.
- Keep tests deterministic and focused on observable behavior.
- Include regression tests for normalization edge cases.

## Error Handling
- Fail loudly with informative exception messages.
- Avoid silent fallbacks that hide root causes.

## Decision Logging
- If multiple valid approaches exist, choose one pragmatically.
- Record notable tradeoffs and rationale in `DEVELOPMENT_LOG.md`.
