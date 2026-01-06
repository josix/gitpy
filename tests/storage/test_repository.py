"""Tests for Repository class."""

from pathlib import Path

import pytest

from gitpy.repository import Repository


class TestRepositoryInit:
    """Tests for Repository.init()."""

    def test_init_creates_structure(self, tmp_path: Path) -> None:
        """Init creates required directories and files."""
        Repository.init(tmp_path / "myrepo")

        git_dir = tmp_path / "myrepo" / ".git"
        assert git_dir.exists()
        assert (git_dir / "objects").is_dir()
        assert (git_dir / "objects" / "info").is_dir()
        assert (git_dir / "objects" / "pack").is_dir()
        assert (git_dir / "refs" / "heads").is_dir()
        assert (git_dir / "refs" / "tags").is_dir()
        assert (git_dir / "info").is_dir()

    def test_init_creates_head(self, tmp_path: Path) -> None:
        """Init creates HEAD pointing to main."""
        Repository.init(tmp_path / "repo")

        head = tmp_path / "repo" / ".git" / "HEAD"
        assert head.read_text() == "ref: refs/heads/main\n"

    def test_init_creates_config(self, tmp_path: Path) -> None:
        """Init creates config file."""
        Repository.init(tmp_path / "repo")

        config = tmp_path / "repo" / ".git" / "config"
        content = config.read_text()
        assert "[core]" in content
        assert "repositoryformatversion = 0" in content
        assert "bare = false" in content

    def test_init_creates_description(self, tmp_path: Path) -> None:
        """Init creates description file."""
        Repository.init(tmp_path / "repo")

        desc = tmp_path / "repo" / ".git" / "description"
        assert desc.exists()
        assert "Unnamed repository" in desc.read_text()

    def test_init_creates_exclude(self, tmp_path: Path) -> None:
        """Init creates info/exclude file."""
        Repository.init(tmp_path / "repo")

        exclude = tmp_path / "repo" / ".git" / "info" / "exclude"
        assert exclude.exists()

    def test_init_bare(self, tmp_path: Path) -> None:
        """Bare init creates repository in path itself."""
        Repository.init(tmp_path / "bare.git", bare=True)

        assert (tmp_path / "bare.git" / "objects").is_dir()
        assert (tmp_path / "bare.git" / "HEAD").exists()

        config = (tmp_path / "bare.git" / "config").read_text()
        assert "bare = true" in config

    def test_init_already_exists(self, tmp_path: Path) -> None:
        """Init on existing repo raises error."""
        Repository.init(tmp_path / "repo")

        with pytest.raises(ValueError, match="Already a git repository"):
            Repository.init(tmp_path / "repo")

    def test_init_returns_repository(self, tmp_path: Path) -> None:
        """Init returns usable Repository instance."""
        repo = Repository.init(tmp_path / "repo")

        assert isinstance(repo, Repository)
        assert repo.worktree == tmp_path / "repo"
        assert repo.git_dir == tmp_path / "repo" / ".git"


class TestRepositoryOpen:
    """Tests for opening existing repositories."""

    def test_open_valid_repo(self, tmp_path: Path) -> None:
        """Open existing repository."""
        Repository.init(tmp_path / "repo")

        repo = Repository(tmp_path / "repo")
        assert repo.worktree == tmp_path / "repo"

    def test_open_invalid_path(self, tmp_path: Path) -> None:
        """Open non-repo raises error."""
        with pytest.raises(ValueError, match="Not a git repository"):
            Repository(tmp_path / "notarepo")

    def test_open_with_git_dir(self, tmp_path: Path) -> None:
        """Open with explicit git_dir."""
        Repository.init(tmp_path / "repo")

        repo = Repository(tmp_path / "repo", git_dir=tmp_path / "repo" / ".git")
        assert repo.git_dir == tmp_path / "repo" / ".git"


class TestRepositoryFind:
    """Tests for Repository.find()."""

    def test_find_from_root(self, tmp_path: Path) -> None:
        """Find repo from root directory."""
        Repository.init(tmp_path / "project")

        found = Repository.find(tmp_path / "project")
        assert found.worktree == tmp_path / "project"

    def test_find_from_subdirectory(self, tmp_path: Path) -> None:
        """Find repo from nested subdirectory."""
        Repository.init(tmp_path / "project")

        subdir = tmp_path / "project" / "src" / "deep" / "nested"
        subdir.mkdir(parents=True)

        found = Repository.find(subdir)
        assert found.worktree == tmp_path / "project"

    def test_find_not_in_repo(self, tmp_path: Path) -> None:
        """Find outside repo raises error."""
        with pytest.raises(ValueError, match="Not a git repository"):
            Repository.find(tmp_path)

    def test_find_default_cwd(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Find with no argument uses cwd."""
        Repository.init(tmp_path / "repo")
        monkeypatch.chdir(tmp_path / "repo")

        found = Repository.find()
        assert found.worktree == tmp_path / "repo"


class TestRepositoryObjects:
    """Tests for Repository.objects integration."""

    def test_objects_database_available(self, tmp_path: Path) -> None:
        """Repository has objects database."""
        repo = Repository.init(tmp_path / "repo")

        assert repo.objects is not None

    def test_write_and_read_through_repo(self, tmp_path: Path) -> None:
        """Can read/write objects through repository."""
        from gitpy.objects import Blob

        repo = Repository.init(tmp_path / "repo")

        blob = Blob(data=b"test content")
        sha = repo.objects.write(blob)

        result = repo.objects.read_blob(sha)
        assert result.data == b"test content"


class TestRepositoryRepr:
    """Tests for Repository string representation."""

    def test_repr(self, tmp_path: Path) -> None:
        """Repository has useful repr."""
        repo = Repository.init(tmp_path / "myrepo")
        assert "myrepo" in repr(repo)
        assert "Repository" in repr(repo)
