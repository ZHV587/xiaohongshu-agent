# Implementation Plan: feishu-performance-metrics(飞书效果指标接通)

## Overview

把 design.md 拆为可增量执行、每步可验证的编码任务。依赖链:先建抽取纯函数(被回填/同步两入口引用)→ 幂等写入根因修复 → 两入口接通(回填先行 + 同步期)→ 效果分去饱和 → 测试 → 本地验证。带 `*` 为可选测试。受影响文件见 design.md「受影响文件清单」。

不改 schema、不重嵌、零 LLM、零新依赖;复用既有 `performance_metric`/`measured_by`/`rank_evidence` 契约。

## Tasks

- [x] 1. 抽取纯函数(被两入口引用,最先建)
  - [x] 1.1 新增 `data_foundation/feishu_metrics.py`
    - 明文常量 `NOTE_LEVEL_TABLE_IDS`(笔记级表 id 白名单,中文表名注释)与 `COLUMN_TO_METRIC`(点赞数→likes/收藏数→collects/评论数→comments/转发数→shares/播放量→views)
    - `extract_performance_metrics(table_id, table_name, fields) -> dict | None`:白名单外→None;遍历列映射,存在且有限非负数才纳入,缺失/空/非数值/负值跳过;无有效 metric→None;纯函数无 I/O 无 LLM
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 2.1, 2.2, 2.3, 2.4, 2.5_

  - [x]* 1.2 新增 `tests/data_foundation/test_feishu_metrics.py`
    - 形状:白名单内含各列、缺列、空值、非数值、负值、全缺→None、评论库 `tblZgH0SF0AfYIpV`→None
    - 属性(hypothesis):任意 fields 不抛错;输出键 ⊆ 映射值域、值非负有限;确定性
    - _Requirements: 1.2, 2.2, 2.3, 2.4, 2.5_

- [x] 2. 检查点 — 抽取就绪
  - Ensure all tests pass, ask the user if questions arise.

- [x] 3. 幂等写入(根因修复)
  - [x] 3.1 `ResourceRepository.find_performance_metric_id(tenant_id, target_resource_id)`
    - `select id from resources where tenant_id=%s and type='performance_metric' and content_json->>'target_resource_id'=%s limit 1`,无则 None
    - _Requirements: 3.1_

  - [x] 3.2 `save_performance_metric_resource` 幂等化
    - 写入前查 `find_performance_metric_id`,命中则把其 id 传给 `upsert_resource`(原地更新),否则新建
    - 复用既有 `writable_resource_metadata` 取 visibility/owner;`add_edge`(measured_by)凭 unique 约束保持单条
    - 同一 target 调用 N 次 ⟹ metric 条数=1、边=1、metrics 被末次覆盖
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 7.1, 7.2, 7.3_

  - [x]* 3.3 扩 `tests/data_foundation/test_performance_feedback.py`
    - 同 target 调 2 次(不同 metrics)→ metric 条数=1、边=1、metrics 覆盖;visibility/owner 继承 target
    - _Requirements: 3.1, 3.2, 3.3, 8.1, 8.2_

- [x] 4. 效果分去饱和(rank_evidence 根因修复)
  - [x] 4.1 `search_ranker.py` p_score 改对数归一化
    - 新增常量 `P_SCORE_LOG_CAP = 1_000_000.0`;`engagement = likes + 2*collects + 5*comments`;`p_score = min(log10(1+engagement)/log10(1+CAP), 1.0)`
    - engagement=0→0;∈[0,1];不动 relevance/freshness/type 口径与 `WEIGHT_*`(和=1)
    - 保留 `why_selected` 的 `p_score>0.01` 文案阈值
    - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5_

  - [x]* 4.2 新增 `tests/data_foundation/test_search_ranker_performance.py`
    - engagement=0→0;100<10⁴<10⁶ p_score 严格递增;万级不再同分;∈[0,1];权重和=1 不变
    - 属性(hypothesis):任意非负 engagement → ∈[0,1] 且单调不减
    - _Requirements: 6.1, 6.2, 6.3, 6.4_

- [x] 5. 检查点 — 写入与排序就绪
  - Ensure all tests pass, ask the user if questions arise.

- [x] 6. 两入口接通(复用同一抽取+写入)
  - [x] 6.1 同步期接通:`feishu_sync.py::sync_base_rows`
    - `upsert_resource` 拿到 resource 后,`extract_performance_metrics(table_id, table_name, fields)`;有 metrics 则 `save_performance_metric_resource(target=resource.id, metrics=...)`
    - 写入异常仅 `warning`,不阻断 base record 落库与计数;表外/无 metrics 行为不变
    - _Requirements: 5.1, 5.2, 5.3, 5.4_

  - [x]* 6.2 扩 `tests/data_foundation/test_feishu_sync.py`
    - 白名单表带效果列 row → 落 base record + 1 metric + 1 边;非白名单/无效果列 → 仅 base record;metric 写入异常不阻断 base record 计数
    - _Requirements: 5.1, 5.2, 5.3_

  - [x] 6.3 存量回填脚本 `scripts/backfill_feishu_performance.py`
    - 分页读 `type='feishu_base_record'`(id/owner_open_id/content_json);逐条抽取→有 metrics 则以记录 owner 为 actor 幂等写入
    - 支持 `--dry-run`(只统计不写);输出 scanned/whitelisted/written/skipped/errors;单条异常计入 errors 不中断;重跑幂等
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5_

- [x] 7. 本地验证
  - [x] 7.1 运行相关测试套件 + 全量回归
    - `uv run pytest tests/data_foundation/test_feishu_metrics.py tests/data_foundation/test_performance_feedback.py tests/data_foundation/test_feishu_sync.py tests/data_foundation/test_search_ranker_performance.py -q`,修复至全绿
    - 全量 `uv run pytest -q` 确认无连带回归(既有契约不破)
    - _Requirements: 8.3, 8.4_

- [x] 8. 交付前本地全量校验
  - Ensure all tests pass, ask the user if questions arise.
  - 复核:抽取/写入单一事实源(两入口共用)、幂等(重跑不堆叠)、p_score 去饱和且 ∈[0,1]、白名单排除评论库、无 schema 迁移/重嵌。
  - 部署与生产存量回填(--dry-run 核对命中量 → 实际写入 → 探测边/metric 数 + 抽样排序上浮)按 server-deployment-rules.md 在 spec 完成后单独执行,本计划不含部署任务。

## Notes

- 标 `*` 子任务为可选测试,核心实现不可跳过。
- Property 5(单一抽取/写入路径)、Property 9(契约不破)主要靠 code review + 全量回归保证。
- 范围外(后续主线):重新启用定时调度(a)、`same_author`/`shares_tag` 关系边(§8②③)、`P_SCORE_LOG_CAP`/权重按真实分布精调。

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1"] },
    { "id": 1, "tasks": ["1.2", "3.1", "4.1"] },
    { "id": 2, "tasks": ["3.2", "4.2"] },
    { "id": 3, "tasks": ["3.3", "6.1", "6.3"] },
    { "id": 4, "tasks": ["6.2"] },
    { "id": 5, "tasks": ["7.1"] }
  ]
}
```
