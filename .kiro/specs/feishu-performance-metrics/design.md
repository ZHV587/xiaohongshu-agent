# Design: feishu-performance-metrics(飞书效果指标接通)

## Overview

把已在库的飞书爆款效果列(点赞/收藏/评论/转发/播放)接入既有 `performance_metric` + `measured_by` + `rank_evidence` 链路。链路两头已就绪——写入契约(`save_performance_metric_resource`)与排序消费(`rank_evidence` 读 `performance_data`,`WEIGHT_PERFORMANCE=0.05`)都在;断的只是中间"把 `content_json.fields` 的效果列喂进去"这一步。

四件落地物:
1. **抽取纯函数**(新 `data_foundation/feishu_metrics.py`):明文表白名单 + 列名映射,`(table_id, table_name, fields) → metrics | None`,零 LLM、零 I/O。
2. **幂等写入**:把 `save_performance_metric_resource` 改为按 target 复用既有 metric(根因修复其当前"每调一次新建一条"的非幂等)。
3. **两个接通入口复用同一路径**:存量回填脚本(b,先行)+ `sync_base_rows` 同步期映射(未来新数据自动接通)。
4. **效果分去饱和**(`rank_evidence` 根因修复):`tanh(.../500)` 对万级对标爆款全部饱和到 ≈1.0,改对数归一化,使 10²~10⁶ 量级单调可区分。

**不在范围**:重新启用定时调度(后续 a)、`same_author`/`shares_tag` 边、新引擎、重嵌入、schema 迁移。

## 现状与根因(实测)

- 生产 `feishu_base_record` 共 506 条,来自单一 base(app_token `V8Kub8gg8afB7RsllZWc4iSRnAc`),**多表聚合 21 张表**。
- 效果列分布(实测):点赞数 403、回复数/用户名/评论内容 257(=💬评论采集库)、收藏数/评论数 126、转发数/播放量 101。
- 数值形态:点赞/收藏/评论/转发为整数;播放量/回复数多为 0;话题/分类/类型为字符串数组。
- **表必须区分**:💬评论采集库(`tblZgH0SF0AfYIpV`,257 行)是**评论级**数据,其"点赞数"是评论点赞,非笔记效果 → 必须排除。笔记级效果集中在 🧲单篇采集库(`tbl24vSVeLvz45ig`,122)、📝博主笔记库(`tblXDHL8hBrUUMI2`,10)、🔥爆款搜索(`tblX58JrbsqczqPl`,3)、📊流量监测库(`tblMUqaUokINcdIK`,4)等。
- 写入路径**两条且分叉**:
  - `PerformanceRepository.save_performance(likes,comments,shares)`:幂等(按 `content_json->>'target_resource_id'` 查重复用),但 metric 集受限、score=likes+2comments+3shares。
  - `performance_feedback.save_performance_metric_resource(...)`:agent 工具路径,metric 集更全(likes/collects/comments/shares/views/conversions),但**不幂等**——每次 `upsert_resource` 无 mapping 新建 → 新 `measured_by` 边,重跑必堆叠。
- `rank_evidence` 的 `p_score` **不读** metric 的 stored score,而是从 `metrics{likes,collects,comments}` 现算 → 故接通只需 metrics 字典齐 + p_score 公式不饱和;两条写路径的 stored-score 公式分叉不影响排序。

## Architecture

```mermaid
graph TD
    subgraph 抽取(纯函数, 零LLM)
        FM["feishu_metrics.extract_performance_metrics<br/>(table_id, table_name, fields)"]
        WL[表白名单 NOTE_LEVEL_TABLE_IDS]
        CM[列名映射 COLUMN_TO_METRIC]
        FM --- WL
        FM --- CM
    end

    subgraph 入口A_存量回填["入口 A:存量回填(b,先行)"]
        BF[scripts/backfill_feishu_performance.py]
    end
    subgraph 入口B_同步期["入口 B:sync_base_rows(未来新数据)"]
        SB[sync_base_rows 落库后]
    end

    BF --> FM
    SB --> FM
    FM -->|metrics or None| IW["幂等写入<br/>save_performance_metric_resource(idempotent-by-target)"]
    IW -->|复用既有 metric| PM[(performance_metric 资源)]
    IW -->|单条边| EDGE[(measured_by 边)]

    PM --> RANK["rank_evidence<br/>p_score 对数归一化(去饱和)"]
    EDGE --> RANK
    RANK -->|高表现上浮| OUT[检索排序结果]
```

主路径:`feishu_base_record` →(白名单 + 列映射)→ metrics →(幂等写入)→ `performance_metric` + `measured_by` 边 →(去饱和 p_score)→ 排序上浮。两个入口共用抽取纯函数与幂等写入,单一事实源。

## Components and Interfaces

### Component 1:抽取纯函数(新 `data_foundation/feishu_metrics.py`)

**Purpose**:把飞书结构化效果列按明文配置转标准 metrics,容缺、零 LLM、确定性。

```python
# 明文可配置(R1.3 / R2.1):笔记级表白名单(按 table_id 精确匹配,中文表名仅注释)
NOTE_LEVEL_TABLE_IDS: frozenset[str] = frozenset({
    "tbl24vSVeLvz45ig",  # 🧲单篇采集库
    "tblXDHL8hBrUUMI2",  # 📝博主笔记库
    "tblX58JrbsqczqPl",  # 🔥爆款搜索
    "tblMUqaUokINcdIK",  # 📊流量监测库
})
# 明文排除(语义注释,实际由"不在白名单"自然排除):tblZgH0SF0AfYIpV 💬评论采集库

# 列名 → 标准 metric(R2.1)。值取 ALLOWED_METRICS 子集,与 rank_evidence 口径一致。
COLUMN_TO_METRIC: dict[str, str] = {
    "点赞数": "likes",
    "收藏数": "collects",
    "评论数": "comments",
    "转发数": "shares",
    "播放量": "views",
}

def extract_performance_metrics(
    table_id: str, table_name: str, fields: dict[str, Any]
) -> dict[str, int | float] | None:
    """纯函数。白名单外或无有效 metric → None;否则 → {metric: 非负数值}。"""
```

**行为**:
- `table_id not in NOTE_LEVEL_TABLE_IDS` → 返回 `None`(R1.2)。
- 遍历 `COLUMN_TO_METRIC`,列存在且可解析为有限非负数值才纳入;缺失/空/非数值/负数 → 跳过该 metric(R2.2/2.3)。
- 解析后 metrics 非空 → 返回;空 → `None`(R2.4)。
- 无 I/O、不读库、不调 LLM(R2.5)。

> 白名单与列映射是**明文常量**(用户坚持明文配置),后续如需扩表/改列名直接改本模块,不引入运行时配置开关。

### Component 2:幂等写入(改 `data_foundation/performance_feedback.py`)

**Purpose**:同一 target 的效果指标恒为单条 metric + 单条边;re-sync 覆盖而非堆叠。这是对 `save_performance_metric_resource` 当前非幂等的**根因修复**(顺带修好 agent 重复回填会堆叠的既有缺陷)。

**改动**:`save_performance_metric_resource` 写入前先查 target 是否已有 `performance_metric`,有则复用其 id 原地更新:

```python
def save_performance_metric_resource(repo, *, tenant_id, actor_open_id,
                                     target_resource_id, metrics, ...):
    ...
    with _unit_of_work(repo):
        target = repo.writable_resource_metadata(...)              # 既有:取 visibility/owner
        existing_id = repo.find_performance_metric_id(             # 新增:按 target 查既有 metric
            tenant_id=tenant_id, target_resource_id=target_resource_id)
        resource = repo.upsert_resource(
            resource_id=existing_id,                               # 有则更新,无则新建
            ... resource_type="performance_metric", ...)
        repo.add_edge(... edge_type="measured_by", weight=score)   # 既有:边 unique 幂等
```

- 新增仓库方法 `ResourceRepository.find_performance_metric_id(tenant_id, target_resource_id)`:`select id from resources where tenant_id=%s and type='performance_metric' and content_json->>'target_resource_id'=%s limit 1`(与 `PerformanceRepository.save_performance` 内既有查重口径一致)。
- `add_edge` 已有 `unique(tenant_id, source, target, edge_type)`:target metric id 稳定 ⟹ 边天然单条(R3.2)。
- 回填以记录 owner 身份调用,`writable_resource_metadata` 通过(R7.2);metric 继承 target 的 visibility/owner(R7.1,既有逻辑)。

> 既有 `PerformanceRepository.save_performance` 老路径不在本 spec 触动范围(metric 集受限、被 telemetry 等旧路径调用)。本 spec 统一走 `save_performance_metric_resource`,不新增第三条写路径。

### Component 3:存量回填脚本(新 `scripts/backfill_feishu_performance.py`)

**Purpose**:对现有 506 条一次性接通(b,先行,零风险验证链路)。

**流程**:
1. 连库,分页读 `type='feishu_base_record'` 资源(id、owner_open_id、content_json)。
2. 每条:`extract_performance_metrics(table_id, table_name, fields)`;`None` 则跳过。
3. 有 metrics → 以记录 owner 为 actor 调 `save_performance_metric_resource`(幂等)。
4. 累计统计:scanned / whitelisted / written / skipped_no_metric / errors,末尾打印。
5. 单条异常捕获并计入 errors,不中断整体(R4.4)。
6. 幂等:重跑不产生重复(R4.3)。

**运维**:先以只读模式(`--dry-run`)在生产核对命中量,再实际写入(R4.5);不在源码插诊断,脚本本身即受控只读/写入入口。

### Component 4:同步期接通(改 `data_foundation/feishu_sync.py::sync_base_rows`)

**Purpose**:落库白名单表记录时自动接通,未来新同步无需再回填(R5)。

**改动**:`sync_base_rows` 在 `upsert_resource` 拿到 `resource` 后:

```python
resource = repo.upsert_resource(... resource_type="feishu_base_record" ...)
imported += 1
metrics = extract_performance_metrics(table_id, table_name, fields)
if metrics:
    try:
        save_performance_metric_resource(
            repo, tenant_id=tenant_id, actor_open_id=actor_open_id,
            target_resource_id=resource.id, metrics=metrics, channel="xiaohongshu")
    except Exception as exc:               # 不阻断 base record 落库(R5.3)
        logger.warning("perf metric attach failed for %s: %s", external_id, exc)
```

- 表不在白名单或无 metrics → `extract` 返回 `None`,跳过,`sync_base_rows` 保持现状(R5.2)。
- 与回填复用同一抽取函数 + 同一写入函数(R5.4,单一事实源)。
- 效果写入失败不影响已计数的 base record 落库(R5.3)。

### Component 5:效果分去饱和(改 `data_foundation/search_ranker.py`)

**Purpose**:`tanh((likes+2collects+5comments)/500)` 对对标爆款(万级)恒饱和到 ≈1.0,爆款间无区分;改对数归一化,使 10²~10⁶ 单调可分。

**根因**:`/500` 尺度是给自发布笔记(几十~几百赞)标定的;对标爆款 engagement 动辄 10⁵~10⁶ → `tanh(很大)=1.0`,所有爆款同分。

**修复**(只改 `p_score` 归一化口径,不动 relevance/freshness/type,R6.5):

```python
# engagement 复用既有权重口径,语义不变
engagement = likes + 2 * collects + 5 * comments
# 对数归一化到 [0,1]:CAP 设为对标量级上界,单调不饱和
# log10(1+1e2)=2.0→0.33; 1e4→0.67; 1e6→1.0,跨 4 个数量级仍单调可分
P_SCORE_LOG_CAP = 1_000_000.0
p_score = min(math.log10(1.0 + engagement) / math.log10(1.0 + P_SCORE_LOG_CAP), 1.0)
```

- `engagement == 0`(无指标)→ `log10(1)=0` → `p_score=0`(R6.4,与现状一致)。
- 单调:engagement↑ ⟹ p_score↑(到 CAP 前严格单调),∈[0,1](R6.1/6.2/6.3)。
- `WEIGHT_PERFORMANCE=0.05` 与四权和=1 结构不变。
- `why_selected` 文案的"历史效果良好"阈值 `p_score>0.01` 保留。

> `P_SCORE_LOG_CAP` 为模块常量(明文)。它定的是"多大算满分效果",取 10⁶ 覆盖当前对标量级;可后续按真实分布微调,不影响结构。shares/views 当前不进 p_score(沿用既有 engagement 口径),metrics 中仍保留以备后用。

## Key Functions with Formal Specifications

### extract_performance_metrics(table_id, table_name, fields) -> dict | None
**Preconditions**:`fields` 为 dict(可空)。
**Postconditions**:
- `table_id ∉ NOTE_LEVEL_TABLE_IDS` ⟹ 返回 `None`。
- 返回非 `None` ⟹ 为非空 dict,键 ⊆ `COLUMN_TO_METRIC.values()`,值均为有限非负数。
- 纯函数:同输入恒同输出,无副作用。

### save_performance_metric_resource(...) -> dict(幂等化后)
**Preconditions**:`target_resource_id` 指向存在且 actor 可写的资源;`metrics` 至少一个受支持项。
**Postconditions**:
- 调用后该 target 恰有 1 条 `performance_metric` 与 1 条 `measured_by` 边。
- 已存在 metric ⟹ 复用其 id 原地更新 metrics/score,边 weight 更新;不新建第二条。
- 对同一 (target, 不同 metrics) 调用 N 次 ⟹ 最终 metric 条数=1、边条数=1(幂等)。

### p_score 去饱和(rank_evidence 内联)
**Preconditions**:`metrics` 提供 likes/collects/comments(缺省按 0)。
**Postconditions**:
- `p_score ∈ [0, 1]`;`engagement==0 ⟹ p_score==0`。
- `engagement₁ < engagement₂ ∧ 两者 < CAP ⟹ p_score₁ < p_score₂`(严格单调)。

## Data Models

不新增表、不改 schema。复用既有:
- `resources(type='performance_metric')`,`content_json = {target_resource_id, metrics, score, channel, ...}`。
- `resource_edges(edge_type='measured_by')`,`unique(tenant_id, source, target, edge_type)`。
- `metrics` 取值域:`{likes, collects, comments, shares, views}`(⊆ 既有 `ALLOWED_METRICS`)。

## Correctness Properties

### Property 1:白名单隔离
∀ 记录,`table_id ∉ NOTE_LEVEL_TABLE_IDS` ⟹ `extract_performance_metrics` 返回 `None` ⟹ 不产 metric/边。特别地 💬评论采集库 `tblZgH0SF0AfYIpV` 永不产效果指标。
**Validates: Requirements 1.1, 1.2, 1.3**

### Property 2:容缺映射确定性
∀ `fields`,缺列/空/非数值/负值的 metric 被跳过且不抛错;抽取为纯函数(同输入同输出)。无任何有效 metric ⟹ `None`。
**Validates: Requirements 2.2, 2.3, 2.4, 2.5**

### Property 3:写入幂等
∀ target,对其调用 `save_performance_metric_resource` N≥1 次 ⟹ 该 target 的 `performance_metric` 条数=1 ∧ `measured_by` 边条数=1;末次 metrics 覆盖先前。
**Validates: Requirements 3.1, 3.2, 3.3, 3.4**

### Property 4:回填可重入
回填脚本执行 K≥1 次 ⟹ 库内由回填产生的 metric/边集合与执行 1 次一致(幂等),且每次输出完整统计。
**Validates: Requirements 4.1, 4.2, 4.3**

### Property 5:单一抽取/写入路径
同步期接通与回填 SHALL 调用同一 `extract_performance_metrics` 与同一 `save_performance_metric_resource`;不存在第二份抽取或写入实现。
**Validates: Requirements 5.4**

### Property 6:效果分单调去饱和
∀ 候选,`p_score = log10(1+engagement)/log10(1+CAP)`(clamp [0,1]);`engagement` 在 [0, CAP) 严格单调映射到 p_score;`p_score ∈ [0,1]`。
**Validates: Requirements 6.1, 6.2, 6.3**

### Property 7:无指标零分
候选 `performance_data` 为空(engagement=0)⟹ `p_score=0`,排序退化为现状(relevance/freshness/type 三项)。
**Validates: Requirements 6.4, 6.5**

### Property 8:可见性继承
∀ 由飞书记录生成的 `performance_metric`,其 `visibility`/`owner_open_id` 等于目标 `feishu_base_record`。
**Validates: Requirements 7.1, 7.2**

### Property 9:契约不破
`measured_by` 语义、`bulk_performance_metrics` 消费、`performance_metric.content_json` 结构不变;全量测试绿;无 schema 迁移/重嵌。
**Validates: Requirements 8.1, 8.2, 8.3, 8.4**

## Error Handling

### 场景 1:单条记录字段异常
**条件**:某记录 `fields` 缺失/类型异常。**响应**:`extract` 跳过该 metric 或整条返回 `None`,不抛错。**恢复**:继续处理其余记录。

### 场景 2:回填中单条写入失败
**条件**:某 target 写 metric 时 DB 异常/权限异常。**响应**:捕获、计入 errors、继续。**恢复**:修因后重跑(幂等,不重复)。

### 场景 3:同步期效果写入失败
**条件**:`sync_base_rows` 写 metric 失败。**响应**:`warning` 日志,**不**回滚 base record 落库。**恢复**:下次同步或回填补齐(幂等)。

### 场景 4:重复处理
**条件**:回填重跑 / 同一记录再同步。**响应**:按 target 复用既有 metric 原地更新,边保持单条。**恢复**:无需,幂等即正确。

## Testing Strategy

### Unit
- **抽取纯函数**(新 `tests/data_foundation/test_feishu_metrics.py`):白名单内外、各列存在/缺失/空/非数值/负值、全缺→None、评论库 table_id→None;确定性。
- **幂等写入**(扩 `tests/data_foundation/test_performance_feedback.py`):同 target 调 2 次 → metric 条数=1、边=1、metrics 被覆盖;`find_performance_metric_id` 命中既有。
- **p_score 去饱和**(扩 `tests/data_foundation/test_search_*` 或新增):engagement=0→0;100<10⁴<10⁶ 严格递增;万级不再同分;∈[0,1];`WEIGHT_*` 和=1 不变。

### Property-Based(hypothesis)
- 抽取:任意 fields(含噪声值)→ 不抛错;输出键 ⊆ 映射值域、值非负有限。
- p_score:任意非负 engagement → ∈[0,1] 且单调不减。

### Integration
- **同步期接通**(扩 `tests/data_foundation/test_feishu_sync.py`):白名单表带效果列的 row → 落 base record + 1 metric + 1 边;非白名单/无效果列 → 仅 base record(行为不变);metric 写入异常不阻断 base record 计数。
- **回填脚本**:构造若干 base record(含白名单/评论库/无效果列)→ 跑回填 → 命中数、metric 数符合预期;重跑幂等。

### 生产验证(部署后,只读探测)
- 回填前 `--dry-run` 核对命中量(预期白名单四表约 122+10+3+4 量级,以实际为准)。
- 回填后探测 `measured_by` 边数、`performance_metric` 数;抽样 `bulk_performance_metrics` 返回非空;出选题时高表现来源上浮(人工核对几个查询)。

## 受影响文件清单

| 文件 | 改动 | 类型 |
|---|---|---|
| `data_foundation/feishu_metrics.py` | 新增:白名单 + 列映射 + `extract_performance_metrics` 纯函数 | 新增 |
| `data_foundation/performance_feedback.py` | `save_performance_metric_resource` 幂等化(按 target 复用既有 metric) | 改 |
| `data_foundation/repositories/resource.py` | 新增 `find_performance_metric_id(tenant_id, target_resource_id)` | 改 |
| `data_foundation/feishu_sync.py` | `sync_base_rows` 落库后接抽取+幂等写入(白名单表) | 改 |
| `data_foundation/search_ranker.py` | `p_score` 由 `tanh/500` 改对数归一化(去饱和),新增 `P_SCORE_LOG_CAP` 常量 | 改 |
| `scripts/backfill_feishu_performance.py` | 新增:存量回填(支持 --dry-run、统计、幂等) | 新增 |
| `tests/data_foundation/test_feishu_metrics.py` | 新增:抽取纯函数单元+属性测试 | 新增 |
| `tests/data_foundation/test_performance_feedback.py` | 扩:幂等(同 target N 次=1 条) | 改 |
| `tests/data_foundation/test_feishu_sync.py` | 扩:同步期接通 + 非阻断 | 改 |
| `tests/data_foundation/test_search_ranker_performance.py` | 新增:p_score 去饱和单调性 | 新增 |

## Dependencies

- 复用:既有 `performance_metric`/`measured_by`/`rank_evidence`/`bulk_performance_metrics` 契约,`upsert_resource` 幂等机制。
- **无新增第三方依赖**;零 LLM;无 schema 迁移、无重嵌入、无新外部服务。
- 部署:改 ingest 映射 + 排序常量属运行时变更,需重建后端镜像;存量回填为一次性脚本,按 server-deployment-rules.md 在生产以受控只读→写入执行。

## 范围外(后续主线)

- **a:重新启用定时调度**(`sync_sources.enabled=true` + 合理周期 + loader 跑通核验),让内容/效果持续刷新。
- **§8②③**:`same_author`(博主)、`shares_tag`/`shares_category`(话题/分类标签数组)关系边,供 `graph_expand` 返回衍生/同源邻域。
- p_score 的 `CAP`/权重按真实分布精调;shares/views 是否纳入 engagement。
