"""统一证据契约(retrieval-flow-consolidation)。

EvidencePackage 是**检索步骤的证据产出契约**,不是各创作技能的最终输出。
三处复用、口径统一:
1. knowledge-atom-retriever 子代理的 ``response_format``(框架强制结构化输出);
2. 检索工具(search_resources/semantic_search_resources)返回结构对齐它;
3. 最终 xhs_topics/xhs_copy 的 evidence 块(字段子集对齐,不破前端契约)。

字段名沿用既有工具与前端 types.ts 的 ``why_selected``,不引入新名。
时效字段 ``source_updated_at``/``indexed_at`` 恒为字符串,未知写"未知",不得以
``updated_at`` 替代。pydantic 已由 deepagents 传递依赖,无新增第三方依赖。
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, model_validator

RetrievalMode = Literal["semantic", "keyword_fallback", "insufficient_relevance"]


class EvidenceItem(BaseModel):
    """单条证据。字段口径与检索工具返回结构、xhs_topics/xhs_copy 的 evidence 块对齐。"""

    resource_id: str
    title: str
    summary: str
    source_updated_at: str = Field(
        description='源端更新时间;未知写"未知",不得猜测或伪造,不得以 updated_at 替代'
    )
    indexed_at: str = Field(
        description='本地索引时间;未知写"未知",不得猜测或伪造'
    )
    score: float = Field(description="绝对相关度(cosine)或 bm25 归一化分")
    why_selected: str = Field(
        description="为何选它。沿用现有工具/前端既有字段名 why_selected,不引入 why_relevant"
    )


class EvidencePackage(BaseModel):
    """统一证据包。knowledge-atom-retriever 的 response_format;检索工具/最终 evidence 块对齐它。"""

    retrieval_mode: RetrievalMode
    evidence: list[EvidenceItem] = Field(default_factory=list)
    gaps: str | None = Field(
        default=None,
        description='数据不足/缺什么;retrieval_mode == "insufficient_relevance" 时必填',
    )

    @model_validator(mode="after")
    def _check_insufficient_relevance(self) -> "EvidencePackage":
        # 数据不足必明说:无相关证据(evidence 空)且 gaps 说明缺什么;不返回弱相关结果。
        if self.retrieval_mode == "insufficient_relevance":
            if self.evidence:
                raise ValueError(
                    "insufficient_relevance requires empty evidence (do not return weak matches)"
                )
            if not (self.gaps and self.gaps.strip()):
                raise ValueError("insufficient_relevance requires a non-empty gaps explanation")
        return self


__all__ = ["RetrievalMode", "EvidenceItem", "EvidencePackage"]
