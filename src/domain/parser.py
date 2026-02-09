"""
Pure JSONL parser for context events (domain layer).

This module contains ONLY pure functions for parsing JSONL strings.
No filesystem operations - those are in infrastructure/jsonl_io.py.

Handles:
- Invalid JSON detection
- Missing field validation
- Operation normalization
- Extra field filtering
"""

import json

from .events import ContextEvent


class ParseError(Exception):
    """Base class for parse errors."""

    def __init__(self, line_number: int, line: str, reason: str):
        self.line_number = line_number
        self.line = line
        self.reason = reason
        super().__init__(f"Line {line_number}: {reason}")


class InvalidJSONError(ParseError):
    """Line is not valid JSON."""


class InvalidEventError(ParseError):
    """Valid JSON but not a valid event."""


def parse_jsonl_line(line: str) -> ContextEvent:
    """
    Parse a single JSONL line into a ContextEvent.

    Pure function - no I/O operations.

    Args:
        line: Single line from JSONL file

    Returns:
        ContextEvent

    Raises:
        InvalidJSONError: Line is not valid JSON
        InvalidEventError: Valid JSON but invalid event
    """
    try:
        data = json.loads(line)
    except json.JSONDecodeError as e:
        raise InvalidJSONError(0, line, f"Invalid JSON: {e}")

    if not isinstance(data, dict):
        raise InvalidEventError(0, line, "Event must be a JSON object")

    # Validate required fields
    if "operation" not in data:
        raise InvalidEventError(0, line, "Missing 'operation' field")

    if "ts" not in data:
        raise InvalidEventError(0, line, "Missing 'ts' field")

    # Validate and normalize operation
    valid_ops = {"read", "write", "edit", "multi_edit", "prompt", "note"}
    op = data["operation"].lower()
    if op not in valid_ops:
        raise InvalidEventError(0, line, f"Invalid operation: {op}")

    # Normalize multi_edit -> multi_edit
    if op == "multi_edit":
        data["operation"] = "multi_edit"

    # Add default source if missing
    if "source" not in data:
        data["source"] = "hook"

    try:
        return ContextEvent.from_dict(data)
    except ValueError as e:
        raise InvalidEventError(0, line, str(e))


def serialize_event(event: ContextEvent) -> str:
    """
    Serialize a ContextEvent to a JSONL line.

    Pure function - no I/O operations.

    Args:
        event: Event to serialize

    Returns:
        JSON string (no trailing newline)
    """
    d = event.to_dict()
    return json.dumps(d, separators=(",", ":"))  # Compact JSON
