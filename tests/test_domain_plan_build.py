"""Tests for LoadPlan build_load_plan() and detect_drift()."""


from domain.events import ContextEvent, OperationType
from domain.plan import (
    LoadPlan,
    PlanAction,
    LoadStep,
    build_load_plan,
    detect_drift,
)


def test_build_load_plan_empty_events():
    """Test building a load plan with no events."""
    plan = build_load_plan([], "test-bundle")

    assert plan.bundle_name == "test-bundle"
    assert len(plan.steps) == 0
    assert plan.total_files == 0
    assert len(plan.warnings) == 0


def test_build_load_plan_with_prompts():
    """Test that user prompts are added first (priority intent)."""
    events = [
        ContextEvent(
            operation=OperationType.PROMPT,
            ts=1000,
            prompt="/cm-save bundle-name",
            source="user",
        ),
    ]

    plan = build_load_plan(events, "test")

    assert len(plan.steps) == 1
    assert plan.steps[0].action == PlanAction.INJECT
    assert "/cm-save" in plan.steps[0].content
    assert plan.steps[0].reason == "user prompt/intent"


def test_build_load_plan_prioritizes_config():
    """Test that config files are prioritized."""
    events = [
        ContextEvent(
            operation=OperationType.READ,
            ts=1000,
            file_path="config/settings.py",
            meta={"tags": ["config"]},
            source="hook",
        ),
        ContextEvent(
            operation=OperationType.READ,
            ts=1001,
            file_path="src/core.py",
            meta={"tags": ["core"]},
            source="hook",
        ),
    ]

    plan = build_load_plan(events, "test")

    # Config should come before core
    assert plan.steps[0].path == "config/settings.py"
    assert plan.steps[1].path == "src/core.py"
    assert plan.total_files == 2


def test_build_load_plan_priority_order():
    """Test the full priority order: prompts > config > core > doc > test > other."""
    events = [
        # Core (should be 2nd)
        ContextEvent(
            operation=OperationType.READ,
            ts=1000,
            file_path="src/core.py",
            meta={"tags": ["core"]},
            source="hook",
        ),
        # Prompt (should be 1st)
        ContextEvent(
            operation=OperationType.PROMPT,
            ts=999,
            prompt="/cm-load",
            source="user",
        ),
        # Config (should be 1st after prompts)
        ContextEvent(
            operation=OperationType.READ,
            ts=1001,
            file_path=".env",
            meta={"tags": ["config"]},
            source="hook",
        ),
        # Test (should be 4th)
        ContextEvent(
            operation=OperationType.READ,
            ts=1002,
            file_path="test_core.py",
            meta={"tags": ["test"]},
            source="hook",
        ),
        # Other (should be last)
        ContextEvent(
            operation=OperationType.READ,
            ts=1003,
            file_path="README.md",
            source="hook",
        ),
    ]

    plan = build_load_plan(events, "test")

    # Verify order
    assert plan.steps[0].action == PlanAction.INJECT  # Prompt first
    assert plan.steps[0].reason == "user prompt/intent"
    assert plan.steps[1].path == ".env"  # Config
    assert plan.steps[1].reason == "configuration"
    assert plan.steps[2].path == "src/core.py"  # Core
    assert plan.steps[2].reason == "core domain"
    assert plan.steps[3].path == "test_core.py"  # Test
    assert plan.steps[3].reason == "tests"
    assert plan.steps[4].path == "README.md"  # Other
    assert plan.steps[4].reason == "other"


def test_build_load_plan_warns_about_writes():
    """Test that write operations generate warnings."""
    events = [
        ContextEvent(
            operation=OperationType.READ,
            ts=1000,
            file_path="src/app.py",
            source="hook",
        ),
        ContextEvent(
            operation=OperationType.WRITE,
            ts=1001,
            file_path="src/app.py",
            source="hook",
        ),
    ]

    plan = build_load_plan(events, "test")

    # Should have warning about the write
    assert len(plan.warnings) == 1
    assert "modified" in plan.warnings[0].lower()
    assert "src/app.py" in plan.warnings[0]

    # Should have a WARN step
    warn_steps = [s for s in plan.steps if s.action == PlanAction.WARN]
    assert len(warn_steps) == 1


def test_build_load_plan_dedupes_same_file():
    """Test that reading the same file multiple times is preserved."""
    events = [
        ContextEvent(
            operation=OperationType.READ,
            ts=1000,
            file_path="config.py",
            source="hook",
        ),
        ContextEvent(
            operation=OperationType.READ,
            ts=1001,
            file_path="config.py",
            source="hook",
        ),
    ]

    plan = build_load_plan(events, "test")

    # Both reads should be in plan (not deduped - shows history)
    assert plan.total_files == 2
    assert plan.steps[0].path == "config.py"
    assert plan.steps[1].path == "config.py"


def test_build_load_plan_with_pinned_tag():
    """Test that pinned files are treated as high priority."""
    events = [
        ContextEvent(
            operation=OperationType.READ,
            ts=1000,
            file_path="important.txt",
            meta={"tags": ["pinned"]},
            source="hook",
        ),
        ContextEvent(
            operation=OperationType.READ,
            ts=1001,
            file_path="normal.py",
            source="hook",
        ),
    ]

    plan = build_load_plan(events, "test")

    # Pinned should come first (treated as config priority)
    assert plan.steps[0].path == "important.txt"
    assert plan.steps[0].reason == "configuration"


def test_detect_drift_no_changes():
    """Test drift detection when no files changed."""
    events = [
        ContextEvent(
            operation=OperationType.READ,
            ts=1000,
            file_path="src/app.py",
            sha256="abc123",
            source="hook",
        ),
    ]

    current_files = {
        "src/app.py": "abc123",
    }

    warnings = detect_drift(events, current_files)

    assert len(warnings) == 0


def test_detect_drift_file_changed():
    """Test drift detection when file was modified."""
    events = [
        ContextEvent(
            operation=OperationType.READ,
            ts=1000,
            file_path="src/app.py",
            sha256="abc123",
            source="hook",
        ),
    ]

    current_files = {
        "src/app.py": "def456",  # Different hash
    }

    warnings = detect_drift(events, current_files)

    assert len(warnings) == 1
    assert "changed since bundle" in warnings[0]
    assert "src/app.py" in warnings[0]
    assert "abc123" in warnings[0]
    assert "def456" in warnings[0]


def test_detect_drift_file_deleted():
    """Test drift detection when file was deleted."""
    events = [
        ContextEvent(
            operation=OperationType.READ,
            ts=1000,
            file_path="src/app.py",
            sha256="abc123",
            source="hook",
        ),
    ]

    current_files = {}  # File doesn't exist

    warnings = detect_drift(events, current_files)

    assert len(warnings) == 1
    assert "no longer exists" in warnings[0]
    assert "src/app.py" in warnings[0]


def test_detect_drift_multiple_files():
    """Test drift detection across multiple files."""
    events = [
        ContextEvent(
            operation=OperationType.READ,
            ts=1000,
            file_path="config.py",
            sha256="aaa111",
            source="hook",
        ),
        ContextEvent(
            operation=OperationType.READ,
            ts=1001,
            file_path="app.py",
            sha256="bbb222",
            source="hook",
        ),
        ContextEvent(
            operation=OperationType.READ,
            ts=1002,
            file_path="utils.py",
            sha256="ccc333",
            source="hook",
        ),
    ]

    current_files = {
        "config.py": "aaa111",  # Same
        "app.py": "changed!",   # Modified
        # utils.py missing       # Deleted
    }

    warnings = detect_drift(events, current_files)

    # Should have 2 warnings (modified + deleted)
    assert len(warnings) == 2

    # Check content
    warning_texts = "\n".join(warnings)
    assert "app.py" in warning_texts
    assert "changed since bundle" in warning_texts
    assert "utils.py" in warning_texts
    assert "no longer exists" in warning_texts


def test_detect_drift_ignores_events_without_sha256():
    """Test that events without SHA256 are skipped."""
    events = [
        ContextEvent(
            operation=OperationType.READ,
            ts=1000,
            file_path="app.py",
            # No sha256
            source="hook",
        ),
    ]

    current_files = {}

    warnings = detect_drift(events, current_files)

    # Should not warn about events without SHA256
    assert len(warnings) == 0


def test_loadplan_summarize():
    """Test LoadPlan.summarize() output."""
    plan = LoadPlan(bundle_name="test-bundle")
    plan.add_read("src/app.py", "core domain")
    plan.add_inject("/cm-load", "user intent")

    summary = plan.summarize()

    assert "test-bundle" in summary
    assert "Files to read: 1" in summary
    assert "Total steps: 2" in summary
    assert "src/app.py" in summary
    assert "/cm-load" in summary


def test_loadplan_to_script():
    """Test LoadPlan.to_script() generates valid script."""
    plan = LoadPlan(bundle_name="test")
    plan.add_read("config.py", "configuration")
    plan.add_inject("Note to self", "user intent")

    script = plan.to_script()

    assert script.startswith("#!/bin/bash")
    assert "config.py" in script
    assert "Note to self" in script
    assert "cat 'config.py'" in script


def test_loadplan_add_warning():
    """Test LoadPlan.add_warning() method."""
    plan = LoadPlan()

    plan.add_warning("Test warning")

    assert len(plan.warnings) == 1
    assert plan.warnings[0] == "Test warning"
    assert len(plan.steps) == 1
    assert plan.steps[0].action == PlanAction.WARN


def test_loadstep_str_representation():
    """Test LoadStep.__str__() output."""
    read_step = LoadStep(action=PlanAction.READ, path="test.py", reason="test")
    inject_step = LoadStep(action=PlanAction.INJECT, content="long content here", reason="note")
    warn_step = LoadStep(action=PlanAction.WARN, content="Error!", reason="warning")

    assert "📖 Read:" in str(read_step)
    assert "test.py" in str(read_step)
    assert "💭 Inject:" in str(inject_step)
    assert "long content here" in str(inject_step)
    assert "⚠️" in str(warn_step)
    assert "Error!" in str(warn_step)
