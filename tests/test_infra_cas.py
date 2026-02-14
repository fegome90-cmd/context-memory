"""Tests for Content-Addressable Storage (CAS)."""


import pytest

from infrastructure.cas import CAS, compute_sha256


@pytest.fixture
def temp_cas_dir(tmp_path):
    """Create a temporary CAS directory."""
    cas_dir = tmp_path / "cas"
    cas_dir.mkdir()
    yield cas_dir
    # Cleanup is automatic with tmp_path


@pytest.fixture
def sample_file(tmp_path):
    """Create a sample test file."""
    test_file = tmp_path / "test.txt"
    test_file.write_text("Hello, World!")
    return test_file


def test_compute_sha256(sample_file):
    """Test SHA256 hash computation."""
    hash1 = compute_sha256(sample_file)
    hash2 = compute_sha256(sample_file)

    # Same file should produce same hash
    assert hash1 == hash2
    assert len(hash1) == 64  # SHA256 is 64 hex chars
    assert all(c in "0123456789abcdef" for c in hash1)


def test_compute_sha256_different_files(tmp_path):
    """Test that different files produce different hashes."""
    file1 = tmp_path / "file1.txt"
    file2 = tmp_path / "file2.txt"

    file1.write_text("content1")
    file2.write_text("content2")

    hash1 = compute_sha256(file1)
    hash2 = compute_sha256(file2)

    assert hash1 != hash2


def test_cas_store_retrieve(temp_cas_dir, sample_file):
    """Test storing and retrieving a file."""
    cas = CAS(temp_cas_dir)

    # Store file
    sha256 = cas.store(sample_file)

    # Check it was stored
    assert cas.has(sha256)

    # Retrieve to new location
    dest = temp_cas_dir / "retrieved.txt"
    assert cas.retrieve(sha256, dest)

    # Verify content
    assert dest.read_text() == sample_file.read_text()


def test_cas_store_same_file_twice(temp_cas_dir, sample_file):
    """Test storing the same file twice doesn't duplicate."""
    cas = CAS(temp_cas_dir)

    # Store same file twice
    hash1 = cas.store(sample_file)
    hash2 = cas.store(sample_file)

    # Should have same hash
    assert hash1 == hash2

    # Should only have one entry
    assert cas.count() == 1


def test_cas_retrieve_nonexistent(temp_cas_dir):
    """Test retrieving a file that doesn't exist."""
    cas = CAS(temp_cas_dir)

    dest = temp_cas_dir / "result.txt"
    assert not cas.retrieve("nonexistent_hash", dest)
    assert not dest.exists()


def test_cas_has(temp_cas_dir, sample_file):
    """Test checking if hash exists."""
    cas = CAS(temp_cas_dir)

    sha256 = cas.store(sample_file)

    # Should exist after storing
    assert cas.has(sha256)

    # Should not exist for random hash
    assert not cas.has("0" * 64)


def test_cas_get_path(temp_cas_dir, sample_file):
    """Test getting path to CAS entry."""
    cas = CAS(temp_cas_dir)

    sha256 = cas.store(sample_file)

    # Should return path when exists
    path = cas.get_path(sha256)
    assert path is not None
    assert path.name == sha256

    # Should return None for nonexistent
    assert cas.get_path("fake_hash") is None


def test_cas_count(temp_cas_dir, tmp_path):
    """Test counting entries in CAS."""
    cas = CAS(temp_cas_dir)

    # Empty CAS
    assert cas.count() == 0

    # Add some files
    file1 = tmp_path / "file1.txt"
    file2 = tmp_path / "file2.txt"
    file1.write_text("content1")
    file2.write_text("content2")

    cas.store(file1)
    assert cas.count() == 1

    cas.store(file2)
    assert cas.count() == 2


def test_cas_size(temp_cas_dir, tmp_path):
    """Test getting total CAS size."""
    cas = CAS(temp_cas_dir)

    # Empty CAS
    assert cas.size() == 0

    # Add a file
    test_file = tmp_path / "test.txt"
    test_file.write_text("x" * 1000)  # 1KB
    cas.store(test_file)

    # Size should be ~1KB
    assert cas.size() >= 1000
    assert cas.size() < 2000  # Should be close


def test_cas_creates_storage_dir(tmp_path):
    """Test that CAS creates storage directory if missing."""
    cas_dir = tmp_path / "new_cas"
    assert not cas_dir.exists()

    cas = CAS(cas_dir)

    # Directory should be created
    assert cas_dir.exists()
    assert cas_dir.is_dir()


def test_cas_retrieve_creates_parent_dirs(temp_cas_dir, sample_file):
    """Test that retrieve creates parent directories."""
    cas = CAS(temp_cas_dir)

    sha256 = cas.store(sample_file)

    # Deep nested destination
    dest = temp_cas_dir / "a" / "b" / "c" / "result.txt"
    assert cas.retrieve(sha256, dest)

    # Parent dirs should be created
    assert dest.exists()
    assert dest.parent.exists()


def test_cas_handles_binary_files(temp_cas_dir, tmp_path):
    """Test that CAS handles binary files correctly."""
    cas = CAS(temp_cas_dir)

    # Create binary file
    binary_file = tmp_path / "binary.bin"
    binary_file.write_bytes(bytes(range(256)))

    # Store and retrieve
    sha256 = cas.store(binary_file)
    dest = temp_cas_dir / "restored.bin"
    cas.retrieve(sha256, dest)

    # Verify binary content
    assert dest.read_bytes() == binary_file.read_bytes()


def test_cas_empty_file(temp_cas_dir, tmp_path):
    """Test storing an empty file."""
    cas = CAS(temp_cas_dir)

    empty_file = tmp_path / "empty.txt"
    empty_file.write_text("")

    sha256 = cas.store(empty_file)

    # Should still store
    assert cas.has(sha256)
    assert cas.count() == 1
