"""Implementation of ``git add``.

Stages files to the index.
"""

import os
import stat as _stat

from gitpy.index.entry import IndexEntry
from gitpy.objects.blob import Blob
from gitpy.repository import Repository


def add(repo: Repository, paths: list[str], *, all: bool = False) -> int:
    """Stage files to the index.

    Args:
        repo: Repository to operate on.
        paths: Relative paths to stage.
        all: When True, stage all tracked and modified files in the worktree
             (``git add -A``). Ignores any path under ``.git``.  Also removes
             index entries for tracked files that no longer exist on disk.

    Returns:
        0 on success, 1 if any path does not exist.
    """
    index = repo.index.read()

    if all:
        # Remove index entries whose worktree file no longer exists.
        stale = [
            entry.path
            for entry in index
            if not (repo.worktree / entry.path).exists()
            and not (repo.worktree / entry.path).is_symlink()
        ]
        for stale_path in stale:
            index.remove(stale_path)

        paths = _collect_all_paths(repo)

    for rel_path in paths:
        full_path = repo.worktree / rel_path
        # Use lstat so we can detect symlinks before is_file() hides them.
        try:
            lst = full_path.lstat()
        except FileNotFoundError:
            print(f"error: pathspec '{rel_path}' did not match any files")
            return 1

        if _stat.S_ISLNK(lst.st_mode):
            # Blob content for a symlink is the link-target path.
            link_target = os.readlink(full_path)
            blob = Blob(data=link_target.encode())
        else:
            blob = Blob.from_file(full_path)

        sha = repo.objects.write(blob)
        entry = IndexEntry.from_path(rel_path, sha, repo.worktree)
        index.add(entry)

    repo.index.write(index)
    return 0


def _collect_all_paths(repo: Repository) -> list[str]:
    """Walk the worktree and return all file/symlink paths excluding .git.

    Args:
        repo: Repository to walk.

    Returns:
        List of repository-relative path strings.
    """
    result: list[str] = []
    for wt_path in repo.worktree.rglob("*"):
        if ".git" not in wt_path.parts and (wt_path.is_file() or wt_path.is_symlink()):
            result.append(str(wt_path.relative_to(repo.worktree)))
    return result
