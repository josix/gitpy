"""Tests for object factory functions."""

import pytest

from gitpy.objects import (
    OBJECT_TYPES,
    Blob,
    Commit,
    Identity,
    Tag,
    Tree,
    TreeEntry,
    create_object_data,
    parse_object,
)


class TestObjectFactory:
    """Tests for parse_object and create_object_data."""

    def test_parse_blob(self) -> None:
        """Parse complete blob object."""
        content = b"hello\n"
        data = b"blob 6\0" + content

        sha, obj = parse_object(data)

        assert sha == "ce013625030ba8dba906f756967f9e9ca394464a"
        assert isinstance(obj, Blob)
        assert obj.data == content

    def test_parse_empty_blob(self) -> None:
        """Parse empty blob object."""
        data = b"blob 0\0"

        sha, obj = parse_object(data)

        assert sha == "e69de29bb2d1d6434b8b29ae775ad8c2e48c5391"
        assert isinstance(obj, Blob)
        assert obj.data == b""

    def test_parse_tree(self) -> None:
        """Parse tree object."""
        # Create a tree with one entry
        tree = Tree(
            entries=[
                TreeEntry(
                    mode="100644",
                    name="hello.txt",
                    sha="ce013625030ba8dba906f756967f9e9ca394464a",
                )
            ]
        )
        data = create_object_data(tree)

        sha, obj = parse_object(data)

        assert isinstance(obj, Tree)
        assert len(obj.entries) == 1
        assert obj.entries[0].name == "hello.txt"

    def test_parse_commit(self) -> None:
        """Parse commit object."""
        author = Identity(
            name="Test", email="test@example.com", timestamp=0, tz_offset="+0000"
        )
        commit = Commit(
            tree_sha="4b825dc642cb6eb9a060e54bf8d69288fbee4904",
            parent_shas=[],
            author=author,
            committer=author,
            message="Initial",
        )
        data = create_object_data(commit)

        sha, obj = parse_object(data)

        assert isinstance(obj, Commit)
        assert obj.message == "Initial"

    def test_parse_tag(self) -> None:
        """Parse tag object."""
        tagger = Identity(
            name="Test", email="test@example.com", timestamp=0, tz_offset="+0000"
        )
        tag = Tag(
            object_sha="a" * 40,
            object_type="commit",
            tag_name="v1.0",
            tagger=tagger,
            message="Release",
        )
        data = create_object_data(tag)

        sha, obj = parse_object(data)

        assert isinstance(obj, Tag)
        assert obj.tag_name == "v1.0"

    def test_parse_size_mismatch(self) -> None:
        """Size mismatch raises ValueError."""
        data = b"blob 100\0hello"  # Claims 100 bytes, has 5

        with pytest.raises(ValueError, match="Size mismatch"):
            parse_object(data)

    def test_parse_unknown_type(self) -> None:
        """Unknown type raises ValueError."""
        data = b"unknown 5\0hello"

        with pytest.raises(ValueError, match="Unknown object type"):
            parse_object(data)

    def test_create_object_data_blob(self) -> None:
        """Create complete blob data."""
        blob = Blob(data=b"hello\n")
        data = create_object_data(blob)

        assert data == b"blob 6\0hello\n"

    def test_create_object_data_empty_blob(self) -> None:
        """Create empty blob data."""
        blob = Blob(data=b"")
        data = create_object_data(blob)

        assert data == b"blob 0\0"

    def test_roundtrip_blob(self) -> None:
        """Blob roundtrips through create/parse."""
        original = Blob(data=b"test content")
        data = create_object_data(original)
        _, restored = parse_object(data)

        assert isinstance(restored, Blob)
        assert restored.data == original.data

    def test_roundtrip_tree(self) -> None:
        """Tree roundtrips through create/parse."""
        original = Tree(
            entries=[
                TreeEntry(mode="100644", name="file.txt", sha="a" * 40),
                TreeEntry(mode="40000", name="dir", sha="b" * 40),
            ]
        )
        data = create_object_data(original)
        _, restored = parse_object(data)

        assert isinstance(restored, Tree)
        assert len(restored.entries) == 2

    def test_roundtrip_commit(self) -> None:
        """Commit roundtrips through create/parse."""
        author = Identity(
            name="Test", email="test@example.com", timestamp=1234567890, tz_offset="+0000"
        )
        original = Commit(
            tree_sha="a" * 40,
            parent_shas=["b" * 40],
            author=author,
            committer=author,
            message="Test commit",
        )
        data = create_object_data(original)
        _, restored = parse_object(data)

        assert isinstance(restored, Commit)
        assert restored.tree_sha == original.tree_sha
        assert restored.message == original.message

    def test_roundtrip_tag(self) -> None:
        """Tag roundtrips through create/parse."""
        tagger = Identity(
            name="Test", email="test@example.com", timestamp=1234567890, tz_offset="+0000"
        )
        original = Tag(
            object_sha="a" * 40,
            object_type="commit",
            tag_name="v1.0",
            tagger=tagger,
            message="Release",
        )
        data = create_object_data(original)
        _, restored = parse_object(data)

        assert isinstance(restored, Tag)
        assert restored.tag_name == original.tag_name

    def test_object_types_registry(self) -> None:
        """OBJECT_TYPES contains all object types."""
        assert "blob" in OBJECT_TYPES
        assert "tree" in OBJECT_TYPES
        assert "commit" in OBJECT_TYPES
        assert "tag" in OBJECT_TYPES

        assert OBJECT_TYPES["blob"] is Blob
        assert OBJECT_TYPES["tree"] is Tree
        assert OBJECT_TYPES["commit"] is Commit
        assert OBJECT_TYPES["tag"] is Tag
