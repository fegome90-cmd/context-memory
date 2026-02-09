"""Shared pytest fixtures for context-memory tests."""
import os
import sys
import pytest
from pathlib import Path

# Add src directory to path for imports
src_dir = Path(__file__).parent.parent / "src"
sys.path.insert(0, str(src_dir))

from domain.events import ContextEvent, OperationType, EventSource


@pytest.fixture
def repo_root(tmp_path, monkeypatch):
    """
    Create a temporary git repo root and change cwd to it.

    This is critical for path tests because normalize_path() uses Path.cwd()
    for resolving relative paths.
    """
    repo_root = tmp_path / "test_repo"
    repo_root.mkdir()

    # Create .git directory to make it a git repo
    (repo_root / ".git").mkdir()

    # CRITICAL: Change cwd to repo_root BEFORE returning
    # This ensures Path.cwd() in code under test returns repo_root
    monkeypatch.chdir(repo_root)

    return repo_root


@pytest.fixture
def temp_dir(tmp_path):
    """Create a temporary directory for testing."""
    test_dir = tmp_path / "test_dir"
    test_dir.mkdir()
    return test_dir


@pytest.fixture
def non_repo_dir(tmp_path, monkeypatch):
    """Create a temporary directory without .git (for testing detection)."""
    non_repo = tmp_path / "non_repo"
    non_repo.mkdir()
    monkeypatch.chdir(non_repo)
    return non_repo


@pytest.fixture
def sample_events():
    """
    Create sample events for pruning tests.

    Returns a list with:
    - 2 reads of README.md (different timestamps)
    - 1 read of pricing.py
    - 1 prompt event
    - 1 write event
    """
    return [
        ContextEvent(
            operation=OperationType.READ,
            file_path="README.md",
            ts=1704067200,  # First README read
            source=EventSource.USER,
            meta={"size": 1000},
        ),
        ContextEvent(
            operation=OperationType.READ,
            file_path="pricing.py",
            ts=1704067215,
            source=EventSource.USER,
            meta={"size": 500},
        ),
        ContextEvent(
            operation=OperationType.PROMPT,
            file_path=None,
            ts=1704067220,
            source=EventSource.USER,
            prompt="Add pricing feature",
            meta={},
        ),
        ContextEvent(
            operation=OperationType.READ,
            file_path="README.md",
            ts=1704067230,  # Second README read (later)
            source=EventSource.USER,
            meta={"size": 1000},
        ),
        ContextEvent(
            operation=OperationType.WRITE,
            file_path="pricing.py",
            ts=1704067245,
            source=EventSource.USER,
            meta={"size": 600},
        ),
    ]


@pytest.fixture
def nested_repos(tmp_path):
    """
    Create a structure of nested git repositories for testing detect_repo_from_file_path().

    Structure:
        /tmp/outer_repo/.git/
          └── inner_repo/.git/
              └── deep_inner/.git/
                  └── test_file.py

    This fixture is used to verify that detect_repo_from_file_path() selects
    the DEEPEST (most specific) repo when multiple repos contain the file.

    Returns:
        dict: {
            "outer": Path to outer_repo,
            "inner": Path to inner_repo,
            "deep_inner": Path to deep_inner,
            "file": Path to test_file.py (inside deep_inner)
        }
    """
    # Create outer repo
    outer = tmp_path / "outer_repo"
    outer.mkdir()
    (outer / ".git").mkdir()

    # Create inner repo (nested inside outer)
    inner = outer / "inner_repo"
    inner.mkdir()
    (inner / ".git").mkdir()

    # Create deep_inner repo (nested inside inner)
    deep_inner = inner / "deep_inner"
    deep_inner.mkdir()
    (deep_inner / ".git").mkdir()

    # Create a test file in the deepest repo
    test_file = deep_inner / "test_file.py"
    test_file.write_text("# Test file in deep_inner repo\nx = 1\n")

    return {
        "outer": outer,
        "inner": inner,
        "deep_inner": deep_inner,
        "file": test_file,
    }
