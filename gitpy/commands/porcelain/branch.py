"""Implementation of ``git branch``.

Lists, creates, deletes, or renames branches.
"""

from gitpy.repository import Repository


def branch(
    repo: Repository,
    name: str | None = None,
    *,
    delete: bool = False,
    move: bool = False,
    old: str | None = None,
    new: str | None = None,
    force: bool = False,
) -> int:
    """List, create, delete, or rename branches.

    Args:
        repo: Repository to operate on.
        name: Branch name (for create/delete).
        delete: If True, delete branch *name*.
        move: If True, rename branch from *old* to *new*.
        old: Old branch name for rename.
        new: New branch name for rename.
        force: Force creation/deletion even if branch exists.

    Returns:
        0 on success, 1 on error.
    """
    if move:
        return _rename_branch(repo, old, new, force=force)

    if delete:
        return _delete_branch(repo, name, force=force)

    if name:
        return _create_branch(repo, name, force=force)

    return _list_branches(repo)


def _list_branches(repo: Repository) -> int:
    """Print all branches, marking the current one with ``*``."""
    current = repo.branches.current()
    branches = repo.branches.list()
    if not branches:
        return 0
    for b in branches:
        marker = "* " if b.name == current else "  "
        print(f"{marker}{b.name}")
    return 0


def _create_branch(repo: Repository, name: str, *, force: bool) -> int:
    """Create a new branch at HEAD."""
    try:
        head_sha = repo.head.resolve(repo.refs)
    except ValueError:
        print("error: Not a valid object name: 'HEAD'")
        return 1

    try:
        repo.branches.create(name, head_sha, force=force)
    except ValueError as exc:
        print(f"error: {exc}")
        return 1
    return 0


def _delete_branch(repo: Repository, name: str | None, *, force: bool) -> int:
    """Delete a branch."""
    if not name:
        print("error: branch name required for delete")
        return 1
    try:
        deleted = repo.branches.delete(name, force=force)
    except ValueError as exc:
        print(f"error: {exc}")
        return 1
    if not deleted:
        print(f"error: branch '{name}' not found")
        return 1
    return 0


def _rename_branch(
    repo: Repository, old: str | None, new: str | None, *, force: bool
) -> int:
    """Rename a branch."""
    if not old or not new:
        print("error: old and new branch names required for rename")
        return 1
    try:
        repo.branches.rename(old, new, force=force)
    except ValueError as exc:
        print(f"error: {exc}")
        return 1
    return 0
