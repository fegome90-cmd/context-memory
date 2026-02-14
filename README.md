# context-memory

Context tracking bundle system for Claude Code. Track operations, prune sessions, rehydrate context across windows.

## Overview

`context-memory` captures your work sessions as **JSONL event logs** and creates **compact bundles** for context rehydration. Inspired by Indy Dev Dan's "Elite Context Engineering" approach.

**Key features:**
- **Append-only JSONL**: O(1) writes, never rewrites history
- **Hybrid storage**: Global scripts + local bundles per repo
- **Intelligent pruning**: Dedupe, prioritize by importance, respect budgets
- **Secure**: Relative paths only, no path traversal, no full content
- **Zero dependencies**: Python stdlib only

## Changelog

### 2026-01-03 - Hook Tests Fixed
- ✅ Fixed 2 failing tests in `test_cm_track_operation.py`
- ✅ Added `nested_repos` fixture to `tests/conftest.py` for testing nested repo structures
- ✅ Fixed JSON serialization bug for MappingProxy in `src/domain/events.py:to_dict()`
- ✅ Verified hook correctly captures Read/Write/Edit/MultiEdit operations
- ✅ Created and tested `hook-tests-fixed` bundle
- ✅ Verified `/cm-load` context rehydration works correctly
- 📊 Test suite: 106 tests passing, 82% coverage

### 2026-01-02 - Initial Release
- Core event tracking with JSONL append-only logs
- Pruning strategy with deduplication and prioritization
- Bundle save/load functionality
- PostToolUse hook for automatic tracking

## Quick Start

### 1. Install in a Repository

**Basic installation:**
```bash
cd /path/to/your/project
python3 ~/.claude/plugins/context-memory/scripts/cm_install.py
```

**Installation options:**
```bash
# Force overwrite existing commands
python3 ~/.claude/plugins/context-memory/scripts/cm_install.py --force

# Don't merge with existing settings (create fresh settings.local.json)
python3 ~/.claude/plugins/context-memory/scripts/cm_install.py --no-merge

# Install in a different repository
python3 ~/.claude/plugins/context-memory/scripts/cm_install.py --repo /path/to/repo
```

This creates:
- `.claude/commands/` with slash commands (`/cm-status`, `/cm-save`, etc.)
- `.claude/settings.local.json` with PostToolUse tracking hook
- `.claude/context_memory/` for sessions and bundles

#### Understanding the 3-Tier Hook Mechanism

**IMPORTANT (v1.0.2 fix)**: Claude Code reads hooks from `settings.json`, NOT from `hooks.json`. The plugin uses a 3-tier system:

1. **Plugin-level** (`hooks/hooks.json`): Auto-loaded when plugin is enabled, uses `${CLAUDE_PLUGIN_ROOT}` for portability
2. **Project-level** (`.claude/settings.local.json`): Created by install script, uses absolute paths for reliability
3. **Global settings** (`~/.claude/settings.json`): User-level hook configuration (optional)

The install script creates `.claude/settings.local.json` (not `hooks.json`) because Claude Code's settings loader only recognizes the `settings.json` file format.

### 2. Work Normally

Just work in Claude Code. The hook tracks:
- `Read` operations: file paths read
- `Write`/`Edit`/`MultiEdit`: file paths modified
- User prompts: commands like `/cm-save my-bundle`

### 3. Save a Bundle

```
/cm-save pricing-refactor
```

This prunes the current session to ~20 critical operations and saves to `.claude/context_memory/bundles/pricing-refactor.jsonl`.

### 4. Rehydrate in New Window

```bash
# New Claude Code window, same repo
/cm-load pricing-refactor
```

Displays a rehydration plan: which files to read, in what order, to restore context.

## Commands

| Command | Description |
|---------|-------------|
| `/cm-status` | Show bundles, sizes, dates, drift detection |
| `/cm-context` | Show summary of current session (top ops) |
| `/cm-save <name> [--max-ops N]` | Prune and save bundle |
| `/cm-load <name>` | Show rehydration plan |
| `/cm-prune [--max-ops N]` | Prune current session in-place |

## Storage Structure

### Global (Plugin)
```
~/.claude/plugins/context-memory/
├── src/domain/          # Pure logic: events, parser, pruning
├── src/infrastructure/  # Adapters: storage, repo detection
├── scripts/             # CLI entry points
└── templates/commands/  # Command templates
```

### Local (Per Repo)
```
<repo>/.claude/
├── commands/            # Installed slash commands
├── settings.local.json  # PostToolUse tracking hook (v1.0.2: was hooks.json)
└── context_memory/
    ├── sessions/
    │   └── current.jsonl          # Active session log
    ├── bundles/
    │   └── <name>.jsonl           # Pruned bundles
    └── cas/
        └── <name>.json            # Optional: snapshots for drift
```

**Note**: Hooks are configured in `settings.local.json` (not `hooks.json`) because Claude Code reads hook configurations from `settings.json` files, not standalone `hooks.json` files. See [docs/troubleshooting.md](docs/troubleshooting.md) for details on the v1.0.2 fixes.

## Event Schema (JSONL)

Each line is a JSON object with minimal fields:

```jsonl
{"operation":"read","file_path":"src/app.py","ts":1704067200,"tool":"Read"}
{"operation":"write","file_path":"src/app.py","ts":1704067300,"tool":"Write","tool_input":"<TRUNCATED>"}
{"operation":"prompt","prompt":"/cm-save refactor","ts":1704067400}
```

**Never includes:**
- Full file content
- Complete tool_output
- Absolute paths
- Paths outside repo

## Pruning Strategy

Bundles are pruned to `MAX_OPS=20` (configurable) using:

1. **Dedupe by path**: Keep last read per file
2. **Prioritize**: config > docs > src > tests > temp
3. **Penalize**: node_modules, dist, .venv, .git
4. **Budget**: Limit ops and estimated bytes

## Repo Identity

Stable repo ID determined by:
1. `.claude/context-memory-id` if exists (created once)
2. Git remote URL + root hash
3. Fallback: random UUID (saved to file)

**Why:** Moving repo doesn't break identity. Branch changes update metadata, not ID.

## Troubleshooting

### Quick Debug Commands

**Enable debug logging:**
```bash
export CM_DEBUG=1
echo '{"tool_name":"Read","tool_input":{"file_path":"/path/to/file.py"}}' | \
  python3 ~/.claude/plugins/context-memory/scripts/cm_track_operation.py
cat /tmp/cm_hook_debug.log
```

**Check hook configuration:**
```bash
# Verify settings.local.json exists (NOT hooks.json)
cat .claude/settings.local.json

# Check hook is registered
grep -A5 "PostToolUse" .claude/settings.local.json
```

**Verify storage:**
```bash
# Check session log is growing
tail -f .claude/context_memory/sessions/current.jsonl

# List saved bundles
ls -la .claude/context_memory/bundles/
```

### Known Issues (v1.0.2 Fixes)

#### Bug #1: Hook not tracking - `hooks.json` ignored

**Symptom**: `.claude/hooks.json` exists but tracking doesn't work

**Root Cause**: Claude Code reads hooks from `settings.json` files, NOT from standalone `hooks.json` files. The plugin's `hooks/hooks.json` is only used for plugin-level registration via `${CLAUDE_PLUGIN_ROOT}`.

**Verification**:
```bash
# Check if settings.local.json exists (should be created by install)
ls -la .claude/settings.local.json

# If missing, re-run install
python3 ~/.claude/plugins/context-memory/scripts/cm_install.py
```

**Fix**: The install script now creates `.claude/settings.local.json` with the hook configuration. Re-run the installer if you have an old installation.

#### Bug #2: Repository detection fails

**Symptom**: Hook reports "Not in a git repo" even though you are in one

**Root Cause**: The hook runs with a different `cwd` than the project directory. v1.0.2 added `detect_repo_from_file_path()` which derives the repo from the absolute file path instead of relying on `cwd`.

**Verification**:
```bash
# Check if the hook is using file_path-based detection
export CM_DEBUG=1
# Trigger a Read operation
cat /tmp/cm_hook_debug.log | grep "Repo detected"
```

**Fix**: Ensure you're using v1.0.2 or later. The hook now prioritizes `detect_repo_from_file_path()` over `detect_repo()`.

#### Bug #3: macOS symlink validation fails

**Symptom**: Path validation errors on macOS with `/tmp` paths

**Root Cause**: macOS uses symlinks for system directories (`/tmp` → `/private/tmp`). The original code rejected ALL symlinks, causing false positives on legitimate macOS paths.

**Verification**:
```bash
# Check if you're hitting symlink validation
export CM_DEBUG=1
# Trigger operation on /tmp file
cat /tmp/cm_hook_debug.log | grep "Symlinks not allowed"
```

**Fix**: v1.0.2 now resolves the prefix for containment checks (handling `/tmp` → `/private/tmp`) while still rejecting symlinks INSIDE the repo that could escape.

### Common Issues

#### Hook not tracking
- Check `.claude/settings.local.json` exists (not `.claude/hooks.json`)
- Verify `cm_install.py` ran successfully
- Check Claude Code has permission to run hooks
- Enable debug mode: `export CM_DEBUG=1`

#### Bundle too large
- Run `/cm-prune --max-ops 10` for tighter budget
- Check for ignored paths (add to `ignore_patterns` in config)
- Review what's being tracked: `/cm-context`

#### Missing files on load
- Files may have been deleted/moved since bundle
- Drift detection warns if `sha256` mismatches (when CAS enabled)
- Use `/cm-status` to see bundle health

#### Tests failing
```bash
# Run specific test with verbose output
python -m pytest tests/test_cm_track_operation.py::test_hook_rejects_paths_outside_repo -v

# Check coverage
python -m pytest tests/ --cov=src --cov-report=term-missing
```

### Error Message Reference

| Error | Cause | Fix |
|-------|-------|-----|
| "hooks.json ignored" | Using wrong file | Use `settings.local.json` instead |
| "Not in a git repo" | cwd != project dir | Upgrade to v1.0.2+ |
| "Symlinks not allowed" | macOS /tmp symlink | Upgrade to v1.0.2+ |
| "Path outside repository" | File outside repo root | Check file location |
| "Object of type mappingproxy" | Old bug | Fixed in v1.0.1+ |

### Bundle save failing with JSON error
- **Symptom**: `TypeError: Object of type mappingproxy is not JSON serializable`
- **Status**: ✅ Fixed in v1.0.1 (2026-01-03)
- **Solution**: Update plugin to latest version

## Development

Run tests:
```bash
cd ~/.claude/plugins/context-memory
python -m pytest tests/ -v
```

## Testing

The plugin has a comprehensive test suite with 106 tests and 82% coverage.

### Run Tests

```bash
# From the plugin directory
cd ~/.claude/plugins/context-memory
python -m pytest tests/ -v

# With coverage report
python -m pytest tests/ --cov=src --cov-report=term-missing
```

### Test Structure

```
tests/
├── test_cm_track_operation.py    # Hook functionality tests
├── test_domain_events.py          # Event creation and validation
├── test_domain_plan_build.py      # Load plan building
├── test_infra_*                   # Infrastructure layer tests
├── test_paths_security.py         # Path validation security tests
├── test_pruning.py                # Pruning strategy tests
└── conftest.py                    # Shared fixtures
```

### Available Fixtures

- `repo_root` - Creates a temporary git repository
- `temp_dir` - Creates a temporary directory
- `non_repo_dir` - Creates directory without .git
- `nested_repos` - Creates 3-level nested repo structure (for testing repo detection)
- `sample_events` - Provides sample event data for pruning tests

### Test Categories

- **Unit tests**: Domain logic (events, parser, pruning) - pure functions, no I/O
- **Integration tests**: Infrastructure layer (storage, repo detection, paths)
- **Hook tests**: PostToolUse hook behavior and security

### Coverage Goals

- Target: >80% coverage
- Current: 82% (✅ meeting target)
- Critical paths: 100% covered

## License

MIT

## Inspired By

- Indy Dev Dan's "Elite Context Engineering"
- Event sourcing patterns
- JSONL as log format
