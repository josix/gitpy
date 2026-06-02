# Diff API Reference

This document provides a complete API reference for the `gitpy.diff` module, which implements the Myers diff algorithm, unified diff formatting, and tree-level diffing.

## Module Overview

```python
from gitpy.diff import (
    EditType,             # Enum: EQUAL, INSERT, DELETE
    Edit,                 # Single edit operation
    myers_diff,           # Compute shortest edit script
    format_unified_diff,  # Format a unified diff string
    DiffStatus,           # Enum: ADDED, DELETED, MODIFIED, RENAMED
    DiffEntry,            # Difference for a single path between two trees
    diff_trees,           # Compare two Git trees
    flatten_tree,         # Recursively flatten a tree to a path mapping
    is_binary,            # Heuristically detect binary content
    format_binary_diff,   # Return the Git binary-diff message
)
```

---

## EditType

**Module:** `gitpy.diff.myers`

Enum describing the type of a single edit operation.

```python
class EditType(Enum):
    EQUAL  = "equal"   # Lines present in both old and new
    INSERT = "insert"  # Lines added in new
    DELETE = "delete"  # Lines removed from old
```

---

## Edit

**Module:** `gitpy.diff.myers`

Single edit operation in a diff script.

```python
@dataclass(slots=True)
class Edit:
    type: EditType      # Kind of edit (EQUAL, INSERT, DELETE)
    old_start: int      # 1-based line number in old file (0 for pure inserts)
    old_count: int      # Number of lines consumed from old file
    new_start: int      # 1-based line number in new file (0 for pure deletes)
    new_count: int      # Number of lines consumed from new file
    old_lines: list[str]  # Lines from old file involved in this edit
    new_lines: list[str]  # Lines from new file involved in this edit
```

### Attributes

| Name | Type | Description |
|------|------|-------------|
| `type` | `EditType` | Kind of edit |
| `old_start` | `int` | 1-based line number in old file (`0` for pure inserts) |
| `old_count` | `int` | Number of lines consumed from old file |
| `new_start` | `int` | 1-based line number in new file (`0` for pure deletes) |
| `new_count` | `int` | Number of lines consumed from new file |
| `old_lines` | `list[str]` | Lines from old file involved in this edit |
| `new_lines` | `list[str]` | Lines from new file involved in this edit |

---

## `myers_diff()`

**Module:** `gitpy.diff.myers`

```python
def myers_diff(old: list[str], new: list[str]) -> list[Edit]
```

Compute the shortest edit script using the Myers O(ND) algorithm. Produces a minimal edit script: the total number of insertions and deletions is the edit distance D between the two sequences. Consecutive edits of the same type are merged into a single `Edit`.

**Parameters:**
- `old` - Lines of the old version.
- `new` - Lines of the new version.

**Returns:** List of `Edit` operations that transform `old` into `new`.

**Example:**
```python
from gitpy.diff import myers_diff, EditType

old = ["line 1", "line 2", "line 3"]
new = ["line 1", "line 2 modified", "line 3", "line 4"]

edits = myers_diff(old, new)
for edit in edits:
    print(edit.type, edit.old_lines, edit.new_lines)
```

---

## `format_unified_diff()`

**Module:** `gitpy.diff.unified`

```python
def format_unified_diff(
    old_lines: list[str],
    new_lines: list[str],
    old_name: str = "a",
    new_name: str = "b",
    context: int = 3,
) -> str
```

Format a pair of line lists as a unified diff string.

**Parameters:**
- `old_lines` - Lines of the old version (without trailing newlines).
- `new_lines` - Lines of the new version (without trailing newlines).
- `old_name` - Label for the old file shown in the `---` header.
- `new_name` - Label for the new file shown in the `+++` header.
- `context` - Number of unchanged context lines around each change.

**Returns:** Unified diff string (including a trailing newline), or an empty string if the two inputs are identical.

**Example:**
```python
from gitpy.diff import format_unified_diff

old = ["hello", "world"]
new = ["hello", "everyone"]

diff = format_unified_diff(
    old, new,
    old_name="a/greeting.txt",
    new_name="b/greeting.txt",
)
print(diff)
# --- a/greeting.txt
# +++ b/greeting.txt
# @@ -1,2 +1,2 @@
#  hello
# -world
# +everyone
```

---

## DiffStatus

**Module:** `gitpy.diff.tree`

Enum describing how a path changed between two trees.

```python
class DiffStatus(Enum):
    ADDED    = "A"  # Path exists only in new tree
    DELETED  = "D"  # Path exists only in old tree
    MODIFIED = "M"  # Path exists in both trees but SHA or mode changed
    RENAMED  = "R"  # Path was renamed (not yet emitted by diff_trees)
```

---

## DiffEntry

**Module:** `gitpy.diff.tree`

Difference for a single path between two trees.

```python
@dataclass(slots=True)
class DiffEntry:
    status: DiffStatus       # How the path changed
    path: str                # Repository-relative path (forward slashes)
    old_sha: str | None      # SHA of the old blob, or None if added
    new_sha: str | None      # SHA of the new blob, or None if deleted
    old_mode: str | None     # Mode string of the old entry, or None if added
    new_mode: str | None     # Mode string of the new entry, or None if deleted
    old_path: str | None     # Original path for renames (None otherwise)
```

### Attributes

| Name | Type | Description |
|------|------|-------------|
| `status` | `DiffStatus` | How the path changed |
| `path` | `str` | Repository-relative path using forward slashes |
| `old_sha` | `str \| None` | SHA of the old blob, or `None` if added |
| `new_sha` | `str \| None` | SHA of the new blob, or `None` if deleted |
| `old_mode` | `str \| None` | Mode string of the old entry, or `None` if added |
| `new_mode` | `str \| None` | Mode string of the new entry, or `None` if deleted |
| `old_path` | `str \| None` | Original path for renames (`None` otherwise) |

---

## `diff_trees()`

**Module:** `gitpy.diff.tree`

```python
def diff_trees(
    old_tree_sha: str | None,
    new_tree_sha: str | None,
    db: ObjectDatabase,
) -> Iterator[DiffEntry]
```

Compare two trees and yield differences for each changed path. Handles `None` on either side to represent an empty tree — useful for diffing the initial commit or a complete deletion.

**Parameters:**
- `old_tree_sha` - SHA of the old tree, or `None` for an empty tree.
- `new_tree_sha` - SHA of the new tree, or `None` for an empty tree.
- `db` - Object database used to read tree and blob objects.

**Yields:** `DiffEntry` for each path that differs between the two trees.

**Example:**
```python
from gitpy.diff import diff_trees, DiffStatus
from gitpy.storage import ObjectDatabase

db = ObjectDatabase(git_dir)

for entry in diff_trees(old_tree_sha, new_tree_sha, db):
    if entry.status == DiffStatus.MODIFIED:
        print(f"M {entry.path}")
    elif entry.status == DiffStatus.ADDED:
        print(f"A {entry.path}")
    elif entry.status == DiffStatus.DELETED:
        print(f"D {entry.path}")
```

---

## `flatten_tree()`

**Module:** `gitpy.diff.tree`

```python
def flatten_tree(
    tree_sha: str,
    db: ObjectDatabase,
    prefix: str,
) -> dict[str, dict[str, str]]
```

Recursively flatten a tree into a mapping of path to `{"sha": ..., "mode": ...}`.

**Parameters:**
- `tree_sha` - SHA of the tree to flatten.
- `db` - Object database.
- `prefix` - Path prefix accumulated during recursion (empty string `""` at the root).

**Returns:** Dict mapping repository-relative paths to `{"sha": ..., "mode": ...}`.

**Example:**
```python
from gitpy.diff import flatten_tree

files = flatten_tree(tree_sha, db, "")
for path, info in sorted(files.items()):
    print(info["mode"], info["sha"], path)
```

---

## `is_binary()`

**Module:** `gitpy.diff.tree`

```python
def is_binary(data: bytes, sample: int = 8000) -> bool
```

Heuristically detect binary content. Checks for a NUL byte in the first `sample` bytes, which is the same heuristic used by Git.

**Parameters:**
- `data` - Raw blob bytes.
- `sample` - Number of bytes to inspect.

**Returns:** `True` if the content appears to be binary.

**Example:**
```python
from gitpy.diff import is_binary

blob_data = db.read_blob(sha).data
if is_binary(blob_data):
    print("Binary file")
```

---

## `format_binary_diff()`

**Module:** `gitpy.diff.tree`

```python
def format_binary_diff(path: str) -> str
```

Return the standard Git message for a binary file diff.

**Parameters:**
- `path` - Repository-relative path of the binary file.

**Returns:** Human-readable string matching Git's binary-diff output.

**Example:**
```python
from gitpy.diff import format_binary_diff

msg = format_binary_diff("images/logo.png")
# "Binary files a/images/logo.png and b/images/logo.png differ"
```

---

## Complete Example

```python
from pathlib import Path
from gitpy.diff import (
    myers_diff, format_unified_diff,
    diff_trees, DiffStatus,
    is_binary, format_binary_diff,
)
from gitpy.storage import ObjectDatabase

git_dir = Path("/path/to/repo/.git")
db = ObjectDatabase(git_dir)

# ---- Line-level diff between two text blobs ----
old_blob = db.read_blob(old_sha)
new_blob = db.read_blob(new_sha)

old_lines = old_blob.data.decode().splitlines()
new_lines = new_blob.data.decode().splitlines()

diff_str = format_unified_diff(
    old_lines, new_lines,
    old_name="a/src/main.py",
    new_name="b/src/main.py",
)
print(diff_str)

# ---- Tree-level diff between two commits ----
for entry in diff_trees(old_tree_sha, new_tree_sha, db):
    blob_data = (db.read_blob(entry.new_sha or entry.old_sha).data
                 if entry.new_sha or entry.old_sha else b"")
    if is_binary(blob_data):
        print(format_binary_diff(entry.path))
    else:
        prefix = {"A": "+", "D": "-", "M": "~"}.get(entry.status.value, "?")
        print(f"{prefix} {entry.path}")
```

---

## Git Compatibility

| Feature | Behaviour |
|---------|-----------|
| Myers algorithm | Produces the same minimal edit distance as Git's diff engine |
| Unified diff headers | `--- a/<path>` / `+++ b/<path>` with `@@ -l,s +l,s @@` hunks |
| Context lines | Default 3, matching `git diff` |
| Binary detection | NUL-byte heuristic, same as Git |
| Binary message | `"Binary files a/<path> and b/<path> differ"` |

---

## See Also

- **[Object Model API](objects.md)**: `Blob`, `Tree`, `TreeEntry` used in tree diffs
- **[Storage API](storage.md)**: `ObjectDatabase` required by `diff_trees` and `flatten_tree`
- **[Staging API](staging.md)**: `get_status` uses `diff_trees` internally to compare index vs HEAD
