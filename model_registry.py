from __future__ import annotations

import threading
import time
from dataclasses import dataclass

from models import ModelCandidate


@dataclass(frozen=True)
class RegistrySnapshot:
    version: str
    pool: list[ModelCandidate]
    loaded_at: float
    last_error: str | None = None


class ModelRegistry:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._snapshot = RegistrySnapshot(version="", pool=[], loaded_at=0.0)

    def replace(self, version: str, pool: list[ModelCandidate]) -> None:
        if not pool:
            raise ValueError("ModelRegistry requires at least one model candidate")
        with self._lock:
            self._snapshot = RegistrySnapshot(version=version, pool=list(pool), loaded_at=time.time())

    def record_error(self, message: str) -> None:
        with self._lock:
            current = self._snapshot
            self._snapshot = RegistrySnapshot(
                version=current.version,
                pool=current.pool,
                loaded_at=current.loaded_at,
                last_error=message,
            )

    def get_pool(self) -> list[ModelCandidate]:
        with self._lock:
            return list(self._snapshot.pool)

    def status(self) -> dict[str, object]:
        with self._lock:
            return {
                "version": self._snapshot.version,
                "loaded_at": self._snapshot.loaded_at,
                "active_models": [candidate.model_id for candidate in self._snapshot.pool],
                "last_error": self._snapshot.last_error,
                "hot_reload_coverage": {
                    "main_agent": True,
                    "server_async": True,
                    "subagents": True,
                    "rubric": False,
                },
            }
