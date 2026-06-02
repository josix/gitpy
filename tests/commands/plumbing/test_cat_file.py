"""Tests for cat_file plumbing command.

Output is collected via an injected io.BytesIO stream.
"""

import io
from pathlib import Path

import pytest

from gitpy.commands.plumbing import cat_file, hash_object
from gitpy.objects.commit import Commit, Identity
from gitpy.objects.tree import Tree, TreeEntry
from gitpy.repository import Repository

EMPTY_BLOB_SHA = "e69de29bb2d1d6434b8b29ae775ad8c2e48c5391"
HELLO_BLOB_SHA = "ce013625030ba8dba906f756967f9e9ca394464a"
EMPTY_TREE_SHA = "4b825dc642cb6eb9a060e54bf8d69288fbee4904"


@pytest.fixture()
def repo(tmp_path: Path) -> Repository:
    return Repository.init(tmp_path)


def _out() -> io.BytesIO:
    return io.BytesIO()


class TestCatFileType:
    def test_blob_type(self, repo: Repository) -> None:
        """-t on a blob returns 'blob'."""
        sha = hash_object(repo, b"hello\n", write=True)
        out = _out()
        rc = cat_file(repo, sha, show_type=True, out=out)
        assert rc == 0
        assert out.getvalue() == b"blob\n"

    def test_tree_type(self, repo: Repository) -> None:
        """-t on an empty tree returns 'tree'."""
        tree = Tree(entries=[])
        sha = repo.objects.write(tree)
        out = _out()
        rc = cat_file(repo, sha, show_type=True, out=out)
        assert rc == 0
        assert out.getvalue() == b"tree\n"

    def test_commit_type(self, repo: Repository) -> None:
        """-t on a commit returns 'commit'."""
        tree = Tree(entries=[])
        tree_sha = repo.objects.write(tree)
        identity = Identity.now("Test", "test@test.com")
        commit = Commit(
            tree_sha=tree_sha,
            parent_shas=[],
            author=identity,
            committer=identity,
            message="init",
        )
        sha = repo.objects.write(commit)
        out = _out()
        rc = cat_file(repo, sha, show_type=True, out=out)
        assert rc == 0
        assert out.getvalue() == b"commit\n"


class TestCatFileSize:
    def test_blob_size(self, repo: Repository) -> None:
        """-s on a blob returns its byte length."""
        data = b"hello\n"
        sha = hash_object(repo, data, write=True)
        out = _out()
        rc = cat_file(repo, sha, show_size=True, out=out)
        assert rc == 0
        assert out.getvalue() == f"{len(data)}\n".encode()

    def test_empty_blob_size(self, repo: Repository) -> None:
        """-s on empty blob returns '0'."""
        sha = hash_object(repo, b"", write=True)
        out = _out()
        rc = cat_file(repo, sha, show_size=True, out=out)
        assert rc == 0
        assert out.getvalue() == b"0\n"


class TestCatFilePrettyPrint:
    def test_blob_pretty_print(self, repo: Repository) -> None:
        """-p on a blob outputs raw bytes."""
        data = b"hello\n"
        sha = hash_object(repo, data, write=True)
        out = _out()
        rc = cat_file(repo, sha, pretty=True, out=out)
        assert rc == 0
        assert out.getvalue() == data

    def test_empty_blob_pretty_print(self, repo: Repository) -> None:
        """-p on empty blob outputs nothing."""
        sha = hash_object(repo, b"", write=True)
        out = _out()
        rc = cat_file(repo, sha, pretty=True, out=out)
        assert rc == 0
        assert out.getvalue() == b""

    def test_tree_pretty_print(self, repo: Repository) -> None:
        """-p on a tree lists entries in ls-tree format."""
        blob_sha = hash_object(repo, b"data\n", write=True)
        tree = Tree(entries=[TreeEntry(mode="100644", name="file.txt", sha=blob_sha)])
        tree_sha = repo.objects.write(tree)
        out = _out()
        rc = cat_file(repo, tree_sha, pretty=True, out=out)
        assert rc == 0
        output = out.getvalue().decode()
        assert "file.txt" in output
        assert blob_sha in output
        assert "100644" in output

    def test_commit_pretty_print(self, repo: Repository) -> None:
        """-p on a commit serialises commit fields."""
        tree = Tree(entries=[])
        tree_sha = repo.objects.write(tree)
        identity = Identity.now("Test", "test@test.com")
        commit = Commit(
            tree_sha=tree_sha,
            parent_shas=[],
            author=identity,
            committer=identity,
            message="init\n",
        )
        sha = repo.objects.write(commit)
        out = _out()
        rc = cat_file(repo, sha, pretty=True, out=out)
        assert rc == 0
        output = out.getvalue().decode()
        assert f"tree {tree_sha}" in output
        assert "author Test" in output


class TestCatFileTypeMismatch:
    def test_type_mismatch_returns_1(self, repo: Repository) -> None:
        """Requesting wrong type for an object returns exit code 1."""
        blob_sha = hash_object(repo, b"hello\n", write=True)
        out = _out()
        rc = cat_file(repo, blob_sha, expected_type="tree", out=out)
        assert rc == 1
        assert b"not a tree" in out.getvalue()

    def test_correct_type_returns_0(self, repo: Repository) -> None:
        """Requesting correct type for an object returns exit code 0."""
        blob_sha = hash_object(repo, b"hello\n", write=True)
        out = _out()
        rc = cat_file(repo, blob_sha, expected_type="blob", out=out)
        assert rc == 0

    def test_missing_object_returns_1(self, repo: Repository) -> None:
        """Non-existent object returns exit code 1."""
        out = _out()
        rc = cat_file(repo, "deadbeef" * 5, show_type=True, out=out)
        assert rc == 1


class TestCatFileRefResolution:
    def test_resolve_via_ref(self, repo: Repository) -> None:
        """cat_file resolves a ref name to the underlying object."""
        tree = Tree(entries=[])
        tree_sha = repo.objects.write(tree)
        identity = Identity.now("Test", "test@test.com")
        commit = Commit(
            tree_sha=tree_sha,
            parent_shas=[],
            author=identity,
            committer=identity,
            message="init\n",
        )
        commit_sha = repo.objects.write(commit)
        repo.refs.write("refs/heads/main", commit_sha)

        out = _out()
        rc = cat_file(repo, "refs/heads/main", show_type=True, out=out)
        assert rc == 0
        assert out.getvalue() == b"commit\n"
