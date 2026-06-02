# Understanding Git's Pack Index

This document explains how Git enables fast object lookup in pack files through index files. If you've ever wondered how Git finds objects instantly among millions, this guide reveals the elegant data structure that makes it possible.

## The Problem: Finding Objects in Packs

Pack files combine thousands or millions of objects into a single file. Without an index, finding an object would require scanning the entire pack:

```
Without index:
  Find object abc123...
  → Scan from start: 1MB... 10MB... 100MB... found at 150MB!
  → Time: O(pack size) = seconds to minutes

With index:
  Find object abc123...
  → Binary search in index: abc123 → offset 157,286,400
  → Seek directly to offset
  → Time: O(log n) = milliseconds
```

The pack index (`.idx` file) provides O(1) amortized lookup time regardless of pack size.

---

## Index File Location

For every `.pack` file, there's a corresponding `.idx` file:

```
.git/objects/pack/
├── pack-abc123def456.pack   # Object data (50MB)
├── pack-abc123def456.idx    # Index (~2MB)
├── pack-789abc012def.pack
└── pack-789abc012def.idx
```

The filenames match—same SHA identifies both files.

---

## Index Format Evolution

Git has used two index formats:

| Version | Introduced | Features |
|---------|-----------|----------|
| 1 | Original | Simple but limited to 2GB packs |
| 2 | Git 1.6+ | Current standard, supports >2GB packs |

Version 2 is the standard. Version 1 is obsolete but still parseable.

---

## Version 2 Index Structure

The index has a carefully designed layout:

```
┌────────────────────────────────────────────────────────────────┐
│                        HEADER (8 bytes)                        │
│     Magic: 0xff 0x74 0x4f 0x63  │  Version: 0x00000002        │
├────────────────────────────────────────────────────────────────┤
│                     FANOUT TABLE (1024 bytes)                  │
│                    256 × 4-byte entries                        │
│                                                                 │
│  fanout[0x00] = count of objects with first SHA byte ≤ 0x00   │
│  fanout[0x01] = count of objects with first SHA byte ≤ 0x01   │
│  ...                                                           │
│  fanout[0xff] = total object count in pack                    │
├────────────────────────────────────────────────────────────────┤
│                      SHA TABLE (N × 20 bytes)                  │
│                     Objects sorted by SHA-1                    │
├────────────────────────────────────────────────────────────────┤
│                     CRC32 TABLE (N × 4 bytes)                  │
│               CRC32 of each object's packed data               │
├────────────────────────────────────────────────────────────────┤
│                    OFFSET TABLE (N × 4 bytes)                  │
│                  Pack file offset for each object              │
│            (high bit set → use large offset table)             │
├────────────────────────────────────────────────────────────────┤
│               LARGE OFFSET TABLE (variable)                    │
│            8-byte offsets for objects beyond 2GB               │
│                  (only if pack > 2GB)                          │
├────────────────────────────────────────────────────────────────┤
│                    PACK SHA (20 bytes)                         │
│               SHA-1 of the pack file content                   │
├────────────────────────────────────────────────────────────────┤
│                   INDEX SHA (20 bytes)                         │
│                  SHA-1 of all above content                    │
└────────────────────────────────────────────────────────────────┘
```

---

## The Fanout Table: Fast Search Narrowing

The fanout table is the key innovation. It's a 256-entry array where:

```
fanout[i] = number of objects with first SHA byte ≤ i
```

This creates a cumulative histogram:

```
Example with 1000 objects:
fanout[0x00] = 3     # 3 objects start with 00
fanout[0x01] = 7     # 7 objects start with ≤ 01
fanout[0x02] = 12    # 12 objects start with ≤ 02
...
fanout[0x80] = 512   # ~half start with ≤ 80 (expected)
...
fanout[0xfe] = 996   # 996 objects start with ≤ fe
fanout[0xff] = 1000  # 1000 total objects
```

### Using the Fanout Table

To find objects starting with byte `0xab`:

```python
def get_search_range(fanout: list[int], first_byte: int) -> tuple[int, int]:
    """Get range of indices for objects with given first byte."""
    if first_byte == 0:
        start = 0
    else:
        start = fanout[first_byte - 1]
    end = fanout[first_byte]
    return start, end

# Example: Find objects starting with 0xab
start, end = get_search_range(fanout, 0xab)
# start = fanout[0xaa] = 670
# end = fanout[0xab] = 674
# Only 4 objects to binary search!
```

This reduces search space by ~256x on average.

---

## Object Lookup Algorithm

Here's the complete lookup process:

```python
def find_object_offset(index: bytes, sha: str) -> int | None:
    """
    Find object's pack file offset using the index.

    Returns offset or None if not found.
    """
    sha_bytes = bytes.fromhex(sha)
    first_byte = sha_bytes[0]

    # Step 1: Read fanout to narrow search range
    fanout_base = 8  # After header
    if first_byte == 0:
        start = 0
    else:
        start = int.from_bytes(
            index[fanout_base + (first_byte - 1) * 4 :
                  fanout_base + first_byte * 4],
            "big"
        )
    end = int.from_bytes(
        index[fanout_base + first_byte * 4 :
              fanout_base + (first_byte + 1) * 4],
        "big"
    )

    # Get total object count
    total_objects = int.from_bytes(
        index[fanout_base + 255 * 4 : fanout_base + 256 * 4],
        "big"
    )

    # Calculate section offsets
    sha_table_base = fanout_base + 256 * 4
    crc_table_base = sha_table_base + total_objects * 20
    offset_table_base = crc_table_base + total_objects * 4

    # Step 2: Binary search in SHA table
    while start < end:
        mid = (start + end) // 2
        mid_sha = index[sha_table_base + mid * 20 :
                       sha_table_base + (mid + 1) * 20]

        if mid_sha == sha_bytes:
            # Found! Read offset
            offset_bytes = index[offset_table_base + mid * 4 :
                                offset_table_base + (mid + 1) * 4]
            offset = int.from_bytes(offset_bytes, "big")

            # Check for large offset
            if offset & 0x80000000:
                # High bit set - look up in large offset table
                large_idx = offset & 0x7fffffff
                large_base = offset_table_base + total_objects * 4
                offset = int.from_bytes(
                    index[large_base + large_idx * 8 :
                          large_base + (large_idx + 1) * 8],
                    "big"
                )

            return offset

        elif mid_sha < sha_bytes:
            start = mid + 1
        else:
            end = mid

    return None  # Not found
```

---

## CRC32 Verification

Each object has a CRC32 checksum of its packed data:

```
Object at offset 1000, ends at offset 1500
CRC32 = crc32(pack_data[1000:1500])
```

This enables:
- **Fast corruption detection**: No need to decompress
- **Partial pack verification**: Check specific objects
- **Network transfer verification**: Verify without unpacking

```python
import zlib

def verify_object_crc(pack_data: bytes, index: PackIndex, sha: str) -> bool:
    """Verify object hasn't been corrupted."""
    entry = index.find(sha)
    if entry is None:
        return False

    # Get object boundaries
    obj_start = entry.offset
    obj_end = find_object_end(pack_data, obj_start)

    # Compute CRC32
    actual_crc = zlib.crc32(pack_data[obj_start:obj_end]) & 0xffffffff

    return actual_crc == entry.crc32
```

---

## Large Pack Support (>2GB)

Standard 4-byte offsets can only address up to ~2GB. For larger packs:

```
Offset table entry interpretation:
  - If high bit (0x80000000) is clear: value is the offset
  - If high bit is set: remaining bits are index into large offset table
```

### Large Offset Table

```
┌───────────────────────────────────────────────────────────┐
│  Entry 0: 8-byte offset for first large object           │
│  Entry 1: 8-byte offset for second large object          │
│  ...                                                      │
└───────────────────────────────────────────────────────────┘
```

This allows packs up to 16 exabytes while keeping the common case (< 2GB) efficient.

### Example: 5GB Pack

```
Objects:
  sha_001: offset 100         → offset table: 0x00000064
  sha_002: offset 2,500,000   → offset table: 0x002625A0
  sha_003: offset 3,000,000,000 (3GB) → offset table: 0x80000000
                               → large_offset[0] = 0x00000000B2D05E00

First two objects use direct 4-byte offsets.
Third object uses large offset table.
```

---

## Building an Index

When creating a new pack file, the index is built simultaneously:

```python
from dataclasses import dataclass
from typing import NamedTuple

@dataclass(slots=True)
class PackIndexEntry:
    """Single entry in pack index."""
    sha: str      # 40-char hex
    offset: int   # Position in pack
    crc32: int    # CRC32 of packed data


class PackIndex:
    """Pack file index for fast object lookup."""

    def __init__(self, pack_sha: str, entries: list[PackIndexEntry]):
        # Sort entries by SHA (required for binary search)
        self.entries = sorted(entries, key=lambda e: e.sha)
        self.pack_sha = pack_sha
        self._build_fanout()
        self._sha_to_idx = {e.sha: i for i, e in enumerate(self.entries)}

    def _build_fanout(self) -> None:
        """Build fanout table from sorted entries."""
        self._fanout = [0] * 256

        for entry in self.entries:
            first_byte = int(entry.sha[:2], 16)
            # Increment counts for this byte and all higher bytes
            for i in range(first_byte, 256):
                self._fanout[i] += 1

    def get_offset(self, sha: str) -> int | None:
        """Look up offset by SHA."""
        idx = self._sha_to_idx.get(sha)
        if idx is not None:
            return self.entries[idx].offset
        return None

    def __contains__(self, sha: str) -> bool:
        return sha in self._sha_to_idx

    @property
    def object_count(self) -> int:
        return len(self.entries)
```

---

## Serializing the Index

Writing an index file:

```python
import hashlib

IDX_MAGIC = b"\xff\x74\x4f\x63"  # 0xff744f63
IDX_VERSION = 2


def serialize_index(index: PackIndex) -> bytes:
    """Serialize index to version 2 format."""
    result = bytearray()

    # Header
    result.extend(IDX_MAGIC)
    result.extend(IDX_VERSION.to_bytes(4, "big"))

    # Fanout table
    for count in index._fanout:
        result.extend(count.to_bytes(4, "big"))

    # SHA table (sorted)
    for entry in index.entries:
        result.extend(bytes.fromhex(entry.sha))

    # CRC32 table
    for entry in index.entries:
        result.extend(entry.crc32.to_bytes(4, "big"))

    # Offset table (with large offset handling)
    large_offsets: list[int] = []
    for entry in index.entries:
        if entry.offset >= 0x80000000:  # Needs large offset
            large_idx = len(large_offsets)
            large_offsets.append(entry.offset)
            result.extend((0x80000000 | large_idx).to_bytes(4, "big"))
        else:
            result.extend(entry.offset.to_bytes(4, "big"))

    # Large offset table
    for offset in large_offsets:
        result.extend(offset.to_bytes(8, "big"))

    # Pack SHA
    result.extend(bytes.fromhex(index.pack_sha))

    # Index SHA (hash of everything so far)
    index_sha = hashlib.sha1(result).digest()
    result.extend(index_sha)

    return bytes(result)
```

---

## Parsing an Index

Reading an existing index file:

```python
def parse_index(data: bytes) -> PackIndex:
    """Parse version 2 index file."""
    # Verify header
    if data[:4] != IDX_MAGIC:
        raise ValueError("Invalid index magic")

    version = int.from_bytes(data[4:8], "big")
    if version != 2:
        raise ValueError(f"Unsupported index version: {version}")

    # Read fanout table
    fanout_start = 8
    fanout = []
    for i in range(256):
        count = int.from_bytes(
            data[fanout_start + i * 4 : fanout_start + (i + 1) * 4],
            "big"
        )
        fanout.append(count)

    object_count = fanout[255]

    # Calculate section offsets
    sha_start = fanout_start + 256 * 4
    crc_start = sha_start + object_count * 20
    offset_start = crc_start + object_count * 4
    large_offset_start = offset_start + object_count * 4

    # Read tables
    entries = []
    for i in range(object_count):
        # SHA
        sha = data[sha_start + i * 20 : sha_start + (i + 1) * 20].hex()

        # CRC32
        crc32 = int.from_bytes(
            data[crc_start + i * 4 : crc_start + (i + 1) * 4],
            "big"
        )

        # Offset
        offset = int.from_bytes(
            data[offset_start + i * 4 : offset_start + (i + 1) * 4],
            "big"
        )
        if offset & 0x80000000:
            # Large offset
            large_idx = offset & 0x7fffffff
            offset = int.from_bytes(
                data[large_offset_start + large_idx * 8 :
                     large_offset_start + (large_idx + 1) * 8],
                "big"
            )

        entries.append(PackIndexEntry(sha=sha, offset=offset, crc32=crc32))

    # Extract pack SHA
    pack_sha_offset = len(data) - 40
    pack_sha = data[pack_sha_offset : pack_sha_offset + 20].hex()

    return PackIndex(pack_sha=pack_sha, entries=entries)
```

---

## Index Verification

The index has multiple integrity checks:

```python
def verify_index(index_data: bytes) -> bool:
    """Verify index file integrity."""
    # 1. Check header
    if index_data[:4] != IDX_MAGIC:
        return False

    version = int.from_bytes(index_data[4:8], "big")
    if version != 2:
        return False

    # 2. Verify index SHA (last 20 bytes)
    expected_sha = index_data[-20:]
    computed_sha = hashlib.sha1(index_data[:-20]).digest()
    if expected_sha != computed_sha:
        return False

    # 3. Verify fanout is monotonically increasing
    fanout_start = 8
    prev = 0
    for i in range(256):
        count = int.from_bytes(
            index_data[fanout_start + i * 4 : fanout_start + (i + 1) * 4],
            "big"
        )
        if count < prev:
            return False
        prev = count

    # 4. Verify SHAs are sorted
    object_count = prev
    sha_start = fanout_start + 256 * 4
    prev_sha = b"\x00" * 20
    for i in range(object_count):
        sha = index_data[sha_start + i * 20 : sha_start + (i + 1) * 20]
        if sha <= prev_sha:
            return False
        prev_sha = sha

    return True
```

---

## Performance Analysis

### Lookup Complexity

| Operation | Time | Space |
|-----------|------|-------|
| Find by SHA | O(log n) | O(1) |
| Fanout lookup | O(1) | - |
| Binary search | O(log(n/256)) | - |
| Overall | O(log n) ≈ O(1) | O(1) |

For practical purposes, lookup is effectively O(1) because:
- Fanout reduces search space by 256x
- Log₂(n/256) is small even for millions of objects
- Memory access patterns are cache-friendly

### Space Overhead

| Component | Size per Object |
|-----------|-----------------|
| SHA | 20 bytes |
| CRC32 | 4 bytes |
| Offset | 4 bytes (+ 8 for large) |
| **Total** | ~28 bytes |

For a pack with 100,000 objects: ~2.8MB index

---

## Multi-Pack Index (MIDX)

Git 2.28+ supports a "multi-pack index" for repositories with many packs:

```
.git/objects/pack/
├── pack-aaa.pack
├── pack-aaa.idx
├── pack-bbb.pack
├── pack-bbb.idx
├── pack-ccc.pack
├── pack-ccc.idx
└── multi-pack-index   # Single index spanning all packs
```

Benefits:
- Single lookup across all packs
- Faster object resolution
- Better cache efficiency

This is an advanced optimization—the basic single-pack index is sufficient for most repositories.

---

## Command-Line Tools

### Inspect Index

```bash
# Show index summary
$ git show-index < .git/objects/pack/pack-*.idx | head
100 abc123def456... (blob)
250 789012345678... (commit)
...

# Verify index integrity
$ git verify-pack -v .git/objects/pack/pack-*.idx
```

### Index Statistics

```bash
# Count objects
$ git show-index < .git/objects/pack/*.idx | wc -l
50000

# Distribution by first byte (should be ~uniform)
$ git show-index < .git/objects/pack/*.idx | \
    cut -c1-2 | sort | uniq -c | head
  195 00
  198 01
  202 02
  ...
```

---

## Implementation in gitpy

### Module Structure

```python
# gitpy/storage/pack_index.py

from dataclasses import dataclass
from pathlib import Path
import hashlib

IDX_SIGNATURE = b"\xff\x74\x4f\x63"
IDX_VERSION = 2


@dataclass(slots=True)
class PackIndexEntry:
    """Single entry in pack index."""
    sha: str       # 40-char hex SHA
    offset: int    # Offset in pack file
    crc32: int     # CRC32 of packed object data


class PackIndex:
    """
    Pack index for fast object lookup.

    Provides O(log n) lookup of pack file offset by SHA.
    """

    def __init__(self, pack_sha: str, entries: list[PackIndexEntry]):
        self.pack_sha = pack_sha
        self.entries = sorted(entries, key=lambda e: e.sha)
        self._build_fanout()
        self._sha_to_idx = {e.sha: i for i, e in enumerate(self.entries)}

    def _build_fanout(self) -> None:
        """Build fanout table from entries."""
        self._fanout = [0] * 256
        counts = [0] * 256

        for entry in self.entries:
            first_byte = int(entry.sha[:2], 16)
            counts[first_byte] += 1

        # Convert to cumulative
        cumulative = 0
        for i in range(256):
            cumulative += counts[i]
            self._fanout[i] = cumulative

    def find(self, sha: str) -> PackIndexEntry | None:
        """Look up entry by SHA."""
        idx = self._sha_to_idx.get(sha)
        if idx is not None:
            return self.entries[idx]
        return None

    def get_offset(self, sha: str) -> int | None:
        """Get pack file offset for SHA."""
        entry = self.find(sha)
        return entry.offset if entry else None

    def __contains__(self, sha: str) -> bool:
        return sha in self._sha_to_idx

    @property
    def object_count(self) -> int:
        return len(self.entries)

    @classmethod
    def from_file(cls, path: Path) -> "PackIndex":
        """Load index from .idx file."""
        return parse_index(path.read_bytes())

    def serialize(self) -> bytes:
        """Serialize to index file format."""
        return serialize_index(self)
```

---

## Testing Index Code

```python
def test_index_roundtrip():
    """Serialize then parse should preserve data."""
    entries = [
        PackIndexEntry(sha="a" * 40, offset=100, crc32=0x12345678),
        PackIndexEntry(sha="b" * 40, offset=500, crc32=0xdeadbeef),
        PackIndexEntry(sha="f" * 40, offset=1000, crc32=0xcafebabe),
    ]

    index = PackIndex(pack_sha="c" * 40, entries=entries)
    data = index.serialize()
    restored = PackIndex.parse(data)

    assert restored.object_count == 3
    assert restored.get_offset("a" * 40) == 100
    assert restored.get_offset("b" * 40) == 500
    assert restored.get_offset("f" * 40) == 1000


def test_fanout_distribution():
    """Fanout should enable efficient lookup."""
    # Create entries with known distribution
    entries = [
        PackIndexEntry(sha="00" + "a" * 38, offset=100, crc32=0),
        PackIndexEntry(sha="00" + "b" * 38, offset=200, crc32=0),
        PackIndexEntry(sha="ff" + "c" * 38, offset=300, crc32=0),
    ]

    index = PackIndex(pack_sha="d" * 40, entries=entries)

    # Check fanout values
    assert index._fanout[0x00] == 2   # Two objects ≤ 0x00
    assert index._fanout[0xfe] == 2   # Still two (none in 01-fe)
    assert index._fanout[0xff] == 3   # Three total


def test_large_offset():
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

---

## Key Takeaways

1. **Fanout table** reduces search space by ~256x
2. **Binary search** on sorted SHAs gives O(log n) lookup
3. **CRC32 values** enable fast corruption detection
4. **Large offset table** supports packs up to 16 exabytes
5. **Trailing checksums** verify both pack and index integrity
6. **Compact format** keeps index ~28 bytes per object

The pack index is a masterpiece of data structure design—simple, efficient, and elegant. It transforms linear search into near-constant-time lookup, making Git fast regardless of repository size.

---

## What's Next?

- **[Pack Files](pack_files.md)**: How objects are stored in packs
- **[Delta Compression](delta_compression.md)**: How similar objects share storage
- **Implementation**: See `gitpy/storage/pack_index.py` for code
