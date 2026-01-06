"""Pack file writer for Git pack format.

Creates .pack and .idx files from a collection of Git objects,
optionally applying delta compression for space efficiency.
"""

import hashlib
import zlib
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

from gitpy.objects import GitObject, create_object_data

from .delta import create_delta
from .pack import (
    PACK_SIGNATURE,
    PACK_VERSION,
    PackObjectType,
    write_ofs_delta_offset,
    write_pack_object_header,
)
from .pack_index import PackIndex, PackIndexEntry


@dataclass(slots=True)
class PackEntry:
    """Object to be written to pack."""

    sha: str  # 40-character hex SHA
    type_name: str  # Object type
    data: bytes  # Object content (or delta)
    delta_base_sha: str | None = None  # Base SHA if deltified


class PackWriter:
    """Writer for Git pack files.

    Creates .pack and .idx files from a collection of objects.
    """

    def __init__(self, objects_dir: Path) -> None:
        """Initialize pack writer.

        Args:
            objects_dir: Path to .git/objects directory.
        """
        self.objects_dir = objects_dir
        self.pack_dir = objects_dir / "pack"
        self.pack_dir.mkdir(parents=True, exist_ok=True)

    def write_pack(
        self,
        objects: Iterable[GitObject],
        *,
        deltify: bool = True,
        window_size: int = 10,
    ) -> tuple[Path, Path]:
        """Write objects to a new pack file.

        Args:
            objects: Iterable of GitObject instances to pack.
            deltify: If True, apply delta compression (default: True).
            window_size: Number of recent objects to consider as delta bases.

        Returns:
            Tuple of (pack_path, index_path).
        """
        # Collect all objects
        entries: list[PackEntry] = []
        for obj in objects:
            data = create_object_data(obj)
            sha = hashlib.sha1(data, usedforsecurity=False).hexdigest()
            # Extract content (without header)
            null_idx = data.index(b"\0")
            content = data[null_idx + 1 :]
            entries.append(
                PackEntry(
                    sha=sha,
                    type_name=obj.type_name,
                    data=content,
                )
            )

        # Sort by type then size (helps delta compression)
        entries.sort(key=lambda e: (e.type_name, len(e.data)))

        # Optionally deltify
        if deltify:
            entries = self._deltify_entries(entries, window_size)

        return self._write_pack_from_entries(entries)

    def _deltify_entries(
        self,
        entries: list[PackEntry],
        window_size: int,
    ) -> list[PackEntry]:
        """Apply delta compression to entries.

        Args:
            entries: List of PackEntry objects.
            window_size: Number of recent objects to consider.

        Returns:
            List of PackEntry objects, some converted to deltas.
        """
        result: list[PackEntry] = []
        window: list[PackEntry] = []

        for entry in entries:
            best_delta: bytes | None = None
            best_base: str | None = None
            best_size = len(entry.data)

            # Try to deltify against recent objects of same type
            for base in window:
                if base.type_name != entry.type_name:
                    continue

                # Skip if base is already a delta
                if base.delta_base_sha is not None:
                    continue

                # Skip if sizes are too different
                if len(base.data) * 10 < len(entry.data):
                    continue
                if len(base.data) > len(entry.data) * 10:
                    continue

                delta = create_delta(base.data, entry.data)
                if len(delta) < best_size:
                    best_delta = delta
                    best_base = base.sha
                    best_size = len(delta)

            if best_delta and len(best_delta) < len(entry.data) * 0.9:
                # Delta is significantly smaller
                result.append(
                    PackEntry(
                        sha=entry.sha,
                        type_name=entry.type_name,
                        data=best_delta,
                        delta_base_sha=best_base,
                    )
                )
            else:
                # Keep as non-delta
                result.append(entry)

            # Update window (use original entry for future delta bases)
            window.append(entry)
            if len(window) > window_size:
                window.pop(0)

        return result

    def _write_pack_from_entries(
        self, entries: list[PackEntry]
    ) -> tuple[Path, Path]:
        """Write entries to pack file.

        Args:
            entries: List of PackEntry objects to write.

        Returns:
            Tuple of (pack_path, index_path).
        """
        pack_data = self._create_pack_data(entries)

        # Compute pack SHA (of content without trailer)
        pack_sha = hashlib.sha1(pack_data[:-20], usedforsecurity=False).hexdigest()

        pack_path = self.pack_dir / f"pack-{pack_sha}.pack"
        pack_path.write_bytes(pack_data)

        # Create and write index
        index = self._create_index(entries, pack_data, pack_sha)
        idx_path = self.pack_dir / f"pack-{pack_sha}.idx"
        index.write(idx_path)

        return pack_path, idx_path

    def _create_pack_data(self, entries: list[PackEntry]) -> bytes:
        """Create pack file content.

        Args:
            entries: List of PackEntry objects.

        Returns:
            Complete pack file bytes including trailer.
        """
        result = bytearray()

        # Header
        result.extend(PACK_SIGNATURE)
        result.extend(PACK_VERSION.to_bytes(4, "big"))
        result.extend(len(entries).to_bytes(4, "big"))

        # Track offsets for OFS_DELTA
        sha_to_offset: dict[str, int] = {}

        for entry in entries:
            offset = len(result)
            sha_to_offset[entry.sha] = offset

            if entry.delta_base_sha:
                # Delta object
                base_offset = sha_to_offset.get(entry.delta_base_sha)

                if base_offset is not None:
                    # Use OFS_DELTA (base already written)
                    obj_type = PackObjectType.OFS_DELTA
                    header = write_pack_object_header(obj_type, len(entry.data))
                    result.extend(header)

                    # Encode negative offset from entry start to base entry start
                    delta_offset = offset - base_offset
                    result.extend(write_ofs_delta_offset(delta_offset))
                else:
                    # Use REF_DELTA (base not in this pack or not yet written)
                    obj_type = PackObjectType.REF_DELTA
                    header = write_pack_object_header(obj_type, len(entry.data))
                    result.extend(header)
                    result.extend(bytes.fromhex(entry.delta_base_sha))
            else:
                # Non-delta object
                obj_type = PackObjectType.from_object_type(entry.type_name)
                header = write_pack_object_header(obj_type, len(entry.data))
                result.extend(header)

            # Compressed data
            compressed = zlib.compress(entry.data)
            result.extend(compressed)

        # Trailer (SHA-1 of everything)
        sha = hashlib.sha1(result, usedforsecurity=False).digest()
        result.extend(sha)

        return bytes(result)

    def _create_index(
        self,
        entries: list[PackEntry],
        pack_data: bytes,
        pack_sha: str,
    ) -> PackIndex:
        """Create index for pack file.

        Args:
            entries: List of PackEntry objects.
            pack_data: Complete pack file data.
            pack_sha: SHA of pack file.

        Returns:
            PackIndex for the pack file.
        """
        index_entries: list[PackIndexEntry] = []
        offset = 12  # After header

        for entry in entries:
            entry_start = offset

            # Skip header
            byte = pack_data[offset]
            offset += 1
            while byte & 0x80:
                byte = pack_data[offset]
                offset += 1

            # Skip delta base reference if present
            if entry.delta_base_sha:
                # Check object type to determine reference format
                obj_type = (pack_data[entry_start] >> 4) & 0x07
                if obj_type == PackObjectType.OFS_DELTA:
                    byte = pack_data[offset]
                    offset += 1
                    while byte & 0x80:
                        byte = pack_data[offset]
                        offset += 1
                else:
                    offset += 20  # REF_DELTA uses 20-byte SHA

            # Find end of compressed data
            decompressor = zlib.decompressobj()
            decompressor.decompress(pack_data[offset:])
            compressed_size = len(pack_data[offset:]) - len(decompressor.unused_data)
            next_offset = offset + compressed_size

            # CRC32 of entire entry
            crc = zlib.crc32(pack_data[entry_start:next_offset]) & 0xFFFFFFFF

            index_entries.append(
                PackIndexEntry(
                    sha=entry.sha,
                    offset=entry_start,
                    crc32=crc,
                )
            )

            offset = next_offset

        return PackIndex(pack_sha=pack_sha, entries=index_entries)
