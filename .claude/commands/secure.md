---
allowed-tools: Bash(inv secure*), Bash(bandit*), Bash(pip-audit*)
description: Run security checks on the codebase
---

Run security analysis on gitpy.

## Steps

1. **Run bandit** (static security analyzer):
   ```
   bandit -r gitpy -ll
   ```

2. **Run pip-audit** (dependency vulnerability check):
   ```
   pip-audit
   ```

3. **Or use invoke task**:
   ```
   inv secure
   ```

## Report

- Security issues found (severity levels)
- Vulnerable dependencies
- Recommended fixes
