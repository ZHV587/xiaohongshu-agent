import React from "react";

/**
 * ThinkingAura (思维微光) — the agent's live reasoning panel. A
 * breathing coral dot, a stepper of statuses (done / active /
 * pending), and an optional collapsible log of raw thoughts.
 */
export function ThinkingAura({
  title = "思考轨迹 (Thinking Aura)",
  steps = [],
  logs = null,
  defaultOpen = false,
  style = {},
  ...rest
}) {
  const [open, setOpen] = React.useState(defaultOpen);

  const stateColor = {
    done: "var(--success)",
    active: "var(--primary)",
    pending: "var(--text-subtle)",
  };
  const stateIcon = { done: "✓", active: "◐", pending: "○" };

  return (
    <div
      style={{
        background: "var(--surface-card)",
        border: "1px solid var(--border-coral)",
        borderRadius: "var(--radius-xl)",
        boxShadow: "var(--shadow-sm)",
        padding: "0.875rem",
        width: "100%",
        ...style,
      }}
      {...rest}
    >
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: "0.75rem" }}>
        <div style={{ display: "flex", alignItems: "center", gap: "0.6rem" }}>
          <span style={{ position: "relative", display: "inline-flex", width: 10, height: 10 }}>
            <span style={{ position: "absolute", inset: 0, borderRadius: "var(--radius-full)", background: "var(--primary)", animation: "xhs-ping 1.4s var(--ease-out) infinite" }} />
            <span style={{ position: "relative", borderRadius: "var(--radius-full)", width: 10, height: 10, background: "var(--primary)" }} />
          </span>
          <span style={{ fontFamily: "var(--font-sans)", fontWeight: "var(--weight-bold)", fontSize: "var(--text-xs)", color: "var(--text-body)" }}>{title}</span>
        </div>
        {logs && (
          <button
            onClick={() => setOpen((o) => !o)}
            style={{ background: "none", border: "none", cursor: "pointer", color: "var(--primary)", fontFamily: "var(--font-sans)", fontWeight: "var(--weight-semibold)", fontSize: "var(--text-2xs)", display: "inline-flex", alignItems: "center", gap: "0.2rem" }}
          >
            {open ? "收起分析详情 ▴" : "展开分析详情 ▾"}
          </button>
        )}
      </div>

      <div style={{ display: "flex", flexDirection: "column", gap: "0.5rem" }}>
        {steps.map((s, i) => {
          const st = s.state || "pending";
          return (
            <div key={i} style={{ display: "flex", alignItems: "center", gap: "0.5rem", fontSize: "var(--text-xs)", color: stateColor[st], fontWeight: st === "active" ? "var(--weight-semibold)" : "var(--weight-regular)" }}>
              <span style={{ width: 14, textAlign: "center", display: "inline-block", animation: st === "active" ? "spin 1.4s linear infinite" : "none" }}>{stateIcon[st]}</span>
              <span>{s.label}</span>
            </div>
          );
        })}
      </div>

      {logs && open && (
        <div
          style={{
            marginTop: "0.7rem",
            borderTop: "1px solid var(--border)",
            paddingTop: "0.6rem",
            display: "flex",
            flexDirection: "column",
            gap: "0.4rem",
            fontFamily: "var(--font-mono)",
            fontSize: "var(--text-2xs)",
            color: "var(--text-subtle)",
            background: "var(--oats-light)",
            borderRadius: "var(--radius-sm)",
            padding: "0.6rem",
            maxHeight: 140,
            overflowY: "auto",
          }}
        >
          {logs.map((l, i) => (
            <div key={i} style={{ display: "flex", gap: "0.4rem" }}>
              {l.time && <span style={{ color: "var(--primary)", fontWeight: "var(--weight-bold)", flexShrink: 0 }}>[{l.time}]</span>}
              <span>{l.text || l}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
