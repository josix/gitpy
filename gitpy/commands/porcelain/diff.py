"""Implementation of ``git diff``.

Shows differences between commits, or between the index and the worktree.
"""

import contextlib
import hashlib

from gitpy.diff.tree import (
    DiffEntry,
    DiffStatus,
    diff_trees,
    flatten_tree,
    format_binary_diff,
    is_binary,
)
from gitpy.diff.unified import format_unified_diff
from gitpy.index.operations import write_tree
from gitpy.objects.blob import Blob
from gitpy.refs.revision import RevisionParser
from gitpy.repository import Repository


def _worktree_blob_sha(repo: Repository, rel_path: str) -> str | None:
    """Compute the SHA of a worktree file without writing it.

    Args:
        repo: Repository to query.
        rel_path: Repository-relative path.

    Returns:
        40-char SHA, or None if the file does not exist.
    """
    full = repo.worktree / rel_path
    if not full.exists():
        return None
    blob = Blob.from_file(full)
    data = blob.serialize()
    header = f"blob {len(data)}\0".encode()
    return hashlib.sha1(header + data, usedforsecurity=False).hexdigest()


def _read_worktree_bytes(repo: Repository, rel_path: str) -> bytes | None:
    """Read raw bytes from a worktree file.

    Args:
        repo: Repository to query.
        rel_path: Repository-relative path.

    Returns:
        File bytes, or None if the file does not exist.
    """
    full = repo.worktree / rel_path
    if not full.exists():
        return None
    return full.read_bytes()


def _resolve_commit_tree(repo: Repository, rev: str) -> str | None:
    """Resolve a revision string to its tree SHA.

    Uses RevisionParser so expressions like HEAD^, HEAD~2, and abbreviated
    SHAs are supported.

    Args:
        repo: Repository to query.
        rev: Revision string.

    Returns:
        40-char tree SHA, or None.
    """
    parser = RevisionParser(repo.refs, repo.objects)
    sha = parser.parse(rev)
    if sha is None:
        return None
    try:
        obj_type = repo.objects.get_type(sha)
    except FileNotFoundError:
        return None
    if obj_type == "commit":
        return repo.objects.read_commit(sha).tree_sha
    if obj_type == "tree":
        return sha
    return None


def _print_diff(repo: Repository, entry: DiffEntry) -> None:
    """Print the unified diff for a single DiffEntry.

    Both old and new sides are read from the object database (for
    commit-vs-commit and staged diffs).  Worktree-vs-index diffs should use
    ``_print_diff_with_bytes`` instead.

    Args:
        repo: Repository to query.
        entry: DiffEntry to display.
    """
    old_data = b""
    new_data = b""
    with contextlib.suppress(FileNotFoundError, TypeError):
        if entry.old_sha:
            old_data = repo.objects.read_blob(entry.old_sha).data
    with contextlib.suppress(FileNotFoundError, TypeError):
        if entry.new_sha:
            new_data = repo.objects.read_blob(entry.new_sha).data

    _emit_diff(entry, old_data, new_data)


def _print_diff_with_bytes(entry: DiffEntry, old_data: bytes, new_data: bytes) -> None:
    """Print the unified diff using pre-read byte strings.

    Used when the new side is a worktree file that hasn't been written to
    the object database.

    Args:
        entry: DiffEntry metadata (status, path, modes).
        old_data: Raw bytes of the old (object DB) side.
        new_data: Raw bytes of the new (worktree) side.
    """
    _emit_diff(entry, old_data, new_data)


def _emit_diff(entry: DiffEntry, old_data: bytes, new_data: bytes) -> None:
    """Emit the diff output for *entry* given pre-resolved byte content.

    Args:
        entry: DiffEntry with status/path/mode metadata.
        old_data: Content of the old side (may be empty).
        new_data: Content of the new side (may be empty).
    """
    path = entry.path

    if is_binary(old_data) or is_binary(new_data):
        print(format_binary_diff(path))
        return

    old_lines = (
        old_data.decode("utf-8", errors="replace").splitlines() if old_data else []
    )
    new_lines = (
        new_data.decode("utf-8", errors="replace").splitlines() if new_data else []
    )

    diff_text = format_unified_diff(
        old_lines,
        new_lines,
        old_name=f"a/{path}",
        new_name=f"b/{path}",
    )
    if diff_text:
        print(f"diff --git a/{path} b/{path}")
        match entry.status:
            case DiffStatus.ADDED:
                print(f"new file mode {entry.new_mode}")
            case DiffStatus.DELETED:
                print(f"deleted file mode {entry.old_mode}")
        print(diff_text, end="")


def diff(repo: Repository, commits: list[str], *, staged: bool = False) -> int:
    """Show differences between commits or between index/worktree.

    Args:
        repo: Repository to inspect.
        commits: Zero, one, or two revision strings.
            - 0 commits + staged=False: worktree vs index.
            - 0 commits + staged=True: index vs HEAD.
            - 1 commit: worktree vs that commit's tree.
            - 2 commits: first commit tree vs second commit tree.
        staged: Compare index vs HEAD (``--staged`` / ``--cached``).

    Returns:
        0 on success, 1 on error.
    """
    if len(commits) == 2:
        return _diff_two_commits(repo, commits[0], commits[1])

    if len(commits) == 1:
        return _diff_commit_vs_worktree(repo, commits[0])

    if staged:
        return _diff_staged(repo)

    return _diff_worktree_vs_index(repo)


# ---------------------------------------------------------------------------
# diff helpers
# ---------------------------------------------------------------------------


def _diff_two_commits(repo: Repository, rev1: str, rev2: str) -> int:
    """Diff two commit trees against each other."""
    tree1 = _resolve_commit_tree(repo, rev1)
    if tree1 is None:
        print(f"fatal: ambiguous argument '{rev1}'")
        return 1
    tree2 = _resolve_commit_tree(repo, rev2)
    if tree2 is None:
        print(f"fatal: ambiguous argument '{rev2}'")
        return 1

    for entry in diff_trees(tree1, tree2, repo.objects):
        _print_diff(repo, entry)
    return 0


def _diff_commit_vs_worktree(repo: Repository, rev: str) -> int:
    """Diff a commit tree against the working tree."""
    tree_sha = _resolve_commit_tree(repo, rev)
    if tree_sha is None:
        print(f"fatal: ambiguous argument '{rev}'")
        return 1

    old_entries = flatten_tree(tree_sha, repo.objects, "")
    all_paths: set[str] = set(old_entries)
    for wt_path in repo.worktree.rglob("*"):
        if wt_path.is_file() and ".git" not in wt_path.parts:
            all_paths.add(str(wt_path.relative_to(repo.worktree)))

    for path in sorted(all_paths):
        old = old_entries.get(path)
        wt_bytes = _read_worktree_bytes(repo, path)
        wt_sha = _worktree_blob_sha(repo, path)

        if old and wt_sha and old["sha"] != wt_sha:
            old_data: bytes = b""
            with contextlib.suppress(FileNotFoundError, TypeError):
                old_data = repo.objects.read_blob(old["sha"]).data
            _print_diff_with_bytes(
                DiffEntry(
                    status=DiffStatus.MODIFIED,
                    path=path,
                    old_sha=old["sha"],
                    new_sha=wt_sha,
                    old_mode=old["mode"],
                    new_mode=old["mode"],
                ),
                old_data,
                wt_bytes or b"",
            )
        elif old and not wt_sha:
            old_data2: bytes = b""
            with contextlib.suppress(FileNotFoundError, TypeError):
                old_data2 = repo.objects.read_blob(old["sha"]).data
            _print_diff_with_bytes(
                DiffEntry(
                    status=DiffStatus.DELETED,
                    path=path,
                    old_sha=old["sha"],
                    new_sha=None,
                    old_mode=old["mode"],
                    new_mode=None,
                ),
                old_data2,
                b"",
            )
        elif not old and wt_sha:
            _print_diff_with_bytes(
                DiffEntry(
                    status=DiffStatus.ADDED,
                    path=path,
                    old_sha=None,
                    new_sha=wt_sha,
                    old_mode=None,
                    new_mode="100644",
                ),
                b"",
                wt_bytes or b"",
            )
    return 0


def _diff_staged(repo: Repository) -> int:
    """Diff the index against HEAD."""
    head_tree: str | None = None
    with contextlib.suppress(ValueError, FileNotFoundError):
        commit_sha = repo.head.resolve(repo.refs)
        head_tree = repo.objects.read_commit(commit_sha).tree_sha

    index = repo.index.read()
    index_tree = write_tree(index, repo.objects)

    for entry in diff_trees(head_tree, index_tree, repo.objects):
        _print_diff(repo, entry)
    return 0


def _diff_worktree_vs_index(repo: Repository) -> int:
    """Diff the working tree against the index."""
    index = repo.index.read()
    index_tree = write_tree(index, repo.objects)
    index_entries = flatten_tree(index_tree, repo.objects, "")

    all_paths: set[str] = set(index_entries)
    for wt_path in repo.worktree.rglob("*"):
        if wt_path.is_file() and ".git" not in wt_path.parts:
            all_paths.add(str(wt_path.relative_to(repo.worktree)))

    for path in sorted(all_paths):
        idx = index_entries.get(path)
        wt_bytes = _read_worktree_bytes(repo, path)
        wt_sha = _worktree_blob_sha(repo, path)

        if idx and wt_sha and idx["sha"] != wt_sha:
            idx_data: bytes = b""
            with contextlib.suppress(FileNotFoundError, TypeError):
                idx_data = repo.objects.read_blob(idx["sha"]).data
            _print_diff_with_bytes(
                DiffEntry(
                    status=DiffStatus.MODIFIED,
                    path=path,
                    old_sha=idx["sha"],
                    new_sha=wt_sha,
                    old_mode=idx["mode"],
                    new_mode=idx["mode"],
                ),
                idx_data,
                wt_bytes or b"",
            )
        elif idx and not wt_sha:
            idx_data2: bytes = b""
            with contextlib.suppress(FileNotFoundError, TypeError):
                idx_data2 = repo.objects.read_blob(idx["sha"]).data
            _print_diff_with_bytes(
                DiffEntry(
                    status=DiffStatus.DELETED,
                    path=path,
                    old_sha=idx["sha"],
                    new_sha=None,
                    old_mode=idx["mode"],
                    new_mode=None,
                ),
                idx_data2,
                b"",
            )
        elif not idx and wt_sha:
            _print_diff_with_bytes(
                DiffEntry(
                    status=DiffStatus.ADDED,
                    path=path,
                    old_sha=None,
                    new_sha=wt_sha,
                    old_mode=None,
                    new_mode="100644",
                ),
                b"",
                wt_bytes or b"",
            )
    return 0
