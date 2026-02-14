# Fix Context Memory Plugin Hooks - Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Fix PostToolUse hooks not firing for context-memory plugin by changing from absolute paths to `${CLAUDE_PLUGIN_ROOT}` environment variable.

**Architecture:** Local plugins must use `${CLAUDE_PLUGIN_ROOT}` in hook command paths, just like official plugins. Claude Code expands this variable at runtime to the plugin's root directory. Absolute paths are blocked for security reasons.

**Tech Stack:** Python 3.10+, Claude Code Plugin System, JSON hooks configuration

**Created:** 2026-01-03
**Status:** Ready for implementation

---

## ROOT CAUSE (from systematic debugging)

**Problem:** PostToolUse hooks never execute for local plugins
- Debug log `/tmp/cm_hook_debug.log` remains empty
- No events captured in `.claude/context_memory/sessions/current.jsonl`
- Script works manually but not when called by Claude Code

**Root Cause:** Local plugins use **absolute paths** in hooks.json:
```json
"command": "python3 /Users/felipe_gonzalez/.claude/plugins/context-memory/scripts/cm_track_operation.py"
```

**Solution:** Use `${CLAUDE_PLUGIN_ROOT}` like official plugins:
```json
"command": "python3 ${CLAUDE_PLUGIN_ROOT}/scripts/cm_track_operation.py"
```

---

## Task 1: Update hooks.json to use CLAUDE_PLUGIN_ROOT

**Files:**
- Modify: `~/.claude/plugins/context-memory/hooks/hooks.json`

**Step 1: Read current hooks.json**

Run: `cat ~/.claude/plugins/context-memory/hooks/hooks.json`
Expected: Shows current configuration with absolute path

**Step 2: Edit hooks.json to use CLAUDE_PLUGIN_ROOT**

Replace the absolute path with `${CLAUDE_PLUGIN_ROOT}`:

```json
{
  "description": "Context Memory Plugin - Track Read/Write/Edit/MultiEdit operations",
  "hooks": {
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
}
```

**Step 3: Verify the change**

Run: `cat ~/.claude/plugins/context-memory/hooks/hooks.json | grep CLAUDE_PLUGIN_ROOT`
Expected: Shows the new command with `${CLAUDE_PLUGIN_ROOT}`

**Step 4: Clear debug log for fresh test**

Run: `rm -f /tmp/cm_hook_debug.log && echo "Debug log cleared"`
Expected: No error, log file deleted

---

## Task 2: Update plugin registration timestamp

**Files:**
- Modify: `~/.claude/plugins/installed_plugins.json`

**Rationale:** Claude Code snapshots plugins at startup. We need to touch the timestamp to force a reload.

**Step 1: Read current registration**

Run: `cat ~/.claude/plugins/installed_plugins.json | grep -A5 context-memory`
Expected: Shows current context-memory registration

**Step 2: Update timestamp in installed_plugins.json**

Change the `lastUpdated` field to current timestamp (ISO 8601 format):

```json
"context-memory@local": [{
  "scope": "user",
  "installPath": "/Users/felipe_gonzalez/.claude/plugins/context-memory",
  "version": "1.0.0",
  "installedAt": "2026-01-02T20:21:00.000Z",
  "lastUpdated": "2026-01-03T12:00:00.000Z",
  "isLocal": true
}]
```

Use current date/time when editing.

**Step 3: Verify the change**

Run: `cat ~/.claude/plugins/installed_plugins.json | grep -A5 context-memory`
Expected: Shows new timestamp

---

## Task 3: Restart Claude Code to reload plugins

**Rationale:** Claude Code loads plugins at startup and takes a snapshot. Changes require restart.

**Step 1: Exit Claude Code completely**

Quit the Claude Code application entirely (Cmd+Q or close all windows)

**Step 2: Wait 2 seconds**

Count: "1, 2" to ensure clean exit

**Step 3: Restart Claude Code**

Open Claude Code application

**Step 4: Verify plugin is loaded**

The plugin should appear in the plugins list automatically

---

## Task 4: Test that hooks are now firing

**Rationale:** Verify the fix works by triggering a Read operation and checking the debug log.

**Step 1: Trigger a Read operation**

Use the Read tool to read any file:
```
Read: /Users/felipe_gonzalez/.claude/plugins/context-memory/README.md
```

**Step 2: Check if debug log was created**

Run: `cat /tmp/cm_hook_debug.log`
Expected: Should see entries like:
```
[12345.67] cm_track_operation.py called
  CLAUDE_TOOL_NAME=Read
  CLAUDE_PROJECT_DIR=/Users/felipe_gonzalez/Developer/raycast_ext
```

**Step 3: If log exists, hooks are working!**

Expected output: Log file exists with timestamp and environment variables

**Step 4: Verify events are being captured**

Run: `cat ~/.claude/context_memory/sessions/current.jsonl | wc -l`
Expected: Should show > 0 lines (events are being captured)

---

## Task 5: Clean up test-hook plugin (optional)

**Files:**
- Delete: `~/.claude/plugins/test-hook/`
- Modify: `~/.claude/plugins/installed_plugins.json`

**Rationale:** test-hook was created for debugging and is no longer needed.

**Step 1: Remove test-hook directory**

Run: `rm -rf ~/.claude/plugins/test-hook/`
Expected: Directory removed, no error

**Step 2: Remove test-hook from installed_plugins.json**

Delete the entire `"test-hook@local"` entry from installed_plugins.json:

```json
"test-hook@local": [...],  // DELETE THIS ENTIRE ENTRY
```

**Step 3: Verify removal**

Run: `cat ~/.claude/plugins/installed_plugins.json | grep test-hook`
Expected: No results (entry removed)

---

## Task 6: Document the fix

**Files:**
- Modify: `~/.claude/plugins/context-memory/docs/audit/hook-debugging-prompt.md`

**Step 1: Add resolution section to audit document**

Append to the end of `hook-debugging-prompt.md`:

```markdown
## Resolution (2026-01-03)

### Root Cause
Local plugins were using **absolute paths** in hooks.json instead of `${CLAUDE_PLUGIN_ROOT}`.

### Fix Applied
Changed from:
```json
"command": "python3 /Users/felipe_gonzalez/.claude/plugins/context-memory/scripts/cm_track_operation.py"
```

To:
```json
"command": "python3 ${CLAUDE_PLUGIN_ROOT}/scripts/cm_track_operation.py"
```

### Verification
- Post restart, hooks now fire correctly
- Debug log shows CLAUDE_TOOL_NAME and CLAUDE_PROJECT_DIR
- Events are captured in current.jsonl

### Lessons Learned
1. **Always use `${CLAUDE_PLUGIN_ROOT}`** in plugin hook commands
2. **Never use absolute paths** - they don't work with Claude Code's security model
3. **Match official plugin structure** - they're the reference implementation
4. **Restart required** - plugin changes need Claude Code restart to take effect
```

**Step 2: Update README.md with troubleshooting**

Add to `~/.claude/plugins/context-memory/README.md`:

```markdown
## Troubleshooting

### Hooks not firing

If you don't see events being captured:

1. Check hooks.json uses `${CLAUDE_PLUGIN_ROOT}`:
   ```bash
   cat ~/.claude/plugins/context-memory/hooks/hooks.json | grep CLAUDE_PLUGIN_ROOT
   ```

2. Restart Claude Code completely (plugins are snapshotted at startup)

3. Check debug log:
   ```bash
   cat /tmp/cm_hook_debug.log
   ```

4. Verify plugin is registered:
   ```bash
   cat ~/.claude/plugins/installed_plugins.json | grep context-memory
   ```
```

---

## Verification Checklist

After completing all tasks, verify:

- [ ] hooks.json uses `${CLAUDE_PLUGIN_ROOT}` instead of absolute path
- [ ] `/tmp/cm_hook_debug.log` exists and has entries after Read operations
- [ ] `current.jsonl` has captured events
- [ ] Plugin restart was performed
- [ ] Documentation updated with root cause and fix

---

## Expected Result

After applying this fix:

1. **Hooks fire on every Read/Write/Edit/MultiEdit operation**
2. **Debug log shows**: `CLAUDE_TOOL_NAME=Read`, `CLAUDE_PROJECT_DIR=/path/to/project`
3. **Events captured**: `current.jsonl` grows with each operation
4. **Context tracking works**: `/cm-init`, `/cm-prune`, `/cm-load` commands function

---

## Rollback Plan (if something goes wrong)

If hooks still don't work after this fix:

1. **Verify CLAUDE_PLUGIN_ROOT is set**: Add debug logging to the hook script to print `$CLAUDE_PLUGIN_ROOT`
2. **Check file permissions**: Ensure `chmod +x scripts/cm_track_operation.py`
3. **Try official plugin location**: Move plugin to `~/.claude/plugins/cache/claude-plugins-official/context-memory/`
4. **Reinstall plugin**: Remove from installed_plugins.json and re-add
5. **Check Claude Code version**: Ensure you're on latest version that supports local plugins

---

## References

- **Debugging prompt**: `docs/audit/hook-debugging-prompt.md`
- **Hook system reference**: Indy Dev Dan's "Elite Context Engineering" video
- **Working example**: `~/.claude/plugins/cache/claude-plugins-official/hookify/*/hooks/hooks.json`
- **Systematic debugging**: Used superpowers:systematic-debugging to find root cause
