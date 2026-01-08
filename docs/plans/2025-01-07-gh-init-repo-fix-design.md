# gh-init-repo Plugin Fix Design

**Date:** 2025-01-07
**Author:** Felipe Gonzalez + Claude Code
**Status:** Design Approved

## Overview

Refactor the `gh-init-repo` plugin to address 22 issues found by multi-agent code review:
- 6 Critical Issues
- 8 Important Issues
- 8 Suggestions

**Approach:** Hybrid validation (bash checks + improved instructions) with interactive error recovery.

---

## Problems Identified

### Critical Issues (6)

1. **All Conditional Checks Bypassed** - `!test ... && echo X || echo Y` pattern doesn't work as blocking check
2. **No Error Checking on Git Init** - No validation after `git init`
3. **No Error Checking on Git Commit** - No validation after `git commit`
4. **No Error Checking on GitHub Repo Create** - No validation after `gh repo create`
5. **Silent File Write Failure** - No validation after file writes
6. **Stderr Suppression Hiding Errors** - `2>/dev/null` hides real errors

### Important Issues (8)

7. Inconsistent README.md creation syntax
8. Missing allowed-tools for file creation
9. Incomplete allowed-tools pattern coverage
10. Logic issue with README creation condition
11. Repository name not validated
12. Visibility check is documentation only
13. Final verification assumes success
14. No validation of GitHub CLI installation

### Suggestions (8)

15-22. Missing CLAUDE.md, repo name validation, plugin.json metadata, description flag, comprehensive .gitignore, error handling section, git config validation, GitHub CLI install check

---

## Solution Architecture

### Two-Layer Validation Architecture

**Layer 1: Critical Bash Validations (Blocking Checks)**
- Executed with `!` prefix for required success
- Fail immediately with clear error messages
- Use explicit checks: `test -f`, `grep`, `command -v`

**Layer 2: Interactive Workflow Instructions**
- Guided by Claude Code based on improved instructions
- Interactive confirmations at each step
- Error recovery with user options

### Interactive Error Recovery

When critical operations fail, user chooses:
- **Retry** - Attempt the operation again
- **Skip** - Continue if operation is idempotent or already done
- **Abort** - Stop with clear guidance

---

## Implementation Plan

### Phase 1: Critical Fixes (Priority 1)

1. **Fix Conditional Checks**
   ```bash
   # OLD (broken):
   !test -d .git && echo "ALREADY_GIT_REPO" || echo "NOT_GIT_REPO"

   # NEW (working):
   test -d .git && GIT_EXISTS="yes" || GIT_EXISTS="no"
   # Then handle based on $GIT_EXISTS in workflow
   ```

2. **Add Error Checking to Critical Operations**
   ```bash
   !git init
   !test -d .git || { echo "❌ .git directory not created"; return 1; }

   !git commit -m "message"
   !git log -1 --oneline || { echo "❌ Commit failed"; return 1; }

   !gh repo create ...
   !git remote get-url origin || { echo "❌ Remote not created"; return 1; }
   ```

3. **Fix Stderr Suppression**
   ```bash
   # OLD:
   !git status --short 2>/dev/null || echo "No files yet"

   # NEW:
   test -d .git && git status --short || echo "Not a git repository"
   ```

4. **Add File Write Validation**
   ```bash
   cat > .gitignore << 'EOF'
   [...]
   EOF
   !test -f .gitignore || { echo "❌ .gitignore not created"; return 1; }
   ```

### Phase 2: Important Fixes (Priority 2)

5. **Fix README Creation Syntax**
   ```bash
   # Use consistent heredoc pattern
   cat > README.md << 'EOF'
   # [Repository Name]
   > [...]
   EOF
   ```

6. **Update allowed-tools**
   ```yaml
   allowed-tools:
     Bash(git init:*), Bash(git add:*), ...
     Bash(cat:*), Bash(echo:*), Bash(grep:*)
   ```

7. **Add Repository Name Validation**
   ```bash
   REPO_NAME=$(basename $(pwd))
   if echo "$REPO_NAME" | grep -q '[^a-zA-Z0-9_-]'; then
     echo "❌ Invalid repository name"
     return 1
   fi
   ```

8. **Implement Actual Visibility Validation**
   ```bash
   if ! echo "$ARGUMENTS" | grep -qE '(--public|--private)'; then
     echo "⚠️ Visibility required: --public or --private"
     return 1
   fi
   ```

### Phase 3: Suggestions (Priority 3)

9. Create `CLAUDE.md` for the plugin itself
10. Add `homepage` and `repository` to `plugin.json`
11. Add support for `--description` flag
12. Create `TESTING.md` with test cases
13. Create `scripts/validate-prerequisites.sh`
14. Enhance `.gitignore` with more patterns

---

## Files to Modify

1. `commands/gh-init-repo.md` - Main command file (major refactor)
2. `.claude-plugin/plugin.json` - Add metadata
3. `CLAUDE.md` - Create new file for plugin development
4. `TESTING.md` - Create new test documentation
5. `scripts/validate-prerequisites.sh` - Create new validation script
6. `.gitignore` - Enhance patterns
7. `README.md` - Update with fixes documented

---

## Testing Strategy

### Manual Test Cases

1. **Happy Path** - Complete successful workflow
2. **CLAUDE.md Missing** - Must block
3. **No Visibility Flag** - Must block
4. **Git Not Installed** - Clear error message
5. **GitHub CLI Not Authenticated** - Clear error message
6. **Existing Git Repo** - Continue/abort options
7. **Invalid Repo Name** - Validation catches
8. **Disk Full** - Error handling
9. **Network Failure** - Retry options
10. **Repo Already Exists on GitHub** - Alternative options

### Validation Script

`scripts/validate-prerequisites.sh` checks:
- Git installed
- GitHub CLI installed
- GitHub CLI authenticated
- Git user.name configured
- Git user.email configured

---

## Success Criteria

- [ ] All 6 critical issues resolved
- [ ] All 8 important issues resolved
- [ ] All 8 suggestions addressed
- [ ] Pre-flight checks validate correctly
- [ ] Error recovery offers Retry/Skip/Abort
- [ ] Manual tests pass for 10 test cases
- [ ] Documentation updated (CLAUDE.md, TESTING.md)
- [ ] Validation script created and working

---

## Estimated Effort

- **Phase 1 (Critical):** 2-3 hours
- **Phase 2 (Important):** 1-2 hours
- **Phase 3 (Suggestions):** 1 hour
- **Testing:** 1-2 hours
- **Documentation:** 1 hour

**Total:** 6-9 hours

---

## Next Steps

1. Create task list from this design
2. Implement Phase 1 fixes
3. Test critical fixes
4. Implement Phase 2 fixes
5. Test important fixes
6. Implement Phase 3 suggestions
7. Create test documentation
8. Final validation
