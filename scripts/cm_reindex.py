#!/usr/bin/env python3
"""
Regenerate local index from existing bundles.

Usage:
    python3 cm_reindex.py
"""

import json
import sys
from pathlib import Path

# Add src to path
plugin_dir = Path(__file__).parent.parent
sys.path.insert(0, str(plugin_dir / "src"))

from infrastructure.repo import detect_repo
from infrastructure.storage_jsonl import JSONLStorage


def main():
    # Detect repo
    repo_info = detect_repo()
    if not repo_info:
        print("Error: Not in a git repository", file=sys.stderr)
        sys.exit(1)

    # Setup paths
    bundles_dir = repo_info.root / ".claude" / "context_memory" / "bundles"
    index_path = repo_info.root / ".claude" / "context_memory" / "index.json"

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
            "branch": repo_info.branch or "unknown",
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
