# 创作流程梳理 · 检索层职责规约(设计草案)

> 状态:草案 / 讨论中。本文是"创作流程优化"的地基,先把**工具/技能/子 agent 的职责边界**和**检索层契约**钉死,后续逐步梳理"出选题→选定→写文案→落库同步→效果复盘"各步时都照此规约执行。
> 依据:对照 deepagents 0.6.10 官方源码(`middleware/skills.py`、`middleware/subagents.py`、`graph.py`)与本项目现状。

## 1. 背景与动机

实际使用主场景:**用户对话 → "帮我出某方向的几个选题"**。梳理发现职责边界存在歧义:

- 同一件"检索 / 落库 / 同步选题",既可由主控技能用工具直做,又存在委派子 agent(`topic-generator`/`knowledge-atom-retriever`)的并行路径,**判据不清**。
- 检索顺序/证据规约在 `topic-content`、`xhs-benchmark`、`xhs-planning`、`xhs-content-system` 四个技能里**各抄一遍**,易漂移。
- 担心:**数据持续增长**后检索/上下文是否失控。

本规约给出确定性判据,消除上述歧义。

## 2. 三层原语职责(官方依据)

| 原语 | 本质 | 能否执行动作 | 能否保证返回格式 | 能否中途与用户交互 | 上下文 |
|---|---|---|---|---|---|
| **工具 Tool** | 一次确定性 I/O 动作 | ✅ | ✅(返回值即固定结构) | —(主控在调用间隙仍可交互) | 共享主控上下文 |
| **技能 Skill** | 注入主控的工作流/领域知识(`SKILL.md`,渐进式披露) | ❌(只是 prompt 文本) | ❌(只能"请求"格式,无强制力) | ✅(主控自己在对话里走) | 共享主控上下文 |
| **子 agent(`task`)** | 临时、**无状态**、**隔离上下文**的独立 agent,只回最终报告 | ✅ | ✅(`response_format` 框架强制) | ❌(跑完才回,中途不可交互) | 隔离 |

官方原文要点:
- 子 agent = "处理**复杂、多步、独立**任务,拥有**隔离上下文窗口**";"**无状态**,只通过最终报告沟通";"擅长**隔离上下文和 token 用量**"。
- 技能 = "渐进式披露";"匹配用户请求领域 / 需要**结构化工作流**时使用"。
- `SubAgent` 支持 `response_format`(Pydantic schema),框架**强制**结构化输出。

## 3. 核心判据(选哪一个)

```
要执行检索/落库/同步等动作          → 工具(技能执行不了)
需要保证返回固定格式               → 工具的返回结构 或 子 agent 的 response_format(技能保证不了)
要和用户来回、要保持对话上下文、活轻 → 主控技能 + 工具直调
要"灌进上下文的量很大"(精读多篇全文综合)、可隔离、只取结论 → 子 agent + response_format
```

**关键澄清:决定用工具还是子 agent 的,是"需要拉进 LLM 上下文的量",不是语料库大小,也不是任务类型标签。**

## 4. 检索层设计

### 4.1 检索动作 = 工具(不立检索技能)

理由:
1. 检索是**动作**,技能(纯文本)执行不了 SQL/HTTP。
2. 检索不是**用户意图**(没人对智能体说"执行检索"),无法语义触发,做成可触发技能不成立。
3. 需要**固定返回格式**,而技能恰恰是三者里唯一保证不了格式的。

现有检索工具保留:`search_resources`(Meili 全文)、`semantic_search_resources`(pgvector 语义)、`get_resource`(精读全文)、`graph_expand`(图扩展)、`sync_feishu_resources`(数据不足时同步上游)。

### 4.2 飞书是上游补给,不是并列检索源

创作流程**只检索 Postgres 数据底座**;飞书由 source processor / `sync_feishu_resources` **预先同步进库**后才进入证据链。**创作时不直接读飞书**(部署规则禁止)。

标准第一步:
> 检索 Postgres(`search_resources` → 需要时 `semantic_search_resources` → 选中 `get_resource`/可选 `graph_expand`);**仅当数据不足**才 `sync_feishu_resources` 同步后重检索;同步后仍无 → 明确"当前数据不足",不编造。

### 4.3 轻 vs 重:工具 vs 子 agent

| 场景 | 走法 |
|---|---|
| **轻**:只需 top-N 摘要 + 少量全文(典型:出选题) | **工具**,主控直调。结果留主控上下文,便于交互/迭代/换角度;格式由工具返回结构保证 |
| **重**:需精读**大量全文**跨多源综合 | **`knowledge-atom-retriever` 子 agent + `response_format=EvidencePackage`**,在隔离上下文里召回+精读+蒸馏,只回小证据包 |

切换信号是**单次查询要深读的全文篇数**(per-query 属性),不是库规模。

### 4.3b 统一标准检索流程(单一数据源)

把"查找"收敛为**一条标准流程**,作为单一事实源,各创作技能(topic-content/benchmark/planning/content-system)**引用而非重写**,消除四处漂移。

```
query
  │
① 语义优先  semantic_search_resources(query, top_k)
  │    ├ mode=semantic              → 拿到 top-N 相关摘要,进 ②/③
  │    ├ mode=insufficient_relevance → top 余弦 < 0.5,判"当前数据不足":
  │    │                              明说 + 建议 sync_feishu_resources,不降级、不编造
  │    └ mode=keyword_fallback      → 语义引擎不可用,已自动退 Meili 全文
  │
② 关键词补充  search_resources(query, limit)
  │    仅当:语义结果偏少、或用户关键词非常明确时补召;不是默认必走
  │
③ 精读  get_resource(resource_id) × top-N
  │    只深读最相关的前几篇(N 小);N 很大时整段交 knowledge-atom-retriever 子 agent 隔离精读
  │
④ 图增强(条件触发,非默认)  graph_expand(resource_ids, hops=1, edge_types)
  │    触发条件:需要候选的**衍生/效果邻域**时——例如要解释"为什么推荐这个方向"、
  │    要看某来源衍生过的文案及其历史表现。沿 derived_from / measured_by / feedback_on 边拉邻域,
  │    可结合 get_resource_performance 取效果分。无此需求则跳过。
  │
⑤ 产出 EvidencePackage(见 §5);全程时效/防伪规约统一
```

**顺序定稿:语义优先,全文补充。** 理由:语义召回是主路径(经中文查询前缀 + 绝对相关度闸门),全文是补充/降级;不再保留"先关键词打底"的并行写法。

**图扩展定位:保留为"条件触发的证据增强",不是可删功能、也不是默认每次都走。** 它把"命中来源 → 衍生内容 → 效果指标"的链路接起来,是"带历史效果的推荐依据"的关键来源。给它明确触发条件(上面 ④),解决"有能力但没用起来"。

### 4.3c 单一数据源的落地机制(在哪一份文件)

"统一标准检索流程 + 证据规约"必须有**唯一物理落点**,否则又退回四处重抄。落点选择受**运行时约束**限定:

> 部署的 deepagents 运行时上下文里**只有** `prompts.py`(主控系统提示)+ 各 `SKILL.md`(渐进式披露)+ subagents 提示。`.kiro/steering` 是 Kiro IDE 机制,**不进入线上运行时**,不能作为规约载体。

定稿:
- **唯一事实源 = `prompts.py` 主控系统提示**,新增/收敛一节"检索与证据规约"(统一检索顺序、insufficient_relevance 处理、EvidencePackage 字段、时效/防伪)。prompts.py 每轮必在上下文,是天然单一源。
- **各创作技能(topic-content/benchmark/planning/content-system)删除各自重抄的检索步骤**,改为一句"按主控《检索与证据规约》执行检索与证据收集",只保留各自**独有**的后续逻辑(出选题卡 / 五重漏斗 / 主题地图等)。
- `knowledge-atom-retriever` 子代理提示同样引用同一规约,并以 `response_format=EvidencePackage` 强制输出。

这样规约改一处(prompts.py)全链路生效;SKILL.md 只保留差异化工作流,消除漂移。

### 4.4 数据增长的应对(语料只会越来越多)

### 4.4 数据增长的应对(语料只会越来越多)

**架构性质:LLM 上下文与语料规模解耦。**

```
全部语料(增长)
   │  增长由引擎吸收(HNSW 近似最近邻、Meili,均为大规模而建)
[pgvector / Meilisearch / FalkorDB]  排序 + 过滤
   │  只吐 top-N(resource_id + 摘要),受 top_k/limit 限流
主控 LLM 上下文(看到的量恒定 ≈ top_k)
```

铁律:**永不把"与语料规模成正比"的数据灌入 LLM;始终 corpus → 引擎(排序/过滤)→ bounded top-N → LLM。**

随增长需主动管理(均为已有机制或可控运维,不动摇上面的结论):

| 随增长的问题 | 对策 |
|---|---|
| 相关度精度下降(近似重复、边界匹配增多) | rank_evidence 重排 + 相关度闸门(`DEFAULT_RELEVANCE_FLOOR=0.50`,库越大越关键)+ 标题去重;后续可调 HNSW recall / 升级 embedding |
| 需深读全文多 | 只深读 top-N + 量大切子 agent 隔离精读 |
| 入库吞吐(嵌入/索引任务多) | outbox + scheduler + 幂等 worker + building→active 原子切换(增量、可重试) |
| 引擎容量/成本(HNSW 内存、Meili 磁盘、embedding 费用) | 后期运维:垂直扩容 / 按 tenant 分片 |

## 5. EvidencePackage 契约(统一证据格式)

单一定义、全链路复用,消除四处重抄,并让格式可被框架强制:

```
EvidencePackage:
  retrieval_mode: "semantic" | "keyword_fallback" | "insufficient_relevance"
  evidence: [
    {
      resource_id: str
      title: str
      summary: str
      source_updated_at: str   # 源端更新时间,未知写"未知"
      indexed_at: str          # 本地索引时间,未知写"未知"
      score: float             # 绝对相关度(cosine)或 bm25 归一化分
      why_relevant: str        # 为何选它
    }
  ]
  gaps: str | null             # 数据不足/缺什么,insufficient_relevance 时必填
```

复用三处,口径统一:
1. **检索工具**的返回结构(现已接近:`resource_id/title/summary/score/metadata{source_updated_at,indexed_at}/why_selected/rank_signals`)。
2. **`knowledge-atom-retriever` 子 agent 的 `response_format`**(重检索时框架强制返回此 schema)。
3. 最终 **`xhs_topics`/`xhs_copy` 的 evidence 块**(字段对齐它)。

证据规约(时效/防伪)作为**单一共享事实源**,由各创作技能引用,而非各写各的:`source_updated_at` 与 `indexed_at` 严格区分;未知写"未知"不猜;`insufficient_relevance` 必须明说"当前数据不足"、不降级凑、不编造。

## 6. 连带决策:thin 持久化子 agent 收回主控

按本规约,以下子 agent 不符合"复杂/多步/需隔离上下文"的子 agent 定位(只是 2 次工具调用、结果需回传、且常处于要与用户交互的创作流中),**应将其职责收回主控技能用工具直调**:

- `topic-generator`(`save_generated_topic` + `sync_topic_to_feishu`)
- `copy-generator`(`save_generated_copy` + `sync_copy_to_feishu`)
- `state-manager`(`save_session_snapshot` + `sync_diagnosis_to_feishu`)

保留为子 agent(符合隔离定位):
- `knowledge-atom-retriever`:**改造**为"仅重检索时用 + `response_format=EvidencePackage`"。
- `persona-distiller`:读多篇历史素材→提炼风格 DNA→产出 SKILL.md 草稿,典型重综合隔离场景。

> 注:HITL 人工确认由 `interrupt_on` 在工具层保证(`sync_*_to_feishu` 等),与"主控直调还是子 agent"无关——收回主控不影响飞书写操作的审批。

## 7. 暂定结论(本规约钉死的部分)

1. 检索 = **工具 + 创作技能的标准第一步**,不立检索技能。
2. 飞书是上游补给,创作只检索 Postgres;数据不足才同步。
3. **统一标准检索流程(§4.3b)= 单一数据源**:语义优先 → 关键词补充 → 精读 top-N →(条件)图增强 → 产出 EvidencePackage;各创作技能引用不重写。
4. **图扩展保留**,定位为"条件触发的证据增强"(衍生/效果邻域),非默认每次走、非可删。
5. 轻量检索走工具(主路径);重检索(深读多篇)走 `knowledge-atom-retriever` 子 agent + `response_format`。
6. 数据增长由引擎吸收,LLM 上下文靠 top_k/排序恒定 bounded;增长期重点维护相关度精度与深读隔离。
7. 统一 **EvidencePackage 契约**,全链路复用,格式由工具返回结构 + 子 agent response_format 双重保证。
8. thin 持久化子 agent(topic/copy/state)收回主控技能用工具直调;子 agent 仅保留 knowledge-atom-retriever(重检索)与 persona-distiller。

### 7.1 检索线实现范围(供立 spec)

检索**相关性内核已上线**(retrieval-relevance-overhaul:中文查询前缀 + 绝对相关度闸门 + 去归一化重排)。本线剩余=**流程收敛与契约统一**,改动集中在提示词/技能/子代理文本 + 一个 schema:

| 文件 | 改动 |
|---|---|
| `prompts.py` | 新增/收敛"检索与证据规约"节(统一检索顺序、insufficient_relevance 处理、EvidencePackage 字段、时效防伪)——**唯一事实源** |
| `.agents/skills/{topic-content,xhs-benchmark,xhs-planning,xhs-content-system}/SKILL.md` | 删除各自重抄的检索步骤,改为引用主控规约;只留差异化工作流 |
| `subagents_executor.py` | `knowledge-atom-retriever` 加 `response_format=EvidencePackage`;**移除** topic-generator/copy-generator/state-manager(职责收回主控技能) |
| (新)`EvidencePackage` schema | Pydantic 模型,供子代理 response_format + 工具返回对齐 |
| `data_foundation/tools.py` | save_*/sync_* 仍是工具(主控直调);确认 thin 子代理移除后主控仍能直接落库同步 |
| tests | 路由/契约测试相应更新(dbskill_alias_coverage 等);新增 EvidencePackage 形状测试 |

风险:纯提示词/技能/子代理重构 + 一个 schema,无 schema 迁移、无重嵌;属中等改造,走正式 spec + 全量测试 + 部署。

## 8. 内容关联与效果增强(独立主线 · 数据底座层)

> 来源:对线上 4685 节点 / 7 边 + content_json 字段的实测探查。本节把"关联图谱增强"按数据事实**重定义**。

### 8.1 实测事实

- 图功能完整可用,但**几乎无边**:4685 节点 / 7 边(全 `derived_from`,来自 2 个生成内容)。ingest 只建节点不抽边。
- `dbskill_atom`(4176)只有 **10 个 topic / 5 个 skill**,每个被上千原子共享 → 按共享建边会形成百万级"毛球",**无精度**。→ 当**分类 facet**用,不建边。
- 正文 hashtag 基本为空(4685 中仅 21 条);**真正的标签在飞书多维表格的结构化列里**,不在正文。
- `feishu_base_record`(506 真实爆款)的 `content_json.fields` 携带**丰富结构化列**:点赞数(403)、收藏数(126)、评论数(126)、回复数(257)、博主(127)、用户名(257)、分类标签(122)、话题标签(110)、类型(146)、标题(408)、正文(108)、发布时间(115)。

### 8.2 最重磅发现:效果数据已在库、却未接入

506 条爆款的**点赞/收藏/评论数就在 `content_json.fields` 里**,但从未流入 `save_performance_metric` / `measured_by` 边 / `rank_evidence` 效果加权。**"哪些内容真的爆了"这个最强选题信号,数据现成、完全没用起来。** 接通它比建任何关联图都更直接提升选题精度。

### 8.3 重定义:从"关联图谱" → "飞书结构化字段抽取增强"

不是建语义图,而是在飞书 base 行落库时(`data_foundation/feishu_sync.py::sync_base_rows` / Feishu source processor),把已有结构化列**映射成效果指标 + 关系边**。全程**结构化、零 LLM、零新依赖、不引入任何 GraphRAG 框架**。

按 ROI 优先级:

| 优先级 | 抽取 | 产物 | 价值 |
|---|---|---|---|
| **① 最高** | 点赞/收藏/评论/回复数 | `performance_metric` 资源 + `measured_by` 边 → 喂 `rank_evidence` 效果分 | 直接让选题"从验证过会爆的内容反推",精度最强 |
| ② | 博主/用户名 | `same_author` 边 | 看某博主在该方向的打法 |
| ③ | 分类标签/话题标签/类型 | `shares_tag` / `shares_category` 边(干净结构化标签) | 按真实话题/品类成簇找方向 |
| facet | dbskill `topics`/`skills`(10/5 类) | 分类筛选维度,**不建边** | 避免毛球;作 retrieval facet |
| 不做 | 泛语义相似 | — | 语义检索已覆盖,建边纯冗余 |

### 8.4 约束

- **列名可配置**:多维表列名因表而异、覆盖率不齐(点赞数 403/506、博主 127/506),映射须容缺、按列名映射表配置,缺列跳过不报错。
- **幂等**:re-sync 时按 record 更新效果指标/边,不重复堆积。
- **效果指标走既有契约**:复用 `save_performance_metric_resource` / `measured_by`,不另起一套。
- **不脱离单一引擎职责**:图仍只走 FalkorDB、效果仍走 Postgres performance 资源;本节只新增"飞书字段 → 既有契约"的映射层。

### 8.5 与检索/选题的衔接

- 效果指标接通后,`rank_evidence` 的 performance 权重(当前 0.05)才真正有数据可用 → 出选题时高表现来源自然上浮。
- `graph_expand`(§4.3b ④)有了 `measured_by`/`same_author`/`shares_tag` 边后才有东西可返回,"为什么推荐这个方向(带历史效果)"才立得住。

### 8.6 范围与定位

本节是**独立主线**(数据底座层),比"检索流程梳理"大,涉及 ingest 映射 + 存量 506 条回填 + 排序整合。建议作为**单独 spec**推进;检索规约(§1-7)可先行。

## 9. 待续(后续梳理,本草案尚未定稿)

- **检索规约(§1-7)**:可先行,基本定稿;落地需改 prompts/SKILL/subagents(较大,走正式 spec)。
- **内容关联与效果增强(§8)**:独立主线,建议单独 spec;优先做"效果指标接通"(① 最高 ROI)。
- 选题入口收敛:`topic-content` / `xhs-planning` / `xhs-content-system` 三条选题路如何合并/分工。
- "出选题→停下等用户选→写文案"的交互编排细节(必须留在主控技能,因子 agent 无状态、不可中途交互)。
- 情况 B(语料无该方向)的产品取舍:严格拒绝 / 标注推断创意 / 混合——待用户定。
- thin 持久化子 agent(topic/copy/state)收回主控的落地。
- 厘清类 4 技能(goal/good-question/deconstruct/action)是否合并。

> 本草案定稿后,再决定是否升级为正式 kiro spec(requirements/design/tasks)并落地实现。当前仅为创作流程梳理的共识地基。
