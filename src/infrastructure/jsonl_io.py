"""
JSONL file I/O adapter for context events.

This module provides filesystem operations for JSONL files,
delegating parsing logic to the domain layer.

Architecture note: This is in infrastructure/ because it performs
I/O operations. The pure parsing logic remains in domain/parser.py.
"""

import sys
from pathlib import Path
from typing import Iterator

# Import parsing functions from domain layer
sys.path.insert(0, str(Path(__file__).parent.parent))
from domain.parser import parse_jsonl_line, serialize_event, InvalidJSONError, InvalidEventError
from domain.events import ContextEvent


def parse_jsonl_file(path: Path) -> Iterator[ContextEvent]:
    """
    Parse a JSONL file, yielding ContextEvents.

    Tolerant to:
    - Truncated final line (skip with logging)
    - Invalid JSON (skip with logging)
    - Invalid events (skip with warning via stderr)

    Args:
        path: Path to JSONL file

    Yields:
        ContextEvent objects

    Returns:
        None (use as iterator)
    """
    if not path.exists():
        return

    with open(path, "r") as f:
        for line_number, line in enumerate(f, start=1):
            line = line.strip()

            # Skip empty lines
            if not line:
                continue

            try:
                event = parse_jsonl_line(line)
                yield event
            except InvalidJSONError as e:
                # Log JSON parsing failures for audit trail
                print(
                    f"[WARNING] jsonl_io: Invalid JSON at {path}:{line_number} - {e.reason}",
                    file=sys.stderr,
                    flush=True
                )
                continue
            except InvalidEventError as e:
                # Log to stderr but continue parsing
                print(f"Warning: {e}", file=sys.stderr)
                continue


def write_jsonl(path: Path, events: list[ContextEvent]) -> None:
    """
    Write events to a JSONL file.

    Note: This does NOT handle locking. Use storage_jsonl for that.

    Args:
        path: Output file path
        events: Events to write
    """
    with open(path, "w") as f:
        for event in events:
            f.write(serialize_event(event) + "\n")
