# Understanding Git References

This document explains how Git names commits. If you've ever wondered how branch names, tags, and HEAD actually work under the hood, and how Git translates `HEAD~2` into a real SHA, this guide makes it concrete.

## The Big Picture: Names Over Hashes

Git's object database is entirely hash-addressed. Every commit, tree, blob, and tag has a 40-character SHA-1 like `f1cd9ac...`. References are the human-readable layer on top: they are files that contain a SHA (or point to another file). That's it. No magic.

```
.git/
├── HEAD                    ← current branch pointer
├── refs/
│   ├── heads/
│   │   ├── main            ← branch "main" → commit SHA
│   │   └── feature-x      ← branch "feature-x" → commit SHA
│   └── tags/
│       ├── v1.0            ← lightweight tag → commit SHA
│       └── v2.0            ← annotated tag → tag-object SHA
└── packed-refs             ← packed form of the above
```

A branch is just a file in `refs/heads/` whose content is a 40-character SHA. When you commit, Git writes a new SHA to that file. That is the entirety of what a branch "is".

---

## Refs as Pointers

### Loose refs

Each loose ref is a text file containing one SHA followed by a newline:

```bash
$ cat .git/refs/heads/main
f1cd9ac3b8965903ad578bd8b2b6545bc50023e1

$ git rev-parse main
f1cd9ac3b8965903ad578bd8b2b6545bc50023e1
```

Creating a branch is literally creating a file:

```bash
$ git branch new-feature
# Creates .git/refs/heads/new-feature containing current HEAD SHA
```

### packed-refs

Repositories with many refs accumulate thousands of tiny files. Git packs them into a single flat file to reduce filesystem pressure:

```
# pack-refs with: peeled fully-peeled sorted
abc123... refs/heads/main
def456... refs/heads/old-branch
789abc... refs/tags/v1.0
```

Loose refs always take priority over packed refs. When you write a new branch, it goes loose again; `git pack-refs` re-consolidates loose refs into the packed file.

```bash
$ git pack-refs --all
# Moves all loose refs into .git/packed-refs, removes loose files
```

---

## HEAD: Where You Are

HEAD is the one ref that does not live in `refs/`—it lives at `.git/HEAD`. It answers the question "which commit am I on right now?"

### Attached HEAD

In normal operation, HEAD points to a branch (a symbolic ref):

```
ref: refs/heads/main
```

When you commit, Git writes a new SHA to `refs/heads/main`. HEAD itself does not change—it still says `ref: refs/heads/main`. The branch moved; HEAD just followed it.

```bash
$ cat .git/HEAD
ref: refs/heads/main

$ git branch
* main
  feature-x
```

### Detached HEAD

When you check out a commit directly (not a branch), HEAD contains a bare SHA:

```
f1cd9ac3b8965903ad578bd8b2b6545bc50023e1
```

This is "detached HEAD" state. Commits you make here are not tracked by any branch. If you switch away without creating a branch, those commits become unreachable.

```bash
$ git checkout f1cd9ac
You are in 'detached HEAD' state...

$ cat .git/HEAD
f1cd9ac3b8965903ad578bd8b2b6545bc50023e1
```

### Resolution chain

To turn HEAD into a concrete SHA, Git follows the chain:

```
HEAD  →  "ref: refs/heads/main"
                    ↓
         refs/heads/main  →  f1cd9ac...
                                ↓
                        (final SHA)
```

The chain can be longer if one symbolic ref points to another, but Git enforces a depth limit (default 10) to prevent infinite loops.

---

## Branches

A branch is simply a mutable pointer to a commit. It moves forward automatically on each new commit.

```bash
# Create a branch at HEAD
$ git branch my-feature

# Create at a specific commit
$ git branch my-feature abc123

# List branches
$ git branch
* main
  my-feature

# Delete a branch
$ git branch -d my-feature

# Rename
$ git branch -m old-name new-name
```

The full reference name is `refs/heads/<short-name>`. Git strips the prefix when displaying branch names to you.

### Branch naming rules

Git enforces several naming constraints. Among the rejected patterns:

- Names containing spaces, `~`, `^`, `:`, `?`, `*`, `[`, `\`
- Names starting with `-`
- Names containing `..`
- Names ending in `.lock`
- Names containing `@{`

---

## Tags

Tags come in two forms: lightweight and annotated.

### Lightweight tags

A lightweight tag is identical in structure to a branch: a file in `refs/tags/` containing a SHA. The only difference is semantic—tags are conventionally not moved.

```bash
$ git tag v1.0-rc1
# Creates .git/refs/tags/v1.0-rc1 → current HEAD SHA

$ cat .git/refs/tags/v1.0-rc1
f1cd9ac3b8965903ad578bd8b2b6545bc50023e1
```

### Annotated tags

Annotated tags introduce an extra layer: the ref points to a tag *object* in the object database, which in turn points to the tagged commit. The tag object records the tagger identity, timestamp, and message.

```bash
$ git tag -a v1.0 -m "First stable release"

# The tag ref points to a tag *object*, not a commit:
$ git cat-file -t $(cat .git/refs/tags/v1.0)
tag

$ git cat-file -p $(cat .git/refs/tags/v1.0)
object f1cd9ac3b8965903ad578bd8b2b6545bc50023e1
type commit
tag v1.0
tagger Alice <alice@example.com> 1699900000 +0000

First stable release
```

The distinction matters for release tooling: annotated tags have a creation date and a tagger separate from the commit author. Lightweight tags are just bookmarks; annotated tags are permanent records.

```
Lightweight:   refs/tags/v1.0  →  <commit SHA>

Annotated:     refs/tags/v2.0  →  <tag-object SHA>
                                        ↓
                               tag object: tagger, message
                                        ↓
                                  <commit SHA>
```

"Peeling" a tag means following the tag object to its underlying commit. `git rev-parse v2.0^{}` returns the commit SHA by peeling.

---

## The Reflog

Every time a ref changes, Git appends an entry to a log file at `.git/logs/<ref-name>`. This lets you recover commits even after a destructive operation like `git reset --hard`.

### Reflog format

Each line records: old SHA, new SHA, identity, and a short message:

```
0000000... f1cd9ac Alice <alice@example.com> 1699900000 +0000	commit: initial
f1cd9ac... 40a138c Alice <alice@example.com> 1699900100 +0000	commit: add feature
40a138c... 55efffa Alice <alice@example.com> 1699900200 +0000	reset: moving to HEAD~1
```

The special value `0000000000000000000000000000000000000000` (40 zeros, `ZERO_SHA`) marks the first entry for a newly created ref—the "old" value before the ref existed.

```bash
$ git reflog
55efffa HEAD@{0}: reset: moving to HEAD~1
40a138c HEAD@{1}: commit: add feature
f1cd9ac HEAD@{2}: commit: initial
```

The reflog is local to your clone. It is not transferred during `git push` or `git fetch`.

---

## Revision Syntax

Git provides a rich syntax for naming commits relative to refs. The most useful forms:

### Basic names

```bash
$ git show HEAD            # current commit
$ git show main            # tip of branch main
$ git show v1.0            # tag v1.0
$ git show abc1234         # abbreviated SHA (4+ chars)
```

### Ancestry operators

```
HEAD^        first parent of HEAD (equivalent to HEAD^1)
HEAD^2       second parent of HEAD (merge commits only)
HEAD^0       HEAD itself, dereferenced through any tag objects
HEAD~1       same as HEAD^
HEAD~3       three steps up the first-parent chain
             (equivalent to HEAD^^^)
```

```bash
$ git show HEAD^           # parent commit
$ git show HEAD~3          # great-grandparent
$ git show HEAD^2          # second parent of a merge commit
```

The difference between `^` and `~`:

```
      A
     / \
    B   C        (A is a merge of B and C)

A^1 = B     (first parent)
A^2 = C     (second parent)
A~1 = B     (first parent)
A~2 = B^1   (grandparent via first-parent chain only)
```

### Reflog references

```bash
$ git show HEAD@{1}        # previous value of HEAD
$ git show HEAD@{3}        # HEAD three moves ago
$ git show main@{2}        # main two moves ago
```

---

## Implementation in gitpy

The reference subsystem lives in `gitpy/refs/`:

```
gitpy/refs/
├── __init__.py
├── manager.py    # RefManager: read/write/resolve/list/pack
├── head.py       # HeadManager, Head, HeadState
├── branch.py     # BranchManager, Branch
├── tag.py        # TagManager, LightweightTag, AnnotatedTag
├── reflog.py     # Reflog, ReflogEntry, ZERO_SHA
└── revision.py   # RevisionParser
```

### RefManager

`RefManager` handles the low-level ref I/O, including packed-refs support. Loose refs take priority over packed refs on read. Writes use an exclusive lock file (`<ref>.lock`) renamed atomically over the final path, matching real Git's protocol.

```python
from gitpy.refs.manager import RefManager
from pathlib import Path

refs = RefManager(Path(".git"))

# Read raw value (SHA or "ref: <target>")
raw = refs.read("refs/heads/main")

# Resolve through symbolic refs to a final SHA
sha = refs.resolve("main")   # tries refs/heads/main, etc.

# Write a ref
refs.write("refs/heads/feature", "abc123...")

# List branches
for name, sha in refs.list_branches():
    print(name, sha)

# Pack all loose refs
refs.pack_refs()
```

`resolve()` tries five candidate prefixes in order (`""`, `"refs/"`, `"refs/tags/"`, `"refs/heads/"`, `"refs/remotes/"`) and follows symbolic refs recursively up to `max_depth` (default 10) before raising `ValueError` for detected loops.

### HeadManager / Head / HeadState

`HeadManager` reads and writes `.git/HEAD`. The `Head` dataclass holds the current state:

```python
from gitpy.refs.head import HeadManager, HeadState

head_mgr = HeadManager(Path(".git"))
head = head_mgr.read()

if head.state == HeadState.ATTACHED:
    print("on branch:", head.branch)   # e.g. "main"
elif head.state == HeadState.DETACHED:
    print("detached at:", head.sha)

# Attach to a branch
head_mgr.set_branch("main")

# Detach at a commit
head_mgr.set_detached("f1cd9ac3b8965903ad578bd8b2b6545bc50023e1")
```

### BranchManager / Branch

`BranchManager` delegates ref I/O to `RefManager` and HEAD mutations to `HeadManager`. The `Branch` dataclass stores the short name and SHA:

```python
from gitpy.refs.branch import BranchManager, Branch

branches = BranchManager(ref_manager=refs, head_manager=head_mgr)

b = branches.create("feature-x", sha="abc123...")
print(b.full_name)    # "refs/heads/feature-x"
print(b.short_sha)    # first 7 chars

branches.delete("old-feature")
branches.rename("old-name", "new-name")
current = branches.current()   # short name or None if detached
```

### TagManager / LightweightTag / AnnotatedTag

`TagManager` distinguishes tag types by inspecting the object type that the ref resolves to: a `tag` object means annotated; anything else means lightweight.

```python
from gitpy.refs.tag import TagManager, LightweightTag, AnnotatedTag

tags = TagManager(ref_manager=refs, object_db=db)

# Create tags
tags.create_lightweight("v1.0-rc", sha=commit_sha)
tags.create_annotated("v1.0", sha=commit_sha, message="Release", tagger=identity)

# Inspect
tag = tags.get("v1.0")
if isinstance(tag, AnnotatedTag):
    print(tag.tagger, tag.message)

# Peel to commit SHA (follows tag objects)
commit_sha = tags.peel("v1.0")
```

### Reflog / ReflogEntry

```python
from gitpy.refs.reflog import Reflog, ReflogEntry, ZERO_SHA

log = Reflog(Path(".git"))

# Append an entry (ZERO_SHA for a brand-new ref)
log.append("HEAD", ZERO_SHA, new_sha, identity, "commit: init")

# Read entries newest-first
entries = log.read("HEAD", limit=10)
for e in entries:
    print(e.old_sha[:7], "->", e.new_sha[:7], e.message)

# Get a specific index (0 = most recent)
prev = log.get("HEAD", 1)
```

### RevisionParser

`RevisionParser.parse()` accepts any revision expression and returns a 40-char SHA or `None`:

```python
from gitpy.refs.revision import RevisionParser

parser = RevisionParser(ref_manager=refs, object_db=db)

parser.parse("HEAD")         # current commit
parser.parse("HEAD^")        # first parent
parser.parse("HEAD~3")       # great-grandparent
parser.parse("HEAD^2")       # second parent of a merge
parser.parse("HEAD^0")       # peel through tag objects
parser.parse("HEAD@{1}")     # previous HEAD (integer index only)
parser.parse("abc1234")      # abbreviated SHA (4–39 chars)
```

Time-based reflog expressions like `HEAD@{yesterday}` are not yet implemented; only integer indices are supported.

---

## Key Takeaways

1. **Refs are files**: A branch is a text file containing a SHA. Nothing more.
2. **Loose before packed**: Git reads loose refs first; packed-refs is a fallback and an optimisation.
3. **HEAD is special**: It is the only widely-used symbolic ref, telling Git which branch you are on.
4. **Detached HEAD**: When HEAD holds a bare SHA instead of `ref: ...`, you are off any branch.
5. **Reflog is local**: It records every ref movement so you can recover lost commits, but it does not cross clone boundaries.
6. **Revision syntax**: `^` navigates parents; `~` walks the first-parent chain; `@{n}` reaches back through the reflog.

## What's Next?

- **[Index & Staging](index_staging.md)**: The binary `.git/index` file that sits between your working directory and the commit tree.
- **[Diff](diff.md)**: How gitpy computes the differences between trees and blobs using the Myers algorithm.
- **[Object Model](object_model.md)**: The four object types (blob, tree, commit, tag) that refs point into.
- **[Object Storage](object_storage.md)**: How those objects are stored on disk.
