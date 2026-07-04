from __future__ import annotations

import threading
from typing import Any

import meilisearch

from data_foundation.engine_config import MeiliConfig


# 模块级底层 client 缓存:按 (url, api_key) 复用 meilisearch.Client,避免每次工具调用/
# 每 cycle 新建 HTTP 客户端。config 变化(换地址/key)自动建新实例。
_client_cache: dict[tuple[str, str], Any] = {}
_cache_lock = threading.Lock()


def _reset_client_cache() -> None:
    with _cache_lock:
        _client_cache.clear()


def _get_client(config: MeiliConfig) -> Any:
    key = (config.url, config.api_key)
    with _cache_lock:
        client = _client_cache.get(key)
        if client is None:
            # timeout(秒):防 Meili 卡顿时工作线程无限阻塞。即便已 asyncio.to_thread 卸到线程,
            # 无超时的 hung socket 会永久占用线程、积压重试也卡住,故必须有硬上限。
            client = meilisearch.Client(config.url, config.api_key, timeout=30)
            _client_cache[key] = client
        return client


class MeiliResourceIndex:
    SEARCHABLE = ["title", "summary", "content_text"]
    FILTERABLE = ["tenant_id", "type"]

    def __init__(self, *, client: Any, index_uid: str = "resources"):
        self.client = client
        self.index_uid = index_uid

    @classmethod
    def from_config(cls, config: MeiliConfig) -> "MeiliResourceIndex":
        return cls(client=_get_client(config))

    def ensure_index(self) -> None:
        index = self.client.index(self.index_uid)
        index.update_filterable_attributes(self.FILTERABLE)
        index.update_searchable_attributes(self.SEARCHABLE)

    def upsert(self, document: dict[str, Any]) -> None:
        # add_documents 是**异步入队**:返回 TaskInfo 即返回,Meili 端任务可能稍后才应用甚至失败。
        # 若不等待,outbox 会在文档实际入库前就被标 succeeded —— 任务失败时 PG 说成功、Meili 里没有,
        # 且无 reconcile 重推 → 永久静默空洞。故等任务终态并校验,失败抛出让 outbox 重试。
        index = self.client.index(self.index_uid)
        info = index.add_documents([document], primary_key="resource_id")
        task = index.wait_for_task(info.task_uid, timeout_in_ms=30000)
        status = getattr(task, "status", None)
        if status != "succeeded":
            raise RuntimeError(
                f"Meili add_documents task not succeeded: status={status} "
                f"error={getattr(task, 'error', None)}"
            )

    def delete(self, resource_id: str) -> None:
        """物理删除单个资源文档,使 Meili 与核心库一致(资源已从 PG 消失时调用)。

        与 upsert 同理:delete_document 是异步入队,须等任务终态并校验,否则 outbox 会在文档
        实际删除前就被标记完成 —— 删除失败时核心库已无、Meili 仍残留,且无重推路径 → 永久脏数据。
        对不存在的文档,Meili 删除任务同样返回 succeeded(幂等),故重复删除安全。
        """
        index = self.client.index(self.index_uid)
        info = index.delete_document(resource_id)
        task = index.wait_for_task(info.task_uid, timeout_in_ms=30000)
        status = getattr(task, "status", None)
        if status != "succeeded":
            raise RuntimeError(
                f"Meili delete_document task not succeeded: status={status} "
                f"error={getattr(task, 'error', None)}"
            )

    def count(self, *, tenant_id: str) -> int:
        """按 tenant 统计索引内文档数(对账用)。limit=0 只取总数不取命中。"""
        result = self.client.index(self.index_uid).search(
            "",
            opt_params={"filter": f'tenant_id = "{tenant_id}"', "limit": 0},
        )
        return int(result.get("estimatedTotalHits") or result.get("totalHits") or 0)

    def search(self, query: str, *, tenant_id: str, limit: int) -> list[tuple[str, float]]:
        # showRankingScore:让 Meili 返回 _rankingScore(0~1 归一化相关度),
        # 贯通到 rank_evidence 作 BM25 口径排序依据;否则全文相关度信号丢失。
        result = self.client.index(self.index_uid).search(
            query,
            opt_params={
                "filter": f'tenant_id = "{tenant_id}"',
                "limit": limit,
                "showRankingScore": True,
            },
        )
        return [
            (hit["resource_id"], float(hit.get("_rankingScore") or 0.0))
            for hit in result.get("hits", [])
        ]
