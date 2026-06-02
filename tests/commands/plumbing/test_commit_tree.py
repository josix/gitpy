"""Tests for commit_tree plumbing command."""

from pathlib import Path

import pytest

from gitpy.commands.plumbing.commit_tree import commit_tree
from gitpy.objects.commit import Commit
from gitpy.objects.tree import Tree
from gitpy.repository import Repository

EMPTY_TREE_SHA = "4b825dc642cb6eb9a060e54bf8d69288fbee4904"


@pytest.fixture()
def repo(tmp_path: Path) -> Repository:
    return Repository.init(tmp_path)


@pytest.fixture()
def empty_tree_sha(repo: Repository) -> str:
    tree = Tree(entries=[])
    return repo.objects.write(tree)


class TestCommitTreeBasic:
    def test_returns_sha(self, repo: Repository, empty_tree_sha: str) -> None:
        """commit_tree returns a 40-char hex SHA."""
        sha = commit_tree(repo, empty_tree_sha, parents=[], message="initial\n")
        assert len(sha) == 40
        assert all(c in "0123456789abcdef" for c in sha)

    def test_stored_in_database(self, repo: Repository, empty_tree_sha: str) -> None:
        """The commit object is stored and readable from the database."""
        sha = commit_tree(repo, empty_tree_sha, parents=[], message="test\n")
        assert repo.objects.exists(sha)
        commit = repo.objects.read_commit(sha)
        assert isinstance(commit, Commit)

    def test_tree_sha_correct(self, repo: Repository, empty_tree_sha: str) -> None:
        """The commit's tree_sha matches the passed tree SHA."""
        sha = commit_tree(repo, empty_tree_sha, parents=[], message="msg\n")
        commit = repo.objects.read_commit(sha)
        assert commit.tree_sha == empty_tree_sha

    def test_message_preserved(self, repo: Repository, empty_tree_sha: str) -> None:
        """The commit message is stored verbatim."""
        message = "This is a commit message.\n"
        sha = commit_tree(repo, empty_tree_sha, parents=[], message=message)
        commit = repo.objects.read_commit(sha)
        assert commit.message == message

    def test_root_commit_has_no_parents(
        self, repo: Repository, empty_tree_sha: str
    ) -> None:
        """Root commit has an empty parent list."""
        sha = commit_tree(repo, empty_tree_sha, parents=[], message="root\n")
        commit = repo.objects.read_commit(sha)
        assert commit.parent_shas == []

    def test_commit_with_parent(self, repo: Repository, empty_tree_sha: str) -> None:
        """Child commit stores parent SHA correctly."""
        parent_sha = commit_tree(repo, empty_tree_sha, parents=[], message="parent\n")
        child_sha = commit_tree(
            repo, empty_tree_sha, parents=[parent_sha], message="child\n"
        )
        child = repo.objects.read_commit(child_sha)
        assert child.parent_shas == [parent_sha]

    def test_commit_with_multiple_parents(
        self, repo: Repository, empty_tree_sha: str
    ) -> None:
        """Merge commit stores all parent SHAs."""
        pa = commit_tree(repo, empty_tree_sha, parents=[], message="a\n")
        pb = commit_tree(repo, empty_tree_sha, parents=[], message="b\n")
        merge = commit_tree(repo, empty_tree_sha, parents=[pa, pb], message="merge\n")
        merge_commit = repo.objects.read_commit(merge)
        assert merge_commit.parent_shas == [pa, pb]


class TestCommitTreeIdentityFromEnv:
    def test_author_from_env(
        self, repo: Repository, empty_tree_sha: str, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Author identity is sourced from environment variables."""
        monkeypatch.setenv("GIT_AUTHOR_NAME", "Alice Tester")
        monkeypatch.setenv("GIT_AUTHOR_EMAIL", "alice@example.com")
        monkeypatch.setenv("GIT_AUTHOR_DATE", "1700000000 +0100")

        sha = commit_tree(repo, empty_tree_sha, parents=[], message="env test\n")
        commit = repo.objects.read_commit(sha)
        assert commit.author is not None
        assert commit.author.name == "Alice Tester"
        assert commit.author.email == "alice@example.com"
        assert commit.author.timestamp == 1700000000
        assert commit.author.tz_offset == "+0100"

    def test_committer_from_env(
        self, repo: Repository, empty_tree_sha: str, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Committer identity is sourced from environment variables."""
        monkeypatch.setenv("GIT_COMMITTER_NAME", "Bob Builder")
        monkeypatch.setenv("GIT_COMMITTER_EMAIL", "bob@example.com")
        monkeypatch.setenv("GIT_COMMITTER_DATE", "1700001000 +0000")

        sha = commit_tree(repo, empty_tree_sha, parents=[], message="committer env\n")
        commit = repo.objects.read_commit(sha)
        assert commit.committer is not None
        assert commit.committer.name == "Bob Builder"
        assert commit.committer.email == "bob@example.com"

    def test_defaults_when_no_env(
        self, repo: Repository, empty_tree_sha: str, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Falls back to defaults when env vars are absent."""
        for var in (
            "GIT_AUTHOR_NAME",
            "GIT_AUTHOR_EMAIL",
            "GIT_AUTHOR_DATE",
            "GIT_COMMITTER_NAME",
            "GIT_COMMITTER_EMAIL",
            "GIT_COMMITTER_DATE",
        ):
            monkeypatch.delenv(var, raising=False)

        sha = commit_tree(repo, empty_tree_sha, parents=[], message="default\n")
        commit = repo.objects.read_commit(sha)
        assert commit.author is not None
        assert commit.committer is not None
        # Should be non-empty strings.
        assert commit.author.name
        assert commit.author.email
