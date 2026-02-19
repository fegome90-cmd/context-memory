"""Exhaustive tests for cm_multi_review.py - Production readiness suite.

Covers all gaps identified in coverage analysis:
- _validate_agent_name() error paths
- detect_context() happy path with mocked git output
- format_agent_list() 
- main() all CLI branches
- _validate_agent_data_consistency() failure case
- code-simplifier in thorough preset (regression)
- Edge cases in shortstat parsing
"""

import json
import subprocess
from pathlib import Path
from unittest.mock import patch, MagicMock
import pytest

from scripts.cm_multi_review import (
    AGENT_MAP,
    AGENT_PRESETS,
    ALL_AGENTS,
    FRAMEWORK_AGENTS,
    PRIMARY_AGENTS,
    SPECIALIZED_AGENTS,
    Agent,
    _find_agent,
    _validate_agent_data_consistency,
    _validate_agent_name,
    detect_context,
    format_agent_list,
    format_output,
    suggest_agents,
    main,
)


# ============================================================================
# Regression: code-simplifier must be in thorough preset
# ============================================================================


class TestCodeSimplifierRegression:
    """Regression tests for code-simplifier inclusion in thorough preset."""

    def test_thorough_includes_code_simplifier(self):
        """code-simplifier MUST be in thorough preset."""
        assert "pr-review-toolkit:code-simplifier" in AGENT_PRESETS["thorough"]

    def test_thorough_preset_agent_count(self):
        """thorough preset should have exactly 4 agents after adding code-simplifier."""
        assert len(AGENT_PRESETS["thorough"]) == 4

    def test_thorough_preset_composition(self):
        """thorough preset should contain the expected 4 agents."""
        expected = {
            "feature-dev:code-reviewer",
            "pr-review-toolkit:pr-test-analyzer",
            "pr-review-toolkit:silent-failure-hunter",
            "pr-review-toolkit:code-simplifier",
        }
        assert set(AGENT_PRESETS["thorough"]) == expected

    def test_comprehensive_is_superset_of_thorough(self):
        """comprehensive preset must contain all agents from thorough."""
        thorough_set = set(AGENT_PRESETS["thorough"])
        comprehensive_set = set(AGENT_PRESETS["comprehensive"])
        assert thorough_set.issubset(comprehensive_set), (
            f"Agents in thorough but not in comprehensive: "
            f"{thorough_set - comprehensive_set}"
        )


# ============================================================================
# _validate_agent_name() - all error branches
# ============================================================================


class TestValidateAgentName:
    """Tests for _validate_agent_name covering all error branches."""

    def test_valid_agent_name(self):
        """Should not raise for valid namespace:name format."""
        _validate_agent_name("feature-dev:code-reviewer")
        _validate_agent_name("pr-review-toolkit:pr-test-analyzer")

    def test_empty_string_raises(self):
        """Should raise ValueError for empty string."""
        with pytest.raises(ValueError, match="Agent name cannot be empty"):
            _validate_agent_name("")

    def test_no_colon_raises(self):
        """Should raise ValueError for name without colon separator."""
        with pytest.raises(ValueError, match="Expected 'namespace:agent-name' format"):
            _validate_agent_name("no-colon-here")

    def test_multiple_colons_raises(self):
        """Should raise ValueError for name with multiple colons."""
        with pytest.raises(ValueError, match="Expected 'namespace:agent-name' format"):
            _validate_agent_name("a:b:c")

    def test_empty_namespace_raises(self):
        """Should raise ValueError when namespace is empty."""
        with pytest.raises(ValueError, match="Both namespace and agent name must be non-empty"):
            _validate_agent_name(":agent-name")

    def test_empty_name_raises(self):
        """Should raise ValueError when agent name part is empty."""
        with pytest.raises(ValueError, match="Both namespace and agent name must be non-empty"):
            _validate_agent_name("namespace:")

    def test_only_colon_raises(self):
        """Should raise ValueError for just a colon."""
        with pytest.raises(ValueError, match="Both namespace and agent name must be non-empty"):
            _validate_agent_name(":")


# ============================================================================
# _validate_agent_data_consistency()
# ============================================================================


class TestValidateAgentDataConsistency:
    """Tests for module-level data consistency validation."""

    def test_current_data_is_consistent(self):
        """Current AGENT_PRESETS and AGENT_MAP should be consistent."""
        # Should not raise - validates current state is valid
        _validate_agent_data_consistency()

    def test_detects_missing_agent_in_preset(self):
        """Should raise ValueError when preset references non-existent agent."""
        with patch.dict(AGENT_PRESETS, {"broken": ["nonexistent:agent"]}):
            with pytest.raises(ValueError, match="Data consistency error"):
                _validate_agent_data_consistency()

    def test_all_preset_agents_exist_in_agent_map(self):
        """Every agent referenced in every preset must exist in AGENT_MAP."""
        for preset_name, agents in AGENT_PRESETS.items():
            for agent_name in agents:
                assert agent_name in AGENT_MAP, (
                    f"Agent '{agent_name}' in preset '{preset_name}' "
                    f"not found in AGENT_MAP"
                )


# ============================================================================
# AGENT_MAP / ALL_AGENTS structural integrity
# ============================================================================


class TestAgentRegistryIntegrity:
    """Structural integrity tests for agent registry."""

    def test_agent_map_matches_all_agents(self):
        """AGENT_MAP should contain exactly the agents in ALL_AGENTS."""
        assert set(AGENT_MAP.keys()) == {a.name for a in ALL_AGENTS}

    def test_all_agents_is_union_of_groups(self):
        """ALL_AGENTS should be PRIMARY + SPECIALIZED + FRAMEWORK."""
        expected = PRIMARY_AGENTS + SPECIALIZED_AGENTS + FRAMEWORK_AGENTS
        assert ALL_AGENTS == expected

    def test_no_duplicate_agent_names(self):
        """No two agents should share the same name."""
        names = [a.name for a in ALL_AGENTS]
        assert len(names) == len(set(names)), f"Duplicates: {[n for n in names if names.count(n) > 1]}"

    def test_all_agents_have_valid_name_format(self):
        """Every registered agent must pass name validation."""
        for agent in ALL_AGENTS:
            _validate_agent_name(agent.name)  # Should not raise

    def test_all_agents_have_description(self):
        """Every agent must have a non-empty description."""
        for agent in ALL_AGENTS:
            assert agent.description, f"Agent '{agent.name}' has empty description"

    def test_all_agents_have_source(self):
        """Every agent must have a non-empty source."""
        for agent in ALL_AGENTS:
            assert agent.source, f"Agent '{agent.name}' has empty source"


# ============================================================================
# detect_context() - happy path with mocked git
# ============================================================================


class TestDetectContextHappyPath:
    """Tests for detect_context() with mocked subprocess calls."""

    def _mock_subprocess(self, side_effects):
        """Helper to create mock subprocess with ordered side effects."""
        mock = MagicMock()
        mock.side_effect = side_effects
        return mock

    def test_detects_pr_exists(self):
        """Should set has_pr=True when gh pr view succeeds."""
        gh_result = MagicMock(returncode=0)
        staged_result = MagicMock(returncode=0, stdout="")
        working_result = MagicMock(returncode=0, stdout="")
        shortstat_result = MagicMock(returncode=0, stdout="")

        with patch('subprocess.run', side_effect=[
            gh_result, staged_result, working_result, shortstat_result
        ]):
            context = detect_context()
            assert context["has_pr"] is True

    def test_detects_staged_files(self):
        """Should parse staged file names from git diff --cached."""
        gh_result = MagicMock(returncode=1)
        staged_result = MagicMock(returncode=0, stdout="src/auth.ts\nsrc/api.py\n")
        working_result = MagicMock(returncode=0, stdout="")
        shortstat_result = MagicMock(returncode=0, stdout="")

        with patch('subprocess.run', side_effect=[
            gh_result, staged_result, working_result, shortstat_result
        ]):
            context = detect_context()
            assert context["staged_files"] == ["src/auth.ts", "src/api.py"]

    def test_detects_working_files(self):
        """Should parse working directory file names."""
        gh_result = MagicMock(returncode=1)
        staged_result = MagicMock(returncode=0, stdout="")
        working_result = MagicMock(returncode=0, stdout="README.md\nsrc/utils.ts\n")
        shortstat_result = MagicMock(returncode=0, stdout="")

        with patch('subprocess.run', side_effect=[
            gh_result, staged_result, working_result, shortstat_result
        ]):
            context = detect_context()
            assert context["working_files"] == ["README.md", "src/utils.ts"]

    def test_detects_test_files_in_staged(self):
        """Should set has_tests=True when staged files include test patterns."""
        gh_result = MagicMock(returncode=1)
        staged_result = MagicMock(returncode=0, stdout="src/auth_test.py\n")
        working_result = MagicMock(returncode=0, stdout="")
        shortstat_result = MagicMock(returncode=0, stdout="")

        with patch('subprocess.run', side_effect=[
            gh_result, staged_result, working_result, shortstat_result
        ]):
            context = detect_context()
            assert context["has_tests"] is True

    @pytest.mark.parametrize("filename,expected", [
        ("tests/test_auth.py", True),
        ("src/auth_test.py", True),
        ("src/auth_test.ts", True),
        ("src/auth.test.ts", True),
        ("src/auth.spec.ts", True),
        ("src/auth.py", False),
        ("src/main.ts", False),
    ])
    def test_test_file_pattern_detection(self, filename, expected):
        """Should correctly identify test file patterns."""
        gh_result = MagicMock(returncode=1)
        staged_result = MagicMock(returncode=0, stdout=f"{filename}\n")
        working_result = MagicMock(returncode=0, stdout="")
        shortstat_result = MagicMock(returncode=0, stdout="")

        with patch('subprocess.run', side_effect=[
            gh_result, staged_result, working_result, shortstat_result
        ]):
            context = detect_context()
            assert context["has_tests"] is expected, f"Expected has_tests={expected} for {filename}"

    @pytest.mark.parametrize("filename,expected", [
        ("src/types.ts", True),
        ("src/types.py", True),
        ("src/user_types.ts", True),
        ("src/index.d.ts", True),
        ("src/main.py", False),
        ("src/typing_utils.py", False),
    ])
    def test_type_file_pattern_detection(self, filename, expected):
        """Should correctly identify type definition file patterns."""
        gh_result = MagicMock(returncode=1)
        staged_result = MagicMock(returncode=0, stdout=f"{filename}\n")
        working_result = MagicMock(returncode=0, stdout="")
        shortstat_result = MagicMock(returncode=0, stdout="")

        with patch('subprocess.run', side_effect=[
            gh_result, staged_result, working_result, shortstat_result
        ]):
            context = detect_context()
            assert context["has_types"] is expected, f"Expected has_types={expected} for {filename}"

    @pytest.mark.parametrize("filename,expected", [
        ("src/error_handler.py", True),
        ("src/exception.ts", True),
        ("src/handler.py", True),
        ("src/main.py", False),
    ])
    def test_error_handling_pattern_detection(self, filename, expected):
        """Should correctly identify error handling file patterns."""
        gh_result = MagicMock(returncode=1)
        staged_result = MagicMock(returncode=0, stdout=f"{filename}\n")
        working_result = MagicMock(returncode=0, stdout="")
        shortstat_result = MagicMock(returncode=0, stdout="")

        with patch('subprocess.run', side_effect=[
            gh_result, staged_result, working_result, shortstat_result
        ]):
            context = detect_context()
            assert context["has_error_handling"] is expected, f"Expected has_error_handling={expected} for {filename}"

    def test_parses_change_size_from_shortstat(self):
        """Should parse insertion count from git diff --shortstat."""
        gh_result = MagicMock(returncode=1)
        staged_result = MagicMock(returncode=0, stdout="src/main.py\n")
        working_result = MagicMock(returncode=0, stdout="")
        shortstat_result = MagicMock(
            returncode=0,
            stdout=" 3 files changed, 150 insertions(+), 20 deletions(-)"
        )

        with patch('subprocess.run', side_effect=[
            gh_result, staged_result, working_result, shortstat_result
        ]):
            context = detect_context()
            assert context["change_size"] == 150

    def test_change_size_zero_when_no_insertions(self):
        """Should keep change_size=0 when shortstat has no insertions."""
        gh_result = MagicMock(returncode=1)
        staged_result = MagicMock(returncode=0, stdout="")
        working_result = MagicMock(returncode=0, stdout="")
        shortstat_result = MagicMock(
            returncode=0,
            stdout=" 1 file changed, 5 deletions(-)"
        )

        with patch('subprocess.run', side_effect=[
            gh_result, staged_result, working_result, shortstat_result
        ]):
            context = detect_context()
            assert context["change_size"] == 0

    def test_change_size_handles_malformed_shortstat(self):
        """Should handle malformed shortstat output without crashing."""
        gh_result = MagicMock(returncode=1)
        staged_result = MagicMock(returncode=0, stdout="")
        working_result = MagicMock(returncode=0, stdout="")
        shortstat_result = MagicMock(
            returncode=0,
            stdout=" file changed, xyz insertions(+)"
        )

        with patch('subprocess.run', side_effect=[
            gh_result, staged_result, working_result, shortstat_result
        ]):
            context = detect_context()
            assert context["change_size"] == 0

    def test_gh_timeout_still_detects_git(self):
        """Should continue detecting git context even if gh times out."""
        staged_result = MagicMock(returncode=0, stdout="src/main.py\n")
        working_result = MagicMock(returncode=0, stdout="")
        shortstat_result = MagicMock(returncode=0, stdout="")

        with patch('subprocess.run', side_effect=[
            subprocess.TimeoutExpired("gh", 5),
            staged_result, working_result, shortstat_result
        ]):
            context = detect_context()
            assert context["has_pr"] is False
            assert context["staged_files"] == ["src/main.py"]

    def test_git_not_found_after_gh_success(self):
        """Should handle git not found after successful gh check."""
        gh_result = MagicMock(returncode=0)

        with patch('subprocess.run', side_effect=[
            gh_result,
            FileNotFoundError("git not found"),
        ]):
            context = detect_context()
            assert context["has_pr"] is True
            assert context["staged_files"] == []

    def test_combines_staged_and_working_for_detection(self):
        """File type detection should check both staged and working files."""
        gh_result = MagicMock(returncode=1)
        staged_result = MagicMock(returncode=0, stdout="src/main.py\n")
        working_result = MagicMock(returncode=0, stdout="tests/test_main.py\n")
        shortstat_result = MagicMock(returncode=0, stdout="")

        with patch('subprocess.run', side_effect=[
            gh_result, staged_result, working_result, shortstat_result
        ]):
            context = detect_context()
            # test file is in working, not staged
            assert context["has_tests"] is True


# ============================================================================
# format_agent_list()
# ============================================================================


class TestFormatAgentList:
    """Tests for format_agent_list display formatting."""

    def test_formats_single_agent(self):
        """Should format one agent correctly."""
        agents = [Agent("ns:agent", "A description", "ns")]
        result = format_agent_list(agents, "Test Group")
        assert "Test Group:" in result
        assert "ns:agent: A description" in result

    def test_formats_multiple_agents(self):
        """Should format multiple agents with proper indentation."""
        agents = [
            Agent("a:one", "First", "a"),
            Agent("b:two", "Second", "b"),
        ]
        result = format_agent_list(agents, "My Agents")
        assert "a:one: First" in result
        assert "b:two: Second" in result

    def test_formats_empty_list(self):
        """Should only show group name for empty agent list."""
        result = format_agent_list([], "Empty Group")
        assert "Empty Group:" in result
        lines = result.strip().split("\n")
        assert len(lines) == 1

    def test_formats_primary_agents(self):
        """Should format PRIMARY_AGENTS correctly."""
        result = format_agent_list(PRIMARY_AGENTS, "Primary")
        assert "Primary:" in result
        assert "feature-dev:code-reviewer" in result

    def test_formats_specialized_agents(self):
        """Should format all SPECIALIZED_AGENTS."""
        result = format_agent_list(SPECIALIZED_AGENTS, "Specialized")
        for agent in SPECIALIZED_AGENTS:
            assert agent.name in result


# ============================================================================
# suggest_agents() - code-simplifier in medium changes
# ============================================================================


class TestSuggestAgentsCodeSimplifier:
    """Tests that code-simplifier appears in suggest_agents for thorough-level changes."""

    def test_large_change_includes_code_simplifier(self):
        """Large changes (comprehensive) must include code-simplifier."""
        context = {"change_size": 600}
        agents = suggest_agents(context)
        assert "pr-review-toolkit:code-simplifier" in agents

    def test_medium_change_with_all_flags_no_simplifier(self):
        """Medium changes with flags use individual selection, not thorough preset directly."""
        context = {
            "change_size": 200,
            "has_tests": True,
            "has_types": True,
            "has_error_handling": True,
        }
        agents = suggest_agents(context)
        # Medium changes build custom list - code-simplifier is NOT auto-added
        # unless the suggest_agents logic is changed to include it
        # This test documents current behavior
        assert "feature-dev:code-reviewer" in agents

    def test_find_agent_code_simplifier_in_thorough(self):
        """_find_agent should find code-simplifier in thorough preset."""
        result = _find_agent("thorough", "code-simplifier")
        assert result == "pr-review-toolkit:code-simplifier"


# ============================================================================
# main() CLI - all branches
# ============================================================================


class TestMainCLI:
    """Tests for main() function covering all CLI branches."""

    def test_list_flag(self, capsys):
        """--list should print all agent groups."""
        with patch('sys.argv', ['cm_multi_review.py', '--list']):
            main()
        captured = capsys.readouterr()
        assert "Available Agents:" in captured.out
        assert "Primary (Recommended):" in captured.out
        assert "Specialized (pr-review-toolkit):" in captured.out
        assert "Framework-Specific:" in captured.out
        assert "feature-dev:code-reviewer" in captured.out

    def test_presets_flag(self, capsys):
        """--presets should print all preset compositions."""
        with patch('sys.argv', ['cm_multi_review.py', '--presets']):
            main()
        captured = capsys.readouterr()
        assert "Available Presets:" in captured.out
        assert "quick:" in captured.out
        assert "thorough:" in captured.out
        assert "comprehensive:" in captured.out
        assert "framework:" in captured.out

    def test_context_flag_standalone(self, capsys):
        """--context alone should print repository context."""
        mock_context = {
            "has_pr": True,
            "has_tests": True,
            "has_types": False,
            "has_error_handling": False,
            "change_size": 42,
            "staged_files": ["src/main.py", "src/utils.py"],
            "working_files": ["README.md"],
        }
        with patch('sys.argv', ['cm_multi_review.py', '--context']):
            with patch('scripts.cm_multi_review.detect_context', return_value=mock_context):
                main()
        captured = capsys.readouterr()
        assert "Repository Context:" in captured.out
        assert "Has PR: True" in captured.out
        assert "Has tests: True" in captured.out
        assert "Change size: 42 lines" in captured.out
        assert "Staged files:" in captured.out
        assert "src/main.py" in captured.out

    def test_context_flag_with_many_staged_files(self, capsys):
        """--context should truncate staged files at 10 and show count."""
        files = [f"src/file_{i}.py" for i in range(15)]
        mock_context = {
            "has_pr": False,
            "has_tests": False,
            "has_types": False,
            "has_error_handling": False,
            "change_size": 0,
            "staged_files": files,
            "working_files": [],
        }
        with patch('sys.argv', ['cm_multi_review.py', '--context']):
            with patch('scripts.cm_multi_review.detect_context', return_value=mock_context):
                main()
        captured = capsys.readouterr()
        assert "... and 5 more" in captured.out

    def test_context_flag_with_many_working_files(self, capsys):
        """--context should truncate working files at 10 and show count."""
        files = [f"src/wip_{i}.ts" for i in range(12)]
        mock_context = {
            "has_pr": False,
            "has_tests": False,
            "has_types": False,
            "has_error_handling": False,
            "change_size": 0,
            "staged_files": [],
            "working_files": files,
        }
        with patch('sys.argv', ['cm_multi_review.py', '--context']):
            with patch('scripts.cm_multi_review.detect_context', return_value=mock_context):
                main()
        captured = capsys.readouterr()
        assert "Working files:" in captured.out
        assert "... and 2 more" in captured.out

    def test_no_flags_prints_help(self, capsys):
        """No flags should print help text."""
        with patch('sys.argv', ['cm_multi_review.py']):
            main()
        captured = capsys.readouterr()
        assert "Multi-agent code review" in captured.out or "usage:" in captured.out

    def test_suggest_flag(self, capsys):
        """--suggest should detect context and print suggested agents."""
        mock_context = {
            "has_pr": False,
            "has_tests": False,
            "has_types": False,
            "has_error_handling": False,
            "change_size": 30,
            "staged_files": [],
            "working_files": [],
        }
        with patch('sys.argv', ['cm_multi_review.py', '--suggest']):
            with patch('scripts.cm_multi_review.detect_context', return_value=mock_context):
                main()
        captured = capsys.readouterr()
        assert "Detecting repository context" in captured.out
        assert "Suggested agents" in captured.out
        assert "feature-dev:code-reviewer" in captured.out

    def test_suggest_with_context_flag(self, capsys):
        """--suggest --context should show both context details and suggestions."""
        mock_context = {
            "has_pr": True,
            "has_tests": True,
            "has_types": False,
            "has_error_handling": False,
            "change_size": 100,
            "staged_files": ["a.py"],
            "working_files": [],
        }
        with patch('sys.argv', ['cm_multi_review.py', '--suggest', '--context']):
            with patch('scripts.cm_multi_review.detect_context', return_value=mock_context):
                main()
        captured = capsys.readouterr()
        assert "Detected Context:" in captured.out
        assert "Has PR: True" in captured.out
        assert "Suggested agents" in captured.out

    def test_suggest_with_missing_agent_in_map(self, capsys):
        """--suggest should fail fast when agents not found in AGENT_MAP.

        Missing agents indicate a configuration bug, so we exit with code 2
        rather than silently continuing.
        """
        mock_context = {
            "has_pr": False,
            "has_tests": False,
            "has_types": False,
            "has_error_handling": False,
            "change_size": 30,
            "staged_files": [],
            "working_files": [],
        }
        with patch('sys.argv', ['cm_multi_review.py', '--suggest']):
            with patch('scripts.cm_multi_review.detect_context', return_value=mock_context):
                with patch('scripts.cm_multi_review.suggest_agents', return_value=["ghost:nonexistent"]):
                    with pytest.raises(SystemExit) as exc_info:
                        main()
        captured = capsys.readouterr()
        # Should exit with code 2 for configuration error
        assert exc_info.value.code == 2
        # Should show the error message
        assert "ERROR" in captured.out or "FATAL" in captured.err
        assert "ghost:nonexistent" in captured.out or "ghost:nonexistent" in captured.err


# ============================================================================
# CLI Integration tests (subprocess-based)
# ============================================================================


class TestCLIIntegration:
    """Integration tests running the script as a subprocess."""

    @pytest.fixture
    def plugin_root(self):
        return Path(__file__).parent.parent

    def test_list_command(self, plugin_root):
        """--list should succeed and show agents."""
        result = subprocess.run(
            [".venv/bin/python3", "scripts/cm_multi_review.py", "--list"],
            capture_output=True, text=True, timeout=10, cwd=str(plugin_root),
        )
        assert result.returncode == 0, f"stderr: {result.stderr}"
        assert "Available Agents" in result.stdout
        assert "feature-dev:code-reviewer" in result.stdout

    def test_presets_command(self, plugin_root):
        """--presets should succeed and show presets."""
        result = subprocess.run(
            [".venv/bin/python3", "scripts/cm_multi_review.py", "--presets"],
            capture_output=True, text=True, timeout=10, cwd=str(plugin_root),
        )
        assert result.returncode == 0, f"stderr: {result.stderr}"
        assert "quick:" in result.stdout
        assert "thorough:" in result.stdout
        # Verify our change: code-simplifier in thorough
        assert "code-simplifier" in result.stdout

    def test_context_command(self, plugin_root):
        """--context should succeed and show repo context."""
        result = subprocess.run(
            [".venv/bin/python3", "scripts/cm_multi_review.py", "--context"],
            capture_output=True, text=True, timeout=10, cwd=str(plugin_root),
        )
        assert result.returncode == 0, f"stderr: {result.stderr}"
        assert "Repository Context" in result.stdout

    def test_no_args_shows_help(self, plugin_root):
        """No args should show help and exit 0."""
        result = subprocess.run(
            [".venv/bin/python3", "scripts/cm_multi_review.py"],
            capture_output=True, text=True, timeout=10, cwd=str(plugin_root),
        )
        assert result.returncode == 0, f"stderr: {result.stderr}"
        assert "usage:" in result.stdout or "--suggest" in result.stdout

    def test_presets_output_includes_code_simplifier_in_thorough(self, plugin_root):
        """Regression: --presets output should show code-simplifier in thorough."""
        result = subprocess.run(
            [".venv/bin/python3", "scripts/cm_multi_review.py", "--presets"],
            capture_output=True, text=True, timeout=10, cwd=str(plugin_root),
        )
        lines = result.stdout.split("\n")
        thorough_line = [l for l in lines if l.strip().startswith("thorough:")]
        assert len(thorough_line) == 1
        assert "code-simplifier" in thorough_line[0]


# ============================================================================
# _find_agent() - additional edge cases
# ============================================================================


class TestFindAgentEdgeCases:
    """Additional edge cases for _find_agent."""

    def test_find_code_reviewer_ambiguous_in_comprehensive(self):
        """code-reviewer suffix matches both feature-dev and pr-review-toolkit in comprehensive."""
        with pytest.raises(ValueError, match="Ambiguous suffix"):
            _find_agent("comprehensive", "code-reviewer")

    def test_find_code_reviewer_unambiguous_in_quick(self):
        """code-reviewer suffix is unambiguous in quick (only feature-dev)."""
        result = _find_agent("quick", "code-reviewer")
        assert result == "feature-dev:code-reviewer"

    def test_find_agent_in_framework_preset(self):
        """Should find agent in framework preset."""
        result = _find_agent("framework", "code-review-checklist")
        assert result == "superpowers:code-review-checklist"

    def test_find_code_simplifier_in_thorough(self):
        """Regression: code-simplifier must be findable in thorough."""
        result = _find_agent("thorough", "code-simplifier")
        assert result == "pr-review-toolkit:code-simplifier"


# ============================================================================
# format_output() - edge cases
# ============================================================================


class TestFormatOutputEdgeCases:
    """Additional tests for format_output edge cases."""

    def test_unknown_preset_returns_empty_agents(self):
        """Unknown preset should return empty available_agents list."""
        output = format_output({}, "nonexistent_preset", [])
        parsed = json.loads(output)
        assert parsed["available_agents"] == []

    def test_success_always_true(self):
        """success field should always be True (current design)."""
        output = format_output({}, "quick", ["some warning"])
        parsed = json.loads(output)
        assert parsed["success"] is True

    def test_errors_always_empty(self):
        """errors field should always be empty list (current design)."""
        output = format_output({}, "quick", [])
        parsed = json.loads(output)
        assert parsed["errors"] == []

    def test_thorough_preset_maps_to_4_agents(self):
        """Regression: thorough preset should map to 4 agents."""
        output = format_output({}, "thorough", [])
        parsed = json.loads(output)
        assert len(parsed["available_agents"]) == 4
        assert "pr-review-toolkit:code-simplifier" in parsed["available_agents"]


# ============================================================================
# Markdown/command file consistency
# ============================================================================


class TestMarkdownConsistency:
    """Tests that the command markdown is consistent with the Python source."""

    @pytest.fixture
    def markdown_content(self):
        md_path = Path(__file__).parent.parent.parent.parent.parent.parent / "commands" / "cm-multi-review.md"
        if not md_path.exists():
            # Try alternate path
            md_path = Path("/Users/felipe_gonzalez/.claude/commands/cm-multi-review.md")
        if md_path.exists():
            return md_path.read_text()
        pytest.skip("cm-multi-review.md not found")

    def test_all_preset_names_in_markdown(self, markdown_content):
        """All preset names defined in Python should be documented in markdown."""
        for preset_name in AGENT_PRESETS:
            assert preset_name in markdown_content, f"Preset '{preset_name}' not documented in markdown"

    def test_all_agent_names_in_markdown(self, markdown_content):
        """All agent names should appear somewhere in the markdown."""
        for agent in ALL_AGENTS:
            assert agent.name in markdown_content, f"Agent '{agent.name}' not documented in markdown"

    def test_thorough_description_includes_code_simplifier(self, markdown_content):
        """Regression: thorough description in markdown should mention code-simplifier."""
        # Find the thorough preset line
        for line in markdown_content.split("\n"):
            if line.startswith("- `thorough`"):
                assert "code-simplifier" in line, (
                    "Markdown thorough preset description does not mention code-simplifier"
                )
                break
        else:
            pytest.fail("Could not find thorough preset line in markdown")
