"""Tests for ls_tree plumbing command."""

import io
from pathlib import Path

import pytest

from gitpy.commands.plumbing import hash_object, ls_tree
from gitpy.objects.commit import Commit, Identity
from gitpy.objects.tree import Tree, TreeEntry
from gitpy.repository import Repository

EMPTY_TREE_SHA = "4b825dc642cb6eb9a060e54bf8d69288fbee4904"


@pytest.fixture()
def repo(tmp_path: Path) -> Repository:
    return Repository.init(tmp_path)


def _out() -> io.BytesIO:
    return io.BytesIO()


class TestLsTreeFlatListing:
    def test_empty_tree(self, repo: Repository) -> None:
        """ls_tree on an empty tree produces no output."""
        tree = Tree(entries=[])
        tree_sha = repo.objects.write(tree)
        out = _out()
        rc = ls_tree(repo, tree_sha, out=out)
        assert rc == 0
        assert out.getvalue() == b""

    def test_single_blob_entry(self, repo: Repository) -> None:
        """Single file entry is listed with mode, type, sha, and name."""
        blob_sha = hash_object(repo, b"content\n", write=True)
        tree = Tree(entries=[TreeEntry(mode="100644", name="file.txt", sha=blob_sha)])
        tree_sha = repo.objects.write(tree)
        out = _out()
        rc = ls_tree(repo, tree_sha, out=out)
        assert rc == 0
        output = out.getvalue().decode()
        assert "100644 blob" in output
        assert blob_sha in output
        assert "file.txt" in output

    def test_multiple_entries_sorted(self, repo: Repository) -> None:
        """Multiple entries are listed in Git sort order."""
        sha_a = hash_object(repo, b"a\n", write=True)
        sha_b = hash_object(repo, b"b\n", write=True)
        tree = Tree(
            entries=[
                TreeEntry(mode="100644", name="b.txt", sha=sha_b),
                TreeEntry(mode="100644", name="a.txt", sha=sha_a),
            ]
        )
        tree_sha = repo.objects.write(tree)
        out = _out()
        rc = ls_tree(repo, tree_sha, out=out)
        assert rc == 0
        lines = out.getvalue().decode().splitlines()
        assert len(lines) == 2
        assert "a.txt" in lines[0]
        assert "b.txt" in lines[1]


class TestLsTreeRecursive:
    def test_recursive_listing(self, repo: Repository) -> None:
        """Recursive listing traverses into subdirectories."""
        blob_sha = hash_object(repo, b"nested\n", write=True)
        subtree = Tree(
            entries=[TreeEntry(mode="100644", name="nested.txt", sha=blob_sha)]
        )
        subtree_sha = repo.objects.write(subtree)
        root = Tree(entries=[TreeEntry(mode="40000", name="subdir", sha=subtree_sha)])
        root_sha = repo.objects.write(root)

        out = _out()
        rc = ls_tree(repo, root_sha, recursive=True, out=out)
        assert rc == 0
        output = out.getvalue().decode()
        assert "subdir/nested.txt" in output

    def test_recursive_no_tree_entry_by_default(self, repo: Repository) -> None:
        """In recursive mode, tree entries are not printed by default."""
        blob_sha = hash_object(repo, b"content\n", write=True)
        subtree = Tree(entries=[TreeEntry(mode="100644", name="f.txt", sha=blob_sha)])
        subtree_sha = repo.objects.write(subtree)
        root = Tree(entries=[TreeEntry(mode="40000", name="sub", sha=subtree_sha)])
        root_sha = repo.objects.write(root)

        out = _out()
        rc = ls_tree(repo, root_sha, recursive=True, out=out)
        assert rc == 0
        lines = out.getvalue().decode().splitlines()
        # Only the blob should be listed.
        assert all("tree" not in line for line in lines)
        assert any("f.txt" in line for line in lines)

    def test_recursive_with_trees_flag(self, repo: Repository) -> None:
        """With trees=True, tree entries are also emitted during recursion."""
        blob_sha = hash_object(repo, b"content\n", write=True)
        subtree = Tree(entries=[TreeEntry(mode="100644", name="f.txt", sha=blob_sha)])
        subtree_sha = repo.objects.write(subtree)
        root = Tree(entries=[TreeEntry(mode="40000", name="sub", sha=subtree_sha)])
        root_sha = repo.objects.write(root)

        out = _out()
        rc = ls_tree(repo, root_sha, recursive=True, trees=True, out=out)
        assert rc == 0
        lines = out.getvalue().decode().splitlines()
        assert any("tree" in line and "sub" in line for line in lines)
        assert any("f.txt" in line for line in lines)


class TestLsTreeCommitResolution:
    def test_ls_tree_on_commit(self, repo: Repository) -> None:
        """ls_tree accepts a commit SHA and lists the commit's tree."""
        blob_sha = hash_object(repo, b"hello\n", write=True)
        tree = Tree(entries=[TreeEntry(mode="100644", name="readme.txt", sha=blob_sha)])
        tree_sha = repo.objects.write(tree)
        identity = Identity.now("Test", "test@test.com")
        commit = Commit(
            tree_sha=tree_sha,
            parent_shas=[],
            author=identity,
            committer=identity,
            message="initial\n",
        )
        commit_sha = repo.objects.write(commit)

        out = _out()
        rc = ls_tree(repo, commit_sha, out=out)
        assert rc == 0
        output = out.getvalue().decode()
        assert "readme.txt" in output

    def test_ls_tree_on_ref(self, repo: Repository) -> None:
        """ls_tree accepts a ref name and resolves it through a commit."""
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
        rc = ls_tree(repo, "refs/heads/main", out=out)
        assert rc == 0


class TestLsTreeErrors:
    def test_invalid_tree_ish_returns_1(self, repo: Repository) -> None:
        """Unknown ref/sha returns exit code 1."""
        out = _out()
        rc = ls_tree(repo, "nonexistent", out=out)
        assert rc == 1
