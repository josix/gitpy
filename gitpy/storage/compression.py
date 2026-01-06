"""Compression utilities for Git object storage.

Git uses zlib compression for all stored objects. This module provides
a thin wrapper around Python's zlib with Git-compatible defaults.
"""

import zlib

# Default compression level (matches Git's default)
DEFAULT_LEVEL = zlib.Z_DEFAULT_COMPRESSION  # Usually 6


def compress(data: bytes, level: int = DEFAULT_LEVEL) -> bytes:
    """Compress data using zlib.

    Args:
        data: Raw bytes to compress.
        level: Compression level (0-9, -1 for default).

    Returns:
        Compressed bytes.
    """
    return zlib.compress(data, level)


def decompress(data: bytes) -> bytes:
    """Decompress zlib data.

    Args:
        data: Compressed bytes.

    Returns:
        Decompressed bytes.

    Raises:
        zlib.error: Invalid compressed data.
    """
    return zlib.decompress(data)


def decompress_stream(data: bytes) -> tuple[bytes, bytes]:
    """Decompress data, returning decompressed content and remaining bytes.

    Useful for packfiles where multiple compressed streams are concatenated.

    Args:
        data: Compressed bytes (possibly with trailing data).

    Returns:
        Tuple of (decompressed_content, remaining_bytes).
    """
    decompressor = zlib.decompressobj()
    content = decompressor.decompress(data)
    remaining = decompressor.unused_data
    return content, remaining
