"""Tests for Commit and Identity objects."""

from gitpy.objects import Commit, Identity


class TestIdentity:
    """Tests for Identity class."""

    def test_identity_str(self) -> None:
        """Identity formats correctly as string."""
        identity = Identity(
            name="Test User",
            email="test@example.com",
            timestamp=1234567890,
            tz_offset="+0000",
        )
        assert str(identity) == "Test User <test@example.com> 1234567890 +0000"

    def test_identity_parse_simple(self) -> None:
        """Parse simple identity string."""
        identity = Identity.parse("Test User <test@example.com> 1234567890 +0000")
        assert identity.name == "Test User"
        assert identity.email == "test@example.com"
        assert identity.timestamp == 1234567890
        assert identity.tz_offset == "+0000"

    def test_identity_parse_with_spaces(self) -> None:
        """Parse identity with spaces in name."""
        identity = Identity.parse(
            "First Middle Last <user@example.com> 1234567890 -0700"
        )
        assert identity.name == "First Middle Last"
        assert identity.email == "user@example.com"
        assert identity.tz_offset == "-0700"

    def test_identity_parse_negative_timezone(self) -> None:
        """Parse identity with negative timezone."""
        identity = Identity.parse("User <user@example.com> 1234567890 -0530")
        assert identity.tz_offset == "-0530"

    def test_identity_roundtrip(self) -> None:
        """Identity roundtrips through str and parse."""
        original = Identity(
            name="Test User",
            email="test@example.com",
            timestamp=1234567890,
            tz_offset="-0800",
        )
        restored = Identity.parse(str(original))
        assert restored.name == original.name
        assert restored.email == original.email
        assert restored.timestamp == original.timestamp
        assert restored.tz_offset == original.tz_offset

    def test_identity_now(self) -> None:
        """Identity.now() creates current timestamp."""
        identity = Identity.now("Test User", "test@example.com")
        assert identity.name == "Test User"
        assert identity.email == "test@example.com"
        assert identity.timestamp > 0
        assert identity.tz_offset == "+0000"

    def test_identity_now_with_timezone(self) -> None:
        """Identity.now() accepts custom timezone."""
        identity = Identity.now("User", "user@example.com", tz_offset="-0700")
        assert identity.tz_offset == "-0700"


class TestCommit:
    """Tests for Commit class."""

    def test_commit_root(self) -> None:
        """Root commit has no parents."""
        author = Identity(
            name="Test", email="test@example.com", timestamp=0, tz_offset="+0000"
        )
        commit = Commit(
            tree_sha="4b825dc642cb6eb9a060e54bf8d69288fbee4904",
            parent_shas=[],
            author=author,
            committer=author,
            message="Initial commit",
        )
        assert commit.is_root
        assert not commit.is_merge

    def test_commit_with_parent(self) -> None:
        """Regular commit has one parent."""
        author = Identity(
            name="Test", email="test@example.com", timestamp=0, tz_offset="+0000"
        )
        commit = Commit(
            tree_sha="a" * 40,
            parent_shas=["b" * 40],
            author=author,
            committer=author,
            message="Second commit",
        )
        assert not commit.is_root
        assert not commit.is_merge

    def test_commit_merge(self) -> None:
        """Merge commit has multiple parents."""
        author = Identity(
            name="Test", email="test@example.com", timestamp=0, tz_offset="+0000"
        )
        commit = Commit(
            tree_sha="a" * 40,
            parent_shas=["b" * 40, "c" * 40],
            author=author,
            committer=author,
            message="Merge branch",
        )
        assert not commit.is_root
        assert commit.is_merge

    def test_commit_roundtrip(self) -> None:
        """Serialize then deserialize preserves all fields."""
        author = Identity(
            name="Alice",
            email="alice@example.com",
            timestamp=1234567890,
            tz_offset="-0700",
        )
        committer = Identity(
            name="Bob", email="bob@example.com", timestamp=1234567899, tz_offset="+0530"
        )

        original = Commit(
            tree_sha="a" * 40,
            parent_shas=["b" * 40, "c" * 40],
            author=author,
            committer=committer,
            message="Merge feature branch\n\nDetailed description.",
        )

        restored = Commit.deserialize(original.serialize())

        assert restored.tree_sha == original.tree_sha
        assert restored.parent_shas == original.parent_shas
        assert restored.author is not None
        assert restored.author.name == "Alice"
        assert restored.author.email == "alice@example.com"
        assert restored.committer is not None
        assert restored.committer.email == "bob@example.com"
        assert restored.is_merge
        assert "Detailed description" in restored.message

    def test_commit_multiline_message(self) -> None:
        """Commit preserves multiline message."""
        author = Identity(
            name="Test", email="test@example.com", timestamp=0, tz_offset="+0000"
        )
        message = "Subject line\n\nBody paragraph 1.\n\nBody paragraph 2."
        commit = Commit(
            tree_sha="a" * 40,
            parent_shas=[],
            author=author,
            committer=author,
            message=message,
        )
        restored = Commit.deserialize(commit.serialize())
        assert restored.message == message

    def test_commit_serialization_format(self) -> None:
        """Verify exact serialization format."""
        author = Identity(
            name="Test",
            email="test@example.com",
            timestamp=1234567890,
            tz_offset="+0000",
        )
        commit = Commit(
            tree_sha="a" * 40,
            parent_shas=["b" * 40],
            author=author,
            committer=author,
            message="Test commit",
        )
        data = commit.serialize()
        text = data.decode("utf-8")

        lines = text.split("\n")
        assert lines[0] == f"tree {'a' * 40}"
        assert lines[1] == f"parent {'b' * 40}"
        assert lines[2].startswith("author Test <test@example.com>")
        assert lines[3].startswith("committer Test <test@example.com>")
        assert lines[4] == ""  # Blank line before message
        assert lines[5] == "Test commit"

    def test_commit_hash_deterministic(self) -> None:
        """Same commit data produces same hash."""
        author = Identity(
            name="Test",
            email="test@example.com",
            timestamp=1234567890,
            tz_offset="+0000",
        )
        commit1 = Commit(
            tree_sha="a" * 40,
            parent_shas=[],
            author=author,
            committer=author,
            message="Test",
        )
        commit2 = Commit(
            tree_sha="a" * 40,
            parent_shas=[],
            author=author,
            committer=author,
            message="Test",
        )
        assert commit1.oid == commit2.oid

    def test_commit_type_name(self) -> None:
        """Commit has correct type name."""
        commit = Commit()
        assert commit.type_name == "commit"
