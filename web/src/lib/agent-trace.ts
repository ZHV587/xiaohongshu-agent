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
    statusText: string;
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

const STAGE_TITLES: Record<string, string> = {
  understand: "理解你的需求",
  retrieve: "查找相关素材",
  rank: "筛选可用依据",
  compose: "整理选题/正文",
  validate: "检查依据是否充分",
  persist: "保存/同步结果",
};

const TOOL_TITLES: Record<string, string> = {
  semantic_search_resources: "查找相关素材",
  search_resources: "按关键词补查素材",
  search_local_note_cards: "检索本地笔记卡",
  get_resource: "打开原文细看",
  graph_expand: "顺着图谱找关联",
  save_generated_topic: "保存选题",
  save_generated_copy: "保存文案",
  sync_copy_to_feishu: "同步文案到飞书",
  sync_topic_to_feishu: "同步选题到飞书",
  sync_diagnosis_to_feishu: "同步诊断到飞书",
  adopt_online_notes: "采纳线上笔记",
  search_xhs_online: "搜索小红书线上",
};

const ENGINEERING_WORD_RE = /\b(agent|trace|run|tool|custom|debug|schema|payload|warning|error|retry)\b/i;

function userTitle(event: XhsTraceEvent): string {
  if (event.stage_id && STAGE_TITLES[event.stage_id]) return STAGE_TITLES[event.stage_id];
  if (event.tool_name && TOOL_TITLES[event.tool_name]) return TOOL_TITLES[event.tool_name];
  return "处理当前步骤";
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

function statusText(event: XhsTraceEvent): string {
  if (event.type.endsWith(".failed")) return "这一步没完成";
  if (event.type.endsWith(".completed")) return "已完成";
  if (event.status === "waiting") return "等你确认";
  if (event.status === "warning") return "需要留意";
  return "正在处理";
}

export function toTracePresentation(state: TraceRunState): TracePresentation {
  const userEvents = state.events.filter((item) => item.visibility === "user");
  const terminal = userEvents.find(
    (item) => item.type === "xhs.trace.run.completed" || item.type === "xhs.trace.run.failed",
  );
  const stageEvents = userEvents.filter(
    (item) => item.stage_id || item.type.startsWith("xhs.trace.tool."),
  );
  const userStages = stageEvents.map((item) => {
    const title = userTitle(item);
    return {
      id: item.stage_id ?? item.tool_call_id ?? item.event_id,
      title,
      summary: userSummary(item, title),
      statusText: statusText(item),
      metricsText: metricsText(item.metrics),
      sourceEventIds: [item.event_id],
    };
  });
  return {
    traceId: state.traceId,
    turnId: state.turnId,
    status: terminal?.type === "xhs.trace.run.failed" ? "error" : terminal ? "done" : "active",
    collapsedByDefault: Boolean(terminal),
    userSummary: terminal ? `查完 ${userStages.length} 步` : "正在查素材和历史数据",
    userStages,
    adminDetails: state.events.filter((item) => item.visibility !== "user"),
  };
}
