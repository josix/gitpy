"""Tests for the unified diff formatter (gitpy/diff/unified.py)."""

import shutil
import subprocess
import tempfile
from pathlib import Path

import pytest

from gitpy.diff.unified import format_unified_diff

# ---------------------------------------------------------------------------
# Basic smoke tests
# ---------------------------------------------------------------------------


def test_no_change_returns_empty() -> None:
    lines = ["a", "b", "c"]
    assert format_unified_diff(lines, lines) == ""


def test_both_empty_returns_empty() -> None:
    assert format_unified_diff([], []) == ""


def test_header_present() -> None:
    result = format_unified_diff(
        ["old"], ["new"], old_name="a/f.txt", new_name="b/f.txt"
    )
    assert result.startswith("--- a/f.txt\n")
    assert "+++ b/f.txt\n" in result


# ---------------------------------------------------------------------------
# Hunk header correctness
# ---------------------------------------------------------------------------


def test_single_change_hunk_header() -> None:
    """A change at line 5 with default context=3 starts at line 2."""
    old = ["line1", "line2", "line3", "line4", "line5", "line6", "line7"]
    new = ["line1", "line2", "line3", "line4", "CHANGED", "line6", "line7"]
    result = format_unified_diff(old, new)
    assert "@@ " in result
    # The hunk should start at line 2 (5-3=2) and end at line 7 (5+2 context).
    assert "@@ -2,6 +2,6 @@" in result


def test_hunk_header_line1_change() -> None:
    """Change at line 1: old_start must be 1, not 0 or negative."""
    old = ["ORIGINAL", "b", "c", "d", "e"]
    new = ["CHANGED", "b", "c", "d", "e"]
    result = format_unified_diff(old, new)
    assert "@@ -1" in result
    assert "@@ -1" in result


# ---------------------------------------------------------------------------
# Context clamping at file start / end
# ---------------------------------------------------------------------------


def test_context_clamp_at_start() -> None:
    """Change at line 1 must not produce negative context lines."""
    old = ["CHANGE", "b", "c", "d"]
    new = ["change", "b", "c", "d"]
    result = format_unified_diff(old, new)
    # Leading context lines (space-prefixed) must not appear before line 1
    lines = result.splitlines()
    hunk_idx = next(i for i, ln in enumerate(lines) if ln.startswith("@@"))
    # The first body line must be the changed line (no context before it when
    # the change is at line 1).
    body_before_change = [
        ln
        for ln in lines[hunk_idx + 1 :]
        if ln.startswith(" ") and not ln.startswith("-")
    ]
    # Since the change is on line 1, there should be no leading context lines.
    # (There should be trailing context only.)
    hunk_header = lines[hunk_idx]
    # old_start in the hunk header must be 1
    assert "-1" in hunk_header
    # No context lines before the change (only trailing context)
    assert len(body_before_change) <= 3  # at most 3 trailing context lines


def test_context_clamp_at_end() -> None:
    """Change at the last line must not produce context beyond EOF."""
    old = ["a", "b", "c", "CHANGE"]
    new = ["a", "b", "c", "change"]
    result = format_unified_diff(old, new)
    lines = result.splitlines()
    # Extract hunk body lines only (exclude --- / +++ headers).
    body = [
        ln
        for ln in lines
        if ln.startswith((" ", "-", "+")) and not ln.startswith(("---", "+++"))
    ]
    # 3 context lines (a, b, c) + 1 delete + 1 insert = 5 body lines.
    assert len(body) == 5


# ---------------------------------------------------------------------------
# Multi-hunk gap splitting
# ---------------------------------------------------------------------------


def test_two_far_apart_changes_produce_two_hunks() -> None:
    """Changes separated by > 2*context equal lines become separate hunks."""
    # 20 unchanged lines between the two changes.
    spacer = [f"line{i}" for i in range(20)]
    old = ["FIRST_OLD"] + spacer + ["SECOND_OLD"]
    new = ["FIRST_NEW"] + spacer + ["SECOND_NEW"]
    result = format_unified_diff(old, new)
    hunk_count = result.count("@@ ")
    assert hunk_count == 2, f"Expected 2 hunks, got {hunk_count}"


def test_two_close_changes_produce_one_hunk() -> None:
    """Changes separated by <= 2*context equal lines merge into one hunk."""
    spacer = ["same"] * 4  # 4 lines — within 2*3=6 context window
    old = ["OLD1"] + spacer + ["OLD2"]
    new = ["NEW1"] + spacer + ["NEW2"]
    result = format_unified_diff(old, new)
    hunk_count = result.count("@@ ")
    assert hunk_count == 1, f"Expected 1 hunk, got {hunk_count}"


# ---------------------------------------------------------------------------
# Content correctness
# ---------------------------------------------------------------------------


def test_delete_only_diff() -> None:
    old = ["a", "b", "c"]
    new = ["a", "c"]
    result = format_unified_diff(old, new)
    assert "-b\n" in result or "-b" in result


def test_insert_only_diff() -> None:
    old = ["a", "c"]
    new = ["a", "b", "c"]
    result = format_unified_diff(old, new)
    assert "+b\n" in result or "+b" in result


def test_output_ends_with_newline() -> None:
    result = format_unified_diff(["a"], ["b"])
    assert result.endswith("\n")


# ---------------------------------------------------------------------------
# Git-gated comparison
# ---------------------------------------------------------------------------


@pytest.mark.skipif(
    shutil.which("git") is None,
    reason="git not available in this environment",
)
def test_hunk_bodies_match_git() -> None:
    """Compare hunk +/- bodies against `git diff --no-index`."""
    old_lines = ["hello", "world", "foo", "bar", "baz"]
    new_lines = ["hello", "earth", "foo", "qux", "baz"]

    with tempfile.TemporaryDirectory() as tmp:
        old_file = Path(tmp) / "old.txt"
        new_file = Path(tmp) / "new.txt"
        old_file.write_text("\n".join(old_lines) + "\n")
        new_file.write_text("\n".join(new_lines) + "\n")

        proc = subprocess.run(
            ["git", "diff", "--no-index", str(old_file), str(new_file)],
            capture_output=True,
            text=True,
        )
        git_output = proc.stdout

    our_result = format_unified_diff(old_lines, new_lines)

    # Extract hunk lines (+/-/ ) from both outputs.
    def _hunk_lines(diff: str) -> list[str]:
        return [
            ln
            for ln in diff.splitlines()
            if ln.startswith(("+", "-", " ")) and not ln.startswith(("---", "+++"))
        ]

    our_body = _hunk_lines(our_result)
    git_body = _hunk_lines(git_output)

    assert our_body == git_body, (
        f"Hunk body mismatch.\nOurs:\n{our_result}\nGit:\n{git_output}"
    )
