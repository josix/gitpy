"""Tag object implementation."""

from dataclasses import dataclass
from typing import Self

from .base import GitObject
from .commit import Identity


@dataclass(slots=True)
class Tag(GitObject):
    """Represents an annotated tag object in Git.

    An annotated tag points to another object (usually a commit) with
    additional metadata: tagger identity, date, and message.

    Note: Lightweight tags are just references (not objects) and are
    handled in the refs module.

    Attributes:
        object_sha: SHA-1 hash of the tagged object.
        object_type: Type of tagged object ("commit", "tree", "blob", "tag").
        tag_name: Name of the tag.
        tagger: Identity of who created the tag.
        message: Tag message (can be multiple lines).
    """

    object_sha: str = ""
    object_type: str = "commit"
    tag_name: str = ""
    tagger: Identity | None = None
    message: str = ""
    type_name: str = "tag"

    def serialize(self) -> bytes:
        """Serialize tag to bytes.

        Returns:
            Binary representation of the tag.
        """
        lines = [
            f"object {self.object_sha}",
            f"type {self.object_type}",
            f"tag {self.tag_name}",
            f"tagger {self.tagger}",
            "",
            self.message,
        ]
        return "\n".join(lines).encode("utf-8")

    @classmethod
    def deserialize(cls, data: bytes) -> Self:
        """Parse tag from bytes.

        Args:
            data: Binary tag data (without header).

        Returns:
            A new Tag instance.
        """
        text = data.decode("utf-8")
        lines = text.split("\n")

        object_sha = ""
        object_type = ""
        tag_name = ""
        tagger = None
        message_start = 0

        for i, line in enumerate(lines):
            if line == "":
                message_start = i + 1
                break

            if line.startswith("object "):
                object_sha = line[7:]
            elif line.startswith("type "):
                object_type = line[5:]
            elif line.startswith("tag "):
                tag_name = line[4:]
            elif line.startswith("tagger "):
                tagger = Identity.parse(line[7:])

        message = "\n".join(lines[message_start:])

        return cls(
            object_sha=object_sha,
            object_type=object_type,
            tag_name=tag_name,
            tagger=tagger,
            message=message,
        )
