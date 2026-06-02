# Understanding Git's Pack Files

This document explains how Git efficiently stores objects using pack files. If you've ever wondered why Git repositories are so compact or what happens during `git gc`, this guide will reveal Git's impressive compression techniques.

## The Big Picture: From Loose to Packed

In our previous exploration of [object storage](object_storage.md), we learned that Git stores objects as individual compressed files called "loose objects." While this works well for small repositories, it becomes inefficient at scale:

- **Filesystem overhead**: Thousands of small files strain the filesystem
- **No delta compression**: Similar files are stored separately
- **Network inefficiency**: Transferring many files is slow

**Pack files** solve all of these by combining many objects into a single file with sophisticated delta compression.

```
Before: .git/objects/
├── 00/a1b2c3...  # loose object
├── 01/d4e5f6...  # loose object
├── 02/g7h8i9...  # loose object
├── ... (thousands more)

After: .git/objects/pack/
├── pack-abc123.idx   # ~200KB index
└── pack-abc123.pack  # ~5MB packed data (was 50MB loose!)
```

---

## Why Pack Files Matter

### Space Savings

Consider a source file that changes slightly between commits. With loose objects:

```
commit 1: utils.py (10KB) → 10KB stored
commit 2: utils.py (10.1KB) → 10.1KB stored
commit 3: utils.py (10.2KB) → 10.2KB stored
...
100 commits: ~1GB stored
```

With pack files and delta compression:

```
commit 1: utils.py (10KB) → 10KB base
commit 2: utils.py delta → ~100 bytes
commit 3: utils.py delta → ~150 bytes
...
100 commits: ~20KB stored!
```

Delta compression stores only the *differences* between similar objects, not complete copies.

### Network Transfer

When you `git clone` or `git fetch`:

```
Without packs:
- Client: "I need objects a, b, c, d, e..."
- Server: Sends 1000 individual HTTP requests
- Time: Minutes to hours

With packs:
- Client: "I need these refs"
- Server: Creates single packfile with all needed objects
- Time: Seconds to minutes
```

Git was designed for the Linux kernel—millions of files, decades of history. Pack files make this manageable.

---

## When Pack Files Are Created

### Automatic Triggers

1. **`git gc`** (garbage collection):
   ```bash
   # Explicit gc
   $ git gc

   # Auto gc (triggered by git periodically)
   $ git gc --auto
   ```

2. **`git push` / `git fetch`**:
   - Objects sent over the network are always packed
   - The server creates a pack on-the-fly

3. **Automatic thresholds**:
   ```bash
   # Git auto-packs when:
   # - Loose objects exceed gc.auto (default: 6700)
   # - Packs exceed gc.autoPackLimit (default: 50)
   ```

### Manual Packing

```bash
# Create new pack from all loose objects
$ git repack -a -d

# Aggressive repacking (better compression, slower)
$ git repack -a -d -f --depth=50 --window=250
```

---

## Pack File Anatomy

### Overall Structure

A pack file (`.pack`) has three sections:

```
┌──────────────────────────────────────────────────────────────┐
│                      HEADER (12 bytes)                        │
│   Signature: "PACK"  │  Version: 2  │  Object Count: N       │
├──────────────────────────────────────────────────────────────┤
│                                                               │
│                      OBJECT ENTRIES                           │
│                                                               │
│   Entry 1: [header] [data]                                   │
│   Entry 2: [header] [delta-base-ref] [delta]                 │
│   Entry 3: [header] [data]                                   │
│   ...                                                         │
│   Entry N: [header] [data]                                   │
│                                                               │
├──────────────────────────────────────────────────────────────┤
│                      TRAILER (20 bytes)                       │
│                   SHA-1 of all above content                  │
└──────────────────────────────────────────────────────────────┘
```

### The Header

```
Bytes 0-3:  "PACK" (magic signature)
Bytes 4-7:  Version number (2 = current standard)
Bytes 8-11: Number of objects in pack (big-endian)
```

```python
# Reading the header
PACK_SIGNATURE = b"PACK"

def read_pack_header(data: bytes) -> tuple[int, int]:
    """Parse pack header."""
    if data[:4] != PACK_SIGNATURE:
        raise ValueError("Invalid pack signature")

    version = int.from_bytes(data[4:8], "big")
    object_count = int.from_bytes(data[8:12], "big")

    return version, object_count
```

### Object Types in Packs

Packs store six types of entries:

| Type | Value | Description |
|------|-------|-------------|
| `OBJ_COMMIT` | 1 | Commit object |
| `OBJ_TREE` | 2 | Tree object |
| `OBJ_BLOB` | 3 | Blob object |
| `OBJ_TAG` | 4 | Annotated tag |
| `OBJ_OFS_DELTA` | 6 | Delta with offset reference |
| `OBJ_REF_DELTA` | 7 | Delta with SHA reference |

Types 1-4 are "undeltified"—stored in full (but still compressed). Types 6-7 are deltas that reference a base object.

**Note**: Type 5 is reserved and unused.

### Object Entry Format

Each entry begins with a variable-length header:

```
┌───────────────────────────────────────────────────────────┐
│                    First byte                             │
│  ┌───┬───────┬───────────────────────────────────────┐   │
│  │MSB│ type  │         size (bits 0-3)               │   │
│  │(1)│  (3)  │              (4)                      │   │
│  └───┴───────┴───────────────────────────────────────┘   │
├───────────────────────────────────────────────────────────┤
│                 Continuation bytes                        │
│  ┌───┬───────────────────────────────────────────────┐   │
│  │MSB│              size (bits 4-10, 11-17, ...)     │   │
│  │(1)│                      (7)                      │   │
│  └───┴───────────────────────────────────────────────┘   │
│              (repeat while MSB=1)                         │
└───────────────────────────────────────────────────────────┘
```

The variable-length encoding allows arbitrary sizes without wasting bytes on small objects.

```python
def read_pack_object_header(data: bytes, offset: int) -> tuple[int, int, int]:
    """
    Read pack object header.

    Returns: (object_type, uncompressed_size, bytes_consumed)
    """
    byte = data[offset]
    obj_type = (byte >> 4) & 0x07  # Bits 4-6
    size = byte & 0x0F             # Bits 0-3

    consumed = 1
    shift = 4

    # Continue while MSB is set
    while byte & 0x80:
        byte = data[offset + consumed]
        size |= (byte & 0x7F) << shift
        shift += 7
        consumed += 1

    return obj_type, size, consumed
```

### Delta Base References

For delta objects (types 6 and 7), an additional reference follows the header:

**OFS_DELTA (type 6)**: Negative offset to base object in same pack
```
[header] [variable-length offset] [compressed delta]
```

**REF_DELTA (type 7)**: SHA-1 of base object (may be in another pack)
```
[header] [20-byte SHA] [compressed delta]
```

OFS_DELTA is more common in stored packs (faster to resolve). REF_DELTA is used in network transfers where the base might already exist on the receiver.

---

## Variable-Length Integer Encoding

Git uses clever encodings to minimize bytes:

### Size Encoding (in headers)

```
Size 0-15:     1 byte  (4 bits in first byte)
Size 16-2047:  2 bytes (4 + 7 bits)
Size up to ~2M: 3 bytes (4 + 7 + 7 bits)
...
```

### OFS_DELTA Offset Encoding

This encoding is particularly clever—it handles arbitrary offsets with minimal bytes:

```python
def read_ofs_delta_offset(data: bytes, offset: int) -> tuple[int, int]:
    """
    Read OFS_DELTA negative offset.

    The encoding adds 1 to each continuation byte to eliminate
    ambiguity in the representation.
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
```

Why the `+1`? Without it, there would be multiple ways to encode the same number. The `+1` ensures each value has exactly one encoding.

---

## Exploring Pack Files

### Command-Line Tools

```bash
# List all pack files
$ ls .git/objects/pack/
pack-abc123def456.idx
pack-abc123def456.pack

# Verify pack integrity
$ git verify-pack -v .git/objects/pack/*.pack

# Show pack statistics
$ git verify-pack -s .git/objects/pack/*.pack
statistics:
  objects: 1234
  total: 5MB
  delta: 890 (72%)

# List objects in a pack
$ git verify-pack -v .git/objects/pack/*.pack | head -20
abc123... commit 234  456  0
def456... tree   890  123  1
789abc... blob   45   67   2 \  # Delta chain start
012def... blob   12   34   3 789abc...  # Deltified against 789abc
```

### Understanding verify-pack Output

```
SHA          type  size  compressed-size  offset  [base-SHA depth]
abc123def... blob  1000  350             12
456789abc... blob  50    30              400     abc123def... 1
```

- **size**: Uncompressed size of the resolved object
- **compressed-size**: Bytes in pack file
- **offset**: Position in pack file
- **base-SHA**: For deltas, the base object
- **depth**: Delta chain depth (1 = direct delta, 2 = delta of delta, etc.)

### Reading Pack Files with Python

```python
import zlib
from pathlib import Path

def explore_pack(pack_path: Path):
    """Quick pack file exploration."""
    data = pack_path.read_bytes()

    # Check header
    assert data[:4] == b"PACK", "Not a pack file"
    version = int.from_bytes(data[4:8], "big")
    count = int.from_bytes(data[8:12], "big")

    print(f"Pack version: {version}")
    print(f"Object count: {count}")

    # Parse first few objects
    offset = 12
    for i in range(min(5, count)):
        obj_type, size, header_len = read_pack_object_header(data, offset)
        print(f"Object {i}: type={obj_type}, size={size}")
        offset += header_len
        # Skip compressed data (would need to decompress to find end)
        break  # Simplified - real parsing is more complex
```

---

## Delta Compression Deep Dive

Delta compression is the key to Git's storage efficiency. Let's understand how it works.

### The Basic Idea

Instead of storing complete copies of similar content:

```
Version 1: "Hello, World!\nThis is line 2.\nThis is line 3.\n"
Version 2: "Hello, Git World!\nThis is line 2.\nThis is line 3.\n"
```

Store the first version, then instructions to transform it:

```
Base: "Hello, World!\nThis is line 2.\nThis is line 3.\n"
Delta: "Copy bytes 0-6, Insert 'Git ', Copy bytes 7-end"
```

### Delta Instruction Format

Deltas consist of two instruction types:

**INSERT**: Add literal bytes
```
┌─────────────────────────────────────────┐
│ 0xxxxxxx │ literal data (x bytes)       │
└─────────────────────────────────────────┘
```
- First bit is 0
- Remaining 7 bits = length (1-127)
- Followed by that many literal bytes

**COPY**: Copy from base object
```
┌─────────────────────────────────────────┐
│ 1oooosss │ offset bytes │ size bytes    │
└─────────────────────────────────────────┘
```
- First bit is 1
- Next 4 bits indicate which offset bytes are present
- Next 3 bits indicate which size bytes are present
- Offset and size are little-endian

### Delta Structure

```
┌──────────────────────────────────────────┐
│     Source (base) size - varint          │
├──────────────────────────────────────────┤
│     Target (result) size - varint        │
├──────────────────────────────────────────┤
│     Delta instructions                    │
│     [COPY] [INSERT] [COPY] ...           │
└──────────────────────────────────────────┘
```

### Example: Applying a Delta

```python
def apply_delta(base: bytes, delta_data: bytes) -> bytes:
    """Reconstruct target from base + delta."""
    offset = 0

    # Read expected sizes (for verification)
    source_size, consumed = read_varint(delta_data, offset)
    offset += consumed
    target_size, consumed = read_varint(delta_data, offset)
    offset += consumed

    assert len(base) == source_size, "Base size mismatch"

    result = bytearray()

    while offset < len(delta_data):
        cmd = delta_data[offset]
        offset += 1

        if cmd & 0x80:
            # COPY instruction
            copy_offset, copy_size = parse_copy_instruction(cmd, delta_data, offset)
            result.extend(base[copy_offset : copy_offset + copy_size])
            offset += bytes_consumed_by_copy(cmd)

        elif cmd > 0:
            # INSERT instruction
            result.extend(delta_data[offset : offset + cmd])
            offset += cmd

        else:
            raise ValueError("Invalid delta instruction: 0x00")

    assert len(result) == target_size, "Target size mismatch"
    return bytes(result)
```

### Delta Chains

Deltas can be chained: Object A is a delta of B, which is a delta of C, which is stored in full.

```
Object A (newest) → delta of B
                     ↓
Object B          → delta of C
                     ↓
Object C (oldest) → stored in full
```

To read Object A:
1. Read C (decompress)
2. Apply delta to get B
3. Apply delta to get A

Git limits chain depth (default: 50) to balance compression vs. read speed.

---

## The Pack Index (.idx)

Pack files alone would require scanning the entire file to find an object. The index provides O(1) lookup.

### Index Structure (Version 2)

```
┌──────────────────────────────────────────────────────────────┐
│                    HEADER (8 bytes)                          │
│           Magic: 0xff744f63  │  Version: 2                   │
├──────────────────────────────────────────────────────────────┤
│                   FANOUT TABLE (1024 bytes)                  │
│                 256 entries × 4 bytes each                   │
│                                                              │
│  fanout[0x00] = count of objects with SHA starting ≤ 0x00   │
│  fanout[0x01] = count of objects with SHA starting ≤ 0x01   │
│  ...                                                         │
│  fanout[0xff] = total object count                          │
├──────────────────────────────────────────────────────────────┤
│                    SHA TABLE                                 │
│              N × 20-byte SHA-1 hashes                        │
│                   (sorted order)                             │
├──────────────────────────────────────────────────────────────┤
│                    CRC32 TABLE                               │
│              N × 4-byte CRC32 values                         │
│           (of compressed data in pack)                       │
├──────────────────────────────────────────────────────────────┤
│                   OFFSET TABLE                               │
│              N × 4-byte pack offsets                         │
│         (high bit set → use large offset table)              │
├──────────────────────────────────────────────────────────────┤
│               LARGE OFFSET TABLE (optional)                  │
│              8-byte offsets for packs > 2GB                  │
├──────────────────────────────────────────────────────────────┤
│                  PACK SHA (20 bytes)                         │
│                  INDEX SHA (20 bytes)                        │
└──────────────────────────────────────────────────────────────┘
```

### The Fanout Table Trick

The fanout table enables fast binary search:

```python
def find_object(index: PackIndex, sha: str) -> int | None:
    """Find object offset in pack using index."""
    sha_bytes = bytes.fromhex(sha)
    first_byte = sha_bytes[0]

    # Use fanout to narrow search range
    if first_byte == 0:
        start = 0
    else:
        start = index.fanout[first_byte - 1]
    end = index.fanout[first_byte]

    # Binary search within the range
    while start < end:
        mid = (start + end) // 2
        mid_sha = index.shas[mid]

        if mid_sha == sha_bytes:
            return index.offsets[mid]
        elif mid_sha < sha_bytes:
            start = mid + 1
        else:
            end = mid

    return None  # Not found
```

For an object starting with `0xab`:
1. Look up `fanout[0xaa]` and `fanout[0xab]`
2. Binary search only between those indices
3. Typically reduces search space by 256x

### Large Pack Support

For packs larger than 2GB, 4-byte offsets aren't enough. The index handles this elegantly:

```
If offset[i] has high bit set:
    actual_offset = large_offsets[offset[i] & 0x7fffffff]
```

This allows seamless support for packs up to 16 exabytes while keeping the common case (< 2GB) efficient.

---

## Creating Pack Files

### The Packing Algorithm

1. **Collect objects**: Gather all objects to pack
2. **Sort**: Group similar objects together (by type, path hints, size)
3. **Find delta bases**: For each object, find good candidates for deltification
4. **Compute deltas**: Create deltas that provide good compression
5. **Write pack**: Output header, objects (deltified or not), trailer
6. **Write index**: Create `.idx` file for fast lookup

### Object Selection for Delta Bases

Git uses heuristics to find good delta bases:

```python
def find_delta_base(obj, candidates: list) -> GitObject | None:
    """Find best delta base for object."""
    best_delta = None
    best_size = len(obj.data)

    for candidate in candidates:
        # Must be same type
        if candidate.type_name != obj.type_name:
            continue

        # Must be similar size (within factor of 10)
        if len(candidate.data) * 10 < len(obj.data):
            continue
        if len(candidate.data) > len(obj.data) * 10:
            continue

        # Compute delta
        delta = create_delta(candidate.data, obj.data)

        if len(delta) < best_size:
            best_delta = candidate
            best_size = len(delta)

    # Only use delta if it saves significant space
    if best_delta and best_size < len(obj.data) * 0.9:
        return best_delta
    return None
```

### The Sliding Window

Git uses a "sliding window" approach:

```python
def pack_objects(objects: list[GitObject], window_size: int = 10):
    """Pack objects with delta compression."""
    # Sort by type, then by filename hint, then by size
    sorted_objects = sort_for_packing(objects)

    window: list[GitObject] = []

    for obj in sorted_objects:
        # Try to deltify against objects in window
        base = find_delta_base(obj, window)

        if base:
            write_delta_object(obj, base)
        else:
            write_full_object(obj)

        # Update window
        window.append(obj)
        if len(window) > window_size:
            window.pop(0)
```

Objects are sorted so that similar objects (same file across versions) are adjacent, maximizing delta opportunities.

---

## Pack File Verification

Git provides robust verification:

### Integrity Checks

```bash
# Verify pack file integrity
$ git verify-pack .git/objects/pack/*.pack

# Verbose output shows any issues
$ git verify-pack -v .git/objects/pack/*.pack 2>&1 | grep -i error
```

### What's Verified

1. **Pack checksum**: SHA-1 of pack file content matches trailer
2. **Index checksum**: SHA-1 of index content matches trailer
3. **Object checksums**: Each object's SHA-1 matches after reconstruction
4. **Delta chain validity**: All delta bases exist and resolve correctly
5. **CRC32 values**: Compressed data hasn't been corrupted

### Self-Healing

If verification fails, Git can often recover:

```bash
# Remove corrupted pack and re-fetch
$ rm .git/objects/pack/pack-corrupted.*
$ git fetch --all

# Or re-clone
$ git clone --mirror <url>
```

---

## Network Transfer: Thin Packs

During `git fetch`/`git push`, Git uses "thin packs"—packs that reference objects the receiver already has.

### Normal Pack vs Thin Pack

**Normal pack**: All delta bases are included in the pack
```
Object A (delta of B) ← B is in this pack
Object B (full)
```

**Thin pack**: Delta bases may be external
```
Object A (delta of B) ← B is NOT in this pack
                        (receiver already has B)
```

### Pack Protocol

```
Client: "I have commits X, Y, Z. Send me everything else."
Server: Creates thin pack with just the new objects
        Uses client's existing objects as delta bases
Client: Receives pack, "thickens" it by resolving deltas
```

This minimizes network transfer—why send objects the client already has?

---

## Performance Characteristics

### Lookup Performance

| Operation | Complexity | Notes |
|-----------|------------|-------|
| Find by SHA (with index) | O(log n) | Binary search in fanout-limited range |
| Read undeltified object | O(1) | Direct seek + decompress |
| Read deltified object | O(d) | d = delta chain depth |
| Scan all objects | O(n) | Linear traversal |

### Space Efficiency

| Scenario | Loose Objects | Packed |
|----------|---------------|--------|
| Linux kernel (1M objects) | ~2GB | ~200MB |
| Typical project (10K objects) | ~100MB | ~10MB |
| Similar files (100 versions) | 100 × size | ~1 × size |

### Tuning Parameters

```bash
# Delta chain depth (default: 50)
$ git config pack.depth 50

# Delta window size (default: 10)
$ git config pack.window 10

# Pack size threshold (default: 2GB)
$ git config pack.packSizeLimit 2g

# Aggressive packing
$ git repack -a -d --depth=250 --window=250
```

---

## Implementation in gitpy

### Module Structure

```
gitpy/storage/
├── __init__.py       # Module exports
├── compression.py    # Zlib utilities
├── loose.py          # Loose object store
├── database.py       # Object database (updated for packs)
├── delta.py          # Delta encoding/decoding
├── pack.py           # Pack file reader
├── pack_index.py     # Pack index
└── pack_writer.py    # Pack file writer
```

### Key Classes

**PackFile**: Reads objects from pack files
```python
class PackFile:
    def __init__(self, pack_path: Path): ...
    def read_object(self, sha: str) -> PackObject | None: ...
    def __contains__(self, sha: str) -> bool: ...
    def __iter__(self) -> Iterator[PackObject]: ...
```

**PackIndex**: Fast SHA → offset lookup
```python
class PackIndex:
    def get_offset(self, sha: str) -> int | None: ...
    def __contains__(self, sha: str) -> bool: ...

    @classmethod
    def from_file(cls, path: Path) -> PackIndex: ...
    def serialize(self) -> bytes: ...
```

**Delta functions**: Encode and decode deltas
```python
def parse_delta(data: bytes) -> tuple[int, int, list[DeltaOp]]: ...
def apply_delta(base: bytes, delta_ops: list[DeltaOp]) -> bytes: ...
def create_delta(source: bytes, target: bytes) -> bytes: ...
```

### Integration with ObjectDatabase

```python
class ObjectDatabase:
    def __init__(self, git_dir: Path):
        self.loose = LooseObjectStore(git_dir)
        self._pack_files: list[PackFile] = []
        self._load_packs()

    def read_raw(self, sha: str) -> bytes:
        # Try loose first (faster for recent objects)
        if self.loose.exists(sha):
            return self.loose.read(sha)

        # Search pack files
        for pack in self._pack_files:
            obj = pack.read_object(sha)
            if obj:
                # Reconstruct with header
                header = f"{obj.type_name} {len(obj.data)}\0".encode()
                return header + obj.data

        raise FileNotFoundError(f"Object not found: {sha}")
```

---

## Git Compatibility

### Reference Hashes

These hashes must match real Git:

| Object | SHA-1 |
|--------|-------|
| Empty blob | `e69de29bb2d1d6434b8b29ae775ad8c2e48c5391` |
| Empty tree | `4b825dc642cb6eb9a060e54bf8d69288fbee4904` |
| `hello\n` blob | `ce013625030ba8dba906f756967f9e9ca394464a` |

### Interoperability Tests

```bash
# Create pack with Git, read with gitpy
$ git gc
$ python3 -c "
from gitpy import Repository
repo = Repository(Path('.'))
blob = repo.objects.read_blob('ce013625')  # From pack
print(blob.data)  # b'hello\n'
"

# Create pack with gitpy, verify with Git
$ python3 -c "
from gitpy import Repository
repo = Repository(Path('.'))
repo.objects.repack()
"
$ git verify-pack -v .git/objects/pack/*.pack  # Should succeed
```

---

## Key Takeaways

1. **Pack files combine many objects** into single files for efficiency
2. **Delta compression** stores differences instead of full copies
3. **The pack index** enables O(1) lookup by SHA
4. **Variable-length encoding** minimizes overhead
5. **Thin packs** optimize network transfer
6. **Delta chains** are limited to balance compression vs. read speed
7. **All formats are Git-compatible** for interoperability

Pack files transform Git from a simple content store into an incredibly efficient version control system. Understanding them reveals how Git can handle massive repositories like the Linux kernel while keeping operations fast.

---

## What's Next?

With pack files understood, explore related topics:

- **[Delta Compression](delta_compression.md)**: Deep dive into delta algorithms
- **[Pack Index](pack_index.md)**: Index format details
- **References** (`gitpy/refs/`): How branches and tags point to commits
- **Garbage Collection**: How Git cleans up unreachable objects
