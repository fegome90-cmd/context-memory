#!/usr/bin/env python3
"""
Context-Memory Operation Tracking Hook

This script runs as a PostToolUse hook to track file operations (Read/Write/Edit)
and store them in a JSONL log for context pruning and bundling.

Input: JSON object via stdin with format:
    {"toolUse": {"name": "Read", "input": {"file_path": "..."}}, "timestamp": ...}

Output: Appends event to .claude/context_memory/sessions/current.jsonl

Environment Variables:
    CM_DEBUG=1: Enable debug logging to /tmp/cm_hook_debug.log
"""

import json
import os
import sys
from pathlib import Path
from typing import Optional

# Add src to path for imports
plugin_dir = Path(__file__).parent.parent
sys.path.insert(0, str(plugin_dir / "src"))

from domain.events import ContextEvent, OperationType, EventSource
from infrastructure.repo import detect_repo, detect_repo_from_file_path
from infrastructure.storage_jsonl import JSONLStorage
from infrastructure.paths import get_relative_path
from infrastructure.logging import get_logger

logger = get_logger(__name__)

# Constants
MAX_TOOL_INPUT_SIZE = 4096
TRACKED_TOOLS = frozenset({"Read", "Write", "Edit", "MultiEdit"})
OPERATION_MAP = {
    "Read": OperationType.READ,
    "Write": OperationType.WRITE,
    "Edit": OperationType.EDIT,
    "MultiEdit": OperationType.MULTI_EDIT,
}
SESSIONS_RELATIVE_PATH = ".claude/context_memory/sessions"


def parse_stdin() -> Optional[dict]:
    """Parse JSON input from stdin."""
    try:
        hook_input = json.load(sys.stdin)
        logger.debug(f"Received JSON: {json.dumps(hook_input)[:200]}")
        return hook_input
    except json.JSONDecodeError as e:
        logger.debug(f"Invalid JSON input: {e}")
        return None


def extract_file_path(input_data: dict) -> Optional[str]:
    """
    Extract file path from tool input.

    Handles both single file operations (file_path field) and
    MultiEdit operations (files array).
    """
    # Single file operations (Read, Write, Edit)
    if file_path := input_data.get("file_path", ""):
        return file_path

    # MultiEdit operations with files array
    files = input_data.get("files", [])
    if not files:
        return None

    first_file = files[0]
    if isinstance(first_file, dict):
        return first_file.get("file", "")
    return first_file or None


def truncate_tool_input(input_data: dict, max_size: int) -> Optional[str]:
    """Truncate tool input to max size for storage."""
    if not input_data:
        return None

    input_str = json.dumps(input_data, default=str)
    if len(input_str) <= max_size:
        return input_str
    return f"{input_str[:max_size]}... [TRUNCATED]"


def map_operation_type(tool_name: str) -> Optional[OperationType]:
    """Map tool name to operation type."""
    return OPERATION_MAP.get(tool_name)


def validate_and_normalize_path(
    file_path_str: str,
    repo_root: Path
) -> Optional[str]:
    """Validate path and normalize to relative path inside repo."""
    try:
        return get_relative_path(Path(file_path_str), repo_root)
    except (ValueError, TypeError) as e:
        logger.warning(f"Path validation failed for {file_path_str}: {e}")
        return None


def create_event(
    tool_name: str,
    rel_path: str,
    input_data: dict,
    timestamp: Optional[int]
) -> Optional[ContextEvent]:
    """Create a ContextEvent with proper validation."""
    try:
        operation = map_operation_type(tool_name)
        if operation is None:
            logger.debug(f"Unknown tool: {tool_name}")
            return None

        ts = timestamp if timestamp is not None else int(os.times()[4])

        return ContextEvent(
            operation=operation,
            ts=ts,
            source=EventSource.HOOK,
            file_path=rel_path,
            tool=tool_name,
            tool_input=truncate_tool_input(input_data, MAX_TOOL_INPUT_SIZE),
        )
    except (ValueError, TypeError) as e:
        logger.error(f"Failed to create event: {e}")
        return None


def store_event(event: ContextEvent, repo_root: Path) -> bool:
    """
    Append event to current.jsonl.

    Returns True if successful, False on error.
    """
    try:
        sessions_dir = repo_root / SESSIONS_RELATIVE_PATH
        storage = JSONLStorage(sessions_dir / "current.jsonl")
        storage.append(event)
        logger.debug(f"Event captured: {event.tool} {event.file_path}")
        return True
    except (OSError, IOError) as e:
        logger.error(f"Storage failed: {e}")
        return False


def main() -> int:
    """
    Main entry point - reads JSON from stdin (not environment variables).

    Returns:
        0 on success, 1 on security event (path validation failure)
    """
    logger.debug("cm_track_operation.py called")

    # 1. Parse stdin
    hook_input = parse_stdin()
    if not hook_input:
        return 0

    # Support both old (toolUse.name) and new (tool_name) JSON structures
    tool_name = hook_input.get("tool_name", "")
    if not tool_name:
        tool_use = hook_input.get("toolUse", {})
        tool_name = tool_use.get("name", "")

    logger.debug(f"Tool: {tool_name}")

    # 2. Skip untracked tools
    if tool_name not in TRACKED_TOOLS:
        logger.debug(f"Skipping tool: {tool_name}")
        return 0

    # 3. Extract file_path FIRST (before repo detection)
    # Support both input structures
    input_data = hook_input.get("tool_input", {})
    if not input_data:
        tool_use = hook_input.get("toolUse", {})
        input_data = tool_use.get("input", {})
    file_path_str = extract_file_path(input_data)
    if not file_path_str:
        logger.debug("No file_path in input - skipping")
        return 0

    # 4. Find repo root from file_path (primary) or cwd (fallback)
    file_path = Path(file_path_str)
    repo_info = None

    if file_path.is_absolute():
        # Primary strategy: derive repo from the absolute file path
        repo_info = detect_repo_from_file_path(file_path)
        if repo_info:
            logger.debug(f"Repo detected from file_path: {repo_info.root}")
    else:
        # Fallback: relative path, try cwd-based detection
        repo_info = detect_repo()
        if repo_info:
            logger.debug(f"Repo detected from cwd: {repo_info.root}")

    if not repo_info:
        logger.debug("Not in a git repo - hook disabled")
        return 0

    # 5. Validate and normalize path
    rel_path = validate_and_normalize_path(file_path_str, repo_info.root)
    if not rel_path:
        # FAIL-CLOSED: Log security event and return error code
        logger.warning(
            f"SECURITY: Path validation blocked - tool={tool_name} path='{file_path_str}'"
        )
        return 1

    logger.debug(f"Tracking {tool_name} on {rel_path}")

    # 6. Create and store event
    event = create_event(tool_name, rel_path, input_data, hook_input.get("timestamp"))
    if event:
        store_event(event, repo_info.root)

    return 0


if __name__ == "__main__":
    main()
