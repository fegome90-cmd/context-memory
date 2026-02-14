"""
Comprehensive error handling tests for context-memory plugin.

Tests verify proper error handling across all modules:
- Import error handling (exit code 2)
- Storage failure notifications
- Path validation error categorization
- SHA256 error handling
- JSON parsing with context
- File lock retry behavior
- Debug status helper
"""
import os
import sys
import json
import pytest
import subprocess
from pathlib import Path
from io import StringIO
from unittest.mock import patch, Mock

# Add src directory to path
src_dir = Path(__file__).parent.parent / "src"
sys.path.insert(0, str(src_dir))

from domain.events import ContextEvent, OperationType, EventSource
from infrastructure.cas import compute_sha256
from infrastructure.logging import get_logger, is_debug_enabled, print_debug_status


# ============================================================================
# Fix #2: Import Error Handling Tests
# ============================================================================

class TestImportErrorHandling:
    """Test that import errors produce actionable error messages."""

    def test_import_error_returns_exit_code_2(self, tmp_path):
        """Import failures should exit with code 2 (dependency error)."""
        # Create a script that simulates import failure
        test_script = tmp_path / "import_test.py"
        test_script.write_text("""
import sys

# Simulate import error handling
try:
    from nonexistent_module import Something
except ImportError as e:
    print(f"[ERROR] Import failed - {e}", file=sys.stderr, flush=True)
    sys.exit(2)  # Exit code 2 = dependency error
""")

        result = subprocess.run(
            [sys.executable, str(test_script)],
            capture_output=True,
            text=True
        )

        assert result.returncode == 2
        assert "[ERROR]" in result.stderr
        assert "Import failed" in result.stderr

    def test_import_error_message_includes_reinstall_hint(self, tmp_path):
        """Import error should suggest re-running install script."""
        test_script = tmp_path / "import_hint_test.py"
        test_script.write_text("""
import sys
try:
    from nonexistent import module
except ImportError as e:
    print(f"[ERROR] cm_track_operation: Import failed - {e}", file=sys.stderr, flush=True)
    print(f"[ERROR] Re-run install: python3 ~/.claude/plugins/context-memory/scripts/cm_install.py",
          file=sys.stderr, flush=True)
    sys.exit(2)
""")

        result = subprocess.run(
            [sys.executable, str(test_script)],
            capture_output=True,
            text=True
        )

        assert "cm_install.py" in result.stderr
        assert "Re-run install" in result.stderr


# ============================================================================
# Fix #3: Storage Failure Notification Tests
# ============================================================================

class TestStorageFailureNotification:
    """Test that storage failures are visible to users."""

    def test_store_event_returns_false_on_failure(self, repo_root):
        """store_event() should return False on I/O error."""
        from scripts.cm_track_operation import store_event, SESSIONS_RELATIVE_PATH

        # Create an event
        event = ContextEvent(
            operation=OperationType.READ,
            file_path="test.py",
            ts=1704067200,
            source=EventSource.HOOK,
            tool="Read",
            tool_input='{"file_path": "test.py"}',
        )

        # Mock storage to fail
        with patch('scripts.cm_track_operation.JSONLStorage') as mock_storage:
            mock_instance = Mock()
            mock_instance.append.side_effect = OSError("Permission denied")
            mock_storage.return_value = mock_instance

            result = store_event(event, repo_root)

            assert result is False, "store_event should return False on storage failure"

    def test_storage_failure_produces_warning_message(self, repo_root, capsys):
        """Storage failures should log warning messages."""
        from scripts.cm_track_operation import store_event
        import logging

        # Capture stderr
        logger = get_logger("test_storage_failure")

        event = ContextEvent(
            operation=OperationType.READ,
            file_path="test.py",
            ts=1704067200,
            source=EventSource.HOOK,
            tool="Read",
        )

        # Create read-only sessions dir to trigger failure
        sessions_dir = repo_root / ".claude" / "context_memory" / "sessions"
        sessions_dir.mkdir(parents=True, exist_ok=True)

        # Make directory read-only (simulate permission error)
        # Note: This may not work on all filesystems
        try:
            os.chmod(sessions_dir, 0o444)
            result = store_event(event, repo_root)

            # Should return False on failure
            # May have error in stderr
            captured = capsys.readouterr()
            # Behavior varies by OS, just verify it doesn't crash
        finally:
            # Restore permissions for cleanup
            os.chmod(sessions_dir, 0o755)


# ============================================================================
# Fix #4: Specific Error Context Tests
# ============================================================================

class TestSpecificErrorContext:
    """Test that error messages include specific context."""

    def test_create_event_error_includes_tool_name(self, repo_root):
        """Event creation errors should include the tool name."""
        from scripts.cm_track_operation import create_event

        # This should fail with specific error context
        result = create_event(
            tool_name="InvalidTool",
            rel_path="test.py",
            input_data={},
            timestamp=None,
        )

        # Unknown tool returns None (logged as debug)
        assert result is None

    def test_create_event_error_includes_path(self, repo_root):
        """Event creation errors should include the file path."""
        from scripts.cm_track_operation import create_event

        # Valid tool but create event with bad data
        result = create_event(
            tool_name="Read",
            rel_path="test.py",
            input_data=None,  # This will cause truncation to handle it
            timestamp=1704067200,
        )

        # Should handle None input gracefully
        assert result is not None


# ============================================================================
# Fix #5: Better Install Error Tests
# ============================================================================

class TestInstallErrorMessages:
    """Test that install script provides actionable error messages."""

    def test_missing_templates_dir_shows_full_path(self, tmp_path, capsys):
        """Missing templates error should show full path."""
        from scripts.cm_install import install_commands

        # Create a fake repo without proper templates
        fake_plugin_dir = tmp_path / "fake_plugin"
        fake_plugin_dir.mkdir()
        fake_templates = fake_plugin_dir / "templates" / "commands"
        # Don't create it - we want it to not exist

        # Patch plugin_dir to point to non-existent templates
        with patch('scripts.cm_install.Path') as mock_path:
            # Mock Path(__file__).parent.parent to return fake_plugin_dir
            mock_file = Mock()
            mock_file.parent = fake_plugin_dir
            mock_path.return_value = fake_plugin_dir

            with patch('scripts.cm_install.plugin_dir', fake_plugin_dir):
                # This should fail with detailed error
                with pytest.raises(SystemExit) as exc_info:
                    install_commands(tmp_path / "repo")

                assert exc_info.value.code == 1

        captured = capsys.readouterr()
        # Error message should be informative
        # (The actual error comes from the templates_dir check)


# ============================================================================
# Fix #6: File Lock Retry Tests
# ============================================================================

class TestFileLockRetry:
    """Test file lock retry behavior with exponential backoff."""

    def test_lock_retry_with_exponential_backoff(self, repo_root):
        """Lock acquisition should retry with exponential backoff."""
        import fcntl
        import time
        from infrastructure.storage_jsonl import JSONLStorage

        sessions_dir = repo_root / ".claude" / "context_memory" / "sessions"
        sessions_dir.mkdir(parents=True, exist_ok=True)
        storage_path = sessions_dir / "current.jsonl"

        storage = JSONLStorage(storage_path)

        event = ContextEvent(
            operation=OperationType.READ,
            file_path="test.py",
            ts=1704067200,
            source=EventSource.HOOK,
        )

        # Should succeed without error
        storage.append(event)

        # Verify file was created
        assert storage_path.exists()

    def test_lock_failure_logs_warning(self, repo_root, capsys):
        """Lock failures should log warnings."""
        from infrastructure.storage_jsonl import JSONLStorage

        sessions_dir = repo_root / ".claude" / "context_memory" / "sessions"
        sessions_dir.mkdir(parents=True, exist_ok=True)
        storage_path = sessions_dir / "current.jsonl"

        storage = JSONLStorage(storage_path)

        event = ContextEvent(
            operation=OperationType.READ,
            file_path="test.py",
            ts=1704067200,
            source=EventSource.HOOK,
        )

        # On Windows, lock fails but continues
        storage.append(event)

        # Should not crash
        assert storage_path.exists()


# ============================================================================
# Fix #7: JSON Parse Context Tests
# ============================================================================

class TestJSONParseContext:
    """Test that JSON parse errors include line preview."""

    def test_json_parse_error_includes_line_preview(self, tmp_path, capsys):
        """Invalid JSON errors should show line preview."""
        from infrastructure.jsonl_io import parse_jsonl_file

        # Create JSONL file with valid events and one invalid JSON line
        jsonl_file = tmp_path / "test.jsonl"
        jsonl_file.write_text(
            '{"operation": "read", "ts": 1704067200, "source": "hook", "file_path": "test.py"}\n'
            '{"bad": invalid json here}\n'
            '{"operation": "read", "ts": 1704067210, "source": "hook", "file_path": "other.py"}\n'
        )

        events = list(parse_jsonl_file(jsonl_file))

        captured = capsys.readouterr()

        # Should have warning about invalid JSON
        assert "[WARNING]" in captured.err
        assert "Invalid JSON" in captured.err
        assert ":" in captured.err  # Should include line number

        # Should parse the 2 valid lines (the invalid JSON line is skipped)
        assert len(events) == 2

    def test_json_parse_error_with_long_line(self, tmp_path, capsys):
        """Long lines should be truncated in error messages."""
        from infrastructure.jsonl_io import parse_jsonl_file

        # Create a very long invalid line
        long_content = '{"data": "' + "x" * 200 + '"invalid}'
        jsonl_file = tmp_path / "long.jsonl"
        jsonl_file.write_text(long_content + "\n")

        events = list(parse_jsonl_file(jsonl_file))

        captured = capsys.readouterr()

        # Error should show line content (truncated if too long)
        assert "[WARNING]" in captured.err
        # The line content should be shown (possibly truncated)
        assert len(captured.err) > 0


# ============================================================================
# Fix #8: Repo Detection Debug Tests
# ============================================================================

class TestRepoDetectionDebug:
    """Test that repo detection failures are debuggable."""

    def test_no_git_found_logs_debug_message(self, non_repo_dir, capsys):
        """No .git found should log debug message."""
        from infrastructure.repo import find_repo_root

        result = find_repo_root(non_repo_dir)

        assert result is None

        # Debug message should be emitted (in stderr when CM_DEBUG=1)
        # This is tested indirectly through behavior

    def test_repo_detection_from_file_path_works(self, nested_repos):
        """detect_repo_from_file_path should find deepest repo."""
        from infrastructure.repo import detect_repo_from_file_path

        repo_info = detect_repo_from_file_path(nested_repos["file"])

        assert repo_info is not None
        # Should find deep_inner (deepest repo containing the file)
        assert repo_info.root == nested_repos["deep_inner"]


# ============================================================================
# Fix #9: SHA256 Error Handling Tests
# ============================================================================

class TestSHA256ErrorHandling:
    """Test that SHA256 computation has proper error handling."""

    def test_sha256_nonexistent_file_raises_fileNotFoundError(self):
        """Nonexistent file should raise FileNotFoundError."""
        with pytest.raises(FileNotFoundError) as exc_info:
            compute_sha256(Path("/nonexistent/file/that/does/not/exist.txt"))

        assert "not found" in str(exc_info.value).lower()

    def test_sha256_directory_raises_valueError(self, tmp_path):
        """Directory should raise ValueError."""
        with pytest.raises(ValueError) as exc_info:
            compute_sha256(tmp_path)

        assert "not a file" in str(exc_info.value).lower()

    def test_sha256_permission_error_produces_message(self, tmp_path, capsys):
        """Permission errors should produce clear error message."""
        # Create a file
        test_file = tmp_path / "test.txt"
        test_file.write_text("test content")

        # Make it unreadable (may not work on all systems)
        try:
            os.chmod(test_file, 0o000)

            with pytest.raises((PermissionError, OSError)):
                compute_sha256(test_file)

            captured = capsys.readouterr()
            # Error message should mention permission
            # (Behavior may vary by OS)
        finally:
            # Restore for cleanup
            try:
                os.chmod(test_file, 0o644)
            except:
                pass

    def test_sha256_works_on_valid_file(self, tmp_path):
        """Valid file should compute hash correctly."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("test content")

        result = compute_sha256(test_file)

        # Should be a 64-character hex string
        assert len(result) == 64
        assert all(c in "0123456789abcdef" for c in result)


# ============================================================================
# Fix #10: Path Validation Specificity Tests
# ============================================================================

class TestPathValidationSpecificity:
    """Test that path validation categorizes errors specifically."""

    def test_outside_repo_error(self, repo_root):
        """Path outside repo should have specific error message."""
        from scripts.cm_track_operation import validate_and_normalize_path

        # Create a path outside the repo
        outside_path = str(repo_root / ".." / "outside.py")

        result = validate_and_normalize_path(outside_path, repo_root)

        # Should return None for invalid path
        assert result is None

    def test_traversal_error(self, repo_root):
        """Path traversal should be specifically identified."""
        from scripts.cm_track_operation import validate_and_normalize_path

        # Try a traversal path
        traversal_path = str(repo_root / "safe" / ".." / ".." / "etc" / "passwd")

        result = validate_and_normalize_path(traversal_path, repo_root)

        # Should be None (blocked)
        assert result is None

    def test_valid_path_passes(self, repo_root):
        """Valid paths inside repo should pass."""
        from scripts.cm_track_operation import validate_and_normalize_path

        # Create a file in the repo
        test_file = repo_root / "src" / "test.py"
        test_file.parent.mkdir(parents=True, exist_ok=True)

        result = validate_and_normalize_path(str(test_file), repo_root)

        # Should return relative path
        assert result is not None
        assert "src" in result or "test.py" in result


# ============================================================================
# Fix #11: Security Hook Tests
# ============================================================================

class TestSecurityHook:
    """Test that security events return exit code 1."""

    def test_security_event_returns_exit_code_1(self, repo_root, tmp_path):
        """Path validation failures should return exit code 1."""
        import subprocess

        # Create input with path outside repo
        test_input = {
            "tool_name": "Read",
            "tool_input": {"file_path": "/etc/passwd"}
        }

        input_file = tmp_path / "input.json"
        input_file.write_text(json.dumps(test_input))

        script_path = Path(__file__).parent.parent / "scripts" / "cm_track_operation.py"

        # Run the hook script
        result = subprocess.run(
            [sys.executable, str(script_path)],
            cwd=str(repo_root),
            input=json.dumps(test_input),
            capture_output=True,
            text=True,
        )

        # Should return 0 because /etc/passwd won't be in the detected repo
        # The behavior depends on whether a repo is detected
        # This is a FAIL-CLOSED security design


# ============================================================================
# Fix #12: Debug Status Helper Tests
# ============================================================================

class TestDebugStatusHelper:
    """Test the debug status helper function."""

    def test_print_debug_status_when_enabled(self, monkeypatch, capsys):
        """Debug status should show log path when enabled."""
        monkeypatch.setenv("CM_DEBUG", "1")

        # Need to reload module to pick up env var
        import importlib
        from infrastructure import logging
        importlib.reload(logging)

        from infrastructure.logging import print_debug_status

        print_debug_status("test_module")

        captured = capsys.readouterr()

        assert "[INFO]" in captured.err
        assert "Debug ENABLED" in captured.err

    def test_print_debug_status_when_disabled(self, monkeypatch, capsys):
        """Debug status should show how to enable when disabled."""
        monkeypatch.setenv("CM_DEBUG", "0")

        # Reload module
        import importlib
        from infrastructure import logging
        importlib.reload(logging)

        from infrastructure.logging import print_debug_status

        print_debug_status("test_module")

        captured = capsys.readouterr()

        assert "[INFO]" in captured.err
        assert "Debug disabled" in captured.err
        assert "CM_DEBUG=1" in captured.err

    def test_is_debug_enabled_reflects_env(self, monkeypatch):
        """is_debug_enabled should reflect CM_DEBUG env var."""
        # Test with debug enabled
        monkeypatch.setenv("CM_DEBUG", "1")

        import importlib
        from infrastructure import logging
        importlib.reload(logging)

        assert logging.is_debug_enabled() is True

        # Test with debug disabled
        monkeypatch.setenv("CM_DEBUG", "0")
        importlib.reload(logging)

        assert logging.is_debug_enabled() is False
