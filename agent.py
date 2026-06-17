"""agent 组装入口。create_deep_agent 装配主智能体 + 飞书工具 + 子智能体 + skill。"""
from deepagents import (
    FilesystemPermission,
    GeneralPurposeSubagentProfile,
    HarnessProfileConfig,
    RubricMiddleware,
    create_deep_agent,
    register_harness_profile,
)
from dotenv import load_dotenv
from langchain.chat_models import init_chat_model

from backends import build_backend
from middlewares import build_retry_middleware
from prompts import MAIN_MODEL, MAIN_SYSTEM_PROMPT
from subagents import ANALYST_MODEL_NAME, baokuan_analyst
from tools.feishu_bitable import read_xhs_data
from tools.lark_cli import lark_cli, auto_update_lark_skills, auto_update_lark_cli

# 启动时自动从官方仓库同步最新的飞书技能（下载失败时自动静默降级，不影响启动）
auto_update_lark_skills()
auto_update_lark_cli()


load_dotenv()

# ── 安全加固:关掉本场景不需要的内置工具和默认子智能体 ──────────────────
# - execute: Shell 命令执行,文案场景不需要,留着是安全隐患
# - write_todos: todo list,两步式工作流(出选题→写文案)不需要
# - general-purpose: 默认通用子智能体,已有 baokuan-analyst,多一个会让模型选错
register_harness_profile("anthropic", HarnessProfileConfig(
    excluded_tools=frozenset({"execute", "write_todos"}),
    general_purpose_subagent=GeneralPurposeSubagentProfile(enabled=False),
))

# 主智能体默认 Claude(中文文案强);如需 GPT 改这里或用环境变量切换。
# timeout/max_retries:中转(43.255.157.166)偶发 502,加单次超时+重试,
# 避免单次调用卡死拖到几分钟才报错(中转通常重试 2-3 次内恢复)。
model = init_chat_model(
    model=MAIN_MODEL,
    temperature=0.7,
    timeout=60,
    max_retries=4,
)

# 三路由 CompositeBackend:/skills/(磁盘共享只读)、/shared/(Store 共享)、
# /drafts/ 及默认(State 随会话隔离)。详见 backends.py。
backend = build_backend()

# ── 文案质量评分中间件 ────────────────────────────────────────────
# 生成文案后自动评估质量,不合格让智能体重写(最多重试 2 轮)。
# 用便宜的 Haiku 做评分模型,控制成本。
# 仅当调用方传入 rubric 时才激活,平时不增加开销。
rubric_middleware = RubricMiddleware(
    model=ANALYST_MODEL_NAME,
    system_prompt="""你是小红书文案质量检查员。评估文案是否满足以下标准:
1. 标题有钩子,不平淡,能引起点击欲望
2. 正文像真人写的小红书笔记,无 AI 腔(不要"首先/其次/总之"、不要"在…领域"等八股)
3. 有 emoji 点缀但不过度
4. 标签 5~10 个且与内容相关
5. 选题和文案有数据依据,不是凭空编的
6. 文案有记忆点,读完能记住一两个关键信息

如果文案不满足以上标准,请给出具体修改建议。""",
    max_iterations=2,
)

agent = create_deep_agent(
    model=model,
    tools=[read_xhs_data, lark_cli],
    system_prompt=MAIN_SYSTEM_PROMPT,
    subagents=[baokuan_analyst],
    skills=["./skills/"],
    backend=backend,
    middleware=[build_retry_middleware(), rubric_middleware],
    # 自学习记忆:团队共享(全员一份方法论)+ 用户私有(按 open_id 隔离)。
    # 团队在前、个人在后 —— sources 按序拼接注入,个人记忆覆盖团队默认。
    # MemoryMiddleware 用 edit_file 写回,文件不存在时首轮跳过、由 agent 创建。
    memory=["/memories/team/AGENTS.md", "/user-memories/AGENTS.md"],
    # ── 文件权限:限制可写路径,防止模型乱写 ─────────────────────────
    # 规则按声明顺序匹配,首条命中即停止。读操作全部放行,写操作只允许白名单路径。
    permissions=[
        FilesystemPermission(operations=["read"], paths=["/**"], mode="allow"),
        FilesystemPermission(operations=["write"], paths=["/drafts/**"], mode="allow"),
        FilesystemPermission(operations=["write"], paths=["/analysis/**"], mode="allow"),
        FilesystemPermission(operations=["write"], paths=["/shared/**"], mode="allow"),
        FilesystemPermission(operations=["write"], paths=["/memories/**"], mode="allow"),
        FilesystemPermission(operations=["write"], paths=["/user-memories/**"], mode="allow"),
        FilesystemPermission(operations=["write"], paths=["/**"], mode="deny"),
    ],
    # LangSmith 追踪时显示的名称,方便在 trace 里快速识别。
    name="xhs-content-agent",
)
