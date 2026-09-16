"""Disk cache for System One responses so re-runs replay instead of paying for inference.

Keyed on a hash of the full request payload (state + model + questions), so tuning
thresholds, weights, or display code never re-asks the model for an answer that has not
changed. `--no-cache` bypasses both read and write; `--offline` reads only.
"""

from __future__ import annotations

import hashlib
import json
import threading
from pathlib import Path
from typing import Any, Optional


def request_key(payload: dict[str, Any]) -> str:
    blob = json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:32]


class JsonCache:
    """A flat {key: response} JSON store with hit/miss accounting."""

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self._data: dict[str, Any] = {}
        self._lock = threading.RLock()  # reentrant: put() holds it across its save() call
        self.hits = 0
        self.misses = 0
        if self.path.exists():
            try:
                loaded = json.loads(self.path.read_text(encoding="utf-8"))
                if isinstance(loaded, dict):
                    self._data = loaded
            except (OSError, json.JSONDecodeError):
                self._data = {}

    def __len__(self) -> int:
        return len(self._data)

    def get(self, payload: dict[str, Any]) -> Optional[dict[str, Any]]:
        hit = self._data.get(request_key(payload))
        if hit is None:
            self.misses += 1
            return None
        self.hits += 1
        return hit

    def put(self, payload: dict[str, Any], response: dict[str, Any]) -> None:
        with self._lock:
            self._data[request_key(payload)] = response
            self.save()

    def save(self) -> None:
        with self._lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.path.with_suffix(self.path.suffix + ".tmp")
            tmp.write_text(json.dumps(self._data, indent=1, sort_keys=True), encoding="utf-8")
            tmp.replace(self.path)
