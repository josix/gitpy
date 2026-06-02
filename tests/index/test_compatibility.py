"""Git binary compatibility tests.

These tests verify that gitpy can read indexes written by real Git and that
real Git can read indexes written by gitpy.  The tests are skipped when Git
is not available in the environment.
"""

import shutil
import subprocess
from pathlib import Path

import pytest

from gitpy.index.entry import IndexEntry
from gitpy.index.index import Index, IndexFile


def _git_available() -> bool:
    return shutil.which("git") is not None


@pytest.fixture()
def git_repo(tmp_path: Path) -> Path:
    """Initialise a real Git repository in *tmp_path*."""
    subprocess.run(
        ["git", "init", "-b", "main", str(tmp_path)],
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.email", "test@example.com"],
        cwd=tmp_path,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Test"],
        cwd=tmp_path,
        check=True,
        capture_output=True,
    )
    return tmp_path


@pytest.mark.skipif(not _git_available(), reason="git not available")
class TestReadGitIndex:
    def test_git_add_then_gitpy_reads_mode(self, git_repo: Path) -> None:
        """gitpy can read an index produced by git add."""
        f = git_repo / "test.txt"
        f.write_text("hello\n")
        subprocess.run(["git", "add", "test.txt"], cwd=git_repo, check=True)

        idx_file = IndexFile(git_repo / ".git")
        idx = idx_file.read()

        assert "test.txt" in idx
        entry = idx.get("test.txt")
        assert entry is not None
        assert entry.mode == 0o100644

    def test_git_add_multiple_files(self, git_repo: Path) -> None:
        """gitpy reads all entries from a multi-file git-created index."""
        for name in ["a.txt", "b.txt", "c.txt"]:
            (git_repo / name).write_text(f"content of {name}\n")
        subprocess.run(["git", "add", "."], cwd=git_repo, check=True)

        idx_file = IndexFile(git_repo / ".git")
        idx = idx_file.read()

        assert len(idx) == 3
        for name in ["a.txt", "b.txt", "c.txt"]:
            assert name in idx


@pytest.mark.skipif(not _git_available(), reason="git not available")
class TestWriteGitReadable:
    def test_gitpy_index_readable_by_git_ls_files(self, git_repo: Path) -> None:
        """git ls-files --stage can read an index written by gitpy."""
        # We need the blob object to already exist so git ls-files is happy.
        blob_data = b"hello\n"
        blob_sha = "ce013625030ba8dba906f756967f9e9ca394464a"

        # Write the blob into .git/objects via git hash-object so Git knows about it.
        result = subprocess.run(
            ["git", "hash-object", "-w", "--stdin"],
            input=blob_data,
            cwd=git_repo,
            capture_output=True,
            check=True,
        )
        written_sha = result.stdout.decode().strip()
        assert written_sha == blob_sha

        # Build index with gitpy.
        idx = Index()
        idx.add(
            IndexEntry(
                ctime_s=0,
                ctime_ns=0,
                mtime_s=0,
                mtime_ns=0,
                dev=0,
                ino=0,
                mode=0o100644,
                uid=0,
                gid=0,
                size=len(blob_data),
                sha=blob_sha,
                flags=len("test.txt"),
                path="test.txt",
            )
        )

        idx_file = IndexFile(git_repo / ".git")
        idx_file.write(idx)

        ls_result = subprocess.run(
            ["git", "ls-files", "--stage"],
            cwd=git_repo,
            capture_output=True,
            text=True,
            check=True,
        )
        assert "test.txt" in ls_result.stdout
        assert blob_sha in ls_result.stdout
