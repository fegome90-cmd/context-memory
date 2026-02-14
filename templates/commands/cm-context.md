---
description: Show summary of current context session (top operations)
argument-hint: [--top N]
allowed-tools: Bash, Read
---

# Current Context Summary

Shows a summary of the active tracking session with top operations.

## Variables

- `--top N`: Show top N operations (default: 10)

## Instructions

Display the current session's tracked operations, showing:
- Total operation count
- Top files by read frequency
- Recent user prompts
- Distribution by operation type

## Workflow

```bash
# Validate environment
if [ -z "${CLAUDE_PLUGIN_ROOT:-}" ]; then
    echo "Error: CLAUDE_PLUGIN_ROOT environment variable is not set."
    echo "This command requires Claude Code's plugin environment."
    echo "Please run this command from within Claude Code."
    exit 1
fi

# Read current.jsonl and summarize
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/cm_status.py" --verbose
```

Or read directly:
```bash
# Show last 20 lines of current session
tail -n 20 .claude/context_memory/sessions/current.jsonl
```

Use this to:
- Preview what would be included in a bundle
- Check tracking coverage
- Identify which files are being accessed most
