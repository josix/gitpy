"""Command-line interface for gitpy."""

import sys


def main() -> int:
    """Entry point for gitpy CLI."""
    print("gitpy - A Python implementation of Git internals")
    print("Usage: gitpy <command> [<args>]")
    return 0


if __name__ == "__main__":
    sys.exit(main())
