import React from "react";

/**
 * IconButton — square, icon-only control. Used for sidebar
 * affordances (log-out, share, carousel arrows). Defaults to a
 * quiet ghost that warms to coral on hover.
 */
export function IconButton({
  children,
  size = "md",
  variant = "ghost",
  rounded = "md",
  label,
  style = {},
  ...rest
}) {
  const dims = { sm: 28, md: 36, lg: 44 }[size];
  const [hover, setHover] = React.useState(false);

  const variants = {
    ghost: {
      background: hover ? "var(--oats-dark)" : "transparent",
      color: hover ? "var(--primary)" : "var(--text-muted)",
      border: "1px solid transparent",
    },
    soft: {
      background: "var(--accent-surface)",
      color: "var(--accent-foreground)",
      border: "1px solid var(--border-coral)",
    },
    solid: {
      background: hover ? "var(--primary-hover)" : "var(--primary)",
      color: "var(--primary-foreground)",
      border: "1px solid transparent",
      boxShadow: "var(--shadow-sm)",
    },
    surface: {
      background: hover ? "#ffffff" : "rgba(255,255,255,0.75)",
      color: "var(--text-body)",
      border: "1px solid var(--border)",
      boxShadow: "var(--shadow-sm)",
    },
  };

  return (
    <button
      aria-label={label}
      title={label}
      onMouseEnter={() => setHover(true)}
      onMouseLeave={() => setHover(false)}
      style={{
        width: dims,
        height: dims,
        display: "inline-flex",
        alignItems: "center",
        justifyContent: "center",
        borderRadius: rounded === "full" ? "var(--radius-full)" : "var(--radius-md)",
        cursor: "pointer",
        flexShrink: 0,
        transition: "background var(--dur-fast) var(--ease-out), color var(--dur-fast) var(--ease-out)",
        ...variants[variant],
        ...style,
      }}
      {...rest}
    >
      {children}
    </button>
  );
}
