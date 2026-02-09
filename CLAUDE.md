# context-memory - Context Tracking for Claude Code

## Project Context

**Business Domain:** Claude Code Plugin for Session Context Management

**User Role:** Claude Code AI assistant maintaining persistent memory across sessions

**Key Concepts:** Event sourcing, JSONL append-only logs, context pruning/rehydration, Clean Architecture/Hexagonal pattern, zero-dependency Python stdlib implementation

---

Track Claude Code sessions as JSONL event logs. Create compact bundles for context rehydration.

## Architecture

**Clean Architecture / Hexagonal**
- `src/domain/` — Pure business logic (events, parser, pruning, plan)
- `src/infrastructure/` — I/O adapters (storage, repo detection, paths)
- `scripts/` — CLI entry points
- `tests/` — Pytest with coverage

**Component Relationships:**
- `src/domain/` communicates with `src/infrastructure/` via dependency inversion (domain defines interfaces, infrastructure implements)
- `hooks/` communicates with `src/domain/` via event creation hooks (pretooluse, posttooluse)
- `scripts/` depends on `src/infrastructure/` for repo detection and path resolution
- `scripts/` depends on `src/domain/` for event processing and plan generation
- `tests/` depends on all layers via pytest fixtures and unit/integration tests

**Architecture Notes:**
- Clean Architecture ensures domain layer has ZERO filesystem dependencies
- JSONL files act as the event store (append-only, O(1) writes)
- Infrastructure layer provides storage adapters that domain layer consumes
- Hooks act as event producers, scripts act as consumers/aggregators

**Key constraint:** Domain layer has ZERO filesystem dependencies. Pure functions + frozen dataclasses.

## Development

```bash
# Run tests
python -m pytest tests/ -v

# Install in a repo (test locally)
cd /path/to/test-repo
python ~/.claude/plugins/context-memory/scripts/cm_install.py
```

## Code Patterns

**Domain (`src/domain/`):**
- Frozen dataclasses for immutable events
- Pure functions (no I/O)
- Security invariants in `__post_init__`

**Infrastructure (`src/infrastructure/`):**
- Adapter pattern for storage backends
- Path security: relative only, no traversal
- JSONL append-only (O(1) writes)

**Tests (`tests/`):**
- Unit tests for domain logic
- Integration tests for storage
- `conftest.py` for fixtures

## Project-Specific Constraints

1. **Zero external dependencies** — Python stdlib only
2. **Security first** — Validate all paths, no absolute paths
3. **Append-only logs** — Never rewrite history
4. **JSONL format** — One JSON object per line

## Documentation

**User-facing:** [README.md](README.md)

**Canonical references:**
- [docs/method.md](docs/method.md) — **Core philosophy & architecture** (event sourcing, pruning, rehydration)
- [docs/rules-of-engagement.md](docs/rules-of-engagement.md) — **Non-negotiable rules** (JSONL append-only, security, domain purity)
- [docs/audit/README.md](docs/audit/README.md) — **Known issues & roadmap** (testing gaps, Windows limitations)

## Common Commands

- `/cm-list` - List all context bundles across all repositories with filtering options
- `/cm-load` - Rehydrate a previous session from a saved context bundle
- `/cm-save` - Save current session context as a new bundle for later restoration
- `/cm-status` - Show current session tracking status and recent operations

---

## Lessons Learned

This section documents critical bugs discovered and fixed during development. Understanding these issues helps prevent similar problems in future features.

### Bug #1: Claude Code ignores `hooks.json` - reads only from `settings.json`

**Discovered**: v1.0.2 (2026-01-03)

**Symptom**: Plugin created `.claude/hooks.json` but hook never fired

**Root Cause**:
- Claude Code's hook system reads from `settings.json` files, NOT standalone `hooks.json` files
- The plugin-level `hooks/hooks.json` is only recognized when loaded via the plugin manifest
- Project-level hooks MUST be in `.claude/settings.local.json` (or `.claude/settings.json`)

**Original Code** (wrong):
```python
# In cm_install.py - created hooks.json
hooks_path = repo_root / ".claude" / "hooks.json"
with open(hooks_path, "w") as f:
    json.dump({"hooks": {...}}, f)
```

**Fixed Code** (correct):
```python
# In cm_install.py - creates settings.local.json
settings_path = repo_root / ".claude" / "settings.local.json"
new_hooks = {
    "hooks": {
        "PostToolUse": [{
            "matcher": "Read|Write|Edit|MultiEdit",
            "hooks": [{"type": "command", "command": f"python3 {script_path}"}]
        }]
    }
}
```

**Key Takeaway**: When integrating with Claude Code's hook system, always use `settings.json` format for project-level configuration. Standalone `hooks.json` is only valid at the plugin level (and even then, it's loaded via the plugin manifest, not directly).

**Debug Command**:
```bash
# Check if settings.local.json exists (correct)
ls -la .claude/settings.local.json

# If you see hooks.json instead, it's wrong
ls -la .claude/hooks.json  # This won't work!
```

---

### Bug #2: Repository detection failed because hook cwd != project directory

**Discovered**: v1.0.2 (2026-01-03)

**Symptom**: Hook reported "Not in a git repo" even when working in a valid repository

**Root Cause**:
- Claude Code runs hooks with `cwd` set to its internal directory, NOT the project directory
- Original code used `detect_repo()` which calls `Path.cwd()` to find the repository
- Hook would search upward from the wrong starting point and fail

**Original Code Flow** (broken):
```python
# In cm_track_operation.py main()
def main():
    # Hook runs with cwd = /internal/claude/code/dir
    repo_info = detect_repo()  # Uses Path.cwd() internally
    # Searches: /internal/claude/code/dir -> /internal/claude -> /internal -> /
    # Never finds .git, returns None
    if not repo_info:
        logger.debug("Not in a git repo - hook disabled")
        return 0
```

**Fixed Code Flow** (v1.0.2):
```python
# In cm_track_operation.py main()
def main():
    # 1. Extract file_path FIRST (from tool input)
    file_path_str = extract_file_path(input_data)
    file_path = Path(file_path_str)  # e.g., /Users/user/project/src/app.py

    # 2. Use absolute file path for repo detection (primary)
    if file_path.is_absolute():
        repo_info = detect_repo_from_file_path(file_path)  # NEW!
        # Searches from file location upward, finds .git
    else:
        # Fallback for relative paths
        repo_info = detect_repo()
```

**Implementation Details**:
- New function `find_repo_root_from_path(file_path: Path)` in `src/infrastructure/repo.py`
- Walks up directory tree starting from the file path
- Stops at `.git` directory or filesystem root (depth limit: 20)
- Wrapper `detect_repo_from_file_path()` returns full `RepoInfo` object

**Code Flow Comparison**:

| Aspect | Old (broken) | New (v1.0.2) |
|--------|-------------|--------------|
| Starting point | `Path.cwd()` | File path from tool input |
| Search direction | Up from hook cwd | Up from file location |
| Success rate | ~0% (wrong cwd) | ~100% (file in repo) |
| Fallback | None | `detect_repo()` for relative paths |

**Key Takeaway**: When writing hooks for Claude Code, NEVER rely on `cwd` being the project directory. Always derive context from the tool input itself (file paths, repository info, etc.).

**Debug Command**:
```bash
# Enable debug to see which detection method is used
export CM_DEBUG=1
# Trigger a Read operation
cat /tmp/cm_hook_debug.log | grep "Repo detected"
# Should see: "Repo detected from file_path: /actual/project/root"
```

---

### Bug #3: Symlink path validation failed on macOS (`/tmp` → `/private/tmp`)

**Discovered**: v1.0.2 (2026-01-03)

**Symptom**: Path validation errors on macOS when working in `/tmp` directory

**Root Cause**:
- macOS uses symlinks for system directories: `/tmp` → `/private/tmp`
- Original code rejected ALL symlinks as a security measure
- Legitimate system symlinks caused false positives

**Original Code** (broken):
```python
# In src/infrastructure/paths.py normalize_path()
def normalize_path(path: str, repo_root: Path) -> str:
    p = Path(path)
    abs_path = p.absolute()  # /tmp/file.py

    # Security check: NO symlinks allowed anywhere
    resolved = abs_path.resolve()  # /private/tmp/file.py
    for part in resolved.parents:
        if part.is_symlink():
            raise ValueError("Symlinks not allowed")
    # Result: /tmp/file.py rejected because /tmp → /private/tmp is a symlink
```

**Fixed Code** (v1.0.2):
```python
# In src/infrastructure/paths.py normalize_path()
def normalize_path(path: str, repo_root: Path) -> str:
    p = Path(path)

    # Get absolute path
    if p.is_absolute():
        abs_path = p.absolute()
    else:
        abs_path = (Path.cwd() / p).absolute()

    # Resolve repo_root (safe - we control this path)
    resolved_root = repo_root.resolve()

    # Resolve the initial path prefix for containment check.
    # This handles macOS /tmp → /private/tmp symlinks and similar cases.
    resolved_abs = abs_path.resolve()

    # Check if outside repo root (using resolved paths for prefix match)
    try:
        rel_path = resolved_abs.relative_to(resolved_root)
    except ValueError:
        raise ValueError(f"Path '{path}' is outside repository root '{repo_root}'")

    # SECURITY: Check that no path component is a symlink INSIDE the repo
    # Build the path incrementally and check each component
    current = resolved_root
    for part in rel_path.parts:
        current = current / part
        if current.is_symlink():
            raise ValueError(
                f"Symlinks not allowed in path: '{path}' (component '{part}' is a symlink)"
            )

    return str(rel_path).replace("\\", "/")
```

**Security Consideration**:
- System-level symlinks (before repo root): Allowed (e.g., `/tmp` → `/private/tmp`)
- Internal symlinks (inside repo): Blocked (could escape containment)

**Example Behavior**:

| Path | Old Behavior | New Behavior |
|------|-------------|--------------|
| `/tmp/file.py` (in repo at `/private/tmp`) | ❌ Rejected (`/tmp` is symlink) | ✅ Allowed (system symlink) |
| `/repo/src/link.py` (symlink to `/etc/passwd`) | ❌ Rejected (any symlink) | ❌ Rejected (internal symlink) |
| `/repo/normal.py` | ✅ Allowed | ✅ Allowed |

**Key Takeaway**: Path security is nuanced. Blanket "no symlinks" policies break legitimate use cases. Instead, allow system symlinks while blocking internal ones that could escape containment.

**Debug Command**:
```bash
# Test symlink handling
export CM_DEBUG=1
# Work with a /tmp file
echo '{"tool_name":"Read","tool_input":{"file_path":"/tmp/test.py"}}' | \
  python3 ~/.claude/plugins/context-memory/scripts/cm_track_operation.py
cat /tmp/cm_hook_debug.log | grep -i symlink
```

---

### Debugging Guide

When investigating hook issues, use this workflow:

**1. Enable debug logging**:
```bash
export CM_DEBUG=1
```

**2. Trigger a hook operation** (e.g., read a file)

**3. Check the debug log**:
```bash
cat /tmp/cm_hook_debug.log
```

**4. Look for these key messages**:

| Debug Message | Indicates |
|--------------|-----------|
| `"Repo detected from file_path"` | ✅ Using v1.0.2+ file_path detection |
| `"Repo detected from cwd"` | ⚠️ Fallback to cwd (may fail) |
| `"Not in a git repo"` | ❌ Both detection methods failed |
| `"Symlinks not allowed"` | ❌ Old code (pre-v1.0.2) |
| `"Path validation blocked"` | ❌ Security check failed |

**5. Verify hook configuration**:
```bash
# Check for correct file (settings.local.json)
cat .claude/settings.local.json | grep -A5 "PostToolUse"

# Should see:
# "hooks": {
#   "PostToolUse": [{
#     "matcher": "Read|Write|Edit|MultiEdit",
# ...
```

**6. Check session log is growing**:
```bash
# Should see new lines appended
tail -f .claude/context_memory/sessions/current.jsonl
```

---

### Prevention Checklist

To avoid similar bugs in future features:

- [ ] **Never assume `cwd`** in hooks - derive context from tool input
- [ ] **Use correct config files** - `settings.json` for hooks, not `hooks.json`
- [ ] **Test on target platform** - macOS symlinks differ from Linux
- [ ] **Security is layered** - prefix resolution OK, component checks for containment
- [ ] **Add debug logging** - `CM_DEBUG=1` should trace the full flow
- [ ] **Document assumptions** - write down what you assume about the host system