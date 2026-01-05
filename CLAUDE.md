# CLAUDE.md

This file provides guidance for AI assistants working with this codebase.

## Project Overview

**gitpy** is an educational project that re-implements Git's core functionality in Python. The goal is to help developers understand Git's internals by building it from scratch.

- **Language**: Python 3.12+
- **Package Manager**: uv
- **Task Runner**: Invoke
- **Linting**: Ruff (replaces flake8, isort, black)
- **Type Checking**: mypy (strict mode)

## Common Commands

### Environment Setup
```sh
uv sync --group dev       # Create venv and install all dependencies
uv run inv env.init-dev   # Or use invoke task
```

### Testing
```sh
uv run pytest             # Run all tests
uv run pytest --cov       # Run tests with coverage report
uv run inv test           # Or use invoke task
```

### Code Style
```sh
uv run ruff check .       # Lint code
uv run ruff format .      # Format code
uv run mypy gitpy tests   # Type check
```

### Security
```sh
uv run bandit -r gitpy    # Security static analysis
uv run pip-audit          # Dependency vulnerability check
```

### Git/Commits
```sh
uv run cz commit          # Create a conventional commit
```

### Documentation
```sh
uv run mkdocs build       # Build documentation
uv run mkdocs serve       # Serve documentation locally
```

### Run gitpy
```sh
uv run gitpy <command>    # Run gitpy CLI
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
└── pyproject.toml        # Project config (PEP 621) and tool settings
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

---

## Claude Code Integration

### Slash Commands

Custom commands available in this project (`.claude/commands/`):

| Command | Description |
|---------|-------------|
| `/test [--cov] [pattern]` | Run pytest tests with optional coverage |
| `/style [--fix]` | Format and lint code with ruff/mypy |
| `/implement <phase>` | Implement a component from design specs |
| `/design <phase>` | View design specification for a phase |
| `/setup` | Initialize development environment |
| `/secure` | Run security checks (bandit, pip-audit) |
| `/verify-git <component>` | Verify compatibility with real Git |

### Hooks

Configured in `.claude/settings.json`:

- **PreToolUse (Write/Edit)**: Reminds to use Python 3.12+ features
- **PostToolUse (Write/Edit)**: Auto-formats Python files with ruff
- **Stop**: Runs session summary (uncommitted changes, style issues)

### Permissions

Pre-approved tool patterns:
- `Bash(uv *)` - Package management
- `Bash(inv *)` - Invoke tasks
- `Bash(pytest *)` - Testing
- `Bash(ruff *)` - Linting/formatting
- `Bash(mypy *)` - Type checking
- `Bash(git *)` - Version control

### Workflow Tips

1. **Start a session**: Run `/setup` to verify environment
2. **Implement a feature**: Use `/implement-loop <phase>` for automated implementation
3. **Check your work**: Run `/test` and `/style`
4. **Before committing**: Run `/secure` for security check
5. **Verify Git compat**: Use `/verify-loop` to test against real Git

### Subagents

Specialized subagents in `.claude/agents/` for different tasks:

| Agent | Purpose | When to Use |
|-------|---------|-------------|
| `code-reviewer` | Python 3.12+ and Git internals review | After writing/modifying code |
| `test-runner` | Run tests, analyze failures, iterate | After code changes |
| `implementer` | Build components from design specs | For new features |
| `git-verifier` | Verification loop for Git compatibility | After implementing features |
| `debugger` | Debug failing tests and errors | When something breaks |

**Usage**: Subagents are invoked automatically via the Task tool when relevant, or you can request them explicitly (e.g., "run the code-reviewer agent").

### Ralph-Wiggum Integration

This project uses the ralph-wiggum plugin for automated verification loops:

| Command | Description |
|---------|-------------|
| `/implement-loop <phase>` | Implement a phase with ralph-wiggum loop until complete |
| `/verify-loop [component]` | Verify Git compatibility in a loop until all pass |

**How it works**:
1. Ralph-wiggum runs an iterative loop with a completion promise
2. Each iteration runs verification/implementation steps
3. Loop continues until success criteria met (e.g., all tests pass)
4. Outputs `<promise>VERIFIED</promise>` or `<promise>PHASE_COMPLETE</promise>` when done

**Reference Hashes** (must match real Git):
- Empty blob: `e69de29bb2d1d6434b8b29ae775ad8c2e48c5391`
- Empty tree: `4b825dc642cb6eb9a060e54bf8d69288fbee4904`
- `"hello\n"` blob: `ce013625030ba8dba906f756967f9e9ca394464a`

### Quick Reference

```
# Implement Phase 1 (Object Model) with verification loop
/implement-loop 1

# Verify blob implementation against real Git
/verify-loop blob

# Run code review after changes
# (Subagent invoked automatically or request: "review this code")

# Debug a failing test
# (Request: "debug the test_blob_hash test")
```
