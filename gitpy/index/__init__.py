"""Git index (staging area) package.

Exports the public API for the index subsystem.
"""

from .entry import IndexEntry
from .index import Index, IndexFile
from .operations import (
    FileStatus,
    StatusEntry,
    add_conflict,
    get_conflicts,
    get_status,
    has_conflicts,
    read_tree,
    resolve_conflict,
    write_tree,
)

__all__ = [
    "IndexEntry",
    "Index",
    "IndexFile",
    "read_tree",
    "write_tree",
    "FileStatus",
    "StatusEntry",
    "get_status",
    "has_conflicts",
    "get_conflicts",
    "add_conflict",
    "resolve_conflict",
]
