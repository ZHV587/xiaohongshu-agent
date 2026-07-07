import type { Message } from "@langchain/langgraph-sdk";
import { getContentString } from "@/components/thread/utils";
import type { TracePresentation } from "@/lib/agent-trace";
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
  "content-system-ingestor": "请内容入库助手收录素材",
  "curriculum-designer": "请课程设计助手搭框架",
  "copywriting-coprocessor": "请文案协处理助手起稿",
  "imitation-writer": "请仿写助手照范本写成品",
};

// 步骤一句话意图(按中文 label 键):让「兜底轨道」也像 Claude Code/Codex 那样每步说清
// "为什么做这一步",而不是只甩一个动作名(黑盒感的主因)。仅补真实工具/委派对应的说明,
// 不虚构内容;缺失则不显示描述。
const STEP_DESCRIPTIONS: Record<string, string> = {
  "按语义找相关素材": "从数据底座按语义相似度召回可用笔记和历史素材",
  "按关键词补查素材": "用关键词补一轮检索,避免只依赖语义相似的一组",
  "检索本地笔记卡": "在本地素材库里找能支撑本轮主题的历史笔记",
  "打开原文细看": "打开候选素材原文,核对关键表达、数据与上下文",
  "顺着图谱找关联": "沿素材关联图找相邻线索,补单条素材的信息盲区",
  "保存选题": "把本轮生成的选题沉淀入库,便于后续继续编辑/同步",
  "保存文案": "把本轮文案草稿沉淀入库",
  "沉淀反馈": "把用户反馈沉淀下来,供后续学习复用",
  "沉淀效果指标": "把发布后的效果数据回填沉淀",
  "同步文案到飞书": "把文案同步到飞书生产线",
  "同步选题到飞书": "把选题同步到飞书生产线",
  "同步诊断到飞书": "把诊断结果同步到飞书生产线",
  "发送审阅通知": "在飞书发起人工审阅通知",
  "采纳线上笔记": "把线上检索到的可用笔记收录进素材库(可追溯)",
  "搜索小红书线上": "在线检索小红书,补本地库之外的新鲜样本",
  "读取运营数据": "读取账号运营数据用于判断",
  "飞书 CLI 操作": "调用飞书 CLI 执行外部动作",
  "请知识检索助手查证据": "委派子助手隔离上下文,专门检索并核验证据",
  "请风格提炼助手看样本": "委派子助手提炼账号既有风格样本",
  "请对标分析助手拆爆款": "委派子助手拆解对标爆款的套路",
  "请专家会商助手给判断": "委派多角色专家会商给出判断",
  "请内容入库助手收录素材": "委派子助手把素材规范化收录入库",
  "请课程设计助手搭框架": "委派子助手搭内容框架",
  "请文案协处理助手起稿": "委派子助手起草并打磨文案",
  "请仿写助手照范本写成品": "委派子助手照范本套路仿写成品",
  "请子任务助手处理": "委派子助手在隔离上下文中处理这步重活",
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
      // 兜底轨道也带一句意图说明(有则显示),让每步读起来是"在干什么/为什么",不再是裸动作名。
      const description = STEP_DESCRIPTIONS[name];
      steps.push({ label: name, state: allDone ? "done" : "active", ...(description ? { description } : {}) });
      i = j;
    }
    return steps;
  };

  const buildRunItem = (): TimelineItem | null => {
    if (!runOpen || atoms.length === 0) return null;
    const allAtomsDone = atoms.length > 0 && atoms.every((a) => a.done);
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
    // 逐步映射每一步的真实状态(stage.state 来自该步终态事件),不再用 run 级状态一刀切。
    // 这样才能像 Claude Code / Codex 那样精确看出"哪几步已完成、当前正卡在第几步"。
    const steps: ThinkingStep[] = presentation.userStages.map((stage) => ({
      label: stage.title,
      state: stage.state === "error" ? "error" : stage.state, // done | active | error
      description: stage.intent,
      result: stage.resultText,
    }));
    // 进度指针:最后一个仍在 active 的步 = 当前步;全部完成 = 停在最后一步。忠实真实事件,不虚构未来步。
    const lastActive = steps.reduce((acc, s, i) => (s.state === "active" ? i : acc), -1);
    const currentStep = steps.length === 0 ? 0 : lastActive >= 0 ? lastActive + 1 : steps.length;
    // 后端目前不发 run.completed 生命周期事件,presentation.status 会一直停在 "active"。
    // 但"流是否还在跑"前端已知(context.loading):流结束即本轮思考结束 —— 据此收尾,
    // 让思考链能干净折叠成「✓ 思考了 Ns · 查了 N 处」,而不是永远显示"正在思考"。
    const runDone = presentation.status === "done" || context.loading === false;
    out.push({
      kind: "thinking",
      run: {
        steps,
        logs: presentation.userStages.map((stage) => ({
          text: stage.metricsText ?? stage.summary,
        })),
        done: runDone,
        currentStep,
        totalSteps: steps.length,
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
