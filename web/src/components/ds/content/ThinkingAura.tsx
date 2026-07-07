"use client";

import { useEffect, useRef, useState, type CSSProperties, type HTMLAttributes } from "react";

/**
 * ThinkingAura — the agent's visible work trace, rendered Claude Code / Codex 式:
 * 运行中顶部有走秒计时(「正在思考 · Ns」)+ 当前步 spinner + 精确「第 N / M 步」指针;
 * 每一步逐行冒出,完成后降噪为灰色 ✓ 并展开 描述 / ↳ 结果;整轮结束折叠成单行
 * 「🍠 ✓ 思考了 Ns · 查了 N 处」,点击可展开完整轨迹。可选「查看做了什么」日志。
 *
 * 数据由真实后端 trace 流驱动(steps 随事件增长、状态 active→done),本组件只负责把它
 * 呈现成可读的流式工作轨迹——不自造步骤、不虚构进度。
 */
type StepState = "done" | "active" | "pending" | "error";

export interface ThinkingStep {
  label: string;
  state?: StepState;
  description?: string;
  result?: string;
}

export type ThinkingLog = string | { time?: string; text?: string };

export interface ThinkingAuraProps extends HTMLAttributes<HTMLDivElement> {
  title?: string;
  steps?: ThinkingStep[];
  logs?: ThinkingLog[] | null;
  defaultOpen?: boolean;
  defaultCollapsed?: boolean;
  /** 当前进行到第几步(1-based)。>0 且未全部完成时,顶栏显示"第 N / M 步"精确进度指针。 */
  currentStep?: number;
  /** 已知总步数。 */
  totalSteps?: number;
  /** 整轮是否已结束(全部步骤完成/失败)。false=运行中,显示走秒计时与进度指针。 */
  running?: boolean;
}

const stateColor: Record<StepState, string> = {
  done: "var(--success)",
  active: "var(--primary)",
  pending: "var(--text-subtle)",
  error: "var(--danger, #e5484d)",
};
const stateIcon: Record<StepState, string> = { done: "✓", active: "◐", pending: "○", error: "✕" };

export function ThinkingAura({
  title = "工作轨迹",
  steps = [],
  logs = null,
  defaultOpen = false,
  defaultCollapsed = false,
  currentStep = 0,
  totalSteps = 0,
  running = false,
  style = {},
  ...rest
}: ThinkingAuraProps) {
  const [open, setOpen] = useState(defaultOpen);
  const [collapsedState, setCollapsedState] = useState({
    source: defaultCollapsed,
    value: defaultCollapsed,
  });
  const collapsed = collapsedState.source === defaultCollapsed ? collapsedState.value : defaultCollapsed;
  const setCollapsed = (value: boolean) => setCollapsedState({ source: defaultCollapsed, value });

  // ── 走秒计时:像 Claude Code 那样让"思考了多久"可见。运行中每 200ms tick;整轮结束后
  //    冻结在最后测得的秒数。历史/刷新后加载的已完成轮我们没测到时长 → 秒数为 null,
  //    折叠摘要只显示"查了 N 处"(绝不编造耗时,遵守真实数据铁律)。 ──
  // startedAtRef 只在 effect 内读写(不在 render 期读 ref,满足 react-hooks/refs);
  // 渲染只消费 elapsedSec 这个 state —— 它在计时开始前为 null,故天然区分"从未开始"。
  const startedAtRef = useRef<number | null>(null);
  const [elapsedSec, setElapsedSec] = useState<number | null>(null);
  useEffect(() => {
    if (!running) return undefined;
    if (startedAtRef.current == null) startedAtRef.current = Date.now();
    const tick = () => {
      const start = startedAtRef.current;
      if (start != null) setElapsedSec(Math.max(0, Math.round((Date.now() - start) / 1000)));
    };
    tick();
    const id = window.setInterval(tick, 200);
    return () => window.clearInterval(id);
  }, [running]);

  // 未开始计时(历史/刷新后加载的已完成轮)elapsedSec 仍为 null → 折叠摘要省略"思考了 Ns"。
  const measuredSec = elapsedSec;
  const stepCount = steps.length;

  // 折叠摘要单行:🍠 ✓ 思考了 Ns · 查了 N 处(未测到耗时则省略"思考了 Ns")。
  if (collapsed) {
    const summary =
      measuredSec != null
        ? `思考了 ${measuredSec}s · 查了 ${stepCount} 处`
        : title && title !== "工作轨迹"
          ? title
          : `查了 ${stepCount} 处`;
    return (
      <div
        onClick={() => setCollapsed(false)}
        style={{
          display: "inline-flex", alignItems: "center", gap: "0.5rem", cursor: "pointer",
          background: "var(--surface-card)", border: "1px solid var(--border-coral)",
          borderRadius: "var(--radius-xl)", boxShadow: "var(--shadow-sm)", padding: "0.5rem 0.75rem",
          fontFamily: "var(--font-mono)",
        }}
        {...rest}
      >
        <span style={{ color: "var(--success)", fontWeight: 700 }}>✓</span>
        <span style={{ fontWeight: "var(--weight-semibold)" as CSSProperties["fontWeight"], fontSize: "var(--text-2xs)", color: "var(--text-muted)" }}>
          🍠 {summary}
        </span>
        <span style={{ color: "var(--text-subtle)", fontSize: "var(--text-2xs)" }}>▾</span>
      </div>
    );
  }

  // 精确进度指针:运行中且已知步数时,展示"第 N / M 步"(忠实真实事件,不虚构未来步)。
  const showProgress = running && totalSteps > 0 && currentStep > 0;

  return (
    <div
      style={{
        background: "var(--surface-card)",
        border: "1px solid var(--border-coral)",
        borderRadius: "var(--radius-xl)",
        boxShadow: "var(--shadow-sm)",
        padding: "0.875rem",
        width: "100%",
        ...style,
      }}
      {...rest}
    >
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: "0.75rem" }}>
        <div style={{ display: "flex", alignItems: "center", gap: "0.6rem", minWidth: 0 }}>
          <span style={{ position: "relative", display: "inline-flex", width: 10, height: 10, flexShrink: 0 }}>
            {running && (
              <span style={{ position: "absolute", inset: 0, borderRadius: "var(--radius-full)", background: "var(--primary)", animation: "xhs-ping 1.4s var(--ease-out) infinite" }} />
            )}
            <span style={{ position: "relative", borderRadius: "var(--radius-full)", width: 10, height: 10, background: running ? "var(--primary)" : "var(--success)" }} />
          </span>
          <span style={{ fontWeight: "var(--weight-bold)" as CSSProperties["fontWeight"], fontSize: "var(--text-xs)", color: "var(--text-body)", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
            {running ? "正在思考" : title}
          </span>
          {/* 走秒计时:运行中显示已思考多少秒(Claude Code 式)。 */}
          {running && measuredSec != null && (
            <span className="font-tabular" style={{ flexShrink: 0, fontSize: "var(--text-2xs)", color: "var(--text-subtle)" }}>· {measuredSec}s</span>
          )}
          {showProgress && (
            <span
              className="font-tabular"
              style={{
                flexShrink: 0, fontSize: "var(--text-2xs)", fontWeight: "var(--weight-semibold)" as CSSProperties["fontWeight"],
                color: "var(--primary)", background: "var(--accent-surface)", borderRadius: "var(--radius-full)",
                padding: "1px 8px", letterSpacing: "var(--tracking-tight)",
              }}
            >
              第 {Math.min(currentStep, totalSteps)} / {totalSteps} 步
            </span>
          )}
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: "0.5rem", flexShrink: 0 }}>
          {logs && (
            <button
              onClick={() => setOpen((o) => !o)}
              style={{ background: "none", border: "none", cursor: "pointer", color: "var(--primary)", fontWeight: "var(--weight-semibold)" as CSSProperties["fontWeight"], fontSize: "var(--text-2xs)", display: "inline-flex", alignItems: "center", gap: "0.2rem" }}
            >
              {open ? "收起记录 ▴" : "查看做了什么 ▾"}
            </button>
          )}
          {/* 已完成时给一个收起入口,折叠成单行摘要。 */}
          {!running && (
            <button
              onClick={() => setCollapsed(true)}
              aria-label="收起工作轨迹"
              style={{ background: "none", border: "none", cursor: "pointer", color: "var(--text-subtle)", fontSize: "var(--text-2xs)", display: "inline-flex", alignItems: "center" }}
            >
              收起 ▴
            </button>
          )}
        </div>
      </div>

      {/* 步骤列 —— 左侧描边模拟流式轨迹;每步逐行呈现,当前步 spinner,完成步灰色 ✓ + 描述 + ↳ 结果。 */}
      <div style={{ display: "flex", flexDirection: "column", gap: "0.65rem", paddingLeft: "0.4rem", borderLeft: "2px solid var(--border)" }}>
        {steps.map((s, i) => {
          const st: StepState = s.state || "pending";
          return (
            <div key={i} className="fade-up" style={{ display: "grid", gridTemplateColumns: "14px 1fr", columnGap: "0.5rem", rowGap: "0.25rem", fontSize: "var(--text-xs)" }}>
              <span style={{ width: 14, textAlign: "center", display: "inline-block", color: stateColor[st], animation: st === "active" ? "spin 1.4s linear infinite" : "none" }}>{stateIcon[st]}</span>
              <div style={{ display: "flex", flexDirection: "column", gap: "0.25rem", minWidth: 0 }}>
                <span style={{ color: st === "done" ? "var(--text-muted)" : stateColor[st], fontWeight: (st === "active" ? "var(--weight-semibold)" : "var(--weight-bold)") as CSSProperties["fontWeight"] }}>{s.label}</span>
                {s.description && (
                  <span style={{ color: "var(--text-subtle)", lineHeight: "var(--leading-relaxed)" }}>
                    {s.description}
                  </span>
                )}
                {s.result && (
                  <span style={{ color: "var(--text-muted)", lineHeight: "var(--leading-relaxed)", display: "inline-flex", gap: "0.35rem" }}>
                    <span style={{ color: "var(--text-subtle)", flexShrink: 0 }}>↳</span>
                    <span>{s.result}</span>
                  </span>
                )}
              </div>
            </div>
          );
        })}
      </div>

      {logs && open && (
        <div
          style={{
            marginTop: "0.7rem",
            borderTop: "1px solid var(--border)",
            paddingTop: "0.6rem",
            display: "flex",
            flexDirection: "column",
            gap: "0.4rem",
            fontFamily: "var(--font-mono)",
            fontSize: "var(--text-2xs)",
            color: "var(--text-subtle)",
            background: "var(--oats-light)",
            borderRadius: "var(--radius-sm)",
            padding: "0.6rem",
            maxHeight: 160,
            overflowY: "auto",
          }}
        >
          {logs.map((l, i) => {
            const isObj = typeof l === "object" && l !== null;
            const time = isObj ? l.time : undefined;
            const text = isObj ? l.text : l;
            return (
              <div key={i} style={{ display: "flex", gap: "0.4rem" }}>
                {time && <span style={{ color: "var(--primary)", fontWeight: "var(--weight-bold)" as CSSProperties["fontWeight"], flexShrink: 0 }}>[{time}]</span>}
                <span>{text}</span>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
