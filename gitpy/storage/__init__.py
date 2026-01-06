"""Git object storage implementation.

This module provides storage backends for Git objects:
- LooseObjectStore: Individual zlib-compressed files
- ObjectDatabase: High-level interface with type-safe access

Storage format follows Git's conventions:
- Objects stored at .git/objects/<sha[0:2]>/<sha[2:40]>
- All data is zlib-compressed
- SHA-1 verification on read
"""

from .compression import compress, decompress, decompress_stream
from .database import ObjectDatabase
from .loose import LooseObjectStore

__all__ = [
    "compress",
    "decompress",
    "decompress_stream",
    "LooseObjectStore",
    "ObjectDatabase",
]
