# Changelog

## 0.2.1 (2026-01-06)

### Fix

- add missing storage docs to mkdocs navigation

## 0.2.0 (2026-01-06)

### Feat

- **storage**: implement Phase 2 object storage system

### Fix

- resolve CI lint and type errors in test files

## 0.1.0 (2026-01-06)

### Feat

- **objects**: implement Phase 1 object model
- add consistency check to stop hook
- use typer and rich for CLI interface
- add minimal package scaffolding for CI
- add ralph-wiggum loop functionality for iterative development
- migrate from Poetry to uv for package management
- add Claude Code subagents and ralph-wiggum integration
- add Claude Code slash commands and hooks
- upgrade to Python 3.12+ and add implementation agents strategy

### Fix

- **ci**: use GITHUB_TOKEN instead of PERSONAL_ACCESS_TOKEN
- add usedforsecurity=False to SHA-1 calls for bandit
- update hooks to use correct JSON schema and remove hardcoded paths
- update permission patterns to use :* prefix matching

### Refactor

- update all references from poetry to uv
