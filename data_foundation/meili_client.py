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
            client = meilisearch.Client(config.url, config.api_key)
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
        self.client.index(self.index_uid).add_documents([document], primary_key="resource_id")

    def search(self, query: str, *, tenant_id: str, limit: int) -> list[str]:
        result = self.client.index(self.index_uid).search(
            query,
            opt_params={"filter": f'tenant_id = "{tenant_id}"', "limit": limit},
        )
        return [hit["resource_id"] for hit in result.get("hits", [])]
