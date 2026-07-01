import React from "react";

/**
 * HashtagTag — a 小红书 topic chip (#话题). Topic-blue by default,
 * coral when emphasised. `addable` shows a + affordance for the
 * smart-recommendation tag picker.
 */
export function HashtagTag({
  children,
  tone = "topic",
  addable = false,
  onAdd,
  style = {},
  ...rest
}) {
  const [hover, setHover] = React.useState(false);

  const tones = {
    topic: { bg: "var(--topicblue-light)", fg: "var(--topicblue-default)", bd: "color-mix(in srgb, var(--topicblue-default) 22%, transparent)" },
    coral: { bg: "var(--accent-surface)", fg: "var(--accent-foreground)", bd: "var(--border-coral)" },
    plain: { bg: "var(--oats-dark)", fg: "var(--text-muted)", bd: "var(--border)" },
  };
  const t = tones[tone] || tones.topic;
  const label = typeof children === "string" && !children.startsWith("#") ? `#${children}` : children;

  return (
    <span
      onMouseEnter={() => setHover(true)}
      onMouseLeave={() => setHover(false)}
      onClick={addable ? onAdd : undefined}
      style={{
        display: "inline-flex",
        alignItems: "center",
        gap: "0.25rem",
        fontFamily: "var(--font-sans)",
        fontSize: "var(--text-2xs)",
        fontWeight: "var(--weight-medium)",
        lineHeight: 1,
        padding: "0.3rem 0.55rem",
        borderRadius: "var(--radius-full)",
        background: hover && addable ? "color-mix(in srgb, " + t.fg + " 14%, var(--surface-card))" : t.bg,
        color: t.fg,
        border: `1px solid ${t.bd}`,
        cursor: addable ? "pointer" : "default",
        transition: "background var(--dur-fast) var(--ease-out)",
        whiteSpace: "nowrap",
        ...style,
      }}
      {...rest}
    >
      {label}
      {addable && <span style={{ fontSize: 12, lineHeight: 1, opacity: 0.8 }}>＋</span>}
    </span>
  );
}
