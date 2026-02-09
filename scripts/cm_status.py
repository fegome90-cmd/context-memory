#!/usr/bin/env python3
"""
Show context memory status for current repository.

Usage:
    python3 cm_status.py [--verbose]
"""

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

# Add src to path
plugin_dir = Path(__file__).parent.parent
sys.path.insert(0, str(plugin_dir / "src"))

from infrastructure.repo import detect_repo
from infrastructure.storage_jsonl import JSONLStorage


def main():
    parser = argparse.ArgumentParser(description="Show context memory status")
    parser.add_argument("-v", "--verbose", action="store_true", help="Verbose output")
    args = parser.parse_args()

    # Detect repo
    repo_info = detect_repo()
    if not repo_info:
        print("Error: Not in a git repository", file=sys.stderr)
        sys.exit(1)

    # Setup paths
    sessions_dir = repo_info.root / ".claude" / "context_memory" / "sessions"
    bundles_dir = repo_info.root / ".claude" / "context_memory" / "bundles"

    # Header
    print("="*60)
    print("Context Memory Status")
    print("="*60)
    print(f"Repo: {repo_info.root.name}")
    print(f"ID: {repo_info.repo_id}")
    if repo_info.branch:
        print(f"Branch: {repo_info.branch}")
    if repo_info.remote_url:
        print(f"Remote: {repo_info.remote_url}")
    print()

    # Current session
    current_storage = JSONLStorage(sessions_dir / "current.jsonl")
    current_count = current_storage.count()
    current_bytes = current_storage.path.stat().st_size if current_storage.exists() else 0

    print("Current Session:")
    print(f"  Events: {current_count}")
    print(f"  Size: {current_bytes:,} bytes")
    print()

    # Bundles - try to read from local index first
    local_index_path = repo_info.root / ".claude" / "context_memory" / "index.json"
    has_local_index = local_index_path.exists()

    if has_local_index:
        with open(local_index_path, "r") as f:
            local_index = json.load(f)
        bundles_data = local_index.get("bundles", {})
        print(f"Bundles ({len(bundles_data)}):")
        for name, data in bundles_data.items():
            mtime = datetime.fromtimestamp(data["ts"]).strftime('%Y-%m-%d %H:%M')
            print(f"  {name}:")
            print(f"    Events: {data['ops_count']}")
            print(f"    Size: {data['bytes_est']:,} bytes")
            print(f"    Modified: {mtime}")
            if not data.get("exists", True):
                print("    ⚠️  File missing!")
    elif bundles_dir.exists():
        bundles = sorted(bundles_dir.glob("*.jsonl"))
        print(f"Bundles ({len(bundles)}):")
        for bundle_path in bundles:
            bundle_storage = JSONLStorage(bundle_path)
            count = bundle_storage.count()
            mtime = datetime.fromtimestamp(bundle_path.stat().st_mtime)
            size = bundle_path.stat().st_size
            print(f"  {bundle_path.stem}:")
            print(f"    Events: {count}")
            print(f"    Size: {size:,} bytes")
            print(f"    Modified: {mtime.strftime('%Y-%m-%d %H:%M')}")
        print("  (No local index - run /cm-save to create one)")
    else:
        print("No bundles saved yet")

    print()

    # Recent global entries (last 10)
    plugin_dir = Path(__file__).parent.parent
    index_path = plugin_dir / "index.jsonl"

    if index_path.exists():
        print("Recent bundles (global index):")

        with open(index_path, "r") as f:
            lines = f.readlines()

        # Get last 10 lines
        for line in lines[-10:]:
            try:
                entry = json.loads(line)
                ts = datetime.fromtimestamp(entry["ts"]).strftime("%Y-%m-%d %H:%M")
                print(f"  [{ts}] {entry['bundle_name']} ({entry['repo_id']}) - {entry['ops_count']} ops")
            except (json.JSONDecodeError, KeyError):
                continue

    print()


if __name__ == "__main__":
    main()
