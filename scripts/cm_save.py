#!/usr/bin/env python3
"""
Save a pruned bundle from current session.

Usage:
    python3 cm_save.py <bundle-name> [--max-ops N]
"""

import argparse
import json
import sys
import os
from datetime import datetime
from pathlib import Path

# Add src to path
plugin_dir = Path(__file__).parent.parent
sys.path.insert(0, str(plugin_dir / "src"))

from domain.pruning import PruningConfig, prune
from infrastructure.jsonl_io import write_jsonl
from infrastructure.repo import detect_repo
from infrastructure.storage_jsonl import JSONLStorage


def main():
    parser = argparse.ArgumentParser(description="Save a pruned context bundle")
    parser.add_argument("name", help="Bundle name")
    parser.add_argument("--max-ops", type=int, default=20, help="Max operations in bundle")
    parser.add_argument("--max-bytes", type=int, default=120_000, help="Max estimated bytes")
    args = parser.parse_args()

    # Detect repo
    repo_info = detect_repo()
    if not repo_info:
        print("Error: Not in a git repository", file=sys.stderr)
        sys.exit(1)

    # Setup paths
    sessions_dir = repo_info.root / ".claude" / "context_memory" / "sessions"
    bundles_dir = repo_info.root / ".claude" / "context_memory" / "bundles"
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


def update_indexes(repo_info, bundle_name: str, ops_count: int, bytes_est: int, bundles_dir: Path) -> None:
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
