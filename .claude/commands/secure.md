---
allowed-tools: Bash(uv run bandit*), Bash(uv run pip-audit*)
description: Run security checks on the codebase
---

Run security analysis on gitpy.

## Steps

1. **Run bandit** (static security analyzer):
   ```
   uv run bandit -r gitpy -ll
   ```

2. **Run pip-audit** (dependency vulnerability check):
   ```
   uv run pip-audit
   ```

## Report

- Security issues found (severity levels)
- Vulnerable dependencies
- Recommended fixes
