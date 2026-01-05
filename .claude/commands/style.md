---
allowed-tools: Bash(ruff*), Bash(mypy*)
description: Format and lint Python code
argument-hint: [--fix] [path]
---

Check and format Python code in gitpy.

Arguments: $ARGUMENTS

Steps:
1. Format code with ruff:
   ```
   ruff format gitpy tests
   ```

2. Check linting (auto-fix if `--fix` specified):
   ```
   ruff check gitpy tests --fix
   ```

3. Run type checking:
   ```
   mypy gitpy tests
   ```

Report any issues found and suggest fixes.
