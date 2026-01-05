# CLAUDE.md

This file provides guidance for AI assistants working with this codebase.

## Project Overview

**gitpy** is an educational project that re-implements Git's core functionality in Python. The goal is to help developers understand Git's internals by building it from scratch.

- **Language**: Python 3.12+
- **Package Manager**: Poetry
- **Task Runner**: Invoke
- **Linting**: Ruff (replaces flake8, isort, black)
- **Type Checking**: mypy (strict mode)

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
ruff check .              # Lint code
ruff format .             # Format code
mypy gitpy tests          # Type check
```

### Security
```sh
inv secure                # Run security checks (bandit + pip-audit)
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

### Run gitpy
```sh
poetry run gitpy <command>   # Run gitpy CLI
```

## Project Structure

```
gitpy/
├── gitpy/                # Main package source code
│   ├── __init__.py
│   ├── cli.py            # CLI entry point
│   ├── repository.py     # Repository class
│   ├── objects/          # Git objects (blob, tree, commit, tag)
│   ├── storage/          # Object database and compression
│   ├── refs/             # References, branches, tags
│   ├── index/            # Staging area
│   ├── diff/             # Diff algorithm
│   └── commands/         # Plumbing and porcelain commands
├── tests/                # Test suite (pytest)
├── tasks/                # Invoke task definitions
├── docs/                 # MkDocs documentation
│   └── design/           # Design specifications
└── pyproject.toml        # Poetry config and tool settings
```

## Code Style

- **Formatter**: ruff format (line length: 88)
- **Linting**: ruff (pycodestyle, pyflakes, isort, bugbear, etc.)
- **Type Checking**: mypy (strict mode)
- **Python Version**: 3.12+ (use modern features)

### Python 3.12+ Features to Use

```python
# Use built-in generics (not typing.List, typing.Dict)
def process(items: list[str]) -> dict[str, int]: ...

# Use | for Optional (not Optional[X])
def get(key: str) -> str | None: ...

# Use Self for return types
from typing import Self
class Foo:
    def clone(self) -> Self: ...

# Use type aliases (PEP 695)
type SHA = str
type RefName = str

# Use pattern matching
match obj:
    case Blob(): ...
    case Tree(): ...

# Use dataclass slots
@dataclass(slots=True)
class Entry: ...
```

## Design Documents

See `docs/design/` for detailed specifications:

- `phase1_object_model.md` - Blob, Tree, Commit, Tag
- `phase2_object_storage.md` - Object database, compression
- `phase3_references.md` - HEAD, branches, tags, reflog
- `phase4_index.md` - Staging area, binary format
- `phase5_8_commands.md` - Diff, plumbing, porcelain
- `implementation_agents.md` - Agent-based implementation strategy
- `python312_features.md` - Modern Python features guide

## Implementation Agents

The codebase is designed to be implemented by specialized agents:

| Agent | Domain | Dependencies |
|-------|--------|--------------|
| 1. Object Model | blob, tree, commit, tag | None |
| 2. Storage | loose objects, compression | Agent 1 |
| 3. References | HEAD, branches, tags | Agents 1-2 |
| 4. Index | staging area | Agents 1-2 |
| 5. Diff | Myers algorithm | Agents 1-2 |
| 6. Plumbing | hash-object, cat-file, etc. | Agents 1-4 |
| 7. Porcelain | init, add, commit, etc. | Agents 1-6 |
| 8. Integration | testing, compatibility | All |

See `docs/design/implementation_agents.md` for full details.

## Commit Convention

This project uses [Conventional Commits](https://www.conventionalcommits.org/):

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
- Property testing: hypothesis

## Pre-commit Hooks

Pre-commit hooks are configured for automated checks. They run style, security, and test validations before commits and pushes.
