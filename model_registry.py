from __future__ import annotations

import threading
import time
from dataclasses import dataclass

from config_center import ConfigSnapshot
from models import ModelCandidate, build_pool_from_config


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

    def current_version(self) -> str:
        with self._lock:
            return self._snapshot.version

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
                    "rubric": True,
                },
            }

    def reload_from_config(self, snapshot: ConfigSnapshot, *, force_discover: bool = False) -> bool:
        """按 config-center 快照重建模型池(探测∩白名单按质量序)。

        force_discover:定时健康探测/配置保存 verify 传 True,强制重探不吃缓存。
        返回是否成功换池:
        - 成功:replace 新池,返回 True。
        - 全挂(白名单内无任一模型被探测确认可用,build_pool_from_config raise):
          record_error 记录原因供 admin 可见,但**保留旧活跃池继续服务**、不 replace、
          不 re-raise,返回 False。绝不把未探测确认的模型塞进池;调用方据返回值决定
          是否告警/重试,但运行中的旧池不受影响(降级而非中断)。
        """
        try:
            pool = build_pool_from_config(snapshot.values, force_discover=force_discover)
        except Exception as exc:
            self.record_error(str(exc))
            return False
        self.replace(version=snapshot.version, pool=pool)
        return True
