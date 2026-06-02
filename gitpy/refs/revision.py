"""Revision expression parser.

Supports Git revision expressions such as HEAD, HEAD^, HEAD~N, HEAD^2,
HEAD@{N}, branch names, tag names, and full/abbreviated SHAs.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from gitpy.storage.database import ObjectDatabase

from .reflog import Reflog

if TYPE_CHECKING:
    from .manager import RefManager


class RevisionParser:
    """Parses Git revision expressions into commit SHAs.

    Supported expressions:

    * Plain names: ``HEAD``, ``main``, ``v1.0``, ``abc123`` (abbrev SHA)
    * Parent: ``HEAD^``, ``HEAD^2`` (second parent of a merge commit)
    * Ancestor: ``HEAD~3`` (three steps up the first-parent chain)
    * Reflog: ``HEAD@{1}`` (previous value of HEAD)

    Args:
        ref_manager: RefManager for resolving branch/tag names.
        object_db: ObjectDatabase for reading commit objects.
    """

    def __init__(self, ref_manager: RefManager, object_db: ObjectDatabase) -> None:
        """Initialise RevisionParser.

        Args:
            ref_manager: Ref manager for the repository.
            object_db: Object database for the repository.
        """
        self.ref_manager = ref_manager
        self.object_db = object_db

    def parse(self, rev: str) -> str | None:
        """Parse a revision expression and return a 40-char SHA.

        Args:
            rev: Revision expression string.

        Returns:
            40-character hex SHA, or None if the expression cannot be
            resolved.
        """
        if "@{" in rev:
            return self._parse_reflog_ref(rev)

        if "^" in rev or "~" in rev:
            return self._parse_with_suffix(rev)

        # Try ref manager first (branch names, tags, HEAD, full SHAs).
        sha = self.ref_manager.resolve(rev)
        if sha is not None:
            return sha

        # Fall back to abbreviated SHA resolution via the object DB.
        if re.fullmatch(r"[0-9a-f]{4,39}", rev):
            return self.object_db.resolve_short_sha(rev)

        return None

    def _apply_suffix(self, sha: str, char: str, num: int) -> str | None:
        """Apply a single ``^`` or ``~`` suffix to *sha*.

        Args:
            sha: Starting commit SHA.
            char: Either ``^`` (nth parent) or ``~`` (first-parent chain).
            num: Numeric argument following the suffix character.

        Returns:
            Resulting SHA, or None if the walk goes out of range.
        """
        if char == "^":
            return self._get_parent(sha, num)
        # char == "~"
        for _ in range(num):
            sha = self._get_parent(sha, 1)  # type: ignore[assignment]
            if sha is None:
                return None
        return sha

    def _parse_with_suffix(self, rev: str) -> str | None:
        """Resolve a revision with ``^`` or ``~`` ancestry suffixes.

        Args:
            rev: Expression such as ``HEAD~3`` or ``HEAD^2``.

        Returns:
            40-character hex SHA, or None.
        """
        m = re.match(r"^([^~^]+)((?:[~^]\d*)+)$", rev)
        if not m:
            return self.ref_manager.resolve(rev)

        base, suffixes = m.groups()
        sha: str | None = self.ref_manager.resolve(base)
        if sha is None:
            return None

        pos = 0
        while pos < len(suffixes):
            char = suffixes[pos]
            pos += 1

            num_m = re.match(r"(\d+)", suffixes[pos:])
            if num_m:
                num = int(num_m.group(1))
                pos += len(num_m.group(1))
            else:
                num = 1

            sha = self._apply_suffix(sha, char, num)
            if sha is None:
                return None

        return sha

    def _get_parent(self, sha: str, n: int) -> str | None:
        """Return the *n*-th parent of a commit.

        ``^0`` is a special case: it peels to the commit itself (identity).

        Args:
            sha: Commit SHA.
            n: 0-based peel (0 = identity) or 1-based parent index (>= 1).

        Returns:
            Parent SHA (or *sha* itself for n=0), or None if the commit has
            fewer than *n* parents.
        """
        if n == 0:
            return sha

        try:
            commit = self.object_db.read_commit(sha)
        except (FileNotFoundError, TypeError):
            return None

        if n > len(commit.parent_shas):
            return None
        return commit.parent_shas[n - 1]

    def _parse_reflog_ref(self, rev: str) -> str | None:
        """Resolve a reflog expression such as ``HEAD@{1}``.

        Only integer indices are supported (time-based expressions like
        ``HEAD@{yesterday}`` are not implemented).

        Args:
            rev: Expression in ``<ref>@{<n>}`` form.

        Returns:
            40-character hex SHA of the ``new_sha`` in the chosen entry,
            or None if out of range or not a numeric index.
        """
        m = re.match(r"^(.+)@\{(\d+)\}$", rev)
        if not m:
            return None

        ref_name, index_str = m.groups()
        index = int(index_str)

        reflog = Reflog(self.ref_manager.git_dir)
        entry = reflog.get(ref_name, index)

        if entry:
            return entry.new_sha
        return None
