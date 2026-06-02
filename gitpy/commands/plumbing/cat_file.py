"""Implementation of ``git cat-file``.

Provides type (-t), size (-s), and pretty-print (-p) operations on
Git objects.

Output-stream contract
----------------------
The ``out`` parameter accepts any object with a ``write`` method that
accepts *bytes*.  Commands write raw bytes so that binary blobs are
reproduced exactly.  Tests inject an ``io.BytesIO`` instance; the CLI
layer wraps ``sys.stdout.buffer``.  When *out* is omitted the command
writes to ``sys.stdout.buffer``.
"""

import sys
from typing import IO

from gitpy.objects.blob import Blob
from gitpy.objects.commit import Commit
from gitpy.objects.tag import Tag
from gitpy.objects.tree import Tree
from gitpy.repository import Repository


def _resolve_oid(repo: Repository, obj: str) -> str | None:
    """Resolve *obj* to a full SHA-1.

    First tries the ref manager (handles ref names + raw SHAs via
    RefManager.resolve), then falls back to the object database's short-SHA
    resolution for abbreviated hashes that are not refs.

    Args:
        repo: Repository to search.
        obj: Ref name, full SHA, or abbreviated SHA.

    Returns:
        40-char hex SHA, or None if not found.
    """
    sha = repo.refs.resolve(obj)
    if sha:
        return sha

    # Fall back to object-database short-SHA resolution.
    return repo.objects.resolve_short_sha(obj)


def _pretty_print_tree(tree: Tree) -> bytes:
    """Render a tree in ``git ls-tree`` single-level format."""
    lines: list[str] = []
    for entry in sorted(tree.entries, key=lambda e: e.sort_key()):
        obj_type = "tree" if entry.is_tree else "blob"
        lines.append(f"{entry.mode} {obj_type} {entry.sha}\t{entry.name}")
    return "\n".join(lines).encode() + (b"\n" if lines else b"")


def cat_file(
    repo: Repository,
    obj: str,
    *,
    show_type: bool = False,
    show_size: bool = False,
    pretty: bool = False,
    expected_type: str | None = None,
    out: IO[bytes] | None = None,
) -> int:
    """Inspect a Git object (equivalent to ``git cat-file``).

    Exactly one of *show_type*, *show_size*, *pretty*, or *expected_type*
    should be True/set for a meaningful result.

    Args:
        repo: Repository to query.
        obj: Object ref, full SHA, or abbreviated SHA.
        show_type: Print the object type (-t).
        show_size: Print the object size in bytes (-s).
        pretty: Pretty-print the object content (-p).
        expected_type: Verify object type; exit 1 on mismatch (-t <type>).
        out: Writable binary stream for output (default: sys.stdout.buffer).

    Returns:
        0 on success, 1 on error (type mismatch or missing object).
    """
    stream: IO[bytes] = out if out is not None else sys.stdout.buffer

    sha = _resolve_oid(repo, obj)
    if sha is None:
        stream.write(f"fatal: Not a valid object name '{obj}'\n".encode())
        return 1

    if expected_type is not None:
        actual_type = repo.objects.get_type(sha)
        if actual_type != expected_type:
            stream.write(
                f"error: object {sha} is a {actual_type}, not a {expected_type}\n".encode()
            )
            return 1
        git_obj = repo.objects.read(sha)
        stream.write(git_obj.serialize())
        return 0

    try:
        if show_type:
            obj_type = repo.objects.get_type(sha)
            stream.write(f"{obj_type}\n".encode())
            return 0

        if show_size:
            size = repo.objects.get_size(sha)
            stream.write(f"{size}\n".encode())
            return 0

        if pretty:
            git_obj = repo.objects.read(sha)
            match git_obj:
                case Blob():
                    stream.write(git_obj.serialize())
                case Tree():
                    stream.write(_pretty_print_tree(git_obj))
                case Commit() | Tag():
                    stream.write(git_obj.serialize())
            return 0

    except FileNotFoundError:
        stream.write(f"fatal: Not a valid object name '{sha}'\n".encode())
        return 1

    return 0
