"""Shared pytest fixtures for the gitpy test suite."""

import shutil
import subprocess
from pathlib import Path

import pytest

from gitpy.repository import Repository


def git_available() -> bool:
    """Return True if the ``git`` binary is on PATH."""
    return shutil.which("git") is not None


#: pytest mark that skips tests when git is not installed.
requires_git = pytest.mark.skipif(not git_available(), reason="git not available")


@pytest.fixture()
def gitpy_repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Repository:
    """Initialise a gitpy repository in a fresh temp directory.

    Patches GIT_AUTHOR_* and GIT_COMMITTER_* so commits work without
    a real git config.
    """
    monkeypatch.setenv("GIT_AUTHOR_NAME", "Test User")
    monkeypatch.setenv("GIT_AUTHOR_EMAIL", "test@example.com")
    monkeypatch.setenv("GIT_COMMITTER_NAME", "Test User")
    monkeypatch.setenv("GIT_COMMITTER_EMAIL", "test@example.com")
    return Repository.init(tmp_path / "repo")


@pytest.fixture()
def git_repo(tmp_path: Path) -> Path:
    """Initialise a real Git repository in a fresh temp directory.

    Skips the test automatically when ``git`` is not available.
    """
    if not git_available():
        pytest.skip("git not available")

    repo_path = tmp_path / "git_repo"
    repo_path.mkdir()
    subprocess.run(
        ["git", "init", "-b", "main", str(repo_path)],
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.email", "test@example.com"],
        cwd=repo_path,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Test"],
        cwd=repo_path,
        check=True,
        capture_output=True,
    )
    return repo_path
