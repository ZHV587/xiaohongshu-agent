"use client";

import { useState, useEffect, type CSSProperties, type HTMLAttributes } from "react";

/**
 * ThinkingAura (思维微光) — the agent's live reasoning panel. A
 * breathing coral dot, a stepper of statuses (done / active /
 * pending), and an optional collapsible log of raw thoughts.
 *
 * Faithfully ported 1:1 from 小红书文案助手 Design System/components/content/ThinkingAura.jsx.
 */
type StepState = "done" | "active" | "pending";

export interface ThinkingStep {
  label: string;
  state?: StepState;
}

export type ThinkingLog = string | { time?: string; text?: string };

export interface ThinkingAuraProps extends HTMLAttributes<HTMLDivElement> {
  title?: string;
  steps?: ThinkingStep[];
  logs?: ThinkingLog[] | null;
  defaultOpen?: boolean;
  defaultCollapsed?: boolean;
}

export function ThinkingAura({
  title = "思考轨迹 (Thinking Aura)",
  steps = [],
  logs = null,
  defaultOpen = false,
  defaultCollapsed = false,
  style = {},
  ...rest
}: ThinkingAuraProps) {
  const [open, setOpen] = useState(defaultOpen);
  const [collapsed, setCollapsed] = useState(defaultCollapsed);

  // 当 defaultCollapsed prop 变化时，collapsed 完全跟随它。
  // true 时折叠、false 时展开。若同一组件实例被复用于新一轮思考链（prop 从 true 回落 false）,
  // 折叠态应重新展开。用户手动展开不受影响——因为 effect 只在 defaultCollapsed prop 本身变化时触发。
  useEffect(() => {
    setCollapsed(defaultCollapsed);
  }, [defaultCollapsed]);

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
          🍠 已完成 {steps.length} 步
        </span>
        <span style={{ color: "var(--primary)", fontSize: "var(--text-2xs)" }}>▾</span>
      </div>
    );
  }

  const stateColor: Record<StepState, string> = {
    done: "var(--success)",
    active: "var(--primary)",
    pending: "var(--text-subtle)",
  };
  const stateIcon: Record<StepState, string> = { done: "✓", active: "◐", pending: "○" };

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
        </div>
        {logs && (
          <button
            onClick={() => setOpen((o) => !o)}
            style={{ background: "none", border: "none", cursor: "pointer", color: "var(--primary)", fontFamily: "var(--font-sans)", fontWeight: "var(--weight-semibold)" as CSSProperties["fontWeight"], fontSize: "var(--text-2xs)", display: "inline-flex", alignItems: "center", gap: "0.2rem" }}
          >
            {open ? "收起分析详情 ▴" : "展开分析详情 ▾"}
          </button>
        )}
      </div>

      <div style={{ display: "flex", flexDirection: "column", gap: "0.5rem" }}>
        {steps.map((s, i) => {
          const st: StepState = s.state || "pending";
          return (
            <div key={i} style={{ display: "flex", alignItems: "center", gap: "0.5rem", fontSize: "var(--text-xs)", color: stateColor[st], fontWeight: (st === "active" ? "var(--weight-semibold)" : "var(--weight-regular)") as CSSProperties["fontWeight"] }}>
              <span style={{ width: 14, textAlign: "center", display: "inline-block", animation: st === "active" ? "spin 1.4s linear infinite" : "none" }}>{stateIcon[st]}</span>
              <span>{s.label}</span>
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
