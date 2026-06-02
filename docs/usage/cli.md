# gitpy CLI Reference

gitpy is a Python reimplementation of Git's core internals. Its command-line
interface mirrors real Git so you can use it as a learning tool alongside the
real thing.

## Installation

gitpy is managed with [uv](https://docs.astral.sh/uv/). After cloning the
repository and running `uv sync --group dev` you can invoke it with:

```sh
uv run gitpy <command> [options]
```

### Global options

| Flag | Description |
|------|-------------|
| `-v`, `--version` | Print the version number and exit |
| `--help` | Show help for any command |

---

## Porcelain Commands

Porcelain commands are the high-level, user-facing operations you use every day.

---

### init

Initialize a new Git repository.

```
gitpy init [DIRECTORY] [--bare]
```

| Argument / Flag | Description |
|-----------------|-------------|
| `DIRECTORY` | Directory to initialize (default: current directory) |
| `--bare` | Create a bare repository (no working tree) |

**Example:**

```sh
$ mkdir myproject && gitpy init myproject
Initialized empty Git repository in myproject/.git
```

---

### status

Show the working tree status — which files are staged, modified, or untracked.

```
gitpy status [-s]
```

| Flag | Description |
|------|-------------|
| `-s`, `--short` | Short (machine-readable) output format |

**Example:**

```sh
$ gitpy status
On branch main
Untracked files:
  hello.txt
```

---

### add

Stage file contents to the index (staging area).

```
gitpy add [PATHS]... [-A]
```

| Argument / Flag | Description |
|-----------------|-------------|
| `PATHS` | One or more files to stage |
| `-A`, `--all` | Stage all changes (new, modified, deleted) |

**Example:**

```sh
$ printf 'hello\n' > hello.txt
$ gitpy add hello.txt
```

---

### commit

Record staged changes as a new commit.

```
gitpy commit -m <message> [--amend]
```

| Flag | Description |
|------|-------------|
| `-m`, `--message` | Commit message (required) |
| `--amend` | Replace the most recent commit with a new one |

**Example:**

```sh
$ gitpy commit -m "Add hello.txt"
[main (root-commit) ce01362] Add hello.txt
```

---

### log

Show the commit history starting from a given revision.

```
gitpy log [REVISION] [--oneline] [-n N]
```

| Argument / Flag | Description |
|-----------------|-------------|
| `REVISION` | Starting commit or branch (default: `HEAD`) |
| `--oneline` | Compact single-line output per commit |
| `-n N` | Limit output to N commits |

**Example:**

```sh
$ gitpy log --oneline -n 3
a1b2c3d Add feature
4e5f6a7 Fix typo
8b9c0d1 Initial commit
```

---

### diff

Show changes between commits, or between the working tree and index.

```
gitpy diff [COMMITS]... [--staged]
```

| Argument / Flag | Description |
|-----------------|-------------|
| `COMMITS` | Zero, one, or two commit SHAs to compare |
| `--staged`, `--cached` | Compare the index against HEAD |

**Example:**

```sh
# Show unstaged changes
$ gitpy diff

# Show what is staged for the next commit
$ gitpy diff --staged
```

---

### branch

List, create, delete, or rename branches.

```
gitpy branch [NAME] [-d] [-m] [--old OLD] [--new NEW] [-f]
```

| Argument / Flag | Description |
|-----------------|-------------|
| `NAME` | Branch name to create or operate on |
| `-d`, `--delete` | Delete the named branch |
| `-m`, `--move` | Rename a branch (use with `--old` and `--new`) |
| `--old OLD` | Old branch name (used with `--move`) |
| `--new NEW` | New branch name (used with `--move`) |
| `-f`, `--force` | Force the operation |

**Examples:**

```sh
# List all branches
$ gitpy branch

# Create a new branch
$ gitpy branch feature-login

# Delete a branch
$ gitpy branch -d feature-login

# Rename a branch
$ gitpy branch -m --old old-name --new new-name
```

---

### checkout

Switch branches or restore working-tree files.

```
gitpy checkout [TARGET] [-b <new-branch>] [--path <path>]...
```

| Argument / Flag | Description |
|-----------------|-------------|
| `TARGET` | Branch name or commit to switch to |
| `-b NEW` | Create a new branch named `NEW` and switch to it |
| `--path PATH` | Restore the given path from the target; repeatable to restore multiple paths |

**Examples:**

```sh
# Switch to an existing branch
$ gitpy checkout main

# Create and switch to a new branch
$ gitpy checkout -b feature-login
```

---

## Plumbing Commands

Plumbing commands expose Git's low-level internals. They are composable
building blocks for scripting and for understanding how Git works internally.

---

### hash-object

Compute the SHA-1 hash of a file and optionally write it to the object store.

```
gitpy hash-object <path> [-t <type>] [-w]
```

| Argument / Flag | Description |
|-----------------|-------------|
| `path` | Path to the file to hash (required) |
| `-t`, `--type` | Object type to use as header (default: `blob`) |
| `-w`, `--write` | Write the object to the repository's object store |

**Example:**

```sh
$ printf 'hello\n' > hello.txt

# Hash without storing
$ gitpy hash-object hello.txt
ce013625030ba8dba906f756967f9e9ca394464a

# Hash and store
$ gitpy hash-object -w hello.txt
ce013625030ba8dba906f756967f9e9ca394464a
```

The hash `ce013625030ba8dba906f756967f9e9ca394464a` is the universal SHA-1 for
`hello\n` — you will get the same value from real Git.

---

### cat-file

Display the content, type, or size of an object in the repository.

```
gitpy cat-file <obj> [-t] [-s] [-p]
```

| Argument / Flag | Description |
|-----------------|-------------|
| `obj` | Object SHA-1 (or prefix) to inspect (required) |
| `-t` | Print the object type |
| `-s` | Print the object size in bytes |
| `-p` | Pretty-print the object content |

**Example:**

```sh
# After storing hello.txt with hash-object -w
$ gitpy cat-file -t ce013625030ba8dba906f756967f9e9ca394464a
blob

$ gitpy cat-file -s ce013625030ba8dba906f756967f9e9ca394464a
6

$ gitpy cat-file -p ce013625030ba8dba906f756967f9e9ca394464a
hello
```

The well-known reference SHA-1 values are:

| Content | SHA-1 |
|---------|-------|
| Empty blob | `e69de29bb2d1d6434b8b29ae775ad8c2e48c5391` |
| Empty tree | `4b825dc642cb6eb9a060e54bf8d69288fbee4904` |
| `hello\n` blob | `ce013625030ba8dba906f756967f9e9ca394464a` |

---

### ls-tree

List the contents of a tree object.

```
gitpy ls-tree <tree-ish> [-r]
```

| Argument / Flag | Description |
|-----------------|-------------|
| `tree-ish` | Tree SHA-1, branch, or `HEAD^{tree}` (required) |
| `-r` | Recurse into sub-trees |

**Example:**

```sh
$ gitpy write-tree
aaa96ced2d9a1c8e72c56b253a0e2fe78393feb7

$ gitpy ls-tree aaa96ced2d9a1c8e72c56b253a0e2fe78393feb7
100644 blob ce013625030ba8dba906f756967f9e9ca394464a    hello.txt
```

---

### write-tree

Create a tree object from the current index (staging area).

```
gitpy write-tree
```

No arguments. Writes every staged entry as a tree and prints the resulting
tree SHA-1.

**Example:**

```sh
$ gitpy add hello.txt
$ gitpy write-tree
aaa96ced2d9a1c8e72c56b253a0e2fe78393feb7
```

---

### commit-tree

Create a commit object directly from a tree SHA-1, bypassing the index.
Useful for scripting and for understanding what `gitpy commit` does internally.

```
gitpy commit-tree <tree> -m <message> [-p <parent>]
```

| Argument / Flag | Description |
|-----------------|-------------|
| `tree` | SHA-1 of the tree to commit (required) |
| `-m`, `--message` | Commit message (required) |
| `-p`, `--parent` | Parent commit SHA-1 (may be repeated for merges) |

**Example:**

```sh
$ TREE=$(gitpy write-tree)
$ gitpy commit-tree "$TREE" -m "Initial commit"
7f3d9e2a1b4c5d6e7f8a9b0c1d2e3f4a5b6c7d8e
```

---

### update-ref

Update or delete a reference (branch pointer).

```
gitpy update-ref <ref> [newvalue] [-d]
```

| Argument / Flag | Description |
|-----------------|-------------|
| `ref` | Fully-qualified reference name, e.g. `refs/heads/main` (required) |
| `newvalue` | New SHA-1 to point the reference at |
| `-d`, `--delete` | Delete the reference |

**Example:**

```sh
# Point a branch at a specific commit
$ COMMIT=$(gitpy commit-tree "$TREE" -m "Initial commit")
$ gitpy update-ref refs/heads/main "$COMMIT"

# Delete a reference
$ gitpy update-ref -d refs/heads/old-branch
```
