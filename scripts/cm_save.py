#!/usr/bin/env python3
"""
Save a pruned bundle from current session.

Usage:
    python3 cm_save.py <bundle-name> [--max-ops N]
"""

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

# Add src to path
plugin_dir = Path(__file__).parent.parent
sys.path.insert(0, str(plugin_dir / "src"))

from domain.events import OperationType
from domain.pruning import PruningConfig, prune
from infrastructure.jsonl_io import write_jsonl
from infrastructure.repo import detect_repo, find_repo_root_from_path
from infrastructure.storage_jsonl import JSONLStorage


# Checkpoint constants (from CHECKPOINT_SPEC.md)
MAX_CHECKPOINT_LINE_LEN = 280


def generate_checkpoint(events: list, pruned_events: list) -> str:
    """
    Generate checkpoint from events.

    Format:
        CHK: <objective> | DONE: <n> | NEXT: <n>
        FOCUS: <dir1>,<dir2> | EVID: <PASS/FAIL/n-a>

    Returns:
        Checkpoint string (max 2 lines, 280 chars each)
    """
    if not events:
        return "CHK: n/a | DONE: n/a | NEXT: n/a\nFOCUS: n/a | EVID: n-a"

    # Calculate DONE (work signal)
    has_write = any(
        e.operation
        in (OperationType.WRITE, OperationType.EDIT, OperationType.MULTI_EDIT)
        for e in pruned_events
    )
    has_read = any(e.operation == OperationType.READ for e in pruned_events)

    if has_write:
        done = "edited"
    elif has_read:
        done = "reviewed"
    else:
        done = "n/a"

    # Calculate NEXT (resume point)
    last_event = pruned_events[-1] if pruned_events else None
    if last_event and last_event.file_path:
        # Extract dir from file_path
        parts = last_event.file_path.split("/")
        next_dir = parts[0] if parts else "n/a"
        next_line = f"resume in {next_dir}"
    else:
        next_line = "n/a"

    # Calculate FOCUS (top dirs by score)
    dir_scores: dict[str, float] = {}
    import time

    now = time.time()

    for e in events:
        if not e.file_path:
            continue
        dir_name = e.file_path.split("/")[0] if "/" in e.file_path else "root"

        # Score: op_type weight + recency
        op_weight = (
            3.0
            if e.operation
            in (OperationType.WRITE, OperationType.EDIT, OperationType.MULTI_EDIT)
            else 1.0
        )
        recency = max(0, 10 - (now - e.ts) / 3600)  # Decay over hour
        score = op_weight + recency

        dir_scores[dir_name] = dir_scores.get(dir_name, 0) + score

    # Top 3 dirs
    top_dirs = sorted(dir_scores.items(), key=lambda x: x[1], reverse=True)[:3]
    focus = ",".join([d[0] for d in top_dirs]) if top_dirs else "n/a"

    # EVID (evidence) - no gates info in events, use n-a
    evid = "n-a"

    # Build checkpoint
    line1 = f"CHK: work in progress | DONE: {done} | NEXT: {next_line}"
    line2 = f"FOCUS: {focus} | EVID: {evid}"

    # Truncate if needed
    line1 = line1[:MAX_CHECKPOINT_LINE_LEN]
    line2 = line2[:MAX_CHECKPOINT_LINE_LEN]

    return f"{line1}\n{line2}"


def write_checkpoint_atomic(
    bundle_dir: Path, bundle_name: str, checkpoint: str
) -> Path:
    """Write checkpoint atomically (write to .tmp then rename)."""
    checkpoint_path = bundle_dir / f"{bundle_name}.checkpoint.txt"
    tmp_path = checkpoint_path.with_suffix(".tmp")

    # Write to tmp first
    with open(tmp_path, "w") as f:
        f.write(checkpoint)

    # Atomic rename
    tmp_path.rename(checkpoint_path)

    return checkpoint_path


def main():
    parser = argparse.ArgumentParser(description="Save a pruned context bundle")
    parser.add_argument("name", help="Bundle name")
    parser.add_argument(
        "--max-ops", type=int, default=20, help="Max operations in bundle"
    )
    parser.add_argument(
        "--max-bytes", type=int, default=120_000, help="Max estimated bytes"
    )
    args = parser.parse_args()

    # Detect repo
    repo_info = None
    repo_root = find_repo_root_from_path(plugin_dir)
    if not repo_root:
        repo_info = detect_repo()
        if not repo_info:
            print("Error: Not in a git repository", file=sys.stderr)
            sys.exit(1)
        repo_root = repo_info.root

    # Ensure we have repo_info for index updates
    if repo_info is None:
        repo_info = detect_repo()
        if not repo_info:
            # Create minimal repo_info-like object
            class MinimalRepoInfo:
                def __init__(self, root):
                    self.root = root
                    self.branch = None
                    self.repo_id = None
                    self.remote_url = None

            repo_info = MinimalRepoInfo(repo_root)

    # Setup paths
    sessions_dir = repo_root / ".claude" / "context_memory" / "sessions"
    bundles_dir = repo_root / ".claude" / "context_memory" / "bundles"
    bundles_dir.mkdir(parents=True, exist_ok=True)

    # Read current session
    current_storage = JSONLStorage(sessions_dir / "current.jsonl")
    events = list(current_storage.read_all())

    if not events:
        print("No events in current session to save")
        sys.exit(0)

    # Prune
    config = PruningConfig(max_ops=args.max_ops, max_bytes_est=args.max_bytes)
    pruned_events, report = prune(events, config)

    # Write bundle
    bundle_path = bundles_dir / f"{args.name}.jsonl"
    write_jsonl(bundle_path, pruned_events)

    # Generate and write checkpoint (atomic)
    checkpoint = generate_checkpoint(events, pruned_events)
    checkpoint_path = write_checkpoint_atomic(bundles_dir, args.name, checkpoint)
    print(f"  Checkpoint: {checkpoint_path.name}")

    # Update indexes (both local and global)
    update_indexes(
        repo_info=repo_info,
        bundle_name=args.name,
        ops_count=report.pruned_count,
        bytes_est=report.total_bytes_est,
        bundles_dir=bundles_dir,
    )

    # Print summary
    print(f"✓ Bundle saved: {args.name}")
    print(f"  Events: {report.original_count} → {report.pruned_count}")
    print(f"  Estimated bytes: {report.total_bytes_est:,}")
    print(f"  Tags: {report.final_tags}")


def update_indexes(
    repo_info, bundle_name: str, ops_count: int, bytes_est: int, bundles_dir: Path
) -> None:
    """Update both local and global indexes."""
    branch = repo_info.branch or "unknown"
    timestamp = int(datetime.now().timestamp())

    # Metadata for both indexes
    metadata = {
        "ts": timestamp,
        "repo_id": repo_info.repo_id,
        "repo_root": str(repo_info.root),
        "branch": branch,
        "remote_url": repo_info.remote_url or None,
        "bundle_name": bundle_name,
        "ops_count": ops_count,
        "bytes_est": bytes_est,
    }

    # 1. Update local index (in repo)
    local_index_path = repo_info.root / ".claude" / "context_memory" / "index.json"
    update_local_index(local_index_path, metadata, bundles_dir)

    # 2. Update global index (in plugin)
    plugin_dir = Path(__file__).parent.parent
    global_index_path = plugin_dir / "index.jsonl"
    with open(global_index_path, "a") as f:
        f.write(json.dumps(metadata, separators=(",", ":")) + "\n")


def update_local_index(index_path: Path, metadata: dict, bundles_dir: Path) -> None:
    """Update local JSON index with bundle metadata."""
    # Read existing or create new
    if index_path.exists():
        with open(index_path, "r") as f:
            index = json.load(f)
    else:
        index = {"bundles": {}}

    # Add/update bundle entry
    bundle_name = metadata["bundle_name"]
    index["bundles"][bundle_name] = {
        "ts": metadata["ts"],
        "ops_count": metadata["ops_count"],
        "bytes_est": metadata["bytes_est"],
        "branch": metadata["branch"],
    }

    # Verify bundle file exists
    bundle_path = bundles_dir / f"{bundle_name}.jsonl"
    index["bundles"][bundle_name]["exists"] = bundle_path.exists()

    # Write back
    with open(index_path, "w") as f:
        json.dump(index, f, indent=2)


if __name__ == "__main__":
    main()
