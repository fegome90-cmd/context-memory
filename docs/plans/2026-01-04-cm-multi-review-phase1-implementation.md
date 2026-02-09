# cm-multi-review Phase 1 Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Fix critical issues in cm_multi_review.py - add logging, exception handling, consistent agent names, and structured JSON output.

**Architecture:** Refactor existing Python script with proper error handling, logging, and consistent agent namespace prefixes. No external dependencies - use Python stdlib only.

**Tech Stack:** Python 3.12+, logging (stdlib), subprocess (stdlib), typing (stdlib)

---

## Task 1: Add Logging Module

**Files:**
- Modify: `scripts/cm_multi_review.py:9-17` (add after imports)

**Step 1: Add logging imports and setup**

After line 17 (after `from typing import Dict, List, Optional`), add:

```python
import logging

# Setup logging to stderr (doesn't interfere with JSON output)
logging.basicConfig(
    level=logging.INFO,
    format='%(levelname)s cm_multi_review: %(message)s',
    stream=sys.stderr
)
logger = logging.getLogger(__name__)
```

**Step 2: Verify no syntax errors**

Run: `python3 -m py_compile scripts/cm_multi_review.py`
Expected: No output (successful compilation)

**Step 3: Run the script to ensure it still works**

Run: `python3 scripts/cm_multi_review.py --list`
Expected: Lists all available agents without errors

**Step 4: Commit**

```bash
git add scripts/cm_multi_review.py
git commit -m "feat(cm-multi-review): add logging module

- Add logging configuration with stderr output
- INFO level by default, DEBUG for troubleshooting
- Format: '[LEVEL] cm_multi_review: message'

Part of Phase 1: Critical issues fixes"
```

---

## Task 2: Add AGENT_PRESETS Constant with Full Qualified Names

**Files:**
- Modify: `scripts/cm_multi_review.py:57-71` (replace PRESETS section)

**Step 1: Write failing test**

Create file: `tests/test_cm_multi_review.py`

```python
"""Tests for cm_multi_review.py"""

import pytest
from scripts.cm_multi_review import AGENT_PRESETS

def test_agent_names_have_namespace_prefix():
    """All agent names should include namespace prefix."""
    for preset, agents in AGENT_PRESETS.items():
        for agent in agents:
            assert ":" in agent, f"{agent} in {preset} missing namespace prefix"

def test_pr_review_toolkit_agents_have_full_prefix():
    """All pr-review-toolkit agents should use full qualified name."""
    pr_agents = [
        "pr-test-analyzer",
        "silent-failure-hunter",
        "type-design-analyzer",
        "comment-analyzer",
        "code-simplifier",
        "code-reviewer",
    ]

    for preset, agents in AGENT_PRESETS.items():
        for agent in agents:
            if any(short in agent for short in pr_agents):
                assert agent.startswith("pr-review-toolkit:"), \
                    f"{agent} in {preset} should start with pr-review-toolkit:"

def test_all_presets_exist():
    """All preset names should be defined."""
    assert "quick" in AGENT_PRESETS
    assert "thorough" in AGENT_PRESETS
    assert "comprehensive" in AGENT_PRESETS
    assert "framework" in AGENT_PRESETS
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_cm_multi_review.py -v`
Expected: FAIL - `AGENT_PRESETS` is not defined yet (or has wrong format)

**Step 3: Implement AGENT_PRESETS constant**

Replace lines 57-71 (the PRESETS section) with:

```python
# Agent presets with full qualified names
AGENT_PRESETS = {
    "quick": ["feature-dev:code-reviewer"],
    "thorough": [
        "feature-dev:code-reviewer",
        "pr-review-toolkit:pr-test-analyzer",
        "pr-review-toolkit:silent-failure-hunter",
    ],
    "comprehensive": [
        "feature-dev:code-reviewer",
        "pr-review-toolkit:pr-test-analyzer",
        "pr-review-toolkit:silent-failure-hunter",
        "pr-review-toolkit:type-design-analyzer",
        "pr-review-toolkit:comment-analyzer",
        "pr-review-toolkit:code-simplifier",
        "pr-review-toolkit:code-reviewer",
    ],
    "framework": ["superpowers:code-review-checklist"],
}

# Legacy PRESETS for backward compatibility (deprecated)
PRESETS = {
    "quick": ["/code-review"],
    "thorough": ["/code-review", "pr-test-analyzer", "silent-failure-hunter"],
    "comprehensive": [
        "/code-review",
        "pr-test-analyzer",
        "silent-failure-hunter",
        "type-design-analyzer",
        "comment-analyzer",
        "code-simplifier",
        "code-reviewer",
    ],
    "framework": ["superpowers:code-review-checklist"],
}
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_cm_multi_review.py -v`
Expected: PASS - All 3 tests pass

**Step 5: Run existing tests to ensure no breakage**

Run: `pytest tests/ -v --ignore=tests/roadmap`
Expected: All existing tests still pass

**Step 6: Commit**

```bash
git add scripts/cm_multi_review.py tests/test_cm_multi_review.py
git commit -m "feat(cm-multi-review): add AGENT_PRESETS with full qualified names

- Add AGENT_PRESETS constant with proper namespace prefixes
- All pr-review-toolkit agents use 'pr-review-toolkit:' prefix
- Keep PRESETS for backward compatibility (deprecated)
- Add tests to validate agent name format

Part of Phase 1: Critical issues fixes"
```

---

## Task 3: Rewrite detect_context() with Proper Exception Handling

**Files:**
- Modify: `scripts/cm_multi_review.py:74-160`

**Step 1: Write test for exception handling**

Add to `tests/test_cm_multi_review.py`:

```python
import subprocess
from unittest.mock import patch, MagicMock
from scripts.cm_multi_review import detect_context

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
    """Should return default context structure on errors."""
    with patch('subprocess.run') as mock_run:
        mock_run.side_effect = Exception("Unexpected error")
        context = detect_context()
        assert "has_pr" in context
        assert "has_tests" in context
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_cm_multi_review.py::test_detect_context_logs_on_gh_not_found -v`
Expected: FAIL - Current code doesn't handle exceptions properly (bare except)

**Step 3: Rewrite detect_context() with proper exception handling**

Replace the entire `detect_context()` function (lines 74-160) with:

```python
def detect_context() -> Dict:
    """Detect repository context and state.

    Returns a dictionary with detected context information.
    Logs warnings for non-fatal errors, returns partial context on failure.
    """
    context = {
        "has_pr": False,
        "has_tests": False,
        "has_types": False,
        "has_error_handling": False,
        "has_comments": False,
        "change_size": 0,
        "staged_files": [],
        "working_files": [],
    }

    # Detect PR
    try:
        result = subprocess.run(
            ["gh", "pr", "view", "--json", "state"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        context["has_pr"] = result.returncode == 0
    except FileNotFoundError:
        logger.warning("gh CLI not found - skipping PR detection")
    except subprocess.TimeoutExpired:
        logger.error("gh command timed out - PR detection failed")
    except Exception as e:
        logger.debug(f"Unexpected error in PR detection: {e}")

    # Detect git state
    try:
        # Detect staged files
        result = subprocess.run(
            ["git", "diff", "--cached", "--name-only"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.stdout.strip():
            context["staged_files"] = result.stdout.strip().split("\n")

        # Detect working directory files
        result = subprocess.run(
            ["git", "diff", "--name-only"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.stdout.strip():
            context["working_files"] = result.stdout.strip().split("\n")

        # Combine all changed files
        all_files = context["staged_files"] + context["working_files"]

        # Check for test files
        context["has_tests"] = any(
            any(pattern in f for pattern in ["_test.py", "_test.ts", ".test.ts", ".spec.ts", "__tests__.py", "tests/"])
            for f in all_files
        )

        # Check for type definitions
        context["has_types"] = any(
            any(pattern in f for pattern in ["_types.ts", ".d.ts", "types.py", "types.ts"])
            for f in all_files
        )

        # Check for error handling changes
        context["has_error_handling"] = any(
            any(pattern in f for pattern in ["error", "exception", "handler"])
            for f in all_files
        )

        # Estimate change size
        result = subprocess.run(
            ["git", "diff", "--cached", "--shortstat"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.stdout.strip() and "file" in result.stdout.lower():
            parts = result.stdout.split()
            for i, part in enumerate(parts):
                if "insertion" in part:
                    try:
                        context["change_size"] = int(parts[i - 1])
                    except (ValueError, IndexError):
                        logger.debug(f"Could not parse change size from: {result.stdout}")

    except FileNotFoundError:
        logger.error("git not found - not in a git repository")
    except subprocess.TimeoutExpired:
        logger.error("git command timed out - using partial context")
    except Exception as e:
        logger.debug(f"Unexpected error in git context detection: {e}")

    return context
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_cm_multi_review.py::test_detect_context_logs_on_gh_not_found -v`
Expected: PASS

Run: `pytest tests/test_cm_multi_review.py::test_detect_context_logs_on_git_timeout -v`
Expected: PASS

Run: `pytest tests/test_cm_multi_review.py::test_detect_context_returns_default_on_error -v`
Expected: PASS

**Step 5: Run all tests to ensure no breakage**

Run: `pytest tests/test_cm_multi_review.py -v`
Expected: All tests pass

**Step 6: Commit**

```bash
git add scripts/cm_multi_review.py tests/test_cm_multi_review.py
git commit -m "refactor(cm-multi-review): proper exception handling in detect_context

- Replace bare except with specific exception types
- Add logging for FileNotFoundError, TimeoutExpired
- Handle subprocess failures gracefully
- Return partial context on non-fatal errors
- Add tests for exception handling scenarios

Part of Phase 1: Critical issues fixes"
```

---

## Task 4: Add validate_environment() Function

**Files:**
- Modify: `scripts/cm_multi_review.py:162` (add after detect_context())

**Step 1: Write test for validate_environment**

Add to `tests/test_cm_multi_review.py`:

```python
from scripts.cm_multi_review import validate_environment

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
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_cm_multi_review.py::test_validate_environment_returns_tuple -v`
Expected: FAIL - `validate_environment` function doesn't exist yet

**Step 3: Implement validate_environment()**

After the `detect_context()` function (after line 261), add:

```python
def validate_environment() -> tuple:
    """Validate that required tools are available.

    Returns:
        tuple: (is_valid: bool, errors: list[str])
    """
    errors = []

    # Check git
    try:
        result = subprocess.run(
            ["git", "--version"],
            capture_output=True,
            timeout=2,
        )
        if result.returncode != 0:
            errors.append("git is not working properly")
    except FileNotFoundError:
        errors.append("git not found - please install git")
    except subprocess.TimeoutExpired:
        errors.append("git timed out - may not be responding")
    except Exception as e:
        errors.append(f"git check failed: {e}")

    return len(errors) == 0, errors
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_cm_multi_review.py -k validate_environment -v`
Expected: All validate_environment tests pass

**Step 5: Commit**

```bash
git add scripts/cm_multi_review.py tests/test_cm_multi_review.py
git commit -m "feat(cm-multi-review): add validate_environment function

- Check git availability with proper error handling
- Return (is_valid, errors) tuple
- Add tests for environment validation
- Timeout after 2 seconds for responsiveness

Part of Phase 1: Critical issues fixes"
```

---

## Task 5: Add format_output() for Structured JSON

**Files:**
- Modify: `scripts/cm_multi_review.py:162` (add after validate_environment())

**Step 1: Write test for format_output**

Add to `tests/test_cm_multi_review.py`:

```python
import json
from scripts.cm_multi_review import format_output

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
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_cm_multi_review.py::test_format_output_returns_valid_json -v`
Expected: FAIL - `format_output` function doesn't exist yet

**Step 3: Implement format_output() and helper**

After the `validate_environment()` function, add:

```python
def _get_preset_reason(preset: str, context: Dict) -> str:
    """Generate explanation for why a preset was suggested."""
    reasons = {
        "quick": "Small change (< 50 lines) - fast review",
        "thorough": "Medium change with specific focus areas",
        "comprehensive": "Large change (> 500 lines) - complete review",
        "framework": "Framework-specific compliance review",
    }

    base_reason = reasons.get(preset, "Standard review")

    # Add context-specific details
    details = []
    if context.get("has_tests"):
        details.append("test files detected")
    if context.get("has_types"):
        details.append("type definitions detected")
    if context.get("has_error_handling"):
        details.append("error handling changes detected")

    if details:
        return f"{base_reason} ({', '.join(details)})"
    return base_reason


def format_output(context: Dict, suggested_preset: str, warnings: List[str]) -> str:
    """Format detection results as structured JSON.

    Args:
        context: Detected repository context
        suggested_preset: Recommended preset name
        warnings: List of non-fatal warnings

    Returns:
        JSON string with structured output
    """
    output = {
        "success": True,
        "context": context,
        "suggested_preset": suggested_preset,
        "suggested_reason": _get_preset_reason(suggested_preset, context),
        "available_agents": AGENT_PRESETS.get(suggested_preset, []),
        "warnings": warnings,
        "errors": [],
    }
    return json.dumps(output, indent=2)
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_cm_multi_review.py -k format_output -v`
Expected: All format_output tests pass

**Step 5: Commit**

```bash
git add scripts/cm_multi_review.py tests/test_cm_multi_review.py
git commit -m "feat(cm-multi-review): add format_output for structured JSON

- Return JSON with success, context, suggested_preset, available_agents
- Include warnings and errors arrays
- Add _get_preset_reason helper for explanations
- Add tests for JSON schema validation

Part of Phase 1: Critical issues fixes"
```

---

## Task 6: Integration Test - End-to-End Verification

**Files:**
- Test: Manual verification

**Step 1: Run script with --suggest flag**

Run: `python3 scripts/cm_multi_review.py --suggest`
Expected: Output shows detected context and suggested agents without errors

**Step 2: Verify JSON output format**

Run: `python3 scripts/cm_multi_review.py --suggest 2>&1 | grep -A 20 "Detected Context"` or use the new format (if implemented in main)

Expected: Structured output with context information

**Step 3: Test in a real repository**

Run: `cd /tmp && mkdir test-repo && cd test-repo && git init && echo "test" > file.txt && git add . && python3 ~/.claude/plugins/context-memory/scripts/cm_multi_review.py --suggest`

Expected: Script works in a fresh git repository

**Step 4: Verify logging works**

Run: `python3 scripts/cm_multi_review.py --suggest 2>&1 | grep -i "cm_multi_review"`

Expected: If there are warnings/errors, they appear with `[LEVEL] cm_multi_review:` prefix

**Step 5: Run full test suite**

Run: `pytest tests/ -v --ignore=tests/roadmap`
Expected: All tests pass, including new cm_multi_review tests

**Step 6: Commit any minor fixes**

```bash
# If any minor adjustments were needed
git add scripts/cm_multi_review.py tests/test_cm_multi_review.py
git commit -m "test(cm-multi-review): add integration tests and verification

- Manual testing in real repository
- Verify logging output format
- Ensure all tests pass

Part of Phase 1: Critical issues fixes"
```

---

## Task 7: Update suggest_agents() to Use AGENT_PRESETS

**Files:**
- Modify: `scripts/cm_multi_review.py:163-188`

**Step 1: Write test for suggest_agents using AGENT_PRESETS**

Add to `tests/test_cm_multi_review.py`:

```python
from scripts.cm_multi_review import suggest_agents

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

    for agent in agents:
        if agent.startswith("pr-"):
            assert agent.startswith("pr-review-toolkit:")

def test_suggest_agents_returns_valid_preset_agents():
    """Should only return agents defined in AGENT_PRESETS."""
    context = {"change_size": 600}  # Large change
    agents = suggest_agents(context)

    # Should return comprehensive preset agents
    comprehensive_agents = AGENT_PRESETS["comprehensive"]
    for agent in agents:
        assert agent in comprehensive_agents, f"{agent} not in comprehensive preset"
```

**Step 2: Run test to verify current behavior**

Run: `pytest tests/test_cm_multi_review.py -k suggest_agents -v`
Expected: May FAIL or PASS depending on current implementation

**Step 3: Update suggest_agents() to use AGENT_PRESETS**

Replace the `suggest_agents()` function (lines 163-188) with:

```python
def suggest_agents(context: Dict) -> List[str]:
    """Suggest agents based on context.

    Uses AGENT_PRESETS for consistent agent names with full namespace prefixes.

    Args:
        context: Repository context from detect_context()

    Returns:
        List of agent names with full namespace prefixes
    """
    # Size-based preset selection
    if context["change_size"] < 50:
        return AGENT_PRESETS["quick"]
    elif context["change_size"] > 500:
        return AGENT_PRESETS["comprehensive"]

    # Medium-sized changes - build custom list based on context
    agents = [AGENT_PRESETS["quick"][0]]  # Start with feature-dev:code-reviewer

    if context["has_pr"]:
        agents.append("feature-dev:code-reviewer")

    if context["has_tests"]:
        agents.append("pr-review-toolkit:pr-test-analyzer")

    if context["has_types"]:
        agents.append("pr-review-toolkit:type-design-analyzer")

    if context["has_error_handling"]:
        agents.append("pr-review-toolkit:silent-failure-hunter")

    return agents
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_cm_multi_review.py -k suggest_agents -v`
Expected: PASS

**Step 5: Commit**

```bash
git add scripts/cm_multi_review.py tests/test_cm_multi_review.py
git commit -m "refactor(cm-multi-review): update suggest_agents to use AGENT_PRESETS

- Use AGENT_PRESETS constant for consistent agent names
- Return agents with full namespace prefixes
- Size-based preset selection (< 50: quick, > 500: comprehensive)
- Context-aware agent selection for medium changes
- Add tests for agent name validation

Part of Phase 1: Critical issues fixes"
```

---

## Task 8: Final Verification and Documentation

**Files:**
- Documentation: Update if needed

**Step 1: Run full test suite**

Run: `pytest tests/ -v --cov=scripts/cm_multi_review --ignore=tests/roadmap`
Expected: All tests pass with good coverage

**Step 2: Manual verification of all commands**

Run each command and verify output:
```bash
python3 scripts/cm_multi_review.py --list
python3 scripts/cm_multi_review.py --presets
python3 scripts/cm_multi_review.py --suggest
python3 scripts/cm_multi_review.py --context
```

Expected: All commands work without errors

**Step 3: Check git diff to see all changes**

Run: `git diff master~1 scripts/cm_multi_review.py | head -100`
Expected: See all the improvements made

**Step 4: Update design document with implementation notes**

Add to `docs/plans/2026-01-04-cm-multi-review-fixes-design.md`:

```markdown
## Implementation Status

**Phase 1 - Completed** ✅

- [x] Add logging module
- [x] Add AGENT_PRESETS with full qualified names
- [x] Rewrite detect_context() with proper exception handling
- [x] Add validate_environment() function
- [x] Add format_output() for structured JSON
- [x] Update suggest_agents() to use AGENT_PRESETS
- [x] Add comprehensive tests
- [x] Integration testing

**Date Completed:** 2026-01-04

**Commits:**
- feat(cm-multi-review): add logging module
- feat(cm-multi-review): add AGENT_PRESETS with full qualified names
- refactor(cm-multi-review): proper exception handling in detect_context
- feat(cm-multi-review): add validate_environment function
- feat(cm-multi-review): add format_output for structured JSON
- refactor(cm-multi-review): update suggest_agents to use AGENT_PRESETS
```

**Step 5: Final commit**

```bash
git add docs/plans/2026-01-04-cm-multi-review-fixes-design.md
git commit -m "docs(cm-multi-review): mark Phase 1 as completed

All critical issues fixed:
- Logging implemented
- Agent names consistent with full namespace prefixes
- Exception handling properly implemented
- Environment validation added
- Structured JSON output available

Ready for Phase 2: Command markdown updates"
```

---

## Success Criteria

Phase 1 is complete when:
- [ ] All tests pass (`pytest tests/ -v`)
- [ ] No bare `except` clauses remain
- [ ] All agent names use full namespace prefixes
- [ ] Logger is configured and functional
- [ ] `format_output()` returns valid JSON
- [ ] Manual testing confirms script works as expected
- [ ] Git log shows 7+ commits for Phase 1

---

## Next Steps

After completing Phase 1:
1. **Phase 2** - Update `.claude/commands/cm-multi-review.md` to sync with Python changes
2. **Phase 3** - Add important issues (more tests, UX improvements)

---

**End of Implementation Plan**
