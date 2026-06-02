"""Implementation of ``git status``.

Shows the working tree status relative to HEAD and the index.
"""

from gitpy.index.operations import FileStatus, get_status
from gitpy.repository import Repository

_INDEX_SHORT: dict[FileStatus, str] = {
    FileStatus.ADDED: "A",
    FileStatus.MODIFIED: "M",
    FileStatus.DELETED: "D",
    FileStatus.UNTRACKED: "?",
    FileStatus.UNMODIFIED: " ",
}

_WORKTREE_SHORT: dict[FileStatus, str] = {
    FileStatus.MODIFIED: "M",
    FileStatus.DELETED: "D",
    FileStatus.UNTRACKED: "?",
    FileStatus.UNMODIFIED: " ",
    FileStatus.ADDED: " ",
}


def _head_tree_sha(repo: Repository) -> str | None:
    """Return the tree SHA of the current HEAD commit, or None.

    Args:
        repo: Repository to inspect.

    Returns:
        40-char tree SHA, or None if no commits exist.
    """
    try:
        commit_sha = repo.head.resolve(repo.refs)
        commit = repo.objects.read_commit(commit_sha)
        return commit.tree_sha
    except (ValueError, FileNotFoundError):
        return None


def status(repo: Repository, *, short: bool = False) -> int:
    """Show the working tree status.

    Args:
        repo: Repository to inspect.
        short: If True, use the short (``-s``) format.

    Returns:
        0 always (status does not indicate errors via exit code).
    """
    head_tree = _head_tree_sha(repo)
    index = repo.index.read()
    entries = get_status(index, head_tree, repo.worktree, repo.objects)

    if short:
        for entry in entries:
            x = _INDEX_SHORT.get(entry.index_status, " ")
            y = _WORKTREE_SHORT.get(entry.worktree_status, " ")
            print(f"{x}{y} {entry.path}")
        return 0

    # Long format
    head = repo.head.read()
    branch = head.branch
    if branch:
        print(f"On branch {branch}")
    else:
        print("HEAD detached")

    if not entries:
        print("nothing to commit, working tree clean")
        return 0

    staged = [e for e in entries if e.index_status is not FileStatus.UNMODIFIED]
    unstaged = [
        e
        for e in entries
        if e.worktree_status is not FileStatus.UNMODIFIED
        and e.index_status is not FileStatus.UNTRACKED
    ]
    untracked = [e for e in entries if e.index_status is FileStatus.UNTRACKED]

    if staged:
        print("\nChanges to be committed:")
        for entry in staged:
            label = entry.index_status.value
            print(f"\t{label}: {entry.path}")

    if unstaged:
        print("\nChanges not staged for commit:")
        for entry in unstaged:
            label = entry.worktree_status.value
            print(f"\t{label}: {entry.path}")

    if untracked:
        print("\nUntracked files:")
        for entry in untracked:
            print(f"\t{entry.path}")

    return 0
