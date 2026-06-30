// RightCanvas — tab shell (phone preview / Feishu sync) + bottom bar.
function RightCanvas({ note, tab, setTab, mode, setMode, imgIdx, onPrev, onNext, scanned, onScan }) {
  return (
    <section style={{ width: "var(--rail-canvas)", borderLeft: "1px solid var(--border)", background: "var(--surface-card)", display: "flex", flexDirection: "column", flexShrink: 0, boxShadow: "var(--shadow-lg)", zIndex: 10 }}>
      {/* tab header */}
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", borderBottom: "1px solid var(--border)", background: "color-mix(in srgb, var(--oats-light) 50%, white)", padding: "0 16px", flexShrink: 0 }}>
        <div style={{ display: "flex", gap: 8, padding: "8px 0" }}>
          <Tab active={tab === "mock"} onClick={() => setTab("mock")}>📱 小红书手机预览</Tab>
          <Tab active={tab === "feishu"} onClick={() => setTab("feishu")}>🔗 飞书同步协作</Tab>
        </div>
        {tab === "mock" && (
          <div style={{ display: "flex", gap: 4, background: "var(--oats-default)", border: "1px solid var(--border)", borderRadius: "var(--radius-md)", padding: 3 }}>
            <Seg active={mode === "detail"} onClick={() => setMode("detail")}>详情视窗</Seg>
            <Seg active={mode === "feed"} onClick={() => setMode("feed")}>瀑布流卡片</Seg>
          </div>
        )}
      </div>

      {tab === "mock"
        ? <PhonePreview note={note} mode={mode} imgIdx={imgIdx} onPrev={onPrev} onNext={onNext} />
        : <FeishuSync note={note} scanned={scanned} onScan={onScan} />}

      {/* bottom bar */}
      <div style={{ height: 60, borderTop: "1px solid var(--border)", padding: "0 24px", background: "var(--surface-card)", display: "flex", alignItems: "center", justifyContent: "space-between", flexShrink: 0 }}>
        <span style={{ fontSize: "var(--text-xs)", color: "var(--text-subtle)" }} className="font-tabular">
          文案长度：{note.body.length} / 1000 字
        </span>
        <CopyButton />
      </div>
    </section>
  );
}

function Tab({ active, onClick, children }) {
  return (
    <button onClick={onClick} style={{
      padding: "6px 16px", borderRadius: "var(--radius-sm)", fontFamily: "var(--font-sans)",
      fontSize: "var(--text-sm)", fontWeight: active ? 600 : 500, cursor: "pointer",
      border: active ? "1px solid var(--border-coral)" : "1px solid transparent",
      background: active ? "var(--accent-surface)" : "transparent",
      color: active ? "var(--primary)" : "var(--text-muted)",
    }}>{children}</button>
  );
}

function Seg({ active, onClick, children }) {
  return (
    <button onClick={onClick} style={{
      padding: "4px 10px", borderRadius: "var(--radius-sm)", border: "none", cursor: "pointer",
      fontSize: 10, fontFamily: "var(--font-sans)", fontWeight: active ? 600 : 400,
      background: active ? "#fff" : "transparent", color: active ? "var(--primary)" : "var(--text-muted)",
      boxShadow: active ? "var(--shadow-xs)" : "none",
    }}>{children}</button>
  );
}

function CopyButton() {
  const { Button } = window.DesignSystem_71831b;
  const [done, setDone] = React.useState(false);
  return (
    <Button variant="soft" size="sm" leftIcon={<Icon name={done ? "check" : "copy"} size={14} />} onClick={() => { setDone(true); setTimeout(() => setDone(false), 1600); }}>
      {done ? "已复制" : "一键复制纯文案"}
    </Button>
  );
}

Object.assign(window, { RightCanvas });
