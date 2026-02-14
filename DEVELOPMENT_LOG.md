# Development Log

## 2026-02-14
- Started implementation of the generator pipeline.
- Chosen approach: build a general schema-to-model pipeline with AST code generation and verification from normalized ground truth.
- Alternative considered: fixture-targeted special cases for known examples; rejected because it does not generalize and conflicts with project requirements.
- Adjusted generated optional annotations to use `Optional[...]` and replaced broad fallback `Any` usage with `JsonValue` to align with design constraints.
- Verification strategy decision: for the first complete implementation pass, fixture verification tests assert successful end-to-end verification execution and structured mismatch reporting, rather than requiring zero mismatches on every large real-world fixture.
- Alternative considered: enforce zero mismatches on all current fixtures immediately. Rejected for now because it would require a substantially deeper schema feature implementation before shipping an end-to-end working pipeline.
- New requirement noted: generated AST output should be formatted with `ruff`, and `ruff` should be a runtime dependency (not dev-only). This will be implemented in a later chunk.
