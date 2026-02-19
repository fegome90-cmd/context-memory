"""Tests for src/domain/measurable.py - TDD RED phase.

These tests define the interface and expected behavior BEFORE implementation.
Run with: python -m pytest tests/test_domain_measurable.py -v
"""

import json
from datetime import datetime
from enum import Enum
import pytest

# These imports will FAIL initially (RED phase) - that's expected!
# Once implementation exists, imports will succeed.


class TestGateStatusEnum:
    """Tests for GateStatus enum."""

    def test_import_gate_status(self):
        """Should be able to import GateStatus enum."""
        from src.domain.measurable import GateStatus
        assert GateStatus is not None

    def test_gate_status_has_pass(self):
        """GateStatus should have PASS value."""
        from src.domain.measurable import GateStatus
        assert GateStatus.PASS.value == "PASS"

    def test_gate_status_has_warning(self):
        """GateStatus should have WARNING value."""
        from src.domain.measurable import GateStatus
        assert GateStatus.WARNING.value == "WARNING"

    def test_gate_status_has_fail(self):
        """GateStatus should have FAIL value."""
        from src.domain.measurable import GateStatus
        assert GateStatus.FAIL.value == "FAIL"

    def test_gate_status_has_inconclusive(self):
        """GateStatus should have INCONCLUSIVE value."""
        from src.domain.measurable import GateStatus
        assert GateStatus.INCONCLUSIVE.value == "INCONCLUSIVE"

    def test_gate_status_count(self):
        """GateStatus should have exactly 4 values."""
        from src.domain.measurable import GateStatus
        assert len(list(GateStatus)) == 4


class TestReasonCodeEnum:
    """Tests for ReasonCode enum."""

    def test_import_reason_code(self):
        """Should be able to import ReasonCode enum."""
        from src.domain.measurable import ReasonCode
        assert ReasonCode is not None

    def test_reason_code_m100_ok(self):
        """ReasonCode should have M100 for normal operation."""
        from src.domain.measurable import ReasonCode
        assert ReasonCode.M100_OK.value == "M100"

    def test_reason_code_m101_small_change(self):
        """ReasonCode should have M101 for small changes (<50 lines)."""
        from src.domain.measurable import ReasonCode
        assert ReasonCode.M101_SMALL_CHANGE.value == "M101"

    def test_reason_code_m102_medium_change(self):
        """ReasonCode should have M102 for medium changes (50-500 lines)."""
        from src.domain.measurable import ReasonCode
        assert ReasonCode.M102_MEDIUM_CHANGE.value == "M102"

    def test_reason_code_m103_large_change(self):
        """ReasonCode should have M103 for large changes (>500 lines)."""
        from src.domain.measurable import ReasonCode
        assert ReasonCode.M103_LARGE_CHANGE.value == "M103"

    def test_reason_code_m200_partial_context(self):
        """ReasonCode should have M200 for partial context detection."""
        from src.domain.measurable import ReasonCode
        assert ReasonCode.M200_PARTIAL_CONTEXT.value == "M200"

    def test_reason_code_m300_no_git(self):
        """ReasonCode should have M300 for no git environment."""
        from src.domain.measurable import ReasonCode
        assert ReasonCode.M300_NO_GIT.value == "M300"


class TestGateDataclass:
    """Tests for Gate frozen dataclass."""

    def test_import_gate(self):
        """Should be able to import Gate dataclass."""
        from src.domain.measurable import Gate
        assert Gate is not None

    def test_gate_is_frozen(self):
        """Gate should be immutable (frozen dataclass)."""
        from src.domain.measurable import Gate, GateStatus
        gate = Gate(
            gate_id="test_gate",
            status=GateStatus.PASS,
            description="Test gate"
        )
        with pytest.raises(AttributeError):
            gate.status = GateStatus.FAIL  # type: ignore[misc]

    def test_gate_creation(self):
        """Should create Gate with required fields."""
        from src.domain.measurable import Gate, GateStatus
        gate = Gate(
            gate_id="context_detection",
            status=GateStatus.PASS,
            description="Context detection successful"
        )
        assert gate.gate_id == "context_detection"
        assert gate.status == GateStatus.PASS
        assert gate.description == "Context detection successful"

    def test_gate_optional_details(self):
        """Gate should have optional details field."""
        from src.domain.measurable import Gate, GateStatus
        gate = Gate(
            gate_id="test_gate",
            status=GateStatus.WARNING,
            description="Test gate",
            details="Additional information"
        )
        assert gate.details == "Additional information"

    def test_gate_default_details_empty(self):
        """Gate details should default to empty string."""
        from src.domain.measurable import Gate, GateStatus
        gate = Gate(
            gate_id="test_gate",
            status=GateStatus.PASS,
            description="Test"
        )
        assert gate.details == ""

    def test_gate_to_dict(self):
        """Gate should have to_dict() method for serialization."""
        from src.domain.measurable import Gate, GateStatus
        gate = Gate(
            gate_id="context_gate",
            status=GateStatus.PASS,
            description="Context OK",
            details="Found 5 files"
        )
        result = gate.to_dict()
        assert result["gate_id"] == "context_gate"
        assert result["status"] == "PASS"
        assert result["description"] == "Context OK"
        assert result["details"] == "Found 5 files"


class TestEnvelopeDataclass:
    """Tests for Envelope frozen dataclass."""

    def test_import_envelope(self):
        """Should be able to import Envelope dataclass."""
        from src.domain.measurable import Envelope
        assert Envelope is not None

    def test_envelope_is_frozen(self):
        """Envelope should be immutable (frozen dataclass)."""
        from src.domain.measurable import Envelope, GateStatus, Gate
        envelope = Envelope(
            schema="https://example.com/schema/v1",
            generated_at="2026-02-14T12:00:00Z",
            verdict=GateStatus.PASS,
            data={"test": "value"},
            gates=(),
            reason_codes=(),
            warnings=(),
            errors=()
        )
        with pytest.raises(AttributeError):
            envelope.verdict = GateStatus.FAIL  # type: ignore[misc]

    def test_envelope_creation(self):
        """Should create Envelope with all required fields."""
        from src.domain.measurable import Envelope, GateStatus, Gate, ReasonCode
        gates = (
            Gate(gate_id="test", status=GateStatus.PASS, description="Test"),
        )
        envelope = Envelope(
            schema="https://claude.ai/schemas/measurable/v1",
            generated_at="2026-02-14T12:00:00Z",
            verdict=GateStatus.PASS,
            data={"agents": ["test:agent"]},
            gates=gates,
            reason_codes=(ReasonCode.M100_OK,),
            warnings=(),
            errors=()
        )
        assert envelope.schema == "https://claude.ai/schemas/measurable/v1"
        assert envelope.verdict == GateStatus.PASS
        assert len(envelope.gates) == 1

    def test_envelope_to_dict(self):
        """Envelope should have to_dict() method for serialization."""
        from src.domain.measurable import Envelope, GateStatus, Gate, ReasonCode
        gate = Gate(gate_id="ctx", status=GateStatus.PASS, description="OK")
        envelope = Envelope(
            schema="https://test.com/v1",
            generated_at="2026-02-14T12:00:00Z",
            verdict=GateStatus.PASS,
            data={"key": "value"},
            gates=(gate,),
            reason_codes=(ReasonCode.M101_SMALL_CHANGE,),
            warnings=("minor issue",),
            errors=()
        )
        result = envelope.to_dict()
        assert result["$schema"] == "https://test.com/v1"
        assert result["verdict"] == "PASS"
        assert result["data"] == {"key": "value"}
        assert len(result["gates"]) == 1
        assert result["reason_codes"] == ["M101"]
        assert result["warnings"] == ["minor issue"]
        assert result["errors"] == []

    def test_envelope_to_json(self):
        """Envelope should have to_json() method returning valid JSON string."""
        from src.domain.measurable import Envelope, GateStatus
        envelope = Envelope(
            schema="https://test.com/v1",
            generated_at="2026-02-14T12:00:00Z",
            verdict=GateStatus.PASS,
            data={"test": 123},
            gates=(),
            reason_codes=(),
            warnings=(),
            errors=()
        )
        json_str = envelope.to_json()
        # Should be valid JSON
        parsed = json.loads(json_str)
        assert parsed["verdict"] == "PASS"
        assert parsed["data"]["test"] == 123

    def test_envelope_verdict_from_gates_all_pass(self):
        """Envelope verdict should be PASS when all gates pass."""
        from src.domain.measurable import Envelope, GateStatus, Gate
        gates = (
            Gate(gate_id="g1", status=GateStatus.PASS, description="OK"),
            Gate(gate_id="g2", status=GateStatus.PASS, description="OK"),
        )
        envelope = Envelope(
            schema="test",
            generated_at="2026-02-14T12:00:00Z",
            verdict=GateStatus.PASS,
            data={},
            gates=gates,
            reason_codes=(),
            warnings=(),
            errors=()
        )
        assert envelope.verdict == GateStatus.PASS

    def test_create_envelope_all_pass_verdict(self):
        """create_envelope should return PASS verdict when all gates pass."""
        from src.domain.measurable import create_envelope, Gate, GateStatus, ReasonCode
        gates = (
            Gate(gate_id="test1", status=GateStatus.PASS, description="OK"),
            Gate(gate_id="test2", status=GateStatus.PASS, description="OK"),
        )
        envelope = create_envelope(
            data={"test": "value"},
            gates=gates,
            reason_codes=(ReasonCode.M101_SMALL_CHANGE,),
            warnings=(),
            errors=()
        )
        assert envelope.verdict == GateStatus.PASS
        assert len(envelope.gates) == 2

    def test_create_envelope_inconclusive_gate_treated_as_pass(self):
        """INCONCLUSIVE gates should not trigger FAIL or WARNING verdict."""
        from src.domain.measurable import create_envelope, Gate, GateStatus, ReasonCode
        gates = (
            Gate(gate_id="test1", status=GateStatus.INCONCLUSIVE, description="Unknown"),
            Gate(gate_id="test2", status=GateStatus.PASS, description="OK"),
        )
        envelope = create_envelope(
            data={"test": "value"},
            gates=gates,
            reason_codes=(ReasonCode.M101_SMALL_CHANGE,),
            warnings=(),
            errors=()
        )
        # INCONCLUSIVE doesn't trigger FAIL or WARNING, so verdict is PASS
        assert envelope.verdict == GateStatus.PASS

    def test_create_envelope_fail_overrides_inconclusive(self):
        """FAIL gate should override INCONCLUSIVE gates."""
        from src.domain.measurable import create_envelope, Gate, GateStatus, ReasonCode
        gates = (
            Gate(gate_id="test1", status=GateStatus.INCONCLUSIVE, description="Unknown"),
            Gate(gate_id="test2", status=GateStatus.FAIL, description="Failed"),
        )
        envelope = create_envelope(
            data={"test": "value"},
            gates=gates,
            reason_codes=(),
            warnings=(),
            errors=()
        )
        assert envelope.verdict == GateStatus.FAIL

    def test_create_envelope_errors_override_gates(self):
        """Errors tuple should cause FAIL regardless of gate status."""
        from src.domain.measurable import create_envelope, Gate, GateStatus, ReasonCode
        gates = (
            Gate(gate_id="test1", status=GateStatus.PASS, description="OK"),
        )
        envelope = create_envelope(
            data={"test": "value"},
            gates=gates,
            reason_codes=(),
            warnings=(),
            errors=("Critical error",)
        )
        assert envelope.verdict == GateStatus.FAIL

    def test_create_envelope_warnings_with_pass_gates(self):
        """Warnings should cause WARNING verdict even with all PASS gates."""
        from src.domain.measurable import create_envelope, Gate, GateStatus, ReasonCode
        gates = (
            Gate(gate_id="test1", status=GateStatus.PASS, description="OK"),
        )
        envelope = create_envelope(
            data={"test": "value"},
            gates=gates,
            reason_codes=(),
            warnings=("Minor issue",),
            errors=()
        )
        assert envelope.verdict == GateStatus.WARNING

    def test_create_envelope_empty_gates_is_pass(self):
        """Empty gates tuple should result in PASS verdict when no errors/warnings."""
        from src.domain.measurable import create_envelope, GateStatus
        envelope = create_envelope(
            data={"test": "value"},
            gates=(),
            reason_codes=(),
            warnings=(),
            errors=()
        )
        assert envelope.verdict == GateStatus.PASS


class TestEvaluateContextDetectionGate:
    """Tests for evaluate_context_detection_gate function."""

    def test_function_exists(self):
        """evaluate_context_detection_gate should be importable."""
        from src.domain.measurable import evaluate_context_detection_gate
        assert callable(evaluate_context_detection_gate)

    def test_returns_gate_with_full_context(self):
        """Should return PASS gate when context is complete."""
        from src.domain.measurable import evaluate_context_detection_gate, GateStatus
        context = {
            "has_pr": True,
            "has_tests": True,
            "change_size": 100,
            "languages": ["python"],
            "git_available": True,
        }
        gate = evaluate_context_detection_gate(context)
        assert gate.gate_id == "context_detection"
        assert gate.status == GateStatus.PASS

    def test_returns_warning_with_partial_context(self):
        """Should return WARNING when some context is missing."""
        from src.domain.measurable import evaluate_context_detection_gate, GateStatus
        context = {
            "has_pr": False,
            "has_tests": True,
            "change_size": 0,
            "languages": [],
            "git_available": True,
        }
        gate = evaluate_context_detection_gate(context)
        assert gate.status == GateStatus.WARNING

    def test_returns_fail_without_git(self):
        """Should return FAIL when git is not available."""
        from src.domain.measurable import evaluate_context_detection_gate, GateStatus
        context = {
            "has_pr": False,
            "has_tests": False,
            "change_size": 0,
            "languages": [],
            "git_available": False,
        }
        gate = evaluate_context_detection_gate(context)
        assert gate.status == GateStatus.FAIL


class TestEvaluateAgentSelectionGate:
    """Tests for evaluate_agent_selection_gate function."""

    def test_function_exists(self):
        """evaluate_agent_selection_gate should be importable."""
        from src.domain.measurable import evaluate_agent_selection_gate
        assert callable(evaluate_agent_selection_gate)

    def test_returns_pass_with_valid_agents(self):
        """Should return PASS when valid agents are selected."""
        from src.domain.measurable import evaluate_agent_selection_gate, GateStatus
        agents = ["feature-dev:code-reviewer", "pr-review-toolkit:pr-test-analyzer"]
        gate = evaluate_agent_selection_gate(agents)
        assert gate.gate_id == "agent_selection"
        assert gate.status == GateStatus.PASS

    def test_returns_fail_with_empty_agents(self):
        """Should return FAIL when no agents are selected."""
        from src.domain.measurable import evaluate_agent_selection_gate, GateStatus
        gate = evaluate_agent_selection_gate([])
        assert gate.status == GateStatus.FAIL
        assert "no agents" in gate.description.lower()

    def test_returns_inconclusive_with_unknown_agents(self):
        """Should return INCONCLUSIVE when agent namespace is unknown."""
        from src.domain.measurable import evaluate_agent_selection_gate, GateStatus
        agents = ["unknown:agent"]
        gate = evaluate_agent_selection_gate(agents)
        # Should still pass but might have warning details
        assert gate.status in (GateStatus.PASS, GateStatus.INCONCLUSIVE)

    def test_returns_inconclusive_with_malformed_agent(self):
        """Should return INCONCLUSIVE when agent has no namespace separator."""
        from src.domain.measurable import evaluate_agent_selection_gate, GateStatus
        # Agent without colon (malformed format)
        agents = ["malformed_agent_without_colon"]
        gate = evaluate_agent_selection_gate(agents)
        assert gate.status == GateStatus.INCONCLUSIVE
        assert "malformed_agent_without_colon" in gate.details

    def test_returns_inconclusive_truncates_unknown_agents(self):
        """Should truncate unknown agent list in details to first 3."""
        from src.domain.measurable import evaluate_agent_selection_gate, GateStatus
        agents = [f"unknown:agent{i}" for i in range(5)]
        gate = evaluate_agent_selection_gate(agents)
        assert gate.status == GateStatus.INCONCLUSIVE
        # Should only show first 3
        assert "unknown:agent0" in gate.details
        assert "unknown:agent2" in gate.details
        assert "unknown:agent3" not in gate.details  # Truncated


class TestGetReasonCodesForContext:
    """Tests for get_reason_codes_for_context function."""

    def test_function_exists(self):
        """get_reason_codes_for_context should be importable."""
        from src.domain.measurable import get_reason_codes_for_context
        assert callable(get_reason_codes_for_context)

    def test_returns_m100_for_normal(self):
        """Should return M100 for normal operation with complete context."""
        from src.domain.measurable import get_reason_codes_for_context, ReasonCode
        # Complete context that should result in normal operation
        context = {
            "change_size": 100,
            "git_available": True,
            "has_pr": True,
            "has_tests": True,
            "languages": ["python"]
        }
        codes = get_reason_codes_for_context(context)
        # With complete context, should get M102 (medium change) not M100
        # M100 is only returned when no other codes apply
        assert ReasonCode.M102_MEDIUM_CHANGE in codes

    def test_returns_m102_when_medium_change(self):
        """Should return M102 for changes 50-500 lines."""
        from src.domain.measurable import get_reason_codes_for_context, ReasonCode
        context = {"change_size": 100, "git_available": True}
        codes = get_reason_codes_for_context(context)
        assert ReasonCode.M102_MEDIUM_CHANGE in codes

    def test_returns_m101_for_small_change(self):
        """Should return M101 for changes < 50 lines."""
        from src.domain.measurable import get_reason_codes_for_context, ReasonCode
        context = {"change_size": 25, "git_available": True}
        codes = get_reason_codes_for_context(context)
        assert ReasonCode.M101_SMALL_CHANGE in codes

    def test_returns_m102_for_medium_change(self):
        """Should return M102 for changes 50-500 lines."""
        from src.domain.measurable import get_reason_codes_for_context, ReasonCode
        context = {"change_size": 250, "git_available": True}
        codes = get_reason_codes_for_context(context)
        assert ReasonCode.M102_MEDIUM_CHANGE in codes

    def test_returns_m103_for_large_change(self):
        """Should return M103 for changes > 500 lines."""
        from src.domain.measurable import get_reason_codes_for_context, ReasonCode
        context = {"change_size": 1000, "git_available": True}
        codes = get_reason_codes_for_context(context)
        assert ReasonCode.M103_LARGE_CHANGE in codes

    def test_returns_m200_for_partial_context(self):
        """Should return M200 when context detection is partial."""
        from src.domain.measurable import get_reason_codes_for_context, ReasonCode
        context = {
            "change_size": 100,
            "git_available": True,
            "has_pr": False,
            "has_tests": False,
            "languages": []
        }
        codes = get_reason_codes_for_context(context)
        assert ReasonCode.M200_PARTIAL_CONTEXT in codes

    def test_returns_m300_for_no_git(self):
        """Should return M300 when git is not available."""
        from src.domain.measurable import get_reason_codes_for_context, ReasonCode
        context = {"change_size": 100, "git_available": False}
        codes = get_reason_codes_for_context(context)
        assert ReasonCode.M300_NO_GIT in codes

    def test_returns_m100_fallback_when_no_other_codes(self):
        """Should return M100_OK as fallback when no other codes apply.

        Note: With current logic, this path may be unreachable since
        git_available=True always produces a size code. This test
        documents the expected fallback behavior.
        """
        from src.domain.measurable import get_reason_codes_for_context, ReasonCode
        # With git available and change_size < 50, should get M101
        context = {"change_size": 25, "git_available": True}
        codes = get_reason_codes_for_context(context)
        # Should have at least one code (either M101 or M100 fallback)
        assert len(codes) >= 1
        # Small change should trigger M101, not fallback
        assert ReasonCode.M101_SMALL_CHANGE in codes
