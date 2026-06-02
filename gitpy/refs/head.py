"""HEAD reference management.

Handles reading and writing the HEAD reference, which can be either
attached (pointing to a branch) or detached (pointing to a SHA).
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .manager import RefManager


class HeadState(Enum):
    """Possible states for the HEAD reference.

    Attributes:
        ATTACHED: HEAD points to a branch ref.
        DETACHED: HEAD points directly to a commit SHA.
    """

    ATTACHED = "attached"
    DETACHED = "detached"


@dataclass(slots=True)
class Head:
    """Represents the HEAD reference.

    HEAD is special: it is the only commonly-used symbolic ref.
    It indicates the current branch or commit.

    Attributes:
        state: Whether HEAD is attached to a branch or detached at a SHA.
        target: Branch ref (e.g. "refs/heads/main") when attached,
            or 40-char SHA when detached.
    """

    state: HeadState
    target: str

    @property
    def is_detached(self) -> bool:
        """True when HEAD points directly to a commit SHA."""
        return self.state == HeadState.DETACHED

    @property
    def branch(self) -> str | None:
        """Current branch short name, or None if detached.

        Returns:
            Short branch name (e.g. "main") or None.
        """
        if self.state == HeadState.ATTACHED:
            if self.target.startswith("refs/heads/"):
                return self.target[11:]
            return self.target
        return None

    @property
    def sha(self) -> str | None:
        """Direct SHA if detached, None if attached.

        Returns:
            40-char hex SHA or None.
        """
        if self.state == HeadState.DETACHED:
            return self.target
        return None


class HeadManager:
    """Manages the HEAD reference.

    Provides atomic read/write operations for HEAD, supporting both
    attached (branch-tracking) and detached (SHA-pinned) states.

    Args:
        git_dir: Path to the .git directory.
    """

    def __init__(self, git_dir: Path) -> None:
        """Initialise HeadManager.

        Args:
            git_dir: Path to the .git directory.
        """
        self.git_dir = git_dir
        self.head_path = git_dir / "HEAD"

    def read(self) -> Head:
        """Read the current HEAD state.

        Returns:
            Head instance reflecting current HEAD content.
        """
        content = self.head_path.read_text().strip()

        if content.startswith("ref: "):
            target = content[5:]
            return Head(state=HeadState.ATTACHED, target=target)

        return Head(state=HeadState.DETACHED, target=content)

    def set_branch(self, branch: str) -> None:
        """Point HEAD at a branch.

        Args:
            branch: Branch short name or full ref (e.g. "main" or
                "refs/heads/main"). Short names are automatically
                prefixed with "refs/heads/".
        """
        if not branch.startswith("refs/"):
            branch = f"refs/heads/{branch}"
        self._write(f"ref: {branch}\n")

    def set_detached(self, sha: str) -> None:
        """Point HEAD at a specific commit (detached mode).

        Args:
            sha: 40-character hex commit SHA.

        Raises:
            ValueError: If sha is not exactly 40 characters.
        """
        if len(sha) != 40:
            raise ValueError("SHA must be 40 characters")
        self._write(f"{sha}\n")

    def _write(self, content: str) -> None:
        """Atomically write content to HEAD via a lock file.

        Args:
            content: Text to write.
        """
        lock = self.head_path.with_suffix(".lock")
        try:
            lock.write_text(content)
            os.replace(lock, self.head_path)
        except Exception:
            lock.unlink(missing_ok=True)
            raise

    def resolve(self, ref_manager: RefManager) -> str:
        """Resolve HEAD to a commit SHA.

        Args:
            ref_manager: Reference manager used to resolve branch names.

        Returns:
            40-character hex SHA of the current commit.

        Raises:
            ValueError: HEAD points to a branch that does not exist yet.
        """
        head = self.read()

        if head.is_detached:
            return head.target

        sha = ref_manager.resolve(head.target)
        if sha is None:
            raise ValueError(f"Branch {head.branch} does not exist")
        return sha
