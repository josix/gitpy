"""Tests for delta compression module."""

import pytest

from gitpy.storage.delta import (
    DeltaCopy,
    DeltaInsert,
    _encode_copy_instruction,
    _encode_delta_size,
    apply_delta,
    create_delta,
    parse_delta,
    read_delta_size,
)


class TestDeltaSizeEncoding:
    """Tests for variable-length size encoding."""

    def test_encode_small_size(self) -> None:
        """Encode size that fits in 7 bits."""
        encoded = _encode_delta_size(10)
        assert encoded == bytes([10])

    def test_encode_medium_size(self) -> None:
        """Encode size requiring multiple bytes."""
        encoded = _encode_delta_size(128)
        # 128 = 0x80 -> needs continuation
        # First byte: 0x80 | (128 & 0x7f) = 0x80 | 0 = 0x80
        # Second byte: 128 >> 7 = 1
        assert encoded == bytes([0x80, 0x01])

    def test_encode_large_size(self) -> None:
        """Encode larger size."""
        encoded = _encode_delta_size(1000)
        size, consumed = read_delta_size(encoded, 0)
        assert size == 1000

    def test_roundtrip_various_sizes(self) -> None:
        """Encode/decode roundtrip for various sizes."""
        for size in [0, 1, 15, 16, 127, 128, 1000, 65535, 1_000_000]:
            encoded = _encode_delta_size(size)
            decoded, _ = read_delta_size(encoded, 0)
            assert decoded == size, f"Failed for size {size}"


class TestDeltaInstructions:
    """Tests for delta instruction parsing."""

    def test_parse_insert_instruction(self) -> None:
        """Parse INSERT instruction."""
        # INSERT 5 bytes: "Hello"
        data = bytes([
            10, 10,          # source/target sizes (varint)
            5,               # INSERT 5
            72, 101, 108, 108, 111  # "Hello"
        ])

        source_size, target_size, ops = parse_delta(data)
        assert source_size == 10
        assert target_size == 10
        assert len(ops) == 1
        assert isinstance(ops[0], DeltaInsert)
        assert ops[0].data == b"Hello"

    def test_parse_copy_instruction(self) -> None:
        """Parse COPY instruction."""
        # COPY from offset 10, size 20
        data = bytes([
            100, 30,         # source/target sizes
            0x91,            # COPY: 1 (copy) + 0x10 (size byte) + 0x01 (offset byte)
            10,              # offset = 10
            20               # size = 20
        ])

        source_size, target_size, ops = parse_delta(data)
        assert source_size == 100
        assert target_size == 30
        assert len(ops) == 1
        assert isinstance(ops[0], DeltaCopy)
        assert ops[0].offset == 10
        assert ops[0].size == 20

    def test_parse_mixed_instructions(self) -> None:
        """Parse delta with both COPY and INSERT."""
        # Create a simple delta manually
        data = bytearray()
        data.extend(_encode_delta_size(100))  # source size
        data.extend(_encode_delta_size(25))   # target size

        # COPY 10 bytes from offset 0
        data.extend(_encode_copy_instruction(0, 10))
        # INSERT 5 bytes
        data.append(5)
        data.extend(b"Hello")
        # COPY 10 bytes from offset 50
        data.extend(_encode_copy_instruction(50, 10))

        source_size, target_size, ops = parse_delta(bytes(data))
        assert source_size == 100
        assert target_size == 25
        assert len(ops) == 3
        assert isinstance(ops[0], DeltaCopy)
        assert isinstance(ops[1], DeltaInsert)
        assert isinstance(ops[2], DeltaCopy)

    def test_invalid_instruction_raises(self) -> None:
        """Invalid 0x00 instruction raises ValueError."""
        data = bytes([
            10, 10,  # sizes
            0x00     # Invalid instruction
        ])

        with pytest.raises(ValueError, match="Invalid delta instruction"):
            parse_delta(data)


class TestDeltaApply:
    """Tests for applying deltas."""

    def test_apply_copy_only(self) -> None:
        """Apply delta with only COPY instructions."""
        base = b"Hello, World!"

        # Create delta to copy entire base
        delta = bytearray()
        delta.extend(_encode_delta_size(len(base)))
        delta.extend(_encode_delta_size(len(base)))
        delta.extend(_encode_copy_instruction(0, len(base)))

        result = apply_delta(base, bytes(delta))
        assert result == base

    def test_apply_insert_only(self) -> None:
        """Apply delta with only INSERT instructions."""
        base = b"ignored"

        # Create delta to insert new content
        delta = bytearray()
        delta.extend(_encode_delta_size(len(base)))
        delta.extend(_encode_delta_size(5))
        delta.append(5)
        delta.extend(b"Hello")

        result = apply_delta(base, bytes(delta))
        assert result == b"Hello"

    def test_apply_mixed(self) -> None:
        """Apply delta with mixed instructions."""
        base = b"Hello, World!"

        # Create delta: copy "Hello, " + insert "Git " + copy "World!"
        delta = bytearray()
        delta.extend(_encode_delta_size(len(base)))
        delta.extend(_encode_delta_size(17))  # "Hello, Git World!"
        delta.extend(_encode_copy_instruction(0, 7))  # "Hello, "
        delta.append(4)
        delta.extend(b"Git ")
        delta.extend(_encode_copy_instruction(7, 6))  # "World!"

        result = apply_delta(base, bytes(delta))
        assert result == b"Hello, Git World!"

    def test_apply_base_size_mismatch(self) -> None:
        """Raise on base size mismatch."""
        base = b"short"

        delta = bytearray()
        delta.extend(_encode_delta_size(100))  # Wrong source size
        delta.extend(_encode_delta_size(5))

        with pytest.raises(ValueError, match="Base size mismatch"):
            apply_delta(base, bytes(delta))


class TestDeltaCreate:
    """Tests for creating deltas."""

    def test_create_identical(self) -> None:
        """Delta of identical content."""
        data = b"x" * 1000

        delta = create_delta(data, data)
        result = apply_delta(data, delta)

        assert result == data
        # Delta should be much smaller than copying everything
        assert len(delta) < len(data)

    def test_create_small_change(self) -> None:
        """Delta with small change."""
        source = b"Hello, World!"
        target = b"Hello, Git World!"

        delta = create_delta(source, target)
        result = apply_delta(source, delta)

        assert result == target

    def test_create_completely_different(self) -> None:
        """Delta of completely different content."""
        source = b"aaaa" * 100
        target = b"bbbb" * 100

        delta = create_delta(source, target)
        result = apply_delta(source, delta)

        assert result == target

    def test_create_empty_source(self) -> None:
        """Delta from empty source."""
        source = b""
        target = b"Hello"

        delta = create_delta(source, target)
        result = apply_delta(source, delta)

        assert result == target

    def test_create_empty_target(self) -> None:
        """Delta to empty target."""
        source = b"Hello"
        target = b""

        delta = create_delta(source, target)
        result = apply_delta(source, delta)

        assert result == target

    def test_create_large_similar(self) -> None:
        """Delta of large similar content."""
        base = b"The quick brown fox jumps over the lazy dog. " * 100
        # Change a few words
        target = base.replace(b"fox", b"cat").replace(b"dog", b"cat")

        delta = create_delta(base, target)
        result = apply_delta(base, delta)

        assert result == target
        # Delta should be smaller than target
        assert len(delta) < len(target)

    def test_roundtrip_various_content(self) -> None:
        """Roundtrip various content types."""
        test_cases = [
            (b"short", b"shorter"),
            (b"A" * 1000, b"A" * 1000 + b"B"),
            (b"prefix" + b"x" * 500, b"prefix" + b"y" * 500),
            (b"\x00\x01\x02" * 100, b"\x00\x01\x03" * 100),
        ]

        for source, target in test_cases:
            delta = create_delta(source, target)
            result = apply_delta(source, delta)
            assert result == target, f"Failed for source={source[:20]!r}..."
