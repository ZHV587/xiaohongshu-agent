"use client";

import type { CSSProperties, HTMLAttributes, ReactNode } from "react";

/**
 * Avatar — circular user/agent mark. Renders initials on a
 * coral-tint disc by default, or the 🍠 agent glyph, or an image.
 *
 * Faithfully ported 1:1 from 小红书文案助手 Design System/components/core/Avatar.jsx.
 */
type AvatarVariant = "coral" | "solid" | "neutral" | "agent";

export interface AvatarProps extends HTMLAttributes<HTMLDivElement> {
  name?: string;
  src?: string | null;
  glyph?: ReactNode;
  size?: number;
  variant?: AvatarVariant;
}

export function Avatar({
  name = "",
  src = null,
  glyph = null,
  size = 32,
  variant = "coral",
  style = {},
  ...rest
}: AvatarProps) {
  const initials = name
    .trim()
    .split(/\s+/)
    .map((w) => w[0])
    .slice(0, 2)
    .join("")
    .toUpperCase();

  const variants: Record<AvatarVariant, CSSProperties> = {
    coral: { background: "var(--accent-surface)", color: "var(--accent-foreground)" },
    solid: { background: "var(--primary)", color: "var(--primary-foreground)" },
    neutral: { background: "var(--oats-dark)", color: "var(--text-body)" },
    agent: { background: "var(--surface-card)", color: "inherit", border: "1px solid var(--border-coral)" },
  };

  return (
    <div
      style={{
        width: size,
        height: size,
        flexShrink: 0,
        borderRadius: "var(--radius-full)",
        display: "inline-flex",
        alignItems: "center",
        justifyContent: "center",
        fontFamily: "var(--font-display)",
        fontWeight: "var(--weight-bold)" as CSSProperties["fontWeight"],
        fontSize: Math.round(size * 0.4),
        overflow: "hidden",
        boxShadow: "var(--shadow-xs)",
        ...variants[variant],
        ...style,
      }}
      {...rest}
    >
      {src ? (
        <img src={src} alt={name} style={{ width: "100%", height: "100%", objectFit: "cover" }} />
      ) : glyph ? (
        <span style={{ fontSize: Math.round(size * 0.56) }}>{glyph}</span>
      ) : (
        initials
      )}
    </div>
  );
}
