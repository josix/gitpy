"""Command-line interface for gitpy."""

from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console

import gitpy
from gitpy.commands.plumbing import (
    cat_file,
    commit_tree,
    hash_object,
    ls_tree,
    update_ref,
    write_tree_cmd,
)
from gitpy.commands.porcelain import (
    add as porcelain_add,
)
from gitpy.commands.porcelain import (
    branch as porcelain_branch,
)
from gitpy.commands.porcelain import (
    checkout as porcelain_checkout,
)
from gitpy.commands.porcelain import (
    commit as porcelain_commit,
)
from gitpy.commands.porcelain import (
    diff as porcelain_diff,
)
from gitpy.commands.porcelain import (
    init as porcelain_init,
)
from gitpy.commands.porcelain import (
    log as porcelain_log,
)
from gitpy.commands.porcelain import (
    status as porcelain_status,
)
from gitpy.repository import Repository

app = typer.Typer(
    name="gitpy",
    help="A Python implementation of Git internals.",
    no_args_is_help=True,
    rich_markup_mode="rich",
)
console = Console()


def version_callback(value: bool) -> None:
    """Print version and exit."""
    if value:
        console.print(f"[bold green]gitpy[/bold green] version {gitpy.__version__}")
        raise typer.Exit()


@app.callback()
def main(
    version: bool = typer.Option(
        False,
        "--version",
        "-v",
        help="Show version and exit.",
        callback=version_callback,
        is_eager=True,
    ),
) -> None:
    """gitpy - A Python implementation of Git internals."""


# ---------------------------------------------------------------------------
# Porcelain commands
# ---------------------------------------------------------------------------


@app.command()
def init(
    directory: str = typer.Argument(".", help="Directory to initialize"),
    bare: bool = typer.Option(False, "--bare", help="Create a bare repository"),
) -> None:
    """Initialize a new git repository."""
    code = porcelain_init(directory, bare=bare)
    raise typer.Exit(code)


@app.command()
def status(
    short: bool = typer.Option(False, "-s", "--short", help="Short format"),
) -> None:
    """Show the working tree status."""
    repo = Repository.find()
    code = porcelain_status(repo, short=short)
    raise typer.Exit(code)


@app.command()
def add(
    paths: Annotated[list[str] | None, typer.Argument(help="Files to stage")] = None,
    all: bool = typer.Option(False, "-A", "--all", help="Stage all changes"),
) -> None:
    """Add file contents to the index."""
    repo = Repository.find()
    effective_paths: list[str] = paths or []
    code = porcelain_add(repo, effective_paths, all=all)
    raise typer.Exit(code)


@app.command()
def commit(
    message: str = typer.Option(..., "-m", "--message", help="Commit message"),
    amend: bool = typer.Option(False, "--amend", help="Amend the last commit"),
) -> None:
    """Record changes to the repository."""
    repo = Repository.find()
    code = porcelain_commit(repo, message, amend=amend)
    raise typer.Exit(code)


@app.command()
def log(
    revision: str = typer.Argument("HEAD", help="Starting revision"),
    oneline: bool = typer.Option(False, "--oneline", help="Compact output"),
    n: int | None = typer.Option(None, "-n", help="Limit number of commits"),
) -> None:
    """Show the commit history."""
    repo = Repository.find()
    code = porcelain_log(repo, revision, oneline=oneline, n=n)
    raise typer.Exit(code)


@app.command()
def diff(
    commits: Annotated[
        list[str] | None, typer.Argument(help="Commits to compare")
    ] = None,
    staged: bool = typer.Option(
        False, "--staged", "--cached", help="Compare index vs HEAD"
    ),
) -> None:
    """Show changes between commits or between the working tree and index."""
    repo = Repository.find()
    code = porcelain_diff(repo, commits or [], staged=staged)
    raise typer.Exit(code)


@app.command()
def branch(
    name: str | None = typer.Argument(None, help="Branch name"),
    delete: bool = typer.Option(False, "-d", "--delete", help="Delete branch"),
    move: bool = typer.Option(False, "-m", "--move", help="Rename branch"),
    old_name: str | None = typer.Option(
        None, "--old", help="Old branch name (for rename)"
    ),
    new_name: str | None = typer.Option(
        None, "--new", help="New branch name (for rename)"
    ),
    force: bool = typer.Option(False, "-f", "--force", help="Force operation"),
) -> None:
    """List, create, delete, or rename branches."""
    repo = Repository.find()
    code = porcelain_branch(
        repo,
        name,
        delete=delete,
        move=move,
        old=old_name,
        new=new_name,
        force=force,
    )
    raise typer.Exit(code)


@app.command()
def checkout(
    target: str | None = typer.Argument(None, help="Branch or commit to switch to"),
    new_branch: str | None = typer.Option(
        None, "-b", help="Create and switch to new branch"
    ),
    paths: Annotated[
        list[str] | None, typer.Option("--path", help="Paths to restore")
    ] = None,
) -> None:
    """Switch branches or restore working tree files."""
    repo = Repository.find()
    code = porcelain_checkout(repo, target, new_branch=new_branch, paths=paths)
    raise typer.Exit(code)


# ---------------------------------------------------------------------------
# Plumbing commands
# ---------------------------------------------------------------------------


@app.command(name="hash-object")
def hash_object_cmd(
    path: str = typer.Argument(..., help="File to hash"),
    obj_type: str = typer.Option("blob", "-t", "--type", help="Object type"),
    write: bool = typer.Option(False, "-w", "--write", help="Write to object store"),
) -> None:
    """Compute object SHA-1 and optionally store it."""
    repo = Repository.find()
    data = Path(path).read_bytes()
    sha = hash_object(repo, data, type_name=obj_type, write=write)
    typer.echo(sha)
    raise typer.Exit(0)


@app.command(name="cat-file")
def cat_file_cmd(
    obj: str = typer.Argument(..., help="Object to inspect"),
    show_type: bool = typer.Option(False, "-t", help="Print object type"),
    show_size: bool = typer.Option(False, "-s", help="Print object size"),
    pretty: bool = typer.Option(False, "-p", help="Pretty-print object"),
) -> None:
    """Provide content or type information for repository objects."""
    import sys

    repo = Repository.find()
    code = cat_file(
        repo,
        obj,
        show_type=show_type,
        show_size=show_size,
        pretty=pretty,
        out=sys.stdout.buffer,
    )
    raise typer.Exit(code)


@app.command(name="ls-tree")
def ls_tree_cmd(
    tree_ish: str = typer.Argument(..., help="Tree-ish to list"),
    recursive: bool = typer.Option(False, "-r", help="Recurse into subtrees"),
) -> None:
    """List contents of a tree object."""
    import sys

    repo = Repository.find()
    code = ls_tree(repo, tree_ish, recursive=recursive, out=sys.stdout.buffer)
    raise typer.Exit(code)


@app.command(name="write-tree")
def write_tree_cmd_cli() -> None:
    """Create a tree object from the current index."""
    repo = Repository.find()
    sha = write_tree_cmd(repo)
    typer.echo(sha)
    raise typer.Exit(0)


@app.command(name="commit-tree")
def commit_tree_cmd(
    tree: str = typer.Argument(..., help="Tree SHA"),
    parent: Annotated[
        list[str] | None, typer.Option("-p", "--parent", help="Parent commit SHA")
    ] = None,
    message: str = typer.Option(..., "-m", "--message", help="Commit message"),
) -> None:
    """Create a new commit object."""
    repo = Repository.find()
    sha = commit_tree(repo, tree, parents=parent or [], message=message)
    typer.echo(sha)
    raise typer.Exit(0)


@app.command(name="update-ref")
def update_ref_cmd(
    ref: str = typer.Argument(..., help="Reference name"),
    newvalue: str | None = typer.Argument(None, help="New SHA"),
    delete: bool = typer.Option(False, "-d", "--delete", help="Delete reference"),
) -> None:
    """Update or delete a reference."""
    repo = Repository.find()
    code = update_ref(repo, ref, newvalue, delete=delete)
    raise typer.Exit(code)


if __name__ == "__main__":
    app()
