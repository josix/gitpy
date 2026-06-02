"""Plumbing command implementations.

Each command is a framework-agnostic function that takes an explicit
Repository and typed parameters, returning an int exit code. Output
is written to an injectable stream (defaulting to sys.stdout or
sys.stdout.buffer where appropriate).
"""

from .cat_file import cat_file
from .commit_tree import commit_tree
from .hash_object import hash_object
from .ls_tree import ls_tree
from .update_ref import update_ref
from .write_tree import write_tree_cmd

__all__ = [
    "hash_object",
    "cat_file",
    "ls_tree",
    "write_tree_cmd",
    "commit_tree",
    "update_ref",
]
