"""Git configuration file reader.

Parses the INI-style .git/config file and provides key-value access
using "section.key" notation (e.g. "user.name").
"""

import configparser
from pathlib import Path


class GitConfig:
    """Read-only view of a .git/config file.

    Supports ``section.key`` lookups, e.g. ``get("user.name")``.

    Args:
        git_dir: Path to the .git directory.
    """

    def __init__(self, git_dir: Path) -> None:
        """Load and parse the config file.

        Args:
            git_dir: Path to the .git directory.
        """
        self._config = configparser.ConfigParser()
        config_path = git_dir / "config"
        if config_path.exists():
            self._config.read(str(config_path))

    def get(self, key: str, default: str | None = None) -> str | None:
        """Retrieve a config value by ``section.option`` key.

        Args:
            key: Dot-separated key in ``section.option`` form, e.g.
                ``"user.name"`` or ``"core.bare"``.
            default: Value to return when the key is absent.

        Returns:
            String value from the config file, or *default* if not found.
        """
        parts = key.split(".", 1)
        if len(parts) != 2:
            return default
        section, option = parts
        if self._config.has_option(section, option):
            return self._config.get(section, option)
        return default
