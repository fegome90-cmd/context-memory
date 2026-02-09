#!/usr/bin/env python3
"""
Install context-memory commands and hooks in a repository.

Usage:
    python3 cm_install.py [--repo PATH]
"""

import argparse
import json
import shutil
import sys
from pathlib import Path

# Add src to path
plugin_dir = Path(__file__).parent.parent
sys.path.insert(0, str(plugin_dir / "src"))

from infrastructure.repo import detect_repo


def install_commands(repo_root: Path, force: bool = False) -> None:
    """Install command templates to .claude/commands."""
    plugin_dir = Path(__file__).parent.parent
    templates_dir = plugin_dir / "templates" / "commands"
    commands_dir = repo_root / ".claude" / "commands"

    if not templates_dir.exists():
        print("Error: Command templates not found", file=sys.stderr)
        sys.exit(1)

    # Create commands directory
    commands_dir.mkdir(parents=True, exist_ok=True)

    # Copy command templates
    templates = {
        "cm-init.md": "cm-init.md",
        "cm-status.md": "cm-status.md",
        "cm-context.md": "cm-context.md",
        "cm-save.md": "cm-save.md",
        "cm-load.md": "cm-load.md",
        "cm-prune.md": "cm-prune.md",
        "cm-track.md": "cm-track.md",
        "cm-multi-review.md": "cm-multi-review.md",
    }

    for src, dst in templates.items():
        src_path = templates_dir / src
        dst_path = commands_dir / dst

        if dst_path.exists() and not force:
            print(f"  Skipping {dst} (exists)")
            continue

        shutil.copy2(src_path, dst_path)
        print(f"  ✓ Installed {dst}")


def install_hooks(repo_root: Path, merge: bool = True) -> None:
    """Install hooks to .claude/settings.local.json (correct location for Claude Code).

    NOTE: Claude Code reads hooks from settings.json files, NOT from hooks.json.
    We use settings.local.json so hooks are not committed to git.
    The plugin's own hooks/hooks.json is loaded automatically when the plugin is enabled.
    This function adds a fallback hook entry at the project level.
    """
    settings_path = repo_root / ".claude" / "settings.local.json"

    # Use absolute path to the plugin script as fallback
    plugin_dir = Path(__file__).parent.parent
    script_path = plugin_dir / "scripts" / "cm_track_operation.py"

    new_hooks = {
        "hooks": {
            "PostToolUse": [
                {
                    "matcher": "Read|Write|Edit|MultiEdit",
                    "hooks": [
                        {
                            "type": "command",
                            "command": f"python3 {script_path}",
                        }
                    ],
                }
            ]
        }
    }

    if settings_path.exists() and merge:
        # Merge with existing settings
        with open(settings_path, "r") as f:
            existing_settings = json.load(f)

        # Add or replace hooks section
        existing_settings["hooks"] = new_hooks["hooks"]

        with open(settings_path, "w") as f:
            json.dump(existing_settings, f, indent=2)

        print(f"  ✓ Merged hooks into settings.local.json")
    else:
        # Create new settings.local.json
        settings_path.parent.mkdir(parents=True, exist_ok=True)
        with open(settings_path, "w") as f:
            json.dump(new_hooks, f, indent=2)

        print(f"  ✓ Created settings.local.json with hooks")


def init_storage(repo_root: Path) -> None:
    """Initialize storage directories."""
    sessions_dir = repo_root / ".claude" / "context_memory" / "sessions"
    bundles_dir = repo_root / ".claude" / "context_memory" / "bundles"
    cas_dir = repo_root / ".claude" / "context_memory" / "cas"

    sessions_dir.mkdir(parents=True, exist_ok=True)
    bundles_dir.mkdir(parents=True, exist_ok=True)
    cas_dir.mkdir(parents=True, exist_ok=True)

    print(f"  ✓ Initialized storage")


def main():
    parser = argparse.ArgumentParser(description="Install context-memory in a repository")
    parser.add_argument("--repo", type=Path, help="Repository path (default: current dir)")
    parser.add_argument("--force", action="store_true", help="Overwrite existing commands")
    parser.add_argument("--no-merge", action="store_true", help="Don't merge existing hooks")
    args = parser.parse_args()

    # Detect repo
    if args.repo:
        repo_root = args.repo.resolve()
        # Verify it's a valid repo
        if not (repo_root / ".git").exists():
            print(f"Warning: {repo_root} doesn't appear to be a git repository", file=sys.stderr)
    else:
        repo_info = detect_repo()
        if not repo_info:
            print("Error: Not in a git repository", file=sys.stderr)
            sys.exit(1)
        repo_root = repo_info.root

    print(f"Installing context-memory to: {repo_root}")
    print()

    # Install components
    print("Installing commands:")
    install_commands(repo_root, force=args.force)

    print("\nInstalling hooks:")
    install_hooks(repo_root, merge=not args.no_merge)

    print("\nInitializing storage:")
    init_storage(repo_root)

    print()
    print("="*60)
    print("Installation complete!")
    print()
    print("Available commands:")
    print("  /cm-init         - Initialize context memory in a repo")
    print("  /cm-status       - Show context memory status")
    print("  /cm-context      - Show current session summary")
    print("  /cm-save         - Save a pruned bundle")
    print("  /cm-load         - Load and display a bundle")
    print("  /cm-prune        - Prune current session")
    print("  /cm-track        - Track an operation manually")
    print("  /cm-multi-review - Multi-agent code review")
    print()
    print("Tracking is now active. Work normally and use")
    print("commands to save/load context bundles.")
    print("="*60)


if __name__ == "__main__":
    main()
