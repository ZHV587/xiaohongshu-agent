"""Activate content grading for structured Xiaohongshu responses."""

from typing import Any

from langchain.agents.middleware import AgentMiddleware
from langchain_core.messages import AIMessage


DEFAULT_CONTENT_RUBRIC = """评估最终的小红书内容是否满足以下标准:
1. 输出遵守 xhs_topics 或 xhs_copy 结构约定,字段完整且内容可用
2. 标题有点击钩子,正文自然、具体、无明显 AI 腔
3. 引用的数据包含实际采用来源的 resource_id、摘要和 updated_at
4. 事实受来源支持,过时信息说明时效限制,创意推断明确标注为推断
5. 数据不足时明确说明,不编造来源、事实或结论
6. xhs_copy 的标签与内容相关且数量合理
"""

_STRUCTURED_CONTENT_FENCES = ("```xhs_topics", "```xhs_copy")


class ContentRubricActivator(AgentMiddleware):
    """Supply the default rubric when the final response is structured content."""

    def after_agent(self, state: dict[str, Any], runtime: Any) -> dict[str, str] | None:
        if state.get("rubric"):
            return None

        messages = state.get("messages", [])
        if not messages or not isinstance(messages[-1], AIMessage):
            return None

        content = messages[-1].content
        if not isinstance(content, str):
            return None
        if not any(fence in content for fence in _STRUCTURED_CONTENT_FENCES):
            return None

        return {"rubric": DEFAULT_CONTENT_RUBRIC}
