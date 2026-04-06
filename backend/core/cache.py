"""FundOps Shared Cache — file-based caching for API responses.

Replaces the duplicated caching logic in Scout and Val. Each agent gets
its own cache namespace but shares the same cache infrastructure.
"""

import json
import time
from pathlib import Path
from typing import Any, Optional


class FileCache:
    """Simple file-based cache with TTL support.

    Cache files are JSON. Each file stores:
        {"data": ..., "cached_at": unix_timestamp}
    """

    def __init__(self, cache_dir: Path | str, default_max_age_hours: int = 12):
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.default_max_age_s = default_max_age_hours * 3600

    def _key_to_path(self, key: str) -> Path:
        """Convert a cache key to a file path. Keys can contain / for namespacing."""
        safe_key = key.replace("/", "_").replace(":", "_")
        return self.cache_dir / f"{safe_key}.json"

    def get(self, key: str, max_age_hours: float = None) -> Optional[Any]:
        """Get cached data if fresh enough. Returns None if missing or stale."""
        path = self._key_to_path(key)
        if not path.exists():
            return None

        try:
            with open(path) as f:
                entry = json.load(f)
        except (json.JSONDecodeError, IOError):
            return None

        cached_at = entry.get("cached_at", 0)
        max_age = (max_age_hours * 3600) if max_age_hours is not None else self.default_max_age_s
        if time.time() - cached_at > max_age:
            return None

        return entry.get("data")

    def set(self, key: str, data: Any) -> None:
        """Store data in cache."""
        path = self._key_to_path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w") as f:
            json.dump({"data": data, "cached_at": time.time()}, f, default=str)

    def invalidate(self, key: str) -> None:
        """Remove a cached entry."""
        path = self._key_to_path(key)
        if path.exists():
            path.unlink()

    def clear(self) -> int:
        """Clear all cached entries. Returns count of files removed."""
        count = 0
        for f in self.cache_dir.glob("*.json"):
            f.unlink()
            count += 1
        return count

    def stats(self) -> dict:
        """Get cache statistics."""
        files = list(self.cache_dir.glob("*.json"))
        total_size = sum(f.stat().st_size for f in files)
        return {
            "entries": len(files),
            "total_size_mb": round(total_size / 1024 / 1024, 2),
            "cache_dir": str(self.cache_dir),
        }
