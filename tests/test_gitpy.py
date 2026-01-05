"""Basic tests for gitpy."""

import gitpy


def test_version() -> None:
    """Test that version is defined."""
    assert gitpy.__version__ == "0.0.1"
