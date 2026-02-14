# Context Memory Troubleshooting Guide

This guide helps diagnose and fix issues with the context-memory plugin for Claude Code.

## Quick Debug Commands

### Enable Debug Logging

```bash
export CM_DEBUG=1
```

After enabling, trigger a file operation and check the log:

```bash
cat /tmp/cm_hook_debug.log
```

### Manual Hook Test

Test the hook directly without Claude Code:

```bash
echo '{"tool_name":"Read","tool_input":{"file_path":"/path/to/file.py"}}' | \
  python3 ~/.claude/plugins/context-memory/scripts/cm_track_operation.py
```

### Check Hook Configuration

```bash
# Verify settings.local.json exists (NOT hooks.json)
cat .claude/settings.local.json

# Check PostToolUse hook is registered
grep -A10 "PostToolUse" .claude/settings.local.json

# Verify the script path is correct
grep "command" .claude/settings.local.json
```

### Verify Storage

```bash
# Check session log is growing
tail -f .claude/context_memory/sessions/current.jsonl

# List saved bundles
ls -la .claude/context_memory/bundles/

# Check bundle contents
head -20 .claude/context_memory/bundles/*.jsonl
```

---

## Bug #1: Hook Not Tracking - `hooks.json` Ignored

### Problem

The plugin creates `.claude/hooks.json` but Claude Code doesn't load the hook.

### Root Cause

**Claude Code reads hooks from `settings.json` files, NOT from standalone `hooks.json` files.**

The plugin has two hook files:
1. **Plugin-level**: `hooks/hooks.json` - Auto-loaded when plugin is enabled (uses `${CLAUDE_PLUGIN_ROOT}`)
2. **Project-level**: `.claude/settings.local.json` - Created by install script (uses absolute paths)

Only project-level hooks in `settings.json` format are recognized by Claude Code.

### Solution

**Version**: Fixed in v1.0.2

Re-run the installer to create the correct file:

```bash
cd /path/to/your/project
python3 ~/.claude/plugins/context-memory/scripts/cm_install.py
```

This creates `.claude/settings.local.json` with the correct format:

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

### Verification

```bash
# Check that settings.local.json exists (correct)
ls -la .claude/settings.local.json

# Verify the hook structure
jq '.hooks.PostToolUse' .claude/settings.local.json

# Trigger a Read operation and check the log
tail -f .claude/context_memory/sessions/current.jsonl
```

### Expected Output

After triggering a file operation, you should see new lines in `current.jsonl`:

```jsonl
{"operation":"read","file_path":"src/app.py","ts":1704067200,"tool":"Read","source":"hook"}
```

### Common Mistakes

| Mistake | Symptom | Fix |
|---------|---------|-----|
| Editing `.claude/hooks.json` | Hook doesn't fire | Edit `.claude/settings.local.json` instead |
| Using relative path in command | Hook not found | Use absolute path to script |
| Missing `hooks` wrapper | Invalid format | Wrap in `{"hooks": {...}}` |

---

## Bug #2: Repository Detection Fails

### Problem

Hook reports "Not in a git repo" even though you're working in a valid repository.

### Root Cause

**Claude Code runs hooks with `cwd` set to its internal directory, NOT the project directory.**

Original code used `detect_repo()` which relies on `Path.cwd()`. When the hook runs:
- `cwd` = `/internal/claude/code/dir` (not your project)
- `detect_repo()` searches upward from wrong location
- Fails to find `.git` directory

### Solution

**Version**: Fixed in v1.0.2

The fix introduces `detect_repo_from_file_path()` which:
1. Extracts the absolute file path from tool input
2. Walks up the directory tree from that file location
3. Finds the repository root correctly

No action needed - upgrade to v1.0.2+.

### Code Flow Comparison

**Old (Broken)**:
```python
# Hook runs with cwd = /internal/claude/code/dir
repo_info = detect_repo()  # Uses Path.cwd()
# Searches: /internal -> / → fails
```

**New (Fixed)**:
```python
# Extract absolute file path from tool input
file_path = Path("/Users/user/project/src/app.py")
repo_info = detect_repo_from_file_path(file_path)
# Searches: /Users/user/project/src → /Users/user/project → finds .git
```

### Verification

```bash
# Enable debug logging
export CM_DEBUG=1

# Trigger a Read operation in Claude Code

# Check which detection method was used
cat /tmp/cm_hook_debug.log | grep "Repo detected"

# Should see:
# "Repo detected from file_path: /Users/user/project"
```

### Debug Output Examples

**Working correctly (v1.0.2+)**:
```
DEBUG:context_memory.cm_track_operation:Tool: Read
DEBUG:context_memory.cm_track_operation:Repo detected from file_path: /Users/user/project
DEBUG:context_memory.cm_track_operation:Tracking Read on src/app.py
```

**Broken (old version)**:
```
DEBUG:context_memory.cm_track_operation:Tool: Read
DEBUG:context_memory.cm_track_operation:Repo detected from cwd: /internal/claude/code/dir
DEBUG:context_memory.cm_track_operation:Not in a git repo - hook disabled
```

### Edge Cases

| Scenario | Behavior |
|----------|----------|
| Absolute path | Uses `detect_repo_from_file_path()` (primary) |
| Relative path | Falls back to `detect_repo()` (cwd-based) |
| Outside git repo | Hook disabled (correct) |
| Nested git repos | Detects innermost repo (file's repo) |

---

## Bug #3: macOS Symlink Validation Fails

### Problem

On macOS, path validation errors occur when working in `/tmp` directory or other system directories that use symlinks.

### Root Cause

**macOS uses symlinks for system directories: `/tmp` → `/private/tmp`**

Original code rejected ALL symlinks as a security measure:
- Checked every path component
- Rejected paths if ANY component was a symlink
- False positives on legitimate system symlinks

### Solution

**Version**: Fixed in v1.0.2

The fix uses a layered approach:
1. **Prefix resolution**: Resolve full path for containment check (handles system symlinks)
2. **Component validation**: Check each path component INSIDE the repo for symlinks

This allows system-level symlinks while blocking internal symlinks that could escape containment.

### Code Comparison

**Old (Broken)**:
```python
# Reject ALL symlinks anywhere in the path
resolved = abs_path.resolve()
for part in resolved.parents:
    if part.is_symlink():
        raise ValueError("Symlinks not allowed")
# /tmp/file.py rejected because /tmp is a symlink
```

**New (Fixed)**:
```python
# Resolve for containment check (handles /tmp → /private/tmp)
resolved_abs = abs_path.resolve()
rel_path = resolved_abs.relative_to(resolved_root)

# Check for symlinks INSIDE the repo only
current = resolved_root
for part in rel_path.parts:
    current = current / part
    if current.is_symlink():
        raise ValueError("Symlinks not allowed in path")
# /tmp allowed (system), but repo/internal-link rejected
```

### Verification

```bash
# Test with a /tmp file on macOS
export CM_DEBUG=1
echo '{"tool_name":"Read","tool_input":{"file_path":"/tmp/test.py"}}' | \
  python3 ~/.claude/plugins/context-memory/scripts/cm_track_operation.py

# Check for symlink errors
cat /tmp/cm_hook_debug.log | grep -i symlink
```

### Behavior Table

| Path | Old Behavior | New Behavior | Reason |
|------|-------------|--------------|--------|
| `/tmp/file.py` (repo at `/private/tmp`) | ❌ Rejected | ✅ Allowed | System symlink |
| `/repo/src/link.py` → `/etc/passwd` | ❌ Rejected | ❌ Rejected | Security (escape) |
| `/repo/docs/readme.md` | ✅ Allowed | ✅ Allowed | Normal file |
| `/repo/src/link.py` → `../other/file.py` | ❌ Rejected | ❌ Rejected | Security (escape) |

### Security Considerations

**Why allow system symlinks?**
- macOS uses them for standard directories (`/tmp`, `/var`)
- They're outside the repo, so no containment risk
- Rejecting them breaks legitimate workflows

**Why reject internal symlinks?**
- Could escape repo containment
- Could point to sensitive files outside repo
- Attackers could create malicious symlinks

---

## General Troubleshooting

### Hook Not Firing

**Symptoms**: No events in `current.jsonl` after file operations

**Checks**:

1. **Verify settings file**:
   ```bash
   cat .claude/settings.local.json
   # Should contain "hooks": {"PostToolUse": [...]}
   ```

2. **Check script path**:
   ```bash
   # Extract the command from settings
   command=$(jq -r '.hooks.PostToolUse[0].hooks[0].command' .claude/settings.local.json)
   # Verify the script exists
   ls -la $command
   ```

3. **Test hook manually**:
   ```bash
   export CM_DEBUG=1
   echo '{"tool_name":"Read","tool_input":{"file_path":"README.md"}}' | python3 $command
   cat /tmp/cm_hook_debug.log
   ```

4. **Check Claude Code permissions**:
   - Verify Claude Code can execute the script
   - Check file permissions: `ls -la ~/.claude/plugins/context-memory/scripts/`

### Bundle Too Large

**Symptoms**: Bundle has >50 operations or >100KB

**Causes**:
- Too many operations in session
- Large `tool_input` values
- Insufficient pruning

**Solutions**:

1. **Reduce max operations**:
   ```bash
   /cm-prune --max-ops 10
   /cm-save my-bundle --max-ops 10
   ```

2. **Check what's being tracked**:
   ```bash
   /cm-context
   # Look for patterns (repeated reads, temp files, etc.)
   ```

3. **Adjust ignore patterns** (if implemented):
   ```bash
   # Edit config to ignore noise
   echo '["*.log", "node_modules/*", "dist/*"]' > .claude/context_memory/ignore.json
   ```

### Paths Wrong Format

**Symptoms**: Absolute paths in JSONL, paths outside repo

**Checks**:

1. **Verify repository detection**:
   ```bash
   export CM_DEBUG=1
   # Trigger operation
   cat /tmp/cm_hook_debug.log | grep "Repo detected"
   ```

2. **Check path normalization**:
   ```bash
   # Look for relative paths in the log
   grep '"file_path"' .claude/context_memory/sessions/current.jsonl
   # Should be: "src/app.py" (relative)
   # NOT: "/Users/user/project/src/app.py" (absolute)
   ```

3. **Validate security checks**:
   ```bash
   # Look for validation errors
   cat /tmp/cm_hook_debug.log | grep "SECURITY\|validation"
   ```

### Bundle Save Failing

**Symptoms**: `/cm-save` returns JSON error

**Known Issues**:

| Error | Status | Fix |
|-------|--------|-----|
| `Object of type mappingproxy is not JSON serializable` | Fixed v1.0.1 | Update plugin |
| `Permission denied` | Check file perms | `chmod +w .claude/context_memory/bundles/` |
| `No space left on device` | Disk full | Free disk space |

**Debug**:
```bash
# Try saving with verbose output
/cm-save test-bundle --verbose

# Check bundle directory
ls -la .claude/context_memory/bundles/
```

### Load Plan Issues

**Symptoms**: `/cm-load` shows wrong or missing files

**Checks**:

1. **Verify bundle contents**:
   ```bash
   # Check bundle exists
   ls -la .claude/context_memory/bundles/

   # Inspect bundle contents
   cat .claude/context_memory/bundles/my-bundle.jsonl | jq .
   ```

2. **Check file still exists**:
   ```bash
   # Extract paths from bundle
   cat .claude/context_memory/bundles/my-bundle.jsonl | jq -r '.file_path'

   # Verify files exist
   cat .claude/context_memory/bundles/my-bundle.jsonl | jq -r '.file_path' | xargs ls -la
   ```

3. **Drift detection** (if CAS enabled):
   ```bash
   # Check for drift warnings
   /cm-load my-bundle | grep -i drift
   ```

---

## Error Message Reference

| Error Message | Cause | Solution | Version Fixed |
|---------------|-------|----------|---------------|
| `hooks.json ignored` | Wrong config file | Use `settings.local.json` | v1.0.2 |
| `Not in a git repo` | cwd != project dir | Use `detect_repo_from_file_path()` | v1.0.2 |
| `Symlinks not allowed` | macOS /tmp symlink | Allow system symlinks | v1.0.2 |
| `Path outside repository` | File outside repo | Check file location | - |
| `Object of type mappingproxy` | Old serialization bug | Update to v1.0.1+ | v1.0.1 |
| `Permission denied` | File permissions | `chmod` or run as appropriate user | - |
| `No such file or directory` | Missing script/bundle | Reinstall or check paths | - |

---

## Performance Debugging

### Slow Hook Execution

**Symptoms**: File operations pause noticeably

**Checks**:

1. **Measure hook execution time**:
   ```bash
   time echo '{"tool_name":"Read","tool_input":{"file_path":"README.md"}}' | \
     python3 ~/.claude/plugins/context-memory/scripts/cm_track_operation.py
   ```

2. **Check for unnecessary operations**:
   ```bash
   # Look for expensive operations in debug log
   cat /tmp/cm_hook_debug.log | grep -E "git|subprocess|resolve"
   ```

3. **Profile the hook**:
   ```bash
   python3 -m cProfile -o profile.stats \
     ~/.claude/plugins/context-memory/scripts/cm_track_operation.py < input.json
   python3 -m pstats profile.stats
   # Type: stats 10
   ```

### Large Session Files

**Symptoms**: `current.jsonl` grows too large (>1MB)

**Solutions**:

1. **Prune regularly**:
   ```bash
   /cm-prune --max-ops 50
   /cm-save checkpoint
   ```

2. **Check for noise patterns**:
   ```bash
   # Look for repeated operations
   cat .claude/context_memory/sessions/current.jsonl | jq -r '.file_path' | sort | uniq -c | sort -rn
   ```

3. **Reset session** (after saving):
   ```bash
   /cm-save backup
   rm .claude/context_memory/sessions/current.jsonl
   ```

---

## Issue Reporting Template

When reporting issues, include:

### Environment

```bash
# Plugin version
cd ~/.claude/plugins/context-memory
git log -1 --oneline

# Python version
python3 --version

# OS
uname -a

# Claude Code version (if available)
claude --version
```

### Configuration

```bash
# Hook configuration
cat .claude/settings.local.json

# Storage structure
tree .claude/context_memory/
```

### Debug Output

```bash
# Enable debug and reproduce issue
export CM_DEBUG=1
# Trigger the issue
cat /tmp/cm_hook_debug.log
```

### Session/Bundle Sample

```bash
# Last 10 lines of session
tail -10 .claude/context_memory/sessions/current.jsonl

# Or bundle contents
cat .claude/context_memory/bundles/*.jsonl | head -20
```

### Steps to Reproduce

1. Command/action taken:
2. Expected result:
3. Actual result:
4. Error messages:

---

## Additional Resources

- **Core documentation**: [docs/method.md](method.md)
- **Project README**: [../README.md](../README.md)
- **Developer notes**: [../CLAUDE.md](../CLAUDE.md)
- **Test suite**: Run `python -m pytest tests/ -v` for examples

---

## Quick Reference

### Common Commands

| Command | Purpose |
|---------|---------|
| `export CM_DEBUG=1` | Enable debug logging |
| `cat /tmp/cm_hook_debug.log` | View debug log |
| `/cm-status` | Show tracking status |
| `/cm-context` | Show session summary |
| `/cm-save <name>` | Save bundle |
| `/cm-load <name>` | Load bundle |
| `/cm-prune` | Prune session |

### Key Files

| File | Purpose |
|------|---------|
| `.claude/settings.local.json` | Hook configuration (v1.0.2+) |
| `.claude/context_memory/sessions/current.jsonl` | Active session log |
| `.claude/context_memory/bundles/*.jsonl` | Saved bundles |
| `/tmp/cm_hook_debug.log` | Debug output (when CM_DEBUG=1) |

### Version History

| Version | Date | Changes |
|---------|------|---------|
| v1.0.2 | 2026-01-03 | Fixed all 3 critical bugs |
| v1.0.1 | 2026-01-03 | Fixed JSON serialization |
| v1.0.0 | 2026-01-02 | Initial release |
