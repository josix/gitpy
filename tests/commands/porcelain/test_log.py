"""Tests for the ``log`` porcelain command."""

from pathlib import Path

import pytest

from gitpy.commands.porcelain.add import add
from gitpy.commands.porcelain.commit import commit
from gitpy.commands.porcelain.log import log
from gitpy.repository import Repository


@pytest.fixture()
def repo_with_commits(tmp_path: Path) -> Repository:
    """Repository with three commits."""
    repo = Repository.init(tmp_path)
    for i in range(3):
        (tmp_path / f"file{i}.txt").write_text(f"content {i}")
        add(repo, [f"file{i}.txt"])
        commit(repo, f"commit {i}")
    return repo


def test_log_returns_zero(repo_with_commits: Repository) -> None:
    assert log(repo_with_commits) == 0


def test_log_oneline_format(
    repo_with_commits: Repository, capsys: pytest.CaptureFixture[str]
) -> None:
    """Oneline format: each line has ``<7sha> <subject>``."""
    log(repo_with_commits, oneline=True)
    out = capsys.readouterr().out
    lines = [ln for ln in out.splitlines() if ln.strip()]
    assert len(lines) == 3
    for line in lines:
        parts = line.split(" ", 1)
        assert len(parts[0]) == 7, f"SHA prefix not 7 chars: {parts[0]!r}"


def test_log_n_limit(
    repo_with_commits: Repository, capsys: pytest.CaptureFixture[str]
) -> None:
    """``-n 1`` shows only one commit."""
    log(repo_with_commits, oneline=True, n=1)
    out = capsys.readouterr().out
    lines = [ln for ln in out.splitlines() if ln.strip()]
    assert len(lines) == 1


def test_log_shows_subject(
    repo_with_commits: Repository, capsys: pytest.CaptureFixture[str]
) -> None:
    """Log shows the commit message subject."""
    log(repo_with_commits, oneline=True)
    out = capsys.readouterr().out
    assert "commit 2" in out


def test_log_long_format_contains_author(
    repo_with_commits: Repository, capsys: pytest.CaptureFixture[str]
) -> None:
    """Long format includes Author: line."""
    log(repo_with_commits, n=1)
    out = capsys.readouterr().out
    assert "Author:" in out


def test_log_invalid_revision_returns_1(repo_with_commits: Repository) -> None:
    """Unknown revision returns exit code 1."""
    code = log(repo_with_commits, "refs/heads/nonexistent")
    assert code == 1
