"""Activate content grading for structured Xiaohongshu responses."""

from typing import Any

from langchain.agents.middleware import AgentMiddleware
from langchain_core.messages import AIMessage


DEFAULT_CONTENT_RUBRIC = """评估最终的小红书内容是否满足以下标准:
1. 输出遵守 xhs_copy 结构约定,字段完整且内容可用
2. 标题有点击钩子,正文自然、具体、无明显 AI 腔
3. 引用的**库内采用来源**包含 resource_id、摘要、source_updated_at 和 indexed_at;**双源出选题的线上实时趋势来源**(用户尚未采纳)允许只标 note_url、无 resource_id 与时效,只要在选题角度注明"(线上实时:note_url)"且不冒充正式依据即可——**不得因线上来源缺 resource_id 判为不合格,也不要为补 resource_id 而自动采纳(采纳由用户在面板触发)**
4. 事实受来源支持,源端过时信息说明时效限制,indexed_at 不得冒充源端更新时间,创意推断明确标注为推断;**来源时效未知时如实写"未知"即可,无须额外解释原因**
5. 数据不足时明确说明,不编造来源、事实或结论
6. xhs_copy 的标签与内容相关且数量合理
"""

# 只对 xhs_copy(最终交付物)激活质检,不对 xhs_topics(中间选题菜单):
# 选题依据(evidence)由前端经 InjectedState 权威直传、结构性已保证,无需 grader 兜;
# 文案依据由 LLM 在 save_generated_copy 时提供,才真正需要质检。把强模型质检收敛到
# 真正需要的交付物上,常见 topic→copy 流程质检调用约减半,显著降本。
_STRUCTURED_CONTENT_FENCES = ("```xhs_copy",)


class ContentRubricActivator(AgentMiddleware):
    """Supply the default rubric when the final response is a finished xhs_copy deliverable."""

    def after_agent(self, state: dict[str, Any], runtime: Any) -> dict[str, str] | None:
        if state.get("rubric"):
            return None

        messages = state.get("messages", [])
        if not messages or not isinstance(messages[-1], AIMessage):
            return None

        content = _message_text(messages[-1].content)
        if not content:
            return None
        if not any(fence in content for fence in _STRUCTURED_CONTENT_FENCES):
            return None

        return {"rubric": DEFAULT_CONTENT_RUBRIC}


def _message_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return ""

    parts: list[str] = []
    for block in content:
        if isinstance(block, str):
            parts.append(block)
        elif isinstance(block, dict) and isinstance(block.get("text"), str):
            parts.append(block["text"])
    return "\n".join(parts)
