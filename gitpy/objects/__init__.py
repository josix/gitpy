"""Git object model implementation.

This module provides the core Git object types:
- Blob: File contents
- Tree: Directory listing
- Commit: Repository snapshot with metadata
- Tag: Annotated tag with metadata

All objects are content-addressable, identified by SHA-1 hash.
"""

import hashlib

from .base import GitObject
from .blob import Blob
from .commit import Commit, Identity
from .tag import Tag
from .tree import Tree, TreeEntry

__all__ = [
    "GitObject",
    "Blob",
    "Tree",
    "TreeEntry",
    "Commit",
    "Identity",
    "Tag",
    "parse_object",
    "create_object_data",
    "OBJECT_TYPES",
]

OBJECT_TYPES: dict[str, type[GitObject]] = {
    "blob": Blob,
    "tree": Tree,
    "commit": Commit,
    "tag": Tag,
}


def parse_object(data: bytes) -> tuple[str, GitObject]:
    """Parse a complete Git object (with header).

    Takes raw object data including the header and returns the SHA-1 hash
    and deserialized object.

    Args:
        data: Complete object data with header: "<type> <size>\\0<content>"

    Returns:
        Tuple of (sha, object) where sha is the 40-char hex hash.

    Raises:
        ValueError: If object type is unknown or size mismatches.
    """
    # Find header boundary
    null_idx = data.index(b"\0")
    header = data[:null_idx].decode("ascii")
    content = data[null_idx + 1 :]

    # Parse header
    type_name, size_str = header.split(" ")
    size = int(size_str)

    if len(content) != size:
        raise ValueError(f"Size mismatch: header says {size}, got {len(content)}")

    # Create appropriate object
    if type_name not in OBJECT_TYPES:
        raise ValueError(f"Unknown object type: {type_name}")

    obj_class = OBJECT_TYPES[type_name]
    obj = obj_class.deserialize(content)

    # Compute and return SHA
    sha = hashlib.sha1(data).hexdigest()

    return sha, obj


def create_object_data(obj: GitObject) -> bytes:
    """Create complete Git object data (with header) from object.

    Args:
        obj: A GitObject instance to serialize.

    Returns:
        Complete object data ready for storage: "<type> <size>\\0<content>"
    """
    content = obj.serialize()
    header = f"{obj.type_name} {len(content)}\0".encode()
    return header + content
