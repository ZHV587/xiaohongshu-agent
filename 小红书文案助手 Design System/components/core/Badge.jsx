import React from "react";

/**
 * Badge — compact status / meta pill. Tones map to the system's
 * semantic surfaces: synced (green), draft (gray), hot (coral),
 * topic (blue), info. Pill or chip (squared) shape.
 */
export function Badge({
  children,
  tone = "neutral",
  shape = "pill",
  dot = false,
  style = {},
  ...rest
}) {
  const tones = {
    neutral: { bg: "var(--oats-dark)", fg: "var(--text-muted)", bd: "var(--border)" },
    synced:  { bg: "var(--success-surface)", fg: "var(--success)", bd: "var(--success-border)" },
    hot:     { bg: "var(--hot-surface)", fg: "var(--hot)", bd: "var(--border-coral)" },
    topic:   { bg: "var(--topicblue-light)", fg: "var(--topicblue-default)", bd: "color-mix(in srgb, var(--topicblue-default) 18%, transparent)" },
    info:    { bg: "var(--info-surface)", fg: "var(--info)", bd: "var(--info-border)" },
    coral:   { bg: "var(--accent-surface)", fg: "var(--accent-foreground)", bd: "var(--border-coral)" },
    draft:   { bg: "#f8f7f4", fg: "var(--text-subtle)", bd: "var(--border)" },
  };
  const t = tones[tone] || tones.neutral;

  return (
    <span
      style={{
        display: "inline-flex",
        alignItems: "center",
        gap: "0.3rem",
        fontFamily: "var(--font-sans)",
        fontSize: "var(--text-2xs)",
        fontWeight: "var(--weight-semibold)",
        lineHeight: 1,
        padding: shape === "pill" ? "0.25rem 0.55rem" : "0.2rem 0.4rem",
        borderRadius: shape === "pill" ? "var(--radius-full)" : "var(--radius-xs)",
        background: t.bg,
        color: t.fg,
        border: `1px solid ${t.bd}`,
        whiteSpace: "nowrap",
        ...style,
      }}
      {...rest}
    >
      {dot && (
        <span
          style={{
            width: 6,
            height: 6,
            borderRadius: "var(--radius-full)",
            background: "currentColor",
            flexShrink: 0,
          }}
        />
      )}
      {children}
    </span>
  );
}
