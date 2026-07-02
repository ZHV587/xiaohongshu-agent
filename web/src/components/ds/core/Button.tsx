"use client";

import { useState, type ButtonHTMLAttributes, type CSSProperties, type ReactNode } from "react";

/**
 * Button — 小红书文案助手 primary action control.
 * Coral-filled CTA, neutral secondary, quiet ghost, and soft
 * (coral-tint) variants. Press shrinks slightly; primary carries
 * a coral glow shadow.
 *
 * Faithfully ported 1:1 from 小红书文案助手 Design System/components/core/Button.jsx.
 */
type ButtonVariant = "primary" | "secondary" | "soft" | "ghost";
type ButtonSize = "sm" | "md" | "lg";

export interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: ButtonVariant;
  size?: ButtonSize;
  block?: boolean;
  loading?: boolean;
  leftIcon?: ReactNode;
  rightIcon?: ReactNode;
}

export function Button({
  children,
  variant = "primary",
  size = "md",
  block = false,
  disabled = false,
  loading = false,
  leftIcon = null,
  rightIcon = null,
  style = {},
  ...rest
}: ButtonProps) {
  const sizes: Record<ButtonSize, CSSProperties> = {
    sm: { fontSize: "var(--text-xs)", padding: "0.375rem 0.75rem", gap: "0.375rem", minHeight: 32 },
    md: { fontSize: "var(--text-sm)", padding: "0.55rem 1.1rem", gap: "0.5rem", minHeight: 40 },
    lg: { fontSize: "var(--text-base)", padding: "0.7rem 1.4rem", gap: "0.6rem", minHeight: 48 },
  };

  const variants: Record<ButtonVariant, CSSProperties> = {
    primary: {
      background: "var(--primary)",
      color: "var(--primary-foreground)",
      border: "1px solid transparent",
      boxShadow: "var(--shadow-coral)",
    },
    secondary: {
      background: "var(--surface-card)",
      color: "var(--text-body)",
      border: "1px solid var(--border)",
      boxShadow: "var(--shadow-xs)",
    },
    soft: {
      background: "var(--accent-surface)",
      color: "var(--accent-foreground)",
      border: "1px solid var(--border-coral)",
      boxShadow: "none",
    },
    ghost: {
      background: "transparent",
      color: "var(--text-muted)",
      border: "1px solid transparent",
      boxShadow: "none",
    },
  };

  const [hover, setHover] = useState(false);
  const isDisabled = disabled || loading;

  const hoverBg: Record<ButtonVariant, string> = {
    primary: "var(--primary-hover)",
    secondary: "var(--oats-default)",
    soft: "color-mix(in srgb, var(--primary) 15%, transparent)",
    ghost: "var(--oats-dark)",
  };

  return (
    <button
      disabled={isDisabled}
      onMouseEnter={() => setHover(true)}
      onMouseLeave={() => setHover(false)}
      style={{
        display: block ? "flex" : "inline-flex",
        width: block ? "100%" : "auto",
        alignItems: "center",
        justifyContent: "center",
        fontFamily: "var(--font-sans)",
        fontWeight: "var(--weight-semibold)" as CSSProperties["fontWeight"],
        borderRadius: "var(--radius-md)",
        cursor: isDisabled ? "not-allowed" : "pointer",
        opacity: isDisabled ? 0.55 : 1,
        transition: "background var(--dur-fast) var(--ease-out), transform var(--dur-fast) var(--ease-out)",
        transform: hover && !isDisabled ? "translateY(-1px)" : "none",
        whiteSpace: "nowrap",
        ...sizes[size],
        ...variants[variant],
        ...(hover && !isDisabled ? { background: hoverBg[variant] } : {}),
        ...style,
      }}
      {...rest}
    >
      {loading ? <Spinner /> : leftIcon}
      {children}
      {rightIcon}
    </button>
  );
}

function Spinner() {
  return (
    <span
      style={{
        width: 14,
        height: 14,
        borderRadius: "var(--radius-full)",
        border: "2px solid currentColor",
        borderTopColor: "transparent",
        display: "inline-block",
        animation: "spin 0.7s linear infinite",
      }}
    />
  );
}
