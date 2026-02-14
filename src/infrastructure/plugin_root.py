"""
Deterministic plugin root detection without cwd dependency.

Handles:
- Finding plugin root from environment variable (CLAUDE_PLUGIN_ROOT)
- Finding plugin root from script location (__file__)
- Validating plugin root contains plugin.json
"""

import os
from pathlib import Path
from typing import Optional

# Marker file that identifies a valid plugin root
PLUGIN_MARKER = ".claude-plugin/plugin.json"

# Maximum depth to search upward for plugin root
MAX_PLUGIN_SEARCH_DEPTH = 20


def find_plugin_root_from_env() -> Optional[Path]:
    """
    Check CLAUDE_PLUGIN_ROOT environment variable if set and valid.

    Returns:
        Path to plugin root if env var is set and valid, None otherwise
    """
    env_root = os.environ.get("CLAUDE_PLUGIN_ROOT", "")
    if not env_root:
        return None

    path = Path(env_root)
    if validate_plugin_root(path):
        return path

    return None


def find_plugin_root_from_script(script_path: Path) -> Optional[Path]:
    """
    Walk up from script location to find .claude-plugin/plugin.json.

    This allows scripts to find their plugin root regardless of cwd.

    Args:
        script_path: Path to a Python script (typically __file__)

    Returns:
        Path to plugin root if found, None otherwise
    """
    try:
        resolved = script_path.resolve()
    except (OSError, RuntimeError):
        return None

    # Start from the script's directory (or itself if it's a directory)
    current = resolved if resolved.is_dir() else resolved.parent

    depth = 0
    while depth < MAX_PLUGIN_SEARCH_DEPTH:
        if validate_plugin_root(current):
            return current

        parent = current.parent
        if parent == current:
            # Reached filesystem root
            break
        current = parent
        depth += 1

    return None


def find_plugin_root(script_path: Optional[Path] = None) -> Optional[Path]:
    """
    Find plugin root using all available strategies.

    Order of preference:
    1. CLAUDE_PLUGIN_ROOT environment variable (if valid)
    2. Walk up from script_path (if provided)

    Args:
        script_path: Optional path to script for detection (use __file__)

    Returns:
        Path to plugin root if found, None otherwise
    """
    # Strategy 1: Environment variable
    root = find_plugin_root_from_env()
    if root:
        return root

    # Strategy 2: From script location
    if script_path:
        root = find_plugin_root_from_script(script_path)
        if root:
            return root

    return None


def validate_plugin_root(path: Path) -> bool:
    """
    Check that path contains .claude-plugin/plugin.json.

    Args:
        path: Path to validate as plugin root

    Returns:
        True if path is a valid plugin root, False otherwise
    """
    marker = path / PLUGIN_MARKER
    return marker.exists() and marker.is_file()


def get_plugin_root_or_die(script_path: Optional[Path] = None) -> Path:
    """
    Get plugin root or exit with helpful error message.

    Args:
        script_path: Optional path to script for detection

    Returns:
        Path to plugin root

    Raises:
        SystemExit: If plugin root cannot be found
    """
    root = find_plugin_root(script_path)
    if root:
        return root

    # Build helpful error message
    env_hint = os.environ.get("CLAUDE_PLUGIN_ROOT", "(not set)")
    print("Error: Could not find plugin root", file=__import__("sys").stderr)
    print("", file=__import__("sys").stderr)
    print("Searched for:", file=__import__("sys").stderr)
    print(f"  - CLAUDE_PLUGIN_ROOT env var: {env_hint}", file=__import__("sys").stderr)
    if script_path:
        print(f"  - Plugin marker from script: {script_path}", file=__import__("sys").stderr)
    print("", file=__import__("sys").stderr)
    print("Solution A: Set environment variable", file=__import__("sys").stderr)
    print("  export CLAUDE_PLUGIN_ROOT=/path/to/plugin", file=__import__("sys").stderr)
    print("", file=__import__("sys").stderr)
    print("Solution B: Run from within the plugin directory", file=__import__("sys").stderr)
    __import__("sys").exit(1)
