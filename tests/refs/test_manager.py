"""Tests for RefManager."""

from pathlib import Path

import pytest

from gitpy.refs.manager import RefManager

SHA_A = "a" * 40
SHA_B = "b" * 40


def make_git_dir(tmp_path: Path) -> Path:
    """Create a minimal .git directory structure."""
    git_dir = tmp_path / ".git"
    git_dir.mkdir()
    (git_dir / "refs" / "heads").mkdir(parents=True)
    (git_dir / "refs" / "tags").mkdir(parents=True)
    (git_dir / "HEAD").write_text("ref: refs/heads/main\n")
    return git_dir


class TestRefManagerRead:
    """Tests for read and resolve methods."""

    def test_read_loose_ref(self, tmp_path: Path) -> None:
        """Read a loose ref file."""
        git_dir = make_git_dir(tmp_path)
        rm = RefManager(git_dir)
        rm.write("refs/heads/test", SHA_A)
        assert rm.read("refs/heads/test") == SHA_A

    def test_resolve_short_name(self, tmp_path: Path) -> None:
        """Prefix resolution: 'test' resolves via refs/heads/test."""
        git_dir = make_git_dir(tmp_path)
        rm = RefManager(git_dir)
        rm.write("refs/heads/test", SHA_A)
        assert rm.resolve("test") == SHA_A

    def test_resolve_full_name(self, tmp_path: Path) -> None:
        """Full ref name resolves directly."""
        git_dir = make_git_dir(tmp_path)
        rm = RefManager(git_dir)
        rm.write("refs/heads/test", SHA_A)
        assert rm.resolve("refs/heads/test") == SHA_A

    def test_resolve_nonexistent_returns_none(self, tmp_path: Path) -> None:
        """Resolving missing ref returns None."""
        git_dir = make_git_dir(tmp_path)
        rm = RefManager(git_dir)
        assert rm.resolve("does-not-exist") is None

    def test_resolve_symbolic_ref(self, tmp_path: Path) -> None:
        """Symbolic ref is followed to its target SHA."""
        git_dir = make_git_dir(tmp_path)
        rm = RefManager(git_dir)
        rm.write("refs/heads/main", SHA_A)
        rm.write_symbolic("HEAD", "refs/heads/main")
        assert rm.resolve("HEAD") == SHA_A

    def test_loop_detection_raises_value_error(self, tmp_path: Path) -> None:
        """Symbolic ref loop raises ValueError."""
        git_dir = make_git_dir(tmp_path)
        rm = RefManager(git_dir)
        # Create a loop: a -> b -> a
        (git_dir / "refs" / "loop_a").write_text("ref: refs/loop_b\n")
        (git_dir / "refs" / "loop_b").write_text("ref: refs/loop_a\n")
        with pytest.raises(ValueError, match="loop"):
            rm.resolve("refs/loop_a")


class TestRefManagerPackedRefs:
    """Tests for packed-refs support."""

    def test_packed_refs_read(self, tmp_path: Path) -> None:
        """Refs in packed-refs are resolved correctly."""
        git_dir = make_git_dir(tmp_path)
        packed = git_dir / "packed-refs"
        packed.write_text(
            f"# pack-refs with: peeled fully-peeled sorted\n"
            f"{SHA_A} refs/heads/packed-branch\n"
        )
        rm = RefManager(git_dir)
        assert rm.resolve("packed-branch") == SHA_A

    def test_loose_takes_priority_over_packed(self, tmp_path: Path) -> None:
        """Loose ref overrides same-named packed ref."""
        git_dir = make_git_dir(tmp_path)
        packed = git_dir / "packed-refs"
        packed.write_text(f"{SHA_A} refs/heads/main\n")
        rm = RefManager(git_dir)
        rm.write("refs/heads/main", SHA_B)
        assert rm.resolve("refs/heads/main") == SHA_B


class TestRefManagerList:
    """Tests for list_branches and list_tags."""

    def test_list_branches(self, tmp_path: Path) -> None:
        """list_branches yields short names."""
        git_dir = make_git_dir(tmp_path)
        rm = RefManager(git_dir)
        rm.write("refs/heads/main", SHA_A)
        rm.write("refs/heads/feature", SHA_B)
        branches = dict(rm.list_branches())
        assert branches["main"] == SHA_A
        assert branches["feature"] == SHA_B

    def test_list_tags(self, tmp_path: Path) -> None:
        """list_tags yields short names."""
        git_dir = make_git_dir(tmp_path)
        rm = RefManager(git_dir)
        rm.write("refs/tags/v1.0", SHA_A)
        tags = dict(rm.list_tags())
        assert tags["v1.0"] == SHA_A


class TestRefManagerPackRefs:
    """Tests for pack_refs operation."""

    def test_pack_refs_creates_packed_refs(self, tmp_path: Path) -> None:
        """pack_refs writes loose refs into packed-refs file."""
        git_dir = make_git_dir(tmp_path)
        rm = RefManager(git_dir)
        rm.write("refs/heads/main", SHA_A)
        rm.pack_refs()
        packed = git_dir / "packed-refs"
        assert packed.exists()
        content = packed.read_text()
        assert SHA_A in content
        assert "refs/heads/main" in content

    def test_pack_refs_removes_loose(self, tmp_path: Path) -> None:
        """After pack_refs, loose ref files are removed."""
        git_dir = make_git_dir(tmp_path)
        rm = RefManager(git_dir)
        rm.write("refs/heads/main", SHA_A)
        rm.pack_refs()
        assert not (git_dir / "refs" / "heads" / "main").exists()

    def test_packed_refs_cache_invalidated_on_write(self, tmp_path: Path) -> None:
        """Writing a ref after reading packed-refs invalidates the cache."""
        git_dir = make_git_dir(tmp_path)
        packed = git_dir / "packed-refs"
        packed.write_text(f"{SHA_A} refs/heads/main\n")
        rm = RefManager(git_dir)
        # Prime the cache
        assert rm.resolve("refs/heads/main") == SHA_A
        # Write new ref (should invalidate cache)
        rm.write("refs/heads/main", SHA_B)
        assert rm.resolve("refs/heads/main") == SHA_B
