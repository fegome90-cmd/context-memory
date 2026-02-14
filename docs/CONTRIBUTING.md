# Contributing to context-memory

Thank you for your interest in contributing to the context-memory plugin! This document outlines the development workflow, available scripts, and testing procedures.

## Development Setup

### Prerequisites

- Python 3.10 or later
- Git (for repository detection)
- No external dependencies required (stdlib only)

### Repository Structure

```
context-memory/
├── src/
│   ├── domain/           # Pure business logic (events, parser, pruning, plan)
│   └── infrastructure/   # I/O adapters (storage, repo detection, paths, logging)
├── scripts/              # CLI entry points
├── tests/                # Pytest test suite
├── hooks/                # Plugin-level hooks configuration
├── templates/            # Command templates for installation
└── docs/                 # Documentation
```

## Available Scripts

The following scripts are available in the `scripts/` directory:

| Script | Purpose | Usage |
|--------|---------|-------|
| `cm_install.py` | Install plugin in a repository | `python3 scripts/cm_install.py [--repo PATH] [--force] [--no-merge]` |
| `cm_track_operation.py` | PostToolUse hook for tracking file operations | Called automatically by Claude Code |
| `cm_save.py` | Save a pruned bundle from current session | `python3 scripts/cm_save.py <name> [--max-ops N]` |
| `cm_load.py` | Load and display a bundle | `python3 scripts/cm_load.py <name>` |
| `cm_status.py` | Show context memory status | `python3 scripts/cm_status.py` |
| `cm_context.py` | Show current session summary | `python3 scripts/cm_context.py` |
| `cm_prune.py` | Prune current session in-place | `python3 scripts/cm_prune.py [--max-ops N]` |
| `cm_list.py` | List all context bundles | `python3 scripts/cm_list.py` |
| `cm_health` | Health check for plugin configuration | `./scripts/cm_health [--verbose]` |
| `cm_reindex.py` | Rebuild bundle indexes | `python3 scripts/cm_reindex.py` |
| `cm_multi_review.py` | Multi-agent code review wizard | `python3 scripts/cm_multi_review.py` |
| `check_bundle_integrity.py` | Verify bundle file integrity | `python3 scripts/check_bundle_integrity.py <bundle>` |
| `cm_capture_from_transcript.py` | Capture events from transcript | `python3 scripts/cm_capture_from_transcript.py` |
| `cm_test.py` | Run plugin tests | `python3 scripts/cm_test.py` |

### Utility Scripts

| Script | Purpose |
|--------|---------|
| `debug_env.sh` | Show environment variables for debugging |
| `simple_test_hook.sh` | Simple hook test |
| `test_hook.py` | Python hook test harness |
| `verify_hook.sh` | Verify hook installation |

## Environment Variables

| Variable | Purpose | Default |
|----------|---------|---------|
| `CM_DEBUG` | Enable debug logging to `/tmp/cm_hook_debug.log` | `0` (disabled) |

### Debug Mode

Enable debug logging to troubleshoot hook issues:

```bash
export CM_DEBUG=1
# Trigger a hook operation (e.g., read a file)
cat /tmp/cm_hook_debug.log
```

## Testing

### Run All Tests

```bash
# From plugin directory
cd ~/.claude/plugins/context-memory
python -m pytest tests/ -v

# With coverage
python -m pytest tests/ --cov=src --cov-report=term-missing
```

### Run Specific Tests

```bash
# Test hook functionality
python -m pytest tests/test_cm_track_operation.py -v

# Test security
python -m pytest tests/test_paths_security.py -v

# Test pruning
python -m pytest tests/test_pruning.py -v
```

### Test Structure

```
tests/
├── conftest.py                    # Shared fixtures
├── test_cm_track_operation.py    # Hook functionality tests
├── test_domain_events.py          # Event creation and validation
├── test_domain_plan_build.py      # Load plan building
├── test_infra_storage_jsonl.py    # JSONL storage tests
├── test_infra_repo_id.py          # Repository identification
├── test_infra_cas.py              # Content-addressable storage
├── test_paths_security.py         # Path validation security
├── test_pruning.py                # Pruning strategy
├── test_parser.py                 # Event parsing
├── test_find_repo_root.py         # Repo detection
├── test_check_bundle_integrity.py # Bundle integrity checks
├── test_cm_install.py             # Installation tests
├── test_cm_multi_review.py        # Multi-agent review tests
└── test_cm_multi_review_exhaustive.py  # Comprehensive review tests
```

### Fixtures

The following fixtures are available in `tests/conftest.py`:

- `repo_root` - Creates a temporary git repository
- `temp_dir` - Creates a temporary directory
- `non_repo_dir` - Creates directory without .git
- `nested_repos` - Creates 3-level nested repo structure
- `sample_events` - Provides sample event data

## Code Style

This project follows Python coding standards:

- **PEP 8** conventions
- **Type annotations** on all function signatures
- **Frozen dataclasses** for immutable data structures
- **Pure functions** in domain layer (no I/O)
- **Security-first** approach (validate all paths)

### Domain Layer Constraints

The `src/domain/` layer has ZERO filesystem dependencies:

- Pure functions only
- Frozen dataclasses for immutability
- No I/O operations
- Security invariants in `__post_init__`

### Infrastructure Layer

The `src/infrastructure/` layer handles all I/O:

- Adapter pattern for storage backends
- Path security validation
- JSONL append-only operations
- Repository detection

## Development Workflow

### 1. Make Changes

Edit files in `src/` or `scripts/` as needed.

### 2. Run Tests

```bash
python -m pytest tests/ -v
```

Ensure all tests pass before committing.

### 3. Check Coverage

```bash
python -m pytest tests/ --cov=src --cov-report=term-missing
```

Target: >80% coverage

### 4. Test Locally

Install in a test repository:

```bash
cd /path/to/test-repo
python3 ~/.claude/plugins/context-memory/scripts/cm_install.py --force
```

### 5. Commit Changes

Follow conventional commit format:

```
<type>: <description>

<optional body>
```

Types: feat, fix, refactor, docs, test, chore, perf, ci

## Architecture

### Clean Architecture / Hexagonal

The plugin follows Clean Architecture principles:

1. **Domain Layer** (`src/domain/`) - Pure business logic
2. **Infrastructure Layer** (`src/infrastructure/`) - I/O adapters
3. **Hooks** (`hooks/`) - Event producers
4. **Scripts** (`scripts/`) - CLI consumers

### Component Relationships

```
┌─────────────────┐
│  Claude Code    │
└────────┬────────┘
         │ PostToolUse events
         ▼
┌─────────────────┐
│  Hooks/         │ ← Event producers
└────────┬────────┘
         │ JSON data
         ▼
┌─────────────────┐
│  Scripts/       │ ← CLI entry points
└────────┬────────┘
         │
         ▼
┌─────────────────────────────┐
│  Infrastructure/            │ ← I/O adapters
│  - storage_jsonl.py         │
│  - repo.py                  │
│  - paths.py                 │
│  - logging.py               │
└────────┬────────────────────┘
         │
         ▼
┌─────────────────────────────┐
│  Domain/                    │ ← Pure logic
│  - events.py                │
│  - parser.py                │
│  - pruning.py               │
│  - plan.py                  │
└─────────────────────────────┘
```

## Common Tasks

### Adding a New Command

1. Create script in `scripts/`
2. Add command template in `templates/commands/`
3. Update `scripts/cm_install.py` to include the template
4. Add tests in `tests/`
5. Update this document with the new command

### Adding a New Event Type

1. Update `src/domain/events.py` with new event type
2. Update `scripts/cm_track_operation.py` to handle the new type
3. Add tests in `tests/test_cm_track_operation.py`
4. Update documentation

### Modifying Pruning Strategy

1. Edit `src/domain/pruning.py`
2. Update tests in `tests/test_pruning.py`
3. Verify coverage remains >80%
4. Test with various event patterns

## Troubleshooting

### Hook Not Firing

1. Check `.claude/settings.local.json` exists (NOT `.claude/hooks.json`)
2. Verify hook is in `PostToolUse` section
3. Enable debug mode: `export CM_DEBUG=1`
4. Check `/tmp/cm_hook_debug.log`

### Tests Failing

```bash
# Run with verbose output
python -m pytest tests/ -vv

# Run specific test
python -m pytest tests/test_name.py::test_function -vv

# Show local variables on failure
python -m pytest tests/ -l
```

### Repository Detection Failing

1. Verify `.git` directory exists
2. Check that file paths are within repo root
3. Enable debug mode to see detection logic
4. Check `src/infrastructure/repo.py` for issues

## Documentation

- **User-facing**: `README.md`
- **Development**: `CLAUDE.md`
- **Architecture**: `docs/method.md`
- **Rules**: `docs/rules-of-engagement.md`
- **Audits**: `docs/audit/README.md`
- **Contributing**: This file

## License

MIT

## Contact

For questions or issues, please refer to the main project documentation.
