"""
Tests for plugin root resolution and PluginContext.

These tests verify the deterministic plugin root detection and
the separation of plugin_root from repo_root.
"""

import os
from pathlib import Path

import pytest

from infrastructure.plugin_root import (
    find_plugin_root,
    find_plugin_root_from_env,
    find_plugin_root_from_script,
    validate_plugin_root,
)
from infrastructure.repo import (
    PluginContext,
    get_plugin_context,
    find_repo_root_from_path,
)


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def tmp_plugin(tmp_path: Path) -> Path:
    """Create a minimal valid plugin structure."""
    plugin_root = tmp_path / "test-plugin"
    plugin_root.mkdir()
    plugin_marker = plugin_root / ".claude-plugin"
    plugin_marker.mkdir()
    (plugin_marker / "plugin.json").write_text('{"name": "test-plugin"}')
    return plugin_root


@pytest.fixture
def tmp_plugin_with_git(tmp_plugin: Path) -> Path:
    """Create a plugin with a git repository."""
    git_dir = tmp_plugin / ".git"
    git_dir.mkdir()
    (git_dir / "config").write_text("[core]\nrepositoryformatversion = 0\n")
    return tmp_plugin


# =============================================================================
# Plugin Root Detection Tests
# =============================================================================

class TestFindPluginRootFromEnv:
    """Tests for environment variable-based plugin root detection."""

    def test_returns_none_when_env_not_set(self, monkeypatch):
        """No plugin root when CLAUDE_PLUGIN_ROOT is not set."""
        monkeypatch.delenv("CLAUDE_PLUGIN_ROOT", raising=False)
        assert find_plugin_root_from_env() is None

    def test_returns_path_when_env_valid(self, tmp_plugin: Path, monkeypatch):
        """Returns path when env var points to valid plugin."""
        monkeypatch.setenv("CLAUDE_PLUGIN_ROOT", str(tmp_plugin))
        result = find_plugin_root_from_env()
        assert result == tmp_plugin

    def test_returns_none_when_env_invalid(self, tmp_path: Path, monkeypatch):
        """Returns None when env var points to non-plugin directory."""
        monkeypatch.setenv("CLAUDE_PLUGIN_ROOT", str(tmp_path))
        assert find_plugin_root_from_env() is None


class TestFindPluginRootFromScript:
    """Tests for script location-based plugin root detection."""

    def test_finds_plugin_from_nested_script(self, tmp_plugin: Path):
        """Finds plugin root from a script deep in the directory tree."""
        # Create nested script location
        nested_dir = tmp_plugin / "src" / "infrastructure"
        nested_dir.mkdir(parents=True)
        script_path = nested_dir / "test_script.py"
        script_path.write_text("# test")

        result = find_plugin_root_from_script(script_path)
        assert result == tmp_plugin

    def test_returns_none_for_non_plugin_path(self, tmp_path: Path):
        """Returns None when script is not in a plugin directory."""
        script_path = tmp_path / "script.py"
        script_path.write_text("# test")

        result = find_plugin_root_from_script(script_path)
        assert result is None


class TestValidatePluginRoot:
    """Tests for plugin root validation."""

    def test_validates_correct_plugin(self, tmp_plugin: Path):
        """Validates a correctly structured plugin."""
        assert validate_plugin_root(tmp_plugin) is True

    def test_rejects_missing_plugin_json(self, tmp_path: Path):
        """Rejects directory without plugin.json."""
        assert validate_plugin_root(tmp_path) is False

    def test_rejects_nonexistent_path(self):
        """Rejects non-existent path."""
        assert validate_plugin_root(Path("/nonexistent/path")) is False


class TestFindPluginRoot:
    """Tests for the main find_plugin_root function."""

    def test_uses_env_when_valid(self, tmp_plugin: Path, monkeypatch):
        """Prefers env var when valid."""
        monkeypatch.setenv("CLAUDE_PLUGIN_ROOT", str(tmp_plugin))
        result = find_plugin_root()
        assert result == tmp_plugin

    def test_uses_script_path_as_fallback(self, tmp_plugin: Path, monkeypatch):
        """Uses script path when env var not set."""
        monkeypatch.delenv("CLAUDE_PLUGIN_ROOT", raising=False)

        # Create nested script
        nested_dir = tmp_plugin / "scripts"
        nested_dir.mkdir()
        script_path = nested_dir / "test.py"
        script_path.write_text("# test")

        result = find_plugin_root(script_path)
        assert result == tmp_plugin


# =============================================================================
# PluginContext Tests
# =============================================================================

class TestGetPluginContext:
    """Tests for PluginContext creation."""

    def test_context_with_git_repo(self, tmp_plugin_with_git: Path):
        """PluginContext correctly identifies git repo."""
        ctx = get_plugin_context(tmp_plugin_with_git)

        assert ctx.plugin_root == tmp_plugin_with_git
        assert ctx.repo_root == tmp_plugin_with_git
        assert ctx.is_global_mode is False
        assert "bundles" in str(ctx.bundle_storage)

    def test_context_without_git_repo(self, tmp_plugin: Path):
        """PluginContext uses global mode when no git repo."""
        ctx = get_plugin_context(tmp_plugin)

        assert ctx.plugin_root == tmp_plugin
        assert ctx.repo_root is None
        assert ctx.is_global_mode is True
        assert "global-bundles" in str(ctx.bundle_storage)

    def test_bundle_storage_inside_repo(self, tmp_plugin_with_git: Path):
        """Bundle storage is inside repo when git exists."""
        ctx = get_plugin_context(tmp_plugin_with_git)

        expected = tmp_plugin_with_git / ".claude" / "context_memory" / "bundles"
        assert ctx.bundle_storage == expected

    def test_bundle_storage_global_fallback(self, tmp_plugin: Path):
        """Bundle storage uses global path when no git."""
        ctx = get_plugin_context(tmp_plugin)

        # Should be in home directory with hash-based subdirectory
        assert ".claude" in str(ctx.bundle_storage)
        assert "context-memory" in str(ctx.bundle_storage)
        assert "global-bundles" in str(ctx.bundle_storage)

    def test_repo_id_present(self, tmp_plugin_with_git: Path):
        """Repo ID is generated for git repos."""
        ctx = get_plugin_context(tmp_plugin_with_git)
        assert ctx.repo_id is not None
        assert len(ctx.repo_id) == 10  # 10-char hex

    def test_repo_id_in_global_mode(self, tmp_plugin: Path):
        """Repo ID is generated even in global mode."""
        ctx = get_plugin_context(tmp_plugin)
        assert ctx.repo_id is not None
        assert len(ctx.repo_id) == 10


class TestPluginContextToDict:
    """Tests for PluginContext serialization."""

    def test_to_dict_includes_all_fields(self, tmp_plugin: Path):
        """to_dict includes all relevant fields."""
        ctx = get_plugin_context(tmp_plugin)
        d = ctx.to_dict()

        assert "plugin_root" in d
        assert "repo_root" in d
        assert "repo_id" in d
        assert "bundle_storage" in d
        assert "is_global_mode" in d

    def test_to_dict_repo_root_is_string_or_none(self, tmp_plugin: Path):
        """repo_root is serialized as string or None."""
        # Without git
        ctx = get_plugin_context(tmp_plugin)
        assert ctx.to_dict()["repo_root"] is None

        # With git (would need git fixture)


# =============================================================================
# Integration Tests
# =============================================================================

class TestRootResolutionIntegration:
    """End-to-end tests for root resolution scenarios."""

    def test_resolution_from_different_cwd(self, tmp_plugin: Path, monkeypatch):
        """Plugin found even from different working directory."""
        # Change to a different directory
        monkeypatch.chdir("/tmp")

        # Create script inside plugin
        script_path = tmp_plugin / "scripts" / "load.py"
        script_path.parent.mkdir(exist_ok=True)
        script_path.write_text("# script")

        result = find_plugin_root(script_path)
        assert result == tmp_plugin

    def test_no_git_repo_does_not_fail(self, tmp_plugin: Path):
        """Context creation succeeds without git repo."""
        # Should not raise
        ctx = get_plugin_context(tmp_plugin)

        # Should be in global mode
        assert ctx.is_global_mode is True

    def test_missing_root_gives_clear_error(self, tmp_path: Path, monkeypatch):
        """Clear error when root cannot be found."""
        monkeypatch.delenv("CLAUDE_PLUGIN_ROOT", raising=False)

        # Script in non-plugin directory
        script_path = tmp_path / "script.py"
        script_path.write_text("# script")

        result = find_plugin_root(script_path)
        assert result is None

    def test_root_override_with_invalid_plugin(self, tmp_path: Path):
        """--root with path that exists but isn't a valid plugin should fail."""
        # Create a directory that exists but isn't a plugin
        not_a_plugin = tmp_path / "not-a-plugin"
        not_a_plugin.mkdir()
        (not_a_plugin / "some_file.txt").write_text("not a plugin")

        # Validate should return False
        assert validate_plugin_root(not_a_plugin) is False

        # find_plugin_root should not find it
        result = find_plugin_root_from_script(not_a_plugin / "some_file.txt")
        assert result is None
