from __future__ import annotations

from collections.abc import Mapping

from data_foundation.sources.base import SourceProcessor
from data_foundation.sources.feishu import FeishuBaseSourceProcessor, FeishuWikiSourceProcessor


class SourceProcessorRegistry:
    def __init__(self, processors: Mapping[str, SourceProcessor] | None = None):
        self._processors = dict(processors or {})

    @property
    def source_types(self) -> list[str]:
        return sorted(self._processors)

    def processor_for(self, source_type: str) -> SourceProcessor | None:
        return self._processors.get(source_type)


def default_feishu_source_registry(resource_repo) -> SourceProcessorRegistry:
    return SourceProcessorRegistry(
        {
            "feishu_base": FeishuBaseSourceProcessor(resource_repo=resource_repo),
            "feishu_wiki": FeishuWikiSourceProcessor(resource_repo=resource_repo),
        }
    )
