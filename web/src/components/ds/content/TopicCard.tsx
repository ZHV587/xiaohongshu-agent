"use client";

import { useState, type CSSProperties, type HTMLAttributes, type ReactNode } from "react";

/**
 * TopicCard — a viral-topic suggestion the agent proposes. Numbered
 * coral index, title + rationale, and a "hot rate" 爆款率 badge.
 * Clickable; lifts to coral on hover (the signature interaction).
 *
 * Faithfully ported 1:1 from 小红书文案助手 Design System/components/content/TopicCard.jsx.
 */
export interface TopicCardProps extends Omit<HTMLAttributes<HTMLDivElement>, "title"> {
  index?: number;
  title?: ReactNode;
  rationale?: ReactNode;
  hotRate?: number | null;
}

export function TopicCard({
  index = 1,
  title,
  rationale,
  hotRate = null,
  onClick,
  style = {},
  ...rest
}: TopicCardProps) {
  const [hover, setHover] = useState(false);

  return (
    <div
      onClick={onClick}
      onMouseEnter={() => setHover(true)}
      onMouseLeave={() => setHover(false)}
      style={{
        display: "flex",
        alignItems: "center",
        gap: "0.75rem",
        padding: "0.875rem",
        borderRadius: "var(--radius-md)",
        background: hover ? "color-mix(in srgb, var(--accent-surface) 55%, var(--surface-card))" : "var(--oats-light)",
        border: `1px solid ${hover ? "var(--primary)" : "var(--border-coral)"}`,
        cursor: "pointer",
        transition: "all var(--dur-base) var(--ease-out)",
        ...style,
      }}
      {...rest}
    >
      <span
        style={{
          flexShrink: 0,
          width: 28,
          height: 28,
          borderRadius: "var(--radius-sm)",
          background: "var(--accent-surface)",
          color: "var(--accent-foreground)",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          fontFamily: "var(--font-display)",
          fontWeight: "var(--weight-bold)" as CSSProperties["fontWeight"],
          fontSize: "var(--text-xs)",
          transform: hover ? "scale(1.08)" : "none",
          transition: "transform var(--dur-base) var(--ease-out)",
        }}
      >
        {index}
      </span>
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ fontFamily: "var(--font-sans)", fontWeight: "var(--weight-semibold)" as CSSProperties["fontWeight"], fontSize: "var(--text-sm)", color: "var(--text-body)" }}>
          {title}
        </div>
        {rationale && (
          <div style={{ fontSize: "var(--text-xs)", color: "var(--text-subtle)", marginTop: 2, lineHeight: "var(--leading-snug)" }}>
            {rationale}
          </div>
        )}
      </div>
      {hotRate != null && (
        <span
          style={{
            flexShrink: 0,
            display: "inline-flex",
            alignItems: "center",
            gap: "0.25rem",
            fontSize: "var(--text-2xs)",
            fontWeight: "var(--weight-bold)" as CSSProperties["fontWeight"],
            color: "var(--hot)",
            background: "var(--hot-surface)",
            border: "1px solid var(--border-coral)",
            padding: "0.2rem 0.5rem",
            borderRadius: "var(--radius-xs)",
          }}
        >
          <span>🔥</span> 爆款率 {hotRate}%
        </span>
      )}
    </div>
  );
}
