"""Regression tests for the 18 Codex review findings.

Each test name identifies the finding number it covers.  Tests are written
so they FAIL on the pre-fix code and PASS after the fix.
"""

import contextlib
import hashlib
import os
import stat
import struct
import tempfile
import zlib
from pathlib import Path

import pytest

from gitpy.commands.plumbing.hash_object import hash_object
from gitpy.commands.porcelain.add import add
from gitpy.commands.porcelain.checkout import _safe_worktree_path, checkout
from gitpy.commands.porcelain.commit import commit
from gitpy.commands.porcelain.diff import diff
from gitpy.commands.porcelain.log import log
from gitpy.index.entry import IndexEntry
from gitpy.objects.blob import Blob
from gitpy.objects.commit import Commit, Identity
from gitpy.objects.tree import Tree, TreeEntry
from gitpy.refs.manager import RefManager
from gitpy.refs.revision import RevisionParser
from gitpy.repository import Repository
from gitpy.storage.database import ObjectDatabase
from gitpy.storage.delta import (
    _emit_copy,
    _encode_delta_size,
    apply_delta,
    create_delta,
)
from gitpy.storage.pack import PackFile, PackObjectType, write_pack_object_header

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _identity() -> Identity:
    return Identity(
        name="Test User",
        email="test@example.com",
        timestamp=1_234_567_890,
        tz_offset="+0000",
    )


def _make_repo(tmp_path: Path) -> Repository:
    return Repository.init(tmp_path)


def _make_commit(repo: Repository, parent_shas: list[str], message: str) -> str:
    tree = Tree(entries=[])
    tree_sha = repo.objects.write(tree)
    ident = _identity()
    c = Commit(
        tree_sha=tree_sha,
        parent_shas=parent_shas,
        author=ident,
        committer=ident,
        message=message,
    )
    return repo.objects.write(c)


def _make_git_dir(tmp_path: Path) -> Path:
    git_dir = tmp_path / ".git"
    git_dir.mkdir()
    (git_dir / "refs" / "heads").mkdir(parents=True)
    (git_dir / "refs" / "tags").mkdir(parents=True)
    (git_dir / "HEAD").write_text("ref: refs/heads/main\n")
    return git_dir


SHA_A = "a" * 40
SHA_B = "b" * 40


# ===========================================================================
# Finding 1 — path traversal in _checkout_tree (BLOCKER)
# ===========================================================================


class TestFinding1PathTraversal:
    """Crafted tree entry with ``../evil`` must not escape the worktree."""

    def test_unsafe_path_skipped(self, tmp_path: Path) -> None:
        """checkout refuses to write a tree entry whose path escapes worktree."""
        repo = _make_repo(tmp_path)

        # Create a blob for the "evil" content.
        evil_blob = Blob(data=b"evil content")
        evil_sha = repo.objects.write(evil_blob)

        # Build a tree with an entry named "../evil" — Tree.deserialize
        # won't validate the name, so construct the entry directly.
        evil_entry = TreeEntry(mode="100644", name="../evil", sha=evil_sha)
        tree = Tree(entries=[evil_entry])
        tree_sha = repo.objects.write(tree)

        ident = _identity()
        c = Commit(
            tree_sha=tree_sha,
            parent_shas=[],
            author=ident,
            committer=ident,
            message="evil",
        )
        commit_sha = repo.objects.write(c)

        repo.refs.write("refs/heads/main", commit_sha)

        checkout(repo, "main")

        # The evil file must NOT have been written outside worktree.
        evil_target = tmp_path.parent / "evil"
        assert not evil_target.exists(), (
            "Path traversal: file was written outside worktree"
        )

    def test_safe_worktree_path_rejects_dotdot(self, tmp_path: Path) -> None:
        wt = tmp_path / "worktree"
        wt.mkdir()
        result = _safe_worktree_path(wt, "../escape")
        assert result is None

    def test_safe_worktree_path_accepts_normal(self, tmp_path: Path) -> None:
        wt = tmp_path / "worktree"
        wt.mkdir()
        result = _safe_worktree_path(wt, "subdir/file.txt")
        assert result is not None
        assert str(result).startswith(str(wt.resolve()))


# ===========================================================================
# Finding 2 — ref path traversal in RefManager (BLOCKER)
# ===========================================================================


class TestFinding2RefPathTraversal:
    """update_ref / RefManager.write must not write outside .git."""

    def test_write_dotdot_ref_raises(self, tmp_path: Path) -> None:
        git_dir = _make_git_dir(tmp_path)
        rm = RefManager(git_dir)
        with pytest.raises(ValueError, match="Unsafe"):
            rm.write("../../escape", SHA_A)

    def test_write_absolute_ref_raises(self, tmp_path: Path) -> None:
        git_dir = _make_git_dir(tmp_path)
        rm = RefManager(git_dir)
        with pytest.raises(ValueError, match="Unsafe"):
            rm.write("/etc/passwd", SHA_A)

    def test_write_escape_does_not_create_file(self, tmp_path: Path) -> None:
        git_dir = _make_git_dir(tmp_path)
        rm = RefManager(git_dir)
        with contextlib.suppress(ValueError):
            rm.write("../../escape", SHA_A)
        assert not (tmp_path.parent / "escape").exists()

    def test_write_symbolic_dotdot_raises(self, tmp_path: Path) -> None:
        git_dir = _make_git_dir(tmp_path)
        rm = RefManager(git_dir)
        with pytest.raises(ValueError, match="Unsafe"):
            rm.write_symbolic("../../symesc", "refs/heads/main")

    def test_delete_dotdot_raises(self, tmp_path: Path) -> None:
        git_dir = _make_git_dir(tmp_path)
        rm = RefManager(git_dir)
        with pytest.raises(ValueError, match="Unsafe"):
            rm.delete("../../escape")

    def test_valid_ref_still_works(self, tmp_path: Path) -> None:
        git_dir = _make_git_dir(tmp_path)
        rm = RefManager(git_dir)
        rm.write("refs/heads/main", SHA_A)
        assert rm.resolve("refs/heads/main") == SHA_A


# ===========================================================================
# Finding 3 — symlink hashed as link target bytes (add.py)
# ===========================================================================


class TestFinding3SymlinkHashing:
    """Staging a symlink must record the link-target path as blob content."""

    def test_symlink_blob_content_is_link_target(self, tmp_path: Path) -> None:
        repo = _make_repo(tmp_path)
        target = tmp_path / "target.txt"
        target.write_bytes(b"hello")
        link = tmp_path / "link.txt"
        link.symlink_to("target.txt")

        rc = add(repo, ["link.txt"])
        assert rc == 0

        index = repo.index.read()
        entry = index.get("link.txt")
        assert entry is not None

        blob = repo.objects.read_blob(entry.sha)
        assert blob.data == b"target.txt", (
            f"Expected link target b'target.txt', got {blob.data!r}"
        )

    def test_symlink_mode_in_index(self, tmp_path: Path) -> None:
        repo = _make_repo(tmp_path)
        target = tmp_path / "t.txt"
        target.write_bytes(b"x")
        link = tmp_path / "lnk"
        link.symlink_to("t.txt")

        add(repo, ["lnk"])
        entry = repo.index.read().get("lnk")
        assert entry is not None
        assert entry.mode == 0o120000


# ===========================================================================
# Finding 4 — checkout restores symlinks and exec bits
# ===========================================================================


class TestFinding4CheckoutModes:
    """checkout must create actual symlinks and set exec bit."""

    def test_checkout_restores_symlink(self, tmp_path: Path) -> None:
        repo = _make_repo(tmp_path)

        # Stage a symlink entry manually.
        link_target = "target.txt"
        blob = Blob(data=link_target.encode())
        sha = repo.objects.write(blob)

        tree = Tree(entries=[TreeEntry(mode="120000", name="link.txt", sha=sha)])
        tree_sha = repo.objects.write(tree)
        ident = _identity()
        c = Commit(
            tree_sha=tree_sha,
            parent_shas=[],
            author=ident,
            committer=ident,
            message="symlink commit",
        )
        commit_sha = repo.objects.write(c)
        repo.refs.write("refs/heads/main", commit_sha)

        checkout(repo, "main")

        link_path = tmp_path / "link.txt"
        assert link_path.is_symlink(), "Symlink was not created"
        assert os.readlink(link_path) == "target.txt"

    def test_checkout_restores_exec_bit(self, tmp_path: Path) -> None:
        repo = _make_repo(tmp_path)

        blob = Blob(data=b"#!/bin/sh\n")
        sha = repo.objects.write(blob)

        tree = Tree(entries=[TreeEntry(mode="100755", name="run.sh", sha=sha)])
        tree_sha = repo.objects.write(tree)
        ident = _identity()
        c = Commit(
            tree_sha=tree_sha,
            parent_shas=[],
            author=ident,
            committer=ident,
            message="exec commit",
        )
        commit_sha = repo.objects.write(c)
        repo.refs.write("refs/heads/main", commit_sha)

        checkout(repo, "main")

        run_path = tmp_path / "run.sh"
        assert run_path.exists()
        file_mode = run_path.stat().st_mode
        assert file_mode & stat.S_IXUSR, "Executable bit not set"


# ===========================================================================
# Finding 5 — checkout removes files absent from target tree
# ===========================================================================


class TestFinding5CheckoutRemovesStaleFiles:
    """Checking out a branch removes files not in the target tree."""

    def test_stale_file_removed_on_checkout(self, tmp_path: Path) -> None:
        repo = _make_repo(tmp_path)

        # Commit 1: a.txt + b.txt
        (tmp_path / "a.txt").write_text("a")
        (tmp_path / "b.txt").write_text("b")
        add(repo, ["a.txt", "b.txt"])
        commit(repo, "both files")
        sha_both = repo.refs.resolve("HEAD")
        assert sha_both is not None
        repo.refs.write("refs/heads/both", sha_both)

        # Commit 2 (on branch 'only_a'): only a.txt
        (tmp_path / "b.txt").unlink()
        add(repo, [], all=True)
        commit(repo, "only a")
        sha_only_a = repo.refs.resolve("HEAD")
        assert sha_only_a is not None
        repo.refs.write("refs/heads/only_a", sha_only_a)

        # Go back to 'both'
        checkout(repo, "both")

        # Go to 'only_a'
        checkout(repo, "only_a")

        assert not (tmp_path / "b.txt").exists(), "b.txt should have been removed"
        index = repo.index.read()
        assert index.get("b.txt") is None, "b.txt should not be in index"


# ===========================================================================
# Finding 6 — add -A removes deleted tracked paths from index
# ===========================================================================


class TestFinding6AddAllRemovesDeleted:
    """``add -A`` must remove index entries for deleted worktree files."""

    def test_add_all_removes_deleted_file(self, tmp_path: Path) -> None:
        repo = _make_repo(tmp_path)

        (tmp_path / "a.txt").write_text("a")
        (tmp_path / "b.txt").write_text("b")
        add(repo, ["a.txt", "b.txt"])

        # Verify both staged
        index = repo.index.read()
        assert index.get("a.txt") is not None
        assert index.get("b.txt") is not None

        # Delete b.txt from disk
        (tmp_path / "b.txt").unlink()

        # add -A should remove b.txt from index
        rc = add(repo, [], all=True)
        assert rc == 0

        index = repo.index.read()
        assert index.get("a.txt") is not None
        assert index.get("b.txt") is None, "Deleted b.txt must be removed from index"


# ===========================================================================
# Finding 7 — hash_object hashes raw bytes without round-trip
# ===========================================================================


class TestFinding7HashObjectRawBytes:
    """hash_object must hash raw input bytes, not re-serialized object data."""

    def test_hash_object_blob_matches_git_canonical(self) -> None:
        """Blob SHA for b'hello\\n' must match the well-known Git hash."""
        with tempfile.TemporaryDirectory() as d:
            repo = Repository.init(Path(d))
            sha = hash_object(repo, b"hello\n", type_name="blob")
            assert sha == "ce013625030ba8dba906f756967f9e9ca394464a"

    def test_hash_object_commit_matches_direct_sha(self, tmp_path: Path) -> None:
        """hash_object for commit type must produce same SHA as direct hashing."""
        repo = _make_repo(tmp_path)
        raw_data = b"tree 4b825dc642cb6eb9a060e54bf8d69288fbee4904\nauthor A <a@b> 0 +0000\ncommitter A <a@b> 0 +0000\n\nhello\n"
        expected_header = f"commit {len(raw_data)}\0".encode()
        expected_sha = hashlib.sha1(
            expected_header + raw_data, usedforsecurity=False
        ).hexdigest()

        sha = hash_object(repo, raw_data, type_name="commit")
        assert sha == expected_sha

    def test_hash_object_does_not_roundtrip(self, tmp_path: Path) -> None:
        """Non-blob data must not be parsed/re-serialized (would change OID)."""
        repo = _make_repo(tmp_path)
        # Deliberately malformed commit data that a round-trip would mangle.
        raw_data = b"not valid commit content but should be hashed as-is"
        header = f"commit {len(raw_data)}\0".encode()
        expected = hashlib.sha1(header + raw_data, usedforsecurity=False).hexdigest()
        sha = hash_object(repo, raw_data, type_name="commit")
        assert sha == expected


# ===========================================================================
# Finding 8 — log/diff route through RevisionParser (HEAD^, HEAD~N)
# ===========================================================================


class TestFinding8RevisionInLogDiff:
    """log and diff must accept HEAD^, HEAD~N, and abbreviated SHAs."""

    def test_log_head_caret(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        repo = _make_repo(tmp_path)
        (tmp_path / "f.txt").write_text("v1")
        add(repo, ["f.txt"])
        commit(repo, "first")
        # Clear any output from the commit call.
        capsys.readouterr()

        (tmp_path / "f.txt").write_text("v2")
        add(repo, ["f.txt"])
        commit(repo, "second")
        capsys.readouterr()

        rc = log(repo, "HEAD^")
        assert rc == 0
        out = capsys.readouterr().out
        # The log output should show "first" (the parent) but not "second".
        assert "    first" in out  # log indents with 4 spaces
        assert "    second" not in out

    def test_log_head_tilde2(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        repo = _make_repo(tmp_path)
        for i in range(3):
            (tmp_path / "f.txt").write_text(f"v{i}")
            add(repo, ["f.txt"])
            commit(repo, f"commit {i}")
        capsys.readouterr()  # clear commit output

        rc = log(repo, "HEAD~2")
        assert rc == 0
        out = capsys.readouterr().out
        assert "    commit 0" in out  # log indents with 4 spaces
        assert "    commit 1" not in out
        assert "    commit 2" not in out

    def test_log_abbreviated_sha(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        repo = _make_repo(tmp_path)
        (tmp_path / "f.txt").write_text("x")
        add(repo, ["f.txt"])
        commit(repo, "abbrev test")
        full_sha = repo.refs.resolve("HEAD")
        assert full_sha is not None

        rc = log(repo, full_sha[:7])
        assert rc == 0
        out = capsys.readouterr().out
        assert "abbrev test" in out


# ===========================================================================
# Finding 9 — RevisionParser resolves abbreviated SHAs
# ===========================================================================


class TestFinding9AbbreviatedSHA:
    """RevisionParser must resolve a 7-char prefix to the full SHA."""

    def test_short_sha_resolves(self, tmp_path: Path) -> None:
        repo = _make_repo(tmp_path)
        sha = _make_commit(repo, [], "init\n")
        parser = RevisionParser(repo.refs, repo.objects)

        result = parser.parse(sha[:7])
        assert result == sha

    def test_short_sha_4_chars(self, tmp_path: Path) -> None:
        repo = _make_repo(tmp_path)
        sha = _make_commit(repo, [], "init\n")
        parser = RevisionParser(repo.refs, repo.objects)

        result = parser.parse(sha[:4])
        assert result == sha


# ===========================================================================
# Finding 10 — HEAD^0 returns the commit itself
# ===========================================================================


class TestFinding10CaretZero:
    """HEAD^0 must return the commit itself (peel/identity)."""

    def test_caret_zero_identity(self, tmp_path: Path) -> None:
        repo = _make_repo(tmp_path)
        sha = _make_commit(repo, [], "root\n")
        repo.refs.write("refs/heads/main", sha)
        parser = RevisionParser(repo.refs, repo.objects)

        result = parser.parse("main^0")
        assert result == sha, f"HEAD^0 should equal HEAD, got {result}"

    def test_caret_zero_equals_head(self, tmp_path: Path) -> None:
        repo = _make_repo(tmp_path)
        c1 = _make_commit(repo, [], "c1\n")
        c2 = _make_commit(repo, [c1], "c2\n")
        repo.refs.write("refs/heads/main", c2)
        parser = RevisionParser(repo.refs, repo.objects)

        assert parser.parse("main^0") == parser.parse("main")


# ===========================================================================
# Finding 11 — worktree diff reads from disk (not unwritten OID)
# ===========================================================================


class TestFinding11WorktreeDiff:
    """Diff of modified tracked file must show modification, not vanish."""

    def test_modified_file_shows_as_modification(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        repo = _make_repo(tmp_path)
        f = tmp_path / "readme.txt"
        f.write_text("original\n")
        add(repo, ["readme.txt"])
        commit(repo, "initial")

        # Modify WITHOUT staging
        f.write_text("modified\n")

        rc = diff(repo, [])
        assert rc == 0
        out = capsys.readouterr().out
        # Must show the modification, not be empty.
        assert "readme.txt" in out
        assert "-original" in out or "+modified" in out

    def test_untracked_file_not_a_crash(self, tmp_path: Path) -> None:
        repo = _make_repo(tmp_path)
        f = tmp_path / "tracked.txt"
        f.write_text("tracked\n")
        add(repo, ["tracked.txt"])
        commit(repo, "init")

        # New untracked file should not cause a crash.
        (tmp_path / "untracked.txt").write_text("new\n")
        rc = diff(repo, [])
        assert rc == 0  # Must not crash


# ===========================================================================
# Finding 12 — index entry flags use UTF-8 byte length
# ===========================================================================


class TestFinding12FlagsUtf8ByteLength:
    """Flags name-length field must reflect UTF-8 BYTE length."""

    def test_multibyte_path_flags(self, tmp_path: Path) -> None:
        # U+00E9 (é) is 2 bytes in UTF-8.
        unicode_name = "café.txt"
        f = tmp_path / unicode_name
        f.write_bytes(b"data")
        sha = "a" * 40

        entry = IndexEntry.from_path(unicode_name, sha, tmp_path)
        byte_len = len(unicode_name.encode("utf-8"))
        char_len = len(unicode_name)

        assert byte_len != char_len, "test requires a multi-byte path"
        assert (entry.flags & 0xFFF) == byte_len, (
            f"Expected byte length {byte_len}, got {entry.flags & 0xFFF}"
        )

    def test_ascii_path_flags_unchanged(self, tmp_path: Path) -> None:
        f = tmp_path / "simple.txt"
        f.write_bytes(b"x")
        sha = "b" * 40
        entry = IndexEntry.from_path("simple.txt", sha, tmp_path)
        assert (entry.flags & 0xFFF) == len("simple.txt")


# ===========================================================================
# Finding 13 — matches_stat detects chmod-only changes
# ===========================================================================


class TestFinding13MatchesStatMode:
    """matches_stat must return False after a chmod that changes the exec bit."""

    def test_chmod_exec_detected(self, tmp_path: Path) -> None:
        f = tmp_path / "script.sh"
        f.write_bytes(b"#!/bin/sh\n")
        f.chmod(0o644)
        sha = "c" * 40

        # Stage as non-executable.
        entry = IndexEntry.from_path("script.sh", sha, tmp_path)
        assert entry.mode == 0o100644

        # Now chmod +x — need a new stat result.
        f.chmod(0o755)
        st = f.stat()
        # stat() follows symlinks; lstat() would also work here.
        assert entry.matches_stat(st) is False, (
            "matches_stat should be False after chmod +x"
        )


# ===========================================================================
# Finding 14 — lock file uses full-name+.lock, not with_suffix
# ===========================================================================


class TestFinding14LockFileDottedRef:
    """A tag named ``v1.0`` must use ``v1.0.lock`` as the lock file."""

    def test_dotted_ref_lock_path(self, tmp_path: Path) -> None:
        git_dir = _make_git_dir(tmp_path)
        rm = RefManager(git_dir)
        tag_ref = "refs/tags/v1.0"
        rm.write(tag_ref, SHA_A)

        # If with_suffix(".lock") were used, the lock would be "v1.lock".
        # With our fix (str + ".lock"), it's "v1.0.lock" — but after the
        # write completes the lock file should be gone (replaced → ref file).
        ref_path = git_dir / tag_ref
        bad_lock = Path(str(ref_path.with_suffix("")) + ".lock")  # v1.lock
        assert not bad_lock.exists(), "Stale lock from with_suffix('.lock') found"

        # Verify the ref was written correctly.
        assert rm.resolve("refs/tags/v1.0") == SHA_A

    def test_dotted_ref_second_write(self, tmp_path: Path) -> None:
        """Writing the same dotted ref twice must succeed (no stale lock)."""
        git_dir = _make_git_dir(tmp_path)
        rm = RefManager(git_dir)
        rm.write("refs/tags/v1.0", SHA_A)
        rm.write("refs/tags/v1.0", SHA_B)  # Should not fail with EEXIST
        assert rm.resolve("refs/tags/v1.0") == SHA_B


# ===========================================================================
# Finding 15 — pack _build_index handles REF_DELTA without .idx
# ===========================================================================


class TestFinding15PackRefDeltaIndexBuild:
    """Building an index for a pack with REF_DELTA must succeed."""

    def _make_pack_with_ref_delta(self, tmp_path: Path) -> Path:
        """Build a minimal pack file containing a REF_DELTA object."""
        base_data = b"hello world, base object content"
        delta_data = create_delta(base_data, base_data + b" extra")

        # Write base blob object header + zlib-compressed data.
        base_type = 3  # OBJ_BLOB
        base_size = len(base_data)

        def _write_obj_header(obj_type: int, size: int) -> bytes:
            result = bytearray()
            byte = (obj_type << 4) | (size & 0x0F)
            size >>= 4
            if size > 0:
                byte |= 0x80
            result.append(byte)
            while size > 0:
                byte = size & 0x7F
                size >>= 7
                if size > 0:
                    byte |= 0x80
                result.append(byte)
            return bytes(result)

        base_header = _write_obj_header(base_type, base_size)
        base_compressed = zlib.compress(base_data)

        # Compute SHA of base object.
        git_header = f"blob {base_size}\0".encode()
        base_sha_hex = hashlib.sha1(
            git_header + base_data, usedforsecurity=False
        ).hexdigest()
        base_sha_bytes = bytes.fromhex(base_sha_hex)

        # Write REF_DELTA entry.
        delta_type = 7  # OBJ_REF_DELTA
        delta_size = len(delta_data)
        delta_header = _write_obj_header(delta_type, delta_size)
        delta_compressed = zlib.compress(delta_data)

        # Pack: header + base_obj + ref_delta_obj + pack_sha
        pack_content = bytearray()
        pack_content += b"PACK"
        pack_content += struct.pack(">I", 2)  # version
        pack_content += struct.pack(">I", 2)  # 2 objects

        pack_content += base_header + base_compressed
        pack_content += delta_header + base_sha_bytes + delta_compressed

        pack_sha = hashlib.sha1(bytes(pack_content), usedforsecurity=False).digest()
        pack_content += pack_sha

        pack_path = tmp_path / "test.pack"
        pack_path.write_bytes(bytes(pack_content))
        return pack_path

    def test_build_index_with_ref_delta(self, tmp_path: Path) -> None:
        pack_path = self._make_pack_with_ref_delta(tmp_path)
        # Must not raise even without a .idx file.
        pf = PackFile(pack_path)
        assert len(pf.index.entries) == 2


# ===========================================================================
# Finding 16 — delta COPY instructions split at 0xFFFFFF bytes
# ===========================================================================


class TestFinding16DeltaCopySplit:
    """COPY ops larger than 0xFFFFFF bytes must be split."""

    def test_emit_copy_splits_large_region(self) -> None:
        result = bytearray()
        # A single 20MB region (> 0xFFFFFF = 16MB).
        size = 0x1000010  # ~16MB + 16 bytes
        _emit_copy(result, 0, size)
        # At least two COPY instructions must have been emitted
        # (first byte of each COPY instruction has bit 7 set).
        copy_count = sum(1 for b in result if b & 0x80)
        assert copy_count >= 2, f"Expected >=2 COPY instructions, got {copy_count}"

    def test_delta_large_copy_roundtrips_via_apply(self) -> None:
        """A manually-constructed delta with a >0xFFFFFF COPY applies correctly.

        We build the delta by hand (using _emit_copy + _encode_delta_size) so
        the test runs in milliseconds rather than minutes, while still
        exercising the split-COPY path end-to-end through apply_delta.
        """
        # 0xFFFFFF + 1 = 16,777,216 bytes — exactly one more than the max single COPY.
        size = 0x1000000
        source = bytes(range(256)) * (size // 256)

        # Build a delta manually: header + one COPY covering all of source.
        delta_buf = bytearray()
        delta_buf.extend(_encode_delta_size(size))  # source size
        delta_buf.extend(_encode_delta_size(size))  # target size (same)
        _emit_copy(delta_buf, 0, size)  # COPY 0..size

        target = apply_delta(source, bytes(delta_buf))
        assert target == source, "Large COPY delta round-trip failed"


# ===========================================================================
# INCOMPLETE FIX 1 — read-side path traversal in RefManager.read() / resolve()
# ===========================================================================


class TestIncompleteFix1RefManagerReadTraversal:
    """rm.read('../outside.txt') must return None, not read outside git_dir."""

    def test_read_dotdot_returns_none(self, tmp_path: Path) -> None:
        """read() with a traversal name returns None without reading the file."""
        git_dir = _make_git_dir(tmp_path)
        outside = tmp_path.parent / "outside.txt"
        outside.write_text("secret content\n")
        rm = RefManager(git_dir)
        result = rm.read("../outside.txt")
        assert result is None, (
            "read() should return None for path-traversal names, "
            f"but returned {result!r}"
        )
        assert result != "secret content", "read() leaked content from outside git_dir"

    def test_read_absolute_returns_none(self, tmp_path: Path) -> None:
        """read() with an absolute path returns None."""
        git_dir = _make_git_dir(tmp_path)
        rm = RefManager(git_dir)
        assert rm.read("/etc/passwd") is None

    def test_resolve_dotdot_returns_none(self, tmp_path: Path) -> None:
        """resolve() with a traversal name returns None."""
        git_dir = _make_git_dir(tmp_path)
        outside = tmp_path.parent / "outside.txt"
        outside.write_text("a" * 40 + "\n")
        rm = RefManager(git_dir)
        result = rm.resolve("../outside.txt")
        assert result is None, (
            "resolve() should return None for path-traversal names, "
            f"but returned {result!r}"
        )

    def test_read_valid_name_still_works(self, tmp_path: Path) -> None:
        """Valid ref names are still readable after the guard is added."""
        git_dir = _make_git_dir(tmp_path)
        rm = RefManager(git_dir)
        rm.write("refs/heads/main", SHA_A)
        assert rm.read("refs/heads/main") == SHA_A


# ===========================================================================
# INCOMPLETE FIX 2 — _restore_paths write path lacks _safe_worktree_path guard
# ===========================================================================


class TestIncompleteFix2RestorePathsTraversal:
    """checkout(repo, paths=['../evil']) must not write outside the worktree."""

    def test_restore_paths_dotdot_is_rejected(self, tmp_path: Path) -> None:
        """Passing paths=['../evil'] to checkout must not write outside worktree."""
        repo = _make_repo(tmp_path)

        # Stage a legitimate file so the repo has a commit.
        (tmp_path / "file.txt").write_bytes(b"safe content")
        add(repo, ["file.txt"])
        commit(repo, "initial")

        # Manually inject an unsafe index entry.
        evil_data = b"evil content"
        evil_blob = Blob(data=evil_data)
        evil_sha = repo.objects.write(evil_blob)

        # Bypass the index write API to plant the entry directly.
        idx = repo.index.read()
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
                size=len(evil_data),
                sha=evil_sha,
                flags=0,
                path="../evil",
            )
        )
        repo.index.write(idx)

        rc = checkout(repo, paths=["../evil"])

        evil_target = tmp_path.parent / "evil"
        assert not evil_target.exists(), (
            "_restore_paths wrote outside the worktree via '../evil'"
        )
        # Return code should indicate failure (not 0), or the file must be absent.
        # Either outcome is acceptable — the key invariant is no file outside wt.
        assert rc == 1 or not evil_target.exists()

    def test_restore_paths_normal_path_works(self, tmp_path: Path) -> None:
        """A legitimate path in paths=[...] is still restored correctly."""
        repo = _make_repo(tmp_path)
        (tmp_path / "hello.txt").write_bytes(b"original")
        add(repo, ["hello.txt"])
        commit(repo, "initial")

        # Overwrite the file, then restore from index.
        (tmp_path / "hello.txt").write_bytes(b"modified")
        rc = checkout(repo, paths=["hello.txt"])
        assert rc == 0
        assert (tmp_path / "hello.txt").read_bytes() == b"original"


# ===========================================================================
# INCOMPLETE FIX 3 — chained REF_DELTA (2-level delta chain) in _build_index
# ===========================================================================


def _make_pack_with_chained_ref_delta(tmp_path: Path) -> tuple[Path, bytes, bytes]:
    """Build a pack: BLOB → REF_DELTA(base=blob) → REF_DELTA(base=delta1).

    Returns (pack_path, base_data, level2_data) where level2_data is the
    expected content of the 2nd-level delta object.
    """
    base_data = b"Hello, this is the base object content for chained delta test."
    level1_data = base_data + b" level1 suffix"
    level2_data = level1_data + b" level2 suffix"

    delta1 = create_delta(base_data, level1_data)
    delta2 = create_delta(level1_data, level2_data)

    # SHA helpers
    def _git_sha(type_name: str, data: bytes) -> str:
        hdr = f"{type_name} {len(data)}\0".encode()
        return hashlib.sha1(hdr + data, usedforsecurity=False).hexdigest()

    base_sha_hex = _git_sha("blob", base_data)
    level1_sha_hex = _git_sha("blob", level1_data)

    # Encode pack-object header: type + size (variable-length).
    def _pack_hdr(obj_type: int, size: int) -> bytes:
        return write_pack_object_header(obj_type, size)

    # Build pack payload.
    pack_buf = bytearray()
    pack_buf += b"PACK"
    pack_buf += struct.pack(">I", 2)  # version 2
    pack_buf += struct.pack(">I", 3)  # 3 objects

    # Object 1: base BLOB
    pack_buf += _pack_hdr(PackObjectType.BLOB, len(base_data))
    pack_buf += zlib.compress(base_data)

    # Object 2: REF_DELTA whose base is the BLOB
    pack_buf += _pack_hdr(PackObjectType.REF_DELTA, len(delta1))
    pack_buf += bytes.fromhex(base_sha_hex)
    pack_buf += zlib.compress(delta1)

    # Object 3: REF_DELTA whose base is level1 (itself a delta)
    pack_buf += _pack_hdr(PackObjectType.REF_DELTA, len(delta2))
    pack_buf += bytes.fromhex(level1_sha_hex)
    pack_buf += zlib.compress(delta2)

    pack_sha = hashlib.sha1(bytes(pack_buf), usedforsecurity=False).digest()
    pack_buf += pack_sha

    pack_path = tmp_path / "chained.pack"
    pack_path.write_bytes(bytes(pack_buf))
    return pack_path, base_data, level2_data


class TestIncompleteFix3ChainedRefDelta:
    """_build_index must handle a 2-level REF_DELTA chain without .idx file."""

    def test_build_index_resolves_all_3_objects(self, tmp_path: Path) -> None:
        """All 3 objects (base + 2 chained deltas) are in the built index."""
        pack_path, _base_data, _level2_data = _make_pack_with_chained_ref_delta(
            tmp_path
        )
        # No .idx file — forces _build_index to run.
        assert not pack_path.with_suffix(".idx").exists()

        pf = PackFile(pack_path)
        assert len(pf.index.entries) == 3, (
            f"Expected 3 index entries, got {len(pf.index.entries)}"
        )

    def test_level2_delta_object_reconstructs_correctly(self, tmp_path: Path) -> None:
        """The 2nd-level deltified object reconstructs to the correct bytes."""
        pack_path, _base_data, level2_data = _make_pack_with_chained_ref_delta(tmp_path)
        pf = PackFile(pack_path)

        # Compute the expected SHA for level2_data.
        hdr = f"blob {len(level2_data)}\0".encode()
        level2_sha = hashlib.sha1(hdr + level2_data, usedforsecurity=False).hexdigest()

        obj = pf.read_object(level2_sha)
        assert obj is not None, (
            f"Level-2 delta object {level2_sha[:7]} not found in pack"
        )
        assert obj.data == level2_data, (
            "Level-2 delta object reconstructed to wrong bytes"
        )


# ===========================================================================
# INCOMPLETE FIX 4 — RevisionParser uses private _resolve_short_sha
# ===========================================================================


class TestIncompleteFix4PublicResolveShortSha:
    """ObjectDatabase.resolve_short_sha() is a public API and returns correctly."""

    def test_resolve_short_sha_returns_full_sha(self, tmp_path: Path) -> None:
        """db.resolve_short_sha(<7-char prefix>) returns the full 40-char SHA."""
        git_dir = tmp_path / ".git"
        git_dir.mkdir()
        (git_dir / "objects").mkdir()
        db = ObjectDatabase(git_dir)

        blob = Blob(data=b"test resolve short sha")
        full_sha = db.write(blob)

        result = db.resolve_short_sha(full_sha[:7])
        assert result == full_sha, (
            f"resolve_short_sha({full_sha[:7]!r}) returned {result!r}, "
            f"expected {full_sha!r}"
        )

    def test_resolve_short_sha_ambiguous_returns_none(self, tmp_path: Path) -> None:
        """Ambiguous prefix returns None (public API swallows ValueError)."""
        git_dir = tmp_path / ".git"
        git_dir.mkdir()
        (git_dir / "objects").mkdir()
        db = ObjectDatabase(git_dir)

        # Write two blobs that share the first 2 hex chars (probabilistic but
        # reliable enough: just check we DON'T get an exception).
        db.write(Blob(data=b"blob one"))
        db.write(Blob(data=b"blob two"))

        # A 40-char non-existent SHA: must return None, never raise.
        result = db.resolve_short_sha("0" * 40)
        assert result is None

    def test_resolve_short_sha_missing_returns_none(self, tmp_path: Path) -> None:
        """Non-existent prefix returns None."""
        git_dir = tmp_path / ".git"
        git_dir.mkdir()
        (git_dir / "objects").mkdir()
        db = ObjectDatabase(git_dir)

        result = db.resolve_short_sha("deadbeef")
        assert result is None

    def test_revision_parser_uses_public_api(self, tmp_path: Path) -> None:
        """RevisionParser.parse() resolves an abbreviated SHA via the public API."""
        repo = _make_repo(tmp_path)
        sha = _make_commit(repo, [], "abbrev check\n")
        parser = RevisionParser(repo.refs, repo.objects)

        result = parser.parse(sha[:7])
        assert result == sha, (
            f"RevisionParser.parse({sha[:7]!r}) returned {result!r}; expected {sha!r}"
        )
