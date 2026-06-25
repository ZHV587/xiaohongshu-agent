# Requirements Document

feishu-performance-metrics(飞书效果指标接通)

## Glossary

- **feishu_base_record**:飞书多维表格行同步进 Postgres 后的资源类型,效果列存于 `content_json.fields`。
- **performance_metric**:效果指标资源类型,`content_json` 含 `target_resource_id`/`metrics`/`score`。
- **measured_by**:从内容资源指向其效果指标的关系边(source=内容,target=metric)。
- **表白名单(NOTE_LEVEL_TABLE_IDS)**:笔记级飞书表的 table_id 集合,仅这些表的记录抽效果;排除评论级表。
- **抽取纯函数(extract_performance_metrics)**:`(table_id, table_name, fields) → metrics | None`,零 LLM、零 I/O。
- **幂等写入**:同一 target 重复处理只更新同一 metric + 单条边,不堆叠。
- **p_score / 去饱和**:`rank_evidence` 的效果分;由 `tanh(.../500)` 改对数归一化,使万级量级仍单调可区分。
- **rank_evidence**:检索重排,按 relevance/freshness/type/performance 加权(和=1,performance 权重 0.05)。

## Introduction

506 条飞书爆款的点赞/收藏/评论/转发数已躺在 `feishu_base_record.content_json.fields` 里,但从未流入 `performance_metric` 资源 / `measured_by` 边 / `rank_evidence` 效果加权。"哪些内容真的爆了"这个最强选题信号现成、完全没用起来。

本 spec 把这条链路接通:在飞书 base 行落库时(及对存量一次性回填)按**表白名单 + 列名映射**把效果列抽成既有契约的 `performance_metric` + `measured_by` 边,并修复 `rank_evidence` 的效果分在对标爆款量级(万级)下的饱和问题,让高表现内容在检索排序中真正上浮。

**范围**:b 先行——存量回填 + 同步期映射 + 效果分归一化修复。**不含**:重新启用定时调度(后续 a)、`same_author`/`shares_tag` 关系边(§8②③)、新检索引擎、重嵌入。

**铁律**:零 LLM、零新依赖、不引入 GraphRAG 框架;复用既有 `performance_metric`/`measured_by`/`rank_evidence` 契约;明文配置;根本性修复不打补丁。

## Requirements

### Requirement 1:表白名单(只认笔记级表)
**User Story:** 作为系统,我要只对笔记级飞书表抽取效果指标,以免把评论级数据误当笔记效果污染排序。

#### Acceptance Criteria
1. WHEN 处理一条 `feishu_base_record` THEN 系统 SHALL 依据其 `content_json.table_id`(优先)或 `table_name` 判断是否属于笔记级表白名单。
2. IF 记录所属表不在白名单(如 💬评论采集库 `tblZgH0SF0AfYIpV`)THEN 系统 SHALL 跳过该记录、不生成任何 `performance_metric` 或 `measured_by` 边。
3. THE 白名单 SHALL 以**明文可配置**的表 id 集合实现(按 table_id 精确匹配,不依赖易变的中文表名)。
4. WHERE 一条记录所属表在白名单内但缺少全部效果列 THE 系统 SHALL 跳过该记录而非报错。

### Requirement 2:列名映射(容缺、零 LLM)
**User Story:** 作为系统,我要把飞书结构化效果列按可配置映射转成标准 metrics,容忍列缺失与列名差异。

#### Acceptance Criteria
1. THE 系统 SHALL 提供**明文可配置**的列名→metric 映射(点赞数→likes、收藏数→collects、评论数→comments、转发数→shares、播放量→views)。
2. WHEN 某 metric 对应的列在 `fields` 中存在且可解析为非负有限数值 THEN 系统 SHALL 采用该值。
3. IF 某列缺失、为空、或非数值 THEN 系统 SHALL 跳过该 metric(不写 0 占位、不报错)。
4. WHEN 抽取后至少有一个受支持 metric THEN 系统 SHALL 生成效果指标;IF 一个都没有 THEN 系统 SHALL 跳过该记录。
5. THE 抽取过程 SHALL 为纯函数(无 I/O、无 LLM),仅依据 `(table_id, table_name, fields)` 决定产物。

### Requirement 3:幂等写入(re-sync 不堆叠)
**User Story:** 作为系统,我要在重复同步/回填同一条记录时更新同一效果指标,而不是堆出多条 metric 与多条边。

#### Acceptance Criteria
1. WHEN 对某 `feishu_base_record`(target)写入效果指标且该 target 已存在 `performance_metric` THEN 系统 SHALL 复用同一 metric 资源(原地更新 metrics/score),不新建第二条。
2. THE 同一 target 与其 metric 之间 SHALL 恒为**单条** `measured_by` 边。
3. WHEN 飞书侧效果数值变化后重新处理同一记录 THEN 系统 SHALL 用新值覆盖旧 metrics,并相应更新边 `weight`。
4. THE 幂等性 SHALL 不依赖调用次数;对同一记录处理 N 次的最终库状态与处理 1 次一致(metric 条数、边条数)。

### Requirement 4:存量回填
**User Story:** 作为运营,我要把现有 506 条飞书记录里白名单表的效果一次性接通,立刻拿到选题精度收益。

#### Acceptance Criteria
1. THE 系统 SHALL 提供一个一次性回填入口(脚本),遍历现有 `feishu_base_record`、按 R1/R2 抽取、按 R3 幂等写入。
2. WHEN 回填执行 THEN 系统 SHALL 输出处理统计(扫描数、命中白名单数、写入 metric 数、跳过数、错误数)。
3. THE 回填 SHALL 可重复执行(幂等),重跑不产生重复 metric/边。
4. IF 单条记录处理失败 THEN 系统 SHALL 记录错误并继续处理其余记录(不整体中断)。
5. THE 回填 SHALL 在生产以只读探测先核对命中量,再实际写入(遵循部署规则,不在源码插诊断代码)。

### Requirement 5:同步期接通(未来新数据自动接通)
**User Story:** 作为系统,我要让 `sync_base_rows` 落库白名单表记录时自动抽取效果指标,使后续同步无需再回填。

#### Acceptance Criteria
1. WHEN `sync_base_rows` 落库一条白名单表记录且抽出 metrics THEN 系统 SHALL 在同一逻辑流程内按 R3 幂等写入 `performance_metric` + `measured_by`。
2. IF 抽取无 metrics 或表不在白名单 THEN `sync_base_rows` SHALL 仅落库 `feishu_base_record`(保持现有行为不变)。
3. IF 效果指标写入失败 THEN 系统 SHALL 不阻断 `feishu_base_record` 本身的落库(记录错误,base record 仍入库)。
4. THE 同步期映射与回填 SHALL 复用同一抽取纯函数与同一幂等写入路径(单一事实源,不两处实现)。

### Requirement 6:排序效果分去饱和(rank_evidence 根本性修复)
**User Story:** 作为创作者,我要让"更爆"的对标在相关度相近时排得更靠前,而不是所有爆款效果分都饱和成同一个值。

#### Acceptance Criteria
1. WHEN 候选含带效果指标的对标爆款 THEN `rank_evidence` 的效果分 SHALL 在对标量级(点赞/收藏 10²~10⁶)区间保持**单调可区分**,不在万级即饱和到同一上界。
2. THE 效果分 SHALL 仍归一化到有界区间 [0, 1],不破坏 `WEIGHT_*` 之和为 1 的加权结构。
3. WHEN 两条候选相关度与时效相近、效果指标量级差一个数量级 THEN 排序 SHALL 体现该差异(更高指标者得分更高)。
4. WHERE 候选无效果指标(`performance_data` 为空)THE 效果分 SHALL 为 0(与现状一致)。
5. THE 修复 SHALL 仅调整效果分的归一化口径,不改动 relevance/freshness/type 三项的既有口径。

### Requirement 7:可见性与权限
**User Story:** 作为系统,我要让效果指标继承目标记录的可见性与归属,回填以系统身份执行而不卡在对话用户权限。

#### Acceptance Criteria
1. WHEN 生成 `performance_metric` THEN 其 `visibility`/`owner_open_id` SHALL 继承目标 `feishu_base_record`。
2. THE 回填 SHALL 以记录归属/管理员身份执行,不要求对话用户对该记录有写权限。
3. THE 既有面向 agent 的 `save_performance_metric` 工具语义(用户发布后回填)SHALL 不被破坏。

### Requirement 8:契约与回归不破
**User Story:** 作为维护者,我要确保接通不破坏既有检索/排序/前端契约。

#### Acceptance Criteria
1. THE `measured_by` 边语义(source=内容,target=metric)与 `bulk_performance_metrics` 消费 SHALL 保持不变。
2. THE `performance_metric` 的 `content_json` 结构(`target_resource_id`/`metrics`/`score`)SHALL 与既有读取路径兼容。
3. WHEN 接通后跑全量测试 THEN 既有套件 SHALL 全绿;新增能力 SHALL 有对应测试(映射纯函数、幂等、效果分单调性、回填统计)。
4. THE 改动 SHALL 不涉及 schema 迁移、重嵌入、新外部服务。
