"""Tests for Blob object."""

import tempfile
from pathlib import Path

import pytest

from gitpy.objects import Blob


class TestBlob:
    """Tests for Blob class."""

    def test_blob_hash_empty(self) -> None:
        """Empty blob has known hash."""
        blob = Blob(data=b"")
        assert blob.oid == "e69de29bb2d1d6434b8b29ae775ad8c2e48c5391"

    def test_blob_hash_hello(self) -> None:
        """'hello\\n' has known hash."""
        blob = Blob(data=b"hello\n")
        assert blob.oid == "ce013625030ba8dba906f756967f9e9ca394464a"

    def test_blob_hash_hello_world(self) -> None:
        """'Hello, World!\\n' has known hash."""
        blob = Blob(data=b"Hello, World!\n")
        assert blob.oid == "8ab686eafeb1f44702738c8b0f24f2567c36da6d"

    def test_blob_roundtrip(self) -> None:
        """Serialize then deserialize preserves content."""
        original = Blob(data=b"test content\nwith newlines\n")
        restored = Blob.deserialize(original.serialize())
        assert original.data == restored.data

    def test_blob_binary_content(self) -> None:
        """Blob handles binary content."""
        binary_data = bytes(range(256))
        blob = Blob(data=binary_data)
        restored = Blob.deserialize(blob.serialize())
        assert restored.data == binary_data

    def test_blob_equality(self) -> None:
        """Blobs with same content are equal."""
        blob1 = Blob(data=b"same content")
        blob2 = Blob(data=b"same content")
        assert blob1 == blob2
        assert blob1.oid == blob2.oid

    def test_blob_inequality(self) -> None:
        """Blobs with different content are not equal."""
        blob1 = Blob(data=b"content 1")
        blob2 = Blob(data=b"content 2")
        assert blob1 != blob2
        assert blob1.oid != blob2.oid

    def test_blob_from_file(self) -> None:
        """Create blob from file."""
        with tempfile.NamedTemporaryFile(mode="wb", delete=False) as f:
            f.write(b"file content\n")
            temp_path = f.name

        try:
            blob = Blob.from_file(temp_path)
            assert blob.data == b"file content\n"
        finally:
            Path(temp_path).unlink()

    def test_blob_from_file_path_object(self) -> None:
        """Create blob from Path object."""
        with tempfile.NamedTemporaryFile(mode="wb", delete=False) as f:
            f.write(b"path content\n")
            temp_path = Path(f.name)

        try:
            blob = Blob.from_file(temp_path)
            assert blob.data == b"path content\n"
        finally:
            temp_path.unlink()

    def test_blob_hash_consistency(self) -> None:
        """Hash is computed consistently."""
        blob = Blob(data=b"consistent content")
        hash1 = blob.compute_hash()
        hash2 = blob.compute_hash()
        hash3 = blob.oid
        assert hash1 == hash2 == hash3

    def test_blob_type_name(self) -> None:
        """Blob has correct type name."""
        blob = Blob(data=b"")
        assert blob.type_name == "blob"
