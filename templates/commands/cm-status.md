---
description: Show context memory status for current repository
argument-hint: [--verbose]
allowed-tools: Bash, Read
---

# Context Memory Status

Shows bundle statistics, current session info, and recent history.

## Variables

None (uses current directory)

## Instructions

Display context memory status including:
- Current repository info (name, ID, branch)
- Current session event count and size
- Saved bundles with metadata
- Recent bundles from global index

## Workflow

```bash
# Validate environment
if [ -z "${CLAUDE_PLUGIN_ROOT:-}" ]; then
    echo "Error: CLAUDE_PLUGIN_ROOT environment variable is not set."
    echo "This command requires Claude Code's plugin environment."
    echo "Please run this command from within Claude Code."
    exit 1
fi

# Show status
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/cm_status.py"
```

The command outputs:
- Repository identification
- Current session statistics
- List of saved bundles
- Recent global entries

Use this to:
- Check what bundles are available
- See session size before pruning
- Verify tracking is working
