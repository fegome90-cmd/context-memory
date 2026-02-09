# Context Memory Method

## Source of Truth

This document describes how the **context-memory** system works. It is the canonical reference for implementation and usage.

## Core Philosophy

**Context is a log, not a state.**

Every session produces an **append-only event log** (JSONL). From this log, we derive **compact bundles** that capture the "essence" of work done.

This is inspired by:
- **Event sourcing**: Events are the source of truth
- **Indy Dev Dan's bundles**: Rehydration plans for context
- **Append-only logs**: O(1) writes, never rewrite history

## Architecture

### Separation of Concerns

```
┌─────────────────────────────────────────────────────────┐
│  Domain Layer (Pure)                                    │
│  - Event dataclasses                                    │
│  - JSONL parser (tolerant)                              │
│  - Pruning strategies (dedupe, prioritize, budget)      │
│  - Load plan builder                                    │
├─────────────────────────────────────────────────────────┤
│  Infrastructure Layer (Impure)                          │
│  - Filesystem operations                                │
│  - Lock management                                      │
│  - Repo detection                                       │
│  - Path validation/security                             │
└─────────────────────────────────────────────────────────┘
```

### Why This Matters

- **Testability**: Domain logic tested without filesystem
- **Performance**: Locks only at write boundary
- **Security**: Path validation centralized
- **Maintainability**: Each layer has single responsibility

## Event Schema

### Minimal (Required)

```json
{"operation":"read","file_path":"src/app.py","ts":1704067200,"tool":"Read"}
```

### Optional Fields

```json
{
  "operation": "write",
  "file_path": "src/app.py",
  "ts": 1704067200,
  "tool": "Write",
  "tool_input": "<TRUNCATED to 2-4KB>"
}
```

### Forbidden

- **Never include**: `tool_output` (too large, mostly irrelevant)
- **Never include**: Full file content (use paths + CAS instead)
- **Never include**: Absolute paths (breaks portability)
- **Never include**: Paths with `..` (security risk)

## Storage

### Global (Plugin)

Location: `~/.claude/plugins/context-memory/`

Contains:
- `src/domain/` - Pure logic modules
- `src/infrastructure/` - Adapters
- `scripts/` - CLI entry points
- `templates/commands/` - Command templates

**Purpose**: Reusable code, installed once, updated independently.

### Local (Per Repo)

Location: `<repo>/.claude/context_memory/`

Contains:
- `sessions/current.jsonl` - Active session log
- `bundles/<name>.jsonl` - Pruned bundles
- `cas/<name>.json` - Optional snapshots

**Purpose**: Repo-specific memory, travels with repo, no cross-contamination.

## Pruning Strategy

### Goals

1. **Compactness**: ~20 operations max (configurable)
2. **Representativeness**: Capture intent, not every keystroke
3. **Rehydratability**: Enough info to restore context

### Algorithm

```python
def prune(events, max_ops=20):
    # 1. Classify by importance
    for event in events:
        event.tags = classify(event.file_path)

    # 2. Dedupe reads (keep last per path)
    events = dedupe_by_path(events)

    # 3. Sort by priority (pinned > core > test > noise)
    events = sort_by_priority(events)

    # 4. Apply budget
    return events[:max_ops]
```

### Classification

| Tag | Patterns | Priority |
|-----|----------|----------|
| `core` | `*.py`, `src/`, `lib/` | Highest |
| `config` | `*.json`, `*.toml`, `*.yaml`, `config/` | Highest |
| `doc` | `README.md`, `docs/`, `*.md` | Medium |
| `test` | `tests/`, `test_*.py` | Medium |
| `noise` | `*.log`, `*.tmp`, `node_modules/`, `dist/` | Lowest |

## Rehydration

### Load Plan

A load plan is a list of **actions** to restore context:

```python
[
    {"action": "read", "path": "README.md", "reason": "project overview"},
    {"action": "read", "path": "src/domain/events.py", "reason": "core domain"},
    {"action": "inject", "content": "Working on pricing refactor", "reason": "user note"},
]
```

### Drift Detection

When CAS is enabled:
1. Store `sha256` of file when saving bundle
2. On load, compute current `sha256`
3. Warn if mismatch: "File changed since bundle"

### Optional CAS

For full reproducibility:
- Enable `cas=true` in config
- Stores file snapshots in `cas/<sha256>`
- Rehydration can load exact content from bundle

**Default**: Off (storage intensive, usually unnecessary)

## Repo Identity

### Stable ID

Determined once, stored in `.claude/context-memory-id`:

```python
if has_git_remote():
    repo_id = sha256(remote_url + root)[:10]
else:
    repo_id = uuid4()  # saved to file
```

### Why Not Path-Based?

- **Moving repo**: Path changes, ID shouldn't
- **Multiple clones**: Different paths, same repo
- **Branch switching**: Branch changes, ID shouldn't

### Metadata

Branch, remote, etc. stored as metadata (not part of ID):

```json
{"repo_id": "abc123", "branch": "main", "remote": "origin"}
```

## Hook Integration

### PostToolUse Hook

**IMPORTANT (v1.0.2)**: Claude Code reads hooks from `settings.json` files, not standalone `hooks.json`. The correct format in `.claude/settings.local.json` is:

```json
{
  "hooks": {
    "PostToolUse": [
      {
        "matcher": "Read|Write|Edit|MultiEdit",
        "hooks": [
          {
            "type": "command",
            "command": "python3 /absolute/path/to/cm_track_operation.py"
          }
        ]
      }
    ]
  }
}
```

**Plugin-level format** (in `hooks/hooks.json`) uses `${CLAUDE_PLUGIN_ROOT}` for portability:
```json
{
  "hooks": {
    "PostToolUse": [
      {
        "matcher": "Read|Write|Edit|MultiEdit",
        "hooks": [
          {
            "type": "command",
            "command": "python3 ${CLAUDE_PLUGIN_ROOT}/scripts/cm_track_operation.py"
          }
        ]
      }
    ]
  }
}
```

### Processing Flow

`cm_track_operation.py` processes each tool use through these steps:

1. **Parse stdin**: Receive JSON with tool_name, tool_input, timestamp
2. **Extract file_path**: Handle both single-file and MultiEdit operations
3. **Detect repository** (v1.0.2 fix): Use `detect_repo_from_file_path()` to find repo from the absolute file path (primary), fall back to `detect_repo()` using cwd (secondary)
4. **Validate path**: Check for traversal attempts, symlinks inside repo, containment
5. **Normalize path**: Convert to relative path from repo root
6. **Create event**: Build ContextEvent with truncated tool_input (max 4KB)
7. **Append to JSONL**: Thread-safe write with `fcntl.flock`

**Code flow for repository detection (v1.0.2)**:
```python
# In cm_track_operation.py main():
# 1. Extract file_path FIRST (before any repo detection)
file_path_str = extract_file_path(input_data)

# 2. Use absolute file path for repo detection (primary)
file_path = Path(file_path_str)
if file_path.is_absolute():
    repo_info = detect_repo_from_file_path(file_path)  # NEW in v1.0.2
else:
    repo_info = detect_repo()  # Fallback for relative paths
```

### Filtering

`cm_track_operation.py` enforces these filters:

1. **Tool whitelist**: Only `Read|Write|Edit|MultiEdit` tracked
2. **Path security**: No `..`, no absolutes, no traversal
3. **Repo containment**: File must be inside detected repo root
4. **Symlink safety**: macOS system symlinks allowed, internal symlinks rejected

### Data Truncation

To keep JSONL compact:
- `tool_output`: Always discarded (too large, mostly irrelevant)
- `tool_input`: Truncated to 4KB max (configurable via `MAX_TOOL_INPUT_SIZE`)

### Locking

Use `fcntl.flock` (Unix) for append safety:

```python
with open(path, "a") as f:
    fcntl.flock(f.fileno(), fcntl.LOCK_EX)
    f.write(line + "\n")
```

### Repository Detection Issues (Bug #2 - Fixed in v1.0.2)

**Problem**: Original code used `detect_repo()` which relies on `Path.cwd()`. However, hooks run with `cwd` set to Claude Code's internal directory, NOT the project directory.

**Old flow (broken)**:
```python
# Hook runs with cwd = /internal/claude/code/dir
repo_info = detect_repo()  # Searches upward from wrong dir
# Result: Fails to find repo, hook disabled
```

**New flow (v1.0.2)**:
```python
# Extract absolute file_path from tool input
file_path = Path(file_path_str)  # e.g., /Users/user/project/src/app.py
repo_info = detect_repo_from_file_path(file_path)  # Searches from file location
# Result: Correctly finds repo by walking up from file
```

**Implementation**: `find_repo_root_from_path()` in `src/infrastructure/repo.py` walks up the directory tree starting from the file path, looking for `.git` directory.

### Symlink Path Validation (Bug #3 - Fixed in v1.0.2)

**Problem**: macOS uses symlinks for system directories (`/tmp` → `/private/tmp`). The original code rejected ALL symlinks, causing false positives on legitimate macOS paths.

**Old behavior (broken)**:
```python
# Resolved the full path, then checked if ANY component was a symlink
resolved = path.resolve()
for part in resolved.parts:
    if part.is_symlink():
        raise ValueError("Symlinks not allowed")
# Result: /tmp/file.py rejected because /tmp is a symlink to /private/tmp
```

**New behavior (v1.0.2)**:
```python
# Resolve ONLY for containment check (handles macOS /tmp → /private/tmp)
resolved_abs = abs_path.resolve()
rel_path = resolved_abs.relative_to(resolved_root)

# Then check each component for symlinks INSIDE the repo
current = resolved_root
for part in rel_path.parts:
    current = current / part
    if current.is_symlink():
        raise ValueError("Symlinks not allowed in path")
# Result: /tmp allowed (system symlink), but repo/internal-link rejected
```

**Security consideration**: This allows system-level symlinks (like macOS's `/tmp`) while still blocking symlinks inside the repo that could be used to escape containment.

## Commands

### Slash Commands

Commands are **markdown files** with front-matter:

```markdown
---
description: Show context memory status
argument-hint: [--verbose]
allowed-tools: Bash, Read
---

# Context Memory Status

Shows bundles, sizes, and drift detection.
```

Installed to: `<repo>/.claude/commands/`

Discovered by: Claude Code (automatic)

### Command: `/cm-status`

Output:
```
Context Memory Status
=====================
Repo: my-project (abc123)
Current Session: 47 ops, ~12KB
Bundles:
  - refactor-pricing (15 ops, 2025-01-02, ✓ clean)
  - auth-fixup (12 ops, 2025-01-03, ⚠ drift: src/auth.py changed)
```

### Command: `/cm-save <name>`

Action:
1. Read `current.jsonl`
2. Prune to MAX_OPS
3. Write to `bundles/<name>.jsonl`
4. Update metadata

### Command: `/cm-load <name>`

Action:
1. Read bundle
2. Build load plan
3. Display plan (what to read, in what order)
4. Optional: Execute reads (if `--execute` flag)

## Troubleshooting

### Hook Not Firing

Symptom: `current.jsonl` not growing

Checks:
1. `.claude/settings.local.json` exists? (NOT `.claude/hooks.json` - Claude Code reads hooks from `settings.json`)
2. `cm_track_operation.py` executable?
3. Claude Code has permissions?
4. Check logs: `export CM_DEBUG=1`

**Verification**:
```bash
# Check for correct file (settings.local.json)
cat .claude/settings.local.json | grep -A5 "PostToolUse"
```

### Bundle Too Large

Symptom: Bundle has >50 ops

Fixes:
1. Adjust `MAX_OPS` in config
2. Add patterns to `ignore_patterns`
3. Run `/cm-prune` manually

### Paths Wrong

Symptom: Absolute paths in JSONL

Fix: Check `repo_root` detection in `cm_track_operation.py`

## Future Enhancements

- [ ] Compression for large bundles
- [ ] Remote bundle storage (sync across machines)
- [ ] LLM-assisted auto-tagging
- [ ] Graph visualization of file dependencies
- [ ] Automatic "checkpoint before big changes"

## References

- Indy Dev Dan: "Elite Context Engineering with Claude Code"
- Event Sourcing: Martin Fowler
- JSONL: https://jsonlines.org/
