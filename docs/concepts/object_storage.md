# Understanding Git's Object Storage

This document explains how Git stores objects on disk. If you've ever wondered what happens inside `.git/objects/` or how Git achieves its legendary performance, this guide will demystify Git's elegant storage system.

## The Big Picture: Content-Addressable Storage

Git's object database is a **content-addressable filesystem**. Instead of organizing files by name or location, Git organizes them by *content*. The SHA-1 hash of an object's content becomes its "address" in the database.

This has profound implications:

1. **Automatic deduplication**: Identical content is stored once
2. **Integrity verification**: Corruption is immediately detectable
3. **Immutability**: Objects never change once created
4. **Efficient sharing**: Same hash = same content across all repositories

---

## The .git/objects Directory

When you run `git init`, Git creates this structure:

```
.git/
└── objects/
    ├── info/           # Auxiliary information
    ├── pack/           # Packfiles (compressed collections)
    └── <XX>/           # Loose objects (2-char prefix directories)
        └── <YYY...>    # Object files (38-char suffix)
```

Let's explore each part.

---

## Loose Objects: The Simple Case

### How Objects Are Stored

When Git creates a new object, it stores it as a "loose object"—an individual file named by its SHA-1 hash.

**Path calculation:**
```
SHA: ce013625030ba8dba906f756967f9e9ca394464a
     ^^
     First 2 chars → directory name

Path: .git/objects/ce/013625030ba8dba906f756967f9e9ca394464a
                   ^^/^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
                   dir        remaining 38 chars
```

**Why split the hash?**

Filesystems become slow with too many files in one directory. By using 256 possible two-character prefixes (00-ff), Git distributes objects across subdirectories.

### Compression

All loose objects are **zlib-compressed**. The compression format:

```
zlib_compress("<type> <size>\0<content>")
```

For example, a blob containing `hello\n`:

```python
# What gets compressed:
raw_data = b"blob 6\0hello\n"

# Stored on disk:
compressed = zlib.compress(raw_data)
```

### Exploring Loose Objects

```bash
# Find an object
$ ls .git/objects/ce/
013625030ba8dba906f756967f9e9ca394464a

# Decompress and view (Python)
$ python3 -c "
import zlib
data = open('.git/objects/ce/013625030ba8dba906f756967f9e9ca394464a', 'rb').read()
print(zlib.decompress(data))
"
b'blob 6\x00hello\n'

# Or use Git's plumbing
$ git cat-file -p ce013625
hello
```

### Object File Format

Inside the compressed file:

```
┌──────────────────────────────────────┐
│ zlib-compressed data                 │
│ ┌──────────────────────────────────┐ │
│ │ type SP size NUL content         │ │
│ │ ^^^^    ^^^^     ^^^^^^^         │ │
│ │ blob    6        hello\n         │ │
│ └──────────────────────────────────┘ │
└──────────────────────────────────────┘
```

- **type**: `blob`, `tree`, `commit`, or `tag`
- **SP**: Space character (0x20)
- **size**: Decimal byte count of content
- **NUL**: Null byte (0x00) separator
- **content**: Raw object data

---

## Atomic Writes: Preventing Corruption

Git uses a critical pattern for writing objects: **write to temp, then rename**.

```python
def write_object(sha, data):
    path = f".git/objects/{sha[:2]}/{sha[2:]}"
    temp_path = path + ".tmp"

    # 1. Write to temporary file
    with open(temp_path, "wb") as f:
        f.write(zlib.compress(data))

    # 2. Atomic rename
    os.rename(temp_path, path)

    # 3. Make read-only (immutable)
    os.chmod(path, 0o444)
```

**Why this matters:**

- If Git crashes during write, only the `.tmp` file is corrupted
- The `rename()` system call is atomic on most filesystems
- Either the complete object exists, or it doesn't—no partial files

### The Idempotency Property

Because objects are content-addressable:

```python
# Writing the same content twice is safe
sha1 = write_object(data)  # Creates object
sha2 = write_object(data)  # Skips (already exists)
assert sha1 == sha2
```

Git checks if the object exists before writing. This is safe because:
- Same content → same hash → same object
- Object files are immutable once created

---

## SHA-1 Verification

When reading an object, Git verifies the hash:

```python
def read_object(sha):
    path = f".git/objects/{sha[:2]}/{sha[2:]}"
    compressed = open(path, "rb").read()
    data = zlib.decompress(compressed)

    # Verify integrity
    computed = hashlib.sha1(data).hexdigest()
    if computed != sha:
        raise CorruptObjectError(f"Expected {sha}, got {computed}")

    return data
```

This catches:
- Disk corruption (bit rot)
- Incomplete writes
- Malicious tampering

If any bit changes, the hash won't match.

---

## Short SHA Resolution

Git allows abbreviated SHA references:

```bash
$ git show ce01362          # 7 characters
$ git show ce0136           # 6 characters
$ git show ce01             # 4 characters (minimum)
```

**How it works:**

```python
def resolve_short_sha(prefix):
    if len(prefix) < 4:
        raise ValueError("Minimum 4 characters required")

    dir_prefix = prefix[:2]
    file_prefix = prefix[2:]

    matches = []
    for file in os.listdir(f".git/objects/{dir_prefix}"):
        if file.startswith(file_prefix):
            matches.append(dir_prefix + file)

    if len(matches) == 0:
        raise NotFoundError(f"No object matching {prefix}")
    if len(matches) > 1:
        raise AmbiguousError(f"{prefix} matches {len(matches)} objects")

    return matches[0]
```

**Ambiguity handling:**

With enough objects, short prefixes become ambiguous. Git requires increasingly longer prefixes:

```bash
$ git show abc1
error: short SHA1 abc1 is ambiguous
hint: The candidates are:
hint:   abc1234... blob
hint:   abc1567... commit
```

---

## Packfiles: Efficient Storage at Scale

Loose objects work well for small repositories, but become inefficient at scale:

- Many small files = filesystem overhead
- Similar objects stored separately (no delta compression)
- Slow for network transfer

**Packfiles** solve this by:

1. Collecting many objects into one file
2. Delta-compressing similar objects
3. Using an index for O(1) lookups

### Pack Structure

```
.git/objects/pack/
├── pack-abc123.idx    # Index (hash → offset)
└── pack-abc123.pack   # Packed objects
```

### When Packing Happens

- `git gc` (garbage collection)
- `git push` / `git fetch` (network transfer)
- Automatically when loose objects exceed threshold

### Pack Format Overview

```
┌─────────────────────────────────────────────┐
│ PACK header (signature, version, count)     │
├─────────────────────────────────────────────┤
│ Object 1 (type, size, compressed data)      │
├─────────────────────────────────────────────┤
│ Object 2 (OFS_DELTA: offset, delta)         │  ← Delta-compressed!
├─────────────────────────────────────────────┤
│ Object 3 (REF_DELTA: base SHA, delta)       │  ← Delta-compressed!
├─────────────────────────────────────────────┤
│ ... more objects ...                        │
├─────────────────────────────────────────────┤
│ SHA-1 checksum of entire pack               │
└─────────────────────────────────────────────┘
```

**Delta compression:**

Instead of storing similar objects fully, Git stores:
- One base object (full content)
- Deltas (instructions to reconstruct others from base)

Example: If file.txt changes slightly between commits:
- Version 1: Full blob (1000 bytes)
- Version 2: Delta from v1 (50 bytes of changes)

This is why Git repositories are so compact!

---

## The Object Database Interface

Git's storage has a clean abstraction:

```
┌─────────────────────────────────────────────┐
│            ObjectDatabase                   │
│  - read(sha) → GitObject                    │
│  - write(obj) → sha                         │
│  - exists(sha) → bool                       │
└─────────────────────────────────────────────┘
                    │
        ┌───────────┴───────────┐
        ▼                       ▼
┌───────────────┐       ┌───────────────┐
│ LooseObjects  │       │   Packfiles   │
│ .git/objects/ │       │ .git/objects/ │
│   XX/YYYY...  │       │   pack/*.pack │
└───────────────┘       └───────────────┘
```

When reading:
1. Check loose objects first
2. Then search packfiles
3. Error if not found

When writing:
1. Always write loose objects
2. `git gc` later converts to packfiles

---

## Repository Initialization

When you run `git init`, Git creates:

```
.git/
├── HEAD                 # Points to current branch
├── config               # Repository configuration
├── description          # For GitWeb (rarely used)
├── objects/
│   ├── info/           # Pack information
│   └── pack/           # Packfiles go here
├── refs/
│   ├── heads/          # Branch references
│   └── tags/           # Tag references
└── info/
    └── exclude         # Local ignore patterns
```

**The essential parts:**

- `HEAD`: Tells Git which branch you're on
- `objects/`: The object database
- `refs/`: Human-readable names for commits

### Bare vs Normal Repositories

**Normal repository:**
```
myproject/
├── .git/               # Git metadata
└── src/                # Working directory
    └── main.py
```

**Bare repository:**
```
myproject.git/          # Just Git metadata, no working directory
├── HEAD
├── config
├── objects/
└── refs/
```

Bare repositories are used for:
- Remote servers (GitHub, etc.)
- Sharing without working directories
- `git clone --bare`

---

## Real-World Storage Patterns

### Small Repository

```
.git/objects/
├── ce/
│   └── 013625...       # A blob
├── 4b/
│   └── 825dc6...       # Empty tree
├── e6/
│   └── 9de29b...       # Empty blob
└── info/
└── pack/               # Empty (no packs yet)
```

### Large Repository After `git gc`

```
.git/objects/
├── pack/
│   ├── pack-abc123.idx    # ~2MB index
│   └── pack-abc123.pack   # ~50MB packed objects
├── info/
│   └── packs              # Lists available packs
└── <few loose objects>    # Recently created, not yet packed
```

---

## Performance Characteristics

### Loose Objects

| Operation | Complexity | Notes |
|-----------|------------|-------|
| Read by SHA | O(1) | Direct path lookup |
| Write | O(1) | Create file |
| Exists check | O(1) | File exists check |
| List all | O(n) | Scan all directories |

### Packfiles

| Operation | Complexity | Notes |
|-----------|------------|-------|
| Read by SHA | O(1) | Index lookup + seek |
| Delta resolution | O(chain) | May need to read base objects |
| Write | N/A | `git gc` handles this |

### Space Efficiency

| Scenario | Loose | Packed |
|----------|-------|--------|
| 1000 small files | ~1000 inodes | 2 files |
| Similar versions | Full copies | Delta compressed |
| Network transfer | Many requests | Single stream |

---

## Implementation in gitpy

### Code Organization

```
gitpy/
├── storage/
│   ├── __init__.py       # Module exports
│   ├── compression.py    # Zlib utilities
│   ├── loose.py          # LooseObjectStore
│   └── database.py       # ObjectDatabase
└── repository.py         # Repository class
```

### LooseObjectStore

Handles individual object files:

```python
class LooseObjectStore:
    def __init__(self, git_dir: Path):
        self.objects_dir = git_dir / "objects"

    def _object_path(self, sha: str) -> Path:
        return self.objects_dir / sha[:2] / sha[2:]

    def exists(self, sha: str) -> bool:
        return self._object_path(sha).exists()

    def read(self, sha: str) -> bytes:
        path = self._object_path(sha)
        compressed = path.read_bytes()
        data = zlib.decompress(compressed)

        # Verify integrity
        if hashlib.sha1(data).hexdigest() != sha:
            raise ValueError("SHA mismatch - corrupted object")

        return data

    def write(self, sha: str, data: bytes) -> Path:
        path = self._object_path(sha)
        if path.exists():
            return path  # Already exists

        path.parent.mkdir(parents=True, exist_ok=True)

        # Atomic write
        temp = path.with_suffix(".tmp")
        temp.write_bytes(zlib.compress(data))
        temp.rename(path)
        path.chmod(0o444)

        return path
```

### ObjectDatabase

High-level interface with type safety:

```python
class ObjectDatabase:
    def __init__(self, git_dir: Path):
        self.loose = LooseObjectStore(git_dir)

    def read(self, sha: str) -> GitObject:
        data = self.loose.read(sha)
        _, obj = parse_object(data)
        return obj

    def read_blob(self, sha: str) -> Blob:
        obj = self.read(sha)
        if not isinstance(obj, Blob):
            raise TypeError(f"Expected blob, got {obj.type_name}")
        return obj

    def write(self, obj: GitObject) -> str:
        data = create_object_data(obj)
        sha = hashlib.sha1(data).hexdigest()
        self.loose.write(sha, data)
        return sha
```

### Repository

Ties everything together:

```python
class Repository:
    def __init__(self, path: Path):
        self.worktree = path
        self.git_dir = path / ".git"
        self.objects = ObjectDatabase(self.git_dir)

    @classmethod
    def init(cls, path: Path, bare: bool = False) -> "Repository":
        git_dir = path if bare else path / ".git"

        # Create directory structure
        (git_dir / "objects" / "info").mkdir(parents=True)
        (git_dir / "objects" / "pack").mkdir()
        (git_dir / "refs" / "heads").mkdir(parents=True)
        (git_dir / "refs" / "tags").mkdir()

        # Create HEAD
        (git_dir / "HEAD").write_text("ref: refs/heads/main\n")

        return cls(path)

    @classmethod
    def find(cls, start: Path = None) -> "Repository":
        """Walk up directory tree to find repository."""
        path = (start or Path.cwd()).resolve()

        while True:
            if (path / ".git").is_dir():
                return cls(path)
            if path.parent == path:
                raise ValueError("Not a git repository")
            path = path.parent
```

---

## Git Compatibility Verification

### Known Hashes

These must match real Git:

| Object | SHA-1 |
|--------|-------|
| Empty blob | `e69de29bb2d1d6434b8b29ae775ad8c2e48c5391` |
| Empty tree | `4b825dc642cb6eb9a060e54bf8d69288fbee4904` |
| `hello\n` blob | `ce013625030ba8dba906f756967f9e9ca394464a` |

### Interoperability Test

```bash
# Create object with Git, read with gitpy
$ git init test-repo && cd test-repo
$ echo "hello" | git hash-object -w --stdin
ce013625030ba8dba906f756967f9e9ca394464a

$ python3 -c "
from gitpy.repository import Repository
repo = Repository(Path('.'))
blob = repo.objects.read_blob('ce013625')
print(blob.data)  # b'hello\n'
"

# Create object with gitpy, read with Git
$ python3 -c "
from gitpy.repository import Repository
from gitpy.objects import Blob
repo = Repository(Path('.'))
sha = repo.objects.write(Blob(data=b'gitpy wrote this\n'))
print(sha)
"

$ git cat-file -p <sha>
gitpy wrote this
```

---

## Key Takeaways

1. **Content-addressable storage** enables deduplication and integrity
2. **Loose objects** are simple zlib-compressed files
3. **Atomic writes** prevent corruption
4. **SHA verification** catches errors
5. **Packfiles** provide efficient storage at scale
6. **Clean abstractions** separate concerns

The storage layer is deliberately simple—complexity comes from what you build on top. With objects stored reliably, Git can focus on commits, branches, and history without worrying about data integrity.

---

## What's Next?

With object storage in place, the next layers build on top:

- **[Pack Files](pack_files.md)**: Efficient storage combining many objects with delta compression
- **[Delta Compression](delta_compression.md)**: How Git stores only differences between similar objects
- **[Pack Index](pack_index.md)**: Fast O(1) object lookup in pack files
- **References** (`gitpy/refs/`): Human-readable names (branches, tags, HEAD)
- **Index** (`gitpy/index/`): The staging area between working directory and repository
- **Commands** (`gitpy/commands/`): Plumbing and porcelain operations

All of these layers ultimately read and write objects through the storage layer we've built.
