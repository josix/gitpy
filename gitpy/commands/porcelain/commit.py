"""Implementation of ``git commit``.

Creates a commit from the current index.
"""

import os
import sys

from gitpy.index.operations import write_tree
from gitpy.objects.commit import Commit, Identity
from gitpy.refs.head import Head
from gitpy.refs.reflog import ZERO_SHA
from gitpy.repository import Repository


def _resolve_identity(repo: Repository, prefix: str) -> Identity:
    """Build an Identity from environment variables or git config.

    Priority: GIT_{prefix}_NAME/EMAIL env vars, then repo config
    user.name/user.email, then fallback defaults.

    Args:
        repo: Repository used for config lookups.
        prefix: "AUTHOR" or "COMMITTER".

    Returns:
        Identity for the commit.
    """
    name = (
        os.environ.get(f"GIT_{prefix}_NAME")
        or repo.config.get("user.name")
        or "Unknown"
    )
    email = (
        os.environ.get(f"GIT_{prefix}_EMAIL")
        or repo.config.get("user.email")
        or "unknown@example.com"
    )
    date_str = os.environ.get(f"GIT_{prefix}_DATE", "")

    if date_str:
        parts = date_str.split()
        timestamp = int(parts[0])
        tz_offset = parts[1] if len(parts) > 1 else "+0000"
        return Identity(
            name=name, email=email, timestamp=timestamp, tz_offset=tz_offset
        )

    return Identity.now(name, email)


def commit(repo: Repository, message: str, *, amend: bool = False) -> int:
    """Create a commit from the current index.

    Args:
        repo: Repository to commit to.
        message: Commit message text.
        amend: If True, replace the current HEAD commit (``--amend``).

    Returns:
        0 on success, 1 on error.
    """
    if amend:
        return _commit_amend(repo, message)
    return _commit_normal(repo, message)


def _commit_normal(repo: Repository, message: str) -> int:
    """Create a regular commit from the current index.

    Args:
        repo: Repository to commit to.
        message: Commit message text.

    Returns:
        0 on success, 1 on error.
    """
    index = repo.index.read()
    tree_sha = write_tree(index, repo.objects)

    parent_shas: list[str] = []
    old_head_sha = ZERO_SHA

    head = repo.head.read()
    try:
        old_head_sha = repo.head.resolve(repo.refs)
        parent_shas = [old_head_sha]
    except ValueError:
        old_head_sha = ZERO_SHA

    author = _resolve_identity(repo, "AUTHOR")
    committer = _resolve_identity(repo, "COMMITTER")

    commit_obj = Commit(
        tree_sha=tree_sha,
        parent_shas=parent_shas,
        author=author,
        committer=committer,
        message=message,
    )
    commit_sha = repo.objects.write(commit_obj)

    _update_refs_and_reflog(
        repo,
        head,
        old_head_sha,
        commit_sha,
        committer,
        f"commit: {message.splitlines()[0]}",
    )

    short_sha = commit_sha[:7]
    subject = message.splitlines()[0]
    branch_name = head.branch or "(detached HEAD)"
    print(f"[{branch_name} {short_sha}] {subject}")
    return 0


def _commit_amend(repo: Repository, message: str) -> int:
    """Amend the current HEAD commit with the index and *message*.

    The new commit reuses the *parents* of the current HEAD commit so that
    the amended commit replaces the tip rather than building on top of it.

    Args:
        repo: Repository to amend.
        message: New commit message.

    Returns:
        0 on success, 1 on error.
    """
    head = repo.head.read()

    # Resolve HEAD to an existing commit (amend requires one).
    try:
        old_head_sha = repo.head.resolve(repo.refs)
    except ValueError:
        print(
            "error: You have nothing to amend — no commits yet on this branch.",
            file=sys.stderr,
        )
        return 1

    old_commit = repo.objects.read_commit(old_head_sha)

    index = repo.index.read()
    tree_sha = write_tree(index, repo.objects)

    # Reuse the original commit's parents (not HEAD itself).
    parent_shas = old_commit.parent_shas

    # Keep the original author; update committer to now.
    author = old_commit.author or _resolve_identity(repo, "AUTHOR")
    committer = _resolve_identity(repo, "COMMITTER")

    amended_commit = Commit(
        tree_sha=tree_sha,
        parent_shas=parent_shas,
        author=author,
        committer=committer,
        message=message,
    )
    commit_sha = repo.objects.write(amended_commit)

    _update_refs_and_reflog(
        repo,
        head,
        old_head_sha,
        commit_sha,
        committer,
        f"commit (amend): {message.splitlines()[0]}",
    )

    short_sha = commit_sha[:7]
    subject = message.splitlines()[0]
    branch_name = head.branch or "(detached HEAD)"
    print(f"[{branch_name} {short_sha}] {subject}")
    return 0


def _update_refs_and_reflog(
    repo: Repository,
    head: Head,
    old_sha: str,
    new_sha: str,
    committer: Identity,
    reflog_msg: str,
) -> None:
    """Update the branch ref (or detached HEAD) and append reflog entries.

    Args:
        repo: Repository to update.
        head: Current HEAD state.
        old_sha: Previous commit SHA (ZERO_SHA for the initial commit).
        new_sha: New commit SHA to point to.
        committer: Committer identity for reflog.
        reflog_msg: Message for the reflog entry.
    """
    if head.is_detached:
        repo.head.set_detached(new_sha)
    else:
        branch_ref = head.target
        repo.refs.write(branch_ref, new_sha)

    repo.reflog.append(
        ref="HEAD",
        old_sha=old_sha,
        new_sha=new_sha,
        identity=committer,
        message=reflog_msg,
    )
    if not head.is_detached and head.target:
        repo.reflog.append(
            ref=head.target,
            old_sha=old_sha,
            new_sha=new_sha,
            identity=committer,
            message=reflog_msg,
        )
