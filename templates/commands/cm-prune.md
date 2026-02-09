---
description: Prune current session (with or without saving)
argument-hint: [--max-ops N] [--max-bytes N] [--in-place]
allowed-tools: Bash, Read
---

# Prune Current Session

Prune the current tracking session to reduce operations while
keeping the most important context.

## Variables

- `--max-ops N`: Maximum operations to keep (default: 20)
- `--max-bytes N`: Maximum estimated bytes (default: 120,000)
- `--in-place`: Modify current.jsonl directly (creates backup)

## Instructions

Apply pruning strategy to current.jsonl:
1. Deduplicate reads (keep last per file)
2. Prioritize by importance (config > core > docs > tests)
3. Apply budget constraints (ops + bytes)
4. Show pruning report

## Workflow

```bash
# Validate environment
if [ -z "${CLAUDE_PLUGIN_ROOT:-}" ]; then
    echo "Error: CLAUDE_PLUGIN_ROOT environment variable is not set."
    echo "This command requires Claude Code's plugin environment."
    echo "Please run this command from within Claude Code."
    exit 1
fi

# Prune to separate file (preview)
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/cm_prune.py"

# Prune with tighter budget
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/cm_prune.py" --max-ops 10

# Prune and replace current.jsonl
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/cm_prune.py" --in-place
```

## Output

```
Pruned session:
  Events: 47 → 15
  Removed: 32
  Reasons: {'dedupe': 20, 'budget': 12}
  Final tags: {'core': 8, 'config': 3, 'doc': 2, 'test': 2}
  Estimated bytes: 45,234

✓ Pruned session saved to: current.pruned.jsonl
  To replace current.jsonl:
    mv current.pruned.jsonl current.jsonl
```

## When to Use

- **Before `/cm-save`**: Preview what the bundle will contain
- **To reduce tracking noise**: Clean up accumulated operations
- **To tune budget**: Test different max-ops values

## Tips

- Run without `--in-place` first to preview
- Check the "Final tags" to see what's being kept
- Use `/cm-context` to see what's in the current session
- If satisfied with prune, use `/cm-save` to persist

## Caution

Using `--in-place` modifies current.jsonl directly:
- Creates backup as current.jsonl.bak
- Removes events permanently (except in backup)
- Cannot undo after deleting backup

## See Also

- `/cm-save` - Prune and save as bundle
- `/cm-context` - Preview current session
