"""Index and IndexFile classes for the Git staging area.

The binary format is Git version 2 compatible. Every entry is padded with
NUL bytes so that its total size is a multiple of 8. A SHA-1 checksum over
all header+entry bytes is appended as the final 20 bytes.
"""

import hashlib
import os
import struct
from collections.abc import Iterator
from pathlib import Path
from typing import Self

from .entry import IndexEntry

INDEX_SIGNATURE: bytes = b"DIRC"
INDEX_VERSION: int = 2

# Byte length of the fixed-size fields in each entry (before the path).
# 10 × uint32 (40 bytes) + 20 bytes SHA + 1 × uint16 (2 bytes) = 62 bytes.
_FIXED_ENTRY_BYTES: int = 62


def _entry_padding(path_bytes_with_nul: bytes) -> int:
    """Return the number of NUL padding bytes required after the path.

    The Git index format requires that each entry (fixed 62-byte header plus
    the NUL-terminated path) occupies a number of bytes that is a multiple of
    8.  The NUL terminator is already included in *path_bytes_with_nul*, so
    this function returns 0 when the total is already aligned, or the number
    of extra NUL bytes needed to reach the next 8-byte boundary.

    Unlike some descriptions of the format, Git does *not* force an extra 8
    bytes when the length is already a multiple of 8 — the NUL terminator
    itself serves as the only required padding in that case.

    Args:
        path_bytes_with_nul: Path encoded to UTF-8 with the NUL terminator
            already appended.

    Returns:
        Number of additional NUL bytes to write (0–7).
    """
    entry_len = _FIXED_ENTRY_BYTES + len(path_bytes_with_nul)
    remainder = entry_len % 8
    return 0 if remainder == 0 else (8 - remainder)


class Index:
    """The Git index (staging area).

    Entries are stored in a dict keyed by ``(path, stage)`` to support merge
    conflict stages (0 = normal, 1–3 = conflict stages). Iteration yields
    all entries sorted by path then stage, matching Git's wire format.

    Attributes:
        entries: Mapping from ``(path, stage)`` to IndexEntry.
        version: Index format version (2 by default).
    """

    def __init__(self) -> None:
        """Create an empty index at version 2."""
        self.entries: dict[tuple[str, int], IndexEntry] = {}
        self.version: int = INDEX_VERSION

    # ------------------------------------------------------------------
    # Collection protocol
    # ------------------------------------------------------------------

    def __len__(self) -> int:
        """Return the number of staged entries."""
        return len(self.entries)

    def __iter__(self) -> Iterator[IndexEntry]:
        """Yield entries sorted by path then stage (Git-canonical order)."""
        for key in sorted(self.entries):
            yield self.entries[key]

    def __contains__(self, path: object) -> bool:
        """Return True when any entry for *path* (stage 0) is in the index."""
        return (path, 0) in self.entries

    # ------------------------------------------------------------------
    # Mutation helpers
    # ------------------------------------------------------------------

    def get(self, path: str, stage: int = 0) -> IndexEntry | None:
        """Return the entry for (*path*, *stage*), or None if absent."""
        return self.entries.get((path, stage))

    def add(self, entry: IndexEntry) -> None:
        """Add or replace the entry keyed by ``(entry.path, entry.stage)``."""
        self.entries[(entry.path, entry.stage)] = entry

    def remove(self, path: str, stage: int | None = None) -> bool:
        """Remove entries for *path*.

        When *stage* is given, only that specific stage is removed.
        When *stage* is None, all stages for *path* are removed.

        Returns:
            True if at least one entry was removed.
        """
        if stage is not None:
            key = (path, stage)
            if key in self.entries:
                del self.entries[key]
                return True
            return False

        # Remove all stages.
        keys = [k for k in self.entries if k[0] == path]
        for k in keys:
            del self.entries[k]
        return bool(keys)

    def clear(self) -> None:
        """Remove all entries."""
        self.entries.clear()

    # ------------------------------------------------------------------
    # Serialisation
    # ------------------------------------------------------------------

    def to_bytes(self) -> bytes:
        """Serialise the index to a Git-compatible byte string.

        Returns:
            Bytes containing header, entries, and trailing SHA-1 checksum.
        """
        sorted_entries = sorted(self.entries.values(), key=lambda e: (e.path, e.stage))

        parts: list[bytes] = []
        parts.append(INDEX_SIGNATURE)
        parts.append(struct.pack(">I", self.version))
        parts.append(struct.pack(">I", len(sorted_entries)))

        for entry in sorted_entries:
            parts.append(_serialize_entry(entry))

        content = b"".join(parts)
        checksum = hashlib.sha1(content, usedforsecurity=False).digest()
        return content + checksum

    @classmethod
    def from_bytes(cls, data: bytes) -> Self:
        """Parse an index from raw bytes.

        Args:
            data: Full contents of a .git/index file.

        Returns:
            A populated Index instance.

        Raises:
            ValueError: If the checksum is wrong, the signature is invalid,
                or the version is unsupported.
        """
        if len(data) < 32:
            raise ValueError("Index data too short")

        stored_checksum = data[-20:]
        computed_checksum = hashlib.sha1(data[:-20], usedforsecurity=False).digest()
        if stored_checksum != computed_checksum:
            raise ValueError("Index checksum mismatch: file may be corrupt")

        if data[:4] != INDEX_SIGNATURE:
            raise ValueError(
                f"Invalid index signature: expected DIRC, got {data[:4]!r}"
            )

        version = struct.unpack(">I", data[4:8])[0]
        if version not in (2, 3, 4):
            raise ValueError(f"Unsupported index version: {version}")

        num_entries = struct.unpack(">I", data[8:12])[0]

        index = cls()
        index.version = version

        pos = 12
        for _ in range(num_entries):
            entry, consumed = _parse_entry(data, pos)
            index.add(entry)
            pos += consumed

        return index


class IndexFile:
    """Manages .git/index with atomic write semantics.

    Writes use an exclusive-create lock file that is then renamed over
    the real index, so a crash during write never leaves a partial file.

    Attributes:
        index_path: Path to the .git/index file.
        lock_path: Path to the .git/index.lock file.
    """

    def __init__(self, git_dir: Path) -> None:
        """Initialise paths for *git_dir*.

        Args:
            git_dir: Absolute path to the .git directory.
        """
        self.index_path = git_dir / "index"
        self.lock_path = git_dir / "index.lock"

    def read(self) -> Index:
        """Read and parse the index file.

        Returns an empty Index if the file does not exist yet.

        Returns:
            Parsed Index.

        Raises:
            ValueError: If the on-disk file is corrupt.
        """
        if not self.index_path.exists():
            return Index()
        data = self.index_path.read_bytes()
        return Index.from_bytes(data)

    def write(self, index: Index) -> None:
        """Write *index* atomically using a lock file.

        Args:
            index: Index to persist.

        Raises:
            RuntimeError: If a lock file already exists (concurrent write).
        """
        data = index.to_bytes()

        try:
            fd = os.open(
                str(self.lock_path),
                os.O_WRONLY | os.O_CREAT | os.O_EXCL,
                0o644,
            )
        except FileExistsError as exc:
            raise RuntimeError("Index is locked by another process") from exc

        try:
            os.write(fd, data)
            os.close(fd)
            self.lock_path.rename(self.index_path)
        except Exception:
            os.close(fd)
            self.lock_path.unlink(missing_ok=True)
            raise

    def exists(self) -> bool:
        """Return True when the .git/index file exists."""
        return self.index_path.exists()


# ---------------------------------------------------------------------------
# Private serialisation helpers (module-level so they can be tested directly)
# ---------------------------------------------------------------------------


def _serialize_entry(entry: IndexEntry) -> bytes:
    """Serialise one IndexEntry to bytes (without checksum).

    The layout is:
      10 × big-endian uint32  (ctime_s, ctime_ns, mtime_s, mtime_ns,
                                dev, ino, mode, uid, gid, size)
      20 bytes  SHA-1 binary
       2 bytes  flags (big-endian uint16)
       N bytes  path encoded UTF-8
       1 byte   NUL terminator
       P bytes  NUL padding so total entry length is multiple of 8

    Args:
        entry: The IndexEntry to serialise.

    Returns:
        Binary representation of the entry.
    """
    fixed = struct.pack(
        ">IIIIIIIIII",
        entry.ctime_s,
        entry.ctime_ns,
        entry.mtime_s,
        entry.mtime_ns,
        entry.dev & 0xFFFFFFFF,
        entry.ino & 0xFFFFFFFF,
        entry.mode,
        entry.uid & 0xFFFFFFFF,
        entry.gid & 0xFFFFFFFF,
        entry.size,
    )
    sha_bytes = bytes.fromhex(entry.sha)
    flags_bytes = struct.pack(">H", entry.flags)

    path_bytes_with_nul = entry.path.encode("utf-8") + b"\x00"
    padding = _entry_padding(path_bytes_with_nul)

    return fixed + sha_bytes + flags_bytes + path_bytes_with_nul + b"\x00" * padding


def _parse_entry(data: bytes, pos: int) -> tuple[IndexEntry, int]:
    """Parse one IndexEntry starting at *pos* in *data*.

    Args:
        data: Full index bytes.
        pos: Byte offset of the start of this entry.

    Returns:
        Tuple of (IndexEntry, bytes_consumed).
    """
    start = pos

    (
        ctime_s,
        ctime_ns,
        mtime_s,
        mtime_ns,
        dev,
        ino,
        mode,
        uid,
        gid,
        size,
    ) = struct.unpack(">IIIIIIIIII", data[pos : pos + 40])
    pos += 40

    sha = data[pos : pos + 20].hex()
    pos += 20

    (flags,) = struct.unpack(">H", data[pos : pos + 2])
    pos += 2

    # Path is NUL-terminated.
    nul_pos = data.index(b"\x00", pos)
    path = data[pos:nul_pos].decode("utf-8")
    pos = nul_pos + 1  # consume the NUL terminator

    # Now skip the padding.  We know entry_len = 62 + len(path_utf8) + 1 (NUL).
    # Padding = 8 - (entry_len % 8), or 8 if that's 0.
    path_bytes_with_nul = path.encode("utf-8") + b"\x00"
    padding = _entry_padding(path_bytes_with_nul)
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

    return entry, pos - start
