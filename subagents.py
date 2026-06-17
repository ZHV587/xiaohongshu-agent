"""子智能体定义。爆款分析子智能体在独立上下文拆解数据,结论落盘。"""
from dotenv import load_dotenv
from langchain.chat_models import init_chat_model

from tools.feishu_bitable import read_xhs_data

# 本模块在 agent.py 里先于其 load_dotenv() 被 import,而下面 init_chat_model 在
# 模块加载时即构造,需要 ANTHROPIC_BASE_URL/KEY 已在环境里 —— 故这里自行加载 .env,
# 不依赖调用方的导入顺序(否则子智能体可能读不到中转 BASE_URL)。
load_dotenv()

# 子智能体默认用便宜快的模型(设计:子智能体用便宜快模型)。
# 模型名提取为常量,agent.py 的 RubricMiddleware 也用它(避免重复硬编码)。
ANALYST_MODEL_NAME = "anthropic:claude-haiku-4-5-20251001"

# 预初始化为带 timeout/max_retries 的实例(而非裸字符串):中转 43.255.157.166
# 偶发 502,子智能体调模型同样需要重试保护,否则中转一抖子智能体就直接挂
# (实测 502 常发生在 tool_node 里的子智能体执行阶段)。
ANALYST_MODEL = init_chat_model(
    ANALYST_MODEL_NAME,
    timeout=60,
    max_retries=4,
)

ANALYST_SYSTEM_PROMPT = """你是小红书爆款分析助手。你的任务是拆解给定方向的爆款笔记,
提炼可复用的创作规律,并把结论写入指定文件。

## 你的工具
- read_xhs_data():读取飞书表里的爆款数据(列名 + 数据行)
- write_file(file_path, content):保存你的分析结论

## 流程
1. 调 read_xhs_data 获取数据。你需自行判断哪列是标题、正文、互动数据(点赞/收藏)、
   话题标签等——列名可能不规范,按语义理解。
2. 筛选与任务给定方向相关的笔记。
3. 拆解并总结这些维度:
   - 选题角度:这些爆款都从什么角度切入
   - 标题套路:标题的结构、关键词、情绪词、数字/emoji 用法
   - 正文结构:开头怎么钩人、中间怎么展开、结尾怎么收
   - 情绪触发点:激发了读者什么情绪(种草/焦虑/共鸣/好奇)
   - 话题标签习惯:常用哪些标签、几个
4. 用 write_file 把结论写到任务里指定的文件路径(如 /analysis/<方向>.md)。

## 要求
- 结论要具体、可操作,引用数据里的真实例子,不要空泛。
- 如果某方向相关数据很少,如实说明,不要硬编。
- 输出中文。
"""

baokuan_analyst = {
    "name": "baokuan-analyst",
    "description": (
        "拆解飞书数据里某个方向的小红书爆款,提炼选题角度、标题套路、正文结构、"
        "情绪点与标签习惯。委派时请说明:分析哪个方向,以及把结论写到哪个文件路径"
        "(如 '分析露营装备方向,结论写到 /analysis/露营装备.md')。"
    ),
    "system_prompt": ANALYST_SYSTEM_PROMPT,
    "model": ANALYST_MODEL,
    "tools": [read_xhs_data],
}
