"""Integration tests for pack file support in ObjectDatabase."""

import hashlib
from pathlib import Path

import pytest

from gitpy.objects import Blob, Commit, Identity, Tree, TreeEntry
from gitpy.storage import ObjectDatabase


class TestObjectDatabasePackSupport:
    """Tests for pack file support in ObjectDatabase."""

    def test_read_from_pack(self, tmp_path: Path) -> None:
        """Read object from pack file via ObjectDatabase."""
        objects_dir = tmp_path / "objects"
        objects_dir.mkdir()

        db = ObjectDatabase(objects_dir)

        # Write some objects as loose
        blobs = [Blob(data=f"content {i}".encode()) for i in range(5)]
        shas = [db.write(blob) for blob in blobs]

        # Repack
        pack_path, idx_path = db.repack()
        assert pack_path.exists()
        assert idx_path.exists()

        # Create new database that loads packs
        db2 = ObjectDatabase(objects_dir)

        # Should find objects in pack
        for i, sha in enumerate(shas):
            obj = db2.read(sha)
            assert obj is not None
            assert isinstance(obj, Blob)
            assert obj.data == f"content {i}".encode()

    def test_exists_checks_packs(self, tmp_path: Path) -> None:
        """ObjectDatabase.exists checks pack files."""
        objects_dir = tmp_path / "objects"
        objects_dir.mkdir()

        db = ObjectDatabase(objects_dir)

        blob = Blob(data=b"packed content")
        sha = db.write(blob)
        db.repack()

        db2 = ObjectDatabase(objects_dir)
        assert db2.exists(sha) is True
        assert db2.exists("x" * 40) is False

    def test_short_sha_resolution_in_packs(self, tmp_path: Path) -> None:
        """Short SHA resolution works with pack files."""
        objects_dir = tmp_path / "objects"
        objects_dir.mkdir()

        db = ObjectDatabase(objects_dir)

        blob = Blob(data=b"unique content for sha test")
        sha = db.write(blob)
        db.repack()

        db2 = ObjectDatabase(objects_dir)

        # Try various prefix lengths
        for length in [7, 8, 10, 20, 40]:
            obj = db2.read(sha[:length])
            assert obj is not None
            assert isinstance(obj, Blob)
            assert obj.data == b"unique content for sha test"

    def test_pack_count(self, tmp_path: Path) -> None:
        """Track number of loaded packs."""
        objects_dir = tmp_path / "objects"
        objects_dir.mkdir()

        db = ObjectDatabase(objects_dir)
        assert db.pack_count == 0

        # Create first pack
        blob1 = Blob(data=b"first")
        db.write(blob1)
        db.repack()

        db2 = ObjectDatabase(objects_dir)
        assert db2.pack_count == 1

    def test_reload_packs(self, tmp_path: Path) -> None:
        """Reload packs after new pack created."""
        objects_dir = tmp_path / "objects"
        objects_dir.mkdir()

        db = ObjectDatabase(objects_dir)

        # Create objects and pack
        blob1 = Blob(data=b"first batch")
        sha1 = db.write(blob1)
        db.repack()

        # Add more objects
        blob2 = Blob(data=b"second batch")
        sha2 = db.write(blob2)
        db.repack()

        # Reload
        db.reload_packs()

        # Both should be accessible
        assert db.exists(sha1)
        assert db.exists(sha2)

    def test_mixed_loose_and_packed(self, tmp_path: Path) -> None:
        """Read from both loose objects and packs."""
        objects_dir = tmp_path / "objects"
        objects_dir.mkdir()

        db = ObjectDatabase(objects_dir)

        # Create and pack first blob
        blob1 = Blob(data=b"packed")
        sha1 = db.write(blob1)
        db.repack()

        # Create loose blob
        blob2 = Blob(data=b"loose")
        sha2 = db.write(blob2)

        # Both should be readable
        obj1 = db.read(sha1)
        obj2 = db.read(sha2)

        assert obj1 is not None
        assert obj2 is not None
        assert isinstance(obj1, Blob)
        assert isinstance(obj2, Blob)
        assert obj1.data == b"packed"
        assert obj2.data == b"loose"

    def test_repack_with_deltification(self, tmp_path: Path) -> None:
        """Repack with delta compression."""
        objects_dir = tmp_path / "objects"
        objects_dir.mkdir()

        db = ObjectDatabase(objects_dir)

        # Create similar blobs
        blobs = [
            Blob(data=b"This is a test file with content number one."),
            Blob(data=b"This is a test file with content number two."),
            Blob(data=b"This is a test file with content number three."),
        ]
        shas = [db.write(blob) for blob in blobs]

        # Repack (deltification is on by default)
        pack_path, _ = db.repack()

        # Verify all objects readable
        for i, sha in enumerate(shas):
            obj = db.read(sha)
            assert obj is not None
            assert isinstance(obj, Blob)
            assert obj.data == blobs[i].data


class TestObjectDatabasePackWithDifferentTypes:
    """Tests for packing different object types."""

    def test_pack_tree(self, tmp_path: Path) -> None:
        """Pack and read tree objects."""
        objects_dir = tmp_path / "objects"
        objects_dir.mkdir()

        db = ObjectDatabase(objects_dir)

        tree = Tree(
            entries=[
                TreeEntry(mode="100644", name="file.txt", sha="a" * 40),
                TreeEntry(mode="040000", name="subdir", sha="b" * 40),
            ]
        )
        sha = db.write(tree)
        db.repack()

        db2 = ObjectDatabase(objects_dir)
        obj = db2.read(sha)

        assert obj is not None
        assert isinstance(obj, Tree)
        assert len(obj.entries) == 2

    def test_pack_commit(self, tmp_path: Path) -> None:
        """Pack and read commit objects."""
        objects_dir = tmp_path / "objects"
        objects_dir.mkdir()

        db = ObjectDatabase(objects_dir)

        author = Identity(
            name="Test Author",
            email="test@example.com",
            timestamp=1234567890,
            tz_offset="+0000",
        )
        committer = Identity(
            name="Test Committer",
            email="test@example.com",
            timestamp=1234567890,
            tz_offset="+0000",
        )
        commit = Commit(
            tree_sha="a" * 40,
            parent_shas=["b" * 40],
            author=author,
            committer=committer,
            message="Test commit message\n\nWith body.",
        )
        sha = db.write(commit)
        db.repack()

        db2 = ObjectDatabase(objects_dir)
        obj = db2.read(sha)

        assert obj is not None
        assert isinstance(obj, Commit)
        assert obj.tree_sha == "a" * 40
        assert obj.message == "Test commit message\n\nWith body."

    def test_pack_mixed_types(self, tmp_path: Path) -> None:
        """Pack mixed object types together."""
        objects_dir = tmp_path / "objects"
        objects_dir.mkdir()

        db = ObjectDatabase(objects_dir)

        blob = Blob(data=b"hello")
        tree = Tree(entries=[TreeEntry(mode="100644", name="hello.txt", sha="a" * 40)])
        author = Identity(name="A", email="a@a.com", timestamp=0, tz_offset="+0000")
        commit = Commit(
            tree_sha="b" * 40,
            parent_shas=[],
            author=author,
            committer=author,
            message="init",
        )

        blob_sha = db.write(blob)
        tree_sha = db.write(tree)
        commit_sha = db.write(commit)

        db.repack()

        db2 = ObjectDatabase(objects_dir)

        assert isinstance(db2.read(blob_sha), Blob)
        assert isinstance(db2.read(tree_sha), Tree)
        assert isinstance(db2.read(commit_sha), Commit)


class TestPackFileIntegrity:
    """Tests for pack file integrity."""

    def test_pack_checksum_valid(self, tmp_path: Path) -> None:
        """Pack files have valid checksums."""
        objects_dir = tmp_path / "objects"
        objects_dir.mkdir()

        db = ObjectDatabase(objects_dir)

        blob = Blob(data=b"checksum test")
        db.write(blob)
        pack_path, _ = db.repack()

        # Verify checksum
        data = pack_path.read_bytes()
        expected_sha = hashlib.sha1(data[:-20], usedforsecurity=False).digest()
        assert data[-20:] == expected_sha

    def test_index_matches_pack(self, tmp_path: Path) -> None:
        """Index file matches pack contents."""
        objects_dir = tmp_path / "objects"
        objects_dir.mkdir()

        db = ObjectDatabase(objects_dir)

        blobs = [Blob(data=f"blob {i}".encode()) for i in range(3)]
        shas = [db.write(blob) for blob in blobs]
        _, idx_path = db.repack()

        # Load pack to get index
        from gitpy.storage.pack import PackFile

        pack_path = idx_path.with_suffix(".pack")
        pack = PackFile(pack_path)

        # All SHAs should be in index
        for sha in shas:
            assert sha in pack.index


class TestPackFileEdgeCases:
    """Edge case tests for pack files."""

    def test_empty_database_repack(self, tmp_path: Path) -> None:
        """Repack empty database raises ValueError."""
        objects_dir = tmp_path / "objects"
        objects_dir.mkdir()

        db = ObjectDatabase(objects_dir)
        with pytest.raises(ValueError, match="No objects to pack"):
            db.repack()

    def test_large_number_of_objects(self, tmp_path: Path) -> None:
        """Pack many objects."""
        objects_dir = tmp_path / "objects"
        objects_dir.mkdir()

        db = ObjectDatabase(objects_dir)

        # Create 100 objects
        shas = []
        for i in range(100):
            blob = Blob(data=f"object number {i} with unique content".encode())
            shas.append(db.write(blob))

        db.repack()

        db2 = ObjectDatabase(objects_dir)

        # Verify all readable
        for i, sha in enumerate(shas):
            obj = db2.read(sha)
            assert obj is not None
            assert isinstance(obj, Blob)
            assert obj.data == f"object number {i} with unique content".encode()

    def test_unicode_content(self, tmp_path: Path) -> None:
        """Pack objects with unicode content."""
        objects_dir = tmp_path / "objects"
        objects_dir.mkdir()

        db = ObjectDatabase(objects_dir)

        content = "Hello 世界 🌍".encode()
        blob = Blob(data=content)
        sha = db.write(blob)
        db.repack()

        db2 = ObjectDatabase(objects_dir)
        obj = db2.read(sha)

        assert obj is not None
        assert isinstance(obj, Blob)
        assert obj.data == content

    def test_binary_content(self, tmp_path: Path) -> None:
        """Pack objects with binary content."""
        objects_dir = tmp_path / "objects"
        objects_dir.mkdir()

        db = ObjectDatabase(objects_dir)

        # All byte values
        content = bytes(range(256))
        blob = Blob(data=content)
        sha = db.write(blob)
        db.repack()

        db2 = ObjectDatabase(objects_dir)
        obj = db2.read(sha)

        assert obj is not None
        assert isinstance(obj, Blob)
        assert obj.data == content
