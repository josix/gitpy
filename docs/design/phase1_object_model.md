# Phase 1: Object Model - Design Specification

> **Status**: Draft
> **Author**: Domain Expert
> **Last Updated**: 2026-01-05

## 1. Overview

The Git object model is the foundation of the entire system. Git is fundamentally a content-addressable filesystem with a VCS user interface built on top. Understanding and implementing this layer correctly is critical for all subsequent phases.

### 1.1 Design Goals

- **Immutability**: Objects, once created, never change
- **Content-Addressability**: Objects are identified by SHA-1 hash of their contents
- **Deduplication**: Identical content is stored exactly once
- **Simplicity**: Four object types cover all use cases

### 1.2 Object Types

| Type | Code | Purpose |
|------|------|---------|
| blob | `blob` | File contents |
| tree | `tree` | Directory listing |
| commit | `commit` | Snapshot with metadata |
| tag | `tag` | Annotated tag |

---

## 2. Object Identification

### 2.1 SHA-1 Hash Computation

Every Git object is identified by a 40-character hexadecimal SHA-1 hash.

**Hash Input Format:**
```
<type> <size>\0<content>
```

Where:
- `<type>` is one of: `blob`, `tree`, `commit`, `tag`
- `<size>` is the decimal byte count of `<content>`
- `\0` is a null byte (0x00)
- `<content>` is the raw object content

**Example - Blob:**
```python
content = b"Hello, World!\n"
header = f"blob {len(content)}\0".encode()
full_object = header + content
sha1 = hashlib.sha1(full_object).hexdigest()
# Result: "8ab686eafeb1f44702738c8b0f24f2567c36da6d"
```

### 2.2 Implementation Specification

```python
# gitpy/objects/base.py

from abc import ABC, abstractmethod
import hashlib
from typing import Optional

class GitObject(ABC):
    """Base class for all Git objects."""

    type_name: str  # "blob", "tree", "commit", "tag"

    @abstractmethod
    def serialize(self) -> bytes:
        """Serialize object content (without header)."""
        pass

    @classmethod
    @abstractmethod
    def deserialize(cls, data: bytes) -> "GitObject":
        """Deserialize object content (without header)."""
        pass

    def compute_hash(self) -> str:
        """Compute SHA-1 hash of this object."""
        content = self.serialize()
        header = f"{self.type_name} {len(content)}\0".encode()
        return hashlib.sha1(header + content).hexdigest()

    @property
    def oid(self) -> str:
        """Object ID (SHA-1 hash)."""
        return self.compute_hash()
```

---

## 3. Blob Object Specification

### 3.1 Purpose

A blob (binary large object) stores the contents of a single file. It contains no filename, permissions, or other metadata—just raw content.

### 3.2 Format

```
blob <size>\0<raw-content>
```

- No internal structure
- Binary-safe (can store any byte sequence)
- Filename stored in parent tree, not in blob

### 3.3 Implementation

```python
# gitpy/objects/blob.py

from dataclasses import dataclass
from .base import GitObject

@dataclass
class Blob(GitObject):
    """Represents file contents."""

    type_name: str = "blob"
    data: bytes = b""

    def serialize(self) -> bytes:
        """Return raw content."""
        return self.data

    @classmethod
    def deserialize(cls, data: bytes) -> "Blob":
        """Create Blob from raw content."""
        return cls(data=data)

    @classmethod
    def from_file(cls, path: str) -> "Blob":
        """Create Blob from file path."""
        with open(path, "rb") as f:
            return cls(data=f.read())
```

### 3.4 Test Cases

```python
def test_blob_hash_empty():
    """Empty blob has known hash."""
    blob = Blob(data=b"")
    assert blob.oid == "e69de29bb2d1d6434b8b29ae775ad8c2e48c5391"

def test_blob_hash_hello():
    """'hello\\n' has known hash."""
    blob = Blob(data=b"hello\n")
    assert blob.oid == "ce013625030ba8dba906f756967f9e9ca394464a"

def test_blob_roundtrip():
    """Serialize then deserialize preserves content."""
    original = Blob(data=b"test content\nwith newlines\n")
    restored = Blob.deserialize(original.serialize())
    assert original.data == restored.data
```

---

## 4. Tree Object Specification

### 4.1 Purpose

A tree represents a directory. It contains entries mapping names to blobs (files) or other trees (subdirectories), along with file mode information.

### 4.2 Format

A tree is a sequence of entries, sorted by name:

```
tree <size>\0<entry1><entry2>...
```

Each entry format:
```
<mode> <name>\0<20-byte-sha>
```

Where:
- `<mode>` is the octal file mode (ASCII digits)
- `<name>` is the filename (no path separators)
- `\0` is a null byte separator
- `<20-byte-sha>` is the binary SHA-1 (20 bytes, not hex)

### 4.3 File Modes

| Mode | Description | Example |
|------|-------------|---------|
| `100644` | Regular file | `.py`, `.txt` |
| `100755` | Executable file | Scripts with `+x` |
| `040000` | Directory (tree) | Subdirectories |
| `120000` | Symbolic link | Symlinks |
| `160000` | Gitlink (submodule) | Submodule reference |

**Note**: Mode `040000` is stored as `40000` (no leading zero).

### 4.4 Sorting Rules

Entries MUST be sorted by name with special handling:
- Directories are sorted as if they had a trailing `/`
- Example: `foo` < `foo.txt` < `foo/` (directory named "foo")

```python
def tree_entry_sort_key(name: str, is_tree: bool) -> str:
    """Generate sort key for tree entry."""
    return name + "/" if is_tree else name
```

### 4.5 Implementation

```python
# gitpy/objects/tree.py

from dataclasses import dataclass, field
from typing import List, Tuple
from .base import GitObject

@dataclass
class TreeEntry:
    """Single entry in a tree object."""
    mode: str        # "100644", "100755", "40000", "120000"
    name: str        # Filename (no slashes)
    sha: str         # 40-char hex SHA-1

    @property
    def is_tree(self) -> bool:
        return self.mode == "40000"

    @property
    def is_blob(self) -> bool:
        return self.mode in ("100644", "100755")

    def sort_key(self) -> str:
        return self.name + "/" if self.is_tree else self.name

@dataclass
class Tree(GitObject):
    """Represents a directory listing."""

    type_name: str = "tree"
    entries: List[TreeEntry] = field(default_factory=list)

    def serialize(self) -> bytes:
        """Serialize tree to bytes."""
        # Sort entries by Git's sorting rules
        sorted_entries = sorted(self.entries, key=lambda e: e.sort_key())

        result = b""
        for entry in sorted_entries:
            # Mode and name as ASCII, null separator, binary SHA
            mode_name = f"{entry.mode} {entry.name}\0".encode()
            sha_binary = bytes.fromhex(entry.sha)
            result += mode_name + sha_binary

        return result

    @classmethod
    def deserialize(cls, data: bytes) -> "Tree":
        """Parse tree from bytes."""
        entries = []
        pos = 0

        while pos < len(data):
            # Find space after mode
            space_idx = data.index(b" ", pos)
            mode = data[pos:space_idx].decode("ascii")

            # Find null after name
            null_idx = data.index(b"\0", space_idx)
            name = data[space_idx + 1:null_idx].decode("utf-8")

            # Next 20 bytes are binary SHA
            sha_binary = data[null_idx + 1:null_idx + 21]
            sha = sha_binary.hex()

            entries.append(TreeEntry(mode=mode, name=name, sha=sha))
            pos = null_idx + 21

        return cls(entries=entries)

    def add_entry(self, mode: str, name: str, sha: str) -> None:
        """Add an entry to this tree."""
        if "/" in name:
            raise ValueError("Tree entry name cannot contain '/'")
        self.entries.append(TreeEntry(mode=mode, name=name, sha=sha))
```

### 4.6 Test Cases

```python
def test_tree_empty():
    """Empty tree has known hash."""
    tree = Tree(entries=[])
    assert tree.oid == "4b825dc642cb6eb9a060e54bf8d69288fbee4904"

def test_tree_single_blob():
    """Tree with single file."""
    tree = Tree(entries=[
        TreeEntry(mode="100644", name="hello.txt",
                  sha="ce013625030ba8dba906f756967f9e9ca394464a")
    ])
    # Verify serialization/deserialization roundtrip
    restored = Tree.deserialize(tree.serialize())
    assert len(restored.entries) == 1
    assert restored.entries[0].name == "hello.txt"

def test_tree_sorting():
    """Entries are sorted correctly."""
    tree = Tree(entries=[
        TreeEntry(mode="100644", name="b.txt", sha="a" * 40),
        TreeEntry(mode="40000", name="a", sha="b" * 40),
        TreeEntry(mode="100644", name="a.txt", sha="c" * 40),
    ])
    data = tree.serialize()
    restored = Tree.deserialize(data)
    names = [e.name for e in restored.entries]
    # "a" (dir as "a/") > "a.txt" but dir should come after "a.txt"
    assert names == ["a.txt", "a", "b.txt"]
```

---

## 5. Commit Object Specification

### 5.1 Purpose

A commit represents a snapshot of the repository at a point in time. It points to a tree (the root directory) and contains metadata about who made the change and when.

### 5.2 Format

```
commit <size>\0tree <tree-sha>
parent <parent-sha>
[parent <parent-sha>...]
author <name> <email> <timestamp> <timezone>
committer <name> <email> <timestamp> <timezone>

<commit message>
```

**Fields:**
- `tree`: Required. SHA of root tree object
- `parent`: Optional. SHA of parent commit(s). Omitted for root commit. Multiple for merges.
- `author`: Required. Who wrote the change
- `committer`: Required. Who committed the change
- Blank line separates headers from message
- Message may be multiple lines

### 5.3 Identity Format

```
Name <email@example.com> 1234567890 +0000
```

- Name can contain spaces
- Email in angle brackets
- Unix timestamp (seconds since epoch)
- Timezone as `+HHMM` or `-HHMM`

### 5.4 Implementation

```python
# gitpy/objects/commit.py

from dataclasses import dataclass, field
from typing import List, Optional
from datetime import datetime, timezone
from .base import GitObject

@dataclass
class Identity:
    """Author or committer identity."""
    name: str
    email: str
    timestamp: int      # Unix timestamp
    tz_offset: str      # "+0000" format

    def __str__(self) -> str:
        return f"{self.name} <{self.email}> {self.timestamp} {self.tz_offset}"

    @classmethod
    def parse(cls, line: str) -> "Identity":
        """Parse 'Name <email> timestamp tz' format."""
        # Find email boundaries
        lt = line.index("<")
        gt = line.index(">")

        name = line[:lt].strip()
        email = line[lt + 1:gt]

        # Parse timestamp and timezone
        rest = line[gt + 1:].strip().split()
        timestamp = int(rest[0])
        tz_offset = rest[1] if len(rest) > 1 else "+0000"

        return cls(name=name, email=email, timestamp=timestamp, tz_offset=tz_offset)

    @classmethod
    def now(cls, name: str, email: str) -> "Identity":
        """Create identity with current timestamp."""
        now = datetime.now(timezone.utc)
        return cls(
            name=name,
            email=email,
            timestamp=int(now.timestamp()),
            tz_offset="+0000"
        )

@dataclass
class Commit(GitObject):
    """Represents a commit object."""

    type_name: str = "commit"
    tree_sha: str = ""
    parent_shas: List[str] = field(default_factory=list)
    author: Optional[Identity] = None
    committer: Optional[Identity] = None
    message: str = ""

    def serialize(self) -> bytes:
        """Serialize commit to bytes."""
        lines = []

        lines.append(f"tree {self.tree_sha}")

        for parent in self.parent_shas:
            lines.append(f"parent {parent}")

        lines.append(f"author {self.author}")
        lines.append(f"committer {self.committer}")
        lines.append("")  # Blank line
        lines.append(self.message)

        return "\n".join(lines).encode("utf-8")

    @classmethod
    def deserialize(cls, data: bytes) -> "Commit":
        """Parse commit from bytes."""
        text = data.decode("utf-8")
        lines = text.split("\n")

        tree_sha = ""
        parent_shas = []
        author = None
        committer = None
        message_start = 0

        for i, line in enumerate(lines):
            if line == "":
                message_start = i + 1
                break

            if line.startswith("tree "):
                tree_sha = line[5:]
            elif line.startswith("parent "):
                parent_shas.append(line[7:])
            elif line.startswith("author "):
                author = Identity.parse(line[7:])
            elif line.startswith("committer "):
                committer = Identity.parse(line[10:])

        message = "\n".join(lines[message_start:])

        return cls(
            tree_sha=tree_sha,
            parent_shas=parent_shas,
            author=author,
            committer=committer,
            message=message
        )

    @property
    def is_root(self) -> bool:
        """True if this is a root commit (no parents)."""
        return len(self.parent_shas) == 0

    @property
    def is_merge(self) -> bool:
        """True if this is a merge commit (multiple parents)."""
        return len(self.parent_shas) > 1
```

### 5.5 Test Cases

```python
def test_commit_root():
    """Root commit has no parents."""
    author = Identity(name="Test", email="test@example.com",
                      timestamp=0, tz_offset="+0000")
    commit = Commit(
        tree_sha="4b825dc642cb6eb9a060e54bf8d69288fbee4904",
        parent_shas=[],
        author=author,
        committer=author,
        message="Initial commit"
    )
    assert commit.is_root
    assert not commit.is_merge

def test_commit_roundtrip():
    """Serialize then deserialize preserves all fields."""
    author = Identity(name="Alice", email="alice@example.com",
                      timestamp=1234567890, tz_offset="-0700")
    committer = Identity(name="Bob", email="bob@example.com",
                         timestamp=1234567899, tz_offset="+0530")

    original = Commit(
        tree_sha="a" * 40,
        parent_shas=["b" * 40, "c" * 40],
        author=author,
        committer=committer,
        message="Merge feature branch\n\nDetailed description."
    )

    restored = Commit.deserialize(original.serialize())

    assert restored.tree_sha == original.tree_sha
    assert restored.parent_shas == original.parent_shas
    assert restored.author.name == "Alice"
    assert restored.committer.email == "bob@example.com"
    assert restored.is_merge
```

---

## 6. Tag Object Specification

### 6.1 Purpose

An annotated tag is an object that points to another object (usually a commit) with additional metadata: tagger identity, date, and message.

**Note**: Lightweight tags are just references (Phase 3) and don't create tag objects.

### 6.2 Format

```
tag <size>\0object <sha>
type <type>
tag <tagname>
tagger <identity>

<tag message>
```

**Fields:**
- `object`: SHA of the tagged object
- `type`: Type of tagged object (`commit`, `tree`, `blob`, `tag`)
- `tag`: Tag name
- `tagger`: Who created the tag
- Message after blank line

### 6.3 Implementation

```python
# gitpy/objects/tag.py

from dataclasses import dataclass
from typing import Optional
from .base import GitObject
from .commit import Identity

@dataclass
class Tag(GitObject):
    """Represents an annotated tag object."""

    type_name: str = "tag"
    object_sha: str = ""
    object_type: str = "commit"
    tag_name: str = ""
    tagger: Optional[Identity] = None
    message: str = ""

    def serialize(self) -> bytes:
        """Serialize tag to bytes."""
        lines = [
            f"object {self.object_sha}",
            f"type {self.object_type}",
            f"tag {self.tag_name}",
            f"tagger {self.tagger}",
            "",
            self.message
        ]
        return "\n".join(lines).encode("utf-8")

    @classmethod
    def deserialize(cls, data: bytes) -> "Tag":
        """Parse tag from bytes."""
        text = data.decode("utf-8")
        lines = text.split("\n")

        object_sha = ""
        object_type = ""
        tag_name = ""
        tagger = None
        message_start = 0

        for i, line in enumerate(lines):
            if line == "":
                message_start = i + 1
                break

            if line.startswith("object "):
                object_sha = line[7:]
            elif line.startswith("type "):
                object_type = line[5:]
            elif line.startswith("tag "):
                tag_name = line[4:]
            elif line.startswith("tagger "):
                tagger = Identity.parse(line[7:])

        message = "\n".join(lines[message_start:])

        return cls(
            object_sha=object_sha,
            object_type=object_type,
            tag_name=tag_name,
            tagger=tagger,
            message=message
        )
```

---

## 7. Object Factory

### 7.1 Purpose

A factory to create the appropriate object type from raw data.

### 7.2 Implementation

```python
# gitpy/objects/__init__.py

from typing import Tuple
from .base import GitObject
from .blob import Blob
from .tree import Tree
from .commit import Commit
from .tag import Tag

OBJECT_TYPES = {
    "blob": Blob,
    "tree": Tree,
    "commit": Commit,
    "tag": Tag,
}

def parse_object(data: bytes) -> Tuple[str, GitObject]:
    """
    Parse a complete Git object (with header).

    Returns (sha, object) tuple.
    """
    # Find header boundary
    null_idx = data.index(b"\0")
    header = data[:null_idx].decode("ascii")
    content = data[null_idx + 1:]

    # Parse header
    type_name, size_str = header.split(" ")
    size = int(size_str)

    if len(content) != size:
        raise ValueError(f"Size mismatch: header says {size}, got {len(content)}")

    # Create appropriate object
    if type_name not in OBJECT_TYPES:
        raise ValueError(f"Unknown object type: {type_name}")

    obj_class = OBJECT_TYPES[type_name]
    obj = obj_class.deserialize(content)

    # Compute and return SHA
    import hashlib
    sha = hashlib.sha1(data).hexdigest()

    return sha, obj

def create_object_data(obj: GitObject) -> bytes:
    """
    Create complete Git object data (with header) from object.

    Returns bytes ready for storage.
    """
    content = obj.serialize()
    header = f"{obj.type_name} {len(content)}\0".encode()
    return header + content
```

---

## 8. Acceptance Criteria

### 8.1 Functional Requirements

- [ ] All four object types can be created and serialized
- [ ] All four object types can be parsed from raw bytes
- [ ] SHA-1 hashes match Git's output for identical content
- [ ] Empty blob hash: `e69de29bb2d1d6434b8b29ae775ad8c2e48c5391`
- [ ] Empty tree hash: `4b825dc642cb6eb9a060e54bf8d69288fbee4904`
- [ ] Tree entries are correctly sorted
- [ ] Binary SHA-1 in tree entries is handled correctly
- [ ] Commit message with multiple lines is preserved
- [ ] Merge commits with multiple parents work correctly

### 8.2 Non-Functional Requirements

- [ ] 100% test coverage for object module
- [ ] Type hints on all public methods
- [ ] Docstrings on all classes and public methods
- [ ] No external dependencies (stdlib only)

### 8.3 Verification

Compare output with real Git:
```bash
# Create test blob
echo -n "test content" | git hash-object --stdin
# Should match Blob(data=b"test content").oid

# Verify tree format
git ls-tree HEAD
git cat-file -p HEAD^{tree}
```

---

## 9. Dependencies

- **Python**: 3.7+ (dataclasses, typing)
- **hashlib**: SHA-1 computation (stdlib)
- **No external packages required**

---

## 10. File Structure

```
gitpy/
└── objects/
    ├── __init__.py      # Exports, factory functions
    ├── base.py          # GitObject ABC
    ├── blob.py          # Blob implementation
    ├── tree.py          # Tree, TreeEntry
    ├── commit.py        # Commit, Identity
    └── tag.py           # Tag implementation
```
