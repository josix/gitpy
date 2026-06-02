"""Tree diff implementation.

Compares two Git tree objects and yields per-file DiffEntry records
describing what changed (added, deleted, modified).
"""

from collections.abc import Iterator
from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from gitpy.storage.database import ObjectDatabase


class DiffStatus(Enum):
    """Status of a path in a tree diff."""

    ADDED = "A"
    DELETED = "D"
    MODIFIED = "M"
    RENAMED = "R"


@dataclass(slots=True)
class DiffEntry:
    """Difference for a single path between two trees.

    Attributes:
        status: How the path changed.
        path: Repository-relative path using forward slashes.
        old_sha: SHA of the old blob, or None if added.
        new_sha: SHA of the new blob, or None if deleted.
        old_mode: Mode string of the old entry, or None if added.
        new_mode: Mode string of the new entry, or None if deleted.
        old_path: Original path for renames (None otherwise).
    """

    status: DiffStatus
    path: str
    old_sha: str | None
    new_sha: str | None
    old_mode: str | None
    new_mode: str | None
    old_path: str | None = field(default=None)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def diff_trees(
    old_tree_sha: str | None,
    new_tree_sha: str | None,
    db: "ObjectDatabase",
) -> Iterator[DiffEntry]:
    """Compare two trees and yield differences for each changed path.

    Handles None on either side to represent an empty tree (useful for
    diffing the initial commit or a complete deletion).

    Args:
        old_tree_sha: SHA of the old tree, or None for an empty tree.
        new_tree_sha: SHA of the new tree, or None for an empty tree.
        db: Object database used to read tree and blob objects.

    Yields:
        DiffEntry for each path that differs between the two trees.
    """
    old_entries: dict[str, dict[str, str]] = {}
    new_entries: dict[str, dict[str, str]] = {}

    if old_tree_sha:
        old_entries = flatten_tree(old_tree_sha, db, "")
    if new_tree_sha:
        new_entries = flatten_tree(new_tree_sha, db, "")

    all_paths = sorted(set(old_entries) | set(new_entries))

    for path in all_paths:
        old = old_entries.get(path)
        new = new_entries.get(path)

        if old and new:
            if old["sha"] != new["sha"] or old["mode"] != new["mode"]:
                yield DiffEntry(
                    status=DiffStatus.MODIFIED,
                    path=path,
                    old_sha=old["sha"],
                    new_sha=new["sha"],
                    old_mode=old["mode"],
                    new_mode=new["mode"],
                )
        elif old:
            yield DiffEntry(
                status=DiffStatus.DELETED,
                path=path,
                old_sha=old["sha"],
                new_sha=None,
                old_mode=old["mode"],
                new_mode=None,
            )
        else:
            if new is None:
                raise RuntimeError(f"Unexpected None for path '{path}' in set union")
            yield DiffEntry(
                status=DiffStatus.ADDED,
                path=path,
                old_sha=None,
                new_sha=new["sha"],
                old_mode=None,
                new_mode=new["mode"],
            )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def flatten_tree(
    tree_sha: str,
    db: "ObjectDatabase",
    prefix: str,
) -> dict[str, dict[str, str]]:
    """Recursively flatten a tree into a mapping of path -> {sha, mode}.

    Args:
        tree_sha: SHA of the tree to flatten.
        db: Object database.
        prefix: Path prefix accumulated during recursion (empty at root).

    Returns:
        Dict mapping repository-relative paths to {"sha": ..., "mode": ...}.
    """
    result: dict[str, dict[str, str]] = {}
    tree = db.read_tree(tree_sha)

    for entry in tree.entries:
        path = f"{prefix}{entry.name}"
        if entry.is_tree:
            result.update(flatten_tree(entry.sha, db, f"{path}/"))
        else:
            result[path] = {"sha": entry.sha, "mode": entry.mode}

    return result


def is_binary(data: bytes, sample: int = 8000) -> bool:
    """Heuristically detect binary content.

    Checks for a NUL byte in the first *sample* bytes, which is the same
    heuristic used by Git.

    Args:
        data: Raw blob bytes.
        sample: Number of bytes to inspect.

    Returns:
        True if the content appears to be binary.
    """
    return b"\x00" in data[:sample]


def format_binary_diff(path: str) -> str:
    """Return the standard Git message for a binary file diff.

    Args:
        path: Repository-relative path of the binary file.

    Returns:
        Human-readable string matching Git's binary-diff output.
    """
    return f"Binary files a/{path} and b/{path} differ"
