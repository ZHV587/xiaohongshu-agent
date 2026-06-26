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
      /** 可选:展开"分析详情"时的终端日志(不含时间戳,由 ThinkingAura 统一加)。 */
      logs?: (ctx: { result?: unknown; name: string }) => string[];
    };

export interface ToolRenderSpec {
  /** 思考链表现 */
  aura: AuraSpec;
  /** 富卡片渲染(独立于思考链,直接把结果渲染成卡片);无则不渲染卡片。 */
  card?: (result: unknown) => ReactNode;
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
    done: ({ name }) => `已完成 ${name || "工具"} 指令执行`,
    logs: ({ name }) => [
      `[SYSTEM] 启动底层工具 [${name || "unknown"}] 并发送参数中...`,
      "[SYSTEM] 指令执行成功，返回结果已成功注入上下文。",
    ],
  },
};

/** 工具名 → 渲染声明。新增工具卡片只改这里。 */
export const TOOL_RENDERERS: Record<string, ToolRenderSpec> = {
  // 搜索发现:富卡片(本地组/线上组),不进思考链
  search_xhs_online: { aura: "hidden", card: searchCard("search_xhs_online") },
  search_local_note_cards: { aura: "hidden", card: searchCard("search_local_note_cards") },

  // 采纳收录:思考链一步
  adopt_online_notes: {
    aura: { running: "正在采纳收录到库 + 飞书…", done: () => "已采纳收录" },
  },

  // 读爆款库:思考链一步 + 终端日志(带条数)
  read_xhs_data: {
    aura: {
      running: "正在读取飞书多维表格数据...",
      done: ({ result }) => {
        const n = arrLen(result, "rows");
        return n != null ? `已成功解析飞书多维表格 (${n} 条爆款数据)` : "已成功解析飞书多维表格";
      },
      logs: () => [
        "[SYSTEM] 正在连接飞书多维表格 API 网关...",
        "[SYSTEM] 企业自建应用凭证校验成功",
        "[SYSTEM] 正在读取多维表格数据...",
        "[SYSTEM] 数据读取完毕，正在过滤空行及无效列...",
        "[SYSTEM] 成功加载并分析爆款记录！",
      ],
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
      logs: () => [
        "[ANALYST] 调起爆款数据分析子智能体...",
        "[ANALYST] 正在对互动量(点赞数、收藏数)进行排序及分位数计算...",
        "[ANALYST] 选题规则构建完成，正在输出精炼后的选题建议...",
      ],
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
  if (path.includes("/skills/")) return HIDDEN;
  if (name && TOOL_RENDERERS[name]) return TOOL_RENDERERS[name];
  return DEFAULT;
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
