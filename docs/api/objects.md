# Object Model API Reference

This document provides a complete API reference for the `gitpy.objects` module, which implements Git's four core object types.

## Module Overview

```python
from gitpy.objects import (
    GitObject,      # Abstract base class
    Blob,           # File contents
    Tree,           # Directory structure
    TreeEntry,      # Single tree entry
    Commit,         # Repository snapshot
    Identity,       # Author/committer info
    Tag,            # Annotated tag
    parse_object,   # Parse object with header
    create_object_data,  # Create object with header
    OBJECT_TYPES,   # Type registry
)
```

---

## GitObject

**Module:** `gitpy.objects.base`

Abstract base class for all Git objects. Git objects are immutable, content-addressable entities identified by a SHA-1 hash of their contents.

```python
class GitObject(ABC):
    type_name: str  # "blob", "tree", "commit", or "tag"
```

### Properties

#### `oid`

```python
@property
def oid(self) -> str
```

Object ID (SHA-1 hash). Returns a 40-character hexadecimal SHA-1 hash identifying this object.

**Example:**
```python
blob = Blob(data=b"hello\n")
print(blob.oid)  # "ce013625030ba8dba906f756967f9e9ca394464a"
```

### Methods

#### `serialize()`

```python
@abstractmethod
def serialize(self) -> bytes
```

Serialize object content (without header).

**Returns:** The raw bytes representing this object's content.

#### `deserialize()`

```python
@classmethod
@abstractmethod
def deserialize(cls, data: bytes) -> Self
```

Deserialize object content (without header).

**Parameters:**
- `data` - Raw bytes of the object content.

**Returns:** A new instance of the object.

#### `compute_hash()`

```python
def compute_hash(self) -> str
```

Compute SHA-1 hash of this object. The hash is computed over the full object data including the header: `<type> <size>\0<content>`.

**Returns:** 40-character hexadecimal SHA-1 hash.

### Comparison and Hashing

```python
def __eq__(self, other: object) -> bool
def __hash__(self) -> int
```

Two objects are equal if they have the same OID. Objects are hashable and can be used in sets and dicts.

---

## Blob

**Module:** `gitpy.objects.blob`

Represents file contents in Git. A blob stores the raw contents of a single file with no filename, permissions, or other metadata.

```python
@dataclass(slots=True)
class Blob(GitObject):
    data: bytes = b""
    type_name: str = "blob"
```

### Attributes

| Name | Type | Default | Description |
|------|------|---------|-------------|
| `data` | `bytes` | `b""` | Raw file contents |
| `type_name` | `str` | `"blob"` | Object type identifier |

### Constructor

```python
def __init__(self, data: bytes = b"") -> None
```

**Parameters:**
- `data` - Raw file contents as bytes.

**Example:**
```python
# Create from bytes
blob = Blob(data=b"Hello, World!\n")

# Empty blob
empty_blob = Blob()
```

### Methods

#### `serialize()`

```python
def serialize(self) -> bytes
```

Return raw content.

**Returns:** The raw file contents.

#### `deserialize()`

```python
@classmethod
def deserialize(cls, data: bytes) -> Self
```

Create Blob from raw content.

**Parameters:**
- `data` - Raw bytes of the file contents.

**Returns:** A new Blob instance.

#### `from_file()`

```python
@classmethod
def from_file(cls, path: str | Path) -> Self
```

Create Blob from file path.

**Parameters:**
- `path` - Path to the file to read.

**Returns:** A new Blob instance with the file's contents.

**Example:**
```python
blob = Blob.from_file("README.md")
print(blob.oid)
```

### Well-Known Hashes

| Content | OID |
|---------|-----|
| Empty (`b""`) | `e69de29bb2d1d6434b8b29ae775ad8c2e48c5391` |
| `b"hello\n"` | `ce013625030ba8dba906f756967f9e9ca394464a` |

---

## TreeEntry

**Module:** `gitpy.objects.tree`

A single entry in a tree object, representing a file or subdirectory.

```python
@dataclass(slots=True)
class TreeEntry:
    mode: str
    name: str
    sha: str
```

### Attributes

| Name | Type | Description |
|------|------|-------------|
| `mode` | `str` | File mode (`"100644"`, `"100755"`, `"40000"`, `"120000"`) |
| `name` | `str` | Filename without path separators |
| `sha` | `str` | 40-character hexadecimal SHA-1 hash |

### Constructor

```python
def __init__(self, mode: str, name: str, sha: str) -> None
```

**Parameters:**
- `mode` - File mode string.
- `name` - Filename (must not contain `/`).
- `sha` - 40-character SHA-1 hash.

**Example:**
```python
entry = TreeEntry(
    mode="100644",
    name="README.md",
    sha="ce013625030ba8dba906f756967f9e9ca394464a"
)
```

### Properties

#### `is_tree`

```python
@property
def is_tree(self) -> bool
```

Returns `True` if this entry points to a tree (directory).

#### `is_blob`

```python
@property
def is_blob(self) -> bool
```

Returns `True` if this entry points to a blob (regular file).

#### `is_symlink`

```python
@property
def is_symlink(self) -> bool
```

Returns `True` if this entry is a symbolic link.

#### `is_executable`

```python
@property
def is_executable(self) -> bool
```

Returns `True` if this entry is an executable file.

### Methods

#### `sort_key()`

```python
def sort_key(self) -> str
```

Generate sort key for tree entry ordering. Git sorts tree entries by name, but directories are sorted as if they had a trailing `/`.

**Returns:** Sort key string.

### File Modes Reference

| Mode | Description |
|------|-------------|
| `100644` | Regular file (non-executable) |
| `100755` | Executable file |
| `40000` | Directory (tree) |
| `120000` | Symbolic link |
| `160000` | Gitlink (submodule) |

---

## Tree

**Module:** `gitpy.objects.tree`

Represents a directory listing in Git. A tree contains entries mapping names to blobs (files) or other trees (subdirectories).

```python
@dataclass(slots=True)
class Tree(GitObject):
    entries: list[TreeEntry] = field(default_factory=list)
    type_name: str = "tree"
```

### Attributes

| Name | Type | Default | Description |
|------|------|---------|-------------|
| `entries` | `list[TreeEntry]` | `[]` | List of TreeEntry objects |
| `type_name` | `str` | `"tree"` | Object type identifier |

### Constructor

```python
def __init__(self, entries: list[TreeEntry] | None = None) -> None
```

**Parameters:**
- `entries` - List of TreeEntry objects (optional).

**Example:**
```python
tree = Tree(entries=[
    TreeEntry("100644", "README.md", "ce01362..."),
    TreeEntry("40000", "src", "7a8b9c0..."),
])
```

### Methods

#### `serialize()`

```python
def serialize(self) -> bytes
```

Serialize tree to bytes.

**Format:** Sequence of entries, each as `<mode> <name>\0<20-byte-sha>`. Entries are sorted by Git's sorting rules.

**Returns:** Binary representation of the tree.

#### `deserialize()`

```python
@classmethod
def deserialize(cls, data: bytes) -> Self
```

Parse tree from bytes.

**Parameters:**
- `data` - Binary tree data (without header).

**Returns:** A new Tree instance.

#### `add_entry()`

```python
def add_entry(self, mode: str, name: str, sha: str) -> None
```

Add an entry to this tree.

**Parameters:**
- `mode` - File mode string.
- `name` - Filename (must not contain `/`).
- `sha` - 40-character SHA-1 hash.

**Raises:**
- `ValueError` - If name contains `/`.

**Example:**
```python
tree = Tree()
tree.add_entry("100644", "file.txt", "abc123...")
tree.add_entry("40000", "subdir", "def456...")
```

#### `get_entry()`

```python
def get_entry(self, name: str) -> TreeEntry | None
```

Get entry by name.

**Parameters:**
- `name` - Filename to look up.

**Returns:** The TreeEntry if found, `None` otherwise.

**Example:**
```python
entry = tree.get_entry("README.md")
if entry:
    print(entry.sha)
```

### Well-Known Hashes

| Content | OID |
|---------|-----|
| Empty tree | `4b825dc642cb6eb9a060e54bf8d69288fbee4904` |

---

## Identity

**Module:** `gitpy.objects.commit`

Author or committer identity. Represents a person's identity in Git commits and tags.

```python
@dataclass(slots=True)
class Identity:
    name: str
    email: str
    timestamp: int
    tz_offset: str
```

### Attributes

| Name | Type | Description |
|------|------|-------------|
| `name` | `str` | Person's name (can contain spaces) |
| `email` | `str` | Email address |
| `timestamp` | `int` | Unix timestamp (seconds since epoch) |
| `tz_offset` | `str` | Timezone offset as `"+HHMM"` or `"-HHMM"` |

### Constructor

```python
def __init__(self, name: str, email: str, timestamp: int, tz_offset: str) -> None
```

**Example:**
```python
author = Identity(
    name="Alice Smith",
    email="alice@example.com",
    timestamp=1699900000,
    tz_offset="-0700"
)
```

### Methods

#### `__str__()`

```python
def __str__(self) -> str
```

Format as Git identity string.

**Returns:** String in format `"Name <email> timestamp tz_offset"`.

**Example:**
```python
print(str(author))  # "Alice Smith <alice@example.com> 1699900000 -0700"
```

#### `parse()`

```python
@classmethod
def parse(cls, line: str) -> Self
```

Parse `"Name <email> timestamp tz"` format.

**Parameters:**
- `line` - Identity string from Git object.

**Returns:** A new Identity instance.

**Example:**
```python
identity = Identity.parse("Alice <alice@example.com> 1699900000 -0700")
```

#### `now()`

```python
@classmethod
def now(cls, name: str, email: str, tz_offset: str = "+0000") -> Self
```

Create identity with current timestamp.

**Parameters:**
- `name` - Person's name.
- `email` - Email address.
- `tz_offset` - Timezone offset (default: `"+0000"` for UTC).

**Returns:** A new Identity instance with current time.

**Example:**
```python
me = Identity.now("Bob", "bob@example.com", "-0800")
```

---

## Commit

**Module:** `gitpy.objects.commit`

Represents a commit object in Git. A commit is a snapshot of the repository at a point in time.

```python
@dataclass(slots=True)
class Commit(GitObject):
    tree_sha: str = ""
    parent_shas: list[str] = field(default_factory=list)
    author: Identity | None = None
    committer: Identity | None = None
    message: str = ""
    type_name: str = "commit"
```

### Attributes

| Name | Type | Default | Description |
|------|------|---------|-------------|
| `tree_sha` | `str` | `""` | SHA-1 hash of the root tree object |
| `parent_shas` | `list[str]` | `[]` | List of parent commit SHAs |
| `author` | `Identity \| None` | `None` | Identity of who wrote the change |
| `committer` | `Identity \| None` | `None` | Identity of who committed the change |
| `message` | `str` | `""` | Commit message (can be multi-line) |
| `type_name` | `str` | `"commit"` | Object type identifier |

### Constructor

```python
def __init__(
    self,
    tree_sha: str = "",
    parent_shas: list[str] | None = None,
    author: Identity | None = None,
    committer: Identity | None = None,
    message: str = "",
) -> None
```

**Example:**
```python
author = Identity.now("Alice", "alice@example.com")
commit = Commit(
    tree_sha="4b825dc642cb6eb9a060e54bf8d69288fbee4904",
    parent_shas=["abc123..."],
    author=author,
    committer=author,
    message="Initial commit\n\nAdd project structure."
)
```

### Properties

#### `is_root`

```python
@property
def is_root(self) -> bool
```

Returns `True` if this is a root commit (no parents).

#### `is_merge`

```python
@property
def is_merge(self) -> bool
```

Returns `True` if this is a merge commit (multiple parents).

### Methods

#### `serialize()`

```python
def serialize(self) -> bytes
```

Serialize commit to bytes.

**Returns:** Binary representation of the commit.

#### `deserialize()`

```python
@classmethod
def deserialize(cls, data: bytes) -> Self
```

Parse commit from bytes.

**Parameters:**
- `data` - Binary commit data (without header).

**Returns:** A new Commit instance.

---

## Tag

**Module:** `gitpy.objects.tag`

Represents an annotated tag object in Git. An annotated tag points to another object (usually a commit) with additional metadata.

```python
@dataclass(slots=True)
class Tag(GitObject):
    object_sha: str = ""
    object_type: str = "commit"
    tag_name: str = ""
    tagger: Identity | None = None
    message: str = ""
    type_name: str = "tag"
```

### Attributes

| Name | Type | Default | Description |
|------|------|---------|-------------|
| `object_sha` | `str` | `""` | SHA-1 hash of the tagged object |
| `object_type` | `str` | `"commit"` | Type of tagged object |
| `tag_name` | `str` | `""` | Name of the tag |
| `tagger` | `Identity \| None` | `None` | Identity of who created the tag |
| `message` | `str` | `""` | Tag message (can be multi-line) |
| `type_name` | `str` | `"tag"` | Object type identifier |

### Constructor

```python
def __init__(
    self,
    object_sha: str = "",
    object_type: str = "commit",
    tag_name: str = "",
    tagger: Identity | None = None,
    message: str = "",
) -> None
```

**Example:**
```python
tagger = Identity.now("Alice", "alice@example.com")
tag = Tag(
    object_sha="abc123...",
    object_type="commit",
    tag_name="v1.0.0",
    tagger=tagger,
    message="Version 1.0.0 - First stable release"
)
```

### Methods

#### `serialize()`

```python
def serialize(self) -> bytes
```

Serialize tag to bytes.

**Returns:** Binary representation of the tag.

#### `deserialize()`

```python
@classmethod
def deserialize(cls, data: bytes) -> Self
```

Parse tag from bytes.

**Parameters:**
- `data` - Binary tag data (without header).

**Returns:** A new Tag instance.

---

## Module-Level Functions

### `parse_object()`

```python
def parse_object(data: bytes) -> tuple[str, GitObject]
```

Parse a complete Git object (with header).

Takes raw object data including the header and returns the SHA-1 hash and deserialized object.

**Parameters:**
- `data` - Complete object data with header: `<type> <size>\0<content>`

**Returns:** Tuple of `(sha, object)` where sha is the 40-char hex hash.

**Raises:**
- `ValueError` - If object type is unknown or size mismatches.

**Example:**
```python
# Read raw object data from disk
raw_data = b"blob 6\x00hello\n"
sha, obj = parse_object(raw_data)
print(sha)  # "ce013625030ba8dba906f756967f9e9ca394464a"
print(obj.data)  # b"hello\n"
```

### `create_object_data()`

```python
def create_object_data(obj: GitObject) -> bytes
```

Create complete Git object data (with header) from object.

**Parameters:**
- `obj` - A GitObject instance to serialize.

**Returns:** Complete object data ready for storage: `<type> <size>\0<content>`

**Example:**
```python
blob = Blob(data=b"hello\n")
data = create_object_data(blob)
print(data)  # b"blob 6\x00hello\n"
```

### `OBJECT_TYPES`

```python
OBJECT_TYPES: dict[str, type[GitObject]] = {
    "blob": Blob,
    "tree": Tree,
    "commit": Commit,
    "tag": Tag,
}
```

Registry mapping type names to their classes.

**Example:**
```python
obj_class = OBJECT_TYPES["blob"]
blob = obj_class.deserialize(b"content")
```

---

## Type Hints

The module uses Python 3.12+ type hints:

```python
from typing import Self

# Type alias (PEP 695)
type SHA = str  # 40-character hex string
type RefName = str  # Reference name like "refs/heads/main"
```

---

## Complete Example

```python
from gitpy.objects import (
    Blob, Tree, TreeEntry, Commit, Tag, Identity,
    create_object_data, parse_object
)

# Create a blob from file contents
blob = Blob(data=b"print('Hello, World!')\n")
print(f"Blob OID: {blob.oid}")

# Create a tree with the blob
tree = Tree()
tree.add_entry("100755", "hello.py", blob.oid)
print(f"Tree OID: {tree.oid}")

# Create a commit
author = Identity.now("Alice", "alice@example.com", "-0700")
commit = Commit(
    tree_sha=tree.oid,
    parent_shas=[],  # Root commit
    author=author,
    committer=author,
    message="Initial commit"
)
print(f"Commit OID: {commit.oid}")
print(f"Is root commit: {commit.is_root}")

# Create an annotated tag
tag = Tag(
    object_sha=commit.oid,
    object_type="commit",
    tag_name="v1.0.0",
    tagger=author,
    message="First release"
)
print(f"Tag OID: {tag.oid}")

# Serialize and parse roundtrip
data = create_object_data(blob)
sha, restored = parse_object(data)
assert sha == blob.oid
assert restored.data == blob.data
```
