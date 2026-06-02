"""Diff engine for gitpy.

Public API:
    EditType, Edit         — Myers edit primitives
    myers_diff             — Compute shortest edit script
    format_unified_diff    — Produce unified diff string
    DiffStatus, DiffEntry  — Tree diff primitives
    diff_trees             — Compare two Git trees
"""

from .myers import Edit, EditType, myers_diff
from .tree import (
    DiffEntry,
    DiffStatus,
    diff_trees,
    flatten_tree,
    format_binary_diff,
    is_binary,
)
from .unified import format_unified_diff

__all__ = [
    "EditType",
    "Edit",
    "myers_diff",
    "format_unified_diff",
    "DiffStatus",
    "DiffEntry",
    "diff_trees",
    "flatten_tree",
    "is_binary",
    "format_binary_diff",
]
