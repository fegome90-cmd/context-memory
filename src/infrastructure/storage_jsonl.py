"""
JSONL storage with locking and tolerant reading.

Handles:
- Append-only writes with file locking
- Tolerant reading (skip truncated lines)
- Thread-safe operations
"""

import fcntl
import sys
from pathlib import Path
from typing import Iterator

# Add parent src to path for imports
src_dir = Path(__file__).parent.parent
if str(src_dir) not in sys.path:
    sys.path.insert(0, str(src_dir))

from domain.events import ContextEvent
from domain.parser import serialize_event
from infrastructure.jsonl_io import parse_jsonl_file


class JSONLStorage:
    """
    Thread-safe JSONL storage with locking.

    Uses fcntl for Unix file locking. On Windows, locking is not available.
    """

    def __init__(self, path: Path):
        """
        Initialize storage for a file.

        Args:
            path: Path to JSONL file
        """
        self.path = path

    def append(self, event: ContextEvent) -> None:
        """
        Append a single event to the JSONL file.

        Thread-safe via file locking (Unix only).
        On Windows, writes without lock (logs warning).

        Args:
            event: Event to append
        """
        # Ensure parent directory exists
        self.path.parent.mkdir(parents=True, exist_ok=True)

        # Open in append mode
        with open(self.path, "a") as f:
            # Acquire exclusive lock (Unix only)
            try:
                fcntl.flock(f.fileno(), fcntl.LOCK_EX)
            except (AttributeError, OSError) as e:
                # Log lock failure for audit trail
                print(
                    f"[WARNING] storage_jsonl: File lock unavailable - {type(e).__name__}",
                    file=sys.stderr,
                    flush=True
                )
                # Continue without lock (Windows or other error)

            try:
                # Write event as JSONL line
                f.write(serialize_event(event) + "\n")
                f.flush()  # Ensure written before releasing lock
            finally:
                # Release lock (Unix only)
                try:
                    fcntl.flock(f.fileno(), fcntl.LOCK_UN)
                except (AttributeError, OSError):
                    pass

    def append_many(self, events: list[ContextEvent]) -> None:
        """
        Append multiple events efficiently.

        Acquires lock once for all events.

        Args:
            events: Events to append
        """
        if not events:
            return

        self.path.parent.mkdir(parents=True, exist_ok=True)

        with open(self.path, "a") as f:
            try:
                fcntl.flock(f.fileno(), fcntl.LOCK_EX)
            except (AttributeError, OSError) as e:
                # Log lock failure for audit trail
                print(
                    f"[WARNING] storage_jsonl: File lock unavailable - {type(e).__name__}",
                    file=sys.stderr,
                    flush=True
                )
                # Continue without lock (Windows or other error)

            try:
                for event in events:
                    f.write(serialize_event(event) + "\n")
                f.flush()
            finally:
                try:
                    fcntl.flock(f.fileno(), fcntl.LOCK_UN)
                except (AttributeError, OSError):
                    pass

    def read_all(self) -> Iterator[ContextEvent]:
        """
        Read all events from the JSONL file.

        Tolerant to:
        - Truncated final line (skipped)
        - Invalid JSON (skipped with warning)
        - Invalid events (skipped with warning)

        Yields:
            ContextEvent objects
        """
        yield from parse_jsonl_file(self.path)

    def read_all_list(self) -> list[ContextEvent]:
        """
        Read all events as a list.

        Returns:
            List of ContextEvent objects
        """
        return list(self.read_all())

    def count(self) -> int:
        """
        Count events in the file.

        Returns:
            Number of events
        """
        return sum(1 for _ in self.read_all())

    def exists(self) -> bool:
        """Check if the storage file exists."""
        return self.path.exists()

    def truncate(self) -> None:
        """
        Truncate the file (remove all events).

        Use with caution!
        """
        if self.exists():
            self.path.unlink()
