"""Tests for RevisionParser."""

from pathlib import Path

from gitpy.objects import Commit, Identity, Tree
from gitpy.refs.reflog import ZERO_SHA
from gitpy.refs.revision import RevisionParser
from gitpy.repository import Repository


def _identity() -> Identity:
    return Identity(
        name="Test User",
        email="test@example.com",
        timestamp=1234567890,
        tz_offset="+0000",
    )


def make_commit(repo: Repository, parent_shas: list[str], message: str) -> str:
    """Write a commit object and return its SHA."""
    tree = Tree(entries=[])
    tree_sha = repo.objects.write(tree)
    ident = _identity()
    commit = Commit(
        tree_sha=tree_sha,
        parent_shas=parent_shas,
        author=ident,
        committer=ident,
        message=message,
    )
    return repo.objects.write(commit)


class TestRevisionParserSimple:
    """Basic resolution tests."""

    def test_parse_branch_name(self, tmp_path: Path) -> None:
        """Parsing a branch name returns its commit SHA."""
        repo = Repository.init(tmp_path / "repo")
        sha = make_commit(repo, [], "init\n")
        repo.refs.write("refs/heads/main", sha)
        parser = RevisionParser(repo.refs, repo.objects)
        assert parser.parse("main") == sha

    def test_parse_head(self, tmp_path: Path) -> None:
        """Parsing HEAD resolves via symbolic ref."""
        repo = Repository.init(tmp_path / "repo")
        sha = make_commit(repo, [], "init\n")
        repo.refs.write("refs/heads/main", sha)
        # HEAD is already pointing at refs/heads/main from init
        parser = RevisionParser(repo.refs, repo.objects)
        assert parser.parse("HEAD") == sha

    def test_parse_nonexistent_returns_none(self, tmp_path: Path) -> None:
        """Parsing a non-existent rev returns None."""
        repo = Repository.init(tmp_path / "repo")
        parser = RevisionParser(repo.refs, repo.objects)
        assert parser.parse("no-such-branch") is None


class TestRevisionParserAncestry:
    """Tests for ^ and ~ suffixes."""

    def test_caret_first_parent(self, tmp_path: Path) -> None:
        """HEAD^ resolves to the first parent."""
        repo = Repository.init(tmp_path / "repo")
        c1 = make_commit(repo, [], "first\n")
        c2 = make_commit(repo, [c1], "second\n")
        repo.refs.write("refs/heads/main", c2)
        parser = RevisionParser(repo.refs, repo.objects)
        assert parser.parse("main^") == c1

    def test_tilde_n(self, tmp_path: Path) -> None:
        """HEAD~3 walks three generations up."""
        repo = Repository.init(tmp_path / "repo")
        c1 = make_commit(repo, [], "c1\n")
        c2 = make_commit(repo, [c1], "c2\n")
        c3 = make_commit(repo, [c2], "c3\n")
        c4 = make_commit(repo, [c3], "c4\n")
        repo.refs.write("refs/heads/main", c4)
        parser = RevisionParser(repo.refs, repo.objects)
        assert parser.parse("main~3") == c1

    def test_caret_2_merge_commit(self, tmp_path: Path) -> None:
        """HEAD^2 resolves to the second parent of a merge commit."""
        repo = Repository.init(tmp_path / "repo")
        c1 = make_commit(repo, [], "base\n")
        c2 = make_commit(repo, [c1], "branch1\n")
        c3 = make_commit(repo, [c1], "branch2\n")
        merge = make_commit(repo, [c2, c3], "merge\n")
        repo.refs.write("refs/heads/main", merge)
        parser = RevisionParser(repo.refs, repo.objects)
        assert parser.parse("main^2") == c3

    def test_caret_beyond_root_returns_none(self, tmp_path: Path) -> None:
        """Going beyond root commit returns None."""
        repo = Repository.init(tmp_path / "repo")
        c1 = make_commit(repo, [], "root\n")
        repo.refs.write("refs/heads/main", c1)
        parser = RevisionParser(repo.refs, repo.objects)
        assert parser.parse("main^") is None


class TestRevisionParserReflog:
    """Tests for HEAD@{N} reflog references."""

    def test_reflog_index(self, tmp_path: Path) -> None:
        """HEAD@{1} returns the previous value from the reflog."""
        repo = Repository.init(tmp_path / "repo")
        c1 = make_commit(repo, [], "first\n")
        c2 = make_commit(repo, [c1], "second\n")
        ident = _identity()

        # Record reflog entries: HEAD moved from c1 to c2
        repo.reflog.append("HEAD", ZERO_SHA, c1, ident, "commit: first")
        repo.reflog.append("HEAD", c1, c2, ident, "commit: second")

        parser = RevisionParser(repo.refs, repo.objects)
        # index 0 = most recent (c2), index 1 = previous (c1)
        assert parser.parse("HEAD@{0}") == c2
        assert parser.parse("HEAD@{1}") == c1

    def test_reflog_out_of_range_returns_none(self, tmp_path: Path) -> None:
        """Requesting an out-of-range reflog index returns None."""
        repo = Repository.init(tmp_path / "repo")
        c1 = make_commit(repo, [], "first\n")
        ident = _identity()
        repo.reflog.append("HEAD", ZERO_SHA, c1, ident, "commit: first")

        parser = RevisionParser(repo.refs, repo.objects)
        assert parser.parse("HEAD@{5}") is None
