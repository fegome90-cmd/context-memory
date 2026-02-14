#!/usr/bin/env python3
"""
Load and display a context bundle (rehydration plan).

Usage:
    python3 cm_load.py <bundle-name> [--execute]
"""

import argparse
import sys
from pathlib import Path

# Add src to path
plugin_dir = Path(__file__).parent.parent
sys.path.insert(0, str(plugin_dir / "src"))

from domain.plan import build_load_plan, detect_drift
from infrastructure.repo import detect_repo, find_repo_root_from_path
from infrastructure.storage_jsonl import JSONLStorage
from infrastructure.cas import compute_sha256
from infrastructure.staleness import assess_staleness


def load_checkpoint(bundle_dir: Path, bundle_name: str) -> str | None:
    """Load checkpoint file if exists."""
    checkpoint_path = bundle_dir / f"{bundle_name}.checkpoint.txt"
    if checkpoint_path.exists():
        return checkpoint_path.read_text()
    return None


def main():
    # Get plugin_dir inside function to avoid scoping issues
    plugin_dir = Path(__file__).parent.parent

    parser = argparse.ArgumentParser(description="Load a context bundle")
    parser.add_argument("name", help="Bundle name")
    parser.add_argument(
        "--execute", action="store_true", help="Execute reads (display file contents)"
    )
    parser.add_argument(
        "--minimal",
        action="store_true",
        default=True,
        help="Show checkpoint first (default)",
    )
    parser.add_argument(
        "--full", action="store_true", help="Show full rehydration plan"
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
        # Ensure we have repo_info for index reads
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

    # Load bundle
    bundle_dir = repo_info.root / ".claude" / "context_memory" / "bundles"
    bundle_path = bundle_dir / f"{args.name}.jsonl"
    if not bundle_path.exists():
        print(f"Error: Bundle '{args.name}' not found", file=sys.stderr)
        sys.exit(1)

    # Load checkpoint FIRST (contract: first line starts with CHK:)
    checkpoint = load_checkpoint(bundle_dir, args.name)
    if checkpoint:
        print("=" * 40)
        print(checkpoint.strip())
        print("=" * 40 + "\n")

        # Extract focus dirs from checkpoint for staleness check
        focus_dirs = []
        for line in checkpoint.strip().split("\n"):
            if line.startswith("FOCUS:"):
                focus_part = line.split("FOCUS:")[1].split("|")[0].strip()
                focus_dirs = [d for d in focus_part.split(",") if d and d != "n/a"]
                break
    else:
        print("CHK: n/a | DONE: n/a | NEXT: n/a")
        print("FOCUS: n/a | EVID: n-a\n")
        focus_dirs = []

    # Load saved staleness metadata from index
    saved_rev = None
    saved_focus_hash = None
    local_index_path = repo_info.root / ".claude" / "context_memory" / "index.json"
    if local_index_path.exists():
        import json

        with open(local_index_path) as f:
            local_index = json.load(f)
        bundle_meta = local_index.get("bundles", {}).get(args.name, {})
        saved_rev = bundle_meta.get("repo_rev")
        saved_focus_hash = bundle_meta.get("focus_hash")

    # Check staleness
    if focus_dirs:
        staleness = assess_staleness(
            repo_root=repo_info.root,
            bundle_ts=bundle_path.stat().st_mtime,
            focus_dirs=focus_dirs,
            saved_rev=saved_rev,
            saved_focus_hash=saved_focus_hash,
        )
        print(f"STALE_RISK: {staleness.risk.upper()} ({staleness.reason})\n")

    storage = JSONLStorage(bundle_path)
    events = list(storage.read_all())

    if not events:
        print(f"Bundle '{args.name}' is empty")
        sys.exit(0)

    # Build load plan
    plan = build_load_plan(events, bundle_name=args.name)

    # Detect drift (SHA256 mismatch)
    current_files = {}
    for event in events:
        if event.file_path and event.operation.name == "READ":
            file_path = repo_info.root / event.file_path
            if file_path.exists():
                try:
                    current_files[event.file_path] = compute_sha256(file_path)
                except Exception:
                    pass  # Skip files that can't be read

    # Map events to their SHA256
    event_shas = {}
    for event in events:
        if event.sha256 and event.file_path:
            event_shas[event.file_path] = event.sha256

    # Check for drift
    drift_warnings = detect_drift(events, current_files)

    for warning in drift_warnings:
        plan.add_warning(warning)

    # Print plan (minimal vs full)
    if args.full:
        print(plan.summarize())
    else:
        # Minimal: show top 5 files only
        read_steps = [s for s in plan.steps if s.action.value == "read"]
        print("📋 Rehydration (top files):")
        for i, step in enumerate(read_steps[:5], 1):
            print(f"   {i}. {step.path}")
        if len(read_steps) > 5:
            print(f"   ... and {len(read_steps) - 5} more")
        if plan.warnings:
            print(f"\n⚠️  Warnings: {len(plan.warnings)}")

    # Optionally execute
    if args.execute:
        print("\n" + "=" * 60)
        print("Executing rehydration...")
        print("=" * 60 + "\n")

        for step in plan.steps:
            if step.action.value == "read" and step.path:
                file_path = repo_info.root / step.path
                if file_path.exists():
                    print(f"\n📖 {step.path}")
                    print("-" * 60)
                    with open(file_path) as f:
                        for line in f:
                            print(line.rstrip())
                    print("-" * 60)
                else:
                    print(f"⚠️  File not found: {step.path}")
            elif step.action.value == "inject":
                print(f"\n💭 {step.content}")
            elif step.action.value == "warn":
                print(f"\n⚠️  {step.content}")


if __name__ == "__main__":
    main()
