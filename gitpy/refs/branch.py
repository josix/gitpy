"""Branch management.

Provides Branch data-class and BranchManager for create, delete, rename,
and list operations on local branches.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .head import HeadManager
    from .manager import RefManager


@dataclass(slots=True)
class Branch:
    """Represents a Git branch.

    Attributes:
        name: Short branch name (e.g. "main").
        sha: Full 40-char SHA the branch currently points to.
    """

    name: str
    sha: str

    @property
    def full_name(self) -> str:
        """Full ref name including namespace (e.g. "refs/heads/main")."""
        return f"refs/heads/{self.name}"

    @property
    def short_sha(self) -> str:
        """First 7 characters of the SHA."""
        return self.sha[:7]


class BranchManager:
    """High-level branch operations.

    Delegates low-level ref I/O to RefManager and HEAD mutations to
    HeadManager.

    Args:
        ref_manager: RefManager instance for this repository.
        head_manager: HeadManager instance for this repository.
    """

    def __init__(self, ref_manager: RefManager, head_manager: HeadManager) -> None:
        """Initialise BranchManager.

        Args:
            ref_manager: Ref manager for the repository.
            head_manager: HEAD manager for the repository.
        """
        self.refs = ref_manager
        self.head = head_manager

    def current(self) -> str | None:
        """Return the current branch short name, or None if detached.

        Returns:
            Branch name string, or None when HEAD is detached.
        """
        return self.head.read().branch

    def exists(self, name: str) -> bool:
        """Check whether a branch exists.

        Args:
            name: Short branch name.

        Returns:
            True if the branch ref can be resolved.
        """
        return self.refs.resolve(f"refs/heads/{name}") is not None

    def get(self, name: str) -> Branch | None:
        """Retrieve a branch by name.

        Args:
            name: Short branch name.

        Returns:
            Branch instance, or None if the branch does not exist.
        """
        sha = self.refs.resolve(f"refs/heads/{name}")
        if sha:
            return Branch(name=name, sha=sha)
        return None

    def create(self, name: str, sha: str, force: bool = False) -> Branch:
        """Create a new branch.

        Args:
            name: Short branch name to create.
            sha: Commit SHA the branch should point to.
            force: If True, overwrite an existing branch.

        Returns:
            Newly created Branch.

        Raises:
            ValueError: Branch already exists and *force* is False, or
                the name is invalid.
        """
        self._validate_name(name)

        if self.exists(name) and not force:
            raise ValueError(f"Branch '{name}' already exists")

        self.refs.write(f"refs/heads/{name}", sha)
        return Branch(name=name, sha=sha)

    def delete(self, name: str, *, force: bool = False) -> bool:
        """Delete a branch.

        Args:
            name: Short branch name.
            force: Reserved for future merge-safety checks; currently
                unused (the branch is deleted regardless).

        Returns:
            True if the branch was deleted, False if it did not exist.

        Raises:
            ValueError: Attempting to delete the currently checked-out
                branch.
        """
        del force  # reserved for merge-safety; not yet implemented
        if name == self.current():
            raise ValueError("Cannot delete the currently checked out branch")

        return self.refs.delete(f"refs/heads/{name}")

    def rename(self, old_name: str, new_name: str, force: bool = False) -> Branch:
        """Rename a branch.

        If the renamed branch is currently checked out, HEAD is updated
        to track the new name.

        Args:
            old_name: Current short branch name.
            new_name: New short branch name.
            force: If True, overwrite *new_name* if it already exists.

        Returns:
            Updated Branch with the new name.

        Raises:
            ValueError: *old_name* does not exist, *new_name* already
                exists and *force* is False, or *new_name* is invalid.
        """
        self._validate_name(new_name)

        old_branch = self.get(old_name)
        if old_branch is None:
            raise ValueError(f"Branch '{old_name}' does not exist")

        if self.exists(new_name) and not force:
            raise ValueError(f"Branch '{new_name}' already exists")

        self.refs.write(f"refs/heads/{new_name}", old_branch.sha)
        self.refs.delete(f"refs/heads/{old_name}")

        if self.current() == old_name:
            self.head.set_branch(new_name)

        return Branch(name=new_name, sha=old_branch.sha)

    def list(self) -> list[Branch]:
        """List all local branches.

        Returns:
            List of Branch instances sorted by the order returned by
            RefManager.list_branches().
        """
        return [Branch(name=name, sha=sha) for name, sha in self.refs.list_branches()]

    def _validate_name(self, name: str) -> None:
        """Validate a branch name against Git naming rules.

        Args:
            name: Branch name to validate.

        Raises:
            ValueError: The name violates one of Git's naming rules.
        """
        if not name:
            raise ValueError("Branch name cannot be empty")
        if name.startswith("-"):
            raise ValueError("Branch name cannot start with '-'")
        if ".." in name:
            raise ValueError("Branch name cannot contain '..'")
        if name.endswith(".lock"):
            raise ValueError("Branch name cannot end with '.lock'")
        if "@{" in name:
            raise ValueError("Branch name cannot contain '@{'")

        invalid = set(" ~^:?*[\\")
        if any(c in name for c in invalid):
            raise ValueError("Branch name contains invalid characters")
