# Context Engineering Integration Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Integrate missing context-engineering components (File Guards, Slash Commands) into the context-memory plugin to align with the theoretical framework documented in `context-engineering-brainstorm.md`.

**Architecture:**
- **File Guards:** PreToolUse hook that validates file paths against repository root before command execution
- **Slash Commands:** Markdown-based command definitions that wrap existing CLI scripts
- **Secret Sanitization:** Out of scope - using precommit hooks instead (documented in Task 4)

**Tech Stack:** Python 3.10+, Claude Code hooks, JSON configuration, Markdown templating

---

## Overview

This plan implements the missing components from the context-engineering brainstorming document:

| Component | Current State | Target State | Priority |
|-----------|---------------|--------------|----------|
| **File Guards** | Post-hoc validation in paths.py | PreToolUse hook blocking invalid paths | HIGH |
| **Slash Commands** | CLI scripts only | Markdown commands + CLI scripts | MEDIUM |
| **/load-bundle** | `cm-load` script | `/load-bundle` slash command | MEDIUM |
| **Secret Sanitization** | None | Precommit hooks (separate task) | HIGH |

---

## Task 1: File Guards PreToolUse Hook

**Purpose:** Block file access outside repository root before command execution (fail-closed security).

**Files:**
- Create: `scripts/cm_file_guard.py`
- Modify: `hooks/hooks.json` (add PreToolUse entry)
- Create: `tests/test_cm_file_guard.py`

**Reference:** `docs/method.md` (security-first design), `src/infrastructure/paths.py` (reuse validation logic)

---

### Step 1: Write the failing test for path blocking

**File:** `tests/test_cm_file_guard.py`

```python
"""Tests for cm_file_guard.py - PreToolUse security hook."""
import json
import pytest
from pathlib import Path
from scripts.cm_file_guard import validate_tool_input


def test_blocks_read_outside_repo(tmp_path, monkeypatch):
    """Test that Read tool with path outside repo is blocked."""
    # Create mock repo
    repo_root = tmp_path / "test_repo"
    repo_root.mkdir()

    # Create file outside repo
    outside_file = tmp_path / "outside" / "secret.txt"
    outside_file.parent.mkdir()
    outside_file.write_text("secret data")

    # Mock payload for Read tool
    payload = {
        "hook_event_name": "PreToolUse",
        "tool_name": "Read",
        "tool_input": {
            "file_path": str(outside_file)
        },
        "project_dir": str(repo_root),
        "cwd": str(repo_root)
    }

    # Should raise SystemExit(1) to block
    with pytest.raises(SystemExit) as exc_info:
        validate_tool_input(payload)

    assert exc_info.value.code == 1


def test_blocks_write_outside_repo(tmp_path):
    """Test that Write tool with path outside repo is blocked."""
    repo_root = tmp_path / "test_repo"
    repo_root.mkdir()

    outside_file = tmp_path / "etc" / "passwd"

    payload = {
        "hook_event_name": "PreToolUse",
        "tool_name": "Write",
        "tool_input": {
            "file_path": str(outside_file),
            "content": "malicious"
        },
        "project_dir": str(repo_root),
        "cwd": str(repo_root)
    }

    with pytest.raises(SystemExit) as exc_info:
        validate_tool_input(payload)

    assert exc_info.value.code == 1


def test_allows_read_inside_repo(tmp_path):
    """Test that Read tool with path inside repo is allowed."""
    repo_root = tmp_path / "test_repo"
    repo_root.mkdir()

    inside_file = repo_root / "src" / "app.py"
    inside_file.parent.mkdir()

    payload = {
        "hook_event_name": "PreToolUse",
        "tool_name": "Read",
        "tool_input": {
            "file_path": str(inside_file)
        },
        "project_dir": str(repo_root),
        "cwd": str(repo_root)
    }

    # Should NOT raise
    validate_tool_input(payload)


def test_blocks_path_traversal(tmp_path):
    """Test that path traversal sequences are blocked."""
    repo_root = tmp_path / "test_repo"
    repo_root.mkdir()

    payload = {
        "hook_event_name": "PreToolUse",
        "tool_name": "Read",
        "tool_input": {
            "file_path": "../../etc/passwd"
        },
        "project_dir": str(repo_root),
        "cwd": str(repo_root)
    }

    with pytest.raises(SystemExit) as exc_info:
        validate_tool_input(payload)

    assert exc_info.value.code == 1


def test_skips_non_file_tools(tmp_path):
    """Test that non-file tools are allowed through."""
    repo_root = tmp_path / "test_repo"
    repo_root.mkdir()

    payload = {
        "hook_event_name": "PreToolUse",
        "tool_name": "Bash",
        "tool_input": {
            "command": "ls -la"
        },
        "project_dir": str(repo_root),
        "cwd": str(repo_root)
    }

    # Should NOT raise (Bash is allowed)
    validate_tool_input(payload)
```

**Step 2: Run test to verify it fails**

```bash
pytest tests/test_cm_file_guard.py -v
```

**Expected:** `ImportError: cannot import name 'validate_tool_input' from 'scripts.cm_file_guard'`

---

### Step 3: Write minimal cm_file_guard.py implementation

**File:** `scripts/cm_file_guard.py`

```python
#!/usr/bin/env python3
"""
PreToolUse hook for file path validation.

Blocks Read/Write/Edit/MultiEdit operations that access files
outside the repository root. This is a security measure to prevent
unintended file access.

Usage:
    Configured as PreToolUse hook in hooks.json

Exit codes:
    0 = Path is safe (allow command)
    1 = Path is blocked (deny command)
"""
import json
import sys
from pathlib import Path


# Tools that access files and need validation
FILE_TOOLS = {"Read", "Write", "Edit", "MultiEdit"}


def validate_tool_input(payload: dict) -> None:
    """
    Validate tool input for file path safety.

    Args:
        payload: Hook payload from Claude Code

    Raises:
        SystemExit: If path is invalid (exit code 1)
    """
    tool_name = payload.get("tool_name", "")
    tool_input = payload.get("tool_input", {})
    project_dir = Path(payload.get("project_dir", ""))

    # Skip non-file tools
    if tool_name not in FILE_TOOLS:
        return

    # Extract file path from tool_input
    file_path_str = tool_input.get("file_path")
    if not file_path_str:
        return

    file_path = Path(file_path_str)

    # Check for path traversal
    if ".." in file_path_str or "\\.." in file_path_str:
        print("[FILE GUARD] Blocked: Path traversal detected", file=sys.stderr)
        sys.exit(1)

    # Resolve to absolute for comparison
    try:
        if file_path.is_absolute():
            abs_path = file_path.resolve()
        else:
            # Relative to CWD
            cwd = Path(payload.get("cwd", "."))
            abs_path = (cwd / file_path).resolve()

        # Check if outside project directory
        project_resolved = project_dir.resolve()
        try:
            abs_path.relative_to(project_resolved)
        except ValueError:
            print(f"[FILE GUARD] Blocked: Path outside repository", file=sys.stderr)
            print(f"  Project root: {project_resolved}", file=sys.stderr)
            print(f"  Requested: {abs_path}", file=sys.stderr)
            sys.exit(1)

    except OSError as e:
        # Path doesn't exist yet (e.g., Write tool creating new file)
        # Check parent directory instead
        parent = file_path.parent
        if parent.exists():
            try:
                parent.resolve().relative_to(project_dir.resolve())
            except ValueError:
                print(f"[FILE GUARD] Blocked: Parent path outside repository", file=sys.stderr)
                sys.exit(1)


def main():
    """Entry point for hook execution."""
    try:
        # Read payload from stdin
        payload_str = sys.stdin.read()
        if not payload_str:
            # Empty stdin = no data, allow through
            sys.exit(0)

        payload = json.loads(payload_str)
        validate_tool_input(payload)

        # If we get here, path is safe
        sys.exit(0)

    except json.JSONDecodeError as e:
        print(f"[FILE GUARD] Invalid JSON payload: {e}", file=sys.stderr)
        sys.exit(1)  # Fail closed on parse errors
    except Exception as e:
        print(f"[FILE GUARD] Unexpected error: {e}", file=sys.stderr)
        sys.exit(1)  # Fail closed on errors


if __name__ == "__main__":
    main()
```

---

### Step 4: Run tests to verify implementation

```bash
pytest tests/test_cm_file_guard.py -v
```

**Expected:** All tests pass

---

### Step 5: Update hooks.json to register PreToolUse hook

**File:** `hooks/hooks.json`

```json
{
  "PreToolUse": [
    {
      "matcher": "Read|Write|Edit|MultiEdit",
      "hooks": [
        {
          "type": "command",
          "command": "python3 ${CLAUDE_PLUGIN_ROOT}/scripts/cm_file_guard.py",
          "timeout": 1
        }
      ]
    }
  ],
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
```

**Step 6: Make script executable**

```bash
chmod +x scripts/cm_file_guard.py
```

---

### Step 7: Integration test - verify hook fires

```bash
# Create test repo
mkdir /tmp/test-hook
cd /tmp/test-hook
git init

# Install context-memory plugin
cm-install

# Try to read file outside repo
echo "Should be blocked"

# Test with actual Claude Code session
# (manual verification step)
```

**Expected:** File Guard blocks access, prints error to stderr

---

### Step 8: Commit File Guard implementation

```bash
git add scripts/cm_file_guard.py tests/test_cm_file_guard.py hooks/hooks.json
git commit -m "feat: add PreToolUse File Guard hook

- Blocks Read/Write/Edit/MultiEdit outside repository
- Validates paths before command execution
- Fails closed on errors
- Tests for traversal, outside repo, and safe paths"
```

---

## Task 2: Slash Commands Integration

**Purpose:** Create markdown-based slash commands that wrap existing CLI scripts for better discoverability and context-engineering alignment.

**Files:**
- Create: `templates/commands/cm-save.md`
- Create: `templates/commands/cm-load.md`
- Create: `templates/commands/cm-prune.md`
- Create: `templates/commands/cm-status.md`
- Modify: `scripts/cm_install` (install commands to .claude/commands/)

**Reference:** `.claude/commands/` format from context-engineering-brainstorm.md

---

### Step 1: Create /cm-save slash command

**File:** `templates/commands/cm-save.md`

```markdown
# Save Current Session as Bundle

Save the current session as a named bundle after pruning.

## Usage
```
/cm-save <bundle-name>
```

## Examples
```
/cm-save auth-feature
/cm-save session-backup-2024-01-03
```

## What it does
1. Reads current session from `.claude/context_memory/sessions/current.jsonl`
2. Applies pruning strategy (core files, config, deduplication)
3. Saves pruned events to `.claude/context_memory/bundles/<name>.jsonl`
4. Updates global bundle index

## Options
- `--max-ops N`: Maximum operations to keep (default: 20)
- `--max-bytes N`: Maximum estimated bytes (default: 120KB)

## Implementation
This command wraps the `cm-save` CLI script:

\`\`\`bash
cm-save "$BUNDLE_NAME" --max-ops "$MAX_OPS" --max-bytes "$MAX_BYTES"
\`\`\`

## See also
- `/cm-load` - Load a saved bundle
- `/cm-prune` - Prune current session in-place
- `/cm-status` - Show bundle inventory
```

---

### Step 2: Create /cm-load slash command

**File:** `templates/commands/cm-load.md`

```markdown
# Load Context Bundle

Generate a load plan for restoring context from a saved bundle.

## Usage
```
/cm-load <bundle-name>
```

## Examples
```
/cm-load auth-feature
/cm-load session-backup-2024-01-03
```

## What it does
1. Reads bundle from `.claude/context_memory/bundles/<name>.jsonl`
2. Generates prioritized load plan (config → core → docs → tests)
3. Detects file drift (changes since bundle was created)
4. Displays plan for review before execution

## Load Plan Priority
1. **User prompts/notes** - Intent and context
2. **Config files** - Project configuration
3. **Core files** - Domain logic (src/, lib/, app/)
4. **Docs/Tests** - Supporting materials

## Drift Detection
Shows warnings for:
- Files that have changed since bundle creation
- Files that no longer exist
- New files not in bundle

## Implementation
This command wraps the `cm-load` CLI script:

\`\`\`bash
cm-load "$BUNDLE_NAME" --plan
\`\`\`

## Auto-load (optional)
To automatically execute the load plan:

\`\`\`bash
/cm-load <bundle-name> --execute
\`\`\`

This will generate a bash script and execute it.

## See also
- `/cm-save` - Save current session as bundle
- `/cm-status` - Show bundle inventory
```

---

### Step 3: Create /cm-prune slash command

**File:** `templates/commands/cm-prune.md`

```markdown
# Prune Current Session

Prune the current session in-place to reduce context size.

## Usage
```
/cm-prune [options]
```

## Options
- `--max-ops N`: Maximum operations to keep (default: 20)
- `--max-bytes N`: Maximum estimated bytes (default: 120KB)
- `--keep-patterns PAT`: Patterns to always keep (comma-separated)
- `--dry-run`: Show what would be pruned without modifying

## What it does
1. Reads current session from `.claude/context_memory/sessions/current.jsonl`
2. Applies pruning strategy:
   - Keep user prompts/notes
   - Keep config files
   - Keep core files (src/, lib/, app/)
   - Deduplicate repeated reads
3. Writes pruned session back to current.jsonl

## Categories (in priority order)
1. **User intent** - Prompts, notes (always kept)
2. **Config** - *.json, *.toml, config/ (high priority)
3. **Core** - src/, lib/, app/ (medium priority)
4. **Docs** - docs/, README.md (low priority)
5. **Tests** - tests/, *_test.py (low priority)

## Examples
```
/cm-prune                                    # Default pruning
/cm-prune --max-ops 50                      # Keep 50 operations
/cm-prune --dry-run                         # Preview changes
/cm-prune --keep-patterns "auth/,users/"    # Always keep auth files
```

## See also
- `/cm-save` - Save as bundle instead of in-place
- `/cm-status` - Show current session stats
```

---

### Step 4: Create /cm-status slash command

**File:** `templates/commands/cm-status.md`

```markdown
# Context Memory Status

Display context memory inventory and statistics.

## Usage
```
/cm-status
```

## What it displays
- **Current session:** Operation count, estimated size
- **Bundles:** List of saved bundles with metadata
- **Repository:** Detected repo root and ID
- **Health:** Configuration status

## Example Output
```
Context Memory Status
=====================

Repository: /Users/user/project (abc123...)

Current Session:
  Operations: 47
  Estimated size: 85KB
  Last activity: 2 minutes ago

Bundles (3):
  • auth-feature [2024-01-03] - 12 ops, 15KB
  • session-backup [2024-01-02] - 23 ops, 32KB
  • initial-setup [2024-01-01] - 8 ops, 10KB

Health: ✓ All checks passed
```

## Implementation
This command wraps the `cm-status` CLI script.

## See also
- `/cm-save` - Save current session
- `/cm-load` - Load a bundle
```

---

### Step 5: Update cm_install to install slash commands

**File:** `scripts/cm_install` (modify the install_commands function)

```python
def install_commands(commands_dir: Path) -> None:
    """Install slash commands to .claude/commands/."""
    commands_dir.mkdir(parents=True, exist_ok=True)

    # Copy command templates
    template_dir = Path(__file__).parent.parent / "templates" / "commands"
    if not template_dir.exists():
        print("[WARN] Commands template directory not found")
        return

    for template_file in template_dir.glob("*.md"):
        dest = commands_dir / template_file.name
        shutil.copy(template_file, dest)
        print(f"  ✓ Installed command: /{template_file.stem}")

    print(f"  Commands installed to: {commands_dir}")
```

---

### Step 6: Test slash command installation

```bash
# Create test repo
mkdir -p /tmp/test-commands
cd /tmp/test-commands
git init

# Run install
cm-install

# Verify commands exist
ls -la .claude/commands/

# Should see:
# cm-save.md
# cm-load.md
# cm-prune.md
# cm-status.md
```

**Expected:** Commands copied to `.claude/commands/`

---

### Step 7: Integration test - verify commands work

```bash
# In a Claude Code session:
/cm-status
# Should display status

/cm-save test-bundle
# Should save bundle

/cm-load test-bundle
# Should show load plan
```

**Expected:** All slash commands execute correctly

---

### Step 8: Commit slash commands implementation

```bash
git add templates/commands/ scripts/cm_install
git commit -m "feat: add slash commands for context-memory operations

- Add /cm-save for saving bundles
- Add /cm-load for loading bundles with plans
- Add /cm-prune for in-place pruning
- Add /cm-status for inventory display
- Update cm_install to install commands to .claude/commands/"
```

---

## Task 3: Enhanced /load-bundle with Interactive Prompts

**Purpose:** Improve /cm-load with interactive prompts and better UX.

**Files:**
- Modify: `scripts/cm_load` (add interactive mode)
- Modify: `src/domain/plan.py` (add prompt generation)
- Create: `tests/test_cm_load_interactive.py`

---

### Step 1: Write test for interactive load prompt

**File:** `tests/test_cm_load_interactive.py`

```python
"""Tests for interactive cm-load functionality."""
import pytest
from pathlib import Path
from src.domain.plan import LoadPlan, LoadStep


def test_load_plan_generates_user_prompt(tmp_path):
    """Test that load plan generates helpful user prompt."""
    events = [
        create_event(operation="prompt", prompt="/cm-save my-feature"),
        create_event(operation="read", file_path="config.json"),
        create_event(operation="read", file_path="src/auth.py"),
    ]

    plan = build_load_plan(events, "my-feature")

    prompt = plan.to_user_prompt()

    assert "my-feature" in prompt
    assert "3 files" in prompt
    assert "config.json" in prompt
    assert "src/auth.py" in prompt


def test_load_plan_includes_drift_warnings(tmp_path):
    """Test that drift warnings are included in prompt."""
    events = [
        create_event(operation="read", file_path="src/auth.py", sha256="abc123"),
    ]

    # Simulate file has changed
    plan = build_load_plan(events, "my-feature")
    plan.warnings.append("File drifted: src/auth.py")

    prompt = plan.to_user_prompt()

    assert "drift" in prompt.lower()
    assert "src/auth.py" in prompt
```

---

### Step 2: Add user prompt generation to LoadPlan

**File:** `src/domain/plan.py` (modify LoadPlan class)

```python
@dataclass
class LoadPlan:
    """Plan for loading a bundle."""

    # ... existing fields ...

    def to_user_prompt(self) -> str:
        """Generate a helpful prompt for the user."""
        lines = [
            f"# Load Plan: {self.bundle_name}",
            "",
            f"This bundle contains **{self.total_files} files** (~{self.total_bytes_est // 1024}KB)",
            "",
        ]

        if self.warnings:
            lines.append("## ⚠️ Warnings")
            for warning in self.warnings:
                lines.append(f"- {warning}")
            lines.append("")

        lines.append("## Files to Load")
        lines.append("")
        lines.append("The following files will be loaded in priority order:")
        lines.append("")

        # Group by priority
        by_priority = self.group_by_priority()
        for priority, steps in by_priority.items():
            lines.append(f"### {priority}")
            for step in steps:
                if step.action == "READ":
                    lines.append(f"- `{step.file_path}`")
            lines.append("")

        lines.append("## Next Steps")
        lines.append("")
        lines.append("Would you like to:")
        lines.append("1. Generate and execute the load script automatically")
        lines.append("2. Generate the script for manual review")
        lines.append("3. Cancel")
        lines.append("")

        return "\n".join(lines)

    def group_by_priority(self) -> dict[str, list[LoadStep]]:
        """Group load steps by priority category."""
        groups = {
            "User Intent": [],
            "Configuration": [],
            "Core Files": [],
            "Documentation": [],
            "Tests": [],
        }

        for step in self.steps:
            if step.action != "READ":
                continue

            path = step.file_path or ""
            if step.meta.get("category") == "prompt":
                groups["User Intent"].append(step)
            elif any(p in path for p in ["config", ".json", ".toml"]):
                groups["Configuration"].append(step)
            elif any(p in path for p in ["src/", "lib/", "app/"]):
                groups["Core Files"].append(step)
            elif any(p in path for p in ["docs/", "README"]):
                groups["Documentation"].append(step)
            elif "test" in path:
                groups["Tests"].append(step)
            else:
                groups["Core Files"].append(step)

        return {k: v for k, v in groups.items() if v}
```

---

### Step 3: Add interactive mode to cm_load

**File:** `scripts/cm_load` (add interactive option)

```python
def interactive_mode(plan: LoadPlan) -> None:
    """Run interactive load with user prompts."""
    # Display the plan
    print(plan.to_user_prompt())

    # Ask user what to do
    while True:
        response = input("\nChoose option [1/2/3]: ").strip()

        if response == "1":
            # Auto-execute
            print("\n🔄 Generating and executing load script...")
            script = generate_load_script(plan)
            result = subprocess.run(["bash"], input=script.encode(), capture_output=True)

            if result.returncode == 0:
                print("✅ Bundle loaded successfully")
            else:
                print(f"❌ Error loading bundle: {result.stderr.decode()}")
            break

        elif response == "2":
            # Generate for review
            script_path = Path.cwd() / "load_bundle.sh"
            script = generate_load_script(plan)
            script_path.write_text(script)
            print(f"\n📝 Load script generated: {script_path}")
            print(f"   Review and execute: bash {script_path}")
            break

        elif response == "3":
            print("\n❌ Cancelled")
            break

        else:
            print("Invalid option. Choose 1, 2, or 3.")


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Load context bundle"
    )
    parser.add_argument("bundle", help="Bundle name")
    parser.add_argument("--interactive", "-i", action="store_true",
                       help="Interactive mode with prompts")
    parser.add_argument("--execute", action="store_true",
                       help="Auto-execute load plan")
    # ... existing args ...

    args = parser.parse_args()

    # ... load bundle and build plan ...

    if args.interactive:
        interactive_mode(plan)
    elif args.execute:
        # Auto-execute
        script = generate_load_script(plan)
        subprocess.run(["bash"], input=script.encode())
    else:
        # Default: show plan
        print(plan.to_user_prompt())
```

---

### Step 4: Test interactive mode

```bash
# Create a test bundle
echo "test" > /tmp/test.txt
cm-save test-bundle

# Load interactively
cm-load test-bundle --interactive
```

**Expected:** Shows prompt, accepts user input, executes accordingly

---

### Step 5: Commit enhanced /cm-load

```bash
git add scripts/cm_load src/domain/plan.py tests/test_cm_load_interactive.py
git commit -m "feat: add interactive mode to cm-load

- Generate user-friendly prompts
- Show drift warnings prominently
- Interactive choice: auto-execute, generate script, or cancel
- Group files by priority in display"
```

---

## Task 4: Document Precommit Approach for Secret Sanitization

**Purpose:** Document using precommit hooks for secret detection instead of sanitizing in the PostToolUse hook.

**Files:**
- Create: `.pre-commit-config.yaml` (template)
- Create: `docs/precommit-secrets.md`

---

### Step 1: Create precommit configuration template

**File:** `.pre-commit-config.yaml` (template)

```yaml
# Precommit hooks for context-memory plugin
# Install: pre-commit install
# Run: pre-commit run --all-files

repos:
  # Detect secrets in committed files
  - repo: https://github.com/Yelp/detect-secrets
    rev: v1.4.0
    hooks:
      - id: detect-secrets
        args: [--baseline, .secrets.baseline]
        exclude: package.lock.json

  # Prevent committing large JSONL files
  - repo: local
    hooks:
      - id: check-jsonl-size
        name: Check JSONL file size
        entry: scripts/check-jsonl-size
        language: script
        files: \.jsonl$
```

---

### Step 2: Create secret detection documentation

**File:** `docs/precommit-secrets.md`

```markdown
# Secret Sanitization Strategy

## Approach: Precommit Hooks (Not PostToolUse)

We use **precommit hooks** for secret detection instead of sanitizing in the PostToolUse hook for these reasons:

1. ** Earlier Detection** - Secrets caught before commit, not after logging
2. ** Standard Tooling** - Leverages existing secret detection tools
3. ** Less Complexity** - No need to parse/modify tool outputs
4. ** Developer-Facing** - Direct feedback to developer committing

## Installation

```bash
# Install precommit framework
pip install pre-commit

# Install hooks
pre-commit install
```

## Usage

```bash
# Run on all files
pre-commit run --all-files

# Run on staged files (automatic on commit)
git commit
```

## Configuration

The `.pre-commit-config.yaml` file configures:

1. **detect-secrets** - Scans for API keys, tokens, passwords
2. **check-jsonl-size** - Prevents committing large session logs

## Excluding Context Memory Logs

Context memory logs should **not be committed**:

```bash
# .gitignore
.claude/context_memory/sessions/
.claude/context_memory/bundles/
```

This prevents secrets from ever entering the repository.

## Alternative: Log Sanitization (Not Implemented)

If PostToolUse sanitization is needed in the future, see:

- `docs/context-engineering-brainstorm.md` section 5.2
- Pattern: `sanitize_payload()` function in hook
```

---

### Step 3: Create JSONL size checker script

**File:** `scripts/check-jsonl-size`

```bash
#!/usr/bin/env bash
# Prevent committing large JSONL files (>1MB)

MAX_SIZE=1048576  # 1MB

for file in "$@"; do
    if [ -f "$file" ]; then
        size=$(stat -f%z "$file" 2>/dev/null || stat -c%s "$file" 2>/dev/null)
        if [ "$size" -gt "$MAX_SIZE" ]; then
            echo "ERROR: $file is too large ($(echo "scale=1; $size/1024/1024" | bc)MB)"
            echo "Max allowed: 1MB"
            echo "Context memory logs should not be committed."
            exit 1
        fi
    fi
done
```

---

### Step 4: Commit precommit documentation

```bash
git add .pre-commit-config.yaml docs/precommit-secrets.md scripts/check-jsonl-size
git commit -m "docs: add precommit strategy for secret detection

- Use precommit hooks instead of PostToolUse sanitization
- Configure detect-secrets for API key detection
- Add JSONL size checker to prevent large log commits
- Document rationale for precommit approach"
```

---

## Testing Checklist

After implementing all tasks, verify:

- [ ] File Guard blocks paths outside repo
- [ ] File Guard allows paths inside repo
- [ ] File Guard blocks path traversal attempts
- [ ] Slash commands install to `.claude/commands/`
- [ ] `/cm-status` displays correctly
- [ ] `/cm-save` creates bundles
- [ ] `/cm-load` shows load plans
- [ ] `/cm-prune` prunes sessions
- [ ] Interactive mode prompts user correctly
- [ ] Precommit hooks detect secrets
- [ ] All tests pass: `pytest -v`

---

## Rollback Plan

If any component fails:

1. **File Guard:** Remove from `hooks.json`, rollback to PostToolUse-only validation
2. **Slash Commands:** Delete `.claude/commands/` entries, continue using CLI scripts
3. **Interactive Mode:** Use `--execute` flag or manual script generation
4. **Precommit:** Skip precommit setup, rely on `.gitignore` for logs

---

**End of Implementation Plan**

**Next Step:** Choose execution approach (subagent-driven in this session, or parallel session with executing-plans).
