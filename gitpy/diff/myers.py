"""Myers diff algorithm implementation.

Implements Eugene Myers' O(ND) diff algorithm for computing the shortest
edit script (SES) between two sequences of lines.
"""

from dataclasses import dataclass
from enum import Enum


class EditType(Enum):
    """Type of a single edit operation."""

    EQUAL = "equal"
    INSERT = "insert"
    DELETE = "delete"


@dataclass(slots=True)
class Edit:
    """Single edit operation in a diff script.

    Attributes:
        type: Kind of edit (EQUAL, INSERT, DELETE).
        old_start: 1-based line number in old file (0 for pure inserts).
        old_count: Number of lines consumed from old file.
        new_start: 1-based line number in new file (0 for pure deletes).
        new_count: Number of lines consumed from new file.
        old_lines: Lines from old file involved in this edit.
        new_lines: Lines from new file involved in this edit.
    """

    type: EditType
    old_start: int
    old_count: int
    new_start: int
    new_count: int
    old_lines: list[str]
    new_lines: list[str]


def myers_diff(old: list[str], new: list[str]) -> list[Edit]:
    """Compute the shortest edit script using the Myers O(ND) algorithm.

    Produces a minimal edit script: the total number of insertions and
    deletions is the edit distance D between the two sequences.

    Args:
        old: Lines of the old version.
        new: Lines of the new version.

    Returns:
        List of Edit operations that transform old into new. Consecutive
        edits of the same type are merged into a single Edit.
    """
    n, m = len(old), len(new)

    if n == 0 and m == 0:
        return []
    if n == 0:
        return [Edit(EditType.INSERT, 0, 0, 1, m, [], list(new))]
    if m == 0:
        return [Edit(EditType.DELETE, 1, n, 0, 0, list(old), [])]

    # Run Myers forward pass, recording the frontier at each depth d.
    max_d = n + m
    # v[k] = furthest x reached on diagonal k (x = old index, y = x - k)
    v: dict[int, int] = {1: 0}
    trace: list[dict[int, int]] = []

    for d in range(max_d + 1):
        trace.append(dict(v))
        for k in range(-d, d + 1, 2):
            # Choose move: down (insert) or right (delete)
            go_down = k == -d or (k != d and v.get(k - 1, 0) < v.get(k + 1, 0))
            x = v.get(k + 1, 0) if go_down else v.get(k - 1, 0) + 1
            y = x - k
            # Extend along equal diagonal
            while x < n and y < m and old[x] == new[y]:
                x += 1
                y += 1
            v[k] = x
            if x >= n and y >= m:
                return _backtrack(trace, old, new)

    return []  # unreachable for finite inputs


def _backtrack(
    trace: list[dict[int, int]],
    old: list[str],
    new: list[str],
) -> list[Edit]:
    """Walk backward through the Myers trace to build the edit list.

    Args:
        trace: Sequence of frontier snapshots, one per d-value.
        old: Old lines.
        new: New lines.

    Returns:
        Merged list of Edit objects in forward order.
    """
    n, m = len(old), len(new)
    x, y = n, m
    raw: list[Edit] = []

    for d in range(len(trace) - 1, -1, -1):
        v = trace[d]
        k = x - y

        go_down = k == -d or (k != d and v.get(k - 1, 0) < v.get(k + 1, 0))
        prev_k = k + 1 if go_down else k - 1
        prev_x = v.get(prev_k, 0)
        prev_y = prev_x - prev_k

        # Diagonal (equal) moves
        while x > prev_x and y > prev_y:
            x -= 1
            y -= 1
            raw.append(Edit(EditType.EQUAL, x + 1, 1, y + 1, 1, [old[x]], [new[y]]))

        if d > 0:
            if go_down:
                # Insert: moved down on diagonal (y advanced without x)
                y -= 1
                raw.append(Edit(EditType.INSERT, x, 0, y + 1, 1, [], [new[y]]))
            else:
                # Delete: moved right on diagonal (x advanced without y)
                x -= 1
                raw.append(Edit(EditType.DELETE, x + 1, 1, y, 0, [old[x]], []))

    raw.reverse()
    return _merge_edits(raw)


def _merge_edits(edits: list[Edit]) -> list[Edit]:
    """Merge consecutive edits of the same type into a single Edit.

    Args:
        edits: Flat list of single-line Edit objects.

    Returns:
        Compacted list where runs of the same EditType are merged.
    """
    if not edits:
        return []

    merged: list[Edit] = [
        Edit(
            edits[0].type,
            edits[0].old_start,
            edits[0].old_count,
            edits[0].new_start,
            edits[0].new_count,
            list(edits[0].old_lines),
            list(edits[0].new_lines),
        )
    ]

    for edit in edits[1:]:
        last = merged[-1]
        if last.type == edit.type:
            merged[-1] = Edit(
                last.type,
                last.old_start,
                last.old_count + edit.old_count,
                last.new_start,
                last.new_count + edit.new_count,
                last.old_lines + list(edit.old_lines),
                last.new_lines + list(edit.new_lines),
            )
        else:
            merged.append(
                Edit(
                    edit.type,
                    edit.old_start,
                    edit.old_count,
                    edit.new_start,
                    edit.new_count,
                    list(edit.old_lines),
                    list(edit.new_lines),
                )
            )

    return merged
