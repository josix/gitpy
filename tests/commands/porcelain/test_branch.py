"""Tests for the ``branch`` porcelain command."""

from pathlib import Path

import pytest

from gitpy.commands.porcelain.add import add
from gitpy.commands.porcelain.branch import branch
from gitpy.commands.porcelain.commit import commit
from gitpy.repository import Repository


@pytest.fixture()
def repo(tmp_path: Path) -> Repository:
    """Repository with one commit on ``main``."""
    r = Repository.init(tmp_path)
    (tmp_path / "f.txt").write_text("f")
    add(r, ["f.txt"])
    commit(r, "initial")
    return r


def test_list_shows_current_branch(
    repo: Repository, capsys: pytest.CaptureFixture[str]
) -> None:
    """Listing branches marks the current one with ``*``."""
    branch(repo)
    out = capsys.readouterr().out
    assert "* main" in out


def test_create_branch(repo: Repository, capsys: pytest.CaptureFixture[str]) -> None:
    """Creating a branch adds it to the list."""
    branch(repo, "feature")
    branch(repo)
    out = capsys.readouterr().out
    assert "feature" in out


def test_create_branch_returns_zero(repo: Repository) -> None:
    assert branch(repo, "new-branch") == 0


def test_delete_branch(repo: Repository, capsys: pytest.CaptureFixture[str]) -> None:
    """Deleting a branch removes it from the listing."""
    branch(repo, "to-delete")
    code = branch(repo, "to-delete", delete=True)
    assert code == 0
    branch(repo)
    out = capsys.readouterr().out
    assert "to-delete" not in out


def test_delete_nonexistent_branch_returns_error(repo: Repository) -> None:
    code = branch(repo, "nope", delete=True)
    assert code == 1


def test_rename_branch(repo: Repository, capsys: pytest.CaptureFixture[str]) -> None:
    """Renaming a branch gives it the new name."""
    branch(repo, "old-name")
    code = branch(repo, move=True, old="old-name", new="new-name")
    assert code == 0
    branch(repo)
    out = capsys.readouterr().out
    assert "new-name" in out
    assert "old-name" not in out


def test_rename_nonexistent_returns_error(repo: Repository) -> None:
    code = branch(repo, move=True, old="ghost", new="new")
    assert code == 1


def test_create_duplicate_without_force_returns_error(repo: Repository) -> None:
    branch(repo, "dup")
    code = branch(repo, "dup")
    assert code == 1


def test_create_with_force_overwrites(repo: Repository) -> None:
    branch(repo, "dup")
    code = branch(repo, "dup", force=True)
    assert code == 0
