export interface XhsTraceEvent {
  type: `xhs.trace.${string}`;
  schema_version: 1;
  event_id: string;
  trace_id: string;
  run_id: string;
  turn_id: string;
  thread_id?: string;
  parent_id?: string;
  seq: number;
  stage_id?: string;
  tool_call_id?: string;
  tool_name?: string;
  /** 本步真实检索词(仅搜索类工具有:keyword/query)。后端 trace_tool 从工具入参提取后带上,
   *  前端把它拼进步骤标题("检索本地笔记卡:露营装备"),让同工具多次调用不再看起来一模一样。 */
  query?: string;
  attempt?: number;
  ts: string;
  label: string;
  summary?: string;
  status?: "pending" | "active" | "done" | "warning" | "error" | "waiting";
  visibility: "user" | "admin" | "debug";
  metrics?: Record<string, number | string | boolean>;
}

export interface TraceRunState {
  traceId: string;
  turnId: string;
  events: XhsTraceEvent[];
  warnings: string[];
}

export interface TracePresentation {
  traceId: string;
  turnId: string;
  status: "active" | "done" | "warning" | "error" | "waiting";
  collapsedByDefault: boolean;
  userSummary: string;
  userStages: Array<{
    id: string;
    title: string;
    summary: string;
    intent: string;
    action: string;
    resultText: string;
    statusText: string;
    /** 机器可读的单步状态:done=该步已出终态事件;active=已开始未出终态;error=该步失败。
     *  供 UI 逐步渲染真实进度指针(第 N/M 步),不再拿 run 级状态一刀切所有步。 */
    state: "active" | "done" | "error";
    metricsText?: string;
    sourceEventIds: string[];
  }>;
  adminDetails: XhsTraceEvent[];
}

export function isXhsTraceEvent(value: unknown): value is XhsTraceEvent {
  const item = value as Partial<XhsTraceEvent>;
  return Boolean(
    item &&
      typeof item.type === "string" &&
      item.type.startsWith("xhs.trace.") &&
      item.schema_version === 1 &&
      typeof item.event_id === "string" &&
      typeof item.trace_id === "string" &&
      typeof item.run_id === "string" &&
      typeof item.turn_id === "string" &&
      typeof item.seq === "number",
  );
}

export function reduceTraceEvents(
  previous: TraceRunState | undefined,
  incoming: XhsTraceEvent[],
): TraceRunState {
  const byId = new Map<string, XhsTraceEvent>();
  for (const item of previous?.events ?? []) byId.set(item.event_id, item);
  for (const item of incoming) byId.set(item.event_id, item);
  const events = [...byId.values()].sort((a, b) => a.seq - b.seq);
  const first = events[0];
  return {
    traceId: first?.trace_id ?? previous?.traceId ?? "",
    turnId: first?.turn_id ?? previous?.turnId ?? "",
    events,
    warnings: [],
  };
}

interface StageCopy {
  title: string;
  summaryTitle: string;
  intent: string;
  action: string;
  fallbackResult: string;
}

// 工具调用链(§Bug1):思考链 = 真实"用了哪个工具、做了什么"。每一步的 title 直接是该工具的中文名
// (与后端 TRACE_TOOL_STAGES / thinking-trace.ts 的 TOOL_LABELS 对齐,单一事实源口径),
// intent 说清这步在干嘛,fallbackResult 是无 metrics 时的兜底结果句。
// 不再用「确认创作目标/核验素材依据」这类预设叙事阶段(那是编好的故事,不是真实工具链)。
const TOOL_COPY: Record<string, StageCopy> = {
  semantic_search_resources: {
    title: "按语义找相关素材",
    summaryTitle: "语义检索",
    intent: "从数据底座按语义相似度召回可用笔记和历史素材。",
    action: "按语义相似度召回与本轮主题相关的素材。",
    fallbackResult: "已完成语义检索。",
  },
  search_resources: {
    title: "按关键词补查素材",
    summaryTitle: "关键词检索",
    intent: "用关键词补一轮检索，避免只依赖语义相似的一组。",
    action: "用关键词补充检索素材。",
    fallbackResult: "已完成关键词检索。",
  },
  search_local_note_cards: {
    title: "检索本地笔记卡",
    summaryTitle: "本地笔记检索",
    intent: "在本地素材库里找能支撑本轮主题的历史笔记。",
    action: "检索本地笔记卡片，找出能支撑本轮主题的历史素材。",
    fallbackResult: "已检索本地笔记卡。",
  },
  get_resource: {
    title: "打开原文细看",
    summaryTitle: "原文核验",
    intent: "打开候选素材原文，核对关键表达、数据与上下文。",
    action: "打开候选素材原文，核对关键表达、数据和上下文。",
    fallbackResult: "已核对候选素材原文。",
  },
  graph_expand: {
    title: "顺着图谱找关联",
    summaryTitle: "关联扩展",
    intent: "沿素材关联图找相邻线索，补单条素材的信息盲区。",
    action: "顺着主题、账号、标签和内容关系扩展关联素材。",
    fallbackResult: "已完成关联素材扩展。",
  },
  get_operations_data: {
    title: "读取运营数据",
    summaryTitle: "运营数据",
    intent: "读取账号运营数据用于判断。",
    action: "读取账号近期运营表现与指标。",
    fallbackResult: "已读取运营数据。",
  },
  get_resource_performance: {
    title: "读取效果表现",
    summaryTitle: "效果表现",
    intent: "读取素材发布后的真实效果表现。",
    action: "读取素材的互动/转化等效果数据。",
    fallbackResult: "已读取效果表现。",
  },
  save_generated_topic: {
    title: "保存选题",
    summaryTitle: "保存选题",
    intent: "把本轮生成的选题沉淀入库，便于后续继续编辑/同步。",
    action: "把本轮选题写入素材库。",
    fallbackResult: "已保存本轮生成的选题。",
  },
  save_generated_copy: {
    title: "保存文案",
    summaryTitle: "保存文案",
    intent: "把本轮文案草稿沉淀入库。",
    action: "把本轮文案草稿写入素材库。",
    fallbackResult: "已保存本轮生成的文案草稿。",
  },
  save_user_feedback: {
    title: "沉淀反馈",
    summaryTitle: "沉淀反馈",
    intent: "把用户反馈沉淀下来，供后续学习复用。",
    action: "把用户反馈写入库。",
    fallbackResult: "已沉淀用户反馈。",
  },
  save_performance_metric: {
    title: "沉淀效果指标",
    summaryTitle: "沉淀效果",
    intent: "把发布后的效果数据回填沉淀。",
    action: "把效果指标回填入库。",
    fallbackResult: "已沉淀效果指标。",
  },
  sync_copy_to_feishu: {
    title: "同步文案到飞书",
    summaryTitle: "同步文案",
    intent: "把文案同步到飞书生产线。",
    action: "把文案写入飞书多维表。",
    fallbackResult: "已把文案同步到飞书生产线。",
  },
  sync_topic_to_feishu: {
    title: "同步选题到飞书",
    summaryTitle: "同步选题",
    intent: "把选题同步到飞书生产线。",
    action: "把选题写入飞书多维表。",
    fallbackResult: "已把选题同步到飞书生产线。",
  },
  sync_diagnosis_to_feishu: {
    title: "同步诊断到飞书",
    summaryTitle: "同步诊断",
    intent: "把诊断结果同步到飞书生产线。",
    action: "把诊断结果写入飞书。",
    fallbackResult: "已把诊断结果同步到飞书生产线。",
  },
  send_review_notification: {
    title: "发送审阅通知",
    summaryTitle: "审阅通知",
    intent: "在飞书发起人工审阅通知。",
    action: "发送审阅通知。",
    fallbackResult: "已发送审阅通知。",
  },
  adopt_online_notes: {
    title: "采纳线上笔记",
    summaryTitle: "线上素材采纳",
    intent: "把线上检索到的可用笔记收录进素材库（可追溯）。",
    action: "整理线上笔记的标题、链接和可用信息，并写入素材库。",
    fallbackResult: "已采纳可用的线上笔记。",
  },
  search_xhs_online: {
    title: "搜索小红书线上",
    summaryTitle: "线上搜索",
    intent: "在线检索小红书，补本地库之外的新鲜样本。",
    action: "在线检索小红书相关内容。",
    fallbackResult: "已完成线上素材搜索。",
  },
};

// task 委派:按 subagent_type 给出"请了哪个子助手"。与 thinking-trace.ts SUBAGENT_LABELS 对齐。
const SUBAGENT_TITLES: Record<string, string> = {
  "knowledge-atom-retriever": "请知识检索助手查证据",
  "persona-distiller": "请风格提炼助手看样本",
  "benchmark-analyst": "请对标分析助手拆爆款",
  "expert-panel-debater": "请专家会商助手给判断",
  "content-system-ingestor": "请内容入库助手收录素材",
  "curriculum-designer": "请课程设计助手搭框架",
  "copywriting-coprocessor": "请文案协处理助手起稿",
  "imitation-writer": "请仿写助手照范本写成品",
};

const ENGINEERING_WORD_RE = /\b(agent|trace|run|tool|custom|debug|schema|payload|warning|error|retry)\b/i;

// 工具链口径:每步先按真实 tool_name 取该工具的中文语义;task 委派按 subagent_type 细化;
// 都取不到才落到「处理当前步骤」的通用兜底(理论上不该出现,因为后端只 emit tool 事件)。
function copyForTool(event: XhsTraceEvent): StageCopy | undefined {
  if (event.tool_name === "task") {
    const sub =
      event.metrics && typeof event.metrics.subagent_type === "string"
        ? (event.metrics.subagent_type as string)
        : undefined;
    const title = (sub && SUBAGENT_TITLES[sub]) || "请子任务助手处理";
    return {
      title,
      summaryTitle: "子任务委派",
      intent: "委派子助手在隔离上下文里处理这步重活。",
      action: "把任务委派给执行型子助手。",
      fallbackResult: "子助手已返回处理结果。",
    };
  }
  if (event.tool_name && TOOL_COPY[event.tool_name]) return TOOL_COPY[event.tool_name];
  return undefined;
}

const GENERIC_COPY: StageCopy = {
  title: "处理当前步骤",
  summaryTitle: "步骤处理",
  intent: "把当前任务继续往前推进。",
  action: "根据当前上下文执行必要的处理步骤。",
  fallbackResult: "已完成当前处理步骤。",
};

function userTitle(event: XhsTraceEvent): string {
  const base = (copyForTool(event) ?? GENERIC_COPY).title;
  // 带上本步真实检索词 → 同工具多次调用在链上可区分("检索本地笔记卡:露营装备" vs "…:新手帐篷"),
  // 不再是无意义的重复。query 只有搜索类工具有;截断防超长标题糊屏。
  const q = typeof event.query === "string" ? event.query.trim() : "";
  if (!q) return base;
  const shown = q.length > 18 ? q.slice(0, 18) + "…" : q;
  return `${base}：${shown}`;
}

function userCopy(event: XhsTraceEvent): StageCopy {
  return copyForTool(event) ?? GENERIC_COPY;
}

function userSummary(event: XhsTraceEvent, title: string): string {
  if (event.summary && !ENGINEERING_WORD_RE.test(event.summary)) return event.summary;
  return title;
}

function metricsText(metrics: XhsTraceEvent["metrics"]): string | undefined {
  if (!metrics) return undefined;
  const parts: string[] = [];
  if (typeof metrics.found_count === "number") parts.push(`找到 ${metrics.found_count} 条`);
  if (typeof metrics.used_count === "number") parts.push(`采用 ${metrics.used_count} 条`);
  if (typeof metrics.excluded_count === "number") parts.push(`排除 ${metrics.excluded_count} 条`);
  return parts.join("，") || undefined;
}

function resultText(event: XhsTraceEvent, copy: StageCopy): string {
  const metrics = event.metrics;
  if (metrics) {
    const parts: string[] = [];
    if (typeof metrics.found_count === "number") parts.push(`找到 ${metrics.found_count} 条相关素材`);
    if (typeof metrics.used_count === "number") parts.push(`采用 ${metrics.used_count} 条作为本次回答依据`);
    if (typeof metrics.excluded_count === "number") parts.push(`排除 ${metrics.excluded_count} 条不适合本轮使用的素材`);
    if (parts.length) return `${parts.join("，")}。`;
    const genericMetrics = metricsText(metrics);
    if (genericMetrics) return genericMetrics;
  }
  if (event.summary && !ENGINEERING_WORD_RE.test(event.summary)) return event.summary;
  return copy.fallbackResult;
}

function statusText(event: XhsTraceEvent): string {
  if (event.type.endsWith(".failed")) return "这一步没完成";
  if (event.type.endsWith(".completed")) return "已完成";
  if (event.status === "waiting") return "等你确认";
  if (event.status === "warning") return "需要留意";
  return "正在处理";
}

interface StageEventGroup {
  event: XhsTraceEvent;
  sourceEventIds: string[];
}

function stageGroupKey(event: XhsTraceEvent): string {
  return event.tool_call_id ?? event.stage_id ?? event.event_id;
}

function isStageTerminal(event: XhsTraceEvent): boolean {
  return (
    event.type.endsWith(".completed") ||
    event.type.endsWith(".failed") ||
    event.status === "done" ||
    event.status === "error" ||
    event.status === "warning"
  );
}

function foldStageEvents(events: XhsTraceEvent[]): StageEventGroup[] {
  const groups = new Map<string, XhsTraceEvent[]>();
  for (const event of events) {
    const key = stageGroupKey(event);
    groups.set(key, [...(groups.get(key) ?? []), event]);
  }

  return [...groups.values()]
    .map((items) => {
      const sorted = [...items].sort((a, b) => a.seq - b.seq);
      const displayEvent =
        [...sorted].reverse().find((item) => isStageTerminal(item)) ?? sorted[sorted.length - 1];
      return {
        event: displayEvent,
        sourceEventIds: sorted.map((item) => item.event_id),
      };
    })
    .sort((a, b) => a.event.seq - b.event.seq);
}

export function toTracePresentation(state: TraceRunState): TracePresentation {
  const userEvents = state.events.filter((item) => item.visibility === "user");
  const terminal = userEvents.find(
    (item) => item.type === "xhs.trace.run.completed" || item.type === "xhs.trace.run.failed",
  );
  const stageEvents = foldStageEvents(userEvents.filter(
    (item) => item.stage_id || item.type.startsWith("xhs.trace.tool."),
  ));
  const userStages = stageEvents.map(({ event: item, sourceEventIds }) => {
    const copy = userCopy(item);
    const title = userTitle(item);
    const result = resultText(item, copy);
    // 意图行也带上真实检索词 → 每步说清"围绕『露营装备』在本地库找历史笔记",而非千篇一律的静态句。
    const q = typeof item.query === "string" ? item.query.trim() : "";
    const intent = q ? `围绕「${q}」${copy.intent}` : copy.intent;
    // 单步真实状态:该组代表事件(foldStageEvents 已选终态优先)是否已到终态。
    // failed → error;completed/其它终态 → done;仅有 started(尚无终态)→ active。
    const stepState: "active" | "done" | "error" = item.type.endsWith(".failed") || item.status === "error"
      ? "error"
      : isStageTerminal(item)
        ? "done"
        : "active";
    return {
      id: item.stage_id ?? item.tool_call_id ?? item.event_id,
      title,
      summary: userSummary(item, title),
      intent,
      action: copy.action,
      resultText: result,
      statusText: statusText(item),
      state: stepState,
      metricsText: metricsText(item.metrics),
      sourceEventIds,
    };
  });
  const completedSummary = (() => {
    if (!terminal) return "正在查素材和历史数据";
    if (userStages.length === 1) {
      const event = stageEvents[0]?.event;
      const copy = event ? userCopy(event) : undefined;
      const metrics = event ? metricsText(event.metrics) : undefined;
      if (copy && metrics) return `已完成${copy.summaryTitle}：${metrics}`;
      if (copy) return `已完成${copy.summaryTitle}`;
    }
    return `已完成 ${userStages.length} 步：${userStages.map((stage) => stage.title).join("、")}`;
  })();
  return {
    traceId: state.traceId,
    turnId: state.turnId,
    status: terminal?.type === "xhs.trace.run.failed" ? "error" : terminal ? "done" : "active",
    collapsedByDefault: Boolean(terminal),
    userSummary: completedSummary,
    userStages,
    adminDetails: state.events.filter((item) => item.visibility !== "user"),
  };
}
