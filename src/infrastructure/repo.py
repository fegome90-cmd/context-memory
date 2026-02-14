"""
Repository detection and stable ID generation.

Handles:
- Finding repo root (.git, or fallback)
- Generating stable repo IDs
- Reading/writing .claude/context-memory-id
"""

import hashlib
import sys
from pathlib import Path
from typing import Optional
from dataclasses import dataclass
import uuid

# Add parent src to path for imports
src_dir = Path(__file__).parent.parent
if str(src_dir) not in sys.path:
    sys.path.insert(0, str(src_dir))


REPO_ID_FILE = ".claude/context-memory-id"
MAX_REPO_SEARCH_DEPTH = 20


def find_repo_root_from_path(file_path: Path) -> Optional[Path]:
    """
    Find the repository root by searching upward from a file path.

    Unlike find_repo_root() which uses cwd, this function starts from
    the given file_path and walks up the directory tree looking for .git.
    This is critical for hooks where cwd is NOT the project directory.

    Args:
        file_path: Absolute path to a file or directory

    Returns:
        Path to repository root (the dir containing .git), or None if not found

    Note:
        - Resolves symlinks on the input path for safety
        - Has a depth limit of MAX_REPO_SEARCH_DEPTH to avoid infinite loops
        - Only checks for .git directories (not .git files for worktrees)
    """
    try:
        resolved = file_path.resolve()
    except (OSError, RuntimeError):
        return None

    # If it's a file, start from its parent directory
    current = resolved if resolved.is_dir() else resolved.parent

    depth = 0
    while depth < MAX_REPO_SEARCH_DEPTH:
        git_dir = current / ".git"
        if git_dir.exists() and git_dir.is_dir():
            return current

        parent = current.parent
        if parent == current:
            # Reached filesystem root
            break
        current = parent
        depth += 1

    return None


def detect_repo_from_file_path(file_path: Path) -> Optional["RepoInfo"]:
    """
    Detect repository information starting from a file path.

    Wrapper around find_repo_root_from_path that returns a full RepoInfo,
    compatible with detect_repo() return type.

    Args:
        file_path: Absolute path to a file inside a repository

    Returns:
        RepoInfo if a repo is found, None otherwise
    """
    root = find_repo_root_from_path(file_path)
    if not root:
        return None

    repo_id = generate_stable_repo_id(root)
    branch = get_current_branch(root)
    remote_url = get_git_remote_url(root)

    return RepoInfo(
        root=root,
        repo_id=repo_id,
        branch=branch,
        remote_url=remote_url,
    )


def find_repo_root(cwd: Path | None = None) -> Optional[Path]:
    """
    Find the repository root directory by searching for .git folder.

    Searches upward from start_path (or current directory) until it finds
    a .git directory or reaches the filesystem root.

    Args:
        cwd: Starting point for search (defaults to current directory)

    Returns:
        Path to repository root, or None if not found
    """
    if cwd is None:
        cwd = Path.cwd()

    current = cwd.resolve()

    # Search upward until we find .git or hit filesystem root
    while current != current.parent:
        git_dir = current / ".git"
        if git_dir.exists() and git_dir.is_dir():
            return current

        # Move up one directory
        current = current.parent

    # Check root level one last time
    if (current / ".git").exists() and (current / ".git").is_dir():
        return current

    return None


def get_git_remote_url(repo_root: Path) -> Optional[str]:
    """
    Get the git remote URL for a repository.

    Args:
        repo_root: Path to repo root

    Returns:
        Remote URL string, or None
    """
    git_dir = repo_root / ".git"

    # Check if it's a git repo
    if not git_dir.exists():
        return None

    # Try to get remote from git config
    import subprocess
    try:
        result = subprocess.run(
            ["git", "remote", "get-url", "origin"],
            cwd=repo_root,
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass

    return None


def generate_stable_repo_id(repo_root: Path) -> str:
    """
    Generate a stable repository ID.

    Strategy:
    1. If .claude/context-memory-id exists, use it
    2. If git remote exists, hash(remote_url + root)
    3. Otherwise, generate UUID and save to file

    Args:
        repo_root: Path to repo root

    Returns:
        10-character hex string (stable ID)
    """
    # 1. Check for existing ID file
    id_file = repo_root / REPO_ID_FILE
    if id_file.exists():
        existing_id = id_file.read_text().strip()
        if existing_id:
            return existing_id

    # 2. Try git remote-based ID
    remote_url = get_git_remote_url(repo_root)
    if remote_url:
        # Hash remote + root path
        data = f"{remote_url}:{repo_root}"
        repo_id = hashlib.sha256(data.encode()).hexdigest()[:10]
    else:
        # 3. Fallback: random UUID
        repo_id = uuid.uuid4().hex[:10]

    # Save to file for persistence
    id_file.parent.mkdir(parents=True, exist_ok=True)
    id_file.write_text(repo_id + "\n")

    return repo_id


def get_current_branch(repo_root: Path) -> Optional[str]:
    """
    Get the current git branch name.

    Args:
        repo_root: Path to repo root

    Returns:
        Branch name, or None
    """
    import subprocess
    try:
        result = subprocess.run(
            ["git", "branch", "--show-current"],
            cwd=repo_root,
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass

    return None


@dataclass
class RepoInfo:
    """Information about a repository."""
    root: Path
    repo_id: str
    branch: Optional[str] = None
    remote_url: Optional[str] = None

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "root": str(self.root),
            "repo_id": self.repo_id,
            "branch": self.branch,
            "remote_url": self.remote_url,
        }


def detect_repo(cwd: Path | None = None) -> Optional[RepoInfo]:
    """
    Detect repository information from current working directory.

    Args:
        cwd: Starting directory (default: current working dir)

    Returns:
        RepoInfo if detected, None otherwise
    """
    root = find_repo_root(cwd)
    if not root:
        return None

    repo_id = generate_stable_repo_id(root)
    branch = get_current_branch(root)
    remote_url = get_git_remote_url(root)

    return RepoInfo(
        root=root,
        repo_id=repo_id,
        branch=branch,
        remote_url=remote_url,
    )
