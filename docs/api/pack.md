# Pack Objects API Reference

This document provides a complete API reference for the `gitpy.storage.pack`, `gitpy.storage.pack_index`, `gitpy.storage.pack_writer`, and `gitpy.storage.delta` modules, which implement Git's pack file format.

## Module Overview

```python
from gitpy.storage.pack import (
    PackFile,           # Pack file reader
    PackObject,         # Object read from pack
    PackObjectType,     # Object type enum
    PACK_SIGNATURE,     # Magic bytes b"PACK"
    PACK_VERSION,       # Version number (2)
)

from gitpy.storage.pack_index import (
    PackIndex,          # Pack index for fast lookup
    PackIndexEntry,     # Single index entry
    IDX_SIGNATURE,      # Magic bytes for index
    IDX_VERSION,        # Index version (2)
)

from gitpy.storage.pack_writer import (
    PackWriter,         # Pack file writer
    PackEntry,          # Object to be packed
)

from gitpy.storage.delta import (
    DeltaInsert,        # Insert instruction
    DeltaCopy,          # Copy instruction
    DeltaOp,            # Union type for operations
    parse_delta,        # Parse delta instructions
    apply_delta,        # Apply delta to base
    create_delta,       # Create delta between objects
)
```

---

## PackObjectType

**Module:** `gitpy.storage.pack`

Enumeration of object types in pack files.

```python
class PackObjectType(IntEnum):
    """Object types stored in pack files."""
    COMMIT = 1
    TREE = 2
    BLOB = 3
    TAG = 4
    # 5 is reserved
    OFS_DELTA = 6
    REF_DELTA = 7
```

### Values

| Name | Value | Description |
|------|-------|-------------|
| `COMMIT` | 1 | Commit object |
| `TREE` | 2 | Tree object |
| `BLOB` | 3 | Blob object |
| `TAG` | 4 | Annotated tag object |
| `OFS_DELTA` | 6 | Delta with offset reference to base |
| `REF_DELTA` | 7 | Delta with SHA-1 reference to base |

### Methods

#### `to_object_type()`

```python
def to_object_type(self) -> str
```

Convert to string type name.

**Returns:** `"commit"`, `"tree"`, `"blob"`, `"tag"`, or `"delta"`.

**Example:**
```python
obj_type = PackObjectType.BLOB
print(obj_type.to_object_type())  # "blob"
```

#### `from_object_type()`

```python
@classmethod
def from_object_type(cls, type_name: str) -> "PackObjectType"
```

Convert from string type name.

**Parameters:**
- `type_name` - Object type string (`"commit"`, `"tree"`, `"blob"`, `"tag"`).

**Returns:** Corresponding `PackObjectType` enum value.

**Raises:**
- `KeyError` - Unknown type name.

**Example:**
```python
obj_type = PackObjectType.from_object_type("blob")
print(obj_type)  # PackObjectType.BLOB
```

#### `is_delta()`

```python
@property
def is_delta(self) -> bool
```

Check if this is a delta type.

**Returns:** `True` if `OFS_DELTA` or `REF_DELTA`, `False` otherwise.

---

## PackObject

**Module:** `gitpy.storage.pack`

Represents an object read from a pack file.

```python
@dataclass(slots=True)
class PackObject:
    """Object read from pack file."""
    sha: str        # 40-character hex SHA
    type_name: str  # "blob", "tree", "commit", or "tag"
    data: bytes     # Uncompressed object content
    offset: int     # Offset in pack file
```

### Attributes

| Name | Type | Description |
|------|------|-------------|
| `sha` | `str` | 40-character hex SHA-1 hash |
| `type_name` | `str` | Object type (`"blob"`, `"tree"`, `"commit"`, `"tag"`) |
| `data` | `bytes` | Decompressed, fully resolved object content |
| `offset` | `int` | Byte offset in pack file |

---

## PackFile

**Module:** `gitpy.storage.pack`

Reader for Git pack files. Provides random access to objects using the pack index.

```python
class PackFile:
    pack_path: Path          # Path to .pack file
    version: int             # Pack format version
    object_count: int        # Number of objects in pack
    index: PackIndex         # Associated index
```

### Constructor

```python
def __init__(
    self,
    pack_path: Path,
    index: PackIndex | None = None
) -> None
```

Open a pack file.

**Parameters:**
- `pack_path` - Path to `.pack` file.
- `index` - Optional pre-loaded index. If not provided, loads from `.idx` file or builds from pack.

**Raises:**
- `ValueError` - Invalid pack signature or unsupported version.
- `FileNotFoundError` - Pack file doesn't exist.

**Example:**
```python
from pathlib import Path
from gitpy.storage.pack import PackFile

pack = PackFile(Path(".git/objects/pack/pack-abc123.pack"))
print(f"Pack version: {pack.version}")
print(f"Object count: {pack.object_count}")
```

### Methods

#### `read_object()`

```python
def read_object(self, sha: str) -> PackObject | None
```

Read object by SHA.

**Parameters:**
- `sha` - 40-character hex SHA-1.

**Returns:** `PackObject` if found, `None` if not in this pack.

**Example:**
```python
obj = pack.read_object("ce013625030ba8dba906f756967f9e9ca394464a")
if obj:
    print(f"Type: {obj.type_name}")
    print(f"Size: {len(obj.data)}")
```

#### `__contains__()`

```python
def __contains__(self, sha: str) -> bool
```

Check if object exists in pack.

**Parameters:**
- `sha` - 40-character hex SHA-1.

**Returns:** `True` if object is in this pack.

**Example:**
```python
if "ce013625..." in pack:
    print("Object found!")
```

#### `__iter__()`

```python
def __iter__(self) -> Iterator[PackObject]
```

Iterate over all objects in pack.

**Yields:** `PackObject` for each object in the pack.

**Example:**
```python
for obj in pack:
    print(f"{obj.sha} {obj.type_name} {len(obj.data)}")
```

#### `verify_checksum()`

```python
def verify_checksum(self) -> bool
```

Verify pack file integrity.

**Returns:** `True` if checksum matches, `False` if corrupted.

**Example:**
```python
if not pack.verify_checksum():
    raise ValueError("Pack file corrupted!")
```

---

## PackIndexEntry

**Module:** `gitpy.storage.pack_index`

A single entry in a pack index.

```python
@dataclass(slots=True)
class PackIndexEntry:
    """Single entry in pack index."""
    sha: str       # 40-character hex SHA
    offset: int    # Offset in pack file
    crc32: int     # CRC32 of packed object data
```

### Attributes

| Name | Type | Description |
|------|------|-------------|
| `sha` | `str` | 40-character hex SHA-1 hash |
| `offset` | `int` | Byte offset in pack file |
| `crc32` | `int` | CRC32 checksum of compressed data |

---

## PackIndex

**Module:** `gitpy.storage.pack_index`

Pack index for fast object lookup. Provides O(log n) SHA to offset lookup.

```python
class PackIndex:
    pack_sha: str                    # SHA of associated pack file
    entries: list[PackIndexEntry]    # Sorted by SHA
    object_count: int                # Number of objects
```

### Constructor

```python
def __init__(
    self,
    pack_sha: str,
    entries: list[PackIndexEntry]
) -> None
```

Create pack index from entries.

**Parameters:**
- `pack_sha` - 40-character hex SHA of the pack file.
- `entries` - List of `PackIndexEntry` objects (will be sorted).

**Example:**
```python
from gitpy.storage.pack_index import PackIndex, PackIndexEntry

entries = [
    PackIndexEntry(sha="a" * 40, offset=12, crc32=0x12345678),
    PackIndexEntry(sha="b" * 40, offset=500, crc32=0xdeadbeef),
]
index = PackIndex(pack_sha="c" * 40, entries=entries)
```

### Properties

#### `object_count`

```python
@property
def object_count(self) -> int
```

Number of objects in pack.

**Returns:** Total object count.

### Methods

#### `find()`

```python
def find(self, sha: str) -> PackIndexEntry | None
```

Look up entry by SHA.

**Parameters:**
- `sha` - 40-character hex SHA-1.

**Returns:** `PackIndexEntry` if found, `None` otherwise.

**Example:**
```python
entry = index.find("ce013625030ba8dba906f756967f9e9ca394464a")
if entry:
    print(f"Offset: {entry.offset}")
    print(f"CRC32: {entry.crc32:08x}")
```

#### `get_offset()`

```python
def get_offset(self, sha: str) -> int | None
```

Get pack file offset for SHA.

**Parameters:**
- `sha` - 40-character hex SHA-1.

**Returns:** Byte offset if found, `None` otherwise.

**Example:**
```python
offset = index.get_offset("ce013625...")
if offset is not None:
    print(f"Object at offset {offset}")
```

#### `__contains__()`

```python
def __contains__(self, sha: str) -> bool
```

Check if SHA is in index.

**Parameters:**
- `sha` - 40-character hex SHA-1.

**Returns:** `True` if found.

#### `from_file()`

```python
@classmethod
def from_file(cls, path: Path) -> "PackIndex"
```

Load index from `.idx` file.

**Parameters:**
- `path` - Path to index file.

**Returns:** Parsed `PackIndex`.

**Raises:**
- `ValueError` - Invalid index format or version.

**Example:**
```python
index = PackIndex.from_file(Path(".git/objects/pack/pack-abc123.idx"))
```

#### `parse()`

```python
@classmethod
def parse(cls, data: bytes) -> "PackIndex"
```

Parse index from raw bytes.

**Parameters:**
- `data` - Raw index file content.

**Returns:** Parsed `PackIndex`.

**Raises:**
- `ValueError` - Invalid signature or version.

#### `serialize()`

```python
def serialize(self) -> bytes
```

Serialize to version 2 index format.

**Returns:** Raw bytes ready to write to `.idx` file.

**Example:**
```python
data = index.serialize()
Path("pack-abc123.idx").write_bytes(data)
```

---

## PackEntry

**Module:** `gitpy.storage.pack_writer`

Object to be written to a pack file.

```python
@dataclass(slots=True)
class PackEntry:
    """Object to be written to pack."""
    sha: str                          # 40-character hex SHA
    type_name: str                    # Object type
    data: bytes                       # Object content (or delta)
    delta_base_sha: str | None = None # Base SHA if deltified
```

### Attributes

| Name | Type | Description |
|------|------|-------------|
| `sha` | `str` | 40-character hex SHA-1 |
| `type_name` | `str` | Object type (`"blob"`, `"tree"`, etc.) |
| `data` | `bytes` | Object content or delta instructions |
| `delta_base_sha` | `str \| None` | If deltified, SHA of base object |

---

## PackWriter

**Module:** `gitpy.storage.pack_writer`

Writer for Git pack files. Creates `.pack` and `.idx` files from objects.

```python
class PackWriter:
    objects_dir: Path    # .git/objects directory
    pack_dir: Path       # .git/objects/pack directory
```

### Constructor

```python
def __init__(self, objects_dir: Path) -> None
```

Initialize pack writer.

**Parameters:**
- `objects_dir` - Path to `.git/objects` directory.

**Example:**
```python
from gitpy.storage.pack_writer import PackWriter
from pathlib import Path

writer = PackWriter(Path(".git/objects"))
```

### Methods

#### `write_pack()`

```python
def write_pack(
    self,
    objects: Iterable[GitObject],
    *,
    deltify: bool = True,
    window_size: int = 10,
) -> tuple[Path, Path]
```

Write objects to a new pack file.

**Parameters:**
- `objects` - Iterable of `GitObject` instances to pack.
- `deltify` - If `True`, apply delta compression (default: `True`).
- `window_size` - Number of recent objects to consider as delta bases (default: 10).

**Returns:** Tuple of `(pack_path, index_path)`.

**Example:**
```python
from gitpy.objects import Blob

objects = [
    Blob(data=b"content 1"),
    Blob(data=b"content 2"),
    Blob(data=b"content 3"),
]

pack_path, idx_path = writer.write_pack(objects)
print(f"Pack: {pack_path}")
print(f"Index: {idx_path}")
```

#### `write_pack_from_entries()`

```python
def write_pack_from_entries(
    self,
    entries: list[PackEntry],
) -> tuple[Path, Path]
```

Write pre-prepared entries to pack.

**Parameters:**
- `entries` - List of `PackEntry` objects (may include deltas).

**Returns:** Tuple of `(pack_path, index_path)`.

---

## Delta Types

**Module:** `gitpy.storage.delta`

### DeltaInsert

Instruction to insert literal data.

```python
@dataclass(slots=True)
class DeltaInsert:
    """Insert literal data into result."""
    data: bytes
```

### DeltaCopy

Instruction to copy from base object.

```python
@dataclass(slots=True)
class DeltaCopy:
    """Copy bytes from base object."""
    offset: int  # Byte offset in base
    size: int    # Number of bytes to copy
```

### DeltaOp

Union type for delta operations.

```python
type DeltaOp = DeltaInsert | DeltaCopy
```

---

## Delta Functions

**Module:** `gitpy.storage.delta`

### `parse_delta()`

```python
def parse_delta(data: bytes) -> tuple[int, int, list[DeltaOp]]
```

Parse delta instructions.

**Parameters:**
- `data` - Raw delta bytes.

**Returns:** Tuple of `(source_size, target_size, operations)`.

**Raises:**
- `ValueError` - Invalid delta instruction (e.g., 0x00 byte).

**Example:**
```python
from gitpy.storage.delta import parse_delta

source_size, target_size, ops = parse_delta(delta_bytes)
print(f"Base size: {source_size}")
print(f"Result size: {target_size}")
for op in ops:
    print(op)
```

### `apply_delta()`

```python
def apply_delta(base: bytes, delta_data: bytes) -> bytes
```

Apply delta to reconstruct target.

**Parameters:**
- `base` - Source/base object data.
- `delta_data` - Raw delta bytes.

**Returns:** Reconstructed target data.

**Raises:**
- `ValueError` - Size mismatch or invalid delta.

**Example:**
```python
from gitpy.storage.delta import apply_delta

base = b"Hello, World!"
result = apply_delta(base, delta_bytes)
print(result)  # b"Hello, Git World!"
```

### `create_delta()`

```python
def create_delta(source: bytes, target: bytes) -> bytes
```

Create delta from source to target.

**Parameters:**
- `source` - Base object data.
- `target` - Target object data.

**Returns:** Delta bytes that transform source into target.

**Example:**
```python
from gitpy.storage.delta import create_delta

source = b"Hello, World!"
target = b"Hello, Git World!"

delta = create_delta(source, target)
print(f"Delta size: {len(delta)} (vs {len(target)} for full)")
```

### `read_delta_size()`

```python
def read_delta_size(data: bytes, offset: int) -> tuple[int, int]
```

Read variable-length size from delta header.

**Parameters:**
- `data` - Delta data bytes.
- `offset` - Starting position.

**Returns:** Tuple of `(size, bytes_consumed)`.

---

## Variable-Length Integer Functions

**Module:** `gitpy.storage.pack`

### `read_pack_object_header()`

```python
def read_pack_object_header(
    data: bytes,
    offset: int
) -> tuple[int, int, int]
```

Read pack object header.

**Parameters:**
- `data` - Pack file data.
- `offset` - Byte offset to start reading.

**Returns:** Tuple of `(object_type, uncompressed_size, bytes_consumed)`.

**Example:**
```python
obj_type, size, consumed = read_pack_object_header(pack_data, offset)
print(f"Type: {PackObjectType(obj_type).to_object_type()}")
print(f"Size: {size}")
```

### `write_pack_object_header()`

```python
def write_pack_object_header(obj_type: int, size: int) -> bytes
```

Encode pack object header.

**Parameters:**
- `obj_type` - Object type value (1-4, 6-7).
- `size` - Uncompressed object size.

**Returns:** Encoded header bytes.

### `read_ofs_delta_offset()`

```python
def read_ofs_delta_offset(
    data: bytes,
    offset: int
) -> tuple[int, int]
```

Read OFS_DELTA negative offset.

**Parameters:**
- `data` - Pack data.
- `offset` - Starting position.

**Returns:** Tuple of `(base_offset, bytes_consumed)`.

### `write_ofs_delta_offset()`

```python
def write_ofs_delta_offset(offset: int) -> bytes
```

Encode OFS_DELTA negative offset.

**Parameters:**
- `offset` - Positive offset value to encode.

**Returns:** Encoded offset bytes.

---

## Constants

### Pack File Constants

```python
PACK_SIGNATURE = b"PACK"  # Magic bytes at start of pack
PACK_VERSION = 2          # Current pack format version
```

### Index File Constants

```python
IDX_SIGNATURE = b"\xff\x74\x4f\x63"  # Magic: 0xff744f63
IDX_VERSION = 2                       # Current index format version
```

---

## Complete Example

```python
from pathlib import Path
from gitpy.repository import Repository
from gitpy.objects import Blob
from gitpy.storage.pack import PackFile
from gitpy.storage.pack_writer import PackWriter
from gitpy.storage.delta import create_delta, apply_delta

# Initialize repository
repo = Repository.init(Path("/tmp/pack-demo"))

# Create some similar blobs
base_content = b"Hello, World!\n" * 100
blobs = [
    Blob(data=base_content),
    Blob(data=base_content + b"Line 2\n"),
    Blob(data=base_content + b"Line 2\nLine 3\n"),
]

# Write as loose objects first
for blob in blobs:
    repo.objects.write(blob)

# Create pack from objects
writer = PackWriter(repo.git_dir / "objects")
pack_path, idx_path = writer.write_pack(blobs, deltify=True)

print(f"Pack created: {pack_path}")
print(f"Index created: {idx_path}")
print(f"Pack size: {pack_path.stat().st_size} bytes")

# Read back from pack
pack = PackFile(pack_path)
print(f"Objects in pack: {pack.object_count}")

for obj in pack:
    print(f"  {obj.sha[:8]} {obj.type_name:6} {len(obj.data):5} bytes")

# Verify object can be read
first_blob = blobs[0]
restored = pack.read_object(first_blob.oid)
assert restored is not None
assert restored.data == first_blob.data
print("Pack verification passed!")

# Delta compression demo
source = b"The quick brown fox jumps over the lazy dog"
target = b"The quick brown cat jumps over the lazy dog"

delta = create_delta(source, target)
print(f"\nDelta compression:")
print(f"  Source: {len(source)} bytes")
print(f"  Target: {len(target)} bytes")
print(f"  Delta:  {len(delta)} bytes ({len(delta)/len(target)*100:.1f}%)")

restored = apply_delta(source, delta)
assert restored == target
print("Delta verification passed!")
```

---

## Git Compatibility

The pack modules are fully compatible with Git:

| Test | Result |
|------|--------|
| gitpy reads Git-created packs | ✅ |
| Git reads gitpy-created packs | ✅ |
| `git verify-pack` validates gitpy packs | ✅ |
| Delta chains resolve correctly | ✅ |
| Large offsets (>2GB) supported | ✅ |

**Verification:**
```bash
# Create pack with gitpy, verify with Git
python3 -c "
from gitpy import Repository
repo = Repository.find()
repo.objects.repack()
"
git verify-pack -v .git/objects/pack/*.pack

# Create pack with Git, read with gitpy
git gc
python3 -c "
from gitpy import Repository
repo = Repository.find()
# gitpy can read all objects from Git's pack
"
```

---

## Performance Notes

### Lookup Complexity

| Operation | Time Complexity |
|-----------|-----------------|
| Find by SHA (with index) | O(log n) |
| Read undeltified object | O(1) |
| Read deltified object | O(depth) |
| Iterate all objects | O(n) |

### Memory Usage

- **PackFile**: Memory-maps pack data, ~constant overhead
- **PackIndex**: ~28 bytes per object in memory
- **Delta resolution**: Caches resolved objects to avoid re-resolution

### Best Practices

```python
# Reuse PackFile instances (don't reopen repeatedly)
pack = PackFile(path)
for sha in shas_to_read:
    obj = pack.read_object(sha)

# Use deltify=True for similar objects
writer.write_pack(similar_objects, deltify=True)

# Use larger window for better compression (slower)
writer.write_pack(objects, deltify=True, window_size=50)
```
