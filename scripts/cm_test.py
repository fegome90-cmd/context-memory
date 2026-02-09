#!/usr/bin/env python3
"""
Simple test runner for context-memory plugin.

Doesn't require pytest - uses built-in assertions and reporting.

Usage:
    python3 cm_test.py [test_name]
"""

import sys
import traceback
from pathlib import Path
from typing import Callable, List, Tuple

# Add src to path
plugin_dir = Path(__file__).parent.parent
sys.path.insert(0, str(plugin_dir / "src"))
sys.path.insert(0, str(plugin_dir / "tests"))


# Colors for output
class Colors:
    GREEN = "\033[92m"
    RED = "\033[91m"
    YELLOW = "\033[93m"
    BLUE = "\033[94m"
    RESET = "\033[0m"
    BOLD = "\033[1m"


# Test result tracking
class TestResults:
    def __init__(self):
        self.passed = 0
        self.failed = 0
        self.errors: List[Tuple[str, str]] = []

    def add_pass(self, name: str):
        self.passed += 1
        print(f"{Colors.GREEN}✓{Colors.RESET} {name}")

    def add_fail(self, name: str, error: str):
        self.failed += 1
        self.errors.append((name, error))
        print(f"{Colors.RED}✗{Colors.RESET} {name}")
        print(f"  {Colors.RED}{error}{Colors.RESET}")

    def summary(self):
        total = self.passed + self.failed
        print()
        print("=" * 60)
        if self.failed == 0:
            print(f"{Colors.GREEN}{Colors.BOLD}All {total} tests passed!{Colors.RESET}")
        else:
            print(f"{Colors.RED}{Colors.BOLD}{self.failed}/{total} tests failed{Colors.RESET}")
            print()
            print("Failures:")
            for name, error in self.errors:
                print(f"\n{Colors.BOLD}{name}:{Colors.RESET}")
                print(f"  {error}")
        print("=" * 60)
        return self.failed == 0


def run_test(name: str, test_func: Callable, results: TestResults):
    """Run a single test function."""
    try:
        test_func()
        results.add_pass(name)
    except AssertionError as e:
        results.add_fail(name, str(e))
    except Exception as e:
        results.add_fail(name, f"{type(e).__name__}: {e}")


# ============================================================================
# Tests for domain/events.py
# ============================================================================

def test_read_event_creation():
    """Test creating a READ event."""
    from domain.events import create_read_event, OperationType

    event = create_read_event("src/app.py", tool="Read", size=1000)

    assert event.operation == OperationType.READ, "Operation should be READ"
    assert event.file_path == "src/app.py", "File path mismatch"
    assert event.tool == "Read", "Tool mismatch"
    assert event.meta["size"] == 1000, "Size metadata missing"
    assert event.is_file_operation is True, "Should be file operation"
    assert event.is_user_intent is False, "Should not be user intent"


def test_prompt_event_creation():
    """Test creating a PROMPT event."""
    from domain.events import create_prompt_event, OperationType

    event = create_prompt_event("/cm-save my-bundle")

    assert event.operation == OperationType.PROMPT, "Operation should be PROMPT"
    assert event.prompt == "/cm-save my-bundle", "Prompt text mismatch"
    assert event.is_file_operation is False, "Should not be file operation"
    assert event.is_user_intent is True, "Should be user intent"


def test_event_validation_absolute_path():
    """Test that absolute paths are rejected."""
    from domain.events import ContextEvent, OperationType, EventSource

    try:
        ContextEvent(
            operation=OperationType.READ,
            ts=1704067200,
            source=EventSource.HOOK,
            file_path="/etc/passwd",  # Absolute path
        )
        raise AssertionError("Should have rejected absolute path")
    except ValueError as e:
        assert "Absolute paths not allowed" in str(e)


def test_event_validation_path_traversal():
    """Test that path traversal is rejected."""
    from domain.events import ContextEvent, OperationType, EventSource

    try:
        ContextEvent(
            operation=OperationType.READ,
            ts=1704067200,
            source=EventSource.HOOK,
            file_path="../../etc/passwd",  # Traversal
        )
        raise AssertionError("Should have rejected path traversal")
    except ValueError as e:
        assert "Path traversal not allowed" in str(e)


def test_event_validation_prompt_requires_text():
    """Test that PROMPT events require prompt text."""
    from domain.events import ContextEvent, OperationType, EventSource

    try:
        ContextEvent(
            operation=OperationType.PROMPT,
            ts=1704067200,
            source=EventSource.USER,
        )
        raise AssertionError("Should have required prompt field")
    except ValueError as e:
        assert "PROMPT events require 'prompt' field" in str(e)


def test_estimated_bytes():
    """Test byte estimation for events."""
    from domain.events import create_read_event, create_prompt_event

    read_event = create_read_event("src/app.py", size=5000)
    assert read_event.estimated_bytes == 5000, "Read event byte estimation failed"

    prompt_event = create_prompt_event("test prompt")
    assert prompt_event.estimated_bytes == len("test prompt"), "Prompt event byte estimation failed"


# ============================================================================
# Tests for domain/pruning.py
# ============================================================================

def test_prune_deduplication():
    """Test that pruning deduplicates events by file path."""
    from domain.events import ContextEvent, OperationType, EventSource
    from domain.pruning import PruningConfig, prune

    events = [
        ContextEvent(
            operation=OperationType.READ,
            ts=1704067200,
            source=EventSource.HOOK,
            file_path="README.md",
            meta={"size": 100},
        ),
        ContextEvent(
            operation=OperationType.READ,
            ts=1704067210,
            source=EventSource.HOOK,
            file_path="README.md",  # Duplicate
            meta={"size": 100},
        ),
        ContextEvent(
            operation=OperationType.READ,
            ts=1704067220,
            source=EventSource.HOOK,
            file_path="src/app.py",
            meta={"size": 200},
        ),
    ]

    config = PruningConfig(max_ops=10, max_bytes_est=10000)
    pruned, report = prune(events, config)

    # Should dedupe README.md (keep latest)
    assert len(pruned) == 2, f"Expected 2 events after deduplication, got {len(pruned)}"
    assert report.original_count == 3, "Original count should be 3"
    assert report.removed_count == 1, "Should have removed 1 duplicate"


def test_prune_budget_enforcement():
    """Test that pruning respects operation budget."""
    from domain.events import ContextEvent, OperationType, EventSource
    from domain.pruning import PruningConfig, prune

    events = [
        ContextEvent(
            operation=OperationType.READ,
            ts=1704067200 + i,
            source=EventSource.HOOK,
            file_path=f"file{i}.py",
            meta={"size": 100},
        )
        for i in range(10)
    ]

    config = PruningConfig(max_ops=5, max_bytes_est=10000)
    pruned, report = prune(events, config)

    assert len(pruned) == 5, f"Should limit to 5 ops, got {len(pruned)}"
    assert report.pruned_count == 5, "Pruned count should be 5"


# ============================================================================
# Tests for infrastructure/repo.py
# ============================================================================

def test_repo_id_generation():
    """Test stable repo ID generation."""
    from infrastructure.repo import generate_stable_repo_id
    import tempfile

    with tempfile.TemporaryDirectory() as tmpdir:
        tmppath = Path(tmpdir)
        id1 = generate_stable_repo_id(tmppath)
        id2 = generate_stable_repo_id(tmppath)

        assert id1 == id2, "Repo ID should be stable"
        assert len(id1) == 10, f"Repo ID should be 10 chars, got {len(id1)}"

        # Check that ID file was created
        id_file = tmppath / ".claude" / "context-memory-id"
        assert id_file.exists(), "ID file should be created"
        assert id_file.read_text().strip() == id1, "ID file content mismatch"


# ============================================================================
# Tests for infrastructure/storage_jsonl.py
# ============================================================================

def test_storage_append_and_read():
    """Test appending to and reading from JSONL storage."""
    from infrastructure.storage_jsonl import JSONLStorage
    from domain.events import create_read_event
    import tempfile

    with tempfile.TemporaryDirectory() as tmpdir:
        storage_path = Path(tmpdir) / "test.jsonl"
        storage = JSONLStorage(storage_path)

        # Append events
        event1 = create_read_event("file1.py", size=100)
        event2 = create_read_event("file2.py", size=200)

        storage.append(event1)
        storage.append(event2)

        # Read back
        events = list(storage.read_all())

        assert len(events) == 2, f"Expected 2 events, got {len(events)}"
        assert events[0].file_path == "file1.py", "First event mismatch"
        assert events[1].file_path == "file2.py", "Second event mismatch"


# ============================================================================
# Main test runner
# ============================================================================

def main():
    """Run all tests."""
    print(f"{Colors.BOLD}{Colors.BLUE}Context-Memory Test Runner{Colors.RESET}")
    print()

    results = TestResults()

    # Domain events tests
    print(f"{Colors.BOLD}Domain Events:{Colors.RESET}")
    run_test("  read_event_creation", test_read_event_creation, results)
    run_test("  prompt_event_creation", test_prompt_event_creation, results)
    run_test("  event_validation_absolute_path", test_event_validation_absolute_path, results)
    run_test("  event_validation_path_traversal", test_event_validation_path_traversal, results)
    run_test("  event_validation_prompt_requires_text", test_event_validation_prompt_requires_text, results)
    run_test("  estimated_bytes", test_estimated_bytes, results)

    # Pruning tests
    print()
    print(f"{Colors.BOLD}Pruning:{Colors.RESET}")
    run_test("  prune_deduplication", test_prune_deduplication, results)
    run_test("  prune_budget_enforcement", test_prune_budget_enforcement, results)

    # Infrastructure tests
    print()
    print(f"{Colors.BOLD}Infrastructure:{Colors.RESET}")
    run_test("  repo_id_generation", test_repo_id_generation, results)
    run_test("  storage_append_and_read", test_storage_append_and_read, results)

    # Print summary
    success = results.summary()

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
