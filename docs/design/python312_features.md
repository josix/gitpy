# Python 3.12+ Features for gitpy

This document outlines modern Python 3.12+ features to leverage in the implementation.

## Required Python Version

```toml
[project]
requires-python = ">=3.12"
```

## Key Features to Use

### 1. Type Parameter Syntax (PEP 695)

**Old style:**
```python
from typing import TypeVar, Generic

T = TypeVar("T")

class Repository(Generic[T]):
    def get(self, key: str) -> T: ...
```

**New style (3.12+):**
```python
class Repository[T]:
    def get(self, key: str) -> T: ...

def parse[T: GitObject](data: bytes, cls: type[T]) -> T: ...
```

### 2. Self Type (PEP 673)

```python
from typing import Self

class GitObject:
    @classmethod
    def deserialize(cls, data: bytes) -> Self:
        """Returns instance of the actual subclass."""
        ...

    def with_updated(self, **kwargs) -> Self:
        """Returns same type as self."""
        ...
```

### 3. Pattern Matching (match/case)

```python
def parse_revision(rev: str) -> str:
    """Parse Git revision expression."""
    match rev.split("^"):
        case [base]:
            return resolve_ref(base)
        case [base, ""]:
            return get_parent(resolve_ref(base), 1)
        case [base, n] if n.isdigit():
            return get_parent(resolve_ref(base), int(n))
        case _:
            raise ValueError(f"Invalid revision: {rev}")

def get_object_type(obj: GitObject) -> str:
    match obj:
        case Blob():
            return "blob"
        case Tree():
            return "tree"
        case Commit():
            return "commit"
        case Tag():
            return "tag"
```

### 4. Dataclasses with slots and kw_only

```python
from dataclasses import dataclass, field

@dataclass(slots=True, frozen=True)
class TreeEntry:
    """Immutable tree entry with memory-efficient slots."""
    mode: str
    name: str
    sha: str

@dataclass(slots=True, kw_only=True)
class Commit:
    """Commit with keyword-only arguments for clarity."""
    tree_sha: str
    parent_shas: list[str] = field(default_factory=list)
    author: Identity
    committer: Identity
    message: str
```

### 5. Built-in Generic Types

**No imports needed for basic generics:**
```python
# Old style
from typing import List, Dict, Optional, Tuple

def process(items: List[str]) -> Dict[str, int]: ...

# New style (3.9+, preferred in 3.12+)
def process(items: list[str]) -> dict[str, int]: ...

def get_entry(path: str) -> TreeEntry | None: ...  # Instead of Optional

def parse(data: bytes) -> tuple[str, GitObject]: ...
```

### 6. TypeAlias and type Statement

```python
# New type alias syntax (3.12+)
type SHA = str
type ObjectData = bytes
type RefName = str

type TreeEntries = list[TreeEntry]
type RefMap = dict[RefName, SHA]

# Generic type aliases
type Result[T] = tuple[T, bytes]
type Parser[T] = Callable[[bytes], T]
```

### 7. Exception Groups and except*

```python
async def validate_objects(shas: list[str]) -> None:
    """Validate multiple objects, collecting all errors."""
    errors: list[Exception] = []

    for sha in shas:
        try:
            validate_sha(sha)
        except ValidationError as e:
            errors.append(e)

    if errors:
        raise ExceptionGroup("validation failed", errors)

# Handling
try:
    validate_objects(shas)
except* ValidationError as eg:
    for error in eg.exceptions:
        print(f"Invalid: {error}")
```

### 8. Improved f-strings (3.12)

```python
# Can now use quotes and backslashes freely
sha = "abc123"
message = f"Commit {sha!r} by {author["name"]}"

# Multiline expressions
result = f"""
Tree: {tree_sha}
Parents: {", ".join(parent_shas)}
Author: {author.name} <{author.email}>
"""
```

### 9. Buffer Protocol (PEP 688)

```python
from collections.abc import Buffer

def write_object(data: Buffer) -> str:
    """Accept any buffer-like object."""
    view = memoryview(data)
    return hashlib.sha1(view).hexdigest()
```

### 10. tomllib (3.11+ stdlib)

```python
import tomllib

def read_config(path: Path) -> dict:
    """Read Git config in TOML-like format."""
    with open(path, "rb") as f:
        return tomllib.load(f)
```

---

## Updated Code Examples

### Object Base Class (Modern)

```python
# gitpy/objects/base.py

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Self
import hashlib

type SHA = str
type ObjectData = bytes

class GitObject(ABC):
    """Base class for all Git objects."""

    type_name: str

    @abstractmethod
    def serialize(self) -> bytes:
        """Serialize object content (without header)."""
        ...

    @classmethod
    @abstractmethod
    def deserialize(cls, data: bytes) -> Self:
        """Deserialize object content."""
        ...

    def compute_hash(self) -> SHA:
        """Compute SHA-1 hash of this object."""
        content = self.serialize()
        header = f"{self.type_name} {len(content)}\0".encode()
        return hashlib.sha1(header + content).hexdigest()

    @property
    def oid(self) -> SHA:
        """Object ID (SHA-1 hash)."""
        return self.compute_hash()
```

### Blob (Modern)

```python
# gitpy/objects/blob.py

from dataclasses import dataclass
from pathlib import Path
from typing import Self

from .base import GitObject

@dataclass(slots=True)
class Blob(GitObject):
    """Represents file contents."""

    type_name: str = "blob"
    data: bytes = b""

    def serialize(self) -> bytes:
        return self.data

    @classmethod
    def deserialize(cls, data: bytes) -> Self:
        return cls(data=data)

    @classmethod
    def from_file(cls, path: Path | str) -> Self:
        """Create Blob from file path."""
        return cls(data=Path(path).read_bytes())
```

### Tree Entry with Pattern Matching

```python
# gitpy/objects/tree.py

from dataclasses import dataclass
from typing import Self

@dataclass(slots=True, frozen=True)
class TreeEntry:
    """Single entry in a tree object."""
    mode: str
    name: str
    sha: str

    @property
    def entry_type(self) -> str:
        match self.mode:
            case "40000":
                return "tree"
            case "100644" | "100755":
                return "blob"
            case "120000":
                return "symlink"
            case "160000":
                return "gitlink"
            case _:
                return "unknown"

    @property
    def is_tree(self) -> bool:
        return self.mode == "40000"

    @property
    def is_executable(self) -> bool:
        return self.mode == "100755"
```

### Command Dispatch with Pattern Matching

```python
# gitpy/cli.py

def dispatch_command(args: list[str]) -> int:
    match args:
        case ["init", *rest]:
            return cmd_init(rest)
        case ["add", *paths] if paths:
            return cmd_add(paths)
        case ["commit", "-m", message]:
            return cmd_commit(message)
        case ["commit", "-m", message, "--amend"]:
            return cmd_commit(message, amend=True)
        case ["log", "--oneline"]:
            return cmd_log(oneline=True)
        case ["log", "-n", n] if n.isdigit():
            return cmd_log(limit=int(n))
        case ["status"]:
            return cmd_status()
        case [cmd, *_]:
            print(f"Unknown command: {cmd}")
            return 1
        case []:
            print_usage()
            return 0
```

---

## Type Hints Summary

| Feature | Python Version | Example |
|---------|---------------|---------|
| `list[T]` instead of `List[T]` | 3.9+ | `list[str]` |
| `dict[K, V]` | 3.9+ | `dict[str, int]` |
| `T \| None` instead of `Optional[T]` | 3.10+ | `str \| None` |
| `match/case` | 3.10+ | Pattern matching |
| `Self` | 3.11+ | Return type for methods |
| `type X = ...` | 3.12+ | Type alias |
| `class Foo[T]:` | 3.12+ | Generic class |
| `def foo[T]():` | 3.12+ | Generic function |

---

## Migration Checklist

- [ ] Update all `from typing import List, Dict, ...` to built-in generics
- [ ] Replace `Optional[X]` with `X | None`
- [ ] Use `Self` for return types in class methods
- [ ] Add `slots=True` to dataclasses for memory efficiency
- [ ] Use pattern matching where appropriate (parsing, dispatch)
- [ ] Define type aliases with `type` statement
- [ ] Use f-string improvements for cleaner formatting
