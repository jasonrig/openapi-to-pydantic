# Development Plan

## Purpose
Track design decisions made during initial discussions.

## Baseline Constraints (from SPEC)
- CLI: `--input`, `--output`, optional `--verify`.
- Output layout rooted at `models/` with endpoint/method subpackages and optional section files.
- Pydantic v2 models (`BaseModel` and `RootModel[T]`), no `Any`/`object` unless the schema is truly unspecified.
- Schema equivalence verification against `model_json_schema()` after normalization.
- Refuse to write into an existing output directory.

## Reference Material
- OpenAPI specification docs available locally under `oai-spec/` (versions 1.2 through 3.2.0, including editor drafts).

## Design Decisions
- Target OpenAPI v3+ only (3.0.x, 3.1.x, 3.2.x). Earlier versions are out of scope.
- Endpoint naming: prefer `operationId` when present and unique; otherwise derive from path with segment separators preserved as `__` and path params as `by_<param>` (e.g., `/users/{user_id}/posts` -> `users__by_user_id__posts`).
- Endpoint naming sanitization:
- Split path on `/` into segments (ignore leading empty).
- For `{param}` segments, use `by_<param>`.
- For other segments, lowercase, replace non‑alphanumerics with `_`, collapse multiple `_`, trim `_` ends.
- Join segments with `__`.
- If result starts with a digit, prefix `x_`; if empty, use `root`.
- Endpoint naming conflicts: emit a warning and fall back to path-based naming for conflicting operations only (hybrid naming).
- Responses: emit per-status models plus top-level unions for OK responses and for error responses.
- Schema parsing: use the `referencing` package for `$ref` resolution (tentative).
- Schema equivalence compares per-schema JSON Schema output (not the full OpenAPI document).
- Preserve documentation metadata in generated models so Pydantic JSON Schema can match OpenAPI schema docs as closely as possible.
- Encode `default` values as actual Pydantic field defaults (not just schema metadata).
- Documentation keywords to match include `example`, `examples`, `xml`, `externalDocs`, `contentMediaType`, and `contentEncoding`; `$comment` is excluded.
- Documentation mapping: schema-level `description` becomes the model class docstring; property-level docs use `Field(...)` metadata.
- Documentation mapping: schema-level `title` is set via `model_config` so it appears as JSON Schema `title`.
- Nullability semantics: generated models must reject `null` unless the schema explicitly allows it (via `nullable: true` in 3.0.x or `type: ["null", ...]` / equivalent in 3.1+).
- `additionalProperties` defaults to `true` when omitted; generated models should allow additional properties unless explicitly `false`.
- Schema features: must support `oneOf`, `anyOf`, `allOf`, and `discriminator` from the first pass with robust Pydantic representations.
- Correctness goal: any compliant OpenAPI v3+ payload should marshal into the generated Pydantic models.
- `$ref` handling: resolve and inline all references (endpoint-scoped models may duplicate shared schemas).
- Discriminator handling: enforce discriminator as required and generate discriminated unions; reject payloads missing discriminator.
- Code generation: emit Python code exclusively via the `ast` module (no string templating).
- Pydantic usage: no hacks or monkeypatching to force schema output.
- Verification ground truth: use a third-party library (e.g., `referencing` or `jsonschema`) to produce the canonical schema used for comparison with Pydantic output.
- Verification tooling: use `jsonschema` for ground-truth schema handling (it depends on `referencing`).
- Version handling policy: treat 3.0.x and 3.1+ differently where semantics differ (notably nullability, schema keyword availability, and JSON Schema dialect). Normalize each version to its intended semantics before comparison.
- Testing approach: prioritize fixture-driven tests that assert generated code structure and schema equivalence, allowing iterative IR refactors with confidence.
- Fixture discovery: tests should automatically pick up any `.yaml`/`.yml` under `tests/fixtures/openapi_specs/` without assuming any single fixture is canonical.
- Generalization: avoid special-case branches for specific fixtures; fixes must generalize.
- Quality gates: ruff, mypy, and pylint must be clean; pre-commit hooks are mandatory and not bypassed.
- Version control: commit frequently and keep commits focused.

## Test Strategy (Initial)
- Unit tests for schema-to-IR conversion and normalization utilities.
- Integration tests per fixture spec that:
- Generate code into a temp dir.
- Import generated models and compare `model_json_schema()` to normalized ground-truth schemas.
- Assert file layout and presence/absence of section files per endpoint.

## IR Sketch (High-Level Only)
- Core types: object model, root model, array, union, literal/enum, scalar.
- Each field carries: name, alias, required/optional, default, and doc metadata.
- Discriminator support represented as a tagged union with required discriminator field.

## Open Questions
- Schema normalization: whether any additional tolerances are needed beyond the approved checklist.

## Normalization Checklist (Approved)

### General
- Compare per-schema JSON Schema only (not full OpenAPI documents).
- Canonicalize object key ordering for comparison (stable JSON serialization).
- Sort arrays where ordering is not semantically significant: `required`, `enum`, and branches for `anyOf`/`oneOf`/`allOf`.
- Preserve and compare documentation keywords: `title`, `description`, `example`, `examples`, `xml`, `externalDocs`, `contentMediaType`, `contentEncoding`. Exclude `$comment`.
- Preserve validation keywords exactly; no dropping of validation-relevant fields.
- Normalize missing `additionalProperties` to explicit `true`.

### OpenAPI 3.0.x
- Convert `nullable: true` to JSON Schema null allowance for comparison (add `"null"` to `type`, or wrap as `anyOf` with a `{ "type": "null" }` schema when `type` is absent).
- Treat `type` string vs single-item type array as equivalent.
- Preserve schema-level `example`.
- Enforce OAS 3.0 keyword subset (extra JSON Schema keywords are unsupported inputs).

### OpenAPI 3.1+
- Use JSON Schema 2020-12 semantics (allow type arrays, boolean schemas).
- Honor `$schema` or `jsonSchemaDialect` if present.
- Preserve deprecated `example` if present and `examples` (plural) as primary.

### Comparison Tolerance
- Allow differences only when they are syntactic forms of the same semantics (e.g., `nullable` vs `type: ["null", ...]`, ordering).
- Do not allow differences that change validation behavior or documentation fields.
