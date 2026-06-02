"""Git reference manager.

Handles reading, writing, resolving, and listing Git references,
including support for packed-refs.
"""

from __future__ import annotations

import fnmatch
import os
from collections.abc import Iterator
from pathlib import Path


class RefManager:
    """Manages Git references.

    Handles reading, writing, and resolving references including support
    for packed refs.  All write and delete operations invalidate the
    packed-refs cache so subsequent reads remain consistent.

    Args:
        git_dir: Path to the .git directory.
    """

    def __init__(self, git_dir: Path) -> None:
        """Initialise RefManager.

        Args:
            git_dir: Path to the .git directory.
        """
        self.git_dir = git_dir
        self.refs_dir = git_dir / "refs"
        self.packed_refs_path = git_dir / "packed-refs"
        self._packed_refs_cache: dict[str, str] | None = None

    # ---------- Reading ----------

    def _validate_name(self, name: str) -> bool:
        """Return True if *name* is safe to use as a ref path.

        Rejects names containing ``..`` segments, leading ``/``, or that
        would resolve outside ``git_dir``.

        Args:
            name: Reference name to validate.

        Returns:
            True if the name is safe, False otherwise.
        """
        if name.startswith("/"):
            return False
        parts = name.replace("\\", "/").split("/")
        if ".." in parts:
            return False
        candidate = (self.git_dir / name).resolve()
        try:
            candidate.relative_to(self.git_dir.resolve())
        except ValueError:
            return False
        return True

    def read(self, name: str) -> str | None:
        """Read a reference value (SHA or "ref: <target>" for symbolic refs).

        Loose refs take priority over packed refs.

        Args:
            name: Reference name (e.g. "refs/heads/main").

        Returns:
            SHA string, "ref: <target>" for symbolic refs, or None if
            the reference does not exist or the name is unsafe.
        """
        if not self._validate_name(name):
            return None

        path = self.git_dir / name

        if path.is_file():
            return path.read_text().strip()

        packed = self._read_packed_refs()
        return packed.get(name)

    def resolve(self, name: str, max_depth: int = 10) -> str | None:
        """Resolve a reference name or SHA to a final commit SHA.

        Resolution order for non-SHA names:
        1. Direct name as-is
        2. refs/<name>
        3. refs/tags/<name>
        4. refs/heads/<name>
        5. refs/remotes/<name>

        Symbolic refs are followed recursively up to *max_depth* times.

        Args:
            name: Reference name or 40-char hex SHA.
            max_depth: Maximum symbolic-ref chain depth (prevents loops).

        Returns:
            40-character hex SHA, or None if not found.

        Raises:
            ValueError: A symbolic reference loop was detected.
        """
        if self._is_sha(name):
            return name

        for prefix in ("", "refs/", "refs/tags/", "refs/heads/", "refs/remotes/"):
            full = prefix + name if prefix else name
            sha = self._resolve_ref(full, max_depth)
            if sha:
                return sha

        return None

    def _resolve_ref(self, name: str, max_depth: int) -> str | None:
        """Resolve a single reference path, following symbolic refs.

        Args:
            name: Exact reference name.
            max_depth: Remaining allowed recursion depth.

        Returns:
            40-character hex SHA, or None.

        Raises:
            ValueError: Symbolic reference loop detected.
        """
        if max_depth <= 0:
            raise ValueError(f"Symbolic reference loop detected at {name}")

        value = self.read(name)
        if value is None:
            return None

        if value.startswith("ref: "):
            target = value[5:]
            return self._resolve_ref(target, max_depth - 1)

        if self._is_sha(value):
            return value

        return None

    @staticmethod
    def _is_sha(value: str) -> bool:
        """Return True if *value* looks like a 40-char hex SHA.

        Args:
            value: String to test.

        Returns:
            True if exactly 40 lowercase hex characters.
        """
        return len(value) == 40 and all(c in "0123456789abcdef" for c in value)

    # ---------- Writing / Path helpers ----------

    def _ref_path(self, name: str) -> Path:
        """Validate *name* and return the absolute path under git_dir.

        Rejects names containing ``..`` segments, leading ``/``, or that
        would resolve outside ``git_dir``.

        Args:
            name: Reference name to validate.

        Returns:
            Absolute Path for the ref file inside git_dir.

        Raises:
            ValueError: The ref name is unsafe.
        """
        if not self._validate_name(name):
            raise ValueError(f"Unsafe ref name: {name!r}")
        return (self.git_dir / name).resolve()

    @staticmethod
    def _lock_path(path: Path) -> Path:
        """Return the lock file path for *path*.

        Uses string concatenation so a dotted name like ``v1.0`` locks to
        ``v1.0.lock`` rather than ``v1.lock``.

        Args:
            path: Ref file path.

        Returns:
            Lock file path (same path with ``.lock`` appended).
        """
        return Path(str(path) + ".lock")

    def write(self, name: str, sha: str) -> None:
        """Update a reference to point to a SHA.

        Creates parent directories as needed.  Uses an atomic lock-file
        write.  Invalidates the packed-refs cache.

        Args:
            name: Reference name (e.g. "refs/heads/main").
            sha: 40-character hex SHA.

        Raises:
            ValueError: *sha* is not a valid 40-char hex SHA, or *name* is unsafe.
        """
        if not self._is_sha(sha):
            raise ValueError(f"Invalid SHA: {sha}")

        path = self._ref_path(name)
        path.parent.mkdir(parents=True, exist_ok=True)

        lock = self._lock_path(path)
        fd = os.open(str(lock), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o666)
        try:
            os.write(fd, f"{sha}\n".encode())
        finally:
            os.close(fd)
        try:
            os.replace(lock, path)
        except Exception:
            lock.unlink(missing_ok=True)
            raise

        self._packed_refs_cache = None

    def write_symbolic(self, name: str, target: str) -> None:
        """Create a symbolic reference pointing to *target*.

        Args:
            name: Reference name (e.g. "HEAD").
            target: Target reference name (e.g. "refs/heads/main").

        Raises:
            ValueError: *name* is unsafe.
        """
        path = self._ref_path(name)
        path.parent.mkdir(parents=True, exist_ok=True)

        lock = self._lock_path(path)
        fd = os.open(str(lock), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o666)
        try:
            os.write(fd, f"ref: {target}\n".encode())
        finally:
            os.close(fd)
        try:
            os.replace(lock, path)
        except Exception:
            lock.unlink(missing_ok=True)
            raise

        self._packed_refs_cache = None

    def delete(self, name: str) -> bool:
        """Delete a loose reference.

        Also cleans up empty parent directories up to refs/.
        Invalidates the packed-refs cache.

        Args:
            name: Reference name.

        Returns:
            True if the reference existed and was deleted, False otherwise.

        Raises:
            ValueError: *name* is unsafe.
        """
        path = self._ref_path(name)
        if path.exists():
            path.unlink()
            self._cleanup_empty_dirs(path.parent)
            self._packed_refs_cache = None
            return True
        return False

    def _cleanup_empty_dirs(self, path: Path) -> None:
        """Remove empty ancestor directories up to (but not including) refs/.

        Args:
            path: Starting directory.
        """
        while path != self.refs_dir and path.is_dir():
            try:
                path.rmdir()
                path = path.parent
            except OSError:
                break

    # ---------- Listing ----------

    def list_refs(self, pattern: str = "refs/**") -> Iterator[tuple[str, str]]:
        """List references matching a glob pattern.

        Loose refs are yielded first; packed refs are yielded for any
        names not already seen.

        Args:
            pattern: Glob pattern relative to git_dir (e.g.
                "refs/heads/*").

        Yields:
            ``(name, sha)`` tuples sorted by loose-first, then packed.
        """
        seen: set[str] = set()
        yield from self._iter_loose_refs(pattern, seen)
        yield from self._iter_packed_refs(pattern, seen)

    def _iter_loose_refs(
        self, pattern: str, seen: set[str]
    ) -> Iterator[tuple[str, str]]:
        """Yield loose refs matching *pattern*, recording names in *seen*.

        Args:
            pattern: Glob pattern relative to git_dir.
            seen: Set updated with every name that is yielded.

        Yields:
            ``(name, sha)`` tuples for loose refs.
        """
        if not self.refs_dir.exists():
            return
        for ref_path in self.refs_dir.rglob("*"):
            if ref_path.is_file():
                name = str(ref_path.relative_to(self.git_dir))
                if fnmatch.fnmatch(name, pattern):
                    sha = self.resolve(name)
                    if sha:
                        seen.add(name)
                        yield name, sha

    def _iter_packed_refs(
        self, pattern: str, seen: set[str]
    ) -> Iterator[tuple[str, str]]:
        """Yield packed refs matching *pattern* that are not already in *seen*.

        Args:
            pattern: Glob pattern relative to git_dir.
            seen: Set of names already yielded (packed refs in this set are skipped).

        Yields:
            ``(name, sha)`` tuples for packed refs not in *seen*.
        """
        packed = self._read_packed_refs()
        for name, sha in packed.items():
            if name not in seen and fnmatch.fnmatch(name, pattern):
                yield name, sha

    def list_branches(self) -> Iterator[tuple[str, str]]:
        """List local branches.

        Yields:
            ``(short_name, sha)`` tuples (short name has "refs/heads/"
            stripped).
        """
        for name, sha in self.list_refs("refs/heads/*"):
            yield name[11:], sha

    def list_tags(self) -> Iterator[tuple[str, str]]:
        """List tags.

        Yields:
            ``(short_name, sha)`` tuples (short name has "refs/tags/"
            stripped).
        """
        for name, sha in self.list_refs("refs/tags/*"):
            yield name[10:], sha

    # ---------- Packed refs ----------

    def _read_packed_refs(self) -> dict[str, str]:
        """Parse and cache the packed-refs file.

        Returns:
            Mapping of ref name → SHA.  Peeled lines (``^``) and
            comments are ignored.
        """
        if self._packed_refs_cache is not None:
            return self._packed_refs_cache

        refs: dict[str, str] = {}
        if not self.packed_refs_path.exists():
            self._packed_refs_cache = refs
            return refs

        for line in self.packed_refs_path.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#") or line.startswith("^"):
                continue
            parts = line.split(" ", 1)
            if len(parts) == 2:
                sha, name = parts
                refs[name] = sha

        self._packed_refs_cache = refs
        return refs

    def pack_refs(self) -> None:
        """Pack all loose refs into the packed-refs file.

        After packing, loose ref files are removed (except HEAD) and
        the cache is invalidated.
        """
        refs = dict(self.list_refs())

        lines = ["# pack-refs with: peeled fully-peeled sorted\n"]
        for name in sorted(refs.keys()):
            lines.append(f"{refs[name]} {name}\n")

        self.packed_refs_path.write_text("".join(lines))

        for name in refs:
            if name != "HEAD":
                path = self.git_dir / name
                if path.exists():
                    path.unlink()
                    self._cleanup_empty_dirs(path.parent)

        self._packed_refs_cache = None
