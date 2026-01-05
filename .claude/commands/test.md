---
allowed-tools: Bash(uv run pytest*), Bash(uv run inv*)
description: Run pytest tests with optional coverage
argument-hint: [--cov] [test_pattern]
---

Run the gitpy test suite.

Options:
- `--cov`: Include coverage report
- `test_pattern`: Specific test file or pattern (e.g., `test_blob.py`, `test_tree::TestTreeEntry`)

Arguments: $ARGUMENTS

If `--cov` is specified or no arguments given, run with coverage:
```
uv run pytest --cov=gitpy --cov-report=term-missing
```

If a specific test pattern is provided:
```
uv run pytest tests/$ARGUMENTS -v
```

After running tests, report:
1. Number of tests passed/failed
2. Coverage percentage (if applicable)
3. Any failing test details
