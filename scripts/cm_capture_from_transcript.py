#!/usr/bin/env python3
"""
Capture context from Claude Code transcript via UserPromptSubmit hook.

This works because UserPromptSubmit hook DOES fire reliably.
It reads the transcript JSON and extracts Read/Write/Edit/MultiEdit operations.
"""

import json
import os
import sys
from pathlib import Path
from datetime import datetime

# Add src to path
plugin_dir = Path(__file__).parent.parent
sys.path.insert(0, str(plugin_dir / "src"))

from domain.events import ContextEvent, OperationType, EventSource
from infrastructure.repo import detect_repo
from infrastructure.storage_jsonl import JSONLStorage


def main():
    # Read hook input from stdin
    try:
        hook_input = json.load(sys.stdin)
    except json.JSONDecodeError:
        return

    # Get transcript path from hook input
    transcript_path = hook_input.get("transcript_path")
    if not transcript_path:
        return

    transcript_file = Path(transcript_path)
    if not transcript_file.exists():
        return

    # Read transcript
    try:
        with open(transcript_file, "r") as f:
            transcript = json.load(f)
    except (json.JSONDecodeError, IOError):
        return

    # Detect repo
    repo_info = detect_repo()
    if not repo_info:
        return

    # Setup storage
    sessions_dir = repo_info.root / ".claude" / "context_memory" / "sessions"
    storage = JSONLStorage(sessions_dir / "current.jsonl")

    # Extract tool uses from transcript
    # Look for the most recent turn (user message + assistant response)
    if "turns" not in transcript:
        return

    # Get last 2 turns (user + assistant)
    recent_turns = transcript["turns"][-2:]

    for turn in recent_turns:
        if turn.get("role") != "assistant":
            continue

        # Extract tool use from assistant's response
        for block in turn.get("content", []):
            if block.get("type") != "tool_use":
                continue

            tool_name = block.get("name", "")
            tool_input = block.get("input", {})

            # Map to operation type
            operation_map = {
                "Read": OperationType.READ,
                "Write": OperationType.WRITE,
                "Edit": OperationType.EDIT,
                "MultiEdit": OperationType.MULTI_EDIT,
            }

            if tool_name not in operation_map:
                continue

            # Extract file path
            file_path = None
            if tool_name == "Read":
                file_path = tool_input.get("file_path")
            elif tool_name == "Write":
                file_path = tool_input.get("file_path")
            elif tool_name == "Edit":
                file_path = tool_input.get("file_path")
            elif tool_name == "MultiEdit":
                files = tool_input.get("files", [])
                if files and isinstance(files[0], dict):
                    file_path = files[0].get("file")
                elif files:
                    file_path = files[0]

            if not file_path:
                continue

            # Normalize to relative path
            from infrastructure.paths import get_relative_path
            try:
                rel_path = get_relative_path(file_path, repo_info.root)
            except (ValueError, TypeError):
                continue

            if not rel_path:
                continue

            # Create event
            try:
                timestamp = int(os.environ.get("CM_TIMESTAMP", os.times()[4]))
                event = ContextEvent(
                    operation=operation_map[tool_name],
                    ts=timestamp,
                    source=EventSource.HOOK,
                    file_path=rel_path,
                    tool=tool_name,
                    tool_input=json.dumps(tool_input, default=str)[:500],  # Truncate
                )
                storage.append(event)
            except (OSError, IOError, ValueError):
                pass


if __name__ == "__main__":
    main()
