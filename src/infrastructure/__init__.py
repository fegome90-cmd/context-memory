"""Infrastructure layer - adapters for IO."""

from .repo import (
    find_repo_root,
    get_git_remote_url,
    generate_stable_repo_id,
    get_current_branch,
    RepoInfo,
    detect_repo,
    REPO_ID_FILE,
)
from .storage_jsonl import JSONLStorage
from .paths import (
    normalize_path,
    validate_path,
    get_relative_path,
    join_paths,
)
from .cas import (
    CAS,
    compute_sha256,
)

__all__ = [
    # Repo
    "find_repo_root",
    "get_git_remote_url",
    "generate_stable_repo_id",
    "get_current_branch",
    "RepoInfo",
    "detect_repo",
    "REPO_ID_FILE",
    # Storage
    "JSONLStorage",
    # Paths
    "normalize_path",
    "validate_path",
    "get_relative_path",
    "join_paths",
    # CAS
    "CAS",
    "compute_sha256",
]
