"""Unified diff format implementation.

Produces unified diff output compatible with `diff -u` and `git diff`.
"""

from dataclasses import dataclass, field

from .myers import Edit, EditType, myers_diff


@dataclass(slots=True)
class _Hunk:
    """Internal representation of a unified diff hunk."""

    old_start: int
    new_start: int
    old_count: int = 0
    new_count: int = 0
    lines: list[tuple[str, str]] = field(default_factory=list)


def format_unified_diff(
    old_lines: list[str],
    new_lines: list[str],
    old_name: str = "a",
    new_name: str = "b",
    context: int = 3,
) -> str:
    """Format a pair of line lists as a unified diff string.

    Args:
        old_lines: Lines of the old version (without trailing newlines).
        new_lines: Lines of the new version (without trailing newlines).
        old_name: Label for the old file shown in the ``---`` header.
        new_name: Label for the new file shown in the ``+++`` header.
        context: Number of unchanged context lines around each change.

    Returns:
        Unified diff string (including a trailing newline), or an empty
        string if the two inputs are identical.
    """
    edits = myers_diff(old_lines, new_lines)

    # If every edit is EQUAL there is nothing to report.
    if not any(e.type != EditType.EQUAL for e in edits):
        return ""

    hunks = _create_hunks(edits, context)
    if not hunks:
        return ""

    out: list[str] = [f"--- {old_name}", f"+++ {new_name}"]

    for hunk in hunks:
        # Unified diff convention: omit count when it equals 1
        old_range = (
            f"{hunk.old_start}"
            if hunk.old_count == 1
            else f"{hunk.old_start},{hunk.old_count}"
        )
        new_range = (
            f"{hunk.new_start}"
            if hunk.new_count == 1
            else f"{hunk.new_start},{hunk.new_count}"
        )
        out.append(f"@@ -{old_range} +{new_range} @@")

        for kind, text in hunk.lines:
            if kind == "context":
                out.append(f" {text}")
            elif kind == "delete":
                out.append(f"-{text}")
            else:
                out.append(f"+{text}")

    return "\n".join(out) + "\n"


# ---------------------------------------------------------------------------
# Hunk builder
# ---------------------------------------------------------------------------


def _create_hunks(edits: list[Edit], context: int) -> list[_Hunk]:
    """Build a list of hunks from a merged edit list.

    The algorithm makes a single pass over the flattened per-line edit
    sequence.  A new hunk is started whenever the gap between two change
    regions exceeds 2*context equal lines.

    Args:
        edits: Merged list of Edit objects from myers_diff.
        context: Context lines on each side of a change.

    Returns:
        List of ``_Hunk`` objects ready to render.
    """
    # Expand edits into a flat per-line sequence.
    # Each item: (kind, text, old_lineno, new_lineno)
    # old_lineno is 0 for pure inserts; new_lineno is 0 for pure deletes.
    flat: list[tuple[str, str, int, int]] = []
    for edit in edits:
        if edit.type == EditType.EQUAL:
            for i, line in enumerate(edit.old_lines):
                flat.append(("equal", line, edit.old_start + i, edit.new_start + i))
        elif edit.type == EditType.DELETE:
            for i, line in enumerate(edit.old_lines):
                flat.append(("delete", line, edit.old_start + i, 0))
        else:  # INSERT
            for i, line in enumerate(edit.new_lines):
                flat.append(("insert", line, 0, edit.new_start + i))

    # Identify positions that carry changes.
    change_indices = [idx for idx, (kind, *_) in enumerate(flat) if kind != "equal"]
    if not change_indices:
        return []

    # Group change indices into clusters separated by > 2*context equal lines.
    clusters: list[list[int]] = []
    current: list[int] = [change_indices[0]]
    for ci in change_indices[1:]:
        if ci - current[-1] - 1 > 2 * context:
            clusters.append(current)
            current = [ci]
        else:
            current.append(ci)
    clusters.append(current)

    hunks: list[_Hunk] = []
    for cluster in clusters:
        first_change = cluster[0]
        last_change = cluster[-1]

        hunk_start_idx = max(0, first_change - context)
        hunk_end_idx = min(len(flat) - 1, last_change + context)

        # Determine hunk header line numbers from the first line in the window.
        old_start = _first_old_lineno(flat, hunk_start_idx)
        new_start = _first_new_lineno(flat, hunk_start_idx)

        hunk = _Hunk(old_start=old_start, new_start=new_start)

        for idx in range(hunk_start_idx, hunk_end_idx + 1):
            kind, text, _old_ln, _new_ln = flat[idx]
            if kind == "equal":
                hunk.lines.append(("context", text))
                hunk.old_count += 1
                hunk.new_count += 1
            elif kind == "delete":
                hunk.lines.append(("delete", text))
                hunk.old_count += 1
            else:
                hunk.lines.append(("insert", text))
                hunk.new_count += 1

        hunks.append(hunk)

    return hunks


def _first_old_lineno(
    flat: list[tuple[str, str, int, int]],
    start: int,
) -> int:
    """Determine the old-file line number for the first line of a hunk window.

    Scans forward from *start* to find the first line that has a known
    old line number, then adjusts for any inserts before the change.

    Args:
        flat: Expanded flat list of (kind, text, old_ln, new_ln).
        start: Index of the first line in this hunk window.

    Returns:
        1-based old-file line number.
    """
    for idx in range(start, len(flat)):
        kind, _t, old_ln, _n = flat[idx]
        if old_ln != 0:
            # offset = number of equal/delete lines between start and idx
            offset = sum(
                1 for i in range(start, idx) if flat[i][0] in ("equal", "delete")
            )
            return old_ln - offset
    return 1  # pragma: no cover


def _first_new_lineno(
    flat: list[tuple[str, str, int, int]],
    start: int,
) -> int:
    """Determine the new-file line number for the first line of a hunk window.

    Args:
        flat: Expanded flat list of (kind, text, old_ln, new_ln).
        start: Index of the first line in this hunk window.

    Returns:
        1-based new-file line number.
    """
    for idx in range(start, len(flat)):
        kind, _t, _o, new_ln = flat[idx]
        if new_ln != 0:
            offset = sum(
                1 for i in range(start, idx) if flat[i][0] in ("equal", "insert")
            )
            return new_ln - offset
    return 1  # pragma: no cover
