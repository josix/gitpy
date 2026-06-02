"""Reflog implementation.

Records when refs change so that commits can be recovered even after
branch resets or rebases.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Self

from gitpy.objects.commit import Identity

ZERO_SHA: str = "0" * 40


@dataclass(slots=True)
class ReflogEntry:
    """A single reflog entry.

    Attributes:
        old_sha: Previous SHA (ZERO_SHA for a newly created ref).
        new_sha: SHA after the change.
        identity: Who made the change.
        message: Short description of what happened.
    """

    old_sha: str
    new_sha: str
    identity: Identity
    message: str

    def format(self) -> str:
        """Serialise as a reflog line (including trailing newline).

        Returns:
            String in the form
            ``"<old> <new> <identity>\\t<message>\\n"``.
        """
        return f"{self.old_sha} {self.new_sha} {self.identity}\t{self.message}\n"

    @classmethod
    def parse(cls, line: str) -> Self:
        """Parse a single reflog line.

        Args:
            line: Raw line from a reflog file (trailing newline stripped).

        Returns:
            A new ReflogEntry instance.
        """
        parts = line.split("\t", 1)
        header = parts[0]
        message = parts[1].strip() if len(parts) > 1 else ""

        old_sha = header[:40]
        new_sha = header[41:81]
        identity_str = header[82:]

        identity = Identity.parse(identity_str)

        return cls(
            old_sha=old_sha,
            new_sha=new_sha,
            identity=identity,
            message=message,
        )


class Reflog:
    """Manages reflog files for references.

    Reflog files are stored under ``.git/logs/<ref-name>``.

    Args:
        git_dir: Path to the .git directory.
    """

    def __init__(self, git_dir: Path) -> None:
        """Initialise Reflog.

        Args:
            git_dir: Path to the .git directory.
        """
        self.git_dir = git_dir
        self.logs_dir = git_dir / "logs"

    def _log_path(self, ref: str) -> Path:
        """Return the log file path for *ref*.

        Args:
            ref: Reference name (e.g. "HEAD" or "refs/heads/main").

        Returns:
            Absolute path to the log file.
        """
        return self.logs_dir / ref

    def append(
        self,
        ref: str,
        old_sha: str,
        new_sha: str,
        identity: Identity,
        message: str,
    ) -> None:
        """Append an entry to the reflog.

        Creates parent directories if they do not exist.

        Args:
            ref: Reference name (e.g. "HEAD").
            old_sha: Previous SHA (use ZERO_SHA for new refs).
            new_sha: New SHA after the change.
            identity: Who made the change.
            message: Human-readable description (e.g. "commit: msg").
        """
        path = self._log_path(ref)
        path.parent.mkdir(parents=True, exist_ok=True)

        entry = ReflogEntry(
            old_sha=old_sha,
            new_sha=new_sha,
            identity=identity,
            message=message,
        )

        with path.open("a") as f:
            f.write(entry.format())

    def read(self, ref: str, limit: int | None = None) -> list[ReflogEntry]:
        """Read reflog entries, newest first.

        Args:
            ref: Reference name.
            limit: Maximum number of entries to return.

        Returns:
            List of ReflogEntry instances, most recent first.
        """
        path = self._log_path(ref)
        if not path.exists():
            return []

        entries = [
            ReflogEntry.parse(line)
            for line in path.read_text().splitlines()
            if line.strip()
        ]

        entries.reverse()

        if limit is not None:
            entries = entries[:limit]

        return entries

    def get(self, ref: str, index: int) -> ReflogEntry | None:
        """Retrieve a specific reflog entry by index.

        Args:
            ref: Reference name.
            index: 0-based index where 0 is the most recent entry.

        Returns:
            ReflogEntry at *index*, or None if not enough entries.
        """
        entries = self.read(ref, limit=index + 1)
        if index < len(entries):
            return entries[index]
        return None

    def clear(self, ref: str) -> None:
        """Delete the reflog for *ref*.

        Args:
            ref: Reference name.
        """
        path = self._log_path(ref)
        if path.exists():
            path.unlink()
