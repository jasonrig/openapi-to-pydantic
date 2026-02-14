# Development Log

## 2026-02-14
- Started implementation of the generator pipeline.
- Chosen approach: build a general schema-to-model pipeline with AST code generation and verification from normalized ground truth.
- Alternative considered: fixture-targeted special cases for known examples; rejected because it does not generalize and conflicts with project requirements.
- Adjusted generated optional annotations to use `Optional[...]` and replaced broad fallback `Any` usage with `JsonValue` to align with design constraints.
- Verification strategy decision: for the first complete implementation pass, fixture verification tests assert successful end-to-end verification execution and structured mismatch reporting, rather than requiring zero mismatches on every large real-world fixture.
- Alternative considered: enforce zero mismatches on all current fixtures immediately. Rejected for now because it would require a substantially deeper schema feature implementation before shipping an end-to-end working pipeline.
- New requirement noted: generated AST output should be formatted with `ruff`, and `ruff` should be a runtime dependency (not dev-only). This will be implemented in a later chunk.
- Implemented generated-file formatting with `ruff` as part of `run_generation` and promoted `ruff` to a runtime dependency.
- Added converter-focused unit tests for:
- reserved-name field rewriting (no `BaseModel`/`RootModel` member shadowing),
- constraint keyword preservation (example: `maximum`),
- typed `additionalProperties`,
- and type-style guardrails in rendered source.
- Decision on `__pydantic_extra__` annotation:
- Chosen approach: keep `__pydantic_extra__` annotation in PEP 604 form for runtime evaluation stability, and preserve typed `additionalProperties` via `model_config.json_schema_extra` when the source uses schema-valued `additionalProperties`.
- Alternative considered: using richer `Optional`/`Annotated`-based value annotations in `__pydantic_extra__`; rejected because Pydantic resolves that special annotation in class namespace and raised `NameError` for typing symbols during model construction on real fixtures.
- Verification policy updated: fixture verification now fails on any mismatch (`mismatch_count > 0`) with detailed mismatch previews in test output.
- Alternative considered: keep verification non-blocking for large fixtures; rejected because acceptance requires zero semantic mismatches.
- Quality policy updated: removed broad pylint ignores and refactored complexity hotspots until `pylint` is clean without those suppressions.
- Refactor decision: extracted shared schema helpers into `schema_utils.py` (`deep_copy_json`, `is_object_schema`, `merge_all_of_schema`) to support reuse and reduce duplicate logic across normalization and conversion.
- Alternative considered: keep duplicate local helpers in each module; rejected because it increased lint complexity and maintenance cost.
- CLI policy update: migrated CLI from `argparse` to `click` after explicit requirement update.
- Error-handling policy update: removed CLI-side exception catching for generation/load paths; failures now propagate as runtime exceptions. Verification mismatches raise `VerificationMismatchError` with an informative message.
- Review marker disposition: all review markers were either implemented directly or superseded by explicit follow-up requirements.
