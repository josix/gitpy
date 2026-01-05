---
allowed-tools: Bash(inv*), Bash(poetry*), Bash(python*)
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
   inv env.init-dev
   ```

3. **Verify installation**:
   ```
   poetry --version
   poetry show
   ```

4. **Run quick validation**:
   ```
   ruff --version
   mypy --version
   pytest --version
   ```

5. **Report status**:
   - Python version
   - Installed packages
   - Any missing dependencies
