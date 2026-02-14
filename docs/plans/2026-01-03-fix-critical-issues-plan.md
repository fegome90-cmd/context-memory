# Context-Memory Plugin: Fix Critical Issues Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Address the critical issues preventing the plugin from working, following a layered approach from invocation to logic.

**Architecture Diagnosis:** The plugin has **TWO independent problems**:
1. **Layer 1 (Invocation)**: Hook may not execute due to absolute path vs `${CLAUDE_PLUGIN_ROOT}`
2. **Layer 2 (Logic)**: Hook uses environment variables that may not exist instead of reading stdin

**Tech Stack:** Python 3.10+, pytest, Claude Code Plugin System

**Priority Order:**
0. **CRITICAL: Fix hook invocation** (absolute path → `${CLAUDE_PLUGIN_ROOT}`)
1. **CRITICAL: Fix hook logic** (environment variables → stdin)
2. **Week 1:** Fix failing tests (unblock CI/CD)
3. **Week 2:** Add debug logging (improve debuggability)
4. **Week 3:** Implement health check command (diagnostics)

---

## ⚠️ CRITICAL: Task 0 - Fix Hook Invocation (Layer 1)

**Context:** Local plugins may be blocked from executing if hooks.json uses absolute paths. Claude Code expands `${CLAUDE_PLUGIN_ROOT}` at runtime for security.

**Files:**
- Modify: `hooks/hooks.json`

**Step 1: Read current hooks.json**

Run: `cat hooks/hooks.json`

Expected output:
```json
{
  "description": "Context Memory Plugin - Track Read/Write/Edit/MultiEdit operations",
  "hooks": {
    "PostToolUse": [
      {
        "matcher": "Read|Write|Edit|MultiEdit",
        "hooks": [
          {
            "type": "command",
            "command": "python3 /Users/felipe_gonzalez/.claude/plugins/context-memory/scripts/cm_track_operation.py",
            "timeout": 5
          }
        ]
      }
    ]
  }
}
```

**Step 2: Replace absolute path with ${CLAUDE_PLUGIN_ROOT}**

Modify: `hooks/hooks.json:10`

```json
{
  "description": "Context Memory Plugin - Track Read/Write/Edit/MultiEdit operations",
  "hooks": {
    "PostToolUse": [
      {
        "matcher": "Read|Write|Edit|MultiEdit",
        "hooks": [
          {
            "type": "command",
            "command": "python3 ${CLAUDE_PLUGIN_ROOT}/scripts/cm_track_operation.py",
            "timeout": 5
          }
        ]
      }
    ]
  }
}
```

**Step 3: Verify the change**

Run: `cat hooks/hooks.json | grep CLAUDE_PLUGIN_ROOT`

Expected: Shows the new command with `${CLAUDE_PLUGIN_ROOT}`

**Step 4: Update plugin registration to force reload**

Modify: `~/.claude/plugins/installed_plugins.json`

Find the `"context-memory@local"` entry and update `"lastUpdated"` to current timestamp:

```json
"lastUpdated": "2026-01-03T12:00:00.000Z"
```

**Step 5: Commit hooks.json change**

```bash
git add hooks/hooks.json
git commit -m "fix: use CLAUDE_PLUGIN_ROOT in hook command path

Local plugins must use \${CLAUDE_PLUGIN_ROOT} instead of absolute paths.
Claude Code expands this variable at runtime. Absolute paths may be
blocked for security reasons.

Ref: https://github.com/anthropics/claude-code/issues/[TBD]"
```

---

## ⚠️ CRITICAL: Task 1 - Fix Hook Logic (Layer 2)

**Context:** Even if the hook executes, it currently depends on environment variables (`CLAUDE_TOOL_NAME`, `CLAUDE_TOOL_INPUT`) that may not be injected. The hook should read JSON from stdin.

**Root Cause:** See `docs/audit/2026-01-03_root-cause-hook-stdin-failure.md`

**Files:**
- Modify: `scripts/cm_track_operation.py` (rewrite main function)
- Test: Manual test with JSON input

**Step 1: Test current behavior with stdin**

Create: `/tmp/hook_test.json`

```json
{
  "toolUse": {
    "name": "Read",
    "input": {
      "file_path": "/tmp/test_project/src/app.py"
    }
  },
  "timestamp": 1234567890
}
```

Run: `echo '{"toolUse":{"name":"Read","input":{"file_path":"test.txt"}}}' | python3 scripts/cm_track_operation.py`

Expected: Hook returns immediately (current behavior is broken)

**Step 2: Create logging module (if not exists from Task 3)**

Create: `src/infrastructure/logging.py`

```python
"""Configurable logging for context-memory plugin."""
import logging
import os
import sys
from pathlib import Path
from typing import Any

_DEBUG_ENABLED = os.environ.get("CM_DEBUG", "0") == "1"


class _NullLogger:
    """No-op logger used when CM_DEBUG=0 (default)."""
    def __init__(self, name: str):
        self._name = name
    def debug(self, msg: str, *args: Any) -> None: pass
    def info(self, msg: str, *args: Any) -> None: pass
    def warning(self, msg: str, *args: Any) -> None: pass
    def error(self, msg: str, *args: Any) -> None: pass
    def exception(self, msg: str, *args: Any) -> None: pass


_loggers: dict[str, logging.Logger | _NullLogger] = {}


def get_logger(name: str) -> logging.Logger | _NullLogger:
    """Get a logger instance (real if CM_DEBUG=1, null otherwise)."""
    if name in _loggers:
        return _loggers[name]

    if not _DEBUG_ENABLED:
        _loggers[name] = _NullLogger(name)
        return _loggers[name]

    if not logging.getLogger().handlers:
        log_file = Path("/tmp") / "cm_hook_debug.log"
        try:
            logging.basicConfig(
                level=logging.DEBUG,
                filename=str(log_file),
                format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                filemode='a'
            )
        except (OSError, IOError):
            logging.basicConfig(
                level=logging.DEBUG,
                stream=sys.stderr,
                format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
            )

    logger = logging.getLogger(name)
    _loggers[name] = logger
    return logger
```

**Step 3: Rewrite main() to read from stdin**

Modify: `scripts/cm_track_operation.py:33-151`

```python
def main():
    """Main entry point - reads JSON from stdin (not environment variables)."""
    logger = get_logger(__name__)
    logger.debug("=" * 60)
    logger.debug("cm_track_operation.py called")

    # Parse JSON input from stdin
    try:
        hook_input = json.load(sys.stdin)
        logger.debug(f"Received JSON: {json.dumps(hook_input)[:200]}")
    except json.JSONDecodeError as e:
        logger.debug(f"Invalid JSON input: {e}")
        return

    # Extract tool use info
    tool_use = hook_input.get("toolUse", {})
    tool_name = tool_use.get("name", "")
    input_data = tool_use.get("input", {})

    logger.debug(f"Tool: {tool_name}")

    # Only track Read/Write/Edit operations
    if tool_name not in ("Read", "Write", "Edit", "MultiEdit"):
        logger.debug(f"Skipping tool: {tool_name}")
        return

    # Detect git repository
    repo_info = detect_repo()
    if not repo_info:
        logger.debug("Not in a git repo - hook disabled")
        return

    logger.debug(f"Repo detected: {repo_info.root}")

    # Extract file path from tool input
    file_path_str = input_data.get("file_path", "")
    if not file_path_str:
        # MultiEdit has files array
        files = input_data.get("files", [])
        if files and isinstance(files[0], dict):
            file_path_str = files[0].get("file", "")
        elif files:
            file_path_str = files[0]

    if not file_path_str:
        logger.debug("No file_path in input - skipping")
        return

    file_path = Path(file_path_str)

    # Normalize to relative path inside repo
    try:
        rel_path = get_relative_path(file_path, repo_info.root)
    except (ValueError, TypeError) as e:
        logger.warning(f"Path validation failed for {file_path}: {e}")
        return

    logger.debug(f"Tracking {tool_name} on {rel_path}")

    # Create event
    try:
        timestamp = hook_input.get("timestamp", int(os.times()[4]))
        event = ContextEvent(
            operation=OperationType(tool_name.lower()),
            ts=timestamp,
            source=EventSource.HOOK,
            file_path=rel_path,
            tool=tool_name,
            tool_input=None,
        )
    except (ValueError, TypeError) as e:
        logger.error(f"Failed to create event: {e}")
        return

    # Append to current.jsonl
    try:
        sessions_dir = repo_info.root / ".claude" / "context_memory" / "sessions"
        storage = JSONLStorage(sessions_dir / "current.jsonl")
        storage.append(event)
        logger.debug(f"✅ Event captured: {tool_name} {rel_path}")
    except (OSError, IOError) as e:
        logger.error(f"Storage failed: {e}")
        return
```

**Step 4: Update docstring**

Modify: `scripts/cm_track_operation.py:1-12`

```python
"""
Context-Memory Operation Tracking Hook

This script runs as a PostToolUse hook to track file operations (Read/Write/Edit)
and store them in a JSONL log for context pruning and bundling.

Input: JSON object via stdin with format:
    {"toolUse": {"name": "Read", "input": {"file_path": "..."}}, "timestamp": ...}

Output: Appends event to .claude/context_memory/sessions/current.jsonl

Environment Variables:
    CM_DEBUG=1: Enable debug logging to /tmp/cm_hook_debug.log
"""
```

**Step 5: Test the rewritten hook**

Run: `cd /tmp && mkdir -p test_project && cd test_project && git init`

Run: `touch src/app.py && git add .`

Run: `echo '{"toolUse":{"name":"Read","input":{"file_path":"/tmp/test_project/src/app.py"}},"timestamp":1234567890}' | python3 /Users/felipe_gonzalez/.claude/plugins/context-memory/scripts/cm_track_operation.py`

Expected: No output (success)

**Step 6: Verify event was captured**

Run: `cat .claude/context_memory/sessions/current.jsonl`

Expected: JSON line with event data

**Step 7: Test with debug logging**

Run: `CM_DEBUG=1 python3 /Users/felipe_gonzalez/.claude/plugins/context-memory/scripts/cm_track_operation.py < /tmp/hook_test.json 2>&1 | tail -5`

Expected: Debug messages showing execution flow

**Step 8: Commit the rewrite**

```bash
git add scripts/cm_track_operation.py src/infrastructure/logging.py
git commit -m "fix: rewrite hook to read from stdin instead of environment variables

CRITICAL FIX: The hook was reading from CLAUDE_TOOL_NAME and CLAUDE_TOOL_INPUT
environment variables that may not be injected. Rewrote to read JSON from stdin
which is the correct Claude Code hook input format.

This also adds configurable debug logging via CM_DEBUG=1."
```

---

## Task 2: Fix Failing Path Security Tests

**Context:** 4 tests in `test_paths_security.py` are failing due to fixture misconfiguration.

**Files:**
- Create: `tests/conftest.py`
- Modify: `tests/test_paths_security.py`

**Step 1: Create shared fixtures**

Create: `tests/conftest.py`

```python
"""Shared pytest fixtures for context-memory tests."""
import pytest
from pathlib import Path

@pytest.fixture
def repo_root(tmp_path, monkeypatch):
    """Create a temporary git repo root and change cwd to it."""
    repo_root = tmp_path / "test_repo"
    repo_root.mkdir()
    (repo_root / ".git").mkdir()
    monkeypatch.chdir(repo_root)
    return repo_root
```

**Step 2: Fix test expectations**

Modify: `tests/test_paths_security.py` (update failing tests to use correct error messages and fixture)

**Step 3: Run tests**

Run: `pytest tests/test_paths_security.py -v`

Expected: All tests pass

**Step 4: Commit**

```bash
git add tests/conftest.py tests/test_paths_security.py
git commit -m "fix: correct repo_root fixture and test expectations"
```

---

## Task 3: Add Debug Logging Mode

**Context:** The plugin has 12 silent failure points making it impossible to debug.

**Files:**
- Create: `src/infrastructure/logging.py` (if not created in Task 1)
- Modify: All scripts to use logger

**Note:** If Task 1 was completed, logging module already exists. Just add imports to remaining scripts.

**Step 1: Import logger in remaining scripts**

Modify: `scripts/cm_*.py`

```python
from infrastructure.logging import get_logger
logger = get_logger(__name__)
```

**Step 2: Add logging to error handling**

Replace silent `except: pass` with `logger.error(...)` or `logger.debug(...)`

**Step 3: Commit**

```bash
git add src/infrastructure/logging.py scripts/*.py
git commit -m "feat: add configurable debug logging via CM_DEBUG=1"
```

---

## Task 4: Create Health Check Command

**Context:** Users have no way to verify if context-memory is working correctly.

**Files:**
- Create: `scripts/cm_health`

**Step 1: Create health check script**

Create: `scripts/cm_health`

```python
#!/usr/bin/env python3
"""Health check for context-memory plugin."""
import argparse
import shutil
import subprocess
import sys
from pathlib import Path

def check_git():
    """Check if git is available."""
    try:
        subprocess.run(["git", "--version"], capture_output=True, check=True, timeout=5)
        print("✅ Git is available")
        return True
    except (FileNotFoundError, subprocess.CalledProcessError):
        print("❌ Git not found")
        return False

def check_write_permissions():
    """Check if we can write to .claude/context_memory."""
    try:
        test_dir = Path(".claude/context_memory/sessions")
        test_dir.mkdir(parents=True, exist_ok=True)
        test_file = test_dir / ".write_test"
        test_file.touch()
        test_file.unlink()
        print("✅ Write permissions OK")
        return True
    except OSError as e:
        print(f"❌ Write permissions failed: {e}")
        return False

def check_disk_space():
    """Check if there's enough disk space (>100MB)."""
    stat = shutil.disk_usage(".")
    free_mb = stat.free / (1024 * 1024)
    if free_mb > 100:
        print(f"✅ Disk space OK ({free_mb:.0f}MB free)")
        return True
    else:
        print(f"⚠️  Low disk space ({free_mb:.0f}MB free)")
        return False

def main():
    """Run all health checks."""
    parser = argparse.ArgumentParser(description="Health check for context-memory")
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args()

    print("Context-Memory Health Check")
    print("=" * 40)

    checks = [check_git(), check_write_permissions(), check_disk_space()]

    print("=" * 40)
    if all(checks):
        print("✅ All checks passed")
        sys.exit(0)
    else:
        print("❌ Some checks failed")
        sys.exit(1)

if __name__ == "__main__":
    main()
```

**Step 2: Make executable**

Run: `chmod +x scripts/cm_health`

**Step 3: Commit**

```bash
git add scripts/cm_health
git commit -m "feat: add health check command"
```

---

## Summary

After completing Tasks 0-2:

- ✅ Hook invocation fixed (uses `${CLAUDE_PLUGIN_ROOT}`)
- ✅ Hook logic fixed (reads from stdin)
- ✅ Tests passing
- ✅ Debug logging available
- ✅ Health check implemented

**Estimated time:** 3-4 hours for critical fixes (Tasks 0-1)

**Next steps:**
1. Restart Claude Code after Task 0
2. Test hook execution with debug logging
3. Verify events are captured in current.jsonl
4. Run full test suite

---

**Plan created:** 2026-01-03
**For implementation:** Use superpowers:executing-plans or superpowers:subagent-driven-development
