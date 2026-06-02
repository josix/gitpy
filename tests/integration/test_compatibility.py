"""Bidirectional Git compatibility tests.

(a) gitpy creates repo+commit; real ``git log``, ``git status``, and
    ``git fsck`` accept it.
(b) real git creates repo+commit+``git pack-refs``; gitpy reads it via
    log/cat-file/packed-refs resolution.
(c) Reference hashes flow identically through both engines.
(d) Pack interop: gitpy writes a pack; ``git verify-pack`` / ``git cat-file``
    reads gitpy objects.  gitpy reads a pack produced by ``git gc``.

All tests in this module are skipped when ``git`` is not available.
"""

import io
import subprocess
from pathlib import Path

import pytest

from gitpy.commands.plumbing.cat_file import cat_file
from gitpy.commands.plumbing.hash_object import hash_object
from gitpy.commands.porcelain.add import add
from gitpy.commands.porcelain.commit import commit
from gitpy.commands.porcelain.log import log
from gitpy.objects.tree import Tree
from gitpy.repository import Repository

# --------------------------------------------------------------------------- #
# helpers                                                                      #
# --------------------------------------------------------------------------- #

HELLO_BLOB_SHA = "ce013625030ba8dba906f756967f9e9ca394464a"
EMPTY_BLOB_SHA = "e69de29bb2d1d6434b8b29ae775ad8c2e48c5391"
EMPTY_TREE_SHA = "4b825dc642cb6eb9a060e54bf8d69288fbee4904"

pytestmark = pytest.mark.skipif(
    not __import__("shutil").which("git"), reason="git not available"
)


def _git(*args: str, cwd: Path) -> subprocess.CompletedProcess[str]:
    """Run a git sub-command, raising on non-zero exit."""
    return subprocess.run(
        ["git", *args],
        cwd=cwd,
        check=True,
        capture_output=True,
        text=True,
    )


def _git_init(path: Path) -> None:
    """Initialise a real git repo with test identity."""
    subprocess.run(
        ["git", "init", "-b", "main", str(path)],
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.email", "test@example.com"],
        cwd=path,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Test"],
        cwd=path,
        check=True,
        capture_output=True,
    )


# --------------------------------------------------------------------------- #
# (a) gitpy creates repo; real git accepts it                                 #
# --------------------------------------------------------------------------- #


class TestGitpyRepoReadableByGit:
    """gitpy-created repos must be accepted by real git tooling."""

    @pytest.fixture()
    def gitpy_committed_repo(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> Repository:
        """A gitpy repo with one commit."""
        monkeypatch.setenv("GIT_AUTHOR_NAME", "Test User")
        monkeypatch.setenv("GIT_AUTHOR_EMAIL", "test@example.com")
        monkeypatch.setenv("GIT_COMMITTER_NAME", "Test User")
        monkeypatch.setenv("GIT_COMMITTER_EMAIL", "test@example.com")
        repo = Repository.init(tmp_path / "repo")
        (repo.worktree / "hello.txt").write_text("hello\n")
        add(repo, ["hello.txt"])
        commit(repo, "Initial commit")
        return repo

    def test_git_log_accepts_gitpy_repo(self, gitpy_committed_repo: Repository) -> None:
        """``git log`` returns exit code 0 on a gitpy-created repo."""
        result = _git("log", "--oneline", cwd=gitpy_committed_repo.worktree)
        assert result.returncode == 0
        assert "Initial commit" in result.stdout

    def test_git_status_accepts_gitpy_repo(
        self, gitpy_committed_repo: Repository
    ) -> None:
        """``git status`` returns exit code 0 on a gitpy-created repo."""
        result = _git("status", cwd=gitpy_committed_repo.worktree)
        assert result.returncode == 0

    def test_git_fsck_accepts_gitpy_repo(
        self, gitpy_committed_repo: Repository
    ) -> None:
        """``git fsck`` returns exit code 0 — no object errors."""
        result = _git("fsck", "--strict", cwd=gitpy_committed_repo.worktree)
        assert result.returncode == 0


# --------------------------------------------------------------------------- #
# (b) real git creates repo; gitpy reads it                                   #
# --------------------------------------------------------------------------- #


class TestGitRepoReadableByGitpy:
    """gitpy must be able to read repos created by real git."""

    @pytest.fixture()
    def real_git_repo_path(self, tmp_path: Path) -> Path:
        """A real git repo with one commit and packed refs."""
        path = tmp_path / "git_repo"
        path.mkdir()
        _git_init(path)

        (path / "readme.txt").write_text("from real git\n")
        _git("add", "readme.txt", cwd=path)
        _git("commit", "-m", "Real git commit", cwd=path)
        # Pack refs so gitpy must parse packed-refs.
        _git("pack-refs", "--all", cwd=path)
        return path

    def test_gitpy_log_reads_real_git_repo(self, real_git_repo_path: Path) -> None:
        """gitpy log can walk a commit created by real git."""
        repo = Repository(real_git_repo_path)
        sha = repo.refs.resolve("refs/heads/main")
        assert sha is not None and len(sha) == 40

        commit_obj = repo.objects.read_commit(sha)
        assert "Real git commit" in commit_obj.message

    def test_gitpy_log_command_reads_real_git_repo(
        self, real_git_repo_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """The gitpy log command works on a real-git repo."""
        repo = Repository(real_git_repo_path)
        assert log(repo, "HEAD", oneline=True) == 0
        captured = capsys.readouterr()
        assert "Real git commit" in captured.out

    def test_gitpy_cat_file_reads_real_git_blob(self, real_git_repo_path: Path) -> None:
        """cat-file retrieves a blob originally written by real git."""
        repo = Repository(real_git_repo_path)
        sha = repo.refs.resolve("refs/heads/main")
        assert sha is not None
        commit_obj = repo.objects.read_commit(sha)
        tree = repo.objects.read_tree(commit_obj.tree_sha)
        blob_entry = tree.entries[0]

        buf = io.BytesIO()
        assert cat_file(repo, blob_entry.sha, pretty=True, out=buf) == 0
        assert buf.getvalue() == b"from real git\n"

    def test_gitpy_reads_packed_refs(self, real_git_repo_path: Path) -> None:
        """RefManager resolves refs from packed-refs (created by git pack-refs)."""
        assert (real_git_repo_path / ".git" / "packed-refs").exists()
        repo = Repository(real_git_repo_path)
        # After pack-refs, refs/heads/main exists only in packed-refs.
        sha = repo.refs.resolve("refs/heads/main")
        assert sha is not None and len(sha) == 40


# --------------------------------------------------------------------------- #
# (c) Reference hash identity                                                  #
# --------------------------------------------------------------------------- #


class TestReferenceHashIdentity:
    """Verify that known reference SHAs match between gitpy and real git."""

    def test_empty_blob_sha_gitpy(self, tmp_path: Path) -> None:
        """gitpy produces the canonical empty-blob SHA."""
        repo = Repository.init(tmp_path / "repo")
        sha = hash_object(repo, b"", type_name="blob", write=False)
        assert sha == EMPTY_BLOB_SHA

    def test_hello_blob_sha_gitpy(self, tmp_path: Path) -> None:
        """gitpy produces the canonical ``hello\\n`` blob SHA."""
        repo = Repository.init(tmp_path / "repo")
        sha = hash_object(repo, b"hello\n", type_name="blob", write=False)
        assert sha == HELLO_BLOB_SHA

    def test_empty_blob_sha_git(self) -> None:
        """real git hash-object produces the canonical empty-blob SHA."""
        result = subprocess.run(
            ["git", "hash-object", "--stdin"],
            input=b"",
            capture_output=True,
            check=True,
        )
        assert result.stdout.decode().strip() == EMPTY_BLOB_SHA

    def test_hello_blob_sha_git(self) -> None:
        """real git hash-object produces the canonical ``hello\\n`` SHA."""
        result = subprocess.run(
            ["git", "hash-object", "--stdin"],
            input=b"hello\n",
            capture_output=True,
            check=True,
        )
        assert result.stdout.decode().strip() == HELLO_BLOB_SHA

    def test_gitpy_hash_matches_git(self, tmp_path: Path) -> None:
        """gitpy hash-object output == git hash-object for arbitrary data."""
        data = b"The quick brown fox\n"
        repo = Repository.init(tmp_path / "repo")
        gitpy_sha = hash_object(repo, data, type_name="blob", write=False)

        result = subprocess.run(
            ["git", "hash-object", "--stdin"],
            input=data,
            capture_output=True,
            check=True,
        )
        git_sha = result.stdout.decode().strip()
        assert gitpy_sha == git_sha

    def test_empty_tree_sha_gitpy(self, tmp_path: Path) -> None:
        """gitpy produces the canonical empty-tree SHA."""
        repo = Repository.init(tmp_path / "repo")
        empty_tree = Tree(entries=[])
        sha = repo.objects.hash_object(empty_tree, write=False)
        assert sha == EMPTY_TREE_SHA

    def test_empty_tree_sha_git(self) -> None:
        """real git produces the canonical empty-tree SHA via hash-object."""
        # Write the empty tree object from the known canonical bytes.
        # The raw content of an empty tree is simply an empty byte string.
        result = subprocess.run(
            ["git", "hash-object", "-t", "tree", "--stdin"],
            input=b"",
            capture_output=True,
            check=True,
        )
        assert result.stdout.decode().strip() == EMPTY_TREE_SHA


# --------------------------------------------------------------------------- #
# (d) Pack interop                                                             #
# --------------------------------------------------------------------------- #


class TestPackInterop:
    """Pack file interoperability between gitpy and real git."""

    @pytest.fixture()
    def gitpy_packed_repo(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> Repository:
        """A gitpy repo with objects repacked into a single pack file."""
        monkeypatch.setenv("GIT_AUTHOR_NAME", "Pack Tester")
        monkeypatch.setenv("GIT_AUTHOR_EMAIL", "pack@example.com")
        monkeypatch.setenv("GIT_COMMITTER_NAME", "Pack Tester")
        monkeypatch.setenv("GIT_COMMITTER_EMAIL", "pack@example.com")

        repo = Repository.init(tmp_path / "pack_repo")
        (repo.worktree / "data.txt").write_text("pack content\n")
        add(repo, ["data.txt"])
        commit(repo, "Pack test commit")
        repo.objects.repack(gc=False)
        return repo

    def test_git_verify_pack_reads_gitpy_pack(
        self, gitpy_packed_repo: Repository
    ) -> None:
        """``git verify-pack`` accepts a pack file produced by gitpy."""
        pack_dir = gitpy_packed_repo.git_dir / "objects" / "pack"
        pack_files = list(pack_dir.glob("*.pack"))
        assert pack_files, "Expected at least one .pack file"

        result = subprocess.run(
            ["git", "verify-pack", "-v", str(pack_files[0])],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, (
            f"git verify-pack failed:\nstdout: {result.stdout}\nstderr: {result.stderr}"
        )

    def test_git_cat_file_reads_gitpy_pack(self, gitpy_packed_repo: Repository) -> None:
        """``git cat-file`` can extract the commit object from a gitpy pack."""
        sha = gitpy_packed_repo.refs.resolve("refs/heads/main")
        assert sha is not None
        result = _git("cat-file", "-t", sha, cwd=gitpy_packed_repo.worktree)
        assert result.stdout.strip() == "commit"

    def test_gitpy_reads_git_gc_pack(self, tmp_path: Path) -> None:
        """gitpy ObjectDatabase reads objects from a pack created by ``git gc``."""
        # Build a real git repo with a commit, then gc to create a pack.
        path = tmp_path / "gc_repo"
        path.mkdir()
        _git_init(path)
        (path / "file.txt").write_text("gc test\n")
        _git("add", "file.txt", cwd=path)
        _git("commit", "-m", "GC test commit", cwd=path)
        # git gc creates pack files from loose objects.
        _git("gc", "--quiet", cwd=path)

        # Verify pack files were created.
        pack_dir = path / ".git" / "objects" / "pack"
        pack_files = list(pack_dir.glob("*.pack"))
        assert pack_files, "git gc should have produced at least one pack file"

        # Now let gitpy read the commit via the pack.
        repo = Repository(path)
        repo.objects.reload_packs()
        sha = repo.refs.resolve("refs/heads/main")
        assert sha is not None
        commit_obj = repo.objects.read_commit(sha)
        assert "GC test commit" in commit_obj.message
