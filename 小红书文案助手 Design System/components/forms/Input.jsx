import React from "react";

/**
 * Input — single-line text field. Oats-tinted rest state that
 * brightens to white with a coral ring on focus. Optional
 * leading icon and trailing slot (e.g. kbd hint / char count).
 */
export function Input({
  leadingIcon = null,
  trailing = null,
  invalid = false,
  style = {},
  containerStyle = {},
  ...rest
}) {
  const [focus, setFocus] = React.useState(false);

  return (
    <div
      style={{
        display: "flex",
        alignItems: "center",
        gap: "0.5rem",
        background: focus ? "var(--surface-card)" : "var(--input-bg)",
        border: `1px solid ${invalid ? "var(--primary)" : focus ? "var(--primary)" : "var(--border)"}`,
        borderRadius: "var(--radius-md)",
        padding: "0 0.75rem",
        boxShadow: focus ? "var(--ring-focus)" : "none",
        transition: "border-color var(--dur-fast) var(--ease-out), box-shadow var(--dur-fast) var(--ease-out), background var(--dur-fast) var(--ease-out)",
        ...containerStyle,
      }}
    >
      {leadingIcon && <span style={{ color: "var(--text-subtle)", display: "inline-flex" }}>{leadingIcon}</span>}
      <input
        onFocus={(e) => { setFocus(true); rest.onFocus?.(e); }}
        onBlur={(e) => { setFocus(false); rest.onBlur?.(e); }}
        style={{
          flex: 1,
          minWidth: 0,
          border: "none",
          outline: "none",
          background: "transparent",
          fontFamily: "var(--font-sans)",
          fontSize: "var(--text-sm)",
          color: "var(--text-body)",
          padding: "0.55rem 0",
          ...style,
        }}
        {...rest}
      />
      {trailing && <span style={{ color: "var(--text-subtle)", display: "inline-flex", flexShrink: 0 }}>{trailing}</span>}
    </div>
  );
}
