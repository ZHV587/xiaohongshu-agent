"""子智能体定义。爆款分析子智能体在独立上下文拆解数据,结论落盘。"""
from dotenv import load_dotenv

from langchain_core.language_models import BaseChatModel

from data_foundation.tools import (
    get_resource,
    graph_expand,
    search_resources,
    semantic_search_resources,
)
from models import ModelPoolProvider, build_router_middleware

# 本模块在 agent.py 里先于其 load_dotenv() 被 import,而下面构造模型在模块加载时
# 即发生,需要 LLM_BASE_URL/KEY 等已在环境里 —— 故这里自行加载 .env,不依赖调用方
# 的导入顺序(否则子智能体可能读不到中转 BASE_URL)。
load_dotenv()

ANALYST_SYSTEM_PROMPT = """你是小红书爆款分析助手。你的任务是拆解给定方向的爆款与对标内容,
提炼可复用的创作规律,并把结论写入指定文件。

## 你的工具
- search_resources(query):优先从 Postgres 统一数据底座检索资源摘要
- semantic_search_resources(query):需要语义召回时补充检索;不可用时回退到关键词结果
- get_resource(resource_id):读取已命中资源的正文、版本、source_updated_at 和 indexed_at
- graph_expand(resource_ids):需要相关案例时做有界关系扩展
- write_file(file_path, content):保存你的分析结论

## 流程
1. 先调用 search_resources 检索任务方向。需要扩大语义召回时再调用 semantic_search_resources;
   如果语义检索不可用,继续使用关键词结果,不要中断任务。
2. 对高相关命中调用 get_resource 读取详情;只有关系上下文确有价值时才调用 graph_expand。
3. 创作分析不得调用 read_xhs_data 或 read_feishu_wiki 作为未沉淀兜底;这些工具不是本子智能体的证据入口。
   统一检索没有可用结果时,明确写“当前数据不足”,建议先调用 sync_feishu_resources 同步飞书资源后再分析。
4. 筛选与任务给定方向相关的笔记或文档。
5. 拆解并总结这些维度:
   - 选题角度:这些爆款都从什么角度切入
   - 标题套路:标题的结构、关键词、情绪词、数字/emoji 用法
   - 正文结构:开头怎么钩人、中间怎么展开、结尾怎么收
   - 情绪触发点:激发了读者什么情绪(种草/焦虑/共鸣/好奇)
   - 话题标签习惯:常用哪些标签、几个
6. 在结论末尾写“关键依据”,逐条记录 resource_id、标题、依据摘要、source_updated_at 和 indexed_at;
   来源没有源端更新时间或索引时间时如实写“未知”,不得猜测或伪造。
7. 用 write_file 把结论写到任务里指定的文件路径(如 /analysis/<方向>.md)。

## 要求
- 结论要具体、可操作,引用数据里的真实例子,不要空泛。
- 如果没有足够的相关来源,明确写“当前数据不足”,建议先同步飞书资源或补充数据,不要硬编。
- 输出中文。
"""

ANALYST_DESCRIPTION = (
    "优先检索统一数据底座并拆解某个方向的小红书爆款,提炼选题角度、标题套路、正文结构, "
    "情绪点与标签习惯。委派时请说明:分析哪个方向,以及把结论写到哪个文件路径"
    "(如 '分析露营装备方向,结论写到 /analysis/露营装备.md')。"
)


def build_baokuan_analyst(
    registry: ModelPoolProvider,
    initial_model: BaseChatModel,
) -> dict:
    return {
        "name": "baokuan-analyst",
        "description": ANALYST_DESCRIPTION,
        "system_prompt": ANALYST_SYSTEM_PROMPT,
        "model": initial_model,
        "tools": [
            search_resources,
            semantic_search_resources,
            graph_expand,
            get_resource,
        ],
        "middleware": [build_router_middleware(registry)],
    }
