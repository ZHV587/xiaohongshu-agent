import React from "react";

/**
 * Select — native dropdown wrapped in the system's field shell
 * (oats rest, coral focus, chevron affordance). Pass an `options`
 * array of {value,label} or plain strings, or use children.
 */
export function Select({
  options = null,
  invalid = false,
  style = {},
  containerStyle = {},
  children,
  ...rest
}) {
  const [focus, setFocus] = React.useState(false);

  const opts = options
    ? options.map((o) => (typeof o === "string" ? { value: o, label: o } : o))
    : null;

  return (
    <div
      style={{
        position: "relative",
        display: "flex",
        alignItems: "center",
        background: focus ? "var(--surface-card)" : "var(--input-bg)",
        border: `1px solid ${invalid ? "var(--primary)" : focus ? "var(--primary)" : "var(--border)"}`,
        borderRadius: "var(--radius-md)",
        boxShadow: focus ? "var(--ring-focus)" : "none",
        transition: "border-color var(--dur-fast) var(--ease-out), box-shadow var(--dur-fast) var(--ease-out)",
        ...containerStyle,
      }}
    >
      <select
        onFocus={() => setFocus(true)}
        onBlur={() => setFocus(false)}
        style={{
          appearance: "none",
          WebkitAppearance: "none",
          border: "none",
          outline: "none",
          background: "transparent",
          fontFamily: "var(--font-sans)",
          fontSize: "var(--text-sm)",
          color: "var(--text-body)",
          padding: "0.55rem 2rem 0.55rem 0.75rem",
          width: "100%",
          cursor: "pointer",
          ...style,
        }}
        {...rest}
      >
        {opts ? opts.map((o) => <option key={o.value} value={o.value}>{o.label}</option>) : children}
      </select>
      <span
        aria-hidden
        style={{
          position: "absolute",
          right: "0.7rem",
          pointerEvents: "none",
          color: "var(--text-subtle)",
          fontSize: 11,
        }}
      >
        ▾
      </span>
    </div>
  );
}
