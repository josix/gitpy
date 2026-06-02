"""End-to-end workflow test: init -> add -> commit -> log.

Verifies that:
- HEAD resolves to the new commit after commit
- The commit's tree equals write_tree output
- The reflog has at least one entry
"""

from pathlib import Path

import pytest

from gitpy.commands.porcelain.add import add
from gitpy.commands.porcelain.commit import commit
from gitpy.index.operations import write_tree
from gitpy.repository import Repository


@pytest.fixture()
def repo(tmp_path: Path) -> Repository:
    """Fresh repository with a committed file."""
    r = Repository.init(tmp_path)
    (tmp_path / "hello.txt").write_text("hello\n")
    return r


def test_init_add_commit_head(repo: Repository) -> None:
    """HEAD resolves to the new commit after add + commit."""
    assert add(repo, ["hello.txt"]) == 0
    assert commit(repo, "initial commit") == 0

    commit_sha = repo.head.resolve(repo.refs)
    assert len(commit_sha) == 40
    assert repo.objects.get_type(commit_sha) == "commit"


def test_commit_tree_matches_write_tree(repo: Repository) -> None:
    """The commit's tree SHA equals write_tree(index) output."""
    assert add(repo, ["hello.txt"]) == 0

    # Capture write_tree output BEFORE commit
    index_before = repo.index.read()
    expected_tree = write_tree(index_before, repo.objects)

    assert commit(repo, "initial commit") == 0

    commit_sha = repo.head.resolve(repo.refs)
    commit_obj = repo.objects.read_commit(commit_sha)
    assert commit_obj.tree_sha == expected_tree


def test_reflog_has_entry(repo: Repository) -> None:
    """At least one reflog entry exists after the first commit."""
    assert add(repo, ["hello.txt"]) == 0
    assert commit(repo, "initial commit") == 0

    entries = repo.reflog.read("HEAD")
    assert len(entries) >= 1
    assert entries[0].message.startswith("commit:")


def test_second_commit_has_parent(tmp_path: Path) -> None:
    """Second commit's parent_shas contains the first commit SHA."""
    repo = Repository.init(tmp_path)
    (tmp_path / "a.txt").write_text("a")
    add(repo, ["a.txt"])
    commit(repo, "first")

    first_sha = repo.head.resolve(repo.refs)

    (tmp_path / "b.txt").write_text("b")
    add(repo, ["b.txt"])
    commit(repo, "second")

    second_sha = repo.head.resolve(repo.refs)
    commit_obj = repo.objects.read_commit(second_sha)
    assert commit_obj.parent_shas == [first_sha]


def test_commit_updates_branch_ref(repo: Repository) -> None:
    """The branch ref (e.g. refs/heads/main) points to the commit."""
    add(repo, ["hello.txt"])
    commit(repo, "initial commit")

    head = repo.head.read()
    assert not head.is_detached
    branch_ref = head.target  # e.g. "refs/heads/main"
    branch_sha = repo.refs.resolve(branch_ref)
    head_sha = repo.head.resolve(repo.refs)
    assert branch_sha == head_sha
