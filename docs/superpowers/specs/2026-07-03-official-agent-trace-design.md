# 官方扩展式 Agent 执行链设计

- 日期: 2026-07-03
- 状态: 已按用户反馈移除 fallback, 待用户复核
- 范围: LangGraph/DeepAgents 后端执行事件, Web 执行链 UI, 生产持久化审计
- 替代/升级: `2026-07-01-thinking-trace-ui-design.md` 的前端派生方案, `2026-07-01-thinking-trace-layer2-reasoning-design.md` 的模型推理展示方案

## 1. 背景

当前生产思考链已经能从 LangGraph `messages` 里派生工具调用步骤, 并在 UI 中显示为「工作轨迹」。这解决了第一层可见性问题, 但仍有三个不足:

1. 数据来源仍以 `messages` 派生为主, 只能推断工具调用, 不能稳定表达命中数、筛选数、耗时、重试、子任务阶段。
2. UI 只能展示简化步骤和工具日志, 还不是完整的生产审计链。
3. 用户明确要求: 必须按 LangGraph / DeepAgents 官方支持的扩展方式, 一次性做到位, 不能靠补丁式前端猜测。

因此新方案不再把“思考链”理解为模型原始 chain-of-thought, 而定义为**生产可审计执行链**: 展示 Agent 做了什么、为什么可信、用了哪些工具、拿到什么结果、哪里失败或降级。原始模型私有思考不展示。

## 2. 官方依据

实现必须只使用公开扩展点:

- LangGraph 官方 stream modes: `values`, `updates`, `messages`, `custom`, `tasks`, `debug`; 新应用官方也推荐 typed event streaming。参考: https://docs.langchain.com/oss/python/langgraph/streaming
- LangChain/LangGraph 工具内自定义进度事件: `get_stream_writer()` 可在工具执行期间写出 `custom` stream 数据。参考: https://docs.langchain.com/oss/python/langchain/streaming
- LangGraph SDK / Agent Server 支持多模式 thread streaming、断线恢复、subgraph streaming。参考: https://docs.langchain.com/langsmith/streaming
- DeepAgents 是基于 LangGraph runtime 的 agent harness, 官方能力包括工具、子 Agent、任务规划、文件系统、上下文管理、人审中断。参考: https://docs.langchain.com/oss/python/deepagents/overview 和 https://github.com/langchain-ai/deepagents

约束:

- 不 fork DeepAgents。
- 不 monkey patch LangGraph/DeepAgents 私有函数。
- 不解析容器日志来生成 UI。
- 不依赖 DOM 或前端启发式猜测作为主数据源。
- `debug` stream mode 只允许本地或受控 debug, 生产默认不暴露。

## 3. 目标与非目标

### 目标

1. 建立统一 `xhs.trace.*` 事件协议, 覆盖对话生成链路, 并预留保存、飞书同步、排期、回填、配置检测等 Agent 动作。
2. 前端从官方 stream modes 消费结构化事件, 不再只从 `messages` 猜步骤。
3. UI 做两层结构:
   - 默认层: 普通用户看阶段摘要。
   - 展开层: 管理员/高级用户看工具详情、结果摘要、耗时、重试、错误。
4. 生产严格脱敏, 不展示原始 chain-of-thought、完整 prompt、token、secret、写入 payload。
5. trace 关键事件持久化, 历史会话可重建执行链。
6. 官方 trace 事件是唯一生产执行链数据源; 如果工具未发 trace, 视为实现缺陷, 不用 `messages` 派生补齐。
7. 普通用户界面必须使用自然中文, 不能把 `Agent` / `trace` / `run` / `tool` / `debug` / `payload` 等技术词直接展示给用户。

### 非目标

- 不展示模型原始 chain-of-thought。
- 不把 `debug` stream 直接开放给生产用户。
- 不在第一版重写 DeepAgents task/subagent 内部调度。
- 不为移动端做适配; 当前用户已确认优先 Web 端。

## 4. 总体架构

```
用户提交
  -> LangGraph / DeepAgents run
    -> values/messages 保持现有状态与回答
    -> custom 发送 xhs.trace.* 产品事件
    -> tasks 发送图任务/子任务状态
    -> 后端 trace sink 持久化关键事件
  -> Web StreamProvider 消费多模式流
  -> TraceStore 聚合事件
  -> TracePresentationAdapter 转成用户可读中文
  -> CreationScreen / WorkbenchShell 渲染执行链
```

### 4.1 实时流

前端提交从当前:

```ts
streamMode: ["values"]
```

升级为:

```ts
streamMode: ["values", "messages", "custom", "tasks"]
streamSubgraphs: true
streamResumable: true
```

说明:

- `values`: 保留当前消息、选题卡、文案块解析。
- `messages`: 保留 token/回答流能力, 后续可减少 values 快照压力。
- `custom`: 承载 `xhs.trace.*` 结构化执行链事件。
- `tasks`: 展示 LangGraph 节点/任务/子图状态, 用于子 Agent 或长任务阶段提示。
- `debug`: 不进生产默认流; 仅本地受控开关。

### 4.2 事件写出

后端工具使用官方 `get_stream_writer()` 写出 custom event。工具可直接写, 也可通过统一 helper:

```python
emit_trace({
    "type": "xhs.trace.tool.started",
    "schema_version": 1,
    "event_id": "...",
    "trace_id": "...",
    "run_id": "...",
    "turn_id": "...",
    "seq": 3,
    "stage_id": "retrieve",
    "tool_name": "semantic_search_resources",
    "label": "按语义找相关素材",
    "visibility": "user",
    "summary": "正在按语义查找相关素材",
})
```

helper 内部做:

- `get_stream_writer()` 存在时发送 custom event。
- 同步写入 trace sink, 用于历史恢复。
- 脱敏与字段白名单。
- 不在非 LangGraph 执行上下文中硬失败; 本地单测可返回 no-op writer。

### 4.3 持久化

新增 trace 事件表或复用现有数据底座 schema 中的审计表。推荐新表:

`agent_trace_events`

字段:

- `id uuid primary key`
- `event_id text not null unique`
- `tenant_id text not null`
- `thread_id text`
- `run_id text not null`
- `turn_id text not null`
- `trace_id text not null`
- `seq int not null`
- `event_type text not null`
- `schema_version int not null default 1`
- `stage_id text`
- `tool_call_id text`
- `tool_name text`
- `attempt int`
- `label text`
- `visibility text`
- `status text`
- `summary text`
- `metrics jsonb`
- `safe_args jsonb`
- `safe_result jsonb`
- `error_code text`
- `error_message text`
- `started_at timestamptz`
- `ended_at timestamptz`
- `duration_ms int`
- `created_at timestamptz not null default now()`

索引:

- `(tenant_id, thread_id, created_at)`
- `(tenant_id, run_id, created_at)`
- `(tenant_id, trace_id, created_at)`
- unique `(tenant_id, trace_id, seq)`

保留策略:

- 默认保留 30-90 天, 可配置。
- 不保存原始 prompt、完整工具返回、完整写入 payload。
- 可导出脱敏审计摘要。

## 5. 事件协议

### 5.1 基础字段

所有事件统一字段:

```ts
interface XhsTraceEvent {
  type: string; // xhs.trace.*
  schema_version: 1;
  event_id: string;
  trace_id: string;
  run_id: string;
  thread_id?: string;
  turn_id: string;
  parent_id?: string;
  seq: number;
  stage_id?: string;
  tool_call_id?: string;
  attempt?: number;
  ts: string; // ISO timestamp
  label: string;
  summary?: string;
  display?: {
    user_title?: string;
    user_summary?: string;
    detail_title?: string;
    detail_summary?: string;
  };
  status?: "pending" | "active" | "done" | "warning" | "error" | "waiting";
  visibility: "user" | "admin" | "debug";
  metrics?: Record<string, number | string | boolean>;
  safe_args?: Record<string, unknown>;
  safe_result?: Record<string, unknown>;
  error?: { code?: string; message: string; retryable?: boolean };
}
```

身份与顺序规则:

- `event_id`: 每条事件全局唯一, 是 `sourceEventIds` 的唯一来源。前端去重、历史恢复、审计反查都以它为准。
- `trace_id`: 一轮用户请求对应一个 trace。用户发起新请求时生成; 同一轮里的阶段、工具、子任务事件共用它。
- `turn_id`: 与用户消息或提交动作绑定, 用于把执行链挂到正确对话轮次。
- `run_id`: 使用 LangGraph run id; 如果 SDK 暂时拿不到, 后端生成稳定 id, 但不得为空地写入持久化表。
- `seq`: 同一 `trace_id` 内单调递增。前端展示优先按 `seq` 排序, `ts` 只作辅助显示和审计。
- `parent_id`: 子任务、工具详情、重试事件可以指向父阶段或父工具事件。
- `attempt`: 同一 `tool_call_id` 下的尝试次数, 首次为 `1`, 重试递增。没有重试的普通阶段可以为空。
- 任一新生产事件缺少 `event_id` / `trace_id` / `run_id` / `turn_id` / `seq` 时, 视为协议错误, 不进入普通用户展示。

### 5.1.1 时序模型

时序是生产执行链的硬约束, 分三层处理:

1. 权威顺序: 后端在 `emit_trace` 里为同一 `trace_id` 分配单调递增 `seq`。可用 DB 行锁、事务内计数器、Redis `INCR` 或等价的单 trace 原子分配器实现, 但不能由前端、浏览器接收顺序或客户端时间生成。
2. 因果关系: `seq` 表示观察到的事件顺序, 不单独表达业务因果。业务因果必须由 `parent_id`、`stage_id`、`tool_call_id`、`attempt` 和生命周期事件表达。
3. 展示顺序: 前端 reducer 用 `event_id` 去重, 用 `seq` 排序, 再由 `TracePresentationAdapter` 按阶段分组。`ts` 只用于显示“用时/发生时间”和审计辅助, 不参与主排序。

必须满足的时序不变量:

- `run.started.seq` 必须小于同一 `trace_id` 内所有业务事件。
- `run.completed` / `run.failed` 必须大于同一 `trace_id` 内所有非缺陷业务事件。
- `stage.started.seq` 必须小于同一 `stage_id` 下的 tool、progress、summary、stage terminal 事件。
- `stage.completed` / `stage.failed` / `warning` 必须晚于该阶段所有仍在执行的工具 terminal 事件。
- `tool.started.seq` 必须小于同一 `tool_call_id` 的 progress、retry、completed、failed。
- 重试必须带 `attempt`; `retry.seq` 必须晚于上一次失败或不稳定信号, 且早于下一次 attempt 的 `tool.started`。
- 人审中断必须先发 `human_approval.waiting`, 用户确认后才允许发 `human_approval.resolved`; 等待期间相关 stage 状态保持 `waiting`。
- 并发工具允许事件交错, 但每个工具自己的生命周期必须局部有序。UI 可以按父阶段分组展示, 不能把并发工具交错渲染成错误的线性因果。
- 断线恢复后如果收到旧事件、重复事件或乱序事件, reducer 必须稳定收敛到同一个 `TraceRunState`。
- 同一 `trace_id` 内出现重复 `seq`、倒退 terminal、缺少 started 的 terminal, 都是 trace 协议缺陷, 只能进入 admin 缺陷状态。

### 5.2 事件类型

必做:

- `xhs.trace.run.started`
- `xhs.trace.stage.started`
- `xhs.trace.stage.completed`
- `xhs.trace.tool.started`
- `xhs.trace.tool.progress`
- `xhs.trace.tool.completed`
- `xhs.trace.tool.failed`
- `xhs.trace.evidence.summary`
- `xhs.trace.retry`
- `xhs.trace.warning`
- `xhs.trace.human_approval.waiting`
- `xhs.trace.human_approval.resolved`
- `xhs.trace.run.completed`
- `xhs.trace.run.failed`

最小生命周期:

- 每个新 trace 必须以 `xhs.trace.run.started` 开始, 以 `xhs.trace.run.completed` 或 `xhs.trace.run.failed` 收口。
- 每个用户可见阶段至少包含 `stage.started` 和阶段 terminal 事件: `stage.completed` / `stage.failed`, 或挂到该 `stage_id` 的 `xhs.trace.warning`。
- 每个工具调用至少包含 `tool.started` 和 `tool.completed` / `tool.failed` 之一。
- `retry`, `evidence.summary`, `human_approval.*` 必须挂到已有 `parent_id`, 不能成为孤儿事件。
- 前端如果收到孤儿事件或生命周期不完整, 只能进入 admin 缺陷状态, 不能生成普通用户猜测文案。

可后续扩展:

- `xhs.trace.subagent.started`
- `xhs.trace.subagent.completed`
- `xhs.trace.persistence.saved`
- `xhs.trace.config.checked`
- `xhs.trace.schedule.created`
- `xhs.trace.backfill.completed`

### 5.3 阶段模型

默认阶段:

1. `understand`: 用户可见「理解你的需求」
2. `retrieve`: 用户可见「查找相关素材」
3. `rank`: 用户可见「筛选可用依据」
4. `compose`: 用户可见「整理选题/正文」
5. `validate`: 用户可见「检查依据是否充分」
6. `persist`: 用户可见「保存/同步结果」

对话生成第一版至少覆盖:

- 查素材: 语义检索、关键词补查、线上搜索、图谱扩展。
- 筛依据: 找到多少、采用多少、排除多少、哪些依据偏弱。
- 生成结果: 选题/文案生成完成。
- 数据不足: 主动用中文解释缺口, 例如「这次素材不够, 我先说明缺口, 不硬凑」。

## 6. 后端接入点

### 6.1 工具包装层

在 `data_foundation.tools`, `tools.feishu_actions`, `tools.redfox_search`, `tools.online_adopt`, `tools.lark_cli` 外围建立统一包装器:

- 调用前: `tool.started`
- 调用中: 工具内部可发 `tool.progress` / `evidence.summary`
- 成功后: `tool.completed`
- 失败后: `tool.failed`
- 重试: middleware 或 wrapper 发 `retry`

工具标签沿用当前 `web/src/lib/thinking-trace.ts` 的中文词典, 但权威词典应迁到共享 JSON 或后端常量。未知工具名不静默兜底为“正常步骤”, 应显示 admin warning 并进入测试修复清单。

### 6.2 `get_stream_writer()` 使用方式

只在工具执行路径和受控 graph node 中调用:

```python
from langgraph.config import get_stream_writer

def emit_trace(event: dict) -> None:
    event = sanitize_trace_event(event)
    persist_trace_event(event)
    try:
        writer = get_stream_writer()
    except Exception:
        return
    writer(event)
```

注意:

- 官方提示: 工具内调用 `get_stream_writer()` 后, 工具在 LangGraph 执行上下文外单独 invoke 时可能没有 writer。因此 helper 必须 no-op 兼容。
- no-op 只允许出现在本地单测、脚本校验、工具独立调用中。生产 LangGraph run 中拿不到 writer 视为 trace 管道缺陷, 需要持久化缺陷事件并让部署验收失败。
- 不能让 trace 写出失败影响业务工具结果。
- 持久化失败可降级为仅 streaming, 并发送 `xhs.trace.warning` 给 admin 可见。

### 6.3 DeepAgents 子 Agent

DeepAgents 自带 task/subagent 能力。第一期不碰内部私有实现, 只做:

- 对 `task` 工具调用显示 `subagent.started/completed`。
- `tasks` stream mode 中可识别的 task/subgraph 状态映射到 UI。
- 子 Agent 内部工具事件如果天然经过同一工具包装器, 自动进入同一 trace。

不做:

- 不 patch DeepAgents SubAgentMiddleware。
- 不解析子 Agent 内部 prompt。

### 6.4 人审中断

当前 `agent.py` 已对 `lark_cli`, `sync_*_to_feishu`, `adopt_online_notes` 配置 `interrupt_on`。trace 协议要覆盖:

- 写入类工具开始前: `human_approval.waiting`
- 用户批准/拒绝后: `human_approval.resolved`
- 拒绝: 阶段状态为 `warning` 或 `error`, UI 展示“已取消写入”。

## 7. 前端设计

### 7.1 StreamProvider

`web/src/providers/stream-context.ts` 当前 `CustomEventType` 只面向 LangGraph UI message。需要扩展为联合类型:

```ts
type CustomEventType = UIMessage | RemoveUIMessage | XhsTraceEvent;
```

`Stream.tsx` 的 `onCustomEvent`:

- 如果是 UI event: 继续走 `uiMessageReducer`。
- 如果是 `xhs.trace.*`: 写入 `traceStore`。
- 未知 custom event: 忽略或 admin debug 记录, 不报错。

### 7.2 TraceStore

新增前端聚合器, 输入为:

- `custom` trace events
- `tasks` events
- `values.messages` 仅用于回答、选题卡、文案块等业务内容, 不参与执行链补齐

输出为归一化中间态, 不是普通用户 UI 模型:

```ts
interface TraceRunState {
  traceId: string;
  turnId: string;
  status: "active" | "done" | "warning" | "error" | "waiting";
  collapsedByDefault: boolean;
  stages: TraceStageState[];
  technicalEvents: TraceTechnicalEvent[];
  warnings: string[];
}
```

`TraceRunState` 只允许传给 `TracePresentationAdapter`, 不能直接传给普通用户组件。

折叠策略:

- 简单成功: 默认折叠为 `查完 N 步`。
- 有风险、失败、重试、数据不足、等待确认: 默认展开摘要。
- debug 详情默认折叠。

### 7.2.1 Trace Presentation Adapter

必须新增展示转化层, 放在 `TraceStore` 和 UI 组件之间。它负责把官方事件和技术字段转换成用户可读中文, 防止协议字段直接进入普通用户界面。

关系不是“协议字段原样一一展示”, 而是“底层事件可追溯, 展示文案经转化”:

```text
xhs.trace.tool.completed
  + tool_name=semantic_search_resources
  + metrics.found_count=12
  + metrics.used_count=3
  -> 业务阶段: 查找相关素材
  -> 用户文案: 找到 12 条相关素材, 采用 3 条作为依据
```

职责:

1. 事件到业务阶段: 将 `type/stage_id/tool_name` 映射为「理解需求」「查找相关素材」「筛选可用依据」「整理选题/正文」「检查依据是否充分」「保存/同步结果」。
2. 状态到中文: 将 `active/done/warning/error/waiting` 映射为「正在处理」「已完成」「需要留意」「这一步没完成」「等你确认」。
3. 指标到结果摘要: 将 `metrics` 转成「找到 N 条」「采用 N 条」「排除 N 条」「用时 N 秒」等中文。
4. 权限过滤: 普通用户只拿 `user_title/user_summary`; 管理员可看 `detail_title/detail_summary`; debug 字段不进生产普通 UI。
5. 可追溯: 每条用户可见阶段或摘要必须保留 `sourceEventIds`; 如果落库字段采用 snake_case, 由 adapter 显式映射, 不能混用命名。
6. 缺失处理: 新 run 如果缺少必要官方事件, 不生成猜测文案, 输出 admin 可见缺陷状态。

输出模型建议:

```ts
interface TracePresentation {
  traceId: string;
  status: "active" | "done" | "warning" | "error" | "waiting";
  collapsedByDefault: boolean;
  userSummary: string;
  userStages: Array<{
    id: string;
    title: string;
    summary: string;
    statusText: string;
    metricsText?: string;
    sourceEventIds: string[];
  }>;
  adminDetails: TraceTechnicalEvent[];
}
```

硬规则:

- UI 组件只消费 `TracePresentation`, 不直接消费 `XhsTraceEvent`。
- 普通用户层不得从 `type/tool_name/stage_id/status` 拼字符串。
- `display.user_title/user_summary` 可由后端事件提供, 但前端仍必须经过 adapter 做脱敏、权限和中文检查。

### 7.3 UI 层

`ThinkingAura` 升级为 `AgentTracePanel` 或保留名称但扩展 props:

默认层:

- 阶段名称, 使用用户可读中文
- 状态图标
- 一句话结果摘要
- 关键指标: `找到 12 条`, `采用 3 条`, `排除 9 条`, `用时 1.2 秒`

展开层:

- 阶段下工具列表
- 工具状态, 仍使用中文动作描述
- 安全参数摘要
- 结果摘要
- 重试/失败原因

技术详情:

- 仅 admin/debug 可见
- 工具名、tool_call_id、duration_ms、safe_args、safe_result
- 不显示 token/secret/prompt/full payload

### 7.3.1 用户可见中文文案规范

普通用户看到的是“做了什么”, 不是“系统内部发生了什么”。实现时必须把协议字段和展示文案分开:

- `type`, `run_id`, `trace_id`, `stage_id`, `tool_name`, `safe_args`, `safe_result` 只能出现在技术详情或测试日志, 不能直接展示给普通用户。
- 普通用户界面不出现 `Agent`, `trace`, `run`, `stage`, `tool`, `custom`, `debug`, `schema`, `payload`, `warning`, `error`, `retry` 等英文或工程词。
- 普通用户界面使用中文动词短句: 「正在查找相关素材」「筛选可用依据」「整理选题」「检查依据是否充分」「等你确认」「已取消写入」。
- 风险和失败要讲人话, 不写错误码裸值。示例:
  - 数据不足: 「这次素材不够, 我先说明缺口, 不硬凑。」
  - 重试: 「刚才查询不稳定, 已重新尝试 1 次。」
  - 等待人审: 「写入飞书前需要你确认。」
  - 工具失败: 「这一步没完成, 我保留了原因, 你可以展开查看。」
- 成功摘要要表达结果, 不只表达动作。示例:
  - 「找到 12 条相关素材, 采用 3 条作为依据。」
  - 「排除了 9 条弱相关内容。」
  - 「已根据 3 条依据整理出选题。」
- 管理员/技术详情可以出现「技术详情」「工具调用」「参数摘要」「返回摘要」「用时」等词, 但仍必须中文优先, 英文字段只作为辅助标识。

推荐普通用户文案:

| 场景 | 文案 |
|---|---|
| 进行中总标题 | 正在查素材和历史数据 |
| 成功折叠 | 查完 N 步 |
| 展开按钮 | 查看做了什么 |
| 收起按钮 | 收起记录 |
| 检索阶段 | 查找相关素材 |
| 筛选阶段 | 筛选可用依据 |
| 生成阶段 | 整理选题/正文 |
| 数据不足 | 素材不够, 先说明缺口 |
| 等待确认 | 等你确认后再继续 |
| 失败 | 这一步没完成 |
| 重试 | 已重新尝试 |

### 7.4 消息顺序

已修正并继续坚持:

- 进行中: 可在回答生成前显示 active 执行链, 但必须绑定到当前 `turn_id` 的助手回答容器内。
- 完成后: 最终回答在上, 执行链在下方折叠/展开。
- 历史恢复: 先按消息时间线渲染用户消息和助手回答, 再按 `turn_id` 把对应 `TracePresentation` 挂到该助手回答下方。
- 流式到达: trace event 先到、回答 token 后到、或断线恢复后批量到达, 都不能改变对话消息主时间线。
- 多轮并发: 如果用户连续发起多轮请求, 每条 trace 只能挂到自己的 `turn_id`; 禁止把上一轮的工具状态显示到下一轮回答下方。
- 选题卡仍在右侧/卡片区展示, 不与执行链混淆。

## 8. 安全与权限

### 8.1 脱敏规则

禁止展示/保存:

- `token`, `credential`, `authorization`, `secret`, `password`, `dsn`, `uat`
- 完整 prompt
- 写入类工具 payload 正文
- 飞书 access token
- 数据库连接串
- 原始模型 chain-of-thought

允许展示:

- 查询主题的短摘要, 如“职场穿搭”
- 找到数、采用数、排除数
- 资源标题片段
- 相关度区间或脱敏 score
- 写入动作名称, 如“保存文案”, 不展示全文 payload

### 8.2 可见性

- `visibility=user`: 普通用户可见。
- `visibility=admin`: 管理员可见。
- `visibility=debug`: 仅本地或显式 debug 开关可见。

生产默认:

- 不启用 `debug` stream mode。
- 不展示 debug 事件。
- admin 详情也只展示脱敏字段。

## 9. 历史恢复

历史会话打开时:

1. 优先从 `agent_trace_events` 按 thread/run/turn 拉取 trace。
2. 如果新会话没有持久化 trace, UI 显示 admin 可见的“执行链缺失”错误, 并记录为验收失败。
3. 旧会话没有 `xhs.trace.*` 时, 不用 `messages` 重建执行链; 可以显示“该会话创建于官方执行链上线前, 无可审计记录”。

兼容策略:

- 老会话不补历史执行链, 避免把猜测数据伪装成官方审计记录。
- 新会话必须使用官方 trace 事件作为唯一执行链数据源。

## 10. 测试计划

### 10.1 后端

- `emit_trace` 在有 writer 时发送 custom event。
- `emit_trace` 在无 writer 时 no-op, 不影响工具单测。
- `emit_trace` 必须补齐并校验 `event_id` / `trace_id` / `run_id` / `turn_id` / `seq`。
- `seq` 分配器并发测试: 同一 `trace_id` 下并发工具写事件时, `seq` 不重复、不跳回、不由客户端生成。
- 脱敏规则 property test: 随机敏感 key 不得进入保存/stream payload。
- 工具 wrapper: started/completed/failed 事件成对。
- 重试 middleware 触发时产生 `xhs.trace.retry`。
- 人审中断产生 waiting/resolved。
- 持久化表 migration + repository 单测。
- 生命周期完整性测试: run、stage、tool 必须有开始和收口事件; 孤儿事件、倒退 terminal、缺少 started 的 terminal 不得通过校验。

### 10.2 前端

- `isXhsTraceEvent` 类型守卫。
- `traceReducer` 事件乱序/重复/断线恢复去重。
- `traceReducer` 按 `event_id` 去重, 按同一 `trace_id` 内的 `seq` 排序。
- `traceReducer` 收敛测试: 同一批事件用顺序、逆序、随机乱序、重复混入、断线分批输入, 最终 `TraceRunState` 必须一致。
- `TracePresentationAdapter` 映射测试: 同一个官方事件能转成正确业务阶段、中文状态、中文摘要, 并保留 `sourceEventIds`。
- `TracePresentationAdapter` 缺失事件测试: 缺 run/stage/tool 收口或存在孤儿事件时, 不生成普通用户文案, 只生成缺陷状态。
- `TraceRunState -> TracePresentation` 折叠策略。
- 多轮对话挂载测试: trace 只能根据 `turn_id` 挂在对应助手回答下方, 不能串轮。
- `AgentTracePanel` 用户层/详情层/admin 层渲染。
- UI 组件边界测试: 普通用户 UI 只能消费 `TracePresentation`, 不能直接渲染 `XhsTraceEvent`。
- 没有 `xhs.trace.*` 的新 run 必须暴露为缺陷状态, 不允许从 `messages` 派生补齐。
- 不显示敏感字段。
- 普通用户层中文文案检查: 不出现 `Agent` / `trace` / `run` / `tool` / `custom` / `debug` / `schema` / `payload` / `warning` / `error` / `retry` 等工程词; 必须出现自然中文阶段名和结果摘要。

### 10.3 E2E / 浏览器自动化

生产同构环境:

1. 发“按职场穿搭出 1 个选题, 要有依据”。
2. 验证 `/api/me=200`。
3. 验证 `custom` trace event 被前端接收。
4. 验证完成态“最终回答在上, 查完 N 步在下”。
5. 展开执行链, 验证阶段摘要和工具详情。
6. 验证普通用户可见区域是友好中文, 不出现技术字段或英文工程词。
7. 验证用户可见阶段能在测试钩子里追溯到 `sourceEventIds`, 但页面不显示这些 id。
8. 模拟或夹具注入乱序/重复 trace events, 验证最终折叠摘要、阶段顺序和详情顺序稳定。
9. 连续发送两轮请求, 验证第一轮 trace 不会挂到第二轮回答下方。
10. 验证没有 console error/page error/network failure/4xx/5xx。
11. 截图保存到 `.codex-ui-audit/`。

## 11. 部署与回滚

部署:

- 新增 DB migration。
- 后端重新构建 LangGraph 镜像。
- Web 重新构建。
- 先在本地/服务器容器 smoke 中验证 custom stream。
- 部署到生产。

回滚:

- 不提供运行时 fallback 到 `messages` 派生。
- 如需回滚, 通过常规部署回滚到上一稳定版本, 或临时隐藏执行链面板并保留回答链路。
- 后端 trace emit helper 的写出失败不影响业务工具结果, 但前端必须将执行链缺失标记为缺陷状态。
- migration 保留表不影响业务路径。

## 12. 验收标准

必须同时满足:

1. 使用官方 stream/custom/tasks 机制, 无私有 patch。
2. 对话生成链路有完整阶段: 查素材、筛依据、生成、校验/数据不足。
3. 展开详情可看到工具级摘要、找到数/采用数/排除数/用时/重试说明。
4. 生产严格脱敏, 不出现 token/secret/prompt/full payload。
5. 普通用户层必须是友好中文: 看得到“正在查什么、找到了什么、采用了什么、哪里不够”, 看不到工程字段。
6. 必须有 Trace Presentation Adapter: 底层事件和用户展示不原样一一展示, 但每条用户可见摘要都能追溯到原始官方事件。
7. 新历史会话可从持久化 trace 恢复执行链; 老会话明确显示无可审计记录, 不做猜测恢复。
8. 单测、集成测试、浏览器自动化全部通过。
9. 部署后生产健康检查通过。
10. 时序验收通过: 乱序、重复、断线恢复、多轮并发、人审暂停/恢复后, 用户看到的执行链顺序稳定且挂载到正确回答下方。

## 13. 自审

### 占位扫描

未保留 TBD/TODO。所有核心模块、事件类型、字段、权限、测试、部署和回滚均有明确描述。

### 内部一致性

本设计和旧规格的关系已明确: 旧前端派生方案被废弃, 新主路径改为官方 custom/tasks stream + 持久化。没有再声称“零后端改动”, 与用户“一次性到位、不需要 fallback”的要求一致。

### 范围检查

范围足够大, 但仍是一个可实施项目: 只围绕 Agent 执行链, 不同时重做选题卡、文案编辑器、飞书配置或移动端。第一交付覆盖对话生成链路, 架构预留其他 Agent 动作。

### 歧义检查

“思考链”已明确定义为“生产可审计执行链”, 非原始 chain-of-thought。完成态顺序、折叠策略、权限层、脱敏边界、持久化优先级均已写死。

### 用户可见中文检查

已明确协议字段和展示文案分离。普通用户看到的是「查找相关素材」「筛选可用依据」「找到 12 条, 采用 3 条」「素材不够, 先说明缺口」这类中文结果摘要, 不直接看到 `trace/run/tool/debug/payload` 等工程词。浏览器自动化必须把这条作为验收项。

### 展示转化层检查

已明确 `TracePresentationAdapter` 是必需边界: `XhsTraceEvent` 不能直接喂给普通用户 UI。底层事件与用户文案不是裸露一一对应, 但每条用户可见文案必须保留 `sourceEventIds`, 能反查到官方事件。

### 事件身份与生命周期检查

已补齐事件身份、顺序和生命周期约束: `event_id` 全局唯一, `(tenant_id, trace_id, seq)` 在同一执行链内唯一, 前端按 `seq` 排序并用 `event_id` 去重。每条 trace、stage、tool 都必须有开始和收口事件; 孤儿事件、不完整生命周期、缺少关键 id 的事件只能进入 admin 缺陷状态, 不能被转成普通用户文案。

### 时序检查

已把时序提升为独立硬约束: 后端负责生成权威 `seq`, 前端只负责去重、排序、收敛和展示, 不能依赖网络到达顺序或浏览器时间。并发工具、人审等待、重试、断线恢复和多轮对话都已有明确不变量; 完成态始终是“最终回答在上, 执行链在下方”, 并通过 `turn_id` 挂载到正确助手回答。

### 官方支持检查

主路径只使用 LangGraph/Agent Server 官方 streaming modes、工具内 `get_stream_writer()`、DeepAgents 公开 tools/subagents/interrupt 能力。不依赖私有字段或日志解析。`debug` 模式被明确排除出生产默认。

### 生产安全检查

生产服务器就是生产环境。设计默认严格脱敏, debug 受控, trace 写入失败不影响业务工具结果, 但不能被 `messages` 派生掩盖; 前端必须把执行链缺失暴露为缺陷状态。写入类 payload 不展示、不保存全文。

### 漏项检查

已覆盖:

- 实时展示
- 历史恢复
- 子 Agent/task
- 人审中断
- 重试/失败
- 数据不足
- 安全脱敏
- 浏览器自动化
- 部署/回滚

后续实施计划需要进一步拆成后端事件协议、工具 wrapper、DB migration、前端 trace reducer、UI 面板、E2E 六个阶段。
