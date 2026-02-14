# OpenAPI to Pydantic Generator

> [!WARNING]
> Slop warning: this project was generated entirely by AI. Use at your own risk.

Generate endpoint-scoped Pydantic v2 models from OpenAPI v3+ documents.

The generator reads an OpenAPI YAML file, resolves local `$ref` values, and emits a Python package under `models/` with per-endpoint/per-method modules for:

- `url_params`
- `query_params`
- `headers`
- `cookies`
- `body`
- `response` (2xx union)
- `errors` (non-2xx union)

Generated code is built from Python `ast` and formatted with `ruff format`.

## What This Project Is

This project is a code generator that converts OpenAPI schemas into runtime-usable Pydantic models and can verify schema equivalence between:

- normalized source schemas from OpenAPI, and
- `model_json_schema()` emitted by generated Pydantic models.

It is focused on endpoint-scoped output (not reproducing the full OpenAPI document).

## Scope and Current Behavior

- Supports OpenAPI `3.x` (rejects `<3.0`).
- Input format: YAML OpenAPI documents.
- Validates input using `openapi-python-client` schema models.
- Resolves local refs (`#/...`) recursively.
- Rejects writing into an existing output directory.
- Optional verification mode reports schema mismatches and exits non-zero when mismatches are found.
- Uses hybrid endpoint naming:
  - use `operationId` when present and unique
  - fallback to path-based naming for missing/conflicting `operationId`
- Emits warning messages when `operationId` conflicts are detected.

## Requirements

- Python `>=3.12`
- `uv`

## Installation and Setup

Install dependencies:

```bash
uv sync --dev
```

Install pre-commit hooks:

```bash
uv run pre-commit install
```

## CLI Usage

Run via project script:

```bash
uv run openapi-to-pydantic-generator --input <spec.yaml> --output <out-dir> [--verify]
```

Run via module:

```bash
uv run python -m openapi_to_pydantic_generator --input <spec.yaml> --output <out-dir> [--verify]
```

Arguments:

- `--input`: path to OpenAPI YAML file
- `--output`: destination directory (must not already exist)
- `--verify`: enable schema equivalence verification

Example:

```bash
uv run openapi-to-pydantic-generator \
  --input tests/fixtures/openapi_specs/petstore.yaml \
  --output /tmp/petstore_models \
  --verify
```

### Exit Codes

- `0`: success (and no verification mismatches)
- `1`: generation succeeded but verification found mismatches
- `2`: CLI/IO/load/write error

## Output Layout

Given endpoint `<endpoint_name>` and method `<method>`, generated files are written under:

```text
<output>/
  models/
    __init__.py
    <endpoint_name>/
      __init__.py
      <method>/
        __init__.py
        url_params.py      # optional
        query_params.py    # optional
        headers.py         # optional
        cookies.py         # optional
        body.py            # optional
        response.py        # optional
        errors.py          # optional
```

Only sections with resolved schema content are emitted.

## Verification Mode

When `--verify` is used, the generator:

1. Imports generated models.
2. Computes each model's `model_json_schema()`.
3. Normalizes source and generated schemas.
4. Compares for semantic mismatch.

CLI output includes a summary:

- verified model count
- mismatch count
- mismatch details (path, expected, actual)

## Naming Rules

- `operationId` is sanitized to a Python-safe identifier.
- Path fallback format:
  - split on `/`
  - `{param}` becomes `by_<param>`
  - other segments are sanitized
  - segments joined with `__`
- If the final name is empty: `root`
- If it starts with a digit: prefix `x_`

## Python API

You can call the generator from Python:

```python
from pathlib import Path
from openapi_to_pydantic_generator import run_generation

run = run_generation(
    input_path=Path("tests/fixtures/openapi_specs/petstore.yaml"),
    output_dir=Path("/tmp/petstore_models"),
    verify=True,
)

print(run.result.output_dir)
if run.verification_report:
    print(run.verification_report.mismatch_count)
```

## Development Workflow

Run quality gates:

```bash
uv run ruff check .
uv run ruff format .
uv run mypy src tests
uv run pydoclint --style=google --check-return-types=False --check-arg-order=True --ignore-private-args=False --should-document-star-arguments=True --allow-init-docstring=True --skip-checking-short-docstrings=False --skip-checking-raises=True --check-class-attributes=False src
uv run pylint src tests
uv run pytest -q
```

Run all pre-commit hooks manually:

```bash
uv run pre-commit run --all-files
```

### Docstring Enforcement

The project enforces Google-style docstrings for source files under `src/` through `pydoclint` in pre-commit.

Current enforced behavior:

- Function and method arguments must be documented (`DOC101`/`DOC103`).
- Argument order in docstrings must match function signatures.
- Private arguments and `*args`/`**kwargs` must be documented when present.
- Short one-line docstrings are still checked (not skipped).

Current non-goals in this gate:

- Return type section matching is not enforced by `pydoclint` (`--check-return-types=False`).
- Raises sections are not enforced by `pydoclint` (`--skip-checking-raises=True`).
- Class attribute docstring checks are disabled (`--check-class-attributes=False`).

## Fixture-Driven Tests

Fixture specs are auto-discovered from:

- `tests/fixtures/openapi_specs/*.yaml`
- `tests/fixtures/openapi_specs/*.yml`

Adding a new fixture file automatically includes it in generation and verification tests.

## Limitations

- Only local references (`#/...`) are currently supported.
- Non-YAML OpenAPI input is not currently supported by CLI docs/workflow.
- The project targets schema/model generation, not full OpenAPI document reproduction.
