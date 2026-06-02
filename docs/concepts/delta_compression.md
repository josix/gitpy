# Understanding Git's Delta Compression

This document explores how Git achieves remarkable space savings through delta compression. If you've ever wondered how Git stores years of history in megabytes instead of gigabytes, this guide reveals the elegant algorithms behind Git's efficiency.

## The Problem: Storing Similar Content

Version control systems face a fundamental challenge: source code files change incrementally. A 10,000-line file might have only 10 lines change between commits. Storing complete copies is wasteful:

```
commit 1: main.py (50KB)
commit 2: main.py (50.1KB)  ← Only 100 bytes changed
commit 3: main.py (50.2KB)  ← Only 50 bytes changed
...
1000 commits: ~50MB stored
```

Delta compression solves this by storing *differences*:

```
commit 1: main.py (50KB)    ← Full copy
commit 2: delta (200 bytes) ← Instructions to recreate from commit 1
commit 3: delta (100 bytes) ← Instructions to recreate from commit 2
...
1000 commits: ~100KB stored
```

That's a 500x improvement!

---

## What is a Delta?

A delta is a set of instructions that transform one piece of content (the **base** or **source**) into another (the **target**). Think of it as a recipe:

```
Base:   "Hello, World!"
Target: "Hello, Git World!"

Delta instructions:
1. COPY bytes 0-6 from base    → "Hello, "
2. INSERT "Git "                → "Hello, Git "
3. COPY bytes 7-13 from base   → "Hello, Git World!"
```

The delta only stores what's different, plus efficient references to unchanged content.

---

## Delta Instruction Types

Git's delta format uses just two instruction types:

### INSERT: Add New Content

```
┌─────────────────────────────────────────────────────┐
│  0XXXXXXX  │  literal data (X bytes, max 127)      │
│    (1 byte)│         (X bytes)                      │
└─────────────────────────────────────────────────────┘
```

- First byte starts with `0` (bit 7 = 0)
- Remaining 7 bits encode the length (1-127)
- Followed by that many literal bytes

Example: Insert "Hello"
```
0x05  'H'  'e'  'l'  'l'  'o'
```

### COPY: Copy from Base

```
┌─────────────────────────────────────────────────────┐
│  1OOOOSSS  │  offset bytes  │  size bytes          │
│    (1 byte)│    (0-4)       │    (0-3)             │
└─────────────────────────────────────────────────────┘
```

The first byte is packed with flags:
- Bit 7: Always 1 (indicates COPY)
- Bits 0-3 (OOOO): Which offset bytes are present
- Bits 4-6 (SSS): Which size bytes are present

This compact encoding allows small copies in just 2-3 bytes.

### Copy Instruction Details

```
Byte: 1 o₄ o₃ o₂ o₁ s₃ s₂ s₁

Offset bytes (little-endian):
  o₁ set: read byte for offset bits 0-7
  o₂ set: read byte for offset bits 8-15
  o₃ set: read byte for offset bits 16-23
  o₄ set: read byte for offset bits 24-31

Size bytes (little-endian):
  s₁ set: read byte for size bits 0-7
  s₂ set: read byte for size bits 8-15
  s₃ set: read byte for size bits 16-23

Special case: size of 0 means 0x10000 (65536 bytes)
```

### Example: Copy 100 bytes from offset 50

```
Offset 50:  0x32 (fits in 1 byte)
Size 100:   0x64 (fits in 1 byte)

Instruction: [1 0001 001] [0x32] [0x64]
             = [0x91]     [0x32] [0x64]

Just 3 bytes to copy 100 bytes!
```

### Example: Copy 1000 bytes from offset 5000

```
Offset 5000: 0x1388 (needs 2 bytes: 0x88, 0x13)
Size 1000:   0x03E8 (needs 2 bytes: 0xE8, 0x03)

Instruction: [1 0011 011] [0x88] [0x13] [0xE8] [0x03]
             = [0x9B]     + 4 data bytes

5 bytes to copy 1000 bytes!
```

---

## Delta File Format

A complete delta has this structure:

```
┌─────────────────────────────────────────────────────┐
│  Source size (variable-length integer)              │
├─────────────────────────────────────────────────────┤
│  Target size (variable-length integer)              │
├─────────────────────────────────────────────────────┤
│  Instructions                                        │
│  [COPY] [INSERT] [COPY] [INSERT] ...               │
└─────────────────────────────────────────────────────┘
```

The sizes are encoded as variable-length integers:

```python
def read_delta_size(data: bytes, offset: int) -> tuple[int, int]:
    """Read variable-length size."""
    size = 0
    shift = 0
    consumed = 0

    while True:
        byte = data[offset + consumed]
        size |= (byte & 0x7F) << shift
        consumed += 1
        if not (byte & 0x80):  # No continuation
            break
        shift += 7

    return size, consumed
```

---

## Parsing Delta Instructions

Here's how to decode delta instructions:

```python
from dataclasses import dataclass

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


def parse_delta(data: bytes) -> tuple[int, int, list[DeltaOp]]:
    """
    Parse delta instructions.

    Returns: (source_size, target_size, operations)
    """
    offset = 0

    # Read sizes
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

            # Size 0 means 0x10000
            if copy_size == 0:
                copy_size = 0x10000

            ops.append(DeltaCopy(offset=copy_offset, size=copy_size))

        elif cmd > 0:
            # INSERT instruction
            insert_data = data[offset : offset + cmd]
            offset += cmd
            ops.append(DeltaInsert(data=insert_data))

        else:
            # cmd == 0 is reserved/invalid
            raise ValueError("Invalid delta instruction: 0x00")

    return source_size, target_size, ops
```

---

## Applying Deltas

Reconstructing the target from base + delta:

```python
def apply_delta(base: bytes, delta_data: bytes) -> bytes:
    """Apply delta to reconstruct target."""
    source_size, target_size, ops = parse_delta(delta_data)

    # Verify base size
    if len(base) != source_size:
        raise ValueError(f"Base size mismatch: {len(base)} != {source_size}")

    result = bytearray()

    for op in ops:
        match op:
            case DeltaInsert(data=data):
                result.extend(data)
            case DeltaCopy(offset=offset, size=size):
                result.extend(base[offset : offset + size])

    # Verify result size
    if len(result) != target_size:
        raise ValueError(f"Result size mismatch: {len(result)} != {target_size}")

    return bytes(result)
```

---

## Creating Deltas

Creating good deltas is more challenging than applying them. The goal is to find the best COPY instructions that minimize delta size.

### The Challenge

Given:
```
Source: "The quick brown fox jumps over the lazy dog"
Target: "The quick brown cat jumps over the lazy dog"
```

Find the minimal set of COPY/INSERT instructions.

### Simple Approach: Longest Common Substrings

```python
def create_delta_simple(source: bytes, target: bytes) -> bytes:
    """
    Create delta using simple substring matching.

    This is a basic implementation. Git uses more
    sophisticated algorithms for better results.
    """
    result = bytearray()

    # Write sizes
    result.extend(encode_delta_size(len(source)))
    result.extend(encode_delta_size(len(target)))

    # Build index of chunks in source
    CHUNK_SIZE = 16
    source_index: dict[bytes, list[int]] = {}
    for i in range(len(source) - CHUNK_SIZE + 1):
        chunk = source[i : i + CHUNK_SIZE]
        source_index.setdefault(chunk, []).append(i)

    # Scan target, finding matches
    target_pos = 0
    pending_insert = bytearray()

    while target_pos < len(target):
        best_offset = -1
        best_length = 0

        # Try to find a match
        if target_pos + CHUNK_SIZE <= len(target):
            chunk = target[target_pos : target_pos + CHUNK_SIZE]

            if chunk in source_index:
                for src_pos in source_index[chunk]:
                    # Extend match as far as possible
                    length = CHUNK_SIZE
                    while (target_pos + length < len(target) and
                           src_pos + length < len(source) and
                           target[target_pos + length] == source[src_pos + length]):
                        length += 1

                    if length > best_length:
                        best_offset = src_pos
                        best_length = length

        if best_length >= CHUNK_SIZE:
            # Found a good match - emit pending insert first
            if pending_insert:
                emit_insert(result, bytes(pending_insert))
                pending_insert.clear()

            # Emit copy
            emit_copy(result, best_offset, best_length)
            target_pos += best_length
        else:
            # No match - accumulate for insert
            pending_insert.append(target[target_pos])
            target_pos += 1

    # Emit final insert
    if pending_insert:
        emit_insert(result, bytes(pending_insert))

    return bytes(result)
```

### Git's Advanced Approach

Real Git uses more sophisticated techniques:

1. **Rolling hash (rabin fingerprint)**: Efficiently find matches without indexing every position

2. **Multiple chunk sizes**: Try different granularities for better matches

3. **Path hints**: Files with similar names are likely similar content

4. **Size-based filtering**: Skip comparisons for very different sizes

5. **Bloom filters**: Quickly eliminate non-matches

---

## Delta Chains

Deltas can reference other deltas, forming chains:

```
Object A → stored as delta of B
Object B → stored as delta of C
Object C → stored in full (base)
```

To read object A:
```
1. Read C (decompress zlib)
2. Apply B's delta → get B
3. Apply A's delta → get A
```

### Chain Depth Limits

Git limits chain depth (default: 50) because:

- **Read performance**: Deep chains require many decompressions
- **Memory usage**: All intermediate objects must be held in memory
- **Error propagation**: Corruption in base affects all dependents

```bash
# Configure maximum delta depth
$ git config pack.depth 50

# Aggressive packing allows deeper chains
$ git repack -a -d --depth=250
```

### Chain Resolution

```python
def resolve_delta_chain(
    pack: PackFile,
    offset: int,
    cache: dict[int, tuple[str, bytes]] | None = None
) -> tuple[str, bytes]:
    """Resolve object, following delta chain if needed."""
    if cache and offset in cache:
        return cache[offset]

    obj_type, size, data, base_info = pack._read_object_at(offset)

    if obj_type in (OBJ_COMMIT, OBJ_TREE, OBJ_BLOB, OBJ_TAG):
        # Non-delta: decompress and return
        result_type = type_name_from_int(obj_type)
        result = zlib.decompress(data)

    elif obj_type == OBJ_OFS_DELTA:
        # Delta with offset reference
        base_offset = offset - base_info
        base_type, base_data = resolve_delta_chain(pack, base_offset, cache)
        result = apply_delta(base_data, zlib.decompress(data))
        result_type = base_type

    elif obj_type == OBJ_REF_DELTA:
        # Delta with SHA reference
        base_sha = base_info
        base_offset = pack.index.get_offset(base_sha)
        base_type, base_data = resolve_delta_chain(pack, base_offset, cache)
        result = apply_delta(base_data, zlib.decompress(data))
        result_type = base_type

    if cache is not None:
        cache[offset] = (result_type, result)

    return result_type, result
```

---

## OFS_DELTA vs REF_DELTA

Git supports two ways to reference delta bases:

### OFS_DELTA (Type 6)

References base by negative offset within the same pack:

```
┌────────────────────────────────────────────┐
│  Header (type=6, size)                     │
├────────────────────────────────────────────┤
│  Negative offset (variable-length)         │
├────────────────────────────────────────────┤
│  Compressed delta data                     │
└────────────────────────────────────────────┘

base_offset = current_offset - negative_offset
```

**Advantages**:
- Compact: offsets are typically small
- Fast: just seek within file, no index lookup
- Self-contained: all bases are in same pack

**Used in**: Stored pack files

### REF_DELTA (Type 7)

References base by SHA-1:

```
┌────────────────────────────────────────────┐
│  Header (type=7, size)                     │
├────────────────────────────────────────────┤
│  Base SHA-1 (20 bytes)                     │
├────────────────────────────────────────────┤
│  Compressed delta data                     │
└────────────────────────────────────────────┘
```

**Advantages**:
- Can reference objects in other packs
- Works for "thin packs" in network transfer

**Used in**: Network transfer, thin packs

### Offset Encoding

OFS_DELTA uses a special encoding for the negative offset:

```python
def read_ofs_delta_offset(data: bytes, pos: int) -> tuple[int, int]:
    """
    Read negative offset for OFS_DELTA.

    The encoding is:
    - Each byte contributes 7 bits
    - High bit indicates continuation
    - Each continuation byte adds 1 before shifting

    This ensures every offset has exactly one encoding.
    """
    byte = data[pos]
    offset = byte & 0x7F
    consumed = 1

    while byte & 0x80:
        byte = data[pos + consumed]
        offset = ((offset + 1) << 7) | (byte & 0x7F)
        consumed += 1

    return offset, consumed


def write_ofs_delta_offset(offset: int) -> bytes:
    """Encode OFS_DELTA negative offset."""
    result = bytearray()
    result.append(offset & 0x7F)
    offset >>= 7

    while offset > 0:
        offset -= 1  # The crucial -1
        result.append(0x80 | (offset & 0x7F))
        offset >>= 7

    result.reverse()
    return bytes(result)
```

---

## Delta Encoding Best Practices

### When Deltas Work Well

- **Similar content**: Source code, documents, config files
- **Incremental changes**: Small modifications to large files
- **Same file type**: Text-to-text, binary-to-binary

### When Deltas Don't Help

- **Completely different content**: No common substrings
- **Already compressed**: ZIP, JPEG, MP4 (random-looking bytes)
- **Small files**: Overhead exceeds savings

### Tuning for Different Scenarios

```bash
# Code repository (many similar text files)
$ git config pack.window 250
$ git config pack.depth 50

# Media repository (large, different files)
$ git config pack.window 10
$ git config pack.depth 10

# Mixed repository
$ git config pack.windowMemory 1g
$ git config pack.deltaCacheSize 256m
```

---

## Real-World Delta Examples

### Example 1: One-Line Change

Source (100 bytes):
```
def hello():
    print("Hello, World!")
    return True
```

Target (105 bytes):
```
def hello():
    print("Hello, Git World!")
    return True
```

Delta (just ~20 bytes):
```
Source size: 100
Target size: 105
COPY 0-25           # "def hello():\n    print(\"Hello, "
INSERT "Git "       # New text
COPY 25-100         # "World!\")\n    return True\n"
```

### Example 2: Adding to End

Source:
```
Line 1
Line 2
```

Target:
```
Line 1
Line 2
Line 3
```

Delta:
```
COPY 0-14      # All of source
INSERT "Line 3\n"
```

### Example 3: Insertion in Middle

Source:
```
AAAAABBBBBCCCCC
```

Target:
```
AAAAAXXXXXBBBBBCCCCC
```

Delta:
```
COPY 0-5       # AAAAA
INSERT "XXXXX"
COPY 5-15      # BBBBBCCCCC
```

---

## Implementation in gitpy

### Module Structure

```python
# gitpy/storage/delta.py

from dataclasses import dataclass
from typing import Iterator

@dataclass(slots=True)
class DeltaInsert:
    """Insert literal data into result."""
    data: bytes

    def __repr__(self) -> str:
        if len(self.data) > 20:
            return f"INSERT({len(self.data)} bytes)"
        return f"INSERT({self.data!r})"

@dataclass(slots=True)
class DeltaCopy:
    """Copy bytes from base object."""
    offset: int
    size: int

    def __repr__(self) -> str:
        return f"COPY({self.offset}, {self.size})"

type DeltaOp = DeltaInsert | DeltaCopy
```

### Public API

```python
def parse_delta(data: bytes) -> tuple[int, int, list[DeltaOp]]:
    """
    Parse delta instructions.

    Args:
        data: Raw delta bytes

    Returns:
        (source_size, target_size, operations)
    """
    ...

def apply_delta(base: bytes, delta_data: bytes) -> bytes:
    """
    Apply delta to base to produce target.

    Args:
        base: Source/base object data
        delta_data: Raw delta bytes

    Returns:
        Reconstructed target data

    Raises:
        ValueError: Size mismatch or invalid delta
    """
    ...

def create_delta(source: bytes, target: bytes) -> bytes:
    """
    Create delta from source to target.

    Args:
        source: Base object data
        target: Target object data

    Returns:
        Delta bytes that transform source into target
    """
    ...
```

---

## Testing Delta Code

### Round-Trip Tests

```python
def test_delta_roundtrip():
    """Delta should reconstruct original."""
    source = b"Hello, World! " * 100
    target = b"Hello, Git World! " * 100

    delta = create_delta(source, target)
    restored = apply_delta(source, delta)

    assert restored == target

def test_delta_identical():
    """Delta of identical content should be small."""
    data = b"x" * 10000
    delta = create_delta(data, data)

    # Delta should be much smaller than copying everything
    assert len(delta) < len(data) // 2

def test_delta_completely_different():
    """Delta of unrelated content still works."""
    source = b"aaaa" * 1000
    target = b"bbbb" * 1000

    delta = create_delta(source, target)
    restored = apply_delta(source, delta)

    assert restored == target
```

### Instruction Parsing Tests

```python
def test_parse_insert():
    """Parse INSERT instruction."""
    # INSERT 5 bytes: "Hello"
    data = bytes([
        10, 10,          # source/target sizes
        5,               # INSERT 5
        72, 101, 108, 108, 111  # "Hello"
    ])

    source_size, target_size, ops = parse_delta(data)
    assert len(ops) == 1
    assert isinstance(ops[0], DeltaInsert)
    assert ops[0].data == b"Hello"

def test_parse_copy():
    """Parse COPY instruction."""
    # COPY from offset 10, size 20
    data = bytes([
        100, 30,         # source/target sizes
        0x91,            # COPY, offset byte 1, size byte 1
        10,              # offset = 10
        20               # size = 20
    ])

    source_size, target_size, ops = parse_delta(data)
    assert len(ops) == 1
    assert isinstance(ops[0], DeltaCopy)
    assert ops[0].offset == 10
    assert ops[0].size == 20
```

---

## Performance Considerations

### Memory Usage

- **Parsing**: O(delta size) - just scanning bytes
- **Applying**: O(target size) - building result
- **Creating**: O(source × window) - finding matches

### Speed Optimizations

1. **Index building**: Pre-compute chunk positions in source
2. **Early termination**: Stop searching after good-enough match
3. **Chunk size tuning**: Larger chunks = fewer lookups but fewer matches
4. **Caching**: Reuse resolved bases for chain resolution

### Git's Production Optimizations

Real Git uses:
- SIMD instructions for byte comparison
- Memory-mapped files for large packs
- Thread pools for parallel delta computation
- Bloom filters for quick non-match detection

---

## Key Takeaways

1. **Two instructions**: INSERT for new data, COPY for reused data
2. **Compact encoding**: Small copies need only 2-3 bytes
3. **Chain resolution**: Deltas can reference other deltas
4. **OFS vs REF**: Offset deltas for storage, SHA deltas for transfer
5. **Size verification**: Always check source and target sizes
6. **Trade-offs**: Better compression vs. slower reads

Delta compression is the secret behind Git's legendary efficiency. Understanding it reveals how Git stores years of history in megabytes while keeping operations fast.

---

## What's Next?

- **[Pack Files](pack_files.md)**: How deltas are stored in packs
- **[Pack Index](pack_index.md)**: Fast object lookup in packs
- **Implementation**: See `gitpy/storage/delta.py` for code
