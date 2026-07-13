import type { Message } from "@langchain/langgraph-sdk";
import { getContentString } from "@/components/thread/utils";
import { toolPresentation, type TracePresentation } from "@/lib/agent-trace";
import { parseXhsBlocks } from "@/lib/xhs-blocks";

export interface ThinkingStep {
  label: string;
  state: "done" | "active" | "pending" | "error";
  description?: string;
  result?: string;
}

export interface ThinkingLog {
  text: string;
}

export interface ThinkingRun {
  steps: ThinkingStep[];
  logs: ThinkingLog[];
  done: boolean;
  /** 当前进行到第几步(1-based;基于真实已出现的步骤,未运行的步骤不虚构)。
   *  = 最后一个 active 步的序号;全部完成时 = 总步数。无步骤时为 0。 */
  currentStep: number;
  /** 目前已知的总步数(= 已出现的步骤数;不预告未来步骤,忠实"绝不塞假")。 */
  totalSteps: number;
  presentation?: TracePresentation;
}

export interface DiscoveryNote {
  note_id: string;
  title: string;
  summary?: string;
  author?: string;
  cover_url?: string;
  note_url?: string;
  likes?: number;
  collects?: number;
  comments?: number;
  tags?: string[];
  source?: "local" | "online";
  already_local?: boolean;
  /** 已入库素材(本地卡)的真实资源 id;线上未采纳的瞬态笔记无此字段(需先收录才有)。
   *  仿写要求范本可追溯到库内 resource_id,故本地卡直接用它,线上卡走「先收录再仿」。 */
  resource_id?: string;
  /** 本地素材卡对应的不可变版本；与 resource_id 成对传给仿写链路。 */
  resource_version?: number;
}

/** 意图分流按钮(§2):模糊创作请求时,模型用 xhs_panel 块给出可点选项,用户点一下直接进
 *  对应流程(不用打字)。{label 显示文案, text 点击后代发的指令}。 */
export interface PanelAction {
  label: string;
  text: string;
}

export type TimelineItem =
  | { kind: "user"; text: string }
  | { kind: "thinking"; run: ThinkingRun }
  | { kind: "ai"; text: string }
  | { kind: "discovery"; notes: DiscoveryNote[] }
  | { kind: "panel"; actions: PanelAction[] }
  | { kind: "error"; text: string };

/** 一条笔记的收录结局(供结果弹窗逐条列出)。
 *  - success:本次新收录入库;
 *  - skipped:库里早有(幂等 upsert,非本次新增);
 *  - failed:入库失败(可重试)。 */
export interface AdoptionRow {
  note_id: string;
  title: string;
  outcome: "success" | "skipped" | "failed";
  /** failed 行的失败原因(取该 note 的第一条 DB/采纳错误,不含飞书/关联的二级告警)。 */
  error?: string;
}

/** 一次 adopt_online_notes 的整体结局:计数 + 逐条 + 失败项 note_id(供「重试失败」)。
 *  callId = 该次采纳的 tool_call_id,用于前端「已看过就不再自动弹」的去重。 */
export interface AdoptionOutcome {
  callId: string;
  rows: AdoptionRow[];
  successCount: number;
  skippedCount: number;
  failedCount: number;
  failedNoteIds: string[];
}

// 发现式搜索工具:结果是可勾选采纳的笔记卡(走卡片通道,不复述进正文,见 prompts.py §6.5)。
const DISCOVERY_TOOLS = new Set(["search_local_note_cards", "search_xhs_online"]);

export interface TimelineContext {
  loading?: boolean;
  error?: unknown;
  tracePresentationsByTurnId?: Record<string, TracePresentation>;
}

// 写类工具名单:这些工具会写库或写飞书,args 可能含敏感 payload/凭证。
// 写类工具的 log 只存中文 label,不回显 args。
const WRITE_TOOLS = new Set([
  "save_generated_topic",
  "save_generated_copy",
  "save_user_feedback",
  "save_writing_teardown",
  "save_performance_metric",
  "save_session_snapshot",
  "confirm_session_snapshot",
  "sync_feishu_resources",
  "sync_copy_to_feishu",
  "sync_topic_to_feishu",
  "sync_diagnosis_to_feishu",
  "send_review_notification",
  "adopt_online_notes",
  "lark_cli",
]);

// 敏感键名模式(大小写不敏感)：剥除读类工具 args 里的此类字段后再 stringify。
const SENSITIVE_KEY_RE = /credential|token|authorization|secret|password|dsn|uat/i;

// task 委派:按 subagent_type 细化;未知/缺失回退通用。
const SUBAGENT_LABELS: Record<string, string> = {
  "knowledge-atom-retriever": "请知识检索助手查证据",
  "persona-distiller": "请风格提炼助手看样本",
  "benchmark-analyst": "请对标分析助手拆爆款",
  "expert-panel-debater": "请专家会商助手给判断",
  "content-system-ingestor": "请内容入库助手收录素材",
  "curriculum-designer": "请课程设计助手搭框架",
  "copywriting-coprocessor": "请文案协处理助手起稿",
  "imitation-writer": "请仿写助手照范本写成品",
};

export function toolLabel(name: string, args: unknown): string {
  if (name === "task") {
    const sub =
      args && typeof args === "object" && "subagent_type" in args
        ? (args as { subagent_type?: unknown }).subagent_type
        : undefined;
    if (typeof sub === "string" && SUBAGENT_LABELS[sub]) return SUBAGENT_LABELS[sub];
    return "请子任务助手处理";
  }
  return toolPresentation(name)?.title ?? name;
}

interface ToolCall {
  id?: string;
  name: string;
  args?: unknown;
}

function safeArgsLog(label: string, args: unknown): string {
  let detail = "";
  try {
    // Strip sensitive keys before stringify (double-guard for read tools)
    let sanitized = args;
    if (args != null && typeof args === "object" && !Array.isArray(args)) {
      const cleaned: Record<string, unknown> = {};
      for (const [k, v] of Object.entries(args as Record<string, unknown>)) {
        if (!SENSITIVE_KEY_RE.test(k)) cleaned[k] = v;
      }
      sanitized = cleaned;
    }
    detail =
      sanitized == null ? "" : typeof sanitized === "string" ? sanitized : JSON.stringify(sanitized);
  } catch {
    detail = "";
  }
  if (detail.length > 200) detail = detail.slice(0, 200) + "…";
  return detail ? `${label}: ${detail}` : label;
}

function safeVisibleText(value: unknown): string {
  let raw = "";
  if (value instanceof Error) {
    raw = value.message;
  } else if (typeof value === "string") {
    raw = value;
  } else if (value && typeof value === "object") {
    try {
      raw = JSON.stringify(value);
    } catch {
      raw = "";
    }
  } else {
    raw = String(value ?? "");
  }
  if (!raw || raw === "[object Object]") return "响应失败，请稍后重试";
  return raw
    .replace(/(token|credential|authorization|secret|password|dsn|uat)\s*[:=]\s*[^,\s;]+/gi, "$1=[redacted]")
    .slice(0, 240);
}

// 剥离 xhs 结构块,只留自然语言(防 JSON 糊屏,spec §8)。
function proseOf(content: Message["content"]): string {
  const raw = getContentString(content);
  if (!raw) return "";
  const segs = parseXhsBlocks(raw);
  return segs
    .filter((s): s is { kind: "text"; text: string } => s.kind === "text")
    .map((s) => s.text)
    .join("")
    .trim();
}

// 是否含中日韩表意文字。本产品面向中文创作者,所有面向用户的回答/进展叙述都是中文;
// 纯英文的 prose 只可能是子代理/模型的英文脚手架旁白(如 "I'll start by reading the
// reference material.")——它是过程噪声,绝不是给用户看的答案,不进对话流(§8 防糊屏的语言维扩展)。
// 判据:出现任一 CJK 表意字即视为"面向用户的中文内容"(中英混排的正常回答也含中文,照常保留);
// 一个中文字都没有 → 判为英文脚手架,丢弃。
const CJK_RE = /[㐀-䶿一-鿿豈-﫿]/;
function hasCJK(text: string): boolean {
  return CJK_RE.test(text);
}

function toolCallsOf(message: Message): ToolCall[] {
  if (message.type !== "ai") return [];
  return ((message as { tool_calls?: ToolCall[] }).tool_calls ?? []).filter(
    (call) => call && typeof call.name === "string",
  );
}

/**
 * DeepAgents 的 ReAct 回合会产生两类 AI 文本：
 * 1. 调工具前/工具之间的过程说明；
 * 2. 所有工具结束后的正式答复。
 *
 * LangGraph 消息本身没有另造一个“progress”角色，可靠边界是工具调用：
 * 当前消息带 tool_calls，或本轮后面仍有 AI tool_calls → 过程说明；
 * 后面再无工具调用 → 正式答复。
 */
function isProcessNarration(turnMessages: Message[], index: number): boolean {
  if (turnMessages[index]?.type !== "ai") return false;
  if (toolCallsOf(turnMessages[index]).length > 0) return true;
  for (let i = index + 1; i < turnMessages.length; i++) {
    if (toolCallsOf(turnMessages[i]).length > 0) return true;
  }
  return false;
}

function compactNarration(text: string): string {
  const compact = text.replace(/\s+/g, " ").trim();
  return compact.length > 72 ? `${compact.slice(0, 72)}…` : compact;
}

function processNarrations(turnMessages: Message[]): string[] {
  const narrations: string[] = [];
  for (let i = 0; i < turnMessages.length; i++) {
    if (!isProcessNarration(turnMessages, i)) continue;
    const prose = proseOf(turnMessages[i].content);
    if (prose && hasCJK(prose)) narrations.push(prose);
  }
  return narrations;
}

// 从 AI 消息里提取 xhs_panel 意图分流按钮(§2);无则空数组。合并所有 panel 段的 actions。
function panelOf(content: Message["content"]): PanelAction[] {
  const raw = getContentString(content);
  if (!raw) return [];
  const out: PanelAction[] = [];
  for (const s of parseXhsBlocks(raw)) {
    if (s.kind === "panel") out.push(...s.data.actions);
  }
  return out;
}

// 把发现工具的一条结果行规整成 DiscoveryNote;缺 note_id/title 的丢弃。健壮:非对象跳过。
function toDiscoveryNote(raw: unknown): DiscoveryNote | null {
  if (!raw || typeof raw !== "object") return null;
  const r = raw as Record<string, unknown>;
  const noteId = typeof r.note_id === "string" && r.note_id.trim()
    ? r.note_id.trim()
    : typeof r.resource_id === "string" && r.resource_id.trim()
      ? r.resource_id.trim()
      : "";
  const title = typeof r.title === "string" ? r.title : "";
  if (!noteId || !title) return null;
  const num = (v: unknown): number | undefined => (typeof v === "number" && isFinite(v) ? v : undefined);
  const resourceId =
    typeof r.resource_id === "string" && r.resource_id.trim()
      ? r.resource_id.trim()
      : null;
  const resourceVersion =
    typeof r.resource_version === "number" &&
    Number.isInteger(r.resource_version) &&
    r.resource_version > 0
      ? r.resource_version
      : null;
  return {
    note_id: noteId,
    title,
    summary: typeof r.summary === "string" ? r.summary : undefined,
    author: typeof r.author === "string" ? r.author : undefined,
    cover_url: typeof r.cover_url === "string" ? r.cover_url : undefined,
    note_url: typeof r.note_url === "string" ? r.note_url : undefined,
    likes: num(r.likes),
    collects: num(r.collects),
    comments: num(r.comments),
    tags: Array.isArray(r.tags) ? r.tags.filter((t): t is string => typeof t === "string") : undefined,
    source: r.source === "local" || r.source === "online" ? r.source : undefined,
    already_local: typeof r.already_local === "boolean" ? r.already_local : undefined,
    // exact identity 是一个原子值：只有 id/version 同时合法才接纳，绝不保留半对身份。
    ...(resourceId != null && resourceVersion != null
      ? { resource_id: resourceId, resource_version: resourceVersion }
      : {}),
  };
}

// 解析一条发现工具 tool 消息的 content(JSON {ok, results:[...]}),取出笔记卡。失败→空数组。
function parseDiscoveryResults(content: Message["content"]): DiscoveryNote[] {
  const text = getContentString(content);
  if (!text) return [];
  try {
    const parsed = JSON.parse(text) as { results?: unknown };
    if (!Array.isArray(parsed.results)) return [];
    return parsed.results.map(toDiscoveryNote).filter((n): n is DiscoveryNote => n !== null);
  } catch {
    return [];
  }
}

// ── 工作流阶段轨道(write_todos 驱动)────────────────────────────────────────
// 智能体开工前用 write_todos 写下这一轮的**工作流阶段计划**(理解需求→检索爆款素材→拆解套路
// →产出选题…),每完成一阶段标 completed、下一阶段标 in_progress。这份计划就是用户在思考链里
// 看到的"智能体在干什么"的进度——泛化的工作流阶段,不是某次具体检索。它是最高优先的轨道:
// 一旦本轮有 write_todos,就用它当思考链主轴,压制官方/兜底的工具级轨道(避免两套并存糊屏)。

interface TodoItem {
  content: string;
  status: "pending" | "in_progress" | "completed";
}

// 计数类工具(检索/发现):其结果条数补进"当前进行中的阶段"作一句结果行(↳ 命中 N 条)。
const COUNTABLE_TOOLS = new Set([
  "search_local_note_cards",
  "search_xhs_online",
  "retrieve_knowledge",
]);

// 从一条 write_todos 工具调用的 args 里解析 todos 数组(args 可能是对象或 JSON 串)。非法 → null。
function parseTodos(args: unknown): TodoItem[] | null {
  let obj = args;
  if (typeof obj === "string") {
    try { obj = JSON.parse(obj); } catch { return null; }
  }
  if (!obj || typeof obj !== "object") return null;
  const raw = (obj as { todos?: unknown }).todos;
  if (!Array.isArray(raw)) return null;
  const out: TodoItem[] = [];
  for (const t of raw) {
    if (!t || typeof t !== "object") continue;
    const content = typeof (t as { content?: unknown }).content === "string" ? (t as { content: string }).content.trim() : "";
    const status = (t as { status?: unknown }).status;
    if (!content) continue;
    out.push({
      content,
      status: status === "in_progress" || status === "completed" ? status : "pending",
    });
  }
  return out.length ? out : null;
}

// 数一条工具结果里命中的条数(结果形如 {results:[...]});取不到 → null(不伪造)。
function countResults(content: Message["content"]): number | null {
  const text = getContentString(content);
  if (!text) return null;
  try {
    const parsed = JSON.parse(text) as { results?: unknown; evidence?: unknown };
    if (Array.isArray(parsed.evidence)) return parsed.evidence.length;
    return Array.isArray(parsed.results) ? parsed.results.length : null;
  } catch {
    return null;
  }
}

// 给一个回合的消息片段构建"工作流阶段" run:以最新一次 write_todos 计划为主轴,把计数类工具
// 命中数归到"命中它时正处于 in_progress 的那个阶段"作结果行。本轮无 write_todos → null(回退)。
function buildTodoRun(
  turnMsgs: Message[],
  turnIsLast: boolean,
  loading: boolean | undefined,
): ThinkingRun | null {
  let latest: TodoItem[] | null = null;
  let currentPhase = ""; // 当前 in_progress 阶段的 content
  const resultsByPhase = new Map<string, number>();
  const narrationsByPhase = new Map<string, string[]>();
  const logs: ThinkingLog[] = [];
  const toolNameByCallId = new Map<string, string>();

  for (let messageIndex = 0; messageIndex < turnMsgs.length; messageIndex++) {
    const m = turnMsgs[messageIndex];
    if (m.type === "ai") {
      const calls = toolCallsOf(m);
      for (const c of calls) {
        if (c.id) toolNameByCallId.set(c.id, c.name);
        if (c.name === "write_todos") {
          const todos = parseTodos(c.args);
          if (todos) {
            latest = todos;
            currentPhase = todos.find((t) => t.status === "in_progress")?.content ?? currentPhase;
          }
          continue;
        }
        const label = toolLabel(c.name, c.args);
        logs.push({ text: WRITE_TOOLS.has(c.name) ? label : safeArgsLog(label, c.args) });
      }
      if (isProcessNarration(turnMsgs, messageIndex)) {
        const narration = proseOf(m.content);
        if (narration && hasCJK(narration)) {
          // 正常情况取当前 in_progress 阶段；模型刚把所有阶段标完、但仍有收尾工具时，
          // 归到最后一个已完成阶段，确保过程说明仍留在同一个小框里。
          const phase =
            currentPhase ||
            latest?.find((item) => item.status === "in_progress")?.content ||
            [...(latest ?? [])].reverse().find((item) => item.status === "completed")?.content ||
            latest?.[0]?.content ||
            "";
          if (phase) {
            narrationsByPhase.set(phase, [...(narrationsByPhase.get(phase) ?? []), narration]);
          }
          logs.push({ text: narration });
        }
      }
    }
    if (m.type === "tool") {
      const cid = (m as { tool_call_id?: string }).tool_call_id;
      const toolName = cid ? toolNameByCallId.get(cid) : undefined;
      // 只统计真实检索/发现工具，避免其它返回 {results:[]} 的工具被误算成素材命中数。
      if (cid && toolName && COUNTABLE_TOOLS.has(toolName) && currentPhase) {
        const n = countResults(m.content);
        if (n != null) resultsByPhase.set(currentPhase, (resultsByPhase.get(currentPhase) ?? 0) + n);
      }
    }
  }

  if (!latest) return null;

  // 参考设计的流式契约是“逐行追加，不预列待办”：pending 阶段尚未发生，不提前展示。
  const visibleTodos = latest.filter((item) => item.status !== "pending");
  const steps: ThinkingStep[] = visibleTodos.map((t) => {
    const state: ThinkingStep["state"] = t.status === "completed" ? "done" : "active";
    const hit = resultsByPhase.get(t.content);
    const narrations = narrationsByPhase.get(t.content) ?? [];
    const description = narrations.length ? compactNarration(narrations[narrations.length - 1]) : undefined;
    return {
      label: t.content,
      state,
      ...(description ? { description } : {}),
      ...(hit != null ? { result: `命中 ${hit} 条相关素材` } : {}),
    };
  });
  const lastActive = steps.reduce((acc, s, i) => (s.state === "active" ? i : acc), -1);
  const currentStep = steps.length === 0 ? 0 : lastActive >= 0 ? lastActive + 1 : steps.length;
  // 收尾口径同官方轨道:全阶段 completed∥历史回合∥最后一轮且流已停。
  const done = latest.every((item) => item.status === "completed") || !turnIsLast || loading === false;
  return { steps, logs, done, currentStep, totalSteps: steps.length };
}

export function deriveTimeline(messages: Message[], context: TimelineContext = {}): TimelineItem[] {
  const out: TimelineItem[] = [];
  const presentations = context.tracePresentationsByTurnId ?? {};

  // 全局:已答/已失败的 tool_call_id 集合(按 tool_call_id 配对,不靠顺序)。
  // 同时记录每个 tool_call_id 对应的工具名,供 tool 消息判断是否是发现工具(要渲染卡片网格)。
  const answered = new Set<string>();
  const errored = new Set<string>();
  const toolNameById = new Map<string, string>();
  let lastHumanIdx = -1;
  for (let i = 0; i < messages.length; i++) {
    const m = messages[i];
    if (m.type === "human") lastHumanIdx = i;
    if (m.type === "tool") {
      const cid = (m as { tool_call_id?: string }).tool_call_id;
      if (cid) {
        answered.add(cid);
        // ToolMessage.status === "error":该步真实失败,兜底轨道要如实标 ✕,不能装作 done。
        if ((m as { status?: string }).status === "error") errored.add(cid);
      }
    }
    if (m.type === "ai") {
      for (const c of ((m as { tool_calls?: ToolCall[] }).tool_calls ?? [])) {
        if (c && typeof c.name === "string" && c.id) toolNameById.set(c.id, c.name);
      }
    }
  }

  // 一轮内累积的原子步骤记录(渲染前折叠)。
  type Atom = { name: string; state: "done" | "active" | "error"; description?: string };
  let atoms: Atom[] = [];
  let logs: ThinkingLog[] = [];
  let queuedNarration: string | undefined;
  let runOpen = false;
  // 当前回合是否有官方 trace 轨道(逐轮判断,不再全局一刀切:
  // 只压制「匹配到 presentation 的那一轮」的兜底轨道,其余轮照常显示)。
  let turnHasOfficial = false;
  // 当前回合是否已有更高优先级的轨道(工作流 todos 或官方 trace)→ 压制兜底工具轨道。
  // 优先级:工作流阶段(write_todos)> 官方工具 trace > 兜底工具轨道。三者只显示最高的一条。
  let turnHasWorkflow = false;

  // 把原子记录按「同名连续」折叠成语义步骤;组状态:任一 error → error;全 done → done;否则 active。
  const foldSteps = (): ThinkingStep[] => {
    const steps: ThinkingStep[] = [];
    let i = 0;
    while (i < atoms.length) {
      const name = atoms[i].name;
      let hasError = atoms[i].state === "error";
      let allDone = atoms[i].state !== "active";
      let narration = atoms[i].description;
      let j = i + 1;
      while (j < atoms.length && atoms[j].name === name) {
        hasError = hasError || atoms[j].state === "error";
        allDone = allDone && atoms[j].state !== "active";
        narration = atoms[j].description ?? narration;
        j++;
      }
      // 兜底轨道也带一句意图说明(有则显示),让每步读起来是"在干什么/为什么",不再是裸动作名。
      const description = narration;
      const state: ThinkingStep["state"] = hasError ? "error" : allDone ? "done" : "active";
      steps.push({ label: name, state, ...(description ? { description } : {}) });
      i = j;
    }
    return steps;
  };

  const buildRunItem = (): TimelineItem | null => {
    if (!runOpen || atoms.length === 0) return null;
    const allAtomsDone = atoms.length > 0 && atoms.every((a) => a.state !== "active");
    const steps = foldSteps();
    // 兜底轨道同样给出进度指针:最后一个 active 步为当前步,全完成则停在末步。
    const lastActive = steps.reduce((acc, s, i) => (s.state === "active" ? i : acc), -1);
    const currentStep = steps.length === 0 ? 0 : lastActive >= 0 ? lastActive + 1 : steps.length;
    return {
      kind: "thinking",
      run: { steps, logs, done: allAtomsDone, currentStep, totalSteps: steps.length },
    };
  };

  const resetRun = () => {
    atoms = [];
    logs = [];
    queuedNarration = undefined;
    runOpen = false;
  };

  const flushRun = () => {
    if (turnHasWorkflow) {
      resetRun();
      return;
    }
    const item = buildRunItem();
    if (item) out.push(item);
    resetRun();
  };

  // 官方轨道:turn_id 契约 = 本轮 human 消息 id(前端 submit 时写入 configurable.turn_id,
  // 后端 agent_trace._config_identity 原样采用)。在 user 项之后立即挂出 —— 像 Claude Code /
  // Codex 一样,工作轨迹在回答上方流式展开,不依赖 prose 是否已产出。
  const appendOfficialTrace = (
    presentation: TracePresentation,
    turnMessages: Message[],
    turnIsLast: boolean,
  ) => {
    const narrations = processNarrations(turnMessages);
    const lastNarration = narrations.length ? compactNarration(narrations[narrations.length - 1]) : undefined;
    const lastActiveIndex = presentation.userStages.reduce(
      (acc, stage, index) => (stage.state === "active" ? index : acc),
      -1,
    );
    // 逐步映射每一步的真实状态(stage.state 来自该步终态事件),不再用 run 级状态一刀切。
    const steps: ThinkingStep[] = presentation.userStages.map((stage, index) => ({
      label: stage.title,
      state: stage.state === "error" ? "error" : stage.state, // done | active | error
      description: index === lastActiveIndex && lastNarration ? lastNarration : stage.intent,
      result: stage.resultText,
    }));
    // 进度指针:最后一个仍在 active 的步 = 当前步;全部完成 = 停在最后一步。忠实真实事件,不虚构未来步。
    const lastActive = steps.reduce((acc, s, i) => (s.state === "active" ? i : acc), -1);
    const currentStep = steps.length === 0 ? 0 : lastActive >= 0 ? lastActive + 1 : steps.length;
    // 后端目前不发 run.completed 生命周期事件,presentation.status 会一直停在 "active"。
    // 收尾口径:①事件已给终态;②历史回合(非最后一轮,同页早已跑完);③最后一轮且流已停。
    // 不能只看 context.loading —— 否则新一轮开跑时,旧回合的轨迹会倒退回"进行中"。
    const runDone =
      presentation.status === "done" || !turnIsLast || context.loading === false;
    out.push({
      kind: "thinking",
      run: {
        steps,
        logs: [
          ...presentation.userStages.map((stage) => ({
            text: stage.metricsText ?? stage.summary,
          })),
          ...narrations.map((text) => ({ text })),
        ],
        done: runDone,
        currentStep,
        totalSteps: steps.length,
        presentation,
      },
    });
  };

  for (let i = 0; i < messages.length; i++) {
    const m = messages[i];
    if (m.type === "human") {
      flushRun();
      out.push({ kind: "user", text: getContentString(m.content) });
      runOpen = true;
      turnHasOfficial = false;
      turnHasWorkflow = false;
      // 本轮消息片段(到下一条 human 之前),供工作流 todos 轨道解析。
      let nextHumanIdx = messages.length;
      for (let k = i + 1; k < messages.length; k++) {
        if (messages[k].type === "human") { nextHumanIdx = k; break; }
      }
      const turnMsgs = messages.slice(i + 1, nextHumanIdx);
      // 优先级 1:工作流阶段轨道(智能体 write_todos 写的真实阶段计划)。有则当思考链主轴。
      const todoRun = buildTodoRun(turnMsgs, i === lastHumanIdx, context.loading);
      if (todoRun) {
        out.push({ kind: "thinking", run: todoRun });
        turnHasWorkflow = true;
        continue;
      }
      // 优先级 2:官方工具 trace(turn_id ≡ 本轮 human 消息 id)。匹配到且有真实步骤才用
      // (空 presentation 不如兜底轨道信息多);匹配不上(如刷新后 store 已清)自动回退兜底。
      const presentation = typeof m.id === "string" ? presentations[m.id] : undefined;
      turnHasOfficial = !!presentation && presentation.userStages.length > 0;
      turnHasWorkflow = turnHasOfficial;
      if (presentation && turnHasOfficial) {
        appendOfficialTrace(presentation, turnMsgs, i === lastHumanIdx);
      }
      continue;
    }
    if (m.type === "ai") {
      runOpen = true;
      const calls = toolCallsOf(m);
      let nextHumanIdx = messages.length;
      for (let k = i + 1; k < messages.length; k++) {
        if (messages[k].type === "human") { nextHumanIdx = k; break; }
      }
      const turnTail = messages.slice(i, nextHumanIdx);
      const rawProse = proseOf(m.content);
      const prose = hasCJK(rawProse) ? rawProse : "";
      const processNarration = isProcessNarration(turnTail, 0);
      const narration = processNarration && prose ? compactNarration(prose) : undefined;
      if (processNarration && narration && calls.length === 0) queuedNarration = narration;
      if (!turnHasWorkflow) {
        let narrationAttached = false;
        for (const c of calls) {
          // write_todos 是规划工具(它产出的阶段计划已由工作流轨道单独渲染),不作为兜底工具步。
          if (c.name === "write_todos") continue;
          const label = toolLabel(c.name, c.args); // task → 已并入 subagent 细分
          const state: Atom["state"] = c.id && errored.has(c.id)
            ? "error"
            : c.id && answered.has(c.id)
              ? "done"
              : "active";
          atoms.push({
            name: label,
            state,
            // 同一条 AI 消息并行调用多个工具时只挂一次过程说明，避免重复刷屏。
            ...(!narrationAttached && (narration || queuedNarration)
              ? { description: narration ?? queuedNarration }
              : {
                  description:
                    c.name === "task"
                      ? "委派子助手在隔离上下文中处理这步重活。"
                      : toolPresentation(c.name)?.intent,
                }),
          });
          narrationAttached = true;
          queuedNarration = undefined;
          // 写类工具只存中文 label,不回显 payload;task 按读类处理(args 无凭证)。
          const logText = WRITE_TOOLS.has(c.name) ? label : safeArgsLog(label, c.args);
          logs.push({ text: logText });
        }
        if (processNarration && prose) logs.push({ text: prose });
      }
      // 纯英文 prose 是子代理/模型的英文脚手架旁白(过程噪声),既不落轨迹也不进对话流:
      // 保持 run 打开,让后续工具继续累积到同一条思考链——不因一句英文旁白把轨迹提前切断。
      // 中文过程旁白同样属于 deepagents 的工作过程，只进入轨迹；本轮最后一条、后面已无
      // 工具调用的中文文本才是正式答复气泡。
      if (prose && !processNarration) {
        // 兜底轨道在回答落地前先落轨迹(user → thinking → ai),与官方轨道的呈现次序一致,
        // 也与 Claude Code / Codex 的"先看到过程、再看到答案"一致。
        flushRun();
        // 去重:结构化输出失败时,模型可能把同一份汇总吐好几遍(观察到重复 4 次),
        // 或流式累积产生内容相同的相邻 AI 段。相邻 kind:"ai" 文本完全相同则不重复入列,
        // 避免同一段话在时间线里连刷多屏。
        const prev = out[out.length - 1];
        if (!(prev && prev.kind === "ai" && prev.text === prose)) {
          out.push({ kind: "ai", text: prose });
        }
      }
      // 意图分流按钮(§2):xhs_panel 块 → 可点选项 timeline 项(紧跟在 prose 后)。
      const panelActions = processNarration ? [] : panelOf(m.content);
      if (panelActions.length) {
        out.push({ kind: "panel", actions: panelActions });
      }
      continue;
    }
    if (m.type === "tool") {
      // 发现工具(本地/线上笔记检索)的结果渲染成可勾选采纳的卡片网格。相邻结果仍合并为
      // 一个 discovery 项，但同 note_id 必须走 exact-pair 合并：后到的完整身份整体覆盖。
      const cid = (m as { tool_call_id?: string }).tool_call_id;
      const toolName = cid ? toolNameById.get(cid) : undefined;
      if (toolName && DISCOVERY_TOOLS.has(toolName)) {
        const notes = parseDiscoveryResults(m.content);
        if (notes.length) {
          const last = out[out.length - 1];
          if (last && last.kind === "discovery") {
            const merged = mergeDiscoveryMaterials(
              [last, { kind: "discovery", notes }],
              new Map(),
            );
            last.notes.splice(0, last.notes.length, ...merged);
          } else {
            out.push({ kind: "discovery", notes });
          }
        }
      }
      // 其它 tool 消息不直接产 item —— 其效果已经过 answered 反映到步骤状态。
    }
  }
  flushRun();
  if (context.loading && !out.some((item) => item.kind === "thinking" && !item.run.done)) {
    out.push({
      kind: "thinking",
      run: {
        steps: [{ label: "正在查素材和历史数据", state: "active" }],
        logs: [],
        done: false,
        currentStep: 1,
        totalSteps: 1,
      },
    });
  }
  if (context.error) {
    out.push({ kind: "error", text: safeVisibleText(context.error) || "响应失败，请稍后重试" });
  }
  return out;
}

// ── 收录(adopt_online_notes)结果解析 ────────────────────────────────────────
// adopt_online_notes 是写类工具:它只在思考链里显示中文 label「采纳线上笔记」,其**结果**
// (JSON {ok, results, errors, next_step})此前无任何 UI 消费 → 用户点「收录」后屏上毫无反馈
// (报告的 bug)。这里把最新一次采纳的 tool 结果解析成结局对象,驱动居中「收录完成」结果弹窗。

const ADOPT_TOOL = "adopt_online_notes";

// 建 tool_call_id → 工具名 的映射(AI 消息的 tool_calls 里声明)。
function buildToolNameById(messages: Message[]): Map<string, string> {
  const byId = new Map<string, string>();
  for (const m of messages) {
    if (m.type !== "ai") continue;
    for (const c of ((m as { tool_calls?: ToolCall[] }).tool_calls ?? [])) {
      if (c && typeof c.name === "string" && c.id) byId.set(c.id, c.name);
    }
  }
  return byId;
}

interface AdoptResultRow {
  note_id?: unknown;
  title?: unknown;
  adopted?: unknown;
  already_adopted?: unknown;
  resource_id?: unknown;
  resource_version?: unknown;
}
interface AdoptErrorRow {
  note_id?: unknown;
  title?: unknown;
  error?: unknown;
}
interface AdoptPayload {
  ok?: unknown;
  results?: unknown;
  errors?: unknown;
}

function str(v: unknown): string {
  return typeof v === "string" ? v : "";
}

// 把一条 adopt_online_notes tool 结果的 JSON 解析成结局对象。健壮:非法 JSON / 形状不符 → null。
function parseAdoptionPayload(callId: string, content: Message["content"]): AdoptionOutcome | null {
  const text = getContentString(content);
  if (!text) return null;
  let payload: AdoptPayload;
  try {
    payload = JSON.parse(text) as AdoptPayload;
  } catch {
    return null;
  }
  const results = Array.isArray(payload.results) ? (payload.results as AdoptResultRow[]) : [];
  const errorRows = Array.isArray(payload.errors) ? (payload.errors as AdoptErrorRow[]) : [];
  // 成功入库的 note_id 集合:用于判定 errors 里哪些是「真失败」(从未入库),哪些只是二级告警
  // (已入库但飞书同步/关联建边失败 —— 库记录仍在,不算收录失败)。
  const adoptedIds = new Set<string>();
  for (const r of results) {
    if (r && r.adopted === true) {
      const id = str(r.note_id);
      if (id) adoptedIds.add(id);
    }
  }

  const rows: AdoptionRow[] = [];
  for (const r of results) {
    if (!r || r.adopted !== true) continue;
    const noteId = str(r.note_id);
    rows.push({
      note_id: noteId,
      title: str(r.title) || noteId,
      // already_adopted=库里早有 → 跳过;否则本次新收录 → 成功。
      outcome: r.already_adopted === true ? "skipped" : "success",
    });
  }

  // 真失败:error 行的 note_id 不在成功集合里(那些是 DB_ADOPT_FAILED / 缺 note_id)。
  // 每个失败 note_id 只列一行,取其第一条错误信息。已入库 note 的飞书/关联告警不计失败。
  const failedSeen = new Set<string>();
  for (const e of errorRows) {
    if (!e) continue;
    const noteId = str(e.note_id);
    if (adoptedIds.has(noteId)) continue; // 二级告警(已入库),不算失败
    if (failedSeen.has(noteId)) continue; // 同一 note 的多条错误只列一次
    failedSeen.add(noteId);
    rows.push({
      note_id: noteId,
      // 后端失败行现也回带 title(兜底为 note_id);缺失时再退化。StudioContext 还会用素材栏兜底。
      title: str(e.title) || noteId || "未知笔记",
      outcome: "failed",
      error: str(e.error) || "收录失败",
    });
  }

  const successCount = rows.filter((r) => r.outcome === "success").length;
  const skippedCount = rows.filter((r) => r.outcome === "skipped").length;
  const failedRows = rows.filter((r) => r.outcome === "failed");
  // 空结局(既无成功/跳过也无失败,如 selected_notes 为空的 ok:false)不弹窗。
  if (rows.length === 0) return null;
  return {
    callId,
    rows,
    successCount,
    skippedCount,
    failedCount: failedRows.length,
    failedNoteIds: failedRows.map((r) => r.note_id).filter(Boolean),
  };
}

/** 取消息流里**最新一次** adopt_online_notes 的采纳结局;无采纳/结果为空 → null。
 *  从后往前找第一条 adopt 工具结果消息即止(最新一次采纳)。 */
export function parseLatestAdoption(messages: Message[]): AdoptionOutcome | null {
  const toolNameById = buildToolNameById(messages);
  for (let i = messages.length - 1; i >= 0; i--) {
    const m = messages[i];
    if (m.type !== "tool") continue;
    const cid = (m as { tool_call_id?: string }).tool_call_id;
    if (!cid || toolNameById.get(cid) !== ADOPT_TOOL) continue;
    return parseAdoptionPayload(cid, m.content);
  }
  return null;
}

export interface AdoptedResourceIdentity {
  resource_id: string;
  resource_version: number;
}

/** 全流程里已成功采纳的线上笔记 note_id → 精确资源身份映射(跨所有 adopt 结果累积)。 */
export function adoptedNoteResourceIdentities(messages: Message[]): Map<string, AdoptedResourceIdentity> {
  const toolNameById = buildToolNameById(messages);
  const out = new Map<string, AdoptedResourceIdentity>();
  for (const m of messages) {
    if (m.type !== "tool") continue;
    const cid = (m as { tool_call_id?: string }).tool_call_id;
    if (!cid || toolNameById.get(cid) !== ADOPT_TOOL) continue;
    const text = getContentString(m.content);
    if (!text) continue;
    try {
      const payload = JSON.parse(text) as AdoptPayload;
      const results = Array.isArray(payload.results) ? (payload.results as AdoptResultRow[]) : [];
      for (const r of results) {
        if (!r || r.adopted !== true) continue;
        const id = str(r.note_id).trim();
        const rid = str(r.resource_id).trim();
        const version = r.resource_version;
        if (
          id && rid &&
          typeof version === "number" &&
          Number.isInteger(version) &&
          version > 0
        ) {
          out.set(id, { resource_id: rid, resource_version: version });
        }
      }
    } catch {
      continue;
    }
  }
  return out;
}

function exactNoteIdentity(note: DiscoveryNote): AdoptedResourceIdentity | null {
  return typeof note.resource_id === "string" &&
    note.resource_id.trim().length > 0 &&
    typeof note.resource_version === "number" &&
    Number.isInteger(note.resource_version) &&
    note.resource_version > 0
    ? {
        resource_id: note.resource_id.trim(),
        resource_version: note.resource_version,
      }
    : null;
}

/**
 * 按消息时间顺序合并素材工作台。后到的完整 exact identity 是更新后的权威身份，必须整对
 * 覆盖；缺 id 或缺 version 的记录只能更新展示字段，绝不能与旧字段拼成一对。采纳工具的
 * 返回值是最终写库结果，优先级最高并无条件整体覆盖 discovery 身份。
 */
export function mergeDiscoveryMaterials(
  timeline: TimelineItem[],
  adoptedIdentities: ReadonlyMap<string, AdoptedResourceIdentity>,
): DiscoveryNote[] {
  const byId = new Map<string, DiscoveryNote>();
  for (const item of timeline) {
    if (item.kind !== "discovery") continue;
    for (const incoming of item.notes) {
      const existing = byId.get(incoming.note_id);
      const incomingIdentity = exactNoteIdentity(incoming);
      const existingIdentity = existing ? exactNoteIdentity(existing) : null;
      const merged: DiscoveryNote = {
        ...(existing ?? {}),
        ...incoming,
        ...(existing?.already_local === true || incoming.already_local === true
          ? { already_local: true }
          : {}),
      };
      if (incomingIdentity) {
        merged.resource_id = incomingIdentity.resource_id;
        merged.resource_version = incomingIdentity.resource_version;
      } else if (existingIdentity) {
        merged.resource_id = existingIdentity.resource_id;
        merged.resource_version = existingIdentity.resource_version;
      } else {
        delete merged.resource_id;
        delete merged.resource_version;
      }
      byId.set(incoming.note_id, merged);
    }
  }

  for (const [noteId, identity] of adoptedIdentities) {
    const existing = byId.get(noteId);
    if (!existing) continue;
    byId.set(noteId, {
      ...existing,
      already_local: true,
      resource_id: identity.resource_id,
      resource_version: identity.resource_version,
    });
  }
  return Array.from(byId.values());
}
