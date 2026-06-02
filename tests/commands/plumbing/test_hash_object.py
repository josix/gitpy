"""Tests for hash_object plumbing command.

Reference hashes (must match real Git):
  empty blob  -> e69de29bb2d1d6434b8b29ae775ad8c2e48c5391
  "hello\\n" blob -> ce013625030ba8dba906f756967f9e9ca394464a
"""

from pathlib import Path

import pytest

from gitpy.commands.plumbing import hash_object
from gitpy.repository import Repository

EMPTY_BLOB_SHA = "e69de29bb2d1d6434b8b29ae775ad8c2e48c5391"
HELLO_BLOB_SHA = "ce013625030ba8dba906f756967f9e9ca394464a"


@pytest.fixture()
def repo(tmp_path: Path) -> Repository:
    return Repository.init(tmp_path)


class TestHashObjectReferenceHashes:
    def test_empty_blob_sha(self, repo: Repository) -> None:
        """hash_object(b'') must equal the well-known empty-blob SHA."""
        sha = hash_object(repo, b"")
        assert sha == EMPTY_BLOB_SHA

    def test_hello_blob_sha(self, repo: Repository) -> None:
        """hash_object(b'hello\\n') must equal the well-known blob SHA."""
        sha = hash_object(repo, b"hello\n")
        assert sha == HELLO_BLOB_SHA


class TestHashObjectWriteFlag:
    def test_no_write_default(self, repo: Repository) -> None:
        """Without write=True, the object is not stored."""
        sha = hash_object(repo, b"hello\n")
        assert not repo.objects.exists(sha)

    def test_write_true_stores_object(self, repo: Repository) -> None:
        """write=True persists the object so it can be read back."""
        sha = hash_object(repo, b"hello\n", write=True)
        assert repo.objects.exists(sha)

    def test_written_object_readable(self, repo: Repository) -> None:
        """A written object can be retrieved and has correct data."""
        sha = hash_object(repo, b"hello\n", write=True)
        obj = repo.objects.read_blob(sha)
        assert obj.data == b"hello\n"

    def test_write_empty_blob(self, repo: Repository) -> None:
        """Persisting the empty blob produces the canonical empty-blob SHA."""
        sha = hash_object(repo, b"", write=True)
        assert sha == EMPTY_BLOB_SHA
        assert repo.objects.exists(sha)


class TestHashObjectTypeNames:
    def test_unknown_type_raises(self, repo: Repository) -> None:
        """Unknown type_name must raise ValueError."""
        with pytest.raises(ValueError, match="Unknown object type"):
            hash_object(repo, b"data", type_name="invalid")

    def test_explicit_blob_type(self, repo: Repository) -> None:
        """Explicitly specifying type_name='blob' still produces correct hash."""
        sha = hash_object(repo, b"hello\n", type_name="blob")
        assert sha == HELLO_BLOB_SHA
