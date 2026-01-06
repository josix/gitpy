"""Pack index for fast object lookup.

The pack index (.idx file) enables O(log n) lookup of objects in pack files
by SHA. It uses a fanout table to narrow the binary search range.

Index Format (Version 2):
    Header:      8 bytes (magic + version)
    Fanout:      1024 bytes (256 × 4-byte cumulative counts)
    SHA Table:   N × 20 bytes (sorted SHA-1 hashes)
    CRC32 Table: N × 4 bytes (CRC32 of packed data)
    Offset Table: N × 4 bytes (pack offsets, high bit for large)
    Large Offsets: variable (8-byte offsets for >2GB packs)
    Pack SHA:    20 bytes (SHA of pack file)
    Index SHA:   20 bytes (SHA of index content)
"""

import hashlib
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Self

IDX_SIGNATURE = b"\xff\x74\x4f\x63"  # Magic number
IDX_VERSION = 2


@dataclass(slots=True)
class PackIndexEntry:
    """Single entry in pack index."""

    sha: str  # 40-char hex SHA
    offset: int  # Offset in pack file
    crc32: int  # CRC32 of packed object data


class PackIndex:
    """Pack index for fast object lookup.

    Provides O(log n) lookup of pack file offset by SHA using
    a fanout table and binary search.
    """

    def __init__(self, pack_sha: str, entries: list[PackIndexEntry]) -> None:
        """Create pack index from entries.

        Args:
            pack_sha: 40-character hex SHA of the pack file.
            entries: List of PackIndexEntry objects (will be sorted).
        """
        self.pack_sha = pack_sha
        self.entries = sorted(entries, key=lambda e: e.sha)
        self._build_fanout()
        self._sha_to_idx: dict[str, int] = {
            e.sha: i for i, e in enumerate(self.entries)
        }

    def _build_fanout(self) -> None:
        """Build fanout table from sorted entries."""
        # Count objects for each first byte
        counts = [0] * 256
        for entry in self.entries:
            first_byte = int(entry.sha[:2], 16)
            counts[first_byte] += 1

        # Convert to cumulative counts
        self._fanout = [0] * 256
        cumulative = 0
        for i in range(256):
            cumulative += counts[i]
            self._fanout[i] = cumulative

    def find(self, sha: str) -> PackIndexEntry | None:
        """Look up entry by SHA.

        Args:
            sha: 40-character hex SHA-1.

        Returns:
            PackIndexEntry if found, None otherwise.
        """
        idx = self._sha_to_idx.get(sha)
        if idx is not None:
            return self.entries[idx]
        return None

    def get_offset(self, sha: str) -> int | None:
        """Get pack file offset for SHA.

        Args:
            sha: 40-character hex SHA-1.

        Returns:
            Byte offset if found, None otherwise.
        """
        entry = self.find(sha)
        return entry.offset if entry else None

    def get_crc32(self, sha: str) -> int | None:
        """Get CRC32 for SHA.

        Args:
            sha: 40-character hex SHA-1.

        Returns:
            CRC32 value if found, None otherwise.
        """
        entry = self.find(sha)
        return entry.crc32 if entry else None

    @property
    def object_count(self) -> int:
        """Number of objects in pack."""
        return len(self.entries)

    def __contains__(self, sha: str) -> bool:
        """Check if SHA is in index."""
        return sha in self._sha_to_idx

    def __len__(self) -> int:
        """Return number of entries."""
        return len(self.entries)

    def __iter__(self) -> Iterator[PackIndexEntry]:
        """Iterate over entries."""
        return iter(self.entries)

    @classmethod
    def from_file(cls, path: Path) -> Self:
        """Load pack index from .idx file.

        Args:
            path: Path to index file.

        Returns:
            Parsed PackIndex.

        Raises:
            ValueError: Invalid index format or version.
            FileNotFoundError: File doesn't exist.
        """
        data = path.read_bytes()
        return cls.parse(data)

    @classmethod
    def parse(cls, data: bytes) -> Self:
        """Parse index from raw bytes.

        Args:
            data: Raw index file content.

        Returns:
            Parsed PackIndex.

        Raises:
            ValueError: Invalid signature or version.
        """
        # Check header
        if data[:4] != IDX_SIGNATURE:
            raise ValueError("Invalid pack index signature")

        version = int.from_bytes(data[4:8], "big")
        if version != IDX_VERSION:
            raise ValueError(f"Unsupported index version: {version}")

        # Read fanout table
        fanout_offset = 8
        fanout = []
        for i in range(256):
            value = int.from_bytes(
                data[fanout_offset + i * 4 : fanout_offset + i * 4 + 4], "big"
            )
            fanout.append(value)

        object_count = fanout[255]

        # Calculate section offsets
        sha_offset = fanout_offset + 256 * 4
        crc_offset = sha_offset + object_count * 20
        offset_offset = crc_offset + object_count * 4
        large_offset_offset = offset_offset + object_count * 4

        # Read SHA table
        shas = []
        for i in range(object_count):
            sha_bytes = data[sha_offset + i * 20 : sha_offset + i * 20 + 20]
            shas.append(sha_bytes.hex())

        # Read CRC32 table
        crcs = []
        for i in range(object_count):
            crc = int.from_bytes(
                data[crc_offset + i * 4 : crc_offset + i * 4 + 4], "big"
            )
            crcs.append(crc)

        # Read offset table
        offsets = []
        for i in range(object_count):
            offset = int.from_bytes(
                data[offset_offset + i * 4 : offset_offset + i * 4 + 4], "big"
            )
            # Check if this is a large offset reference
            if offset & 0x80000000:
                # High bit set - this is an index into large offset table
                large_idx = offset & 0x7FFFFFFF
                large_offset = int.from_bytes(
                    data[
                        large_offset_offset + large_idx * 8 : large_offset_offset
                        + large_idx * 8
                        + 8
                    ],
                    "big",
                )
                offsets.append(large_offset)
            else:
                offsets.append(offset)

        # Extract pack SHA (before index SHA at end)
        pack_sha_offset = len(data) - 40
        pack_sha = data[pack_sha_offset : pack_sha_offset + 20].hex()

        # Build entries
        entries = [
            PackIndexEntry(sha=shas[i], offset=offsets[i], crc32=crcs[i])
            for i in range(object_count)
        ]

        return cls(pack_sha=pack_sha, entries=entries)

    def serialize(self) -> bytes:
        """Serialize to version 2 index format.

        Returns:
            Raw bytes ready to write to .idx file.
        """
        result = bytearray()

        # Header
        result.extend(IDX_SIGNATURE)
        result.extend(IDX_VERSION.to_bytes(4, "big"))

        # Fanout table
        for count in self._fanout:
            result.extend(count.to_bytes(4, "big"))

        # SHA table (sorted)
        for entry in self.entries:
            result.extend(bytes.fromhex(entry.sha))

        # CRC32 table
        for entry in self.entries:
            result.extend(entry.crc32.to_bytes(4, "big"))

        # Offset table
        large_offsets: list[int] = []
        for entry in self.entries:
            if entry.offset >= 0x80000000:
                # Large offset - store index with high bit set
                large_idx = len(large_offsets)
                large_offsets.append(entry.offset)
                result.extend((0x80000000 | large_idx).to_bytes(4, "big"))
            else:
                result.extend(entry.offset.to_bytes(4, "big"))

        # Large offset table
        for offset in large_offsets:
            result.extend(offset.to_bytes(8, "big"))

        # Pack file SHA
        result.extend(bytes.fromhex(self.pack_sha))

        # Index file SHA (hash of everything so far)
        index_sha = hashlib.sha1(result, usedforsecurity=False).digest()
        result.extend(index_sha)

        return bytes(result)

    def write(self, path: Path) -> None:
        """Write index to file.

        Args:
            path: Path to write index file.
        """
        path.write_bytes(self.serialize())
