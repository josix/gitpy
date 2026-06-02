"""Tests for the ``status`` porcelain command."""

from pathlib import Path

import pytest

from gitpy.commands.porcelain.add import add
from gitpy.commands.porcelain.commit import commit
from gitpy.commands.porcelain.status import status
from gitpy.repository import Repository


@pytest.fixture()
def repo(tmp_path: Path) -> Repository:
    return Repository.init(tmp_path)


def test_status_new_repo_clean(
    repo: Repository, capsys: pytest.CaptureFixture[str]
) -> None:
    """Fresh repo with no files reports clean working tree."""
    code = status(repo)
    assert code == 0
    out = capsys.readouterr().out
    assert "nothing to commit" in out


def test_status_untracked_file(
    repo: Repository, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Untracked file shows up in status."""
    (tmp_path / "untracked.txt").write_text("untracked")
    status(repo)
    out = capsys.readouterr().out
    assert "untracked.txt" in out


def test_status_staged_file(
    repo: Repository, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Staged (added) file shows up in status."""
    (tmp_path / "staged.txt").write_text("staged")
    add(repo, ["staged.txt"])
    status(repo)
    out = capsys.readouterr().out
    assert "staged.txt" in out


def test_status_modified_after_commit(
    repo: Repository, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Modified file (not staged) shows up as modified in status."""
    (tmp_path / "file.txt").write_text("original")
    add(repo, ["file.txt"])
    commit(repo, "initial")

    (tmp_path / "file.txt").write_text("modified content")
    status(repo)
    out = capsys.readouterr().out
    assert "file.txt" in out


def test_status_short_format(
    repo: Repository, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Short format produces XY code lines."""
    (tmp_path / "new.txt").write_text("new")
    status(repo, short=True)
    out = capsys.readouterr().out
    # Should contain 2-char code + space + filename
    assert "new.txt" in out
    lines = [ln for ln in out.splitlines() if ln.strip()]
    assert all(len(ln) >= 4 for ln in lines)


def test_status_short_staged_shows_A(
    repo: Repository, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Short format shows 'A' for a newly staged file."""
    (tmp_path / "added.txt").write_text("added")
    add(repo, ["added.txt"])
    commit(repo, "first")  # ensure HEAD exists
    # Add a new file (staged)
    (tmp_path / "new2.txt").write_text("new")
    add(repo, ["new2.txt"])
    status(repo, short=True)
    out = capsys.readouterr().out
    assert "A" in out
