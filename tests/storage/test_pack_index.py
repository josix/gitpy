"""Tests for pack index module."""

from pathlib import Path

import pytest

from gitpy.storage.pack_index import (
    IDX_SIGNATURE,
    IDX_VERSION,
    PackIndex,
    PackIndexEntry,
)


class TestPackIndexEntry:
    """Tests for PackIndexEntry."""

    def test_create_entry(self) -> None:
        """Create a pack index entry."""
        entry = PackIndexEntry(sha="a" * 40, offset=100, crc32=0x12345678)

        assert entry.sha == "a" * 40
        assert entry.offset == 100
        assert entry.crc32 == 0x12345678


class TestPackIndex:
    """Tests for PackIndex."""

    def test_create_empty(self) -> None:
        """Create empty index."""
        index = PackIndex(pack_sha="b" * 40, entries=[])

        assert index.object_count == 0
        assert index.pack_sha == "b" * 40

    def test_create_with_entries(self) -> None:
        """Create index with entries."""
        entries = [
            PackIndexEntry(sha="a" * 40, offset=100, crc32=0x12345678),
            PackIndexEntry(sha="b" * 40, offset=200, crc32=0xdeadbeef),
            PackIndexEntry(sha="c" * 40, offset=300, crc32=0xcafebabe),
        ]

        index = PackIndex(pack_sha="d" * 40, entries=entries)

        assert index.object_count == 3
        assert len(index) == 3

    def test_entries_sorted(self) -> None:
        """Entries are sorted by SHA."""
        entries = [
            PackIndexEntry(sha="c" * 40, offset=300, crc32=0),
            PackIndexEntry(sha="a" * 40, offset=100, crc32=0),
            PackIndexEntry(sha="b" * 40, offset=200, crc32=0),
        ]

        index = PackIndex(pack_sha="d" * 40, entries=entries)

        assert index.entries[0].sha == "a" * 40
        assert index.entries[1].sha == "b" * 40
        assert index.entries[2].sha == "c" * 40

    def test_find_existing(self) -> None:
        """Find existing entry."""
        entries = [
            PackIndexEntry(sha="a" * 40, offset=100, crc32=0x12345678),
            PackIndexEntry(sha="b" * 40, offset=200, crc32=0xdeadbeef),
        ]

        index = PackIndex(pack_sha="c" * 40, entries=entries)

        entry = index.find("a" * 40)
        assert entry is not None
        assert entry.offset == 100
        assert entry.crc32 == 0x12345678

    def test_find_missing(self) -> None:
        """Find returns None for missing entry."""
        entries = [
            PackIndexEntry(sha="a" * 40, offset=100, crc32=0),
        ]

        index = PackIndex(pack_sha="b" * 40, entries=entries)

        assert index.find("x" * 40) is None

    def test_get_offset(self) -> None:
        """Get offset for SHA."""
        entries = [
            PackIndexEntry(sha="a" * 40, offset=12345, crc32=0),
        ]

        index = PackIndex(pack_sha="b" * 40, entries=entries)

        assert index.get_offset("a" * 40) == 12345
        assert index.get_offset("x" * 40) is None

    def test_get_crc32(self) -> None:
        """Get CRC32 for SHA."""
        entries = [
            PackIndexEntry(sha="a" * 40, offset=100, crc32=0xdeadbeef),
        ]

        index = PackIndex(pack_sha="b" * 40, entries=entries)

        assert index.get_crc32("a" * 40) == 0xdeadbeef
        assert index.get_crc32("x" * 40) is None

    def test_contains(self) -> None:
        """Test __contains__."""
        entries = [
            PackIndexEntry(sha="a" * 40, offset=100, crc32=0),
            PackIndexEntry(sha="b" * 40, offset=200, crc32=0),
        ]

        index = PackIndex(pack_sha="c" * 40, entries=entries)

        assert "a" * 40 in index
        assert "b" * 40 in index
        assert "x" * 40 not in index

    def test_iter(self) -> None:
        """Test iteration over entries."""
        entries = [
            PackIndexEntry(sha="a" * 40, offset=100, crc32=0),
            PackIndexEntry(sha="b" * 40, offset=200, crc32=0),
        ]

        index = PackIndex(pack_sha="c" * 40, entries=entries)

        shas = [e.sha for e in index]
        assert shas == ["a" * 40, "b" * 40]


class TestPackIndexFanout:
    """Tests for fanout table."""

    def test_fanout_single_bucket(self) -> None:
        """Fanout with entries in single bucket."""
        entries = [
            PackIndexEntry(sha="00" + "a" * 38, offset=100, crc32=0),
            PackIndexEntry(sha="00" + "b" * 38, offset=200, crc32=0),
        ]

        index = PackIndex(pack_sha="c" * 40, entries=entries)

        # Both objects have first byte 0x00
        assert index._fanout[0x00] == 2
        assert index._fanout[0xff] == 2

    def test_fanout_distribution(self) -> None:
        """Fanout with distributed entries."""
        entries = [
            PackIndexEntry(sha="00" + "a" * 38, offset=100, crc32=0),
            PackIndexEntry(sha="80" + "b" * 38, offset=200, crc32=0),
            PackIndexEntry(sha="ff" + "c" * 38, offset=300, crc32=0),
        ]

        index = PackIndex(pack_sha="d" * 40, entries=entries)

        # Cumulative counts
        assert index._fanout[0x00] == 1  # 1 object <= 0x00
        assert index._fanout[0x7f] == 1  # still 1 (none in 01-7f)
        assert index._fanout[0x80] == 2  # 2 objects <= 0x80
        assert index._fanout[0xfe] == 2  # still 2
        assert index._fanout[0xff] == 3  # 3 total


class TestPackIndexSerialization:
    """Tests for index serialization."""

    def test_serialize_header(self) -> None:
        """Serialized index has correct header."""
        index = PackIndex(pack_sha="a" * 40, entries=[])
        data = index.serialize()

        assert data[:4] == IDX_SIGNATURE
        assert int.from_bytes(data[4:8], "big") == IDX_VERSION

    def test_roundtrip_empty(self) -> None:
        """Roundtrip empty index."""
        index = PackIndex(pack_sha="a" * 40, entries=[])
        data = index.serialize()
        restored = PackIndex.parse(data)

        assert restored.object_count == 0
        assert restored.pack_sha == "a" * 40

    def test_roundtrip_with_entries(self) -> None:
        """Roundtrip index with entries."""
        entries = [
            PackIndexEntry(sha="a" * 40, offset=100, crc32=0x12345678),
            PackIndexEntry(sha="b" * 40, offset=500, crc32=0xdeadbeef),
            PackIndexEntry(sha="f" * 40, offset=1000, crc32=0xcafebabe),
        ]

        index = PackIndex(pack_sha="c" * 40, entries=entries)
        data = index.serialize()
        restored = PackIndex.parse(data)

        assert restored.object_count == 3
        assert restored.get_offset("a" * 40) == 100
        assert restored.get_offset("b" * 40) == 500
        assert restored.get_offset("f" * 40) == 1000
        assert restored.get_crc32("a" * 40) == 0x12345678
        assert restored.get_crc32("b" * 40) == 0xdeadbeef

    def test_roundtrip_large_offset(self) -> None:
        """Roundtrip index with large offsets (>2GB)."""
        large_offset = 0x100000000  # 4GB

        entries = [
            PackIndexEntry(sha="a" * 40, offset=large_offset, crc32=0),
        ]

        index = PackIndex(pack_sha="b" * 40, entries=entries)
        data = index.serialize()
        restored = PackIndex.parse(data)

        assert restored.get_offset("a" * 40) == large_offset

    def test_parse_invalid_signature(self) -> None:
        """Reject invalid signature."""
        data = b"XXXX" + b"\x00" * 100

        with pytest.raises(ValueError, match="Invalid pack index signature"):
            PackIndex.parse(data)

    def test_parse_invalid_version(self) -> None:
        """Reject unsupported version."""
        data = IDX_SIGNATURE + (99).to_bytes(4, "big") + b"\x00" * 100

        with pytest.raises(ValueError, match="Unsupported index version"):
            PackIndex.parse(data)


class TestPackIndexFile:
    """Tests for file I/O."""

    def test_write_and_read(self, tmp_path: Path) -> None:
        """Write and read index file."""
        entries = [
            PackIndexEntry(sha="a" * 40, offset=100, crc32=0x12345678),
            PackIndexEntry(sha="b" * 40, offset=200, crc32=0xdeadbeef),
        ]

        index = PackIndex(pack_sha="c" * 40, entries=entries)

        idx_path = tmp_path / "test.idx"
        index.write(idx_path)

        restored = PackIndex.from_file(idx_path)

        assert restored.object_count == 2
        assert restored.get_offset("a" * 40) == 100
        assert restored.get_offset("b" * 40) == 200
