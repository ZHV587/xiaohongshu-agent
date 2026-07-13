from __future__ import annotations

import re
from pathlib import Path


def test_agent_source_wraps_trace_enabled_tools() -> None:
    src = Path("agent.py").read_text(encoding="utf-8")

    # 共享的 trace 包装工具 + stage 映射(agent 与子代理同一份,避免漂移)。
    assert "from data_foundation.agent_trace import TRACE_TOOL_STAGES, with_trace" in src
    assert "assembled_tools = with_trace(" in src


def test_stage_mapping_lives_in_agent_trace() -> None:
    """TRACE_TOOL_STAGES 已收敛到 data_foundation/agent_trace.py 作单一事实源。"""
    src = Path("data_foundation/agent_trace.py").read_text(encoding="utf-8")
    assert "TRACE_TOOL_STAGES" in src
    for name in (
        "semantic_search_resources",
        "sync_copy_to_feishu",
        "adopt_online_notes",
        "search_local_note_cards",
        "get_generated_copy_lifecycle",
        "get_writing_profile",
        "get_session_snapshots",
        "save_writing_teardown",
        "save_session_snapshot",
        "confirm_session_snapshot",
    ):
        assert name in src
    assert "def with_trace(" in src


def test_subagents_wrap_tools_with_trace() -> None:
    """执行型子代理的工具必须过 with_trace —— 否则委派出去的检索/精读不 emit trace,
    工具调用链会缺失子代理这一大段(报告的思考链稀疏根因 B)。"""
    src = Path("subagents_executor.py").read_text(encoding="utf-8")
    assert "from data_foundation.agent_trace import with_trace" in src
    assert 'with_trace(sub["tools"])' in src


def test_main_agent_trace_mapping_matches_assembled_tools_and_frontend_registry() -> None:
    """主 Agent 可调用工具、后端官方 trace 与前端展示必须是同一个集合。

    过去测试只抽查几个字符串，导致工具已注册、前端也有中文名，但后端映射遗漏后
    `with_trace` 静默跳过。这里按 agent.py 的真实组装边界构造集合，新增工具若未同步
    trace 两端会立即失败。
    """

    from data_foundation.agent_trace import TRACE_TOOL_STAGES
    from data_foundation.tools import data_foundation_tools
    from tools.feishu_actions import feishu_action_tools
    from tools.lark_cli import lark_cli
    from tools.online_adopt import adopt_online_notes
    from tools.redfox_search import search_xhs_online

    assembled = {
        tool.name
        for tool in (
            data_foundation_tools
            + feishu_action_tools
            + [search_xhs_online, adopt_online_notes, lark_cli]
        )
    }
    backend = set(TRACE_TOOL_STAGES)

    frontend_src = Path("web/src/lib/agent-trace.ts").read_text(encoding="utf-8")
    registry_start = frontend_src.index("const TOOL_COPY")
    registry_end = frontend_src.index("\n};", registry_start)
    frontend = set(
        re.findall(
            r"^  ([a-z][a-z0-9_]*): \{",
            frontend_src[registry_start:registry_end],
            flags=re.MULTILINE,
        )
    )

    assert backend == assembled
    assert frontend == assembled
