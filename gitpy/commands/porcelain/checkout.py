"""Implementation of ``git checkout``.

Switches branches or restores working tree files.
"""

import os
import pathlib
import stat

from gitpy.index.index import Index
from gitpy.index.operations import read_tree
from gitpy.repository import Repository


def checkout(
    repo: Repository,
    target: str | None = None,
    *,
    new_branch: str | None = None,
    paths: list[str] | None = None,
) -> int:
    """Switch branches or restore working tree files.

    Args:
        repo: Repository to operate on.
        target: Branch name, commit SHA, or tag to switch to.
        new_branch: If set, create this branch and switch to it (``-b``).
        paths: If set, restore only these specific paths from index.

    Returns:
        0 on success, 1 on error.
    """
    if new_branch:
        return _create_and_switch(repo, new_branch, target)

    if paths:
        return _restore_paths(repo, paths)

    if target:
        return _switch(repo, target)

    print("error: no target specified")
    return 1


def _create_and_switch(
    repo: Repository, new_branch: str, start_point: str | None
) -> int:
    """Create a new branch and switch to it.

    Args:
        repo: Repository to operate on.
        new_branch: New branch name.
        start_point: Commit or branch to start from; defaults to HEAD.

    Returns:
        0 on success, 1 on error.
    """
    if start_point:
        sha = repo.refs.resolve(start_point)
        if sha is None:
            print(f"error: pathspec '{start_point}' did not match any file(s)")
            return 1
    else:
        try:
            sha = repo.head.resolve(repo.refs)
        except ValueError:
            print("error: Not a valid object name 'HEAD'")
            return 1

    try:
        repo.branches.create(new_branch, sha)
    except ValueError as exc:
        print(f"error: {exc}")
        return 1

    repo.head.set_branch(new_branch)
    print(f"Switched to a new branch '{new_branch}'")
    return 0


def _switch(repo: Repository, target: str) -> int:
    """Switch to an existing branch or commit.

    Args:
        repo: Repository to operate on.
        target: Branch short name or commit SHA.

    Returns:
        0 on success, 1 on error.
    """
    # Check if target is a known branch
    branch_obj = repo.branches.get(target)
    if branch_obj:
        commit_sha = branch_obj.sha
        _checkout_tree(repo, commit_sha)
        repo.head.set_branch(target)
        print(f"Switched to branch '{target}'")
        return 0

    # Try resolving as a raw ref or SHA
    sha = repo.refs.resolve(target)
    if sha is None:
        print(f"error: pathspec '{target}' did not match any file(s) known to git")
        return 1

    _checkout_tree(repo, sha)
    repo.head.set_detached(sha)
    print(f"HEAD is now at {sha[:7]}")
    return 0


def _restore_paths(repo: Repository, paths: list[str]) -> int:
    """Restore specific paths from the index to the working tree.

    Args:
        repo: Repository to operate on.
        paths: List of repository-relative paths to restore.

    Returns:
        0 on success, 1 if any path is missing from the index.
    """
    index = repo.index.read()
    for rel_path in paths:
        entry = index.get(rel_path)
        if entry is None:
            print(f"error: pathspec '{rel_path}' did not match any file(s)")
            return 1
        full_path = _safe_worktree_path(repo.worktree, rel_path)
        if full_path is None:
            print(f"error: unsafe path '{rel_path}' skipped")
            return 1
        blob = repo.objects.read_blob(entry.sha)
        full_path.parent.mkdir(parents=True, exist_ok=True)
        if full_path.exists() or full_path.is_symlink():
            full_path.unlink()
        if entry.mode == 0o120000:
            os.symlink(blob.data.decode("utf-8", errors="replace"), full_path)
        else:
            full_path.write_bytes(blob.data)
            if entry.mode == 0o100755:
                current = stat.S_IMODE(full_path.stat().st_mode)
                full_path.chmod(current | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    return 0


def _safe_worktree_path(worktree: pathlib.Path, rel_path: str) -> pathlib.Path | None:
    """Resolve *rel_path* under *worktree* and verify it stays within.

    Args:
        worktree: Absolute path to the repository working directory.
        rel_path: Repository-relative path from a tree entry.

    Returns:
        Resolved absolute path if safe, None if it would escape the worktree.
    """
    wt = worktree.resolve()
    candidate = (wt / rel_path).resolve()
    try:
        candidate.relative_to(wt)
    except ValueError:
        return None
    return candidate


def _remove_stale_files(worktree: pathlib.Path, stale_paths: set[str]) -> None:
    """Delete working-tree files no longer tracked and prune empty directories.

    Args:
        worktree: Absolute path to the repository working directory.
        stale_paths: Set of repo-relative paths to remove.
    """
    for stale_path in stale_paths:
        full_path = worktree / stale_path
        if full_path.exists() or full_path.is_symlink():
            full_path.unlink()
        parent = full_path.parent
        while parent != worktree:
            try:
                parent.rmdir()
                parent = parent.parent
            except OSError:
                break


def _write_blob_to_path(full_path: pathlib.Path, data: bytes, mode: int) -> None:
    """Write blob data to *full_path* respecting *mode*.

    Handles symlinks (mode 0o120000) and executable bits (mode 0o100755).

    Args:
        full_path: Absolute destination path (already validated).
        data: Raw blob bytes.
        mode: Git file mode.
    """
    if full_path.exists() or full_path.is_symlink():
        full_path.unlink()

    if mode == 0o120000:
        os.symlink(data.decode("utf-8", errors="replace"), full_path)
    else:
        full_path.write_bytes(data)
        if mode == 0o100755:
            current = stat.S_IMODE(full_path.stat().st_mode)
            full_path.chmod(current | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


def _checkout_tree(repo: Repository, commit_sha: str) -> None:
    """Restore the working tree to match a commit's tree.

    Reads the commit's tree into a fresh index, then writes every blob
    to the corresponding path in the working tree.  Files present in the
    current index but absent from the target tree are deleted.

    Args:
        repo: Repository to operate on.
        commit_sha: SHA of the commit to check out.
    """
    try:
        commit_obj = repo.objects.read_commit(commit_sha)
    except (FileNotFoundError, TypeError):
        return

    old_paths = {entry.path for entry in repo.index.read()}

    tree_sha = commit_obj.tree_sha
    new_index = Index()
    read_tree(new_index, tree_sha, repo.objects)
    new_paths = {entry.path for entry in new_index}

    _remove_stale_files(repo.worktree, old_paths - new_paths)

    for entry in new_index:
        safe = _safe_worktree_path(repo.worktree, entry.path)
        if safe is None:
            print(f"error: unsafe path '{entry.path}' skipped")
            continue

        safe.parent.mkdir(parents=True, exist_ok=True)

        try:
            blob = repo.objects.read_blob(entry.sha)
        except (FileNotFoundError, TypeError):
            continue

        _write_blob_to_path(safe, blob.data, entry.mode)

    repo.index.write(new_index)
