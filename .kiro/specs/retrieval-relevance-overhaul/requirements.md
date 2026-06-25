# Requirements Document

## Introduction

本需求文档从已批准的设计文档 (`design.md`) 反推而来,描述对小红书内容智能体语义检索 (`semantic_search_resources`) 的相关性根本性修复。

当前缺陷:对语料中不存在的查询(如"露营装备推荐"),系统仍返回最近邻;排序层的候选集内归一化把弱相关结果(绝对余弦 0.46)抬升为 `relevance=1.0`、最终分 0.80,以"虚高分依据"形式呈现给主 agent,违背"数据不足要明说、绝不编造"的核心原则。

修复在检索质量的三个层面做根因修正,并满足一组边界约束:

1. **查询指令前缀(模型感知)**:对非对称检索模型(Qwen3-Embedding 类)在查询端注入指令前缀,文档端保持裸文本。
2. **排序去归一化(口径隔离)**:余弦路径使用绝对相关度,BM25 路径保留候选集内归一化,二者严格隔离。
3. **绝对相关度闸门**:语义检索 top 绝对余弦低于阈值时,返回明确的"数据不足/低相关"态,而非把弱相关结果当依据。

边界约束:不改 schema(仍 1536 维)、不重嵌文档、不影响 active 索引、相关测试按"不做兼容"重写、密钥与指令模板不进日志/遥测。

本文档的需求与设计文档中的 6 条 Correctness Properties 一一对应,以便后续补全设计中的 "Validates: Requirements X.Y" 引用。

## Glossary

- **Query_Embedder**: 查询端嵌入组件 (`data_foundation/tools.py::_embed_query`),负责把查询文本送嵌入 provider 取向量,并按配置决定是否注入指令前缀。
- **Document_Embedder**: 文档端嵌入组件 (`data_foundation/processors/embedding.py::EmbeddingProcessor._embed`),负责对入库文档生成向量。
- **Evidence_Ranker**: 证据排序组件 (`data_foundation/search_ranker.py::rank_evidence`),负责对候选结果加权排序、去重、截断。
- **Semantic_Search_Tool**: 语义检索工具 (`data_foundation/tools.py::semantic_search_resources`),编排嵌入、检索、闸门、排序,产出带 `mode` 的结构化返回。
- **Embedding_Config**: 嵌入配置 (`EmbeddingProviderConfig` 及 `data_foundation/config.py` 快照),承载 `model`、`dimensions`、`query_instruction` 等字段。
- **Query_Instruction**: 查询端指令模板字符串,含 `{query}` 占位符;由配置键 `XHS_EMBEDDING_QUERY_INSTRUCTION` 或模型感知默认值确定。
- **Asymmetric_Model**: 非对称检索嵌入模型,指模型名(大小写不敏感)包含 `qwen3-embedding` 的模型。
- **Relevance_Floor**: 绝对相关度下限闸门阈值,默认 0.50,可经配置键 `XHS_EMBEDDING_RELEVANCE_FLOOR`(归属 `XHS_EMBEDDING_*` 配置族,支持配置中心热重载)覆盖,仅作用于语义(余弦)路径。
- **Fulltext_Search_Tool**: 全文检索工具 (`data_foundation/tools.py::search_resources`),走 Meilisearch BM25,既是 `Semantic_Search_Tool` 降级时的被调方,也是可被 agent/skill 直接调用的独立工具;其内部直接调用 `Evidence_Ranker`。
- **Prompt_Consumers**: 解读 `Semantic_Search_Tool` 返回 `mode` 的提示词消费方,包括主控系统提示词 (`prompts.py`)、`topic-content` 的 `SKILL.md`、`knowledge-atom-retriever` 子代理提示词。
- **Cosine_Path**: 语义检索路径,分数为 pgvector 绝对余弦相似度(≈ 0~1),进入 `Evidence_Ranker` 时 `score_kind="cosine"`。
- **BM25_Path**: 全文降级路径,分数为 Meilisearch BM25 类分数(无固定上界),进入 `Evidence_Ranker` 时 `score_kind="bm25"`。
- **Active_Index**: 当前生效的嵌入索引 (`active_embedding_index` / `embedding_indexes`)。
- **Insufficient_Relevance_Mode**: 返回态 `mode == "insufficient_relevance"`,表示语义检索正常但库内无足够相关内容。
- **Keyword_Fallback_Mode**: 返回态 `mode == "keyword_fallback"`,表示语义基础设施不可用时的全文兜底。

## Requirements

### Requirement 1: 模型感知的查询端指令前缀

**User Story:** As a 检索系统维护者, I want 查询端对非对称嵌入模型注入指令前缀且文档端保持裸文本, so that 非对称检索模型的查询区分度提升而不破坏其他 provider 的对称检索语义。

#### Acceptance Criteria

1. WHERE `Embedding_Config.query_instruction` 非空, THE Query_Embedder SHALL 将发送给嵌入 provider 的文本设为 `query_instruction.format(query=query)`。
2. WHERE `Embedding_Config.query_instruction` 为 None, THE Query_Embedder SHALL 将发送给嵌入 provider 的文本设为原始查询裸文本。
3. THE Document_Embedder SHALL 发送裸文本,且 SHALL NOT 读取 `Embedding_Config.query_instruction`。
4. WHEN 计算 `query_instruction` 默认值且管理员未显式配置 `XHS_EMBEDDING_QUERY_INSTRUCTION` 且模型为 Asymmetric_Model, THE Embedding_Config SHALL 将 `query_instruction` 设为含 `{query}` 占位符的默认指令模板。
5. WHEN 计算 `query_instruction` 默认值且管理员未显式配置 `XHS_EMBEDDING_QUERY_INSTRUCTION` 且模型不是 Asymmetric_Model, THE Embedding_Config SHALL 将 `query_instruction` 设为 None。
6. WHERE 管理员显式配置了 `XHS_EMBEDDING_QUERY_INSTRUCTION`, THE Embedding_Config SHALL 使用该显式配置值作为 `query_instruction`,优先于模型感知默认值。
7. THE Embedding_Config SHALL 将 `XHS_EMBEDDING_QUERY_INSTRUCTION` 归属 `XHS_EMBEDDING_*` 配置族,支持配置中心热重载。
8. IF `Query_Instruction` 模板不含 `{query}` 占位符, THEN THE Embedding_Config SHALL 在配置解析层拒绝该模板。
9. WHEN 为语义查询解析 `Query_Instruction`, THE 系统 SHALL 基于 Active_Index 的模型名与**当前**配置(显式 `XHS_EMBEDDING_QUERY_INSTRUCTION`)计算,且 SHALL NOT 取自随 `config_version` 回放的历史快照存值;因此即使 Active_Index 的 `config_version` 早于本功能,Asymmetric_Model 仍命中模型感知默认前缀。

### Requirement 2: 排序去归一化与分数口径隔离

**User Story:** As a 检索系统维护者, I want 余弦路径保留绝对相关度而 BM25 路径保留候选集内归一化, so that 弱相关语义结果不再被归一化抬升成虚高分,且两类分数口径不互相污染。

#### Acceptance Criteria

1. THE Evidence_Ranker SHALL 接受一个**必填**参数 `score_kind`(无默认值),取值集合为 `{"cosine", "bm25"}`。
2. WHEN `score_kind == "cosine"`, THE Evidence_Ranker SHALL 将每条结果的 `relevance` 设为 `clamp(item["score"], 0.0, 1.0)`,且 SHALL NOT 做候选集内归一化。
3. WHEN `score_kind == "bm25"`, THE Evidence_Ranker SHALL 将每条结果的 `relevance` 设为 `item["score"] / max_raw_score`(候选集内归一化)。
4. WHEN `score_kind == "cosine"`, THE Evidence_Ranker SHALL 使任一结果的 `relevance` 仅由其自身绝对余弦决定,不随候选集中其他结果的最大值变化。
5. THE Evidence_Ranker SHALL 按 `final = 0.70*relevance + 0.15*freshness + 0.10*type_weight + 0.05*performance` 计算最终分。
6. THE Evidence_Ranker SHALL 将权重常量定义为 `WEIGHT_RELEVANCE=0.70`、`WEIGHT_FRESHNESS=0.15`、`WEIGHT_TYPE=0.10`、`WEIGHT_PERFORMANCE=0.05`,且四者之和等于 1.0。
7. THE Evidence_Ranker SHALL 按 `final` 降序排序结果、对标题相似度大于 0.90 的结果做模糊去重、并截断到 `limit`。
8. THE Evidence_Ranker SHALL 在 `rank_signals.relevance` 中反映该路径对应 `score_kind` 的真实 relevance 口径。
9. WHEN Fulltext_Search_Tool 调用 Evidence_Ranker, THE Fulltext_Search_Tool SHALL 显式传入 `score_kind="bm25"`(该调用点位于 `search_resources` 内部,即真实的 BM25 入排序点)。
10. BEFORE 依赖 BM25 归一化, THE Fulltext_Search_Tool SHALL 确保传入 Evidence_Ranker 的每条结果带有有意义的 BM25 相关度分数(若 Meilisearch 检索路径未产出可用分数,则需修正分数来源,而非对全 0/占位分数做无效归一化)。

### Requirement 3: 绝对相关度闸门与数据不足返回态

**User Story:** As a 主 agent, I want 库内无足够相关内容时收到明确的"数据不足"信号, so that 我不把弱相关结果当作创作依据,兑现反编造原则。

#### Acceptance Criteria

1. THE Semantic_Search_Tool SHALL 使用绝对相关度下限阈值 `Relevance_Floor`,默认值为 0.50,且 SHALL 支持经配置键 `XHS_EMBEDDING_RELEVANCE_FLOOR` 覆盖(归属 `XHS_EMBEDDING_*` 配置族,支持配置中心热重载)。
2. WHEN 语义检索成功, THE Semantic_Search_Tool SHALL 基于 `semantic_search` 返回的原始绝对余弦,在调用 `Evidence_Ranker` 加权之前,计算结果集 top 绝对余弦。
3. IF 语义检索成功且结果集 top 绝对余弦小于 `Relevance_Floor`, THEN THE Semantic_Search_Tool SHALL 返回 `mode == "insufficient_relevance"`、`results == []`,并携带 `top_score` 与 `threshold` 字段。
4. WHEN 语义检索成功且结果集 top 绝对余弦大于等于 `Relevance_Floor`, THE Semantic_Search_Tool SHALL 返回 `mode == "semantic"`,且 `results` 为 `Evidence_Ranker(score_kind="cosine")` 的排序结果。
5. IF 语义检索成功且结果集为空, THEN THE Semantic_Search_Tool SHALL 返回 `mode == "insufficient_relevance"` 且 `results == []`。
6. WHEN 进入 Insufficient_Relevance_Mode, THE Semantic_Search_Tool SHALL NOT 降级到 BM25_Path。
7. THE Relevance_Floor 的默认值与生效值 SHALL 在最终上线的查询指令模板(`Query_Instruction` 默认值)下、基于生产语料用多组真实查询完成经验标定;SHALL NOT 沿用以其他指令文本(例如标定期使用的临时英文模板)测得的分数作为阈值依据。
8. WHEN 闸门解析 `Relevance_Floor`, THE Semantic_Search_Tool SHALL 从**当前**配置解析(`XHS_EMBEDDING_RELEVANCE_FLOOR` 或 `DEFAULT_RELEVANCE_FLOOR`),且 SHALL NOT 取自随 Active_Index `config_version` 回放的历史 embedding profile;`Relevance_Floor` SHALL NOT 作为 `EmbeddingProviderConfig` 字段随历史回放。

### Requirement 4: 基础设施降级语义保持

**User Story:** As a 主 agent, I want 语义检索基础设施不可用时仍得到全文兜底结果, so that 在嵌入能力不可用时检索依然可用,且该兜底不被新闸门误判。

#### Acceptance Criteria

1. IF 不存在 Active_Index, THEN THE Semantic_Search_Tool SHALL 返回 `mode == "keyword_fallback"`,`fallback_reason == "NO_ACTIVE_EMBEDDING_INDEX"`。
2. IF 嵌入 provider 返回 401 或 403, THEN THE Query_Embedder SHALL 抛出 `EmbeddingSearchUnavailable("EMBEDDING_QUERY_UNAUTHORIZED")`,且 THE Semantic_Search_Tool SHALL 返回 `mode == "keyword_fallback"`。
3. IF 嵌入 provider 出现网络异常(5xx、超时、拒连), THEN THE Semantic_Search_Tool SHALL 返回 `mode == "keyword_fallback"`,`fallback_reason` 前缀为 `"EMBEDDING_QUERY_HTTP_ERROR"`。
4. IF 查询向量校验失败(维度不符或含 NaN), THEN THE Semantic_Search_Tool SHALL 返回 `mode == "keyword_fallback"`,`fallback_reason` 前缀为 `"EMBEDDING_QUERY_INVALID_VECTOR"`。
5. IF 查询为空或全空白, THEN THE Semantic_Search_Tool SHALL 返回 `mode == "keyword_fallback"`,`fallback_reason == "EMPTY_QUERY"`,且 SHALL NOT 调用嵌入 provider。
6. WHEN 进入 Keyword_Fallback_Mode, THE Semantic_Search_Tool SHALL 使用 `Evidence_Ranker(score_kind="bm25")`,且 SHALL NOT 将 BM25 分数与 `Relevance_Floor` 比较。
7. THE 系统 SHALL 将以下情形记录为**已知限制**:当语义基础设施不可用而走 BM25_Path 时,不施加绝对相关度闸门,因此"数据不足必明说"的保证仅在 Cosine_Path(语义可用)成立;BM25_Path 仍可能返回弱相关结果。

### Requirement 5: Schema 与索引边界保持

**User Story:** As a 部署负责人, I want 本次修复不触动数据底座的向量 schema 与已嵌入资源, so that 无需重嵌、active 索引不受影响、部署风险可控。

#### Acceptance Criteria

1. THE Embedding_Config SHALL 保持向量维度为 1536。
2. THE Query_Embedder SHALL 校验嵌入 provider 返回的向量为 1536 维有限浮点向量。
3. THE Document_Embedder SHALL 保持现有文档端嵌入行为不变,不触发对 `resource_embeddings` 的重嵌。
4. THE Semantic_Search_Tool SHALL NOT 修改 Active_Index 或 `embedding_indexes` 的内容。

### Requirement 6: 测试重写与密钥/模板脱敏

**User Story:** As a 检索系统维护者, I want 相关测试按"不做兼容"重写且敏感信息不入日志, so that 测试反映真实的修复后行为,且指令模板与密钥不泄露。

#### Acceptance Criteria

1. THE Evidence_Ranker 测试 SHALL 断言 `score_kind="cosine"` 时 `relevance` 等于绝对余弦(例如 score=0.46 对应 relevance≈0.46,而非 1.0)。
2. THE Evidence_Ranker 测试 SHALL 断言 `score_kind="bm25"` 时保留候选集内归一化行为。
3. THE Evidence_Ranker 测试 SHALL 断言权重配比为 0.70/0.15/0.10/0.05。
4. THE Semantic_Search_Tool 测试 SHALL 断言 Asymmetric_Model 时查询 `input` 文本含指令前缀,非 Asymmetric_Model 时为裸文本。
5. THE Semantic_Search_Tool 测试 SHALL 断言 top 绝对余弦小于阈值时返回 `mode == "insufficient_relevance"`、`results == []` 并携带 `top_score`/`threshold`。
6. THE Semantic_Search_Tool SHALL NOT 将 `Query_Instruction` 模板或 `api_key` 写入日志、错误摘要或遥测数据。

### Requirement 7: 提示词消费方解读新返回态

**User Story:** As a 主 agent / 子代理, I want 提示词明确告知如何处理 `insufficient_relevance` 返回态, so that 我在库内无足够相关内容时明确告知"当前数据不足",不把弱相关结果当依据、不擅自降级或编造。

#### Acceptance Criteria

1. THE Prompt_Consumers SHALL 描述 `Semantic_Search_Tool` 的三种 `mode`(`semantic`、`insufficient_relevance`、`keyword_fallback`)及各自含义。
2. WHEN `Semantic_Search_Tool` 返回 `mode == "insufficient_relevance"`, THE 主控系统提示词与 `topic-content` 工作流 SHALL 指示 agent 明确回复"当前数据不足"并建议同步/补充数据,且 SHALL NOT 把空结果或弱相关内容当作创作依据、SHALL NOT 编造来源。
3. THE `knowledge-atom-retriever` 子代理提示词 SHALL 更新为识别 `insufficient_relevance`(不再仅依据 `keyword_fallback` 判断),在该态下报告证据不足(`gaps`)而非强行补召回。
4. THE Prompt_Consumers SHALL NOT 指示在 `insufficient_relevance` 态下回退到关键词检索以"凑"出依据。
