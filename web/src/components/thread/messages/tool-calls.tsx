// web/src/components/thread/messages/tool-calls.tsx
import { AIMessage, ToolMessage } from "@langchain/langgraph-sdk";
import { useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { ChevronDown, LoaderCircle, Check } from "lucide-react";
import { useStreamContext } from "@/providers/Stream";
import { getToolDisplay, extractRowCount } from "@/lib/tool-display";

// 进行中状态条：仅当该 tool_call 还没有对应的 ToolResult 时显示
export function ToolCalls({
  toolCalls,
}: {
  toolCalls: AIMessage["tool_calls"];
}) {
  const thread = useStreamContext();
  if (!toolCalls || toolCalls.length === 0) return null;

  // 已存在结果的 tool_call_id 集合
  const resolvedIds = new Set(
    thread.messages
      .filter((m): m is ToolMessage => m.type === "tool")
      .map((m) => m.tool_call_id)
      .filter(Boolean),
  );

  return (
    <div className="mx-auto flex max-w-3xl flex-col gap-2">
      {toolCalls.map((tc, idx) => {
        const display = getToolDisplay(tc.name, tc.args as Record<string, any>);
        if (display.hidden) return null;
        // 有 id 且已 resolved → 交给 ToolResult 渲染；
        // 无 id 属异常数据（正常 SDK 路径 tool_call_id 必然存在），保守显示进行中条。
        if (tc.id && resolvedIds.has(tc.id)) return null;
        return (
          <div
            key={tc.id || idx}
            className="border-border bg-card text-muted-foreground inline-flex w-fit items-center gap-2 rounded-xl border px-3.5 py-2 text-sm"
          >
            <LoaderCircle className="text-primary size-3.5 animate-spin" />
            {display.running}
          </div>
        );
      })}
    </div>
  );
}

// 完成状态条 + 可展开朴素内容
export function ToolResult({ message }: { message: ToolMessage }) {
  const [expanded, setExpanded] = useState(false);
  const [showRaw, setShowRaw] = useState(false);

  // 解析结果内容
  let parsed: any = message.content;
  let isJson = false;
  try {
    if (typeof message.content === "string") {
      parsed = JSON.parse(message.content);
      isJson = typeof parsed === "object" && parsed !== null;
    }
  } catch {
    parsed = message.content;
  }

  const rowCount = extractRowCount(message.name, message.content);
  const display = getToolDisplay(message.name, undefined, rowCount);
  if (display.hidden) return null;

  const rawStr =
    typeof message.content === "string"
      ? message.content
      : JSON.stringify(message.content, null, 2);

  const hasRows = isJson && Array.isArray(parsed?.rows) && Array.isArray(parsed?.columns);
  const hasDocuments = isJson && Array.isArray(parsed?.documents);

  return (
    <div className="mx-auto flex max-w-3xl flex-col">
      <button
        type="button"
        onClick={() => setExpanded((v) => !v)}
        className="border-border inline-flex w-fit items-center gap-2 rounded-xl border bg-[oklch(0.97_0.02_145)] px-3.5 py-2 text-sm text-[oklch(0.45_0.08_145)] transition-colors hover:opacity-90"
      >
        <Check className="size-3.5" />
        {display.done}
        <ChevronDown
          className={`size-3.5 transition-transform ${expanded ? "rotate-180" : ""}`}
        />
      </button>

      <AnimatePresence initial={false}>
        {expanded && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.2 }}
            className="overflow-hidden"
          >
            <div className="border-border mt-2 rounded-xl border bg-card p-3">
              {hasRows ? (
                <RowCards columns={parsed.columns} rows={parsed.rows} />
              ) : hasDocuments ? (
                <DocumentCards documents={parsed.documents} />
              ) : (
                <div className="text-foreground/80 text-sm leading-relaxed whitespace-pre-wrap">
                  {typeof parsed === "string" ? parsed : rawStr}
                </div>
              )}
              <button
                type="button"
                onClick={() => setShowRaw((v) => !v)}
                className="text-muted-foreground border-border mt-3 w-full border-t pt-2 text-left text-xs hover:text-foreground"
              >
                ⧉ {showRaw ? "收起原始数据" : "查看原始（开发用）"}
              </button>
              {showRaw && (
                <pre className="text-muted-foreground mt-2 max-h-64 overflow-auto rounded-lg bg-secondary p-2 text-xs whitespace-pre-wrap">
                  {rawStr}
                </pre>
              )}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

// 通用行卡：按列名平铺「列名：值」，不猜字段语义
function RowCards({ columns, rows }: { columns: string[]; rows: Record<string, any>[] }) {
  const MAX = 8;
  const shown = rows.slice(0, MAX);
  return (
    <div className="flex flex-col gap-2">
      {shown.map((row, i) => (
        <div key={i} className="border-border/60 rounded-lg border bg-secondary/40 px-3 py-2">
          {columns.map((col) => {
            const v = row[col];
            if (v == null || v === "") return null;
            const text = typeof v === "object" ? JSON.stringify(v) : String(v);
            return (
              <div key={col} className="flex gap-2 text-xs leading-relaxed">
                <span className="text-muted-foreground min-w-[3rem] flex-shrink-0">{col}</span>
                <span className="text-foreground break-all">{text}</span>
              </div>
            );
          })}
        </div>
      ))}
      {rows.length > MAX && (
        <div className="text-muted-foreground pt-1 text-center text-xs">
          还有 {rows.length - MAX} 条…
        </div>
      )}
    </div>
  );
}

function DocumentCards({ documents }: { documents: Record<string, unknown>[] }) {
  const MAX = 5;
  const shown = documents.slice(0, MAX);
  return (
    <div className="flex flex-col gap-2">
      {shown.map((doc, i) => (
        <div key={i} className="border-border/60 rounded-lg border bg-secondary/40 px-3 py-2 text-left">
          <div className="font-semibold text-xs text-foreground mb-1 break-all">{String(doc.title ?? "")}</div>
          <div className="text-muted-foreground text-xs line-clamp-3 whitespace-pre-wrap break-all">
            {String(doc.content ?? "")}
          </div>
        </div>
      ))}
      {documents.length > MAX && (
        <div className="text-muted-foreground pt-1 text-center text-xs font-medium">
          还有 {documents.length - MAX} 篇文档…
        </div>
      )}
    </div>
  );
}
