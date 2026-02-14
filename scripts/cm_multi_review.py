#!/usr/bin/env python3
"""
Multi-agent code review orchestration script.

This script provides context detection, agent suggestions, and result
aggregation for flexible multi-agent code reviews using the
Claude Code agent framework.

Dependencies:
    - git: Required for repository context detection
    - gh CLI: Optional, for PR-aware agent suggestions
    - Python 3.10+

Usage:
    python3 cm_multi_review.py --suggest     # Context-aware suggestions
    python3 cm_multi_review.py --list        # List all agents
    python3 cm_multi_review.py --presets     # List available presets
    python3 cm_multi_review.py --context     # Show detected context

Example:
    >>> context = detect_context()
    >>> agents = suggest_agents(context)
    >>> print(agents)
    ['feature-dev:code-reviewer', 'pr-review-toolkit:pr-test-analyzer']
"""

import argparse
import json
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Tuple

# Add src to path for imports
plugin_dir = Path(__file__).parent.parent
sys.path.insert(0, str(plugin_dir / "src"))

from infrastructure.logging import get_logger  # type: ignore[import-not-found]
from domain.measurable import (  # type: ignore[import-not-found]
    Gate,
    GateStatus,
    ReasonCode,
    Envelope,
    create_envelope,
    evaluate_context_detection_gate,
    evaluate_agent_selection_gate,
    get_reason_codes_for_context,
)

logger = get_logger(__name__)


# =============================================================================
# CONSTANTS
# =============================================================================

# Change size thresholds for preset selection
CHANGE_SIZE_SMALL_THRESHOLD = 50   # Lines: use "quick" preset
CHANGE_SIZE_LARGE_THRESHOLD = 500  # Lines: use "comprehensive" preset

# Maximum reasonable change size (for bounds checking)
MAX_REASONABLE_CHANGE_SIZE = 10_000_000  # 10 million lines

# Default timeout for git/gh CLI operations (in seconds)
DEFAULT_GIT_TIMEOUT = 5
DEFAULT_GH_TIMEOUT = 5
VALIDATION_TIMEOUT = 2


# =============================================================================
# EXCEPTIONS
# =============================================================================

class EnvironmentValidationError(Exception):
    """Raised when environment validation fails.

    Attributes:
        errors: List of error messages describing validation failures.

    Example:
        >>> raise EnvironmentValidationError(["git not found", "gh CLI not found"])
    """

    def __init__(self, errors: List[str]):
        self.errors = errors
        message = "Environment validation failed:\n" + "\n".join(f"  - {e}" for e in errors)
        super().__init__(message)


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def _run_git_command(
    args: List[str],
    timeout: int = DEFAULT_GIT_TIMEOUT,
    operation: str = "git command"
) -> subprocess.CompletedProcess:
    """Run a git command with comprehensive error handling.

    Args:
        args: Command arguments (without 'git' prefix).
        timeout: Timeout in seconds (default: 5).
        operation: Human-readable operation name for error messages.

    Returns:
        CompletedProcess result with stdout, stderr, returncode.

    Raises:
        RuntimeError: With actionable error message on failure.
        FileNotFoundError: If git executable not found.
        subprocess.TimeoutExpired: If command times out.
        PermissionError: If permission denied.
        OSError: For other OS-level errors.

    Example:
        >>> result = _run_git_command(["diff", "--cached", "--name-only"])
        >>> files = result.stdout.strip().split("\\n") if result.stdout.strip() else []
    """
    try:
        result = subprocess.run(
            ["git"] + args,
            capture_output=True,
            text=True,
            encoding='utf-8',
            errors='replace',
            timeout=timeout,
        )

        # Check for specific git errors
        if result.returncode != 0:
            stderr = result.stderr.strip()

            # Provide actionable error messages
            if "index.lock" in stderr.lower() or "locked" in stderr.lower():
                raise RuntimeError(
                    f"{operation} failed: Git index is locked. "
                    f"Another git operation may be in progress. "
                    f"Try closing other git terminals or remove .git/index.lock"
                )
            elif "corrupt" in stderr.lower():
                raise RuntimeError(
                    f"{operation} failed: Git repository may be corrupted. "
                    f"Run 'git fsck' to diagnose."
                )
            elif "not a git repository" in stderr.lower():
                raise RuntimeError(
                    f"{operation} failed: Not in a git repository"
                )
            elif "fatal:" in stderr.lower():
                raise RuntimeError(
                    f"{operation} failed: {stderr or 'unknown error'}"
                )

        return result

    except subprocess.TimeoutExpired:
        raise RuntimeError(
            f"{operation} timed out after {timeout} seconds. "
            f"Repository may be very large or git may be unresponsive."
        )
    except FileNotFoundError:
        raise RuntimeError(
            f"{operation} failed: git executable not found. "
            f"Install from https://git-scm.com/"
        )
    except PermissionError as e:
        raise RuntimeError(
            f"{operation} failed: Permission denied: {e}"
        )
    except OSError as e:
        raise RuntimeError(
            f"{operation} failed: {e}"
        )
    except RuntimeError:
        # Re-raise RuntimeError already raised above
        raise
    # Don't catch Exception here - let specific errors propagate


def _run_gh_command(
    args: List[str],
    timeout: int = DEFAULT_GH_TIMEOUT
) -> subprocess.CompletedProcess:
    """Run a GitHub CLI (gh) command with comprehensive error handling.

    Args:
        args: Command arguments (without 'gh' prefix).
        timeout: Timeout in seconds (default: 5).

    Returns:
        CompletedProcess result with stdout, stderr, returncode.

    Raises:
        RuntimeError: With actionable error message on failure.
        FileNotFoundError: If gh CLI not found.
        subprocess.TimeoutExpired: If command times out.

    Notes:
        - gh CLI is optional; PR detection will be skipped if not available.
        - Returns result with returncode set; caller should check for success.

    Example:
        >>> result = _run_gh_command(["pr", "view", "--json", "state"])
        >>> has_pr = result.returncode == 0
    """
    try:
        result = subprocess.run(
            ["gh"] + args,
            capture_output=True,
            text=True,
            encoding='utf-8',
            errors='replace',
            timeout=timeout,
        )
        return result

    except FileNotFoundError:
        raise RuntimeError(
            "gh CLI not found. Install from https://cli.github.com/ "
            "to enable PR-aware agent suggestions."
        )
    except subprocess.TimeoutExpired:
        raise RuntimeError(
            f"gh command timed out after {timeout} seconds. "
            "Check network connectivity."
        )
    except OSError as e:
        raise RuntimeError(
            f"gh command failed: {e}"
        )


# =============================================================================
# DATA CLASSES
# =============================================================================

@dataclass(frozen=True)
class Agent:
    """Agent definition for multi-agent code review.

    Attributes:
        name: Full qualified agent name in 'namespace:agent-name' format.
        description: Human-readable description of the agent's purpose.
        source: Plugin source ('feature-dev', 'pr-review-toolkit', or 'superpowers').

    Example:
        >>> agent = Agent("feature-dev:code-reviewer", "General review", "feature-dev")
        >>> agent.name
        'feature-dev:code-reviewer'
    """
    name: str
    description: str
    source: str  # "feature-dev", "pr-review-toolkit", "superpowers"


# =============================================================================
# VALIDATION FUNCTIONS
# =============================================================================

def _validate_agent_name(agent_name: str) -> None:
    """Validate agent name follows namespace:agent-name format.

    Args:
        agent_name: Agent name to validate.

    Raises:
        ValueError: If agent name doesn't match expected format.
    """
    if not agent_name:
        raise ValueError("Agent name cannot be empty")

    # Strip whitespace and validate no remaining whitespace
    agent_name_stripped = agent_name.strip()
    if agent_name != agent_name_stripped:
        raise ValueError(
            f"Agent name '{agent_name}' has leading/trailing whitespace. "
            f"Use '{agent_name_stripped}' instead."
        )

    if " " in agent_name or "\t" in agent_name:
        raise ValueError(
            f"Agent name '{agent_name}' contains whitespace. "
            f"Use format 'namespace:agent-name' without spaces."
        )

    # Check for control characters and other problematic characters
    problematic_chars = ['\n', '\r', '\0', '\v', '\f']
    found = [c for c in problematic_chars if c in agent_name]
    if found:
        raise ValueError(
            f"Agent name '{agent_name}' contains invalid character(s): {repr(found)}"
        )

    parts = agent_name.split(":")
    if len(parts) != 2:
        raise ValueError(
            f"Invalid agent name format '{agent_name}'. "
            f"Expected 'namespace:agent-name' format with exactly one colon separator."
        )

    namespace, name = parts
    if not namespace or not name:
        raise ValueError(
            f"Invalid agent name '{agent_name}'. "
            f"Both namespace and agent name must be non-empty."
        )


def _validate_agent_data_consistency() -> None:
    """Validate that all agents in AGENT_PRESETS exist in AGENT_MAP.

    Also checks for duplicates and other inconsistencies.

    Raises:
        ValueError: If data consistency issues are detected.
    """
    errors = []

    # Check 1: Agents in presets exist in map
    missing_agents = []
    for preset_name, agent_list in AGENT_PRESETS.items():
        for agent_name in agent_list:
            if agent_name not in AGENT_MAP:
                missing_agents.append(
                    f"  - '{agent_name}' in preset '{preset_name}'"
                )

    if missing_agents:
        errors.append(
            "Agents in AGENT_PRESETS not found in AGENT_MAP:\n"
            + "\n".join(missing_agents) +
            f"\n\nAvailable agents in AGENT_MAP: {list(AGENT_MAP.keys())}"
        )

    # Check 2: No duplicate agents in presets
    for preset_name, agent_list in AGENT_PRESETS.items():
        seen = set()
        duplicates = set()
        for agent_name in agent_list:
            if agent_name in seen:
                duplicates.add(agent_name)
            seen.add(agent_name)

        if duplicates:
            errors.append(
                f"Duplicate agents in preset '{preset_name}': {list(duplicates)}"
            )

    # Check 3: No duplicate agent names in AGENT_MAP
    agent_names = list(AGENT_MAP.keys())
    if len(agent_names) != len(set(agent_names)):
        seen_counts: dict[str, int] = {}
        dup_list: list[str] = []
        for name in agent_names:
            count = seen_counts.get(name, 0)
            if count > 0:
                dup_list.append(f"'{name}' appears {count + 1} times")
            seen_counts[name] = count + 1

        if dup_list:
            errors.append(f"Duplicate agent names in AGENT_MAP: {dup_list}")

    # Check 4: Validate all agent name formats
    for agent_name in AGENT_MAP.keys():
        try:
            _validate_agent_name(agent_name)
        except ValueError as e:
            errors.append(f"Invalid agent name '{agent_name}': {e}")

    if errors:
        error_msg = "Data consistency errors detected:\n\n" + "\n\n".join(errors)
        logger.critical(error_msg)
        raise ValueError(error_msg)


# =============================================================================
# AGENT DATA
# =============================================================================

# Available agents organized by priority
PRIMARY_AGENTS = [
    Agent("feature-dev:code-reviewer", "General code review with confidence scoring", "feature-dev"),
]

SPECIALIZED_AGENTS = [
    Agent("pr-review-toolkit:pr-test-analyzer", "Test coverage quality and completeness", "pr-review-toolkit"),
    Agent("pr-review-toolkit:silent-failure-hunter", "Error handling and silent failures", "pr-review-toolkit"),
    Agent("pr-review-toolkit:type-design-analyzer", "Type design quality and invariants", "pr-review-toolkit"),
    Agent("pr-review-toolkit:comment-analyzer", "Code comment accuracy and maintainability", "pr-review-toolkit"),
    Agent("pr-review-toolkit:code-simplifier", "Code simplification and refactoring", "pr-review-toolkit"),
    Agent("pr-review-toolkit:code-reviewer", "General code review for project guidelines", "pr-review-toolkit"),
]

FRAMEWORK_AGENTS = [
    Agent("superpowers:code-review-checklist", "Framework-specific review guidance", "superpowers"),
]

ALL_AGENTS = PRIMARY_AGENTS + SPECIALIZED_AGENTS + FRAMEWORK_AGENTS
AGENT_MAP = {agent.name: agent for agent in ALL_AGENTS}

# Agent presets with full qualified names
AGENT_PRESETS = {
    "quick": ["feature-dev:code-reviewer"],
    "thorough": [
        "feature-dev:code-reviewer",
        "pr-review-toolkit:pr-test-analyzer",
        "pr-review-toolkit:silent-failure-hunter",
        "pr-review-toolkit:code-simplifier",
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


# =============================================================================
# LAZY VALIDATION
# =============================================================================
# NOTE: This module-level lazy validation pattern assumes single-threaded
# execution. The module-level _validation_performed and _validation_failed
# flags are accessed without locking. In Python's CPython implementation,
# the GIL (Global Interpreter Lock) prevents actual race conditions for
# simple boolean reads/writes, making this pattern safe for CLI scripts.
# If this code is ever used in a multi-threaded context, add threading.Lock().

_validation_performed = False
_validation_failed = False


def _ensure_agent_data_consistency() -> None:
    """Ensure agent data is consistent, validating once.

    This function implements a lazy validation pattern that validates
    agent data consistency only on first call, then caches the result.
    Subsequent calls return immediately (or raise if validation failed).

    Thread Safety: This function is NOT thread-safe. It assumes single-
    threaded CLI execution. See module-level note for details.

    Raises:
        ValueError: If data consistency issues are detected.
    """
    global _validation_performed, _validation_failed

    if _validation_performed:
        if _validation_failed:
            raise ValueError("Agent data consistency check previously failed")
        return

    try:
        _validate_agent_data_consistency()
        _validation_performed = True
    except ValueError:
        _validation_failed = True
        raise


# =============================================================================
# CONTEXT DETECTION
# =============================================================================

def detect_context() -> Dict[str, Any]:
    """Detect repository context and state.

    Performs git and gh CLI operations to gather:
    - PR status (via gh CLI)
    - Changed files (staged + working directory)
    - File type patterns (tests, types, error handlers)
    - Change size (line count from git diff --shortstat)

    Returns:
        Dictionary with keys: has_pr, has_tests, has_types, has_error_handling,
        has_comments, change_size, staged_files, working_files, git_available.
        May include partial_context=True if git detection failed partially.

    Notes:
        - Logs warnings for non-fatal errors (gh CLI not found, git timeout)
        - Returns partial context on git failures (fields may be empty/default)
        - Change size of 0 indicates detection failure or no changes

    Raises:
        RuntimeError: If git binary not found and no context can be detected.
    """
    context: Dict[str, Any] = {
        "has_pr": False,
        "has_tests": False,
        "has_types": False,
        "has_error_handling": False,
        "has_comments": False,
        "change_size": 0,
        "staged_files": [],
        "working_files": [],
        "git_available": True,  # Default to True, set False if git fails
    }

    # Detect PR using helper
    try:
        result = _run_gh_command(["pr", "view", "--json", "state"])
        context["has_pr"] = result.returncode == 0

        # If gh CLI exists but returns error, provide helpful feedback
        if result.returncode != 0 and result.stderr:
            if "not logged in" in result.stderr.lower():
                logger.warning(
                    "gh CLI not authenticated. Run 'gh auth login' to enable PR detection."
                )
            elif "not a git repository" in result.stderr.lower():
                logger.debug("Not in a git repository - PR detection unavailable")
            elif "could not find a pr" in result.stderr.lower():
                logger.debug("No PR found for current branch")

    except RuntimeError as e:
        # RuntimeError from _run_gh_command already has actionable message
        logger.warning(str(e))
        context["has_pr"] = False

    # Detect git state
    try:
        # Detect staged files using helper
        result = _run_git_command(
            ["diff", "--cached", "--name-only"],
            operation="staged files detection"
        )
        if result.stdout.strip():
            # Sanitize file paths (filter null bytes, carriage returns)
            raw_files = result.stdout.strip().split("\n")
            # SECURITY: Limit file list to prevent memory exhaustion
            MAX_FILES = 10000
            if len(raw_files) > MAX_FILES:
                logger.warning(
                    f"Too many staged files ({len(raw_files)}), "
                    f"truncating to {MAX_FILES}"
                )
                raw_files = raw_files[:MAX_FILES]
            context["staged_files"] = [
                f for f in raw_files
                if f and not any(c in f for c in ['\0', '\r'])
            ]

        # Detect working directory files using helper
        result = _run_git_command(
            ["diff", "--name-only"],
            operation="working directory detection"
        )
        if result.stdout.strip():
            raw_files = result.stdout.strip().split("\n")
            # SECURITY: Limit file list to prevent memory exhaustion
            MAX_FILES = 10000
            if len(raw_files) > MAX_FILES:
                logger.warning(
                    f"Too many working files ({len(raw_files)}), "
                    f"truncating to {MAX_FILES}"
                )
                raw_files = raw_files[:MAX_FILES]
            context["working_files"] = [
                f for f in raw_files
                if f and not any(c in f for c in ['\0', '\r'])
            ]

        # Combine all changed files
        all_files = context["staged_files"] + context["working_files"]

        # Check for test files (case-insensitive)
        test_patterns = ["_test.py", "_test.ts", ".test.ts", ".spec.ts", "__tests__.py", "tests/"]
        context["has_tests"] = any(
            any(pattern.lower() in f.lower() for pattern in test_patterns)
            for f in all_files
        )

        # Check for type definitions (case-insensitive)
        type_patterns = ["_types.ts", ".d.ts", "types.py", "types.ts"]
        context["has_types"] = any(
            any(pattern.lower() in f.lower() for pattern in type_patterns)
            for f in all_files
        )

        # Check for error handling changes (case-insensitive)
        error_patterns = ["error", "exception", "handler"]
        context["has_error_handling"] = any(
            any(pattern.lower() in f.lower() for pattern in error_patterns)
            for f in all_files
        )

        # Estimate change size with robust parsing using helper
        result = _run_git_command(
            ["diff", "--cached", "--shortstat"],
            operation="change size detection"
        )
        if result.stdout.strip():
            try:
                # More robust parsing using regex
                match = re.search(r'(\d+)\s+insertion', result.stdout)
                if match:
                    change_size = int(match.group(1))
                    # Add bounds checking
                    context["change_size"] = min(change_size, MAX_REASONABLE_CHANGE_SIZE)
                    if change_size >= MAX_REASONABLE_CHANGE_SIZE:
                        logger.warning(f"Change size capped at {MAX_REASONABLE_CHANGE_SIZE}")
            except (ValueError, AttributeError) as e:
                logger.error(
                    f"Unexpected error parsing git shortstat output: {e}. "
                    f"Output was: {result.stdout}"
                )

    except RuntimeError as e:
        # RuntimeError from _run_git_command - already has actionable message
        logger.error(f"Git context detection failed: {e}")
        context["partial_context"] = True
        context["git_available"] = False  # Mark git as unavailable

    return context


# =============================================================================
# ENVIRONMENT VALIDATION
# =============================================================================

def validate_environment(raise_on_error: bool = False) -> Tuple[bool, List[str]]:
    """Validate that required tools are available.

    Checks for git (required) and gh CLI (optional) availability.

    Args:
        raise_on_error: If True, raises EnvironmentValidationError on failure.
            If False, returns tuple for backward compatibility.

    Returns:
        Tuple of (is_valid: bool, errors: list[str]) when raise_on_error=False.
        When raise_on_error=True, raises EnvironmentValidationError instead.

    Raises:
        EnvironmentValidationError: If validation fails and raise_on_error=True.

    Examples:
        >>> is_valid, errors = validate_environment()
        >>> if not is_valid:
        ...     print("\\n".join(errors))
    """
    errors = []

    # Check git (REQUIRED)
    try:
        result = subprocess.run(
            ["git", "--version"],
            capture_output=True,
            text=True,
            timeout=VALIDATION_TIMEOUT,
        )
        if result.returncode != 0:
            error = "git is not working properly"
            errors.append(error)
            logger.error(error)
        elif not result.stdout.strip():
            error = "git produced no output (may be corrupted)"
            errors.append(error)
            logger.error(error)
        else:
            logger.info(f"git detected: {result.stdout.strip()}")

    except FileNotFoundError:
        error = "git not found - install from https://git-scm.com/"
        errors.append(error)
        logger.error(error)
    except subprocess.TimeoutExpired:
        error = "git timed out after 2 seconds - may not be responding"
        errors.append(error)
        logger.error(error)
    except PermissionError as e:
        error = f"git permission denied: {e}"
        errors.append(error)
        logger.error(error)
    # Catch-all for truly unexpected exceptions (defensive programming at top level).
    # This is acceptable here because: (1) we're at module entry point, (2) we log
    # the full traceback for debugging, (3) we return error status rather than crash.
    except Exception as e:
        error = f"Unexpected git check failure: {e}"
        errors.append(error)
        logger.error(error, exc_info=True)

    # Check gh CLI (OPTIONAL)
    try:
        result = subprocess.run(
            ["gh", "--version"],
            capture_output=True,
            text=True,
            timeout=VALIDATION_TIMEOUT,
        )
        if result.returncode == 0:
            logger.info(f"gh CLI detected: {result.stdout.strip()}")
        else:
            logger.debug("gh CLI check returned non-zero (optional tool)")
    except FileNotFoundError:
        logger.debug("gh CLI not found - PR detection will be disabled")
    except subprocess.TimeoutExpired:
        logger.debug("gh CLI timed out (optional tool)")
    except OSError as e:
        # Catch OS-level errors (PermissionError, etc.) for optional tool
        logger.debug(f"gh CLI check failed with OS error: {e}")
    # Note: gh CLI is optional, so we gracefully handle all expected errors.
    # Unexpected non-OS errors (e.g., KeyboardInterrupt) should propagate.

    is_valid = len(errors) == 0

    if not is_valid and raise_on_error:
        raise EnvironmentValidationError(errors)

    return is_valid, errors


# =============================================================================
# AGENT SELECTION
# =============================================================================

def _find_agent(preset: str, suffix: str) -> str:
    """Find agent in preset by name suffix.

    Searches for agents ending with the given suffix within a preset.
    Validates agent name format and existence in AGENT_MAP.

    Args:
        preset: Preset name ('thorough', 'comprehensive', etc.)
        suffix: Agent name suffix ('pr-test-analyzer', 'code-reviewer', etc.)

    Returns:
        Full qualified agent name with namespace prefix.

    Raises:
        ValueError: If suffix is empty, preset is invalid, no match found,
            match is ambiguous, agent format invalid, or agent not in AGENT_MAP.

    Example:
        >>> _find_agent("thorough", "pr-test-analyzer")
        'pr-review-toolkit:pr-test-analyzer'
    """
    if not suffix:
        raise ValueError("suffix cannot be empty")

    if preset not in AGENT_PRESETS:
        raise ValueError(f"Invalid preset '{preset}'. Must be one of: {list(AGENT_PRESETS.keys())}")

    # Find all agents matching the suffix
    matching_agents = [agent for agent in AGENT_PRESETS[preset] if agent.endswith(suffix)]

    if not matching_agents:
        raise ValueError(f"No agent ending with '{suffix}' in {preset} preset")

    # Check for ambiguous matches
    if len(matching_agents) > 1:
        raise ValueError(
            f"Ambiguous suffix '{suffix}' in {preset} preset. "
            f"Multiple agents match: {matching_agents}"
        )

    agent = matching_agents[0]

    # Validate agent name format
    _validate_agent_name(agent)

    # Check agent exists in AGENT_MAP
    if agent not in AGENT_MAP:
        raise ValueError(
            f"Agent '{agent}' found in preset '{preset}' but not in AGENT_MAP. "
            f"Available agents: {list(AGENT_MAP.keys())}"
        )

    return agent


def _get_preset_reason(preset: str, context: Dict[str, Any]) -> str:
    """Generate explanation for why a preset was suggested.

    Args:
        preset: Preset name that was selected.
        context: Repository context from detect_context().

    Returns:
        Human-readable explanation string.
    """
    reasons = {
        "quick": "Small change (< 50 lines) - fast review",
        "thorough": "Medium change with specific focus areas",
        "comprehensive": "Large change (> 500 lines) - complete review",
        "framework": "Framework-specific compliance review",
        "custom": "Context-driven agent selection",
    }

    if preset not in reasons:
        logger.warning(f"Unknown preset '{preset}' - using default reason. "
                      f"Known presets: {list(reasons.keys())}")

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


def format_output(context: Dict[str, Any], suggested_preset: str, warnings: List[str]) -> str:
    """Format detection results as structured JSON.

    Args:
        context: Detected repository context.
        suggested_preset: Recommended preset name.
        warnings: List of non-fatal warnings.

    Returns:
        JSON string with structured output.
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


def suggest_agents(context: Dict[str, Any]) -> List[str]:
    """Suggest agents based on repository context.

    Uses change size and file type detection to recommend appropriate
    review agents from AGENT_PRESETS.

    Args:
        context: Repository context from detect_context() with keys:
            - change_size: Number of lines changed (int)
            - has_tests: Whether test files were detected (bool)
            - has_types: Whether type definition files detected (bool)
            - has_error_handling: Whether error handler files detected (bool)

    Returns:
        List of full qualified agent names with namespace prefixes.

    Selection Criteria:
        - change_size < 50: Returns 'quick' preset (1 agent)
        - change_size > 500: Returns 'comprehensive' preset (7 agents)
        - Medium changes: Builds custom list based on detected file types

    Example:
        >>> context = {"change_size": 100, "has_tests": True}
        >>> suggest_agents(context)
        ['feature-dev:code-reviewer', 'pr-review-toolkit:pr-test-analyzer']
    """
    # Size-based preset selection using constants
    if context.get("change_size", 0) < CHANGE_SIZE_SMALL_THRESHOLD:
        return AGENT_PRESETS["quick"]
    elif context.get("change_size", 0) > CHANGE_SIZE_LARGE_THRESHOLD:
        return AGENT_PRESETS["comprehensive"]

    # Medium-sized changes - build custom list based on context
    agents = [_find_agent("quick", "code-reviewer")]

    if context.get("has_tests", False):
        agents.append(_find_agent("thorough", "pr-test-analyzer"))

    if context.get("has_types", False):
        agents.append(_find_agent("comprehensive", "type-design-analyzer"))

    if context.get("has_error_handling", False):
        agents.append(_find_agent("thorough", "silent-failure-hunter"))

    return agents


# =============================================================================
# MEASURABLE SYSTEM: Agent Suggestions with Reason Codes
# =============================================================================

@dataclass(frozen=True)
class AgentSuggestion:
    """Structured agent suggestion with reason codes.

    Attributes:
        agents: Tuple of recommended agent names
        reason_codes: Tuple of reason codes explaining the selection
        preset_used: Name of the preset used (or 'custom')
    """
    agents: Tuple[str, ...]
    reason_codes: Tuple[ReasonCode, ...]
    preset_used: str


def suggest_agents_with_reasons(context: Dict[str, Any]) -> AgentSuggestion:
    """Suggest agents with structured reason codes.

    This is the measurable version of suggest_agents() that returns
    structured data with reason codes explaining the selection.

    Args:
        context: Repository context from detect_context()

    Returns:
        AgentSuggestion with agents, reason codes, and preset name.

    Example:
        >>> context = {"change_size": 25, "git_available": True}
        >>> result = suggest_agents_with_reasons(context)
        >>> result.preset_used
        'quick'
        >>> result.reason_codes[0]
        <ReasonCode.M101_SMALL_CHANGE: 'M101'>
    """
    # Get reason codes from context
    reason_codes = get_reason_codes_for_context(context)

    # Determine preset based on change size
    change_size = context.get("change_size", 0)
    git_available = context.get("git_available", True)

    if not git_available:
        # Fallback to quick preset when git unavailable (degraded mode)
        logger.warning(
            "Git not available - operating in degraded mode. "
            "Using 'quick' preset as fallback."
        )
        preset_name = "quick"
        agents = tuple(AGENT_PRESETS[preset_name])
    elif change_size < CHANGE_SIZE_SMALL_THRESHOLD:
        preset_name = "quick"
        agents = tuple(AGENT_PRESETS[preset_name])
    elif change_size > CHANGE_SIZE_LARGE_THRESHOLD:
        preset_name = "comprehensive"
        agents = tuple(AGENT_PRESETS[preset_name])
    else:
        # Medium-sized changes - build custom list
        preset_name = "custom"
        agent_list = [_find_agent("quick", "code-reviewer")]

        if context.get("has_tests", False):
            agent_list.append(_find_agent("thorough", "pr-test-analyzer"))

        if context.get("has_types", False):
            agent_list.append(_find_agent("comprehensive", "type-design-analyzer"))

        if context.get("has_error_handling", False):
            agent_list.append(_find_agent("thorough", "silent-failure-hunter"))

        agents = tuple(agent_list)

    return AgentSuggestion(
        agents=agents,
        reason_codes=reason_codes,
        preset_used=preset_name,
    )


def format_output_envelope(
    context: Dict[str, Any],
    suggested_preset: str,
    agents: List[str],
    warnings: List[str],
    errors: List[str]
) -> str:
    """Format output as structured JSON envelope.

    Creates a measurable envelope with quality gates, reason codes,
    and structured data for reliable parsing.

    Args:
        context: Detected repository context
        suggested_preset: Recommended preset name
        agents: List of suggested agents
        warnings: Non-fatal warning messages
        errors: Error messages (causes FAIL verdict)

    Returns:
        JSON string with envelope structure.

    Example:
        >>> context = {"change_size": 100, "git_available": True}
        >>> result = format_output_envelope(context, "quick", ["test:agent"], [], [])
        >>> import json
        >>> parsed = json.loads(result)
        >>> "$schema" in parsed
        True
    """
    # Evaluate quality gates
    context_gate = evaluate_context_detection_gate(context)
    agent_gate = evaluate_agent_selection_gate(agents)

    gates = (context_gate, agent_gate)

    # Get reason codes
    reason_codes = get_reason_codes_for_context(context)

    # Build data payload
    data = {
        "agents": agents,
        "preset": suggested_preset,
        "context": {
            "has_pr": context.get("has_pr", False),
            "has_tests": context.get("has_tests", False),
            "has_types": context.get("has_types", False),
            "has_error_handling": context.get("has_error_handling", False),
            "change_size": context.get("change_size", 0),
        },
    }

    # Create envelope using domain helper
    envelope = create_envelope(
        data=data,
        gates=gates,
        reason_codes=reason_codes,
        warnings=tuple(warnings),
        errors=tuple(errors),
    )

    return envelope.to_json()


def format_agent_list(agents: List[Agent], group_name: str) -> str:
    """Format agents for display.

    Args:
        agents: List of Agent objects to format.
        group_name: Section header for the agent group.

    Returns:
        Formatted string with group name and agent details.

    Example:
        >>> agents = [Agent("feature-dev:code-reviewer", "General review", "feature-dev")]
        >>> print(format_agent_list(agents, "Primary"))
        <blank line>
        Primary:
          feature-dev:code-reviewer: General code review with confidence scoring
    """
    lines = [f"\n{group_name}:"]
    for agent in agents:
        lines.append(f"  {agent.name}: {agent.description}")
    return "\n".join(lines)


# =============================================================================
# MAIN ENTRY POINT
# =============================================================================

def main() -> None:
    """Main entry point with comprehensive error handling."""
    try:
        # Ensure data consistency before running
        _ensure_agent_data_consistency()
    except ValueError as e:
        print(f"Configuration error: {e}", file=sys.stderr)
        print("\nThis appears to be a bug in the agent configuration.", file=sys.stderr)
        print("Please report this issue.", file=sys.stderr)
        sys.exit(1)

    try:
        parser = argparse.ArgumentParser(
            description="Multi-agent code review orchestration",
            formatter_class=argparse.RawDescriptionHelpFormatter,
            epilog="""
Examples:
  %(prog)s --suggest              # Suggest agents based on context
  %(prog)s --list                 # List all available agents
  %(prog)s --presets              # List available presets
            """
        )

        parser.add_argument(
            "--suggest",
            action="store_true",
            help="Suggest agents based on current repository context"
        )
        parser.add_argument(
            "--list",
            action="store_true",
            help="List all available agents"
        )
        parser.add_argument(
            "--presets",
            action="store_true",
            help="List available presets"
        )
        parser.add_argument(
            "--context",
            action="store_true",
            help="Show detected context information"
        )
        parser.add_argument(
            "--json",
            action="store_true",
            help="Output in structured JSON envelope format (use with --suggest)"
        )

        args = parser.parse_args()

        if args.suggest:
            try:
                context = detect_context()
            except RuntimeError as e:
                if args.json:
                    # Output error as JSON envelope
                    error_output = format_output_envelope(
                        context={},
                        suggested_preset="",
                        agents=[],
                        warnings=[],
                        errors=[f"Error detecting repository context: {e}"]
                    )
                    print(error_output)
                else:
                    print(f"Error detecting repository context: {e}", file=sys.stderr)
                    print("\nCannot suggest agents without context information.", file=sys.stderr)
                sys.exit(1)
            except subprocess.TimeoutExpired as e:
                # Handle timeout specifically - user can take action (increase timeout)
                if args.json:
                    error_output = format_output_envelope(
                        context={},
                        suggested_preset="",
                        agents=[],
                        warnings=[],
                        errors=[f"Git command timed out: {e}. Try running in a smaller repository."]
                    )
                    print(error_output)
                else:
                    print(f"Git command timed out: {e}", file=sys.stderr)
                    print("Try running in a smaller repository or check git performance.", file=sys.stderr)
                logger.error(f"Git timeout during context detection: {e}")
                sys.exit(1)
            except (FileNotFoundError, PermissionError) as e:
                # Handle filesystem/access errors specifically
                if args.json:
                    error_output = format_output_envelope(
                        context={},
                        suggested_preset="",
                        agents=[],
                        warnings=[],
                        errors=[f"System error: {e}"]
                    )
                    print(error_output)
                else:
                    print(f"System error: {e}", file=sys.stderr)
                logger.error(f"Filesystem error during context detection: {e}")
                sys.exit(1)
            except OSError as e:
                # Handle other OS-level errors
                if args.json:
                    error_output = format_output_envelope(
                        context={},
                        suggested_preset="",
                        agents=[],
                        warnings=[],
                        errors=[f"OS error: {e}"]
                    )
                    print(error_output)
                else:
                    print(f"OS error: {e}", file=sys.stderr)
                logger.error(f"OS error during context detection: {e}")
                sys.exit(1)
            except Exception as e:
                # Catch-all for truly unexpected errors with full traceback
                if args.json:
                    error_output = format_output_envelope(
                        context={},
                        suggested_preset="",
                        agents=[],
                        warnings=[],
                        errors=[f"Unexpected error ({type(e).__name__}): {e}"]
                    )
                    print(error_output)
                else:
                    print(f"Unexpected error ({type(e).__name__}): {e}", file=sys.stderr)
                logger.error(f"Context detection failed with unexpected error: {e}", exc_info=True)
                sys.exit(1)

            # JSON output mode
            if args.json:
                suggestion = suggest_agents_with_reasons(context)
                warnings = []
                if not context.get("has_pr"):
                    warnings.append("No PR detected")
                if context.get("change_size", 0) == 0:
                    warnings.append("Change size could not be determined")

                output = format_output_envelope(
                    context=context,
                    suggested_preset=suggestion.preset_used,
                    agents=list(suggestion.agents),
                    warnings=warnings,
                    errors=[]
                )
                print(output)
                return

            # Human-readable output mode
            print("🔍 Detecting repository context...\n")

            if args.context:
                print("Detected Context:")
                print(f"  Has PR: {context['has_pr']}")
                print(f"  Has tests: {context['has_tests']}")
                print(f"  Has types: {context['has_types']}")
                print(f"  Has error handling: {context['has_error_handling']}")
                print(f"  Change size: {context['change_size']} lines")
                print(f"  Staged files: {len(context['staged_files'])}")
                print(f"  Working files: {len(context['working_files'])}")
                print()

            agents = suggest_agents(context)
            missing_agents = []
            print("✅ Suggested agents based on context:\n")
            for agent_name in agents:
                agent = AGENT_MAP.get(agent_name)
                if agent:
                    print(f"  • {agent.name}")
                    print(f"    {agent.description}")
                else:
                    # CRITICAL: Track missing agents and fail after display
                    missing_agents.append(agent_name)
                    print(f"  ❌ ERROR: Agent '{agent_name}' not found in AGENT_MAP")
                    logger.error(f"Agent '{agent_name}' not found. Valid: {list(AGENT_MAP.keys())}")
            print()

            # Fail fast if any agents are missing - indicates configuration bug
            if missing_agents:
                print(f"FATAL: {len(missing_agents)} agent(s) not found in AGENT_MAP.", file=sys.stderr)
                print("This indicates a plugin configuration bug.", file=sys.stderr)
                sys.exit(2)

        elif args.list:
            print("Available Agents:\n")
            print(format_agent_list(PRIMARY_AGENTS, "Primary (Recommended)"))
            print(format_agent_list(SPECIALIZED_AGENTS, "Specialized (pr-review-toolkit)"))
            print(format_agent_list(FRAMEWORK_AGENTS, "Framework-Specific"))
            print()

        elif args.presets:
            print("Available Presets:\n")
            for name, agents in AGENT_PRESETS.items():
                print(f"  {name}: {', '.join(agents)}")
            print()

        elif args.context:
            print("Repository Context:\n")
            try:
                context = detect_context()
            except RuntimeError as e:
                print(f"Error detecting repository context: {e}", file=sys.stderr)
                sys.exit(1)
            except Exception as e:
                print(f"Unexpected error detecting context: {e}", file=sys.stderr)
                logger.error(f"Context detection failed: {e}", exc_info=True)
                sys.exit(1)

            print(f"  Has PR: {context['has_pr']}")
            print(f"  Has tests: {context['has_tests']}")
            print(f"  Has types: {context['has_types']}")
            print(f"  Has error handling: {context['has_error_handling']}")
            print(f"  Change size: {context['change_size']} lines")
            print(f"  Staged files: {len(context['staged_files'])}")
            print(f"  Working files: {len(context['working_files'])}")

            if context["staged_files"]:
                print("\n  Staged files:")
                for f in context["staged_files"][:10]:
                    print(f"    - {f}")
                if len(context["staged_files"]) > 10:
                    print(f"    ... and {len(context['staged_files']) - 10} more")

            if context["working_files"]:
                print("\n  Working files:")
                for f in context["working_files"][:10]:
                    print(f"    - {f}")
                if len(context["working_files"]) > 10:
                    print(f"    ... and {len(context['working_files']) - 10} more")

            print()

        else:
            parser.print_help()

    except KeyboardInterrupt:
        print("\nOperation cancelled by user.", file=sys.stderr)
        sys.exit(130)  # Standard exit code for SIGINT
    except MemoryError:
        print("Out of memory. The repository may be too large.", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Unexpected error: {e}", file=sys.stderr)
        logger.error(f"Unhandled exception in main(): {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
