"""Tests for checkpoint generation and loading."""

import json
import pytest
import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from domain.events import ContextEvent, OperationType, EventSource
from scripts.cm_save import (
    generate_checkpoint,
    write_checkpoint_atomic,
    MAX_CHECKPOINT_LINE_LEN,
    extract_last_todos,
    find_latest_plan,
    generate_enhanced_handoff_card,
)


class TestGenerateCheckpoint:
    """Tests for checkpoint generation."""

    def test_empty_events_returns_na(self):
        """Empty events should return n/a checkpoint."""
        checkpoint, focus_dirs = generate_checkpoint([], [])
        assert "n/a" in checkpoint
        assert checkpoint.count("\n") == 1
        assert focus_dirs == []

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
        checkpoint, focus_dirs = generate_checkpoint(events, events)

        assert checkpoint.startswith("CHK:")
        assert "DONE:" in checkpoint
        assert "NEXT:" in checkpoint
        assert "FOCUS:" in checkpoint
        assert "EVID:" in checkpoint

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
        checkpoint, focus_dirs = generate_checkpoint(events, events)
        assert "DONE: edited" in checkpoint

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
        checkpoint, focus_dirs = generate_checkpoint(events, events)
        assert "DONE: reviewed" in checkpoint

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

        checkpoint, focus_dirs = generate_checkpoint(events, events)
        lines = checkpoint.split("\n")

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
        checkpoint, focus_dirs = generate_checkpoint(events, events)

        assert "src" in checkpoint
        assert "tests" in checkpoint
        assert "src" in focus_dirs
        assert "tests" in focus_dirs


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


class TestExtractLastTodos:
    """Tests for extracting todos from events."""

    def test_empty_events_returns_empty_list(self):
        """No events should return empty list."""
        result = extract_last_todos([])
        assert result == []

    def test_no_todo_events_returns_empty_list(self):
        """Events without TodoWrite should return empty list."""
        events = [
            ContextEvent(
                operation=OperationType.READ,
                ts=1234567890,
                source=EventSource.HOOK,
                file_path="src/app.py",
            )
        ]
        result = extract_last_todos(events)
        assert result == []

    def test_extracts_todos_from_tool_input(self):
        """Should extract todos from TodoWrite tool_input."""
        tool_input = json.dumps({
            "todos": [
                {"subject": "Task 1", "status": "completed", "description": "Do task 1"},
                {"subject": "Task 2", "status": "pending", "description": "Do task 2"},
            ]
        })
        events = [
            ContextEvent(
                operation=OperationType.TODO,
                ts=1234567890,
                source=EventSource.HOOK,
                tool="TodoWrite",
                tool_input=tool_input,
            )
        ]
        result = extract_last_todos(events)

        assert len(result) == 2
        assert result[0]["subject"] == "Task 1"
        assert result[0]["status"] == "completed"
        assert result[1]["subject"] == "Task 2"

    def test_limits_to_n_todos(self):
        """Should limit extraction to n todos."""
        tool_input = json.dumps({
            "todos": [
                {"subject": f"Task {i}", "status": "pending", "description": ""}
                for i in range(10)
            ]
        })
        events = [
            ContextEvent(
                operation=OperationType.TODO,
                ts=1234567890,
                source=EventSource.HOOK,
                tool="TodoWrite",
                tool_input=tool_input,
            )
        ]
        result = extract_last_todos(events, n=3)

        assert len(result) == 3


class TestFindLatestPlan:
    """Tests for finding the latest plan file."""

    def test_returns_none_when_no_plans_dir(self, tmp_path):
        """Should return None when plans directory doesn't exist."""
        with patch.object(Path, "home", return_value=tmp_path):
            result = find_latest_plan()
            assert result is None

    def test_returns_none_when_no_plan_files(self, tmp_path):
        """Should return None when no .md files in plans dir."""
        plans_dir = tmp_path / ".claude" / "plans"
        plans_dir.mkdir(parents=True)
        # No files created

        with patch.object(Path, "home", return_value=tmp_path):
            result = find_latest_plan()
            assert result is None

    def test_returns_most_recent_plan(self, tmp_path):
        """Should return content of most recent plan file."""
        import time

        plans_dir = tmp_path / ".claude" / "plans"
        plans_dir.mkdir(parents=True)

        # Create old plan
        old_plan = plans_dir / "old.md"
        old_plan.write_text("# Old Plan\nOld content")
        time.sleep(0.1)

        # Create new plan
        new_plan = plans_dir / "new.md"
        new_plan.write_text("# New Plan\nNew content")

        with patch.object(Path, "home", return_value=tmp_path):
            result = find_latest_plan()

        assert result is not None
        assert "New Plan" in result


class TestGenerateEnhancedHandoffCard:
    """Tests for enhanced handoff card generation."""

    def test_includes_bundle_name(self):
        """Card should include bundle name."""
        card = generate_enhanced_handoff_card(
            bundle_name="test-bundle",
            focus_dirs="src",
            status="edited",
            todos=[],
            plan_content=None,
            checkpoint="CHK: test",
        )

        assert "test-bundle" in card
        assert "/cm-load test-bundle" in card

    def test_includes_plan_section_when_provided(self):
        """Card should include plan section when plan_content is provided."""
        card = generate_enhanced_handoff_card(
            bundle_name="test",
            focus_dirs="src",
            status="edited",
            todos=[],
            plan_content="# My Plan\nStep 1: Do thing",
            checkpoint="CHK: test",
        )

        assert "LAST PLAN" in card
        assert "My Plan" in card

    def test_no_plan_section_when_none(self):
        """Card should not include plan section when plan_content is None."""
        card = generate_enhanced_handoff_card(
            bundle_name="test",
            focus_dirs="src",
            status="edited",
            todos=[],
            plan_content=None,
            checkpoint="CHK: test",
        )

        assert "LAST PLAN" not in card

    def test_includes_todos_section_when_provided(self):
        """Card should include todos section when todos are provided."""
        todos = [
            {"subject": "Write tests", "status": "pending", "description": ""},
            {"subject": "Fix bug", "status": "completed", "description": ""},
        ]
        card = generate_enhanced_handoff_card(
            bundle_name="test",
            focus_dirs="src",
            status="edited",
            todos=todos,
            plan_content=None,
            checkpoint="CHK: test",
        )

        assert "LAST TODOS" in card
        assert "Write tests" in card
        assert "Fix bug" in card
        assert "[x]" in card  # Completed checkbox
        assert "[ ]" in card  # Pending checkbox

    def test_includes_checkpoint_section(self):
        """Card should include checkpoint section."""
        card = generate_enhanced_handoff_card(
            bundle_name="test",
            focus_dirs="src",
            status="edited",
            todos=[],
            plan_content=None,
            checkpoint="CHK: work | DONE: edited | NEXT: src\nFOCUS: src | EVID: n-a",
        )

        assert "CHECKPOINT" in card
        assert "CHK: work" in card
        assert "FOCUS: src" in card

    def test_includes_resume_command(self):
        """Card should include resume command."""
        card = generate_enhanced_handoff_card(
            bundle_name="my-bundle",
            focus_dirs="src",
            status="edited",
            todos=[],
            plan_content=None,
            checkpoint="CHK: test",
        )

        assert "COPY-PASTE TO NEXT AGENT" in card
        assert "/cm-load my-bundle" in card
