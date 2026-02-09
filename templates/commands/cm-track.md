---
description: Track specific files in current context session
argument-hint: <file1.md> <file2.md> ...
allowed-tools: Read, Bash
---

# Track Files in Context

Manually track specific files by reading them. Each Read operation will be captured by the context memory hook.

## Usage

```
/cm-track CLAUDE.md README.md src/main.py
```

## Instructions

1. Read each specified file using the Read tool
2. The hook will automatically capture each Read operation
3. Use `/cm-context` to verify what was tracked
4. Use `/cm-save <name>` to save a pruned bundle

## Workflow

```bash
# Read files to track them
Read tool for each file

# Verify tracking
/cm-context

# Save bundle
/cm-save feature-xyz
```

## Notes

- Only files Read during this command will be tracked
- Agent-initiated Read operations might not trigger hooks
- Use this command when you want to explicitly capture context
