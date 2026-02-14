#!/usr/bin/env python3
"""
Regenerate local index from existing bundles.

Usage:
    python3 cm_reindex.py [--repo PATH]
"""

import argparse
import json
import sys
from pathlib import Path

# Add src to path
plugin_dir = Path(__file__).parent.parent
sys.path.insert(0, str(plugin_dir / "src"))

from infrastructure.repo import (
    detect_repo,
    find_repo_root_from_path,
    get_current_branch,
)
from infrastructure.storage_jsonl import JSONLStorage


def main():
    parser = argparse.ArgumentParser(description="Regenerate local index from bundles")
    parser.add_argument(
        "--repo", type=Path, help="Repository path (default: auto-detect)"
    )
    args = parser.parse_args()

    if args.repo:
        repo_root = args.repo.resolve()
        if not (repo_root / ".git").exists():
            print(
                f"Warning: {repo_root} doesn't appear to be a git repository",
                file=sys.stderr,
            )
    else:
        # Try to detect from plugin directory (may be in a subdirectory of a repo)
        repo_root = find_repo_root_from_path(plugin_dir)
        if not repo_root:
            # Fallback to cwd-based detection
            repo_info = detect_repo()
            if not repo_info:
                print("Error: Not in a git repository", file=sys.stderr)
                sys.exit(1)
            repo_root = repo_info.root

    # Setup paths
    bundles_dir = repo_root / ".claude" / "context_memory" / "bundles"
    index_path = repo_root / ".claude" / "context_memory" / "index.json"

    if not bundles_dir.exists():
        print("No bundles directory found")
        sys.exit(0)

    # Find all bundles
    bundle_files = sorted(bundles_dir.glob("*.jsonl"))

    if not bundle_files:
        print("No bundles found")
        sys.exit(0)

    # Build index
    index = {"bundles": {}}

    for bundle_path in bundle_files:
        storage = JSONLStorage(bundle_path)
        count = storage.count()
        mtime = bundle_path.stat().st_mtime
        size = bundle_path.stat().st_size

        index["bundles"][bundle_path.stem] = {
            "ts": mtime,
            "ops_count": count,
            "bytes_est": size,
            "branch": get_current_branch(repo_root) or "unknown",
            "exists": True,
        }

        print(f"Indexed: {bundle_path.stem} ({count} ops, {size:,} bytes)")

    # Write index
    with open(index_path, "w") as f:
        json.dump(index, f, indent=2)

    print(f"\n✓ Local index created with {len(index['bundles'])} bundles")
    print(f"  Path: {index_path}")


if __name__ == "__main__":
    main()
