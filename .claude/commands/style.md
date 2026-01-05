---
allowed-tools: Bash(uv run ruff*), Bash(uv run mypy*)
description: Format and lint Python code
argument-hint: [--fix] [path]
---

Check and format Python code in gitpy.

Arguments: $ARGUMENTS

Steps:
1. Format code with ruff:
   ```
   uv run ruff format gitpy tests
   ```

2. Check linting (auto-fix if `--fix` specified):
   ```
   uv run ruff check gitpy tests --fix
   ```

3. Run type checking:
   ```
   uv run mypy gitpy tests
   ```

Report any issues found and suggest fixes.
