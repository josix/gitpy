"""Command-line interface for gitpy."""

import typer
from rich.console import Console

import gitpy

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


@app.command()
def init(
    directory: str = typer.Argument(".", help="Directory to initialize"),
) -> None:
    """Initialize a new git repository."""
    console.print(f"[yellow]TODO:[/yellow] Initialize repository in {directory}")


@app.command()
def status() -> None:
    """Show the working tree status."""
    console.print("[yellow]TODO:[/yellow] Show repository status")


if __name__ == "__main__":
    app()
