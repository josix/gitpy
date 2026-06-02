"""Tests for Branch and BranchManager."""

from pathlib import Path

import pytest

from gitpy.repository import Repository

SHA_A = "a" * 40
SHA_B = "b" * 40


class TestBranchCreate:
    """Tests for BranchManager.create."""

    def test_create_branch(self, tmp_path: Path) -> None:
        """Creating a branch makes it resolvable."""
        repo = Repository.init(tmp_path / "repo")
        branch = repo.branches.create("feature", SHA_A)
        assert branch.name == "feature"
        assert repo.branches.exists("feature")

    def test_create_duplicate_raises(self, tmp_path: Path) -> None:
        """Creating an already-existing branch without force raises."""
        repo = Repository.init(tmp_path / "repo")
        repo.branches.create("feature", SHA_A)
        with pytest.raises(ValueError, match="already exists"):
            repo.branches.create("feature", SHA_B)

    def test_create_force_overwrites(self, tmp_path: Path) -> None:
        """Creating with force=True overwrites existing branch."""
        repo = Repository.init(tmp_path / "repo")
        repo.branches.create("feature", SHA_A)
        branch = repo.branches.create("feature", SHA_B, force=True)
        assert branch.sha == SHA_B


class TestBranchDelete:
    """Tests for BranchManager.delete."""

    def test_delete_branch(self, tmp_path: Path) -> None:
        """Deleting a non-current branch works."""
        repo = Repository.init(tmp_path / "repo")
        repo.branches.create("feature", SHA_A)
        result = repo.branches.delete("feature")
        assert result is True
        assert not repo.branches.exists("feature")

    def test_delete_current_branch_raises(self, tmp_path: Path) -> None:
        """Deleting the currently checked-out branch raises ValueError."""
        repo = Repository.init(tmp_path / "repo")
        repo.branches.create("main", SHA_A)
        repo.head.set_branch("main")
        with pytest.raises(ValueError, match="currently checked out"):
            repo.branches.delete("main")

    def test_delete_nonexistent_returns_false(self, tmp_path: Path) -> None:
        """Deleting a branch that does not exist returns False."""
        repo = Repository.init(tmp_path / "repo")
        result = repo.branches.delete("ghost")
        assert result is False


class TestBranchRename:
    """Tests for BranchManager.rename."""

    def test_rename_branch(self, tmp_path: Path) -> None:
        """Renaming a non-current branch updates the ref."""
        repo = Repository.init(tmp_path / "repo")
        repo.branches.create("old", SHA_A)
        branch = repo.branches.rename("old", "new")
        assert branch.name == "new"
        assert repo.branches.exists("new")
        assert not repo.branches.exists("old")

    def test_rename_updates_head(self, tmp_path: Path) -> None:
        """Renaming the current branch updates HEAD."""
        repo = Repository.init(tmp_path / "repo")
        repo.branches.create("old", SHA_A)
        repo.head.set_branch("old")
        repo.branches.rename("old", "new")
        assert repo.head.read().branch == "new"

    def test_rename_nonexistent_raises(self, tmp_path: Path) -> None:
        """Renaming a branch that does not exist raises ValueError."""
        repo = Repository.init(tmp_path / "repo")
        with pytest.raises(ValueError, match="does not exist"):
            repo.branches.rename("ghost", "new")


class TestBranchList:
    """Tests for BranchManager.list."""

    def test_list_branches(self, tmp_path: Path) -> None:
        """List returns all created branches."""
        repo = Repository.init(tmp_path / "repo")
        repo.branches.create("main", SHA_A)
        repo.branches.create("feature", SHA_B)
        names = {b.name for b in repo.branches.list()}
        assert "main" in names
        assert "feature" in names
