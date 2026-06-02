"""Tests for the tree diff implementation (gitpy/diff/tree.py)."""

from pathlib import Path

import pytest

from gitpy.diff.tree import (
    DiffStatus,
    diff_trees,
    format_binary_diff,
    is_binary,
)
from gitpy.objects import Blob, Tree, TreeEntry
from gitpy.storage.database import ObjectDatabase

# Known empty-tree SHA (Git canonical constant).
EMPTY_TREE_SHA = "4b825dc642cb6eb9a060e54bf8d69288fbee4904"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def db(tmp_path: Path) -> ObjectDatabase:
    """Create a fresh ObjectDatabase backed by a temporary directory."""
    git_dir = tmp_path / ".git"
    git_dir.mkdir()
    (git_dir / "objects").mkdir()
    return ObjectDatabase(git_dir)


def _make_tree(db: ObjectDatabase, files: dict[str, bytes]) -> str:
    """Write blobs for *files* and return the SHA of a flat tree.

    Args:
        db: ObjectDatabase to write into.
        files: Mapping of filename -> content bytes.

    Returns:
        SHA of the written tree object.
    """
    entries: list[TreeEntry] = []
    for name, content in sorted(files.items()):
        blob = Blob(data=content)
        sha = db.write(blob)
        entries.append(TreeEntry(mode="100644", name=name, sha=sha))
    tree = Tree(entries=entries)
    return db.write(tree)


def _make_nested_tree(
    db: ObjectDatabase,
    structure: dict[str, bytes],
) -> str:
    """Write a nested tree structure.

    Keys in *structure* may contain '/' to denote sub-trees, e.g.
    {"src/main.py": b"...", "README": b"..."}.

    Returns:
        SHA of the root tree.
    """
    # Group by first path component.
    by_dir: dict[str, dict[str, bytes]] = {}
    flat: dict[str, bytes] = {}
    for path, content in structure.items():
        parts = path.split("/", 1)
        if len(parts) == 2:
            parent, rest = parts
            by_dir.setdefault(parent, {})[rest] = content
        else:
            flat[path] = content

    entries: list[TreeEntry] = []
    for name, content in sorted(flat.items()):
        blob = Blob(data=content)
        sha = db.write(blob)
        entries.append(TreeEntry(mode="100644", name=name, sha=sha))

    for dirname, subfiles in sorted(by_dir.items()):
        subtree_sha = _make_nested_tree(db, subfiles)
        entries.append(TreeEntry(mode="40000", name=dirname, sha=subtree_sha))

    tree = Tree(entries=entries)
    return db.write(tree)


# ---------------------------------------------------------------------------
# Empty-tree sentinel
# ---------------------------------------------------------------------------


def test_empty_tree_sha_is_correct(db: ObjectDatabase) -> None:
    """The empty-tree SHA must match the known Git constant."""
    tree = Tree(entries=[])
    sha = db.write(tree)
    assert sha == EMPTY_TREE_SHA


# ---------------------------------------------------------------------------
# Added / deleted / modified detection
# ---------------------------------------------------------------------------


def test_added_files(db: ObjectDatabase) -> None:
    """Files in new tree but not old are ADDED."""
    old_sha = _make_tree(db, {"a.txt": b"old"})
    new_sha = _make_tree(db, {"a.txt": b"old", "b.txt": b"new"})
    entries = list(diff_trees(old_sha, new_sha, db))
    statuses = {e.path: e.status for e in entries}
    assert "b.txt" in statuses
    assert statuses["b.txt"] == DiffStatus.ADDED
    # a.txt unchanged — not in diff
    assert "a.txt" not in statuses


def test_deleted_files(db: ObjectDatabase) -> None:
    """Files in old tree but not new are DELETED."""
    old_sha = _make_tree(db, {"a.txt": b"old", "gone.txt": b"bye"})
    new_sha = _make_tree(db, {"a.txt": b"old"})
    entries = list(diff_trees(old_sha, new_sha, db))
    statuses = {e.path: e.status for e in entries}
    assert statuses["gone.txt"] == DiffStatus.DELETED
    assert "a.txt" not in statuses


def test_modified_files(db: ObjectDatabase) -> None:
    """Files with different content are MODIFIED."""
    old_sha = _make_tree(db, {"file.txt": b"version 1"})
    new_sha = _make_tree(db, {"file.txt": b"version 2"})
    entries = list(diff_trees(old_sha, new_sha, db))
    assert len(entries) == 1
    assert entries[0].status == DiffStatus.MODIFIED
    assert entries[0].path == "file.txt"


def test_unchanged_files_not_in_diff(db: ObjectDatabase) -> None:
    """Unchanged files must not appear in the diff output."""
    content = b"same"
    old_sha = _make_tree(db, {"same.txt": content})
    new_sha = _make_tree(db, {"same.txt": content})
    entries = list(diff_trees(old_sha, new_sha, db))
    assert entries == []


# ---------------------------------------------------------------------------
# None-side (empty tree)
# ---------------------------------------------------------------------------


def test_old_none_all_added(db: ObjectDatabase) -> None:
    """Passing None as old_tree_sha treats it as an empty tree."""
    new_sha = _make_tree(db, {"foo.txt": b"hello"})
    entries = list(diff_trees(None, new_sha, db))
    assert len(entries) == 1
    assert entries[0].status == DiffStatus.ADDED
    assert entries[0].old_sha is None


def test_new_none_all_deleted(db: ObjectDatabase) -> None:
    """Passing None as new_tree_sha treats it as an empty tree."""
    old_sha = _make_tree(db, {"bar.txt": b"hello"})
    entries = list(diff_trees(old_sha, None, db))
    assert len(entries) == 1
    assert entries[0].status == DiffStatus.DELETED
    assert entries[0].new_sha is None


def test_empty_tree_sha_as_old(db: ObjectDatabase) -> None:
    """Using EMPTY_TREE_SHA explicitly works like None."""
    # Write the empty tree so it exists in the db.
    db.write(Tree(entries=[]))
    new_sha = _make_tree(db, {"x.txt": b"x"})
    entries = list(diff_trees(EMPTY_TREE_SHA, new_sha, db))
    assert len(entries) == 1
    assert entries[0].status == DiffStatus.ADDED


# ---------------------------------------------------------------------------
# Nested trees
# ---------------------------------------------------------------------------


def test_nested_tree_added(db: ObjectDatabase) -> None:
    """Added file inside a sub-directory is reported with its full path."""
    old_sha = _make_nested_tree(db, {"src/a.py": b"a"})
    new_sha = _make_nested_tree(db, {"src/a.py": b"a", "src/b.py": b"b"})
    entries = list(diff_trees(old_sha, new_sha, db))
    paths = {e.path for e in entries}
    assert "src/b.py" in paths


def test_nested_tree_modified(db: ObjectDatabase) -> None:
    """Modified file in sub-directory is detected."""
    old_sha = _make_nested_tree(db, {"lib/util.py": b"v1"})
    new_sha = _make_nested_tree(db, {"lib/util.py": b"v2"})
    entries = list(diff_trees(old_sha, new_sha, db))
    assert len(entries) == 1
    assert entries[0].status == DiffStatus.MODIFIED
    assert entries[0].path == "lib/util.py"


# ---------------------------------------------------------------------------
# DiffEntry fields
# ---------------------------------------------------------------------------


def test_diff_entry_shas_populated(db: ObjectDatabase) -> None:
    old_sha = _make_tree(db, {"f.txt": b"old"})
    new_sha = _make_tree(db, {"f.txt": b"new"})
    entries = list(diff_trees(old_sha, new_sha, db))
    assert len(entries) == 1
    entry = entries[0]
    assert entry.old_sha is not None
    assert entry.new_sha is not None
    assert entry.old_sha != entry.new_sha


def test_diff_entry_modes_populated(db: ObjectDatabase) -> None:
    old_sha = _make_tree(db, {"f.txt": b"x"})
    new_sha = _make_tree(db, {"f.txt": b"y"})
    entries = list(diff_trees(old_sha, new_sha, db))
    entry = entries[0]
    assert entry.old_mode == "100644"
    assert entry.new_mode == "100644"


# ---------------------------------------------------------------------------
# Binary detection
# ---------------------------------------------------------------------------


def test_is_binary_with_nul_byte() -> None:
    assert is_binary(b"hello\x00world") is True


def test_is_binary_with_plain_text() -> None:
    assert is_binary(b"hello world\n") is False


def test_is_binary_empty() -> None:
    assert is_binary(b"") is False


def test_binary_blob_reported_not_crash(db: ObjectDatabase) -> None:
    """Diff of a binary file does not raise; format_binary_diff returns correct string."""
    binary_data = b"PNG\x00\x01\x02\x03"
    old_sha = _make_tree(db, {"image.png": binary_data})
    new_sha = _make_tree(db, {"image.png": b"PNG\x00\x01\x02\x04"})
    entries = list(diff_trees(old_sha, new_sha, db))
    assert len(entries) == 1
    entry = entries[0]

    # Read the blobs and check binary detection + message.
    old_blob = db.read_blob(entry.old_sha)  # type: ignore[arg-type]
    assert is_binary(old_blob.data)
    msg = format_binary_diff(entry.path)
    assert "image.png" in msg
    assert "differ" in msg


# ---------------------------------------------------------------------------
# Output ordering
# ---------------------------------------------------------------------------


def test_diff_entries_sorted_by_path(db: ObjectDatabase) -> None:
    """diff_trees must yield entries in sorted path order."""
    old_sha = _make_tree(db, {"z.txt": b"z", "a.txt": b"a"})
    new_sha = _make_tree(db, {"z.txt": b"Z", "a.txt": b"A"})
    entries = list(diff_trees(old_sha, new_sha, db))
    paths = [e.path for e in entries]
    assert paths == sorted(paths)
