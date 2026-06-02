"""Tests for the ``add`` porcelain command."""

from pathlib import Path

import pytest

from gitpy.commands.porcelain.add import add
from gitpy.repository import Repository


@pytest.fixture()
def repo(tmp_path: Path) -> Repository:
    return Repository.init(tmp_path)


def test_add_single_file(repo: Repository, tmp_path: Path) -> None:
    """Staging a single file puts it in the index."""
    (tmp_path / "file.txt").write_text("content")
    code = add(repo, ["file.txt"])
    assert code == 0

    index = repo.index.read()
    entry = index.get("file.txt")
    assert entry is not None
    assert len(entry.sha) == 40


def test_add_nonexistent_file_returns_error(repo: Repository) -> None:
    """Adding a nonexistent path returns exit code 1."""
    code = add(repo, ["no_such_file.txt"])
    assert code == 1


def test_add_all_skips_git_dir(repo: Repository, tmp_path: Path) -> None:
    """``add -A`` does not stage files under .git."""
    (tmp_path / "real.txt").write_text("real content")
    code = add(repo, [], all=True)
    assert code == 0

    index = repo.index.read()
    for entry in index:
        assert ".git" not in Path(entry.path).parts


def test_add_all_stages_all_files(repo: Repository, tmp_path: Path) -> None:
    """``add -A`` stages every file in the worktree."""
    (tmp_path / "a.txt").write_text("a")
    (tmp_path / "b.txt").write_text("b")
    code = add(repo, [], all=True)
    assert code == 0

    index = repo.index.read()
    paths = {entry.path for entry in index}
    assert "a.txt" in paths
    assert "b.txt" in paths


def test_add_multiple_files(repo: Repository, tmp_path: Path) -> None:
    """Staging multiple files in one call."""
    (tmp_path / "x.txt").write_text("x")
    (tmp_path / "y.txt").write_text("y")
    code = add(repo, ["x.txt", "y.txt"])
    assert code == 0

    index = repo.index.read()
    assert index.get("x.txt") is not None
    assert index.get("y.txt") is not None


def test_add_blob_written_to_db(repo: Repository, tmp_path: Path) -> None:
    """After staging, the blob object exists in the object database."""
    content = b"hello world"
    (tmp_path / "data.txt").write_bytes(content)
    add(repo, ["data.txt"])

    index = repo.index.read()
    entry = index.get("data.txt")
    assert entry is not None
    assert repo.objects.exists(entry.sha)
