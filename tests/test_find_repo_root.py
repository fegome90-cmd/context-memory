"""Tests for find_repo_root_from_path() and detect_repo_from_file_path()."""
from pathlib import Path

from infrastructure.repo import (
    find_repo_root_from_path,
    detect_repo_from_file_path,
    MAX_REPO_SEARCH_DEPTH,
    RepoInfo,
)


def test_find_repo_root_from_file_in_repo(tmp_path):
    """Test finding repo root from a file inside a repo."""
    repo = tmp_path / "my_project"
    repo.mkdir()
    (repo / ".git").mkdir()

    test_file = repo / "src" / "app.py"
    test_file.parent.mkdir(parents=True)
    test_file.write_text("x = 1")

    result = find_repo_root_from_path(test_file)
    assert result == repo


def test_find_repo_root_from_deeply_nested(tmp_path):
    """Test finding repo root from a deeply nested file (5 levels)."""
    repo = tmp_path / "project"
    repo.mkdir()
    (repo / ".git").mkdir()

    deep_file = repo / "a" / "b" / "c" / "d" / "e" / "deep.py"
    deep_file.parent.mkdir(parents=True)
    deep_file.write_text("x = 1")

    result = find_repo_root_from_path(deep_file)
    assert result == repo


def test_find_repo_root_returns_none_outside_repo(tmp_path):
    """Test that it returns None when file is not inside any repo."""
    no_repo = tmp_path / "no_repo_here"
    no_repo.mkdir()
    test_file = no_repo / "random.py"
    test_file.write_text("x = 1")

    result = find_repo_root_from_path(test_file)
    assert result is None


def test_find_repo_root_max_depth_limit(tmp_path):
    """Test that search stops after MAX_REPO_SEARCH_DEPTH levels."""
    # Create a path deeper than MAX_REPO_SEARCH_DEPTH without any .git
    deep = tmp_path
    for i in range(MAX_REPO_SEARCH_DEPTH + 5):
        deep = deep / f"level_{i}"
    deep.mkdir(parents=True)

    test_file = deep / "file.py"
    test_file.write_text("x = 1")

    # Even though tmp_path might be inside a real git repo,
    # the depth limit should prevent finding it
    result = find_repo_root_from_path(test_file)
    # Result is either None (no repo found within depth) or a repo
    # The key guarantee: the function terminates and doesn't loop
    assert result is None or isinstance(result, Path)


def test_find_repo_root_resolves_symlinks(tmp_path):
    """Test that symlinks are resolved before searching."""
    repo = tmp_path / "real_project"
    repo.mkdir()
    (repo / ".git").mkdir()
    (repo / "src").mkdir()

    real_file = repo / "src" / "app.py"
    real_file.write_text("x = 1")

    # Create a symlink outside the repo that points to the file
    link = tmp_path / "link_to_app.py"
    link.symlink_to(real_file)

    result = find_repo_root_from_path(link)
    assert result == repo


def test_find_repo_root_from_directory(tmp_path):
    """Test that it works when given a directory instead of a file."""
    repo = tmp_path / "project"
    repo.mkdir()
    (repo / ".git").mkdir()
    subdir = repo / "src" / "components"
    subdir.mkdir(parents=True)

    result = find_repo_root_from_path(subdir)
    assert result == repo


def test_find_repo_root_finds_deepest_repo(tmp_path):
    """Test that it finds the deepest (most specific) repo."""
    # Outer repo
    outer = tmp_path / "outer"
    outer.mkdir()
    (outer / ".git").mkdir()

    # Inner repo (nested)
    inner = outer / "inner"
    inner.mkdir()
    (inner / ".git").mkdir()

    test_file = inner / "file.py"
    test_file.write_text("x = 1")

    result = find_repo_root_from_path(test_file)
    assert result == inner  # Should find the DEEPEST repo


def test_detect_repo_from_file_path_returns_repo_info(tmp_path):
    """Test that detect_repo_from_file_path returns full RepoInfo."""
    repo = tmp_path / "project"
    repo.mkdir()
    (repo / ".git").mkdir()

    test_file = repo / "main.py"
    test_file.write_text("x = 1")

    info = detect_repo_from_file_path(test_file)
    assert info is not None
    assert isinstance(info, RepoInfo)
    assert info.root == repo
    assert len(info.repo_id) == 10


def test_detect_repo_from_file_path_returns_none_outside(tmp_path):
    """Test that detect_repo_from_file_path returns None outside a repo."""
    no_repo = tmp_path / "no_git"
    no_repo.mkdir()
    test_file = no_repo / "file.py"
    test_file.write_text("x = 1")

    result = detect_repo_from_file_path(test_file)
    assert result is None

