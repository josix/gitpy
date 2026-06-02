"""Tests for the ``checkout`` porcelain command."""

from pathlib import Path

import pytest

from gitpy.commands.porcelain.add import add
from gitpy.commands.porcelain.branch import branch
from gitpy.commands.porcelain.checkout import checkout
from gitpy.commands.porcelain.commit import commit
from gitpy.repository import Repository


@pytest.fixture()
def repo(tmp_path: Path) -> Repository:
    """Repository with one commit on ``main``."""
    r = Repository.init(tmp_path)
    (tmp_path / "file.txt").write_text("main content")
    add(r, ["file.txt"])
    commit(r, "initial")
    return r


def test_checkout_b_creates_and_switches(repo: Repository) -> None:
    """-b creates a new branch and switches to it."""
    code = checkout(repo, new_branch="feature")
    assert code == 0
    assert repo.branches.current() == "feature"


def test_checkout_b_returns_zero(repo: Repository) -> None:
    assert checkout(repo, new_branch="dev") == 0


def test_checkout_existing_branch_switches(repo: Repository) -> None:
    """Switching to an existing branch updates HEAD."""
    branch(repo, "other")
    code = checkout(repo, "other")
    assert code == 0
    assert repo.branches.current() == "other"


def test_checkout_restores_worktree_files(tmp_path: Path) -> None:
    """Checking out a branch restores the working tree files."""
    repo = Repository.init(tmp_path)

    # First commit: file_a.txt
    (tmp_path / "file_a.txt").write_text("content a")
    add(repo, ["file_a.txt"])
    commit(repo, "add file_a")

    # Create branch 'alt' and add file_b.txt
    checkout(repo, new_branch="alt")
    (tmp_path / "file_b.txt").write_text("content b")
    add(repo, ["file_b.txt"])
    commit(repo, "add file_b on alt")

    # Go back to main; file_b.txt should be gone from index
    checkout(repo, "main")
    assert repo.branches.current() == "main"
    index = repo.index.read()
    paths = {entry.path for entry in index}
    assert "file_a.txt" in paths
    assert "file_b.txt" not in paths


def test_checkout_nonexistent_branch_returns_error(repo: Repository) -> None:
    code = checkout(repo, "nonexistent")
    assert code == 1


def test_checkout_no_target_returns_error(repo: Repository) -> None:
    code = checkout(repo)
    assert code == 1


def test_checkout_b_duplicate_returns_error(repo: Repository) -> None:
    """Creating a branch that already exists fails."""
    checkout(repo, new_branch="existing")
    code = checkout(repo, new_branch="existing")
    assert code == 1
