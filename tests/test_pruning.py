"""Tests for pruning strategies."""

from datetime import datetime

import pytest

from domain.events import ContextEvent, OperationType, EventSource
from domain.pruning import (
    PruningConfig,
    prune,
    dedupe_by_path,
    classify_path,
    tag_events,
    sort_by_priority,
    apply_budget,
)


def test_dedupe_by_path_keeps_last_read(sample_events):
    """Test that deduplication keeps the last read per file."""
    pruned = dedupe_by_path(sample_events)

    # Should have 4 events (3 unique + 1 prompt + 1 write)
    # Original: 5 events (2 reads of README.md, 1 read of pricing.py, 1 prompt, 1 write)
    # After dedupe: 4 events (1 read of README.md, 1 read of pricing.py, 1 prompt, 1 write)
    assert len(pruned) == 4

    # The last README read should be kept
    readme_events = [e for e in pruned if e.file_path == "README.md"]
    assert len(readme_events) == 1
    assert readme_events[0].ts == 1704067230  # Last README read


def test_prune_applies_budget(sample_events):
    """Test that pruning respects max_ops budget."""
    config = PruningConfig(max_ops=2)
    pruned, report = prune(sample_events, config)

    assert len(pruned) <= 2
    assert report.pruned_count <= 2


def test_prune_report_contains_stats(sample_events):
    """Test that prune report contains useful statistics."""
    config = PruningConfig(max_ops=10)
    pruned, report = prune(sample_events, config)

    assert report.original_count == len(sample_events)
    assert report.pruned_count == len(pruned)
    assert report.removed_count >= 0
    assert isinstance(report.final_tags, dict)
    assert report.total_bytes_est >= 0


def test_classify_path_core():
    """Test classifying core source files."""
    config = PruningConfig()
    tags = classify_path("src/pricing.py", config)

    assert "core" in tags


def test_classify_path_config():
    """Test classifying configuration files."""
    config = PruningConfig()
    tags = classify_path("pyproject.toml", config)

    assert "config" in tags


def test_classify_path_doc():
    """Test classifying documentation."""
    config = PruningConfig()
    tags = classify_path("README.md", config)

    assert "doc" in tags


def test_classify_path_test():
    """Test classifying test files."""
    config = PruningConfig()
    tags = classify_path("tests/test_pricing.py", config)

    assert "test" in tags


def test_classify_path_noise():
    """Test classifying noise files."""
    config = PruningConfig()
    tags = classify_path("node_modules/package/index.js", config)

    assert "noise" in tags


def test_tag_events_adds_tags_to_meta():
    """Test that tag_events adds tags to event metadata."""
    from domain.events import create_read_event

    config = PruningConfig()
    event = create_read_event("src/app.py")

    tagged = tag_events([event], config)

    assert len(tagged) == 1
    assert "tags" in tagged[0].meta
    assert "core" in tagged[0].meta["tags"]


def test_sort_by_priority_pins_prompts():
    """Test that user prompts are prioritized."""
    from domain.events import create_read_event, create_prompt_event

    config = PruningConfig()
    events = [
        create_read_event("src/test.py"),
        create_prompt_event("Important user note"),
        create_read_event("src/other.py"),
    ]

    tagged = tag_events(events, config)
    sorted_events = sort_by_priority(tagged, config)

    # Prompt should be first (highest priority)
    assert sorted_events[0].operation == OperationType.PROMPT


def test_apply_budget_limits_ops():
    """Test that apply_budget respects max_ops."""
    from domain.events import create_read_event

    config = PruningConfig(max_ops=3)

    events = [
        create_read_event(f"src/file{i}.py")
        for i in range(10)
    ]

    tagged = tag_events(events, config)
    budgeted = apply_budget(tagged, config)

    assert len(budgeted) <= 3


def test_apply_budget_limits_bytes():
    """Test that apply_budget respects max_bytes."""
    from domain.events import create_read_event

    config = PruningConfig(max_ops=100, max_bytes_est=5000)

    events = [
        create_read_event(f"src/file{i}.py", size=1000)
        for i in range(10)
    ]

    tagged = tag_events(events, config)
    budgeted = apply_budget(tagged, config)

    # Should only fit ~5 files (5 * 1000 = 5000)
    assert len(budgeted) <= 5
