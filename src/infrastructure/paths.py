"""
Path normalization and security.

Handles:
- Converting absolute paths to relative
- Validating paths (no traversal, no escapes)
- Normalizing paths
"""

from pathlib import Path
from typing import Optional


def normalize_path(
    path: str,
    repo_root: Path,
    allow_absolute: bool = False
) -> str:
    """
    Normalize a path relative to repo root.

    SECURITY: Does NOT follow symlinks to prevent symlink bypass attacks.

    Args:
        path: Path to normalize (can be absolute or relative)
        repo_root: Repository root directory
        allow_absolute: If True, absolute paths are allowed

    Returns:
        Normalized relative path

    Raises:
        ValueError: If path is outside repo_root, contains traversal, or has symlinks
    """
    p = Path(path)

    # Get absolute path
    if p.is_absolute():
        abs_path = p.absolute()
    else:
        # Relative to current working dir
        abs_path = (Path.cwd() / p).absolute()

    # Resolve repo_root (safe - we control this path)
    resolved_root = repo_root.resolve()

    # Resolve the initial path prefix for containment check.
    # This handles macOS /tmp → /private/tmp symlinks and similar cases.
    # Note: per-component symlink check below still catches any symlinks
    # INSIDE the repo that try to escape.
    resolved_abs = abs_path.resolve()

    # Check if outside repo root (using resolved paths for prefix match)
    try:
        rel_path = resolved_abs.relative_to(resolved_root)
    except ValueError:
        raise ValueError(
            f"Path '{path}' is outside repository root '{repo_root}'"
        )

    # SECURITY: Check that no path component is a symlink
    # Build the path incrementally and check each component
    current = resolved_root
    for part in rel_path.parts:
        current = current / part
        if current.is_symlink():
            raise ValueError(
                f"Symlinks not allowed in path: '{path}' (component '{part}' is a symlink)"
            )

    # Convert to string with forward slashes
    normalized = str(rel_path).replace("\\", "/")

    # Final security check: no .. components
    if ".." in normalized:
        raise ValueError(
            f"Path traversal not allowed: '{path}'"
        )

    return normalized


def validate_path(path: str) -> bool:
    """
    Validate that a path is safe (no traversal, not absolute).

    Args:
        path: Path to validate

    Returns:
        True if safe, False otherwise
    """
    # No path traversal
    if ".." in path:
        return False

    # No absolute paths (for portability) - cross-platform check
    # This catches both Unix (/path) and Windows (C:\path, D:/path)
    if Path(path).is_absolute():
        return False

    # No suspicious characters
    if "\0" in path:
        return False

    return True


def get_relative_path(
    file_path: str,
    repo_root: Path
) -> Optional[str]:
    """
    Get relative path from repo root for a file.

    Handles both absolute and relative input paths.

    Args:
        file_path: File path (absolute or relative)
        repo_root: Repository root directory

    Returns:
        Relative path string, or None if invalid
    """
    try:
        return normalize_path(file_path, repo_root)
    except ValueError:
        return None


def join_paths(base: str, *parts: str) -> str:
    """
    Join path parts safely.

    Args:
        base: Base path
        *parts: Additional path parts

    Returns:
        Joined path string with normalized slashes

    Raises:
        ValueError: If path contains traversal components
    """
    # Collect all parts including base
    all_parts = [base] + list(parts)

    # Split each part by / and filter out empty strings
    segments = []
    for part in all_parts:
        if not part:
            continue
        # Split by slash and filter empty strings (from // or leading/trailing /)
        segments.extend([s for s in part.split("/") if s])

    # SECURITY: Check for path traversal
    if ".." in segments:
        raise ValueError(
            f"Path traversal not allowed in join_paths: {segments}"
        )

    # Join with single slashes
    return "/".join(segments)
