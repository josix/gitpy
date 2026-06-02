"""Tag management.

Provides lightweight and annotated tag data-classes plus TagManager for
create, get, delete, list, and peel operations.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from gitpy.objects.commit import Identity
from gitpy.objects.tag import Tag as TagObject
from gitpy.storage.database import ObjectDatabase

if TYPE_CHECKING:
    from .manager import RefManager


@dataclass(slots=True)
class LightweightTag:
    """A lightweight tag (just a reference, no tag object).

    Attributes:
        name: Short tag name.
        sha: SHA the tag points to (usually a commit).
    """

    name: str
    sha: str

    @property
    def is_annotated(self) -> bool:
        """Always False for lightweight tags."""
        return False


@dataclass(slots=True)
class AnnotatedTag:
    """An annotated tag (tag object + reference).

    Attributes:
        name: Short tag name.
        sha: SHA of the tag *object*.
        target: SHA of the tagged commit (or other object).
        message: Tag message.
        tagger: Identity who created the tag, or None.
    """

    name: str
    sha: str
    target: str
    message: str
    tagger: Identity | None

    @property
    def is_annotated(self) -> bool:
        """Always True for annotated tags."""
        return True


type TagType = LightweightTag | AnnotatedTag


class TagManager:
    """High-level tag operations.

    Args:
        ref_manager: RefManager instance for this repository.
        object_db: ObjectDatabase instance for this repository.
    """

    def __init__(self, ref_manager: RefManager, object_db: ObjectDatabase) -> None:
        """Initialise TagManager.

        Args:
            ref_manager: Ref manager for the repository.
            object_db: Object database for the repository.
        """
        self.refs = ref_manager
        self.objects = object_db

    def get(self, name: str) -> TagType | None:
        """Get a tag by name, distinguishing lightweight from annotated.

        Args:
            name: Short tag name.

        Returns:
            LightweightTag or AnnotatedTag, or None if not found.
        """
        sha = self.refs.resolve(f"refs/tags/{name}")
        if sha is None:
            return None

        obj_type = self.objects.get_type(sha)
        if obj_type == "tag":
            tag_obj = self.objects.read_tag(sha)
            return AnnotatedTag(
                name=name,
                sha=sha,
                target=tag_obj.object_sha,
                message=tag_obj.message,
                tagger=tag_obj.tagger,
            )

        return LightweightTag(name=name, sha=sha)

    def create_lightweight(
        self, name: str, sha: str, force: bool = False
    ) -> LightweightTag:
        """Create a lightweight tag.

        Args:
            name: Short tag name.
            sha: SHA to tag (usually a commit).
            force: If True, overwrite existing tag.

        Returns:
            Created LightweightTag.

        Raises:
            ValueError: Tag already exists and *force* is False.
        """
        if self.exists(name) and not force:
            raise ValueError(f"Tag '{name}' already exists")

        self.refs.write(f"refs/tags/{name}", sha)
        return LightweightTag(name=name, sha=sha)

    def create_annotated(
        self,
        name: str,
        sha: str,
        message: str,
        tagger: Identity,
        force: bool = False,
    ) -> AnnotatedTag:
        """Create an annotated tag.

        Writes a tag object to the object database and creates a ref
        pointing to that object.

        Args:
            name: Short tag name.
            sha: SHA of the object being tagged (usually a commit).
            message: Tag message.
            tagger: Identity of the person creating the tag.
            force: If True, overwrite existing tag.

        Returns:
            Created AnnotatedTag.

        Raises:
            ValueError: Tag already exists and *force* is False.
        """
        if self.exists(name) and not force:
            raise ValueError(f"Tag '{name}' already exists")

        tag_obj = TagObject(
            object_sha=sha,
            object_type="commit",
            tag_name=name,
            tagger=tagger,
            message=message,
        )
        tag_sha = self.objects.write(tag_obj)

        self.refs.write(f"refs/tags/{name}", tag_sha)

        return AnnotatedTag(
            name=name,
            sha=tag_sha,
            target=sha,
            message=message,
            tagger=tagger,
        )

    def exists(self, name: str) -> bool:
        """Check whether a tag exists.

        Args:
            name: Short tag name.

        Returns:
            True if the tag ref resolves.
        """
        return self.refs.resolve(f"refs/tags/{name}") is not None

    def delete(self, name: str) -> bool:
        """Delete a tag.

        Args:
            name: Short tag name.

        Returns:
            True if deleted, False if it did not exist.
        """
        return self.refs.delete(f"refs/tags/{name}")

    def list(self) -> list[TagType]:
        """List all tags.

        Returns:
            List of LightweightTag or AnnotatedTag instances.
        """
        tags: list[TagType] = []
        for name, _ in self.refs.list_tags():
            tag = self.get(name)
            if tag is not None:
                tags.append(tag)
        return tags

    def peel(self, name: str) -> str | None:
        """Resolve a tag to the underlying commit SHA.

        For lightweight tags this is the sha itself; for annotated tags
        this follows the tag object to its target.

        Args:
            name: Short tag name.

        Returns:
            Commit SHA, or None if the tag does not exist.
        """
        tag = self.get(name)
        if tag is None:
            return None
        if isinstance(tag, LightweightTag):
            return tag.sha
        return tag.target
