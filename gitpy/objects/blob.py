"""Blob object implementation."""

from dataclasses import dataclass
from pathlib import Path
from typing import Self

from .base import GitObject


@dataclass(slots=True)
class Blob(GitObject):
    """Represents file contents in Git.

    A blob (binary large object) stores the raw contents of a single file.
    It contains no filename, permissions, or other metadata - just the
    raw binary content. Filenames are stored in the parent tree object.

    Attributes:
        data: Raw file contents as bytes.
    """

    data: bytes = b""
    type_name: str = "blob"

    def serialize(self) -> bytes:
        """Return raw content.

        Returns:
            The raw file contents.
        """
        return self.data

    @classmethod
    def deserialize(cls, data: bytes) -> Self:
        """Create Blob from raw content.

        Args:
            data: Raw bytes of the file contents.

        Returns:
            A new Blob instance.
        """
        return cls(data=data)

    @classmethod
    def from_file(cls, path: str | Path) -> Self:
        """Create Blob from file path.

        Args:
            path: Path to the file to read.

        Returns:
            A new Blob instance with the file's contents.
        """
        with open(path, "rb") as f:
            return cls(data=f.read())
