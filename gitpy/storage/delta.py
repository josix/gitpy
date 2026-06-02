"""Delta compression for Git pack files.

This module implements Git's delta encoding format, which stores objects
as differences from a base object. Delta compression dramatically reduces
storage for similar content.

Delta Format:
    [source_size: varint]
    [target_size: varint]
    [instructions: (INSERT | COPY)*]

Instructions:
    INSERT: 0xxxxxxx [data]  - Insert x bytes of literal data (1-127)
    COPY:   1oooosss [offset] [size] - Copy from base object
"""

from dataclasses import dataclass


@dataclass(slots=True)
class DeltaInsert:
    """Insert literal data into result."""

    data: bytes

    def __repr__(self) -> str:
        if len(self.data) > 20:
            return f"DeltaInsert({len(self.data)} bytes)"
        return f"DeltaInsert({self.data!r})"


@dataclass(slots=True)
class DeltaCopy:
    """Copy bytes from base object."""

    offset: int
    size: int

    def __repr__(self) -> str:
        return f"DeltaCopy(offset={self.offset}, size={self.size})"


type DeltaOp = DeltaInsert | DeltaCopy


def read_delta_size(data: bytes, offset: int) -> tuple[int, int]:
    """Read variable-length size from delta header.

    Args:
        data: Delta data bytes.
        offset: Starting position.

    Returns:
        Tuple of (size, bytes_consumed).
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


def _encode_delta_size(size: int) -> bytes:
    """Encode size as variable-length integer.

    Args:
        size: Size value to encode.

    Returns:
        Encoded bytes.
    """
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


def _parse_copy_op(data: bytes, cmd: int, offset: int) -> tuple[DeltaCopy, int]:
    """Decode a COPY instruction (cmd has bit 7 set).

    Reads the variable-length offset and size fields that follow the
    command byte and returns the decoded operation plus the updated
    stream position.

    Args:
        data: Raw delta bytes.
        cmd: Command byte (already consumed from *data*).
        offset: Current stream position (immediately after *cmd*).

    Returns:
        Tuple of (DeltaCopy, new_offset).
    """
    copy_offset = 0
    copy_size = 0

    # Offset bytes (little-endian, presence controlled by bits 0-3 of cmd)
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

    # Size bytes (little-endian, presence controlled by bits 4-6 of cmd)
    if cmd & 0x10:
        copy_size |= data[offset]
        offset += 1
    if cmd & 0x20:
        copy_size |= data[offset] << 8
        offset += 1
    if cmd & 0x40:
        copy_size |= data[offset] << 16
        offset += 1

    if copy_size == 0:
        copy_size = 0x10000

    return DeltaCopy(offset=copy_offset, size=copy_size), offset


def parse_delta(data: bytes) -> tuple[int, int, list[DeltaOp]]:
    """Parse delta instructions.

    Args:
        data: Raw delta bytes.

    Returns:
        Tuple of (source_size, target_size, operations).

    Raises:
        ValueError: Invalid delta instruction (e.g., 0x00 byte).
    """
    offset = 0

    source_size, consumed = read_delta_size(data, offset)
    offset += consumed

    target_size, consumed = read_delta_size(data, offset)
    offset += consumed

    ops: list[DeltaOp] = []

    while offset < len(data):
        cmd = data[offset]
        offset += 1

        if cmd & 0x80:
            op, offset = _parse_copy_op(data, cmd, offset)
            ops.append(op)
        elif cmd > 0:
            ops.append(DeltaInsert(data=data[offset : offset + cmd]))
            offset += cmd
        else:
            raise ValueError("Invalid delta instruction: 0x00")

    return source_size, target_size, ops


def apply_delta(base: bytes, delta_data: bytes) -> bytes:
    """Apply delta to reconstruct target.

    Args:
        base: Source/base object data.
        delta_data: Raw delta bytes.

    Returns:
        Reconstructed target data.

    Raises:
        ValueError: Size mismatch or invalid delta.
    """
    source_size, target_size, ops = parse_delta(delta_data)

    if len(base) != source_size:
        raise ValueError(f"Base size mismatch: expected {source_size}, got {len(base)}")

    result = bytearray()

    for op in ops:
        match op:
            case DeltaInsert(data=data):
                result.extend(data)
            case DeltaCopy(offset=offset, size=size):
                result.extend(base[offset : offset + size])

    if len(result) != target_size:
        raise ValueError(
            f"Result size mismatch: expected {target_size}, got {len(result)}"
        )

    return bytes(result)


def _encode_copy_instruction(offset: int, size: int) -> bytes:
    """Encode COPY instruction.

    Args:
        offset: Byte offset in base object.
        size: Number of bytes to copy.

    Returns:
        Encoded instruction bytes.
    """
    result = bytearray()
    cmd = 0x80
    data = bytearray()

    # Offset bytes (little-endian)
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


def _emit_insert(result: bytearray, data: bytes) -> None:
    """Emit INSERT instructions for data.

    Splits into chunks of max 127 bytes.

    Args:
        result: Output buffer to append to.
        data: Data to insert.
    """
    for i in range(0, len(data), 127):
        chunk = data[i : i + 127]
        result.append(len(chunk))
        result.extend(chunk)


_MAX_COPY_SIZE = 0xFFFFFF  # Maximum bytes a single COPY instruction can copy.


def _emit_copy(result: bytearray, offset: int, size: int) -> None:
    """Emit one or more COPY instructions for a region in the base object.

    Splits the copy into chunks of at most 0xFFFFFF bytes so the 24-bit
    size field in the COPY instruction is never overflowed.

    Args:
        result: Output buffer to append to.
        offset: Starting byte offset in the base object.
        size: Total number of bytes to copy.
    """
    while size > 0:
        chunk = min(size, _MAX_COPY_SIZE)
        result.extend(_encode_copy_instruction(offset, chunk))
        offset += chunk
        size -= chunk


def _build_source_index(source: bytes, chunk_size: int) -> dict[bytes, list[int]]:
    """Build a lookup map from source chunks to their starting positions.

    Args:
        source: Base object data.
        chunk_size: Size of each chunk key.

    Returns:
        Mapping of chunk bytes → list of offsets in *source*.
    """
    index: dict[bytes, list[int]] = {}
    for i in range(len(source) - chunk_size + 1):
        chunk = source[i : i + chunk_size]
        if chunk not in index:
            index[chunk] = []
        index[chunk].append(i)
    return index


def _find_best_match(
    source: bytes,
    target: bytes,
    target_pos: int,
    source_index: dict[bytes, list[int]],
    chunk_size: int,
) -> tuple[int, int]:
    """Find the longest match for *target[target_pos:]* in *source*.

    Args:
        source: Base object data.
        target: Target object data.
        target_pos: Current position in *target*.
        source_index: Output of ``_build_source_index``.
        chunk_size: Minimum chunk size for a valid match.

    Returns:
        Tuple of (best_src_offset, best_length); best_length is 0 when no
        match reaches *chunk_size*.
    """
    best_offset = -1
    best_length = 0

    if target_pos + chunk_size > len(target):
        return best_offset, best_length

    chunk = target[target_pos : target_pos + chunk_size]
    if chunk not in source_index:
        return best_offset, best_length

    for src_pos in source_index[chunk]:
        length = chunk_size
        while (
            target_pos + length < len(target)
            and src_pos + length < len(source)
            and target[target_pos + length] == source[src_pos + length]
        ):
            length += 1

        if length > best_length:
            best_offset = src_pos
            best_length = length

    return best_offset, best_length


def create_delta(source: bytes, target: bytes) -> bytes:
    """Create delta from source to target.

    Uses a simple algorithm with chunk-based matching.
    Production Git uses more sophisticated rolling hash matching.

    Args:
        source: Base object data.
        target: Target object data.

    Returns:
        Delta bytes that transform source into target.
    """
    result = bytearray()
    result.extend(_encode_delta_size(len(source)))
    result.extend(_encode_delta_size(len(target)))

    if len(source) == 0:
        _emit_insert(result, target)
        return bytes(result)

    chunk_size = 16
    source_index = _build_source_index(source, chunk_size)

    target_pos = 0
    pending_insert = bytearray()

    while target_pos < len(target):
        best_offset, best_length = _find_best_match(
            source, target, target_pos, source_index, chunk_size
        )

        if best_length >= chunk_size:
            if pending_insert:
                _emit_insert(result, bytes(pending_insert))
                pending_insert = bytearray()
            _emit_copy(result, best_offset, best_length)
            target_pos += best_length
        else:
            pending_insert.append(target[target_pos])
            target_pos += 1

    if pending_insert:
        _emit_insert(result, bytes(pending_insert))

    return bytes(result)
