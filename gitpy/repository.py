"""Git repository abstraction.

Provides the main Repository class for interacting with Git repositories,
including initialization, discovery, and access to storage components.
"""

from pathlib import Path
from typing import Self

from .storage.database import ObjectDatabase


class Repository:
    """Represents a Git repository.

    Provides access to all repository components:
    objects, references, index, etc.
    """

    def __init__(self, path: Path, git_dir: Path | None = None) -> None:
        """Open existing repository.

        Args:
            path: Working directory path.
            git_dir: .git directory (default: path/.git).

        Raises:
            ValueError: Not a git repository.
        """
        self.worktree = path.resolve()
        self.git_dir = git_dir or (self.worktree / ".git")

        if not self.git_dir.exists():
            raise ValueError(f"Not a git repository: {path}")

        self.objects = ObjectDatabase(self.git_dir)

    @classmethod
    def init(cls, path: Path, *, bare: bool = False) -> Self:
        """Initialize a new repository.

        Args:
            path: Where to create repository.
            bare: If True, create bare repository (no working directory).

        Returns:
            Newly created Repository.

        Raises:
            ValueError: Already a git repository.
        """
        path = Path(path).resolve()

        if bare:
            git_dir = path
            worktree = path  # For bare repos, use path as worktree for consistency
        else:
            git_dir = path / ".git"
            worktree = path

        # Check not already a repo
        if git_dir.exists():
            raise ValueError(f"Already a git repository: {path}")

        # Create directory structure
        git_dir.mkdir(parents=True, exist_ok=True)

        # Create subdirectories
        (git_dir / "objects" / "info").mkdir(parents=True)
        (git_dir / "objects" / "pack").mkdir(parents=True)
        (git_dir / "refs" / "heads").mkdir(parents=True)
        (git_dir / "refs" / "tags").mkdir(parents=True)
        (git_dir / "info").mkdir(parents=True)

        # Create HEAD
        (git_dir / "HEAD").write_text("ref: refs/heads/main\n")

        # Create config
        config = f"""[core]
\trepositoryformatversion = 0
\tfilemode = true
\tbare = {str(bare).lower()}
"""
        (git_dir / "config").write_text(config)

        # Create description
        (git_dir / "description").write_text(
            "Unnamed repository; edit this file to name it.\n"
        )

        # Create info/exclude
        (git_dir / "info" / "exclude").write_text(
            "# git ls-files --others --exclude-from=.git/info/exclude\n"
        )

        return cls(path=worktree, git_dir=git_dir)

    @classmethod
    def find(cls, start_path: Path | None = None) -> Self:
        """Find repository containing path.

        Searches up directory tree for .git directory.

        Args:
            start_path: Where to start search (default: cwd).

        Returns:
            Repository containing start_path.

        Raises:
            ValueError: Not inside a repository.
        """
        path = Path(start_path or Path.cwd()).resolve()

        while True:
            git_dir = path / ".git"
            if git_dir.is_dir():
                return cls(path=path, git_dir=git_dir)

            if git_dir.is_file():
                # Handle git worktrees: .git is file pointing to real git dir
                content = git_dir.read_text().strip()
                if content.startswith("gitdir: "):
                    real_git_dir = Path(content[8:])
                    if not real_git_dir.is_absolute():
                        real_git_dir = path / real_git_dir
                    return cls(path=path, git_dir=real_git_dir.resolve())

            parent = path.parent
            if parent == path:
                raise ValueError("Not a git repository (or any parent)")
            path = parent

    def __repr__(self) -> str:
        """Return string representation."""
        return f"Repository({self.worktree})"
