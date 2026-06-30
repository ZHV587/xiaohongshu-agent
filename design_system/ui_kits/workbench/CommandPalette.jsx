// CommandPalette — Ctrl+P modal of polish commands.
function CommandPalette({ open, onClose, onRun }) {
  const { Input } = window.DesignSystem_71831b;
  const D = window.XHS_DATA;
  const [q, setQ] = React.useState("");
  if (!open) return null;

  const list = D.commands.filter((c) => (c.name + c.desc).toLowerCase().includes(q.toLowerCase()));

  return (
    <div
      onClick={onClose}
      style={{ position: "fixed", inset: 0, background: "rgba(15,15,16,0.4)", backdropFilter: "blur(3px)", display: "flex", justifyContent: "center", alignItems: "flex-start", paddingTop: 96, zIndex: 50 }}
    >
      <div onClick={(e) => e.stopPropagation()} style={{ width: 500, maxWidth: "90vw", background: "var(--surface-card)", borderRadius: "var(--radius-lg)", border: "1px solid var(--border-coral)", boxShadow: "var(--shadow-2xl)", overflow: "hidden" }}>
        <div style={{ padding: 12, borderBottom: "1px solid var(--oats-dark)" }}>
          <Input autoFocus value={q} onChange={(e) => setQ(e.target.value)} placeholder="输入命令或搜索动作..." leadingIcon={<Icon name="search" size={16} />} trailing={<kbd onClick={onClose} style={{ fontSize: 10, background: "var(--oats-dark)", border: "1px solid var(--border)", color: "var(--text-subtle)", padding: "1px 6px", borderRadius: 4, cursor: "pointer", fontFamily: "var(--font-mono)" }}>ESC</kbd>} />
        </div>
        <div style={{ padding: 8, display: "flex", flexDirection: "column", maxHeight: 260, overflowY: "auto" }} className="custom-scrollbar">
          {list.map((c) => (
            <button key={c.id} onClick={() => onRun(c.id)} style={{ display: "flex", alignItems: "center", gap: 12, width: "100%", textAlign: "left", padding: "10px 12px", borderRadius: "var(--radius-sm)", border: "none", background: "transparent", cursor: "pointer", fontFamily: "var(--font-sans)" }}
              onMouseEnter={(e) => (e.currentTarget.style.background = "var(--oats-default)")}
              onMouseLeave={(e) => (e.currentTarget.style.background = "transparent")}>
              <Icon name={c.icon} size={16} color={c.color} />
              <span style={{ fontSize: "var(--text-xs)" }}>
                <span style={{ fontWeight: 600, color: "var(--text-body)" }}>{c.name}</span>
                <span style={{ color: "var(--text-subtle)", marginLeft: 8 }}>{c.desc}</span>
              </span>
            </button>
          ))}
          {list.length === 0 && <div style={{ padding: 16, fontSize: "var(--text-xs)", color: "var(--text-subtle)", textAlign: "center" }}>无匹配命令</div>}
        </div>
      </div>
    </div>
  );
}

Object.assign(window, { CommandPalette });
