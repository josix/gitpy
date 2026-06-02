# Config API Reference

This document provides a complete API reference for the `gitpy.config` module, which provides read-only access to the `.git/config` file.

## Module Overview

```python
from gitpy.config import GitConfig  # Read-only view of .git/config
```

---

## GitConfig

**Module:** `gitpy.config`

Read-only view of a `.git/config` file. Parses the INI-style config file on construction and provides key-value access using `"section.key"` notation.

```python
class GitConfig:
    ...
```

### Constructor

```python
def __init__(self, git_dir: Path) -> None
```

Load and parse the config file. If the config file does not exist, the object still constructs successfully — all subsequent `get()` calls will return the default value.

**Parameters:**
- `git_dir` - Path to the `.git` directory.

**Example:**
```python
from pathlib import Path
from gitpy.config import GitConfig

config = GitConfig(Path("/path/to/repo/.git"))
```

### Methods

#### `get()`

```python
def get(self, key: str, default: str | None = None) -> str | None
```

Retrieve a config value by `section.option` key.

**Parameters:**
- `key` - Dot-separated key in `section.option` form (e.g. `"user.name"` or `"core.bare"`).
- `default` - Value to return when the key is absent.

**Returns:** String value from the config file, or `default` if not found.

**Example:**
```python
name = config.get("user.name")
email = config.get("user.email")
bare = config.get("core.bare", "false")

print(name)   # "Alice Smith"
print(email)  # "alice@example.com"
print(bare)   # "false"
```

### Common Keys

| Key | Description |
|-----|-------------|
| `user.name` | Committer/author name |
| `user.email` | Committer/author email |
| `core.bare` | `"true"` if this is a bare repository |
| `core.repositoryformatversion` | Index format version (usually `"0"`) |
| `core.filemode` | Whether to track executable bit |

---

## Complete Example

```python
from pathlib import Path
from gitpy.config import GitConfig
from gitpy.objects import Identity
import time

git_dir = Path("/path/to/repo/.git")
config = GitConfig(git_dir)

# Read author identity from config
name = config.get("user.name", "Unknown")
email = config.get("user.email", "unknown@example.com")
author = Identity(
    name=name,
    email=email,
    timestamp=int(time.time()),
    tz_offset="+0000",
)
print(f"Committing as: {author}")

# Check if bare repo
is_bare = config.get("core.bare") == "true"
print(f"Bare repository: {is_bare}")
```

---

## See Also

- **[Storage API](storage.md)**: `Repository` class that instantiates `GitConfig` alongside the object database
- **[Object Model API](objects.md)**: `Identity` class whose fields are typically populated from config values
