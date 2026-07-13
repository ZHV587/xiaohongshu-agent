from __future__ import annotations

from collections.abc import Callable, Mapping

from psycopg import Connection

from data_foundation.models import ProcessorState
from data_foundation.processors.embedding import (
    EmbeddingProcessor,
    EmbeddingProviderConfig,
    embedding_config_from_runtime,
)
from data_foundation.processors.base import Processor


DEFAULT_TOPICS = (
    "embedding_generate",
    "graph_ingest",
    "knowledge_enrich",
    "meili_index",
    "preference_synthesize",
)


class ProcessorRegistry:
    def __init__(self, processors: Mapping[str, Processor] | None = None):
        self._processors = dict(processors or {})

    @property
    def topics(self) -> list[str]:
        return sorted(set(DEFAULT_TOPICS) | set(self._processors))

    def processor_for(self, topic: str) -> Processor | None:
        return self._processors.get(topic)

    def state_for(self, topic: str) -> ProcessorState:
        processor = self.processor_for(topic)
        if processor is None:
            return ProcessorState(
                topic=topic,
                status="disabled",
                config_version=None,
                reason_code="PROCESSOR_DISABLED",
            )
        state = processor.state()
        if state is None:
            return ProcessorState(
                topic=topic,
                status="active",
                config_version=None,
                reason_code=None,
            )
        return state


_UNSET = object()


def default_processor_registry(
    conn: Connection,
    *,
    embedding_config: EmbeddingProviderConfig | None | object = _UNSET,
    preference_connection_factory: Callable[[], Connection] | None = None,
) -> ProcessorRegistry:
    if embedding_config is _UNSET:
        embedding_config = embedding_config_from_runtime()
    from data_foundation.engine_config import falkor_config_from_env, meili_config_from_env
    from data_foundation.falkor_client import FalkorResourceGraph
    from data_foundation.meili_client import MeiliResourceIndex
    from data_foundation.processors.graph import GraphProcessor
    from data_foundation.processors.knowledge import KnowledgeEnrichProcessor
    from data_foundation.processors.meili import MeiliProcessor
    from data_foundation.processors.preference import PreferenceSynthesizeProcessor

    meili_cfg = meili_config_from_env()
    meili_index = MeiliResourceIndex.from_config(meili_cfg) if meili_cfg.state == "enabled" else None
    falkor_cfg = falkor_config_from_env()
    falkor_graph = FalkorResourceGraph.from_config(falkor_cfg) if falkor_cfg.state == "enabled" else None
    return ProcessorRegistry(
        {
            "embedding_generate": EmbeddingProcessor(
                conn,
                config=embedding_config,
            ),
            "knowledge_enrich": KnowledgeEnrichProcessor(conn),
            "preference_synthesize": PreferenceSynthesizeProcessor(
                conn,
                connection_factory=preference_connection_factory,
            ),
            "meili_index": MeiliProcessor(conn, index=meili_index, config=meili_cfg),
            "graph_ingest": GraphProcessor(conn, graph=falkor_graph, config=falkor_cfg),
        }
    )
