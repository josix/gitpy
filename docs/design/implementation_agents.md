# Implementation Agents Strategy

This document defines specialized agents for implementing gitpy, enabling parallel development with clear boundaries and responsibilities.

## Overview

The implementation is divided into independent workstreams, each handled by a specialized agent with domain expertise. This enables:

- **Parallel development** of independent components
- **Clear ownership** and responsibility boundaries
- **Focused expertise** on specific Git internals
- **Testable deliverables** at each stage

---

## Agent Definitions

### Agent 1: Object Model Agent

**Domain**: Git object types and serialization

**Responsibilities**:
- Implement `Blob`, `Tree`, `Commit`, `Tag` classes
- SHA-1 hashing with proper header format
- Binary serialization/deserialization
- Tree entry sorting and binary SHA handling

**Files to Create**:
```
gitpy/
└── objects/
    ├── __init__.py
    ├── base.py      # GitObject ABC
    ├── blob.py      # Blob implementation
    ├── tree.py      # Tree, TreeEntry
    ├── commit.py    # Commit, Identity
    └── tag.py       # Tag implementation
tests/
└── objects/
    ├── test_blob.py
    ├── test_tree.py
    ├── test_commit.py
    └── test_tag.py
```

**Dependencies**: None (foundation layer)

**Acceptance Criteria**:
- [ ] All objects serialize/deserialize correctly
- [ ] SHA-1 matches Git for identical content
- [ ] Empty blob hash: `e69de29bb2d1d6434b8b29ae775ad8c2e48c5391`
- [ ] Empty tree hash: `4b825dc642cb6eb9a060e54bf8d69288fbee4904`
- [ ] 100% test coverage

**Estimated Complexity**: Medium

---

### Agent 2: Storage Agent

**Domain**: Object persistence and compression

**Responsibilities**:
- Loose object storage with zlib compression
- Object database with read/write operations
- Short SHA resolution
- Repository initialization

**Files to Create**:
```
gitpy/
├── storage/
│   ├── __init__.py
│   ├── loose.py        # LooseObjectStore
│   ├── database.py     # ObjectDatabase
│   └── compression.py  # Zlib utilities
└── repository.py       # Repository class
tests/
└── storage/
    ├── test_loose.py
    ├── test_database.py
    └── test_repository.py
```

**Dependencies**: Agent 1 (Object Model)

**Acceptance Criteria**:
- [ ] Objects stored in `.git/objects/XX/YYY...`
- [ ] Zlib compression matches Git format
- [ ] Atomic writes with temp files
- [ ] Short SHA resolution (minimum 4 chars)
- [ ] Repository.init() creates valid structure
- [ ] Git can read gitpy objects and vice versa

**Estimated Complexity**: Medium

---

### Agent 3: References Agent

**Domain**: Branches, tags, HEAD management

**Responsibilities**:
- Reference reading/writing
- Symbolic reference resolution
- HEAD management (attached/detached)
- Branch and tag operations
- Packed refs support
- Reflog

**Files to Create**:
```
gitpy/
└── refs/
    ├── __init__.py
    ├── manager.py     # RefManager
    ├── head.py        # HeadManager
    ├── branch.py      # BranchManager
    ├── tag.py         # TagManager
    ├── reflog.py      # Reflog
    └── revision.py    # RevisionParser (^, ~, @{})
tests/
└── refs/
    ├── test_manager.py
    ├── test_head.py
    ├── test_branch.py
    └── test_revision.py
```

**Dependencies**: Agent 1, Agent 2

**Acceptance Criteria**:
- [ ] HEAD attached/detached states work
- [ ] Branch create/delete/rename operations
- [ ] Symbolic refs resolve correctly
- [ ] Revision expressions (HEAD^, main~3) parse
- [ ] Packed refs are readable
- [ ] Reflog entries recorded

**Estimated Complexity**: High

---

### Agent 4: Index Agent

**Domain**: Staging area and working directory

**Responsibilities**:
- Binary index format parsing/writing
- Index entry with stat caching
- read_tree / write_tree operations
- Working directory comparison
- Merge conflict stages

**Files to Create**:
```
gitpy/
└── index/
    ├── __init__.py
    ├── entry.py       # IndexEntry
    ├── index.py       # Index, IndexFile
    └── operations.py  # read_tree, write_tree, status
tests/
└── index/
    ├── test_entry.py
    ├── test_index.py
    └── test_operations.py
```

**Dependencies**: Agent 1, Agent 2

**Acceptance Criteria**:
- [ ] Parse Git index file (version 2)
- [ ] Write Git-compatible index
- [ ] Checksum validation
- [ ] Atomic writes with lock file
- [ ] read_tree populates index from tree
- [ ] write_tree creates tree from index
- [ ] Status detection (modified, added, deleted)

**Estimated Complexity**: High

---

### Agent 5: Diff Agent

**Domain**: Change detection and formatting

**Responsibilities**:
- Myers diff algorithm
- Unified diff format output
- Tree diff (comparing directories)
- Index diff operations

**Files to Create**:
```
gitpy/
└── diff/
    ├── __init__.py
    ├── myers.py       # Myers algorithm
    ├── unified.py     # Unified diff format
    └── tree.py        # Tree comparison
tests/
└── diff/
    ├── test_myers.py
    ├── test_unified.py
    └── test_tree.py
```

**Dependencies**: Agent 1, Agent 2

**Acceptance Criteria**:
- [ ] Myers produces minimal edit distance
- [ ] Unified diff format matches Git
- [ ] Tree diff detects add/modify/delete
- [ ] Context lines configurable
- [ ] Binary files handled gracefully

**Estimated Complexity**: Medium

---

### Agent 6: Plumbing Commands Agent

**Domain**: Low-level Git commands

**Responsibilities**:
- hash-object, cat-file
- ls-tree, ls-files
- write-tree, read-tree
- commit-tree
- update-ref, symbolic-ref

**Files to Create**:
```
gitpy/
└── commands/
    ├── __init__.py
    ├── base.py
    └── plumbing/
        ├── __init__.py
        ├── hash_object.py
        ├── cat_file.py
        ├── ls_tree.py
        ├── write_tree.py
        ├── commit_tree.py
        └── update_ref.py
tests/
└── commands/
    └── plumbing/
        ├── test_hash_object.py
        ├── test_cat_file.py
        └── ...
```

**Dependencies**: Agents 1-4

**Acceptance Criteria**:
- [ ] All commands match Git behavior
- [ ] Exit codes correct
- [ ] Error messages helpful
- [ ] Argument parsing complete

**Estimated Complexity**: Medium

---

### Agent 7: Porcelain Commands Agent

**Domain**: User-facing Git commands

**Responsibilities**:
- init, add, commit, status
- log, show, diff
- branch, checkout, switch
- Command-line interface

**Files to Create**:
```
gitpy/
├── cli.py
└── commands/
    └── porcelain/
        ├── __init__.py
        ├── init.py
        ├── add.py
        ├── commit.py
        ├── status.py
        ├── log.py
        ├── diff.py
        ├── branch.py
        └── checkout.py
tests/
└── commands/
    └── porcelain/
        ├── test_init.py
        ├── test_add.py
        └── ...
```

**Dependencies**: Agents 1-6

**Acceptance Criteria**:
- [ ] Basic workflow works: init → add → commit
- [ ] Status shows correct state
- [ ] Log displays history
- [ ] Branch operations functional
- [ ] CLI entry point works

**Estimated Complexity**: High

---

### Agent 8: Integration & QA Agent

**Domain**: Testing, compatibility, documentation

**Responsibilities**:
- End-to-end integration tests
- Git compatibility verification
- Performance benchmarks
- Documentation updates
- CI/CD pipeline

**Files to Create**:
```
tests/
├── integration/
│   ├── test_workflow.py
│   ├── test_compatibility.py
│   └── test_edge_cases.py
├── conftest.py
.github/
└── workflows/
    └── ci.yaml
```

**Dependencies**: All agents

**Acceptance Criteria**:
- [ ] Full workflow tests pass
- [ ] Git can use gitpy repos
- [ ] gitpy can use Git repos
- [ ] All edge cases handled
- [ ] CI passes on all PRs

**Estimated Complexity**: Medium

---

## Agent Execution Order

```
Phase 1 (Foundation):
┌─────────────────────┐
│  Agent 1: Objects   │
└─────────────────────┘
          │
          ▼
Phase 2 (Core Infrastructure):
┌─────────────────────┐
│  Agent 2: Storage   │
└─────────────────────┘
          │
          ▼
Phase 3 (Parallel):
┌──────────────┐  ┌──────────────┐  ┌──────────────┐
│ Agent 3:     │  │ Agent 4:     │  │ Agent 5:     │
│ References   │  │ Index        │  │ Diff         │
└──────────────┘  └──────────────┘  └──────────────┘
          │              │                │
          └──────────────┼────────────────┘
                         ▼
Phase 4 (Commands):
┌─────────────────────────────────────────────────┐
│              Agent 6: Plumbing                  │
└─────────────────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────┐
│              Agent 7: Porcelain                 │
└─────────────────────────────────────────────────┘
                         │
                         ▼
Phase 5 (Verification):
┌─────────────────────────────────────────────────┐
│           Agent 8: Integration & QA             │
└─────────────────────────────────────────────────┘
```

---

## Parallel Execution Opportunities

### Can Run in Parallel

| Agent A | Agent B | Notes |
|---------|---------|-------|
| Agent 3 (Refs) | Agent 4 (Index) | Independent subsystems |
| Agent 3 (Refs) | Agent 5 (Diff) | No dependencies |
| Agent 4 (Index) | Agent 5 (Diff) | No dependencies |

### Must Run Sequentially

| Prerequisite | Dependent | Reason |
|--------------|-----------|--------|
| Agent 1 | Agent 2 | Storage needs object types |
| Agent 2 | Agent 3 | Refs need object database |
| Agent 2 | Agent 4 | Index needs object database |
| Agents 3,4 | Agent 6 | Plumbing needs refs + index |
| Agent 6 | Agent 7 | Porcelain uses plumbing |

---

## Communication Protocol

### Handoff Requirements

When completing work, each agent must provide:

1. **Implementation Summary**
   - Files created/modified
   - Public API documented
   - Key design decisions

2. **Test Report**
   - Test coverage percentage
   - Edge cases covered
   - Known limitations

3. **Integration Notes**
   - How to use from other modules
   - Import statements needed
   - Configuration requirements

### Interface Contracts

Each agent must define clear interfaces:

```python
# Example: Agent 1 provides to Agent 2
from gitpy.objects import Blob, Tree, Commit, Tag, GitObject
from gitpy.objects import parse_object, create_object_data
```

---

## Quality Gates

Each agent must pass before handoff:

| Gate | Requirement |
|------|-------------|
| Tests | All tests passing |
| Coverage | ≥90% for new code |
| Types | mypy strict mode passes |
| Style | ruff check passes |
| Docs | Public APIs documented |

---

## Risk Mitigation

| Risk | Mitigation |
|------|------------|
| Index format complexity | Start with version 2 only |
| Packfile complexity | Defer to future phase |
| Merge conflicts | Start with simple cases |
| Performance | Profile after correctness |

---

## Success Metrics

| Metric | Target |
|--------|--------|
| Git compatibility | 100% for basic operations |
| Test coverage | ≥90% overall |
| Documentation | All public APIs |
| Performance | Within 10x of Git for basic ops |
