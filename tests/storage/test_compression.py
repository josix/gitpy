"""Tests for compression utilities."""

import zlib

import pytest

from gitpy.storage.compression import compress, decompress, decompress_stream


class TestCompress:
    """Tests for compress function."""

    def test_compress_basic(self) -> None:
        """Compress data successfully."""
        data = b"hello world"
        compressed = compress(data)

        # Should be smaller or similar size
        assert isinstance(compressed, bytes)
        assert len(compressed) > 0

        # Should be valid zlib
        assert zlib.decompress(compressed) == data

    def test_compress_empty(self) -> None:
        """Compress empty data."""
        compressed = compress(b"")
        assert zlib.decompress(compressed) == b""

    def test_compress_with_level(self) -> None:
        """Compress with different levels."""
        data = b"hello " * 100

        # Level 0 = no compression
        uncompressed = compress(data, level=0)
        # Level 9 = max compression
        max_compressed = compress(data, level=9)

        # Higher compression should be smaller or equal
        assert len(max_compressed) <= len(uncompressed)


class TestDecompress:
    """Tests for decompress function."""

    def test_decompress_basic(self) -> None:
        """Decompress data successfully."""
        original = b"test data"
        compressed = zlib.compress(original)

        result = decompress(compressed)
        assert result == original

    def test_decompress_invalid(self) -> None:
        """Invalid data raises error."""
        with pytest.raises(zlib.error):
            decompress(b"not valid zlib data")

    def test_roundtrip(self) -> None:
        """Compress then decompress returns original."""
        original = b"roundtrip test data with special chars: \x00\xff\n"
        result = decompress(compress(original))
        assert result == original


class TestDecompressStream:
    """Tests for decompress_stream function."""

    def test_decompress_stream_no_trailing(self) -> None:
        """Decompress stream without trailing data."""
        original = b"stream data"
        compressed = compress(original)

        content, remaining = decompress_stream(compressed)
        assert content == original
        assert remaining == b""

    def test_decompress_stream_with_trailing(self) -> None:
        """Decompress stream with trailing data."""
        original = b"first part"
        trailing = b"trailing data"
        compressed = compress(original) + trailing

        content, remaining = decompress_stream(compressed)
        assert content == original
        assert remaining == trailing

    def test_decompress_multiple_streams(self) -> None:
        """Decompress multiple concatenated streams."""
        data1 = b"first"
        data2 = b"second"
        combined = compress(data1) + compress(data2)

        # First decompression
        content1, remaining = decompress_stream(combined)
        assert content1 == data1

        # Second decompression from remaining
        content2, final = decompress_stream(remaining)
        assert content2 == data2
        assert final == b""
