# Git Object Model - Concepts & Illustrations

This document provides visual illustrations of Git's object model as implemented in gitpy.

## Overview

Git is fundamentally a **content-addressable filesystem**. Every piece of data is identified by a SHA-1 hash of its contents.

```
┌─────────────────────────────────────────────────────────────┐
│                    GIT OBJECT MODEL                         │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│   ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐   │
│   │   Blob   │  │   Tree   │  │  Commit  │  │   Tag    │   │
│   │  (file)  │  │  (dir)   │  │(snapshot)│  │ (label)  │   │
│   └──────────┘  └──────────┘  └──────────┘  └──────────┘   │
│        │              │             │             │         │
│        └──────────────┴─────────────┴─────────────┘         │
│                           │                                 │
│                    ┌──────┴──────┐                          │
│                    │  GitObject  │                          │
│                    │  (base ABC) │                          │
│                    └─────────────┘                          │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

## Object Identification (SHA-1 Hashing)

Every Git object is identified by a 40-character hexadecimal SHA-1 hash.

```
┌─────────────────────────────────────────────────────────────┐
│                   HASH COMPUTATION                          │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│   Input:                                                    │
│   ┌─────────────────────────────────────────────────────┐   │
│   │  <type> <size>\0<content>                           │   │
│   └─────────────────────────────────────────────────────┘   │
│                          │                                  │
│                          ▼                                  │
│                    ┌──────────┐                             │
│                    │  SHA-1   │                             │
│                    │  Hash    │                             │
│                    └──────────┘                             │
│                          │                                  │
│                          ▼                                  │
│   Output:                                                   │
│   ┌─────────────────────────────────────────────────────┐   │
│   │  e69de29bb2d1d6434b8b29ae775ad8c2e48c5391          │   │
│   └─────────────────────────────────────────────────────┘   │
│                                                             │
└─────────────────────────────────────────────────────────────┘

Example - "hello\n" blob:

  header = "blob 6\0"           content = "hello\n"
       │                              │
       └──────────────┬───────────────┘
                      │
                      ▼
          ┌───────────────────────┐
          │   blob 6\0hello\n     │
          └───────────────────────┘
                      │
                      ▼ SHA-1
          ┌───────────────────────────────────────────┐
          │  ce013625030ba8dba906f756967f9e9ca394464a │
          └───────────────────────────────────────────┘
```

## 1. Blob Object (File Contents)

A blob stores raw file contents with no metadata.

```
┌─────────────────────────────────────────────────────────────┐
│                      BLOB OBJECT                            │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│   File: hello.txt                                           │
│   ┌─────────────────┐                                       │
│   │ hello           │                                       │
│   │ world           │                                       │
│   └─────────────────┘                                       │
│            │                                                │
│            ▼                                                │
│   ┌─────────────────────────────────────────────────────┐   │
│   │  Blob                                               │   │
│   │  ├── type_name: "blob"                              │   │
│   │  └── data: b"hello\nworld\n"                        │   │
│   └─────────────────────────────────────────────────────┘   │
│            │                                                │
│            ▼ serialize()                                    │
│   ┌─────────────────────────────────────────────────────┐   │
│   │  blob 12\0hello\nworld\n                            │   │
│   └─────────────────────────────────────────────────────┘   │
│            │                                                │
│            ▼ SHA-1                                          │
│   ┌─────────────────────────────────────────────────────┐   │
│   │  OID: 94954abda49de8615a048f8d2e64b5de848e27a1      │   │
│   └─────────────────────────────────────────────────────┘   │
│                                                             │
│   Note: Filename "hello.txt" is NOT stored in the blob!     │
│         It's stored in the parent Tree object.              │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### Reference Blob Hashes

```
┌────────────────────────────────────────────────────────────┐
│  Content          │  SHA-1 Hash                            │
├───────────────────┼────────────────────────────────────────┤
│  (empty)          │  e69de29bb2d1d6434b8b29ae775ad8c2e48c5391  │
│  "hello\n"        │  ce013625030ba8dba906f756967f9e9ca394464a  │
│  "Hello, World!\n"│  8ab686eafeb1f44702738c8b0f24f2567c36da6d  │
└────────────────────────────────────────────────────────────┘
```

## 2. Tree Object (Directory Listing)

A tree maps filenames to blobs (files) or other trees (subdirectories).

```
┌─────────────────────────────────────────────────────────────┐
│                      TREE OBJECT                            │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│   Directory structure:                                      │
│   ┌─────────────────────────────────────────────────────┐   │
│   │  project/                                           │   │
│   │  ├── README.md        (file)                        │   │
│   │  ├── src/             (directory)                   │   │
│   │  │   └── main.py      (file)                        │   │
│   │  └── run.sh           (executable)                  │   │
│   └─────────────────────────────────────────────────────┘   │
│                          │                                  │
│                          ▼                                  │
│   ┌─────────────────────────────────────────────────────┐   │
│   │  Tree (root)                                        │   │
│   │  ├── TreeEntry(mode="100644", name="README.md",     │   │
│   │  │             sha="abc123...")        → Blob       │   │
│   │  ├── TreeEntry(mode="100755", name="run.sh",        │   │
│   │  │             sha="def456...")        → Blob       │   │
│   │  └── TreeEntry(mode="40000",  name="src",           │   │
│   │                sha="789abc...")        → Tree       │   │
│   └─────────────────────────────────────────────────────┘   │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### Tree Entry Binary Format

```
┌─────────────────────────────────────────────────────────────┐
│                 TREE ENTRY FORMAT                           │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│   Each entry:  <mode> <name>\0<20-byte-binary-SHA>          │
│                                                             │
│   Example entry for "hello.txt":                            │
│                                                             │
│   ┌────────┬───────────┬────┬─────────────────────────────┐ │
│   │ 100644 │ hello.txt │ \0 │ [20 bytes binary SHA-1]     │ │
│   └────────┴───────────┴────┴─────────────────────────────┘ │
│       │         │        │              │                   │
│       │         │        │              └── Binary SHA-1    │
│       │         │        └── Null byte separator            │
│       │         └── Filename (UTF-8)                        │
│       └── File mode (ASCII)                                 │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### File Modes

```
┌──────────┬─────────────────────┬──────────────────────────┐
│  Mode    │  Description        │  Example                 │
├──────────┼─────────────────────┼──────────────────────────┤
│  100644  │  Regular file       │  README.md, src/main.py  │
│  100755  │  Executable file    │  run.sh, scripts/build   │
│  40000   │  Directory (tree)   │  src/, docs/             │
│  120000  │  Symbolic link      │  link -> target          │
│  160000  │  Gitlink (submodule)│  external/lib            │
└──────────┴─────────────────────┴──────────────────────────┘
```

### Tree Sorting Rules

```
┌─────────────────────────────────────────────────────────────┐
│                   TREE SORTING                              │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│   Directories are sorted as if they had a trailing "/"      │
│                                                             │
│   Entries:                    Sort keys:                    │
│   ┌─────────────────┐        ┌─────────────────┐            │
│   │ foo.txt (file)  │   →    │ "foo.txt"       │            │
│   │ foo     (dir)   │   →    │ "foo/"          │            │
│   │ foobar  (file)  │   →    │ "foobar"        │            │
│   └─────────────────┘        └─────────────────┘            │
│                                                             │
│   Sorted order: foo.txt < foo/ < foobar                     │
│   (because: "foo.txt" < "foo/" < "foobar")                  │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### Reference Tree Hash

```
┌────────────────────────────────────────────────────────────┐
│  Content      │  SHA-1 Hash                                │
├───────────────┼────────────────────────────────────────────┤
│  (empty tree) │  4b825dc642cb6eb9a060e54bf8d69288fbee4904  │
└────────────────────────────────────────────────────────────┘
```

## 3. Commit Object (Repository Snapshot)

A commit points to a tree and contains metadata.

```
┌─────────────────────────────────────────────────────────────┐
│                     COMMIT OBJECT                           │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│   ┌─────────────────────────────────────────────────────┐   │
│   │  Commit                                             │   │
│   │  ├── tree_sha: "4b825dc..."     ─────────┐          │   │
│   │  ├── parent_shas: ["abc123..."] ───┐     │          │   │
│   │  ├── author: Identity             │     │          │   │
│   │  ├── committer: Identity          │     │          │   │
│   │  └── message: "Initial commit"    │     │          │   │
│   └───────────────────────────────────│─────│──────────┘   │
│                                       │     │              │
│                                       ▼     ▼              │
│                              ┌────────┐   ┌────────┐       │
│                              │ Parent │   │  Tree  │       │
│                              │ Commit │   │ (root) │       │
│                              └────────┘   └────────┘       │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### Commit Format

```
┌─────────────────────────────────────────────────────────────┐
│                   COMMIT FORMAT                             │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│   tree 4b825dc642cb6eb9a060e54bf8d69288fbee4904             │
│   parent abc123def456789...                                 │
│   author Alice <alice@example.com> 1234567890 -0700         │
│   committer Bob <bob@example.com> 1234567899 +0000          │
│                                                 ← blank line│
│   Add new feature                                           │
│                                                             │
│   This commit adds a fantastic new feature                  │
│   that does amazing things.                                 │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### Commit Types

```
┌─────────────────────────────────────────────────────────────┐
│                    COMMIT TYPES                             │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│   ROOT COMMIT (no parents):                                 │
│   ┌─────────┐                                               │
│   │ Commit  │  ← is_root = True                             │
│   │ (root)  │    is_merge = False                           │
│   └─────────┘                                               │
│                                                             │
│   REGULAR COMMIT (one parent):                              │
│   ┌─────────┐                                               │
│   │ Parent  │◄────┐                                         │
│   └─────────┘     │                                         │
│                   │                                         │
│   ┌─────────┐     │  ← is_root = False                      │
│   │ Commit  │─────┘    is_merge = False                     │
│   └─────────┘                                               │
│                                                             │
│   MERGE COMMIT (multiple parents):                          │
│   ┌─────────┐  ┌─────────┐                                  │
│   │ Parent1 │  │ Parent2 │                                  │
│   └─────────┘  └─────────┘                                  │
│        ▲            ▲                                       │
│        └──────┬─────┘                                       │
│               │                                             │
│         ┌─────────┐    ← is_root = False                    │
│         │  Merge  │      is_merge = True                    │
│         │ Commit  │                                         │
│         └─────────┘                                         │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### Identity Format

```
┌─────────────────────────────────────────────────────────────┐
│                   IDENTITY FORMAT                           │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│   Format: Name <email> timestamp timezone                   │
│                                                             │
│   ┌───────────────────────────────────────────────────────┐ │
│   │ Alice Smith <alice@example.com> 1234567890 -0700      │ │
│   └───────────────────────────────────────────────────────┘ │
│         │              │              │         │           │
│         │              │              │         └── TZ      │
│         │              │              └── Unix timestamp    │
│         │              └── Email in angle brackets          │
│         └── Name (can contain spaces)                       │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

## 4. Tag Object (Annotated Tag)

An annotated tag points to another object with metadata.

```
┌─────────────────────────────────────────────────────────────┐
│                      TAG OBJECT                             │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│   ┌─────────────────────────────────────────────────────┐   │
│   │  Tag                                                │   │
│   │  ├── object_sha: "abc123..."   ───────────┐         │   │
│   │  ├── object_type: "commit"                │         │   │
│   │  ├── tag_name: "v1.0.0"                   │         │   │
│   │  ├── tagger: Identity                     │         │   │
│   │  └── message: "Release v1.0.0"            │         │   │
│   └───────────────────────────────────────────│─────────┘   │
│                                               │             │
│                                               ▼             │
│                                        ┌───────────┐        │
│                                        │  Commit   │        │
│                                        │ (tagged)  │        │
│                                        └───────────┘        │
│                                                             │
│   Note: Tags can point to any object type:                  │
│   - commit (most common)                                    │
│   - tree                                                    │
│   - blob                                                    │
│   - tag (nested tags)                                       │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### Tag Format

```
┌─────────────────────────────────────────────────────────────┐
│                     TAG FORMAT                              │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│   object abc123def456789...                                 │
│   type commit                                               │
│   tag v1.0.0                                                │
│   tagger Alice <alice@example.com> 1234567890 -0700         │
│                                                 ← blank line│
│   Release version 1.0.0                                     │
│                                                             │
│   This release includes:                                    │
│   - Feature A                                               │
│   - Bug fix B                                               │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

## Object Relationships

```
┌─────────────────────────────────────────────────────────────┐
│              OBJECT RELATIONSHIP DIAGRAM                    │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│                     ┌───────────┐                           │
│                     │    Tag    │                           │
│                     │  "v1.0"   │                           │
│                     └─────┬─────┘                           │
│                           │ points to                       │
│                           ▼                                 │
│                     ┌───────────┐                           │
│                     │  Commit   │                           │
│   ┌─────────────────│  "Fix X"  │                           │
│   │ parent          └─────┬─────┘                           │
│   │                       │ tree                            │
│   ▼                       ▼                                 │
│ ┌───────────┐       ┌───────────┐                           │
│ │  Commit   │       │   Tree    │                           │
│ │  "Add Y"  │       │  (root)   │                           │
│ └───────────┘       └─────┬─────┘                           │
│                           │                                 │
│            ┌──────────────┼──────────────┐                  │
│            │              │              │                  │
│            ▼              ▼              ▼                  │
│      ┌──────────┐   ┌──────────┐   ┌──────────┐             │
│      │   Blob   │   │   Blob   │   │   Tree   │             │
│      │ README   │   │ main.py  │   │   src/   │             │
│      └──────────┘   └──────────┘   └────┬─────┘             │
│                                         │                   │
│                                         ▼                   │
│                                   ┌──────────┐              │
│                                   │   Blob   │              │
│                                   │ utils.py │              │
│                                   └──────────┘              │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

## Object Factory

The factory functions handle serialization with headers.

```
┌─────────────────────────────────────────────────────────────┐
│                   OBJECT FACTORY                            │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│   create_object_data(obj) → bytes                           │
│   ┌─────────────────────────────────────────────────────┐   │
│   │                                                     │   │
│   │   Blob(data=b"hello\n")                             │   │
│   │           │                                         │   │
│   │           ▼                                         │   │
│   │   ┌───────────────────┐                             │   │
│   │   │ blob 6\0hello\n   │  ← Complete object data     │   │
│   │   └───────────────────┘                             │   │
│   │                                                     │   │
│   └─────────────────────────────────────────────────────┘   │
│                                                             │
│   parse_object(data) → (sha, obj)                           │
│   ┌─────────────────────────────────────────────────────┐   │
│   │                                                     │   │
│   │   b"blob 6\0hello\n"                                │   │
│   │           │                                         │   │
│   │           ▼                                         │   │
│   │   ("ce013625...", Blob(data=b"hello\n"))            │   │
│   │                                                     │   │
│   └─────────────────────────────────────────────────────┘   │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

## Class Hierarchy

```
┌─────────────────────────────────────────────────────────────┐
│                   CLASS HIERARCHY                           │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│   gitpy/objects/                                            │
│   │                                                         │
│   ├── base.py                                               │
│   │   └── GitObject (ABC)                                   │
│   │       ├── type_name: str                                │
│   │       ├── serialize() → bytes                           │
│   │       ├── deserialize(bytes) → Self                     │
│   │       ├── compute_hash() → str                          │
│   │       └── oid: str (property)                           │
│   │                                                         │
│   ├── blob.py                                               │
│   │   └── Blob(GitObject)                                   │
│   │       ├── data: bytes                                   │
│   │       └── from_file(path) → Self                        │
│   │                                                         │
│   ├── tree.py                                               │
│   │   ├── TreeEntry                                         │
│   │   │   ├── mode: str                                     │
│   │   │   ├── name: str                                     │
│   │   │   ├── sha: str                                      │
│   │   │   ├── is_tree: bool                                 │
│   │   │   ├── is_blob: bool                                 │
│   │   │   └── sort_key() → str                              │
│   │   │                                                     │
│   │   └── Tree(GitObject)                                   │
│   │       ├── entries: list[TreeEntry]                      │
│   │       ├── add_entry(mode, name, sha)                    │
│   │       └── get_entry(name) → TreeEntry | None            │
│   │                                                         │
│   ├── commit.py                                             │
│   │   ├── Identity                                          │
│   │   │   ├── name: str                                     │
│   │   │   ├── email: str                                    │
│   │   │   ├── timestamp: int                                │
│   │   │   ├── tz_offset: str                                │
│   │   │   ├── parse(str) → Self                             │
│   │   │   └── now(name, email) → Self                       │
│   │   │                                                     │
│   │   └── Commit(GitObject)                                 │
│   │       ├── tree_sha: str                                 │
│   │       ├── parent_shas: list[str]                        │
│   │       ├── author: Identity                              │
│   │       ├── committer: Identity                           │
│   │       ├── message: str                                  │
│   │       ├── is_root: bool                                 │
│   │       └── is_merge: bool                                │
│   │                                                         │
│   └── tag.py                                                │
│       └── Tag(GitObject)                                    │
│           ├── object_sha: str                               │
│           ├── object_type: str                              │
│           ├── tag_name: str                                 │
│           ├── tagger: Identity                              │
│           └── message: str                                  │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

## Key Properties

| Property | Description |
|----------|-------------|
| **Immutability** | Objects never change once created |
| **Content-Addressable** | Same content → same hash → same object |
| **Deduplication** | Identical files stored only once |
| **Integrity** | Hash verifies data hasn't been corrupted |

## Usage Examples

```python
from gitpy.objects import Blob, Tree, TreeEntry, Commit, Identity

# Create a blob
blob = Blob(data=b"Hello, World!\n")
print(blob.oid)  # 8ab686eafeb1f44702738c8b0f24f2567c36da6d

# Create a tree with entries
tree = Tree(entries=[
    TreeEntry(mode="100644", name="hello.txt", sha=blob.oid)
])
print(tree.oid)

# Create a commit
author = Identity.now("Alice", "alice@example.com")
commit = Commit(
    tree_sha=tree.oid,
    parent_shas=[],
    author=author,
    committer=author,
    message="Initial commit"
)
print(commit.oid)
print(commit.is_root)  # True
```
