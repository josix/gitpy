# Phase 5-8: Commands & Advanced Features - Design Specification

> **Status**: Draft
> **Author**: Domain Expert
> **Last Updated**: 2026-01-05
> **Dependencies**: Phases 1-4

## Phase 5: Diff Engine

### 5.1 Overview

The diff engine compares content and produces human-readable output showing changes.

### 5.2 Myers Diff Algorithm

Git uses Eugene Myers' diff algorithm for optimal (shortest) edit sequences.

```python
# gitpy/diff/myers.py

from typing import List, Tuple, Optional
from dataclasses import dataclass
from enum import Enum

class EditType(Enum):
    EQUAL = "equal"
    INSERT = "insert"
    DELETE = "delete"

@dataclass
class Edit:
    """Single edit operation."""
    type: EditType
    old_start: int    # Line number in old (1-indexed, 0 if insert)
    old_count: int    # Number of lines in old
    new_start: int    # Line number in new (1-indexed, 0 if delete)
    new_count: int    # Number of lines in new
    old_lines: List[str]  # Lines from old file
    new_lines: List[str]  # Lines from new file

def myers_diff(old: List[str], new: List[str]) -> List[Edit]:
    """
    Compute shortest edit script using Myers algorithm.

    Args:
        old: Lines of old version
        new: Lines of new version

    Returns:
        List of Edit operations to transform old to new
    """
    n, m = len(old), len(new)

    # Handle trivial cases
    if n == 0:
        if m == 0:
            return []
        return [Edit(EditType.INSERT, 0, 0, 1, m, [], new)]
    if m == 0:
        return [Edit(EditType.DELETE, 1, n, 0, 0, old, [])]

    # Myers algorithm
    max_d = n + m
    v = {1: 0}
    trace = []

    for d in range(max_d + 1):
        trace.append(dict(v))

        for k in range(-d, d + 1, 2):
            # Decide whether to go down or right
            if k == -d or (k != d and v.get(k - 1, 0) < v.get(k + 1, 0)):
                x = v.get(k + 1, 0)
            else:
                x = v.get(k - 1, 0) + 1

            y = x - k

            # Follow diagonal (matching lines)
            while x < n and y < m and old[x] == new[y]:
                x += 1
                y += 1

            v[k] = x

            # Check if we reached the end
            if x >= n and y >= m:
                return _backtrack(trace, old, new)

    return []  # Should never reach here

def _backtrack(
    trace: List[dict],
    old: List[str],
    new: List[str]
) -> List[Edit]:
    """Backtrack through trace to build edit script."""
    n, m = len(old), len(new)
    x, y = n, m
    edits = []

    for d in range(len(trace) - 1, -1, -1):
        v = trace[d]
        k = x - y

        if k == -d or (k != d and v.get(k - 1, 0) < v.get(k + 1, 0)):
            prev_k = k + 1
        else:
            prev_k = k - 1

        prev_x = v.get(prev_k, 0)
        prev_y = prev_x - prev_k

        # Diagonal moves (equal lines)
        while x > prev_x and y > prev_y:
            x -= 1
            y -= 1
            edits.append(Edit(
                EditType.EQUAL, x + 1, 1, y + 1, 1,
                [old[x]], [new[y]]
            ))

        if d > 0:
            if x == prev_x:
                # Insert
                y -= 1
                edits.append(Edit(
                    EditType.INSERT, x, 0, y + 1, 1,
                    [], [new[y]]
                ))
            else:
                # Delete
                x -= 1
                edits.append(Edit(
                    EditType.DELETE, x + 1, 1, y, 0,
                    [old[x]], []
                ))

    edits.reverse()
    return _merge_edits(edits)

def _merge_edits(edits: List[Edit]) -> List[Edit]:
    """Merge consecutive edits of same type."""
    if not edits:
        return []

    merged = [edits[0]]
    for edit in edits[1:]:
        last = merged[-1]
        if last.type == edit.type:
            # Merge
            merged[-1] = Edit(
                type=last.type,
                old_start=last.old_start,
                old_count=last.old_count + edit.old_count,
                new_start=last.new_start,
                new_count=last.new_count + edit.new_count,
                old_lines=last.old_lines + edit.old_lines,
                new_lines=last.new_lines + edit.new_lines,
            )
        else:
            merged.append(edit)

    return merged
```

### 5.3 Unified Diff Format

```python
# gitpy/diff/unified.py

from typing import List, TextIO
import sys

def format_unified_diff(
    old_lines: List[str],
    new_lines: List[str],
    old_name: str = "a",
    new_name: str = "b",
    context: int = 3
) -> str:
    """
    Format diff as unified diff.

    Args:
        old_lines: Lines of old version
        new_lines: Lines of new version
        old_name: Name for old file
        new_name: Name for new file
        context: Lines of context around changes

    Returns:
        Unified diff string
    """
    edits = myers_diff(old_lines, new_lines)
    if not edits:
        return ""

    # Filter to just changes
    changes = [e for e in edits if e.type != EditType.EQUAL]
    if not changes:
        return ""

    output = []

    # Header
    output.append(f"--- {old_name}")
    output.append(f"+++ {new_name}")

    # Group changes into hunks
    hunks = _create_hunks(edits, context)

    for hunk in hunks:
        # Hunk header
        old_start = hunk['old_start']
        old_count = hunk['old_count']
        new_start = hunk['new_start']
        new_count = hunk['new_count']

        output.append(f"@@ -{old_start},{old_count} +{new_start},{new_count} @@")

        # Hunk content
        for line_type, line in hunk['lines']:
            if line_type == 'context':
                output.append(f" {line}")
            elif line_type == 'delete':
                output.append(f"-{line}")
            elif line_type == 'insert':
                output.append(f"+{line}")

    return "\n".join(output) + "\n"

def _create_hunks(edits: List[Edit], context: int) -> List[dict]:
    """Group edits into hunks with context."""
    hunks = []
    current_hunk = None

    old_pos = 1
    new_pos = 1

    for edit in edits:
        if edit.type == EditType.EQUAL:
            if current_hunk:
                # Add trailing context
                for i, line in enumerate(edit.old_lines[:context]):
                    current_hunk['lines'].append(('context', line))
                    current_hunk['old_count'] += 1
                    current_hunk['new_count'] += 1

                if len(edit.old_lines) > context * 2:
                    # Gap too large, close hunk
                    hunks.append(current_hunk)
                    current_hunk = None

            old_pos += edit.old_count
            new_pos += edit.new_count

        else:
            if current_hunk is None:
                # Start new hunk with leading context
                current_hunk = {
                    'old_start': max(1, old_pos - context),
                    'new_start': max(1, new_pos - context),
                    'old_count': 0,
                    'new_count': 0,
                    'lines': []
                }
                # Add leading context from previous equal block
                # (simplified - full impl would track previous edits)

            if edit.type == EditType.DELETE:
                for line in edit.old_lines:
                    current_hunk['lines'].append(('delete', line))
                    current_hunk['old_count'] += 1
                old_pos += edit.old_count

            elif edit.type == EditType.INSERT:
                for line in edit.new_lines:
                    current_hunk['lines'].append(('insert', line))
                    current_hunk['new_count'] += 1
                new_pos += edit.new_count

    if current_hunk:
        hunks.append(current_hunk)

    return hunks
```

### 5.4 Tree Diff

```python
# gitpy/diff/tree.py

from dataclasses import dataclass
from typing import List, Optional, Iterator
from enum import Enum

class DiffStatus(Enum):
    ADDED = "A"
    DELETED = "D"
    MODIFIED = "M"
    RENAMED = "R"
    COPIED = "C"
    TYPE_CHANGED = "T"

@dataclass
class DiffEntry:
    """Difference between two trees."""
    status: DiffStatus
    path: str
    old_sha: Optional[str]
    new_sha: Optional[str]
    old_mode: Optional[str]
    new_mode: Optional[str]
    old_path: Optional[str] = None  # For renames

def diff_trees(
    old_tree_sha: Optional[str],
    new_tree_sha: Optional[str],
    db: "ObjectDatabase"
) -> Iterator[DiffEntry]:
    """
    Compare two trees and yield differences.

    Args:
        old_tree_sha: SHA of old tree (None for empty)
        new_tree_sha: SHA of new tree (None for empty)
        db: Object database

    Yields:
        DiffEntry for each changed path
    """
    old_entries = {}
    new_entries = {}

    if old_tree_sha:
        old_entries = _flatten_tree(old_tree_sha, db, "")
    if new_tree_sha:
        new_entries = _flatten_tree(new_tree_sha, db, "")

    all_paths = set(old_entries.keys()) | set(new_entries.keys())

    for path in sorted(all_paths):
        old = old_entries.get(path)
        new = new_entries.get(path)

        if old and new:
            if old['sha'] != new['sha'] or old['mode'] != new['mode']:
                yield DiffEntry(
                    status=DiffStatus.MODIFIED,
                    path=path,
                    old_sha=old['sha'],
                    new_sha=new['sha'],
                    old_mode=old['mode'],
                    new_mode=new['mode'],
                )
        elif old:
            yield DiffEntry(
                status=DiffStatus.DELETED,
                path=path,
                old_sha=old['sha'],
                new_sha=None,
                old_mode=old['mode'],
                new_mode=None,
            )
        else:
            yield DiffEntry(
                status=DiffStatus.ADDED,
                path=path,
                old_sha=None,
                new_sha=new['sha'],
                old_mode=None,
                new_mode=new['mode'],
            )

def _flatten_tree(
    tree_sha: str,
    db: "ObjectDatabase",
    prefix: str
) -> dict:
    """Flatten tree to dict of path -> {sha, mode}."""
    result = {}
    tree = db.read_tree(tree_sha)

    for entry in tree.entries:
        path = f"{prefix}{entry.name}" if prefix else entry.name

        if entry.is_tree:
            result.update(_flatten_tree(entry.sha, db, f"{path}/"))
        else:
            result[path] = {'sha': entry.sha, 'mode': entry.mode}

    return result
```

---

## Phase 6: Plumbing Commands

### 6.1 Command Architecture

```python
# gitpy/commands/base.py

from abc import ABC, abstractmethod
from typing import List, Optional
import argparse

class Command(ABC):
    """Base class for git commands."""

    name: str
    help: str

    @abstractmethod
    def run(self, args: List[str], repo: "Repository") -> int:
        """
        Execute command.

        Args:
            args: Command arguments
            repo: Repository instance

        Returns:
            Exit code (0 = success)
        """
        pass

    def setup_parser(self, parser: argparse.ArgumentParser) -> None:
        """Configure argument parser."""
        pass
```

### 6.2 hash-object

```python
# gitpy/commands/plumbing/hash_object.py

class HashObjectCommand(Command):
    """
    Compute object ID and optionally create object.

    Usage:
        gitpy hash-object [-w] [-t <type>] [--stdin] <file>...

    Options:
        -w          Write object to database
        -t <type>   Object type (default: blob)
        --stdin     Read from stdin instead of file
    """

    name = "hash-object"
    help = "Compute object ID"

    def setup_parser(self, parser):
        parser.add_argument("-w", action="store_true", help="Write object")
        parser.add_argument("-t", default="blob", help="Object type")
        parser.add_argument("--stdin", action="store_true")
        parser.add_argument("files", nargs="*")

    def run(self, args, repo):
        if args.stdin:
            data = sys.stdin.buffer.read()
            sha = self._hash_data(data, args.t, args.w, repo)
            print(sha)
        else:
            for path in args.files:
                with open(path, "rb") as f:
                    data = f.read()
                sha = self._hash_data(data, args.t, args.w, repo)
                print(sha)
        return 0

    def _hash_data(self, data, type_name, write, repo):
        from gitpy.objects.blob import Blob
        blob = Blob(data=data)
        if write:
            return repo.objects.write(blob)
        return blob.oid
```

### 6.3 cat-file

```python
# gitpy/commands/plumbing/cat_file.py

class CatFileCommand(Command):
    """
    Display object contents, type, or size.

    Usage:
        gitpy cat-file <type> <object>
        gitpy cat-file -t <object>
        gitpy cat-file -s <object>
        gitpy cat-file -p <object>

    Options:
        -t    Show object type
        -s    Show object size
        -p    Pretty-print object
    """

    name = "cat-file"
    help = "Display object content"

    def setup_parser(self, parser):
        parser.add_argument("-t", action="store_true", help="Show type")
        parser.add_argument("-s", action="store_true", help="Show size")
        parser.add_argument("-p", action="store_true", help="Pretty-print")
        parser.add_argument("object", help="Object SHA")
        parser.add_argument("type", nargs="?", help="Expected type")

    def run(self, args, repo):
        sha = repo.refs.resolve(args.object)
        if not sha:
            print(f"fatal: Not a valid object name {args.object}", file=sys.stderr)
            return 1

        if args.t:
            print(repo.objects.get_type(sha))
        elif args.s:
            print(repo.objects.get_size(sha))
        elif args.p:
            self._pretty_print(sha, repo)
        else:
            obj = repo.objects.read(sha)
            if args.type and obj.type_name != args.type:
                print(f"fatal: expected {args.type}, got {obj.type_name}", file=sys.stderr)
                return 1
            sys.stdout.buffer.write(obj.serialize())

        return 0

    def _pretty_print(self, sha, repo):
        obj = repo.objects.read(sha)

        if obj.type_name == "blob":
            sys.stdout.buffer.write(obj.data)
        elif obj.type_name == "tree":
            for entry in obj.entries:
                type_name = "tree" if entry.is_tree else "blob"
                print(f"{entry.mode} {type_name} {entry.sha}\t{entry.name}")
        elif obj.type_name == "commit":
            print(obj.serialize().decode())
        elif obj.type_name == "tag":
            print(obj.serialize().decode())
```

### 6.4 ls-tree

```python
# gitpy/commands/plumbing/ls_tree.py

class LsTreeCommand(Command):
    """
    List tree contents.

    Usage:
        gitpy ls-tree [-r] [-d] [-t] <tree-ish>

    Options:
        -r    Recurse into subtrees
        -d    Show only directories
        -t    Show trees when recursing
    """

    name = "ls-tree"
    help = "List tree contents"

    def run(self, args, repo):
        sha = repo.refs.resolve(args.tree_ish)

        # If it's a commit, get its tree
        obj = repo.objects.read(sha)
        if obj.type_name == "commit":
            sha = obj.tree_sha

        self._list_tree(sha, repo, "", args.recursive, args.tree_only)
        return 0

    def _list_tree(self, sha, repo, prefix, recursive, tree_only):
        tree = repo.objects.read_tree(sha)

        for entry in tree.entries:
            path = f"{prefix}{entry.name}"
            type_name = "tree" if entry.is_tree else "blob"

            if not tree_only or entry.is_tree:
                print(f"{entry.mode} {type_name} {entry.sha}\t{path}")

            if recursive and entry.is_tree:
                self._list_tree(entry.sha, repo, f"{path}/", True, tree_only)
```

### 6.5 write-tree

```python
# gitpy/commands/plumbing/write_tree.py

class WriteTreeCommand(Command):
    """
    Create tree from index.

    Usage:
        gitpy write-tree [--prefix=<prefix>]
    """

    name = "write-tree"
    help = "Create tree from index"

    def run(self, args, repo):
        from gitpy.index.operations import write_tree

        index = repo.index.read()
        sha = write_tree(index, repo.objects)
        print(sha)
        return 0
```

### 6.6 commit-tree

```python
# gitpy/commands/plumbing/commit_tree.py

class CommitTreeCommand(Command):
    """
    Create commit object.

    Usage:
        gitpy commit-tree <tree> [-p <parent>]... [-m <message>]
    """

    name = "commit-tree"
    help = "Create commit object"

    def setup_parser(self, parser):
        parser.add_argument("tree", help="Tree SHA")
        parser.add_argument("-p", action="append", dest="parents", default=[])
        parser.add_argument("-m", dest="message", required=True)

    def run(self, args, repo):
        from gitpy.objects.commit import Commit, Identity

        # Get author/committer from config or environment
        author = Identity.now(
            name=os.environ.get("GIT_AUTHOR_NAME", "Unknown"),
            email=os.environ.get("GIT_AUTHOR_EMAIL", "unknown@example.com")
        )
        committer = Identity.now(
            name=os.environ.get("GIT_COMMITTER_NAME", author.name),
            email=os.environ.get("GIT_COMMITTER_EMAIL", author.email)
        )

        commit = Commit(
            tree_sha=args.tree,
            parent_shas=args.parents,
            author=author,
            committer=committer,
            message=args.message
        )

        sha = repo.objects.write(commit)
        print(sha)
        return 0
```

### 6.7 update-ref

```python
# gitpy/commands/plumbing/update_ref.py

class UpdateRefCommand(Command):
    """
    Update reference value.

    Usage:
        gitpy update-ref <ref> <newvalue> [<oldvalue>]
        gitpy update-ref -d <ref> [<oldvalue>]
    """

    name = "update-ref"
    help = "Update reference"

    def run(self, args, repo):
        if args.delete:
            repo.refs.delete(args.ref)
        else:
            repo.refs.write(args.ref, args.newvalue)
        return 0
```

---

## Phase 7: Porcelain Commands

### 7.1 init

```python
# gitpy/commands/porcelain/init.py

class InitCommand(Command):
    """
    Initialize a new repository.

    Usage:
        gitpy init [<directory>]
        gitpy init --bare [<directory>]
    """

    name = "init"
    help = "Create empty repository"

    def setup_parser(self, parser):
        parser.add_argument("directory", nargs="?", default=".")
        parser.add_argument("--bare", action="store_true")

    def run(self, args, repo=None):
        from gitpy.repository import Repository
        from pathlib import Path

        path = Path(args.directory)
        Repository.init(path, bare=args.bare)

        if args.bare:
            print(f"Initialized empty Git repository in {path.resolve()}")
        else:
            print(f"Initialized empty Git repository in {path.resolve()}/.git/")

        return 0
```

### 7.2 add

```python
# gitpy/commands/porcelain/add.py

class AddCommand(Command):
    """
    Stage files for commit.

    Usage:
        gitpy add <pathspec>...
        gitpy add -A
    """

    name = "add"
    help = "Add files to index"

    def setup_parser(self, parser):
        parser.add_argument("paths", nargs="*")
        parser.add_argument("-A", "--all", action="store_true")

    def run(self, args, repo):
        from gitpy.objects.blob import Blob
        from gitpy.index.entry import IndexEntry

        index = repo.index.read()

        if args.all:
            paths = list(repo.worktree.rglob("*"))
        else:
            paths = [repo.worktree / p for p in args.paths]

        for path in paths:
            if not path.is_file():
                continue
            if ".git" in path.parts:
                continue

            rel_path = str(path.relative_to(repo.worktree))

            # Create blob
            blob = Blob.from_file(str(path))
            sha = repo.objects.write(blob)

            # Create index entry
            entry = IndexEntry.from_path(rel_path, sha, repo.worktree)
            index.add(entry)

        repo.index.write(index)
        return 0
```

### 7.3 commit

```python
# gitpy/commands/porcelain/commit.py

class CommitCommand(Command):
    """
    Record changes to repository.

    Usage:
        gitpy commit -m <message>
        gitpy commit --amend
    """

    name = "commit"
    help = "Record changes"

    def setup_parser(self, parser):
        parser.add_argument("-m", dest="message", required=True)
        parser.add_argument("--amend", action="store_true")

    def run(self, args, repo):
        from gitpy.objects.commit import Commit, Identity
        from gitpy.index.operations import write_tree

        index = repo.index.read()

        # Check for changes
        if len(index) == 0:
            print("nothing to commit", file=sys.stderr)
            return 1

        # Create tree from index
        tree_sha = write_tree(index, repo.objects)

        # Get parent(s)
        parents = []
        try:
            head_sha = repo.head.resolve(repo.refs)
            parents.append(head_sha)
        except ValueError:
            pass  # Initial commit

        # Get author info
        author = Identity.now(
            name=repo.config.get("user.name", "Unknown"),
            email=repo.config.get("user.email", "unknown@example.com")
        )

        # Create commit
        commit = Commit(
            tree_sha=tree_sha,
            parent_shas=parents,
            author=author,
            committer=author,
            message=args.message
        )
        commit_sha = repo.objects.write(commit)

        # Update HEAD
        head = repo.head.read()
        if head.is_detached:
            repo.head.set_detached(commit_sha)
        else:
            repo.refs.write(head.target, commit_sha)

        # Update reflog
        repo.reflog.append(
            "HEAD",
            parents[0] if parents else "0" * 40,
            commit_sha,
            author,
            f"commit: {args.message.split(chr(10))[0]}"
        )

        print(f"[{head.branch or 'detached'}] {commit_sha[:7]} {args.message.split(chr(10))[0]}")
        return 0
```

### 7.4 status

```python
# gitpy/commands/porcelain/status.py

class StatusCommand(Command):
    """
    Show working tree status.

    Usage:
        gitpy status
        gitpy status -s
    """

    name = "status"
    help = "Show status"

    def setup_parser(self, parser):
        parser.add_argument("-s", "--short", action="store_true")

    def run(self, args, repo):
        from gitpy.index.operations import get_status, FileStatus

        # Get HEAD tree
        try:
            head_sha = repo.head.resolve(repo.refs)
            head_commit = repo.objects.read_commit(head_sha)
            head_tree = head_commit.tree_sha
        except ValueError:
            head_tree = None

        index = repo.index.read()
        status = get_status(index, head_tree, repo.worktree, repo.objects)

        if args.short:
            self._print_short(status)
        else:
            self._print_long(status, repo)

        return 0

    def _print_short(self, status):
        for entry in status:
            idx = entry.index_status.value[0].upper() if entry.index_status != FileStatus.UNMODIFIED else " "
            wt = entry.worktree_status.value[0].upper() if entry.worktree_status != FileStatus.UNMODIFIED else " "
            print(f"{idx}{wt} {entry.path}")

    def _print_long(self, status, repo):
        head = repo.head.read()
        print(f"On branch {head.branch or '(detached)'}")
        print()

        staged = [e for e in status if e.index_status != FileStatus.UNMODIFIED]
        unstaged = [e for e in status if e.worktree_status not in (FileStatus.UNMODIFIED, FileStatus.UNTRACKED)]
        untracked = [e for e in status if e.worktree_status == FileStatus.UNTRACKED]

        if staged:
            print("Changes to be committed:")
            for e in staged:
                print(f"  {e.index_status.value}: {e.path}")
            print()

        if unstaged:
            print("Changes not staged for commit:")
            for e in unstaged:
                print(f"  {e.worktree_status.value}: {e.path}")
            print()

        if untracked:
            print("Untracked files:")
            for e in untracked:
                print(f"  {e.path}")
            print()
```

### 7.5 log

```python
# gitpy/commands/porcelain/log.py

class LogCommand(Command):
    """
    Show commit history.

    Usage:
        gitpy log [<revision>]
        gitpy log --oneline
        gitpy log -n <count>
    """

    name = "log"
    help = "Show commit log"

    def setup_parser(self, parser):
        parser.add_argument("revision", nargs="?", default="HEAD")
        parser.add_argument("--oneline", action="store_true")
        parser.add_argument("-n", type=int, default=None)

    def run(self, args, repo):
        sha = repo.refs.resolve(args.revision)
        if not sha:
            print(f"fatal: unknown revision {args.revision}", file=sys.stderr)
            return 1

        count = 0
        while sha:
            if args.n and count >= args.n:
                break

            commit = repo.objects.read_commit(sha)

            if args.oneline:
                message = commit.message.split("\n")[0]
                print(f"{sha[:7]} {message}")
            else:
                self._print_commit(sha, commit)

            sha = commit.parent_shas[0] if commit.parent_shas else None
            count += 1

        return 0

    def _print_commit(self, sha, commit):
        from datetime import datetime

        print(f"commit {sha}")
        print(f"Author: {commit.author.name} <{commit.author.email}>")

        dt = datetime.fromtimestamp(commit.author.timestamp)
        print(f"Date:   {dt.strftime('%a %b %d %H:%M:%S %Y')} {commit.author.tz_offset}")
        print()
        for line in commit.message.split("\n"):
            print(f"    {line}")
        print()
```

### 7.6 diff

```python
# gitpy/commands/porcelain/diff.py

class DiffCommand(Command):
    """
    Show changes.

    Usage:
        gitpy diff                  # Working tree vs index
        gitpy diff --staged         # Index vs HEAD
        gitpy diff <commit>         # Working tree vs commit
        gitpy diff <c1> <c2>        # Commit vs commit
    """

    name = "diff"
    help = "Show changes"

    def setup_parser(self, parser):
        parser.add_argument("--staged", "--cached", action="store_true")
        parser.add_argument("commits", nargs="*")

    def run(self, args, repo):
        from gitpy.diff.tree import diff_trees
        from gitpy.diff.unified import format_unified_diff

        if args.staged:
            # Index vs HEAD
            head_sha = repo.head.resolve(repo.refs)
            head_commit = repo.objects.read_commit(head_sha)
            # Compare HEAD tree with tree from index
            index = repo.index.read()
            index_tree = write_tree(index, repo.objects)
            entries = diff_trees(head_commit.tree_sha, index_tree, repo.objects)
        elif len(args.commits) == 2:
            # Commit vs commit
            sha1 = repo.refs.resolve(args.commits[0])
            sha2 = repo.refs.resolve(args.commits[1])
            c1 = repo.objects.read_commit(sha1)
            c2 = repo.objects.read_commit(sha2)
            entries = diff_trees(c1.tree_sha, c2.tree_sha, repo.objects)
        else:
            # Working tree vs index (default)
            # Implementation: compare each index entry with working file
            pass

        for entry in entries:
            if entry.old_sha and entry.new_sha:
                old_blob = repo.objects.read_blob(entry.old_sha)
                new_blob = repo.objects.read_blob(entry.new_sha)
                old_lines = old_blob.data.decode().splitlines()
                new_lines = new_blob.data.decode().splitlines()
                diff = format_unified_diff(
                    old_lines, new_lines,
                    f"a/{entry.path}", f"b/{entry.path}"
                )
                print(diff)

        return 0
```

### 7.7 branch

```python
# gitpy/commands/porcelain/branch.py

class BranchCommand(Command):
    """
    List, create, or delete branches.

    Usage:
        gitpy branch              # List branches
        gitpy branch <name>       # Create branch
        gitpy branch -d <name>    # Delete branch
        gitpy branch -m <old> <new>  # Rename
    """

    name = "branch"
    help = "Manage branches"

    def run(self, args, repo):
        if args.delete:
            repo.branches.delete(args.name, force=args.force)
            print(f"Deleted branch {args.name}")
        elif args.move:
            repo.branches.rename(args.old, args.new, force=args.force)
            print(f"Renamed branch {args.old} to {args.new}")
        elif args.name:
            head_sha = repo.head.resolve(repo.refs)
            repo.branches.create(args.name, head_sha)
            print(f"Created branch {args.name}")
        else:
            current = repo.branches.current()
            for branch in repo.branches.list():
                prefix = "* " if branch.name == current else "  "
                print(f"{prefix}{branch.name}")

        return 0
```

### 7.8 checkout

```python
# gitpy/commands/porcelain/checkout.py

class CheckoutCommand(Command):
    """
    Switch branches or restore files.

    Usage:
        gitpy checkout <branch>
        gitpy checkout -b <new-branch>
        gitpy checkout -- <file>...
    """

    name = "checkout"
    help = "Switch branches or restore files"

    def run(self, args, repo):
        if args.new_branch:
            # Create and switch
            head_sha = repo.head.resolve(repo.refs)
            repo.branches.create(args.new_branch, head_sha)
            repo.head.set_branch(args.new_branch)
            print(f"Switched to a new branch '{args.new_branch}'")
        elif args.paths:
            # Restore files from index
            index = repo.index.read()
            for path in args.paths:
                entry = index.get(path)
                if entry:
                    blob = repo.objects.read_blob(entry.sha)
                    (repo.worktree / path).write_bytes(blob.data)
        else:
            # Switch branch
            branch = repo.branches.get(args.branch)
            if branch:
                self._checkout_tree(branch.sha, repo)
                repo.head.set_branch(args.branch)
                print(f"Switched to branch '{args.branch}'")
            else:
                # Detached HEAD
                sha = repo.refs.resolve(args.branch)
                self._checkout_tree(sha, repo)
                repo.head.set_detached(sha)
                print(f"HEAD is now at {sha[:7]}")

        return 0

    def _checkout_tree(self, commit_sha, repo):
        """Update working directory and index to match commit."""
        from gitpy.index.operations import read_tree

        commit = repo.objects.read_commit(commit_sha)

        # Update index
        index = Index()
        read_tree(index, commit.tree_sha, repo.objects)
        repo.index.write(index)

        # Update working directory
        for entry in index:
            path = repo.worktree / entry.path
            path.parent.mkdir(parents=True, exist_ok=True)
            blob = repo.objects.read_blob(entry.sha)
            path.write_bytes(blob.data)
            if entry.mode == 0o100755:
                path.chmod(0o755)
```

---

## Phase 8: Advanced Features

### 8.1 Merge (Three-Way)

```python
# gitpy/merge/three_way.py

from typing import Optional, Tuple, List
from dataclasses import dataclass

@dataclass
class MergeResult:
    """Result of a merge operation."""
    success: bool
    tree_sha: Optional[str]
    conflicts: List[str]

def merge_trees(
    base_sha: Optional[str],
    ours_sha: str,
    theirs_sha: str,
    db: "ObjectDatabase"
) -> MergeResult:
    """
    Three-way merge of trees.

    Args:
        base_sha: Common ancestor tree
        ours_sha: Our tree (current branch)
        theirs_sha: Their tree (branch being merged)
        db: Object database

    Returns:
        MergeResult with merged tree or conflicts
    """
    conflicts = []
    merged_entries = {}

    # Get all paths from all trees
    base = _flatten_tree(base_sha, db) if base_sha else {}
    ours = _flatten_tree(ours_sha, db)
    theirs = _flatten_tree(theirs_sha, db)

    all_paths = set(base.keys()) | set(ours.keys()) | set(theirs.keys())

    for path in all_paths:
        b = base.get(path)
        o = ours.get(path)
        t = theirs.get(path)

        result = _merge_file(b, o, t, path, db)
        if result.conflict:
            conflicts.append(path)
        if result.entry:
            merged_entries[path] = result.entry

    if conflicts:
        return MergeResult(success=False, tree_sha=None, conflicts=conflicts)

    # Build merged tree
    tree_sha = _build_tree(merged_entries, db)
    return MergeResult(success=True, tree_sha=tree_sha, conflicts=[])

def _merge_file(base, ours, theirs, path, db):
    """Merge single file using 3-way logic."""
    # Case: same in all
    if ours == theirs:
        return MergeEntry(conflict=False, entry=ours)

    # Case: only we changed
    if base == theirs:
        return MergeEntry(conflict=False, entry=ours)

    # Case: only they changed
    if base == ours:
        return MergeEntry(conflict=False, entry=theirs)

    # Case: both changed differently - conflict
    # Could attempt content merge here
    return MergeEntry(conflict=True, entry=None)
```

### 8.2 CLI Entry Point

```python
# gitpy/cli.py

import sys
import argparse
from pathlib import Path

from gitpy.repository import Repository
from gitpy.commands import COMMANDS

def main():
    parser = argparse.ArgumentParser(
        prog="gitpy",
        description="Git reimplemented in Python"
    )
    parser.add_argument("-C", dest="directory", help="Run in directory")

    subparsers = parser.add_subparsers(dest="command")

    # Register commands
    for cmd_class in COMMANDS:
        cmd = cmd_class()
        subparser = subparsers.add_parser(cmd.name, help=cmd.help)
        cmd.setup_parser(subparser)

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return 1

    # Find repository
    try:
        if args.directory:
            repo = Repository.find(Path(args.directory))
        elif args.command in ("init", "clone"):
            repo = None
        else:
            repo = Repository.find()
    except ValueError as e:
        if args.command not in ("init", "clone"):
            print(f"fatal: {e}", file=sys.stderr)
            return 128
        repo = None

    # Run command
    cmd_class = next(c for c in COMMANDS if c.name == args.command)
    cmd = cmd_class()
    return cmd.run(args, repo)

if __name__ == "__main__":
    sys.exit(main())
```

### 8.3 pyproject.toml Entry Point

```toml
[tool.poetry.scripts]
gitpy = "gitpy.cli:main"
```

---

## 9. Acceptance Criteria

### 9.1 Plumbing Commands

- [ ] `hash-object` computes SHA, optionally writes
- [ ] `cat-file` shows type/size/content
- [ ] `ls-tree` lists tree contents
- [ ] `write-tree` creates tree from index
- [ ] `commit-tree` creates commit object
- [ ] `update-ref` modifies references

### 9.2 Porcelain Commands

- [ ] `init` creates repository
- [ ] `add` stages files
- [ ] `commit` creates commit and updates HEAD
- [ ] `status` shows working tree state
- [ ] `log` shows history
- [ ] `diff` shows changes
- [ ] `branch` manages branches
- [ ] `checkout` switches branches

### 9.3 Compatibility

- [ ] Can create repo usable by real Git
- [ ] Can work with repo created by real Git
- [ ] Output format matches Git where appropriate

---

## 10. File Structure

```
gitpy/
├── cli.py
├── diff/
│   ├── __init__.py
│   ├── myers.py
│   ├── unified.py
│   └── tree.py
├── merge/
│   ├── __init__.py
│   └── three_way.py
└── commands/
    ├── __init__.py
    ├── base.py
    ├── plumbing/
    │   ├── __init__.py
    │   ├── hash_object.py
    │   ├── cat_file.py
    │   ├── ls_tree.py
    │   ├── write_tree.py
    │   ├── commit_tree.py
    │   └── update_ref.py
    └── porcelain/
        ├── __init__.py
        ├── init.py
        ├── add.py
        ├── commit.py
        ├── status.py
        ├── log.py
        ├── diff.py
        ├── branch.py
        └── checkout.py
```
