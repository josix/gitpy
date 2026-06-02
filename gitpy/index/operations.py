"""Index operations: read_tree, write_tree, status, conflicts.

These functions implement the core operations that bridge the index with
the object database and the working directory.
"""

from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from gitpy.objects.blob import Blob
from gitpy.objects.tree import Tree, TreeEntry
from gitpy.storage.database import ObjectDatabase

from .entry import IndexEntry
from .index import Index

# ---------------------------------------------------------------------------
# read_tree
# ---------------------------------------------------------------------------


def read_tree(
    index: Index,
    tree_sha: str,
    db: ObjectDatabase,
    prefix: str = "",
) -> None:
    """Populate *index* from a tree object (recursive).

    This is the core of ``git read-tree``.  Existing entries for paths
    under *prefix* are replaced; entries outside *prefix* are untouched.

    Args:
        index: Index to populate.
        tree_sha: SHA-1 of the root tree to read.
        db: Object database.
        prefix: Path prefix prepended to every entry name.
    """
    tree = db.read_tree(tree_sha)

    for te in tree.entries:
        path = f"{prefix}{te.name}" if prefix else te.name

        if te.is_tree:
            read_tree(index, te.sha, db, prefix=f"{path}/")
        else:
            index_entry = IndexEntry(
                ctime_s=0,
                ctime_ns=0,
                mtime_s=0,
                mtime_ns=0,
                dev=0,
                ino=0,
                mode=int(te.mode, 8),
                uid=0,
                gid=0,
                size=0,
                sha=te.sha,
                flags=min(len(path.encode("utf-8")), 0xFFF),
                path=path,
            )
            index.add(index_entry)


# ---------------------------------------------------------------------------
# write_tree
# ---------------------------------------------------------------------------


def write_tree(index: Index, db: ObjectDatabase) -> str:
    """Create tree objects from the index.

    This is the core of ``git write-tree``.

    Args:
        index: Index to convert.
        db: Object database to write trees into.

    Returns:
        SHA-1 of the root tree object.
    """
    return _write_tree_recursive(index, db, "")


def _write_tree_recursive(
    index: Index,
    db: ObjectDatabase,
    prefix: str,
) -> str:
    """Recursively build a tree for the directory indicated by *prefix*.

    Args:
        index: Full index (all entries).
        db: Object database.
        prefix: Slash-terminated directory prefix, or "" for root.

    Returns:
        SHA-1 of the created Tree object.
    """
    tree_entries: list[TreeEntry] = []
    seen_dirs: set[str] = set()

    for index_entry in index:
        path = index_entry.path

        if prefix and not path.startswith(prefix):
            continue

        rel = path[len(prefix) :]

        if "/" in rel:
            subdir = rel.split("/")[0]
            if subdir not in seen_dirs:
                seen_dirs.add(subdir)
                subtree_sha = _write_tree_recursive(index, db, f"{prefix}{subdir}/")
                tree_entries.append(
                    TreeEntry(mode="40000", name=subdir, sha=subtree_sha)
                )
        else:
            # Convert numeric mode to the octal string Tree expects.
            mode_str = oct(index_entry.mode)[2:]
            tree_entries.append(TreeEntry(mode=mode_str, name=rel, sha=index_entry.sha))

    tree = Tree(entries=tree_entries)
    return db.write(tree)


# ---------------------------------------------------------------------------
# Status
# ---------------------------------------------------------------------------


class FileStatus(Enum):
    """Status of a file relative to index or HEAD."""

    UNMODIFIED = "unmodified"
    MODIFIED = "modified"
    DELETED = "deleted"
    UNTRACKED = "untracked"
    ADDED = "added"


@dataclass(slots=True)
class StatusEntry:
    """Status of a single file path.

    Attributes:
        path: Repository-relative file path.
        index_status: Comparison of index vs HEAD (staged changes).
        worktree_status: Comparison of working directory vs index (unstaged).
    """

    path: str
    index_status: FileStatus
    worktree_status: FileStatus


def get_status(
    index: Index,
    head_tree_sha: str | None,
    worktree: Path,
    db: ObjectDatabase,
) -> list[StatusEntry]:
    """Compare index and working directory against HEAD.

    Args:
        index: Current index.
        head_tree_sha: SHA-1 of the HEAD commit's tree, or None for a new repo.
        worktree: Absolute path to the working directory.
        db: Object database.

    Returns:
        List of StatusEntry for every path that is not fully unmodified.
    """
    # Collect all stage-0 paths in the current index.
    all_paths: set[str] = {path for (path, stage) in index.entries if stage == 0}

    # Populate HEAD entries.
    head_index: Index | None = None
    if head_tree_sha:
        head_index = Index()
        read_tree(head_index, head_tree_sha, db)
        all_paths.update(path for (path, stage) in head_index.entries if stage == 0)

    # Add working-directory paths.
    for wt_path in worktree.rglob("*"):
        if wt_path.is_file() and ".git" not in wt_path.parts:
            rel = str(wt_path.relative_to(worktree))
            all_paths.add(rel)

    results: list[StatusEntry] = []

    for path in sorted(all_paths):
        index_entry = index.get(path)
        head_entry = head_index.get(path) if head_index else None
        wt_file = worktree / path

        index_status, worktree_status = _compute_file_status(
            index_entry, head_entry, wt_file
        )

        if (
            index_status is not FileStatus.UNMODIFIED
            or worktree_status is not FileStatus.UNMODIFIED
        ):
            results.append(
                StatusEntry(
                    path=path,
                    index_status=index_status,
                    worktree_status=worktree_status,
                )
            )

    return results


def _compute_file_status(
    index_entry: IndexEntry | None,
    head_entry: IndexEntry | None,
    wt_file: Path,
) -> tuple[FileStatus, FileStatus]:
    """Compute the index-vs-HEAD and worktree-vs-index status for one path.

    Args:
        index_entry: Current stage-0 index entry, or None if absent.
        head_entry: HEAD tree entry, or None if absent.
        wt_file: Absolute path to the working-tree file.

    Returns:
        ``(index_status, worktree_status)`` tuple.
    """
    # --- index vs HEAD ---
    if index_entry and head_entry:
        index_status = (
            FileStatus.UNMODIFIED
            if index_entry.sha == head_entry.sha
            else FileStatus.MODIFIED
        )
    elif index_entry:
        index_status = FileStatus.ADDED
    elif head_entry:
        index_status = FileStatus.DELETED
    else:
        index_status = FileStatus.UNTRACKED

    # --- worktree vs index ---
    if index_entry:
        if not wt_file.exists():
            worktree_status = FileStatus.DELETED
        elif _file_modified(index_entry, wt_file):
            worktree_status = FileStatus.MODIFIED
        else:
            worktree_status = FileStatus.UNMODIFIED
    else:
        worktree_status = (
            FileStatus.UNTRACKED if wt_file.exists() else FileStatus.UNMODIFIED
        )

    return index_status, worktree_status


def _file_modified(entry: IndexEntry, path: Path) -> bool:
    """Return True when the file at *path* differs from *entry*.

    Uses cached stat for a fast path; falls back to SHA computation.

    Args:
        entry: IndexEntry with cached stat.
        path: Absolute path to the file.

    Returns:
        True if the file content differs from the indexed blob.
    """
    st = path.stat()
    if entry.matches_stat(st):
        return False
    current_blob = Blob.from_file(str(path))
    return current_blob.oid != entry.sha


# ---------------------------------------------------------------------------
# Merge conflict helpers
# ---------------------------------------------------------------------------


def has_conflicts(index: Index) -> bool:
    """Return True when any entry in *index* has a non-zero merge stage.

    Args:
        index: Index to inspect.

    Returns:
        True if there is at least one conflicted entry.
    """
    return any(e.stage != 0 for e in index)


def get_conflicts(index: Index) -> dict[str, list[IndexEntry]]:
    """Return conflicted entries grouped by path.

    Args:
        index: Index to inspect.

    Returns:
        Mapping from path to list of IndexEntry objects (stages 1–3).
    """
    conflicts: dict[str, list[IndexEntry]] = {}
    for entry in index:
        if entry.stage != 0:
            conflicts.setdefault(entry.path, []).append(entry)
    return conflicts


def add_conflict(
    index: Index,
    path: str,
    base: IndexEntry | None,
    ours: IndexEntry | None,
    theirs: IndexEntry | None,
) -> None:
    """Record a merge conflict for *path* in the index.

    Removes any stage-0 entry for *path* and adds the three conflict stages.

    Args:
        index: Index to modify.
        path: Conflicted file path.
        base: Stage-1 (common ancestor) entry, or None.
        ours: Stage-2 (current branch) entry, or None.
        theirs: Stage-3 (incoming branch) entry, or None.
    """
    index.remove(path)

    if base is not None:
        base.flags = (base.flags & 0x0FFF) | (1 << 12)
        index.add(base)
    if ours is not None:
        ours.flags = (ours.flags & 0x0FFF) | (2 << 12)
        index.add(ours)
    if theirs is not None:
        theirs.flags = (theirs.flags & 0x0FFF) | (3 << 12)
        index.add(theirs)


def resolve_conflict(index: Index, path: str, sha: str, mode: int) -> None:
    """Resolve a merge conflict by creating a stage-0 entry.

    Removes all staged conflict entries for *path* and adds a clean
    stage-0 entry.

    Args:
        index: Index to modify.
        path: Conflicted file path to resolve.
        sha: 40-character hex SHA-1 of the resolved blob.
        mode: File mode integer (e.g. 0o100644).
    """
    # Remove all entries for this path (all stages).
    index.remove(path)

    resolved = IndexEntry(
        ctime_s=0,
        ctime_ns=0,
        mtime_s=0,
        mtime_ns=0,
        dev=0,
        ino=0,
        mode=mode,
        uid=0,
        gid=0,
        size=0,
        sha=sha,
        flags=min(len(path.encode("utf-8")), 0xFFF),
        path=path,
    )
    index.add(resolved)
