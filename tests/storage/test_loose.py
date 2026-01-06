"""Tests for LooseObjectStore."""

import hashlib
import zlib
from pathlib import Path

import pytest

from gitpy.objects import Blob, create_object_data
from gitpy.storage.loose import LooseObjectStore


class TestLooseObjectStore:
    """Tests for LooseObjectStore class."""

    @pytest.fixture
    def store(self, tmp_path: Path) -> LooseObjectStore:
        """Create a store with temporary git directory."""
        git_dir = tmp_path / ".git"
        git_dir.mkdir()
        (git_dir / "objects").mkdir()
        return LooseObjectStore(git_dir)

    def test_object_path(self, store: LooseObjectStore) -> None:
        """SHA maps to correct path."""
        sha = "8ab686eafeb1f44702738c8b0f24f2567c36da6d"
        path = store._object_path(sha)

        assert path.parent.name == "8a"
        assert path.name == "b686eafeb1f44702738c8b0f24f2567c36da6d"

    def test_object_path_invalid_sha(self, store: LooseObjectStore) -> None:
        """Invalid SHA length raises error."""
        with pytest.raises(ValueError, match="Invalid SHA length"):
            store._object_path("abc123")

    def test_exists_not_found(self, store: LooseObjectStore) -> None:
        """Non-existent object returns False."""
        sha = "0" * 40
        assert store.exists(sha) is False

    def test_write_and_read(self, store: LooseObjectStore) -> None:
        """Write object and read it back."""
        blob = Blob(data=b"test content")
        data = create_object_data(blob)
        sha = hashlib.sha1(data, usedforsecurity=False).hexdigest()

        store.write(sha, data)

        assert store.exists(sha)
        assert store.read(sha) == data

    def test_write_creates_directory(self, store: LooseObjectStore) -> None:
        """Write creates subdirectory if needed."""
        blob = Blob(data=b"test")
        data = create_object_data(blob)
        sha = hashlib.sha1(data, usedforsecurity=False).hexdigest()

        path = store.write(sha, data)

        assert path.exists()
        assert path.parent.name == sha[:2]

    def test_write_is_idempotent(self, store: LooseObjectStore) -> None:
        """Writing same object twice is safe."""
        blob = Blob(data=b"test")
        data = create_object_data(blob)
        sha = hashlib.sha1(data, usedforsecurity=False).hexdigest()

        path1 = store.write(sha, data)
        path2 = store.write(sha, data)

        assert path1 == path2

    def test_write_makes_readonly(self, store: LooseObjectStore) -> None:
        """Written objects are read-only."""
        blob = Blob(data=b"readonly test")
        data = create_object_data(blob)
        sha = hashlib.sha1(data, usedforsecurity=False).hexdigest()

        path = store.write(sha, data)

        # Check file is read-only (0o444)
        assert (path.stat().st_mode & 0o777) == 0o444

    def test_sha_verification(self, store: LooseObjectStore) -> None:
        """Reading corrupted object raises error."""
        blob = Blob(data=b"original")
        data = create_object_data(blob)
        sha = hashlib.sha1(data, usedforsecurity=False).hexdigest()

        store.write(sha, data)

        # Corrupt the file
        path = store._object_path(sha)
        path.chmod(0o644)
        corrupted = zlib.compress(b"blob 8\0corrupted")
        path.write_bytes(corrupted)

        with pytest.raises(ValueError, match="SHA mismatch"):
            store.read(sha)

    def test_read_not_found(self, store: LooseObjectStore) -> None:
        """Reading non-existent object raises error."""
        sha = "1" * 40
        with pytest.raises(FileNotFoundError):
            store.read(sha)

    def test_delete(self, store: LooseObjectStore) -> None:
        """Delete removes object."""
        blob = Blob(data=b"delete me")
        data = create_object_data(blob)
        sha = hashlib.sha1(data, usedforsecurity=False).hexdigest()

        store.write(sha, data)
        assert store.exists(sha)

        result = store.delete(sha)
        assert result is True
        assert not store.exists(sha)

    def test_delete_not_found(self, store: LooseObjectStore) -> None:
        """Delete non-existent object returns False."""
        sha = "2" * 40
        result = store.delete(sha)
        assert result is False

    def test_iter_objects(self, store: LooseObjectStore) -> None:
        """Iterate over stored objects."""
        # Write some objects
        shas = []
        for i in range(3):
            blob = Blob(data=f"content {i}".encode())
            data = create_object_data(blob)
            sha = hashlib.sha1(data, usedforsecurity=False).hexdigest()
            store.write(sha, data)
            shas.append(sha)

        # Iterate and collect
        found = list(store.iter_objects())

        assert len(found) == 3
        for sha in shas:
            assert sha in found

    def test_iter_objects_empty(self, store: LooseObjectStore) -> None:
        """Iterate over empty store."""
        found = list(store.iter_objects())
        assert found == []
