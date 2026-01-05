"""Tests for Tag object."""

import pytest

from gitpy.objects import Identity, Tag


class TestTag:
    """Tests for Tag class."""

    def test_tag_basic(self) -> None:
        """Create basic tag."""
        tagger = Identity(
            name="Test User",
            email="test@example.com",
            timestamp=1234567890,
            tz_offset="+0000",
        )
        tag = Tag(
            object_sha="a" * 40,
            object_type="commit",
            tag_name="v1.0.0",
            tagger=tagger,
            message="Release version 1.0.0",
        )
        assert tag.object_sha == "a" * 40
        assert tag.object_type == "commit"
        assert tag.tag_name == "v1.0.0"
        assert tag.tagger is not None
        assert tag.tagger.name == "Test User"

    def test_tag_roundtrip(self) -> None:
        """Serialize then deserialize preserves all fields."""
        tagger = Identity(
            name="Tagger Name",
            email="tagger@example.com",
            timestamp=1234567890,
            tz_offset="-0700",
        )
        original = Tag(
            object_sha="b" * 40,
            object_type="commit",
            tag_name="v2.0.0",
            tagger=tagger,
            message="Major release\n\nWith breaking changes.",
        )

        restored = Tag.deserialize(original.serialize())

        assert restored.object_sha == original.object_sha
        assert restored.object_type == original.object_type
        assert restored.tag_name == original.tag_name
        assert restored.tagger is not None
        assert restored.tagger.name == "Tagger Name"
        assert restored.tagger.tz_offset == "-0700"
        assert "breaking changes" in restored.message

    def test_tag_multiline_message(self) -> None:
        """Tag preserves multiline message."""
        tagger = Identity(
            name="Test", email="test@example.com", timestamp=0, tz_offset="+0000"
        )
        message = "Tag subject\n\nDetailed notes.\n\n- Point 1\n- Point 2"
        tag = Tag(
            object_sha="a" * 40,
            object_type="commit",
            tag_name="v1.0",
            tagger=tagger,
            message=message,
        )
        restored = Tag.deserialize(tag.serialize())
        assert restored.message == message

    def test_tag_serialization_format(self) -> None:
        """Verify exact serialization format."""
        tagger = Identity(
            name="Test", email="test@example.com", timestamp=1234567890, tz_offset="+0000"
        )
        tag = Tag(
            object_sha="a" * 40,
            object_type="commit",
            tag_name="v1.0",
            tagger=tagger,
            message="Tag message",
        )
        data = tag.serialize()
        text = data.decode("utf-8")

        lines = text.split("\n")
        assert lines[0] == f"object {'a' * 40}"
        assert lines[1] == "type commit"
        assert lines[2] == "tag v1.0"
        assert lines[3].startswith("tagger Test <test@example.com>")
        assert lines[4] == ""  # Blank line before message
        assert lines[5] == "Tag message"

    def test_tag_for_tree(self) -> None:
        """Tag can point to tree."""
        tagger = Identity(
            name="Test", email="test@example.com", timestamp=0, tz_offset="+0000"
        )
        tag = Tag(
            object_sha="4b825dc642cb6eb9a060e54bf8d69288fbee4904",
            object_type="tree",
            tag_name="empty-tree",
            tagger=tagger,
            message="Tag pointing to empty tree",
        )
        restored = Tag.deserialize(tag.serialize())
        assert restored.object_type == "tree"

    def test_tag_for_blob(self) -> None:
        """Tag can point to blob."""
        tagger = Identity(
            name="Test", email="test@example.com", timestamp=0, tz_offset="+0000"
        )
        tag = Tag(
            object_sha="e69de29bb2d1d6434b8b29ae775ad8c2e48c5391",
            object_type="blob",
            tag_name="empty-blob",
            tagger=tagger,
            message="Tag pointing to empty blob",
        )
        restored = Tag.deserialize(tag.serialize())
        assert restored.object_type == "blob"

    def test_tag_hash_deterministic(self) -> None:
        """Same tag data produces same hash."""
        tagger = Identity(
            name="Test", email="test@example.com", timestamp=1234567890, tz_offset="+0000"
        )
        tag1 = Tag(
            object_sha="a" * 40,
            object_type="commit",
            tag_name="v1.0",
            tagger=tagger,
            message="Test",
        )
        tag2 = Tag(
            object_sha="a" * 40,
            object_type="commit",
            tag_name="v1.0",
            tagger=tagger,
            message="Test",
        )
        assert tag1.oid == tag2.oid

    def test_tag_type_name(self) -> None:
        """Tag has correct type name."""
        tag = Tag()
        assert tag.type_name == "tag"
