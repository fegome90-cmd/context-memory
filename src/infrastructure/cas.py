"""
Content-Addressable Storage (CAS) for optional file snapshots.

Provides:
- Hash-based file storage
- Drift detection (compare current to snapshot)
- Optional exact rehydration
"""

import hashlib
from pathlib import Path
from typing import Optional


def compute_sha256(file_path: Path) -> str:
    """
    Compute SHA256 hash of a file.

    Args:
        file_path: Path to file

    Returns:
        Hexadecimal SHA256 hash
    """
    sha256 = hashlib.sha256()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            sha256.update(chunk)
    return sha256.hexdigest()


class CAS:
    """
    Content-Addressable Storage.

    Stores file snapshots by SHA256 hash.
    """

    def __init__(self, storage_dir: Path):
        """
        Initialize CAS storage.

        Args:
            storage_dir: Directory for CAS storage
        """
        self.storage_dir = storage_dir
        self.storage_dir.mkdir(parents=True, exist_ok=True)

    def store(self, file_path: Path) -> str:
        """
        Store a file in CAS.

        Args:
            file_path: Path to file to store

        Returns:
            SHA256 hash of stored file
        """
        sha256 = compute_sha256(file_path)

        # Copy file to CAS
        cas_path = self.storage_dir / sha256
        if not cas_path.exists():
            import shutil
            shutil.copy2(file_path, cas_path)

        return sha256

    def retrieve(self, sha256: str, dest_path: Path) -> bool:
        """
        Retrieve a file from CAS.

        Args:
            sha256: Hash of file to retrieve
            dest_path: Where to copy the file

        Returns:
            True if retrieved, False if not found
        """
        cas_path = self.storage_dir / sha256
        if not cas_path.exists():
            return False

        import shutil
        dest_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(cas_path, dest_path)
        return True

    def has(self, sha256: str) -> bool:
        """
        Check if a hash exists in CAS.

        Args:
            sha256: Hash to check

        Returns:
            True if exists, False otherwise
        """
        return (self.storage_dir / sha256).exists()

    def get_path(self, sha256: str) -> Optional[Path]:
        """
        Get path to CAS entry.

        Args:
            sha256: Hash to look up

        Returns:
            Path to CAS entry, or None if not found
        """
        cas_path = self.storage_dir / sha256
        return cas_path if cas_path.exists() else None

    def size(self) -> int:
        """
        Get total size of CAS storage in bytes.

        Returns:
            Size in bytes
        """
        total = 0
        for path in self.storage_dir.iterdir():
            if path.is_file():
                total += path.stat().st_size
        return total

    def count(self) -> int:
        """
        Get number of entries in CAS.

        Returns:
            Number of stored files
        """
        return sum(1 for _ in self.storage_dir.iterdir() if _.is_file())
