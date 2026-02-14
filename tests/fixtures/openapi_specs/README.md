# OpenAPI Fixture Specs

Drop additional OpenAPI YAML files in this directory to include them in automated schema verification.

Accepted file extensions:
- `.yaml`
- `.yml`

Test behavior:
- `tests/test_openapi_to_pydantic_ast.py` always validates project-root `gw-api-spec.yaml` and `petstore.yaml`.
- It also auto-discovers every YAML file in this directory and validates each one with the same generation + schema equivalence checks.
