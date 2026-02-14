# OpenAPI to Pydantic Generator Specification

## Purpose
Provide a deterministic generator that turns an OpenAPI document into endpoint-scoped Pydantic model packages, plus verification that the generated models' JSON Schemas are equivalent to the OpenAPI schemas.

## Scope
The project covers:
- Parsing OpenAPI YAML documents.
- Generating Pydantic model classes (BaseModel and RootModel) per endpoint and HTTP method.
- Organizing generated code into a stable, predictable package layout.
- Verifying JSON Schema equivalence between OpenAPI source schemas and generated Pydantic models.
- Running automated tests against a fixtures directory of OpenAPI documents.

The project does not cover:
- HTTP client implementation.
- Runtime request execution.
- Server-side request handling.

## Inputs

### 1) Generator CLI
- `--input` (required): Path to an OpenAPI YAML file.
- `--output` (required): Target directory for generated Python packages.
- `--verify` (optional): Flag to run schema equivalence verification.

### 2) Test Fixtures
- One or more `.yaml` or `.yml` OpenAPI documents placed in `tests/fixtures/openapi_specs/`.

## Outputs

### 1) Generated Packages
Generated code must be organized under the output directory as:

```
models/
  <endpoint_name>/
    <http_method>/
      __init__.py
      url_params.py       (optional)
      query_params.py     (optional)
      headers.py          (optional)
      cookies.py          (optional)
      body.py             (optional)
      response.py         (optional)
      errors.py           (optional)
  __init__.py
```

Where:
- `<endpoint_name>` is a sanitized, stable identifier derived from the OpenAPI path.
- `<http_method>` is the lowercase HTTP method.
- Each section file is only emitted when the endpoint actually has content for that section.
- Models are endpoint-scoped; duplication across endpoints is allowed and acceptable.

### 2) Generated Model Content
Each generated section file contains:
- Pydantic model classes for that section.
- `BaseModel` classes for object schemas.
- `RootModel[T]` classes for root schemas, with the root type expressed as a type parameter.
- Proper aliases where API field names differ from safe Python identifiers.
- No use of `Any` or `object` unless the OpenAPI schema is not further specified.

### 3) Verification Output
When verification runs:
- A count of verified models and mismatches is produced.
- If mismatches exist, details include the endpoint/model, the mismatch path, and expected vs actual snippets.

## Behavior Requirements

### OpenAPI Parsing
- Input is YAML and must be parsed via a YAML parser.
- The OpenAPI document is treated as immutable; the generator does not modify the source file.

### Schema Handling
- URL parameters, query parameters, headers, cookies, request bodies, success responses, and error responses are all supported.
- Nullable handling must match OpenAPI semantics.
- `additionalProperties` behavior must match the OpenAPI schema defaults and explicit values.
- JSON Schema keywords that affect validation must be preserved in the generated schema output.

### Naming and Conflicts
- Python identifiers must be valid and stable.
- Any name that would conflict with Pydantic `BaseModel` attributes must be rewritten, preserving the original API name via alias.

### Verification
- Verification compares the OpenAPI schema to the JSON Schema produced by Pydantic's `model_json_schema()`.
- Equivalence is structural and exact after normalization.
- No custom bypass or substitution of the OpenAPI schema is allowed.

### Safety
- Generation refuses to write into an output directory that already exists.
- Generated output directories are created only at a new, empty location.

## Acceptance Criteria

### Functional
1. Given a valid OpenAPI YAML document, the generator produces a complete, endpoint-scoped model package tree matching the specified layout.
2. Each endpoint/method contains only the section files relevant to that endpoint.
3. All model schemas produced by Pydantic are structurally equivalent to the OpenAPI source schemas.
4. No generated field name conflicts with Pydantic `BaseModel` members; aliases preserve the original API names.
5. Root models are emitted using `RootModel[T]` with `Optional[T]` where applicable.

### Verification
6. `uv run pytest -q` passes for all fixture specs under `tests/fixtures/openapi_specs/`.

### Usability
7. Running the CLI without required arguments produces a help screen.
8. The generator accepts any OpenAPI YAML document and produces output without modifying the input.

### Non-Goals
10. No HTTP client code is generated or required.

