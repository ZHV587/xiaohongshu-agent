# 思考链 UI 设计(思维微光接真实 agent 执行流)

- 日期:2026-07-01
- 范围:前端(web),零后端改动
- 状态:设计已定稿,待写实现计划

## 1. 背景与问题

Design System 的 `ThinkingAura`(思维微光)组件已 1:1 移植为
`web/src/components/ds/content/ThinkingAura.tsx`(呼吸微光点 + 步骤器
done ✓ / active ◐ / pending ○ + 可折叠原始日志),但**从未接上真实数据,是死代码**:

- 全项目仅一处使用,在 `CreationScreen.tsx:102`,且极度退化:
  `<ThinkingAura steps={[{ label: m.text, state: "active" }]} />`——把一条消息
  文本塞进单个 active 步骤,无多步链、无 logs、无状态流转。
- 触发条件 `m.thinking` 字段在 `StudioContext.tsx` 的 `deriveChat()` 里**从不被设置**,
  故 `ThinkingAura` 实际从未渲染真实内容。

真实的 agent 执行信号其实都在前端 `messages` 流里(已由 `ensure-tool-responses.ts`
证明消费过 `tool_calls` / `ToolMessage` / `tool_call_id` / `tc.name`),只是被
`deriveChat` 丢弃了。本设计把这些真实信号解析出来,喂给已有的 `ThinkingAura`。

## 2. 目标与非目标

**目标**:让思考链在创作聊天区内联实时步进(一跳一跳,superstep 级,非逐字打字机),
完成后折叠为「已完成 N 步 ▾」摘要。全部真实数据,零 mock,零后端改动,
全走 LangGraph SDK + deepagents 官方消息契约。

**非目标(YAGNI + 已决策)**:
- 模型原生 thinking/reasoning 块——另立 spec,先验证网关是否透传。
- RubricMiddleware 质检迭代展示——信号弱、收益小,不做。
- 深度创作(DeepCreation)区的思考链——本轮不覆盖(见 §7 范围界定)。

## 3. 真实性契约(数据来源)

全部字段已核实存在于前端 `messages` 流:

| 思考步骤来源 | 字段 | 官方机制 |
|---|---|---|
| 工具调用 | AI 消息 `tool_calls[]`(`tc.name` / `tc.args` / `tc.id`) | LangGraph Message |
| 工具结果 | `ToolMessage`(`type:"tool"` / `tool_call_id`) | LangGraph Message |
| 子 agent 委派 | `task` 工具调用,`tc.args.subagent_type` | deepagents SubAgentMiddleware |

状态判定(真实,不伪造):
- tool_call 有、配对 ToolMessage 未到 → `active`(◐)。
- 配对 ToolMessage 已到 → `done`(✓)。
- **绝不造 pending 占位**——只渲染真实已发生/正在发生的步骤(对齐项目「真实数据铁律」)。
  这与 DS 的 prompt 示例带 pending 态有出入,以真实数据铁律为准。

安全(对齐 CLAUDE.md):logs 里工具参数/结果**截断 + 脱敏**,不打印
credentials / token / Authorization / DSN / UAT;写类工具只显示动作语义,不回显 payload。

## 4. 架构:统一时间线 + 纯函数解析器

关键修正(自审推翻了「thinkingRuns 与 chatExtra 松散并存」的初版):
`chatExtra`(一维 ChatMsg[])与按轮聚合的思考链是**两个维度,对不齐**,线性
`chatExtra.map` 塞不进思考链。故合并为**统一有序时间线**。

**新增 `web/src/components/studio/thinking-trace.ts`(纯函数,无 React,可单测)**

```
deriveTimeline(messages: Message[]): TimelineItem[]

type TimelineItem =
  | { kind: "user"; text: string }
  | { kind: "thinking"; run: ThinkingRun }   // 一轮的思考链
  | { kind: "ai"; text: string }             // 该轮最终正文气泡

interface ThinkingRun {
  steps: ThinkingStep[];   // 复用 ThinkingAura 的 ThinkingStep
  logs: ThinkingLog[];     // 复用 ThinkingAura 的 ThinkingLog
  done: boolean;           // 该轮是否已收敛(决定折叠为摘要态)
}
```

**轮(run)切分规则(写死,解析器核心)**:
- 以 `human` 消息为分隔;相邻两条 human 之间的所有 `ai` + `tool` 消息聚为一轮。
- 一轮内 deepagents 多步工具循环会产出**多条 AI message**(AI→tool→AI→tool→…→AI 最终文本):
  - 所有中间 AI 的 `tool_calls` 全部归入该轮 `ThinkingRun.steps`;
  - 中间 AI 常只有 tool_calls、`content` 为空(见 `getContentString` 注释),不产出 ai 气泡;
  - **只有该轮最后一条有实际文本的 AI** 产出 `{ kind: "ai" }` 正文气泡。

**tool_call ↔ ToolMessage 配对**:用 `tool_call_id` **精确配对**,不靠数组顺序。

**步骤标签词典(名称 → 中文语义)** 集中在本文件,覆盖**两个工具来源**:
- `data_foundation/tools.py`:`search_resources`→「关键词检索数据底座」、
  `semantic_search_resources`→「语义检索数据底座」、`get_resource`→「精读素材原文」、
  `graph_expand`→「图谱扩展关联」、`save_generated_topic`→「沉淀选题入库」、
  `save_generated_copy`→「沉淀文案入库」、`save_user_feedback`→「沉淀反馈」、
  `save_performance_metric`→「沉淀效果指标」、`get_operations_data`→「读取运营数据」、
  `search_local_note_cards`→「检索本地笔记卡」、`sync_feishu_resources`→「同步飞书资源」。
- `tools/feishu_actions.py` 等:`sync_copy_to_feishu`→「同步文案到飞书」、
  `sync_topic_to_feishu`→「同步选题到飞书」、`sync_diagnosis_to_feishu`→「同步诊断到飞书」、
  `send_review_notification`→「发送审阅通知」、`adopt_online_notes`→「采纳线上笔记」、
  `search_xhs_online`→「搜索小红书线上」、`lark_cli`→「飞书 CLI 操作」。
- `task`(deepagents 委派):读 `tc.args.subagent_type` →
  `knowledge-atom-retriever`→「委派子任务:知识检索」、
  `persona-distiller`→「委派子任务:风格提炼」。
- **未知工具名兜底**:显示原名,不崩。

**改 2 处现有代码(修根因)**:
1. `StudioContext.tsx`:`deriveChat()` 由 `deriveTimeline()` 取代;store 暴露
   `timeline: TimelineItem[]`(替代 `chatExtra`)。步骤 active/done 完全由
   tool_call 与 ToolMessage 的 `tool_call_id` 配对决定,**不依赖** `isLoading` /
   `isStreaming`;后两者仅用于「整轮是否收敛 / 是否折叠」的辅助判定(可选增强,
   非硬依赖)——现 StudioContext 只用 `t.isLoading`,如需更精确的收尾时机可再接
   `t.isStreaming`。
2. `CreationScreen.tsx`:`ChatColumn` 改为消费 `timeline`,按 `kind` 渲染
   user 气泡 / ThinkingAura / ai 气泡。

**`ThinkingAura.tsx` 明确的组件改动(修正自审「基本不动」的失实)**:
现组件三态只有 done/active/pending,**无整体折叠为摘要的能力**。你选的「完成后折叠」
形态需要新增一个**折叠摘要态**:`done=true` 时默认渲染为单行「🍠 已完成 N 步 ▾」,
点击展开为完整步骤器。方案:给 `ThinkingAura` 加 `defaultCollapsed?: boolean` +
内部摘要头,或在 studio 侧包一层 `<ThinkingRunView>` 外壳。优先加 prop(组件内聚)。

## 5. 「已完成 N 步」计数规则

按**语义阶段**折叠计数,而非原始工具调用数。理由:一轮内 `get_resource` 精读 5 篇
会产生 5 个 tool_call,显示「已完成 5 步」里 4 步是重复精读,是噪音。规则:
- 同名连续工具调用折叠为一个语义阶段(5 次 get_resource → 1 步「精读素材原文」)。
- N = 去重后的语义阶段数。展开时仍可看到每次调用的独立 log。
- 与 §3「绝不造 pending」不冲突:折叠计数只对**已发生**的步骤去重合并,
  不预告未发生的阶段,不引入 pending 占位。

## 6. 状态流转与边界情况

一轮生命周期(全部真实流驱动):
- 用户发消息 → `isLoading=true`;首个 AI token 到 → `isStreaming=true`。
- AI 吐 tool_calls → 对应阶段 `active`(◐ 旋转);配对 ToolMessage 到 → 翻 `done`(✓)。
- 一轮内多工具依次点亮(检索→精读→图谱→落库→同步)。
- 最终 AI 吐正文且 `isLoading=false` → 该轮 `done=true`,折叠为「已完成 N 步 ▾」摘要,
  正文气泡渲染在其下方。

边界情况(逐个明确):
- **只回文本、没调工具**(闲聊)→ 该轮无 thinking item,直接出 ai 气泡,零噪音。
- **HITL 中断**(`interrupt_on`:`lark_cli` / `sync_*_to_feishu` / `adopt_online_notes`)
  → 该工具阶段停在 `active`,标签追加「· 等待确认」;组件不新增第四态,**复用 active + 文案**表达。恢复后翻 done。
- **流式未闭合**(tool_call 出、ToolMessage 未到)→ 停 `active`,不补假 done。
- **task 子 agent 委派** → 首版做「委派中(active)/ 已返回(done)」两态即可;
  子 agent 内部中间活动(streamSubgraphs 已开)暂不展开,留后续。
- **Anthropic 内容块数组态消息** → 复用现有 `getContentString`;解析器读 `tool_calls`
  字段(与内容格式无关),不受影响。
- **历史会话重放** → `fetchStateHistory:true` 已加载完整 messages,历史轮全部 `done`
  折叠展示,可展开回看。

**实现时校验点**:`task` 工具 `tc.name` 的真实大小写(`task` vs `Task`)
需用真实流打印一次或读 StructuredTool 的 `name=` 定义确认,词典 key 据此写死。

## 7. 范围界定

**本轮仅覆盖创作聊天区**(`CreationScreen` 的 `ChatColumn`)。已核实:
- `ChatColumn` / `chatExtra` **唯一消费点**是 `CreationScreen.tsx:19`(`showTopics={false}` 写死);
- 深度创作(DeepCreation)**不使用** `ChatColumn` / `chatExtra`,其 `polish` / `shorten` /
  `chooseTopic` 触发的 agent 调用本轮不展示思考链(留作后续)。

故改动天然收窄到单一入口,不会误伤深度创作或其他视图。

## 8. 测试

- **新增 `web/src/components/studio/thinking-trace.test.ts`**(纯函数,与现有
  `thread-*.test.ts` 同风格):
  - 纯文本轮 → 无 thinking item,仅 ai 气泡;
  - 单工具:active(无 ToolMessage)→ done(有配对 ToolMessage);
  - 多工具顺序 + 同名折叠计数(5× get_resource → 1 阶段);
  - tool_call 未闭合 → active;
  - `task` 委派 → 读 subagent_type 出中文标签;
  - Anthropic 数组内容态消息;
  - 未知工具名 → 兜底原名;
  - 多条中间 AI(只 tool_calls、content 空)→ 只有最后 AI 出 ai 气泡。
- **e2e 可观测钩子**:新增 `window.__XHS_THINKING_STEPS__`(与现有
  `__XHS_STREAMING__` / `__XHS_TOPICS_LEN__` 约定同构),供 Playwright 断言步骤数。
- **前端验收**:`tsc --noEmit` + `eslint src` + 上述单测。
- **浏览器端到端**:Docker Compose 环境实发一轮「按露营出选题」,肉眼确认阶段实时
  点亮 → 完成折叠(走 CLAUDE.md 容器化验证流程)。

## 9. 影响面小结

- 新增:`thinking-trace.ts` + `thinking-trace.test.ts`。
- 改动:`StudioContext.tsx`(deriveTimeline + 接 isStreaming + 钩子)、
  `CreationScreen.tsx`(ChatColumn 消费 timeline)、`ThinkingAura.tsx`(折叠摘要态 prop)、
  `types.ts`(TimelineItem / ThinkingRun 类型,移除死的 `ChatMsg.thinking`)。
- 删除:`deriveChat` 及 `ChatMsg`(被 TimelineItem 取代);`CreationScreen` 里退化的
  `m.thinking` 分支。
- 后端:**零改动**。

