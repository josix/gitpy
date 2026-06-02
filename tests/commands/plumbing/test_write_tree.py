"""Tests for write_tree_cmd plumbing command.

Reference hashes:
  empty tree -> 4b825dc642cb6eb9a060e54bf8d69288fbee4904
"""

from pathlib import Path

import pytest

from gitpy.commands.plumbing import write_tree_cmd
from gitpy.index.entry import IndexEntry
from gitpy.index.index import Index
from gitpy.objects.blob import Blob
from gitpy.repository import Repository

EMPTY_TREE_SHA = "4b825dc642cb6eb9a060e54bf8d69288fbee4904"
HELLO_BLOB_SHA = "ce013625030ba8dba906f756967f9e9ca394464a"


@pytest.fixture()
def repo(tmp_path: Path) -> Repository:
    return Repository.init(tmp_path)


class TestWriteTreeEmpty:
    def test_empty_index_produces_empty_tree(self, repo: Repository) -> None:
        """An empty index must produce the canonical empty-tree SHA."""
        sha = write_tree_cmd(repo)
        assert sha == EMPTY_TREE_SHA


class TestWriteTreeWithEntries:
    def _make_entry(self, path: str, sha: str, mode: int = 0o100644) -> IndexEntry:
        return IndexEntry(
            ctime_s=0,
            ctime_ns=0,
            mtime_s=0,
            mtime_ns=0,
            dev=0,
            ino=0,
            mode=mode,
            uid=0,
            gid=0,
            size=0,
            sha=sha,
            flags=min(len(path), 0xFFF),
            path=path,
        )

    def test_single_blob_entry(self, repo: Repository) -> None:
        """write_tree_cmd with a single staged file produces a readable tree."""
        blob = Blob(data=b"hello\n")
        blob_sha = repo.objects.write(blob)

        index = Index()
        index.add(self._make_entry("hello.txt", blob_sha))
        repo.index.write(index)

        sha = write_tree_cmd(repo)
        assert sha != EMPTY_TREE_SHA

        tree = repo.objects.read_tree(sha)
        assert len(tree.entries) == 1
        assert tree.entries[0].name == "hello.txt"
        assert tree.entries[0].sha == blob_sha

    def test_nested_path_creates_subtree(self, repo: Repository) -> None:
        """Nested paths create intermediate tree objects."""
        blob = Blob(data=b"data\n")
        blob_sha = repo.objects.write(blob)

        index = Index()
        index.add(self._make_entry("sub/file.txt", blob_sha))
        repo.index.write(index)

        root_sha = write_tree_cmd(repo)
        root_tree = repo.objects.read_tree(root_sha)
        assert len(root_tree.entries) == 1
        assert root_tree.entries[0].name == "sub"
        assert root_tree.entries[0].is_tree

        sub_tree = repo.objects.read_tree(root_tree.entries[0].sha)
        assert len(sub_tree.entries) == 1
        assert sub_tree.entries[0].name == "file.txt"
