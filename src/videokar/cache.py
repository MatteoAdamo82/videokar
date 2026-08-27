"""On-disk cache keyed by audio content.

Separation is the slow part of the pipeline — minutes per track — and it only
depends on the audio, never on the lyrics or the styling. Keying the cache on a
hash of the file means you can rewrite the lyrics, restyle the video and re-run
as often as you like without paying for demucs again, and moving or renaming the
audio still hits the same entry.
"""

from __future__ import annotations

import hashlib
import os
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path

_CHUNK = 1 << 20


def cache_root() -> Path:
    """Base cache directory, overridable with VIDEOKAR_CACHE_DIR."""
    override = os.environ.get("VIDEOKAR_CACHE_DIR")
    if override:
        return Path(override).expanduser()
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Caches" / "videokar"
    xdg = os.environ.get("XDG_CACHE_HOME")
    return (Path(xdg) if xdg else Path.home() / ".cache") / "videokar"


def file_digest(path: str | Path) -> str:
    """SHA-256 of a file's contents, hex."""
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        while chunk := handle.read(_CHUNK):
            digest.update(chunk)
    return digest.hexdigest()


@dataclass(frozen=True, slots=True)
class AudioCache:
    """Cache entries belonging to one audio file."""

    digest: str
    directory: Path

    @classmethod
    def for_audio(cls, path: str | Path) -> AudioCache:
        digest = file_digest(path)
        directory = cache_root() / digest[:16]
        return cls(digest=digest, directory=directory)

    def path(self, name: str) -> Path:
        """Path of one cache entry. The directory is created on demand."""
        self.directory.mkdir(parents=True, exist_ok=True)
        return self.directory / name

    def has(self, name: str) -> bool:
        entry = self.directory / name
        return entry.exists() and entry.stat().st_size > 0


def cache_size() -> int:
    """Total bytes held in the cache."""
    root = cache_root()
    if not root.exists():
        return 0
    return sum(f.stat().st_size for f in root.rglob("*") if f.is_file())


def clear_cache() -> int:
    """Delete the whole cache, returning the number of bytes reclaimed."""
    root = cache_root()
    freed = cache_size()
    if root.exists():
        shutil.rmtree(root)
    return freed
