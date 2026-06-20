from __future__ import annotations

from collections.abc import Mapping

from data_foundation.models import ProcessorState
from data_foundation.processors.base import Processor


DEFAULT_TOPICS = ("embedding_generate", "graph_ingest", "meili_index")


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
