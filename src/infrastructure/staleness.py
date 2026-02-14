"""Staleness detection for context bundles."""

import hashlib
from pathlib import Path
from typing import Optional
from dataclasses import dataclass


def get_repo_rev(repo_root: Path) -> Optional[str]:
    """Get current git commit hash (short)."""
    import subprocess

    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
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


def is_repo_dirty(repo_root: Path) -> bool:
    """Check if repo has uncommitted changes."""
    import subprocess

    try:
        result = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=repo_root,
            capture_output=True,
            text=True,
            timeout=5,
        )
        return bool(result.stdout.strip())
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


def get_focus_dirs_hash(repo_root: Path, focus_dirs: list[str]) -> Optional[str]:
    """Get hash of focus directories' files."""
    hasher = hashlib.sha256()

    for d in focus_dirs:
        dir_path = repo_root / d
        if not dir_path.exists():
            continue
        try:
            for f in dir_path.rglob("*"):
                if f.is_file():
                    hasher.update(str(f.relative_to(repo_root)).encode())
                    hasher.update(str(f.stat().st_mtime).encode())
        except Exception:
            pass

    return hasher.hexdigest()[:8] if hasher.digest_size > 0 else None


@dataclass
class StalenessInfo:
    """Staleness assessment for a bundle."""

    risk: str
    reason: str
    repo_rev: Optional[str] = None
    is_dirty: bool = False
    focus_hash: Optional[str] = None


def assess_staleness(
    repo_root: Path,
    bundle_ts: int,
    focus_dirs: list[str],
    saved_rev: Optional[str] = None,
    saved_focus_hash: Optional[str] = None,
) -> StalenessInfo:
    """Assess how stale a bundle might be."""
    import time

    current_rev = get_repo_rev(repo_root)
    dirty = is_repo_dirty(repo_root)
    current_focus_hash = get_focus_dirs_hash(repo_root, focus_dirs)

    if current_rev is None:
        return StalenessInfo(risk="unknown", reason="No git repository")

    if saved_rev and current_rev != saved_rev:
        return StalenessInfo(
            risk="high",
            reason=f"Commit changed: {saved_rev} -> {current_rev}",
            repo_rev=current_rev,
            is_dirty=dirty,
            focus_hash=current_focus_hash,
        )

    if dirty:
        return StalenessInfo(
            risk="high",
            reason="Repository has uncommitted changes",
            repo_rev=current_rev,
            is_dirty=True,
            focus_hash=current_focus_hash,
        )

    if saved_focus_hash and current_focus_hash != saved_focus_hash:
        return StalenessInfo(
            risk="medium",
            reason="Focus directories have changed",
            repo_rev=current_rev,
            is_dirty=dirty,
            focus_hash=current_focus_hash,
        )

    age_hours = (time.time() - bundle_ts) / 3600
    if age_hours > 24:
        return StalenessInfo(
            risk="medium",
            reason=f"Bundle is {age_hours:.1f}h old",
            repo_rev=current_rev,
            is_dirty=dirty,
            focus_hash=current_focus_hash,
        )

    return StalenessInfo(
        risk="low",
        reason="No significant changes detected",
        repo_rev=current_rev,
        is_dirty=dirty,
        focus_hash=current_focus_hash,
    )
