# Rules of Engagement

## Core Principles (Non-Negotiable)

### 1. JSONL is Append-Only

**Rule**: Never rewrite or truncate `current.jsonl` during normal operation.

**Why**:
- O(1) append performance
- Never lose data due to crashes
- Event sourcing pattern

**Exception**: Explicit `/cm-prune --in-place` (with backup)

### 2. Relative Paths Only

**Rule**: All file paths in JSONL must be relative to repo root.

**Why**:
- Portability across machines
- Works when repo is moved
- Security (no accidental system file access)

**Validation**: Paths validated at write time, rejected if:
- Absolute (starts with `/`)
- Contains `..` (path traversal)
- Outside repo root

### 3. No Full Content in JSONL

**Rule**: Never store complete file contents or tool_output in JSONL.

**Why**:
- JSONL would become massive
- Slow to read/parse
- Privacy concerns (credentials, etc.)

**Instead**:
- Store file paths only
- Store truncated tool_input (max 4KB)
- Use CAS for snapshots (optional)

### 4. Domain is Pure

**Rule**: Domain layer (`src/domain/`) has zero filesystem operations.

**Why**:
- Testable without real files
- Fast unit tests
- Clear separation of concerns

**Domain does**:
- Parse JSONL
- Classify paths
- Calculate prune budgets
- Build load plans

**Infrastructure does**:
- File reads/writes
- Lock management
- Repo detection
- Hash computation

### 5. Security First

**Rules**:
- Paths validated before storage
- No traversal (`../`) allowed
- No absolute paths allowed
- Null bytes rejected
- CAS storage sandboxed to repo

### 6. Idempotent Operations

**Rule**: Commands should be safe to run multiple times.

**Examples**:
- `/cm-save feature` → Overwrites existing bundle (same name)
- `cm_install.py` → Skip existing commands (unless `--force`)

### 7. Backward Compatibility

**Rule**: New schema versions should read old versions.

**Implementation**:
- Schema version in event: `{"schema": 1, ...}`
- Parser handles missing fields gracefully
- Old events readable by new code

## Pruning Rules

### Budgets

**Default budgets** (configurable):
- `MAX_OPS = 20`
- `MAX_BYTES_EST = 120,000`

**Why**:
- Keeps bundles compact
- Fast to rehydrate
- Fits in context window

### Priority Order

**Highest to lowest**:
1. `pinned` - User prompts/notes
2. `config` - Configuration files
3. `core` - Source code
4. `doc` - Documentation
5. `test` - Tests
6. `noise` - Generated/cache files

### Deduplication

**Rule**: For duplicate reads of same file, keep the LAST one.

**Why**:
- Most recent read is most relevant
- Reduces bundle size
- Still captures intent

## Naming Conventions

### Bundles

**Use descriptive names**:
- ✅ `pricing-refactor`
- ✅ `auth-fix-2025-01-02`
- ❌ `bundle1`
- ❌ `temp`

### Files

**Plugin structure**:
- `src/domain/` - Pure logic
- `src/infrastructure/` - IO adapters
- `scripts/` - CLI entry points
- `templates/commands/` - Command templates

## Testing Rules

### TDD Workflow

1. **Write failing test first**
2. **Implement minimal code to pass**
3. **Refactor if needed**

### Coverage

**Minimum 80% branch coverage** for:
- Domain logic (parser, pruning, plan)
- Path validation/security
- Storage operations

### Security Tests

**Must test**:
- Path traversal rejection
- Absolute path rejection
- Null byte rejection
- Repo boundary enforcement

## Performance Targets

### Hook Performance

**Target**: `<200ms` per event

**What affects it**:
- JSON serialization
- File append (with lock)
- Path validation

**Optimization**:
- Compact JSON (no spaces)
- Single lock acquisition
- Minimal syscalls

### Bundle Size

**Target**: `<50KB` per bundle (compressed)

**Why**:
- Fast to transmit/load
- Fits in context easily
- Not overwhelming for review

## Error Handling

### Graceful Degradation

**Principle**: Never crash user's session due to context-memory errors.

**Examples**:
- Hook fails silently (log stderr, don't block)
- Invalid JSONL lines skipped (with warning)
- Missing files in load → warning, continue

### Error Messages

**Principle**: Actionable error messages.

**Good**:
```
Error: Path '../../etc/passwd' is outside repository root
```

**Bad**:
```
Error: Invalid path
```

## Configuration

### Local Overrides

**Location**: `.claude/context_memory/config.json`

**Example**:
```json
{
  "max_ops": 30,
  "max_bytes_est": 200000,
  "ignore_patterns": ["*.log", "*.tmp"]
}
```

### Defaults

**Defined in**: `domain/pruning.py::PruningConfig`

**Override priority**:
1. Command-line flags (`--max-ops`)
2. Local config file
3. Plugin defaults

## Deployment

### Installation

**Single command**:
```bash
python3 ~/.claude/plugins/context-memory/scripts/cm_install.py
```

**What it does**:
1. Creates `.claude/commands/`
2. Copies command templates
3. Creates/merges `.claude/hooks.json`
4. Initializes storage directories

### Updates

**To update plugin**:
1. Pull latest in `~/.claude/plugins/context-memory/`
2. Re-run `cm_install.py --force` in each repo

**Bundles are compatible** across versions (schema versioning).

## Monitoring

### Health Checks

**Run regularly**:
```bash
/cm-status  # Check bundle counts, sizes
/cm-context  # Check current session growth
```

### When to Prune

**Signs you need to prune**:
- Current session >100 ops
- current.jsonl >50KB
- Bundle size unexpectedly large

**Solution**:
```bash
/cm-prune  # Preview
/cm-save <name>  # Create clean bundle
```

## Support

### Troubleshooting

**Common issues**:
1. Hook not tracking → Check `.claude/hooks.json`
2. Commands not found → Re-run `cm_install.py`
3. Bundles too large → Adjust `--max-ops`, check ignore patterns

### Getting Help

**Debug mode**:
```bash
export CM_DEBUG=1
/cm-status  # Will show verbose output
```

**Check logs**:
```bash
# Hook errors go to stderr
# Check Claude Code logs for hook failures
```
