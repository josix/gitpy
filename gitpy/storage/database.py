"""High-level Git object database.

The ObjectDatabase provides a type-safe interface to Git object storage,
handling serialization, compression, and SHA computation automatically.
"""

import hashlib
from pathlib import Path

from gitpy.objects import (
    Blob,
    Commit,
    GitObject,
    Tag,
    Tree,
    create_object_data,
    parse_object,
)

from .loose import LooseObjectStore


class ObjectDatabase:
    """High-level interface to Git object storage.

    Provides read/write access to Git objects with automatic
    serialization, compression, and SHA computation.
    """

    def __init__(self, git_dir: Path) -> None:
        """Initialize object database.

        Args:
            git_dir: Path to .git directory.
        """
        self.git_dir = git_dir
        self.loose = LooseObjectStore(git_dir)

    def exists(self, sha: str) -> bool:
        """Check if object exists.

        Args:
            sha: Full or abbreviated SHA-1.

        Returns:
            True if object exists, False otherwise.
        """
        if len(sha) < 40:
            return self._resolve_short_sha(sha) is not None
        return self.loose.exists(sha)

    def _resolve_short_sha(self, short_sha: str) -> str | None:
        """Resolve abbreviated SHA to full SHA.

        Args:
            short_sha: Abbreviated SHA (minimum 4 chars).

        Returns:
            Full 40-char SHA or None if not found.

        Raises:
            ValueError: If SHA is ambiguous (multiple matches) or too short.
        """
        if len(short_sha) < 4:
            raise ValueError("SHA prefix too short (minimum 4)")

        if len(short_sha) >= 40:
            return short_sha if self.loose.exists(short_sha) else None

        matches: list[str] = []
        prefix = short_sha[:2]
        suffix_prefix = short_sha[2:]

        subdir = self.loose.objects_dir / prefix
        if subdir.exists():
            for obj_file in subdir.iterdir():
                if obj_file.name.startswith(suffix_prefix):
                    matches.append(prefix + obj_file.name)

        if len(matches) == 0:
            return None
        if len(matches) == 1:
            return matches[0]
        raise ValueError(
            f"Ambiguous SHA prefix: {short_sha} matches {len(matches)} objects"
        )

    def read_raw(self, sha: str) -> bytes:
        """Read raw object data (decompressed, with header).

        Args:
            sha: Object SHA (full or abbreviated).

        Returns:
            Raw object bytes.

        Raises:
            FileNotFoundError: Object not found.
        """
        if len(sha) < 40:
            full_sha = self._resolve_short_sha(sha)
            if full_sha is None:
                raise FileNotFoundError(f"Object not found: {sha}")
            sha = full_sha

        return self.loose.read(sha)

    def read(self, sha: str) -> GitObject:
        """Read and parse object.

        Args:
            sha: Object SHA (full or abbreviated).

        Returns:
            Parsed GitObject (Blob, Tree, Commit, or Tag).

        Raises:
            FileNotFoundError: Object not found.
            ValueError: Invalid object format.
        """
        data = self.read_raw(sha)
        _, obj = parse_object(data)
        return obj

    def read_blob(self, sha: str) -> Blob:
        """Read object as Blob.

        Args:
            sha: Object SHA (full or abbreviated).

        Returns:
            Blob object.

        Raises:
            TypeError: Object is not a blob.
            FileNotFoundError: Object not found.
        """
        obj = self.read(sha)
        if not isinstance(obj, Blob):
            raise TypeError(f"Expected blob, got {obj.type_name}")
        return obj

    def read_tree(self, sha: str) -> Tree:
        """Read object as Tree.

        Args:
            sha: Object SHA (full or abbreviated).

        Returns:
            Tree object.

        Raises:
            TypeError: Object is not a tree.
            FileNotFoundError: Object not found.
        """
        obj = self.read(sha)
        if not isinstance(obj, Tree):
            raise TypeError(f"Expected tree, got {obj.type_name}")
        return obj

    def read_commit(self, sha: str) -> Commit:
        """Read object as Commit.

        Args:
            sha: Object SHA (full or abbreviated).

        Returns:
            Commit object.

        Raises:
            TypeError: Object is not a commit.
            FileNotFoundError: Object not found.
        """
        obj = self.read(sha)
        if not isinstance(obj, Commit):
            raise TypeError(f"Expected commit, got {obj.type_name}")
        return obj

    def read_tag(self, sha: str) -> Tag:
        """Read object as Tag.

        Args:
            sha: Object SHA (full or abbreviated).

        Returns:
            Tag object.

        Raises:
            TypeError: Object is not a tag.
            FileNotFoundError: Object not found.
        """
        obj = self.read(sha)
        if not isinstance(obj, Tag):
            raise TypeError(f"Expected tag, got {obj.type_name}")
        return obj

    def write(self, obj: GitObject) -> str:
        """Write object to storage.

        Args:
            obj: GitObject to write.

        Returns:
            SHA-1 of written object.
        """
        data = create_object_data(obj)
        sha = hashlib.sha1(data, usedforsecurity=False).hexdigest()
        self.loose.write(sha, data)
        return sha

    def hash_object(self, obj: GitObject, *, write: bool = True) -> str:
        """Compute SHA of object, optionally storing it.

        Args:
            obj: GitObject to hash.
            write: If True, also write to storage.

        Returns:
            SHA-1 hash.
        """
        data = create_object_data(obj)
        sha = hashlib.sha1(data, usedforsecurity=False).hexdigest()

        if write:
            self.loose.write(sha, data)

        return sha

    def get_type(self, sha: str) -> str:
        """Get object type without full parse.

        Args:
            sha: Object SHA (full or abbreviated).

        Returns:
            Object type name ("blob", "tree", "commit", or "tag").
        """
        data = self.read_raw(sha)
        null_idx = data.index(b"\0")
        header = data[:null_idx].decode("ascii")
        type_name, _ = header.split(" ")
        return type_name

    def get_size(self, sha: str) -> int:
        """Get object size without full parse.

        Args:
            sha: Object SHA (full or abbreviated).

        Returns:
            Size in bytes of the object content.
        """
        data = self.read_raw(sha)
        null_idx = data.index(b"\0")
        header = data[:null_idx].decode("ascii")
        _, size_str = header.split(" ")
        return int(size_str)
