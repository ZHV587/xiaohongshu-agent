"use client";

import type { CSSProperties, HTMLAttributes, ReactNode } from "react";

/**
 * StatCard — a metric tile for the 数据看板. Shows a label, a big
 * tabular value, an optional delta (up = success, down = muted/coral),
 * and an optional leading icon chip. `editable` renders the value as
 * an inline field for 数据回填 (manual metric entry).
 *
 * Faithfully ported 1:1 from 小红书文案助手 Design System/components/data/StatCard.jsx.
 */
type StatTone = "neutral" | "coral" | "topic" | "success";

export interface StatCardProps extends HTMLAttributes<HTMLDivElement> {
  label?: ReactNode;
  value?: string | number;
  unit?: string;
  delta?: number | string | null;
  icon?: ReactNode;
  tone?: StatTone;
  editable?: boolean;
  onValueChange?: (value: string) => void;
}

export function StatCard({
  label,
  value,
  unit = "",
  delta = null,
  icon = null,
  tone = "neutral",
  editable = false,
  onValueChange,
  style = {},
  ...rest
}: StatCardProps) {
  const tones: Record<StatTone, string> = {
    neutral: "var(--text-body)",
    coral: "var(--primary)",
    topic: "var(--topicblue-default)",
    success: "var(--success)",
  };
  const deltaUp = typeof delta === "number" ? delta >= 0 : null;

  return (
    <div
      style={{
        background: "var(--surface-card)",
        border: "1px solid var(--border)",
        borderRadius: "var(--radius-lg)",
        boxShadow: "var(--shadow-sm)",
        padding: "var(--space-3-5)",
        display: "flex",
        flexDirection: "column",
        gap: 8,
        minWidth: 0,
        ...style,
      }}
      {...rest}
    >
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 8 }}>
        <span style={{ fontSize: "var(--text-xs)", color: "var(--text-muted)", fontWeight: "var(--weight-medium)" as CSSProperties["fontWeight"], whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{label}</span>
        {icon && (
          <span style={{ width: 26, height: 26, borderRadius: "var(--radius-sm)", background: "var(--accent-surface)", color: "var(--primary)", display: "inline-flex", alignItems: "center", justifyContent: "center", flexShrink: 0 }}>
            {icon}
          </span>
        )}
      </div>

      <div style={{ display: "flex", alignItems: "baseline", gap: 4 }}>
        {editable ? (
          <input
            value={value}
            onChange={(e) => onValueChange?.(e.target.value)}
            inputMode="numeric"
            aria-label={typeof label === "string" ? label : undefined}
            name={typeof label === "string" ? label : undefined}
            style={{
              width: "100%",
              border: "1px dashed var(--border-strong)",
              borderRadius: "var(--radius-sm)",
              background: "var(--oats-light)",
              fontFamily: "var(--font-display)",
              fontWeight: "var(--weight-bold)" as CSSProperties["fontWeight"],
              fontSize: "var(--text-2xl)",
              color: tones[tone],
              padding: "2px 8px",
              outline: "none",
            }}
            className="font-tabular"
          />
        ) : (
          <span className="font-tabular" style={{ fontFamily: "var(--font-display)", fontWeight: "var(--weight-black)" as CSSProperties["fontWeight"], fontSize: "var(--text-2xl)", color: tones[tone], lineHeight: 1 }}>
            {value}
          </span>
        )}
        {unit && <span style={{ fontSize: "var(--text-xs)", color: "var(--text-subtle)" }}>{unit}</span>}
      </div>

      {delta != null && (
        <span style={{ display: "inline-flex", alignItems: "center", gap: 3, fontSize: "var(--text-2xs)", fontWeight: "var(--weight-semibold)" as CSSProperties["fontWeight"], color: deltaUp ? "var(--success)" : "var(--text-muted)" }}>
          <span>{deltaUp ? "▲" : "▼"}</span>
          {typeof delta === "number" ? `${Math.abs(delta)}%` : delta}
          <span style={{ color: "var(--text-subtle)", fontWeight: 400, marginLeft: 2 }}>近7天</span>
        </span>
      )}
    </div>
  );
}
