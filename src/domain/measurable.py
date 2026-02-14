"""
Domain types for the Measurable system.

This module provides structured output types for code review operations,
including envelope patterns, reason codes, and quality gates.

Usage:
    >>> from src.domain.measurable import Envelope, Gate, GateStatus, ReasonCode
    >>> gate = Gate(gate_id="test", status=GateStatus.PASS, description="OK")
    >>> envelope = Envelope(
    ...     schema="https://claude.ai/schemas/measurable/v1",
    ...     generated_at="2026-02-14T12:00:00Z",
    ...     verdict=GateStatus.PASS,
    ...     data={},
    ...     gates=(gate,),
    ...     reason_codes=(ReasonCode.M100_OK,),
    ...     warnings=(),
    ...     errors=()
    ... )
"""

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, Tuple


class GateStatus(Enum):
    """Status values for quality gates.

    Attributes:
        PASS: Gate passed successfully
        WARNING: Gate passed with concerns
        FAIL: Gate failed
        INCONCLUSIVE: Unable to determine gate status
    """
    PASS = "PASS"
    WARNING = "WARNING"
    FAIL = "FAIL"
    INCONCLUSIVE = "INCONCLUSIVE"


class ReasonCode(Enum):
    """Reason codes explaining why certain decisions were made.

    M1xx: Normal operation codes
    M2xx: Context detection codes
    M3xx: Environment codes
    """
    # Normal operation
    M100_OK = "M100"
    M101_SMALL_CHANGE = "M101"   # < 50 lines
    M102_MEDIUM_CHANGE = "M102"  # 50-500 lines
    M103_LARGE_CHANGE = "M103"   # > 500 lines

    # Context detection
    M200_PARTIAL_CONTEXT = "M200"

    # Environment
    M300_NO_GIT = "M300"


# Type aliases for clarity
GateTuple = Tuple["Gate", ...]
ReasonCodeTuple = Tuple[ReasonCode, ...]
StringTuple = Tuple[str, ...]


@dataclass(frozen=True)
class Gate:
    """Represents a quality gate evaluation result.

    Gates are used to evaluate specific aspects of a code review,
    such as context detection, agent selection, or test coverage.

    Attributes:
        gate_id: Unique identifier for this gate
        status: The gate's evaluation status
        description: Human-readable description of the gate result
        details: Optional additional details

    Example:
        >>> gate = Gate(
        ...     gate_id="context_detection",
        ...     status=GateStatus.PASS,
        ...     description="All context detected successfully",
        ...     details="Found git, PR, and test files"
        ... )
    """
    gate_id: str
    status: GateStatus
    description: str
    details: str = ""

    def to_dict(self) -> Dict[str, Any]:
        """Convert gate to dictionary for serialization."""
        return {
            "gate_id": self.gate_id,
            "status": self.status.value,
            "description": self.description,
            "details": self.details,
        }


@dataclass(frozen=True)
class Envelope:
    """Standardized envelope for structured output.

    The envelope pattern provides a consistent structure for all outputs,
    including schema version, timestamp, verdict, and structured data.

    Attributes:
        schema: JSON schema URL for this envelope format
        generated_at: ISO 8601 timestamp of generation
        verdict: Overall verdict across all gates
        data: The actual payload data
        gates: Tuple of quality gate results
        reason_codes: Tuple of reason codes explaining decisions
        warnings: Tuple of warning messages
        errors: Tuple of error messages

    Example:
        >>> envelope = Envelope(
        ...     schema="https://claude.ai/schemas/measurable/v1",
        ...     generated_at="2026-02-14T12:00:00Z",
        ...     verdict=GateStatus.PASS,
        ...     data={"agents": ["feature-dev:code-reviewer"]},
        ...     gates=(),
        ...     reason_codes=(ReasonCode.M100_OK,),
        ...     warnings=(),
        ...     errors=()
        ... )
    """
    schema: str
    generated_at: str
    verdict: GateStatus
    data: Dict[str, Any]
    gates: GateTuple
    reason_codes: ReasonCodeTuple
    warnings: StringTuple
    errors: StringTuple

    def to_dict(self) -> Dict[str, Any]:
        """Convert envelope to dictionary for serialization."""
        return {
            "$schema": self.schema,
            "generated_at": self.generated_at,
            "verdict": self.verdict.value,
            "data": self.data,
            "gates": [gate.to_dict() for gate in self.gates],
            "reason_codes": [code.value for code in self.reason_codes],
            "warnings": list(self.warnings),
            "errors": list(self.errors),
        }

    def to_json(self) -> str:
        """Convert envelope to JSON string."""
        return json.dumps(self.to_dict(), indent=2)


# =============================================================================
# GATE EVALUATION FUNCTIONS
# =============================================================================

def evaluate_context_detection_gate(context: Dict[str, Any]) -> Gate:
    """Evaluate the context detection quality gate.

    Analyzes the detected context to determine if sufficient information
    was gathered for making agent recommendations.

    Args:
        context: Dictionary containing detected context information.
            Expected keys: has_pr, has_tests, change_size, languages, git_available

    Returns:
        Gate with evaluation result and details.

    Example:
        >>> context = {"has_pr": True, "has_tests": True, "change_size": 100,
        ...            "languages": ["python"], "git_available": True}
        >>> gate = evaluate_context_detection_gate(context)
        >>> gate.status
        <GateStatus.PASS: 'PASS'>
    """
    git_available = context.get("git_available", False)

    # Critical: No git = FAIL
    if not git_available:
        return Gate(
            gate_id="context_detection",
            status=GateStatus.FAIL,
            description="Git not available - cannot detect repository context",
            details="Install git or run from within a git repository"
        )

    # Count missing context items
    missing = []
    if not context.get("has_pr"):
        missing.append("PR context")
    if not context.get("has_tests"):
        missing.append("test detection")
    if context.get("change_size", 0) == 0:
        missing.append("change size")
    if not context.get("languages"):
        missing.append("language detection")

    if not missing:
        return Gate(
            gate_id="context_detection",
            status=GateStatus.PASS,
            description="Full context detected",
            details="Git, PR status, tests, changes, and languages detected"
        )
    elif len(missing) <= 2:
        return Gate(
            gate_id="context_detection",
            status=GateStatus.WARNING,
            description=f"Partial context: missing {', '.join(missing)}",
            details="Some context unavailable, using fallback recommendations"
        )
    else:
        return Gate(
            gate_id="context_detection",
            status=GateStatus.WARNING,
            description=f"Limited context: missing {', '.join(missing)}",
            details="Multiple context sources unavailable"
        )


def evaluate_agent_selection_gate(agents: list[str]) -> Gate:
    """Evaluate the agent selection quality gate.

    Validates that appropriate agents were selected for the review.

    Args:
        agents: List of selected agent names (namespace:agent-name format)

    Returns:
        Gate with evaluation result and details.

    Example:
        >>> agents = ["feature-dev:code-reviewer", "pr-review-toolkit:pr-test-analyzer"]
        >>> gate = evaluate_agent_selection_gate(agents)
        >>> gate.status
        <GateStatus.PASS: 'PASS'>
    """
    if not agents:
        return Gate(
            gate_id="agent_selection",
            status=GateStatus.FAIL,
            description="No agents selected",
            details="Agent selection failed or no suitable agents found"
        )

    # Known valid namespaces
    known_namespaces = {
        "feature-dev",
        "pr-review-toolkit",
        "superpowers",
        "everything-claude-code",
        "production-ready",
        "multi-review",
    }

    unknown_agents = []
    for agent in agents:
        if ":" not in agent:
            unknown_agents.append(agent)
            continue
        namespace = agent.split(":")[0]
        if namespace not in known_namespaces:
            unknown_agents.append(agent)

    if unknown_agents:
        return Gate(
            gate_id="agent_selection",
            status=GateStatus.INCONCLUSIVE,
            description=f"Selected {len(agents)} agents, {len(unknown_agents)} with unknown namespace",
            details=f"Unknown agents: {', '.join(unknown_agents[:3])}"
        )

    return Gate(
        gate_id="agent_selection",
        status=GateStatus.PASS,
        description=f"Selected {len(agents)} agents",
        details=f"Agents: {', '.join(agents[:3])}{'...' if len(agents) > 3 else ''}"
    )


# =============================================================================
# REASON CODE FUNCTIONS
# =============================================================================

def get_reason_codes_for_context(context: Dict[str, Any]) -> Tuple[ReasonCode, ...]:
    """Determine reason codes based on detected context.

    Analyzes the context dictionary and returns appropriate reason codes
    explaining why certain decisions were made.

    Args:
        context: Dictionary containing detected context information.
            Expected keys: change_size, git_available, has_pr, has_tests, languages

    Returns:
        Tuple of applicable reason codes.

    Example:
        >>> context = {"change_size": 25, "git_available": True}
        >>> codes = get_reason_codes_for_context(context)
        >>> ReasonCode.M101_SMALL_CHANGE in codes
        True
    """
    codes: list[ReasonCode] = []

    # Size-based codes
    change_size = context.get("change_size", 0)
    git_available = context.get("git_available", False)

    if not git_available:
        codes.append(ReasonCode.M300_NO_GIT)
    else:
        if change_size < 50:
            codes.append(ReasonCode.M101_SMALL_CHANGE)
        elif change_size <= 500:
            codes.append(ReasonCode.M102_MEDIUM_CHANGE)
        else:
            codes.append(ReasonCode.M103_LARGE_CHANGE)

        # Check for partial context
        has_pr = context.get("has_pr", False)
        has_tests = context.get("has_tests", False)
        languages = context.get("languages", [])

        if not has_pr and not has_tests and not languages:
            codes.append(ReasonCode.M200_PARTIAL_CONTEXT)

    # Default to OK if no other codes
    if not codes:
        codes.append(ReasonCode.M100_OK)

    return tuple(codes)


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def get_current_timestamp() -> str:
    """Get current UTC timestamp in ISO 8601 format."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def create_envelope(
    data: Dict[str, Any],
    gates: GateTuple,
    reason_codes: ReasonCodeTuple,
    warnings: StringTuple = (),
    errors: StringTuple = (),
    schema: str = "https://claude.ai/schemas/measurable/v1"
) -> Envelope:
    """Create an envelope with automatic verdict calculation.

    The verdict is calculated from gates:
    - Any FAIL gate → FAIL verdict
    - Any WARNING gate and no FAIL → WARNING verdict
    - All PASS → PASS verdict

    Args:
        data: The payload data
        gates: Tuple of quality gates
        reason_codes: Tuple of reason codes
        warnings: Optional tuple of warning messages
        errors: Optional tuple of error messages
        schema: Optional custom schema URL

    Returns:
        Envelope with calculated verdict.
    """
    # Calculate verdict from gates
    has_fail = any(g.status == GateStatus.FAIL for g in gates)
    has_warning = any(g.status == GateStatus.WARNING for g in gates)

    if errors or has_fail:
        verdict = GateStatus.FAIL
    elif warnings or has_warning:
        verdict = GateStatus.WARNING
    else:
        verdict = GateStatus.PASS

    return Envelope(
        schema=schema,
        generated_at=get_current_timestamp(),
        verdict=verdict,
        data=data,
        gates=gates,
        reason_codes=reason_codes,
        warnings=warnings,
        errors=errors,
    )
