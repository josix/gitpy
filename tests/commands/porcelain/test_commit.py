"""Tests for the ``commit`` porcelain command."""

from pathlib import Path

import pytest

from gitpy.commands.porcelain.add import add
from gitpy.commands.porcelain.commit import commit
from gitpy.repository import Repository


@pytest.fixture()
def repo(tmp_path: Path) -> Repository:
    repo = Repository.init(tmp_path)
    (tmp_path / "file.txt").write_text("hello")
    add(repo, ["file.txt"])
    return repo


def test_commit_returns_zero(repo: Repository) -> None:
    assert commit(repo, "test commit") == 0


def test_commit_creates_commit_object(repo: Repository) -> None:
    commit(repo, "test commit")
    sha = repo.head.resolve(repo.refs)
    obj = repo.objects.read_commit(sha)
    assert obj.message == "test commit"


def test_commit_author_from_config(tmp_path: Path) -> None:
    """Author identity comes from repo config when env vars are absent."""
    repo = Repository.init(tmp_path)
    # Write user config
    config_text = "[user]\n\tname = Test User\n\temail = test@example.com\n"
    (tmp_path / ".git" / "config").write_text(config_text)

    # Invalidate the cached config
    repo._config = None  # noqa: SLF001

    (tmp_path / "f.txt").write_text("f")
    add(repo, ["f.txt"])

    commit(repo, "cfg commit")

    sha = repo.head.resolve(repo.refs)
    obj = repo.objects.read_commit(sha)
    assert obj.author is not None
    assert obj.author.name == "Test User"
    assert obj.author.email == "test@example.com"


def test_commit_no_message(repo: Repository) -> None:
    """Commit stores the exact message provided."""
    commit(repo, "multi\nline\nmessage")
    sha = repo.head.resolve(repo.refs)
    obj = repo.objects.read_commit(sha)
    assert obj.message == "multi\nline\nmessage"


def test_commit_root_has_no_parents(repo: Repository) -> None:
    """First commit has no parents."""
    commit(repo, "root")
    sha = repo.head.resolve(repo.refs)
    obj = repo.objects.read_commit(sha)
    assert obj.parent_shas == []


def test_amend_replaces_tip_and_keeps_same_parent(tmp_path: Path) -> None:
    """Amend replaces HEAD, shares the same parent as the original commit."""
    repo = Repository.init(tmp_path)

    # Make an initial commit (root).
    (tmp_path / "a.txt").write_text("a")
    add(repo, ["a.txt"])
    assert commit(repo, "initial") == 0
    root_sha = repo.head.resolve(repo.refs)
    root_obj = repo.objects.read_commit(root_sha)
    assert root_obj.parent_shas == []

    # Make a second commit so the amendment has a parent.
    (tmp_path / "b.txt").write_text("b")
    add(repo, ["b.txt"])
    assert commit(repo, "second") == 0
    second_sha = repo.head.resolve(repo.refs)
    second_obj = repo.objects.read_commit(second_sha)
    assert second_obj.parent_shas == [root_sha]

    # Stage an extra file, then amend with a new message.
    (tmp_path / "c.txt").write_text("c")
    add(repo, ["c.txt"])
    assert commit(repo, "amended second", amend=True) == 0

    amended_sha = repo.head.resolve(repo.refs)

    # The amended commit must be different from the original second commit.
    assert amended_sha != second_sha

    amended_obj = repo.objects.read_commit(amended_sha)

    # The amended commit must share the same parent as the original second commit.
    assert amended_obj.parent_shas == [root_sha]

    # The new message is stored.
    assert amended_obj.message == "amended second"

    # The new tree must include c.txt (staged before amend).
    from gitpy.diff.tree import flatten_tree

    tree_files = flatten_tree(amended_obj.tree_sha, repo.objects, "")
    assert "c.txt" in tree_files
    assert "b.txt" in tree_files


def test_amend_on_empty_repo_returns_error(tmp_path: Path) -> None:
    """Amending when HEAD has no commits returns exit code 1."""
    repo = Repository.init(tmp_path)
    # Stage something so write_tree won't fail.
    (tmp_path / "x.txt").write_text("x")
    add(repo, ["x.txt"])
    result = commit(repo, "any message", amend=True)
    assert result == 1
