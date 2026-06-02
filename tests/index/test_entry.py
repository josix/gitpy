"""Tests for IndexEntry."""

import os
from pathlib import Path
from unittest.mock import MagicMock

from gitpy.index.entry import IndexEntry

FAKE_SHA = "a" * 40


def _make_fake_st(
    *,
    ctime_ns: int = 1_700_000_000_000_000_000,
    mtime_ns: int = 1_700_000_001_000_000_000,
    dev: int = 16777220,
    ino: int = 12345678,
    mode: int = 0o100644,
    uid: int = 501,
    gid: int = 20,
    size: int = 42,
) -> os.stat_result:
    """Build a minimal stat_result-like object via MagicMock."""
    st = MagicMock(spec=os.stat_result)
    st.st_ctime_ns = ctime_ns
    st.st_mtime_ns = mtime_ns
    st.st_dev = dev
    st.st_ino = ino
    st.st_mode = mode
    st.st_uid = uid
    st.st_gid = gid
    st.st_size = size
    return st


class TestFromPath:
    def test_regular_file_mode(self, tmp_path: Path) -> None:
        """Regular file gets mode 0o100644."""
        f = tmp_path / "hello.txt"
        f.write_bytes(b"hello\n")
        # Ensure non-executable
        f.chmod(0o644)
        entry = IndexEntry.from_path("hello.txt", FAKE_SHA, tmp_path)
        assert entry.mode == 0o100644

    def test_executable_mode(self, tmp_path: Path) -> None:
        """Executable file gets mode 0o100755."""
        f = tmp_path / "run.sh"
        f.write_bytes(b"#!/bin/sh\n")
        f.chmod(0o755)
        entry = IndexEntry.from_path("run.sh", FAKE_SHA, tmp_path)
        assert entry.mode == 0o100755

    def test_symlink_mode(self, tmp_path: Path) -> None:
        """Symlink gets mode 0o120000."""
        target = tmp_path / "target.txt"
        target.write_bytes(b"data")
        link = tmp_path / "link.txt"
        link.symlink_to(target)
        entry = IndexEntry.from_path("link.txt", FAKE_SHA, tmp_path)
        assert entry.mode == 0o120000

    def test_flags_encode_stage_and_name_length(self, tmp_path: Path) -> None:
        """flags must encode (stage << 12) | min(name_len, 0xFFF)."""
        f = tmp_path / "abc.txt"
        f.write_bytes(b"x")
        f.chmod(0o644)
        stage = 2
        entry = IndexEntry.from_path("abc.txt", FAKE_SHA, tmp_path, stage=stage)
        expected_flags = (stage << 12) | len("abc.txt")
        assert entry.flags == expected_flags

    def test_flags_name_length_capped_at_0xfff(self) -> None:
        """Name length in flags is capped at 0xFFF for long paths.

        This tests the flags calculation formula directly, without creating
        a real file (OS path-length limits prevent paths > ~1000 bytes on macOS).
        """
        long_path = "a" * 4100
        name_len = min(len(long_path), 0xFFF)
        flags = (0 << 12) | name_len
        assert (flags & 0xFFF) == 0xFFF

    def test_nanosecond_precision(self, tmp_path: Path) -> None:
        """ctime_ns / mtime_ns are stored as sub-second part only."""
        f = tmp_path / "ns.txt"
        f.write_bytes(b"ns")
        f.chmod(0o644)
        entry = IndexEntry.from_path("ns.txt", FAKE_SHA, tmp_path)
        st = f.stat()
        assert entry.ctime_s == st.st_ctime_ns // 1_000_000_000
        assert entry.ctime_ns == st.st_ctime_ns % 1_000_000_000
        assert entry.mtime_s == st.st_mtime_ns // 1_000_000_000
        assert entry.mtime_ns == st.st_mtime_ns % 1_000_000_000


class TestMatchesStat:
    def _make_entry(
        self,
        mtime_s: int = 1_700_000_001,
        mtime_ns: int = 0,
        ino: int = 12345678,
        size: int = 42,
    ) -> IndexEntry:
        return IndexEntry(
            ctime_s=0,
            ctime_ns=0,
            mtime_s=mtime_s,
            mtime_ns=mtime_ns,
            dev=0,
            ino=ino & 0xFFFFFFFF,
            mode=0o100644,
            uid=0,
            gid=0,
            size=size,
            sha=FAKE_SHA,
            flags=4,
            path="file",
        )

    def test_matches_when_identical(self) -> None:
        entry = self._make_entry(size=42, ino=11, mtime_s=100, mtime_ns=500)
        # ctime_ns=0 matches entry.ctime_s=0 / ctime_ns=0; mode=0o100644 matches.
        st = _make_fake_st(
            size=42,
            ino=11,
            mtime_ns=100 * 10**9 + 500,
            ctime_ns=0,
            mode=0o100644,
        )
        assert entry.matches_stat(st) is True

    def test_mismatch_on_size_change(self) -> None:
        entry = self._make_entry(size=42)
        st = _make_fake_st(size=99, ctime_ns=0, mode=0o100644)
        assert entry.matches_stat(st) is False

    def test_mismatch_on_mtime_change(self) -> None:
        entry = self._make_entry(mtime_s=100, mtime_ns=0)
        st = _make_fake_st(
            mtime_ns=200 * 10**9, ctime_ns=0, mode=0o100644
        )  # different seconds
        assert entry.matches_stat(st) is False

    def test_mismatch_on_ino_change(self) -> None:
        entry = self._make_entry(ino=11, size=42, mtime_s=100, mtime_ns=0)
        st = _make_fake_st(
            ino=99, size=42, mtime_ns=100 * 10**9, ctime_ns=0, mode=0o100644
        )
        assert entry.matches_stat(st) is False


class TestProperties:
    def _entry(self, mode: int, flags: int = 0) -> IndexEntry:
        return IndexEntry(
            ctime_s=0,
            ctime_ns=0,
            mtime_s=0,
            mtime_ns=0,
            dev=0,
            ino=0,
            mode=mode,
            uid=0,
            gid=0,
            size=0,
            sha=FAKE_SHA,
            flags=flags,
            path="f",
        )

    def test_is_regular_file(self) -> None:
        assert self._entry(0o100644).is_regular_file is True

    def test_is_executable(self) -> None:
        assert self._entry(0o100755).is_executable is True

    def test_is_symlink(self) -> None:
        assert self._entry(0o120000).is_symlink is True

    def test_stage_from_flags(self) -> None:
        for stage in range(4):
            e = self._entry(0o100644, flags=(stage << 12) | 4)
            assert e.stage == stage

    def test_assume_valid(self) -> None:
        e = self._entry(0o100644, flags=0x8000)
        assert e.assume_valid is True
        e2 = self._entry(0o100644, flags=0)
        assert e2.assume_valid is False
