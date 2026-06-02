"""Implementation of ``git log``.

Walks the commit history and prints commit information.
"""

from datetime import datetime, timedelta, timezone

from gitpy.objects.commit import Commit, Identity
from gitpy.refs.revision import RevisionParser
from gitpy.repository import Repository


def _format_date(identity: Identity) -> str:
    """Format an Identity timestamp as a human-readable date string.

    Args:
        identity: Identity whose timestamp to format.

    Returns:
        Date string like "Mon Jan 01 00:00:00 2024 +0000".
    """
    ts = identity.timestamp
    tz_str = identity.tz_offset  # e.g. "+0530"
    sign = 1 if tz_str[0] == "+" else -1
    hours = int(tz_str[1:3])
    minutes = int(tz_str[3:5])
    offset = timezone(timedelta(hours=sign * hours, minutes=sign * minutes))
    dt = datetime.fromtimestamp(ts, tz=offset)
    return dt.strftime("%a %b %d %H:%M:%S %Y ") + tz_str


def log(
    repo: Repository,
    revision: str = "HEAD",
    *,
    oneline: bool = False,
    n: int | None = None,
) -> int:
    """Walk and print the commit history.

    Args:
        repo: Repository to inspect.
        revision: Starting revision (default "HEAD").
        oneline: If True, print one line per commit (``<7-sha> <subject>``).
        n: Maximum number of commits to show (None for unlimited).

    Returns:
        0 on success, 1 if the revision cannot be resolved.
    """
    parser = RevisionParser(repo.refs, repo.objects)
    sha = parser.parse(revision)
    if sha is None:
        print(f"fatal: ambiguous argument '{revision}': unknown revision")
        return 1

    count = 0
    current: str | None = sha

    while current is not None:
        if n is not None and count >= n:
            break

        try:
            commit_obj = repo.objects.read_commit(current)
        except (FileNotFoundError, TypeError):
            break

        if oneline:
            _format_oneline_commit(commit_obj, current)
        else:
            _format_long_commit(commit_obj, current)

        count += 1
        current = commit_obj.parent_shas[0] if commit_obj.parent_shas else None

    return 0


def _format_oneline_commit(commit_obj: Commit, sha: str) -> None:
    """Print a one-line summary for *commit_obj*.

    Args:
        commit_obj: Commit object to format.
        sha: Full 40-char SHA of the commit.
    """
    subject = commit_obj.message.splitlines()[0] if commit_obj.message else ""
    print(f"{sha[:7]} {subject}")


def _format_long_commit(commit_obj: Commit, sha: str) -> None:
    """Print the full log entry for *commit_obj*.

    Args:
        commit_obj: Commit object to format.
        sha: Full 40-char SHA of the commit.
    """
    print(f"commit {sha}")
    if commit_obj.author:
        print(f"Author: {commit_obj.author.name} <{commit_obj.author.email}>")
        print(f"Date:   {_format_date(commit_obj.author)}")
    print()
    for line in commit_obj.message.splitlines():
        print(f"    {line}")
    print()
