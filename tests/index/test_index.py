"""Tests for Index and IndexFile serialisation."""

import struct
from pathlib import Path

import pytest

from gitpy.index.entry import IndexEntry
from gitpy.index.index import (
    INDEX_SIGNATURE,
    INDEX_VERSION,
    Index,
    IndexFile,
    _entry_padding,
    _serialize_entry,
)

FAKE_SHA = "a" * 40


def _make_entry(path: str, stage: int = 0) -> IndexEntry:
    name_len = min(len(path), 0xFFF)
    return IndexEntry(
        ctime_s=1234567890,
        ctime_ns=123456789,
        mtime_s=1234567890,
        mtime_ns=123456789,
        dev=16777220,
        ino=12345678,
        mode=0o100644,
        uid=501,
        gid=20,
        size=1234,
        sha=FAKE_SHA,
        flags=(stage << 12) | name_len,
        path=path,
    )


class TestEmptyIndex:
    def test_header_signature(self) -> None:
        data = Index().to_bytes()
        assert data[:4] == INDEX_SIGNATURE

    def test_header_version(self) -> None:
        data = Index().to_bytes()
        (version,) = struct.unpack(">I", data[4:8])
        assert version == INDEX_VERSION

    def test_header_count_zero(self) -> None:
        data = Index().to_bytes()
        (count,) = struct.unpack(">I", data[8:12])
        assert count == 0

    def test_total_length(self) -> None:
        # header 12 + checksum 20
        data = Index().to_bytes()
        assert len(data) == 32


class TestRoundtrip:
    def test_single_entry_roundtrip(self) -> None:
        idx = Index()
        idx.add(_make_entry("test.txt"))

        restored = Index.from_bytes(idx.to_bytes())

        assert len(restored) == 1
        assert "test.txt" in restored
        e = restored.get("test.txt")
        assert e is not None
        assert e.sha == FAKE_SHA
        assert e.mode == 0o100644
        assert e.path == "test.txt"

    def test_multiple_entries_roundtrip(self) -> None:
        idx = Index()
        for path in ["c.txt", "a.txt", "b.txt"]:
            idx.add(_make_entry(path))

        restored = Index.from_bytes(idx.to_bytes())
        assert len(restored) == 3
        assert "a.txt" in restored
        assert "b.txt" in restored
        assert "c.txt" in restored

    def test_all_fields_preserved(self) -> None:
        entry = IndexEntry(
            ctime_s=11,
            ctime_ns=22,
            mtime_s=33,
            mtime_ns=44,
            dev=55,
            ino=66,
            mode=0o100755,
            uid=77,
            gid=88,
            size=99,
            sha="b" * 40,
            flags=7,
            path="exec.sh",
        )
        idx = Index()
        idx.add(entry)
        restored = Index.from_bytes(idx.to_bytes())
        e = restored.get("exec.sh")
        assert e is not None
        assert e.ctime_s == 11
        assert e.ctime_ns == 22
        assert e.mtime_s == 33
        assert e.mtime_ns == 44
        assert e.mode == 0o100755
        assert e.uid == 77
        assert e.gid == 88
        assert e.size == 99
        assert e.sha == "b" * 40


class TestChecksum:
    def test_corrupt_checksum_raises(self) -> None:
        idx = Index()
        idx.add(_make_entry("file.txt"))
        data = bytearray(idx.to_bytes())
        data[-1] ^= 0xFF  # flip last byte of checksum
        with pytest.raises(ValueError, match="checksum"):
            Index.from_bytes(bytes(data))

    def test_corrupt_body_raises(self) -> None:
        idx = Index()
        idx.add(_make_entry("file.txt"))
        data = bytearray(idx.to_bytes())
        # corrupt a byte in the header region
        data[3] ^= 0x01
        with pytest.raises(ValueError):
            Index.from_bytes(bytes(data))


class TestSorting:
    def test_iteration_sorted(self) -> None:
        idx = Index()
        for path in ["z.txt", "a.txt", "m.txt"]:
            idx.add(_make_entry(path))
        paths = [e.path for e in idx]
        assert paths == sorted(paths)

    def test_serialised_sorted(self) -> None:
        idx = Index()
        for path in ["z.txt", "a.txt", "m.txt"]:
            idx.add(_make_entry(path))
        restored = Index.from_bytes(idx.to_bytes())
        paths = [e.path for e in restored]
        assert paths == sorted(paths)


class TestPaddingRoundtrip:
    """Verify that every path length 1..20 produces entries aligned to 8 bytes."""

    @pytest.mark.parametrize("name_len", range(1, 21))
    def test_entry_byte_length_multiple_of_8(self, name_len: int) -> None:
        path = "x" * name_len
        entry = _make_entry(path)
        serialised = _serialize_entry(entry)
        assert len(serialised) % 8 == 0, (
            f"Entry for path length {name_len} has length {len(serialised)}, "
            f"not a multiple of 8"
        )

    @pytest.mark.parametrize("name_len", range(1, 21))
    def test_roundtrip_for_path_length(self, name_len: int) -> None:
        path = "a" * name_len
        idx = Index()
        idx.add(_make_entry(path))
        restored = Index.from_bytes(idx.to_bytes())
        assert path in restored
        assert restored.get(path).sha == FAKE_SHA  # type: ignore[union-attr]

    def test_padding_range(self) -> None:
        """Padding is 0–7 extra bytes; entry total is always a multiple of 8.

        When the fixed header (62 bytes) plus the NUL-terminated path already
        aligns to 8 bytes, no extra padding is written (0 extra bytes).
        This matches real Git behaviour.
        """
        for name_len in range(1, 21):
            path_bytes_nul = ("a" * name_len).encode() + b"\x00"
            p = _entry_padding(path_bytes_nul)
            total = 62 + len(path_bytes_nul) + p
            assert 0 <= p <= 7, f"padding={p} for path length {name_len}"
            assert total % 8 == 0, (
                f"total={total} not multiple of 8 for path len {name_len}"
            )


class TestIndexFile:
    def test_read_nonexistent_returns_empty(self, tmp_path: Path) -> None:
        git_dir = tmp_path / ".git"
        git_dir.mkdir()
        idx_file = IndexFile(git_dir)
        idx = idx_file.read()
        assert len(idx) == 0

    def test_write_and_read(self, tmp_path: Path) -> None:
        git_dir = tmp_path / ".git"
        git_dir.mkdir()
        idx_file = IndexFile(git_dir)

        idx = Index()
        idx.add(_make_entry("hello.txt"))
        idx_file.write(idx)

        loaded = idx_file.read()
        assert "hello.txt" in loaded

    def test_lock_file_cleaned_up(self, tmp_path: Path) -> None:
        git_dir = tmp_path / ".git"
        git_dir.mkdir()
        idx_file = IndexFile(git_dir)
        idx = Index()
        idx_file.write(idx)
        assert not idx_file.lock_path.exists()

    def test_exists(self, tmp_path: Path) -> None:
        git_dir = tmp_path / ".git"
        git_dir.mkdir()
        idx_file = IndexFile(git_dir)
        assert idx_file.exists() is False
        idx_file.write(Index())
        assert idx_file.exists() is True
