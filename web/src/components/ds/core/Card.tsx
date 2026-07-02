"use client";

import { useState, type CSSProperties, type HTMLAttributes, type ReactNode } from "react";

/**
 * Card — white surface container on the oats canvas. Soft border
 * + low shadow. `interactive` adds a coral hover lift (used for
 * clickable topic / sync cards). `tone` tints the whole card.
 *
 * Faithfully ported 1:1 from 小红书文案助手 Design System/components/core/Card.jsx.
 */
type CardTone = "default" | "sunken" | "coral";
type CardPadding = "none" | "sm" | "md" | "lg";

export interface CardProps extends HTMLAttributes<HTMLDivElement> {
  interactive?: boolean;
  tone?: CardTone;
  padding?: CardPadding;
  children?: ReactNode;
}

export function Card({
  children,
  interactive = false,
  tone = "default",
  padding = "md",
  style = {},
  ...rest
}: CardProps) {
  const [hover, setHover] = useState(false);

  const pads: Record<CardPadding, string | number> = { none: 0, sm: "0.875rem", md: "1.25rem", lg: "1.5rem" };

  const tones: Record<CardTone, { background: string; border: string }> = {
    default: { background: "var(--surface-card)", border: "var(--border)" },
    sunken: { background: "var(--oats-light)", border: "var(--border-coral)" },
    coral: { background: "var(--accent-surface)", border: "var(--border-coral)" },
  };
  const t = tones[tone] || tones.default;

  return (
    <div
      onMouseEnter={() => setHover(true)}
      onMouseLeave={() => setHover(false)}
      style={{
        background: t.background,
        border: `1px solid ${interactive && hover ? "var(--primary)" : t.border}`,
        borderRadius: "var(--radius-lg)",
        boxShadow: "var(--shadow-sm)",
        padding: pads[padding],
        cursor: interactive ? "pointer" : "default",
        transition: "border-color var(--dur-base) var(--ease-out), transform var(--dur-base) var(--ease-out), background var(--dur-base) var(--ease-out)",
        transform: interactive && hover ? "translateY(-2px)" : "none",
        ...(interactive && hover ? { background: "color-mix(in srgb, var(--accent-surface) 60%, var(--surface-card))" } : {}),
        ...style,
      }}
      {...rest}
    >
      {children}
    </div>
  );
}
