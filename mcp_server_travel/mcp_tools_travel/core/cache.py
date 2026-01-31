from __future__ import annotations

import hashlib
import json
import os
import time
from dataclasses import dataclass
from typing import Any, Dict, Optional


@dataclass
class FileCache:
    """Simple file-based JSON cache with TTL.

    Why:
    - Token-free APIs still rate-limit (Overpass/Nominatim especially).
    - Notebooks should be reproducible and fast.
    - Caching makes trainings stable.
    """
    cache_dir: str
    ttl_seconds: int = 24 * 3600  # 1 day default

    def __post_init__(self) -> None:
        os.makedirs(self.cache_dir, exist_ok=True)

    def _path_for_key(self, key: str) -> str:
        h = hashlib.sha256(key.encode("utf-8")).hexdigest()
        return os.path.join(self.cache_dir, f"{h}.json")

    def get(self, key: str) -> Optional[Dict[str, Any]]:
        path = self._path_for_key(key)
        if not os.path.exists(path):
            return None
        try:
            with open(path, "r", encoding="utf-8") as f:
                payload = json.load(f)
            ts = payload.get("_cached_at")
            if ts is None:
                return payload
            if (time.time() - ts) > self.ttl_seconds:
                return None
            return payload
        except Exception:
            return None

    def set(self, key: str, value: Dict[str, Any]) -> None:
        path = self._path_for_key(key)
        payload = dict(value)
        payload["_cached_at"] = time.time()
        with open(path, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
