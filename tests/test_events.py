"""Tests for ContextEvent dataclass."""

import pytest

from domain.events import (
    ContextEvent,
    OperationType,
    EventSource,
    create_read_event,
    create_prompt_event,
)


def test_read_event_creation():
    """Test creating a READ event."""
    event = create_read_event("src/app.py", tool="Read", size=1000)

    assert event.operation == OperationType.READ
    assert event.file_path == "src/app.py"
    assert event.tool == "Read"
    assert event.meta["size"] == 1000
    assert event.is_file_operation is True
    assert event.is_user_intent is False


def test_prompt_event_creation():
    """Test creating a PROMPT event."""
    event = create_prompt_event("/cm-save my-bundle")

    assert event.operation == OperationType.PROMPT
    assert event.prompt == "/cm-save my-bundle"
    assert event.is_file_operation is False
    assert event.is_user_intent is True


def test_event_validation_absolute_path():
    """Test that absolute paths are rejected."""
    with pytest.raises(ValueError, match="Absolute paths not allowed"):
        ContextEvent(
            operation=OperationType.READ,
            ts=1704067200,
            source=EventSource.HOOK,
            file_path="/etc/passwd",  # Absolute path
        )


def test_event_validation_path_traversal():
    """Test that path traversal is rejected."""
    with pytest.raises(ValueError, match="Path traversal not allowed"):
        ContextEvent(
            operation=OperationType.READ,
            ts=1704067200,
            source=EventSource.HOOK,
            file_path="../../etc/passwd",  # Traversal
        )


def test_event_validation_prompt_requires_text():
    """Test that PROMPT events require prompt text."""
    with pytest.raises(ValueError, match="PROMPT events require 'prompt' field"):
        ContextEvent(
            operation=OperationType.PROMPT,
            ts=1704067200,
            source=EventSource.USER,
        )


def test_event_to_dict():
    """Test serializing event to dict."""
    event = create_read_event("src/app.py")
    d = event.to_dict()

    assert d["operation"] == "read"
    assert "file_path" in d
    assert "ts" in d


def test_event_from_dict():
    """Test deserializing event from dict."""
    d = {
        "operation": "read",
        "ts": 1704067200,
        "source": "hook",
        "file_path": "src/app.py",
        "tool": "Read",
    }

    event = ContextEvent.from_dict(d)

    assert event.operation == OperationType.READ
    assert event.file_path == "src/app.py"


def test_estimated_bytes():
    """Test byte estimation for events."""
    read_event = create_read_event("src/app.py", size=5000)
    assert read_event.estimated_bytes == 5000

    prompt_event = create_prompt_event("test prompt")
    assert prompt_event.estimated_bytes == len("test prompt")
