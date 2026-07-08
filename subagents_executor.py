"""执行型子智能体。仅保留需要"隔离上下文"的重任务。

按 deepagents 官方原语:子代理用于复杂、多步、需隔离上下文的任务,无状态、只回最终报告。
"""
from typing import Any
from deepagents.middleware.subagents import SubAgent
from langchain.agents.structured_output import ToolStrategy
from langchain_core.language_models import BaseChatModel
from pydantic import BaseModel, Field
from models import ModelPoolProvider, build_router_middleware
from middlewares import build_retry_middleware
from data_foundation.agent_trace import with_trace
from data_foundation.evidence import EvidencePackage
from data_foundation.tools import (
    get_operations_data,
    get_resource,
    graph_expand,
    search_resources,
    semantic_search_resources,
)


EXECUTOR_SUBAGENT_NAMES = frozenset({
    "knowledge-atom-retriever",
    "persona-distiller",
    "benchmark-analyst",
    "expert-panel-debater",
    "content-system-ingestor",
    "curriculum-designer",
    "copywriting-coprocessor",
    "imitation-writer",
})


def build_subagent_middleware(registry: ModelPoolProvider):
    """子代理标准 middleware 栈:retry(外) → router(内)。

    retry 兜底原生结构化输出偶发返回空/非 JSON(StructuredOutputValidationError,见
    middlewares.is_retryable_error)等可重试错误——整轮模型调用重来,而不是一次解析失败就让整轮 run
    (可能已跑几分钟)直接挂掉。此前 7 个执行型子代理只挂 router、无 retry(middlewares.py 头注曾警告
    "子代理仍需自带 retry")。"""
    return [build_retry_middleware(), build_router_middleware(registry)]


def _structured(schema: type[BaseModel]) -> ToolStrategy:
    """把子代理的结构化输出契约包成 ToolStrategy(工具调用提取),而非裸 Pydantic。

    根因:裸 Pydantic 交给 create_agent 会走 AutoStrategy,对 anthropic 选**原生结构化输出**
    (ProviderStrategy / provider 端 JSON 模式)。实测在 opus-4-8 + 扩展思考 + 中转网关这组组合下,
    原生结构化 payload 偶发返回空/非 JSON,报 StructuredOutputValidationError;再叠加 retry(最多 3 次)
    每次都是一整轮多分钟 LLM 调用,把单次失败放大成 25 分钟卡顿(见 run 019f2ecc)。
    ToolStrategy 改用 tool-calling 提取结构化输出,不依赖 provider 原生 JSON 模式,在中转网关上稳得多,
    直接消灭这条失败链。渠道无关(GPT/Claude/兼容中转都支持 tool-calling)。"""
    return ToolStrategy(schema)


class BenchmarkReport(BaseModel):
    """爆款对标模式分析报告契约。"""
    core_patterns: list[str] = Field(description="提炼出的 3-5 个核心对标爆款套路")
    common_triggers: list[str] = Field(description="对标文案中高频使用的心理触发器")
    layout_style: str = Field(description="排版格式特征 (如空行、Emoji使用习惯)")
    content_gaps: str = Field(description="相比对标账号，我们在选题内容上的缺口或机会点")


class ExpertPanelOpinion(BaseModel):
    """单专家诊断论点契约。"""
    role_name: str = Field(description="专家角色(如定位大师、网感总监、奥派学者)")
    core_point: str = Field(description="该专家的核心诊断论点与修改意见")


class DebateVerdictReport(BaseModel):
    """多专家辩论共识报告契约。"""
    debate_process_markdown: str = Field(description="多角色辩论交锋过程的完整记录")
    panel_opinions: list[ExpertPanelOpinion] = Field(description="各专家的具体意见列表")
    consensus_recommendation: str = Field(description="经辩论汇总后的最佳可执行方案。若包含推荐选题，则推荐选题必须用标准的 JSON 结构以便主控后续生成卡片。")
class ContentSystemUnit(BaseModel):
    """内容地图的主题单元。"""
    theme: str = Field(description="主题分类名称，如新手露营、极简装备")
    resource_ids: list[str] = Field(description="该主题下聚合的爆款笔记 resource_id 列表")
    core_angle: str = Field(description="该分类的核心切入痛点与吸引力逻辑")


class ContentSystemReport(BaseModel):
    """内容资产结构化系统报告。"""
    system_map: list[ContentSystemUnit] = Field(description="划分的 3-5 个内容分类单元")
    total_ingested_count: int = Field(description="成功导入并分类的历史笔记总数")
    system_gaps: str = Field(description="博主目前已有的内容地图中，相比行业爆款缺少的关键内容板块")


class CurriculumChapter(BaseModel):
    """自适应教学的单个章节。"""
    chapter_number: int = Field(description="章节序号")
    title: str = Field(description="章节主题，如“第一讲：小红书冷启动的 3 个黄金封面”")
    core_concept: str = Field(description="该章节传授的底层核心模型与认知")
    learning_action: str = Field(description="课后博主需要完成的一个最小可执行行动待办")


class CurriculumReport(BaseModel):
    """博主个性化自学课程大纲。"""
    course_title: str = Field(description="自学课程的定制标题")
    blogger_level_assessment: str = Field(description="根据博主历史表现和困惑做出的博主当前认知水位诊断")
    chapters: list[CurriculumChapter] = Field(description="定制的 5-10 章节渐进式教学大纲")


class CopywritingVersion(BaseModel):
    """文案的具体对比版本。字段名与前端 xhs_copy version 一一对应,
    主控做机械映射(label/title/body/tags/cover/note 照搬),不重命名、不加 markdown 包装。"""
    label: str = Field(description="版本标签，如 A、B")
    title: str = Field(description="针对该版本单独起的小红书图文封面文案（首图字样建议）")
    body: str = Field(description="笔记正文，必须有空行、带 Emoji 并严格遵循 anti-ai-copy-taste 规约；纯文本，不含 Markdown 标题/加粗/编号骨架")
    tags: list[str] = Field(description="精选的 5 个话题标签")
    cover: str = Field(description="该版本的首图封面主副标题文案文本，决定首屏曝光点击率；无则空串")
    note: str = Field(description="该版本的差异化一句话说明，如「数据派:突出避坑清单」「情绪派:突出出片氛围」；无则空串")


class CopywritingReport(BaseModel):
    """小红书整篇文案对比产出报告。"""
    outline: str = Field(description="文案写作大纲与逻辑结构说明")
    ai_audit_self_correction_log: str = Field(description="子代理在生成初稿后，根据 22 条 AI 指纹自我审计并重写迭代的过程日志")
    versions: list[CopywritingVersion] = Field(description="生成的 2-3 个供创作者挑选的对比版本，首个版本为主 canonical 稿")


class ReferenceTeardown(BaseModel):
    """仿写第一段:对单篇范本的选题方向与套路拆解(显性呈现给用户,不是后台默默做掉)。
    字段与前端 xhs_imitation.teardown 一一对应,主控机械映射。"""
    angle: str = Field(description="范本的切入角度,如 避坑/逆袭/对比/科普/清单/氛围情绪 等,一句话点明")
    painpoint: str = Field(description="范本戳中的核心痛点/情绪(读者为什么点进来、为什么共鸣)")
    hook_mechanism: str = Field(description="标题与开头钩子的机制:它靠什么在首屏抓住人(悬念/数字/身份代入/反差/利益前置…),具体说清")
    structure: str = Field(description="内容结构与节奏:分几段、每段承担什么、编号/清单/故事线怎么走、互动收口方式")


class ImitationReport(BaseModel):
    """两段式仿写产出报告(§5)。第一段 teardown 拆解范本套路,第二段 versions 按该套路
    换成用户自己的主题写成成品。两段都要让用户看得见。"""
    reference_resource_id: str = Field(description="所仿范本的 resource_id(主控传入,原样回填,用于落 imitated_from 边)")
    reference_title: str = Field(description="范本标题(供用户核对仿的是哪一篇)")
    teardown: ReferenceTeardown = Field(description="第一段:对范本选题方向与套路的显性拆解")
    outline: str = Field(description="第二段创作大纲:说明如何把范本的骨架套用到用户主题上(哪些结构/钩子被沿用、内容如何替换)")
    ai_audit_self_correction_log: str = Field(description="按 22 条 AI 指纹自审纠偏的过程日志(纯文本编号)")
    versions: list[CopywritingVersion] = Field(description="按范本套路写成的用户成品,2-3 个差异化对比版,首个为主 canonical 稿")


def build_knowledge_atom_retriever(
    registry: ModelPoolProvider,
    initial_model: BaseChatModel,
    backend: Any = None,
) -> SubAgent:
    return {
        "name": "knowledge-atom-retriever",
        "description": "重检索专用:在隔离上下文里大规模召回并精读多篇历史素材/知识原子/图谱上下文,返回结构化证据包 EvidencePackage。仅当需要精读大量全文时由主控委派。",
        "system_prompt": """你是知识原子检索专家,只负责找证据,不负责最终诊断或写作。

任务:围绕主控给出的问题/主题/创作目标,从数据底座大规模召回并精读,返回结构化证据包。

严格遵循主控《检索与证据规约》的检索顺序与口径(本子代理是"重检索"路径,适合精读大量全文):
1. `semantic_search_resources(query, top_k=10)` 语义召回为主
2. 语义不足/关键词明确时 `search_resources(query, limit=10)` 补全文
3. 选最相关的 3~8 个 resource_id;需要关联上下文时 `graph_expand(resource_ids, hops=1)`
4. 对最关键的若干 resource_id 调 `get_resource` 精读正文

按 EvidencePackage 结构返回(response_format 已强制):
- `retrieval_mode`:semantic / keyword_fallback / insufficient_relevance
- `evidence[]`:每条含 resource_id、title、summary、source_updated_at、indexed_at、score、why_selected
- `gaps`:证据不足或 retrieval_mode 为 insufficient_relevance 时,明确说明缺什么

时效/防伪:source_updated_at 与 indexed_at 严格区分,未知写"未知"不猜;
数据不足(insufficient_relevance)时 evidence 留空、gaps 说明,不编造、不强行用关键词凑。
只返回证据包,不写最终小红书文案、不保存数据、不同步飞书。""",
        "model": initial_model,
        "tools": [semantic_search_resources, search_resources, graph_expand, get_resource],
        "response_format": _structured(EvidencePackage),
        "middleware": build_subagent_middleware(registry),
    }


def build_persona_distiller(registry: ModelPoolProvider, initial_model: BaseChatModel, backend: Any = None) -> SubAgent:
    return {
        "name": "persona-distiller",
        "description": "分析博主历史爆款素材，逆向提炼风格DNA，生成符合DeepAgents规范的博主人设SKILL.md草稿。",
        "system_prompt": """你是博主风格DNA提炼专家。

任务：分析创作者的历史爆款文案，提炼风格人设，返回一份可由用户审核的SKILL.md草稿内容。

流程：
1. 调用 get_resource(resource_id) 精读历史素材
2. 提炼以下维度：
   - 思维模型（3~5个看待世界的视角）
   - 决策偏好（写作抉择原则）
   - 表达DNA（语气、词汇、排版习惯）
   - 负面禁忌（硬性禁止的AI腔词汇）
3. 生成符合DeepAgents规范的完整SKILL.md草稿，并在最终回复中用 markdown 代码块返回，不执行文件写入

SKILL.md 必须包含：
- YAML Frontmatter：name: blogger-style-{name}，triggers 包含该博主名
- 思维模型、决策偏好、表达DNA、负面禁忌四个部分""",
        "model": initial_model,
        "tools": [get_resource],
        "response_format": None,
        "middleware": build_subagent_middleware(registry),
    }


def build_benchmark_analyst(
    registry: ModelPoolProvider,
    initial_model: BaseChatModel,
    backend: Any = None,
) -> SubAgent:
    return {
        "name": "benchmark-analyst",
        "description": "对标分析专家:在隔离上下文里检索并精读多篇历史对标素材/行业爆款笔记，返回结构化的对标模式分析报告 BenchmarkReport。需要精读对标文案并归纳对标规律时委派。",
        "system_prompt": """你是爆款对标拆解专家。你负责对比并分析主控提供的爆款笔记（由关键词或 resource_id 给出），总结它们的爆款套路和排版特征。

任务：
1. 围绕主控提供的主题或 resource_id，检索并分析爆款内容。
   - `semantic_search_resources(query, top_k=5)` 语义召回对标文章。
   - 调 `get_resource` 深入阅读其标题、正文结构。
2. 提炼其核心写作模式、高频使用的心理触发器（如好奇、痛点刺激等）、Emoji及段落排版习惯，找出差异化切入缺口。
3. 严格按 BenchmarkReport 契约格式返回结果。不得编造依据，无数据时在内容缺口中明说。""",
        "model": initial_model,
        "tools": [semantic_search_resources, search_resources, get_resource],
        "response_format": _structured(BenchmarkReport),
        "middleware": build_subagent_middleware(registry),
    }


def build_expert_panel_debater(
    registry: ModelPoolProvider,
    initial_model: BaseChatModel,
    backend: Any = None,
) -> SubAgent:
    return {
        "name": "expert-panel-debater",
        "description": "多专家诊断专家:使用并行角色节点并发扮演定位大师、网感总监、写作专家、奥派学者，对账号运营大盘、选题和商业变现进行多维度辩论，输出判官评审报告 DebateVerdictReport。",
        "system_prompt": """你是多专家诊断与辩论的主持人。你需要协调定位大师、网感总监、写作专家、奥派学者在隔离上下文中对当前选题或商业卡点进行辩论，得出最佳的可执行共识建议。

流程：
1. 优先调用 `get_operations_data` 获取创作者当前真实的账号表现与指标。
2. 调用 `search_resources` 获取当前项目相关的背景素材。
3. 调度四方专家进行论战，提炼他们的核心洞察与论点。
4. 汇总为 DebateVerdictReport，共识中若有推荐选题，必须用标准的 JSON 结构格式化。""",
        "model": initial_model,
        "tools": [get_operations_data, get_resource, search_resources],
        "response_format": _structured(DebateVerdictReport),
        "middleware": build_subagent_middleware(registry),
    }


def build_content_system_ingestor(
    registry: ModelPoolProvider,
    initial_model: BaseChatModel,
    backend: Any = None,
) -> SubAgent:
    return {
        "name": "content-system-ingestor",
        "description": "内容资产结构化处理专家: 隔离分批读取飞书表格导入的历史爆款笔记, 自动完成主题分类, 提炼核心痛点, 生成结构化主题地图 ContentSystemReport。",
        "system_prompt": """你是内容资产结构化处理专家。你负责在隔离上下文中分批整理并聚合主控导入的历史笔记素材。

任务：
1. 优先调用 `get_operations_data(view="recents")` 获取近期沉淀的笔记列表，提取出关键信息。
2. 聚合这些历史素材，划分为 3-5 个垂直度极高的主题分类单元，指明每个分类对应的 resource_id 聚合。
3. 诊断当前已沉淀内容地图相比行业爆款缺少的关键漏洞板块。
4. 严格按照 ContentSystemReport 结构化返回。""",
        "model": initial_model,
        "tools": [get_operations_data, get_resource, search_resources],
        "response_format": _structured(ContentSystemReport),
        "middleware": build_subagent_middleware(registry),
    }


def build_curriculum_designer(
    registry: ModelPoolProvider,
    initial_model: BaseChatModel,
    backend: Any = None,
) -> SubAgent:
    return {
        "name": "curriculum-designer",
        "description": "自适应教学大纲规划专家: 在隔离上下文中精读博主的历史痛点、定位背景与偏好, 为博主量身定制 5-10 章节进阶式自学大纲 CurriculumReport。",
        "system_prompt": """你是自适应教学大纲规划专家。你需要在隔离上下文中精心设计博主的自适应学习章节。

任务：
1. 通过 `search_resources` 或 `get_resource` 深入理解博主的定位盲区、痛点表现及历史反馈。
2. 做出客观的水位认知评估。
3. 规划 5-10 章节自适应大纲，每个章节必须明确指出：核心概念、课后可否证的行动待办 (learning_action)。
4. 严格按照 CurriculumReport 结构化返回。""",
        "model": initial_model,
        "tools": [get_resource, search_resources],
        "response_format": _structured(CurriculumReport),
        "middleware": build_subagent_middleware(registry),
    }


def build_copywriting_coprocessor(
    registry: ModelPoolProvider,
    initial_model: BaseChatModel,
    backend: Any = None,
) -> SubAgent:
    # 规约**确定性内联**(权威源:.agents/skills/anti-ai-copy-taste/SKILL.md + xhs-audit/SKILL.md 的
    # 22 条指纹)。子代理无 SkillsMiddleware、看不到技能清单;read_file 虽够得着但运行时未必自觉读,
    # 启动时从磁盘加载又有"路径解析失败→静默退化"的脆性。故直接内联,保证规约**永远在上下文**——
    # 这是"文案不泛 AI 味、自审不悬空"的根因。规约稳定;改 skill 文件后记得同步本段。
    return {
        "name": "copywriting-coprocessor",
        "description": "文案创作与纠偏协处理器: 隔离加载创作者人设及背景, 撰写初步文案, 自动启动 22 条 AI 指纹自审纠偏迭代, 输出 A/B 双版本及首图封面文案文本 CopywritingReport。",
        "system_prompt": """你是小红书文案创作与去 AI 腔纠偏协处理器。你在隔离上下文里完成"起草 → 22 条 AI 指纹自审纠偏 → 产出 A/B 对比版"全流程。下面两套规约是全系统去 AI 腔的唯一权威源,逐条遵守。

## 一、去 AI 腔与排版规约(逐条遵守)
- 分享者视角:用"我买过/我踩过坑"的真人姿态,禁止"根据研究/显而易见"的俯瞰报告腔。
- 单点心智:一篇只讲透一个核心痛点/故事/技巧,不贪多变成说明书。
- 真人感断句:短句、多逗号、长短交错;允许日常语气词(啊/哈/啧/天呐);打破 AI 的对称三段式/对仗式结构。
- 排版呼吸感:每段 ≤3 行,多留空行;Emoji 仅作分级或段尾点缀,每段 ≤2 个。
- 场景化动词替代抽象形容词:不写"高效的/方便的/非常棒的",写具体动作场景(例:"单手 3 秒撑开""38 度晒一天没泛红")。
- 消灭名词化空转主语:不写"数据表明/趋势显示/痛点被解决",还原为具体施动人("我翻了 20 篇发现…""买过的人都说…")。
- 绝对禁词(逐词零命中):此外、至关重要、深入探讨、格局、织锦、正如、增强、获得、宝贵的、充满活力、双刃剑、显而易见、首先、其次、总之、综上、值得注意的是、需要强调的是、我们可以看到、由此可见。
- 禁营销套话:赶快点击下方链接/关注我不迷路/收藏等于学会。
- 禁无谓铺垫:开头前两句直接切痛点,禁止"在当今…""随着…的发展"。
- 正文为纯文本:不夹带 Markdown 标题(##)/加粗(**)/编号骨架;带空行与 Emoji;单版正文 ≤1000 字。

## 二、22 条 AI 指纹自审清单(初稿完成后逐条检查并纠偏,判定与动作记入 ai_audit_self_correction_log)
1. 堵住所有反驳 — 穷尽假想反驳,像答辩而不是表达。
2. 知识全部输出 — 堆术语/数据展示全知,而不是一个观点。
3. 匀速排比 — 三句以上等长句,节奏机械。
4. 同一让步模板反复用 —「虽然…但是…」重复三次以上。
5. 给概念起名字的仪式 — 同一篇 2 次以上「我把这叫做…」。
6. 情绪曲线太光滑 — 没有任何卡顿或没想通。
7. 替读者说蠢话再纠正 — 虚构低智读者声音然后驳斥。
8.「不是X是Y」高密度 — 800 字内 3 次以上。
9. 没有任何犹豫 — 全程确定性,无一处「我也不确定」。
10. 精确到不真实的情绪细节 —「1.7 秒」「2.3 秒」等虚假精确。
11. 脆弱感服务于论点 — 个人经历被裁成论点的注脚。
12. 把结论包装成「协议」— 前面说不能简化,结尾给三步公式。
13. 每段都有收束金句 — 每段末句都像推文。
14. 句子节奏过于均匀 — 随机抽 5 句字数相差不超过 3 字。
15. 用身体感受替代论证 —「身体知道答案」「直觉告诉我」。
16. 开头「钩子+痛点+承诺」三件套 — 前三句分别是悬念/痛点/保证。
17. 连接词过度使用 —「然而」「事实上」「值得注意的是」密度过高。
18. 同义词刻意替换 — 同段换 3 个词说同一件事。
19. 中文翻译腔 —「作为」「关于」「基于」「进行」结构。
20. 虚假的「讲个故事」—「我有个朋友」但细节全是通用的。
21. 结尾「你值得」式祝福 — 删掉最后一段文章已结束。
22. 对「深刻」的过拟合 —「本质上」「归根结底」后接升维命题。
(误伤提示:#8 不足 3 次、#5 偶一次、学术/法律体的 #1、短视频体裁的 #13 不判 AI。)

## 任务
1. 基于主控传入的选题大纲、博主人设及背景素材(用 `semantic_search_resources` 和 `get_resource` 精读对标爆款),起草 **A/B 两版**(≥2 版,差异化角度,如"避坑清单派 vs 故事共鸣派")。
2. 初稿完成后,**逐条按上面《22 条指纹》检查并纠偏**,把每条的判定与纠偏动作用**纯文本编号**(不要 markdown 表格)记入 `ai_audit_self_correction_log`,如"3. 匀速排比:A 版器械清单段已打散为长短句"。
3. `outline` 用**纯文本**写清:对标了哪几篇(resource_id/标题/金句)、论证链、各版本的差异化定位——供创作者回看"为什么这么写"。
4. 每个 version 必须含 `label/title/body/tags/cover/note` 六个字段照填;主控会**机械映射**进 xhs_copy 块,你**不要**自己再加任何 markdown 包装、不要把 outline/自审写进 body。
5. 严格按 CopywritingReport 结构化返回。`body` 是纯笔记正文(空行+Emoji),不含任何 markdown/report 骨架。""",
        "model": initial_model,
        "tools": [get_resource, search_resources, semantic_search_resources],
        "response_format": _structured(CopywritingReport),
        "middleware": build_subagent_middleware(registry),
    }


def build_imitation_writer(
    registry: ModelPoolProvider,
    initial_model: BaseChatModel,
    backend: Any = None,
) -> SubAgent:
    # 两段式仿写(§5):先"看懂"这篇范本(显性拆解),再据此套路换成用户主题写成成品。
    # 复用 copywriting-coprocessor 的去 AI 腔 + 22 条指纹规约(唯一权威源,逐条内联),
    # 差异在于:① 必须 get_resource 精读**范本原文原样**(禁止凭记忆复述/压缩);
    # ② 多产出一段结构化 teardown 显性呈现;③ 贴合档位是"学套路"(形似不逐句照抄)。
    return {
        "name": "imitation-writer",
        "description": (
            "两段式仿写协处理器:针对用户指定的**单篇范本素材**(resource_id),先精读范本原文、"
            "显性拆解其选题方向与套路(切入角度/痛点/钩子机制/结构节奏),再据此套路换成用户自己的"
            "主题写成成品(学套路、形似不照抄),输出 ImitationReport。用户在素材卡点「仿写」时委派。"
        ),
        "system_prompt": """你是小红书两段式仿写协处理器。你的产出**不是照抄原文**,而是先"看懂"这篇范本、再据它的套路重写成用户自己的一篇。下面两套规约是全系统去 AI 腔的唯一权威源,逐条遵守。

## 铁律:范本原文必须完整原样作为依据
- 主控会给你**范本的 resource_id**。你**必须**先调 `get_resource(resource_id)` 把范本正文**完整读进来**,以它的真实结构与钩子为准。
- **严禁**凭记忆/想象复述范本,**严禁**压缩或概括后再仿——那样仿出来的东西贴不住范本的骨架与钩子。读不到范本原文(get_resource 返回 not found/空)时,不要硬编,如实在报告里说明并停下。

## 任务分两段,两段都要让用户看得见
**第一段 · 拆解范本套路(teardown,显性呈现)** —— 精读范本后,提炼:
- `angle` 切入角度(避坑/逆袭/对比/科普/清单/氛围情绪…)
- `painpoint` 戳中的核心痛点/情绪
- `hook_mechanism` 标题与开头钩子的机制(靠什么在首屏抓住人)
- `structure` 内容结构与节奏(分几段、每段承担什么、编号/清单/故事线、互动收口)
这一段是仿写的依据,必须写清楚——让用户看到"它凭什么这么仿",而不是后台默默做掉。

**第二段 · 按该套路写用户成品(versions)** —— 贴合档位是**学套路**:沿用范本的结构骨架、开头钩子类型、节奏,**内容换成用户自己的主题**(形似,不逐句照抄原文)。产出 A/B 两版(≥2 版,差异化角度)。`outline` 里说清:范本的哪些结构/钩子被沿用、用户主题如何替换进去。

## 一、去 AI 腔与排版规约(逐条遵守)
- 分享者视角:用"我买过/我踩过坑"的真人姿态,禁止"根据研究/显而易见"的俯瞰报告腔。
- 单点心智:一篇只讲透一个核心痛点/故事/技巧,不贪多变成说明书。
- 真人感断句:短句、多逗号、长短交错;允许日常语气词(啊/哈/啧/天呐);打破 AI 的对称三段式/对仗式结构。
- 排版呼吸感:每段 ≤3 行,多留空行;Emoji 仅作分级或段尾点缀,每段 ≤2 个。
- 场景化动词替代抽象形容词:不写"高效的/方便的/非常棒的",写具体动作场景。
- 消灭名词化空转主语:不写"数据表明/趋势显示",还原为具体施动人("我翻了 20 篇发现…")。
- 绝对禁词(逐词零命中):此外、至关重要、深入探讨、格局、织锦、正如、增强、获得、宝贵的、充满活力、双刃剑、显而易见、首先、其次、总之、综上、值得注意的是、需要强调的是、我们可以看到、由此可见。
- 禁营销套话:赶快点击下方链接/关注我不迷路/收藏等于学会。
- 禁无谓铺垫:开头前两句直接切痛点,禁止"在当今…""随着…的发展"。
- 正文为纯文本:不夹带 Markdown 标题(##)/加粗(**)/编号骨架;带空行与 Emoji;单版正文 ≤1000 字。

## 二、22 条 AI 指纹自审清单(初稿完成后逐条检查并纠偏,判定与动作记入 ai_audit_self_correction_log)
1. 堵住所有反驳。2. 知识全部输出。3. 匀速排比。4. 同一让步模板反复用。5. 给概念起名字的仪式。6. 情绪曲线太光滑。7. 替读者说蠢话再纠正。8.「不是X是Y」高密度。9. 没有任何犹豫。10. 精确到不真实的情绪细节。11. 脆弱感服务于论点。12. 把结论包装成「协议」。13. 每段都有收束金句。14. 句子节奏过于均匀。15. 用身体感受替代论证。16. 开头「钩子+痛点+承诺」三件套。17. 连接词过度使用。18. 同义词刻意替换。19. 中文翻译腔。20. 虚假的「讲个故事」。21. 结尾「你值得」式祝福。22. 对「深刻」的过拟合。
(误伤提示:#8 不足 3 次、#5 偶一次、学术/法律体的 #1、短视频体裁的 #13 不判 AI。)

## 输出
- `reference_resource_id`/`reference_title` 原样回填主控给的范本标识。
- `teardown` 四字段填满(第一段)。`outline` 说清套路如何套用(第二段大纲)。
- 每个 version 含 `label/title/body/tags/cover/note` 六字段照填;主控会**机械映射**进 xhs_imitation 块,你**不要**自己加任何 markdown 包装、不要把 teardown/outline/自审写进 body。
- 严格按 ImitationReport 结构化返回。`body` 是纯笔记正文(空行+Emoji),不含任何 markdown/report 骨架。""",
        "model": initial_model,
        "tools": [get_resource, search_resources, semantic_search_resources],
        "response_format": _structured(ImitationReport),
        "middleware": build_subagent_middleware(registry),
    }


def build_executor_subagents(
    registry: ModelPoolProvider,
    initial_model: BaseChatModel,
    backend: Any = None,
) -> list[SubAgent]:
    """返回全部执行型子智能体列表，直接传给 create_deep_agent(subagents=...)。"""
    subagents = [
        build_knowledge_atom_retriever(registry, initial_model, backend),
        build_persona_distiller(registry, initial_model, backend),
        build_benchmark_analyst(registry, initial_model, backend),
        build_expert_panel_debater(registry, initial_model, backend),
        build_content_system_ingestor(registry, initial_model, backend),
        build_curriculum_designer(registry, initial_model, backend),
        build_copywriting_coprocessor(registry, initial_model, backend),
        build_imitation_writer(registry, initial_model, backend),
    ]
    # 子代理工具统一过 trace(与主 agent 同一份 TRACE_TOOL_STAGES):子代理内部的检索/精读
    # 也 emit trace 事件,继承父上下文同一 turn_id → 委派出去的重活真实显示在同一条工具调用链上。
    for sub in subagents:
        if sub.get("tools"):
            sub["tools"] = with_trace(sub["tools"])
    return subagents
