"""Tests for HeadManager and Head."""

from pathlib import Path

import pytest

from gitpy.refs.head import HeadState
from gitpy.repository import Repository

SHA_A = "a" * 40


class TestHeadAfterInit:
    """Verify HEAD state immediately after Repository.init."""

    def test_head_file_content(self, tmp_path: Path) -> None:
        """HEAD file must be exactly 'ref: refs/heads/main\\n' after init."""
        repo = Repository.init(tmp_path / "repo")
        content = (repo.git_dir / "HEAD").read_text()
        assert content == "ref: refs/heads/main\n"

    def test_head_read_attached(self, tmp_path: Path) -> None:
        """read() returns ATTACHED state pointing at 'main'."""
        repo = Repository.init(tmp_path / "repo")
        head = repo.head.read()
        assert head.state == HeadState.ATTACHED
        assert head.branch == "main"
        assert head.is_detached is False


class TestHeadDetached:
    """Tests for detached HEAD mode."""

    def test_set_and_read_detached(self, tmp_path: Path) -> None:
        """Setting detached HEAD stores the SHA directly."""
        repo = Repository.init(tmp_path / "repo")
        repo.head.set_detached(SHA_A)
        head = repo.head.read()
        assert head.is_detached
        assert head.sha == SHA_A
        assert head.branch is None

    def test_set_detached_wrong_length_raises(self, tmp_path: Path) -> None:
        """set_detached with wrong-length SHA raises ValueError."""
        repo = Repository.init(tmp_path / "repo")
        with pytest.raises(ValueError, match="40"):
            repo.head.set_detached("abc123")


class TestHeadSetBranch:
    """Tests for set_branch."""

    def test_set_branch_short_name(self, tmp_path: Path) -> None:
        """set_branch with short name writes full ref path."""
        repo = Repository.init(tmp_path / "repo")
        repo.head.set_branch("feature")
        head = repo.head.read()
        assert head.branch == "feature"
        assert head.target == "refs/heads/feature"

    def test_set_branch_full_name(self, tmp_path: Path) -> None:
        """set_branch with full refs/heads/ name is stored as-is."""
        repo = Repository.init(tmp_path / "repo")
        repo.head.set_branch("refs/heads/develop")
        head = repo.head.read()
        assert head.branch == "develop"


class TestHeadResolve:
    """Tests for HeadManager.resolve."""

    def test_resolve_attached_existing_branch(self, tmp_path: Path) -> None:
        """Resolving HEAD when branch exists returns the commit SHA."""
        repo = Repository.init(tmp_path / "repo")
        repo.refs.write("refs/heads/main", SHA_A)
        sha = repo.head.resolve(repo.refs)
        assert sha == SHA_A

    def test_resolve_detached(self, tmp_path: Path) -> None:
        """Resolving detached HEAD returns the stored SHA directly."""
        repo = Repository.init(tmp_path / "repo")
        repo.head.set_detached(SHA_A)
        sha = repo.head.resolve(repo.refs)
        assert sha == SHA_A

    def test_resolve_missing_branch_raises(self, tmp_path: Path) -> None:
        """Resolving HEAD pointing to non-existent branch raises ValueError."""
        repo = Repository.init(tmp_path / "repo")
        # HEAD points to refs/heads/main but that ref doesn't exist yet
        with pytest.raises(ValueError):
            repo.head.resolve(repo.refs)
