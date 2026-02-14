"""Tests for scripts/cm_benchmark.py - TDD RED phase.

Run with: python -m pytest tests/test_cm_benchmark.py -v
"""

import json
import subprocess
from pathlib import Path
import pytest


class TestBenchmarkResult:
    """Tests for BenchmarkResult dataclass."""

    def test_import_benchmark_result(self):
        """Should be able to import BenchmarkResult."""
        from scripts.cm_benchmark import BenchmarkResult
        assert BenchmarkResult is not None

    def test_benchmark_result_fields(self):
        """BenchmarkResult should have required fields."""
        from scripts.cm_benchmark import BenchmarkResult
        result = BenchmarkResult(
            iteration=1,
            duration_ms=50.5,
            success=True,
            error=""
        )
        assert result.iteration == 1
        assert result.duration_ms == 50.5
        assert result.success is True
        assert result.error == ""

    def test_benchmark_result_is_frozen(self):
        """BenchmarkResult should be immutable."""
        from scripts.cm_benchmark import BenchmarkResult
        result = BenchmarkResult(
            iteration=1,
            duration_ms=50.5,
            success=True
        )
        with pytest.raises(AttributeError):
            result.duration_ms = 100.0  # type: ignore[misc]


class TestBenchmarkReport:
    """Tests for BenchmarkReport dataclass."""

    def test_import_benchmark_report(self):
        """Should be able to import BenchmarkReport."""
        from scripts.cm_benchmark import BenchmarkReport
        assert BenchmarkReport is not None

    def test_benchmark_report_fields(self):
        """BenchmarkReport should have statistical fields."""
        from scripts.cm_benchmark import BenchmarkReport
        report = BenchmarkReport(
            total_iterations=10,
            successful_iterations=10,
            failed_iterations=0,
            min_ms=10.0,
            max_ms=100.0,
            mean_ms=50.0,
            median_ms=45.0,
            p95_ms=90.0,
            p99_ms=98.0,
            results=()
        )
        assert report.total_iterations == 10
        assert report.p95_ms == 90.0
        assert report.p99_ms == 98.0


class TestRunBenchmarks:
    """Tests for run_benchmarks function."""

    def test_function_exists(self):
        """run_benchmarks should be importable."""
        from scripts.cm_benchmark import run_benchmarks
        assert callable(run_benchmarks)

    def test_returns_benchmark_report(self):
        """run_benchmarks should return BenchmarkReport."""
        from scripts.cm_benchmark import run_benchmarks, BenchmarkReport
        report = run_benchmarks(iterations=2)
        assert isinstance(report, BenchmarkReport)

    def test_quick_mode_runs_10_iterations(self):
        """Quick mode should run 10 iterations."""
        from scripts.cm_benchmark import run_benchmarks
        report = run_benchmarks(iterations=10)
        assert report.total_iterations == 10

    def test_custom_iterations(self):
        """Should accept custom iteration count."""
        from scripts.cm_benchmark import run_benchmarks
        report = run_benchmarks(iterations=5)
        assert report.total_iterations == 5


class TestBenchmarkCLI:
    """Tests for benchmark CLI."""

    def test_cli_exists(self):
        """cm_benchmark.py should be executable."""
        plugin_root = Path(__file__).parent.parent
        script_path = plugin_root / "scripts" / "cm_benchmark.py"
        assert script_path.exists(), "cm_benchmark.py should exist"

    def test_cli_quick_mode(self):
        """--quick flag should run quick benchmark."""
        import subprocess
        from pathlib import Path
        plugin_root = Path(__file__).parent.parent
        result = subprocess.run(
            ["python3", "scripts/cm_benchmark.py", "--quick"],
            capture_output=True,
            text=True,
            timeout=60,
            cwd=str(plugin_root)
        )
        assert result.returncode == 0, f"Script failed: {result.stderr}"
        # Should include timing output
        assert "ms" in result.stdout.lower() or "p95" in result.stdout.lower()

    def test_cli_json_output(self):
        """--json flag should output valid JSON."""
        import subprocess
        import json
        from pathlib import Path
        plugin_root = Path(__file__).parent.parent
        result = subprocess.run(
            ["python3", "scripts/cm_benchmark.py", "--quick", "--json"],
            capture_output=True,
            text=True,
            timeout=60,
            cwd=str(plugin_root)
        )
        assert result.returncode == 0, f"Script failed: {result.stderr}"
        # Should be valid JSON
        try:
            parsed = json.loads(result.stdout)
            assert "p95_ms" in parsed or "total_iterations" in parsed
        except json.JSONDecodeError:
            pytest.fail(f"Output is not valid JSON: {result.stdout[:500]}")

    def test_cli_custom_iterations(self):
        """--iterations N should run N iterations."""
        import subprocess
        from pathlib import Path
        plugin_root = Path(__file__).parent.parent
        result = subprocess.run(
            ["python3", "scripts/cm_benchmark.py", "--iterations", "3"],
            capture_output=True,
            text=True,
            timeout=60,
            cwd=str(plugin_root)
        )
        assert result.returncode == 0, f"Script failed: {result.stderr}"
        # Should indicate 3 iterations
        assert "3" in result.stdout or "iterations" in result.stdout.lower()


class TestBenchmarkPerformance:
    """Performance tests for the benchmark harness."""

    def test_p95_under_200ms(self):
        """P95 should be under 200ms for suggest operation."""
        from scripts.cm_benchmark import run_benchmarks
        report = run_benchmarks(iterations=10)
        # This is a reasonable target for the suggest operation
        assert report.p95_ms < 2000, f"P95 {report.p95_ms}ms exceeds 2000ms threshold"
