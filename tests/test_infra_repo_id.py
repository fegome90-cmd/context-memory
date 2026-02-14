"""Tests for repository detection and ID generation."""



from infrastructure.repo import (
    find_repo_root,
    generate_stable_repo_id,
    RepoInfo,
    detect_repo,
    REPO_ID_FILE,
)


def test_find_repo_root_finds_git_dir(repo_root):
    """Test finding repository root by .git directory."""
    found = find_repo_root(repo_root)

    assert found == repo_root
    assert (found / ".git").exists()


def test_find_repo_root_searches_upward(temp_dir):
    """Test that repo root search goes upward."""
    # Create .git at temp_dir
    (temp_dir / ".git").mkdir()

    # Create nested structure
    (temp_dir / "subdir" / "nested").mkdir(parents=True)

    # Change to nested directory and search
    import os
    original_cwd = os.getcwd()
    try:
        os.chdir(temp_dir / "subdir" / "nested")
        found = find_repo_root()
        assert found == temp_dir
    finally:
        os.chdir(original_cwd)


def test_generate_repo_id_creates_file(repo_root):
    """Test that repo ID generation creates ID file."""
    repo_id = generate_stable_repo_id(repo_root)

    # Should create .claude/context-memory-id
    id_file = repo_root / REPO_ID_FILE
    assert id_file.exists()

    # Should be readable
    assert id_file.read_text().strip() == repo_id

    # Should be consistent on second call
    repo_id_2 = generate_stable_repo_id(repo_root)
    assert repo_id == repo_id_2


def test_generate_repo_id_is_hex_string(repo_root):
    """Test that repo ID is a hex string."""
    repo_id = generate_stable_repo_id(repo_root)

    assert len(repo_id) == 10
    assert all(c in "0123456789abcdef" for c in repo_id)


def test_detect_repo_returns_repo_info(repo_root):
    """Test detecting repo info."""
    repo_info = detect_repo(repo_root)

    assert isinstance(repo_info, RepoInfo)
    assert repo_info.root == repo_root
    assert repo_info.repo_id
    assert len(repo_info.repo_id) == 10


def test_detect_repo_from_current_dir(repo_root):
    """Test detecting repo from current working directory."""
    import os
    original_cwd = os.getcwd()

    try:
        os.chdir(repo_root)
        repo_info = detect_repo()

        assert repo_info is not None
        assert repo_info.root == repo_root
    finally:
        os.chdir(original_cwd)


def test_detect_repo_returns_none_outside_git(temp_dir):
    """Test that detection returns None outside of git."""
    # No .git directory here
    found = find_repo_root(temp_dir)

    # Should return None when not in a git repo
    assert found is None


def test_repo_info_to_dict(repo_root):
    """Test converting RepoInfo to dictionary."""
    repo_info = detect_repo(repo_root)
    d = repo_info.to_dict()

    assert "root" in d
    assert "repo_id" in d
    assert "branch" in d
    assert "remote_url" in d
