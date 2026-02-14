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
from infrastructure.repo import detect_repo
from infrastructure.storage_jsonl import JSONLStorage
from infrastructure.cas import compute_sha256


def main():
    parser = argparse.ArgumentParser(description="Load a context bundle")
    parser.add_argument("name", help="Bundle name")
    parser.add_argument("--execute", action="store_true", help="Execute reads (display file contents)")
    args = parser.parse_args()

    # Detect repo
    repo_info = detect_repo()
    if not repo_info:
        print("Error: Not in a git repository", file=sys.stderr)
        sys.exit(1)

    # Load bundle
    bundle_path = repo_info.root / ".claude" / "context_memory" / "bundles" / f"{args.name}.jsonl"
    if not bundle_path.exists():
        print(f"Error: Bundle '{args.name}' not found", file=sys.stderr)
        sys.exit(1)

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

    # Print plan
    print(plan.summarize())

    # Optionally execute
    if args.execute:
        print("\n" + "="*60)
        print("Executing rehydration...")
        print("="*60 + "\n")

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
