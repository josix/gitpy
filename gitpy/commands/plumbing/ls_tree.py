"""Implementation of ``git ls-tree``.

Lists the contents of a tree object, optionally recursing into subtrees.

Output-stream contract
----------------------
``out`` accepts any object with a ``write(bytes)`` method.
Tests inject ``io.BytesIO``; the CLI layer uses ``sys.stdout.buffer``.
"""

import sys
from typing import IO

from gitpy.objects.tree import TreeEntry
from gitpy.repository import Repository


def _resolve_to_tree_sha(repo: Repository, tree_ish: str) -> str | None:
    """Resolve *tree_ish* to the SHA of a tree object.

    Accepts a tree SHA directly, a commit SHA (returns its tree), or a ref
    that resolves to either.

    Args:
        repo: Repository to query.
        tree_ish: Tree SHA, commit SHA, or ref name.

    Returns:
        40-char hex SHA of the tree, or None if not resolvable.
    """
    sha = repo.refs.resolve(tree_ish)
    if sha is None:
        # Try object-database short-SHA resolution.
        sha = repo.objects.resolve_short_sha(tree_ish)
    if sha is None:
        return None

    obj_type = repo.objects.get_type(sha)
    if obj_type == "commit":
        commit = repo.objects.read_commit(sha)
        return commit.tree_sha
    if obj_type == "tag":
        # Annotated tag: dereference to the tagged object.
        tag = repo.objects.read_tag(sha)
        if tag.object_type == "commit":
            commit = repo.objects.read_commit(tag.object_sha)
            return commit.tree_sha
        if tag.object_type == "tree":
            return tag.object_sha
        return None
    if obj_type == "tree":
        return sha
    return None


def _format_entry(entry: TreeEntry, prefix: str) -> str:
    """Format a single tree entry for output.

    Args:
        entry: Tree entry to format.
        prefix: Path prefix (empty for top-level, e.g. "sub/" for subdirs).

    Returns:
        Formatted line string without trailing newline.
    """
    obj_type = "tree" if entry.is_tree else "blob"
    path = f"{prefix}{entry.name}"
    return f"{entry.mode} {obj_type} {entry.sha}\t{path}"


def _list_tree(
    repo: Repository,
    tree_sha: str,
    prefix: str,
    recursive: bool,
    dirs_only: bool,
    trees_flag: bool,
    lines: list[str],
) -> None:
    """Recursively build listing lines for a tree.

    Args:
        repo: Repository to query.
        tree_sha: SHA of the tree to list.
        prefix: Current path prefix.
        recursive: When True, recurse into subtrees.
        dirs_only: When True, emit only tree (directory) entries.
        trees_flag: When True, also emit tree entries in recursive mode.
        lines: Accumulator list to append formatted lines to.
    """
    tree = repo.objects.read_tree(tree_sha)
    sorted_entries = sorted(tree.entries, key=lambda e: e.sort_key())

    for entry in sorted_entries:
        if recursive and entry.is_tree:
            if trees_flag:
                lines.append(_format_entry(entry, prefix))
            _list_tree(
                repo,
                entry.sha,
                f"{prefix}{entry.name}/",
                recursive,
                dirs_only,
                trees_flag,
                lines,
            )
        else:
            if dirs_only and not entry.is_tree:
                continue
            lines.append(_format_entry(entry, prefix))


def ls_tree(
    repo: Repository,
    tree_ish: str,
    *,
    recursive: bool = False,
    dirs_only: bool = False,
    trees: bool = False,
    out: IO[bytes] | None = None,
) -> int:
    """List contents of a tree object (equivalent to ``git ls-tree``).

    Args:
        repo: Repository to query.
        tree_ish: Tree SHA, commit SHA, or ref name.
        recursive: Recurse into subtrees (-r).
        dirs_only: Only show directories (-d).
        trees: Also show tree entries when recursing (-t).
        out: Writable binary stream for output (default: sys.stdout.buffer).

    Returns:
        0 on success, 1 on error.
    """
    stream: IO[bytes] = out if out is not None else sys.stdout.buffer

    tree_sha = _resolve_to_tree_sha(repo, tree_ish)
    if tree_sha is None:
        stream.write(f"fatal: Not a valid object name '{tree_ish}'\n".encode())
        return 1

    lines: list[str] = []
    _list_tree(repo, tree_sha, "", recursive, dirs_only, trees, lines)

    output = "\n".join(lines)
    if output:
        stream.write((output + "\n").encode())
    return 0
