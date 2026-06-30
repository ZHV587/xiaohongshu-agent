// FeishuSync — the right-canvas "飞书同步协作" tab: bitable write,
// group-notify, and the flip-card re-auth.
function FeishuSync({ note, scanned, onScan }) {
  const { Card, Button, Select, Badge } = window.DesignSystem_71831b;
  const D = window.XHS_DATA;
  const [steps, setSteps] = React.useState(0); // 0 idle, 1-3 progress, 4 done
  const [syncing, setSyncing] = React.useState(false);

  const runSync = () => {
    if (syncing) return;
    setSyncing(true);
    setSteps(1);
    let s = 1;
    const tick = () => {
      s += 1;
      setSteps(s);
      if (s <= 3) setTimeout(tick, 850);
      else {
        setTimeout(() => { setSyncing(false); setSteps(0); }, 2600);
      }
    };
    setTimeout(tick, 850);
  };

  const stepLabels = ["正在验证飞书 CLI 环境配置...", "正在解析多维表格行结构与空字段映射...", "正在写入文案至多维表格..."];

  return (
    <div style={{ flex: 1, overflowY: "auto", padding: 24, display: "flex", flexDirection: "column", gap: 20 }} className="custom-scrollbar">
      {/* Bitable write */}
      <Card padding="md">
        <Row icon="database" iconTone="green" title="同步到飞书多维表格" sub="APP Token: bascnu… | Table ID: tblx…" badge={<Badge tone="synced">连接成功</Badge>} />
        <div style={{ display: "flex", flexDirection: "column", gap: 10, fontSize: "var(--text-xs)", marginTop: 14 }}>
          <KV k="绑定选题记录：" v={`${note.title} (第 4 行)`} />
          <KV k="飞书文档列映射：" v="「正文内容」字段" muted />
          <KV k="字数检测：" v={`${note.body.length} 字 (符合限制)`} ok />
        </div>

        {steps > 0 && (
          <div style={{ marginTop: 14, border: "1px solid var(--border-coral)", borderRadius: "var(--radius-md)", padding: 12, background: "var(--oats-light)", display: "flex", flexDirection: "column", gap: 8 }}>
            {stepLabels.map((label, i) => {
              const n = i + 1;
              const done = steps > n || steps === 4;
              const active = steps === n;
              return (
                <div key={i} style={{ display: "flex", alignItems: "center", gap: 8, fontSize: "var(--text-xs)", color: done ? "var(--success)" : active ? "var(--primary)" : "var(--text-subtle)", fontWeight: active ? 600 : 400 }}>
                  <span style={{ width: 14, textAlign: "center", animation: active ? "spin 1s linear infinite" : "none" }}>{done ? "✓" : active ? "◐" : "○"}</span>
                  {label}
                </div>
              );
            })}
          </div>
        )}

        <div style={{ marginTop: 14 }}>
          <Button variant="primary" block leftIcon={<Icon name="cloud-upload" size={16} />} onClick={runSync} loading={syncing}>
            {syncing ? "同步中…" : "立即同步至飞书多维表格"}
          </Button>
        </div>
      </Card>

      {/* Group notify */}
      <Card padding="md">
        <Row icon="message-square" iconTone="blue" title="群发通知与协同审核" sub="机器人消息 / 个人卡片群发" badge={<Badge tone="info">配置可用</Badge>} />
        <div style={{ display: "flex", flexDirection: "column", gap: 8, marginTop: 14 }}>
          <label style={{ fontSize: "var(--text-xs)", color: "var(--text-muted)", fontWeight: 600 }}>选择接收通知的飞书群聊：</label>
          <Select options={["小红书文案运营审核群 (oc_chat_10293)", "露营项目内容策划小组 (oc_chat_88301)", "博主内容备份群 (oc_chat_73229)"]} />
        </div>
        <div style={{ marginTop: 14 }}>
          <Button variant="secondary" block leftIcon={<Icon name="send" size={16} />}>一键发送通知至飞书群聊</Button>
        </div>
      </Card>

      {/* Re-auth flip card */}
      <div style={{ perspective: 1000, height: 240 }}>
        <div style={{ position: "relative", width: "100%", height: "100%", transformStyle: "preserve-3d", transition: "transform var(--dur-slow) var(--ease-out)", transform: scanned ? "rotateY(180deg)" : "none" }}>
          {/* front */}
          <div style={{ position: "absolute", inset: 0, backfaceVisibility: "hidden", background: "color-mix(in srgb, var(--hot-surface) 70%, white)", border: "1px solid var(--coral-300)", borderRadius: "var(--radius-lg)", padding: 18, display: "flex", flexDirection: "column", gap: 10 }}>
            <div style={{ display: "flex", gap: 8 }}>
              <Icon name="alert-triangle" size={17} color="var(--coral-600)" />
              <div>
                <h4 style={{ margin: 0, fontSize: "var(--text-xs)", fontWeight: 700, color: "var(--coral-700)" }}>飞书个人身份已过期</h4>
                <p style={{ margin: "2px 0 0", fontSize: 9, color: "var(--coral-600)" }}>若需以您的个人名义将文案导出至飞书云文档，请扫码进行 User 身份重连。</p>
              </div>
            </div>
            <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 8 }}>
              <button onClick={onScan} style={{ background: "#fff", padding: 8, border: "1px solid var(--coral-300)", borderRadius: "var(--radius-md)", boxShadow: "var(--shadow-md)", cursor: "pointer" }} title="点此模拟扫码成功">
                <div style={{ width: 84, height: 84, display: "grid", gridTemplateColumns: "repeat(3,1fr)", gap: 4, placeItems: "center" }}>
                  {[1,0,1,0,1,0,1,0,1].map((b, i) => <div key={i} style={{ width: 22, height: 22, background: b ? "var(--charcoal-default)" : "var(--gray-200)", borderRadius: 3 }} />)}
                </div>
              </button>
              <span style={{ fontSize: 8, color: "var(--coral-600)" }}>使用飞书扫码，授权 Scope 权限</span>
            </div>
          </div>
          {/* back */}
          <div style={{ position: "absolute", inset: 0, backfaceVisibility: "hidden", transform: "rotateY(180deg)", background: "var(--green-500)", color: "#fff", borderRadius: "var(--radius-lg)", padding: 18, display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", gap: 10, textAlign: "center" }}>
            <div style={{ width: 48, height: 48, borderRadius: "999px", background: "#fff", color: "var(--green-600)", display: "flex", alignItems: "center", justifyContent: "center", boxShadow: "var(--shadow-md)" }}>
              <Icon name="check" size={24} />
            </div>
            <div>
              <h4 style={{ margin: 0, fontSize: "var(--text-sm)", fontWeight: 700 }}>飞书个人身份重连成功</h4>
              <p style={{ margin: "4px 0 0", fontSize: 10, color: "rgba(255,255,255,0.85)" }}>欢迎回来，张潇潇！已获取所有云端权限。</p>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

function Row({ icon, iconTone, title, sub, badge }) {
  const tones = { green: { bg: "var(--success-surface)", fg: "var(--success)", bd: "var(--success-border)" }, blue: { bg: "var(--info-surface)", fg: "var(--info)", bd: "var(--info-border)" } };
  const t = tones[iconTone] || tones.green;
  return (
    <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", borderBottom: "1px solid var(--oats-dark)", paddingBottom: 12 }}>
      <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
        <div style={{ width: 32, height: 32, borderRadius: "var(--radius-sm)", background: t.bg, border: `1px solid ${t.bd}`, color: t.fg, display: "flex", alignItems: "center", justifyContent: "center" }}>
          <Icon name={icon} size={17} />
        </div>
        <div>
          <h4 style={{ margin: 0, fontSize: "var(--text-sm)", fontWeight: 700, color: "var(--text-body)" }}>{title}</h4>
          <p style={{ margin: "2px 0 0", fontSize: 10, color: "var(--text-subtle)" }}>{sub}</p>
        </div>
      </div>
      {badge}
    </div>
  );
}

function KV({ k, v, muted, ok }) {
  return (
    <div style={{ display: "flex", justifyContent: "space-between" }}>
      <span style={{ color: "var(--text-muted)" }}>{k}</span>
      <span style={{ fontWeight: 500, color: ok ? "var(--success)" : muted ? "var(--text-muted)" : "var(--text-body)" }}>{v}</span>
    </div>
  );
}

Object.assign(window, { FeishuSync });
