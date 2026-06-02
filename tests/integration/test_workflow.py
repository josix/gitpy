"""Full lifecycle integration tests for gitpy porcelain/CLI layer.

Exercises: init -> add -> commit -> branch -> checkout -> commit -> log -> diff.
Asserts HEAD, refs, and reflog consistency throughout.
"""

import io
from pathlib import Path

import pytest

from gitpy.commands.plumbing.cat_file import cat_file
from gitpy.commands.porcelain.add import add
from gitpy.commands.porcelain.branch import branch
from gitpy.commands.porcelain.checkout import checkout
from gitpy.commands.porcelain.commit import commit
from gitpy.commands.porcelain.diff import diff
from gitpy.commands.porcelain.log import log
from gitpy.commands.porcelain.status import status
from gitpy.repository import Repository


@pytest.fixture()
def repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Repository:
    """Initialise a gitpy repository with a fixed identity."""
    monkeypatch.setenv("GIT_AUTHOR_NAME", "Integration Tester")
    monkeypatch.setenv("GIT_AUTHOR_EMAIL", "it@example.com")
    monkeypatch.setenv("GIT_COMMITTER_NAME", "Integration Tester")
    monkeypatch.setenv("GIT_COMMITTER_EMAIL", "it@example.com")
    return Repository.init(tmp_path / "repo")


class TestFullLifecycle:
    """init -> add -> commit -> branch -> checkout -> commit -> log -> diff."""

    def _write(self, repo: Repository, path: str, content: str) -> None:
        full = repo.worktree / path
        full.parent.mkdir(parents=True, exist_ok=True)
        full.write_text(content)

    def test_init_creates_repo(self, repo: Repository) -> None:
        """Repository.init produces a valid .git directory."""
        assert (repo.git_dir / "HEAD").exists()
        assert (repo.git_dir / "objects").is_dir()
        assert (repo.git_dir / "refs" / "heads").is_dir()

    def test_add_and_commit_first(self, repo: Repository) -> None:
        """A single add+commit advances the branch."""
        self._write(repo, "README.md", "# Hello\n")
        assert add(repo, ["README.md"]) == 0
        assert commit(repo, "Initial commit") == 0

        sha = repo.head.resolve(repo.refs)
        assert len(sha) == 40
        # HEAD points to main
        head = repo.head.read()
        assert head.branch == "main"

    def test_add_multiple_files_and_commit(self, repo: Repository) -> None:
        """Multiple files can be staged and committed together."""
        for name in ["a.txt", "b.txt", "subdir/c.txt"]:
            self._write(repo, name, f"content {name}\n")

        assert add(repo, ["a.txt", "b.txt", "subdir/c.txt"]) == 0
        assert commit(repo, "Add multiple files") == 0

        sha = repo.head.resolve(repo.refs)
        commit_obj = repo.objects.read_commit(sha)
        assert commit_obj.message == "Add multiple files"

    def test_create_branch_after_commit(self, repo: Repository) -> None:
        """Branch creation points to HEAD commit."""
        self._write(repo, "file.txt", "v1\n")
        assert add(repo, ["file.txt"]) == 0
        assert commit(repo, "First commit") == 0

        first_sha = repo.head.resolve(repo.refs)
        assert branch(repo, "feature") == 0

        feature_branch = repo.branches.get("feature")
        assert feature_branch is not None
        assert feature_branch.sha == first_sha

    def test_checkout_and_second_commit(self, repo: Repository) -> None:
        """Checkout switches branch; second commit advances only that branch."""
        self._write(repo, "file.txt", "v1\n")
        assert add(repo, ["file.txt"]) == 0
        assert commit(repo, "First commit") == 0
        first_sha = repo.head.resolve(repo.refs)

        assert branch(repo, "feature") == 0
        assert checkout(repo, "feature") == 0
        assert repo.head.read().branch == "feature"

        self._write(repo, "file.txt", "v2\n")
        assert add(repo, ["file.txt"]) == 0
        assert commit(repo, "Second commit") == 0

        second_sha = repo.head.resolve(repo.refs)
        assert second_sha != first_sha

        # main still at first commit
        main_branch = repo.branches.get("main")
        assert main_branch is not None
        assert main_branch.sha == first_sha

    def test_log_shows_two_commits(
        self, repo: Repository, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """log prints both commits after two sequential commits."""
        self._write(repo, "file.txt", "v1\n")
        assert add(repo, ["file.txt"]) == 0
        assert commit(repo, "First commit") == 0

        self._write(repo, "file.txt", "v2\n")
        assert add(repo, ["file.txt"]) == 0
        assert commit(repo, "Second commit") == 0

        # Flush commit output captured so far so only log output is inspected.
        capsys.readouterr()

        assert log(repo, "HEAD", oneline=True) == 0
        captured = capsys.readouterr()
        lines = [line for line in captured.out.splitlines() if line.strip()]
        assert len(lines) == 2
        assert "Second commit" in lines[0]
        assert "First commit" in lines[1]

    def test_diff_between_two_commits(
        self, repo: Repository, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """diff between two commits shows changed lines."""
        self._write(repo, "file.txt", "line one\n")
        assert add(repo, ["file.txt"]) == 0
        assert commit(repo, "First commit") == 0
        sha1 = repo.head.resolve(repo.refs)

        self._write(repo, "file.txt", "line two\n")
        assert add(repo, ["file.txt"]) == 0
        assert commit(repo, "Second commit") == 0
        sha2 = repo.head.resolve(repo.refs)

        assert diff(repo, [sha1, sha2]) == 0
        captured = capsys.readouterr()
        assert "-line one" in captured.out
        assert "+line two" in captured.out

    def test_head_consistency_after_workflow(self, repo: Repository) -> None:
        """HEAD always resolves after a sequence of commits and branch ops."""
        self._write(repo, "f.txt", "a\n")
        assert add(repo, ["f.txt"]) == 0
        assert commit(repo, "commit A") == 0
        sha_a = repo.head.resolve(repo.refs)

        assert branch(repo, "dev") == 0
        assert checkout(repo, "dev") == 0
        self._write(repo, "f.txt", "b\n")
        assert add(repo, ["f.txt"]) == 0
        assert commit(repo, "commit B") == 0
        sha_b = repo.head.resolve(repo.refs)

        assert sha_b != sha_a
        # main still at sha_a
        assert repo.refs.resolve("refs/heads/main") == sha_a
        # dev at sha_b
        assert repo.refs.resolve("refs/heads/dev") == sha_b

    def test_reflog_recorded_for_commits(self, repo: Repository) -> None:
        """Reflog has one entry per commit on HEAD."""
        self._write(repo, "f.txt", "1\n")
        assert add(repo, ["f.txt"]) == 0
        assert commit(repo, "commit 1") == 0

        self._write(repo, "f.txt", "2\n")
        assert add(repo, ["f.txt"]) == 0
        assert commit(repo, "commit 2") == 0

        # read() returns newest first.
        entries = repo.reflog.read("HEAD")
        assert len(entries) == 2
        assert entries[0].message == "commit: commit 2"
        assert entries[1].message == "commit: commit 1"


class TestStatusIntegration:
    """status command integration."""

    def test_status_empty_repo(
        self, repo: Repository, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """status on an empty repo shows 'nothing to commit'."""
        assert status(repo) == 0
        captured = capsys.readouterr()
        assert "nothing to commit" in captured.out

    def test_status_shows_staged_file(
        self, repo: Repository, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """status shows newly staged file as added."""
        (repo.worktree / "new.txt").write_text("hello\n")
        assert add(repo, ["new.txt"]) == 0
        assert status(repo, short=True) == 0
        captured = capsys.readouterr()
        assert "new.txt" in captured.out

    def test_status_clean_after_commit(
        self, repo: Repository, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """status is clean after all changes are committed."""
        (repo.worktree / "f.txt").write_text("hi\n")
        assert add(repo, ["f.txt"]) == 0
        assert commit(repo, "msg") == 0
        assert status(repo) == 0
        captured = capsys.readouterr()
        assert "nothing to commit" in captured.out


class TestCatFileIntegration:
    """cat-file plumbing command integration."""

    def test_cat_file_blob(self, repo: Repository) -> None:
        """cat-file -p returns blob content."""
        (repo.worktree / "data.txt").write_text("hello\n")
        assert add(repo, ["data.txt"]) == 0
        assert commit(repo, "add data") == 0

        sha = repo.head.resolve(repo.refs)
        commit_obj = repo.objects.read_commit(sha)
        tree = repo.objects.read_tree(commit_obj.tree_sha)
        blob_sha = tree.entries[0].sha

        buf = io.BytesIO()
        assert cat_file(repo, blob_sha, pretty=True, out=buf) == 0
        assert buf.getvalue() == b"hello\n"
