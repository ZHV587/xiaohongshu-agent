// web/src/lib/tool-display.ts

export interface ToolDisplay {
  /** true 表示这是内部噪音（skills 内部读写），完全不渲染 */
  hidden: boolean;
  running: string;  // 进行中文案
  done: string;     // 完成文案
}

/** 取 args 里可能的文件路径字段 */
function argPath(args: Record<string, unknown> | undefined): string {
  if (!args) return "";
  return String(args.file_path ?? args.path ?? args.filename ?? "");
}

/**
 * 由工具名 + args 推导显示信息。
 * resultCount: 若已知工具结果的行数（read_xhs_data 的 rows.length），用于完成态计数。
 */
export function getToolDisplay(
  name: string | undefined,
  args?: Record<string, unknown>,
  resultCount?: number,
): ToolDisplay {
  const path = argPath(args);

  // skills 内部操作：读写命中 /skills/ 的文件，纯噪音
  if (path.includes("/skills/")) {
    return { hidden: true, running: "", done: "" };
  }

  switch (name) {
    case "read_xhs_data":
      return {
        hidden: false,
        running: "正在读取你的爆款库…",
        done: resultCount != null ? `已读取爆款库（${resultCount} 条）` : "已读取爆款库",
      };
    case "task":
      // 子 agent 委派（baokuan-analyst 等）
      return { hidden: false, running: "正在分析爆款规律…", done: "已总结这批爆款的共性" };
    case "write_file":
    case "edit_file":
      if (path.includes("/shared/")) {
        return { hidden: false, running: "正在更新你的风格库…", done: "已更新你的风格库" };
      }
      if (path.includes("/drafts/")) {
        return { hidden: false, running: "正在保存草稿…", done: "已保存草稿" };
      }
      if (path.includes("/analysis/")) {
        return { hidden: true, running: "", done: "" }; // 中间分析文件，内部噪音
      }
      return { hidden: false, running: "正在写入…", done: "已写入" };
    case "read_file":
      // 读 /analysis/ /shared/ 等内部文件，不展示
      return { hidden: true, running: "", done: "" };
    default:
      return { hidden: false, running: "正在处理…", done: "已完成" };
  }
}

/** 从 read_xhs_data 的结果 content 里取 rows 行数；取不到返回 undefined */
export function extractRowCount(content: unknown): number | undefined {
  try {
    const obj = typeof content === "string" ? JSON.parse(content) : content;
    if (obj && Array.isArray((obj as Record<string, unknown>).rows)) return ((obj as Record<string, unknown>).rows as unknown[]).length;
  } catch {
    /* ignore */
  }
  return undefined;
}
