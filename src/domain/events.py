"""
Domain events for context memory.

Pure dataclasses representing operations tracked during a session.
No filesystem logic, just data.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, Mapping, Any
from datetime import datetime


class OperationType(Enum):
    """Types of operations tracked."""
    READ = "read"
    WRITE = "write"
    EDIT = "edit"
    MULTI_EDIT = "multi_edit"
    PROMPT = "prompt"
    NOTE = "note"
    TODO = "todo"


class EventSource(Enum):
    """Where the event originated."""
    HOOK = "hook"      # From Claude Code hook
    USER = "user"      # Explicit user command
    SYSTEM = "system"  # System-generated


@dataclass(frozen=True)
class ContextEvent:
    """
    A single context event.

    Immutable by design (frozen=True). Events are facts that happened.
    """
    operation: OperationType
    ts: int  # Unix timestamp
    source: EventSource

    # Optional fields (not all ops have these)
    file_path: Optional[str] = None
    tool: Optional[str] = None
    tool_input: Optional[str] = None
    prompt: Optional[str] = None
    sha256: Optional[str] = None

    # Free-form metadata (tags, size, etc.)
    # Use Mapping for type-level immutability (read-only view)
    # Internally converted to immutable mapping in __post_init__
    meta: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        """Validate event invariants."""
        # Protect meta field - convert dict to immutable mapping
        # This must happen before validation to ensure meta is properly set
        if isinstance(self.meta, dict):
            # Convert dict to MappingProxy (immutable read-only view)
            from types import MappingProxyType
            object.__setattr__(self, 'meta', MappingProxyType(self.meta))

        # Prompts must have prompt text
        if self.operation == OperationType.PROMPT and not self.prompt:
            raise ValueError("PROMPT events require 'prompt' field")

        # File ops must have file_path
        if self.operation in {
            OperationType.READ,
            OperationType.WRITE,
            OperationType.EDIT,
            OperationType.MULTI_EDIT,
        } and not self.file_path:
            raise ValueError(f"{self.operation.value} events require 'file_path' field")

        # Security: no absolute paths
        if self.file_path and self.file_path.startswith("/"):
            raise ValueError(f"Absolute paths not allowed: {self.file_path}")

        # Security: no path traversal
        if self.file_path and ".." in self.file_path:
            raise ValueError(f"Path traversal not allowed: {self.file_path}")

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        d: dict[str, object] = {
            "operation": self.operation.value,
            "ts": self.ts,
            "source": self.source.value,
        }

        if self.file_path:
            d["file_path"] = self.file_path
        if self.tool:
            d["tool"] = self.tool
        if self.tool_input:
            d["tool_input"] = self.tool_input
        if self.prompt:
            d["prompt"] = self.prompt
        if self.sha256:
            d["sha256"] = self.sha256
        if self.meta:
            # Convert MappingProxy to dict for JSON serialization
            d["meta"] = dict(self.meta)

        return d

    @classmethod
    def from_dict(cls, d: dict) -> "ContextEvent":
        """Create from dictionary (JSON deserialization)."""
        # Handle string enums
        operation = OperationType(d["operation"])
        source = EventSource(d.get("source", "hook"))

        # Get meta dict - will be converted to MappingProxy in __post_init__
        meta_dict = d.get("meta", {})

        return cls(
            operation=operation,
            ts=int(d["ts"]),
            source=source,
            file_path=d.get("file_path"),
            tool=d.get("tool"),
            tool_input=d.get("tool_input"),
            prompt=d.get("prompt"),
            sha256=d.get("sha256"),
            meta=meta_dict,  # dict, will be converted to MappingProxy
        )

    @property
    def is_file_operation(self) -> bool:
        """True if this operates on a file."""
        return self.operation in {
            OperationType.READ,
            OperationType.WRITE,
            OperationType.EDIT,
            OperationType.MULTI_EDIT,
        }

    @property
    def is_user_intent(self) -> bool:
        """True if this represents user intent (vs automatic tracking)."""
        return self.operation in {OperationType.PROMPT, OperationType.NOTE}

    @property
    def estimated_bytes(self) -> int:
        """Estimate bytes contributed to context budget."""
        if self.operation == OperationType.READ:
            # Estimate based on file size in meta, or default
            return self.meta.get("size", 1000)
        if self.operation == OperationType.PROMPT:
            # Prompts are high value but small
            return len(self.prompt or "")
        return 100  # Default for other ops


def create_read_event(file_path: str, tool: str = "Read", **meta) -> ContextEvent:
    """Helper to create a READ event."""
    return ContextEvent(
        operation=OperationType.READ,
        ts=int(datetime.now().timestamp()),
        source=EventSource.HOOK,
        file_path=file_path,
        tool=tool,
        meta=meta,
    )


def create_write_event(
    file_path: str,
    tool: str = "Write",
    tool_input: Optional[str] = None,
    **meta
) -> ContextEvent:
    """Helper to create a WRITE event."""
    return ContextEvent(
        operation=OperationType.WRITE,
        ts=int(datetime.now().timestamp()),
        source=EventSource.HOOK,
        file_path=file_path,
        tool=tool,
        tool_input=tool_input,
        meta=meta,
    )


def create_prompt_event(prompt: str) -> ContextEvent:
    """Helper to create a PROMPT event (user command)."""
    return ContextEvent(
        operation=OperationType.PROMPT,
        ts=int(datetime.now().timestamp()),
        source=EventSource.USER,
        prompt=prompt,
    )
