"""Pack file reader for Git pack format.

Pack files combine multiple objects into a single file with optional
delta compression for efficient storage and transfer.

Pack Format:
    Header:  12 bytes (signature + version + object count)
    Objects: Variable (type/size header + compressed data)
    Trailer: 20 bytes (SHA-1 of all above)

Object Types:
    1 = OBJ_COMMIT
    2 = OBJ_TREE
    3 = OBJ_BLOB
    4 = OBJ_TAG
    6 = OBJ_OFS_DELTA (delta with offset reference)
    7 = OBJ_REF_DELTA (delta with SHA reference)
"""

import hashlib
import zlib
from collections.abc import Iterator
from dataclasses import dataclass
from enum import IntEnum
from pathlib import Path
from typing import Self

from .delta import apply_delta
from .pack_index import PackIndex, PackIndexEntry

PACK_SIGNATURE = b"PACK"
PACK_VERSION = 2


class PackObjectType(IntEnum):
    """Object types in pack files."""

    COMMIT = 1
    TREE = 2
    BLOB = 3
    TAG = 4
    # 5 is reserved
    OFS_DELTA = 6
    REF_DELTA = 7

    def to_object_type(self) -> str:
        """Convert to string type name.

        Returns:
            Object type string or "delta" for delta types.
        """
        return {
            self.COMMIT: "commit",
            self.TREE: "tree",
            self.BLOB: "blob",
            self.TAG: "tag",
        }.get(self, "delta")

    @classmethod
    def from_object_type(cls, type_name: str) -> Self:
        """Convert from string type name.

        Args:
            type_name: Object type string.

        Returns:
            Corresponding PackObjectType.

        Raises:
            KeyError: Unknown type name.
        """
        return {
            "commit": cls.COMMIT,
            "tree": cls.TREE,
            "blob": cls.BLOB,
            "tag": cls.TAG,
        }[type_name]

    @property
    def is_delta(self) -> bool:
        """Check if this is a delta type."""
        return self in (self.OFS_DELTA, self.REF_DELTA)


@dataclass(slots=True)
class PackObject:
    """Object read from pack file."""

    sha: str  # 40-character hex SHA
    type_name: str  # "blob", "tree", "commit", or "tag"
    data: bytes  # Uncompressed object content
    offset: int  # Offset in pack file


def read_pack_object_header(data: bytes, offset: int) -> tuple[int, int, int]:
    """Read pack object header.

    Args:
        data: Pack file data.
        offset: Byte offset to start reading.

    Returns:
        Tuple of (object_type, uncompressed_size, bytes_consumed).
    """
    byte = data[offset]
    obj_type = (byte >> 4) & 0x07  # Bits 4-6
    size = byte & 0x0F  # Bits 0-3

    consumed = 1
    shift = 4

    # Continue while MSB is set
    while byte & 0x80:
        byte = data[offset + consumed]
        size |= (byte & 0x7F) << shift
        shift += 7
        consumed += 1

    return obj_type, size, consumed


def write_pack_object_header(obj_type: int, size: int) -> bytes:
    """Encode pack object header.

    Args:
        obj_type: Object type value (1-4, 6-7).
        size: Uncompressed object size.

    Returns:
        Encoded header bytes.
    """
    result = bytearray()

    # First byte: type in bits 4-6, low 4 bits of size
    byte = (obj_type << 4) | (size & 0x0F)
    size >>= 4

    if size > 0:
        byte |= 0x80
    result.append(byte)

    # Remaining size bytes
    while size > 0:
        byte = size & 0x7F
        size >>= 7
        if size > 0:
            byte |= 0x80
        result.append(byte)

    return bytes(result)


def read_ofs_delta_offset(data: bytes, offset: int) -> tuple[int, int]:
    """Read OFS_DELTA negative offset.

    The encoding adds 1 to each continuation byte to eliminate
    ambiguity in the representation.

    Args:
        data: Pack data.
        offset: Starting position.

    Returns:
        Tuple of (base_offset, bytes_consumed).
    """
    byte = data[offset]
    result = byte & 0x7F
    consumed = 1

    while byte & 0x80:
        byte = data[offset + consumed]
        # The +1 is crucial: it makes the encoding unambiguous
        result = ((result + 1) << 7) | (byte & 0x7F)
        consumed += 1

    return result, consumed


def write_ofs_delta_offset(offset: int) -> bytes:
    """Encode OFS_DELTA negative offset.

    Args:
        offset: Positive offset value to encode.

    Returns:
        Encoded offset bytes.
    """
    result = bytearray()
    result.append(offset & 0x7F)
    offset >>= 7

    while offset > 0:
        offset -= 1  # The crucial -1
        result.append(0x80 | (offset & 0x7F))
        offset >>= 7

    result.reverse()
    return bytes(result)


class PackFile:
    """Reader for Git pack files.

    Pack files store multiple objects efficiently using
    zlib compression and delta encoding.
    """

    def __init__(self, pack_path: Path, index: PackIndex | None = None) -> None:
        """Open pack file.

        Args:
            pack_path: Path to .pack file.
            index: Optional pre-loaded index. If not provided, loads from
                   .idx file or builds from pack.

        Raises:
            ValueError: Invalid pack signature or unsupported version.
            FileNotFoundError: Pack file doesn't exist.
        """
        self.pack_path = pack_path
        self._data = pack_path.read_bytes()

        # Cache for resolved objects (offset -> (type, data))
        # Must be initialized before _build_index is called
        self._cache: dict[int, tuple[str, bytes]] = {}

        # Parse header
        self.version, self.object_count = self._read_header()

        # Load or create index
        if index:
            self.index = index
        else:
            idx_path = pack_path.with_suffix(".idx")
            if idx_path.exists():
                self.index = PackIndex.from_file(idx_path)
            else:
                self.index = self._build_index()

    def _read_header(self) -> tuple[int, int]:
        """Parse pack header.

        Returns:
            Tuple of (version, object_count).

        Raises:
            ValueError: Invalid signature or version.
        """
        if self._data[:4] != PACK_SIGNATURE:
            raise ValueError("Invalid pack signature")

        version = int.from_bytes(self._data[4:8], "big")
        if version not in (2, 3):
            raise ValueError(f"Unsupported pack version: {version}")

        object_count = int.from_bytes(self._data[8:12], "big")
        return version, object_count

    def verify_checksum(self) -> bool:
        """Verify pack file integrity.

        Returns:
            True if checksum matches, False if corrupted.
        """
        expected_sha = self._data[-20:]
        actual_sha = hashlib.sha1(self._data[:-20], usedforsecurity=False).digest()
        return expected_sha == actual_sha

    def _read_object_at(
        self, offset: int
    ) -> tuple[int, int, bytes, int, int | None, str | None]:
        """Read raw object data at offset.

        Args:
            offset: Byte offset in pack file.

        Returns:
            Tuple of (object_type, uncompressed_size, decompressed_data,
                     next_offset, base_offset, base_sha).
            base_offset is set for OFS_DELTA, base_sha for REF_DELTA.
        """
        pos = offset

        # Read type and size
        obj_type, size, consumed = read_pack_object_header(self._data, pos)
        pos += consumed

        # Handle delta base reference
        base_offset: int | None = None
        base_sha: str | None = None

        if obj_type == PackObjectType.OFS_DELTA:
            # Read negative offset to base
            delta_offset, consumed = read_ofs_delta_offset(self._data, pos)
            pos += consumed
            base_offset = offset - delta_offset

        elif obj_type == PackObjectType.REF_DELTA:
            # Read 20-byte SHA reference
            base_sha = self._data[pos : pos + 20].hex()
            pos += 20

        # Decompress data
        decompressor = zlib.decompressobj()
        decompressed = decompressor.decompress(self._data[pos:])
        next_offset = pos + len(self._data[pos:]) - len(decompressor.unused_data)

        return obj_type, size, decompressed, next_offset, base_offset, base_sha

    def _resolve_object(self, offset: int) -> tuple[str, bytes]:
        """Resolve object at offset, following delta chains.

        Args:
            offset: Byte offset in pack file.

        Returns:
            Tuple of (type_name, object_data).
        """
        # Check cache
        if offset in self._cache:
            return self._cache[offset]

        obj_type, size, data, next_offset, base_offset, base_sha = self._read_object_at(
            offset
        )

        if obj_type in (
            PackObjectType.COMMIT,
            PackObjectType.TREE,
            PackObjectType.BLOB,
            PackObjectType.TAG,
        ):
            # Non-delta object
            type_name = PackObjectType(obj_type).to_object_type()
            result = (type_name, data)

        elif obj_type == PackObjectType.OFS_DELTA:
            # Delta with offset reference
            if base_offset is None:
                raise ValueError("OFS_DELTA missing base offset")
            base_type, base_data = self._resolve_object(base_offset)
            resolved_data = apply_delta(base_data, data)
            result = (base_type, resolved_data)

        elif obj_type == PackObjectType.REF_DELTA:
            # Delta with SHA reference
            if base_sha is None:
                raise ValueError("REF_DELTA missing base SHA")
            ref_base_offset = self.index.get_offset(base_sha)
            if ref_base_offset is None:
                raise ValueError(f"Base object not found: {base_sha}")
            base_type, base_data = self._resolve_object(ref_base_offset)
            resolved_data = apply_delta(base_data, data)
            result = (base_type, resolved_data)

        else:
            raise ValueError(f"Unknown object type: {obj_type}")

        # Cache result
        self._cache[offset] = result
        return result

    def read_object(self, sha: str) -> PackObject | None:
        """Read object by SHA.

        Args:
            sha: 40-character hex SHA-1.

        Returns:
            PackObject if found, None if not in this pack.
        """
        offset = self.index.get_offset(sha)
        if offset is None:
            return None

        type_name, data = self._resolve_object(offset)

        return PackObject(sha=sha, type_name=type_name, data=data, offset=offset)

    def __contains__(self, sha: str) -> bool:
        """Check if object exists in pack."""
        return sha in self.index

    def __iter__(self) -> Iterator[PackObject]:
        """Iterate over all objects in pack."""
        for entry in self.index.entries:
            obj = self.read_object(entry.sha)
            if obj:
                yield obj

    def __len__(self) -> int:
        """Return number of objects in pack."""
        return self.object_count

    def _scan_raw_entries(self) -> list[tuple[int, int]]:
        """Scan pack data and collect (entry_start, crc32) pairs.

        Traverses the compressed object stream without resolving deltas.

        Returns:
            List of (entry_start_offset, crc32) for every object.
        """
        raw_entries: list[tuple[int, int]] = []
        offset = 12  # After header

        for _ in range(self.object_count):
            entry_start = offset

            obj_type, _size, consumed = read_pack_object_header(self._data, offset)
            offset += consumed

            if obj_type == PackObjectType.OFS_DELTA:
                _, consumed = read_ofs_delta_offset(self._data, offset)
                offset += consumed
            elif obj_type == PackObjectType.REF_DELTA:
                offset += 20

            decompressor = zlib.decompressobj()
            decompressor.decompress(self._data[offset:])
            compressed_size = len(self._data[offset:]) - len(decompressor.unused_data)
            next_offset = offset + compressed_size

            crc = zlib.crc32(self._data[entry_start:next_offset]) & 0xFFFFFFFF
            raw_entries.append((entry_start, crc))
            offset = next_offset

        return raw_entries

    def _build_sha_map(self, raw_entries: list[tuple[int, int]]) -> dict[str, int]:
        """Build a complete SHA→offset map for all objects in the pack.

        Non-delta and OFS_DELTA objects are resolved first (their bases are
        self-contained).  REF_DELTA objects are resolved iteratively: each
        pass resolves any delta whose base SHA is now known, until all are
        resolved or no further progress can be made.

        Args:
            raw_entries: Output of ``_scan_raw_entries``.

        Returns:
            Mapping of 40-char hex SHA to byte offset in the pack file.

        Raises:
            ValueError: A REF_DELTA chain references an unknown base.
        """
        sha_to_offset: dict[str, int] = {}

        for entry_start, _ in raw_entries:
            obj_type = read_pack_object_header(self._data, entry_start)[0]
            if obj_type != PackObjectType.REF_DELTA:
                type_name, resolved_data = self._resolve_object(entry_start)
                hdr = f"{type_name} {len(resolved_data)}\0".encode()
                sha = hashlib.sha1(
                    hdr + resolved_data, usedforsecurity=False
                ).hexdigest()
                sha_to_offset[sha] = entry_start

        pending = [
            s
            for s, _ in raw_entries
            if read_pack_object_header(self._data, s)[0] == PackObjectType.REF_DELTA
        ]
        self._resolve_ref_delta_chain(pending, sha_to_offset)
        return sha_to_offset

    def _resolve_ref_delta_chain(
        self,
        pending: list[int],
        sha_to_offset: dict[str, int],
    ) -> None:
        """Resolve REF_DELTA entries iteratively, updating *sha_to_offset* in-place.

        Args:
            pending: Pack offsets of unresolved REF_DELTA objects.
            sha_to_offset: Grows as each delta is resolved.

        Raises:
            ValueError: No progress in a round — chain cannot be resolved.
        """
        while pending:
            resolved_this_round: list[int] = []
            for entry_start in pending:
                _, _, _, _, _, base_sha = self._read_object_at(entry_start)
                if base_sha is not None and base_sha in sha_to_offset:
                    type_name, resolved_data = self._resolve_object_with_map(
                        entry_start, sha_to_offset
                    )
                    hdr = f"{type_name} {len(resolved_data)}\0".encode()
                    sha = hashlib.sha1(
                        hdr + resolved_data, usedforsecurity=False
                    ).hexdigest()
                    sha_to_offset[sha] = entry_start
                    resolved_this_round.append(entry_start)

            if not resolved_this_round:
                unresolved = [self._read_object_at(s)[5] for s in pending]
                raise ValueError(
                    f"Cannot resolve REF_DELTA chain; missing base(s): {unresolved}"
                )

            pending = [e for e in pending if e not in resolved_this_round]

    def _build_index(self) -> PackIndex:
        """Build index by scanning pack file.

        Uses a multi-pass strategy so that REF_DELTA chains of arbitrary
        depth can be resolved even when no ``.idx`` file exists.

        Returns:
            PackIndex built from pack contents.
        """
        raw_entries = self._scan_raw_entries()
        sha_to_offset = self._build_sha_map(raw_entries)

        entries: list[PackIndexEntry] = []
        for entry_start, crc in raw_entries:
            type_name, resolved_data = self._resolve_object_with_map(
                entry_start, sha_to_offset
            )
            hdr = f"{type_name} {len(resolved_data)}\0".encode()
            sha = hashlib.sha1(hdr + resolved_data, usedforsecurity=False).hexdigest()
            entries.append(PackIndexEntry(sha=sha, offset=entry_start, crc32=crc))

        pack_sha = self._data[-20:].hex()
        return PackIndex(pack_sha=pack_sha, entries=entries)

    def _resolve_object_with_map(
        self, offset: int, sha_to_offset: dict[str, int]
    ) -> tuple[str, bytes]:
        """Resolve object at *offset* using *sha_to_offset* for REF_DELTA.

        Identical to ``_resolve_object`` except that REF_DELTA resolution
        uses *sha_to_offset* instead of ``self.index`` (which may not yet
        exist during index construction).

        Args:
            offset: Byte offset in pack file.
            sha_to_offset: Mapping of SHA → pack offset for base objects.

        Returns:
            Tuple of (type_name, object_data).
        """
        if offset in self._cache:
            return self._cache[offset]

        obj_type, _size, data, _next, base_offset, base_sha = self._read_object_at(
            offset
        )

        if obj_type in (
            PackObjectType.COMMIT,
            PackObjectType.TREE,
            PackObjectType.BLOB,
            PackObjectType.TAG,
        ):
            type_name = PackObjectType(obj_type).to_object_type()
            result = (type_name, data)

        elif obj_type == PackObjectType.OFS_DELTA:
            if base_offset is None:
                raise ValueError("OFS_DELTA missing base offset")
            base_type, base_data = self._resolve_object_with_map(
                base_offset, sha_to_offset
            )
            result = (base_type, apply_delta(base_data, data))

        elif obj_type == PackObjectType.REF_DELTA:
            if base_sha is None:
                raise ValueError("REF_DELTA missing base SHA")
            ref_base_offset = sha_to_offset.get(base_sha)
            if ref_base_offset is None:
                raise ValueError(f"Base object not found in map: {base_sha}")
            base_type, base_data = self._resolve_object_with_map(
                ref_base_offset, sha_to_offset
            )
            result = (base_type, apply_delta(base_data, data))

        else:
            raise ValueError(f"Unknown object type: {obj_type}")

        self._cache[offset] = result
        return result

    def clear_cache(self) -> None:
        """Clear the resolved object cache."""
        self._cache.clear()
