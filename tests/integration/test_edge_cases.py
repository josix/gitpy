"""Edge-case integration tests.

Covers:
- Empty-repo status (no commits yet)
- Detached-HEAD commit
- Nested directories in write_tree
- Binary-file diff (NUL bytes)
- Reading packed-refs after ``git pack-refs`` (git-gated)
"""

import shutil
import subprocess
from pathlib import Path

import pytest

from gitpy.commands.porcelain.add import add
from gitpy.commands.porcelain.commit import commit
from gitpy.commands.porcelain.diff import diff
from gitpy.commands.porcelain.log import log
from gitpy.commands.porcelain.status import status
from gitpy.index.operations import write_tree
from gitpy.repository import Repository

# --------------------------------------------------------------------------- #
# helpers                                                                      #
# --------------------------------------------------------------------------- #


def _git_available() -> bool:
    return shutil.which("git") is not None


@pytest.fixture()
def repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Repository:
    """Gitpy repo with fixed identity."""
    monkeypatch.setenv("GIT_AUTHOR_NAME", "Edge Tester")
    monkeypatch.setenv("GIT_AUTHOR_EMAIL", "edge@example.com")
    monkeypatch.setenv("GIT_COMMITTER_NAME", "Edge Tester")
    monkeypatch.setenv("GIT_COMMITTER_EMAIL", "edge@example.com")
    return Repository.init(tmp_path / "repo")


# --------------------------------------------------------------------------- #
# Empty repo status                                                            #
# --------------------------------------------------------------------------- #


class TestEmptyRepoStatus:
    """Status commands on a brand-new (no-commit) repository."""

    def test_status_empty_repo_returns_zero(
        self, repo: Repository, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """status returns 0 and says nothing to commit."""
        assert status(repo) == 0
        captured = capsys.readouterr()
        assert "nothing to commit" in captured.out

    def test_head_unborn_raises_on_resolve(self, repo: Repository) -> None:
        """head.resolve raises ValueError before any commits."""
        with pytest.raises(ValueError):
            repo.head.resolve(repo.refs)

    def test_log_fails_gracefully_on_empty_repo(
        self, repo: Repository, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """log returns 1 when HEAD cannot be resolved."""
        result = log(repo, "HEAD")
        assert result == 1
        captured = capsys.readouterr()
        assert "fatal" in captured.out or result == 1

    def test_status_shows_untracked_files(
        self, repo: Repository, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Untracked files appear in status output."""
        (repo.worktree / "new_file.txt").write_text("hello\n")
        assert status(repo, short=True) == 0
        captured = capsys.readouterr()
        assert "new_file.txt" in captured.out


# --------------------------------------------------------------------------- #
# Detached HEAD commit                                                         #
# --------------------------------------------------------------------------- #


class TestDetachedHead:
    """Commits made while HEAD is detached."""

    def _setup_two_commits(self, repo: Repository) -> tuple[str, str]:
        """Create two commits and return their SHAs."""
        (repo.worktree / "f.txt").write_text("first\n")
        add(repo, ["f.txt"])
        commit(repo, "First")
        sha1 = repo.head.resolve(repo.refs)

        (repo.worktree / "f.txt").write_text("second\n")
        add(repo, ["f.txt"])
        commit(repo, "Second")
        sha2 = repo.head.resolve(repo.refs)

        return sha1, sha2

    def test_detach_head_at_first_commit(self, repo: Repository) -> None:
        """HEAD can be detached at an older commit."""
        sha1, _sha2 = self._setup_two_commits(repo)
        repo.head.set_detached(sha1)
        head = repo.head.read()
        assert head.is_detached
        assert head.target == sha1

    def test_commit_on_detached_head_advances_head(self, repo: Repository) -> None:
        """A commit on detached HEAD updates HEAD SHA directly."""
        sha1, _sha2 = self._setup_two_commits(repo)
        repo.head.set_detached(sha1)

        (repo.worktree / "f.txt").write_text("detached change\n")
        add(repo, ["f.txt"])
        commit(repo, "Detached commit")

        new_sha = repo.head.resolve(repo.refs)
        assert new_sha != sha1
        head = repo.head.read()
        assert head.is_detached

    def test_detached_head_log(
        self, repo: Repository, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """log works from a detached HEAD."""
        sha1, sha2 = self._setup_two_commits(repo)
        repo.head.set_detached(sha2)

        capsys.readouterr()
        assert log(repo, "HEAD", oneline=True) == 0
        captured = capsys.readouterr()
        assert "Second" in captured.out


# --------------------------------------------------------------------------- #
# Nested directories in write_tree                                             #
# --------------------------------------------------------------------------- #


class TestNestedDirWriteTree:
    """write_tree must produce nested tree objects for deep paths."""

    def test_write_tree_single_level(self, repo: Repository) -> None:
        """A single-level directory produces a sub-tree object."""
        (repo.worktree / "sub").mkdir()
        (repo.worktree / "sub" / "file.txt").write_text("deep\n")
        add(repo, ["sub/file.txt"])

        index = repo.index.read()
        tree_sha = write_tree(index, repo.objects)

        root_tree = repo.objects.read_tree(tree_sha)
        assert any(e.name == "sub" for e in root_tree.entries)

        sub_entry = next(e for e in root_tree.entries if e.name == "sub")
        sub_tree = repo.objects.read_tree(sub_entry.sha)
        assert any(e.name == "file.txt" for e in sub_tree.entries)

    def test_write_tree_deep_nesting(self, repo: Repository) -> None:
        """Deeply nested paths produce the correct tree hierarchy."""
        deep = repo.worktree / "a" / "b" / "c"
        deep.mkdir(parents=True)
        (deep / "leaf.txt").write_text("leaf\n")
        add(repo, ["a/b/c/leaf.txt"])

        index = repo.index.read()
        tree_sha = write_tree(index, repo.objects)

        # Walk a -> b -> c -> leaf.txt
        def get_subtree(sha: str, name: str) -> str:
            tree = repo.objects.read_tree(sha)
            entry = next(e for e in tree.entries if e.name == name)
            return entry.sha

        sha_b = get_subtree(tree_sha, "a")
        sha_c = get_subtree(sha_b, "b")
        sha_leaf_dir = get_subtree(sha_c, "c")

        leaf_tree = repo.objects.read_tree(sha_leaf_dir)
        assert any(e.name == "leaf.txt" for e in leaf_tree.entries)

    def test_commit_with_nested_dirs_round_trips(self, repo: Repository) -> None:
        """A commit containing nested directories can be checked out."""
        (repo.worktree / "src").mkdir()
        (repo.worktree / "src" / "main.py").write_text("print('hi')\n")
        (repo.worktree / "docs").mkdir()
        (repo.worktree / "docs" / "readme.md").write_text("# Docs\n")

        add(repo, ["src/main.py", "docs/readme.md"])
        commit(repo, "Add nested dirs")

        sha = repo.head.resolve(repo.refs)
        commit_obj = repo.objects.read_commit(sha)
        root_tree = repo.objects.read_tree(commit_obj.tree_sha)

        names = {e.name for e in root_tree.entries}
        assert "src" in names
        assert "docs" in names


# --------------------------------------------------------------------------- #
# Binary-file diff                                                             #
# --------------------------------------------------------------------------- #


class TestBinaryFileDiff:
    """diff handles binary files (NUL bytes) gracefully."""

    def test_diff_binary_file_shows_binary_marker(
        self, repo: Repository, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """diff prints a binary marker instead of unified-diff lines."""
        binary_data = b"binary\x00data\xff\xfe"
        (repo.worktree / "file.bin").write_bytes(binary_data)
        add(repo, ["file.bin"])
        commit(repo, "Add binary file")
        sha1 = repo.head.resolve(repo.refs)

        new_binary = b"changed\x00binary\xff"
        (repo.worktree / "file.bin").write_bytes(new_binary)
        add(repo, ["file.bin"])
        commit(repo, "Modify binary file")
        sha2 = repo.head.resolve(repo.refs)

        capsys.readouterr()
        assert diff(repo, [sha1, sha2]) == 0
        captured = capsys.readouterr()
        # Should mention the file but not attempt a text diff.
        assert "file.bin" in captured.out
        assert "Binary" in captured.out

    def test_diff_null_byte_in_text_shows_binary(
        self, repo: Repository, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """A file with a NUL byte is treated as binary."""
        (repo.worktree / "mixed.txt").write_bytes(b"text\x00with NUL")
        add(repo, ["mixed.txt"])
        commit(repo, "Add NUL file")
        sha1 = repo.head.resolve(repo.refs)

        (repo.worktree / "mixed.txt").write_bytes(b"changed\x00text")
        add(repo, ["mixed.txt"])
        commit(repo, "Change NUL file")
        sha2 = repo.head.resolve(repo.refs)

        capsys.readouterr()
        diff(repo, [sha1, sha2])
        captured = capsys.readouterr()
        assert "mixed.txt" in captured.out


# --------------------------------------------------------------------------- #
# Packed-refs after git pack-refs (git-gated)                                 #
# --------------------------------------------------------------------------- #


@pytest.mark.skipif(not _git_available(), reason="git not available")
class TestPackedRefs:
    """Reading packed-refs created by real ``git pack-refs``."""

    def test_gitpy_resolves_packed_ref(self, tmp_path: Path) -> None:
        """gitpy RefManager resolves a ref that exists only in packed-refs."""
        path = tmp_path / "repo"
        path.mkdir()
        subprocess.run(
            ["git", "init", "-b", "main", str(path)],
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["git", "config", "user.email", "t@t.com"],
            cwd=path,
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["git", "config", "user.name", "T"],
            cwd=path,
            check=True,
            capture_output=True,
        )
        (path / "f.txt").write_text("hi\n")
        subprocess.run(
            ["git", "add", "f.txt"], cwd=path, check=True, capture_output=True
        )
        subprocess.run(
            ["git", "commit", "-m", "initial"],
            cwd=path,
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["git", "pack-refs", "--all"],
            cwd=path,
            check=True,
            capture_output=True,
        )

        # Loose ref file must be gone (packed).
        assert not (path / ".git" / "refs" / "heads" / "main").exists()
        assert (path / ".git" / "packed-refs").exists()

        repo = Repository(path)
        sha = repo.refs.resolve("refs/heads/main")
        assert sha is not None
        assert len(sha) == 40

    def test_gitpy_status_works_with_packed_refs(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """status works on a repo whose refs are packed by git."""
        path = tmp_path / "repo"
        path.mkdir()
        subprocess.run(
            ["git", "init", "-b", "main", str(path)],
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["git", "config", "user.email", "t@t.com"],
            cwd=path,
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["git", "config", "user.name", "T"],
            cwd=path,
            check=True,
            capture_output=True,
        )
        (path / "f.txt").write_text("hello\n")
        subprocess.run(
            ["git", "add", "f.txt"], cwd=path, check=True, capture_output=True
        )
        subprocess.run(
            ["git", "commit", "-m", "initial"],
            cwd=path,
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["git", "pack-refs", "--all"],
            cwd=path,
            check=True,
            capture_output=True,
        )

        repo = Repository(path)
        assert status(repo) == 0
        captured = capsys.readouterr()
        assert "nothing to commit" in captured.out
