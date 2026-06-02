"""Tests for update_ref plumbing command."""

from pathlib import Path

import pytest

from gitpy.commands.plumbing import update_ref
from gitpy.repository import Repository

SHA_A = "a" * 40
SHA_B = "b" * 40


@pytest.fixture()
def repo(tmp_path: Path) -> Repository:
    return Repository.init(tmp_path)


class TestUpdateRefWrite:
    def test_creates_new_ref(self, repo: Repository) -> None:
        """update_ref creates a ref that can then be resolved."""
        rc = update_ref(repo, "refs/heads/feature", SHA_A)
        assert rc == 0
        assert repo.refs.resolve("refs/heads/feature") == SHA_A

    def test_updates_existing_ref(self, repo: Repository) -> None:
        """update_ref overwrites an existing ref with the new SHA."""
        update_ref(repo, "refs/heads/feature", SHA_A)
        rc = update_ref(repo, "refs/heads/feature", SHA_B)
        assert rc == 0
        assert repo.refs.resolve("refs/heads/feature") == SHA_B

    def test_invalid_sha_returns_1(self, repo: Repository) -> None:
        """An invalid SHA value returns exit code 1."""
        rc = update_ref(repo, "refs/heads/bad", "not-a-sha")
        assert rc == 1

    def test_none_value_returns_1(self, repo: Repository) -> None:
        """Passing newvalue=None without delete=True returns exit code 1."""
        rc = update_ref(repo, "refs/heads/nothing", None)
        assert rc == 1


class TestUpdateRefDelete:
    def test_deletes_existing_ref(self, repo: Repository) -> None:
        """delete=True removes a ref so it can no longer be resolved."""
        update_ref(repo, "refs/heads/todelete", SHA_A)
        assert repo.refs.resolve("refs/heads/todelete") == SHA_A

        rc = update_ref(repo, "refs/heads/todelete", None, delete=True)
        assert rc == 0
        assert repo.refs.resolve("refs/heads/todelete") is None

    def test_delete_nonexistent_ref_returns_0(self, repo: Repository) -> None:
        """Deleting a non-existent ref is a no-op returning 0."""
        rc = update_ref(repo, "refs/heads/ghost", None, delete=True)
        assert rc == 0

    def test_delete_ignores_newvalue(self, repo: Repository) -> None:
        """When delete=True, newvalue is ignored even if provided."""
        update_ref(repo, "refs/heads/target", SHA_A)
        rc = update_ref(repo, "refs/heads/target", SHA_B, delete=True)
        assert rc == 0
        assert repo.refs.resolve("refs/heads/target") is None
