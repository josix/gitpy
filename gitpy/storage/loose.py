"""Loose object storage for Git.

Loose objects are individual zlib-compressed files stored in
.git/objects/<sha[0:2]>/<sha[2:40]>.

This is Git's primary storage format for newly created objects.
Packfiles (Phase 2b) provide more efficient storage for many objects.
"""

import contextlib
import hashlib
from collections.abc import Iterator
from pathlib import Path

from .compression import compress, decompress


class LooseObjectStore:
    """Manages loose object storage in .git/objects/.

    Loose objects are individual zlib-compressed files,
    one per object, named by SHA-1 hash.
    """

    def __init__(self, git_dir: Path) -> None:
        """Initialize loose object store.

        Args:
            git_dir: Path to .git directory.
        """
        self.objects_dir = git_dir / "objects"

    def _object_path(self, sha: str) -> Path:
        """Compute filesystem path for object.

        Args:
            sha: 40-character hex SHA-1.

        Returns:
            Path where the object should be stored.

        Raises:
            ValueError: If SHA is not 40 characters.
        """
        if len(sha) != 40:
            raise ValueError(f"Invalid SHA length: {len(sha)}, expected 40")
        return self.objects_dir / sha[:2] / sha[2:]

    def exists(self, sha: str) -> bool:
        """Check if object exists in store.

        Args:
            sha: 40-character hex SHA-1.

        Returns:
            True if object exists, False otherwise.
        """
        return self._object_path(sha).exists()

    def read(self, sha: str) -> bytes:
        """Read and decompress object.

        Args:
            sha: 40-character hex SHA-1.

        Returns:
            Decompressed object data (with header).

        Raises:
            FileNotFoundError: Object doesn't exist.
            zlib.error: Decompression failed.
            ValueError: SHA mismatch (corrupted object).
        """
        path = self._object_path(sha)
        compressed = path.read_bytes()
        data = decompress(compressed)

        # Verify SHA matches content
        computed_sha = hashlib.sha1(data, usedforsecurity=False).hexdigest()
        if computed_sha != sha:
            raise ValueError(f"SHA mismatch: expected {sha}, got {computed_sha}")

        return data

    def write(self, sha: str, data: bytes) -> Path:
        """Compress and write object atomically.

        Args:
            sha: 40-character hex SHA-1.
            data: Complete object data (with header).

        Returns:
            Path to written object.

        Note:
            Write is atomic - uses temp file + rename.
            If object already exists, returns existing path without rewriting.
        """
        path = self._object_path(sha)

        # Skip if already exists (content-addressable = immutable)
        if path.exists():
            return path

        # Ensure directory exists
        path.parent.mkdir(parents=True, exist_ok=True)

        # Compress
        compressed = compress(data)

        # Atomic write: write to temp, then rename
        temp_path = path.with_suffix(".tmp")
        try:
            temp_path.write_bytes(compressed)
            temp_path.rename(path)
        except Exception:
            # Clean up temp file on failure
            temp_path.unlink(missing_ok=True)
            raise

        # Set read-only (objects are immutable)
        path.chmod(0o444)

        return path

    def delete(self, sha: str) -> bool:
        """Delete object (for garbage collection).

        Args:
            sha: 40-character hex SHA-1.

        Returns:
            True if deleted, False if didn't exist.
        """
        path = self._object_path(sha)
        if path.exists():
            path.chmod(0o644)  # Make writable first
            path.unlink()
            # Clean up empty directory
            with contextlib.suppress(OSError):
                path.parent.rmdir()
            return True
        return False

    def iter_objects(self) -> Iterator[str]:
        """Iterate over all object SHAs in store.

        Yields:
            40-character hex SHA-1 strings for each object.
        """
        if not self.objects_dir.exists():
            return

        for subdir in self.objects_dir.iterdir():
            if len(subdir.name) != 2 or not subdir.is_dir():
                continue
            if subdir.name in ("info", "pack"):
                continue
            for obj_file in subdir.iterdir():
                if len(obj_file.name) == 38:
                    yield subdir.name + obj_file.name
