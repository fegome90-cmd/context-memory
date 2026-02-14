#!/usr/bin/env python3
"""
Prune current.jsonl session in-place.

Usage:
    python3 cm_prune.py [--max-ops N] [--max-bytes N]
"""

import argparse
import sys
from pathlib import Path

# Add src to path
plugin_dir = Path(__file__).parent.parent
sys.path.insert(0, str(plugin_dir / "src"))

from domain.pruning import PruningConfig, prune
from infrastructure.jsonl_io import write_jsonl
from infrastructure.repo import detect_repo, find_repo_root_from_path
from infrastructure.storage_jsonl import JSONLStorage


def main():
    # Get plugin_dir inside function to avoid scoping issues
    plugin_dir = Path(__file__).parent.parent

    parser = argparse.ArgumentParser(description="Prune current session")
    parser.add_argument("--max-ops", type=int, default=20, help="Max operations")
    parser.add_argument(
        "--max-bytes", type=int, default=120_000, help="Max estimated bytes"
    )
    parser.add_argument(
        "--in-place", action="store_true", help="Modify current.jsonl in place"
    )
    args = parser.parse_args()

    # Detect repo (with fallback to find from plugin_dir)
    repo_info = None
    repo_root = find_repo_root_from_path(plugin_dir)
    if not repo_root:
        repo_info = detect_repo()
        if not repo_info:
            print("Error: Not in a git repository", file=sys.stderr)
            sys.exit(1)
        repo_root = repo_info.root
    else:
        # Ensure we have repo_info for operations
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
    sessions_dir = repo_info.root / ".claude" / "context_memory" / "sessions"
    current_path = sessions_dir / "current.jsonl"

    if not current_path.exists():
        print("No current session to prune")
        sys.exit(0)

    # Read current
    storage = JSONLStorage(current_path)
    events = list(storage.read_all())

    if not events:
        print("Current session is empty")
        sys.exit(0)

    # Prune
    config = PruningConfig(max_ops=args.max_ops, max_bytes_est=args.max_bytes)
    pruned_events, report = prune(events, config)

    # Print report
    print("Pruned session:")
    print(f"  Events: {report.original_count} → {report.pruned_count}")
    print(f"  Removed: {report.removed_count}")
    print(f"  Reasons: {report.removed_reasons}")
    print(f"  Final tags: {report.final_tags}")
    print(f"  Estimated bytes: {report.total_bytes_est:,}")

    # Write output
    if args.in_place:
        # Backup original
        backup_path = current_path.with_suffix(".jsonl.bak")
        import shutil

        shutil.copy2(current_path, backup_path)
        print(f"\n✓ Backup saved to: {backup_path.name}")

        # Write pruned
        write_jsonl(current_path, pruned_events)
        print("✓ Pruned current.jsonl in place")
    else:
        # Write to new file
        output_path = current_path.with_suffix(".pruned.jsonl")
        write_jsonl(output_path, pruned_events)
        print(f"\n✓ Pruned session saved to: {output_path.name}")
        print("  To replace current.jsonl:")
        print(f"    mv {output_path.name} current.jsonl")


if __name__ == "__main__":
    main()
