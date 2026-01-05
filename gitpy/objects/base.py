"""Base class for all Git objects."""

from abc import ABC, abstractmethod
import hashlib
from typing import Self


class GitObject(ABC):
    """Abstract base class for all Git objects.

    Git objects are immutable, content-addressable entities identified by
    a SHA-1 hash of their contents. This base class provides the common
    interface for all object types (blob, tree, commit, tag).
    """

    type_name: str  # "blob", "tree", "commit", "tag"

    @abstractmethod
    def serialize(self) -> bytes:
        """Serialize object content (without header).

        Returns:
            The raw bytes representing this object's content.
        """

    @classmethod
    @abstractmethod
    def deserialize(cls, data: bytes) -> Self:
        """Deserialize object content (without header).

        Args:
            data: Raw bytes of the object content.

        Returns:
            A new instance of the object.
        """

    def compute_hash(self) -> str:
        """Compute SHA-1 hash of this object.

        The hash is computed over the full object data including the header:
        "<type> <size>\\0<content>"

        Returns:
            40-character hexadecimal SHA-1 hash.
        """
        content = self.serialize()
        header = f"{self.type_name} {len(content)}\0".encode()
        return hashlib.sha1(header + content).hexdigest()

    @property
    def oid(self) -> str:
        """Object ID (SHA-1 hash).

        Returns:
            40-character hexadecimal SHA-1 hash identifying this object.
        """
        return self.compute_hash()

    def __eq__(self, other: object) -> bool:
        """Two objects are equal if they have the same OID."""
        if not isinstance(other, GitObject):
            return NotImplemented
        return self.oid == other.oid

    def __hash__(self) -> int:
        """Hash based on OID for use in sets and dicts."""
        return hash(self.oid)
