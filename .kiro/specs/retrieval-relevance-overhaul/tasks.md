# Implementation Plan: 检索相关性根本性修复 (retrieval-relevance-overhaul)

## Overview

本计划将 `design.md` 的三层根因修复(查询端模型感知指令前缀、排序去归一化与口径隔离、绝对相关度闸门)拆解为可增量执行、每步可验证的编码任务。遵循项目铁律:**从根因改,不打补丁、不加兼容层,相关测试一并重写**。

实现语言为 **Python**(设计已使用具体语言,无需另选)。任务顺序遵循"先底层常量/配置 → 再查询端注入 → 再工具编排闸门 → 最后测试重写"的依赖链,确保每一步都能落在已存在的上游产物之上,无悬挂代码。

受影响文件(见设计"受影响文件清单"):`data_foundation/search_ranker.py`、`data_foundation/config.py`、`data_foundation/processors/embedding.py`、`data_foundation/tools.py`、`data_foundation/search.py`、`tests/data_foundation/test_search_ranker.py`、`tests/data_foundation/test_search_graph_tools.py`。

## Tasks

- [x] 1. 排序层:常量集中定义 + 去归一化与口径隔离
  - [x] 1.1 在 `search_ranker.py` 新增阈值/权重常量并实现 `score_kind` 口径分支
    - 在 `data_foundation/search_ranker.py` 模块级新增常量:`DEFAULT_RELEVANCE_FLOOR = 0.50`(默认阈值,可被配置覆盖)、`WEIGHT_RELEVANCE = 0.70`、`WEIGHT_FRESHNESS = 0.15`、`WEIGHT_TYPE = 0.10`、`WEIGHT_PERFORMANCE = 0.05`(附设计中的经验依据与"标定口径警示"注释)
    - 为 `rank_evidence` 增加**必填**关键字参数 `score_kind: str`(无默认值,强制每个调用点显式声明口径),校验取值 ∈ `{"cosine", "bm25"}`
    - 实现 `_relevance_score(item, score_kind, max_raw_score)`:`cosine` 路径返回 `clamp(raw, 0.0, 1.0)`(不做候选集内归一化);`bm25` 路径返回 `raw / max_raw_score`(保留候选集内归一化)
    - 将最终分计算改为使用 `WEIGHT_*` 常量:`final = WEIGHT_RELEVANCE*relevance + WEIGHT_FRESHNESS*freshness + WEIGHT_TYPE*type_weight + WEIGHT_PERFORMANCE*performance`
    - 保留既有行为:按 `final` 降序排序、标题相似度 > 0.90 模糊去重、截断到 `limit`、`rank_signals.relevance` 反映该路径真实口径
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 2.7, 2.8_

- [x] 2. 嵌入配置:查询指令模板配置键 + 模型感知默认值
  - [x] 2.1 在 `config.py` 新增配置键、模型感知指令解析与当前值读取器
    - 在 `data_foundation/config.py` 的嵌入配置键集合(`EMBEDDING_CONFIG_KEYS` 或等价结构)追加 `XHS_EMBEDDING_QUERY_INSTRUCTION` 与 `XHS_EMBEDDING_RELEVANCE_FLOOR`,均归属 `XHS_EMBEDDING_*` 族以支持配置中心热重载
    - 定义 `_DEFAULT_QUERY_INSTRUCTION`(含 `{query}` 占位符)与 `_model_aware_query_instruction(model, explicit)`:显式配置优先;否则模型名含 `qwen3-embedding`(大小写不敏感)→ 默认模板;其他模型 → `None`
    - 实现**当前值读取器**(读当前配置中心/env,非历史回放):`current_query_instruction()` 返回当前显式 `XHS_EMBEDDING_QUERY_INSTRUCTION`(可为 None);`current_relevance_floor()` 解析 `XHS_EMBEDDING_RELEVANCE_FLOOR`,未配置回退 `DEFAULT_RELEVANCE_FLOOR`
    - 在配置解析层校验:若显式指令模板不含 `{query}` 占位符则拒绝
    - 保持向量维度常量为 1536 不变
    - _Requirements: 1.4, 1.5, 1.6, 1.7, 1.8, 1.9, 3.1, 3.8, 5.1_

  - [x]* 2.2 为 `config.py` 指令解析、默认值与当前值读取器编写单元测试
    - 验证显式配置优先、Qwen3 命中默认模板、非 Qwen3 返回 None、缺 `{query}` 占位符被拒绝、热重载归属正确
    - 验证 `current_relevance_floor()` 已配置/未配置(回退默认)、`current_query_instruction()` 读当前显式值
    - _Requirements: 1.4, 1.5, 1.6, 1.8, 3.1_

  - [x] 2.3 确认 `embedding.py` 不引入检索期策略字段、文档端不受影响
    - **不**给 `EmbeddingProviderConfig` 增加 `query_instruction`/`relevance_floor` 字段(检索期策略在查询路径解析,见 task 5.1);`embedding_config_from_snapshot` 保持纯快照函数、不读当前配置
    - 确认文档端 `EmbeddingProcessor._embed` 行为不变,仍发送裸文本
    - _Requirements: 1.3, 5.3_

  - [x]* 2.4 为 `embedding.py` 文档端裸文本编写单元测试
    - 验证 `EmbeddingProcessor._embed` 发送裸文本,不含指令前缀
    - 验证 `embedding_config_from_snapshot` 未新增检索期策略字段、行为不变
    - _Requirements: 1.3, 5.3_

- [ ] 3. 检查点 — 底层常量与配置就绪
  - Ensure all tests pass, ask the user if questions arise.

- [x] 4. 查询端:`_embed_query` 模型感知注入指令前缀
  - [x] 4.1 修改 `tools.py::_embed_query` 接受并注入指令前缀参数
    - 将签名改为 `_embed_query(query, *, config, query_instruction: str | None)`;`query_instruction` 非空时发送文本为 `query_instruction.format(query=query)`,否则发送原始裸文本
    - `_embed_query` **不自行读配置**决定指令(避免历史回放污染),指令由调用方(task 5.1)解析后传入
    - 保持向量校验逻辑(1536 维有限浮点),401/403 → `EmbeddingSearchUnavailable("EMBEDDING_QUERY_UNAUTHORIZED")`
    - 确保 `query_instruction` 模板与 `api_key` 不写入日志/错误摘要/遥测
    - _Requirements: 1.1, 1.2, 4.2, 5.2, 6.6_

  - [x]* 4.2 为 `_embed_query` 编写单元测试
    - 断言传入指令模板时发送给 provider 的 `input` 文本含前缀;传入 None 时为裸文本
    - 断言 401/403 抛 `EmbeddingSearchUnavailable("EMBEDDING_QUERY_UNAUTHORIZED")`
    - 断言日志/错误摘要中不含模板与 `api_key`
    - _Requirements: 1.1, 1.2, 4.2, 6.6_

- [x] 5. 工具编排:绝对相关度闸门 + `insufficient_relevance` 返回态 + 口径传参
  - [x] 5.1 在 `semantic_search_resources` 解析检索期策略并实现绝对相关度闸门与新返回态
    - 在 `data_foundation/tools.py::semantic_search_resources` 中,取得 `query_config = _embedding_query_config_for_index(active_index)`(历史回放:model/dims/key)后,从**当前**配置解析检索期策略:
      - `query_instruction = _model_aware_query_instruction(model=query_config.model, explicit=current_query_instruction())`(模型名取 active index 判定 Qwen3,显式覆盖取当前配置)
      - `floor = current_relevance_floor()`(当前配置;**不**从历史回放 config 取)
    - 调用 `_embed_query(query, config=query_config, query_instruction=query_instruction)` 取查询向量
    - 语义检索成功后、调用 `rank_evidence` **之前**,基于原始绝对余弦计算 `top_score = max(score, default=0.0)`
    - `top_score < floor`(含结果集为空)→ 返回 `{"ok": True, "mode": "insufficient_relevance", "results": [], "top_score": round(top_score,4), "threshold": floor}`,且不降级到 BM25
    - `top_score >= floor` → 调用 `rank_evidence(..., score_kind="cosine")`,返回 `{"ok": True, "mode": "semantic", "results": ranked}`
    - _Requirements: 1.9, 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.8_

  - [x] 5.2 在 `search_resources` 内部 `rank_evidence` 调用传 `score_kind="bm25"` 并验证 BM25 分数有效
    - **目标点是 `data_foundation/tools.py::search_resources` 内部那次 `rank_evidence(...)` 调用(真实 BM25 入排序点),而非 `_fulltext_fallback` 包装层**——`_fulltext_fallback` 仅转调 `search_resources.func(...)`,不直接调 `rank_evidence`
    - 将该调用改为显式 `rank_evidence(..., score_kind="bm25")`
    - **先验证全文路径的 score 来源**:确认 `search_resources` 经 Meilisearch + `readable_rows_by_ids` 后,传入 `rank_evidence` 的每条结果带有意义的 BM25 相关度分数;若实际是 0/占位(归一化无效),修正分数来源(如让 Meili 检索返回 `_rankingScore` 并贯通到 `_rows_to_payload`),而非对全 0 分数做空归一化
    - 复核所有降级分支(无 active 索引、401/403、HTTP 异常、向量校验失败、空查询)返回 `keyword_fallback` 且 BM25 分数不与 `relevance_floor` 比较
    - 确保 active 索引 / `embedding_indexes` 内容不被修改
    - _Requirements: 2.9, 2.10, 4.1, 4.3, 4.4, 4.5, 4.6, 5.4_

  - [x] 5.3 复核 `search.py::semantic_search` 返回绝对余弦
    - 在 `data_foundation/search.py` 复核 `semantic_search` 返回的是绝对余弦相似度(`1 - (embedding <=> vector)`);预期仅补充注释、无逻辑改动
    - 若发现与设计不符则记录并修正,否则仅以注释明确口径
    - _Requirements: 3.2, 5.4_

  - [x] 5.4 更新提示词消费方解读 `insufficient_relevance` 返回态
    - `prompts.py` 主控提示词:描述 `semantic_search_resources` 三种 `mode`,并指示 `insufficient_relevance` 时明确回复"当前数据不足"、建议同步/补充数据、不编造来源、不擅自降级
    - `.agents/skills/topic-content/SKILL.md`:在检索顺序/数据不足处补充 `insufficient_relevance` 的处理(对齐既有"当前数据不足"措辞)
    - `subagents_executor.py` 的 `knowledge-atom-retriever` 子代理提示词:识别 `insufficient_relevance`(不再仅凭 `keyword_fallback`),在该态下报告 `gaps` 而非强行补召回
    - 纯提示词文案改动,不改工具签名;确保不指示在该态下回退关键词凑依据
    - _Requirements: 7.1, 7.2, 7.3, 7.4_

- [ ] 6. 检查点 — 查询端与工具编排就绪
  - Ensure all tests pass, ask the user if questions arise.

- [x] 7. 测试重写(不做兼容)
  - [x] 7.1 重写 `tests/data_foundation/test_search_ranker.py`
    - 删除旧的 `relevance == 1.0`(0.9/0.9 归一化)断言
    - 新增:`score_kind="cosine"` 时 relevance 等于绝对余弦(如 score=0.46 → relevance≈0.46,非 1.0)
    - 新增:`score_kind="bm25"` 时保留候选集内归一化行为
    - 更新权重断言为新配比 0.70/0.15/0.10/0.05,并断言四者之和为 1.0
    - 保留:排序降序、标题模糊去重、freshness/performance 计算
    - _Requirements: 6.1, 6.2, 6.3_

  - [x] 7.2 重写 `tests/data_foundation/test_search_graph_tools.py` 相关用例
    - `test_embed_query_*`:断言 Qwen3 模型 `input` 文本含指令前缀、非 Qwen3 为裸文本
    - 新增:top 绝对余弦 < 阈值时返回 `mode=="insufficient_relevance"`、`results==[]`、携带 `top_score`/`threshold`
    - 新增:top 绝对余弦 >= 阈值时返回 `mode=="semantic"` 且 relevance 为绝对值
    - 新增:`XHS_EMBEDDING_RELEVANCE_FLOOR` 配置覆盖后,闸门按新阈值判定(取当前配置,非历史回放)
    - 新增:当前 active index 的 `config_version` 早于本功能时,Qwen3 查询仍加指令前缀(检索期策略不随历史回放)
    - 复核:各 `keyword_fallback` 降级分支不受闸门影响、BM25 走归一化
    - 断言模板/`api_key` 不入日志
    - _Requirements: 1.9, 3.8, 6.4, 6.5, 6.6_

  - [ ]* 7.3 属性测试:余弦 relevance 与候选集无关
    - **Property 2: 绝对相关度不被抹除**
    - 使用 Hypothesis 生成随机 score 列表,验证 `rank_evidence(score_kind="cosine")` 的 `rank_signals.relevance == clamp(input_score, 0, 1)`,不随候选集最大值变化
    - **Validates: Requirements 2.2, 2.4**

  - [ ]* 7.4 属性测试:闸门单调性
    - **Property 1: 数据不足必明说**
    - 使用 Hypothesis 在阈值上下边界生成 top_score,验证 top_score 单调下降越过 `Relevance_Floor` 时返回态从 `semantic` 切到 `insufficient_relevance`(单调、互斥)
    - **Validates: Requirements 3.2, 3.3, 3.5**

  - [ ]* 7.5 属性测试:口径隔离与降级语义保持
    - **Property 3: 口径隔离 / Property 6: 降级语义保持**
    - 验证 `score_kind="bm25"` 路径永不与 `Relevance_Floor` 比较;基础设施不可用仍返回 `keyword_fallback`,不被误判为 `insufficient_relevance`
    - **Validates: Requirements 2.3, 4.1, 4.6**

- [x] 8. 本地验证
  - [x] 8.1 运行数据底座测试套件
    - 执行 `uv run pytest tests/data_foundation -q`,修复任何失败用例直至全绿
    - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5_

  - [x] 8.2 在最终中文指令模板下重新标定相关度阈值
    - 用上线的 `_DEFAULT_QUERY_INSTRUCTION`(中文)而非标定期临时英文前缀,在生产/暂存语料上跑多组真实查询(相关 + 无关各若干),记录 top 绝对余弦分布
    - 据分布确定 `DEFAULT_RELEVANCE_FLOOR` 终值(或经 `XHS_EMBEDDING_RELEVANCE_FLOOR` 配置覆盖);确认相关查询不被误杀、无关查询被正确判为 `insufficient_relevance`
    - 通过只读探测脚本进行(不改服务器磁盘源码,遵循 server-deployment-rules.md)
    - 标定结果(中文模板,生产语料,10 组查询):相关 0.579~0.729、无关 0.360~0.480;0.50 落在空档中,确认为合适默认值,无需调整。
    - _Requirements: 3.7_

- [ ] 9. 交付前本地全量校验
  - Ensure all tests pass, ask the user if questions arise.
  - 复核受影响文件清单全部覆盖、无悬挂代码;确认未触动 schema(仍 1536 维)、未重嵌、未改 active 索引;部署按 `server-deployment-rules.md` 在 spec 完成后单独执行(本计划不含部署/上线任务)。

## Notes

- 标记 `*` 的子任务为可选(单元/属性/集成测试),可为更快 MVP 跳过;核心实现任务不可跳过。
- 每个任务引用具体子需求条目以保证可追溯性。
- 检查点用于增量验证,确保每一阶段产物落在已存在上游之上、无悬挂代码。
- 属性测试覆盖设计 Testing Strategy 的两个方向(余弦 relevance 与候选集无关、闸门单调性),使用 Hypothesis(dev 依赖,不进生产镜像)。
- 集成测试(真实 Postgres + pgvector)依赖 `migrated_conn` fixture,在无 `TEST_XHS_DATABASE_URL` 时跳过,按部署规则在 CI/专用 runner 补跑,故不作为独立编码任务列出。

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1", "2.1"] },
    { "id": 1, "tasks": ["2.2", "2.3"] },
    { "id": 2, "tasks": ["2.4", "4.1", "5.3"] },
    { "id": 3, "tasks": ["4.2", "5.1"] },
    { "id": 4, "tasks": ["5.2", "5.4"] },
    { "id": 5, "tasks": ["7.1", "7.2"] },
    { "id": 6, "tasks": ["7.3", "7.4", "7.5"] },
    { "id": 7, "tasks": ["8.1"] },
    { "id": 8, "tasks": ["8.2"] }
  ]
}
```
