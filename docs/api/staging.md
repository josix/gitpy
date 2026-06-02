# Staging (Index) API Reference

This document provides a complete API reference for the `gitpy.index` module, which implements Git's staging area (the index).

## Module Overview

```python
from gitpy.index import (
    IndexEntry,       # A single staged-file record
    Index,            # In-memory staging area
    IndexFile,        # Read/write .git/index with atomic writes
    read_tree,        # Populate index from a tree object
    write_tree,       # Create tree objects from the index
    FileStatus,       # Enum: UNMODIFIED, MODIFIED, DELETED, UNTRACKED, ADDED
    StatusEntry,      # Per-file status (index vs HEAD, worktree vs index)
    get_status,       # Compare index and worktree against HEAD
    has_conflicts,    # Check for unresolved merge conflicts
    get_conflicts,    # Retrieve conflicted entries grouped by path
    add_conflict,     # Record a merge conflict in the index
    resolve_conflict, # Resolve a conflict by writing a stage-0 entry
)
```

---

## IndexEntry

**Module:** `gitpy.index.entry`

A single entry in the Git index. Tracks a file's identity, content hash, and stat metadata for efficient change detection.

```python
@dataclass(slots=True)
class IndexEntry:
    ctime_s: int
    ctime_ns: int
    mtime_s: int
    mtime_ns: int
    dev: int
    ino: int
    mode: int
    uid: int
    gid: int
    size: int
    sha: str
    flags: int
    path: str
    extended_flags: int  # default 0
```

### Attributes

| Name | Type | Description |
|------|------|-------------|
| `ctime_s` | `int` | Creation time seconds |
| `ctime_ns` | `int` | Creation time nanoseconds (sub-second part only) |
| `mtime_s` | `int` | Modification time seconds |
| `mtime_ns` | `int` | Modification time nanoseconds (sub-second part only) |
| `dev` | `int` | Device ID (masked to 32 bits) |
| `ino` | `int` | Inode number (masked to 32 bits) |
| `mode` | `int` | File mode as integer (e.g. `0o100644`) |
| `uid` | `int` | User ID (masked to 32 bits) |
| `gid` | `int` | Group ID (masked to 32 bits) |
| `size` | `int` | File size in bytes |
| `sha` | `str` | 40-character hex SHA-1 of the blob |
| `flags` | `int` | Packed flags (stage \| name_length) |
| `path` | `str` | Relative path within the repository |
| `extended_flags` | `int` | Extended flags (version 3+, default `0`) |

### Properties

#### `stage`

```python
@property
def stage(self) -> int
```

Merge stage: `0` = normal, `1` = base, `2` = ours, `3` = theirs.

#### `name_length`

```python
@property
def name_length(self) -> int
```

Stored name length (truncated to `0xFFF` for long paths).

#### `assume_valid`

```python
@property
def assume_valid(self) -> bool
```

`True` when the assume-valid flag is set (skip in status checks).

#### `is_regular_file`

```python
@property
def is_regular_file(self) -> bool
```

`True` when the entry represents a regular file.

#### `is_executable`

```python
@property
def is_executable(self) -> bool
```

`True` when the entry is an executable file (mode `0o100755`).

#### `is_symlink`

```python
@property
def is_symlink(self) -> bool
```

`True` when the entry represents a symbolic link (mode `0o120000`).

### Class Methods

#### `from_path()`

```python
@classmethod
def from_path(
    cls,
    path: str,
    sha: str,
    worktree: Path,
    stage: int = 0,
) -> Self
```

Create an `IndexEntry` by stat-ing a file in the working tree. Uses nanosecond timestamps directly from `st_ctime_ns` / `st_mtime_ns` to avoid floating-point precision loss.

**Parameters:**
- `path` - Repository-relative path of the file.
- `sha` - 40-character hex SHA-1 of the file's blob.
- `worktree` - Absolute path to the repository working directory.
- `stage` - Merge stage (0 for normal files).

**Returns:** A new `IndexEntry` populated from the file's stat.

**Example:**
```python
from pathlib import Path
from gitpy.index import IndexEntry

entry = IndexEntry.from_path("src/main.py", blob_sha, Path("/repo"))
```

### Methods

#### `matches_stat()`

```python
def matches_stat(self, st: os.stat_result) -> bool
```

Check whether a file's stat still matches the cached metadata. Returns `True` when the file is probably unchanged (fast path). Returns `False` when the file has definitely changed. Checks size, mtime, inode, ctime, and file mode (exec-bit / type).

**Parameters:**
- `st` - Result of `os.stat()` on the file.

**Returns:** `True` if the cached metadata still matches `st`.

---

## Index

**Module:** `gitpy.index.index`

The Git index (staging area). Entries are stored in a dict keyed by `(path, stage)` to support merge conflict stages (`0` = normal, `1`–`3` = conflict stages). Iteration yields all entries sorted by path then stage, matching Git's wire format.

```python
class Index:
    entries: dict[tuple[str, int], IndexEntry]  # Keyed by (path, stage)
    version: int                                 # Index format version (2)
```

### Constructor

```python
def __init__(self) -> None
```

Create an empty index at version 2.

**Example:**
```python
from gitpy.index import Index

index = Index()
```

### Collection Protocol

#### `__len__()`

```python
def __len__(self) -> int
```

Return the number of staged entries.

#### `__iter__()`

```python
def __iter__(self) -> Iterator[IndexEntry]
```

Yield entries sorted by path then stage (Git-canonical order).

#### `__contains__()`

```python
def __contains__(self, path: object) -> bool
```

Return `True` when any entry for `path` (stage 0) is in the index.

**Example:**
```python
if "README.md" in index:
    print("staged")
```

### Methods

#### `get()`

```python
def get(self, path: str, stage: int = 0) -> IndexEntry | None
```

Return the entry for `(path, stage)`, or `None` if absent.

**Parameters:**
- `path` - Repository-relative file path.
- `stage` - Merge stage (default `0`).

#### `add()`

```python
def add(self, entry: IndexEntry) -> None
```

Add or replace the entry keyed by `(entry.path, entry.stage)`.

**Parameters:**
- `entry` - The `IndexEntry` to add.

#### `remove()`

```python
def remove(self, path: str, stage: int | None = None) -> bool
```

Remove entries for `path`. When `stage` is given, only that specific stage is removed. When `stage` is `None`, all stages for `path` are removed.

**Parameters:**
- `path` - Repository-relative file path.
- `stage` - Specific stage to remove, or `None` to remove all stages.

**Returns:** `True` if at least one entry was removed.

#### `clear()`

```python
def clear(self) -> None
```

Remove all entries.

#### `to_bytes()`

```python
def to_bytes(self) -> bytes
```

Serialise the index to a Git-compatible byte string.

**Returns:** Bytes containing header, entries, and trailing SHA-1 checksum.

#### `from_bytes()`

```python
@classmethod
def from_bytes(cls, data: bytes) -> Self
```

Parse an index from raw bytes.

**Parameters:**
- `data` - Full contents of a `.git/index` file.

**Returns:** A populated `Index` instance.

**Raises:**
- `ValueError` - If the checksum is wrong, the signature is invalid, or the version is unsupported.

---

## IndexFile

**Module:** `gitpy.index.index`

Manages `.git/index` with atomic write semantics. Writes use an exclusive-create lock file that is then renamed over the real index, so a crash during write never leaves a partial file.

```python
class IndexFile:
    index_path: Path  # Path to .git/index
    lock_path: Path   # Path to .git/index.lock
```

### Constructor

```python
def __init__(self, git_dir: Path) -> None
```

**Parameters:**
- `git_dir` - Absolute path to the `.git` directory.

**Example:**
```python
from pathlib import Path
from gitpy.index import IndexFile

idx_file = IndexFile(Path("/path/to/repo/.git"))
```

### Methods

#### `read()`

```python
def read(self) -> Index
```

Read and parse the index file. Returns an empty `Index` if the file does not exist yet.

**Returns:** Parsed `Index`.

**Raises:**
- `ValueError` - If the on-disk file is corrupt.

#### `write()`

```python
def write(self, index: Index) -> None
```

Write `index` atomically using a lock file.

**Parameters:**
- `index` - `Index` to persist.

**Raises:**
- `RuntimeError` - If a lock file already exists (concurrent write).

#### `exists()`

```python
def exists(self) -> bool
```

Return `True` when the `.git/index` file exists.

---

## `read_tree()`

**Module:** `gitpy.index.operations`

```python
def read_tree(
    index: Index,
    tree_sha: str,
    db: ObjectDatabase,
    prefix: str = "",
) -> None
```

Populate `index` from a tree object (recursive). This is the core of `git read-tree`. Existing entries for paths under `prefix` are replaced; entries outside `prefix` are untouched.

**Parameters:**
- `index` - Index to populate.
- `tree_sha` - SHA-1 of the root tree to read.
- `db` - Object database.
- `prefix` - Path prefix prepended to every entry name.

**Example:**
```python
from gitpy.index import Index, read_tree
from gitpy.storage import ObjectDatabase

db = ObjectDatabase(git_dir)
index = Index()
read_tree(index, tree_sha, db)
```

---

## `write_tree()`

**Module:** `gitpy.index.operations`

```python
def write_tree(index: Index, db: ObjectDatabase) -> str
```

Create tree objects from the index. This is the core of `git write-tree`.

**Parameters:**
- `index` - Index to convert.
- `db` - Object database to write trees into.

**Returns:** SHA-1 of the root tree object.

**Example:**
```python
from gitpy.index import write_tree

tree_sha = write_tree(index, db)
print(tree_sha)  # 40-char hex SHA
```

---

## FileStatus

**Module:** `gitpy.index.operations`

Enum describing the status of a file relative to the index or HEAD.

```python
class FileStatus(Enum):
    UNMODIFIED = "unmodified"
    MODIFIED   = "modified"
    DELETED    = "deleted"
    UNTRACKED  = "untracked"
    ADDED      = "added"
```

| Value | Description |
|-------|-------------|
| `UNMODIFIED` | File is unchanged |
| `MODIFIED` | File has been changed |
| `DELETED` | File has been removed |
| `UNTRACKED` | File is not tracked by Git |
| `ADDED` | File is newly staged |

---

## StatusEntry

**Module:** `gitpy.index.operations`

Status of a single file path.

```python
@dataclass(slots=True)
class StatusEntry:
    path: str                      # Repository-relative file path
    index_status: FileStatus       # Comparison of index vs HEAD (staged changes)
    worktree_status: FileStatus    # Comparison of working directory vs index
```

### Attributes

| Name | Type | Description |
|------|------|-------------|
| `path` | `str` | Repository-relative file path |
| `index_status` | `FileStatus` | Comparison of index vs HEAD (staged changes) |
| `worktree_status` | `FileStatus` | Comparison of working directory vs index (unstaged changes) |

---

## `get_status()`

**Module:** `gitpy.index.operations`

```python
def get_status(
    index: Index,
    head_tree_sha: str | None,
    worktree: Path,
    db: ObjectDatabase,
) -> list[StatusEntry]
```

Compare index and working directory against HEAD.

**Parameters:**
- `index` - Current index.
- `head_tree_sha` - SHA-1 of the HEAD commit's tree, or `None` for a new repo with no commits.
- `worktree` - Absolute path to the working directory.
- `db` - Object database.

**Returns:** List of `StatusEntry` for every path that is not fully unmodified.

**Example:**
```python
from gitpy.index import get_status

entries = get_status(index, head_tree_sha, worktree, db)
for e in entries:
    print(e.path, e.index_status, e.worktree_status)
```

---

## `has_conflicts()`

**Module:** `gitpy.index.operations`

```python
def has_conflicts(index: Index) -> bool
```

Return `True` when any entry in `index` has a non-zero merge stage.

**Parameters:**
- `index` - Index to inspect.

**Returns:** `True` if there is at least one conflicted entry.

---

## `get_conflicts()`

**Module:** `gitpy.index.operations`

```python
def get_conflicts(index: Index) -> dict[str, list[IndexEntry]]
```

Return conflicted entries grouped by path.

**Parameters:**
- `index` - Index to inspect.

**Returns:** Mapping from path to list of `IndexEntry` objects (stages 1–3).

**Example:**
```python
from gitpy.index import get_conflicts

conflicts = get_conflicts(index)
for path, entries in conflicts.items():
    stages = [e.stage for e in entries]
    print(f"{path}: stages {stages}")
```

---

## `add_conflict()`

**Module:** `gitpy.index.operations`

```python
def add_conflict(
    index: Index,
    path: str,
    base: IndexEntry | None,
    ours: IndexEntry | None,
    theirs: IndexEntry | None,
) -> None
```

Record a merge conflict for `path` in the index. Removes any stage-0 entry for `path` and adds the three conflict stages.

**Parameters:**
- `index` - Index to modify.
- `path` - Conflicted file path.
- `base` - Stage-1 (common ancestor) entry, or `None`.
- `ours` - Stage-2 (current branch) entry, or `None`.
- `theirs` - Stage-3 (incoming branch) entry, or `None`.

---

## `resolve_conflict()`

**Module:** `gitpy.index.operations`

```python
def resolve_conflict(index: Index, path: str, sha: str, mode: int) -> None
```

Resolve a merge conflict by creating a stage-0 entry. Removes all staged conflict entries for `path` and adds a clean stage-0 entry.

**Parameters:**
- `index` - Index to modify.
- `path` - Conflicted file path to resolve.
- `sha` - 40-character hex SHA-1 of the resolved blob.
- `mode` - File mode integer (e.g. `0o100644`).

---

## Complete Example

```python
from pathlib import Path
from gitpy.index import Index, IndexFile, IndexEntry, read_tree, write_tree, get_status
from gitpy.storage import ObjectDatabase
from gitpy.objects import Blob

git_dir = Path("/path/to/repo/.git")
worktree = Path("/path/to/repo")
db = ObjectDatabase(git_dir)
idx_file = IndexFile(git_dir)

# Read the existing index (or start fresh)
index = idx_file.read()

# Stage a file
blob = Blob.from_file(str(worktree / "README.md"))
blob_sha = db.write(blob)
entry = IndexEntry.from_path("README.md", blob_sha, worktree)
index.add(entry)

# Check status
statuses = get_status(index, head_tree_sha, worktree, db)
for s in statuses:
    print(f"{s.index_status.value:12} {s.worktree_status.value:12} {s.path}")

# Write to a tree object
tree_sha = write_tree(index, db)
print(f"Tree: {tree_sha}")

# Persist
idx_file.write(index)
```

---

## Git Compatibility

The binary index format is Git version 2 compatible:

| Detail | Value |
|--------|-------|
| Signature | `DIRC` |
| Version | `2` |
| Entry size | `62` fixed bytes + NUL-terminated path, padded to 8-byte boundary |
| Checksum | SHA-1 over header + all entries |

Git 2.x can read and write index files produced by gitpy, and vice versa.

---

## See Also

- **[Object Model API](objects.md)**: `Blob`, `Tree`, `TreeEntry` used by index operations
- **[Storage API](storage.md)**: `ObjectDatabase` used by `read_tree`, `write_tree`, `get_status`
- **[References API](refs.md)**: Resolving HEAD to obtain the `head_tree_sha` for `get_status`
