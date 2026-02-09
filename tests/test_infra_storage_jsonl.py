"""Tests for JSONL storage."""

import pytest

from domain.events import create_read_event, create_prompt_event
from infrastructure.storage_jsonl import JSONLStorage


def test_storage_append_event(temp_dir):
    """Test appending a single event."""
    storage_path = temp_dir / "test.jsonl"
    storage = JSONLStorage(storage_path)

    event = create_read_event("src/app.py")
    storage.append(event)

    assert storage_path.exists()
    content = storage_path.read_text()
    assert '"operation":"read"' in content
    assert '"file_path":"src/app.py"' in content


def test_storage_append_multiple_events(temp_dir):
    """Test appending multiple events."""
    storage_path = temp_dir / "test.jsonl"
    storage = JSONLStorage(storage_path)

    events = [
        create_prompt_event("prompt 1"),
        create_read_event("src/app.py"),
        create_read_event("tests/test.py"),
    ]

    storage.append_many(events)

    # Should have 3 lines
    content = storage_path.read_text()
    lines = content.strip().split("\n")
    assert len(lines) == 3


def test_storage_read_all(temp_dir):
    """Test reading all events."""
    storage_path = temp_dir / "test.jsonl"
    storage = JSONLStorage(storage_path)

    # Write events
    events = [
        create_prompt_event("test"),
        create_read_event("src/app.py"),
    ]
    storage.append_many(events)

    # Read back
    read_events = list(storage.read_all())
    assert len(read_events) == 2


def test_storage_count(temp_dir):
    """Test counting events."""
    storage_path = temp_dir / "test.jsonl"
    storage = JSONLStorage(storage_path)

    assert storage.count() == 0

    storage.append(create_read_event("src/app.py"))
    assert storage.count() == 1

    storage.append(create_read_event("tests/test.py"))
    assert storage.count() == 2


def test_storage_truncate(temp_dir):
    """Test truncating storage."""
    storage_path = temp_dir / "test.jsonl"
    storage = JSONLStorage(storage_path)

    storage.append(create_read_event("src/app.py"))
    assert storage.count() == 1

    storage.truncate()
    assert storage.count() == 0


def test_storage_creates_directory(temp_dir):
    """Test that append creates parent directory."""
    storage_path = temp_dir / "subdir" / "test.jsonl"
    storage = JSONLStorage(storage_path)

    storage.append(create_read_event("src/app.py"))

    assert storage_path.parent.exists()
    assert storage_path.exists()


def test_storage_read_empty_file(temp_dir):
    """Test reading from non-existent file."""
    storage_path = temp_dir / "nonexistent.jsonl"
    storage = JSONLStorage(storage_path)

    events = list(storage.read_all())
    assert len(events) == 0
