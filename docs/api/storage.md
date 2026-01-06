# Storage API Reference

This document provides a complete API reference for the `gitpy.storage` and `gitpy.repository` modules, which implement Git's object storage and repository management.

## Module Overview

```python
from gitpy.storage import (
    compress,           # Zlib compression
    decompress,         # Zlib decompression
    decompress_stream,  # Stream decompression
    LooseObjectStore,   # Low-level loose object storage
    ObjectDatabase,     # High-level object database
)
from gitpy.repository import Repository  # Repository abstraction
```

---

## Compression Utilities

**Module:** `gitpy.storage.compression`

Git uses zlib compression for all stored objects.

### `compress()`

```python
def compress(data: bytes, level: int = DEFAULT_LEVEL) -> bytes
```

Compress data using zlib.

**Parameters:**
- `data` - Raw bytes to compress.
- `level` - Compression level (0-9, -1 for default). Default uses `zlib.Z_DEFAULT_COMPRESSION`.

**Returns:** Compressed bytes.

**Example:**
```python
from gitpy.storage import compress

compressed = compress(b"hello world")
```

### `decompress()`

```python
def decompress(data: bytes) -> bytes
```

Decompress zlib data.

**Parameters:**
- `data` - Compressed bytes.

**Returns:** Decompressed bytes.

**Raises:**
- `zlib.error` - Invalid compressed data.

**Example:**
```python
from gitpy.storage import decompress

original = decompress(compressed_data)
```

### `decompress_stream()`

```python
def decompress_stream(data: bytes) -> tuple[bytes, bytes]
```

Decompress data, returning decompressed content and remaining bytes.

Useful for packfiles where multiple compressed streams are concatenated.

**Parameters:**
- `data` - Compressed bytes (possibly with trailing data).

**Returns:** Tuple of `(decompressed_content, remaining_bytes)`.

**Example:**
```python
from gitpy.storage import decompress_stream

# Decompress first stream from concatenated data
content, remaining = decompress_stream(packed_data)
```

---

## LooseObjectStore

**Module:** `gitpy.storage.loose`

Low-level interface to loose object storage. Loose objects are individual zlib-compressed files stored in `.git/objects/<sha[0:2]>/<sha[2:40]>`.

```python
class LooseObjectStore:
    objects_dir: Path  # Path to .git/objects/
```

### Constructor

```python
def __init__(self, git_dir: Path) -> None
```

Initialize loose object store.

**Parameters:**
- `git_dir` - Path to `.git` directory.

**Example:**
```python
from pathlib import Path
from gitpy.storage import LooseObjectStore

store = LooseObjectStore(Path("/path/to/repo/.git"))
```

### Methods

#### `exists()`

```python
def exists(self, sha: str) -> bool
```

Check if object exists in store.

**Parameters:**
- `sha` - 40-character hex SHA-1.

**Returns:** `True` if object exists, `False` otherwise.

#### `read()`

```python
def read(self, sha: str) -> bytes
```

Read and decompress object.

**Parameters:**
- `sha` - 40-character hex SHA-1.

**Returns:** Decompressed object data (with header).

**Raises:**
- `FileNotFoundError` - Object doesn't exist.
- `zlib.error` - Decompression failed.
- `ValueError` - SHA mismatch (corrupted object).

**Example:**
```python
data = store.read("ce013625030ba8dba906f756967f9e9ca394464a")
# Returns: b"blob 6\x00hello\n"
```

#### `write()`

```python
def write(self, sha: str, data: bytes) -> Path
```

Compress and write object atomically.

**Parameters:**
- `sha` - 40-character hex SHA-1.
- `data` - Complete object data (with header).

**Returns:** Path to written object.

**Note:** Write is atomic (uses temp file + rename). If object already exists, returns existing path without rewriting.

**Example:**
```python
from gitpy.objects import Blob, create_object_data
import hashlib

blob = Blob(data=b"hello\n")
data = create_object_data(blob)
sha = hashlib.sha1(data, usedforsecurity=False).hexdigest()
path = store.write(sha, data)
```

#### `delete()`

```python
def delete(self, sha: str) -> bool
```

Delete object (for garbage collection).

**Parameters:**
- `sha` - 40-character hex SHA-1.

**Returns:** `True` if deleted, `False` if didn't exist.

#### `iter_objects()`

```python
def iter_objects(self) -> Iterator[str]
```

Iterate over all object SHAs in store.

**Yields:** 40-character hex SHA-1 strings for each object.

**Example:**
```python
for sha in store.iter_objects():
    print(sha)
```

---

## ObjectDatabase

**Module:** `gitpy.storage.database`

High-level interface to Git object storage. Provides type-safe access with automatic serialization, compression, and SHA computation.

```python
class ObjectDatabase:
    git_dir: Path       # Path to .git directory
    loose: LooseObjectStore  # Underlying loose object store
```

### Constructor

```python
def __init__(self, git_dir: Path) -> None
```

Initialize object database.

**Parameters:**
- `git_dir` - Path to `.git` directory.

**Example:**
```python
from pathlib import Path
from gitpy.storage import ObjectDatabase

db = ObjectDatabase(Path("/path/to/repo/.git"))
```

### Methods

#### `exists()`

```python
def exists(self, sha: str) -> bool
```

Check if object exists.

**Parameters:**
- `sha` - Full or abbreviated SHA-1.

**Returns:** `True` if object exists, `False` otherwise.

**Example:**
```python
if db.exists("ce01362"):  # Short SHA supported
    print("Object found!")
```

#### `read()`

```python
def read(self, sha: str) -> GitObject
```

Read and parse object.

**Parameters:**
- `sha` - Object SHA (full or abbreviated).

**Returns:** Parsed `GitObject` (`Blob`, `Tree`, `Commit`, or `Tag`).

**Raises:**
- `FileNotFoundError` - Object not found.
- `ValueError` - Invalid object format.

**Example:**
```python
obj = db.read("ce013625030ba8dba906f756967f9e9ca394464a")
print(obj.type_name)  # "blob"
```

#### `read_blob()`

```python
def read_blob(self, sha: str) -> Blob
```

Read object as Blob.

**Parameters:**
- `sha` - Object SHA (full or abbreviated).

**Returns:** `Blob` object.

**Raises:**
- `TypeError` - Object is not a blob.
- `FileNotFoundError` - Object not found.

#### `read_tree()`

```python
def read_tree(self, sha: str) -> Tree
```

Read object as Tree.

**Parameters:**
- `sha` - Object SHA (full or abbreviated).

**Returns:** `Tree` object.

**Raises:**
- `TypeError` - Object is not a tree.
- `FileNotFoundError` - Object not found.

#### `read_commit()`

```python
def read_commit(self, sha: str) -> Commit
```

Read object as Commit.

**Parameters:**
- `sha` - Object SHA (full or abbreviated).

**Returns:** `Commit` object.

**Raises:**
- `TypeError` - Object is not a commit.
- `FileNotFoundError` - Object not found.

#### `read_tag()`

```python
def read_tag(self, sha: str) -> Tag
```

Read object as Tag.

**Parameters:**
- `sha` - Object SHA (full or abbreviated).

**Returns:** `Tag` object.

**Raises:**
- `TypeError` - Object is not a tag.
- `FileNotFoundError` - Object not found.

#### `read_raw()`

```python
def read_raw(self, sha: str) -> bytes
```

Read raw object data (decompressed, with header).

**Parameters:**
- `sha` - Object SHA (full or abbreviated).

**Returns:** Raw object bytes.

**Raises:**
- `FileNotFoundError` - Object not found.

#### `write()`

```python
def write(self, obj: GitObject) -> str
```

Write object to storage.

**Parameters:**
- `obj` - `GitObject` to write.

**Returns:** SHA-1 of written object.

**Example:**
```python
from gitpy.objects import Blob

blob = Blob(data=b"hello world")
sha = db.write(blob)
print(sha)  # "95d09f2b10159347eece71399a7e2e907ea3df4f"
```

#### `hash_object()`

```python
def hash_object(self, obj: GitObject, *, write: bool = True) -> str
```

Compute SHA of object, optionally storing it.

**Parameters:**
- `obj` - `GitObject` to hash.
- `write` - If `True`, also write to storage.

**Returns:** SHA-1 hash.

**Example:**
```python
# Just compute hash without storing
sha = db.hash_object(blob, write=False)
```

#### `get_type()`

```python
def get_type(self, sha: str) -> str
```

Get object type without full parse.

**Parameters:**
- `sha` - Object SHA (full or abbreviated).

**Returns:** Object type name (`"blob"`, `"tree"`, `"commit"`, or `"tag"`).

#### `get_size()`

```python
def get_size(self, sha: str) -> int
```

Get object size without full parse.

**Parameters:**
- `sha` - Object SHA (full or abbreviated).

**Returns:** Size in bytes of the object content.

---

## Repository

**Module:** `gitpy.repository`

Represents a Git repository. Provides access to all repository components: objects, references, index, etc.

```python
class Repository:
    worktree: Path           # Working directory path
    git_dir: Path            # .git directory path
    objects: ObjectDatabase  # Object database
```

### Constructor

```python
def __init__(self, path: Path, git_dir: Path | None = None) -> None
```

Open existing repository.

**Parameters:**
- `path` - Working directory path.
- `git_dir` - `.git` directory (default: `path/.git`).

**Raises:**
- `ValueError` - Not a git repository.

**Example:**
```python
from pathlib import Path
from gitpy.repository import Repository

repo = Repository(Path("/path/to/repo"))
```

### Class Methods

#### `init()`

```python
@classmethod
def init(cls, path: Path, *, bare: bool = False) -> Self
```

Initialize a new repository.

**Parameters:**
- `path` - Where to create repository.
- `bare` - If `True`, create bare repository (no working directory).

**Returns:** Newly created `Repository`.

**Raises:**
- `ValueError` - Already a git repository.

**Example:**
```python
# Create normal repository
repo = Repository.init(Path("/path/to/new/repo"))

# Create bare repository
bare_repo = Repository.init(Path("/path/to/repo.git"), bare=True)
```

**Created Structure:**
```
.git/
├── HEAD                 # ref: refs/heads/main
├── config               # Repository config
├── description          # Repo description
├── objects/
│   ├── info/
│   └── pack/
├── refs/
│   ├── heads/
│   └── tags/
└── info/
    └── exclude          # Local gitignore
```

#### `find()`

```python
@classmethod
def find(cls, start_path: Path | None = None) -> Self
```

Find repository containing path.

Searches up directory tree for `.git` directory.

**Parameters:**
- `start_path` - Where to start search (default: cwd).

**Returns:** `Repository` containing `start_path`.

**Raises:**
- `ValueError` - Not inside a repository.

**Example:**
```python
# Find repo from current directory
repo = Repository.find()

# Find repo from specific path
repo = Repository.find(Path("/path/to/repo/src/deep/nested"))
```

---

## Complete Example

```python
from pathlib import Path
from gitpy.repository import Repository
from gitpy.objects import Blob, Tree, TreeEntry, Commit, Identity

# Initialize a new repository
repo = Repository.init(Path("/tmp/my-repo"))

# Create and store a blob
readme_blob = Blob(data=b"# My Project\n\nWelcome to my project!\n")
readme_sha = repo.objects.write(readme_blob)
print(f"README blob: {readme_sha}")

# Create and store a tree
tree = Tree(entries=[
    TreeEntry(mode=0o100644, name="README.md", sha=readme_sha),
])
tree_sha = repo.objects.write(tree)
print(f"Root tree: {tree_sha}")

# Create and store a commit
author = Identity(
    name="Alice",
    email="alice@example.com",
    timestamp=1704067200,
    tz_offset=0,
)
commit = Commit(
    tree_sha=tree_sha,
    parent_shas=[],
    author=author,
    committer=author,
    message="Initial commit\n",
)
commit_sha = repo.objects.write(commit)
print(f"Commit: {commit_sha}")

# Read back the commit
restored_commit = repo.objects.read_commit(commit_sha)
print(f"Message: {restored_commit.message}")
print(f"Author: {restored_commit.author.name}")

# Use short SHA
obj = repo.objects.read(commit_sha[:7])
print(f"Type: {obj.type_name}")
```

---

## Git Compatibility

The storage module is fully compatible with Git:

| Test | Result |
|------|--------|
| gitpy reads Git-written objects | ✅ |
| Git reads gitpy-written objects | ✅ |
| Empty blob hash matches | ✅ `e69de29bb2d1d6434b8b29ae775ad8c2e48c5391` |
| Empty tree hash matches | ✅ `4b825dc642cb6eb9a060e54bf8d69288fbee4904` |
| `"hello\n"` blob hash matches | ✅ `ce013625030ba8dba906f756967f9e9ca394464a` |

**Verification:**
```bash
# Create object with Git, read with gitpy
echo "hello" | git hash-object -w --stdin
# gitpy can read this object

# Create object with gitpy, read with Git
# After gitpy writes an object:
git cat-file -p <sha>  # Works!
```

---

## Type Hints

The module uses Python 3.12+ type hints:

```python
from typing import Self
from pathlib import Path
from collections.abc import Iterator
```
