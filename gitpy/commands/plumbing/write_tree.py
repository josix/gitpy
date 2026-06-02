"""Implementation of ``git write-tree``.

Creates tree objects from the current index.
"""

from gitpy.index.operations import write_tree
from gitpy.repository import Repository


def write_tree_cmd(repo: Repository) -> str:
    """Write the current index as a tree object and return its SHA.

    Reads ``repo.index`` (loading from disk if not already loaded) and
    calls ``gitpy.index.operations.write_tree`` to create the tree objects
    in the repository's object database.

    Args:
        repo: Repository whose index and object database are used.

    Returns:
        40-character hex SHA-1 of the root tree object.
    """
    index = repo.index.read()
    return write_tree(index, repo.objects)
