"""Tests for cm_install.py - CLAUDE_PLUGIN_ROOT validation."""
import json
import os
import subprocess
import sys
from pathlib import Path

# Add scripts directory to path for imports
plugin_dir = Path(__file__).parent.parent
sys.path.insert(0, str(plugin_dir))


def test_install_hooks_includes_plugin_root_validation(repo_root):
    """Test that hook command includes CLAUDE_PLUGIN_ROOT validation."""
    from scripts import cm_install

    # Install hooks
    cm_install.install_hooks(repo_root, merge=False)

    # Read hooks.json
    hooks_path = repo_root / ".claude" / "hooks.json"
    assert hooks_path.exists(), "hooks.json should be created"

    with open(hooks_path) as f:
        hooks = json.load(f)

    # Verify hook command has CLAUDE_PLUGIN_ROOT validation
    assert "PostToolUse" in hooks
    hook_cmd = hooks["PostToolUse"]["command"]

    # Check for validation pattern
    assert "CLAUDE_PLUGIN_ROOT" in hook_cmd, "Hook command should use CLAUDE_PLUGIN_ROOT"
    assert "if [ -z" in hook_cmd, "Hook command should validate CLAUDE_PLUGIN_ROOT is set"
    assert "exit 0" in hook_cmd, "Hook should exit 0 on validation failure (silent)"


def test_install_commands_includes_plugin_root_validation(repo_root):
    """Test that command templates have CLAUDE_PLUGIN_ROOT validation."""
    from scripts import cm_install

    # Install commands
    cm_install.install_commands(repo_root, force=True)

    # Check each installed command has validation
    commands_dir = repo_root / ".claude" / "commands"
    assert commands_dir.exists(), "Commands directory should be created"

    for cmd_file in ["cm-save.md", "cm-status.md", "cm-load.md",
                     "cm-prune.md", "cm-context.md"]:
        cmd_path = commands_dir / cmd_file
        assert cmd_path.exists(), f"{cmd_file} should be installed"

        content = cmd_path.read_text()

        # Verify CLAUDE_PLUGIN_ROOT is used
        assert "CLAUDE_PLUGIN_ROOT" in content, \
            f"{cmd_file} should use CLAUDE_PLUGIN_ROOT variable"

        # Verify validation pattern exists
        assert 'if [ -z "${CLAUDE_PLUGIN_ROOT:-}" ]' in content, \
            f"{cmd_file} should validate CLAUDE_PLUGIN_ROOT is set"

        # Verify clear error message
        assert "CLAUDE_PLUGIN_ROOT environment variable is not set" in content, \
            f"{cmd_file} should have clear error message about CLAUDE_PLUGIN_ROOT"


def test_hook_exits_zero_when_plugin_root_unset(repo_root):
    """Test that hook exits 0 when CLAUDE_PLUGIN_ROOT is not set (doesn't break workflow)."""
    from scripts import cm_install

    # Install hooks
    cm_install.install_hooks(repo_root, merge=False)

    # Read hooks.json
    hooks_path = repo_root / ".claude" / "hooks.json"
    with open(hooks_path) as f:
        hooks = json.load(f)

    hook_cmd = hooks["PostToolUse"]["command"]

    # Execute hook command WITHOUT CLAUDE_PLUGIN_ROOT set
    # Should exit 0 (not fail) to avoid breaking workflow
    env = os.environ.copy()
    env.pop("CLAUDE_PLUGIN_ROOT", None)

    result = subprocess.run(
        hook_cmd,
        shell=True,
        capture_output=True,
        text=True,
        env=env
    )

    # Hook should NOT fail (exit 0) even when CLAUDE_PLUGIN_ROOT is unset
    assert result.returncode == 0, \
        "Hook should exit 0 when CLAUDE_PLUGIN_ROOT is unset (silent failure)"


def test_install_hooks_creates_hooks_json(repo_root):
    """Test that install_hooks creates hooks.json with correct structure."""
    from scripts import cm_install

    # Install hooks
    cm_install.install_hooks(repo_root, merge=False)

    hooks_path = repo_root / ".claude" / "hooks.json"

    # Verify file exists
    assert hooks_path.exists(), "hooks.json should be created"

    # Verify structure
    with open(hooks_path) as f:
        hooks = json.load(f)

    assert "PostToolUse" in hooks, "PostToolUse hook should be present"
    assert "matcher" in hooks["PostToolUse"], "Hook should have matcher"
    assert "command" in hooks["PostToolUse"], "Hook should have command"
    assert "capture" in hooks["PostToolUse"], "Hook should have capture"

    # Verify matcher
    assert hooks["PostToolUse"]["matcher"] == "Read|Write|Edit|MultiEdit"


def test_install_commands_copies_templates(repo_root):
    """Test that install_commands copies all template files."""
    from scripts import cm_install

    # Install commands
    cm_install.install_commands(repo_root, force=True)

    commands_dir = repo_root / ".claude" / "commands"

    # Verify expected commands are installed
    expected_commands = [
        "cm-init.md",
        "cm-status.md",
        "cm-context.md",
        "cm-save.md",
        "cm-load.md",
        "cm-prune.md",
        "cm-track.md",
        "cm-multi-review.md",
    ]

    for cmd in expected_commands:
        cmd_path = commands_dir / cmd
        assert cmd_path.exists(), f"{cmd} should be installed"


def test_init_storage_creates_directories(repo_root):
    """Test that init_storage creates required directories."""
    from scripts import cm_install

    # Initialize storage
    cm_install.init_storage(repo_root)

    # Verify directories exist
    sessions_dir = repo_root / ".claude" / "context_memory" / "sessions"
    bundles_dir = repo_root / ".claude" / "context_memory" / "bundles"
    cas_dir = repo_root / ".claude" / "context_memory" / "cas"

    assert sessions_dir.exists(), "Sessions directory should be created"
    assert bundles_dir.exists(), "Bundles directory should be created"
    assert cas_dir.exists(), "CAS directory should be created"


def test_install_hooks_merges_with_existing_hooks(repo_root):
    """Test that install_hooks merges with existing hooks.json."""
    from scripts import cm_install

    # Create existing hooks.json with different hook
    existing_hooks = {
        "PreToolUse": {
            "matcher": "Write",
            "command": "echo 'before'",
            "capture": "tool"
        }
    }

    hooks_path = repo_root / ".claude" / "hooks.json"
    hooks_path.parent.mkdir(parents=True, exist_ok=True)
    with open(hooks_path, "w") as f:
        json.dump(existing_hooks, f)

    # Install hooks with merge=True
    cm_install.install_hooks(repo_root, merge=True)

    # Read merged hooks
    with open(hooks_path) as f:
        hooks = json.load(f)

    # Both hooks should exist
    assert "PreToolUse" in hooks, "Existing PreToolUse hook should be preserved"
    assert "PostToolUse" in hooks, "New PostToolUse hook should be added"

    # Existing hook should be unchanged
    assert hooks["PreToolUse"]["command"] == "echo 'before'"
