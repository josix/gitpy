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
- [x] All objects serialize/deserialize correctly
- [x] SHA-1 matches Git for identical content
- [x] Empty blob hash: `e69de29bb2d1d6434b8b29ae775ad8c2e48c5391`
- [x] Empty tree hash: `4b825dc642cb6eb9a060e54bf8d69288fbee4904`
- [x] 100% test coverage

**Status**: ✅ **COMPLETE** (Phase 1)

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
- [x] Objects stored in `.git/objects/XX/YYY...`
- [x] Zlib compression matches Git format
- [x] Atomic writes with temp files
- [x] Short SHA resolution (minimum 4 chars)
- [x] Repository.init() creates valid structure
- [x] Git can read gitpy objects and vice versa

**Status**: ✅ **COMPLETE** (Phase 2)

**Estimated Complexity**: Medium

---

### Agent 2b: Pack Objects Agent

**Domain**: Pack files and delta compression

**Responsibilities**:
- Pack file format parsing (.pack)
- Pack index reading/writing (.idx)
- Delta encoding and decoding
- OFS_DELTA and REF_DELTA resolution
- Delta chain traversal
- Pack file creation with delta compression

**Files to Create**:
```
gitpy/
└── storage/
    ├── delta.py         # Delta encoding/decoding
    ├── pack.py          # PackFile reader
    ├── pack_index.py    # PackIndex
    └── pack_writer.py   # PackWriter
tests/
└── storage/
    ├── test_delta.py
    ├── test_pack.py
    ├── test_pack_index.py
    └── test_pack_writer.py
```

**Dependencies**: Agent 1 (Object Model), Agent 2 (Storage)

**Acceptance Criteria**:
- [x] Pack files can be read and objects extracted
- [x] Pack index enables O(1) lookup by SHA
- [x] OFS_DELTA and REF_DELTA objects resolved correctly
- [x] Delta chains of arbitrary depth handled
- [x] Pack files can be written with delta compression
- [x] Git can read gitpy pack files and vice versa

**Status**: ✅ **COMPLETE** (Phase 2b)

**Estimated Complexity**: High

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
- [x] HEAD attached/detached states work
- [x] Branch create/delete/rename operations
- [x] Symbolic refs resolve correctly
- [x] Revision expressions (HEAD^, main~3) parse
- [x] Packed refs are readable
- [x] Reflog entries recorded

**Status**: ✅ **COMPLETE** (Phase 3)

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
- [x] Parse Git index file (version 2)
- [x] Write Git-compatible index
- [x] Checksum validation
- [x] Atomic writes with lock file
- [x] read_tree populates index from tree
- [x] write_tree creates tree from index
- [x] Status detection (modified, added, deleted)

**Status**: ✅ **COMPLETE** (Phase 4)

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
- [x] Myers produces minimal edit distance
- [x] Unified diff format matches Git
- [x] Tree diff detects add/modify/delete
- [x] Context lines configurable
- [x] Binary files handled gracefully

**Status**: ✅ **COMPLETE** (Phase 5)

**Estimated Complexity**: Medium

---

### Agent 6: Plumbing Commands Agent

**Status**: ✅ **COMPLETE** (Phase 6)

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
- [x] All commands match Git behavior
- [x] Exit codes correct
- [x] Error messages helpful
- [x] Argument parsing complete

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
- [x] Basic workflow works: init → add → commit
- [x] Status shows correct state
- [x] Log displays history
- [x] Branch operations functional
- [x] CLI entry point works

**Status**: ✅ **COMPLETE** (Phase 7)

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
- [x] Full workflow tests pass
- [x] Git can use gitpy repos
- [x] gitpy can use Git repos
- [x] All edge cases handled
- [x] CI passes on all PRs

**Status**: ✅ **COMPLETE** (Phase 8)

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
Phase 2b (Advanced Storage - Optional):
┌─────────────────────┐
│ Agent 2b: Pack Obj  │
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
| Agent 2b (Pack) | Agent 3 (Refs) | Independent after Agent 2 |
| Agent 2b (Pack) | Agent 4 (Index) | Independent after Agent 2 |
| Agent 2b (Pack) | Agent 5 (Diff) | Independent after Agent 2 |
| Agent 3 (Refs) | Agent 4 (Index) | Independent subsystems |
| Agent 3 (Refs) | Agent 5 (Diff) | No dependencies |
| Agent 4 (Index) | Agent 5 (Diff) | No dependencies |

### Must Run Sequentially

| Prerequisite | Dependent | Reason |
|--------------|-----------|--------|
| Agent 1 | Agent 2 | Storage needs object types |
| Agent 2 | Agent 2b | Pack needs loose object store |
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
| Packfile complexity | Design complete (phase2b), implement as optional Agent 2b |
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
