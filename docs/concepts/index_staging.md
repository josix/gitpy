# Understanding Git's Index and Staging Area

This document explains what the Git index is, how its binary format is laid out on disk, and how the three-way snapshot model (HEAD, index, worktree) drives `git status` and `git commit`.

## The Big Picture: Three Snapshots

At any moment, Git is tracking three versions of your project simultaneously:

```
HEAD                  Index (staging area)         Working tree
(last commit)         (.git/index)                 (your files)

┌─────────────┐       ┌─────────────┐              ┌─────────────┐
│ tree        │       │ entry per   │              │ actual      │
│ from last   │  ───► │ staged file │  ───────►    │ files on    │
│ commit      │       │ + SHA + stat│              │ disk        │
└─────────────┘       └─────────────┘              └─────────────┘
      ↑                     ↑
      │                     │
      └──── git diff HEAD ──┘──── git diff ────────┘
```

The index is the snapshot you are *building toward* the next commit. `git add` copies a file's current content into the object database as a blob and records the blob's SHA in the index. `git commit` turns the index into a tree object, wraps it in a commit, and advances the branch pointer. The working tree is never committed directly.

This intermediate layer is Git's most powerful feature: you can build up a commit piece by piece, staging individual hunks, without touching anything else.

---

## Seeing the Index in Action

```bash
# Stage a file
$ echo "hello" > greeting.txt
$ git add greeting.txt

# Inspect the index
$ git ls-files --stage
100644 ce013625030ba8dba906f756967f9e9ca394464a 0	greeting.txt
#      ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^    ^^^^^^^^
#      blob SHA of "hello\n"               stage      path
```

The blob SHA `ce013625030ba8dba906f756967f9e9ca394464a` is the same in every Git repository on Earth that has ever staged the string `"hello\n"`. You can verify:

```bash
$ echo "hello" | git hash-object --stdin
ce013625030ba8dba906f756967f9e9ca394464a
```

An empty index produces the well-known empty tree:

```bash
$ git write-tree           # from an empty index
4b825dc642cb6eb9a060e54bf8d69288fbee4904
```

---

## The DIRC Binary Format

The index is stored at `.git/index` as a binary file. Understanding the layout helps when debugging corruption or building compatible tools.

### High-level structure

```
┌──────────────────────────────────────────────────────────┐
│  4 bytes  "DIRC" (magic signature)                       │
│  4 bytes  version (big-endian uint32, value = 2)         │
│  4 bytes  entry count (big-endian uint32)                │
├──────────────────────────────────────────────────────────┤
│  Entry 0  (variable length, multiple of 8 bytes)         │
│  Entry 1                                                 │
│  ...                                                     │
├──────────────────────────────────────────────────────────┤
│  20 bytes  SHA-1 checksum of everything above            │
└──────────────────────────────────────────────────────────┘
```

The 4-byte magic `DIRC` stands for "directory cache"—an early Git name for the index.

### Entry layout

Each entry stores the cached `stat(2)` metadata alongside the blob SHA and file path:

```
Offset   Size   Field
  0        4    ctime seconds         ─┐
  4        4    ctime nanoseconds      │ file metadata
  8        4    mtime seconds          │ for fast
 12        4    mtime nanoseconds      │ change
 16        4    device id             │ detection
 20        4    inode number          │
 24        4    file mode             │
 28        4    uid                    │
 32        4    gid                   │
 36        4    file size            ─┘
 40       20    SHA-1 (binary, 20 bytes)
 60        2    flags (uint16)
 62        N    path (UTF-8, NUL-terminated)
 62+N      P    NUL padding (so total entry size is multiple of 8)
```

All multi-byte integers are big-endian.

### The flags field

The 16-bit flags word packs three pieces of information:

```
Bit 15    assume-valid flag (skip this entry in status checks)
Bits 14   extended flag (set = version 3 extended flags follow)
Bits 12-13  merge stage  (0 = normal, 1-3 = conflict stages)
Bits 0-11   name length  (min(path_length, 0xFFF))
```

The stage bits are what make three-way merge conflict tracking possible: a single conflicted file appears in the index three times, each with a different stage number.

### 8-byte padding

Each entry is padded with NUL bytes so that the entry occupies a whole multiple of 8 bytes. The NUL path terminator counts toward the total. If the path is already aligned the NUL terminator alone is sufficient; no extra padding bytes are added.

```
Total bytes = 62 (fixed fields) + len(path_utf8) + 1 (NUL)
Pad to next multiple of 8 if not already aligned.
```

### SHA-1 trailer

The final 20 bytes of the file are the SHA-1 digest of all preceding bytes. Git verifies this checksum on every read. A mismatch aborts with a "corrupted index" error.

---

## Entries Keyed by (path, stage)

For normal files the stage is always 0. During a merge conflict the index can contain up to three entries for the same path:

| Stage | Meaning |
|-------|---------|
| 0 | Normal (no conflict) |
| 1 | Common ancestor (merge base) |
| 2 | "Ours" (current branch version) |
| 3 | "Theirs" (incoming branch version) |

```bash
$ git ls-files --stage conflicted.txt
100644 aaa...  1	conflicted.txt   ← base
100644 bbb...  2	conflicted.txt   ← ours
100644 ccc...  3	conflicted.txt   ← theirs

$ git status
both modified: conflicted.txt
```

Stage-0 entries are absent while conflicts exist; the file is "unresolved". Writing a stage-0 entry (via `git add` after editing) resolves the conflict.

---

## Stat Caching: How Status Stays Fast

Git avoids re-hashing every file on every `git status` call by caching `stat(2)` results in the index. The check sequence is:

```
For each index entry:
  1. stat() the working-tree file
  2. Compare size, mtime, inode, ctime, and mode
  3. If all match → "probably unchanged" (skip SHA computation)
  4. If any differ → hash the file and compare SHAs
```

This is why `git status` is nearly instant on large repos: the expensive SHA computation is only triggered when the filesystem says something changed.

---

## Operations: read_tree, write_tree, get_status

Three functions in `gitpy/index/operations.py` are the workhorse bridge between the index and the object database.

### write_tree: index → commit tree

`write_tree` converts the current index into a tree object and returns the root SHA. If the index is empty, it writes the empty tree:

```bash
$ git write-tree
4b825dc642cb6eb9a060e54bf8d69288fbee4904   ← always the same empty-tree SHA
```

The function recurses through the path hierarchy, grouping entries by directory prefix to build nested tree objects bottom-up.

### read_tree: tree → index

`read_tree` is the inverse: it populates the index from an existing tree object. This is what `git checkout` uses internally before writing files to disk.

```bash
$ git read-tree HEAD^{tree}
# Populates index from the HEAD commit's tree
```

Entries produced by `read_tree` have all stat fields set to zero because there is no working-tree file to stat yet.

### get_status: three-way comparison

`get_status` computes `git status` output by comparing three sources:

1. **HEAD tree**: what the last commit recorded
2. **Index**: what is staged
3. **Working tree**: what is on disk

For each path it returns a `StatusEntry` with two `FileStatus` values:

| `index_status` | Meaning |
|----------------|---------|
| `ADDED` | staged but not in HEAD |
| `MODIFIED` | staged with different SHA than HEAD |
| `DELETED` | removed from index but in HEAD |
| `UNMODIFIED` | same as HEAD |

| `worktree_status` | Meaning |
|-------------------|---------|
| `MODIFIED` | working-tree file differs from index |
| `DELETED` | file missing from working tree |
| `UNTRACKED` | file in working tree, not in index |
| `UNMODIFIED` | working tree matches index |

```bash
$ git status
Changes to be committed:      ← index_status != UNMODIFIED
  modified:  README.md

Changes not staged for commit: ← worktree_status != UNMODIFIED
  modified:  src/main.py

Untracked files:              ← UNTRACKED
  scratch.py
```

---

## Well-Known SHA Values

These hash values are identical in every Git installation:

| Content | SHA-1 |
|---------|-------|
| Empty blob (empty file) | `e69de29bb2d1d6434b8b29ae775ad8c2e48c5391` |
| Empty tree (empty index → write-tree) | `4b825dc642cb6eb9a060e54bf8d69288fbee4904` |
| Blob for `"hello\n"` | `ce013625030ba8dba906f756967f9e9ca394464a` |

You can verify locally:

```bash
$ git hash-object -t blob /dev/null
e69de29bb2d1d6434b8b29ae775ad8c2e48c5391

$ git hash-object -t tree /dev/null
4b825dc642cb6eb9a060e54bf8d69288fbee4904

$ printf 'hello\n' | git hash-object --stdin
ce013625030ba8dba906f756967f9e9ca394464a
```

---

## Implementation in gitpy

The staging area lives in `gitpy/index/`:

```
gitpy/index/
├── __init__.py
├── entry.py        # IndexEntry dataclass
├── index.py        # Index, IndexFile
└── operations.py   # read_tree, write_tree, get_status, conflict helpers
```

### IndexEntry

`IndexEntry` is a `@dataclass(slots=True)` holding every field from the binary format, plus computed properties:

```python
from gitpy.index.entry import IndexEntry

entry = IndexEntry.from_path(
    path="src/main.py",
    sha="ce013625030ba8dba906f756967f9e9ca394464a",
    worktree=Path("/my/repo"),
    stage=0,
)

entry.stage           # 0
entry.is_executable   # False (mode 0o100644)
entry.is_symlink      # False
entry.matches_stat(st)  # fast-path change detection
```

`from_path()` uses nanosecond timestamps (`st_ctime_ns`, `st_mtime_ns`) directly to avoid floating-point precision loss from dividing by `1e9`.

### Index

`Index` stores entries in a `dict[tuple[str, int], IndexEntry]` keyed by `(path, stage)`. Iteration yields entries sorted by `(path, stage)`, which is the canonical Git wire order.

```python
from gitpy.index.index import Index

idx = Index()
idx.add(entry)
entry = idx.get("src/main.py", stage=0)
idx.remove("src/main.py")          # removes all stages
idx.remove("src/main.py", stage=2) # removes only stage 2
len(idx)                            # number of entries
```

Serialisation produces a byte string with the DIRC header, all entries (padded to multiples of 8), and the 20-byte SHA-1 trailer. Parsing verifies the checksum before reading any entries.

### IndexFile

`IndexFile` manages the `.git/index` file with atomic write semantics using an exclusive-create lock file (`.git/index.lock`):

```python
from gitpy.index.index import IndexFile

idx_file = IndexFile(Path(".git"))
idx = idx_file.read()    # returns empty Index if file absent
# ... mutate idx ...
idx_file.write(idx)      # atomic rename over .git/index
```

### Operations

```python
from gitpy.index.operations import (
    read_tree,
    write_tree,
    get_status,
    FileStatus,
    StatusEntry,
    has_conflicts,
    get_conflicts,
    add_conflict,
    resolve_conflict,
)

# Populate index from a tree SHA
read_tree(index, tree_sha, db)

# Convert index to a tree and return root SHA
root_sha = write_tree(index, db)

# Three-way status
entries = get_status(index, head_tree_sha, worktree, db)
for e in entries:
    print(e.path, e.index_status, e.worktree_status)

# Conflict helpers
if has_conflicts(index):
    for path, stages in get_conflicts(index).items():
        print(path, [s.stage for s in stages])
```

---

## Key Takeaways

1. **The index is a snapshot cache**: it holds the staged version of every file, plus enough `stat(2)` metadata to detect changes quickly.
2. **Binary DIRC format**: 4-byte magic, big-endian header, entries padded to 8-byte multiples, SHA-1 trailer.
3. **Stage bits enable merge conflicts**: the same path appears three times (stages 1-3) during a conflict; stage 0 is normal.
4. **write_tree of an empty index is always** `4b825dc642cb6eb9a060e54bf8d69288fbee4904`.
5. **get_status does a three-way comparison**: HEAD tree vs index (staged changes), index vs working tree (unstaged changes).

## What's Next?

- **[References](references.md)**: How HEAD, branches, and tags point into the commit graph.
- **[Diff](diff.md)**: How gitpy computes line-level differences between blobs using the Myers algorithm.
- **[Object Model](object_model.md)**: The blob and tree objects that the index refers to.
- **[Object Storage](object_storage.md)**: How those objects are compressed and stored on disk.
