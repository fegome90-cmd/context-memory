"""Configurable logging for context-memory plugin.

This module provides a simple logging system that can be enabled via
environment variable CM_DEBUG=1. When disabled, all logging calls are no-ops
with zero overhead.

Usage:
    from infrastructure.logging import get_logger

    logger = get_logger(__name__)
    logger.debug("Hook called with input:", input_data)
    logger.warning("Git not found - context-memory disabled")
"""
import logging
import os
import sys
from pathlib import Path
from typing import Any

# Global flag - checked once at module load
_DEBUG_ENABLED = os.environ.get("CM_DEBUG", "0") == "1"


class _NullLogger:
    """No-op logger used when CM_DEBUG=0 (default).

    Errors and warnings are still printed to stderr for production visibility.
    """

    def __init__(self, name: str):
        self._name = name

    def debug(self, msg: str, *args: Any, **kwargs: Any) -> None:
        """No-op debug log."""
        pass

    def info(self, msg: str, *args: Any, **kwargs: Any) -> None:
        """No-op info log."""
        pass

    def warning(self, msg: str, *args: Any, **kwargs: Any) -> None:
        """Print warnings to stderr for production visibility."""
        import sys
        print(f"[WARNING] {self._name}: {msg}", file=sys.stderr, flush=True)

    def error(self, msg: str, *args: Any, **kwargs: Any) -> None:
        """Print errors to stderr for production visibility."""
        import sys
        print(f"[ERROR] {self._name}: {msg}", file=sys.stderr, flush=True)

    def exception(self, msg: str, *args: Any, **kwargs: Any) -> None:
        """Print exceptions to stderr for production visibility."""
        import sys
        print(f"[ERROR] {self._name}: {msg}", file=sys.stderr, flush=True)

    def critical(self, msg: str, *args: Any, **kwargs: Any) -> None:
        """Print critical errors to stderr for production visibility."""
        import sys
        print(f"[CRITICAL] {self._name}: {msg}", file=sys.stderr, flush=True)


_loggers: dict[str, logging.Logger | _NullLogger] = {}


def get_logger(name: str) -> logging.Logger | _NullLogger:
    """
    Get a logger instance.

    Returns a real logger if CM_DEBUG=1, otherwise a no-op logger.

    Args:
        name: Logger name (typically __name__ from calling module)

    Returns:
        Logger instance (real or null)
    """
    if name in _loggers:
        return _loggers[name]

    if not _DEBUG_ENABLED:
        _loggers[name] = _NullLogger(name)
        return _loggers[name]

    # Configure logging on first use
    if not logging.getLogger().handlers:
        log_file = Path("/tmp") / "cm_hook_debug.log"

        try:
            logging.basicConfig(
                level=logging.DEBUG,
                filename=str(log_file),
                format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                filemode='a'  # Append mode
            )
        except (OSError, IOError) as e:
            # If we can't create log file, fall back to stderr
            logging.basicConfig(
                level=logging.DEBUG,
                stream=sys.stderr,
                format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
            )

    logger = logging.getLogger(name)
    _loggers[name] = logger
    return logger


def is_debug_enabled() -> bool:
    """Check if debug logging is enabled."""
    return _DEBUG_ENABLED
