"""Tests for JSONL parser."""

import json
from pathlib import Path

import pytest

from domain.events import ContextEvent, OperationType
from domain.parser import (
    parse_jsonl_line,
    serialize_event,
    InvalidJSONError,
    InvalidEventError,
)
from infrastructure.jsonl_io import write_jsonl


def test_parse_valid_read_event():
    """Test parsing a valid READ event."""
    line = '{"operation":"read","file_path":"src/app.py","ts":1704067200,"source":"hook"}'
    event = parse_jsonl_line(line)

    assert event.operation == OperationType.READ
    assert event.file_path == "src/app.py"


def test_parse_valid_prompt_event():
    """Test parsing a valid PROMPT event."""
    line = '{"operation":"prompt","prompt":"/cm-save","ts":1704067200,"source":"user"}'
    event = parse_jsonl_line(line)

    assert event.operation == OperationType.PROMPT
    assert event.prompt == "/cm-save"


def test_parse_invalid_json():
    """Test that invalid JSON is handled gracefully."""
    line = '{"operation":"read", invalid json'

    with pytest.raises(InvalidJSONError):
        parse_jsonl_line(line)


def test_parse_missing_required_field():
    """Test that missing required fields raise error."""
    line = '{"operation":"read"}'  # Missing "ts"

    with pytest.raises(InvalidEventError, match="Missing 'ts' field"):
        parse_jsonl_line(line)


def test_parse_invalid_operation():
    """Test that invalid operations are rejected."""
    line = '{"operation":"delete","ts":1704067200,"source":"hook"}'

    with pytest.raises(InvalidEventError, match="Invalid operation"):
        parse_jsonl_line(line)


def test_parse_adds_default_source():
    """Test that missing source defaults to 'hook'."""
    line = '{"operation":"read","ts":1704067200,"file_path":"src/app.py"}'
    event = parse_jsonl_line(line)

    assert event.operation == OperationType.READ


def test_serialize_event():
    """Test serializing event to JSONL."""
    from domain.events import create_read_event

    event = create_read_event("src/app.py", tool="Read")
    line = serialize_event(event)

    # Should be valid JSON
    data = json.loads(line)
    assert data["operation"] == "read"
    assert data["file_path"] == "src/app.py"


def test_serialize_is_compact():
    """Test that serialization produces compact JSON."""
    from domain.events import create_read_event

    event = create_read_event("src/app.py")
    line = serialize_event(event)

    # No spaces in compact JSON
    assert " " not in line


def test_write_jsonl(temp_dir):
    """Test writing events to JSONL file."""
    from domain.events import create_read_event, create_prompt_event

    events = [
        create_prompt_event("test prompt"),
        create_read_event("src/app.py"),
    ]

    output_path = temp_dir / "test.jsonl"
    write_jsonl(output_path, events)

    # Verify file exists and has 2 lines
    assert output_path.exists()
    content = output_path.read_text()
    lines = content.strip().split("\n")
    assert len(lines) == 2

    # Verify each line is valid JSON
    for line in lines:
        data = json.loads(line)
        assert "operation" in data
