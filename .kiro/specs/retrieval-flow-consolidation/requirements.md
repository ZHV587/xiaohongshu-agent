# Requirements Document

## Introduction

本需求文档从已完成并经三轮自审的 `design.md` 反推而来。`retrieval-flow-consolidation` 是一次**纯结构重构**:把"检索 / 取证 / 落库 / 同步"在四个创作技能里各抄一遍、又与 thin 子代理并行的逻辑,收敛为**单一事实源**(落 `prompts.py`),并按 deepagents 0.6.10 官方三层原语(工具 / 技能 / 子代理)重新对齐职责边界,引入统一的 `EvidencePackage` 证据契约。

**不在本范围**:相关性算法(中文查询前缀 / 绝对相关度闸门 / 去归一化重排)已由 `retrieval-relevance-overhaul` 上线,本 spec 不改动;内容关联图谱建边(同作者 / 同标签等)属另一条独立主线(草案 §8),`graph_expand` 在本 spec 内仅保留为条件触发占位,其实际产出待该主线落地。无 schema 迁移、无重嵌入、无新依赖。

本文档需求与 design.md 的 9 条 Correctness Properties 一一对应,以便补齐设计中的 "Validates: Requirements X.Y" 引用。

## Glossary

- **Retrieval_Evidence_Spec**:《检索与证据规约》——统一检索顺序、mode 三态处理、EvidencePackage 字段、时效/防伪规约的定义节,落于 `prompts.py` 主控系统提示。
- **Main_Prompt**:主控系统提示 `prompts.py`,运行时每轮常驻上下文,是 Retrieval_Evidence_Spec 的唯一物理载体。
- **Creation_Skill**:四个创作技能 `topic-content`、`xhs-benchmark`、`xhs-planning`、`xhs-content-system` 的 SKILL.md。
- **EvidencePackage**:统一证据包 Pydantic 模型(`retrieval_mode` + `evidence[]` + `gaps`);**检索步骤的证据产出契约**,非各技能最终输出。
- **EvidenceItem**:EvidencePackage 中单条证据,字段 `resource_id`/`title`/`summary`/`source_updated_at`/`indexed_at`/`score`/`why_selected`。
- **Retrieval_Mode**:检索返回态,取值 `semantic` | `keyword_fallback` | `insufficient_relevance`。
- **Knowledge_Atom_Retriever**:重检索子代理 `knowledge-atom-retriever`,通过 `task` 委派,带 `response_format=EvidencePackage`。
- **Thin_Persistence_Subagents**:被移除的三个 thin 持久化子代理 `topic-generator`/`copy-generator`/`state-manager`。
- **Executor_Subagents**:`build_executor_subagents()` 返回的子代理集合与 `EXECUTOR_SUBAGENT_NAMES`。
- **Persistence_Tools**:落库与同步工具 `save_generated_topic`/`save_generated_copy`/`save_session_snapshot` 及对应 `sync_*_to_feishu`。
- **Routing_Contract**:`test_dbskill_alias_coverage.py` 守护的路由契约(语义触发短语、无斜杠命令、无手抄路由表、prompt 点名真实单元)。
- **Delegation_Decision_Point**:决定轻量(主控直调)还是重检索(委派)的评估时点——初次语义检索之后。

## Requirements

### Requirement 1: 检索与证据规约单一事实源

**User Story:** As a 系统维护者, I want 检索顺序/mode 处理/防伪规约只在一处定义, so that 不再四处重抄、不漂移。

#### Acceptance Criteria

1. THE Retrieval_Evidence_Spec SHALL 完整定义于 Main_Prompt(`prompts.py`)中,且为该定义的唯一运行时载体。
2. THE 系统 SHALL NOT 将 Retrieval_Evidence_Spec 放入 `.kiro/steering`(其不进入 deepagents 运行时)。
3. WHERE 任一 Creation_Skill 需要检索与取证, THE 该 Creation_Skill SHALL 以一句引用指向 Main_Prompt 的 Retrieval_Evidence_Spec,而非重述其内容。
4. THE 每个 Creation_Skill 正文 SHALL NOT 包含 Retrieval_Mode 三态的完整重述(此为语义不变量,由 code review 保证;可选弱自动化:断言技能正文不出现 mode 字面量)。
5. WHILE 删除检索/取证重述, THE 每个 Creation_Skill SHALL 保留其**差异化工作流**(`topic-content` 方向→选题→文案两步流、`xhs-benchmark` 五重漏斗去噪与行级拆解、`xhs-planning` 规律提炼与选题卡装配、`xhs-content-system` 底座审计/主题地图/单元结构化);去重 SHALL 仅针对检索/取证重述部分,SHALL NOT 删除上述差异化逻辑。

### Requirement 2: 统一检索流程与 mode 三态完备

**User Story:** As a 主控 Agent, I want 一套确定的检索顺序与三态处理, so that 每种检索结果都有明确分支。

#### Acceptance Criteria

1. THE Retrieval_Evidence_Spec SHALL 规定检索顺序:① 语义优先 `semantic_search_resources` → ② 关键词补充 `search_resources`(条件)→ ③ 精读 `get_resource` × top-N → ④ `graph_expand`(条件触发)→ ⑤ 产出 EvidencePackage。
2. THE Retrieval_Mode SHALL 仅取值 `semantic`、`keyword_fallback`、`insufficient_relevance` 三者之一。
3. WHEN Retrieval_Mode == `semantic`, THE 主控 SHALL 正常使用 evidence 进行创作。
4. WHEN Retrieval_Mode == `keyword_fallback`, THE 主控 SHALL 使用其全文结果并标注为降级。
5. THE 创作流程 SHALL 仅检索 Postgres 数据底座;WHEN 数据不足, THE 主控 SHALL 调 `sync_feishu_resources` 同步后重检索。

### Requirement 3: 数据不足不编造

**User Story:** As a 主控 Agent, I want 库内无足够相关内容时明确告知, so that 不编造、不强行降级凑依据。

#### Acceptance Criteria

1. WHEN Retrieval_Mode == `insufficient_relevance`, THE 返回 EvidencePackage SHALL 满足 `evidence == []` 且 `gaps` 非空。
2. WHEN Retrieval_Mode == `insufficient_relevance`, THE 主控 SHALL 明确回复"当前数据不足"并建议同步/补充数据,且 SHALL NOT 降级到关键词检索去凑依据。
3. IF 同步后仍无可用来源, THEN THE 主控 SHALL 维持"数据不足"结论,SHALL NOT 编造来源或选题。

### Requirement 4: 证据时效与防伪字段恒在

**User Story:** As a 内容质检, I want 每条证据的时效字段如实且必现, so that 源端过时不被包装成当前事实。

#### Acceptance Criteria

1. THE 每个 EvidenceItem SHALL 包含字符串字段 `source_updated_at` 与 `indexed_at`。
2. IF 某时效值未知, THEN THE 该字段值 SHALL 为字面量 `"未知"`,且 SHALL NOT 省略字段。
3. THE EvidenceItem SHALL NOT 以 `updated_at` 作为 `source_updated_at` 或 `indexed_at` 的替代。
4. THE EvidenceItem 的 `source_updated_at`(源端)与 `indexed_at`(本地索引)SHALL 语义严格区分。

### Requirement 5: EvidencePackage 契约与边界

**User Story:** As a 实现者, I want EvidencePackage 是检索步骤的证据契约且字段对齐既有, so that 结构可被框架强制且不破坏前端。

#### Acceptance Criteria

1. THE 系统 SHALL 定义 `EvidencePackage`/`EvidenceItem` 为 Pydantic 模型(放置 `data_foundation/evidence.py`),无新增第三方依赖。
2. THE EvidenceItem SHALL 使用字段名 `why_selected`(沿用现有工具与前端 `types.ts`),SHALL NOT 引入新名 `why_relevant`。
3. WHEN 从检索工具结果组装 EvidenceItem, THE 实现 SHALL 将 `metadata` 内的 `source_updated_at`/`indexed_at` 提平到 EvidenceItem 顶层。
4. THE EvidencePackage SHALL 是检索步骤的证据产出契约,SHALL NOT 取代各 Creation_Skill 的最终输出格式(如去噪报告、主题地图)。
5. THE `xhs_topics`/`xhs_copy` 的 evidence 块字段集 SHALL 与 EvidenceItem 对齐(为其子集),SHALL NOT 增删前端依赖字段。

### Requirement 6: 重检索强制结构化

**User Story:** As a 主控 Agent, I want 重检索子代理强制返回结构化证据包, so that 隔离上下文的同时格式有保证。

#### Acceptance Criteria

1. THE Knowledge_Atom_Retriever 的子代理规格 SHALL 含 `response_format == EvidencePackage`。
2. WHEN Knowledge_Atom_Retriever 完成, THE 其返回 SHALL 是符合 EvidencePackage 的结构化输出。
3. IF 其输出缺字段或 `retrieval_mode` 非法, THEN THE 框架 SHALL 触发 ValidationError(重试/报错),SHALL NOT 静默放过。
4. THE Knowledge_Atom_Retriever 的 system_prompt SHALL 引用同一 Retrieval_Evidence_Spec 口径。

### Requirement 7: 子代理集合收敛与职责边界

**User Story:** As a 系统维护者, I want 移除 thin 持久化子代理并由主控直调工具, so that 职责边界符合官方原语、无并行歧义。

#### Acceptance Criteria

1. THE `build_executor_subagents()` 返回集合的 name SHALL 恰为 `{"knowledge-atom-retriever", "persona-distiller"}`。
2. THE `EXECUTOR_SUBAGENT_NAMES` SHALL 与上述集合一致,且 SHALL NOT 含 Thin_Persistence_Subagents 任一。
3. THE `subagents_executor.py` SHALL 移除 `build_topic_generator`/`build_copy_generator`/`build_state_manager` 三个工厂。
4. THE Main_Prompt §1"可用执行型 subagent"枚举 SHALL 删除 Thin_Persistence_Subagents 三行,仅保留两个保留子代理。
5. THE Main_Prompt §3 委派规则 SHALL 删除对 Thin_Persistence_Subagents 的委派条目,并明确落库同步由主控直调 Persistence_Tools。
6. THE Main_Prompt SHALL NOT 残留对 Thin_Persistence_Subagents 任一的点名(无悬挂引用)。

### Requirement 8: 落库能力不回退

**User Story:** As a 主控 Agent, I want 移除子代理后仍能落库与同步, so that 创作闭环不缺失、HITL 不受影响。

#### Acceptance Criteria

1. THE 主控 SHALL 能直接调用 Persistence_Tools(`save_generated_topic`/`save_generated_copy`/`save_session_snapshot` + 对应 `sync_*_to_feishu`)。
2. THE `sync_*_to_feishu` 工具的 HITL 拦截 SHALL 仍由工具层 `interrupt_on` 保证,不因子代理移除而改变。
3. WHEN `save_*` 成功而 `sync_*_to_feishu` 失败, THE 主控 SHALL 保留数据库事实并明确报告同步失败,SHALL NOT 回滚落库。

### Requirement 9: 轻/重委派的决策点

**User Story:** As a 主控 Agent, I want 明确何时内联检索、何时委派重检索, so that 不再摇摆。

> 本需求为**提示词行为类**:由主控 LLM 遵循 Retrieval_Evidence_Spec 体现,**靠 review/eval 验证,非单元测试**。下列阈值为启发式默认,非硬性可断言数值。

#### Acceptance Criteria

1. THE 主控 SHALL 总是先执行轻量语义检索(`semantic_search_resources`)取候选。
2. THE Delegation_Decision_Point SHALL 发生在初次语义检索之后,而非之前。
3. WHEN 候选仅需摘要加**少量**精读即可支撑(主控判定无需隔离上下文;经验默认约 5 篇,可调,非硬阈值), THE 主控 SHALL 内联直调 `get_resource` 完成(轻),SHALL NOT 委派。
4. WHEN 需精读**大量**全文跨多源综合才能定, THE 主控 SHALL 委派 Knowledge_Atom_Retriever(重)。
5. THE 委派切换信号 SHALL 是 per-query 的候选深读量,SHALL NOT 由语料库规模决定。

### Requirement 10: 路由契约与测试保持

**User Story:** As a 系统维护者, I want 重构后路由契约与装配测试仍绿, so that 不引入回归。

#### Acceptance Criteria

1. THE 每个被路由的 Creation_Skill 的 `description` SHALL 保留至少 2 个「」语义触发短语。
2. THE 所有 SKILL.md(frontmatter 与正文)与 Main_Prompt SHALL NOT 含斜杠命令,Main_Prompt SHALL NOT 含"强匹配"手抄路由表。
3. THE Main_Prompt 点名的每个 skill/subagent SHALL 真实存在(对应目录或注册名)。
4. THE `tests/test_agent_assembly.py` 中对 Thin_Persistence_Subagents 的逐名断言(现第 415-427 行)SHALL 被删除或重写为"仅 2 个子代理 + Knowledge_Atom_Retriever 带 response_format"。
5. THE `tests/test_subagents.py` SHALL 更新为断言 2 个子代理,移除对三个 thin 工厂的导入/断言。
6. THE 新增 `tests/test_evidence_package.py` SHALL 覆盖 EvidencePackage 形状与不变量(含 `insufficient_relevance ⟺ evidence==[] ∧ gaps≠None`、时效字段恒为字符串)。

### Requirement 11: 重构边界

**User Story:** As a 部署负责人, I want 本 spec 严格限定为结构重构, so that 风险可控、无数据迁移。

#### Acceptance Criteria

1. THE 本 spec SHALL NOT 改动相关性算法(查询前缀 / 闸门 / 重排)。
2. THE 本 spec SHALL NOT 涉及 schema 迁移、向量重嵌、新检索引擎或新外部服务。
3. THE `graph_expand` SHALL 在本 spec 内仅作为条件触发占位保留,其关联边产出依赖独立主线(草案 §8),不在本 spec 范围。
4. THE 引擎职责 SHALL 保持单一(全文 Meili、语义 pgvector、图 FalkorDB)。
