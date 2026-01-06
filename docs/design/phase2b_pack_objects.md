# Phase 2b: Pack Objects - Design Specification

> **Status**: Draft
> **Author**: Domain Expert
> **Last Updated**: 2026-01-06
> **Dependencies**: Phase 1 (Object Model), Phase 2 (Object Storage)

## 1. Overview

Pack files are Git's mechanism for efficient object storage and transfer. While loose objects store each object as an individual compressed file, pack files combine multiple objects into a single file with delta compression, dramatically reducing storage space and improving transfer speeds.

### 1.1 Design Goals

- **Space Efficiency**: Delta compression reduces storage by 10-100x for similar objects
- **Transfer Optimization**: Single file for network transfer instead of thousands of loose objects
- **Random Access**: Index file enables O(1) object lookup by SHA
- **Streaming**: Objects can be read without loading entire pack into memory
- **Git Compatibility**: Exact binary format compatibility with Git

### 1.2 Storage Locations

```
.git/
└── objects/
    └── pack/
        ├── pack-<sha>.pack   # Pack data file
        ├── pack-<sha>.idx    # Pack index file
        ├── pack-<sha>.rev    # Reverse index (optional, v2.31+)
        └── multi-pack-index  # Multi-pack index (optional)
```

### 1.3 When Pack Files Are Created

- `git gc` - Garbage collection packs loose objects
- `git repack` - Explicitly repack objects
- `git clone` / `git fetch` - Received as packfile from remote
- `git push` - Sent as packfile to remote

---

## 2. Pack File Format (.pack)

### 2.1 Overall Structure

```
┌──────────────────────────────────────────────────────────────┐
│                         Header (12 bytes)                     │
├──────────────────────────────────────────────────────────────┤
│                       Object Entry 1                          │
├──────────────────────────────────────────────────────────────┤
│                       Object Entry 2                          │
├──────────────────────────────────────────────────────────────┤
│                           ...                                 │
├──────────────────────────────────────────────────────────────┤
│                       Object Entry N                          │
├──────────────────────────────────────────────────────────────┤
│                    Trailer (20 bytes SHA-1)                   │
└──────────────────────────────────────────────────────────────┘
```

### 2.2 Header Format

```
┌─────────────────┬─────────────────┬─────────────────────────┐
│   Signature     │    Version      │     Object Count        │
│   "PACK"        │   (4 bytes)     │     (4 bytes)           │
│   (4 bytes)     │   BE uint32     │     BE uint32           │
└─────────────────┴─────────────────┴─────────────────────────┘
```

- **Signature**: ASCII "PACK" (`0x5041434b`)
- **Version**: 2 (current) or 3 (with capabilities)
- **Object Count**: Number of objects in pack (big-endian)

```python
PACK_SIGNATURE = b"PACK"
PACK_VERSION = 2

def read_pack_header(data: bytes) -> tuple[int, int]:
    """Parse pack header, return (version, object_count)."""
    if data[:4] != PACK_SIGNATURE:
        raise ValueError("Invalid pack signature")

    version = int.from_bytes(data[4:8], "big")
    object_count = int.from_bytes(data[8:12], "big")

    if version not in (2, 3):
        raise ValueError(f"Unsupported pack version: {version}")

    return version, object_count
```

### 2.3 Object Entry Format

Each object entry consists of:

```
┌─────────────────────────────────────────────────────────────┐
│                    Variable-length header                    │
│              (type + uncompressed size)                      │
├─────────────────────────────────────────────────────────────┤
│                 Delta base reference                         │
│         (only for OFS_DELTA or REF_DELTA types)             │
├─────────────────────────────────────────────────────────────┤
│                   Zlib-compressed data                       │
│          (or delta instructions if delta type)               │
└─────────────────────────────────────────────────────────────┘
```

### 2.4 Object Types

| Type Value | Name | Description |
|------------|------|-------------|
| 1 | OBJ_COMMIT | Commit object |
| 2 | OBJ_TREE | Tree object |
| 3 | OBJ_BLOB | Blob object |
| 4 | OBJ_TAG | Annotated tag object |
| 6 | OBJ_OFS_DELTA | Delta with offset to base |
| 7 | OBJ_REF_DELTA | Delta with SHA reference to base |

**Note**: Type 5 is reserved/unused.

```python
from enum import IntEnum

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
        """Convert to string type name."""
        return {
            self.COMMIT: "commit",
            self.TREE: "tree",
            self.BLOB: "blob",
            self.TAG: "tag",
        }.get(self, "delta")

    @classmethod
    def from_object_type(cls, type_name: str) -> "PackObjectType":
        """Convert from string type name."""
        return {
            "commit": cls.COMMIT,
            "tree": cls.TREE,
            "blob": cls.BLOB,
            "tag": cls.TAG,
        }[type_name]
```

### 2.5 Variable-Length Integer Encoding

Pack files use a variable-length encoding for sizes and offsets:

**Size/Type Header** (first byte special):
```
┌───┬───┬───┬───┬───┬───┬───┬───┐
│MSB│  type │      size         │
│(1)│  (3)  │       (4)         │
└───┴───┴───┴───┴───┴───┴───┴───┘
```

- Bit 7 (MSB): 1 if more bytes follow
- Bits 4-6: Object type (for first byte only)
- Bits 0-3: Size bits (4 bits from first byte, 7 bits from subsequent)

```python
def read_pack_object_header(data: bytes, offset: int) -> tuple[int, int, int]:
    """
    Read pack object header.

    Returns:
        (object_type, uncompressed_size, bytes_consumed)
    """
    byte = data[offset]
    obj_type = (byte >> 4) & 0x07  # bits 4-6
    size = byte & 0x0F  # bits 0-3

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
    """Encode pack object header."""
    # First byte: type in bits 4-6, low 4 bits of size
    byte = (obj_type << 4) | (size & 0x0F)
    size >>= 4

    result = bytearray()

    if size > 0:
        byte |= 0x80  # Set MSB to indicate more bytes
    result.append(byte)

    # Remaining size bytes
    while size > 0:
        byte = size & 0x7F
        size >>= 7
        if size > 0:
            byte |= 0x80
        result.append(byte)

    return bytes(result)
```

### 2.6 OFS_DELTA Base Offset Encoding

For OFS_DELTA objects, the base object offset is encoded as a variable-length negative offset from the current position:

```python
def read_ofs_delta_offset(data: bytes, offset: int) -> tuple[int, int]:
    """
    Read OFS_DELTA base offset.

    The offset is encoded with MSB continuation, but each byte
    after the first adds 1 before shifting (to avoid ambiguity).

    Returns:
        (base_offset, bytes_consumed)
    """
    byte = data[offset]
    base_offset = byte & 0x7F
    consumed = 1

    while byte & 0x80:
        byte = data[offset + consumed]
        # Add 1 before shifting to handle the encoding
        base_offset = ((base_offset + 1) << 7) | (byte & 0x7F)
        consumed += 1

    return base_offset, consumed


def write_ofs_delta_offset(offset: int) -> bytes:
    """Encode OFS_DELTA base offset."""
    # Encode in reverse order
    result = bytearray()
    result.append(offset & 0x7F)
    offset >>= 7

    while offset > 0:
        offset -= 1  # Subtract 1 before encoding
        result.append(0x80 | (offset & 0x7F))
        offset >>= 7

    result.reverse()
    return bytes(result)
```

### 2.7 Trailer

The pack file ends with a 20-byte SHA-1 checksum of all preceding content (header + all object entries).

---

## 3. Pack Index Format (.idx)

The index file enables fast object lookup by SHA without scanning the entire pack.

### 3.1 Version 2 Format (Current Standard)

```
┌─────────────────────────────────────────────────────────────┐
│                    Header (8 bytes)                          │
│            Magic: 0xff744f63  Version: 2                     │
├─────────────────────────────────────────────────────────────┤
│                   Fanout Table (1024 bytes)                  │
│              256 entries × 4 bytes (BE uint32)               │
├─────────────────────────────────────────────────────────────┤
│                    SHA-1 Table                               │
│               N entries × 20 bytes each                      │
├─────────────────────────────────────────────────────────────┤
│                    CRC32 Table                               │
│               N entries × 4 bytes each                       │
├─────────────────────────────────────────────────────────────┤
│                   Offset Table (4-byte)                      │
│               N entries × 4 bytes each                       │
├─────────────────────────────────────────────────────────────┤
│              Large Offset Table (8-byte, optional)           │
│          For offsets > 2GB, variable number of entries       │
├─────────────────────────────────────────────────────────────┤
│                  Pack File SHA-1 (20 bytes)                  │
├─────────────────────────────────────────────────────────────┤
│                  Index File SHA-1 (20 bytes)                 │
└─────────────────────────────────────────────────────────────┘
```

### 3.2 Fanout Table

The fanout table enables binary search by first SHA byte:

```python
def read_fanout_table(data: bytes, offset: int) -> list[int]:
    """
    Read 256-entry fanout table.

    fanout[i] = number of objects with first SHA byte <= i
    fanout[255] = total object count
    """
    fanout = []
    for i in range(256):
        value = int.from_bytes(data[offset + i*4 : offset + i*4 + 4], "big")
        fanout.append(value)
    return fanout


def lookup_sha_range(fanout: list[int], first_byte: int) -> tuple[int, int]:
    """
    Get the range of indices for objects starting with first_byte.

    Returns:
        (start_index, end_index) - half-open range
    """
    if first_byte == 0:
        start = 0
    else:
        start = fanout[first_byte - 1]
    end = fanout[first_byte]
    return start, end
```

### 3.3 Index Implementation

```python
# gitpy/storage/pack_index.py

from dataclasses import dataclass
from pathlib import Path
from typing import Optional
import hashlib
import struct

IDX_SIGNATURE = b"\xff\x74\x4f\x63"  # Magic number
IDX_VERSION = 2

@dataclass(slots=True)
class PackIndexEntry:
    """Single entry in pack index."""
    sha: str       # 40-char hex SHA
    offset: int    # Offset in pack file
    crc32: int     # CRC32 of packed object data


@dataclass
class PackIndex:
    """
    Pack index for fast object lookup.

    Provides O(1) lookup of object offset by SHA.
    """

    pack_sha: str                    # SHA of the pack file
    entries: list[PackIndexEntry]    # Sorted by SHA
    _fanout: list[int]              # Fanout table for binary search
    _sha_to_idx: dict[str, int]     # SHA -> entry index

    def __init__(self, pack_sha: str, entries: list[PackIndexEntry]):
        self.pack_sha = pack_sha
        self.entries = sorted(entries, key=lambda e: e.sha)
        self._build_fanout()
        self._sha_to_idx = {e.sha: i for i, e in enumerate(self.entries)}

    def _build_fanout(self) -> None:
        """Build fanout table from entries."""
        self._fanout = [0] * 256
        for entry in self.entries:
            first_byte = int(entry.sha[:2], 16)
            for i in range(first_byte, 256):
                self._fanout[i] += 1

        # Convert to cumulative counts
        for i in range(1, 256):
            self._fanout[i] += self._fanout[i - 1]

    def find(self, sha: str) -> Optional[PackIndexEntry]:
        """Look up object by SHA."""
        return self._sha_to_idx.get(sha)

    def get_offset(self, sha: str) -> Optional[int]:
        """Get pack file offset for SHA."""
        idx = self._sha_to_idx.get(sha)
        if idx is not None:
            return self.entries[idx].offset
        return None

    @property
    def object_count(self) -> int:
        """Number of objects in pack."""
        return len(self.entries)

    def __contains__(self, sha: str) -> bool:
        return sha in self._sha_to_idx

    @classmethod
    def from_file(cls, path: Path) -> "PackIndex":
        """Load pack index from .idx file."""
        data = path.read_bytes()
        return cls.parse(data)

    @classmethod
    def parse(cls, data: bytes) -> "PackIndex":
        """Parse index file data."""
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
                data[fanout_offset + i*4 : fanout_offset + i*4 + 4], "big"
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
            sha_bytes = data[sha_offset + i*20 : sha_offset + i*20 + 20]
            shas.append(sha_bytes.hex())

        # Read CRC32 table
        crcs = []
        for i in range(object_count):
            crc = int.from_bytes(
                data[crc_offset + i*4 : crc_offset + i*4 + 4], "big"
            )
            crcs.append(crc)

        # Read offset table
        offsets = []
        large_offsets = []
        for i in range(object_count):
            offset = int.from_bytes(
                data[offset_offset + i*4 : offset_offset + i*4 + 4], "big"
            )
            # Check if this is a large offset reference
            if offset & 0x80000000:
                # High bit set - this is an index into large offset table
                large_idx = offset & 0x7FFFFFFF
                large_offset = int.from_bytes(
                    data[large_offset_offset + large_idx*8 :
                         large_offset_offset + large_idx*8 + 8], "big"
                )
                offsets.append(large_offset)
            else:
                offsets.append(offset)

        # Extract pack SHA (last 40 bytes before index SHA)
        pack_sha_offset = len(data) - 40
        pack_sha = data[pack_sha_offset : pack_sha_offset + 20].hex()

        # Build entries
        entries = [
            PackIndexEntry(sha=shas[i], offset=offsets[i], crc32=crcs[i])
            for i in range(object_count)
        ]

        return cls(pack_sha=pack_sha, entries=entries)

    def serialize(self) -> bytes:
        """Serialize to index file format."""
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
        large_offsets = []
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
        index_sha = hashlib.sha1(result).digest()
        result.extend(index_sha)

        return bytes(result)
```

---

## 4. Delta Encoding

Delta compression stores objects as differences from a "base" object, dramatically reducing storage for similar content.

### 4.1 Delta Format

```
┌─────────────────────────────────────────────────────────────┐
│              Source (base) size - varint                     │
├─────────────────────────────────────────────────────────────┤
│              Target (result) size - varint                   │
├─────────────────────────────────────────────────────────────┤
│                    Delta instructions                        │
│            (sequence of COPY or INSERT ops)                  │
└─────────────────────────────────────────────────────────────┘
```

### 4.2 Delta Instructions

Two instruction types:

**INSERT** (add new data):
```
┌───┬───────────────────────────────────────┐
│ 0 │            size (1-127)               │
├───┴───────────────────────────────────────┤
│          literal data (size bytes)         │
└───────────────────────────────────────────┘
```
- First bit is 0
- Remaining 7 bits = number of literal bytes to insert (1-127)
- Followed by that many literal bytes

**COPY** (copy from base):
```
┌───┬───┬───┬───┬───┬───┬───┬───┐
│ 1 │o₄ │o₃ │o₂ │o₁ │s₃ │s₂ │s₁ │  instruction byte
├───┴───┴───┴───┴───┴───┴───┴───┤
│  offset bytes (0-4, little-endian)  │
├─────────────────────────────────────┤
│   size bytes (0-3, little-endian)   │
└─────────────────────────────────────┘
```
- First bit is 1
- Bits 0-3: which offset bytes are present (o₁-o₄)
- Bits 4-6: which size bytes are present (s₁-s₃)
- Offset bytes (little-endian, only present bytes)
- Size bytes (little-endian, only present bytes)
- Size of 0 means 0x10000 (65536)

### 4.3 Delta Implementation

```python
# gitpy/storage/delta.py

from dataclasses import dataclass
from typing import Iterator

@dataclass(slots=True)
class DeltaInsert:
    """Insert literal data."""
    data: bytes


@dataclass(slots=True)
class DeltaCopy:
    """Copy from base object."""
    offset: int
    size: int


type DeltaOp = DeltaInsert | DeltaCopy


def read_delta_size(data: bytes, offset: int) -> tuple[int, int]:
    """
    Read variable-length size from delta header.

    Returns:
        (size, bytes_consumed)
    """
    size = 0
    shift = 0
    consumed = 0

    while True:
        byte = data[offset + consumed]
        size |= (byte & 0x7F) << shift
        consumed += 1
        if not (byte & 0x80):
            break
        shift += 7

    return size, consumed


def parse_delta(data: bytes) -> tuple[int, int, list[DeltaOp]]:
    """
    Parse delta instructions.

    Returns:
        (source_size, target_size, operations)
    """
    offset = 0

    # Read source and target sizes
    source_size, consumed = read_delta_size(data, offset)
    offset += consumed

    target_size, consumed = read_delta_size(data, offset)
    offset += consumed

    # Parse instructions
    ops: list[DeltaOp] = []

    while offset < len(data):
        cmd = data[offset]
        offset += 1

        if cmd & 0x80:
            # COPY instruction
            copy_offset = 0
            copy_size = 0

            # Read offset bytes (little-endian)
            if cmd & 0x01:
                copy_offset |= data[offset]
                offset += 1
            if cmd & 0x02:
                copy_offset |= data[offset] << 8
                offset += 1
            if cmd & 0x04:
                copy_offset |= data[offset] << 16
                offset += 1
            if cmd & 0x08:
                copy_offset |= data[offset] << 24
                offset += 1

            # Read size bytes (little-endian)
            if cmd & 0x10:
                copy_size |= data[offset]
                offset += 1
            if cmd & 0x20:
                copy_size |= data[offset] << 8
                offset += 1
            if cmd & 0x40:
                copy_size |= data[offset] << 16
                offset += 1

            # Size of 0 means 0x10000
            if copy_size == 0:
                copy_size = 0x10000

            ops.append(DeltaCopy(offset=copy_offset, size=copy_size))

        elif cmd > 0:
            # INSERT instruction - cmd is the size
            insert_data = data[offset : offset + cmd]
            offset += cmd
            ops.append(DeltaInsert(data=insert_data))

        else:
            # cmd == 0 is reserved/invalid
            raise ValueError("Invalid delta instruction: 0x00")

    return source_size, target_size, ops


def apply_delta(base: bytes, delta_ops: list[DeltaOp]) -> bytes:
    """Apply delta operations to base object."""
    result = bytearray()

    for op in delta_ops:
        match op:
            case DeltaInsert(data=data):
                result.extend(data)
            case DeltaCopy(offset=offset, size=size):
                result.extend(base[offset : offset + size])

    return bytes(result)


def create_delta(source: bytes, target: bytes) -> bytes:
    """
    Create delta from source to target.

    Uses a simple algorithm - production Git uses more sophisticated
    matching (rolling hash, etc.) for better compression.
    """
    result = bytearray()

    # Write sizes
    result.extend(_encode_delta_size(len(source)))
    result.extend(_encode_delta_size(len(target)))

    # Simple approach: find common substrings
    # For a basic implementation, we can use a sliding window
    ops = _compute_delta_ops(source, target)

    for op in ops:
        match op:
            case DeltaInsert(data=data):
                # Split into chunks of max 127 bytes
                for i in range(0, len(data), 127):
                    chunk = data[i : i + 127]
                    result.append(len(chunk))
                    result.extend(chunk)

            case DeltaCopy(offset=offset, size=size):
                result.extend(_encode_copy_instruction(offset, size))

    return bytes(result)


def _encode_delta_size(size: int) -> bytes:
    """Encode size as variable-length integer."""
    result = bytearray()
    while True:
        byte = size & 0x7F
        size >>= 7
        if size:
            byte |= 0x80
        result.append(byte)
        if not size:
            break
    return bytes(result)


def _encode_copy_instruction(offset: int, size: int) -> bytes:
    """Encode COPY instruction."""
    result = bytearray()
    cmd = 0x80
    data = bytearray()

    # Offset bytes
    if offset & 0xFF:
        cmd |= 0x01
        data.append(offset & 0xFF)
    if offset & 0xFF00:
        cmd |= 0x02
        data.append((offset >> 8) & 0xFF)
    if offset & 0xFF0000:
        cmd |= 0x04
        data.append((offset >> 16) & 0xFF)
    if offset & 0xFF000000:
        cmd |= 0x08
        data.append((offset >> 24) & 0xFF)

    # Size bytes (0x10000 encoded as size=0)
    actual_size = size if size != 0x10000 else 0
    if actual_size & 0xFF:
        cmd |= 0x10
        data.append(actual_size & 0xFF)
    if actual_size & 0xFF00:
        cmd |= 0x20
        data.append((actual_size >> 8) & 0xFF)
    if actual_size & 0xFF0000:
        cmd |= 0x40
        data.append((actual_size >> 16) & 0xFF)

    result.append(cmd)
    result.extend(data)
    return bytes(result)


def _compute_delta_ops(source: bytes, target: bytes) -> list[DeltaOp]:
    """
    Compute delta operations from source to target.

    This is a simplified algorithm. Git uses a rolling hash
    (similar to rsync) for much better match finding.
    """
    ops: list[DeltaOp] = []

    # Build index of 16-byte chunks in source
    chunk_size = 16
    source_index: dict[bytes, list[int]] = {}
    for i in range(len(source) - chunk_size + 1):
        chunk = source[i : i + chunk_size]
        if chunk not in source_index:
            source_index[chunk] = []
        source_index[chunk].append(i)

    target_pos = 0
    pending_insert = bytearray()

    while target_pos < len(target):
        # Try to find a match
        match_offset = -1
        match_length = 0

        if target_pos + chunk_size <= len(target):
            chunk = target[target_pos : target_pos + chunk_size]
            if chunk in source_index:
                for src_pos in source_index[chunk]:
                    # Extend match as far as possible
                    length = chunk_size
                    while (target_pos + length < len(target) and
                           src_pos + length < len(source) and
                           target[target_pos + length] == source[src_pos + length]):
                        length += 1

                    if length > match_length:
                        match_offset = src_pos
                        match_length = length

        if match_length >= chunk_size:
            # Emit pending insert if any
            if pending_insert:
                ops.append(DeltaInsert(data=bytes(pending_insert)))
                pending_insert = bytearray()

            # Emit copy
            ops.append(DeltaCopy(offset=match_offset, size=match_length))
            target_pos += match_length
        else:
            # No good match - accumulate for insert
            pending_insert.append(target[target_pos])
            target_pos += 1

    # Emit final pending insert
    if pending_insert:
        ops.append(DeltaInsert(data=bytes(pending_insert)))

    return ops
```

---

## 5. Pack File Reader

### 5.1 Implementation

```python
# gitpy/storage/pack.py

from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Iterator
import zlib
import hashlib

from .pack_index import PackIndex, PackIndexEntry
from .delta import parse_delta, apply_delta, PackObjectType


@dataclass(slots=True)
class PackObject:
    """Object read from pack file."""
    sha: str
    type_name: str
    data: bytes
    offset: int


class PackFile:
    """
    Reader for Git pack files.

    Pack files store multiple objects efficiently using
    zlib compression and delta encoding.
    """

    def __init__(self, pack_path: Path, index: Optional[PackIndex] = None):
        """
        Open pack file.

        Args:
            pack_path: Path to .pack file
            index: Optional pre-loaded index (loads from .idx if not provided)
        """
        self.pack_path = pack_path
        self._data = pack_path.read_bytes()

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

        # Cache for resolved objects (offset -> (type, data))
        self._cache: dict[int, tuple[str, bytes]] = {}

    def _read_header(self) -> tuple[int, int]:
        """Parse pack header."""
        if self._data[:4] != b"PACK":
            raise ValueError("Invalid pack signature")

        version = int.from_bytes(self._data[4:8], "big")
        object_count = int.from_bytes(self._data[8:12], "big")

        return version, object_count

    def _verify_checksum(self) -> bool:
        """Verify pack file integrity."""
        expected_sha = self._data[-20:]
        actual_sha = hashlib.sha1(self._data[:-20]).digest()
        return expected_sha == actual_sha

    def _read_object_at(self, offset: int) -> tuple[int, int, bytes, int]:
        """
        Read raw object data at offset.

        Returns:
            (object_type, uncompressed_size, compressed_data, next_offset)
        """
        pos = offset

        # Read type and size
        byte = self._data[pos]
        obj_type = (byte >> 4) & 0x07
        size = byte & 0x0F
        pos += 1

        shift = 4
        while byte & 0x80:
            byte = self._data[pos]
            size |= (byte & 0x7F) << shift
            shift += 7
            pos += 1

        # Handle delta base reference
        base_offset = None
        base_sha = None

        if obj_type == PackObjectType.OFS_DELTA:
            # Read negative offset to base
            byte = self._data[pos]
            base_offset_value = byte & 0x7F
            pos += 1

            while byte & 0x80:
                byte = self._data[pos]
                base_offset_value = ((base_offset_value + 1) << 7) | (byte & 0x7F)
                pos += 1

            base_offset = offset - base_offset_value

        elif obj_type == PackObjectType.REF_DELTA:
            # Read 20-byte SHA reference
            base_sha = self._data[pos : pos + 20].hex()
            pos += 20

        # Decompress data
        decompressor = zlib.decompressobj()
        decompressed = decompressor.decompress(self._data[pos:])
        next_offset = pos + len(self._data[pos:]) - len(decompressor.unused_data)

        return obj_type, size, decompressed, next_offset, base_offset, base_sha

    def read_object(self, sha: str) -> Optional[PackObject]:
        """
        Read object by SHA.

        Args:
            sha: 40-character hex SHA

        Returns:
            PackObject or None if not found
        """
        offset = self.index.get_offset(sha)
        if offset is None:
            return None

        type_name, data = self._resolve_object(offset)

        return PackObject(
            sha=sha,
            type_name=type_name,
            data=data,
            offset=offset
        )

    def _resolve_object(self, offset: int) -> tuple[str, bytes]:
        """
        Resolve object at offset, following delta chains.

        Returns:
            (type_name, object_data)
        """
        # Check cache
        if offset in self._cache:
            return self._cache[offset]

        obj_type, size, data, next_offset, base_offset, base_sha = \
            self._read_object_at(offset)

        if obj_type in (PackObjectType.COMMIT, PackObjectType.TREE,
                        PackObjectType.BLOB, PackObjectType.TAG):
            # Non-delta object
            type_name = PackObjectType(obj_type).to_object_type()
            result = (type_name, data)

        elif obj_type == PackObjectType.OFS_DELTA:
            # Delta with offset reference
            base_type, base_data = self._resolve_object(base_offset)
            _, _, delta_ops = parse_delta(data)
            resolved_data = apply_delta(base_data, delta_ops)
            result = (base_type, resolved_data)

        elif obj_type == PackObjectType.REF_DELTA:
            # Delta with SHA reference
            base_offset = self.index.get_offset(base_sha)
            if base_offset is None:
                raise ValueError(f"Base object not found: {base_sha}")
            base_type, base_data = self._resolve_object(base_offset)
            _, _, delta_ops = parse_delta(data)
            resolved_data = apply_delta(base_data, delta_ops)
            result = (base_type, resolved_data)

        else:
            raise ValueError(f"Unknown object type: {obj_type}")

        # Cache result
        self._cache[offset] = result
        return result

    def __contains__(self, sha: str) -> bool:
        return sha in self.index

    def __iter__(self) -> Iterator[PackObject]:
        """Iterate over all objects in pack."""
        for entry in self.index.entries:
            obj = self.read_object(entry.sha)
            if obj:
                yield obj

    def _build_index(self) -> PackIndex:
        """Build index by scanning pack file."""
        entries = []
        offset = 12  # After header

        for _ in range(self.object_count):
            # Read and resolve object
            obj_type, size, data, next_offset, base_offset, base_sha = \
                self._read_object_at(offset)

            # Resolve to get final type and data
            type_name, resolved_data = self._resolve_object(offset)

            # Compute SHA
            header = f"{type_name} {len(resolved_data)}\0".encode()
            sha = hashlib.sha1(header + resolved_data).hexdigest()

            # Compute CRC32 of compressed data
            compressed_end = next_offset
            compressed_data = self._data[offset:compressed_end]
            crc = zlib.crc32(compressed_data) & 0xFFFFFFFF

            entries.append(PackIndexEntry(sha=sha, offset=offset, crc32=crc))
            offset = next_offset

        pack_sha = self._data[-20:].hex()
        return PackIndex(pack_sha=pack_sha, entries=entries)
```

---

## 6. Pack File Writer

### 6.1 Implementation

```python
# gitpy/storage/pack_writer.py

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Optional
import zlib
import hashlib

from gitpy.objects import GitObject, create_object_data
from .pack import PackObjectType
from .pack_index import PackIndex, PackIndexEntry
from .delta import create_delta


@dataclass(slots=True)
class PackEntry:
    """Object to be written to pack."""
    sha: str
    type_name: str
    data: bytes
    delta_base_sha: Optional[str] = None  # If deltified


class PackWriter:
    """
    Writer for Git pack files.

    Creates .pack and .idx files from a collection of objects.
    """

    def __init__(self, objects_dir: Path):
        """
        Initialize pack writer.

        Args:
            objects_dir: Path to .git/objects directory
        """
        self.objects_dir = objects_dir
        self.pack_dir = objects_dir / "pack"
        self.pack_dir.mkdir(parents=True, exist_ok=True)

    def write_pack(
        self,
        objects: Iterable[GitObject],
        deltify: bool = True,
        window_size: int = 10,
    ) -> tuple[Path, Path]:
        """
        Write objects to a new pack file.

        Args:
            objects: Objects to pack
            deltify: Whether to use delta compression
            window_size: Number of recent objects to consider for delta base

        Returns:
            (pack_path, index_path)
        """
        # Collect all objects
        entries = []
        for obj in objects:
            data = create_object_data(obj)
            sha = hashlib.sha1(data).hexdigest()
            # Extract content (without header)
            null_idx = data.index(b"\0")
            content = data[null_idx + 1:]
            entries.append(PackEntry(
                sha=sha,
                type_name=obj.type_name,
                data=content,
            ))

        # Sort by type then size (helps delta compression)
        entries.sort(key=lambda e: (e.type_name, len(e.data)))

        # Optionally deltify
        if deltify:
            entries = self._deltify_entries(entries, window_size)

        # Write pack file
        pack_data = self._create_pack_data(entries)
        pack_sha = hashlib.sha1(pack_data).hexdigest()

        pack_path = self.pack_dir / f"pack-{pack_sha}.pack"
        pack_path.write_bytes(pack_data)

        # Create and write index
        index = self._create_index(entries, pack_data, pack_sha)
        idx_path = self.pack_dir / f"pack-{pack_sha}.idx"
        idx_path.write_bytes(index.serialize())

        return pack_path, idx_path

    def _deltify_entries(
        self,
        entries: list[PackEntry],
        window_size: int,
    ) -> list[PackEntry]:
        """Apply delta compression to entries."""
        result = []
        window: list[PackEntry] = []

        for entry in entries:
            best_delta = None
            best_base = None
            best_size = len(entry.data)

            # Try to deltify against recent objects of same type
            for base in window:
                if base.type_name != entry.type_name:
                    continue

                delta = create_delta(base.data, entry.data)
                if len(delta) < best_size:
                    best_delta = delta
                    best_base = base.sha
                    best_size = len(delta)

            if best_delta and len(best_delta) < len(entry.data) * 0.9:
                # Delta is significantly smaller
                result.append(PackEntry(
                    sha=entry.sha,
                    type_name=entry.type_name,
                    data=best_delta,
                    delta_base_sha=best_base,
                ))
            else:
                # Keep as non-delta
                result.append(entry)

            # Update window
            window.append(entry)
            if len(window) > window_size:
                window.pop(0)

        return result

    def _create_pack_data(self, entries: list[PackEntry]) -> bytes:
        """Create pack file content."""
        result = bytearray()

        # Header
        result.extend(b"PACK")
        result.extend((2).to_bytes(4, "big"))  # Version 2
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
                    header = self._encode_header(obj_type, len(entry.data))
                    result.extend(header)

                    # Encode negative offset
                    delta_offset = offset - base_offset
                    result.extend(self._encode_ofs_delta_offset(delta_offset))
                else:
                    # Use REF_DELTA (base not in this pack)
                    obj_type = PackObjectType.REF_DELTA
                    header = self._encode_header(obj_type, len(entry.data))
                    result.extend(header)
                    result.extend(bytes.fromhex(entry.delta_base_sha))
            else:
                # Non-delta object
                obj_type = PackObjectType.from_object_type(entry.type_name)
                header = self._encode_header(obj_type, len(entry.data))
                result.extend(header)

            # Compressed data
            compressed = zlib.compress(entry.data)
            result.extend(compressed)

        # Trailer (SHA-1 of everything)
        sha = hashlib.sha1(result).digest()
        result.extend(sha)

        return bytes(result)

    def _encode_header(self, obj_type: int, size: int) -> bytes:
        """Encode pack object header."""
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

    def _encode_ofs_delta_offset(self, offset: int) -> bytes:
        """Encode OFS_DELTA negative offset."""
        result = bytearray()
        result.append(offset & 0x7F)
        offset >>= 7

        while offset > 0:
            offset -= 1
            result.append(0x80 | (offset & 0x7F))
            offset >>= 7

        result.reverse()
        return bytes(result)

    def _create_index(
        self,
        entries: list[PackEntry],
        pack_data: bytes,
        pack_sha: str,
    ) -> PackIndex:
        """Create index for pack file."""
        # Calculate offsets and CRCs
        index_entries = []
        offset = 12  # After header

        for entry in entries:
            # Find end of this entry
            # (We need to decompress to find boundary)
            pos = offset

            # Skip header
            byte = pack_data[pos]
            pos += 1
            while byte & 0x80:
                byte = pack_data[pos]
                pos += 1

            # Skip delta base reference if present
            if entry.delta_base_sha:
                # Check if OFS or REF delta based on type
                obj_type = (pack_data[offset] >> 4) & 0x07
                if obj_type == PackObjectType.OFS_DELTA:
                    byte = pack_data[pos]
                    pos += 1
                    while byte & 0x80:
                        byte = pack_data[pos]
                        pos += 1
                else:
                    pos += 20

            # Find end of compressed data
            decompressor = zlib.decompressobj()
            decompressor.decompress(pack_data[pos:])
            compressed_size = len(pack_data[pos:]) - len(decompressor.unused_data)
            next_offset = pos + compressed_size

            # CRC32 of entire entry
            crc = zlib.crc32(pack_data[offset:next_offset]) & 0xFFFFFFFF

            index_entries.append(PackIndexEntry(
                sha=entry.sha,
                offset=offset,
                crc32=crc,
            ))

            offset = next_offset

        return PackIndex(pack_sha=pack_sha, entries=index_entries)
```

---

## 7. Integration with Object Database

### 7.1 Updated ObjectDatabase

```python
# Updates to gitpy/storage/database.py

class ObjectDatabase:
    """Extended to support pack files."""

    def __init__(self, git_dir: Path):
        self.git_dir = git_dir
        self.loose = LooseObjectStore(git_dir)
        self._pack_files: list[PackFile] = []
        self._load_packs()

    def _load_packs(self) -> None:
        """Load all pack files from objects/pack/."""
        pack_dir = self.git_dir / "objects" / "pack"
        if not pack_dir.exists():
            return

        for pack_path in pack_dir.glob("*.pack"):
            idx_path = pack_path.with_suffix(".idx")
            if idx_path.exists():
                pack = PackFile(pack_path)
                self._pack_files.append(pack)

    def exists(self, sha: str) -> bool:
        """Check if object exists in loose or pack storage."""
        if len(sha) < 40:
            sha = self._resolve_short_sha(sha)
            if sha is None:
                return False

        # Check loose objects
        if self.loose.exists(sha):
            return True

        # Check pack files
        for pack in self._pack_files:
            if sha in pack:
                return True

        return False

    def read_raw(self, sha: str) -> bytes:
        """Read raw object data from loose or pack storage."""
        if len(sha) < 40:
            full_sha = self._resolve_short_sha(sha)
            if full_sha is None:
                raise FileNotFoundError(f"Object not found: {sha}")
            sha = full_sha

        # Try loose first
        if self.loose.exists(sha):
            return self.loose.read(sha)

        # Try pack files
        for pack in self._pack_files:
            obj = pack.read_object(sha)
            if obj:
                # Reconstruct full object with header
                header = f"{obj.type_name} {len(obj.data)}\0".encode()
                return header + obj.data

        raise FileNotFoundError(f"Object not found: {sha}")

    def repack(self, gc: bool = False) -> tuple[Path, Path]:
        """
        Repack all objects into a single pack file.

        Args:
            gc: If True, also remove loose objects that are now packed

        Returns:
            (pack_path, index_path)
        """
        from .pack_writer import PackWriter

        # Collect all objects
        objects = list(self._iter_all_objects())

        # Write new pack
        writer = PackWriter(self.git_dir / "objects")
        pack_path, idx_path = writer.write_pack(objects)

        # Reload packs
        self._pack_files.clear()
        self._load_packs()

        if gc:
            # Remove loose objects that are now in packs
            for sha in list(self.loose.iter_objects()):
                if any(sha in pack for pack in self._pack_files):
                    self.loose.delete(sha)

        return pack_path, idx_path

    def _iter_all_objects(self) -> Iterator[GitObject]:
        """Iterate over all objects in the database."""
        seen: set[str] = set()

        # Loose objects
        for sha in self.loose.iter_objects():
            if sha not in seen:
                seen.add(sha)
                yield self.read(sha)

        # Pack objects
        for pack in self._pack_files:
            for obj in pack:
                if obj.sha not in seen:
                    seen.add(obj.sha)
                    yield self.read(obj.sha)
```

---

## 8. Test Cases

### 8.1 Pack Header Tests

```python
import pytest
from gitpy.storage.pack import PackFile, PackObjectType

class TestPackHeader:

    def test_read_valid_header(self):
        """Parse valid pack header."""
        # PACK + version 2 + 5 objects
        data = b"PACK" + (2).to_bytes(4, "big") + (5).to_bytes(4, "big")
        data += b"\x00" * 100  # Padding for minimal valid pack

        # Would need complete pack for full test
        version, count = read_pack_header(data)
        assert version == 2
        assert count == 5

    def test_invalid_signature(self):
        """Reject invalid signature."""
        data = b"NOTPACK..."
        with pytest.raises(ValueError, match="Invalid pack signature"):
            read_pack_header(data)


class TestVarintEncoding:

    def test_encode_small_size(self):
        """Encode size that fits in 4 bits."""
        header = write_pack_object_header(PackObjectType.BLOB, 10)
        assert header == bytes([0x30 | 10])  # type=3, size=10

    def test_encode_medium_size(self):
        """Encode size requiring multiple bytes."""
        header = write_pack_object_header(PackObjectType.BLOB, 1000)
        # First byte: type=3, low 4 bits of size, MSB set
        # Remaining bytes encode rest of size
        obj_type, size, _ = read_pack_object_header(header, 0)
        assert obj_type == PackObjectType.BLOB
        assert size == 1000

    def test_roundtrip_various_sizes(self):
        """Encode/decode roundtrip for various sizes."""
        for size in [0, 1, 15, 16, 127, 128, 1000, 65535, 1_000_000]:
            header = write_pack_object_header(PackObjectType.COMMIT, size)
            obj_type, decoded_size, _ = read_pack_object_header(header, 0)
            assert decoded_size == size
```

### 8.2 Delta Tests

```python
from gitpy.storage.delta import parse_delta, apply_delta, create_delta

class TestDelta:

    def test_parse_simple_delta(self):
        """Parse delta with copy and insert."""
        source = b"Hello, World!"
        target = b"Hello, Git World!"

        delta = create_delta(source, target)
        source_size, target_size, ops = parse_delta(delta)

        assert source_size == len(source)
        assert target_size == len(target)

    def test_apply_delta(self):
        """Apply delta to reconstruct target."""
        source = b"Hello, World!"
        target = b"Hello, Git World!"

        delta = create_delta(source, target)
        _, _, ops = parse_delta(delta)
        result = apply_delta(source, ops)

        assert result == target

    def test_delta_identical(self):
        """Delta of identical content is small."""
        data = b"x" * 1000
        delta = create_delta(data, data)

        # Should be much smaller than original
        assert len(delta) < len(data) // 2

    def test_delta_completely_different(self):
        """Delta of completely different content."""
        source = b"aaaa" * 100
        target = b"bbbb" * 100

        delta = create_delta(source, target)
        _, _, ops = parse_delta(delta)
        result = apply_delta(source, ops)

        assert result == target


class TestOFSDeltaOffset:

    def test_encode_decode_small(self):
        """Small offset roundtrip."""
        for offset in [1, 10, 127]:
            encoded = write_ofs_delta_offset(offset)
            decoded, _ = read_ofs_delta_offset(encoded, 0)
            assert decoded == offset

    def test_encode_decode_large(self):
        """Large offset roundtrip."""
        for offset in [128, 1000, 100000, 10_000_000]:
            encoded = write_ofs_delta_offset(offset)
            decoded, _ = read_ofs_delta_offset(encoded, 0)
            assert decoded == offset
```

### 8.3 Pack Index Tests

```python
from gitpy.storage.pack_index import PackIndex, PackIndexEntry

class TestPackIndex:

    def test_index_roundtrip(self):
        """Serialize and parse index."""
        entries = [
            PackIndexEntry(sha="a" * 40, offset=12, crc32=0x12345678),
            PackIndexEntry(sha="b" * 40, offset=100, crc32=0xDEADBEEF),
            PackIndexEntry(sha="f" * 40, offset=500, crc32=0xCAFEBABE),
        ]

        index = PackIndex(pack_sha="c" * 40, entries=entries)
        data = index.serialize()
        restored = PackIndex.parse(data)

        assert restored.object_count == 3
        assert restored.get_offset("a" * 40) == 12
        assert restored.get_offset("b" * 40) == 100
        assert restored.get_offset("f" * 40) == 500

    def test_fanout_table(self):
        """Fanout table enables fast lookup."""
        entries = [
            PackIndexEntry(sha="00" + "a" * 38, offset=12, crc32=0),
            PackIndexEntry(sha="00" + "b" * 38, offset=24, crc32=0),
            PackIndexEntry(sha="ff" + "c" * 38, offset=36, crc32=0),
        ]

        index = PackIndex(pack_sha="d" * 40, entries=entries)

        # First byte 0x00: 2 objects
        # First byte 0xff: 3 objects total
        assert index._fanout[0] == 2
        assert index._fanout[255] == 3

    def test_large_offset(self):
        """Handle offsets > 2GB."""
        large_offset = 0x100000000  # 4GB

        entries = [
            PackIndexEntry(sha="a" * 40, offset=large_offset, crc32=0),
        ]

        index = PackIndex(pack_sha="b" * 40, entries=entries)
        data = index.serialize()
        restored = PackIndex.parse(data)

        assert restored.get_offset("a" * 40) == large_offset
```

### 8.4 Integration Tests

```python
class TestPackFileIntegration:

    @pytest.fixture
    def repo(self, tmp_path):
        return Repository.init(tmp_path)

    def test_write_and_read_pack(self, repo):
        """Write objects to pack and read back."""
        # Create some objects
        blobs = [
            Blob(data=f"Content {i}".encode())
            for i in range(10)
        ]

        for blob in blobs:
            repo.objects.write(blob)

        # Repack
        pack_path, idx_path = repo.objects.repack()

        assert pack_path.exists()
        assert idx_path.exists()

        # Read back
        for blob in blobs:
            restored = repo.objects.read_blob(blob.oid)
            assert restored.data == blob.data

    def test_delta_compression(self, repo):
        """Verify delta compression reduces size."""
        # Create similar blobs
        base_content = b"x" * 10000
        blobs = [
            Blob(data=base_content),
            Blob(data=base_content + b"_modified"),
            Blob(data=b"prefix_" + base_content),
        ]

        for blob in blobs:
            repo.objects.write(blob)

        # Get loose size
        loose_size = sum(
            (repo.git_dir / "objects" / sha[:2] / sha[2:]).stat().st_size
            for sha in [b.oid for b in blobs]
        )

        # Repack
        pack_path, _ = repo.objects.repack()
        pack_size = pack_path.stat().st_size

        # Pack should be significantly smaller due to delta
        assert pack_size < loose_size * 0.5

    def test_git_compatibility(self, repo, tmp_path):
        """Verify pack files are compatible with real Git."""
        import subprocess

        # Create and pack objects
        blob = Blob(data=b"hello from gitpy\n")
        sha = repo.objects.write(blob)
        repo.objects.repack()

        # Use real Git to verify
        result = subprocess.run(
            ["git", "cat-file", "-p", sha],
            cwd=repo.worktree,
            capture_output=True,
            text=True,
        )

        assert result.returncode == 0
        assert result.stdout == "hello from gitpy\n"
```

---

## 9. Acceptance Criteria

### 9.1 Functional Requirements

- [ ] Pack files can be read and objects extracted
- [ ] Pack index enables O(1) lookup by SHA
- [ ] OFS_DELTA objects are correctly resolved
- [ ] REF_DELTA objects are correctly resolved
- [ ] Delta chains of arbitrary depth are handled
- [ ] Pack files can be written from loose objects
- [ ] Delta compression is applied when beneficial
- [ ] Large offsets (>2GB) are handled correctly

### 9.2 Non-Functional Requirements

- [ ] Compatible with Git pack format v2
- [ ] Pack files created by gitpy are readable by real Git
- [ ] Pack files created by Git are readable by gitpy
- [ ] Memory efficient (streaming where possible)
- [ ] Reasonable performance for typical repository sizes

### 9.3 Verification Commands

```bash
# Create pack with real Git, read with gitpy
git gc
# gitpy should read objects from .git/objects/pack/*.pack

# Create pack with gitpy, read with real Git
gitpy repack
git cat-file -p <sha>  # Should work

# Verify pack integrity
git verify-pack -v .git/objects/pack/*.pack

# Compare delta compression
ls -la .git/objects/pack/
```

---

## 10. File Structure

```
gitpy/
└── storage/
    ├── __init__.py
    ├── compression.py    # Zlib utilities
    ├── database.py       # ObjectDatabase (updated)
    ├── loose.py          # LooseObjectStore
    ├── delta.py          # Delta encoding/decoding
    ├── pack.py           # PackFile reader
    ├── pack_index.py     # PackIndex
    └── pack_writer.py    # PackWriter
```

---

## 11. Implementation Notes

### 11.1 Delta Base Selection

Git uses sophisticated heuristics for choosing delta bases:
- Objects of the same type
- Similar file paths (from tree entries)
- Similar sizes
- Rolling hash for content similarity

For initial implementation, a simpler approach (recent objects of same type) is acceptable.

### 11.2 Thin Packs

For network transfer, Git supports "thin packs" that reference base objects not in the pack itself. These are used during fetch/push and must be "thickened" before storage.

### 11.3 Multi-Pack Index

Git 2.28+ supports a multi-pack-index for repositories with many pack files. This is an optimization for very large repositories and can be deferred.

### 11.4 Performance Considerations

- Cache resolved delta objects to avoid re-resolution
- Use memory-mapped files for large packs
- Build object offset index on first access, cache for reuse
- Consider thread safety for concurrent access

---

## 12. References

- [Git Pack Format Documentation](https://git-scm.com/docs/pack-format)
- [Git Index Format](https://git-scm.com/docs/index-format)
- [Pro Git Book - Packfiles](https://git-scm.com/book/en/v2/Git-Internals-Packfiles)
- [Git Source: pack.h](https://github.com/git/git/blob/master/pack.h)
- [Git Source: pack-objects.c](https://github.com/git/git/blob/master/pack-objects.c)
