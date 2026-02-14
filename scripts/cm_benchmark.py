#!/usr/bin/env python3
"""
Benchmark harness for cm_multi_review.py operations.

Measures performance of agent suggestion operations to detect regressions
and ensure acceptable response times.

Usage:
    python3 cm_benchmark.py --quick           # 10 iterations
    python3 cm_benchmark.py --iterations 50   # Custom iterations
    python3 cm_benchmark.py --quick --json    # JSON output

Performance Targets:
    - P95 < 200ms for suggest operation
    - P99 < 500ms for suggest operation
"""

import argparse
import json
import statistics
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Tuple


# =============================================================================
# DATA CLASSES
# =============================================================================

@dataclass(frozen=True)
class BenchmarkResult:
    """Result of a single benchmark iteration.

    Attributes:
        iteration: Iteration number (1-indexed)
        duration_ms: Duration in milliseconds
        success: Whether the operation succeeded
        error: Error message if failed, empty string otherwise
    """
    iteration: int
    duration_ms: float
    success: bool
    error: str = ""


@dataclass(frozen=True)
class BenchmarkReport:
    """Aggregated benchmark statistics.

    Attributes:
        total_iterations: Total iterations run
        successful_iterations: Number of successful iterations
        failed_iterations: Number of failed iterations
        min_ms: Minimum duration in milliseconds
        max_ms: Maximum duration in milliseconds
        mean_ms: Mean duration in milliseconds
        median_ms: Median duration in milliseconds
        p95_ms: 95th percentile duration in milliseconds
        p99_ms: 99th percentile duration in milliseconds
        results: Tuple of individual results
    """
    total_iterations: int
    successful_iterations: int
    failed_iterations: int
    min_ms: float
    max_ms: float
    mean_ms: float
    median_ms: float
    p95_ms: float
    p99_ms: float
    results: Tuple[BenchmarkResult, ...]

    def to_dict(self) -> dict:
        """Convert report to dictionary for serialization.

        Returns None for unavailable statistics instead of sentinel -1.0 values.
        """
        # Check if stats are available (non-negative sentinel check)
        stats_available = self.min_ms >= 0

        return {
            "total_iterations": self.total_iterations,
            "successful_iterations": self.successful_iterations,
            "failed_iterations": self.failed_iterations,
            "min_ms": round(self.min_ms, 2) if stats_available else None,
            "max_ms": round(self.max_ms, 2) if stats_available else None,
            "mean_ms": round(self.mean_ms, 2) if stats_available else None,
            "median_ms": round(self.median_ms, 2) if stats_available else None,
            "p95_ms": round(self.p95_ms, 2) if stats_available else None,
            "p99_ms": round(self.p99_ms, 2) if stats_available else None,
        }

    def to_json(self) -> str:
        """Convert report to JSON string."""
        return json.dumps(self.to_dict(), indent=2)


# =============================================================================
# BENCHMARK FUNCTIONS
# =============================================================================

def _percentile(data: list[float], p: float) -> float:
    """Calculate percentile without numpy.

    Args:
        data: List of values
        p: Percentile (0-100)

    Returns:
        The percentile value.
    """
    if not data:
        return 0.0
    sorted_data = sorted(data)
    k = (len(sorted_data) - 1) * p / 100
    f = int(k)
    c = f + 1
    if c >= len(sorted_data):
        return sorted_data[-1]
    return sorted_data[f] + (k - f) * (sorted_data[c] - sorted_data[f])


# Maximum length for error messages (longer messages are truncated)
_MAX_ERROR_LENGTH = 200


def _truncate_error(message: str, max_len: int = _MAX_ERROR_LENGTH) -> str:
    """Truncate error message with ellipsis if too long.

    Args:
        message: Error message to truncate
        max_len: Maximum length (default: 200)

    Returns:
        Truncated message with "..." if needed, otherwise original.
    """
    if len(message) <= max_len:
        return message
    # Reserve 3 chars for ellipsis
    return message[:max_len - 3] + "..."


def run_benchmarks(iterations: int = 10) -> BenchmarkReport:
    """Run benchmark iterations for the suggest operation.

    Args:
        iterations: Number of iterations to run (default: 10)

    Returns:
        BenchmarkReport with aggregated statistics.
    """
    plugin_root = Path(__file__).parent.parent
    script_path = plugin_root / "scripts" / "cm_multi_review.py"

    results: list[BenchmarkResult] = []
    durations: list[float] = []

    for i in range(iterations):
        start_time = time.perf_counter()

        try:
            result = subprocess.run(
                ["python3", str(script_path), "--suggest", "--json"],
                capture_output=True,
                text=True,
                timeout=30,
                cwd=str(plugin_root)
            )

            end_time = time.perf_counter()
            duration_ms = (end_time - start_time) * 1000

            success = result.returncode == 0
            error = "" if success else _truncate_error(result.stderr)

            benchmark_result = BenchmarkResult(
                iteration=i + 1,
                duration_ms=duration_ms,
                success=success,
                error=error
            )

            if success:
                durations.append(duration_ms)

        except subprocess.TimeoutExpired:
            benchmark_result = BenchmarkResult(
                iteration=i + 1,
                duration_ms=30000.0,  # 30 second timeout
                success=False,
                error="Operation timed out after 30 seconds"
            )
        except Exception as e:
            benchmark_result = BenchmarkResult(
                iteration=i + 1,
                duration_ms=0.0,
                success=False,
                error=_truncate_error(str(e))
            )

        results.append(benchmark_result)

    # Calculate statistics
    successful = [r for r in results if r.success]
    failed = [r for r in results if not r.success]

    if durations:
        stats = {
            "min_ms": min(durations),
            "max_ms": max(durations),
            "mean_ms": statistics.mean(durations),
            "median_ms": statistics.median(durations),
            "p95_ms": _percentile(durations, 95),
            "p99_ms": _percentile(durations, 99),
        }
    else:
        # Use sentinel value -1.0 to indicate unavailable statistics
        # This prevents misleading 0.0ms displays when all benchmarks failed
        stats = {
            "min_ms": -1.0,
            "max_ms": -1.0,
            "mean_ms": -1.0,
            "median_ms": -1.0,
            "p95_ms": -1.0,
            "p99_ms": -1.0,
        }

    return BenchmarkReport(
        total_iterations=iterations,
        successful_iterations=len(successful),
        failed_iterations=len(failed),
        results=tuple(results),
        **stats
    )


def _format_stat(value_ms: float) -> str:
    """Format a timing statistic, handling unavailable data.

    Args:
        value_ms: Value in milliseconds, or -1.0 for unavailable.

    Returns:
        Formatted string (e.g., "123.45ms" or "N/A").
    """
    if value_ms < 0:
        return "N/A"
    return f"{value_ms:.2f}ms"


def format_report(report: BenchmarkReport) -> str:
    """Format report for human-readable output.

    Args:
        report: BenchmarkReport to format

    Returns:
        Formatted string for display.
    """
    lines = [
        "=" * 50,
        "BENCHMARK RESULTS",
        "=" * 50,
        "",
        f"Total iterations:     {report.total_iterations}",
        f"Successful:           {report.successful_iterations}",
        f"Failed:               {report.failed_iterations}",
        "",
        "Timing Statistics:",
        f"  Min:                {_format_stat(report.min_ms)}",
        f"  Max:                {_format_stat(report.max_ms)}",
        f"  Mean:               {_format_stat(report.mean_ms)}",
        f"  Median:             {_format_stat(report.median_ms)}",
        f"  P95:                {_format_stat(report.p95_ms)}",
        f"  P99:                {_format_stat(report.p99_ms)}",
        "",
    ]

    # Performance assessment - skip if no data available
    if report.p95_ms < 0:
        lines.append("❌ All benchmarks failed - no timing data available")
    elif report.p95_ms < 200:
        lines.append("✅ P95 < 200ms - Performance target met!")
    elif report.p95_ms < 500:
        lines.append("⚠️  P95 between 200-500ms - Acceptable but could improve")
    else:
        lines.append("❌ P95 > 500ms - Performance regression detected!")

    return "\n".join(lines)


# =============================================================================
# MAIN ENTRY POINT
# =============================================================================

def main() -> None:
    """Main entry point for benchmark CLI."""
    parser = argparse.ArgumentParser(
        description="Benchmark harness for cm_multi_review.py",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s --quick              # Quick benchmark (10 iterations)
  %(prog)s --iterations 50      # Run 50 iterations
  %(prog)s --quick --json       # JSON output

Performance Targets:
  P95 < 200ms  (good)
  P95 < 500ms  (acceptable)
        """
    )

    parser.add_argument(
        "--quick",
        action="store_true",
        help="Run quick benchmark (10 iterations)"
    )
    parser.add_argument(
        "--iterations",
        type=int,
        default=10,
        help="Number of iterations to run (default: 10)"
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output results as JSON"
    )

    args = parser.parse_args()

    iterations = args.iterations
    if args.quick:
        iterations = 10

    print(f"Running {iterations} benchmark iterations...", file=sys.stderr)
    report = run_benchmarks(iterations=iterations)

    if args.json:
        print(report.to_json())
    else:
        print(format_report(report))


if __name__ == "__main__":
    main()
