---
description: Prune current session and save as a named bundle
argument-hint: <bundle-name> [--max-ops N] [--max-bytes N]
allowed-tools: Bash, Read, Write
---

# Save Context Bundle

Prune the current session and save as a compact, rehydratable bundle.

## Variables

- `bundle-name`: Name for the bundle (required)
- `--max-ops N`: Maximum operations to keep (default: 20)
- `--max-bytes N`: Maximum estimated bytes (default: 120,000)

## Instructions

Create a pruned context bundle that captures the essential operations
from the current session. The bundle is optimized for:
- Compactness (fewer operations = less context)
- Representativeness (keeps important files)
- Rehydratability (enough info to restore context)

## Workflow

```bash
# Set default plugin root if not already set
CLAUDE_PLUGIN_ROOT="${CLAUDE_PLUGIN_ROOT:-$HOME/.claude/plugins/context-memory}"

# Save bundle with default settings (20 ops max)
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/cm_save.py" my-feature

# Save with tighter budget
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/cm_save.py" my-feature --max-ops 10

# Save with larger budget
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/cm_save.py" my-feature --max-ops 50 --max-bytes 250000
```

The script will:
1. Read current.jsonl
2. Apply pruning strategy (dedupe, prioritize, budget)
3. Save to bundles/<name>.jsonl
4. Update global index
5. Print summary of what was saved

## Output

```
✓ Bundle saved: my-feature
  Events: 47 → 15
  Estimated bytes: 45,234
  Tags: {'core': 8, 'config': 3, 'doc': 2, 'test': 2}
```

## Tips

- Save at natural breakpoints (feature complete, bug fixed, etc.)
- Use descriptive names that reflect the work done
- Check the summary to verify important files were kept
- Smaller bundles (10-15 ops) rehydrate faster

## See Also

- `/cm-prune` - Prune without saving
- `/cm-load` - Rehydrate from a bundle
