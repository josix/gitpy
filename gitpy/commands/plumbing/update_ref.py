"""Implementation of ``git update-ref``.

Creates, updates, or deletes a Git reference.
"""

from gitpy.repository import Repository


def update_ref(
    repo: Repository,
    ref: str,
    newvalue: str | None,
    *,
    delete: bool = False,
) -> int:
    """Create, update, or delete a Git reference.

    Args:
        repo: Repository whose ref manager is used.
        ref: Fully-qualified ref name (e.g. ``refs/heads/main``).
        newvalue: New SHA-1 to write.  Ignored when *delete* is True.
        delete: When True, delete the reference rather than writing it.

    Returns:
        0 on success, 1 on error.
    """
    if delete:
        repo.refs.delete(ref)
        return 0

    if newvalue is None:
        return 1

    try:
        repo.refs.write(ref, newvalue)
    except ValueError:
        return 1

    return 0
