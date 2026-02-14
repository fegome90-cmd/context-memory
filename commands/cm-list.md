---
description: List all context bundles across all repositories
argument-hint: [--repo-id REPO_ID]
allowed-tools: Bash
---

# List Context Bundles

List all available context bundles across all repositories.

## Variables

- `--repo-id REPO_ID`: Filter bundles by repository ID (optional)

## Instructions

Execute the cm_list.py script to display all bundles:
1. Read global index from plugin directory
2. Group bundles by repository
3. Show bundle name, ops, size, and creation date

## Workflow

```bash
# List all bundles
python3 ~/.claude/plugins/context-memory/scripts/cm_list.py

# Filter by specific repo
python3 ~/.claude/plugins/context-memory/scripts/cm_list.py --repo-id 0f89290791
```

## Output

```
======================================================================
Context Memory Bundles
======================================================================
Total: 6 bundle(s) across 2 repo(s)

📁 Repo: 0f89290791
   Path: /Users/felipe_gonzalez
   Branch: master
   Bundles: 5

   • init
     Ops: 3, Size: 3 KB, Created: 2026-01-03 16:38
   • youtube-scraper-refactor-session
     Ops: 3, Size: 3 KB, Created: 2026-01-03 16:30
   ...
```

## Use Cases

- **Discover bundles**: Find what context is available
- **Cross-repo search**: See bundles from all projects
- **Filter by repo**: Narrow down to specific repository

## Tips

- Bundles are sorted by creation date (newest first)
- Use bundle names with `/cm-load` to rehydrate
- Repository ID is shown for reference

## See Also

- `/cm-load` - Load a specific bundle
- `/cm-save` - Save a new bundle
- `/cm-status` - Show current session status
