"""Commit object implementation."""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Self

from .base import GitObject


@dataclass(slots=True)
class Identity:
    """Author or committer identity.

    Represents a person's identity in Git commits and tags, including
    their name, email, timestamp, and timezone offset.

    Attributes:
        name: Person's name (can contain spaces).
        email: Email address.
        timestamp: Unix timestamp (seconds since epoch).
        tz_offset: Timezone offset as "+HHMM" or "-HHMM".
    """

    name: str
    email: str
    timestamp: int
    tz_offset: str

    def __str__(self) -> str:
        """Format as Git identity string.

        Returns:
            String in format "Name <email> timestamp tz_offset".
        """
        return f"{self.name} <{self.email}> {self.timestamp} {self.tz_offset}"

    @classmethod
    def parse(cls, line: str) -> Self:
        """Parse 'Name <email> timestamp tz' format.

        Args:
            line: Identity string from Git object.

        Returns:
            A new Identity instance.
        """
        # Find email boundaries
        lt = line.index("<")
        gt = line.index(">")

        name = line[:lt].strip()
        email = line[lt + 1 : gt]

        # Parse timestamp and timezone
        rest = line[gt + 1 :].strip().split()
        timestamp = int(rest[0])
        tz_offset = rest[1] if len(rest) > 1 else "+0000"

        return cls(name=name, email=email, timestamp=timestamp, tz_offset=tz_offset)

    @classmethod
    def now(cls, name: str, email: str, tz_offset: str = "+0000") -> Self:
        """Create identity with current timestamp.

        Args:
            name: Person's name.
            email: Email address.
            tz_offset: Timezone offset (default: "+0000" for UTC).

        Returns:
            A new Identity instance with current time.
        """
        now = datetime.now(timezone.utc)
        return cls(
            name=name,
            email=email,
            timestamp=int(now.timestamp()),
            tz_offset=tz_offset,
        )


@dataclass(slots=True)
class Commit(GitObject):
    """Represents a commit object in Git.

    A commit is a snapshot of the repository at a point in time. It points
    to a tree (the root directory) and contains metadata about who made
    the change and when.

    Attributes:
        tree_sha: SHA-1 hash of the root tree object.
        parent_shas: List of parent commit SHAs (empty for root, multiple for merge).
        author: Identity of who wrote the change.
        committer: Identity of who committed the change.
        message: Commit message (can be multiple lines).
    """

    tree_sha: str = ""
    parent_shas: list[str] = field(default_factory=list)
    author: Identity | None = None
    committer: Identity | None = None
    message: str = ""
    type_name: str = "commit"

    def serialize(self) -> bytes:
        """Serialize commit to bytes.

        Returns:
            Binary representation of the commit.
        """
        lines = []

        lines.append(f"tree {self.tree_sha}")

        for parent in self.parent_shas:
            lines.append(f"parent {parent}")

        lines.append(f"author {self.author}")
        lines.append(f"committer {self.committer}")
        lines.append("")  # Blank line separates headers from message
        lines.append(self.message)

        return "\n".join(lines).encode("utf-8")

    @classmethod
    def deserialize(cls, data: bytes) -> Self:
        """Parse commit from bytes.

        Args:
            data: Binary commit data (without header).

        Returns:
            A new Commit instance.
        """
        text = data.decode("utf-8")
        lines = text.split("\n")

        tree_sha = ""
        parent_shas: list[str] = []
        author = None
        committer = None
        message_start = 0

        for i, line in enumerate(lines):
            if line == "":
                message_start = i + 1
                break

            if line.startswith("tree "):
                tree_sha = line[5:]
            elif line.startswith("parent "):
                parent_shas.append(line[7:])
            elif line.startswith("author "):
                author = Identity.parse(line[7:])
            elif line.startswith("committer "):
                committer = Identity.parse(line[10:])

        message = "\n".join(lines[message_start:])

        return cls(
            tree_sha=tree_sha,
            parent_shas=parent_shas,
            author=author,
            committer=committer,
            message=message,
        )

    @property
    def is_root(self) -> bool:
        """True if this is a root commit (no parents)."""
        return len(self.parent_shas) == 0

    @property
    def is_merge(self) -> bool:
        """True if this is a merge commit (multiple parents)."""
        return len(self.parent_shas) > 1
