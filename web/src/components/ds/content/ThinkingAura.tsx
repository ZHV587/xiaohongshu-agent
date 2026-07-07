"use client";

import { useState, type CSSProperties, type HTMLAttributes } from "react";

/**
 * ThinkingAura — the agent's visible work trace. A
 * breathing coral dot, a stepper of statuses (done / active /
 * pending), and an optional collapsible log of tool/action details.
 *
 * Faithfully ported 1:1 from 小红书文案助手 Design System/components/content/ThinkingAura.jsx.
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
  /** 整轮是否已结束(全部步骤完成/失败)。用于决定是否显示"进行中"进度指针。 */
  running?: boolean;
}

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
  const collapsedTitle = title === "工作轨迹" ? `查完 ${steps.length} 步` : title;

  if (collapsed) {
    return (
      <div
        onClick={() => setCollapsed(false)}
        style={{
          display: "inline-flex", alignItems: "center", gap: "0.5rem", cursor: "pointer",
          background: "var(--surface-card)", border: "1px solid var(--border-coral)",
          borderRadius: "var(--radius-xl)", boxShadow: "var(--shadow-sm)", padding: "0.5rem 0.75rem",
        }}
        {...rest}
      >
        <span style={{ position: "relative", display: "inline-flex", width: 8, height: 8 }}>
          <span style={{ position: "relative", borderRadius: "var(--radius-full)", width: 8, height: 8, background: "var(--success)" }} />
        </span>
        <span style={{ fontFamily: "var(--font-sans)", fontWeight: "var(--weight-semibold)" as CSSProperties["fontWeight"], fontSize: "var(--text-xs)", color: "var(--text-body)" }}>
          🍠 {collapsedTitle}
        </span>
        <span style={{ color: "var(--primary)", fontSize: "var(--text-2xs)" }}>▾</span>
      </div>
    );
  }

  const stateColor: Record<StepState, string> = {
    done: "var(--success)",
    active: "var(--primary)",
    pending: "var(--text-subtle)",
    error: "var(--danger, #e5484d)",
  };
  const stateIcon: Record<StepState, string> = { done: "✓", active: "◐", pending: "○", error: "✕" };
  // 精确进度指针:一轮尚未结束(running)且已知步数时,展示"第 N / M 步"——像 Claude Code 那样
  // 让用户一眼看出智能体正卡在第几步(忠实已发生的步骤,未运行的步不虚构总数)。
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
        <div style={{ display: "flex", alignItems: "center", gap: "0.6rem" }}>
          <span style={{ position: "relative", display: "inline-flex", width: 10, height: 10 }}>
            <span style={{ position: "absolute", inset: 0, borderRadius: "var(--radius-full)", background: "var(--primary)", animation: "xhs-ping 1.4s var(--ease-out) infinite" }} />
            <span style={{ position: "relative", borderRadius: "var(--radius-full)", width: 10, height: 10, background: "var(--primary)" }} />
          </span>
          <span style={{ fontFamily: "var(--font-sans)", fontWeight: "var(--weight-bold)" as CSSProperties["fontWeight"], fontSize: "var(--text-xs)", color: "var(--text-body)" }}>{title}</span>
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
        {logs && (
          <button
            onClick={() => setOpen((o) => !o)}
            style={{ background: "none", border: "none", cursor: "pointer", color: "var(--primary)", fontFamily: "var(--font-sans)", fontWeight: "var(--weight-semibold)" as CSSProperties["fontWeight"], fontSize: "var(--text-2xs)", display: "inline-flex", alignItems: "center", gap: "0.2rem" }}
          >
            {open ? "收起记录 ▴" : "查看做了什么 ▾"}
          </button>
        )}
      </div>

      <div style={{ display: "flex", flexDirection: "column", gap: "0.65rem" }}>
        {steps.map((s, i) => {
          const st: StepState = s.state || "pending";
          return (
            <div key={i} style={{ display: "grid", gridTemplateColumns: "14px 1fr", columnGap: "0.5rem", rowGap: "0.25rem", fontSize: "var(--text-xs)" }}>
              <span style={{ width: 14, textAlign: "center", display: "inline-block", color: stateColor[st], animation: st === "active" ? "spin 1.4s linear infinite" : "none" }}>{stateIcon[st]}</span>
              <div style={{ display: "flex", flexDirection: "column", gap: "0.25rem", minWidth: 0 }}>
                <span style={{ color: stateColor[st], fontWeight: (st === "active" ? "var(--weight-semibold)" : "var(--weight-bold)") as CSSProperties["fontWeight"] }}>{s.label}</span>
                {s.description && (
                  <span style={{ color: "var(--text-muted)", lineHeight: "var(--leading-relaxed)" }}>
                    {s.description}
                  </span>
                )}
                {s.result && (
                  <span style={{ color: "var(--text-body)", lineHeight: "var(--leading-relaxed)", background: "var(--oats-light)", border: "1px solid var(--border)", borderRadius: "var(--radius-sm)", padding: "0.35rem 0.5rem" }}>
                    结果：{s.result}
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
            maxHeight: 140,
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
