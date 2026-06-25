# Implementation Plan: retrieval-flow-consolidation(检索流程收敛与职责统一)

## Overview

本计划把 `design.md` 的纯结构重构拆为可增量执行、每步可验证的编码任务。**不改相关性算法**(已上线),只动 EvidencePackage schema、prompts.py、四个创作 SKILL.md、subagents_executor.py 及相关测试。

依赖链:先建 `EvidencePackage` 契约(被 prompts/子代理/测试引用)→ 再收《检索与证据规约》入 prompts.py(唯一事实源)→ 子代理收敛(移除 thin + 加 response_format)→ 四技能去重 → 测试重写 → 本地验证。带 `*` 子任务为可选测试。

受影响文件见 design.md「受影响文件清单」。

## Tasks

- [x] 1. EvidencePackage 证据契约(被后续引用,最先建)
  - [x] 1.1 新增 `data_foundation/evidence.py` 定义 `EvidenceItem` / `EvidencePackage`
    - 按 design.md Data Models 定义两个 `pydantic.BaseModel`;`RetrievalMode = Literal["semantic","keyword_fallback","insufficient_relevance"]`
    - `EvidenceItem` 字段:`resource_id/title/summary/source_updated_at/indexed_at/score/why_selected`(**用 `why_selected`,不引入 why_relevant**)
    - `EvidencePackage` 字段:`retrieval_mode` / `evidence: list[EvidenceItem]` / `gaps: str | None`
    - 实现校验:`insufficient_relevance` ⟹ `evidence == []` 且 `gaps` 非空;时效字段恒为字符串(未知写"未知")
    - 不新增第三方依赖(pydantic 已由 deepagents 传递依赖)
    - _Requirements: 5.1, 5.2, 4.1, 4.2, 4.3, 4.4, 3.1_

  - [x]* 1.2 新增 `tests/data_foundation/test_evidence_package.py`
    - 形状测试:合法/非法 dict 构造;非法 `retrieval_mode` 抛 ValidationError
    - 不变量测试(Hypothesis):`insufficient_relevance ⟺ (evidence==[] ∧ gaps≠None)`;时效字段恒为字符串;round-trip 字段稳定
    - _Requirements: 3.1, 4.1, 4.2, 5.1_

- [x] 2. 检查点 — 契约就绪
  - Ensure all tests pass, ask the user if questions arise.

- [x] 3. prompts.py:唯一事实源 + 职责边界收敛
  - [x] 3.1 在 `prompts.py` 新增/收敛《检索与证据规约》节(唯一事实源)
    - 写入统一检索顺序(语义优先→关键词补充→精读 top-N→条件触发 graph_expand→产出 EvidencePackage)
    - 写入 mode 三态处理(semantic 正常用 / insufficient_relevance 明说数据不足不降级不编造 / keyword_fallback 可用但标注降级)
    - 写入 EvidencePackage 字段、时效防伪(source_updated_at vs indexed_at、未知写"未知"、不以 updated_at 替代)
    - 写入轻/重委派决策点(先轻量语义检索,拿候选后评估;少量精读内联,大量精读才委派 knowledge-atom-retriever)
    - 飞书是上游补给:创作只检索 Postgres,数据不足才 sync_feishu_resources
    - **规约文本写精炼**(控制常驻 token 开销)
    - _Requirements: 1.1, 1.2, 2.1, 2.2, 2.3, 2.4, 2.5, 3.2, 3.3, 4.1, 4.4, 9.1, 9.2, 9.3, 9.4, 9.5_

  - [x] 3.2 收敛 prompts.py §1 枚举与 §3 委派规则(移除 thin 子代理引用)
    - **§1"可用执行型 subagent"枚举**:删除 `topic-generator`/`copy-generator`/`state-manager` 三行,仅留 `knowledge-atom-retriever`、`persona-distiller`(防悬挂引用)
    - **§3 委派规则**:删除对三者的委派条目;明确"主控自己调 `save_generated_topic`/`save_generated_copy`/`save_session_snapshot` + 对应 `sync_*_to_feishu`"
    - 全文确认无对三者的残留点名
    - _Requirements: 7.4, 7.5, 7.6, 8.1, 8.3_

- [x] 4. subagents_executor.py:子代理收敛 + response_format
  - [x] 4.1 移除三个 thin 持久化子代理工厂
    - 删除 `build_topic_generator`/`build_copy_generator`/`build_state_manager`
    - `EXECUTOR_SUBAGENT_NAMES` 收敛为 `{"knowledge-atom-retriever", "persona-distiller"}`
    - `build_executor_subagents` 仅返回 knowledge-atom-retriever + persona-distiller
    - _Requirements: 7.1, 7.2, 7.3_

  - [x] 4.2 knowledge-atom-retriever 加 response_format + 引用规约
    - 子代理 dict 增加 `"response_format": EvidencePackage`(import from data_foundation.evidence)
    - system_prompt 引用同一《检索与证据规约》口径(不再内联完整检索口径副本),返回态识别 insufficient_relevance
    - _Requirements: 6.1, 6.2, 6.3, 6.4_

- [x] 5. 检查点 — 提示词与子代理就绪
  - Ensure all tests pass, ask the user if questions arise.

- [x] 6. 四个创作技能去重(引用规约,保留差异化工作流)
  - [x] 6.1 `topic-content/SKILL.md`:删"工具边界与检索顺序"整节及 mode/防伪重述,改引用主控规约
    - 保留:方向→出选题卡→停下等用户选→写文案两步流、质量检查清单、落库同步主控直调
    - _Requirements: 1.3, 1.4, 1.5, 8.1_

  - [x] 6.2 `xhs-benchmark/SKILL.md`:Phase 1 检索清单改引用规约
    - 保留:五重漏斗去噪、行级拆解、可复用规律总结
    - _Requirements: 1.3, 1.4, 1.5_

  - [x] 6.3 `xhs-planning/SKILL.md`:Phase 1 检索清单改引用规约
    - 保留:爆款规律提炼、选题卡装配、Phase 4 主控直调 save_generated_topic + sync_topic_to_feishu
    - _Requirements: 1.3, 1.4, 1.5, 8.1_

  - [x] 6.4 `xhs-content-system/SKILL.md`:Phase 2/3 检索清单改引用规约
    - 保留:底座审计、主题地图、内容单元结构化、选题装配、主控直调 save_*/sync_*
    - _Requirements: 1.3, 1.4, 1.5, 8.1_

- [x] 7. 测试重写(不做兼容)
  - [x] 7.1 重写 `tests/test_agent_assembly.py` 子代理断言
    - **删除/重写第 415-427 行**对 topic-generator/copy-generator/state-manager 的逐名断言
    - 改为断言:子代理恰 2 个;knowledge-atom-retriever 含 `response_format == EvidencePackage`
    - 确认 `create_deep_agent(subagents=build_executor_subagents(...))` 仍可装配
    - _Requirements: 7.1, 7.2, 10.4_

  - [x] 7.2 更新 `tests/test_subagents.py`
    - 断言收敛为 2 个子代理;移除对三个 thin 工厂的导入/断言
    - _Requirements: 7.1, 7.3, 10.5_

  - [x]* 7.3 路由契约回归 `tests/test_dbskill_alias_coverage.py`
    - 确认四技能改后仍 ≥2 个「」触发短语、无斜杠命令;prompts 无"强匹配"、无斜杠命令、点名单元真实、无对三个 thin 子代理的残留点名
    - _Requirements: 10.1, 10.2, 10.3, 7.6_

  - [x]* 7.4 弱自动化:技能正文不重述 mode(Property 1 兜底)
    - 断言四个 SKILL.md 正文不再出现 `insufficient_relevance`/`keyword_fallback` mode 字面量(规约措辞只在 prompts.py)
    - _Requirements: 1.4_

- [x] 8. 本地验证
  - [x] 8.1 运行相关测试套件
    - `uv run pytest tests/test_agent_assembly.py tests/test_subagents.py tests/test_dbskill_alias_coverage.py tests/data_foundation/test_evidence_package.py -q`,修复失败直至全绿
    - 全量回归 `uv run pytest -q` 确认无连带回归
    - _Requirements: 7.1, 10.4, 10.5, 10.6_

- [x] 9. 交付前本地全量校验
  - Ensure all tests pass, ask the user if questions arise.
  - 复核:规约只在 prompts.py 出现一次(review)、四技能差异化工作流保留(review)、无对三个 thin 子代理残留点名、未改相关性算法、无 schema 迁移/重嵌;部署按 server-deployment-rules.md 单独执行(本计划不含部署任务)。

## Notes

- 标 `*` 子任务为可选测试,核心实现任务不可跳过。
- Property 1(唯一事实源)、Requirement 9(轻/重决策点)属语义/行为级,主要靠 code review 与 eval 保证;7.4 提供弱自动化兜底。
- `data_foundation/tools.py` 的 `save_*`/`sync_*` 无需改动(本就是主控可直调工具),仅需在 6.x/3.2 确认落库链路完整。
- 部署涉及重建后端镜像让新 prompt/SKILL/subagents 生效,按 server-deployment-rules.md 在 spec 完成后单独执行。

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1"] },
    { "id": 1, "tasks": ["1.2", "3.1", "3.2", "4.1"] },
    { "id": 2, "tasks": ["4.2"] },
    { "id": 3, "tasks": ["6.1", "6.2", "6.3", "6.4"] },
    { "id": 4, "tasks": ["7.1", "7.2", "7.3", "7.4"] },
    { "id": 5, "tasks": ["8.1"] }
  ]
}
```
