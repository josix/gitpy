"""Tests for ObjectDatabase."""

from pathlib import Path

import pytest

from gitpy.objects import Blob, Commit, Identity, Tree, TreeEntry
from gitpy.storage.database import ObjectDatabase


class TestObjectDatabase:
    """Tests for ObjectDatabase class."""

    @pytest.fixture
    def db(self, tmp_path: Path) -> ObjectDatabase:
        """Create a database with temporary git directory."""
        git_dir = tmp_path / ".git"
        git_dir.mkdir()
        (git_dir / "objects").mkdir()
        return ObjectDatabase(git_dir)

    def test_write_and_read_blob(self, db: ObjectDatabase) -> None:
        """Write blob and read back."""
        blob = Blob(data=b"hello world")
        sha = db.write(blob)

        result = db.read_blob(sha)
        assert result.data == b"hello world"

    def test_write_and_read_tree(self, db: ObjectDatabase) -> None:
        """Write tree and read back."""
        # First create a blob
        blob = Blob(data=b"file content")
        blob_sha = db.write(blob)

        # Create tree with entry
        entry = TreeEntry(mode=0o100644, name="file.txt", sha=blob_sha)
        tree = Tree(entries=[entry])
        tree_sha = db.write(tree)

        result = db.read_tree(tree_sha)
        assert len(result.entries) == 1
        assert result.entries[0].name == "file.txt"
        assert result.entries[0].sha == blob_sha

    def test_write_and_read_commit(self, db: ObjectDatabase) -> None:
        """Write commit and read back."""
        # Create a tree first
        tree = Tree(entries=[])
        tree_sha = db.write(tree)

        # Create commit
        author = Identity(name="Test", email="test@example.com", timestamp=1234567890, tz_offset=0)
        commit = Commit(
            tree_sha=tree_sha,
            parent_shas=[],
            author=author,
            committer=author,
            message="Initial commit\n",
        )
        commit_sha = db.write(commit)

        result = db.read_commit(commit_sha)
        assert result.tree_sha == tree_sha
        assert result.message == "Initial commit\n"

    def test_exists_full_sha(self, db: ObjectDatabase) -> None:
        """Check existence with full SHA."""
        blob = Blob(data=b"exists test")
        sha = db.write(blob)

        assert db.exists(sha) is True
        assert db.exists("0" * 40) is False

    def test_exists_short_sha(self, db: ObjectDatabase) -> None:
        """Check existence with short SHA."""
        blob = Blob(data=b"short sha test")
        sha = db.write(blob)

        assert db.exists(sha[:7]) is True
        assert db.exists("0000") is False

    def test_short_sha_resolution(self, db: ObjectDatabase) -> None:
        """Short SHA resolves to full."""
        blob = Blob(data=b"unique content 12345")
        sha = db.write(blob)

        # Read with short SHA
        short = sha[:7]
        result = db.read_blob(short)
        assert result.data == b"unique content 12345"

    def test_short_sha_too_short(self, db: ObjectDatabase) -> None:
        """SHA prefix too short raises error."""
        with pytest.raises(ValueError, match="too short"):
            db._resolve_short_sha("abc")

    def test_type_checking_blob(self, db: ObjectDatabase) -> None:
        """Reading blob as wrong type raises TypeError."""
        blob = Blob(data=b"not a tree")
        sha = db.write(blob)

        with pytest.raises(TypeError, match="Expected tree"):
            db.read_tree(sha)

        with pytest.raises(TypeError, match="Expected commit"):
            db.read_commit(sha)

    def test_get_type(self, db: ObjectDatabase) -> None:
        """Get type without full parse."""
        blob = Blob(data=b"type test")
        sha = db.write(blob)

        assert db.get_type(sha) == "blob"

    def test_get_size(self, db: ObjectDatabase) -> None:
        """Get size without full parse."""
        blob = Blob(data=b"12345")
        sha = db.write(blob)

        assert db.get_size(sha) == 5

    def test_hash_object_write_true(self, db: ObjectDatabase) -> None:
        """hash_object with write=True stores object."""
        blob = Blob(data=b"hash write test")
        sha = db.hash_object(blob, write=True)

        assert db.exists(sha)
        assert db.read_blob(sha).data == b"hash write test"

    def test_hash_object_write_false(self, db: ObjectDatabase) -> None:
        """hash_object with write=False doesn't store object."""
        blob = Blob(data=b"hash no write test")
        sha = db.hash_object(blob, write=False)

        assert not db.exists(sha)

    def test_read_raw(self, db: ObjectDatabase) -> None:
        """read_raw returns raw data with header."""
        blob = Blob(data=b"raw test")
        sha = db.write(blob)

        raw = db.read_raw(sha)
        assert raw.startswith(b"blob 8\0")
        assert b"raw test" in raw

    def test_read_not_found(self, db: ObjectDatabase) -> None:
        """Reading non-existent object raises error."""
        with pytest.raises(FileNotFoundError):
            db.read("0" * 40)

    def test_read_short_sha_not_found(self, db: ObjectDatabase) -> None:
        """Reading non-existent short SHA raises error."""
        with pytest.raises(FileNotFoundError):
            db.read("0000000")


class TestObjectDatabaseKnownHashes:
    """Test known Git object hashes for compatibility."""

    @pytest.fixture
    def db(self, tmp_path: Path) -> ObjectDatabase:
        """Create a database with temporary git directory."""
        git_dir = tmp_path / ".git"
        git_dir.mkdir()
        (git_dir / "objects").mkdir()
        return ObjectDatabase(git_dir)

    def test_empty_blob_hash(self, db: ObjectDatabase) -> None:
        """Empty blob has known hash."""
        blob = Blob(data=b"")
        sha = db.hash_object(blob, write=False)
        assert sha == "e69de29bb2d1d6434b8b29ae775ad8c2e48c5391"

    def test_hello_newline_blob_hash(self, db: ObjectDatabase) -> None:
        """'hello\\n' blob has known hash."""
        blob = Blob(data=b"hello\n")
        sha = db.hash_object(blob, write=False)
        assert sha == "ce013625030ba8dba906f756967f9e9ca394464a"

    def test_empty_tree_hash(self, db: ObjectDatabase) -> None:
        """Empty tree has known hash."""
        tree = Tree(entries=[])
        sha = db.hash_object(tree, write=False)
        assert sha == "4b825dc642cb6eb9a060e54bf8d69288fbee4904"
