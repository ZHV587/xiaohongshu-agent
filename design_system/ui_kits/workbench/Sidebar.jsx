// Sidebar — new-chat CTA, recent creations list, user footer.
function Sidebar({ activeId, onSelect, onNewChat }) {
  const { Button, Badge, Avatar, IconButton } = window.DesignSystem_71831b;
  const D = window.XHS_DATA;

  return (
    <aside
      style={{
        width: "var(--rail-sidebar)",
        background: "var(--surface-sidebar)",
        borderRight: "1px solid var(--border)",
        display: "flex",
        flexDirection: "column",
        justifyContent: "space-between",
        flexShrink: 0,
      }}
    >
      <div style={{ display: "flex", flexDirection: "column", padding: 16, gap: 16, overflow: "hidden", height: "100%" }}>
        <Button variant="primary" block leftIcon={<Icon name="square-pen" size={16} />} onClick={onNewChat}>
          开启全新灵感对话
        </Button>

        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginTop: 4 }}>
          <Eyebrow>最近创作</Eyebrow>
          <span style={{ fontSize: 10, color: "var(--gray-300)" }}>按 Ctrl+J 隐藏</span>
        </div>

        <div style={{ display: "flex", flexDirection: "column", gap: 4, overflowY: "auto" }} className="custom-scrollbar">
          {D.recents.map((r) => {
            const active = r.id === activeId;
            return (
              <button
                key={r.id}
                onClick={() => onSelect(r.id)}
                style={{
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "space-between",
                  gap: 8,
                  width: "100%",
                  textAlign: "left",
                  padding: "10px 12px",
                  fontSize: "var(--text-sm)",
                  borderRadius: "var(--radius-sm)",
                  cursor: "pointer",
                  border: "none",
                  borderLeft: active ? "2px solid var(--primary)" : "2px solid transparent",
                  background: active ? "var(--oats-dark)" : "transparent",
                  color: active ? "var(--primary)" : "var(--text-muted)",
                  fontWeight: active ? "var(--weight-semibold)" : "var(--weight-regular)",
                  fontFamily: "var(--font-sans)",
                }}
              >
                <span style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                  {r.icon} {r.title}
                </span>
                <Badge tone={r.status === "synced" ? "synced" : "draft"} shape="chip">
                  {r.status === "synced" ? "已同步" : "草稿"}
                </Badge>
              </button>
            );
          })}
        </div>
      </div>

      <div style={{ padding: 16, borderTop: "1px solid var(--oats-dark)", display: "flex", alignItems: "center", justifyContent: "space-between" }}>
        <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
          <Avatar name="Z" />
          <span style={{ fontSize: "var(--text-sm)", fontWeight: "var(--weight-medium)", color: "var(--text-body)" }}>{D.user.name}</span>
        </div>
        <IconButton label="退出登录"><Icon name="log-out" /></IconButton>
      </div>
    </aside>
  );
}

Object.assign(window, { Sidebar });
