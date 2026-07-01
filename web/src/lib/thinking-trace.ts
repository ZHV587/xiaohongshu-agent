import type { Message } from "@langchain/langgraph-sdk";
import { getContentString } from "@/components/thread/utils";
import { parseXhsBlocks } from "@/lib/xhs-blocks";

export interface ThinkingStep {
  label: string;
  state: "done" | "active";
}

export interface ThinkingLog {
  text: string;
}

export interface ThinkingRun {
  steps: ThinkingStep[];
  logs: ThinkingLog[];
  done: boolean;
}

export type TimelineItem =
  | { kind: "user"; text: string }
  | { kind: "thinking"; run: ThinkingRun }
  | { kind: "ai"; text: string };

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
  semantic_search_resources: "语义检索数据底座",
  search_resources: "关键词检索数据底座",
  search_local_note_cards: "检索本地笔记卡",
  get_resource: "精读素材原文",
  graph_expand: "图谱扩展关联",
  save_generated_topic: "沉淀选题入库",
  save_generated_copy: "沉淀文案入库",
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
  "knowledge-atom-retriever": "委派子任务:知识检索",
  "persona-distiller": "委派子任务:风格提炼",
};

export function toolLabel(name: string, args: unknown): string {
  if (name === "task") {
    const sub =
      args && typeof args === "object" && "subagent_type" in args
        ? (args as { subagent_type?: unknown }).subagent_type
        : undefined;
    if (typeof sub === "string" && SUBAGENT_LABELS[sub]) return SUBAGENT_LABELS[sub];
    return "委派子任务";
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

export function deriveTimeline(messages: Message[]): TimelineItem[] {
  const out: TimelineItem[] = [];

  // 全局:已答的 tool_call_id 集合(按 tool_call_id 配对,不靠顺序)。
  const answered = new Set<string>();
  for (const m of messages) {
    if (m.type === "tool") {
      const cid = (m as { tool_call_id?: string }).tool_call_id;
      if (cid) answered.add(cid);
    }
  }

  // 一轮内累积的原子步骤记录(渲染前折叠)。
  type Atom = { name: string; done: boolean };
  let atoms: Atom[] = [];
  let logs: ThinkingLog[] = [];
  let runOpen = false;
  let runDone = false;

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

  const flushRun = () => {
    if (runOpen && atoms.length > 0) {
      // spec OR: runDone = prose was seen  OR  all atoms are done
      const allAtomsDone = atoms.length > 0 && atoms.every((a) => a.done);
      out.push({ kind: "thinking", run: { steps: foldSteps(), logs, done: runDone || allAtomsDone } });
    }
    atoms = [];
    logs = [];
    runOpen = false;
    runDone = false;
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
      for (const c of calls) {
        const label = toolLabel(c.name, c.args); // task → 已并入 subagent 细分
        const done = !!(c.id && answered.has(c.id));
        atoms.push({ name: label, done });
        // 写类工具只存中文 label,不回显 payload;task 按读类处理(args 无凭证)。
        const logText = WRITE_TOOLS.has(c.name) ? label : safeArgsLog(label, c.args);
        logs.push({ text: logText });
      }
      const prose = proseOf(m.content);
      if (prose) {
        runDone = true;
        flushRun();
        out.push({ kind: "ai", text: prose });
      }
      continue;
    }
    // tool 消息不直接产 item —— 其效果已经过 answered 反映到步骤状态。
  }
  flushRun();
  return out;
}
