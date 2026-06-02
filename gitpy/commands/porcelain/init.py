"""Implementation of ``git init``.

Initialises a new repository at the given directory.
"""

from pathlib import Path

from gitpy.repository import Repository


def init(directory: str = ".", *, bare: bool = False) -> int:
    """Initialise a new git repository.

    Args:
        directory: Directory to initialise (created if absent).
        bare: If True, create a bare repository.

    Returns:
        0 on success, 1 on error.
    """
    path = Path(directory).resolve()
    path.mkdir(parents=True, exist_ok=True)

    try:
        repo = Repository.init(path, bare=bare)
    except ValueError as exc:
        print(f"error: {exc}")
        return 1

    hint = " (bare)" if bare else ""
    print(f"Initialized empty Git repository in {repo.git_dir}{hint}")
    return 0
