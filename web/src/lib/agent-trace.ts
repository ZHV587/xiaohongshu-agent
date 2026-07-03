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
    intent: string;
    action: string;
    resultText: string;
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

interface StageCopy {
  title: string;
  summaryTitle: string;
  intent: string;
  action: string;
  fallbackResult: string;
}

const STAGE_COPY: Record<string, StageCopy> = {
  understand: {
    title: "确认创作目标",
    summaryTitle: "需求确认",
    intent: "先把你要的交付物、主题和限制条件对齐，避免答偏。",
    action: "读取你的输入，区分是要选题、正文、标题，还是账号运营判断。",
    fallbackResult: "已确认本轮回答的目标和边界。",
  },
  retrieve: {
    title: "核验素材依据",
    summaryTitle: "素材核验",
    intent: "先确认有没有可用素材，避免凭空给建议。",
    action: "从数据底座检索与你需求相关的笔记和历史素材。",
    fallbackResult: "已完成相关素材检索。",
  },
  rank: {
    title: "筛选可用依据",
    summaryTitle: "依据筛选",
    intent: "把相关但不够有用的素材剔除，只保留能支撑回答的依据。",
    action: "按相关度、信息完整度和可转化程度筛选素材。",
    fallbackResult: "已筛出本轮回答可用的依据。",
  },
  compose: {
    title: "组织回答结构",
    summaryTitle: "回答组织",
    intent: "把素材结论整理成你能直接使用的选题或文案。",
    action: "按小红书表达场景组织标题、正文结构和行动建议。",
    fallbackResult: "已把依据整理成回答内容。",
  },
  validate: {
    title: "检查依据是否充分",
    summaryTitle: "依据检查",
    intent: "确认回答没有脱离素材，也没有把不确定内容说满。",
    action: "复核回答和素材依据之间的对应关系。",
    fallbackResult: "已完成依据充分性检查。",
  },
  persist: {
    title: "保存/同步结果",
    summaryTitle: "结果同步",
    intent: "把本轮产出沉淀下来，方便后续继续编辑或同步到飞书。",
    action: "保存生成结果，并按需同步到生产工作流。",
    fallbackResult: "已完成结果保存或同步。",
  },
};

const TOOL_COPY: Record<string, StageCopy> = {
  semantic_search_resources: STAGE_COPY.retrieve,
  search_resources: {
    ...STAGE_COPY.retrieve,
    action: "用关键词补充检索，避免只依赖语义相似的一组素材。",
  },
  search_local_note_cards: {
    ...STAGE_COPY.retrieve,
    action: "检索本地笔记卡片，找出能支撑本轮主题的历史素材。",
  },
  get_resource: {
    title: "查看原文细节",
    summaryTitle: "原文核验",
    intent: "确认素材的具体语境，避免只看标题或摘要就下判断。",
    action: "打开候选素材原文，核对关键表达、数据和上下文。",
    fallbackResult: "已核对候选素材原文。",
  },
  graph_expand: {
    title: "查找关联线索",
    summaryTitle: "关联扩展",
    intent: "沿着已有素材继续找相邻线索，补足单条素材的信息盲区。",
    action: "顺着主题、账号、标签和内容关系扩展关联素材。",
    fallbackResult: "已完成关联素材扩展。",
  },
  save_generated_topic: {
    ...STAGE_COPY.persist,
    title: "保存选题结果",
    fallbackResult: "已保存本轮生成的选题。",
  },
  save_generated_copy: {
    ...STAGE_COPY.persist,
    title: "保存文案草稿",
    fallbackResult: "已保存本轮生成的文案草稿。",
  },
  sync_copy_to_feishu: {
    ...STAGE_COPY.persist,
    title: "同步文案到飞书",
    fallbackResult: "已把文案同步到飞书生产线。",
  },
  sync_topic_to_feishu: {
    ...STAGE_COPY.persist,
    title: "同步选题到飞书",
    fallbackResult: "已把选题同步到飞书生产线。",
  },
  sync_diagnosis_to_feishu: {
    ...STAGE_COPY.persist,
    title: "同步诊断到飞书",
    fallbackResult: "已把诊断结果同步到飞书生产线。",
  },
  adopt_online_notes: {
    title: "采纳线上笔记",
    summaryTitle: "线上素材采纳",
    intent: "把线上检索到的可用笔记纳入数据底座，减少一次性素材浪费。",
    action: "整理线上笔记的标题、链接和可用信息，并写入素材库。",
    fallbackResult: "已采纳可用的线上笔记。",
  },
  search_xhs_online: {
    ...STAGE_COPY.retrieve,
    title: "搜索小红书线上素材",
    action: "在线检索小红书相关内容，补充本地数据底座之外的新鲜样本。",
    fallbackResult: "已完成线上素材搜索。",
  },
};

const ENGINEERING_WORD_RE = /\b(agent|trace|run|tool|custom|debug|schema|payload|warning|error|retry)\b/i;

function userTitle(event: XhsTraceEvent): string {
  if (event.stage_id && STAGE_COPY[event.stage_id]) return STAGE_COPY[event.stage_id].title;
  if (event.tool_name && TOOL_COPY[event.tool_name]) return TOOL_COPY[event.tool_name].title;
  return "处理当前步骤";
}

function userCopy(event: XhsTraceEvent): StageCopy {
  if (event.stage_id && STAGE_COPY[event.stage_id]) return STAGE_COPY[event.stage_id];
  if (event.tool_name && TOOL_COPY[event.tool_name]) return TOOL_COPY[event.tool_name];
  return {
    title: "处理当前步骤",
    summaryTitle: "步骤处理",
    intent: "把当前任务继续往前推进。",
    action: "根据当前上下文执行必要的处理步骤。",
    fallbackResult: "已完成当前处理步骤。",
  };
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
    return {
      id: item.stage_id ?? item.tool_call_id ?? item.event_id,
      title,
      summary: userSummary(item, title),
      intent: copy.intent,
      action: copy.action,
      resultText: result,
      statusText: statusText(item),
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
