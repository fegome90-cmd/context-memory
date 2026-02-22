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

from domain.events import ContextEvent, OperationType
from domain.pruning import PruningConfig, prune
from infrastructure.jsonl_io import write_jsonl
from infrastructure.repo import detect_repo, find_repo_root_from_path
from infrastructure.storage_jsonl import JSONLStorage


# Checkpoint constants (from CHECKPOINT_SPEC.md)
MAX_CHECKPOINT_LINE_LEN = 280


def extract_last_todos(events: list[ContextEvent], n: int = 3) -> list[dict]:
    """
    Extract last N TodoWrite operations from events.

    Returns list of dicts with: subject, status, description
    """
    todos = []
    for event in reversed(events):
        if event.operation == OperationType.TODO and event.tool_input:
            # Parse tool_input JSON to extract todo items
            # TodoWrite format: {"todos": [{"subject": ..., "status": ..., "description": ...}]}
            try:
                data = json.loads(event.tool_input)
                for todo in data.get("todos", []):
                    todos.append({
                        "subject": todo.get("subject", ""),
                        "status": todo.get("status", "pending"),
                        "description": todo.get("description", ""),
                    })
                    if len(todos) >= n:
                        return todos
            except json.JSONDecodeError:
                continue
    return todos


def find_latest_plan() -> str | None:
    """
    Find the most recent plan file from plan mode.

    Checks:
    1. ~/.claude/plans/ directory (global plans)

    Returns the content of the most recent plan or None.
    """
    plans_dir = Path.home() / ".claude" / "plans"
    if not plans_dir.exists():
        return None

    # Get most recent .md file (glob("*.md") already excludes .bak files)
    plan_files = sorted(
        plans_dir.glob("*.md"),
        key=lambda p: p.stat().st_mtime,
        reverse=True
    )

    if not plan_files:
        return None

    # Read the most recent plan (first 100 lines for summary)
    latest = plan_files[0]
    try:
        content = latest.read_text()
        lines = content.split("\n")[:100]  # Truncate to avoid bloat
        return "\n".join(lines)
    except OSError:
        return None


def compute_work_status(pruned_events: list[ContextEvent]) -> str:
    """Compute work status from pruned events."""
    has_write = any(
        e.operation in (OperationType.WRITE, OperationType.EDIT, OperationType.MULTI_EDIT)
        for e in pruned_events
    )
    return "edited" if has_write else "reviewed"


def generate_checkpoint(events: list[ContextEvent], pruned_events: list[ContextEvent]) -> tuple[str, list[str]]:
    """
    Generate checkpoint from events.

    Format:
        CHK: <objective> | DONE: <n> | NEXT: <n>
        FOCUS: <dir1>,<dir2> | EVID: <PASS/FAIL/n-a>

    Returns:
        Tuple of (checkpoint string, focus directories list)
    """
    if not events:
        return "CHK: n/a | DONE: n/a | NEXT: n/a\nFOCUS: n/a | EVID: n-a", []

    # Calculate DONE (work signal)
    done = compute_work_status(pruned_events)

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
    focus_dirs = [d[0] for d in top_dirs] if top_dirs else []
    focus = ",".join(focus_dirs) if focus_dirs else "n/a"

    # EVID (evidence) - no gates info in events, use n-a
    evid = "n-a"

    # Build checkpoint
    line1 = f"CHK: work in progress | DONE: {done} | NEXT: {next_line}"
    line2 = f"FOCUS: {focus} | EVID: {evid}"

    # Truncate if needed
    line1 = line1[:MAX_CHECKPOINT_LINE_LEN]
    line2 = line2[:MAX_CHECKPOINT_LINE_LEN]

    return f"{line1}\n{line2}", focus_dirs


def generate_enhanced_handoff_card(
    bundle_name: str,
    focus_dirs: str,
    status: str,
    todos: list[dict],
    plan_content: str | None,
    checkpoint: str,
) -> str:
    """
    Generate comprehensive handoff card with all session context.

    Args:
        bundle_name: Name of the saved bundle
        focus_dirs: Comma-separated focus directories
        status: Work status from checkpoint
        todos: List of last N todos (from extract_last_todos)
        plan_content: Content of latest plan file (or None)
        checkpoint: Checkpoint string

    Returns:
        Formatted handoff card string with box drawing characters
    """
    CARD_WIDTH = 51  # Total width including borders
    INNER_WIDTH = CARD_WIDTH - 2  # Space for content between │ chars

    def format_line(content: str) -> str:
        """Format a line with proper padding."""
        # Truncate if too long
        if len(content) > INNER_WIDTH - 2:
            content = content[:INNER_WIDTH - 5] + "..."
        return f"│ {content:<{INNER_WIDTH - 2}}│"

    lines = []
    lines.append("┌" + "─" * (CARD_WIDTH - 2) + "┐")

    # Header section
    lines.append(format_line(f"HANDOFF: {bundle_name}"))
    lines.append(format_line(f"Focus: {focus_dirs} | Status: {status}"))
    lines.append("├" + "─" * (CARD_WIDTH - 2) + "┤")

    # Plan section
    if plan_content:
        lines.append(format_line("LAST PLAN (summary)"))
        plan_lines = plan_content.split("\n")[:8]  # First 8 lines
        for pl in plan_lines:
            if pl.strip():  # Skip empty lines
                lines.append(format_line(pl))
        lines.append("├" + "─" * (CARD_WIDTH - 2) + "┤")

    # Todos section
    if todos:
        lines.append(format_line("LAST TODOS"))
        for i, todo in enumerate(todos[:3], 1):
            checkbox = "x" if todo["status"] == "completed" else " "
            subject = todo["subject"][:38]  # Leave room for numbering
            lines.append(format_line(f"{i}. [{checkbox}] {subject}"))
        lines.append("├" + "─" * (CARD_WIDTH - 2) + "┤")

    # Checkpoint section
    lines.append(format_line("CHECKPOINT"))
    for cp_line in checkpoint.split("\n"):
        lines.append(format_line(cp_line))
    lines.append("├" + "─" * (CARD_WIDTH - 2) + "┤")

    # Resume command
    lines.append(format_line("COPY-PASTE TO NEXT AGENT:"))
    lines.append(format_line(f"Load context bundle '{bundle_name}'"))
    lines.append(format_line(f"Use: /cm-load {bundle_name}"))
    lines.append("└" + "─" * (CARD_WIDTH - 2) + "┘")

    return "\n".join(lines)


def write_checkpoint_atomic(
    bundle_dir: Path, bundle_name: str, checkpoint: str
) -> Path:
    """Write checkpoint atomically (write to .tmp then rename)."""
    checkpoint_path = bundle_dir / f"{bundle_name}.checkpoint.txt"
    tmp_path = checkpoint_path.with_suffix(".tmp")

    try:
        # Write to tmp first
        with open(tmp_path, "w") as f:
            f.write(checkpoint)

        # Atomic rename
        tmp_path.rename(checkpoint_path)
    except OSError:
        # Clean up tmp file on failure
        if tmp_path.exists():
            tmp_path.unlink()
        raise

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
    context_memory_dir = repo_root / ".claude" / "context_memory"
    sessions_dir = context_memory_dir / "sessions"
    bundles_dir = context_memory_dir / "bundles"
    context_memory_dir.mkdir(parents=True, exist_ok=True)
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
    checkpoint, focus_dirs = generate_checkpoint(events, pruned_events)
    checkpoint_path = write_checkpoint_atomic(bundles_dir, args.name, checkpoint)
    print(f"  Checkpoint: {checkpoint_path.name}")

    # Get repo state for staleness tracking
    from infrastructure.staleness import get_repo_rev, get_focus_dirs_hash

    repo_rev = get_repo_rev(repo_root)
    focus_hash = get_focus_dirs_hash(repo_root, focus_dirs) if focus_dirs else None

    # Update indexes (both local and global)
    update_indexes(
        repo_info=repo_info,
        bundle_name=args.name,
        ops_count=report.pruned_count,
        bytes_est=report.total_bytes_est,
        bundles_dir=bundles_dir,
        repo_rev=repo_rev,
        focus_hash=focus_hash,
    )

    # Print summary
    print(f"✓ Bundle saved: {args.name}")
    print(f"  Events: {report.original_count} → {report.pruned_count}")
    print(f"  Estimated bytes: {report.total_bytes_est:,}")
    print(f"  Tags: {report.final_tags}")

    # Compute status for handoff using shared function
    status = compute_work_status(pruned_events)
    focus_display = ",".join(focus_dirs) if focus_dirs else "n/a"

    # Extract session state for enhanced handoff card
    todos = extract_last_todos(events, n=3)
    plan_content = find_latest_plan()

    # Generate and print enhanced handoff card
    handoff_card = generate_enhanced_handoff_card(
        bundle_name=args.name,
        focus_dirs=focus_display,
        status=status,
        todos=todos,
        plan_content=plan_content,
        checkpoint=checkpoint,
    )
    print(handoff_card)


def update_indexes(
    repo_info,
    bundle_name: str,
    ops_count: int,
    bytes_est: int,
    bundles_dir: Path,
    repo_rev: str | None = None,
    focus_hash: str | None = None,
) -> None:
    """Update both local and global indexes."""
    branch = repo_info.branch or "unknown"
    timestamp = int(datetime.now().timestamp())

    # Metadata for both indexes (includes staleness tracking)
    metadata = {
        "ts": timestamp,
        "repo_id": repo_info.repo_id,
        "repo_root": str(repo_info.root),
        "branch": branch,
        "remote_url": repo_info.remote_url or None,
        "bundle_name": bundle_name,
        "ops_count": ops_count,
        "bytes_est": bytes_est,
        "repo_rev": repo_rev,
        "focus_hash": focus_hash,
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

    # Add/update bundle entry (with staleness tracking)
    bundle_name = metadata["bundle_name"]
    index["bundles"][bundle_name] = {
        "ts": metadata["ts"],
        "ops_count": metadata["ops_count"],
        "bytes_est": metadata["bytes_est"],
        "branch": metadata["branch"],
        "repo_rev": metadata.get("repo_rev"),
        "focus_hash": metadata.get("focus_hash"),
    }

    # Verify bundle file exists
    bundle_path = bundles_dir / f"{bundle_name}.jsonl"
    index["bundles"][bundle_name]["exists"] = bundle_path.exists()

    # Write back
    with open(index_path, "w") as f:
        json.dump(index, f, indent=2)


if __name__ == "__main__":
    main()
