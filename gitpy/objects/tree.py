"""Tree object implementation."""

from dataclasses import dataclass, field
from typing import Self

from .base import GitObject


@dataclass(slots=True)
class TreeEntry:
    """Single entry in a tree object.

    Represents a file or subdirectory in a Git tree. Each entry has a mode
    (file permissions), name (filename without path), and SHA (object ID).

    Attributes:
        mode: File mode as string ("100644", "100755", "40000", "120000").
        name: Filename without path separators.
        sha: 40-character hexadecimal SHA-1 of the referenced object.
    """

    mode: str
    name: str
    sha: str

    @property
    def is_tree(self) -> bool:
        """True if this entry points to a tree (directory)."""
        return self.mode == "40000"

    @property
    def is_blob(self) -> bool:
        """True if this entry points to a blob (regular file)."""
        return self.mode in ("100644", "100755")

    @property
    def is_symlink(self) -> bool:
        """True if this entry is a symbolic link."""
        return self.mode == "120000"

    @property
    def is_executable(self) -> bool:
        """True if this entry is an executable file."""
        return self.mode == "100755"

    def sort_key(self) -> str:
        """Generate sort key for tree entry ordering.

        Git sorts tree entries by name, but directories are sorted as if
        they had a trailing '/'. This ensures correct ordering like:
        'foo.txt' < 'foo' (directory) < 'foobar'

        Returns:
            Sort key string.
        """
        return self.name + "/" if self.is_tree else self.name


@dataclass(slots=True)
class Tree(GitObject):
    """Represents a directory listing in Git.

    A tree contains entries mapping names to blobs (files) or other trees
    (subdirectories), along with file mode information.

    Attributes:
        entries: List of TreeEntry objects.
    """

    entries: list[TreeEntry] = field(default_factory=list)
    type_name: str = "tree"

    def serialize(self) -> bytes:
        """Serialize tree to bytes.

        Format: sequence of entries, each as "<mode> <name>\\0<20-byte-sha>"
        Entries are sorted by Git's sorting rules.

        Returns:
            Binary representation of the tree.
        """
        sorted_entries = sorted(self.entries, key=lambda e: e.sort_key())

        result = b""
        for entry in sorted_entries:
            mode_name = f"{entry.mode} {entry.name}\0".encode()
            sha_binary = bytes.fromhex(entry.sha)
            result += mode_name + sha_binary

        return result

    @classmethod
    def deserialize(cls, data: bytes) -> Self:
        """Parse tree from bytes.

        Args:
            data: Binary tree data (without header).

        Returns:
            A new Tree instance.
        """
        entries: list[TreeEntry] = []
        pos = 0

        while pos < len(data):
            # Find space after mode
            space_idx = data.index(b" ", pos)
            mode = data[pos:space_idx].decode("ascii")

            # Find null after name
            null_idx = data.index(b"\0", space_idx)
            name = data[space_idx + 1 : null_idx].decode("utf-8")

            # Next 20 bytes are binary SHA
            sha_binary = data[null_idx + 1 : null_idx + 21]
            sha = sha_binary.hex()

            entries.append(TreeEntry(mode=mode, name=name, sha=sha))
            pos = null_idx + 21

        return cls(entries=entries)

    def add_entry(self, mode: str, name: str, sha: str) -> None:
        """Add an entry to this tree.

        Args:
            mode: File mode string.
            name: Filename (must not contain '/').
            sha: 40-character SHA-1 hash.

        Raises:
            ValueError: If name contains '/'.
        """
        if "/" in name:
            raise ValueError("Tree entry name cannot contain '/'")
        self.entries.append(TreeEntry(mode=mode, name=name, sha=sha))

    def get_entry(self, name: str) -> TreeEntry | None:
        """Get entry by name.

        Args:
            name: Filename to look up.

        Returns:
            The TreeEntry if found, None otherwise.
        """
        for entry in self.entries:
            if entry.name == name:
                return entry
        return None
