"""Tests for TagManager, LightweightTag, and AnnotatedTag."""

from pathlib import Path

import pytest

from gitpy.objects import Commit, Identity, Tree
from gitpy.refs.tag import AnnotatedTag, LightweightTag
from gitpy.repository import Repository

SHA_A = "a" * 40


def make_commit_sha(repo: Repository) -> str:
    """Write a minimal commit object and return its SHA."""
    tree = Tree(entries=[])
    tree_sha = repo.objects.write(tree)
    identity = Identity(
        name="Test User",
        email="test@example.com",
        timestamp=1234567890,
        tz_offset="+0000",
    )
    commit = Commit(
        tree_sha=tree_sha,
        parent_shas=[],
        author=identity,
        committer=identity,
        message="initial\n",
    )
    return repo.objects.write(commit)


class TestLightweightTag:
    """Tests for lightweight tag creation and peeling."""

    def test_create_lightweight(self, tmp_path: Path) -> None:
        """Creating a lightweight tag stores the SHA."""
        repo = Repository.init(tmp_path / "repo")
        commit_sha = make_commit_sha(repo)
        tag = repo.tags.create_lightweight("v1.0", commit_sha)
        assert isinstance(tag, LightweightTag)
        assert tag.name == "v1.0"
        assert repo.tags.exists("v1.0")

    def test_peel_lightweight(self, tmp_path: Path) -> None:
        """Peeling a lightweight tag returns the commit SHA."""
        repo = Repository.init(tmp_path / "repo")
        commit_sha = make_commit_sha(repo)
        repo.tags.create_lightweight("v1.0", commit_sha)
        assert repo.tags.peel("v1.0") == commit_sha

    def test_create_duplicate_raises(self, tmp_path: Path) -> None:
        """Creating a duplicate tag without force raises ValueError."""
        repo = Repository.init(tmp_path / "repo")
        commit_sha = make_commit_sha(repo)
        repo.tags.create_lightweight("v1.0", commit_sha)
        with pytest.raises(ValueError, match="already exists"):
            repo.tags.create_lightweight("v1.0", commit_sha)


class TestAnnotatedTag:
    """Tests for annotated tag creation and peeling."""

    def test_create_annotated(self, tmp_path: Path) -> None:
        """Creating an annotated tag writes a tag object and ref."""
        repo = Repository.init(tmp_path / "repo")
        commit_sha = make_commit_sha(repo)
        tagger = Identity(
            name="Tagger",
            email="tagger@example.com",
            timestamp=1234567890,
            tz_offset="+0000",
        )
        tag = repo.tags.create_annotated("v2.0", commit_sha, "Release 2.0", tagger)
        assert isinstance(tag, AnnotatedTag)
        assert tag.name == "v2.0"
        assert tag.target == commit_sha

    def test_annotated_tag_object_stored(self, tmp_path: Path) -> None:
        """Annotated tag writes a tag object readable from the database."""
        repo = Repository.init(tmp_path / "repo")
        commit_sha = make_commit_sha(repo)
        tagger = Identity(
            name="Tagger",
            email="tagger@example.com",
            timestamp=1234567890,
            tz_offset="+0000",
        )
        tag = repo.tags.create_annotated("v2.0", commit_sha, "Release 2.0", tagger)
        # The tag sha should point to a tag object in the db
        assert repo.objects.get_type(tag.sha) == "tag"

    def test_peel_annotated(self, tmp_path: Path) -> None:
        """Peeling an annotated tag returns the underlying commit SHA."""
        repo = Repository.init(tmp_path / "repo")
        commit_sha = make_commit_sha(repo)
        tagger = Identity(
            name="Tagger",
            email="tagger@example.com",
            timestamp=1234567890,
            tz_offset="+0000",
        )
        repo.tags.create_annotated("v2.0", commit_sha, "Release 2.0", tagger)
        assert repo.tags.peel("v2.0") == commit_sha

    def test_get_distinguishes_types(self, tmp_path: Path) -> None:
        """get() returns LightweightTag vs AnnotatedTag correctly."""
        repo = Repository.init(tmp_path / "repo")
        commit_sha = make_commit_sha(repo)
        tagger = Identity(
            name="Tagger",
            email="tagger@example.com",
            timestamp=1234567890,
            tz_offset="+0000",
        )
        repo.tags.create_lightweight("lw", commit_sha)
        repo.tags.create_annotated("ann", commit_sha, "msg", tagger)

        assert isinstance(repo.tags.get("lw"), LightweightTag)
        assert isinstance(repo.tags.get("ann"), AnnotatedTag)
