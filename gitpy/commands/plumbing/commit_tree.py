"""Implementation of ``git commit-tree``.

Creates a new commit object from a tree SHA, parent list, and message.
Identity is taken from environment variables with sensible fallbacks.
"""

import os

from gitpy.objects.commit import Commit, Identity
from gitpy.repository import Repository


def _identity_from_env(prefix: str) -> Identity:
    """Build an Identity from ``GIT_{prefix}_NAME/EMAIL/DATE`` env vars.

    Falls back to safe defaults when variables are absent.

    Args:
        prefix: Either "AUTHOR" or "COMMITTER".

    Returns:
        Identity populated from the environment (or defaults).
    """
    name = os.environ.get(f"GIT_{prefix}_NAME", "Unknown")
    email = os.environ.get(f"GIT_{prefix}_EMAIL", "unknown@example.com")
    date_str = os.environ.get(f"GIT_{prefix}_DATE", "")

    if date_str:
        # Accept "<timestamp> <tz>" format, e.g. "1700000000 +0000".
        parts = date_str.split()
        timestamp = int(parts[0])
        tz_offset = parts[1] if len(parts) > 1 else "+0000"
        return Identity(
            name=name, email=email, timestamp=timestamp, tz_offset=tz_offset
        )

    return Identity.now(name, email)


def commit_tree(
    repo: Repository,
    tree: str,
    *,
    parents: list[str],
    message: str,
) -> str:
    """Create a new commit object and return its SHA.

    Author and committer identities are sourced from
    ``GIT_AUTHOR_NAME``, ``GIT_AUTHOR_EMAIL``, ``GIT_AUTHOR_DATE``,
    ``GIT_COMMITTER_NAME``, ``GIT_COMMITTER_EMAIL``, and
    ``GIT_COMMITTER_DATE`` environment variables, with defaults when absent.

    Args:
        repo: Repository whose object database receives the new commit.
        tree: 40-char hex SHA-1 of the root tree object.
        parents: List of parent commit SHAs (empty list for a root commit).
        message: Commit message text.

    Returns:
        40-character hex SHA-1 of the newly created commit object.
    """
    author = _identity_from_env("AUTHOR")
    committer = _identity_from_env("COMMITTER")

    commit = Commit(
        tree_sha=tree,
        parent_shas=parents,
        author=author,
        committer=committer,
        message=message,
    )
    return repo.objects.write(commit)
