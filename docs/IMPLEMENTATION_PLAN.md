# Git Internals Implementation Plan

This document outlines the core concepts of Git internals to be implemented in gitpy, organized in a logical learning progression.

---

## Phase 1: Object Model (Foundation) ✅ COMPLETE

The heart of Git is its content-addressable object database. Everything in Git is built on four object types.

### 1.1 Object Basics

```
gitpy/objects/
├── __init__.py
├── base.py          # Base GitObject class
├── blob.py          # Blob object (file contents)
├── tree.py          # Tree object (directory structure)
├── commit.py        # Commit object (snapshot + metadata)
└── tag.py           # Tag object (annotated tags)
```

**Core Concepts:**
- **SHA-1 Hashing**: Every object is identified by SHA-1 hash of its contents
- **Content-Addressable Storage**: Objects are stored by their hash, enabling deduplication
- **Immutability**: Once created, objects never change

### 1.2 Blob Object
- Stores file contents (binary data)
- Format: `blob <size>\0<content>`
- No filename or metadata - just raw content

### 1.3 Tree Object
- Represents a directory
- Contains entries: `<mode> <name>\0<sha-1>`
- Modes: 100644 (file), 100755 (executable), 040000 (directory), 120000 (symlink)

### 1.4 Commit Object
- Points to a tree (root directory snapshot)
- Contains: parent commit(s), author, committer, timestamp, message
- Format: tree, parent(s), author, committer, blank line, message

### 1.5 Tag Object (Annotated)
- Points to another object (usually commit)
- Contains: tagger, date, message, optional GPG signature

---

## Phase 2: Object Storage ✅ COMPLETE

### 2.1 Object Database Structure

```
.git/objects/
├── pack/            # Packfiles (compressed objects)
├── info/            # Additional info
└── ab/              # Loose objects (first 2 chars of SHA)
    └── cdef123...   # Object file (remaining 38 chars)
```

**Implementation:**
```
gitpy/storage/
├── __init__.py
├── database.py      # Object database operations
├── loose.py         # Loose object read/write
├── pack.py          # Packfile support (advanced)
└── compression.py   # Zlib compression utilities
```

### 2.2 Loose Objects
- Stored as individual zlib-compressed files
- Path: `.git/objects/<sha[0:2]>/<sha[2:]>`
- Operations: read, write, exists, delete

### 2.3 Packfiles (Advanced)
- Multiple objects compressed together
- Delta compression (store differences)
- Index file for fast lookups

---

## Phase 3: References System

References are human-readable pointers to commits.

### 3.1 Reference Types

```
.git/
├── HEAD             # Current branch/commit
├── refs/
│   ├── heads/       # Local branches
│   │   └── main
│   ├── tags/        # Tags
│   │   └── v1.0.0
│   └── remotes/     # Remote-tracking branches
│       └── origin/
│           └── main
```

**Implementation:**
```
gitpy/refs/
├── __init__.py
├── ref.py           # Reference base class
├── head.py          # HEAD management
├── branch.py        # Branch operations
└── tag.py           # Tag references
```

### 3.2 Reference Operations
- Resolve: follow references to final SHA
- Update: atomic reference updates
- Symbolic refs: references to other refs (HEAD -> refs/heads/main)
- Reflog: history of reference changes

---

## Phase 4: Index (Staging Area)

The index is the bridge between working directory and repository.

### 4.1 Index Structure

```
.git/index           # Binary file containing staged entries
```

**Implementation:**
```
gitpy/index/
├── __init__.py
├── index.py         # Index file read/write
└── entry.py         # Index entry class
```

### 4.2 Index Entry Fields
- ctime, mtime (timestamps)
- dev, ino (device/inode)
- mode (file mode)
- uid, gid (user/group)
- file_size
- sha1 (object hash)
- flags (name length, stage)
- path (file path)

### 4.3 Index Operations
- Read/parse index file
- Write index file
- Add entry, remove entry
- Compare with working directory
- Compare with tree (commit)

---

## Phase 5: Diff Engine

Understanding and displaying changes between objects.

### 5.1 Diff Components

```
gitpy/diff/
├── __init__.py
├── algorithm.py     # Myers diff algorithm
├── patch.py         # Patch generation
└── output.py        # Unified diff format
```

### 5.2 Diff Types
- Blob diff: line-by-line file comparison
- Tree diff: directory structure comparison
- Index diff: staged vs HEAD
- Working tree diff: working dir vs index

---

## Phase 6: Plumbing Commands (Low-Level)

These are the building blocks for higher-level commands.

### 6.1 Object Commands
| Command | Description |
|---------|-------------|
| `hash-object` | Compute SHA and optionally store object |
| `cat-file` | Read object contents/type/size |
| `write-tree` | Create tree from index |
| `read-tree` | Read tree into index |
| `commit-tree` | Create commit from tree |
| `ls-tree` | List tree contents |
| `ls-files` | List index contents |

### 6.2 Reference Commands
| Command | Description |
|---------|-------------|
| `update-ref` | Update reference value |
| `symbolic-ref` | Read/update symbolic refs |
| `rev-parse` | Parse revision to SHA |
| `for-each-ref` | Iterate over references |

### 6.3 Index Commands
| Command | Description |
|---------|-------------|
| `update-index` | Modify index entries |
| `checkout-index` | Copy from index to working tree |

---

## Phase 7: Porcelain Commands (User-Facing)

High-level commands that users interact with.

### 7.1 Repository Setup
| Command | Description |
|---------|-------------|
| `init` | Initialize new repository |
| `clone` | Clone repository (advanced) |

### 7.2 Basic Workflow
| Command | Description |
|---------|-------------|
| `add` | Stage files |
| `rm` | Remove files |
| `mv` | Move/rename files |
| `status` | Show working tree status |
| `commit` | Create commit |

### 7.3 History & Inspection
| Command | Description |
|---------|-------------|
| `log` | Show commit history |
| `show` | Show object details |
| `diff` | Show changes |

### 7.4 Branching
| Command | Description |
|---------|-------------|
| `branch` | List/create/delete branches |
| `checkout` | Switch branches/restore files |
| `switch` | Switch branches (modern) |
| `merge` | Merge branches |

### 7.5 Remote Operations (Advanced)
| Command | Description |
|---------|-------------|
| `remote` | Manage remotes |
| `fetch` | Download objects/refs |
| `pull` | Fetch and merge |
| `push` | Upload objects/refs |

---

## Phase 8: Advanced Features

### 8.1 Merge Engine
- Three-way merge algorithm
- Conflict detection and markers
- Merge strategies (recursive, ours, theirs)

### 8.2 Rebase
- Replay commits on new base
- Interactive rebase

### 8.3 Stash
- Save/restore working directory state

### 8.4 Hooks
- Pre-commit, post-commit, etc.

### 8.5 Configuration
- .git/config parsing
- Global vs local config

---

## Suggested Implementation Order

```
Week 1-2: Foundation
├── Object model (blob, tree, commit)
├── SHA-1 hashing
├── Object serialization
└── Basic tests

Week 3-4: Storage
├── Loose object storage
├── Zlib compression
├── Object database
└── cat-file, hash-object commands

Week 5-6: References
├── Reference system
├── HEAD management
├── Branch operations
└── update-ref, symbolic-ref commands

Week 7-8: Index
├── Index file format
├── Index read/write
├── ls-files command
└── update-index command

Week 9-10: Basic Commands
├── init
├── add (using index)
├── status
├── commit
└── log

Week 11-12: Diff & More
├── Diff algorithm
├── diff command
├── branch command
├── checkout command

Beyond: Advanced
├── Merge
├── Remote operations
├── Packfiles
└── Performance optimization
```

---

## Module Architecture

```
gitpy/
├── __init__.py
├── cli.py               # Command-line interface
├── repository.py        # Repository class
├── objects/
│   ├── __init__.py
│   ├── base.py
│   ├── blob.py
│   ├── tree.py
│   ├── commit.py
│   └── tag.py
├── storage/
│   ├── __init__.py
│   ├── database.py
│   └── loose.py
├── refs/
│   ├── __init__.py
│   ├── ref.py
│   └── head.py
├── index/
│   ├── __init__.py
│   └── index.py
├── diff/
│   ├── __init__.py
│   └── algorithm.py
└── commands/
    ├── __init__.py
    ├── plumbing/
    │   ├── hash_object.py
    │   ├── cat_file.py
    │   └── ...
    └── porcelain/
        ├── init.py
        ├── add.py
        ├── commit.py
        └── ...
```

---

## Key Learning Resources

1. **Pro Git Book** - Chapter 10: Git Internals
2. **Git Source Code** - github.com/git/git
3. **Write Yourself a Git** - wyag.thb.lt
4. **Git from the Bottom Up** - jwiegley.github.io/git-from-the-bottom-up

---

## Testing Strategy

Each phase should include:
- Unit tests for individual components
- Integration tests for command workflows
- Property-based tests (hypothesis) for serialization
- Comparison tests against real Git behavior
