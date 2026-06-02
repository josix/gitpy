# References API Reference

This document provides a complete API reference for the `gitpy.refs` module, which implements Git's reference management: branches, tags, HEAD, reflogs, and revision expressions.

## Module Overview

```python
from gitpy.refs import (
    RefManager,      # Low-level ref read/write/resolve
    Head,            # HEAD state data class
    HeadState,       # Enum: ATTACHED or DETACHED
    HeadManager,     # Read/write HEAD
    Branch,          # Branch data class
    BranchManager,   # High-level branch operations
    LightweightTag,  # Lightweight tag data class
    AnnotatedTag,    # Annotated tag data class
    TagType,         # Type alias: LightweightTag | AnnotatedTag
    TagManager,      # High-level tag operations
    Reflog,          # Reflog file manager
    ReflogEntry,     # Single reflog entry
    ZERO_SHA,        # "0" * 40 — sentinel for new refs
    RevisionParser,  # Parse revision expressions to SHAs
)
```

---

## RefManager

**Module:** `gitpy.refs.manager`

Manages Git references. Handles reading, writing, resolving, and listing references including support for packed-refs. All write and delete operations invalidate the packed-refs cache so subsequent reads remain consistent.

```python
class RefManager:
    git_dir: Path            # Path to the .git directory
    refs_dir: Path           # Path to .git/refs/
    packed_refs_path: Path   # Path to .git/packed-refs
```

### Constructor

```python
def __init__(self, git_dir: Path) -> None
```

**Parameters:**
- `git_dir` - Path to the `.git` directory.

**Example:**
```python
from pathlib import Path
from gitpy.refs import RefManager

ref_mgr = RefManager(Path("/path/to/repo/.git"))
```

### Methods

#### `read()`

```python
def read(self, name: str) -> str | None
```

Read a reference value (SHA or `"ref: <target>"` for symbolic refs). Loose refs take priority over packed refs.

**Parameters:**
- `name` - Reference name (e.g. `"refs/heads/main"`).

**Returns:** SHA string, `"ref: <target>"` for symbolic refs, or `None` if the reference does not exist or the name is unsafe.

**Example:**
```python
value = ref_mgr.read("refs/heads/main")
# Returns: "abc123def456..." or None
```

#### `resolve()`

```python
def resolve(self, name: str, max_depth: int = 10) -> str | None
```

Resolve a reference name or SHA to a final commit SHA. Resolution order for non-SHA names: direct name, `refs/<name>`, `refs/tags/<name>`, `refs/heads/<name>`, `refs/remotes/<name>`. Symbolic refs are followed recursively up to `max_depth` times.

**Parameters:**
- `name` - Reference name or 40-char hex SHA.
- `max_depth` - Maximum symbolic-ref chain depth (prevents loops).

**Returns:** 40-character hex SHA, or `None` if not found.

**Raises:**
- `ValueError` - A symbolic reference loop was detected.

**Example:**
```python
sha = ref_mgr.resolve("main")         # short name
sha = ref_mgr.resolve("refs/heads/main")  # full ref
sha = ref_mgr.resolve("HEAD")         # follows symref chain
```

#### `write()`

```python
def write(self, name: str, sha: str) -> None
```

Update a reference to point to a SHA. Creates parent directories as needed. Uses an atomic lock-file write. Invalidates the packed-refs cache.

**Parameters:**
- `name` - Reference name (e.g. `"refs/heads/main"`).
- `sha` - 40-character hex SHA.

**Raises:**
- `ValueError` - `sha` is not a valid 40-char hex SHA, or `name` is unsafe.

#### `write_symbolic()`

```python
def write_symbolic(self, name: str, target: str) -> None
```

Create a symbolic reference pointing to `target`.

**Parameters:**
- `name` - Reference name (e.g. `"HEAD"`).
- `target` - Target reference name (e.g. `"refs/heads/main"`).

**Raises:**
- `ValueError` - `name` is unsafe.

#### `delete()`

```python
def delete(self, name: str) -> bool
```

Delete a loose reference. Also cleans up empty parent directories up to `refs/`. Invalidates the packed-refs cache.

**Parameters:**
- `name` - Reference name.

**Returns:** `True` if the reference existed and was deleted, `False` otherwise.

**Raises:**
- `ValueError` - `name` is unsafe.

#### `list_refs()`

```python
def list_refs(self, pattern: str = "refs/**") -> Iterator[tuple[str, str]]
```

List references matching a glob pattern. Loose refs are yielded first; packed refs are yielded for any names not already seen.

**Parameters:**
- `pattern` - Glob pattern relative to `git_dir` (e.g. `"refs/heads/*"`).

**Yields:** `(name, sha)` tuples.

**Example:**
```python
for name, sha in ref_mgr.list_refs("refs/heads/*"):
    print(name, sha)
```

#### `list_branches()`

```python
def list_branches(self) -> Iterator[tuple[str, str]]
```

List local branches.

**Yields:** `(short_name, sha)` tuples where `short_name` has `"refs/heads/"` stripped.

#### `list_tags()`

```python
def list_tags(self) -> Iterator[tuple[str, str]]
```

List tags.

**Yields:** `(short_name, sha)` tuples where `short_name` has `"refs/tags/"` stripped.

#### `pack_refs()`

```python
def pack_refs(self) -> None
```

Pack all loose refs into the `packed-refs` file. After packing, loose ref files are removed (except `HEAD`) and the cache is invalidated.

---

## HeadState

**Module:** `gitpy.refs.head`

Enum describing the two possible states of the HEAD reference.

```python
class HeadState(Enum):
    ATTACHED = "attached"   # HEAD points to a branch ref
    DETACHED = "detached"   # HEAD points directly to a commit SHA
```

---

## Head

**Module:** `gitpy.refs.head`

Data class representing the HEAD reference state.

```python
@dataclass(slots=True)
class Head:
    state: HeadState   # Whether HEAD is attached or detached
    target: str        # Branch ref (attached) or SHA (detached)
```

### Attributes

| Name | Type | Description |
|------|------|-------------|
| `state` | `HeadState` | Whether HEAD is attached to a branch or detached at a SHA |
| `target` | `str` | Full ref (e.g. `"refs/heads/main"`) when attached, or 40-char SHA when detached |

### Properties

#### `is_detached`

```python
@property
def is_detached(self) -> bool
```

`True` when HEAD points directly to a commit SHA.

#### `branch`

```python
@property
def branch(self) -> str | None
```

Current branch short name, or `None` if detached. Strips the `"refs/heads/"` prefix from `target`.

**Returns:** Short branch name (e.g. `"main"`) or `None`.

#### `sha`

```python
@property
def sha(self) -> str | None
```

Direct SHA if detached, `None` if attached.

**Returns:** 40-char hex SHA or `None`.

---

## HeadManager

**Module:** `gitpy.refs.head`

Manages the HEAD reference. Provides atomic read/write operations for HEAD, supporting both attached (branch-tracking) and detached (SHA-pinned) states.

```python
class HeadManager:
    git_dir: Path       # Path to the .git directory
    head_path: Path     # Path to .git/HEAD
```

### Constructor

```python
def __init__(self, git_dir: Path) -> None
```

**Parameters:**
- `git_dir` - Path to the `.git` directory.

### Methods

#### `read()`

```python
def read(self) -> Head
```

Read the current HEAD state.

**Returns:** `Head` instance reflecting current HEAD content.

**Example:**
```python
head = head_mgr.read()
if head.is_detached:
    print(f"Detached at {head.sha}")
else:
    print(f"On branch {head.branch}")
```

#### `set_branch()`

```python
def set_branch(self, branch: str) -> None
```

Point HEAD at a branch. Short names are automatically prefixed with `"refs/heads/"`.

**Parameters:**
- `branch` - Branch short name or full ref (e.g. `"main"` or `"refs/heads/main"`).

#### `set_detached()`

```python
def set_detached(self, sha: str) -> None
```

Point HEAD at a specific commit (detached mode).

**Parameters:**
- `sha` - 40-character hex commit SHA.

**Raises:**
- `ValueError` - If `sha` is not exactly 40 characters.

#### `resolve()`

```python
def resolve(self, ref_manager: RefManager) -> str
```

Resolve HEAD to a commit SHA.

**Parameters:**
- `ref_manager` - Reference manager used to resolve branch names.

**Returns:** 40-character hex SHA of the current commit.

**Raises:**
- `ValueError` - HEAD points to a branch that does not exist yet.

---

## Branch

**Module:** `gitpy.refs.branch`

Data class representing a Git branch.

```python
@dataclass(slots=True)
class Branch:
    name: str   # Short branch name (e.g. "main")
    sha: str    # Full 40-char SHA the branch currently points to
```

### Attributes

| Name | Type | Description |
|------|------|-------------|
| `name` | `str` | Short branch name (e.g. `"main"`) |
| `sha` | `str` | Full 40-char SHA the branch currently points to |

### Properties

#### `full_name`

```python
@property
def full_name(self) -> str
```

Full ref name including namespace (e.g. `"refs/heads/main"`).

#### `short_sha`

```python
@property
def short_sha(self) -> str
```

First 7 characters of the SHA.

---

## BranchManager

**Module:** `gitpy.refs.branch`

High-level branch operations. Delegates low-level ref I/O to `RefManager` and HEAD mutations to `HeadManager`.

```python
class BranchManager:
    refs: RefManager    # Ref manager for this repository
    head: HeadManager   # HEAD manager for this repository
```

### Constructor

```python
def __init__(self, ref_manager: RefManager, head_manager: HeadManager) -> None
```

**Parameters:**
- `ref_manager` - `RefManager` instance for this repository.
- `head_manager` - `HeadManager` instance for this repository.

### Methods

#### `current()`

```python
def current(self) -> str | None
```

Return the current branch short name, or `None` if detached.

**Returns:** Branch name string, or `None` when HEAD is detached.

#### `exists()`

```python
def exists(self, name: str) -> bool
```

Check whether a branch exists.

**Parameters:**
- `name` - Short branch name.

**Returns:** `True` if the branch ref can be resolved.

#### `get()`

```python
def get(self, name: str) -> Branch | None
```

Retrieve a branch by name.

**Parameters:**
- `name` - Short branch name.

**Returns:** `Branch` instance, or `None` if the branch does not exist.

#### `create()`

```python
def create(self, name: str, sha: str, force: bool = False) -> Branch
```

Create a new branch.

**Parameters:**
- `name` - Short branch name to create.
- `sha` - Commit SHA the branch should point to.
- `force` - If `True`, overwrite an existing branch.

**Returns:** Newly created `Branch`.

**Raises:**
- `ValueError` - Branch already exists and `force` is `False`, or the name is invalid.

**Example:**
```python
branch = branch_mgr.create("feature/my-work", commit_sha)
print(branch.full_name)  # "refs/heads/feature/my-work"
```

#### `delete()`

```python
def delete(self, name: str, *, force: bool = False) -> bool
```

Delete a branch.

**Parameters:**
- `name` - Short branch name.
- `force` - Reserved for future merge-safety checks; currently unused.

**Returns:** `True` if the branch was deleted, `False` if it did not exist.

**Raises:**
- `ValueError` - Attempting to delete the currently checked-out branch.

#### `rename()`

```python
def rename(self, old_name: str, new_name: str, force: bool = False) -> Branch
```

Rename a branch. If the renamed branch is currently checked out, HEAD is updated to track the new name.

**Parameters:**
- `old_name` - Current short branch name.
- `new_name` - New short branch name.
- `force` - If `True`, overwrite `new_name` if it already exists.

**Returns:** Updated `Branch` with the new name.

**Raises:**
- `ValueError` - `old_name` does not exist, `new_name` already exists and `force` is `False`, or `new_name` is invalid.

#### `list()`

```python
def list(self) -> list[Branch]
```

List all local branches.

**Returns:** List of `Branch` instances.

---

## LightweightTag

**Module:** `gitpy.refs.tag`

A lightweight tag — just a reference, no tag object.

```python
@dataclass(slots=True)
class LightweightTag:
    name: str   # Short tag name
    sha: str    # SHA the tag points to (usually a commit)
```

### Attributes

| Name | Type | Description |
|------|------|-------------|
| `name` | `str` | Short tag name |
| `sha` | `str` | SHA the tag points to (usually a commit) |

### Properties

#### `is_annotated`

```python
@property
def is_annotated(self) -> bool
```

Always `False` for lightweight tags.

---

## AnnotatedTag

**Module:** `gitpy.refs.tag`

An annotated tag — a tag object stored in the object database plus a reference.

```python
@dataclass(slots=True)
class AnnotatedTag:
    name: str               # Short tag name
    sha: str                # SHA of the tag object
    target: str             # SHA of the tagged commit (or other object)
    message: str            # Tag message
    tagger: Identity | None # Identity who created the tag, or None
```

### Attributes

| Name | Type | Description |
|------|------|-------------|
| `name` | `str` | Short tag name |
| `sha` | `str` | SHA of the tag *object* |
| `target` | `str` | SHA of the tagged commit (or other object) |
| `message` | `str` | Tag message |
| `tagger` | `Identity \| None` | Identity who created the tag, or `None` |

### Properties

#### `is_annotated`

```python
@property
def is_annotated(self) -> bool
```

Always `True` for annotated tags.

---

## TagType

**Module:** `gitpy.refs.tag`

Type alias for tag union.

```python
type TagType = LightweightTag | AnnotatedTag
```

---

## TagManager

**Module:** `gitpy.refs.tag`

High-level tag operations.

```python
class TagManager:
    refs: RefManager         # Ref manager for this repository
    objects: ObjectDatabase  # Object database for this repository
```

### Constructor

```python
def __init__(self, ref_manager: RefManager, object_db: ObjectDatabase) -> None
```

**Parameters:**
- `ref_manager` - `RefManager` instance for this repository.
- `object_db` - `ObjectDatabase` instance for this repository.

### Methods

#### `get()`

```python
def get(self, name: str) -> TagType | None
```

Get a tag by name, distinguishing lightweight from annotated.

**Parameters:**
- `name` - Short tag name.

**Returns:** `LightweightTag` or `AnnotatedTag`, or `None` if not found.

#### `create_lightweight()`

```python
def create_lightweight(self, name: str, sha: str, force: bool = False) -> LightweightTag
```

Create a lightweight tag.

**Parameters:**
- `name` - Short tag name.
- `sha` - SHA to tag (usually a commit).
- `force` - If `True`, overwrite existing tag.

**Returns:** Created `LightweightTag`.

**Raises:**
- `ValueError` - Tag already exists and `force` is `False`.

**Example:**
```python
tag = tag_mgr.create_lightweight("v1.0.0", commit_sha)
```

#### `create_annotated()`

```python
def create_annotated(
    self,
    name: str,
    sha: str,
    message: str,
    tagger: Identity,
    force: bool = False,
) -> AnnotatedTag
```

Create an annotated tag. Writes a tag object to the object database and creates a ref pointing to that object.

**Parameters:**
- `name` - Short tag name.
- `sha` - SHA of the object being tagged (usually a commit).
- `message` - Tag message.
- `tagger` - Identity of the person creating the tag.
- `force` - If `True`, overwrite existing tag.

**Returns:** Created `AnnotatedTag`.

**Raises:**
- `ValueError` - Tag already exists and `force` is `False`.

**Example:**
```python
from gitpy.objects import Identity

tagger = Identity.now("Alice", "alice@example.com")
tag = tag_mgr.create_annotated("v1.0.0", commit_sha, "Release 1.0", tagger)
```

#### `exists()`

```python
def exists(self, name: str) -> bool
```

Check whether a tag exists.

**Parameters:**
- `name` - Short tag name.

**Returns:** `True` if the tag ref resolves.

#### `delete()`

```python
def delete(self, name: str) -> bool
```

Delete a tag.

**Parameters:**
- `name` - Short tag name.

**Returns:** `True` if deleted, `False` if it did not exist.

#### `list()`

```python
def list(self) -> list[TagType]
```

List all tags.

**Returns:** List of `LightweightTag` or `AnnotatedTag` instances.

#### `peel()`

```python
def peel(self, name: str) -> str | None
```

Resolve a tag to the underlying commit SHA. For lightweight tags this is the `sha` itself; for annotated tags this follows the tag object to its target.

**Parameters:**
- `name` - Short tag name.

**Returns:** Commit SHA, or `None` if the tag does not exist.

---

## ZERO_SHA

**Module:** `gitpy.refs.reflog`

```python
ZERO_SHA: str = "0" * 40
```

Sentinel SHA used to represent the absence of a previous value when a ref is newly created.

---

## ReflogEntry

**Module:** `gitpy.refs.reflog`

A single reflog entry.

```python
@dataclass(slots=True)
class ReflogEntry:
    old_sha: str        # Previous SHA (ZERO_SHA for a newly created ref)
    new_sha: str        # SHA after the change
    identity: Identity  # Who made the change
    message: str        # Short description of what happened
```

### Attributes

| Name | Type | Description |
|------|------|-------------|
| `old_sha` | `str` | Previous SHA (`ZERO_SHA` for a newly created ref) |
| `new_sha` | `str` | SHA after the change |
| `identity` | `Identity` | Who made the change |
| `message` | `str` | Short description of what happened |

### Methods

#### `format()`

```python
def format(self) -> str
```

Serialise as a reflog line (including trailing newline).

**Returns:** String in the form `"<old> <new> <identity>\t<message>\n"`.

#### `parse()`

```python
@classmethod
def parse(cls, line: str) -> Self
```

Parse a single reflog line.

**Parameters:**
- `line` - Raw line from a reflog file (trailing newline stripped).

**Returns:** A new `ReflogEntry` instance.

---

## Reflog

**Module:** `gitpy.refs.reflog`

Manages reflog files for references. Reflog files are stored under `.git/logs/<ref-name>`.

```python
class Reflog:
    git_dir: Path   # Path to the .git directory
    logs_dir: Path  # Path to .git/logs/
```

### Constructor

```python
def __init__(self, git_dir: Path) -> None
```

**Parameters:**
- `git_dir` - Path to the `.git` directory.

### Methods

#### `append()`

```python
def append(
    self,
    ref: str,
    old_sha: str,
    new_sha: str,
    identity: Identity,
    message: str,
) -> None
```

Append an entry to the reflog. Creates parent directories if they do not exist.

**Parameters:**
- `ref` - Reference name (e.g. `"HEAD"`).
- `old_sha` - Previous SHA (use `ZERO_SHA` for new refs).
- `new_sha` - New SHA after the change.
- `identity` - Who made the change.
- `message` - Human-readable description (e.g. `"commit: initial commit"`).

**Example:**
```python
from gitpy.refs import ZERO_SHA
from gitpy.objects import Identity

reflog.append("HEAD", ZERO_SHA, commit_sha, author, "commit: initial commit")
```

#### `read()`

```python
def read(self, ref: str, limit: int | None = None) -> list[ReflogEntry]
```

Read reflog entries, newest first.

**Parameters:**
- `ref` - Reference name.
- `limit` - Maximum number of entries to return.

**Returns:** List of `ReflogEntry` instances, most recent first.

#### `get()`

```python
def get(self, ref: str, index: int) -> ReflogEntry | None
```

Retrieve a specific reflog entry by index.

**Parameters:**
- `ref` - Reference name.
- `index` - 0-based index where `0` is the most recent entry.

**Returns:** `ReflogEntry` at `index`, or `None` if not enough entries.

#### `clear()`

```python
def clear(self, ref: str) -> None
```

Delete the reflog for `ref`.

**Parameters:**
- `ref` - Reference name.

---

## RevisionParser

**Module:** `gitpy.refs.revision`

Parses Git revision expressions into commit SHAs.

Supported expressions:
- Plain names: `HEAD`, `main`, `v1.0`, `abc123` (abbreviated SHA)
- Parent: `HEAD^`, `HEAD^2` (second parent of a merge commit)
- Ancestor: `HEAD~3` (three steps up the first-parent chain)
- Reflog: `HEAD@{1}` (previous value of HEAD)

```python
class RevisionParser:
    ref_manager: RefManager    # Ref manager for resolving branch/tag names
    object_db: ObjectDatabase  # Object database for reading commit objects
```

### Constructor

```python
def __init__(self, ref_manager: RefManager, object_db: ObjectDatabase) -> None
```

**Parameters:**
- `ref_manager` - `RefManager` for resolving branch/tag names.
- `object_db` - `ObjectDatabase` for reading commit objects.

### Methods

#### `parse()`

```python
def parse(self, rev: str) -> str | None
```

Parse a revision expression and return a 40-char SHA.

**Parameters:**
- `rev` - Revision expression string.

**Returns:** 40-character hex SHA, or `None` if the expression cannot be resolved.

**Example:**
```python
parser = RevisionParser(ref_mgr, db)

sha = parser.parse("HEAD")       # current commit
sha = parser.parse("HEAD^")      # parent of HEAD
sha = parser.parse("HEAD~3")     # three ancestors back
sha = parser.parse("HEAD^2")     # second parent (merge commit)
sha = parser.parse("HEAD@{1}")   # previous HEAD value
sha = parser.parse("main")       # branch tip
sha = parser.parse("v1.0")       # tag
sha = parser.parse("abc1234")    # abbreviated SHA
```

---

## Complete Example

```python
from pathlib import Path
from gitpy.refs import (
    RefManager, HeadManager, BranchManager, TagManager,
    Reflog, RevisionParser, ZERO_SHA,
)
from gitpy.storage import ObjectDatabase
from gitpy.objects import Identity

git_dir = Path("/path/to/repo/.git")
ref_mgr = RefManager(git_dir)
head_mgr = HeadManager(git_dir)
db = ObjectDatabase(git_dir)

branch_mgr = BranchManager(ref_mgr, head_mgr)
tag_mgr = TagManager(ref_mgr, db)
reflog = Reflog(git_dir)
parser = RevisionParser(ref_mgr, db)

# Create a branch and check HEAD
branch = branch_mgr.create("feature/my-work", some_sha)
head_mgr.set_branch("feature/my-work")
head = head_mgr.read()
print(head.branch)  # "feature/my-work"

# Create a lightweight tag
tag_mgr.create_lightweight("v0.1", some_sha)

# Record in reflog
identity = Identity.now("Alice", "alice@example.com")
reflog.append("HEAD", ZERO_SHA, some_sha, identity, "commit: initial")

# Parse revision expressions
sha = parser.parse("HEAD~1")
sha = parser.parse("HEAD@{0}")

# Pack all loose refs
ref_mgr.pack_refs()
```

---

## Git Compatibility

| Feature | Notes |
|---------|-------|
| Loose refs | Stored as `refs/heads/<name>`, `refs/tags/<name>` |
| Packed refs | Parsed and written in Git's `packed-refs` format |
| Symbolic refs | `"ref: <target>"` format, followed recursively |
| Reflog | Appended to `.git/logs/<ref>` in Git wire format |
| Revision expressions | `HEAD`, `HEAD^`, `HEAD~N`, `HEAD^2`, `HEAD@{N}` |

---

## See Also

- **[Storage API](storage.md)**: Object database used by `TagManager` and `RevisionParser`
- **[Object Model API](objects.md)**: `Identity` class used in tag and reflog entries
- **[Staging API](staging.md)**: Index operations that consume ref resolution
