# Understanding Git's Object Model

This document explains how Git stores data internally. If you've ever wondered what happens when you run `git add` or `git commit`, this guide will demystify Git's elegant storage system.

## The Big Picture: Git is a Content-Addressable Filesystem

Before diving into details, let's understand Git's fundamental insight: **Git is not really a version control system at its core—it's a content-addressable filesystem with a VCS built on top.**

What does "content-addressable" mean? In a traditional filesystem, you access files by their path: `/home/user/project/README.md`. In Git's object store, you access data by its *content*. Specifically, Git computes a SHA-1 hash of the content, and that hash becomes the "address" of the data.

This has profound implications:

1. **Automatic deduplication**: If two files have identical content, they're stored once
2. **Integrity verification**: If any bit changes, the hash changes, so corruption is detectable
3. **Immutability**: You can't modify an object without changing its address

---

## Seeing Git Objects in the Real World

Before we dive into theory, let's see Git's object model in action. Every Git repository has a hidden `.git` directory—this is where all the magic happens.

### Exploring the Object Database

```bash
# Look inside any Git repository
$ ls .git/objects/
4b/  8a/  ce/  e6/  info/  pack/

# Objects are stored by their first 2 hash characters
$ ls .git/objects/ce/
013625030ba8dba906f756967f9e9ca394464a
```

The file `.git/objects/ce/013625030ba8dba906f756967f9e9ca394464a` is a Git object. Its full hash is `ce013625030ba8dba906f756967f9e9ca394464a`—Git splits it into a 2-character directory and 38-character filename.

### Examining Objects with git cat-file

Git provides `cat-file` to inspect objects:

```bash
# What type is this object?
$ git cat-file -t ce013625030ba8dba906f756967f9e9ca394464a
blob

# What's the size?
$ git cat-file -s ce013625030ba8dba906f756967f9e9ca394464a
6

# Show the content
$ git cat-file -p ce013625030ba8dba906f756967f9e9ca394464a
hello
```

This object is a blob containing `hello\n` (6 bytes including the newline).

### Creating Objects with git hash-object

You can create objects directly:

```bash
# Hash content without storing
$ echo "hello" | git hash-object --stdin
ce013625030ba8dba906f756967f9e9ca394464a

# Hash and store in the database
$ echo "hello" | git hash-object --stdin -w
ce013625030ba8dba906f756967f9e9ca394464a
```

This is the "plumbing" command that `git add` uses internally.

---

## The Four Object Types

Git uses just four object types to represent an entire repository's history:

```
┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐
│   Blob   │  │   Tree   │  │  Commit  │  │   Tag    │
│  (file)  │  │  (dir)   │  │(snapshot)│  │ (label)  │
└──────────┘  └──────────┘  └──────────┘  └──────────┘
```

That's it. Four types to store unlimited history of any project. Let's explore each one.

---

## How Objects Are Identified: SHA-1 Hashing

Every Git object has an "Object ID" (OID)—a 40-character hexadecimal string like `ce013625030ba8dba906f756967f9e9ca394464a`. This is computed using SHA-1, but not just on the raw content. Git prepends a header:

```
<type> <size>\0<content>
```

For example, if you have a file containing `hello\n` (6 bytes), Git computes:

```
SHA-1("blob 6\0hello\n") = ce013625030ba8dba906f756967f9e9ca394464a
```

The `\0` is a null byte that separates the header from the content. This header is crucial—it means a blob and a commit with the same content will have different hashes (because the type differs).

### Well-Known Hashes

These hashes are the same in every Git repository in the world:

| Content | SHA-1 |
|---------|-------|
| Empty blob | `e69de29bb2d1d6434b8b29ae775ad8c2e48c5391` |
| Empty tree | `4b825dc642cb6eb9a060e54bf8d69288fbee4904` |
| `hello\n` | `ce013625030ba8dba906f756967f9e9ca394464a` |

You can verify these yourself:

```bash
$ echo -n "" | git hash-object --stdin
e69de29bb2d1d6434b8b29ae775ad8c2e48c5391

$ git hash-object -t tree /dev/null
4b825dc642cb6eb9a060e54bf8d69288fbee4904
```

---

## Blob: Storing File Contents

A blob represents file contents. That's it—just raw bytes. No filename, no permissions, no timestamps. Just content.

### Why Separate Content from Metadata?

This is a key insight in Git's design. Consider two files:

```
/src/utils.py    → contains "def helper(): pass\n"
/lib/utils.py    → contains "def helper(): pass\n"
```

In a traditional system, these are two separate files. In Git, they're **one blob** referenced from two different trees. This is automatic deduplication in action.

### Real-World Example: Large Binary Files

This is why Git struggles with large binary files. If you have a 100MB video and change one byte:
- Traditional systems: Store the diff (a few bytes)
- Git: Creates a new 100MB blob (entire new content)

This is also why Git LFS (Large File Storage) exists—it stores large files outside the normal object database.

### Examining a Blob

```bash
# Stage a file
$ echo "Hello, World!" > greeting.txt
$ git add greeting.txt

# Find the blob
$ git ls-files --stage
100644 8ab686eafeb1f44702738c8b0f24f2567c36da6d 0	greeting.txt

# Examine it
$ git cat-file -p 8ab686ea
Hello, World!
```

Notice: the blob contains just `Hello, World!`—no filename. The filename `greeting.txt` is stored in the tree (index), not the blob.

---

## Tree: Representing Directories

If blobs are files, how do we represent directories? That's what trees are for. A tree is a list of entries, where each entry maps a name to either a blob (file) or another tree (subdirectory).

### What's in a Tree Entry?

Each entry contains:

- **mode**: File permissions (`100644` for regular, `100755` for executable, `40000` for directory)
- **name**: The filename (just the name, not the full path)
- **sha**: The OID of the referenced object

### Examining a Real Tree

```bash
# Look at the tree for HEAD
$ git cat-file -p HEAD^{tree}
100644 blob 8ab686eafeb1f44702738c8b0f24f2567c36da6d	README.md
100755 blob 5c1f5e3b8c9e2a1d7f6e4b3c2a1d8e7f6c5b4a3d	run.sh
040000 tree 7a8b9c0d1e2f3a4b5c6d7e8f9a0b1c2d3e4f5a6b	src
```

This tree has three entries:
- `README.md` (regular file) → points to a blob
- `run.sh` (executable) → points to a blob
- `src` (directory) → points to another tree

### File Modes Explained

These cryptic numbers like `100644` come from Unix—but Git simplifies them dramatically.

#### Understanding the Mode Format

In Unix, file modes are 6-digit octal numbers:

```
100644
│││└┴┴─ Permission bits: 644 (rw-r--r--)
││└──── Special bits: 0 (no setuid/setgid/sticky)
└┴───── File type: 10 (regular file)
```

The **file type prefix** tells you what kind of entry it is:

| Prefix | Type | Full Mode |
|--------|------|-----------|
| `10` | Regular file | `100644`, `100755` |
| `12` | Symbolic link | `120000` |
| `04` | Directory | `040000` (stored as `40000`) |
| `16` | Gitlink (submodule) | `160000` |

The **permission bits** are standard Unix:

```
644 = rw-r--r--  (owner read+write, others read-only)
755 = rwxr-xr-x  (owner full access, others read+execute)
```

#### Git's Simplification

Here's the key insight: **Git only tracks a handful of modes**, not the full Unix permission space.

| Mode | Meaning | When Git Assigns It |
|------|---------|---------------------|
| `100644` | Regular file | Default for non-executable files |
| `100755` | Executable | File has the executable bit (+x) |
| `40000` | Directory | Tree entries pointing to other trees |
| `120000` | Symlink | File is a symbolic link |
| `160000` | Gitlink | Submodule reference |

**Why so limited?** Three reasons:

1. **Portability**: Windows doesn't have Unix permissions
2. **Simplicity**: Git tracks content, not fine-grained metadata
3. **Consistency**: Avoids "permission-only" changes cluttering history

#### How Git Decides the Mode

When you `git add` a file, Git uses this logic:

```
Is it a symbolic link?
  → Yes: 120000
  → No: Is the executable bit set?
        → Yes: 100755
        → No:  100644
```

Git ignores group permissions, setuid bits, and read/write distinctions. It only cares: *is it executable or not?*

#### Changing File Modes

```bash
# Make a script executable
$ chmod +x deploy.sh
$ git add deploy.sh

# Git notices the mode change
$ git diff --cached
diff --git a/deploy.sh b/deploy.sh
old mode 100644
new mode 100755
```

#### The Windows Problem

Windows has no executable bit, so Git uses a config setting:

```bash
# Check if Git tracks executable bit
$ git config core.fileMode
true   # Unix (default)
false  # Windows (default)

# Manually mark a file executable on Windows
$ git update-index --chmod=+x deploy.sh
```

#### Why 644 and 755?

These are sensible Unix defaults:

- **644** (`rw-r--r--`): Owner can edit, everyone can read. Safe for source files.
- **755** (`rwxr-xr-x`): Everyone can run it, but only owner can edit. Standard for scripts.

Note: Git stores `40000` not `040000`—leading zeros are omitted in mode strings.

### Tree Sorting: A Subtle Detail

Trees must be sorted, but with a twist: directories sort as if they had a trailing `/`.

Consider: `foo` (directory), `foo.txt` (file), `foobar` (file)

```
Sort keys:     "foo/"    "foo.txt"   "foobar"
Sorted order:  foo.txt   foo         foobar
```

Why does this matter? Git uses binary search on trees. Wrong ordering = corrupt repository.

### Nested Trees: How Paths Work

Git doesn't store paths like `/src/lib/utils.py`. Instead:

```
Root Tree
├── src (tree)
│   └── lib (tree)
│       └── utils.py (blob)
```

To find `/src/lib/utils.py`, Git:
1. Looks up `src` in the root tree → gets another tree
2. Looks up `lib` in that tree → gets another tree
3. Looks up `utils.py` in that tree → gets the blob

This is why Git is fast at switching branches but slow at `git log -- path/to/file` (must traverse all trees).

---

## Commit: Capturing Snapshots

A commit ties everything together. It represents a complete snapshot of your project at a point in time, plus metadata.

### Anatomy of a Commit

```bash
$ git cat-file -p HEAD
tree 7a8b9c0d1e2f3a4b5c6d7e8f9a0b1c2d3e4f5a6b
parent 1a2b3c4d5e6f7a8b9c0d1e2f3a4b5c6d7e8f9a0b
author Alice <alice@example.com> 1699900000 -0700
committer Bob <bob@example.com> 1699900100 +0000

Fix critical bug in authentication

This commit resolves the login issue reported in #123.
Users can now authenticate properly.
```

### Breaking Down the Fields

**tree**: Points to the root tree—the complete state of all files at this commit.

**parent**: Points to the previous commit(s). This creates the history chain.
- Root commit: No parent line
- Regular commit: One parent
- Merge commit: Multiple parents

**author vs committer**: These can differ!
- **Author**: Who wrote the original change
- **Committer**: Who added it to the repository

Example: Alice writes a patch, emails it to Bob, Bob applies it. Alice is author, Bob is committer.

**Identity format**: `Name <email> timestamp timezone`
- Timestamp: Unix epoch (seconds since 1970-01-01)
- Timezone: Offset from UTC (e.g., `-0700` is 7 hours behind)

**message**: Everything after the blank line.

### The Commit Graph

Commits form a directed acyclic graph (DAG):

```
         ┌─────────┐
         │ Commit  │  ← Root (no parents)
         │  "Init" │
         └────┬────┘
              │
         ┌────┴────┐
         │ Commit  │  ← Linear history
         │ "Add X" │
         └────┬────┘
              │
    ┌─────────┴─────────┐
    │                   │
┌───┴───┐          ┌────┴────┐
│ "Fix" │          │"Feature"│  ← Branches diverge
└───┬───┘          └────┬────┘
    │                   │
    └─────────┬─────────┘
              │
         ┌────┴────┐
         │ "Merge" │  ← Merge (two parents)
         └─────────┘
```

### Why Commits Are Immutable

If you change anything in a commit—the message, the author, a single file—the hash changes. That new hash means a new commit.

This is why `git commit --amend` creates a new commit (new hash) rather than modifying the old one. The old commit still exists until garbage collected.

### Real-World: How git log Works

When you run `git log`:

1. Git reads HEAD → gets a commit hash
2. Reads that commit → displays it
3. Follows the parent pointer → gets another commit
4. Repeat until no more parents

For `git log --all`, it starts from all refs (branches, tags) and traverses the entire graph.

---

## Tag: Named References with Metadata

There are two kinds of tags:

1. **Lightweight tags**: Just a name → commit mapping (like a branch that doesn't move)
2. **Annotated tags**: Actual objects with metadata

### Annotated Tag Structure

```bash
$ git cat-file -p v1.0.0
object 1a2b3c4d5e6f7a8b9c0d1e2f3a4b5c6d7e8f9a0b
type commit
tag v1.0.0
tagger Alice <alice@example.com> 1699900000 -0700

Version 1.0.0 - First stable release

This release includes:
- Feature A
- Feature B
- Bug fixes
```

### When to Use Each?

**Lightweight tags** are quick bookmarks:
```bash
$ git tag temp-marker  # Just creates refs/tags/temp-marker → SHA
```

**Annotated tags** are for releases:
```bash
$ git tag -a v1.0.0 -m "Version 1.0.0"  # Creates a tag object
```

Annotated tags record *who* tagged *when* and *why*—important for releases.

### Tags Can Point to Anything

Though tags usually point to commits, they can point to any object:

```bash
# Tag a specific file version (blob)
$ git tag important-config abc123

# Tag a directory state (tree)
$ git tag baseline-structure def456
```

---

## How Git Commands Use Objects

Now let's see how common Git operations translate to object operations.

### git add

1. Reads file content
2. Computes blob hash
3. If blob doesn't exist, creates it in `.git/objects/`
4. Updates the index (staging area) with the file → blob mapping

```bash
$ echo "new content" > file.txt
$ git add file.txt
# Creates: .git/objects/ab/cd1234...  (the blob)
# Updates: .git/index (file.txt → abcd1234)
```

### git commit

1. Writes a tree object from the current index
2. Creates a commit object pointing to that tree
3. Updates HEAD (and current branch) to the new commit

```bash
$ git commit -m "Add file"
# Creates: .git/objects/12/34abcd...  (tree from index)
# Creates: .git/objects/56/78efgh...  (commit)
# Updates: .git/refs/heads/main → 5678efgh
```

### git checkout

1. Reads the commit's tree
2. Recursively reads all trees and blobs
3. Writes blob contents to working directory
4. Updates index to match

```bash
$ git checkout feature-branch
# Reads: commit → tree → blobs
# Writes: all files to working directory
```

### git diff

1. For staged changes: compares index trees
2. For unstaged: compares working directory to index
3. For commits: compares their trees recursively

Git doesn't store diffs—it computes them on-demand by comparing blob contents.

### git merge

1. Finds the common ancestor (merge base)
2. Computes three-way diff (base, ours, theirs)
3. Creates new blobs for merged files
4. Creates a new tree
5. Creates a merge commit with two parents

```bash
$ git merge feature
# If successful:
# Creates: new blobs (merged content)
# Creates: new tree
# Creates: commit with parents [HEAD, feature]
```

### git clone

1. Downloads all objects (usually as a packfile)
2. Expands packfile into `.git/objects/`
3. Creates refs (branches, tags) pointing to objects
4. Checks out HEAD

---

## Object Storage on Disk

### Loose Objects

Individual objects are stored "loose" as zlib-compressed files:

```
.git/objects/ce/013625030ba8dba906f756967f9e9ca394464a
             ^^
             First 2 chars of hash (directory name)
```

The file contains: `zlib_compress(header + content)`

### Packfiles

For efficiency, Git periodically packs loose objects:

```
.git/objects/pack/
├── pack-abc123.idx   # Index (hash → offset mapping)
└── pack-abc123.pack  # Packed objects (delta-compressed)
```

Packfiles use delta compression—storing differences between similar objects. This is how Git achieves small repository sizes despite storing full snapshots.

### When Packing Happens

- `git gc` (garbage collection)
- `git push` (sends packfile)
- `git clone` (receives packfile)
- Automatically when loose objects exceed a threshold

---

## The Object Graph: Putting It Together

Here's how all objects connect in a real repository:

```
                  ┌───────────┐
                  │    Tag    │
                  │  "v1.0"   │
                  └─────┬─────┘
                        │ points to
                        ▼
                  ┌───────────┐
                  │  Commit   │
    ┌─────────────│ "Release" │
    │ parent      └─────┬─────┘
    │                   │ tree
    ▼                   ▼
┌───────────┐     ┌───────────┐
│  Commit   │     │   Tree    │
│ "Add docs"│     │  (root)   │
└───────────┘     └─────┬─────┘
                        │
         ┌──────────────┼──────────────┐
         │              │              │
         ▼              ▼              ▼
   ┌──────────┐   ┌──────────┐   ┌──────────┐
   │   Blob   │   │   Blob   │   │   Tree   │
   │ README   │   │ main.py  │   │   src/   │
   └──────────┘   └──────────┘   └────┬─────┘
                                      │
                                      ▼
                                ┌──────────┐
                                │   Blob   │
                                │ utils.py │
                                └──────────┘
```

Key observations:

1. **Tags → Commits**: Named release points
2. **Commits → Commits**: History chain via parents
3. **Commits → Trees**: Snapshots of directory state
4. **Trees → Trees/Blobs**: Directory structure
5. **Blobs**: Leaf nodes containing file data

---

## Key Insights

### Snapshots, Not Diffs

Unlike older VCS (CVS, SVN), Git stores complete snapshots. Each commit has a tree representing *all* files, not just changes.

Why? It makes checkouts fast (don't need to replay diffs) and enables efficient branching (branches are just pointers).

### Everything is Reachable from Commits

If you have a commit hash, you can reach every file in that version of the project. This is why commit hashes are so important—they're the entry point to complete snapshots.

### Unreachable Objects Get Garbage Collected

Objects not reachable from any ref (branch, tag) will eventually be deleted by `git gc`. This is how Git reclaims space from amended commits, rebases, etc.

### Immutability Enables Sharing

Because objects never change, Git can share them freely:
- Between branches (same blob in multiple trees)
- Between commits (unchanged files keep same blob)
- Between repositories (same content = same hash)

---

## What's Next?

The object model is the foundation. The next layers build on top:

- **Object Storage**: How objects are compressed and stored on disk
- **References**: How branches, tags, and HEAD point to objects
- **Index**: The staging area between working directory and repository
- **Commands**: The porcelain commands that orchestrate everything

Every Git operation ultimately reduces to creating, reading, or referencing these four simple object types. Understanding this model unlocks a deep understanding of how Git really works.
