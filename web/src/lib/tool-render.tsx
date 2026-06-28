// web/src/lib/tool-render.tsx
//
// 工具渲染注册表 —— 对话里"每个工具结果怎么展示"的唯一事实源。
//
// 解耦原则:
//   - 后端工具只产出结构化数据(如 {ok, results:[...]}),不掺任何 UI 概念。
//   - 前端在这里集中声明每个工具的展示方式;ThinkingAura(思考链)、卡片渲染、
//     进行中 chip 三个消费方都读本表,不再各自硬编码工具名。
//   - 加一种新卡片/新工具展示 = 本表加一条 + (如需)写一个卡片组件,其余 UI 不动。
import type { ReactNode } from "react";
import { SearchCards, type SearchToolResult } from "@/components/thread/messages/search-cards";

/** 思考链(ThinkingAura)里的表现:hidden=不展示;否则一步,带进行中/完成文案与可选终端日志。 */
export type AuraSpec =
  | "hidden"
  | {
      running: string;
      done: (ctx: { result?: unknown; name: string }) => string;
    };

export interface ToolRenderSpec {
  /** 思考链表现 */
  aura: AuraSpec;
  /** 富卡片渲染(独立于思考链,直接把结果渲染成卡片);无则不渲染卡片。 */
  card?: (result: unknown) => ReactNode;
  /** 业务显示名:用于 HITL 审批标题等"让用户确认"的场景(中文、面向用户)。 */
  title?: string;
  /** 思考链里展示的关键入参摘要(面向用户、简短,如检索词/资源ID);无则不展示。 */
  argsSummary?: (args: Record<string, unknown>) => string | undefined;
}

/** 从 args 取一个非空字符串字段,做思考链入参摘要用。 */
function strArg(args: Record<string, unknown> | undefined, key: string): string | undefined {
  const v = args?.[key];
  return typeof v === "string" && v.trim() ? v.trim() : undefined;
}

function parse(result: unknown): Record<string, unknown> | null {
  if (result == null) return null;
  try {
    const o = typeof result === "string" ? JSON.parse(result) : result;
    return o && typeof o === "object" ? (o as Record<string, unknown>) : null;
  } catch {
    return null;
  }
}

function arrLen(result: unknown, key: string): number | null {
  const o = parse(result);
  return o && Array.isArray(o[key]) ? (o[key] as unknown[]).length : null;
}

const searchCard = (toolName: string) => (result: unknown): ReactNode => {
  const data = parse(result);
  if (!data) return null;
  return <SearchCards toolName={toolName} data={data as unknown as SearchToolResult} />;
};

const HIDDEN: ToolRenderSpec = { aura: "hidden" };

const DEFAULT: ToolRenderSpec = {
  aura: {
    running: "正在处理…",
    done: () => "已完成一步处理",
  },
};

// 检索/取证类:统一"检索中→已检索"措辞;可选 argsKey 把关键入参(检索词/ID)显示出来
const retrieval = (running: string, done: string, argsKey?: string): ToolRenderSpec => ({
  aura: { running, done: () => done },
  ...(argsKey ? { argsSummary: (a: Record<string, unknown>) => strArg(a, argsKey) } : {}),
});

/** 工具名 → 渲染声明。新增工具卡片只改这里。 */
export const TOOL_RENDERERS: Record<string, ToolRenderSpec> = {
  // 搜索发现:思考链显示"检索中→已找到 N 条"一步,同时下方渲染富卡片(本地组/线上组)
  search_xhs_online: {
    aura: {
      running: "正在检索小红书线上热门笔记…",
      done: ({ result }) => {
        const n = arrLen(result, "results");
        return n ? `已找到线上 ${n} 条笔记` : "线上暂无相关笔记";
      },
    },
    card: searchCard("search_xhs_online"),
    argsSummary: (a) => strArg(a, "keyword"),
  },
  search_local_note_cards: {
    aura: {
      running: "正在检索本地已收录笔记…",
      done: ({ result }) => {
        const n = arrLen(result, "results");
        return n ? `已找到本地 ${n} 条笔记` : "本地暂无相关笔记";
      },
    },
    card: searchCard("search_local_note_cards"),
    argsSummary: (a) => strArg(a, "keyword"),
  },

  // 采纳收录:思考链一步
  adopt_online_notes: {
    aura: { running: "正在采纳收录到库 + 飞书…", done: () => "已采纳收录" },
    title: "采纳收录线上笔记到数据库 + 飞书爆款采集库",
  },

  // ── 检索 / 取证 ──────────────────────────────
  semantic_search_resources: retrieval("正在语义检索数据底座…", "已检索到相关素材", "query"),
  search_resources: retrieval("正在关键词检索数据底座…", "已检索到相关素材", "query"),
  get_resource: retrieval("正在精读笔记原文…", "已精读笔记", "resource_id"),
  graph_expand: {
    aura: { running: "正在扩展关联图谱…", done: () => "已扩展关联上下文" },
    argsSummary: (a) => (Array.isArray(a?.resource_ids) ? `${(a.resource_ids as unknown[]).length} 个起点` : undefined),
  },
  get_resource_performance: retrieval("正在查历史效果数据…", "已读取历史效果", "resource_id"),
  get_data_foundation_status: retrieval("正在核对数据底座状态…", "已核对底座状态"),

  // ── 落库 / 同步(数据库 + 飞书镜像)──────────────
  save_generated_topic: { aura: { running: "正在保存选题到数据库…", done: () => "已保存选题" }, title: "保存选题到数据库", argsSummary: (a) => strArg(a, "direction") },
  save_generated_copy: { aura: { running: "正在保存文案到数据库…", done: () => "已保存文案" }, title: "保存文案到数据库", argsSummary: (a) => strArg(a, "title") },
  save_user_feedback: { aura: { running: "正在记录修改意见…", done: () => "已记录修改意见" } },
  save_performance_metric: { aura: { running: "正在写入效果数据…", done: () => "已写入效果数据" }, title: "写入效果数据" },
  save_session_snapshot: { aura: { running: "正在保存会话快照…", done: () => "已保存快照" } },
  sync_feishu_resources: { aura: { running: "正在同步飞书资源…", done: () => "已同步飞书资源" }, title: "同步资源到飞书" },
  sync_topic_to_feishu: { aura: { running: "正在同步选题到飞书…", done: () => "已同步飞书(选题)" }, title: "同步选题到飞书多维表格" },
  sync_copy_to_feishu: { aura: { running: "正在同步文案到飞书…", done: () => "已同步飞书(文案)" }, title: "同步文案到飞书多维表格" },
  sync_diagnosis_to_feishu: { aura: { running: "正在同步诊断到飞书…", done: () => "已同步飞书(诊断)" }, title: "同步诊断到飞书多维表格" },
  send_review_notification: { aura: { running: "正在发送飞书群审核通知…", done: () => "已发送审核通知" }, title: "发送飞书群审核通知" },
  lark_cli: { aura: { running: "正在执行飞书操作…", done: () => "已执行飞书操作" }, title: "执行飞书操作" },

  // 读爆款库:思考链一步(带条数)
  read_xhs_data: {
    aura: {
      running: "正在读取飞书多维表格数据...",
      done: ({ result }) => {
        const n = arrLen(result, "rows");
        return n != null ? `已成功解析飞书多维表格 (${n} 条爆款数据)` : "已成功解析飞书多维表格";
      },
    },
  },

  // 读知识库
  read_feishu_wiki: {
    aura: {
      running: "正在读取飞书知识库…",
      done: ({ result }) => {
        const n = arrLen(result, "documents");
        return n != null ? `已读取知识库 (${n} 篇文档)` : "已读取知识库";
      },
    },
  },

  // 子 agent 委派
  task: {
    aura: {
      running: "正在分析爆款规律…",
      done: () => "已完成爆款数据深度分析",
    },
  },

  // skills 内部文件读写:噪音,不展示
  read_file: HIDDEN,
  write_file: HIDDEN,
  edit_file: HIDDEN,
};

/** 解析某工具的渲染声明;命中 /skills/ 路径强制 hidden,未注册走 DEFAULT。 */
export function resolveToolRender(
  name?: string,
  args?: Record<string, unknown>,
): ToolRenderSpec {
  const path = String((args?.file_path ?? args?.path ?? args?.filename ?? "") || "");
  // skill 激活是"通用思考链"的信号:读取某 skill 的 SKILL.md = 智能体正在运用该技能。
  // 由消息流(read_file 调用)天然派生,与具体 skill 无耦合、零 per-skill 代码。
  const skillMatch = path.match(/\/skills\/([^/]+)\/SKILL\.md$/i);
  if (skillMatch) {
    const slug = skillMatch[1].replace(/^xhs-/, "");
    return {
      aura: {
        running: `正在调取「${slug}」技能…`,
        done: () => `已运用「${slug}」技能`,
      },
    };
  }
  if (path.includes("/skills/")) return HIDDEN; // 其它 skill 目录读写是噪音,不展示
  if (name && TOOL_RENDERERS[name]) return TOOL_RENDERERS[name];
  return DEFAULT;
}

/** HITL 审批等"让用户确认"场景的工具业务名(中文、面向用户)。
 *  优先取注册表 title;create_online_note_record 等非展示工具也在此兜底;
 *  未知工具回退到"执行操作",绝不暴露英文工具名。 */
const EXTRA_TITLES: Record<string, string> = {
  create_online_note_record: "写入笔记到飞书爆款采集库",
  sync_online_note_to_feishu: "同步线上笔记到飞书爆款采集库",
};

export function toolDisplayName(name?: string): string {
  if (!name) return "执行操作";
  const spec = TOOL_RENDERERS[name];
  if (spec?.title) return spec.title;
  if (EXTRA_TITLES[name]) return EXTRA_TITLES[name];
  return "执行操作";
}

/** HITL 参数字段的中文标签(面向用户确认);未知字段回退原 key。 */
const FIELD_LABELS: Record<string, string> = {
  notes: "笔记",
  note: "笔记",
  title: "标题",
  body: "正文",
  content: "内容",
  topic: "选题",
  topics: "选题",
  tags: "话题标签",
  table_id: "目标表",
  app_token: "多维表格",
  record_id: "记录",
  resource_id: "资源",
  summary: "摘要",
  reason: "原因",
  message: "说明",
};

export function fieldLabel(key: string): string {
  return FIELD_LABELS[key] ?? key;
}

export interface ToolCallLike {
  id?: string;
  name: string;
  args?: unknown;
  result?: unknown;
}

/** 把一组工具调用里"有富卡片且已出结果"的渲染成卡片(搜索卡片走这条活路径)。 */
export function ToolResultCards({ tools }: { tools?: ToolCallLike[] }) {
  const items = (tools || [])
    .map((t, i) => {
      const spec = resolveToolRender(t.name, t.args as Record<string, unknown>);
      if (!spec.card || t.result == null) return null;
      const node = spec.card(t.result);
      return node ? <div key={t.id || `${t.name}-${i}`}>{node}</div> : null;
    })
    .filter(Boolean);
  return items.length ? <>{items}</> : null;
}
