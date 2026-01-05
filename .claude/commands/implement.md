---
allowed-tools: Read, Write, Edit, Glob, Grep, Bash(uv run pytest*), Bash(uv run ruff*), Bash(uv run mypy*)
description: Implement a phase or component from design docs
argument-hint: <phase_number|component_name>
---

Implement a gitpy component based on the design specifications.

Argument: $ARGUMENTS

## Process

1. **Read the design spec** from `docs/design/`:
   - Phase 1: `phase1_object_model.md` (blob, tree, commit, tag)
   - Phase 2: `phase2_object_storage.md` (loose objects, compression)
   - Phase 3: `phase3_references.md` (HEAD, branches, tags)
   - Phase 4: `phase4_index.md` (staging area)
   - Phase 5-8: `phase5_8_commands.md` (diff, commands)

2. **Check Python 3.12+ features** in `docs/design/python312_features.md`

3. **Implement the component**:
   - Follow the spec exactly
   - Use modern Python 3.12+ syntax (type aliases, pattern matching, Self, slots)
   - Add docstrings to all public APIs
   - Create corresponding test file in `tests/`

4. **Run validation**:
   - Format: `uv run ruff format <files>`
   - Lint: `uv run ruff check <files>`
   - Type check: `uv run mypy <files>`
   - Tests: `uv run pytest tests/<test_file> -v`

5. **Report completion status** with:
   - Files created/modified
   - Test results
   - Any deviations from spec

## Example Usage

- `/implement 1` - Implement Phase 1 (Object Model)
- `/implement blob` - Implement just the Blob class
- `/implement storage` - Implement object storage
