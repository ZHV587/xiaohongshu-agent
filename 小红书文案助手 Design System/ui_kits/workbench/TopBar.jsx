// TopBar — brand lockup, Feishu CLI status, and the expired-identity
// re-auth prompt that flips the right canvas to the scan card.
function TopBar({ onReauth }) {
  const { Badge } = window.DesignSystem_71831b;
  return (
    <header
      style={{
        height: "var(--topbar-height)",
        background: "rgba(255,255,255,0.85)",
        backdropFilter: "blur(8px)",
        borderBottom: "1px solid var(--border)",
        padding: "0 24px",
        display: "flex",
        alignItems: "center",
        justifyContent: "space-between",
        flexShrink: 0,
        zIndex: 10,
      }}
    >
      <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
        <span
          style={{
            width: 32,
            height: 32,
            borderRadius: "var(--radius-md)",
            background: "var(--coral-brand)",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            fontSize: 18,
            boxShadow: "var(--shadow-coral)",
          }}
        >
          🍠
        </span>
        <h1
          style={{
            margin: 0,
            fontFamily: "var(--font-display)",
            fontWeight: "var(--weight-bold)",
            fontSize: "var(--text-lg)",
            letterSpacing: "var(--tracking-tight)",
            color: "var(--text-body)",
          }}
        >
          小红书文案助手
          <span style={{ fontFamily: "var(--font-sans)", fontSize: "var(--text-xs)", fontWeight: 400, color: "var(--text-subtle)", marginLeft: 8 }}>
            v1.2 工作台
          </span>
        </h1>
      </div>

      <div style={{ display: "flex", alignItems: "center", gap: 14 }}>
        <Badge tone="synced" dot>飞书 CLI 状态：Ready (bot)</Badge>
        <button
          onClick={onReauth}
          style={{
            display: "inline-flex",
            alignItems: "center",
            gap: 6,
            background: "var(--accent-surface)",
            border: "1px solid var(--border-coral)",
            color: "var(--primary)",
            padding: "5px 10px",
            borderRadius: "var(--radius-full)",
            fontSize: "var(--text-xs)",
            fontFamily: "var(--font-sans)",
            cursor: "pointer",
          }}
        >
          <Icon name="key-round" size={12} />
          User 身份已过期，点此扫码重连
        </button>
      </div>
    </header>
  );
}

Object.assign(window, { TopBar });
