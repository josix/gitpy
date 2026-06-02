"""Index entry implementation.

Each IndexEntry represents a single staged file and caches its stat
metadata so that status checks can skip SHA computation for unchanged files.
"""

import os
import stat as _stat_module
import stat as stat_module
from dataclasses import dataclass, field
from pathlib import Path
from typing import Self


@dataclass(slots=True)
class IndexEntry:
    """A single entry in the Git index.

    Tracks a file's identity, content hash, and stat metadata for
    efficient change detection.

    Attributes:
        ctime_s: Creation time seconds.
        ctime_ns: Creation time nanoseconds (sub-second part only).
        mtime_s: Modification time seconds.
        mtime_ns: Modification time nanoseconds (sub-second part only).
        dev: Device ID (masked to 32 bits).
        ino: Inode number (masked to 32 bits).
        mode: File mode as integer (e.g. 0o100644).
        uid: User ID (masked to 32 bits).
        gid: Group ID (masked to 32 bits).
        size: File size in bytes.
        sha: 40-character hex SHA-1 of the blob.
        flags: Packed flags (stage | name_length).
        path: Relative path within the repository.
        extended_flags: Extended flags (version 3+, default 0).
    """

    ctime_s: int
    ctime_ns: int
    mtime_s: int
    mtime_ns: int
    dev: int
    ino: int
    mode: int
    uid: int
    gid: int
    size: int
    sha: str
    flags: int
    path: str
    extended_flags: int = field(default=0)

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def stage(self) -> int:
        """Merge stage (0 = normal, 1 = base, 2 = ours, 3 = theirs)."""
        return (self.flags >> 12) & 0x3

    @property
    def name_length(self) -> int:
        """Stored name length (truncated to 0xFFF for long paths)."""
        return self.flags & 0xFFF

    @property
    def assume_valid(self) -> bool:
        """True when the assume-valid flag is set (skip in status checks)."""
        return bool(self.flags & 0x8000)

    @property
    def is_regular_file(self) -> bool:
        """True when the entry represents a regular file."""
        return (self.mode >> 12) == 0o10

    @property
    def is_executable(self) -> bool:
        """True when the entry is an executable file."""
        return self.mode == 0o100755

    @property
    def is_symlink(self) -> bool:
        """True when the entry represents a symbolic link."""
        return (self.mode >> 12) == 0o12

    # ------------------------------------------------------------------
    # Factory
    # ------------------------------------------------------------------

    @classmethod
    def from_path(
        cls,
        path: str,
        sha: str,
        worktree: Path,
        stage: int = 0,
    ) -> Self:
        """Create an IndexEntry by stat-ing a file in the working tree.

        Uses nanosecond timestamps directly from st_ctime_ns / st_mtime_ns
        to avoid floating-point precision loss.

        Args:
            path: Repository-relative path of the file.
            sha: 40-character hex SHA-1 of the file's blob.
            worktree: Absolute path to the repository working directory.
            stage: Merge stage (0 for normal files).

        Returns:
            A new IndexEntry populated from the file's stat.
        """
        full_path = worktree / path
        st = full_path.lstat()

        if stat_module.S_ISLNK(st.st_mode):
            mode = 0o120000
        elif st.st_mode & stat_module.S_IXUSR:
            mode = 0o100755
        else:
            mode = 0o100644

        name_len = min(len(path.encode("utf-8")), 0xFFF)
        flags = (stage << 12) | name_len

        return cls(
            ctime_s=st.st_ctime_ns // 1_000_000_000,
            ctime_ns=st.st_ctime_ns % 1_000_000_000,
            mtime_s=st.st_mtime_ns // 1_000_000_000,
            mtime_ns=st.st_mtime_ns % 1_000_000_000,
            dev=st.st_dev & 0xFFFFFFFF,
            ino=st.st_ino & 0xFFFFFFFF,
            mode=mode,
            uid=st.st_uid & 0xFFFFFFFF,
            gid=st.st_gid & 0xFFFFFFFF,
            size=st.st_size,
            sha=sha,
            flags=flags,
            path=path,
        )

    # ------------------------------------------------------------------
    # Stat comparison
    # ------------------------------------------------------------------

    def matches_stat(self, st: os.stat_result) -> bool:
        """Check whether file stat matches the cached metadata.

        Returns True when the file is PROBABLY unchanged (fast path).
        Returns False when the file has DEFINITELY changed.

        Checks size, mtime, inode, ctime, and file mode (exec-bit /
        type) so that a chmod-only change is detected.

        Args:
            st: Result of os.stat() on the file.

        Returns:
            True if the cached metadata still matches st.
        """
        if st.st_size != self.size:
            return False

        mtime_s = st.st_mtime_ns // 1_000_000_000
        mtime_ns = st.st_mtime_ns % 1_000_000_000
        if mtime_s != self.mtime_s or mtime_ns != self.mtime_ns:
            return False

        if st.st_ino & 0xFFFFFFFF != self.ino:
            return False

        ctime_s = st.st_ctime_ns // 1_000_000_000
        ctime_ns = st.st_ctime_ns % 1_000_000_000
        if ctime_s != self.ctime_s or ctime_ns != self.ctime_ns:
            return False

        # Compare exec-bit and file-type portions of mode.
        st_mode = st.st_mode
        # Compute the git mode for the on-disk file the same way from_path does.
        if _stat_module.S_ISLNK(st_mode):
            disk_mode = 0o120000
        elif st_mode & _stat_module.S_IXUSR:
            disk_mode = 0o100755
        else:
            disk_mode = 0o100644
        return disk_mode == self.mode
