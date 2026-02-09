"""Tests for check_bundle_integrity.py - Precommit hook for JSONL validation."""
import json
import pytest
import subprocess
from pathlib import Path


@pytest.fixture
def bundle_script():
    """Path to the bundle integrity checker script."""
    return Path(__file__).parent.parent / "scripts" / "check_bundle_integrity.py"


def create_test_jsonl(tmp_path: Path, content: str) -> Path:
    """Helper to create a test JSONL file."""
    jsonl_file = tmp_path / "test.jsonl"
    jsonl_file.write_text(content)
    return jsonl_file


def test_rejects_invalid_json(bundle_script, tmp_path):
    """Test that invalid JSON in JSONL is rejected."""
    # Create JSONL with invalid JSON on line 2
    content = '''{"operation": "read", "file": "test.py"}
this is not json
{"operation": "write", "file": "out.py"}
'''
    jsonl_file = create_test_jsonl(tmp_path, content)

    # Run script
    result = subprocess.run(
        ["python3", str(bundle_script), str(jsonl_file)],
        capture_output=True,
        text=True
    )

    # Should fail
    assert result.returncode != 0
    assert "Invalid JSON" in result.stderr or "Invalid JSON" in result.stdout


def test_rejects_secrets(bundle_script, tmp_path):
    """Test that secrets in JSONL are detected."""
    # Create JSONL with AWS API key
    content = f'''{{"operation": "read", "file": "config.py", "tool_input": "AKIAIOSFODNN7EXAMPLE"}}
{{"operation": "write", "file": "out.py"}}
'''
    jsonl_file = create_test_jsonl(tmp_path, content)

    # Run script
    result = subprocess.run(
        ["python3", str(bundle_script), str(jsonl_file)],
        capture_output=True,
        text=True
    )

    # Should warn about secret (but might not fail - depends on severity)
    output = result.stdout + result.stderr
    assert "secret" in output.lower() or "AKIA" in output


def test_accepts_valid_jsonl(bundle_script, tmp_path):
    """Test that valid JSONL without secrets is accepted."""
    # Create valid JSONL
    content = '''{"operation": "read", "file": "test.py"}
{"operation": "write", "file": "out.py", "content": "hello"}
{"operation": "prompt", "prompt": "/cm-save"}
'''
    jsonl_file = create_test_jsonl(tmp_path, content)

    # Run script
    result = subprocess.run(
        ["python3", str(bundle_script), str(jsonl_file)],
        capture_output=True,
        text=True
    )

    # Should pass
    assert result.returncode == 0


def test_skips_empty_lines(bundle_script, tmp_path):
    """Test that empty lines are skipped (not treated as invalid JSON)."""
    # Create JSONL with empty lines
    content = '''{"operation": "read", "file": "test.py"}

{"operation": "write", "file": "out.py"}

'''
    jsonl_file = create_test_jsonl(tmp_path, content)

    # Run script
    result = subprocess.run(
        ["python3", str(bundle_script), str(jsonl_file)],
        capture_output=True,
        text=True
    )

    # Should pass (empty lines are ok)
    assert result.returncode == 0


def test_handles_broken_symlink(bundle_script, tmp_path):
    """Test that broken symlinks are handled gracefully."""
    # Create broken symlink
    jsonl_file = tmp_path / "broken_link.jsonl"
    jsonl_file.symlink_to(tmp_path / "nonexistent.jsonl")

    # Run script
    result = subprocess.run(
        ["python3", str(bundle_script), str(jsonl_file)],
        capture_output=True,
        text=True
    )

    # Should fail gracefully
    assert result.returncode != 0
    assert "not found" in result.stderr.lower() or "no such" in result.stderr.lower()


def test_detects_multiple_secret_patterns(bundle_script, tmp_path):
    """Test detection of various secret patterns."""
    # Create JSONL with different secret types
    content = f'''{{"operation": "read", "tool_input": "sk-proj-abc123def456"}}
{{"operation": "write", "content": "Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9"}}
{{"operation": "read", "file": "config.py", "tool_input": "-----BEGIN RSA PRIVATE KEY-----"}}
'''
    jsonl_file = create_test_jsonl(tmp_path, content)

    # Run script
    result = subprocess.run(
        ["python3", str(bundle_script), str(jsonl_file)],
        capture_output=True,
        text=True
    )

    # Should detect at least one secret
    output = result.stdout + result.stderr
    assert any(pattern in output for pattern in ["secret", "AKIA", "sk-proj", "Bearer"])
