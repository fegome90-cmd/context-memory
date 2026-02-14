"""Tests for checkpoint generation and loading."""

import pytest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from domain.events import ContextEvent, OperationType, EventSource
from scripts.cm_save import (
    generate_checkpoint,
    write_checkpoint_atomic,
    MAX_CHECKPOINT_LINE_LEN,
)


class TestGenerateCheckpoint:
    """Tests for checkpoint generation."""

    def test_empty_events_returns_na(self):
        """Empty events should return n/a checkpoint."""
        result = generate_checkpoint([], [])
        assert "n/a" in result
        assert result.count("\n") == 1

    def test_checkpoint_format(self):
        """Checkpoint should have correct format."""
        events = [
            ContextEvent(
                operation=OperationType.WRITE,
                ts=1234567890,
                source=EventSource.HOOK,
                file_path="src/app.py",
            )
        ]
        result = generate_checkpoint(events, events)

        assert result.startswith("CHK:")
        assert "DONE:" in result
        assert "NEXT:" in result
        assert "FOCUS:" in result
        assert "EVID:" in result

    def test_edited_when_write_event(self):
        """DONE should be 'edited' when there's a write event."""
        events = [
            ContextEvent(
                operation=OperationType.WRITE,
                ts=1234567890,
                source=EventSource.HOOK,
                file_path="src/app.py",
            )
        ]
        result = generate_checkpoint(events, events)
        assert "DONE: edited" in result

    def test_reviewed_when_only_reads(self):
        """DONE should be 'reviewed' when only reads."""
        events = [
            ContextEvent(
                operation=OperationType.READ,
                ts=1234567890,
                source=EventSource.HOOK,
                file_path="src/app.py",
            )
        ]
        result = generate_checkpoint(events, events)
        assert "DONE: reviewed" in result

    def test_max_line_length(self):
        """Each line should respect MAX_CHECKPOINT_LINE_LEN."""
        events = []
        for i in range(50):
            events.append(
                ContextEvent(
                    operation=OperationType.READ,
                    ts=1234567890 + i,
                    source=EventSource.HOOK,
                    file_path=f"src/very/long/path/to/file_{i}.py",
                )
            )

        result = generate_checkpoint(events, events)
        lines = result.split("\n")

        for line in lines:
            assert len(line) <= MAX_CHECKPOINT_LINE_LEN

    def test_focus_extraction(self):
        """FOCUS should extract directory from file path."""
        events = [
            ContextEvent(
                operation=OperationType.READ,
                ts=1234567890,
                source=EventSource.HOOK,
                file_path="src/components/Button.tsx",
            ),
            ContextEvent(
                operation=OperationType.READ,
                ts=1234567891,
                source=EventSource.HOOK,
                file_path="tests/app.test.ts",
            ),
        ]
        result = generate_checkpoint(events, events)

        assert "src" in result
        assert "tests" in result


class TestCheckpointAtomicWrite:
    """Tests for atomic checkpoint writing."""

    def test_atomic_write(self, tmp_path):
        """Should write checkpoint atomically."""
        content = "CHK: test | DONE: edited\nFOCUS: src"

        result = write_checkpoint_atomic(tmp_path, "test-bundle", content)

        assert result.exists()
        assert result.read_text() == content

    def test_overwrites_existing(self, tmp_path):
        """Should overwrite existing checkpoint."""
        content1 = "CHK: old"
        content2 = "CHK: new"

        write_checkpoint_atomic(tmp_path, "test", content1)
        write_checkpoint_atomic(tmp_path, "test", content2)

        result = tmp_path / "test.checkpoint.txt"
        assert result.read_text() == content2
