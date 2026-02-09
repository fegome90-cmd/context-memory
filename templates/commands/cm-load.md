---
description: Load and display a context bundle (rehydration plan)
argument-hint: <bundle-name> [--execute]
allowed-tools: Bash, Read, Write, MultiEdit, Grep, Glob
---

# Load Context Bundle

Display the rehydration plan for a saved bundle, optionally executing
file reads to restore context.

## Variables

- `bundle-name`: Name of bundle to load (required)
- `--execute`: Actually read and display file contents

## Instructions

Load a context bundle and show how to rebuild the session:
1. Reads the bundle from bundles/<name>.jsonl
2. Builds a load plan (which files to read, in what order)
3. Displays the plan with reasoning
4. Optionally executes reads to show actual content

## Workflow

```bash
# Validate environment
if [ -z "${CLAUDE_PLUGIN_ROOT:-}" ]; then
    echo "Error: CLAUDE_PLUGIN_ROOT environment variable is not set."
    echo "This command requires Claude Code's plugin environment."
    echo "Please run this command from within Claude Code."
    exit 1
fi

# Show load plan (what would be read)
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/cm_load.py" my-feature

# Execute and display file contents
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/cm_load.py" my-feature --execute
```

## Load Plan Output

```
📦 Load Plan: my-feature
   Files to read: 8
   Total steps: 12
   Warnings: 0

📋 Steps:
   1. 💭 Inject: Working on pricing refactor (user intent)
   2. 📖 Read: README.md (project overview)
   3. 📖 Read: pyproject.toml (configuration)
   4. 📖 Read: src/domain/events.py (core domain)
   5. 📖 Read: src/domain/pricing.py (core domain)
   6. 📖 Read: tests/test_pricing.py (tests)
   ...
```

## Drift Detection

If files have SHA256 hashes stored, the load will warn about drift:
```
⚠️  File changed since bundle: src/pricing.py
  Bundle: 1a2b3c4d5e...
  Current: 6f7g8h9i0j...
```

## Tips

- Use `--execute` to actually see file contents
- Review the plan before rehydrating to ensure key files are included
- Drift warnings help identify what changed since the bundle
- Load in a new Claude Code window to continue work with fresh context

## See Also

- `/cm-save` - Create bundles
- `/cm-status` - List available bundles
