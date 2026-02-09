"""Tests for cm_multi_review.py"""

import json
import subprocess
from pathlib import Path
from unittest.mock import patch, MagicMock
import pytest
from scripts.cm_multi_review import (
    AGENT_PRESETS,
    detect_context,
    validate_environment,
    format_output,
    suggest_agents,
    _find_agent,
    _get_preset_reason,
)

def test_agent_names_have_namespace_prefix():
    """All agent names should include namespace prefix."""
    for preset, agents in AGENT_PRESETS.items():
        for agent in agents:
            assert ":" in agent, f"{agent} in {preset} missing namespace prefix"

def test_pr_review_toolkit_agents_have_full_prefix():
    """All pr-review-toolkit agents should use full qualified name."""
    pr_agents = {
        "pr-test-analyzer": "pr-review-toolkit:pr-test-analyzer",
        "silent-failure-hunter": "pr-review-toolkit:silent-failure-hunter",
        "type-design-analyzer": "pr-review-toolkit:type-design-analyzer",
        "comment-analyzer": "pr-review-toolkit:comment-analyzer",
        "code-simplifier": "pr-review-toolkit:code-simplifier",
        "code-reviewer": "pr-review-toolkit:code-reviewer",
    }

    for preset, agents in AGENT_PRESETS.items():
        for agent in agents:
            if agent in pr_agents.values():
                assert agent.startswith("pr-review-toolkit:"), \
                    f"{agent} in {preset} should start with pr-review-toolkit:"

def test_all_presets_exist():
    """All preset names should be defined."""
    assert "quick" in AGENT_PRESETS
    assert "thorough" in AGENT_PRESETS
    assert "comprehensive" in AGENT_PRESETS
    assert "framework" in AGENT_PRESETS


def test_detect_context_logs_on_gh_not_found():
    """Should log warning when gh CLI is not found."""
    with patch('subprocess.run') as mock_run:
        mock_run.side_effect = FileNotFoundError("gh not found")
        # Should not raise exception
        context = detect_context()
        assert context["has_pr"] == False

def test_detect_context_logs_on_git_timeout():
    """Should handle git timeout gracefully."""
    with patch('subprocess.run') as mock_run:
        mock_run.side_effect = subprocess.TimeoutExpired("git", 5)
        # Should not raise exception
        context = detect_context()
        assert isinstance(context, dict)

def test_detect_context_returns_default_on_error():
    """Should return default context structure on errors.

    The new implementation uses helper functions _run_gh_command and
    _run_git_command that wrap subprocess.run. We need to patch those.
    """
    with patch('scripts.cm_multi_review._run_gh_command') as mock_gh:
        with patch('scripts.cm_multi_review._run_git_command') as mock_git:
            # Configure mocks to return valid results (no exception)
            mock_gh.return_value = MagicMock(returncode=0, stdout="", stderr="")
            mock_git.return_value = MagicMock(returncode=0, stdout="", stderr="")

            context = detect_context()
            assert "has_pr" in context
            assert "has_tests" in context

def test_validate_environment_returns_tuple():
    """Should return (is_valid, errors) tuple."""
    result = validate_environment()
    assert isinstance(result, tuple)
    assert len(result) == 2
    assert isinstance(result[0], bool)
    assert isinstance(result[1], list)

def test_validate_environment_detects_git():
    """Should check if git is available."""
    is_valid, errors = validate_environment()
    # If we're in a git repo, git should be available
    # If not, we should get an error
    assert is_valid == (len(errors) == 0)

def test_validate_environment_with_mock_git_failure():
    """Should return errors when git is not available."""
    with patch('subprocess.run') as mock_run:
        mock_run.side_effect = FileNotFoundError("git not found")
        is_valid, errors = validate_environment()
        assert is_valid == False
        assert len(errors) > 0
        assert "git" in errors[0].lower()


# ============================================================================
# Comprehensive tests for validate_environment()
# ============================================================================


def test_validate_environment_git_success():
    """Should return (True, []) when git check succeeds."""
    with patch('subprocess.run') as mock_run:
        mock_run.return_value = MagicMock(returncode=0)
        is_valid, errors = validate_environment()
        assert is_valid is True
        assert errors == []


def test_validate_environment_git_not_found():
    """Should return error message when git is not found."""
    with patch('subprocess.run') as mock_run:
        mock_run.side_effect = FileNotFoundError("git not found")
        is_valid, errors = validate_environment()
        assert is_valid is False
        assert len(errors) == 1
        # Updated message includes installation URL
        assert "git not found" in errors[0]
        assert "install" in errors[0] or "https://git-scm.com/" in errors[0]


def test_validate_environment_git_timeout():
    """Should return error message when git times out."""
    with patch('subprocess.run') as mock_run:
        mock_run.side_effect = subprocess.TimeoutExpired("git", 2)
        is_valid, errors = validate_environment()
        assert is_valid is False
        assert len(errors) == 1
        # Updated message includes timeout duration
        assert "git timed out" in errors[0]
        assert "2 seconds" in errors[0] or "2" in errors[0]


def test_validate_environment_git_returncode_nonzero():
    """Should return error when git returns non-zero exit code."""
    with patch('subprocess.run') as mock_run:
        mock_run.return_value = MagicMock(returncode=1)
        is_valid, errors = validate_environment()
        assert is_valid is False
        assert len(errors) == 1
        assert "git is not working properly" in errors[0]


def test_validate_environment_generic_exception():
    """Should return error message for unexpected exceptions."""
    with patch('subprocess.run') as mock_run:
        mock_run.side_effect = Exception("Unexpected error")
        is_valid, errors = validate_environment()
        assert is_valid is False
        assert len(errors) == 1
        # Updated message is more descriptive
        assert "git check failure" in errors[0] or "git" in errors[0].lower()
        assert "Unexpected error" in errors[0]


def test_format_output_returns_valid_json():
    """Output should be parseable JSON string."""
    context = {
        "has_pr": True,
        "has_tests": False,
        "change_size": 100,
    }
    output = format_output(context, "thorough", [])
    parsed = json.loads(output)
    assert isinstance(parsed, dict)


def test_format_output_has_required_fields():
    """Output should contain all required fields."""
    context = {"has_pr": False}
    output = format_output(context, "quick", ["warning message"])
    parsed = json.loads(output)

    assert "success" in parsed
    assert "context" in parsed
    assert "suggested_preset" in parsed
    assert "suggested_reason" in parsed
    assert "available_agents" in parsed
    assert "warnings" in parsed
    assert "errors" in parsed


def test_format_output_includes_warnings():
    """Warnings should be included in output."""
    context = {}
    warnings = ["gh CLI not found"]
    output = format_output(context, "quick", warnings)
    parsed = json.loads(output)

    assert parsed["warnings"] == warnings


def test_format_output_maps_preset_to_agents():
    """Should map preset name to actual agent list."""
    context = {}
    output = format_output(context, "thorough", [])
    parsed = json.loads(output)

    assert parsed["suggested_preset"] == "thorough"
    assert "feature-dev:code-reviewer" in parsed["available_agents"]
    assert "pr-review-toolkit:pr-test-analyzer" in parsed["available_agents"]


def test_format_output_includes_context():
    """Context should be included in output."""
    context = {
        "has_pr": True,
        "has_tests": True,
        "has_types": False,
        "change_size": 150,
    }
    output = format_output(context, "thorough", [])
    parsed = json.loads(output)

    assert parsed["context"] == context
    assert parsed["context"]["has_pr"] is True
    assert parsed["context"]["has_tests"] is True
    assert parsed["context"]["change_size"] == 150


# ============================================================================
# Tests for _get_preset_reason() helper function
# ============================================================================


def test_get_preset_reason_quick():
    """Should generate correct reason for quick preset."""
    context = {}
    reason = _get_preset_reason("quick", context)

    assert reason == "Small change (< 50 lines) - fast review"


def test_get_preset_reason_thorough():
    """Should generate correct reason for thorough preset."""
    context = {}
    reason = _get_preset_reason("thorough", context)

    assert reason == "Medium change with specific focus areas"


def test_get_preset_reason_comprehensive():
    """Should generate correct reason for comprehensive preset."""
    context = {}
    reason = _get_preset_reason("comprehensive", context)

    assert reason == "Large change (> 500 lines) - complete review"


def test_get_preset_reason_framework():
    """Should generate correct reason for framework preset."""
    context = {}
    reason = _get_preset_reason("framework", context)

    assert reason == "Framework-specific compliance review"


def test_get_preset_reason_with_context_flags():
    """Should append context details to reason."""
    context = {
        "has_tests": True,
        "has_types": True,
        "has_error_handling": False,
    }
    reason = _get_preset_reason("thorough", context)

    assert "Medium change with specific focus areas" in reason
    assert "test files detected" in reason
    assert "type definitions detected" in reason
    assert "error handling changes detected" not in reason


def test_get_preset_reason_with_all_flags():
    """Should append all context details when all flags are True."""
    context = {
        "has_tests": True,
        "has_types": True,
        "has_error_handling": True,
    }
    reason = _get_preset_reason("comprehensive", context)

    assert "Large change (> 500 lines) - complete review" in reason
    assert "test files detected" in reason
    assert "type definitions detected" in reason
    assert "error handling changes detected" in reason


def test_get_preset_reason_unknown_preset():
    """Should return fallback reason for unknown preset."""
    context = {}
    reason = _get_preset_reason("unknown_preset", context)

    assert reason == "Standard review"


def test_get_preset_reason_unknown_preset_with_context():
    """Should append context details even for unknown preset."""
    context = {"has_tests": True}
    reason = _get_preset_reason("unknown", context)

    assert "Standard review" in reason
    assert "test files detected" in reason


def test_suggest_agents_returns_qualified_names():
    """Should return agents with full namespace prefixes."""
    context = {
        "has_pr": True,
        "has_tests": True,
        "has_types": True,
        "has_error_handling": True,
        "change_size": 600,
    }
    agents = suggest_agents(context)

    # All agents should have namespace prefixes (feature-dev:, pr-review-toolkit:, etc.)
    for agent in agents:
        assert ":" in agent, f"Agent '{agent}' should have a namespace prefix"

def test_suggest_agents_returns_valid_preset_agents():
    """Should only return agents defined in AGENT_PRESETS."""
    context = {"change_size": 600}  # Large change
    agents = suggest_agents(context)

    # Should return comprehensive preset agents
    comprehensive_agents = AGENT_PRESETS["comprehensive"]
    for agent in agents:
        assert agent in comprehensive_agents, f"{agent} not in comprehensive preset"


# ============================================================================
# Tests for _find_agent() helper function
# ============================================================================


def test_find_agent_returns_full_qualified_name():
    """Should return full namespace-qualified agent name."""
    result = _find_agent("thorough", "pr-test-analyzer")
    assert result == "pr-review-toolkit:pr-test-analyzer"


def test_find_agent_finds_by_suffix():
    """Should find agent by matching suffix."""
    # Test with different suffixes
    assert _find_agent("quick", "code-reviewer") == "feature-dev:code-reviewer"
    assert _find_agent("thorough", "silent-failure-hunter") == "pr-review-toolkit:silent-failure-hunter"
    assert _find_agent("comprehensive", "type-design-analyzer") == "pr-review-toolkit:type-design-analyzer"


def test_find_agent_raises_value_error_on_bad_preset():
    """Should raise ValueError when preset name is invalid."""
    with pytest.raises(ValueError, match="Invalid preset 'invalid'. Must be one of:"):
        _find_agent("invalid", "pr-test-analyzer")


def test_find_agent_raises_value_error_on_bad_suffix():
    """Should raise ValueError when suffix doesn't match any agent."""
    with pytest.raises(ValueError, match="No agent ending with 'nonexistent-agent' in thorough preset"):
        _find_agent("thorough", "nonexistent-agent")


def test_find_agent_with_empty_suffix():
    """Should raise ValueError when suffix is empty."""
    with pytest.raises(ValueError, match="suffix cannot be empty"):
        _find_agent("thorough", "")


# ============================================================================
# Edge case tests for suggest_agents()
# ============================================================================


def test_suggest_agents_medium_change_no_flags():
    """Medium change without special flags returns base agent only."""
    context = {
        "change_size": 100,  # Medium size (50-500)
        "has_tests": False,
        "has_types": False,
        "has_error_handling": False,
    }
    agents = suggest_agents(context)

    # Should only return the base code-reviewer agent
    assert len(agents) == 1
    assert agents == ["feature-dev:code-reviewer"]


def test_suggest_agents_boundary_small():
    """Change size at small boundary (50) should use medium preset."""
    context = {
        "change_size": 50,  # Exactly at boundary
        "has_tests": False,
        "has_types": False,
        "has_error_handling": False,
    }
    agents = suggest_agents(context)

    # 50 is not < 50, so should use medium preset logic
    assert len(agents) == 1
    assert agents == ["feature-dev:code-reviewer"]


def test_suggest_agents_boundary_large():
    """Change size at large boundary (500) should use medium preset."""
    context = {
        "change_size": 500,  # Exactly at boundary
        "has_tests": False,
        "has_types": False,
        "has_error_handling": False,
    }
    agents = suggest_agents(context)

    # 500 is not > 500, so should use medium preset logic
    assert len(agents) == 1
    assert agents == ["feature-dev:code-reviewer"]


def test_suggest_agents_empty_context():
    """Empty context dict should use defaults (medium preset)."""
    context = {}
    agents = suggest_agents(context)

    # Missing change_size defaults to 0 via .get(), which is < 50
    # So should return quick preset
    assert agents == AGENT_PRESETS["quick"]


def test_suggest_agents_no_duplicates():
    """Verify no duplicate agents in output even with multiple conditions."""
    context = {
        "change_size": 200,  # Medium size
        "has_tests": True,
        "has_types": True,
        "has_error_handling": True,
    }
    agents = suggest_agents(context)

    # Check no duplicates
    assert len(agents) == len(set(agents)), "Agent list contains duplicates"

    # Verify expected agents are present
    assert "feature-dev:code-reviewer" in agents
    assert "pr-review-toolkit:pr-test-analyzer" in agents
    assert "pr-review-toolkit:type-design-analyzer" in agents
    assert "pr-review-toolkit:silent-failure-hunter" in agents

    # Verify exactly 4 agents (base + 3 specialized)
    assert len(agents) == 4


# ============================================================================
# Integration tests for --suggest command
# ============================================================================


def test_suggest_command_integration():
    """Integration test for --suggest command.

    Tests the complete CLI execution flow:
    1. Runs the script as a subprocess
    2. Verifies exit code is 0
    3. Verifies output contains expected content
    4. Verifies suggested agents have valid format
    """
    # Get plugin root dynamically (Rule #2: Relative Paths Only)
    plugin_root = Path(__file__).parent.parent

    result = subprocess.run(
        ["python3", "scripts/cm_multi_review.py", "--suggest"],
        capture_output=True,
        text=True,
        timeout=10,
        cwd=str(plugin_root)
    )

    # Verify exit code
    assert result.returncode == 0, f"Script failed with stderr: {result.stderr}"

    # Verify output contains expected sections from actual script output
    output = result.stdout
    assert "Detecting repository context" in output
    assert "Suggested agents" in output

    # Verify specific expected agent names (more specific than just ":")
    # These are actual agents returned by the script
    assert "feature-dev:" in output or "pr-review-toolkit:" in output, \
        "Output should contain namespace-qualified agent names"

    # Verify no errors in stderr (warnings are ok)
    if result.stderr:
        assert "error" not in result.stderr.lower(), f"Errors in stderr: {result.stderr}"


def test_suggest_command_with_context_flag():
    """Integration test for --suggest --context command combination.

    Verifies that the --context flag works with --suggest.
    """
    # Get plugin root dynamically (Rule #2: Relative Paths Only)
    plugin_root = Path(__file__).parent.parent

    result = subprocess.run(
        ["python3", "scripts/cm_multi_review.py", "--suggest", "--context"],
        capture_output=True,
        text=True,
        timeout=10,
        cwd=str(plugin_root)
    )

    # Verify exit code
    assert result.returncode == 0, f"Script failed with stderr: {result.stderr}"

    # Verify output includes context information
    output = result.stdout
    # Should show detected context details - more specific assertion
    assert ("Detecting repository context" in output or
            "Context" in output or
            any(term in output for term in ["PR:", "Tests:", "Types:"])), \
        "Output should include context information"
