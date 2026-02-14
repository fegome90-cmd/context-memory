"""Tests for the main hook script (cm_track_operation.py)."""
import json
import os
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock
import sys

# Add scripts to path
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))


@pytest.fixture
def temp_repo(tmp_path):
    """Create a temporary git repository."""
    repo_root = tmp_path / "test_repo"
    repo_root.mkdir()
    (repo_root / ".git").mkdir()

    # Change to repo directory
    original_cwd = os.getcwd()
    os.chdir(repo_root)

    yield repo_root

    os.chdir(original_cwd)


def test_hook_rejects_invalid_json(temp_repo, capsys):
    """Test that hook handles invalid JSON gracefully."""
    # Mock stdin with invalid JSON
    mock_stdin = MagicMock()
    mock_stdin.read.return_value = "not valid json"

    with patch('sys.stdin', mock_stdin):
        # Should not raise exception
        import cm_track_operation
        cm_track_operation.main()

    # Should exit silently (no output)
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == ""


def test_hook_skips_non_rwe_tools(temp_repo):
    """Test that hook ignores tools other than Read/Write/Edit."""
    input_data = {
        "toolUse": {
            "name": "Glob",  # Not R/W/E
            "input": {"pattern": "*.py"}
        },
        "timestamp": 1234567890
    }

    mock_stdin = MagicMock()
    mock_stdin.read.return_value = json.dumps(input_data)

    with patch('sys.stdin', mock_stdin):
        import cm_track_operation
        cm_track_operation.main()

    # Should not create any files
    sessions_dir = Path(".claude/context_memory/sessions")
    assert not sessions_dir.exists()


def test_hook_tracks_read_operation(temp_repo):
    """Test that hook correctly tracks Read operations."""
    # Create a test file to read
    test_file = temp_repo / "src" / "app.py"
    test_file.parent.mkdir(parents=True)
    test_file.write_text("print('hello')")

    input_data = {
        "toolUse": {
            "name": "Read",
            "input": {"file_path": str(test_file)}
        },
        "timestamp": 1234567890
    }

    mock_stdin = MagicMock()
    mock_stdin.read.return_value = json.dumps(input_data)

    with patch('sys.stdin', mock_stdin):
        import cm_track_operation
        cm_track_operation.main()

    # Verify event was stored
    sessions_dir = Path(".claude/context_memory/sessions")
    current_file = sessions_dir / "current.jsonl"

    assert current_file.exists()

    events = list(current_file.read_text().strip().split("\n"))
    assert len(events) == 1

    event = json.loads(events[0])
    assert event["operation"] == "read"
    assert "src/app.py" in event["file_path"]


def test_hook_rejects_paths_outside_repo(temp_repo, capsys):
    """Test that hook handles absolute paths outside any repo gracefully.

    With file_path-based repo detection, an absolute path like /etc/passwd
    has no .git above it, so the hook skips it (return 0, no repo found).
    This is correct: there's no repo to protect, so no security event.
    """
    # Try to read a file outside any repo
    outside_file = "/etc/passwd"

    input_data = {
        "toolUse": {
            "name": "Read",
            "input": {"file_path": outside_file}
        },
        "timestamp": 1234567890
    }

    mock_stdin = MagicMock()
    mock_stdin.read.return_value = json.dumps(input_data)

    with patch('sys.stdin', mock_stdin):
        import cm_track_operation
        exit_code = cm_track_operation.main()

    # With file_path-based detection: no repo found → graceful exit
    assert exit_code == 0

    # Should not create any files
    sessions_dir = Path(".claude/context_memory/sessions")
    current_file = sessions_dir / "current.jsonl"
    assert not current_file.exists()


def test_hook_blocks_path_traversal_attacks(temp_repo, capsys):
    """Test that hook blocks path traversal attempts (FAIL-CLOSED)."""
    # Try to read a file using path traversal
    traversal_path = "../../etc/passwd"

    input_data = {
        "toolUse": {
            "name": "Read",
            "input": {"file_path": traversal_path}
        },
        "timestamp": 1234567890
    }

    mock_stdin = MagicMock()
    mock_stdin.read.return_value = json.dumps(input_data)

    with patch('sys.stdin', mock_stdin):
        import cm_track_operation
        exit_code = cm_track_operation.main()

    # Should return error code for security event
    assert exit_code == 1

    # Should log security warning to stderr
    captured = capsys.readouterr()
    assert "SECURITY: Path validation blocked" in captured.err
    assert traversal_path in captured.err

    # Should not create any files
    sessions_dir = Path(".claude/context_memory/sessions")
    current_file = sessions_dir / "current.jsonl"
    assert not current_file.exists()


def test_hook_handles_permission_denied(temp_repo, capsys):
    """Test that hook handles storage failures gracefully."""
    # Create a test file
    test_file = temp_repo / "test.py"
    test_file.write_text("x = 1")

    input_data = {
        "toolUse": {
            "name": "Read",
            "input": {"file_path": str(test_file)}
        },
        "timestamp": 1234567890
    }

    mock_stdin = MagicMock()
    mock_stdin.read.return_value = json.dumps(input_data)

    # Mock open to raise permission error
    def mock_open(*args, **kwargs):
        raise PermissionError("Denied")

    with patch('sys.stdin', mock_stdin):
        with patch('builtins.open', mock_open):
            import cm_track_operation
            # Should not raise exception
            cm_track_operation.main()

    # Should exit silently
    captured = capsys.readouterr()
    assert captured.out == ""


def test_hook_creates_sessions_directory(temp_repo):
    """Test that hook creates .claude/context_memory/sessions directory."""
    test_file = temp_repo / "test.py"
    test_file.write_text("x = 1")

    input_data = {
        "toolUse": {
            "name": "Read",
            "input": {"file_path": str(test_file)}
        },
        "timestamp": 1234567890
    }

    mock_stdin = MagicMock()
    mock_stdin.read.return_value = json.dumps(input_data)

    with patch('sys.stdin', mock_stdin):
        import cm_track_operation
        cm_track_operation.main()

    # Verify directory structure
    sessions_dir = Path(".claude/context_memory/sessions")
    assert sessions_dir.exists()
    assert sessions_dir.is_dir()


def test_hook_handles_multiedit(temp_repo):
    """Test that hook correctly extracts file path from MultiEdit."""
    test_file = temp_repo / "src" / "app.py"
    test_file.parent.mkdir(parents=True)
    test_file.write_text("x = 1")

    input_data = {
        "toolUse": {
            "name": "MultiEdit",
            "input": {
                "files": [
                    {"file": str(test_file), "edit": "x = 2"}
                ]
            }
        },
        "timestamp": 1234567890
    }

    mock_stdin = MagicMock()
    mock_stdin.read.return_value = json.dumps(input_data)

    with patch('sys.stdin', mock_stdin):
        import cm_track_operation
        cm_track_operation.main()

    # Verify event was stored (using temp_repo path since we changed directory)
    sessions_dir = temp_repo / ".claude" / "context_memory" / "sessions"
    current_file = sessions_dir / "current.jsonl"

    assert current_file.exists(), f"File not found: {current_file}"

    events = list(current_file.read_text().strip().split("\n"))
    assert len(events) == 1

    event = json.loads(events[0])
    assert event["operation"] == "multi_edit"
    assert "src/app.py" in event["file_path"]


def test_hook_skips_when_no_repo_detected(tmp_path, monkeypatch):
    """Test that hook does nothing when not in a git repo."""
    # Create directory without .git
    non_repo = tmp_path / "non_repo"
    non_repo.mkdir()
    monkeypatch.chdir(non_repo)

    test_file = non_repo / "test.py"
    test_file.write_text("x = 1")

    input_data = {
        "toolUse": {
            "name": "Read",
            "input": {"file_path": str(test_file)}
        },
        "timestamp": 1234567890
    }

    mock_stdin = MagicMock()
    mock_stdin.read.return_value = json.dumps(input_data)

    with patch('sys.stdin', mock_stdin):
        import cm_track_operation
        cm_track_operation.main()

    # Should not create any files
    sessions_dir = Path(".claude/context_memory/sessions")
    assert not sessions_dir.exists()


# ============================================================
# Tests for file_path-based repo detection (fix for cwd bug)
# ============================================================


def test_hook_finds_repo_from_absolute_path(tmp_path):
    """
    Test that hook finds repo from absolute file_path even when cwd is elsewhere.

    This is the core fix: Claude Code runs hooks with cwd != project dir,
    but file_path in stdin is absolute. The hook must use file_path to find .git.
    """
    # Create repo
    repo = tmp_path / "project"
    repo.mkdir()
    (repo / ".git").mkdir()
    test_file = repo / "src" / "app.py"
    test_file.parent.mkdir(parents=True)
    test_file.write_text("print('hello')")

    # cwd is /tmp (NOT the repo)
    original_cwd = os.getcwd()
    os.chdir(tmp_path)

    try:
        input_data = {
            "toolUse": {
                "name": "Read",
                "input": {"file_path": str(test_file)}
            },
            "timestamp": 1234567890
        }

        mock_stdin = MagicMock()
        mock_stdin.read.return_value = json.dumps(input_data)

        with patch('sys.stdin', mock_stdin):
            import cm_track_operation
            exit_code = cm_track_operation.main()

        assert exit_code == 0

        # Verify event was stored IN THE REPO (not in cwd)
        current_file = repo / ".claude" / "context_memory" / "sessions" / "current.jsonl"
        assert current_file.exists(), f"Event file not found at {current_file}"

        events = current_file.read_text().strip().split("\n")
        assert len(events) == 1

        event = json.loads(events[0])
        assert event["operation"] == "read"
        assert event["file_path"] == "src/app.py"
    finally:
        os.chdir(original_cwd)


def test_hook_finds_repo_from_nested_path(tmp_path):
    """
    Test that hook finds repo when file_path is 3 levels deep.
    """
    repo = tmp_path / "project"
    repo.mkdir()
    (repo / ".git").mkdir()
    nested_file = repo / "a" / "b" / "c" / "deep.py"
    nested_file.parent.mkdir(parents=True)
    nested_file.write_text("x = 1")

    original_cwd = os.getcwd()
    os.chdir(tmp_path)

    try:
        input_data = {
            "toolUse": {
                "name": "Write",
                "input": {"file_path": str(nested_file)}
            },
            "timestamp": 1234567890
        }

        mock_stdin = MagicMock()
        mock_stdin.read.return_value = json.dumps(input_data)

        with patch('sys.stdin', mock_stdin):
            import cm_track_operation
            exit_code = cm_track_operation.main()

        assert exit_code == 0

        current_file = repo / ".claude" / "context_memory" / "sessions" / "current.jsonl"
        assert current_file.exists()

        event = json.loads(current_file.read_text().strip())
        assert event["file_path"] == "a/b/c/deep.py"
    finally:
        os.chdir(original_cwd)


def test_hook_fails_gracefully_outside_repo(tmp_path):
    """
    Test that hook returns 0 gracefully when file_path has no .git above it.
    """
    no_repo = tmp_path / "no_repo"
    no_repo.mkdir()
    test_file = no_repo / "random.py"
    test_file.write_text("x = 1")

    input_data = {
        "toolUse": {
            "name": "Read",
            "input": {"file_path": str(test_file)}
        },
        "timestamp": 1234567890
    }

    mock_stdin = MagicMock()
    mock_stdin.read.return_value = json.dumps(input_data)

    with patch('sys.stdin', mock_stdin):
        import cm_track_operation
        exit_code = cm_track_operation.main()

    assert exit_code == 0


def test_hook_ignores_cwd(tmp_path):
    """
    Test that the hook works when cwd is irrelevant (e.g., /tmp).

    This simulates the real Claude Code scenario: cwd is some random dir,
    but file_path in stdin points to the actual project.
    """
    # Create repo somewhere
    repo = tmp_path / "real_project"
    repo.mkdir()
    (repo / ".git").mkdir()
    test_file = repo / "main.py"
    test_file.write_text("x = 1")

    # cwd is a completely unrelated directory
    unrelated = tmp_path / "unrelated_dir"
    unrelated.mkdir()
    original_cwd = os.getcwd()
    os.chdir(unrelated)

    try:
        input_data = {
            "toolUse": {
                "name": "Edit",
                "input": {"file_path": str(test_file)}
            },
            "timestamp": 9999999999
        }

        mock_stdin = MagicMock()
        mock_stdin.read.return_value = json.dumps(input_data)

        with patch('sys.stdin', mock_stdin):
            import cm_track_operation
            exit_code = cm_track_operation.main()

        assert exit_code == 0

        current_file = repo / ".claude" / "context_memory" / "sessions" / "current.jsonl"
        assert current_file.exists()

        event = json.loads(current_file.read_text().strip())
        assert event["operation"] == "edit"
        assert event["file_path"] == "main.py"
    finally:
        os.chdir(original_cwd)
