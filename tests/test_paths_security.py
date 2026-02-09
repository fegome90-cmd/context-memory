"""Tests for path normalization and security."""

import pytest

from infrastructure.paths import (
    normalize_path,
    validate_path,
    get_relative_path,
    join_paths,
)


def test_normalize_relative_path(repo_root):
    """Test normalizing a relative path."""
    result = normalize_path("src/app.py", repo_root)

    assert result == "src/app.py"


def test_normalize_absolute_path(repo_root, temp_dir):
    """Test normalizing an absolute path to relative."""
    abs_path = temp_dir / "src" / "app.py"
    abs_path.mkdir(parents=True)

    result = normalize_path(str(abs_path), temp_dir)

    assert result == "src/app.py"


def test_normalize_rejects_traversal(repo_root):
    """Test that path traversal is rejected."""
    # After security fix, traversal is detected before "outside repo" check
    with pytest.raises(ValueError, match="Path traversal not allowed|outside repository root"):
        normalize_path("../../../etc/passwd", repo_root)


def test_normalize_rejects_outside_repo(repo_root, temp_dir):
    """Test that paths outside repo are rejected."""
    outside_path = temp_dir / "outside" / "file.py"

    with pytest.raises(ValueError, match="outside repository root"):
        normalize_path(str(outside_path), repo_root)


def test_validate_path_accepts_valid():
    """Test that valid paths pass validation."""
    assert validate_path("src/app.py") is True
    assert validate_path("README.md") is True
    assert validate_path("tests/test_app.py") is True


def test_validate_path_rejects_absolute():
    """Test that absolute paths fail validation."""
    assert validate_path("/etc/passwd") is False
    assert validate_path("/usr/local/bin") is False


def test_validate_path_rejects_traversal():
    """Test that path traversal fails validation."""
    assert validate_path("../../../etc/passwd") is False
    assert validate_path("src/../../secret") is False


def test_validate_path_rejects_null_bytes():
    """Test that null bytes fail validation."""
    assert validate_path("src/app.py\x00.exe") is False


def test_get_relative_path_valid(repo_root):
    """Test getting relative path for valid input."""
    result = get_relative_path("src/app.py", repo_root)

    assert result == "src/app.py"


def test_get_relative_path_invalid_returns_none(repo_root):
    """Test that invalid paths return None."""
    result = get_relative_path("../../../etc/passwd", repo_root)

    assert result is None


def test_join_paths():
    """Test joining path parts."""
    result = join_paths("src", "app.py")

    assert result == "src/app.py"


def test_join_paths_multiple():
    """Test joining multiple path parts."""
    result = join_paths("src", "domain", "events.py")

    assert result == "src/domain/events.py"


def test_join_paths_normalizes_slashes():
    """Test that join normalizes slashes."""
    result = join_paths("src/", "/domain/", "//events.py")

    assert result == "src/domain/events.py"


def test_normalize_path_windows_style(repo_root):
    """Test that Windows-style backslashes are converted."""
    result = normalize_path("src\\domain\\events.py", repo_root)

    # Should use forward slashes
    assert "\\" not in result
    assert result == "src/domain/events.py"


def test_normalize_rejects_symlink_to_outside(repo_root, tmp_path):
    """Test that symlinks pointing outside the repo are rejected (security critical)."""
    # Create a file outside the repo
    outside_dir = tmp_path / "outside"
    outside_dir.mkdir()
    outside_file = outside_dir / "secret.txt"
    outside_file.write_text("secret data")

    # Create a symlink inside the repo pointing outside
    symlink = repo_root / "backdoor"
    symlink.symlink_to(outside_file)

    # Must reject the symlink path (caught either by symlink check or
    # by containment check after resolve follows the symlink)
    with pytest.raises(ValueError, match="(Symlinks not allowed|outside repository root)"):
        normalize_path("backdoor", repo_root)


def test_normalize_rejects_symlink_component(repo_root, tmp_path):
    """Test that symlinks in path components are rejected."""
    # Create a directory outside the repo
    outside_dir = tmp_path / "outside"
    outside_dir.mkdir()

    # Create nested directory structure inside repo
    (repo_root / "src").mkdir()

    # Create a symlink in the middle of the path
    symlink = repo_root / "src" / "backdoor"
    symlink.symlink_to(outside_dir)

    # Must reject the path containing symlink component (caught either by
    # symlink check or by containment check after resolve follows the symlink)
    with pytest.raises(ValueError, match="(Symlinks not allowed|outside repository root)"):
        normalize_path("src/backdoor/file.py", repo_root)


def test_join_paths_rejects_traversal():
    """Test that join_paths rejects path traversal attacks."""
    with pytest.raises(ValueError, match="Path traversal not allowed"):
        join_paths("src", "..", "etc")


def test_join_paths_rejects_traversal_middle():
    """Test that join_paths rejects traversal in middle components."""
    with pytest.raises(ValueError, match="Path traversal not allowed"):
        join_paths("src", "../", "app.py")
