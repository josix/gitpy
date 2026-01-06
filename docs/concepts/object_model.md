# Understanding Git's Object Model

This document explains how Git stores data internally and how we've implemented it in gitpy. If you've ever wondered what happens when you run `git add` or `git commit`, this guide will demystify Git's elegant storage system.

## The Big Picture: Git is a Content-Addressable Filesystem

Before diving into code, let's understand Git's fundamental insight: **Git is not really a version control system at its core—it's a content-addressable filesystem with a VCS built on top.**

What does "content-addressable" mean? In a traditional filesystem, you access files by their path: `/home/user/project/README.md`. In Git's object store, you access data by its *content*. Specifically, Git computes a SHA-1 hash of the content, and that hash becomes the "address" of the data.

This has profound implications:

1. **Automatic deduplication**: If two files have identical content, they're stored once
2. **Integrity verification**: If any bit changes, the hash changes, so corruption is detectable
3. **Immutability**: You can't modify an object without changing its address

## The Four Object Types

Git uses just four object types to represent an entire repository's history:

```
┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐
│   Blob   │  │   Tree   │  │  Commit  │  │   Tag    │
│  (file)  │  │  (dir)   │  │(snapshot)│  │ (label)  │
└──────────┘  └──────────┘  └──────────┘  └──────────┘
```

Let's explore each one and understand why Git needs them.

---

## How Objects Are Identified: SHA-1 Hashing

Every Git object has an "Object ID" (OID)—a 40-character hexadecimal string like `ce013625030ba8dba906f756967f9e9ca394464a`. This is computed using SHA-1, but not just on the raw content. Git prepends a header:

```
<type> <size>\0<content>
```

For example, if you have a file containing `hello\n` (6 bytes), Git computes:

```
SHA-1("blob 6\0hello\n") = ce013625030ba8dba906f756967f9e9ca394464a
```

### Implementation in gitpy

We implement this in the `GitObject` base class (`gitpy/objects/base.py`):

```python
def compute_hash(self) -> str:
    content = self.serialize()
    header = f"{self.type_name} {len(content)}\0".encode()
    return hashlib.sha1(header + content, usedforsecurity=False).hexdigest()
```

The `usedforsecurity=False` parameter tells Python we're using SHA-1 for content addressing, not cryptographic security (which is important for security scanners like Bandit).

**Why does this matter?** This hash formula is Git's contract. If our hashes don't match Git's, our objects won't be compatible. We verify this with known test vectors:

| Content | Expected SHA-1 |
|---------|---------------|
| (empty) | `e69de29bb2d1d6434b8b29ae775ad8c2e48c5391` |
| `hello\n` | `ce013625030ba8dba906f756967f9e9ca394464a` |

---

## Blob: The Simplest Object

A blob represents file contents. That's it—just raw bytes. No filename, no permissions, no timestamps. Just content.

### Why separate content from metadata?

This is a key insight in Git's design. Consider two files:

```
/src/utils.py    → contains "def helper(): pass\n"
/lib/utils.py    → contains "def helper(): pass\n"
```

In a traditional system, these are two separate files. In Git, they're **one blob** referenced from two different trees. This is automatic deduplication in action.

### Implementation

The `Blob` class (`gitpy/objects/blob.py`) is beautifully simple:

```python
@dataclass(slots=True)
class Blob(GitObject):
    data: bytes = b""
    type_name: str = "blob"

    def serialize(self) -> bytes:
        return self.data

    @classmethod
    def deserialize(cls, data: bytes) -> Self:
        return cls(data=data)
```

We use `@dataclass(slots=True)` for memory efficiency—this is a Python 3.10+ feature that avoids creating a `__dict__` for each instance.

### Creating blobs from files

We also provide a convenience method to create blobs from files:

```python
@classmethod
def from_file(cls, path: str | Path) -> Self:
    with open(path, "rb") as f:
        return cls(data=f.read())
```

Note the `str | Path` type hint—this is Python 3.10+ union syntax, cleaner than `Union[str, Path]`.

---

## Tree: Representing Directories

If blobs are files, how do we represent directories? That's what trees are for. A tree is a list of entries, where each entry maps a name to either a blob (file) or another tree (subdirectory).

### The Tree Entry Structure

Each entry in a tree contains:

- **mode**: File permissions (e.g., `100644` for regular files, `100755` for executables)
- **name**: The filename (just the name, not the full path)
- **sha**: The OID of the referenced object (blob or tree)

```python
@dataclass(slots=True)
class TreeEntry:
    mode: str
    name: str
    sha: str

    @property
    def is_tree(self) -> bool:
        return self.mode == "40000"

    @property
    def is_blob(self) -> bool:
        return self.mode in ("100644", "100755")
```

### File Modes Explained

Git supports several file modes:

| Mode | Meaning | Example |
|------|---------|---------|
| `100644` | Regular file | `README.md` |
| `100755` | Executable | `run.sh` |
| `40000` | Directory | `src/` |
| `120000` | Symbolic link | `link -> target` |

Notice that directories use `40000`, not `040000`. Git stores modes without leading zeros.

### The Tricky Part: Binary Format and Sorting

Tree serialization has two subtleties that trip up many implementations:

**1. Binary SHA storage**: In the serialized format, the SHA is stored as 20 raw bytes, not 40 hex characters:

```python
def serialize(self) -> bytes:
    result = b""
    for entry in sorted_entries:
        mode_name = f"{entry.mode} {entry.name}\0".encode()
        sha_binary = bytes.fromhex(entry.sha)  # Convert hex to binary!
        result += mode_name + sha_binary
    return result
```

**2. Directory sorting**: Entries must be sorted, but directories are sorted as if they had a trailing `/`. This ensures correct ordering:

```python
def sort_key(self) -> str:
    return self.name + "/" if self.is_tree else self.name
```

Why? Consider these entries: `foo` (directory), `foo.txt` (file), `foobar` (file). The correct order is:

```
foo.txt   →  "foo.txt"   (1st)
foo/      →  "foo/"      (2nd)
foobar    →  "foobar"    (3rd)
```

Without the trailing slash trick, `foo` would sort before `foo.txt`, which breaks Git compatibility.

### Example: Visualizing a Tree

```
project/
├── README.md        (blob: abc123...)
├── src/             (tree: def456...)
│   └── main.py      (blob: 789abc...)
└── run.sh           (blob: fed987...)
```

This directory becomes a tree with three entries:
- `TreeEntry(mode="100644", name="README.md", sha="abc123...")`
- `TreeEntry(mode="40000", name="src", sha="def456...")`
- `TreeEntry(mode="100755", name="run.sh", sha="fed987...")`

The `src/` entry points to another tree object that contains `main.py`.

---

## Commit: Capturing a Snapshot

A commit ties everything together. It represents a complete snapshot of your project at a point in time, plus metadata about who made the change and when.

### What's in a Commit?

```python
@dataclass(slots=True)
class Commit(GitObject):
    tree_sha: str = ""           # The root tree (project snapshot)
    parent_shas: list[str] = field(default_factory=list)  # Parent commits
    author: Identity | None = None      # Who wrote the change
    committer: Identity | None = None   # Who committed it
    message: str = ""            # The commit message
```

**Why separate author and committer?** In open source, you might apply someone else's patch. The author is who wrote the code; the committer is who merged it.

### The Identity Class

Git stores author/committer information in a specific format:

```
Alice Smith <alice@example.com> 1234567890 -0700
```

We parse and generate this with the `Identity` class:

```python
@dataclass(slots=True)
class Identity:
    name: str
    email: str
    timestamp: int      # Unix timestamp
    tz_offset: str      # "+0000" or "-0700"

    def __str__(self) -> str:
        return f"{self.name} <{self.email}> {self.timestamp} {self.tz_offset}"

    @classmethod
    def parse(cls, line: str) -> Self:
        # Parse "Name <email> timestamp tz" format
        lt = line.index("<")
        gt = line.index(">")
        name = line[:lt].strip()
        email = line[lt + 1:gt]
        rest = line[gt + 1:].strip().split()
        return cls(name=name, email=email,
                   timestamp=int(rest[0]), tz_offset=rest[1])
```

### Commit Serialization Format

The serialized format is human-readable:

```
tree 4b825dc642cb6eb9a060e54bf8d69288fbee4904
parent abc123def456789...
author Alice <alice@example.com> 1234567890 -0700
committer Bob <bob@example.com> 1234567899 +0000

This is the commit message.

It can have multiple lines.
```

Key points:
- Headers come first, one per line
- A blank line separates headers from the message
- Root commits have no `parent` line
- Merge commits have multiple `parent` lines

### Commit Types

We provide convenience properties to identify commit types:

```python
@property
def is_root(self) -> bool:
    """True if this is the first commit (no parents)."""
    return len(self.parent_shas) == 0

@property
def is_merge(self) -> bool:
    """True if this is a merge commit (multiple parents)."""
    return len(self.parent_shas) > 1
```

### Visualizing Commit History

```
         ┌─────────┐
         │ Commit  │  ← is_root = True (no parents)
         │ "Init"  │
         └────┬────┘
              │
         ┌────┴────┐
         │ Commit  │  ← Regular commit (one parent)
         │ "Add X" │
         └────┬────┘
              │
    ┌─────────┴─────────┐
    │                   │
┌───┴───┐          ┌────┴────┐
│ "Fix" │          │"Feature"│  ← Branch diverges
└───┬───┘          └────┬────┘
    │                   │
    └─────────┬─────────┘
              │
         ┌────┴────┐
         │ "Merge" │  ← is_merge = True (two parents)
         └─────────┘
```

---

## Tag: Named References with Metadata

Annotated tags are like commits that point to other objects instead of trees. They store who created the tag, when, and a message.

### When to Use Tags vs. Branches?

- **Branches** are movable pointers (they advance with new commits)
- **Lightweight tags** are fixed pointers (just a name → SHA mapping)
- **Annotated tags** are objects with metadata (who tagged, message, signature)

For releases, annotated tags are preferred because they record *who* tagged *when* and *why*.

### Tag Structure

```python
@dataclass(slots=True)
class Tag(GitObject):
    object_sha: str = ""       # What we're tagging
    object_type: str = "commit"  # Usually "commit"
    tag_name: str = ""         # e.g., "v1.0.0"
    tagger: Identity | None = None
    message: str = ""
```

### Tag Serialization

Similar to commits:

```
object abc123def456789...
type commit
tag v1.0.0
tagger Alice <alice@example.com> 1234567890 -0700

Release version 1.0.0

This release includes many improvements.
```

---

## Putting It All Together: The Object Graph

Here's how all the objects relate to represent a repository:

```
                  ┌───────────┐
                  │    Tag    │
                  │  "v1.0"   │
                  └─────┬─────┘
                        │ points to
                        ▼
                  ┌───────────┐
                  │  Commit   │
    ┌─────────────│  "Fix X"  │
    │ parent      └─────┬─────┘
    │                   │ tree
    ▼                   ▼
┌───────────┐     ┌───────────┐
│  Commit   │     │   Tree    │
│  "Add Y"  │     │  (root)   │
└───────────┘     └─────┬─────┘
                        │
         ┌──────────────┼──────────────┐
         │              │              │
         ▼              ▼              ▼
   ┌──────────┐   ┌──────────┐   ┌──────────┐
   │   Blob   │   │   Blob   │   │   Tree   │
   │ README   │   │ main.py  │   │   src/   │
   └──────────┘   └──────────┘   └────┬─────┘
                                      │
                                      ▼
                                ┌──────────┐
                                │   Blob   │
                                │ utils.py │
                                └──────────┘
```

This graph shows:
- A tag pointing to a commit
- The commit having a parent (previous commit) and a tree (snapshot)
- The tree containing blobs (files) and another tree (subdirectory)
- The nested tree containing another blob

---

## The Object Factory

For convenience, we provide factory functions to parse and create complete objects (with headers):

### Parsing Objects

```python
def parse_object(data: bytes) -> tuple[str, GitObject]:
    """Parse raw object data (with header) into (sha, object)."""
    null_idx = data.index(b"\0")
    header = data[:null_idx].decode("ascii")
    content = data[null_idx + 1:]

    type_name, size_str = header.split(" ")
    if len(content) != int(size_str):
        raise ValueError("Size mismatch!")

    obj_class = OBJECT_TYPES[type_name]  # {"blob": Blob, "tree": Tree, ...}
    obj = obj_class.deserialize(content)

    sha = hashlib.sha1(data, usedforsecurity=False).hexdigest()
    return sha, obj
```

### Creating Object Data

```python
def create_object_data(obj: GitObject) -> bytes:
    """Serialize an object with its header, ready for storage."""
    content = obj.serialize()
    header = f"{obj.type_name} {len(content)}\0".encode()
    return header + content
```

---

## Design Principles in Our Implementation

### 1. Immutability

All our objects are effectively immutable. We use `@dataclass(slots=True)` which creates fixed slots, and our methods return new instances rather than modifying existing ones.

### 2. Type Safety

We leverage Python 3.12+ type hints throughout:
- `Self` for methods returning the same class type
- `list[str]` instead of `List[str]`
- `str | None` instead of `Optional[str]`

### 3. Separation of Concerns

Each object knows how to serialize/deserialize itself, but doesn't know about storage. Storage is handled separately (Phase 2), which allows us to:
- Test objects in isolation
- Swap storage backends
- Keep each class focused

### 4. Git Compatibility

We obsessively verify against real Git:

```bash
# Our empty blob hash must match Git's
echo -n "" | git hash-object --stdin
# e69de29bb2d1d6434b8b29ae775ad8c2e48c5391

# Our empty tree hash must match Git's
git hash-object -t tree /dev/null
# 4b825dc642cb6eb9a060e54bf8d69288fbee4904
```

---

## Usage Examples

### Creating and Hashing a Blob

```python
from gitpy.objects import Blob

# From raw bytes
blob = Blob(data=b"Hello, World!\n")
print(blob.oid)  # 8ab686eafeb1f44702738c8b0f24f2567c36da6d

# From a file
blob = Blob.from_file("README.md")
print(f"README.md hash: {blob.oid}")
```

### Building a Tree

```python
from gitpy.objects import Tree, TreeEntry, Blob

# Create some blobs
readme = Blob(data=b"# My Project\n")
main_py = Blob(data=b"print('hello')\n")

# Create a tree referencing them
tree = Tree(entries=[
    TreeEntry(mode="100644", name="README.md", sha=readme.oid),
    TreeEntry(mode="100644", name="main.py", sha=main_py.oid),
])

print(f"Tree hash: {tree.oid}")
```

### Creating a Commit

```python
from gitpy.objects import Commit, Identity

author = Identity.now("Alice", "alice@example.com")

commit = Commit(
    tree_sha=tree.oid,
    parent_shas=[],  # First commit, no parents
    author=author,
    committer=author,
    message="Initial commit\n\nThis is the first commit."
)

print(f"Commit: {commit.oid}")
print(f"Is root: {commit.is_root}")  # True
```

---

## What's Next?

The object model is the foundation. In subsequent phases, we build on top of it:

- **Phase 2: Object Storage** - Compressing and storing objects on disk
- **Phase 3: References** - HEAD, branches, and tags pointing to objects
- **Phase 4: Index** - The staging area for preparing commits
- **Phase 5+: Commands** - The porcelain commands like `add`, `commit`, `log`

Each phase builds on the immutable, content-addressable objects we've defined here. The elegance of Git is that everything reduces to these four simple object types.
