import type { Message } from "@langchain/langgraph-sdk";
import { getContentString } from "@/components/thread/utils";
import type { TracePresentation } from "@/lib/agent-trace";
import { parseXhsBlocks } from "@/lib/xhs-blocks";

export interface ThinkingStep {
  label: string;
  state: "done" | "active" | "pending";
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
  "save_performance_metric",
  "save_session_snapshot",
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

// 工具名 → 中文语义。覆盖 data_foundation/tools.py 与 tools/feishu_actions.py 两来源。
const TOOL_LABELS: Record<string, string> = {
  semantic_search_resources: "按语义找相关素材",
  search_resources: "按关键词补查素材",
  search_local_note_cards: "检索本地笔记卡",
  get_resource: "打开原文细看",
  graph_expand: "顺着图谱找关联",
  save_generated_topic: "保存选题",
  save_generated_copy: "保存文案",
  save_user_feedback: "沉淀反馈",
  save_performance_metric: "沉淀效果指标",
  save_session_snapshot: "保存会话快照",
  get_resource_performance: "读取效果表现",
  get_operations_data: "读取运营数据",
  get_data_foundation_status: "读取数据底座状态",
  sync_feishu_resources: "同步飞书资源",
  sync_copy_to_feishu: "同步文案到飞书",
  sync_topic_to_feishu: "同步选题到飞书",
  sync_diagnosis_to_feishu: "同步诊断到飞书",
  send_review_notification: "发送审阅通知",
  adopt_online_notes: "采纳线上笔记",
  search_xhs_online: "搜索小红书线上",
  lark_cli: "飞书 CLI 操作",
};

// task 委派:按 subagent_type 细化;未知/缺失回退通用。
const SUBAGENT_LABELS: Record<string, string> = {
  "knowledge-atom-retriever": "请知识检索助手查证据",
  "persona-distiller": "请风格提炼助手看样本",
  "benchmark-analyst": "请对标分析助手拆爆款",
  "expert-panel-debater": "请专家会商助手给判断",
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
  return TOOL_LABELS[name] ?? name;
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
    // 本地卡带真实 resource_id(local_cards.hydrate_note_card 输出);线上卡通常没有。
    resource_id: typeof r.resource_id === "string" && r.resource_id.trim() ? r.resource_id.trim() : undefined,
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

export function deriveTimeline(messages: Message[], context: TimelineContext = {}): TimelineItem[] {
  const out: TimelineItem[] = [];
  const hasOfficialTrace = Object.keys(context.tracePresentationsByTurnId ?? {}).length > 0;

  // 全局:已答的 tool_call_id 集合(按 tool_call_id 配对,不靠顺序)。
  // 同时记录每个 tool_call_id 对应的工具名,供 tool 消息判断是否是发现工具(要渲染卡片网格)。
  const answered = new Set<string>();
  const toolNameById = new Map<string, string>();
  for (const m of messages) {
    if (m.type === "tool") {
      const cid = (m as { tool_call_id?: string }).tool_call_id;
      if (cid) answered.add(cid);
    }
    if (m.type === "ai") {
      for (const c of ((m as { tool_calls?: ToolCall[] }).tool_calls ?? [])) {
        if (c && typeof c.name === "string" && c.id) toolNameById.set(c.id, c.name);
      }
    }
  }

  // 一轮内累积的原子步骤记录(渲染前折叠)。
  type Atom = { name: string; done: boolean };
  let atoms: Atom[] = [];
  let logs: ThinkingLog[] = [];
  let runOpen = false;

  // 把原子记录按「同名连续」折叠成语义步骤;每组状态 = 组内全部 done 才 done。
  const foldSteps = (): ThinkingStep[] => {
    const steps: ThinkingStep[] = [];
    let i = 0;
    while (i < atoms.length) {
      const name = atoms[i].name;
      let allDone = atoms[i].done;
      let j = i + 1;
      while (j < atoms.length && atoms[j].name === name) {
        allDone = allDone && atoms[j].done;
        j++;
      }
      steps.push({ label: name, state: allDone ? "done" : "active" });
      i = j;
    }
    return steps;
  };

  const buildRunItem = (): TimelineItem | null => {
    if (!runOpen || atoms.length === 0) return null;
    const allAtomsDone = atoms.length > 0 && atoms.every((a) => a.done);
    return { kind: "thinking", run: { steps: foldSteps(), logs, done: allAtomsDone } };
  };

  const resetRun = () => {
    atoms = [];
    logs = [];
    runOpen = false;
  };

  const flushRun = () => {
    if (hasOfficialTrace) {
      resetRun();
      return;
    }
    const item = buildRunItem();
    if (item) out.push(item);
    resetRun();
  };

  const appendOfficialTrace = (turnId: string | undefined) => {
    if (!turnId) return;
    const presentation = context.tracePresentationsByTurnId?.[turnId];
    if (!presentation) return;
    out.push({
      kind: "thinking",
      run: {
        steps: presentation.userStages.map((stage) => ({
          label: stage.title,
          state: presentation.status === "done" ? "done" : "active",
          description: stage.intent,
          result: stage.resultText,
        })),
        logs: presentation.userStages.map((stage) => ({
          text: stage.metricsText ?? stage.summary,
        })),
        done: presentation.status === "done",
        presentation,
      },
    });
  };

  for (const m of messages) {
    if (m.type === "human") {
      flushRun();
      out.push({ kind: "user", text: getContentString(m.content) });
      runOpen = true;
      continue;
    }
    if (m.type === "ai") {
      runOpen = true;
      const calls = ((m as { tool_calls?: ToolCall[] }).tool_calls ?? []).filter(
        (c) => c && typeof c.name === "string",
      );
      if (!hasOfficialTrace) {
        for (const c of calls) {
          const label = toolLabel(c.name, c.args); // task → 已并入 subagent 细分
          const done = !!(c.id && answered.has(c.id));
          atoms.push({ name: label, done });
          // 写类工具只存中文 label,不回显 payload;task 按读类处理(args 无凭证)。
          const logText = WRITE_TOOLS.has(c.name) ? label : safeArgsLog(label, c.args);
          logs.push({ text: logText });
        }
      }
      const prose = proseOf(m.content);
      if (prose) {
        // 去重:结构化输出失败时,模型可能把同一份汇总吐好几遍(观察到重复 4 次),
        // 或流式累积产生内容相同的相邻 AI 段。相邻 kind:"ai" 文本完全相同则不重复入列,
        // 避免同一段话在时间线里连刷多屏。
        const prev = out[out.length - 1];
        if (!(prev && prev.kind === "ai" && prev.text === prose)) {
          out.push({ kind: "ai", text: prose });
        }
        appendOfficialTrace(typeof m.id === "string" ? m.id : undefined);
      }
      // 意图分流按钮(§2):xhs_panel 块 → 可点选项 timeline 项(紧跟在 prose 后)。
      const panelActions = panelOf(m.content);
      if (panelActions.length) {
        out.push({ kind: "panel", actions: panelActions });
      }
      continue;
    }
    if (m.type === "tool") {
      // 发现工具(本地/线上笔记检索)的结果渲染成可勾选采纳的卡片网格。合并相邻的发现结果
      // (本地+线上两路)到同一 discovery 项,按 note_id 去重,保留最先出现的(通常本地在前)。
      const cid = (m as { tool_call_id?: string }).tool_call_id;
      const toolName = cid ? toolNameById.get(cid) : undefined;
      if (toolName && DISCOVERY_TOOLS.has(toolName)) {
        const notes = parseDiscoveryResults(m.content);
        if (notes.length) {
          const last = out[out.length - 1];
          if (last && last.kind === "discovery") {
            const seen = new Set(last.notes.map((n) => n.note_id));
            for (const n of notes) if (!seen.has(n.note_id)) { last.notes.push(n); seen.add(n.note_id); }
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
      },
    });
  }
  if (context.error) {
    out.push({ kind: "error", text: safeVisibleText(context.error) || "响应失败，请稍后重试" });
  }
  return out;
}
