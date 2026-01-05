# CLAUDE.md

This file provides guidance for AI assistants working with this codebase.

## Project Overview

**gitpy** is an educational project that re-implements Git's core functionality in Python. The goal is to help developers understand Git's internals by building it from scratch.

- **Language**: Python 3.7+
- **Package Manager**: Poetry
- **Task Runner**: Invoke

## Common Commands

### Environment Setup
```sh
inv env.init-dev          # Create virtual environment and install dependencies
```

### Testing
```sh
inv test                  # Run all tests
inv test.cov              # Run tests with coverage report
```

### Code Style
```sh
inv style.reformat        # Auto-format code (black + isort)
inv style                 # Run all style checks (flake8, mypy)
inv style.pylint          # Run pylint (optional, not all warnings need fixing)
```

### Security
```sh
inv secure                # Run security checks (bandit + safety)
```

### Git/Commits
```sh
inv git.commit            # Create a conventional commit
```

### Documentation
```sh
inv doc.build             # Build documentation
inv doc.serve             # Serve documentation locally
```

## Project Structure

```
gitpy/
├── gitpy/                # Main package source code
│   ├── __init__.py
│   └── gitpy.py          # Core implementation
├── tests/                # Test suite (pytest)
│   └── test_gitpy.py
├── tasks/                # Invoke task definitions
├── docs/                 # MkDocs documentation
└── pyproject.toml        # Poetry config and tool settings
```

## Code Style

- **Formatter**: black (line length: 88)
- **Import Sorting**: isort (black profile)
- **Linting**: flake8, mypy, pylint
- **Type Hints**: Encouraged, checked by mypy

## Commit Convention

This project uses [Conventional Commits](https://www.conventionalcommits.org/). Use `inv git.commit` for guided commit creation, or follow the format:

```
type(scope): description

[optional body]
```

Types: `feat`, `fix`, `docs`, `style`, `refactor`, `test`, `chore`

## Testing

- Framework: pytest
- Location: `tests/` directory
- Run with: `inv test`
- Coverage: `inv test.cov`

## Pre-commit Hooks

Pre-commit hooks are configured for automated checks. They run style, security, and test validations before commits and pushes.
