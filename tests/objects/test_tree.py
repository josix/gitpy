"""Tests for Tree object."""

import pytest

from gitpy.objects import Tree, TreeEntry


class TestTreeEntry:
    """Tests for TreeEntry class."""

    def test_entry_is_tree(self) -> None:
        """Directory entry is identified as tree."""
        entry = TreeEntry(mode="40000", name="subdir", sha="a" * 40)
        assert entry.is_tree is True
        assert entry.is_blob is False
        assert entry.is_symlink is False

    def test_entry_is_blob_regular(self) -> None:
        """Regular file entry is identified as blob."""
        entry = TreeEntry(mode="100644", name="file.txt", sha="a" * 40)
        assert entry.is_blob is True
        assert entry.is_tree is False
        assert entry.is_executable is False

    def test_entry_is_blob_executable(self) -> None:
        """Executable file entry is identified correctly."""
        entry = TreeEntry(mode="100755", name="script.sh", sha="a" * 40)
        assert entry.is_blob is True
        assert entry.is_executable is True

    def test_entry_is_symlink(self) -> None:
        """Symlink entry is identified correctly."""
        entry = TreeEntry(mode="120000", name="link", sha="a" * 40)
        assert entry.is_symlink is True
        assert entry.is_blob is False

    def test_entry_sort_key_file(self) -> None:
        """File sort key is just the name."""
        entry = TreeEntry(mode="100644", name="file.txt", sha="a" * 40)
        assert entry.sort_key() == "file.txt"

    def test_entry_sort_key_directory(self) -> None:
        """Directory sort key has trailing slash."""
        entry = TreeEntry(mode="40000", name="dir", sha="a" * 40)
        assert entry.sort_key() == "dir/"


class TestTree:
    """Tests for Tree class."""

    def test_tree_empty(self) -> None:
        """Empty tree has known hash."""
        tree = Tree(entries=[])
        assert tree.oid == "4b825dc642cb6eb9a060e54bf8d69288fbee4904"

    def test_tree_single_blob(self) -> None:
        """Tree with single file roundtrips correctly."""
        tree = Tree(
            entries=[
                TreeEntry(
                    mode="100644",
                    name="hello.txt",
                    sha="ce013625030ba8dba906f756967f9e9ca394464a",
                )
            ]
        )
        restored = Tree.deserialize(tree.serialize())
        assert len(restored.entries) == 1
        assert restored.entries[0].name == "hello.txt"
        assert restored.entries[0].mode == "100644"
        assert restored.entries[0].sha == "ce013625030ba8dba906f756967f9e9ca394464a"

    def test_tree_sorting_files(self) -> None:
        """Files are sorted alphabetically."""
        tree = Tree(
            entries=[
                TreeEntry(mode="100644", name="c.txt", sha="a" * 40),
                TreeEntry(mode="100644", name="a.txt", sha="b" * 40),
                TreeEntry(mode="100644", name="b.txt", sha="c" * 40),
            ]
        )
        data = tree.serialize()
        restored = Tree.deserialize(data)
        names = [e.name for e in restored.entries]
        assert names == ["a.txt", "b.txt", "c.txt"]

    def test_tree_sorting_directory_vs_file(self) -> None:
        """Directories sorted as if they had trailing /."""
        tree = Tree(
            entries=[
                TreeEntry(mode="100644", name="b.txt", sha="a" * 40),
                TreeEntry(mode="40000", name="a", sha="b" * 40),
                TreeEntry(mode="100644", name="a.txt", sha="c" * 40),
            ]
        )
        data = tree.serialize()
        restored = Tree.deserialize(data)
        names = [e.name for e in restored.entries]
        # "a.txt" < "a/" (directory) < "b.txt"
        assert names == ["a.txt", "a", "b.txt"]

    def test_tree_binary_sha(self) -> None:
        """SHA is stored as 20 binary bytes."""
        entry = TreeEntry(
            mode="100644",
            name="test.txt",
            sha="ce013625030ba8dba906f756967f9e9ca394464a",
        )
        tree = Tree(entries=[entry])
        data = tree.serialize()

        # Check binary SHA is in the data (20 bytes after null)
        null_idx = data.index(b"\0")
        sha_bytes = data[null_idx + 1 : null_idx + 21]
        assert sha_bytes == bytes.fromhex("ce013625030ba8dba906f756967f9e9ca394464a")

    def test_tree_add_entry(self) -> None:
        """Add entry to tree."""
        tree = Tree()
        tree.add_entry("100644", "file.txt", "a" * 40)
        assert len(tree.entries) == 1
        assert tree.entries[0].name == "file.txt"

    def test_tree_add_entry_with_slash_raises(self) -> None:
        """Adding entry with / in name raises ValueError."""
        tree = Tree()
        with pytest.raises(ValueError, match="cannot contain '/'"):
            tree.add_entry("100644", "path/to/file.txt", "a" * 40)

    def test_tree_get_entry(self) -> None:
        """Get entry by name."""
        tree = Tree(
            entries=[
                TreeEntry(mode="100644", name="file1.txt", sha="a" * 40),
                TreeEntry(mode="100644", name="file2.txt", sha="b" * 40),
            ]
        )
        entry = tree.get_entry("file2.txt")
        assert entry is not None
        assert entry.sha == "b" * 40

    def test_tree_get_entry_not_found(self) -> None:
        """Get nonexistent entry returns None."""
        tree = Tree()
        assert tree.get_entry("nonexistent") is None

    def test_tree_roundtrip_multiple_entries(self) -> None:
        """Complex tree roundtrips correctly."""
        entries = [
            TreeEntry(mode="100644", name="README.md", sha="a" * 40),
            TreeEntry(mode="100755", name="run.sh", sha="b" * 40),
            TreeEntry(mode="40000", name="src", sha="c" * 40),
            TreeEntry(mode="120000", name="link", sha="d" * 40),
        ]
        tree = Tree(entries=entries)
        restored = Tree.deserialize(tree.serialize())

        assert len(restored.entries) == 4
        # Entries are sorted in serialization
        assert restored.entries[0].name == "README.md"
        assert restored.entries[1].name == "link"
        assert restored.entries[2].name == "run.sh"
        assert restored.entries[3].name == "src"

    def test_tree_type_name(self) -> None:
        """Tree has correct type name."""
        tree = Tree()
        assert tree.type_name == "tree"

    def test_tree_hash_deterministic(self) -> None:
        """Same entries produce same hash regardless of input order."""
        tree1 = Tree(
            entries=[
                TreeEntry(mode="100644", name="a.txt", sha="a" * 40),
                TreeEntry(mode="100644", name="b.txt", sha="b" * 40),
            ]
        )
        tree2 = Tree(
            entries=[
                TreeEntry(mode="100644", name="b.txt", sha="b" * 40),
                TreeEntry(mode="100644", name="a.txt", sha="a" * 40),
            ]
        )
        assert tree1.oid == tree2.oid
