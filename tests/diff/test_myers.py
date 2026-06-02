"""Tests for the Myers diff algorithm (gitpy/diff/myers.py)."""

import pytest

from gitpy.diff.myers import Edit, EditType, myers_diff

# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------


def _count_changes(edits: list[Edit]) -> int:
    """Count total lines that are INSERT or DELETE (the edit distance)."""
    total = 0
    for e in edits:
        if e.type == EditType.INSERT:
            total += e.new_count
        elif e.type == EditType.DELETE:
            total += e.old_count
    return total


def _reconstruct_new(_old: list[str], edits: list[Edit]) -> list[str]:
    """Apply the edit script to *_old* and return the resulting sequence."""
    result: list[str] = []
    for edit in edits:
        if edit.type == EditType.EQUAL:
            result.extend(edit.old_lines)
        elif edit.type == EditType.INSERT:
            result.extend(edit.new_lines)
        # DELETE: skip old lines
    return result


# ---------------------------------------------------------------------------
# Edge-case inputs
# ---------------------------------------------------------------------------


def test_both_empty() -> None:
    assert myers_diff([], []) == []


def test_old_empty_new_nonempty() -> None:
    new = ["a", "b", "c"]
    edits = myers_diff([], new)
    assert len(edits) == 1
    assert edits[0].type == EditType.INSERT
    assert edits[0].new_lines == new
    assert edits[0].new_count == 3


def test_new_empty_old_nonempty() -> None:
    old = ["x", "y"]
    edits = myers_diff(old, [])
    assert len(edits) == 1
    assert edits[0].type == EditType.DELETE
    assert edits[0].old_lines == old
    assert edits[0].old_count == 2


def test_identical_inputs() -> None:
    lines = ["hello", "world", "foo"]
    edits = myers_diff(lines, lines)
    # All edits must be EQUAL
    for edit in edits:
        assert edit.type == EditType.EQUAL
    # Reconstruct must be identical
    assert _reconstruct_new(lines, edits) == lines


# ---------------------------------------------------------------------------
# Correctness: reconstructed output matches expected new
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "old, new",
    [
        (["a"], ["b"]),
        (["a", "b", "c"], ["a", "c"]),
        (["a", "c"], ["a", "b", "c"]),
        (["a", "b", "c", "d"], ["b", "c", "d", "e"]),
        (["line1", "line2", "line3"], ["line1", "line2", "lineX", "line3"]),
    ],
)
def test_reconstruct_matches_new(old: list[str], new: list[str]) -> None:
    edits = myers_diff(old, new)
    assert _reconstruct_new(old, edits) == new


# ---------------------------------------------------------------------------
# Classic Myers example: ABCABBA -> CBABAC
# ---------------------------------------------------------------------------


def test_classic_myers_example() -> None:
    """Verify the textbook ABCABBA -> CBABAC example.

    The edit distance for this pair is 5 (delete A, delete B at start,
    delete one A, insert C at end — the classic trace gives D=5).
    """
    old = list("ABCABBA")
    new = list("CBABAC")
    edits = myers_diff(old, new)

    # Reconstruction must be correct.
    assert _reconstruct_new(old, edits) == new

    # Minimality: the known edit distance is 5.
    assert _count_changes(edits) == 5


# ---------------------------------------------------------------------------
# Minimality assertions
# ---------------------------------------------------------------------------


def test_insert_only_is_minimal() -> None:
    old: list[str] = []
    new = ["x"] * 4
    edits = myers_diff(old, new)
    assert _count_changes(edits) == 4


def test_delete_only_is_minimal() -> None:
    old = ["x"] * 3
    new: list[str] = []
    edits = myers_diff(old, new)
    assert _count_changes(edits) == 3


def test_single_substitution_is_minimal() -> None:
    """Substituting one line has edit distance 2 (1 delete + 1 insert)."""
    edits = myers_diff(["old"], ["new"])
    assert _count_changes(edits) == 2


def test_prefix_suffix_common_lines_reduce_edit_distance() -> None:
    """Lines shared at prefix/suffix must be recognised as EQUAL, not diffed."""
    old = ["a", "b", "c", "d"]
    new = ["a", "X", "c", "d"]
    edits = myers_diff(old, new)
    # Only 'b' vs 'X' differs: distance = 2
    assert _count_changes(edits) == 2


def test_all_lines_different_is_minimal() -> None:
    old = ["1", "2", "3"]
    new = ["a", "b"]
    edits = myers_diff(old, new)
    # Edit distance = 3 + 2 = 5 (no common lines)
    assert _count_changes(edits) == 5


# ---------------------------------------------------------------------------
# Structural invariants
# ---------------------------------------------------------------------------


def test_consecutive_edits_are_merged() -> None:
    """Adjacent edits of the same type must be merged into one Edit."""
    old = ["a", "b", "c"]
    new = ["x", "y", "z"]
    edits = myers_diff(old, new)
    types = [e.type for e in edits]
    # There should be no two consecutive equal types.
    for i in range(len(types) - 1):
        assert types[i] != types[i + 1], "Consecutive same-type edits were not merged"


def test_line_numbers_are_1_based_for_equal() -> None:
    old = ["a", "b", "c"]
    edits = myers_diff(old, old)
    for edit in edits:
        if edit.type == EditType.EQUAL:
            assert edit.old_start >= 1
            assert edit.new_start >= 1
