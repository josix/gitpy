# Phase 2: Object Storage - Design Specification

> **Status**: ✅ Implemented
> **Author**: Domain Expert
> **Last Updated**: 2026-01-06
> **Dependencies**: Phase 1 (Object Model)

## 1. Overview

The object storage system provides persistent storage for Git objects. Objects are stored in a content-addressable manner using their SHA-1 hash as the key.

### 1.1 Design Goals

- **Durability**: Objects persist across sessions
- **Integrity**: Corruption is detectable via SHA-1 verification
- **Efficiency**: Compression reduces storage requirements
- **Atomicity**: Object writes are atomic (no partial objects)

### 1.2 Storage Locations

```
.git/
└── objects/
    ├── info/           # Auxiliary information
    ├── pack/           # Packfiles (Phase 2b - advanced)
    ├── ab/             # Loose objects with SHA starting "ab"
    │   └── cdef...     # Object file (remaining 38 chars)
    └── cd/
        └── 1234...
```

---

## 2. Loose Object Storage

### 2.1 Path Computation

Objects are stored using the first 2 characters of SHA as directory name:

```
.git/objects/<sha[0:2]>/<sha[2:40]>
```

**Example:**
```
SHA: 8ab686eafeb1f44702738c8b0f24f2567c36da6d
Path: .git/objects/8a/b686eafeb1f44702738c8b0f24f2567c36da6d
```

### 2.2 Compression

All loose objects are zlib-compressed at default level (usually 6).

**Storage Format:**
```
zlib_compress(type + " " + size + "\0" + content)
```

### 2.3 Implementation

```python
# gitpy/storage/loose.py

import os
import zlib
from pathlib import Path
from typing import Optional, Tuple

class LooseObjectStore:
    """
    Manages loose object storage in .git/objects/.

    Loose objects are individual zlib-compressed files,
    one per object, named by SHA-1 hash.
    """

    def __init__(self, git_dir: Path):
        """
        Initialize loose object store.

        Args:
            git_dir: Path to .git directory
        """
        self.objects_dir = git_dir / "objects"

    def _object_path(self, sha: str) -> Path:
        """Compute filesystem path for object."""
        if len(sha) != 40:
            raise ValueError(f"Invalid SHA length: {len(sha)}")
        return self.objects_dir / sha[:2] / sha[2:]

    def exists(self, sha: str) -> bool:
        """Check if object exists in store."""
        return self._object_path(sha).exists()

    def read(self, sha: str) -> bytes:
        """
        Read and decompress object.

        Args:
            sha: 40-character hex SHA-1

        Returns:
            Decompressed object data (with header)

        Raises:
            FileNotFoundError: Object doesn't exist
            zlib.error: Decompression failed
        """
        path = self._object_path(sha)
        compressed = path.read_bytes()
        data = zlib.decompress(compressed)

        # Verify SHA matches content
        import hashlib
        computed_sha = hashlib.sha1(data).hexdigest()
        if computed_sha != sha:
            raise ValueError(f"SHA mismatch: expected {sha}, got {computed_sha}")

        return data

    def write(self, sha: str, data: bytes) -> Path:
        """
        Compress and write object atomically.

        Args:
            sha: 40-character hex SHA-1
            data: Complete object data (with header)

        Returns:
            Path to written object

        Note:
            Write is atomic - uses temp file + rename
        """
        path = self._object_path(sha)

        # Skip if already exists (content-addressable = immutable)
        if path.exists():
            return path

        # Ensure directory exists
        path.parent.mkdir(parents=True, exist_ok=True)

        # Compress
        compressed = zlib.compress(data)

        # Atomic write: write to temp, then rename
        temp_path = path.with_suffix(".tmp")
        try:
            temp_path.write_bytes(compressed)
            temp_path.rename(path)
        except Exception:
            # Clean up temp file on failure
            temp_path.unlink(missing_ok=True)
            raise

        # Set read-only (objects are immutable)
        path.chmod(0o444)

        return path

    def delete(self, sha: str) -> bool:
        """
        Delete object (for garbage collection).

        Returns:
            True if deleted, False if didn't exist
        """
        path = self._object_path(sha)
        if path.exists():
            path.chmod(0o644)  # Make writable first
            path.unlink()
            # Clean up empty directory
            try:
                path.parent.rmdir()
            except OSError:
                pass  # Directory not empty
            return True
        return False

    def iter_objects(self) -> Iterable[str]:
        """Iterate over all object SHAs in store."""
        for subdir in self.objects_dir.iterdir():
            if len(subdir.name) != 2 or not subdir.is_dir():
                continue
            if subdir.name in ("info", "pack"):
                continue
            for obj_file in subdir.iterdir():
                if len(obj_file.name) == 38:
                    yield subdir.name + obj_file.name
```

---

## 3. Object Database

### 3.1 Purpose

High-level interface for object storage that:
- Abstracts storage backend (loose vs packed)
- Handles object parsing
- Provides convenient read/write methods

### 3.2 Implementation

```python
# gitpy/storage/database.py

from pathlib import Path
from typing import Optional, Union
import hashlib

from gitpy.objects import GitObject, parse_object, create_object_data
from gitpy.objects.blob import Blob
from gitpy.objects.tree import Tree
from gitpy.objects.commit import Commit
from gitpy.objects.tag import Tag
from .loose import LooseObjectStore

class ObjectDatabase:
    """
    High-level interface to Git object storage.

    Provides read/write access to Git objects with automatic
    serialization, compression, and SHA computation.
    """

    def __init__(self, git_dir: Path):
        """
        Initialize object database.

        Args:
            git_dir: Path to .git directory
        """
        self.git_dir = git_dir
        self.loose = LooseObjectStore(git_dir)

    def exists(self, sha: str) -> bool:
        """Check if object exists."""
        # Short SHA support
        if len(sha) < 40:
            return self._resolve_short_sha(sha) is not None
        return self.loose.exists(sha)

    def _resolve_short_sha(self, short_sha: str) -> Optional[str]:
        """
        Resolve abbreviated SHA to full SHA.

        Args:
            short_sha: Abbreviated SHA (minimum 4 chars)

        Returns:
            Full 40-char SHA or None if not found

        Raises:
            ValueError: If ambiguous (multiple matches)
        """
        if len(short_sha) < 4:
            raise ValueError("SHA prefix too short (minimum 4)")

        matches = []
        prefix = short_sha[:2]
        suffix_prefix = short_sha[2:]

        subdir = self.loose.objects_dir / prefix
        if subdir.exists():
            for obj_file in subdir.iterdir():
                if obj_file.name.startswith(suffix_prefix):
                    matches.append(prefix + obj_file.name)

        if len(matches) == 0:
            return None
        if len(matches) == 1:
            return matches[0]
        raise ValueError(f"Ambiguous SHA prefix: {short_sha} matches {len(matches)} objects")

    def read_raw(self, sha: str) -> bytes:
        """
        Read raw object data (decompressed, with header).

        Args:
            sha: Object SHA (full or abbreviated)

        Returns:
            Raw object bytes
        """
        if len(sha) < 40:
            full_sha = self._resolve_short_sha(sha)
            if full_sha is None:
                raise FileNotFoundError(f"Object not found: {sha}")
            sha = full_sha

        return self.loose.read(sha)

    def read(self, sha: str) -> GitObject:
        """
        Read and parse object.

        Args:
            sha: Object SHA (full or abbreviated)

        Returns:
            Parsed GitObject (Blob, Tree, Commit, or Tag)
        """
        data = self.read_raw(sha)
        _, obj = parse_object(data)
        return obj

    def read_blob(self, sha: str) -> Blob:
        """Read object as Blob."""
        obj = self.read(sha)
        if not isinstance(obj, Blob):
            raise TypeError(f"Expected blob, got {obj.type_name}")
        return obj

    def read_tree(self, sha: str) -> Tree:
        """Read object as Tree."""
        obj = self.read(sha)
        if not isinstance(obj, Tree):
            raise TypeError(f"Expected tree, got {obj.type_name}")
        return obj

    def read_commit(self, sha: str) -> Commit:
        """Read object as Commit."""
        obj = self.read(sha)
        if not isinstance(obj, Commit):
            raise TypeError(f"Expected commit, got {obj.type_name}")
        return obj

    def write(self, obj: GitObject) -> str:
        """
        Write object to storage.

        Args:
            obj: GitObject to write

        Returns:
            SHA-1 of written object
        """
        data = create_object_data(obj)
        sha = hashlib.sha1(data).hexdigest()
        self.loose.write(sha, data)
        return sha

    def hash_object(self, obj: GitObject, write: bool = True) -> str:
        """
        Compute SHA of object, optionally storing it.

        Args:
            obj: GitObject to hash
            write: If True, also write to storage

        Returns:
            SHA-1 hash
        """
        data = create_object_data(obj)
        sha = hashlib.sha1(data).hexdigest()

        if write:
            self.loose.write(sha, data)

        return sha

    def get_type(self, sha: str) -> str:
        """Get object type without full parse."""
        data = self.read_raw(sha)
        null_idx = data.index(b"\0")
        header = data[:null_idx].decode("ascii")
        type_name, _ = header.split(" ")
        return type_name

    def get_size(self, sha: str) -> int:
        """Get object size without full parse."""
        data = self.read_raw(sha)
        null_idx = data.index(b"\0")
        header = data[:null_idx].decode("ascii")
        _, size_str = header.split(" ")
        return int(size_str)
```

---

## 4. Repository Initialization

### 4.1 Directory Structure

A new Git repository requires:

```
.git/
├── HEAD                 # ref: refs/heads/main
├── config               # Repository config
├── description          # Repo description (for gitweb)
├── objects/
│   ├── info/
│   └── pack/
├── refs/
│   ├── heads/
│   └── tags/
├── info/
│   └── exclude          # Local gitignore
└── hooks/               # Git hooks (optional)
```

### 4.2 Implementation

```python
# gitpy/repository.py

from pathlib import Path
from typing import Optional
from .storage.database import ObjectDatabase

class Repository:
    """
    Represents a Git repository.

    Provides access to all repository components:
    objects, references, index, etc.
    """

    def __init__(self, path: Path, git_dir: Optional[Path] = None):
        """
        Open existing repository.

        Args:
            path: Working directory path
            git_dir: .git directory (default: path/.git)
        """
        self.worktree = path.resolve()
        self.git_dir = git_dir or (self.worktree / ".git")

        if not self.git_dir.exists():
            raise ValueError(f"Not a git repository: {path}")

        self.objects = ObjectDatabase(self.git_dir)

    @classmethod
    def init(cls, path: Path, bare: bool = False) -> "Repository":
        """
        Initialize a new repository.

        Args:
            path: Where to create repository
            bare: If True, create bare repository

        Returns:
            Newly created Repository
        """
        path = Path(path).resolve()

        if bare:
            git_dir = path
            worktree = None
        else:
            git_dir = path / ".git"
            worktree = path

        # Check not already a repo
        if git_dir.exists():
            raise ValueError(f"Already a git repository: {path}")

        # Create directory structure
        git_dir.mkdir(parents=True, exist_ok=True)

        # Create subdirectories
        (git_dir / "objects" / "info").mkdir(parents=True)
        (git_dir / "objects" / "pack").mkdir(parents=True)
        (git_dir / "refs" / "heads").mkdir(parents=True)
        (git_dir / "refs" / "tags").mkdir(parents=True)
        (git_dir / "info").mkdir(parents=True)

        # Create HEAD
        (git_dir / "HEAD").write_text("ref: refs/heads/main\n")

        # Create config
        config = """[core]
\trepositoryformatversion = 0
\tfilemode = true
\tbare = {}
""".format(str(bare).lower())
        (git_dir / "config").write_text(config)

        # Create description
        (git_dir / "description").write_text(
            "Unnamed repository; edit this file to name it.\n"
        )

        # Create info/exclude
        (git_dir / "info" / "exclude").write_text(
            "# git ls-files --others --exclude-from=.git/info/exclude\n"
        )

        return cls(path=worktree or path, git_dir=git_dir)

    @classmethod
    def find(cls, start_path: Optional[Path] = None) -> "Repository":
        """
        Find repository containing path.

        Searches up directory tree for .git directory.

        Args:
            start_path: Where to start search (default: cwd)

        Returns:
            Repository containing start_path

        Raises:
            ValueError: Not inside a repository
        """
        path = Path(start_path or Path.cwd()).resolve()

        while True:
            git_dir = path / ".git"
            if git_dir.is_dir():
                return cls(path=path, git_dir=git_dir)

            if git_dir.is_file():
                # Handle git worktrees: .git is file pointing to real git dir
                content = git_dir.read_text().strip()
                if content.startswith("gitdir: "):
                    real_git_dir = Path(content[8:])
                    if not real_git_dir.is_absolute():
                        real_git_dir = path / real_git_dir
                    return cls(path=path, git_dir=real_git_dir.resolve())

            parent = path.parent
            if parent == path:
                raise ValueError("Not a git repository (or any parent)")
            path = parent
```

---

## 5. Compression Utilities

### 5.1 Implementation

```python
# gitpy/storage/compression.py

import zlib
from typing import Tuple

# Default compression level (matches Git)
DEFAULT_LEVEL = zlib.Z_DEFAULT_COMPRESSION  # Usually 6

def compress(data: bytes, level: int = DEFAULT_LEVEL) -> bytes:
    """
    Compress data using zlib.

    Args:
        data: Raw bytes to compress
        level: Compression level (0-9, -1 for default)

    Returns:
        Compressed bytes
    """
    return zlib.compress(data, level)

def decompress(data: bytes) -> bytes:
    """
    Decompress zlib data.

    Args:
        data: Compressed bytes

    Returns:
        Decompressed bytes

    Raises:
        zlib.error: Invalid compressed data
    """
    return zlib.decompress(data)

def decompress_stream(data: bytes) -> Tuple[bytes, bytes]:
    """
    Decompress data, returning decompressed content and remaining bytes.

    Useful for packfiles where multiple compressed streams are concatenated.

    Args:
        data: Compressed bytes (possibly with trailing data)

    Returns:
        Tuple of (decompressed_content, remaining_bytes)
    """
    decompressor = zlib.decompressobj()
    content = decompressor.decompress(data)
    remaining = decompressor.unused_data
    return content, remaining
```

---

## 6. Test Cases

### 6.1 Loose Object Store Tests

```python
import pytest
from pathlib import Path
import tempfile

from gitpy.storage.loose import LooseObjectStore
from gitpy.objects.blob import Blob
from gitpy.objects import create_object_data

class TestLooseObjectStore:

    @pytest.fixture
    def store(self, tmp_path):
        git_dir = tmp_path / ".git"
        git_dir.mkdir()
        (git_dir / "objects").mkdir()
        return LooseObjectStore(git_dir)

    def test_write_and_read(self, store):
        """Write object and read it back."""
        blob = Blob(data=b"test content")
        data = create_object_data(blob)
        sha = blob.oid

        store.write(sha, data)

        assert store.exists(sha)
        assert store.read(sha) == data

    def test_path_computation(self, store):
        """SHA maps to correct path."""
        sha = "8ab686eafeb1f44702738c8b0f24f2567c36da6d"
        path = store._object_path(sha)

        assert path.parent.name == "8a"
        assert path.name == "b686eafeb1f44702738c8b0f24f2567c36da6d"

    def test_write_is_idempotent(self, store):
        """Writing same object twice is safe."""
        blob = Blob(data=b"test")
        data = create_object_data(blob)
        sha = blob.oid

        path1 = store.write(sha, data)
        path2 = store.write(sha, data)

        assert path1 == path2

    def test_sha_verification(self, store):
        """Reading corrupted object raises error."""
        blob = Blob(data=b"original")
        data = create_object_data(blob)
        sha = blob.oid

        store.write(sha, data)

        # Corrupt the file
        path = store._object_path(sha)
        path.chmod(0o644)
        import zlib
        corrupted = zlib.compress(b"blob 8\0corrupted")
        path.write_bytes(corrupted)

        with pytest.raises(ValueError, match="SHA mismatch"):
            store.read(sha)

    def test_delete(self, store):
        """Delete removes object."""
        blob = Blob(data=b"delete me")
        data = create_object_data(blob)
        sha = blob.oid

        store.write(sha, data)
        assert store.exists(sha)

        store.delete(sha)
        assert not store.exists(sha)
```

### 6.2 Object Database Tests

```python
class TestObjectDatabase:

    @pytest.fixture
    def db(self, tmp_path):
        repo = Repository.init(tmp_path)
        return repo.objects

    def test_write_and_read_blob(self, db):
        """Write blob and read back."""
        blob = Blob(data=b"hello world")
        sha = db.write(blob)

        result = db.read_blob(sha)
        assert result.data == b"hello world"

    def test_short_sha_resolution(self, db):
        """Short SHA resolves to full."""
        blob = Blob(data=b"unique content 12345")
        sha = db.write(blob)

        # Read with short SHA
        short = sha[:7]
        result = db.read_blob(short)
        assert result.data == b"unique content 12345"

    def test_type_checking(self, db):
        """Reading wrong type raises TypeError."""
        blob = Blob(data=b"not a tree")
        sha = db.write(blob)

        with pytest.raises(TypeError, match="Expected tree"):
            db.read_tree(sha)

    def test_get_type_and_size(self, db):
        """Can get type and size without full parse."""
        blob = Blob(data=b"12345")
        sha = db.write(blob)

        assert db.get_type(sha) == "blob"
        assert db.get_size(sha) == 5
```

### 6.3 Repository Init Tests

```python
class TestRepositoryInit:

    def test_init_creates_structure(self, tmp_path):
        """Init creates required directories and files."""
        repo = Repository.init(tmp_path / "myrepo")

        git_dir = tmp_path / "myrepo" / ".git"
        assert git_dir.exists()
        assert (git_dir / "objects").is_dir()
        assert (git_dir / "refs" / "heads").is_dir()
        assert (git_dir / "HEAD").read_text() == "ref: refs/heads/main\n"

    def test_init_bare(self, tmp_path):
        """Bare init creates repository in path itself."""
        repo = Repository.init(tmp_path / "bare.git", bare=True)

        assert (tmp_path / "bare.git" / "objects").is_dir()
        assert (tmp_path / "bare.git" / "HEAD").exists()

    def test_find_repository(self, tmp_path):
        """Find locates repository from subdirectory."""
        repo = Repository.init(tmp_path / "project")

        subdir = tmp_path / "project" / "src" / "deep"
        subdir.mkdir(parents=True)

        found = Repository.find(subdir)
        assert found.worktree == tmp_path / "project"
```

---

## 7. Acceptance Criteria

### 7.1 Functional Requirements

- [x] Objects are stored compressed in `.git/objects/XX/YYYY...`
- [x] Objects can be read back and decompressed correctly
- [x] SHA-1 is verified on read
- [x] Duplicate writes are safely skipped
- [x] Short SHA resolution works with minimum 4 characters
- [x] Ambiguous short SHA raises clear error
- [x] Repository can be initialized (normal and bare)
- [x] Repository can be found from subdirectory

### 7.2 Non-Functional Requirements

- [x] Atomic writes (temp file + rename)
- [x] Object files are read-only after creation
- [x] Compatible with real Git (can read/write same format)
- [x] No data loss on crash during write

### 7.3 Verification

```bash
# Verify gitpy can read Git's objects
git init test-repo && cd test-repo
echo "hello" | git hash-object -w --stdin
# gitpy should read this object

# Verify Git can read gitpy's objects
# After gitpy writes an object, git cat-file should work
git cat-file -p <sha>
```

---

## 8. File Structure

```
gitpy/
├── storage/
│   ├── __init__.py
│   ├── compression.py   # Zlib utilities
│   ├── database.py      # ObjectDatabase
│   └── loose.py         # LooseObjectStore
└── repository.py        # Repository class
```
