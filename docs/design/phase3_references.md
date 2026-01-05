# Phase 3: References System - Design Specification

> **Status**: Draft
> **Author**: Domain Expert
> **Last Updated**: 2026-01-05
> **Dependencies**: Phase 1 (Object Model), Phase 2 (Storage)

## 1. Overview

References (refs) are human-readable names that point to commit SHAs. They make Git usable by allowing us to say "main" instead of "a1b2c3d4...".

### 1.1 Design Goals

- **Readability**: Human-friendly names for commits
- **Mutability**: Unlike objects, refs can change
- **Atomicity**: Ref updates are atomic
- **Hierarchy**: Refs organized in namespaces

### 1.2 Reference Types

| Type | Location | Purpose |
|------|----------|---------|
| HEAD | `.git/HEAD` | Current branch or commit |
| Branch | `.git/refs/heads/<name>` | Local branch tip |
| Tag | `.git/refs/tags/<name>` | Named release point |
| Remote | `.git/refs/remotes/<remote>/<branch>` | Remote-tracking branch |
| Stash | `.git/refs/stash` | Stashed changes |

---

## 2. Reference Format

### 2.1 Direct Reference

A direct reference contains a 40-character SHA-1 followed by newline:

```
a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2\n
```

### 2.2 Symbolic Reference

A symbolic reference points to another reference:

```
ref: refs/heads/main\n
```

**Key Properties:**
- Only HEAD is typically symbolic
- Symbolic refs are resolved recursively
- Detached HEAD contains SHA directly

### 2.3 Packed References

For performance, refs can be packed into `.git/packed-refs`:

```
# pack-refs with: peeled fully-peeled sorted
a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2 refs/heads/main
b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3 refs/heads/feature
^c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4
```

The `^` line is the "peeled" value for annotated tags.

---

## 3. HEAD Management

### 3.1 States

| State | Content | Meaning |
|-------|---------|---------|
| Attached | `ref: refs/heads/main` | On a branch |
| Detached | `<sha>` | At specific commit |

### 3.2 Implementation

```python
# gitpy/refs/head.py

from pathlib import Path
from typing import Optional, Tuple
from dataclasses import dataclass
from enum import Enum

class HeadState(Enum):
    ATTACHED = "attached"
    DETACHED = "detached"

@dataclass
class Head:
    """
    Represents the HEAD reference.

    HEAD is special: it's the only commonly-used symbolic ref.
    It indicates the current branch or commit.
    """

    state: HeadState
    target: str  # Branch name (attached) or SHA (detached)

    @property
    def is_detached(self) -> bool:
        return self.state == HeadState.DETACHED

    @property
    def branch(self) -> Optional[str]:
        """Current branch name, or None if detached."""
        if self.state == HeadState.ATTACHED:
            # Strip refs/heads/ prefix
            if self.target.startswith("refs/heads/"):
                return self.target[11:]
            return self.target
        return None

    @property
    def sha(self) -> Optional[str]:
        """Direct SHA if detached, None if attached."""
        if self.state == HeadState.DETACHED:
            return self.target
        return None

class HeadManager:
    """Manages HEAD reference."""

    def __init__(self, git_dir: Path):
        self.git_dir = git_dir
        self.head_path = git_dir / "HEAD"

    def read(self) -> Head:
        """Read current HEAD state."""
        content = self.head_path.read_text().strip()

        if content.startswith("ref: "):
            # Symbolic reference
            target = content[5:]
            return Head(state=HeadState.ATTACHED, target=target)
        else:
            # Direct SHA
            return Head(state=HeadState.DETACHED, target=content)

    def set_branch(self, branch: str) -> None:
        """Point HEAD at a branch."""
        if not branch.startswith("refs/"):
            branch = f"refs/heads/{branch}"
        self._write(f"ref: {branch}\n")

    def set_detached(self, sha: str) -> None:
        """Point HEAD at a specific commit."""
        if len(sha) != 40:
            raise ValueError("SHA must be 40 characters")
        self._write(f"{sha}\n")

    def _write(self, content: str) -> None:
        """Atomic write to HEAD."""
        temp = self.head_path.with_suffix(".lock")
        try:
            temp.write_text(content)
            temp.rename(self.head_path)
        except Exception:
            temp.unlink(missing_ok=True)
            raise

    def resolve(self, ref_manager: "RefManager") -> str:
        """
        Resolve HEAD to a commit SHA.

        Args:
            ref_manager: Reference manager for branch resolution

        Returns:
            40-character SHA

        Raises:
            ValueError: HEAD points to non-existent branch
        """
        head = self.read()

        if head.is_detached:
            return head.target

        # Resolve branch reference
        sha = ref_manager.resolve(head.target)
        if sha is None:
            raise ValueError(f"Branch {head.branch} does not exist")
        return sha
```

---

## 4. Reference Manager

### 4.1 Core Operations

| Operation | Description |
|-----------|-------------|
| `resolve(name)` | Convert ref name to SHA |
| `read(name)` | Read ref value (may be symbolic) |
| `write(name, sha)` | Update ref to point to SHA |
| `delete(name)` | Remove reference |
| `list(pattern)` | List refs matching pattern |

### 4.2 Resolution Rules

When resolving a reference name:

1. If it's a 40-char hex string, use directly
2. Check `refs/<name>`
3. Check `refs/tags/<name>`
4. Check `refs/heads/<name>`
5. Check `refs/remotes/<name>`
6. Check `refs/remotes/<name>/HEAD`

### 4.3 Implementation

```python
# gitpy/refs/manager.py

from pathlib import Path
from typing import Optional, List, Iterator, Tuple
import fnmatch
import re

class RefManager:
    """
    Manages Git references.

    Handles reading, writing, and resolving references
    including support for packed refs.
    """

    def __init__(self, git_dir: Path):
        self.git_dir = git_dir
        self.refs_dir = git_dir / "refs"
        self.packed_refs_path = git_dir / "packed-refs"
        self._packed_refs_cache: Optional[dict] = None

    # =========== Reading ===========

    def read(self, name: str) -> Optional[str]:
        """
        Read reference value (SHA or symbolic target).

        Args:
            name: Reference name (e.g., "refs/heads/main")

        Returns:
            SHA or "ref: <target>" for symbolic refs, None if not found
        """
        path = self.git_dir / name

        # Check loose ref first
        if path.is_file():
            content = path.read_text().strip()
            return content

        # Check packed refs
        packed = self._read_packed_refs()
        if name in packed:
            return packed[name]

        return None

    def resolve(self, name: str, max_depth: int = 10) -> Optional[str]:
        """
        Resolve reference to final SHA.

        Follows symbolic references recursively.

        Args:
            name: Reference name or SHA
            max_depth: Maximum symbolic ref depth (prevent loops)

        Returns:
            40-character SHA or None if not found
        """
        # Direct SHA
        if self._is_sha(name):
            return name

        # Try various prefixes
        for prefix in ["", "refs/", "refs/tags/", "refs/heads/", "refs/remotes/"]:
            full_name = prefix + name if prefix else name
            sha = self._resolve_ref(full_name, max_depth)
            if sha:
                return sha

        return None

    def _resolve_ref(self, name: str, max_depth: int) -> Optional[str]:
        """Resolve a single reference path."""
        if max_depth <= 0:
            raise ValueError(f"Symbolic reference loop detected at {name}")

        value = self.read(name)
        if value is None:
            return None

        # Follow symbolic reference
        if value.startswith("ref: "):
            target = value[5:]
            return self._resolve_ref(target, max_depth - 1)

        # Direct SHA
        if self._is_sha(value):
            return value

        return None

    def _is_sha(self, value: str) -> bool:
        """Check if value looks like a SHA."""
        return len(value) == 40 and all(c in "0123456789abcdef" for c in value)

    # =========== Writing ===========

    def write(self, name: str, sha: str) -> None:
        """
        Update reference to point to SHA.

        Args:
            name: Reference name
            sha: 40-character SHA
        """
        if not self._is_sha(sha):
            raise ValueError(f"Invalid SHA: {sha}")

        path = self.git_dir / name
        path.parent.mkdir(parents=True, exist_ok=True)

        # Atomic write
        temp = path.with_suffix(".lock")
        try:
            temp.write_text(f"{sha}\n")
            temp.rename(path)
        except Exception:
            temp.unlink(missing_ok=True)
            raise

    def write_symbolic(self, name: str, target: str) -> None:
        """
        Create symbolic reference.

        Args:
            name: Reference name
            target: Target reference name
        """
        path = self.git_dir / name
        path.parent.mkdir(parents=True, exist_ok=True)

        temp = path.with_suffix(".lock")
        try:
            temp.write_text(f"ref: {target}\n")
            temp.rename(path)
        except Exception:
            temp.unlink(missing_ok=True)
            raise

    def delete(self, name: str) -> bool:
        """
        Delete reference.

        Returns:
            True if deleted, False if didn't exist
        """
        path = self.git_dir / name
        if path.exists():
            path.unlink()
            # Clean up empty directories
            self._cleanup_empty_dirs(path.parent)
            return True
        return False

    def _cleanup_empty_dirs(self, path: Path) -> None:
        """Remove empty parent directories up to refs/."""
        while path != self.refs_dir and path.is_dir():
            try:
                path.rmdir()
                path = path.parent
            except OSError:
                break  # Not empty

    # =========== Listing ===========

    def list_refs(self, pattern: str = "refs/**") -> Iterator[Tuple[str, str]]:
        """
        List references matching pattern.

        Args:
            pattern: Glob pattern (e.g., "refs/heads/*")

        Yields:
            (name, sha) tuples
        """
        seen = set()

        # Loose refs
        for ref_path in self.refs_dir.rglob("*"):
            if ref_path.is_file():
                name = str(ref_path.relative_to(self.git_dir))
                if fnmatch.fnmatch(name, pattern):
                    sha = self.resolve(name)
                    if sha:
                        seen.add(name)
                        yield (name, sha)

        # Packed refs
        packed = self._read_packed_refs()
        for name, sha in packed.items():
            if name not in seen and fnmatch.fnmatch(name, pattern):
                yield (name, sha)

    def list_branches(self) -> Iterator[Tuple[str, str]]:
        """List local branches."""
        for name, sha in self.list_refs("refs/heads/*"):
            branch_name = name[11:]  # Strip refs/heads/
            yield (branch_name, sha)

    def list_tags(self) -> Iterator[Tuple[str, str]]:
        """List tags."""
        for name, sha in self.list_refs("refs/tags/*"):
            tag_name = name[10:]  # Strip refs/tags/
            yield (tag_name, sha)

    # =========== Packed Refs ===========

    def _read_packed_refs(self) -> dict:
        """Read packed-refs file."""
        if self._packed_refs_cache is not None:
            return self._packed_refs_cache

        refs = {}
        if not self.packed_refs_path.exists():
            return refs

        for line in self.packed_refs_path.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#") or line.startswith("^"):
                continue

            parts = line.split(" ", 1)
            if len(parts) == 2:
                sha, name = parts
                refs[name] = sha

        self._packed_refs_cache = refs
        return refs

    def pack_refs(self) -> None:
        """Pack loose refs into packed-refs file."""
        refs = dict(self.list_refs())

        lines = ["# pack-refs with: peeled fully-peeled sorted\n"]
        for name in sorted(refs.keys()):
            sha = refs[name]
            lines.append(f"{sha} {name}\n")

        self.packed_refs_path.write_text("".join(lines))

        # Delete loose refs (except HEAD)
        for name in refs:
            if name != "HEAD":
                path = self.git_dir / name
                if path.exists():
                    path.unlink()
                    self._cleanup_empty_dirs(path.parent)

        # Invalidate cache
        self._packed_refs_cache = None
```

---

## 5. Branch Operations

### 5.1 Branch Class

```python
# gitpy/refs/branch.py

from dataclasses import dataclass
from pathlib import Path
from typing import Optional, List

@dataclass
class Branch:
    """Represents a Git branch."""
    name: str
    sha: str

    @property
    def full_name(self) -> str:
        return f"refs/heads/{self.name}"

    @property
    def short_sha(self) -> str:
        return self.sha[:7]

class BranchManager:
    """High-level branch operations."""

    def __init__(self, ref_manager: "RefManager", head_manager: "HeadManager"):
        self.refs = ref_manager
        self.head = head_manager

    def current(self) -> Optional[str]:
        """Get current branch name, or None if detached."""
        return self.head.read().branch

    def exists(self, name: str) -> bool:
        """Check if branch exists."""
        return self.refs.resolve(f"refs/heads/{name}") is not None

    def get(self, name: str) -> Optional[Branch]:
        """Get branch by name."""
        sha = self.refs.resolve(f"refs/heads/{name}")
        if sha:
            return Branch(name=name, sha=sha)
        return None

    def create(self, name: str, sha: str, force: bool = False) -> Branch:
        """
        Create a new branch.

        Args:
            name: Branch name
            sha: Commit SHA to point to
            force: Overwrite if exists

        Returns:
            Created branch

        Raises:
            ValueError: Branch exists and force=False
        """
        self._validate_name(name)

        if self.exists(name) and not force:
            raise ValueError(f"Branch '{name}' already exists")

        self.refs.write(f"refs/heads/{name}", sha)
        return Branch(name=name, sha=sha)

    def delete(self, name: str, force: bool = False) -> bool:
        """
        Delete a branch.

        Args:
            name: Branch name
            force: Delete even if not merged

        Returns:
            True if deleted

        Raises:
            ValueError: Trying to delete current branch
        """
        if name == self.current():
            raise ValueError("Cannot delete the currently checked out branch")

        ref_name = f"refs/heads/{name}"
        return self.refs.delete(ref_name)

    def rename(self, old_name: str, new_name: str, force: bool = False) -> Branch:
        """
        Rename a branch.

        Args:
            old_name: Current name
            new_name: New name
            force: Overwrite if new_name exists
        """
        self._validate_name(new_name)

        old_branch = self.get(old_name)
        if old_branch is None:
            raise ValueError(f"Branch '{old_name}' does not exist")

        if self.exists(new_name) and not force:
            raise ValueError(f"Branch '{new_name}' already exists")

        # Create new, delete old
        self.refs.write(f"refs/heads/{new_name}", old_branch.sha)
        self.refs.delete(f"refs/heads/{old_name}")

        # Update HEAD if renaming current branch
        if self.current() == old_name:
            self.head.set_branch(new_name)

        return Branch(name=new_name, sha=old_branch.sha)

    def list(self) -> List[Branch]:
        """List all branches."""
        return [
            Branch(name=name, sha=sha)
            for name, sha in self.refs.list_branches()
        ]

    def _validate_name(self, name: str) -> None:
        """Validate branch name."""
        if not name:
            raise ValueError("Branch name cannot be empty")
        if name.startswith("-"):
            raise ValueError("Branch name cannot start with '-'")
        if ".." in name:
            raise ValueError("Branch name cannot contain '..'")
        if name.endswith(".lock"):
            raise ValueError("Branch name cannot end with '.lock'")
        if "@{" in name:
            raise ValueError("Branch name cannot contain '@{'")

        # Check for invalid characters
        invalid = set(" ~^:?*[\\")
        if any(c in name for c in invalid):
            raise ValueError(f"Branch name contains invalid characters")
```

---

## 6. Tag Operations

### 6.1 Tag Types

| Type | Storage | Description |
|------|---------|-------------|
| Lightweight | Reference only | Points directly to commit |
| Annotated | Tag object + Reference | Contains message and tagger |

### 6.2 Implementation

```python
# gitpy/refs/tag.py

from dataclasses import dataclass
from typing import Optional, List, Union

from gitpy.objects.tag import Tag as TagObject
from gitpy.objects.commit import Identity
from gitpy.storage.database import ObjectDatabase

@dataclass
class LightweightTag:
    """A lightweight tag (just a reference)."""
    name: str
    sha: str  # Points to commit

    @property
    def is_annotated(self) -> bool:
        return False

@dataclass
class AnnotatedTag:
    """An annotated tag (tag object + reference)."""
    name: str
    sha: str       # Tag object SHA
    target: str    # Target commit SHA
    message: str
    tagger: Optional[Identity]

    @property
    def is_annotated(self) -> bool:
        return True

TagType = Union[LightweightTag, AnnotatedTag]

class TagManager:
    """High-level tag operations."""

    def __init__(self, ref_manager: "RefManager", object_db: ObjectDatabase):
        self.refs = ref_manager
        self.objects = object_db

    def get(self, name: str) -> Optional[TagType]:
        """
        Get tag by name.

        Returns LightweightTag or AnnotatedTag depending on type.
        """
        sha = self.refs.resolve(f"refs/tags/{name}")
        if sha is None:
            return None

        # Check if it's an annotated tag
        obj_type = self.objects.get_type(sha)
        if obj_type == "tag":
            tag_obj = self.objects.read(sha)
            return AnnotatedTag(
                name=name,
                sha=sha,
                target=tag_obj.object_sha,
                message=tag_obj.message,
                tagger=tag_obj.tagger
            )
        else:
            return LightweightTag(name=name, sha=sha)

    def create_lightweight(self, name: str, sha: str, force: bool = False) -> LightweightTag:
        """Create lightweight tag."""
        if self.exists(name) and not force:
            raise ValueError(f"Tag '{name}' already exists")

        self.refs.write(f"refs/tags/{name}", sha)
        return LightweightTag(name=name, sha=sha)

    def create_annotated(
        self,
        name: str,
        sha: str,
        message: str,
        tagger: Identity,
        force: bool = False
    ) -> AnnotatedTag:
        """Create annotated tag."""
        if self.exists(name) and not force:
            raise ValueError(f"Tag '{name}' already exists")

        # Create tag object
        tag_obj = TagObject(
            object_sha=sha,
            object_type="commit",
            tag_name=name,
            tagger=tagger,
            message=message
        )
        tag_sha = self.objects.write(tag_obj)

        # Create reference
        self.refs.write(f"refs/tags/{name}", tag_sha)

        return AnnotatedTag(
            name=name,
            sha=tag_sha,
            target=sha,
            message=message,
            tagger=tagger
        )

    def exists(self, name: str) -> bool:
        """Check if tag exists."""
        return self.refs.resolve(f"refs/tags/{name}") is not None

    def delete(self, name: str) -> bool:
        """Delete tag."""
        return self.refs.delete(f"refs/tags/{name}")

    def list(self) -> List[TagType]:
        """List all tags."""
        tags = []
        for name, _ in self.refs.list_tags():
            tag = self.get(name)
            if tag:
                tags.append(tag)
        return tags

    def peel(self, name: str) -> Optional[str]:
        """
        Get the commit SHA a tag points to.

        For lightweight tags, returns the tag target.
        For annotated tags, follows to the commit.
        """
        tag = self.get(name)
        if tag is None:
            return None

        if isinstance(tag, LightweightTag):
            return tag.sha
        else:
            return tag.target
```

---

## 7. Reflog

### 7.1 Purpose

Reflog records when refs change, enabling recovery of lost commits.

### 7.2 Format

`.git/logs/<ref>` contains log entries:

```
<old-sha> <new-sha> <identity> <timestamp> <tz>\t<message>
```

Example:
```
0000000000000000000000000000000000000000 a1b2c3d4... User <user@example.com> 1234567890 +0000	commit (initial): Initial commit
a1b2c3d4... b2c3d4e5... User <user@example.com> 1234567891 +0000	commit: Add feature
```

### 7.3 Implementation

```python
# gitpy/refs/reflog.py

from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional
from datetime import datetime

from gitpy.objects.commit import Identity

ZERO_SHA = "0" * 40

@dataclass
class ReflogEntry:
    """Single reflog entry."""
    old_sha: str
    new_sha: str
    identity: Identity
    message: str

    def format(self) -> str:
        """Format as reflog line."""
        return f"{self.old_sha} {self.new_sha} {self.identity}\t{self.message}\n"

    @classmethod
    def parse(cls, line: str) -> "ReflogEntry":
        """Parse reflog line."""
        # Split on tab for message
        parts = line.split("\t", 1)
        header = parts[0]
        message = parts[1] if len(parts) > 1 else ""

        # Parse header: old_sha new_sha identity
        old_sha = header[:40]
        new_sha = header[41:81]
        identity_str = header[82:]

        identity = Identity.parse(identity_str)

        return cls(
            old_sha=old_sha,
            new_sha=new_sha,
            identity=identity,
            message=message.strip()
        )

class Reflog:
    """Manages reflog for references."""

    def __init__(self, git_dir: Path):
        self.git_dir = git_dir
        self.logs_dir = git_dir / "logs"

    def _log_path(self, ref: str) -> Path:
        """Get log file path for reference."""
        return self.logs_dir / ref

    def append(
        self,
        ref: str,
        old_sha: str,
        new_sha: str,
        identity: Identity,
        message: str
    ) -> None:
        """
        Append entry to reflog.

        Args:
            ref: Reference name
            old_sha: Previous SHA (ZERO_SHA for new ref)
            new_sha: New SHA
            identity: Who made the change
            message: What happened (e.g., "commit: Add feature")
        """
        path = self._log_path(ref)
        path.parent.mkdir(parents=True, exist_ok=True)

        entry = ReflogEntry(
            old_sha=old_sha,
            new_sha=new_sha,
            identity=identity,
            message=message
        )

        with open(path, "a") as f:
            f.write(entry.format())

    def read(self, ref: str, limit: Optional[int] = None) -> List[ReflogEntry]:
        """
        Read reflog entries (newest first).

        Args:
            ref: Reference name
            limit: Maximum entries to return
        """
        path = self._log_path(ref)
        if not path.exists():
            return []

        entries = []
        for line in path.read_text().splitlines():
            if line.strip():
                entries.append(ReflogEntry.parse(line))

        # Reverse for newest first
        entries.reverse()

        if limit:
            entries = entries[:limit]

        return entries

    def get(self, ref: str, index: int) -> Optional[ReflogEntry]:
        """
        Get specific reflog entry.

        Args:
            ref: Reference name
            index: Entry index (0 = most recent)
        """
        entries = self.read(ref, limit=index + 1)
        if index < len(entries):
            return entries[index]
        return None

    def clear(self, ref: str) -> None:
        """Clear reflog for reference."""
        path = self._log_path(ref)
        if path.exists():
            path.unlink()
```

---

## 8. Revision Parsing

### 8.1 Revision Expressions

Git supports complex revision expressions:

| Expression | Meaning |
|------------|---------|
| `HEAD` | Current commit |
| `main` | Branch tip |
| `v1.0` | Tag |
| `abc123` | Abbreviated SHA |
| `HEAD^` | First parent |
| `HEAD^2` | Second parent (merge) |
| `HEAD~3` | 3rd ancestor |
| `HEAD@{1}` | Previous HEAD value |
| `main@{yesterday}` | Branch at time |

### 8.2 Implementation

```python
# gitpy/refs/revision.py

import re
from typing import Optional
from dataclasses import dataclass

@dataclass
class RevisionParser:
    """Parses Git revision expressions."""

    ref_manager: "RefManager"
    object_db: "ObjectDatabase"

    def parse(self, rev: str) -> Optional[str]:
        """
        Parse revision expression to SHA.

        Args:
            rev: Revision expression

        Returns:
            40-character SHA or None
        """
        # Handle suffixes
        if "^" in rev or "~" in rev:
            return self._parse_with_suffix(rev)

        if "@{" in rev:
            return self._parse_reflog_ref(rev)

        # Direct resolution
        return self.ref_manager.resolve(rev)

    def _parse_with_suffix(self, rev: str) -> Optional[str]:
        """Parse revision with ^ or ~ suffix."""
        # Split base and suffixes
        match = re.match(r'^([^~^]+)((?:[~^]\d*)+)$', rev)
        if not match:
            return self.ref_manager.resolve(rev)

        base, suffixes = match.groups()
        sha = self.ref_manager.resolve(base)
        if sha is None:
            return None

        # Process each suffix
        pos = 0
        while pos < len(suffixes):
            char = suffixes[pos]
            pos += 1

            # Get optional number
            num_match = re.match(r'(\d+)', suffixes[pos:])
            if num_match:
                num = int(num_match.group(1))
                pos += len(num_match.group(1))
            else:
                num = 1

            if char == '^':
                sha = self._get_parent(sha, num)
            elif char == '~':
                for _ in range(num):
                    sha = self._get_parent(sha, 1)
                    if sha is None:
                        return None

            if sha is None:
                return None

        return sha

    def _get_parent(self, sha: str, n: int) -> Optional[str]:
        """Get nth parent of commit."""
        commit = self.object_db.read_commit(sha)
        if n <= 0 or n > len(commit.parent_shas):
            return None
        return commit.parent_shas[n - 1]

    def _parse_reflog_ref(self, rev: str) -> Optional[str]:
        """Parse reflog reference like HEAD@{1}."""
        match = re.match(r'^(.+)@\{(\d+)\}$', rev)
        if not match:
            return None

        ref, index = match.groups()
        index = int(index)

        # Get from reflog
        from .reflog import Reflog
        reflog = Reflog(self.ref_manager.git_dir)
        entry = reflog.get(ref, index)

        if entry:
            return entry.new_sha
        return None
```

---

## 9. Test Cases

### 9.1 HEAD Tests

```python
class TestHead:

    def test_read_attached(self, repo):
        head = repo.head.read()
        assert head.state == HeadState.ATTACHED
        assert head.branch == "main"

    def test_read_detached(self, repo):
        repo.head.set_detached("a" * 40)
        head = repo.head.read()
        assert head.is_detached
        assert head.sha == "a" * 40

    def test_set_branch(self, repo):
        repo.head.set_branch("feature")
        head = repo.head.read()
        assert head.branch == "feature"
```

### 9.2 Reference Tests

```python
class TestRefManager:

    def test_resolve_branch(self, repo):
        repo.refs.write("refs/heads/test", "a" * 40)
        assert repo.refs.resolve("test") == "a" * 40
        assert repo.refs.resolve("refs/heads/test") == "a" * 40

    def test_resolve_short_sha(self, repo):
        sha = "abcdef1234567890" * 2 + "abcdef12"
        repo.refs.write("refs/heads/test", sha)
        # SHA resolution is handled by object database, not refs
```

### 9.3 Branch Tests

```python
class TestBranchManager:

    def test_create_branch(self, repo):
        branch = repo.branches.create("feature", "a" * 40)
        assert branch.name == "feature"
        assert repo.branches.exists("feature")

    def test_delete_current_branch_fails(self, repo):
        repo.head.set_branch("main")
        with pytest.raises(ValueError, match="currently checked out"):
            repo.branches.delete("main")

    def test_rename_updates_head(self, repo):
        repo.branches.create("old", "a" * 40)
        repo.head.set_branch("old")
        repo.branches.rename("old", "new")
        assert repo.head.read().branch == "new"
```

---

## 10. Acceptance Criteria

### 10.1 Functional Requirements

- [ ] HEAD can be attached (branch) or detached (SHA)
- [ ] References resolve through prefix search
- [ ] Symbolic refs are followed recursively
- [ ] Packed refs are read correctly
- [ ] Branch create/delete/rename work
- [ ] Tags (lightweight and annotated) work
- [ ] Reflog entries are recorded
- [ ] Revision expressions (^, ~) parse correctly

### 10.2 Non-Functional Requirements

- [ ] Atomic ref updates (lock files)
- [ ] Compatible with real Git refs
- [ ] Efficient packed-refs reading

---

## 11. File Structure

```
gitpy/
└── refs/
    ├── __init__.py
    ├── head.py        # HEAD management
    ├── manager.py     # RefManager
    ├── branch.py      # BranchManager
    ├── tag.py         # TagManager
    ├── reflog.py      # Reflog
    └── revision.py    # RevisionParser
```
