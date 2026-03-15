"""Configuration file support — ~/.config/mac-cleanup/config.toml"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

CONFIG_DIR = Path.home() / ".config" / "mac-cleanup"
CONFIG_PATH = CONFIG_DIR / "config.toml"

DEFAULT_CONFIG: dict[str, Any] = {
    "thresholds": {
        "min_size_mb": 1,
    },
    "skip": {
        "categories": [],
    },
    "custom_paths": {
        "targets": [],
    },
}


def load_config() -> dict[str, Any]:
    """Load config from TOML file, falling back to defaults."""
    if not CONFIG_PATH.exists():
        return DEFAULT_CONFIG.copy()

    # tomllib is built-in from Python 3.11+
    if sys.version_info >= (3, 11):
        import tomllib
    else:
        try:
            import tomllib  # type: ignore[import]
        except ImportError:
            try:
                import tomli as tomllib  # type: ignore[import,no-redef]
            except ImportError:
                return DEFAULT_CONFIG.copy()

    try:
        with open(CONFIG_PATH, "rb") as f:
            user_cfg = tomllib.load(f)
    except Exception:
        return DEFAULT_CONFIG.copy()

    # Merge with defaults
    merged = DEFAULT_CONFIG.copy()
    for section in ("thresholds", "skip", "custom_paths"):
        if section in user_cfg:
            merged[section] = {**merged.get(section, {}), **user_cfg[section]}
    return merged


def init_config() -> Path:
    """Create a default config file if it doesn't exist. Returns the path."""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    if not CONFIG_PATH.exists():
        CONFIG_PATH.write_text(
            '# mac-cleanup configuration\n'
            '# See: https://github.com/user/mac-cleanup\n'
            '\n'
            '[thresholds]\n'
            'min_size_mb = 1          # Skip targets smaller than this\n'
            '\n'
            '[skip]\n'
            'categories = []          # e.g. ["tm", "docker"]\n'
            '\n'
            '# Add custom cleanup targets:\n'
            '# [[custom_paths.targets]]\n'
            '# name = "Turborepo Cache"\n'
            '# path = "~/.turbo"\n',
        )
    return CONFIG_PATH
