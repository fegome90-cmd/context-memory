# Changelog

All notable changes to the context-memory plugin will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Planned
- Windows file locking support
- Concurrent append tests
- Performance metrics in prune reports

## [1.0.2] - 2026-02-09

### Added
- `CONTRIBUTING.md` with development workflow and scripts reference
- `CHANGELOG.md` for tracking version history
- Environment variable documentation (`CM_DEBUG`)
- Comprehensive scripts reference table

### Changed
- Improved documentation structure and organization
- Clarified hook configuration requirements (settings.json vs hooks.json)

### Fixed
- Documentation for repository detection with file_path-based detection
- Clarified symlink handling on macOS

## [1.0.1] - 2026-01-03

### Fixed
- JSON serialization bug for MappingProxy in `src/domain/events.py:to_dict()`
- Repository detection now uses file_path-based detection as primary strategy
- Symlink validation on macOS (handles `/tmp` → `/private/tmp`)
- Hook configuration now uses `settings.local.json` instead of `hooks.json`

### Added
- `nested_repos` fixture in `tests/conftest.py`
- Tests for hook functionality (9 tests passing)
- Verification of hook capturing Read/Write/Edit/MultiEdit operations

### Changed
- Updated install script to create `.claude/settings.local.json` (not `hooks.json`)
- Improved error messages and debug logging

## [1.0.0] - 2026-01-02

### Added
- Initial release of context-memory plugin
- Core event tracking with JSONL append-only logs
- Pruning strategy with deduplication and prioritization
- Bundle save/load functionality
- PostToolUse hook for automatic tracking
- Zero-dependency implementation (Python stdlib only)
- Clean Architecture / Hexagonal pattern
- Comprehensive test suite (106 tests, 82% coverage)

### Features
- Track Read, Write, Edit, MultiEdit operations
- Intelligent pruning with configurable budgets
- Repository identification via git remote or generated ID
- Security-first path validation
- Content-addressable storage (optional)
- Multi-agent code review wizard
- Health check command
- Bundle integrity verification

[Unreleased]: https://github.com/felipe-gonzalez/context-memory/compare/v1.0.2...HEAD
[1.0.2]: https://github.com/felipe-gonzalez/context-memory/compare/v1.0.1...v1.0.2
[1.0.1]: https://github.com/felipe-gonzalez/context-memory/compare/v1.0.0...v1.0.1
[1.0.0]: https://github.com/felipe-gonzalez/context-memory/releases/tag/v1.0.0
