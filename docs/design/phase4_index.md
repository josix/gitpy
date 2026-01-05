# Phase 4: Index (Staging Area) - Design Specification

> **Status**: Draft
> **Author**: Domain Expert
> **Last Updated**: 2026-01-05
> **Dependencies**: Phase 1-3

## 1. Overview

The index (also called staging area or cache) is the bridge between the working directory and the repository. It holds a snapshot of the content that will go into the next commit.

### 1.1 Design Goals

- **Performance**: Fast status checking via cached metadata
- **Atomicity**: Index updates are atomic
- **Accuracy**: Precise tracking of file states
- **Compatibility**: Binary format matches Git

### 1.2 Index Location

```
.git/index        # Main index file
.git/index.lock   # Lock file during updates
```

---

## 2. Index File Format

### 2.1 Overall Structure

```
+------------------+
| Header (12 bytes)|
+------------------+
| Entry 1          |
+------------------+
| Entry 2          |
+------------------+
| ...              |
+------------------+
| Extensions       |
+------------------+
| SHA-1 (20 bytes) |
+------------------+
```

### 2.2 Header Format

```c
struct index_header {
    char signature[4];    // "DIRC" (dircache)
    uint32_t version;     // 2, 3, or 4
    uint32_t entries;     // Number of entries
};
```

All integers are network byte order (big-endian).

### 2.3 Entry Format (Version 2)

```c
struct index_entry {
    // File metadata (for change detection)
    uint32_t ctime_sec;   // Creation time seconds
    uint32_t ctime_nsec;  // Creation time nanoseconds
    uint32_t mtime_sec;   // Modification time seconds
    uint32_t mtime_nsec;  // Modification time nanoseconds
    uint32_t dev;         // Device ID
    uint32_t ino;         // Inode number
    uint32_t mode;        // File mode
    uint32_t uid;         // User ID
    uint32_t gid;         // Group ID
    uint32_t file_size;   // File size in bytes

    // Object reference
    char sha1[20];        // SHA-1 of blob content

    // Flags
    uint16_t flags;       // See below

    // Path (variable length)
    char path[];          // NUL-terminated, padded to 8-byte boundary
};
```

### 2.4 Flags Field

```
15 14 13 12 11 10  9  8  7  6  5  4  3  2  1  0
|  |  |  |  |______________________________________|
|  |  |  |                  |
|  |  |  |                  +-- name length (12 bits, max 0xFFF)
|  |  |  +-- extended flag (version 3+)
|  |  +-- skip-worktree (sparse checkout)
|  +-- assume-valid
+-- (reserved)
```

If name length > 0xFFF, value is 0xFFF and actual length must be found by scanning for NUL.

### 2.5 Entry Mode

| Mode | Description |
|------|-------------|
| `0100644` | Regular file |
| `0100755` | Executable file |
| `0120000` | Symbolic link |
| `0160000` | Gitlink (submodule) |

Mode is stored as 32-bit integer: `(type << 12) | permissions`

### 2.6 Padding

Each entry is padded with 1-8 NUL bytes to align to 8-byte boundary:

```
entry_length = 62 + path_length + 1 (NUL terminator)
padding = 8 - (entry_length % 8)
if padding == 0:
    padding = 8
```

### 2.7 Checksum

The final 20 bytes are SHA-1 of all preceding content.

---

## 3. Implementation

### 3.1 Index Entry Class

```python
# gitpy/index/entry.py

from dataclasses import dataclass
from typing import Optional
import os
import stat as stat_module

@dataclass
class IndexEntry:
    """
    Represents a single entry in the Git index.

    Tracks a file's identity, content hash, and metadata
    for efficient change detection.
    """

    # Timestamps (for change detection)
    ctime_s: int    # Creation time seconds
    ctime_ns: int   # Creation time nanoseconds
    mtime_s: int    # Modification time seconds
    mtime_ns: int   # Modification time nanoseconds

    # File identity
    dev: int        # Device ID
    ino: int        # Inode number
    mode: int       # File mode (type + permissions)
    uid: int        # User ID
    gid: int        # Group ID
    size: int       # File size in bytes

    # Content
    sha: str        # 40-char hex SHA-1 of blob

    # Flags
    flags: int      # Flag bits
    path: str       # File path (relative to repo root)

    # Extended flags (version 3+)
    extended_flags: int = 0

    @property
    def stage(self) -> int:
        """
        Merge stage (0-3).

        0 = normal
        1 = base
        2 = ours
        3 = theirs
        """
        return (self.flags >> 12) & 0x3

    @property
    def name_length(self) -> int:
        """Stored name length (may be truncated to 0xFFF)."""
        return self.flags & 0xFFF

    @property
    def assume_valid(self) -> bool:
        """Skip file in status checks."""
        return bool(self.flags & 0x8000)

    @property
    def is_regular_file(self) -> bool:
        return (self.mode >> 12) == 0o10

    @property
    def is_executable(self) -> bool:
        return self.mode == 0o100755

    @property
    def is_symlink(self) -> bool:
        return (self.mode >> 12) == 0o12

    @classmethod
    def from_path(
        cls,
        path: str,
        sha: str,
        worktree: "Path",
        stage: int = 0
    ) -> "IndexEntry":
        """
        Create index entry from file path.

        Args:
            path: Relative path within repository
            sha: SHA-1 of file contents
            worktree: Repository working directory
            stage: Merge stage (0 for normal)
        """
        full_path = worktree / path
        st = full_path.stat()

        # Determine mode
        if stat_module.S_ISLNK(st.st_mode):
            mode = 0o120000
        elif st.st_mode & stat_module.S_IXUSR:
            mode = 0o100755
        else:
            mode = 0o100644

        # Calculate flags
        name_len = min(len(path), 0xFFF)
        flags = (stage << 12) | name_len

        return cls(
            ctime_s=int(st.st_ctime),
            ctime_ns=int((st.st_ctime % 1) * 1e9),
            mtime_s=int(st.st_mtime),
            mtime_ns=int((st.st_mtime % 1) * 1e9),
            dev=st.st_dev,
            ino=st.st_ino,
            mode=mode,
            uid=st.st_uid,
            gid=st.st_gid,
            size=st.st_size,
            sha=sha,
            flags=flags,
            path=path,
        )

    def matches_stat(self, st: os.stat_result) -> bool:
        """
        Check if file stat matches cached metadata.

        Used for fast "has file changed?" check.
        Returns True if file MIGHT be unchanged (needs content check if True).
        Returns False if file has DEFINITELY changed.
        """
        # Check size first (fast rejection)
        if st.st_size != self.size:
            return False

        # Check mtime
        mtime_s = int(st.st_mtime)
        mtime_ns = int((st.st_mtime % 1) * 1e9)
        if mtime_s != self.mtime_s or mtime_ns != self.mtime_ns:
            return False

        # Check inode (file replacement detection)
        if st.st_ino != self.ino:
            return False

        # If we get here, file is probably unchanged
        # (could still verify content hash for certainty)
        return True
```

### 3.2 Index Class

```python
# gitpy/index/index.py

from pathlib import Path
from typing import Dict, List, Optional, Iterator
import struct
import hashlib

from .entry import IndexEntry

INDEX_SIGNATURE = b"DIRC"
INDEX_VERSION = 2

class Index:
    """
    Represents the Git index (staging area).

    The index is a flat list of file entries, sorted by path.
    It serves as a cache between working directory and repository.
    """

    def __init__(self):
        self.entries: Dict[str, IndexEntry] = {}
        self.version: int = INDEX_VERSION

    def __len__(self) -> int:
        return len(self.entries)

    def __iter__(self) -> Iterator[IndexEntry]:
        """Iterate entries in sorted order."""
        for path in sorted(self.entries.keys()):
            yield self.entries[path]

    def __contains__(self, path: str) -> bool:
        return path in self.entries

    def get(self, path: str) -> Optional[IndexEntry]:
        """Get entry by path."""
        return self.entries.get(path)

    def add(self, entry: IndexEntry) -> None:
        """Add or update entry."""
        self.entries[entry.path] = entry

    def remove(self, path: str) -> bool:
        """Remove entry by path."""
        if path in self.entries:
            del self.entries[path]
            return True
        return False

    def clear(self) -> None:
        """Remove all entries."""
        self.entries.clear()

    # =========== Serialization ===========

    def to_bytes(self) -> bytes:
        """Serialize index to bytes."""
        # Sort entries by path
        sorted_entries = sorted(self.entries.values(), key=lambda e: e.path)

        # Build content
        content = b""

        # Header
        content += INDEX_SIGNATURE
        content += struct.pack(">I", self.version)
        content += struct.pack(">I", len(sorted_entries))

        # Entries
        for entry in sorted_entries:
            content += self._serialize_entry(entry)

        # Checksum
        checksum = hashlib.sha1(content).digest()
        content += checksum

        return content

    def _serialize_entry(self, entry: IndexEntry) -> bytes:
        """Serialize single entry."""
        data = b""

        # Fixed fields (62 bytes)
        data += struct.pack(">I", entry.ctime_s)
        data += struct.pack(">I", entry.ctime_ns)
        data += struct.pack(">I", entry.mtime_s)
        data += struct.pack(">I", entry.mtime_ns)
        data += struct.pack(">I", entry.dev)
        data += struct.pack(">I", entry.ino)
        data += struct.pack(">I", entry.mode)
        data += struct.pack(">I", entry.uid)
        data += struct.pack(">I", entry.gid)
        data += struct.pack(">I", entry.size)
        data += bytes.fromhex(entry.sha)  # 20 bytes
        data += struct.pack(">H", entry.flags)

        # Path with NUL terminator
        path_bytes = entry.path.encode("utf-8") + b"\x00"
        data += path_bytes

        # Padding to 8-byte boundary
        entry_len = 62 + len(path_bytes)
        padding = 8 - (entry_len % 8)
        if padding == 0:
            padding = 8
        data += b"\x00" * padding

        return data

    @classmethod
    def from_bytes(cls, data: bytes) -> "Index":
        """Parse index from bytes."""
        index = cls()

        # Verify checksum
        stored_checksum = data[-20:]
        computed_checksum = hashlib.sha1(data[:-20]).digest()
        if stored_checksum != computed_checksum:
            raise ValueError("Index checksum mismatch")

        # Parse header
        if data[:4] != INDEX_SIGNATURE:
            raise ValueError("Invalid index signature")

        version = struct.unpack(">I", data[4:8])[0]
        if version not in (2, 3, 4):
            raise ValueError(f"Unsupported index version: {version}")

        index.version = version
        num_entries = struct.unpack(">I", data[8:12])[0]

        # Parse entries
        pos = 12
        for _ in range(num_entries):
            entry, bytes_read = cls._parse_entry(data, pos, version)
            index.add(entry)
            pos += bytes_read

        return index

    @classmethod
    def _parse_entry(cls, data: bytes, pos: int, version: int) -> tuple:
        """Parse single entry, return (entry, bytes_consumed)."""
        start_pos = pos

        # Fixed fields
        ctime_s = struct.unpack(">I", data[pos:pos+4])[0]; pos += 4
        ctime_ns = struct.unpack(">I", data[pos:pos+4])[0]; pos += 4
        mtime_s = struct.unpack(">I", data[pos:pos+4])[0]; pos += 4
        mtime_ns = struct.unpack(">I", data[pos:pos+4])[0]; pos += 4
        dev = struct.unpack(">I", data[pos:pos+4])[0]; pos += 4
        ino = struct.unpack(">I", data[pos:pos+4])[0]; pos += 4
        mode = struct.unpack(">I", data[pos:pos+4])[0]; pos += 4
        uid = struct.unpack(">I", data[pos:pos+4])[0]; pos += 4
        gid = struct.unpack(">I", data[pos:pos+4])[0]; pos += 4
        size = struct.unpack(">I", data[pos:pos+4])[0]; pos += 4
        sha = data[pos:pos+20].hex(); pos += 20
        flags = struct.unpack(">H", data[pos:pos+2])[0]; pos += 2

        # Path (find NUL terminator)
        nul_pos = data.index(b"\x00", pos)
        path = data[pos:nul_pos].decode("utf-8")
        pos = nul_pos + 1

        # Skip padding (align to 8 bytes)
        entry_len = pos - start_pos
        padding = 8 - (entry_len % 8)
        if padding < 8:
            pos += padding

        entry = IndexEntry(
            ctime_s=ctime_s,
            ctime_ns=ctime_ns,
            mtime_s=mtime_s,
            mtime_ns=mtime_ns,
            dev=dev,
            ino=ino,
            mode=mode,
            uid=uid,
            gid=gid,
            size=size,
            sha=sha,
            flags=flags,
            path=path,
        )

        return entry, pos - start_pos


class IndexFile:
    """Manages index file I/O with locking."""

    def __init__(self, git_dir: Path):
        self.index_path = git_dir / "index"
        self.lock_path = git_dir / "index.lock"

    def read(self) -> Index:
        """Read index from file."""
        if not self.index_path.exists():
            return Index()
        data = self.index_path.read_bytes()
        return Index.from_bytes(data)

    def write(self, index: Index) -> None:
        """Write index atomically with lock."""
        data = index.to_bytes()

        # Acquire lock
        try:
            # Exclusive create (fails if lock exists)
            fd = os.open(
                str(self.lock_path),
                os.O_WRONLY | os.O_CREAT | os.O_EXCL,
                0o644
            )
        except FileExistsError:
            raise RuntimeError("Index is locked by another process")

        try:
            os.write(fd, data)
            os.close(fd)
            self.lock_path.rename(self.index_path)
        except Exception:
            os.close(fd)
            self.lock_path.unlink(missing_ok=True)
            raise

    def exists(self) -> bool:
        """Check if index file exists."""
        return self.index_path.exists()
```

---

## 4. Index Operations

### 4.1 Building Index from Tree

```python
# gitpy/index/operations.py

from pathlib import Path
from typing import Set

from .index import Index, IndexEntry
from gitpy.objects.tree import Tree, TreeEntry
from gitpy.storage.database import ObjectDatabase

def read_tree(
    index: Index,
    tree_sha: str,
    db: ObjectDatabase,
    prefix: str = ""
) -> None:
    """
    Populate index from a tree object.

    This is the core of `git read-tree` and `git checkout`.

    Args:
        index: Index to populate
        tree_sha: SHA of tree to read
        db: Object database
        prefix: Path prefix for entries
    """
    tree = db.read_tree(tree_sha)

    for entry in tree.entries:
        path = f"{prefix}{entry.name}" if prefix else entry.name

        if entry.is_tree:
            # Recurse into subdirectory
            read_tree(index, entry.sha, db, prefix=f"{path}/")
        else:
            # Add file entry
            # Note: We use minimal metadata since we don't have stat info
            index_entry = IndexEntry(
                ctime_s=0, ctime_ns=0,
                mtime_s=0, mtime_ns=0,
                dev=0, ino=0,
                mode=int(entry.mode, 8),
                uid=0, gid=0,
                size=0,
                sha=entry.sha,
                flags=min(len(path), 0xFFF),
                path=path,
            )
            index.add(index_entry)
```

### 4.2 Building Tree from Index

```python
def write_tree(index: Index, db: ObjectDatabase) -> str:
    """
    Create tree objects from index.

    This is the core of `git write-tree`.

    Args:
        index: Index to convert
        db: Object database for writing trees

    Returns:
        SHA of root tree
    """
    return _write_tree_recursive(index, db, "")

def _write_tree_recursive(
    index: Index,
    db: ObjectDatabase,
    prefix: str
) -> str:
    """Recursively build tree for directory."""
    from gitpy.objects.tree import Tree, TreeEntry

    entries = []
    seen_dirs: Set[str] = set()

    for index_entry in index:
        path = index_entry.path

        # Skip if not under our prefix
        if prefix and not path.startswith(prefix):
            continue

        # Get relative path
        rel_path = path[len(prefix):] if prefix else path

        # Check if this is a direct child or in subdirectory
        if "/" in rel_path:
            # Entry is in a subdirectory
            subdir = rel_path.split("/")[0]
            if subdir not in seen_dirs:
                seen_dirs.add(subdir)
                # Recurse to build subtree
                subtree_sha = _write_tree_recursive(
                    index, db, f"{prefix}{subdir}/"
                )
                entries.append(TreeEntry(
                    mode="40000",
                    name=subdir,
                    sha=subtree_sha
                ))
        else:
            # Direct child file
            mode = oct(index_entry.mode)[2:]  # Remove "0o" prefix
            entries.append(TreeEntry(
                mode=mode,
                name=rel_path,
                sha=index_entry.sha
            ))

    # Create and store tree
    tree = Tree(entries=entries)
    return db.write(tree)
```

### 4.3 Comparing Index with Working Directory

```python
from enum import Enum
from dataclasses import dataclass
from typing import List, Tuple

class FileStatus(Enum):
    """Status of a file in working directory."""
    UNMODIFIED = "unmodified"
    MODIFIED = "modified"
    DELETED = "deleted"
    UNTRACKED = "untracked"
    ADDED = "added"  # In index, not in HEAD

@dataclass
class StatusEntry:
    """Status of a single file."""
    path: str
    index_status: FileStatus    # Index vs HEAD
    worktree_status: FileStatus  # Worktree vs Index

def get_status(
    index: Index,
    head_tree_sha: Optional[str],
    worktree: Path,
    db: ObjectDatabase
) -> List[StatusEntry]:
    """
    Compare index and working directory.

    Returns list of files with their status.
    """
    results = []

    # Build set of all paths
    all_paths = set(index.entries.keys())

    # Add paths from HEAD tree
    head_paths = set()
    if head_tree_sha:
        head_index = Index()
        read_tree(head_index, head_tree_sha, db)
        head_paths = set(head_index.entries.keys())
        all_paths.update(head_paths)

    # Add paths from working directory
    for path in worktree.rglob("*"):
        if path.is_file() and ".git" not in path.parts:
            rel_path = str(path.relative_to(worktree))
            all_paths.add(rel_path)

    # Check each path
    for path in sorted(all_paths):
        index_entry = index.get(path)
        head_entry = head_index.get(path) if head_tree_sha else None
        worktree_path = worktree / path

        # Determine index status (staged changes)
        if index_entry and head_entry:
            if index_entry.sha == head_entry.sha:
                index_status = FileStatus.UNMODIFIED
            else:
                index_status = FileStatus.MODIFIED
        elif index_entry and not head_entry:
            index_status = FileStatus.ADDED
        elif head_entry and not index_entry:
            index_status = FileStatus.DELETED
        else:
            index_status = FileStatus.UNTRACKED

        # Determine worktree status (unstaged changes)
        if index_entry:
            if not worktree_path.exists():
                worktree_status = FileStatus.DELETED
            elif _file_modified(index_entry, worktree_path, db):
                worktree_status = FileStatus.MODIFIED
            else:
                worktree_status = FileStatus.UNMODIFIED
        else:
            if worktree_path.exists():
                worktree_status = FileStatus.UNTRACKED
            else:
                worktree_status = FileStatus.UNMODIFIED

        # Only include if something changed
        if (index_status != FileStatus.UNMODIFIED or
            worktree_status != FileStatus.UNMODIFIED):
            results.append(StatusEntry(
                path=path,
                index_status=index_status,
                worktree_status=worktree_status
            ))

    return results

def _file_modified(entry: IndexEntry, path: Path, db: ObjectDatabase) -> bool:
    """Check if file differs from index entry."""
    st = path.stat()

    # Fast path: check cached stat data
    if entry.matches_stat(st):
        return False

    # Slow path: compare content
    from gitpy.objects.blob import Blob
    current_blob = Blob.from_file(str(path))
    return current_blob.oid != entry.sha
```

---

## 5. Merge Conflicts

### 5.1 Conflict Stages

During a merge conflict, multiple versions of a file exist:

| Stage | Meaning |
|-------|---------|
| 0 | Normal (no conflict) |
| 1 | Common ancestor (base) |
| 2 | Current branch (ours) |
| 3 | Merged branch (theirs) |

### 5.2 Implementation

```python
def has_conflicts(index: Index) -> bool:
    """Check if index has unresolved conflicts."""
    return any(e.stage != 0 for e in index)

def get_conflicts(index: Index) -> Dict[str, List[IndexEntry]]:
    """
    Get conflicted entries grouped by path.

    Returns dict mapping path to list of entries (stages 1-3).
    """
    conflicts = {}
    for entry in index:
        if entry.stage != 0:
            if entry.path not in conflicts:
                conflicts[entry.path] = []
            conflicts[entry.path].append(entry)
    return conflicts

def add_conflict(
    index: Index,
    path: str,
    base: Optional[IndexEntry],
    ours: Optional[IndexEntry],
    theirs: Optional[IndexEntry]
) -> None:
    """Add conflict entries for a path."""
    # Remove any stage-0 entry
    index.remove(path)

    # Add conflict entries
    if base:
        base.flags = (base.flags & 0x0FFF) | (1 << 12)
        index.add(base)
    if ours:
        ours.flags = (ours.flags & 0x0FFF) | (2 << 12)
        index.add(ours)
    if theirs:
        theirs.flags = (theirs.flags & 0x0FFF) | (3 << 12)
        index.add(theirs)

def resolve_conflict(index: Index, path: str, sha: str, mode: int) -> None:
    """Resolve conflict by setting stage-0 entry."""
    # Remove all conflict entries for this path
    to_remove = [e.path for e in index if e.path == path and e.stage != 0]
    for p in to_remove:
        index.remove(p)

    # Add resolved entry at stage 0
    entry = IndexEntry(
        ctime_s=0, ctime_ns=0, mtime_s=0, mtime_ns=0,
        dev=0, ino=0, mode=mode, uid=0, gid=0, size=0,
        sha=sha, flags=min(len(path), 0xFFF), path=path
    )
    index.add(entry)
```

---

## 6. Test Cases

### 6.1 Index Serialization

```python
class TestIndexSerialization:

    def test_empty_index(self):
        """Empty index serializes correctly."""
        index = Index()
        data = index.to_bytes()

        # Verify header
        assert data[:4] == b"DIRC"
        version = struct.unpack(">I", data[4:8])[0]
        count = struct.unpack(">I", data[8:12])[0]
        assert version == 2
        assert count == 0

    def test_roundtrip(self):
        """Serialize and deserialize preserves entries."""
        index = Index()
        entry = IndexEntry(
            ctime_s=1234567890, ctime_ns=123456789,
            mtime_s=1234567890, mtime_ns=123456789,
            dev=16777220, ino=12345678,
            mode=0o100644, uid=501, gid=20,
            size=1234,
            sha="a" * 40,
            flags=8,
            path="test.txt"
        )
        index.add(entry)

        data = index.to_bytes()
        restored = Index.from_bytes(data)

        assert len(restored) == 1
        assert "test.txt" in restored
        assert restored.get("test.txt").sha == "a" * 40

    def test_checksum_validation(self):
        """Corrupted checksum is detected."""
        index = Index()
        index.add(IndexEntry(
            ctime_s=0, ctime_ns=0, mtime_s=0, mtime_ns=0,
            dev=0, ino=0, mode=0o100644, uid=0, gid=0, size=0,
            sha="a" * 40, flags=4, path="file"
        ))

        data = bytearray(index.to_bytes())
        data[-1] ^= 0xFF  # Corrupt checksum

        with pytest.raises(ValueError, match="checksum"):
            Index.from_bytes(bytes(data))

    def test_sorting(self):
        """Entries are sorted by path."""
        index = Index()
        for path in ["c.txt", "a.txt", "b.txt"]:
            index.add(IndexEntry(
                ctime_s=0, ctime_ns=0, mtime_s=0, mtime_ns=0,
                dev=0, ino=0, mode=0o100644, uid=0, gid=0, size=0,
                sha="a" * 40, flags=len(path), path=path
            ))

        paths = [e.path for e in index]
        assert paths == ["a.txt", "b.txt", "c.txt"]
```

### 6.2 Git Compatibility

```python
class TestGitCompatibility:

    def test_read_git_index(self, git_repo):
        """Can read index created by Git."""
        # Create file and stage with real git
        (git_repo / "test.txt").write_text("hello")
        subprocess.run(["git", "add", "test.txt"], cwd=git_repo)

        # Read with gitpy
        index_file = IndexFile(git_repo / ".git")
        index = index_file.read()

        assert "test.txt" in index
        entry = index.get("test.txt")
        assert entry.mode == 0o100644

    def test_write_git_readable(self, git_repo):
        """Git can read index created by gitpy."""
        # Create index with gitpy
        index = Index()
        blob = Blob(data=b"hello\n")
        sha = repo.objects.write(blob)

        index.add(IndexEntry(
            ctime_s=0, ctime_ns=0, mtime_s=0, mtime_ns=0,
            dev=0, ino=0, mode=0o100644, uid=0, gid=0, size=6,
            sha=sha, flags=8, path="test.txt"
        ))

        index_file = IndexFile(git_repo / ".git")
        index_file.write(index)

        # Verify with git
        result = subprocess.run(
            ["git", "ls-files", "--stage"],
            cwd=git_repo,
            capture_output=True,
            text=True
        )
        assert "test.txt" in result.stdout
```

---

## 7. Acceptance Criteria

### 7.1 Functional Requirements

- [ ] Parse Git index file (version 2)
- [ ] Write Git-compatible index file
- [ ] Checksum validation on read
- [ ] Atomic writes with lock file
- [ ] Entry metadata caching for fast status
- [ ] read_tree populates index from tree
- [ ] write_tree creates tree from index
- [ ] Merge conflict stages (1-3) supported

### 7.2 Non-Functional Requirements

- [ ] Binary compatible with Git
- [ ] Lock file prevents concurrent writes
- [ ] Efficient stat caching

### 7.3 Verification

```bash
# Verify gitpy can read Git's index
git init test && cd test
echo "test" > file.txt
git add file.txt
# gitpy should read this index

# Verify Git can read gitpy's index
# After gitpy writes index:
git ls-files --stage
git status
```

---

## 8. File Structure

```
gitpy/
└── index/
    ├── __init__.py
    ├── entry.py         # IndexEntry class
    ├── index.py         # Index, IndexFile classes
    └── operations.py    # read_tree, write_tree, status
```
