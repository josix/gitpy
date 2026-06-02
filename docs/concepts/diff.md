# Understanding Git's Diff Engine

This document explains how Git computes the difference between two versions of a file, how those differences are presented in the familiar unified diff format, and how gitpy extends line-level diffing up to whole-tree comparisons.

## The Big Picture: Computing Differences on Demand

Git never stores diffs. Every commit is a complete snapshot—a tree pointing to full blob objects. When you run `git diff`, Git reads the two blob contents, computes the difference algorithmically, and throws the result away. Next time you run `git diff`, it computes it again.

This "compute on demand" design has two consequences:

1. **Checkouts are fast**: no need to replay a chain of patches.
2. **Diffs are always exact**: the algorithm is deterministic given the same inputs.

The algorithm Git uses—and the one implemented in gitpy—is the **Myers diff algorithm**, published by Eugene Myers in 1986.

---

## The Edit Graph: A Visual Model

Before looking at code, it helps to visualise what "shortest edit script" means.

Given two sequences of lines:

```
Old:  A  B  C  D
New:  A  C  D  E
```

Lay them out as a grid. The old file is the horizontal axis (columns), the new file is the vertical axis (rows). Each position `(x, y)` means "consumed x lines of old and y lines of new".

```
        A   B   C   D
      ┌───┬───┬───┬───┐
   A  │╲  │   │   │   │   ← diagonal = equal (A=A)
      ├───┼───┼───┼───┤
   C  │   │   │╲  │   │   ← diagonal = equal (C=C)
      ├───┼───┼───┼───┤
   D  │   │   │   │╲  │   ← diagonal = equal (D=D)
      ├───┼───┼───┼───┤
   E  │   │   │   │   │
      └───┴───┴───┴───┘
```

- **Moving right** (→) costs 1: delete a line from the old file.
- **Moving down** (↓) costs 1: insert a line from the new file.
- **Moving diagonally** (↘) costs 0: the lines are equal.

The **shortest edit script** is the path from `(0,0)` to `(4,4)` with the fewest non-diagonal moves. Myers' O(ND) algorithm finds that path efficiently, where N is the total number of lines and D is the number of differences.

The path for the example above:

```
(0,0) → diagonal A   → (1,1)
(1,1) → right B      → (2,1)   DELETE "B"
(2,1) → diagonal C   → (3,2)
(3,2) → diagonal D   → (4,3)
(4,3) → down E       → (4,4)   INSERT "E"
```

Result: delete `B`, insert `E`. That is the minimal edit—two operations.

---

## Myers Algorithm: O(ND)

The insight behind Myers' algorithm is that you do not need to explore the entire grid. Instead, you explore "diagonals". Define diagonal `k = x - y`. All positions reachable from `(0,0)` with exactly `d` non-diagonal moves lie on diagonals `{-d, -d+2, ..., d-2, d}`.

The algorithm builds a map `v[k]` = "furthest x reached on diagonal k". For each depth `d` it extends each reachable diagonal one step (choosing the better of a right-move or a down-move as the starting point) then slides diagonally as far as possible over equal lines. When `x == n and y == m`, you have reached the end.

```
d=0: v[0] = 0 → slide diagonal (A=A) → v[0] = 1
d=1: k=-1: down from v[0]=1 → (1,2), no equal → v[-1]=1
     k=+1: right from v[0]=1 → (2,1), slide (C=C,D=D) → v[1]=4
           x=4, y=3, not done
d=2: k=-2: down from v[-1]=1 → (1,3), no equal → v[-2]=1
     k=0 : right from v[1]=4 → (5,4) — out of range; use down from v[-1]=1 → (1,2)
     k=+2: right from v[1]=4 → (5,3) — beyond n=4, so x=4, slide (E=E? no) → v[2]=4
           at (4,4): done! D=2, two edits.
```

The algorithm records a "trace" (one snapshot of `v` per depth) so it can walk backward to reconstruct the edit path.

### Minimal edit scripts

An important property: Myers always produces the **minimum** edit distance. There may be multiple edit scripts of the same minimum length, but Myers guarantees it never produces one longer than necessary.

---

## Edit and EditType

In gitpy, each edit operation is represented by an `Edit` dataclass:

```python
class EditType(Enum):
    EQUAL  = "equal"    # lines are the same
    INSERT = "insert"   # line added in new file
    DELETE = "delete"   # line removed from old file

@dataclass(slots=True)
class Edit:
    type: EditType
    old_start: int    # 1-based line number in old file (0 for pure inserts)
    old_count: int    # lines consumed from old file
    new_start: int    # 1-based line number in new file (0 for pure deletes)
    new_count: int    # lines consumed from new file
    old_lines: list[str]
    new_lines: list[str]
```

`myers_diff(old, new)` returns a merged list of `Edit` objects. Consecutive operations of the same type are combined into a single `Edit`, so you get compact blocks rather than one object per line.

```python
from gitpy.diff.myers import myers_diff, EditType

old = ["alpha", "beta", "gamma"]
new = ["alpha", "delta", "gamma"]

edits = myers_diff(old, new)
# [Edit(EQUAL, ..., ["alpha"]), Edit(DELETE, ..., ["beta"]),
#  Edit(INSERT, ..., ["delta"]), Edit(EQUAL, ..., ["gamma"])]
```

---

## Unified Diff Format

The raw edit list is not how humans read diffs. Git displays them in **unified diff** format, the same format produced by `diff -u`:

```diff
--- a/greeting.txt
+++ b/greeting.txt
@@ -1,4 +1,4 @@
 line one
-line two
+line TWO
 line three
 line four
```

The format has three parts:

**File headers**: `---` names the old file; `+++` names the new file.

**Hunk headers**: `@@ -<old_start>,<old_count> +<new_start>,<new_count> @@` describes the range of lines covered by this hunk. The counts are omitted when they equal 1.

**Hunk body lines**:
- ` ` prefix: context line (unchanged, shown for readability)
- `-` prefix: deleted line (from old file only)
- `+` prefix: inserted line (to new file only)

By default, three context lines surround each change. Changes separated by more than six equal lines appear in separate hunks.

```bash
$ git diff HEAD~1 HEAD
--- a/src/app.py
+++ b/src/app.py
@@ -10,7 +10,7 @@
 def main():
-    print("hello")
+    print("hello, world")
     return 0
```

### format_unified_diff

```python
from gitpy.diff.unified import format_unified_diff

old_lines = ["line one", "line two", "line three"]
new_lines = ["line one", "line TWO", "line three"]

result = format_unified_diff(
    old_lines, new_lines,
    old_name="a/greeting.txt",
    new_name="b/greeting.txt",
    context=3,
)
print(result)
# --- a/greeting.txt
# +++ b/greeting.txt
# @@ -1,3 +1,3 @@
#  line one
# -line two
# +line TWO
#  line three
```

Returns an empty string when the two inputs are identical.

---

## Tree Diffs

A line diff compares two blobs. A tree diff compares two whole commit trees and reports which files were added, modified, or deleted.

```bash
$ git diff HEAD~1 HEAD
diff --git a/src/app.py b/src/app.py
...
$ git diff --stat HEAD~1 HEAD
 src/app.py  | 2 +-
 tests/test_app.py | 5 +++++
 2 files changed, 6 insertions(+), 1 deletion(-)
```

Tree diffing works in two steps:

1. **Flatten**: recursively expand each tree into a flat map of `path → {sha, mode}`.
2. **Compare**: for each path in the union of the two maps, emit a `DiffEntry` describing what changed.

```
old tree:                new tree:
  README.md  → SHA_A      README.md  → SHA_A   (unchanged)
  src/app.py → SHA_B      src/app.py → SHA_C   (modified)
  old.txt    → SHA_D      new.txt    → SHA_E   (deleted + added)
```

`DiffStatus` values:

| Status | Meaning |
|--------|---------|
| `ADDED` | path exists in new tree, absent from old |
| `DELETED` | path exists in old tree, absent from new |
| `MODIFIED` | path exists in both with a different SHA or mode |
| `RENAMED` | path changed (detected externally; not yet auto-detected) |

### diff_trees and flatten_tree

```python
from gitpy.diff.tree import diff_trees, flatten_tree, DiffStatus, DiffEntry

for entry in diff_trees(old_tree_sha, new_tree_sha, db):
    if entry.status == DiffStatus.ADDED:
        print(f"A  {entry.path}")
    elif entry.status == DiffStatus.DELETED:
        print(f"D  {entry.path}")
    elif entry.status == DiffStatus.MODIFIED:
        print(f"M  {entry.path}  ({entry.old_sha[:7]} → {entry.new_sha[:7]})")
```

Pass `None` for either SHA to represent an empty tree—useful for diffing the initial commit (no parent) or a complete deletion.

`flatten_tree` is also useful on its own when you need all paths in a tree:

```python
paths = flatten_tree(tree_sha, db, prefix="")
# {"src/app.py": {"sha": "...", "mode": "100644"}, ...}
```

---

## Binary Files

Not all blobs are text. `is_binary` detects binary content using the same heuristic as Git: it looks for a NUL byte in the first 8000 bytes.

```python
from gitpy.diff.tree import is_binary, format_binary_diff

data = open("image.png", "rb").read()
if is_binary(data):
    print(format_binary_diff("image.png"))
    # Binary files a/image.png and b/image.png differ
```

When a diff would span a binary file, gitpy (like Git) skips the line-level diff and emits that single summary line.

```bash
$ git diff HEAD~1 HEAD -- logo.png
Binary files a/logo.png and b/logo.png differ
```

---

## Implementation in gitpy

The diff engine lives in `gitpy/diff/`:

```
gitpy/diff/
├── __init__.py
├── myers.py     # myers_diff, Edit, EditType
├── unified.py   # format_unified_diff
└── tree.py      # diff_trees, flatten_tree, is_binary, format_binary_diff
```

### myers.py

Public API:
- `myers_diff(old: list[str], new: list[str]) -> list[Edit]`

The function runs the Myers forward pass, stores a frontier snapshot at each depth, then backtracks through the trace to reconstruct the path. Consecutive same-type edits are merged before returning.

### unified.py

Public API:
- `format_unified_diff(old_lines, new_lines, old_name, new_name, context) -> str`

Internally calls `myers_diff`, groups edits into hunk clusters (changes separated by more than `2 * context` equal lines go into separate hunks), and renders the `---`/`+++` headers plus `@@` hunk lines.

### tree.py

Public API:
- `diff_trees(old_tree_sha, new_tree_sha, db) -> Iterator[DiffEntry]`
- `flatten_tree(tree_sha, db, prefix) -> dict[str, dict[str, str]]`
- `is_binary(data, sample=8000) -> bool`
- `format_binary_diff(path) -> str`

`DiffEntry` and `DiffStatus` are also exported for callers that need to inspect results programmatically.

---

## Putting It All Together: git diff Flow

Here is how `git diff HEAD~1 HEAD` is implemented end-to-end:

```
1. Resolve "HEAD~1" and "HEAD" to commit SHAs  → RevisionParser
2. Read each commit to get its tree SHA         → ObjectDatabase
3. diff_trees(old_tree_sha, new_tree_sha, db)   → per-file DiffEntry list
4. For each modified DiffEntry:
   a. Read old blob and new blob                → ObjectDatabase
   b. If is_binary(data): emit format_binary_diff
   c. Else: split into lines, call format_unified_diff
5. Print results
```

The key insight: steps 1-3 navigate object graph structure; steps 4-5 do the actual text analysis. These concerns are cleanly separated in the codebase.

---

## Key Takeaways

1. **Git never stores diffs**: every `git diff` result is computed fresh from full blob snapshots.
2. **Myers O(ND)**: the algorithm explores diagonals in the edit graph and is guaranteed to find the minimum edit distance.
3. **Unified diff**: `---`/`+++` headers, `@@ -old +new @@` hunk headers, ` `/`-`/`+` line prefixes.
4. **Tree diff = flatten + compare**: reduce both trees to flat path maps, then emit `DiffEntry` for every path that differs.
5. **Binary detection**: a NUL byte in the first 8000 bytes triggers "Binary files differ" instead of a line diff.

## What's Next?

- **[References](references.md)**: How to name commits (`HEAD`, `HEAD~1`, branch names) before you can diff them.
- **[Index & Staging](index_staging.md)**: The staged snapshot that `git diff --cached` compares against HEAD.
- **[Object Model](object_model.md)**: The blob and tree objects that the diff engine reads.
- **[Object Storage](object_storage.md)**: How those objects are retrieved from `.git/objects/`.
