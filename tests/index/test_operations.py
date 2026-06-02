"""Tests for index operations: read_tree, write_tree, get_status."""

from pathlib import Path

from gitpy.index.entry import IndexEntry
from gitpy.index.index import Index
from gitpy.index.operations import (
    FileStatus,
    add_conflict,
    get_conflicts,
    get_status,
    has_conflicts,
    read_tree,
    resolve_conflict,
    write_tree,
)
from gitpy.objects.blob import Blob
from gitpy.repository import Repository
from gitpy.storage.database import ObjectDatabase

# Reference hashes (must match real Git)
EMPTY_TREE_SHA = "4b825dc642cb6eb9a060e54bf8d69288fbee4904"
HELLO_BLOB_SHA = "ce013625030ba8dba906f756967f9e9ca394464a"

FAKE_SHA = "a" * 40


def _repo(tmp_path: Path) -> tuple[Repository, ObjectDatabase]:
    repo = Repository.init(tmp_path)
    return repo, repo.objects


class TestWriteTreeEmptyIndex:
    def test_empty_index_produces_empty_tree(self, tmp_path: Path) -> None:
        """write_tree of an empty index must equal the well-known empty tree SHA."""
        _, db = _repo(tmp_path)
        idx = Index()
        sha = write_tree(idx, db)
        assert sha == EMPTY_TREE_SHA


class TestHelloBlob:
    def test_hello_blob_sha(self, tmp_path: Path) -> None:
        """b'hello\\n' blob must hash to the reference SHA."""
        _, db = _repo(tmp_path)
        blob = Blob(data=b"hello\n")
        sha = db.write(blob)
        assert sha == HELLO_BLOB_SHA


class TestWriteAndReadTreeRoundtrip:
    def test_single_file_roundtrip(self, tmp_path: Path) -> None:
        """Stage a blob, write_tree, then read_tree reproduces the entry."""
        _, db = _repo(tmp_path)

        blob = Blob(data=b"hello\n")
        blob_sha = db.write(blob)
        assert blob_sha == HELLO_BLOB_SHA

        idx = Index()
        idx.add(
            IndexEntry(
                ctime_s=0,
                ctime_ns=0,
                mtime_s=0,
                mtime_ns=0,
                dev=0,
                ino=0,
                mode=0o100644,
                uid=0,
                gid=0,
                size=6,
                sha=blob_sha,
                flags=len("hello.txt"),
                path="hello.txt",
            )
        )

        tree_sha = write_tree(idx, db)

        restored_idx = Index()
        read_tree(restored_idx, tree_sha, db)

        assert "hello.txt" in restored_idx
        e = restored_idx.get("hello.txt")
        assert e is not None
        assert e.sha == HELLO_BLOB_SHA
        assert e.mode == 0o100644

    def test_nested_dir_builds_subtree(self, tmp_path: Path) -> None:
        """Nested paths cause a subtree to be created."""
        _, db = _repo(tmp_path)

        blob_sha = db.write(Blob(data=b"data"))

        idx = Index()
        for path in ["src/main.py", "src/util.py", "README.md"]:
            idx.add(
                IndexEntry(
                    ctime_s=0,
                    ctime_ns=0,
                    mtime_s=0,
                    mtime_ns=0,
                    dev=0,
                    ino=0,
                    mode=0o100644,
                    uid=0,
                    gid=0,
                    size=4,
                    sha=blob_sha,
                    flags=len(path),
                    path=path,
                )
            )

        tree_sha = write_tree(idx, db)

        restored_idx = Index()
        read_tree(restored_idx, tree_sha, db)

        assert "src/main.py" in restored_idx
        assert "src/util.py" in restored_idx
        assert "README.md" in restored_idx

    def test_write_tree_then_read_tree_identical_shas(self, tmp_path: Path) -> None:
        """write_tree followed by read_tree gives back the same blob SHAs."""
        _, db = _repo(tmp_path)

        sha_a = db.write(Blob(data=b"file A"))
        sha_b = db.write(Blob(data=b"file B"))

        idx = Index()
        idx.add(
            IndexEntry(
                ctime_s=0,
                ctime_ns=0,
                mtime_s=0,
                mtime_ns=0,
                dev=0,
                ino=0,
                mode=0o100644,
                uid=0,
                gid=0,
                size=6,
                sha=sha_a,
                flags=len("a.txt"),
                path="a.txt",
            )
        )
        idx.add(
            IndexEntry(
                ctime_s=0,
                ctime_ns=0,
                mtime_s=0,
                mtime_ns=0,
                dev=0,
                ino=0,
                mode=0o100644,
                uid=0,
                gid=0,
                size=6,
                sha=sha_b,
                flags=len("b.txt"),
                path="b.txt",
            )
        )

        tree_sha = write_tree(idx, db)
        restored = Index()
        read_tree(restored, tree_sha, db)

        assert restored.get("a.txt").sha == sha_a  # type: ignore[union-attr]
        assert restored.get("b.txt").sha == sha_b  # type: ignore[union-attr]


class TestGetStatus:
    def _blob_entry(
        self,
        path: str,
        sha: str,
        size: int = 0,
    ) -> IndexEntry:
        return IndexEntry(
            ctime_s=0,
            ctime_ns=0,
            mtime_s=0,
            mtime_ns=0,
            dev=0,
            ino=0,
            mode=0o100644,
            uid=0,
            gid=0,
            size=size,
            sha=sha,
            flags=len(path),
            path=path,
        )

    def test_added_file(self, tmp_path: Path) -> None:
        """File in index but not in HEAD shows as ADDED."""
        _, db = _repo(tmp_path)
        sha = db.write(Blob(data=b"new"))

        idx = Index()
        idx.add(self._blob_entry("new.txt", sha))

        statuses = get_status(idx, None, tmp_path, db)
        entry = next(s for s in statuses if s.path == "new.txt")
        assert entry.index_status == FileStatus.ADDED

    def test_deleted_file(self, tmp_path: Path) -> None:
        """File in HEAD but removed from index shows as DELETED."""
        _, db = _repo(tmp_path)
        sha = db.write(Blob(data=b"gone"))

        # Build a HEAD tree with the file.
        head_idx = Index()
        head_idx.add(self._blob_entry("gone.txt", sha))
        head_tree = write_tree(head_idx, db)

        # Index does NOT have the file.
        idx = Index()
        statuses = get_status(idx, head_tree, tmp_path, db)
        entry = next(s for s in statuses if s.path == "gone.txt")
        assert entry.index_status == FileStatus.DELETED

    def test_modified_file(self, tmp_path: Path) -> None:
        """File with different SHA in index vs HEAD shows as MODIFIED."""
        _, db = _repo(tmp_path)
        old_sha = db.write(Blob(data=b"old content"))
        new_sha = db.write(Blob(data=b"new content"))

        head_idx = Index()
        head_idx.add(self._blob_entry("file.txt", old_sha))
        head_tree = write_tree(head_idx, db)

        idx = Index()
        idx.add(self._blob_entry("file.txt", new_sha))

        statuses = get_status(idx, head_tree, tmp_path, db)
        entry = next(s for s in statuses if s.path == "file.txt")
        assert entry.index_status == FileStatus.MODIFIED

    def test_untracked_file_in_worktree(self, tmp_path: Path) -> None:
        """File on disk but not in index shows as UNTRACKED."""
        _, db = _repo(tmp_path)

        untracked = tmp_path / "untracked.txt"
        untracked.write_bytes(b"untracked")

        idx = Index()
        statuses = get_status(idx, None, tmp_path, db)
        entry = next((s for s in statuses if s.path == "untracked.txt"), None)
        assert entry is not None
        assert entry.worktree_status == FileStatus.UNTRACKED

    def test_worktree_modified(self, tmp_path: Path) -> None:
        """File on disk with different content from index shows worktree MODIFIED."""
        _, db = _repo(tmp_path)

        original = b"original"
        sha = db.write(Blob(data=original))

        f = tmp_path / "mod.txt"
        f.write_bytes(b"changed content")

        idx = Index()
        idx.add(self._blob_entry("mod.txt", sha, size=len(original)))

        statuses = get_status(idx, None, tmp_path, db)
        entry = next(s for s in statuses if s.path == "mod.txt")
        assert entry.worktree_status == FileStatus.MODIFIED


class TestConflicts:
    def _make_entry(self, path: str, sha: str = FAKE_SHA) -> IndexEntry:
        return IndexEntry(
            ctime_s=0,
            ctime_ns=0,
            mtime_s=0,
            mtime_ns=0,
            dev=0,
            ino=0,
            mode=0o100644,
            uid=0,
            gid=0,
            size=0,
            sha=sha,
            flags=len(path),
            path=path,
        )

    def test_has_conflicts_false_when_clean(self) -> None:
        idx = Index()
        idx.add(self._make_entry("clean.txt"))
        assert has_conflicts(idx) is False

    def test_has_conflicts_true_when_staged(self) -> None:
        idx = Index()
        e = self._make_entry("conflict.txt")
        add_conflict(idx, "conflict.txt", e, e, e)
        assert has_conflicts(idx) is True

    def test_get_conflicts_returns_entries(self) -> None:
        idx = Index()
        base = self._make_entry("file.txt", "a" * 40)
        ours = self._make_entry("file.txt", "b" * 40)
        theirs = self._make_entry("file.txt", "c" * 40)
        add_conflict(idx, "file.txt", base, ours, theirs)
        conflicts = get_conflicts(idx)
        assert "file.txt" in conflicts
        assert len(conflicts["file.txt"]) == 3

    def test_resolve_conflict_clears_stages(self) -> None:
        idx = Index()
        e = self._make_entry("r.txt")
        add_conflict(idx, "r.txt", e, e, e)
        resolve_conflict(idx, "r.txt", FAKE_SHA, 0o100644)
        assert not has_conflicts(idx)
        assert "r.txt" in idx
        assert idx.get("r.txt").stage == 0  # type: ignore[union-attr]
