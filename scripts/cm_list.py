#!/usr/bin/env python3
"""
List all available bundles across all repositories.

Usage:
    python3 cm_list.py [--all] [--repo-id REPO_ID]
"""

import argparse
import sys
from pathlib import Path
from datetime import datetime

# Add src to path
plugin_dir = Path(__file__).parent.parent
sys.path.insert(0, str(plugin_dir / "src"))


def format_bytes(size: int) -> str:
    """Format bytes in human-readable format."""
    for unit in ['B', 'KB', 'MB']:
        if size < 1024:
            return f"{size:.0f} {unit}"
        size /= 1024
    return f"{size:.1f} GB"


def format_timestamp(ts: int) -> str:
    """Format unix timestamp to readable date."""
    return datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M")


def get_index_path() -> Path:
    """Get global index path."""
    # Index is in plugin root
    return Path(__file__).parent.parent / "index.jsonl"


def list_bundles(repo_id_filter: str = None) -> int:
    """
    List all bundles from global index.

    Returns:
        Number of bundles found
    """
    index_path = get_index_path()

    if not index_path.exists():
        print("No bundles found (index does not exist)")
        return 0

    # Read index
    bundles = []
    with open(index_path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            import json
            entry = json.loads(line)
            bundles.append(entry)

    if not bundles:
        print("No bundles found (index is empty)")
        return 0

    # Filter by repo_id if specified
    if repo_id_filter:
        bundles = [b for b in bundles if b.get("repo_id") == repo_id_filter]
        if not bundles:
            print(f"No bundles found for repo: {repo_id_filter}")
            return 0

    # Sort by timestamp (newest first)
    bundles.sort(key=lambda b: b.get("ts", 0), reverse=True)

    # Group by repo
    by_repo: dict[str, list[dict]] = {}
    for bundle in bundles:
        repo_id = bundle.get("repo_id", "unknown")
        if repo_id not in by_repo:
            by_repo[repo_id] = []
        by_repo[repo_id].append(bundle)

    # Print summary
    print(f"\n{'='*70}")
    print("Context Memory Bundles")
    print(f"{'='*70}")
    print(f"Total: {len(bundles)} bundle(s) across {len(by_repo)} repo(s)\n")

    # Print by repo
    for repo_id, repo_bundles in by_repo.items():
        # Get repo info from first bundle
        first = repo_bundles[0]
        repo_root = first.get("repo_root", "unknown")
        branch = first.get("branch", "unknown")

        print(f"📁 Repo: {repo_id}")
        print(f"   Path: {repo_root}")
        print(f"   Branch: {branch}")
        print(f"   Bundles: {len(repo_bundles)}\n")

        # List bundles in this repo
        for bundle in repo_bundles:
            name = bundle.get("bundle_name", "unnamed")
            ops = bundle.get("ops_count", 0)
            bytes_est = bundle.get("bytes_est", 0)
            ts = bundle.get("ts", 0)

            print(f"   • {name}")
            print(f"     Ops: {ops}, Size: {format_bytes(bytes_est)}, Created: {format_timestamp(ts)}")

        print()  # Blank line between repos

    return len(bundles)


def main():
    parser = argparse.ArgumentParser(description="List context bundles")
    parser.add_argument("--repo-id", help="Filter by repository ID")
    args = parser.parse_args()

    count = list_bundles(repo_id_filter=args.repo_id)

    if count == 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
