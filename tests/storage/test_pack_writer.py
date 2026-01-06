"""Tests for pack file writer module."""

import hashlib
from pathlib import Path

from gitpy.objects import Blob, Commit, Identity, Tree, TreeEntry
from gitpy.storage.pack import PACK_SIGNATURE, PACK_VERSION, PackFile
from gitpy.storage.pack_writer import PackEntry, PackWriter


class TestPackEntry:
    """Tests for PackEntry dataclass."""

    def test_create_entry(self) -> None:
        """Create a pack entry."""
        entry = PackEntry(
            sha="a" * 40, type_name="blob", data=b"content", delta_base_sha=None
        )

        assert entry.sha == "a" * 40
        assert entry.type_name == "blob"
        assert entry.data == b"content"
        assert entry.delta_base_sha is None

    def test_create_delta_entry(self) -> None:
        """Create a delta pack entry."""
        entry = PackEntry(
            sha="a" * 40, type_name="blob", data=b"delta", delta_base_sha="b" * 40
        )

        assert entry.delta_base_sha == "b" * 40


class TestPackWriter:
    """Tests for PackWriter class."""

    def test_write_single_blob(self, tmp_path: Path) -> None:
        """Write single blob to pack."""
        objects_dir = tmp_path / "objects"
        objects_dir.mkdir()

        writer = PackWriter(objects_dir)
        blob = Blob(data=b"hello world")

        pack_path, idx_path = writer.write_pack([blob], deltify=False)

        assert pack_path.exists()
        assert idx_path.exists()
        assert pack_path.suffix == ".pack"
        assert idx_path.suffix == ".idx"

        # Verify we can read it back
        pack = PackFile(pack_path)
        assert len(pack) == 1

    def test_write_multiple_blobs(self, tmp_path: Path) -> None:
        """Write multiple blobs to pack."""
        objects_dir = tmp_path / "objects"
        objects_dir.mkdir()

        writer = PackWriter(objects_dir)
        blobs = [
            Blob(data=b"file 1 content"),
            Blob(data=b"file 2 content"),
            Blob(data=b"file 3 content"),
        ]

        pack_path, idx_path = writer.write_pack(blobs, deltify=False)

        pack = PackFile(pack_path)
        assert len(pack) == 3

        # Verify all objects can be read
        for blob in blobs:
            header = f"blob {len(blob.data)}\0".encode()
            sha = hashlib.sha1(header + blob.data, usedforsecurity=False).hexdigest()
            obj = pack.read_object(sha)
            assert obj is not None
            assert obj.data == blob.data

    def test_write_different_types(self, tmp_path: Path) -> None:
        """Write different object types to pack."""
        objects_dir = tmp_path / "objects"
        objects_dir.mkdir()

        writer = PackWriter(objects_dir)

        blob = Blob(data=b"file content")
        tree = Tree(
            entries=[
                TreeEntry(mode="100644", name="file.txt", sha="a" * 40),
            ]
        )
        author = Identity(
            name="Test", email="test@test.com", timestamp=1234567890, tz_offset="+0000"
        )
        commit = Commit(
            tree_sha="b" * 40,
            parent_shas=[],
            author=author,
            committer=author,
            message="Test commit",
        )

        pack_path, idx_path = writer.write_pack([blob, tree, commit], deltify=False)

        pack = PackFile(pack_path)
        assert len(pack) == 3

    def test_pack_file_structure(self, tmp_path: Path) -> None:
        """Verify pack file has correct structure."""
        objects_dir = tmp_path / "objects"
        objects_dir.mkdir()

        writer = PackWriter(objects_dir)
        blob = Blob(data=b"test")

        pack_path, _ = writer.write_pack([blob], deltify=False)

        data = pack_path.read_bytes()

        # Check header
        assert data[:4] == PACK_SIGNATURE
        version = int.from_bytes(data[4:8], "big")
        assert version == PACK_VERSION
        object_count = int.from_bytes(data[8:12], "big")
        assert object_count == 1

        # Check trailer
        expected_sha = hashlib.sha1(data[:-20], usedforsecurity=False).digest()
        assert data[-20:] == expected_sha

    def test_pack_naming(self, tmp_path: Path) -> None:
        """Pack files are named by their SHA."""
        objects_dir = tmp_path / "objects"
        objects_dir.mkdir()

        writer = PackWriter(objects_dir)
        blob = Blob(data=b"unique content")

        pack_path, idx_path = writer.write_pack([blob], deltify=False)

        # Names should match
        pack_sha = pack_path.stem.replace("pack-", "")
        idx_sha = idx_path.stem.replace("pack-", "")
        assert pack_sha == idx_sha
        assert len(pack_sha) == 40

    def test_pack_directory_creation(self, tmp_path: Path) -> None:
        """Pack directory is created if missing."""
        objects_dir = tmp_path / "objects"
        # Don't create it - writer should handle this

        writer = PackWriter(objects_dir)
        blob = Blob(data=b"test")

        pack_path, _ = writer.write_pack([blob], deltify=False)

        assert (objects_dir / "pack").exists()
        assert pack_path.parent == objects_dir / "pack"


class TestPackWriterDeltification:
    """Tests for delta compression in PackWriter."""

    def test_deltify_similar_blobs(self, tmp_path: Path) -> None:
        """Similar blobs should be deltified."""
        objects_dir = tmp_path / "objects"
        objects_dir.mkdir()

        writer = PackWriter(objects_dir)

        # Create similar content
        base_content = b"This is a base file with some content that is repeated."
        similar_content = (
            b"This is a similar file with some content that is repeated."
        )

        blobs = [
            Blob(data=base_content),
            Blob(data=similar_content),
        ]

        # Write with deltification
        pack_with_delta, _ = writer.write_pack(blobs, deltify=True)

        # Write without deltification
        pack_without_delta, _ = writer.write_pack(blobs, deltify=False)

        # Delta pack should be smaller (or same if delta not beneficial)
        delta_size = pack_with_delta.stat().st_size
        nodelta_size = pack_without_delta.stat().st_size
        assert delta_size <= nodelta_size

    def test_deltify_preserves_content(self, tmp_path: Path) -> None:
        """Deltified pack should produce correct content."""
        objects_dir = tmp_path / "objects"
        objects_dir.mkdir()

        writer = PackWriter(objects_dir)

        contents = [
            b"First file with some base content here.",
            b"Second file with some base content here and more.",
            b"Third file with some base content here and even more.",
        ]
        blobs = [Blob(data=c) for c in contents]

        pack_path, _ = writer.write_pack(blobs, deltify=True)
        pack = PackFile(pack_path)

        # Verify all content is correct
        for content in contents:
            header = f"blob {len(content)}\0".encode()
            sha = hashlib.sha1(header + content, usedforsecurity=False).hexdigest()
            obj = pack.read_object(sha)
            assert obj is not None
            assert obj.data == content

    def test_window_size(self, tmp_path: Path) -> None:
        """Window size limits delta base candidates."""
        objects_dir = tmp_path / "objects"
        objects_dir.mkdir()

        writer = PackWriter(objects_dir)

        # Create many similar blobs
        blobs = [Blob(data=f"content version {i}".encode()) for i in range(20)]

        # Should work with different window sizes
        for window_size in [1, 5, 10]:
            pack_path, _ = writer.write_pack(
                blobs, deltify=True, window_size=window_size
            )
            pack = PackFile(pack_path)
            assert len(pack) == 20

    def test_no_deltify_different_types(self, tmp_path: Path) -> None:
        """Don't deltify across different object types."""
        objects_dir = tmp_path / "objects"
        objects_dir.mkdir()

        writer = PackWriter(objects_dir)

        blob = Blob(data=b"same content pattern")
        # Tree has similar raw bytes but different type
        tree = Tree(entries=[TreeEntry(mode="100644", name="file", sha="a" * 40)])

        pack_path, _ = writer.write_pack([blob, tree], deltify=True)
        pack = PackFile(pack_path)

        # Both should be readable
        for obj in pack:
            assert obj.data is not None


class TestPackWriterRoundtrip:
    """Roundtrip tests for PackWriter."""

    def test_roundtrip_empty_blob(self, tmp_path: Path) -> None:
        """Roundtrip empty blob."""
        objects_dir = tmp_path / "objects"
        objects_dir.mkdir()

        writer = PackWriter(objects_dir)
        blob = Blob(data=b"")

        pack_path, _ = writer.write_pack([blob], deltify=False)
        pack = PackFile(pack_path)

        # Empty blob SHA
        sha = "e69de29bb2d1d6434b8b29ae775ad8c2e48c5391"
        obj = pack.read_object(sha)
        assert obj is not None
        assert obj.data == b""

    def test_roundtrip_large_blob(self, tmp_path: Path) -> None:
        """Roundtrip large blob."""
        objects_dir = tmp_path / "objects"
        objects_dir.mkdir()

        writer = PackWriter(objects_dir)
        content = b"x" * 100000
        blob = Blob(data=content)

        pack_path, _ = writer.write_pack([blob], deltify=False)
        pack = PackFile(pack_path)

        header = f"blob {len(content)}\0".encode()
        sha = hashlib.sha1(header + content, usedforsecurity=False).hexdigest()
        obj = pack.read_object(sha)
        assert obj is not None
        assert obj.data == content

    def test_roundtrip_binary_content(self, tmp_path: Path) -> None:
        """Roundtrip binary content."""
        objects_dir = tmp_path / "objects"
        objects_dir.mkdir()

        writer = PackWriter(objects_dir)
        content = bytes(range(256)) * 10
        blob = Blob(data=content)

        pack_path, _ = writer.write_pack([blob], deltify=False)
        pack = PackFile(pack_path)

        header = f"blob {len(content)}\0".encode()
        sha = hashlib.sha1(header + content, usedforsecurity=False).hexdigest()
        obj = pack.read_object(sha)
        assert obj is not None
        assert obj.data == content

    def test_roundtrip_with_index(self, tmp_path: Path) -> None:
        """Verify index is correct for roundtrip."""
        objects_dir = tmp_path / "objects"
        objects_dir.mkdir()

        writer = PackWriter(objects_dir)
        blobs = [Blob(data=f"blob {i}".encode()) for i in range(5)]

        pack_path, idx_path = writer.write_pack(blobs, deltify=False)

        # Load pack using index
        pack = PackFile(pack_path)

        # Verify index contains all objects
        assert len(pack.index) == 5

        # Verify all objects readable
        for obj in pack:
            assert obj.data is not None
