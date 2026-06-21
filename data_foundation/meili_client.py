from __future__ import annotations

from typing import Any

import meilisearch

from data_foundation.engine_config import MeiliConfig


class MeiliResourceIndex:
    SEARCHABLE = ["title", "summary", "content_text"]
    FILTERABLE = ["tenant_id", "type"]

    def __init__(self, *, client: Any, index_uid: str = "resources"):
        self.client = client
        self.index_uid = index_uid

    @classmethod
    def from_config(cls, config: MeiliConfig) -> "MeiliResourceIndex":
        client = meilisearch.Client(config.url, config.api_key)
        return cls(client=client)

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
