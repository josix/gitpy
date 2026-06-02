"""Tests for pack file module."""

import hashlib
import zlib
from pathlib import Path

import pytest

from gitpy.storage.pack import (
    PACK_SIGNATURE,
    PACK_VERSION,
    PackFile,
    PackObject,
    PackObjectType,
    read_ofs_delta_offset,
    read_pack_object_header,
    write_ofs_delta_offset,
    write_pack_object_header,
)
from gitpy.storage.pack_index import PackIndex, PackIndexEntry


class TestPackObjectType:
    """Tests for PackObjectType enum."""

    def test_to_object_type(self) -> None:
        """Convert to string type names."""
        assert PackObjectType.COMMIT.to_object_type() == "commit"
        assert PackObjectType.TREE.to_object_type() == "tree"
        assert PackObjectType.BLOB.to_object_type() == "blob"
        assert PackObjectType.TAG.to_object_type() == "tag"
        assert PackObjectType.OFS_DELTA.to_object_type() == "delta"
        assert PackObjectType.REF_DELTA.to_object_type() == "delta"

    def test_from_object_type(self) -> None:
        """Convert from string type names."""
        assert PackObjectType.from_object_type("commit") == PackObjectType.COMMIT
        assert PackObjectType.from_object_type("tree") == PackObjectType.TREE
        assert PackObjectType.from_object_type("blob") == PackObjectType.BLOB
        assert PackObjectType.from_object_type("tag") == PackObjectType.TAG

    def test_from_object_type_invalid(self) -> None:
        """Reject invalid type names."""
        with pytest.raises(KeyError):
            PackObjectType.from_object_type("invalid")

    def test_is_delta(self) -> None:
        """Check delta type detection."""
        assert not PackObjectType.COMMIT.is_delta
        assert not PackObjectType.TREE.is_delta
        assert not PackObjectType.BLOB.is_delta
        assert not PackObjectType.TAG.is_delta
        assert PackObjectType.OFS_DELTA.is_delta
        assert PackObjectType.REF_DELTA.is_delta


class TestPackObjectHeader:
    """Tests for pack object header encoding/decoding."""

    def test_read_small_object(self) -> None:
        """Read header for small object (size fits in 4 bits)."""
        # Type 3 (blob), size 10: 0011_1010 = 0x3a
        data = bytes([0x3A])
        obj_type, size, consumed = read_pack_object_header(data, 0)

        assert obj_type == 3
        assert size == 10
        assert consumed == 1

    def test_read_medium_object(self) -> None:
        """Read header with continuation byte."""
        # Type 1 (commit), size 150: first byte = 1_001_0110, second = 0_0001001
        # size = 6 + (9 << 4) = 6 + 144 = 150
        data = bytes([0x96, 0x09])
        obj_type, size, consumed = read_pack_object_header(data, 0)

        assert obj_type == 1
        assert size == 150
        assert consumed == 2

    def test_read_large_object(self) -> None:
        """Read header with multiple continuation bytes."""
        # Generate header for type 3 (blob), size 74565
        expected_size = 74565
        header = write_pack_object_header(3, expected_size)
        obj_type, size, consumed = read_pack_object_header(header, 0)

        assert obj_type == 3
        assert size == expected_size
        assert consumed == len(header)

    def test_write_small_object(self) -> None:
        """Write header for small object."""
        header = write_pack_object_header(3, 10)
        assert header == bytes([0x3A])

    def test_write_medium_object(self) -> None:
        """Write header with continuation."""
        header = write_pack_object_header(1, 150)
        assert header == bytes([0x96, 0x09])

    def test_roundtrip_various_sizes(self) -> None:
        """Roundtrip headers of various sizes."""
        test_cases = [
            (1, 0),
            (2, 15),
            (3, 16),
            (4, 127),
            (1, 128),
            (2, 1000),
            (3, 10000),
            (4, 100000),
            (1, 1000000),
        ]

        for obj_type, size in test_cases:
            header = write_pack_object_header(obj_type, size)
            read_type, read_size, _ = read_pack_object_header(header, 0)
            assert read_type == obj_type
            assert read_size == size


class TestOfsDeltaOffset:
    """Tests for OFS_DELTA offset encoding."""

    def test_read_small_offset(self) -> None:
        """Read small offset (single byte)."""
        data = bytes([0x7F])  # 127
        offset, consumed = read_ofs_delta_offset(data, 0)

        assert offset == 127
        assert consumed == 1

    def test_read_medium_offset(self) -> None:
        """Read medium offset (two bytes)."""
        # Generate encoding for offset 200
        expected_offset = 200
        encoded = write_ofs_delta_offset(expected_offset)
        offset, consumed = read_ofs_delta_offset(encoded, 0)

        assert offset == expected_offset
        assert consumed == len(encoded)

    def test_write_small_offset(self) -> None:
        """Write small offset."""
        encoded = write_ofs_delta_offset(127)
        assert encoded == bytes([0x7F])

    def test_roundtrip_offsets(self) -> None:
        """Roundtrip various offset values."""
        test_values = [1, 10, 100, 127, 128, 200, 1000, 10000, 100000, 1000000]

        for value in test_values:
            encoded = write_ofs_delta_offset(value)
            decoded, _ = read_ofs_delta_offset(encoded, 0)
            assert decoded == value, f"Failed for {value}"


class TestPackFile:
    """Tests for PackFile class."""

    def _create_test_pack(self, objects: list[tuple[str, bytes]]) -> bytes:
        """Create a minimal pack file for testing.

        Args:
            objects: List of (type_name, data) tuples.

        Returns:
            Pack file bytes.
        """
        result = bytearray()

        # Header
        result.extend(PACK_SIGNATURE)
        result.extend(PACK_VERSION.to_bytes(4, "big"))
        result.extend(len(objects).to_bytes(4, "big"))

        # Objects
        for type_name, data in objects:
            obj_type = PackObjectType.from_object_type(type_name)
            header = write_pack_object_header(obj_type, len(data))
            result.extend(header)
            result.extend(zlib.compress(data))

        # Trailer
        sha = hashlib.sha1(result, usedforsecurity=False).digest()
        result.extend(sha)

        return bytes(result)

    def _compute_sha(self, type_name: str, data: bytes) -> str:
        """Compute Git object SHA."""
        header = f"{type_name} {len(data)}\0".encode()
        return hashlib.sha1(header + data, usedforsecurity=False).hexdigest()

    def test_read_header(self, tmp_path: Path) -> None:
        """Read pack file header."""
        pack_data = self._create_test_pack([("blob", b"test")])
        pack_path = tmp_path / "test.pack"
        pack_path.write_bytes(pack_data)

        pack = PackFile(pack_path)

        assert pack.version == 2
        assert pack.object_count == 1

    def test_verify_checksum(self, tmp_path: Path) -> None:
        """Verify pack checksum."""
        pack_data = self._create_test_pack([("blob", b"hello")])
        pack_path = tmp_path / "test.pack"
        pack_path.write_bytes(pack_data)

        pack = PackFile(pack_path)
        assert pack.verify_checksum() is True

    def test_verify_checksum_corrupted(self, tmp_path: Path) -> None:
        """Detect corrupted pack via checksum."""
        pack_data = bytearray(self._create_test_pack([("blob", b"hello")]))
        # Corrupt only the trailer SHA (last 20 bytes) so pack parses but
        # checksum verification fails
        pack_data[-1] ^= 0xFF
        pack_path = tmp_path / "test.pack"
        pack_path.write_bytes(bytes(pack_data))

        pack = PackFile(pack_path)
        assert pack.verify_checksum() is False

    def test_read_single_blob(self, tmp_path: Path) -> None:
        """Read single blob from pack."""
        data = b"hello world"
        pack_data = self._create_test_pack([("blob", data)])
        pack_path = tmp_path / "test.pack"
        pack_path.write_bytes(pack_data)

        pack = PackFile(pack_path)
        sha = self._compute_sha("blob", data)

        obj = pack.read_object(sha)
        assert obj is not None
        assert obj.type_name == "blob"
        assert obj.data == data

    def test_read_multiple_objects(self, tmp_path: Path) -> None:
        """Read multiple objects from pack."""
        objects = [
            ("blob", b"file1 content"),
            ("blob", b"file2 content"),
            ("blob", b"file3 content"),
        ]
        pack_data = self._create_test_pack(objects)
        pack_path = tmp_path / "test.pack"
        pack_path.write_bytes(pack_data)

        pack = PackFile(pack_path)

        for type_name, data in objects:
            sha = self._compute_sha(type_name, data)
            obj = pack.read_object(sha)
            assert obj is not None
            assert obj.data == data

    def test_read_nonexistent(self, tmp_path: Path) -> None:
        """Reading nonexistent object returns None."""
        pack_data = self._create_test_pack([("blob", b"test")])
        pack_path = tmp_path / "test.pack"
        pack_path.write_bytes(pack_data)

        pack = PackFile(pack_path)

        assert pack.read_object("a" * 40) is None

    def test_contains(self, tmp_path: Path) -> None:
        """Test __contains__ method."""
        data = b"test content"
        pack_data = self._create_test_pack([("blob", data)])
        pack_path = tmp_path / "test.pack"
        pack_path.write_bytes(pack_data)

        pack = PackFile(pack_path)
        sha = self._compute_sha("blob", data)

        assert sha in pack
        assert "x" * 40 not in pack

    def test_len(self, tmp_path: Path) -> None:
        """Test __len__ method."""
        objects = [("blob", b"a"), ("blob", b"b"), ("blob", b"c")]
        pack_data = self._create_test_pack(objects)
        pack_path = tmp_path / "test.pack"
        pack_path.write_bytes(pack_data)

        pack = PackFile(pack_path)
        assert len(pack) == 3

    def test_iter(self, tmp_path: Path) -> None:
        """Test iteration over pack objects."""
        objects = [("blob", b"one"), ("blob", b"two")]
        pack_data = self._create_test_pack(objects)
        pack_path = tmp_path / "test.pack"
        pack_path.write_bytes(pack_data)

        pack = PackFile(pack_path)
        pack_objects = list(pack)

        assert len(pack_objects) == 2
        assert all(isinstance(obj, PackObject) for obj in pack_objects)

    def test_load_with_index(self, tmp_path: Path) -> None:
        """Load pack with preexisting index."""
        data = b"indexed content"
        sha = self._compute_sha("blob", data)

        pack_data = self._create_test_pack([("blob", data)])
        pack_path = tmp_path / "test.pack"
        pack_path.write_bytes(pack_data)

        # Create index
        entries = [PackIndexEntry(sha=sha, offset=12, crc32=0)]
        pack_sha = pack_data[-20:].hex()
        index = PackIndex(pack_sha=pack_sha, entries=entries)
        idx_path = pack_path.with_suffix(".idx")
        index.write(idx_path)

        # Load with index
        pack = PackFile(pack_path)
        obj = pack.read_object(sha)
        assert obj is not None
        assert obj.data == data

    def test_invalid_signature(self, tmp_path: Path) -> None:
        """Reject invalid pack signature."""
        pack_path = tmp_path / "test.pack"
        pack_path.write_bytes(b"XXXX" + b"\x00" * 100)

        with pytest.raises(ValueError, match="Invalid pack signature"):
            PackFile(pack_path)

    def test_unsupported_version(self, tmp_path: Path) -> None:
        """Reject unsupported pack version."""
        data = PACK_SIGNATURE + (99).to_bytes(4, "big") + b"\x00" * 100
        pack_path = tmp_path / "test.pack"
        pack_path.write_bytes(data)

        with pytest.raises(ValueError, match="Unsupported pack version"):
            PackFile(pack_path)

    def test_cache(self, tmp_path: Path) -> None:
        """Test object caching."""
        data = b"cached content"
        pack_data = self._create_test_pack([("blob", data)])
        pack_path = tmp_path / "test.pack"
        pack_path.write_bytes(pack_data)

        pack = PackFile(pack_path)
        sha = self._compute_sha("blob", data)

        # Read twice
        obj1 = pack.read_object(sha)
        obj2 = pack.read_object(sha)

        assert obj1 is not None
        assert obj2 is not None
        assert obj1.data == obj2.data

    def test_clear_cache(self, tmp_path: Path) -> None:
        """Test cache clearing."""
        data = b"test"
        pack_data = self._create_test_pack([("blob", data)])
        pack_path = tmp_path / "test.pack"
        pack_path.write_bytes(pack_data)

        pack = PackFile(pack_path)
        sha = self._compute_sha("blob", data)

        # Fill cache
        pack.read_object(sha)
        assert len(pack._cache) > 0

        # Clear
        pack.clear_cache()
        assert len(pack._cache) == 0


class TestPackFileWithIndex:
    """Tests for PackFile with external index."""

    def test_builds_index_when_missing(self, tmp_path: Path) -> None:
        """Build index when .idx file is missing."""
        data = b"no index file"
        sha = hashlib.sha1(
            f"blob {len(data)}\0".encode() + data, usedforsecurity=False
        ).hexdigest()

        # Create pack without index
        result = bytearray()
        result.extend(PACK_SIGNATURE)
        result.extend(PACK_VERSION.to_bytes(4, "big"))
        result.extend((1).to_bytes(4, "big"))  # 1 object

        header = write_pack_object_header(PackObjectType.BLOB, len(data))
        result.extend(header)
        result.extend(zlib.compress(data))

        trailer = hashlib.sha1(result, usedforsecurity=False).digest()
        result.extend(trailer)

        pack_path = tmp_path / "test.pack"
        pack_path.write_bytes(bytes(result))

        # No .idx file
        idx_path = pack_path.with_suffix(".idx")
        assert not idx_path.exists()

        # Should build index
        pack = PackFile(pack_path)
        assert sha in pack
        obj = pack.read_object(sha)
        assert obj is not None
        assert obj.data == data
