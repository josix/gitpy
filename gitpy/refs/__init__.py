"""Git references implementation.

Exports all public types and classes for managing Git references:
HEAD, branches, tags, reflog, and revision expressions.
"""

from .branch import Branch, BranchManager
from .head import Head, HeadManager, HeadState
from .manager import RefManager
from .reflog import ZERO_SHA, Reflog, ReflogEntry
from .revision import RevisionParser
from .tag import AnnotatedTag, LightweightTag, TagManager, TagType

__all__ = [
    "RefManager",
    "Head",
    "HeadManager",
    "HeadState",
    "Branch",
    "BranchManager",
    "LightweightTag",
    "AnnotatedTag",
    "TagManager",
    "TagType",
    "Reflog",
    "ReflogEntry",
    "ZERO_SHA",
    "RevisionParser",
]
