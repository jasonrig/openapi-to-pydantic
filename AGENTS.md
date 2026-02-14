# AGENTS.md

## Guiding Principles
- Prefer clarity and correctness over cleverness.
- Keep changes small, focused, and easy to review.
- Preserve existing behavior unless the task explicitly requires change.
- Optimize for maintainability and readable code.
- Make decisions explicit; document assumptions when needed.

## Code Style and Structure
- Write straightforward, human-readable code.
- Use descriptive names for functions, variables, and modules.
- Keep functions short and single-purpose.
- Avoid unnecessary abstraction.
- Do not duplicate logic when a small shared helper suffices.

## Typing and Mypy
- All new code should be type-annotated.
- Avoid using `Any` or `object` unless the input truly has no known shape.
- Prefer `Optional[T]` over `T | None` if the project convention requires it.
- Run `mypy` on relevant code paths; fix errors rather than silencing them.
- Do not ignore or suppress type errors unless there is a clear, documented justification.

## Formatting and Linting
- Use `ruff format` for formatting.
- Use `ruff` for linting whenever possible.
- Use `pylint` to catch issues not covered by `ruff`.
- Keep imports clean and ordered; remove unused imports.
- Prefer explicitness over implicit behavior when it improves readability.

## Testing
- Add or update tests when behavior changes.
- Keep tests deterministic and fast.
- Prefer `pytest` for new tests.
- Tests should verify externally observable behavior, not implementation details.
- Avoid brittle or overly coupled tests.

## Dependency Management and `uv`
- Use `uv` for all dependency operations and tool execution.
- Add runtime dependencies with `uv add`.
- Add development dependencies with `uv add --dev`.
- Run tools through `uv run` to ensure consistent environments.
- Do not edit `uv.lock` manually.
- Never use `pip` or `uv pip`.

## Documentation
- Keep documentation accurate and up to date with behavior.
- Document non-obvious decisions or tradeoffs.
- Avoid documenting implementation details that are likely to change.

## Git and Change Management
- Keep commits focused and logically grouped.
- Commit changes progressively to allow for easy rollback.
- Do not mix refactors with behavior changes unless necessary.
- Avoid rewriting history unless explicitly requested.
- Commit frequently in small logical chunks while implementing.
- Once a stable checkpoint exists, commit before starting the next logical unit of work.
- Avoid carrying large uncommitted deltas across multiple unrelated tasks.

## Delivery Workflow
- Use the test harness as the primary driver for implementation.
- Prefer adding or tightening tests first, then implement only what is needed to satisfy failing tests.
- Keep failure diagnostics in tests actionable (include expected/actual context for schema mismatches).
- Prefer harness-driven debugging over one-off custom scripts; use ad-hoc scripts only when the harness cannot provide the needed signal.

## Execution Enforcement
- Commit checkpoint rule: commit before starting the next logical unit of work once the current unit reaches a stable checkpoint.
- Progress status rule: every substantial progress update must include current goal, current gate result, and latest commit hash.
- Dirty tree limit rule: if more than 5 files are modified, stop and either commit a stable chunk or explicitly report the blocker and recovery plan.
- Completion rule: do not claim completion unless all gates pass in the working tree:
  - `uv run ruff check .`
  - `uv run mypy src tests`
  - `uv run pylint src tests`
  - `uv run pytest -q`
- Audit response rule: on request, immediately provide `git status --short` and `git log --oneline -n 5`.

## Generated Artifacts
- Do not manually edit generated files.
- If changes are needed, update the generator or source of truth.
- Clearly separate generated output from source code.

## Error Handling
- Handle errors explicitly where failures are expected.
- Avoid silent failure.
- Prefer clear error messages that help users resolve issues.

## Security and Safety
- Validate inputs when appropriate.
- Avoid unsafe operations in build or test scripts.
- Do not introduce destructive operations unless explicitly required.
