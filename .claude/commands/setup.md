---
allowed-tools: Bash(uv*), Bash(python*)
description: Initialize or verify development environment
---

Set up the gitpy development environment.

## Steps

1. **Check Python version** (must be 3.12+):
   ```
   python3 --version
   ```

2. **Initialize virtual environment and install dependencies**:
   ```
   uv sync --group dev
   ```

3. **Verify installation**:
   ```
   uv --version
   uv pip list
   ```

4. **Run quick validation**:
   ```
   uv run ruff --version
   uv run mypy --version
   uv run pytest --version
   ```

5. **Report status**:
   - Python version
   - Installed packages
   - Any missing dependencies
