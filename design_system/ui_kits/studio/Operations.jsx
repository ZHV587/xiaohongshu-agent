// 账号运营 screen — 数据看板 · 选题库/爆款拆解 · 内容日历/排期 · 数据回填.
// hosting tweak: "page" (独立页面) | "inline" (会话内 agent 驱动) | "hybrid" (同屏融合)
function Operations({ hosting }) {
  if (hosting === "inline") return <OpsInline />;
  if (hosting === "hybrid") return <OpsHybrid />;
  return <OpsPage />;
}

// 多账号页：左侧账号矩阵栏 + （矩阵总览 / 单账号看板）
function OpsPage() {
  const S = window.STUDIO;
  const [acct, setAcct] = React.useState("all");
  const account = S.accounts.find((a) => a.id === acct);
  return (
    <div style={{ flex: 1, display: "flex", minHeight: 0, background: "var(--background)" }}>
      <AccountRail selected={acct} onSelect={setAcct} />
      <div className="cs" style={{ flex: 1, overflowY: "auto" }}>
        {acct === "all" ? <MatrixOverview onOpen={setAcct} /> : <DashboardBody account={account} />}
      </div>
    </div>
  );
}

function AccountRail({ selected, onSelect }) {
  const { actions } = useStudio();
  const S = window.STUDIO;
  const dot = (initial, tone) => ({ width: 26, height: 26, borderRadius: "999px", flexShrink: 0, display: "inline-flex", alignItems: "center", justifyContent: "center", fontSize: 11, fontWeight: 700, background: tone === "coral" ? "var(--accent-surface)" : tone === "topic" ? "var(--topicblue-light)" : "var(--oats-dark)", color: tone === "coral" ? "var(--primary)" : tone === "topic" ? "var(--topicblue-default)" : "var(--text-body)" });
  const Item = ({ id, label, sub, initial, tone, active }) => (
    <button onClick={() => onSelect(id)} style={{ display: "flex", alignItems: "center", gap: 9, width: "100%", textAlign: "left", padding: "9px 11px", borderRadius: "var(--radius-sm)", border: "none", cursor: "pointer", borderLeft: active ? "2px solid var(--primary)" : "2px solid transparent", background: active ? "var(--oats-dark)" : "transparent" }}>
      <span style={dot(initial, tone)}>{initial}</span>
      <span style={{ flex: 1, minWidth: 0 }}>
        <span style={{ display: "block", fontSize: "var(--text-xs)", fontWeight: 600, color: active ? "var(--primary)" : "var(--text-body)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{label}</span>
        <span style={{ display: "block", fontSize: 9, color: "var(--text-subtle)" }}>{sub}</span>
      </span>
    </button>
  );
  return (
    <aside className="cs" style={{ width: 208, borderRight: "1px solid var(--border)", background: "var(--surface-card)", flexShrink: 0, overflowY: "auto" }}>
      <div style={{ padding: 14, display: "flex", flexDirection: "column", gap: 6 }}>
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
          <Eyebrow>账号矩阵</Eyebrow>
          <span style={{ fontSize: 9, color: "var(--text-subtle)" }}>{S.accounts.length} 个</span>
        </div>
        <Item id="all" label="矩阵总览" sub="聚合 · 横向对比" initial="∑" tone="topic" active={selected === "all"} />
        <div style={{ height: 1, background: "var(--border)", margin: "4px 0" }} />
        {S.accounts.map((a) => <Item key={a.id} id={a.id} label={a.handle} sub={`${a.niche} · ${a.fans}`} initial={a.initial} tone={a.tone} active={selected === a.id} />)}
        <button onClick={() => actions.toast("➕ 接入新账号：扫码授权小红书账号（示意）")} style={{ display: "flex", alignItems: "center", gap: 6, marginTop: 4, padding: "8px 11px", border: "1px dashed var(--border-strong)", borderRadius: "var(--radius-sm)", background: "transparent", cursor: "pointer", color: "var(--text-subtle)", fontSize: "var(--text-xs)" }}><Icon name="plus" size={13} /> 接入新账号</button>
      </div>
    </aside>
  );
}

function MatrixOverview({ onOpen }) {
  const { StatCard, Card, Badge, Button } = window.DesignSystem_71831b;
  const { actions } = useStudio();
  const S = window.STUDIO;
  const sum = (k) => S.accounts.reduce((s, a) => s + a[k], 0);
  const fmt = (n) => (n >= 10000 ? (n / 10000).toFixed(1) + "w" : n.toLocaleString());
  const avgHot = Math.round(sum("hot") / S.accounts.length);
  const statusTone = { "主力": "synced", "成长": "info", "孵化": "draft" };
  const col = "2fr 1fr 0.9fr 0.8fr 0.7fr 0.8fr";
  return (
    <div style={{ padding: 28, maxWidth: 1180, margin: "0 auto", display: "flex", flexDirection: "column", gap: 20 }}>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
        <div>
          <div style={{ fontFamily: "var(--font-display)", fontWeight: 800, fontSize: "var(--text-xl)" }}>账号矩阵总览</div>
          <div style={{ fontSize: "var(--text-xs)", color: "var(--text-muted)", marginTop: 3 }}>{S.accounts.length} 个账号 · 近 7 天 · 数据底座聚合（performance_metric）</div>
        </div>
        <Button variant="secondary" size="sm" leftIcon={<Icon name="download" size={13} />} onClick={() => actions.toast("📊 矩阵周报已导出（示意）")}>导出矩阵周报</Button>
      </div>
      <section>
        <Eyebrow style={{ marginBottom: 10 }}>矩阵聚合</Eyebrow>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 12 }}>
          <StatCard label="矩阵总粉丝" value={fmt(sum("fansNum"))} delta={14} tone="coral" icon={<Icon name="users" size={15} />} />
          <StatCard label="本周新增粉丝" value={"+" + sum("dFans")} unit="人" delta={22} tone="success" icon={<Icon name="user-plus" size={15} />} />
          <StatCard label="本周发布" value={sum("posts")} unit="篇" delta={8} tone="topic" icon={<Icon name="file-text" size={15} />} />
          <StatCard label="平均爆款率" value={avgHot} unit="%" delta={5} icon={<Icon name="flame" size={15} />} />
        </div>
      </section>
      <section style={{ display: "flex", flexDirection: "column", gap: 10 }}>
        <PanelHead icon="layout-grid" title="账号横向对比" sub="点任意账号进入它的运营看板" />
        <Card padding="none" style={{ overflow: "hidden" }}>
          <div style={{ display: "grid", gridTemplateColumns: col, padding: "9px 14px", borderBottom: "1px solid var(--border)", fontSize: 9, fontWeight: 700, color: "var(--text-subtle)", letterSpacing: "var(--tracking-wide)" }}>
            <span>账号</span><span>垂类</span><span>粉丝</span><span>近7天</span><span>爆款率</span><span>状态</span>
          </div>
          {S.accounts.map((a, i) => (
            <button key={a.id} onClick={() => onOpen(a.id)} style={{ display: "grid", gridTemplateColumns: col, alignItems: "center", width: "100%", textAlign: "left", padding: "11px 14px", border: "none", borderTop: i ? "1px solid var(--border)" : "none", background: "transparent", cursor: "pointer", fontSize: "var(--text-xs)" }}>
              <span style={{ display: "flex", alignItems: "center", gap: 8, minWidth: 0 }}>
                <span style={{ width: 24, height: 24, borderRadius: "999px", flexShrink: 0, display: "inline-flex", alignItems: "center", justifyContent: "center", fontSize: 10, fontWeight: 700, background: a.tone === "coral" ? "var(--accent-surface)" : a.tone === "topic" ? "var(--topicblue-light)" : "var(--oats-dark)", color: a.tone === "coral" ? "var(--primary)" : a.tone === "topic" ? "var(--topicblue-default)" : "var(--text-body)" }}>{a.initial}</span>
                <span style={{ fontWeight: 600, color: "var(--text-body)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{a.handle}</span>
              </span>
              <span style={{ color: "var(--text-muted)" }}>{a.niche}</span>
              <span className="font-tabular" style={{ fontWeight: 600 }}>{a.fans}</span>
              <span className="font-tabular" style={{ color: "var(--success)", fontWeight: 600 }}>+{a.dFans}</span>
              <span style={{ color: "var(--hot)", fontWeight: 700 }}>🔥{a.hot}</span>
              <span><Badge tone={statusTone[a.status]} shape="chip">{a.status}</Badge></span>
            </button>
          ))}
        </Card>
      </section>
      <CalendarSection />
    </div>
  );
}

function DashboardBody({ dense = false, account = null }) {
  const { StatCard, Button } = window.DesignSystem_71831b;
  const { actions } = useStudio();
  const S = window.STUDIO;
  const acct = account || { handle: S.user.handle, fans: S.user.fans, niche: "" };
  return (
    <div style={{ padding: dense ? 16 : 28, maxWidth: 1180, margin: "0 auto", display: "flex", flexDirection: "column", gap: 20 }}>
      {!dense && (
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
          <div>
            <div style={{ fontFamily: "var(--font-display)", fontWeight: 800, fontSize: "var(--text-xl)" }}>{acct.handle}</div>
            <div style={{ fontSize: "var(--text-xs)", color: "var(--text-muted)", marginTop: 3 }}>粉丝 {acct.fans}{acct.niche ? ` · ${acct.niche}` : ""} · 近 7 天 · 数据底座 / 飞书同步</div>
          </div>
          <div style={{ display: "flex", gap: 8 }}>
            <Button variant="secondary" size="sm" leftIcon={<Icon name="download" size={13} />} onClick={() => actions.toast("📄 该账号周报已导出（示意）")}>导出周报</Button>
            <Button variant="primary" size="sm" leftIcon={<Icon name="pencil" size={13} />} onClick={() => actions.toast("✏️ 下拉到「数据回填」即可录入真实表现")}>数据回填</Button>
          </div>
        </div>
      )}

      {/* 数据看板 */}
      <section>
        <Eyebrow style={{ marginBottom: 10 }}>数据看板</Eyebrow>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 12 }}>
          {S.dashboard.map((d) => <StatCard key={d.label} label={d.label} value={d.value} unit={d.unit} delta={d.delta} tone={d.tone} icon={<Icon name={d.icon} size={15} />} />)}
        </div>
      </section>

      <LibrarySection />
      <CalendarSection accountFilter={account ? account.initial : null} />

      {!dense && <PublishPipeline account={account} />}
      {!dense && <BackfillSection />}
    </div>
  );
}

// 选题库 / 爆款拆解
function LibrarySection() {
  const { Card, Badge, Button } = window.DesignSystem_71831b;
  const { actions } = useStudio();
  const S = window.STUDIO;
  const [sel, setSel] = React.useState(1);
  const td = S.teardown;
  const selItem = S.library.find((x) => x.id === sel);
  const statusTone = { "已发布": "synced", "排期中": "info", "草稿": "draft" };
  return (
    <section style={{ display: "flex", flexDirection: "column", gap: 10 }}>
      <PanelHead icon="library-big" title="选题库 · 爆款拆解" sub="沉淀的选题与表现，点击拆解爆款套路" />
      <Card padding="none" style={{ overflow: "hidden" }}>
        {S.library.map((it, i) => {
          const on = it.id === sel;
          return (
            <button key={it.id} onClick={() => setSel(it.id)} style={{ display: "flex", alignItems: "center", gap: 10, width: "100%", textAlign: "left", padding: "11px 13px", border: "none", borderTop: i ? "1px solid var(--border)" : "none", cursor: "pointer", background: on ? "var(--accent-surface)" : "transparent" }}>
              <span style={{ fontSize: 11, fontWeight: 700, color: "var(--hot)", width: 38, flexShrink: 0 }}>🔥{it.hot}</span>
              <span style={{ flex: 1, minWidth: 0 }}>
                <span style={{ display: "block", fontSize: "var(--text-xs)", fontWeight: 600, color: "var(--text-body)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{it.title}</span>
                <span style={{ display: "block", fontSize: 10, color: "var(--text-subtle)", marginTop: 2 }}>{it.angle} · 赞 {it.likes} · 藏 {it.saves}</span>
              </span>
              <Badge tone={statusTone[it.status]} shape="chip">{it.status}</Badge>
            </button>
          );
        })}
      </Card>
      {/* teardown */}
      <Card padding="md" tone="sunken">
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 9 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 7, minWidth: 0 }}>
            <Icon name="scan-search" size={15} color="var(--primary)" />
            <span style={{ fontSize: "var(--text-xs)", fontWeight: 700, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>爆款拆解 · {selItem ? selItem.title : td.title}</span>
          </div>
          <Button variant="soft" size="sm" leftIcon={<Icon name="copy-plus" size={12} />} onClick={() => actions.reuse(sel <= 3 ? sel : 1)}>复用选题</Button>
        </div>
        <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
          {td.points.map((p) => (
            <div key={p.label} style={{ display: "flex", gap: 9 }}>
              <span style={{ fontSize: 10, fontWeight: 700, color: "var(--primary)", background: "var(--accent-surface)", border: "1px solid var(--border-coral)", borderRadius: 6, padding: "2px 7px", height: "fit-content", flexShrink: 0 }}>{p.label}</span>
              <span style={{ fontSize: 11, color: "var(--text-muted)", lineHeight: 1.5 }}>{p.detail}</span>
            </div>
          ))}
        </div>
      </Card>
    </section>
  );
}

// 内容日历 / 发布排期
function CalendarSection({ accountFilter = null }) {
  const { Card } = window.DesignSystem_71831b;
  const { calendar } = useStudio();
  const S = window.STUDIO;
  const toneColor = { coral: "var(--primary)", topic: "var(--topicblue-default)", draft: "var(--text-subtle)" };
  const toneBg = { coral: "var(--accent-surface)", topic: "var(--topicblue-light)", draft: "var(--oats-dark)" };
  const byDate = {};
  calendar.forEach((d) => { byDate[d.date] = accountFilter ? d.items.filter((it) => !it.acct || it.acct === accountFilter) : d.items; });
  const m = S.month;
  const cells = [];
  for (let i = 0; i < m.firstOffset; i++) cells.push(null);
  for (let d = 1; d <= m.days; d++) cells.push(d);
  return (
    <section style={{ display: "flex", flexDirection: "column", gap: 10 }}>
      <PanelHead icon="calendar-days" title="内容日历 · 发布排期" sub={`${m.label} · ${accountFilter ? "该账号" : "跨账号矩阵"}排期`} right={<span style={{ display: "inline-flex", gap: 6, color: "var(--text-subtle)" }}><Icon name="chevron-left" size={15} /><Icon name="chevron-right" size={15} /></span>} />
      <Card padding="md">
        <div style={{ display: "grid", gridTemplateColumns: "repeat(7, 1fr)", gap: 5 }}>
          {S.weekdays.map((w) => <div key={w} style={{ textAlign: "center", fontSize: 10, fontWeight: 600, color: "var(--text-subtle)", paddingBottom: 4 }}>{w}</div>)}
          {cells.map((d, idx) => d === null
            ? <div key={"b" + idx} />
            : (
              <div key={d} style={{ minHeight: 66, borderRadius: "var(--radius-sm)", border: "1px solid var(--border)", background: (byDate[d] && byDate[d].length) ? "var(--surface-card)" : "var(--oats-light)", padding: 4, display: "flex", flexDirection: "column", gap: 3 }}>
                <span style={{ fontSize: 10, color: "var(--text-subtle)", fontWeight: 600 }}>{d}</span>
                {(byDate[d] || []).map((it, i) => (
                  <div key={i} style={{ background: toneBg[it.tone], borderLeft: `2px solid ${toneColor[it.tone]}`, borderRadius: 3, padding: "2px 3px" }}>
                    <div style={{ display: "flex", alignItems: "center", gap: 2 }}>
                      {it.acct && <span style={{ width: 11, height: 11, borderRadius: "999px", background: toneColor[it.tone], color: "#fff", fontSize: 7, display: "inline-flex", alignItems: "center", justifyContent: "center", flexShrink: 0 }}>{it.acct}</span>}
                      <div style={{ fontSize: 8, fontWeight: 600, color: "var(--text-body)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{it.t}</div>
                    </div>
                  </div>
                ))}
              </div>
            ))}
        </div>
        <div style={{ display: "flex", gap: 14, marginTop: 10, fontSize: 10, color: "var(--text-subtle)" }}>
          <span style={{ display: "inline-flex", alignItems: "center", gap: 4 }}><span style={{ width: 8, height: 8, borderRadius: 2, background: "var(--primary)" }} />已排期</span>
          <span style={{ display: "inline-flex", alignItems: "center", gap: 4 }}><span style={{ width: 8, height: 8, borderRadius: 2, background: "var(--topicblue-default)" }} />跨账号</span>
          <span style={{ display: "inline-flex", alignItems: "center", gap: 4 }}><span style={{ width: 8, height: 8, borderRadius: 2, background: "var(--text-subtle)" }} />草稿待定</span>
        </div>
      </Card>
    </section>
  );
}

// 数据回填
function BackfillSection() {
  const { StatCard, Card, Button, Badge } = window.DesignSystem_71831b;
  const { actions } = useStudio();
  const [vals, setVals] = React.useState({ views: "12480", likes: "1240", saves: "864", comments: "207" });
  const set = (k) => (v) => setVals((p) => ({ ...p, [k]: v }));
  return (
    <section style={{ display: "flex", flexDirection: "column", gap: 10 }}>
      <PanelHead icon="clipboard-pen" title="数据回填" sub="发布后录入真实表现，沉淀回飞书 → 训练下一轮选题" right={<Badge tone="info">效果反馈闭环</Badge>} />
      <Card padding="md">
        <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 12, marginBottom: 12 }}>
          <StatCard label="实际浏览量" value={vals.views} editable onValueChange={set("views")} />
          <StatCard label="点赞" value={vals.likes} editable onValueChange={set("likes")} tone="coral" />
          <StatCard label="收藏" value={vals.saves} editable onValueChange={set("saves")} tone="success" />
          <StatCard label="评论" value={vals.comments} editable onValueChange={set("comments")} />
        </div>
        <div style={{ display: "flex", justifyContent: "flex-end", gap: 8 }}>
          <Button variant="ghost" size="sm" onClick={() => actions.toast("📥 已从小红书后台导入近 7 天数据")}>从小红书后台导入</Button>
          <Button variant="primary" size="sm" leftIcon={<Icon name="cloud-upload" size={13} />} onClick={actions.backfillSave}>保存并同步飞书</Button>
        </div>
      </Card>
    </section>
  );
}

// 发布管线 · 回链闭环（待发布 → 已发布·回链 → 已回填）
function PublishPipeline({ account }) {
  const { Card, Badge, Button } = window.DesignSystem_71831b;
  const S = window.STUDIO;
  const filter = account ? account.initial : null;
  const q = filter ? S.publishQueue.filter((x) => x.acct === filter) : S.publishQueue;
  const stages = [
    { key: "scheduled", label: "待发布", icon: "clock" },
    { key: "published", label: "已发布 · 回链", icon: "link" },
    { key: "measured", label: "已回填", icon: "check-circle-2" },
  ];
  return (
    <section style={{ display: "flex", flexDirection: "column", gap: 10 }}>
      <PanelHead icon="git-branch" title="发布管线 · 回链闭环" sub="小红书无开放发布 API：人工/半自动发布后贴回链 → 拿到数据回填" right={<Badge tone="info">最后一公里</Badge>} />
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 12 }}>
        {stages.map((st) => {
          const items = q.filter((x) => x.stage === st.key);
          return (
            <Card key={st.key} padding="sm">
              <div style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 8 }}>
                <Icon name={st.icon} size={13} color="var(--text-muted)" />
                <span style={{ fontSize: 11, fontWeight: 700 }}>{st.label}</span>
                <span style={{ marginLeft: "auto", fontSize: 10, color: "var(--text-subtle)" }}>{items.length}</span>
              </div>
              <div style={{ display: "flex", flexDirection: "column", gap: 7 }}>
                {items.length === 0 && <span style={{ fontSize: 10, color: "var(--text-subtle)" }}>—</span>}
                {items.map((it) => (
                  <div key={it.id} style={{ border: "1px solid var(--border)", borderRadius: "var(--radius-sm)", padding: "7px 8px", background: "var(--oats-light)" }}>
                    <div style={{ display: "flex", alignItems: "center", gap: 5 }}>
                      <span style={{ width: 14, height: 14, borderRadius: 999, background: "var(--accent-surface)", color: "var(--primary)", fontSize: 8, fontWeight: 700, display: "inline-flex", alignItems: "center", justifyContent: "center", flexShrink: 0 }}>{it.acct}</span>
                      <span style={{ fontSize: 10, fontWeight: 600, color: "var(--text-body)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{it.title}</span>
                    </div>
                    <div style={{ fontSize: 9, color: "var(--text-subtle)", marginTop: 3, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{it.link ? `🔗 ${it.link}` : it.time}</div>
                    {st.key === "scheduled" && <Button variant="soft" size="sm" block style={{ marginTop: 6 }} leftIcon={<Icon name="send" size={11} />}>标记已发 · 贴回链</Button>}
                    {st.key === "published" && <Button variant="soft" size="sm" block style={{ marginTop: 6 }} leftIcon={<Icon name="clipboard-pen" size={11} />}>回填数据</Button>}
                  </div>
                ))}
              </div>
            </Card>
          );
        })}
      </div>
    </section>
  );
}

// hosting: 会话内 (agent-driven, single conversation does everything)
function OpsInline() {
  const { Avatar, Card } = window.DesignSystem_71831b;
  const msgs = [
    { who: "user", text: "看下我账号本周的数据，再把下周露营选题排上。" },
    { who: "ai", text: "已从飞书拉取近 7 天数据 👇", module: "stats" },
    { who: "ai", text: "帮你拆解了本周最高赞笔记的套路，并排好了下周内容日历：", module: "cal" },
    { who: "user", text: "「露营避坑」那篇发布了，帮我回填真实数据。" },
    { who: "ai", text: "好的，录入后我会沉淀回飞书、用于优化下一轮选题：", module: "backfill" },
  ];
  return (
    <div className="cs" style={{ flex: 1, overflowY: "auto", background: "var(--background)" }}>
      <div style={{ maxWidth: 760, margin: "0 auto", padding: 24, display: "flex", flexDirection: "column", gap: 16 }}>
        <div style={{ textAlign: "center", fontSize: "var(--text-xs)", color: "var(--text-subtle)", background: "var(--oats-dark)", borderRadius: 999, padding: "5px 12px", alignSelf: "center" }}>一个会话里完成全部运营动作 · agent 驱动</div>
        {msgs.map((m, i) => m.who === "user" ? (
          <div key={i} style={{ display: "flex", gap: 11, alignSelf: "flex-end", flexDirection: "row-reverse", maxWidth: "85%" }}>
            <Avatar name="我" variant="solid" size={30} />
            <div style={{ background: "var(--surface-card)", border: "1px solid var(--border-coral)", borderRadius: "var(--radius-xl)", padding: "11px 15px", fontSize: "var(--text-sm)", boxShadow: "var(--shadow-sm)" }}>{m.text}</div>
          </div>
        ) : (
          <div key={i} style={{ display: "flex", gap: 11, maxWidth: "94%" }}>
            <Avatar glyph="🍠" variant="agent" size={32} />
            <div style={{ flex: 1, display: "flex", flexDirection: "column", gap: 9, minWidth: 0 }}>
              <div style={{ background: "var(--surface-card)", border: "1px solid var(--border-coral)", borderRadius: "var(--radius-xl)", padding: "11px 15px", fontSize: "var(--text-sm)", boxShadow: "var(--shadow-sm)", alignSelf: "flex-start" }}>{m.text}</div>
              {m.module === "stats" && <StatsMini />}
              {m.module === "cal" && <Card padding="md"><CalInline /></Card>}
              {m.module === "backfill" && <BackfillSection />}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

function StatsMini() {
  const { StatCard } = window.DesignSystem_71831b;
  const S = window.STUDIO;
  return <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 10 }}>{S.dashboard.map((d) => <StatCard key={d.label} label={d.label} value={d.value} unit={d.unit} delta={d.delta} tone={d.tone} icon={<Icon name={d.icon} size={15} />} />)}</div>;
}
function CalInline() { return <CalendarSection />; }

// hosting: 同屏融合 (chat + dashboard side by side)
function OpsHybrid() {
  const { Avatar, Textarea, Button } = window.DesignSystem_71831b;
  return (
    <div style={{ flex: 1, display: "flex", minHeight: 0, background: "var(--background)" }}>
      <section style={{ width: 380, borderRight: "1px solid var(--border)", background: "var(--surface-card)", display: "flex", flexDirection: "column", flexShrink: 0 }}>
        <div className="cs" style={{ flex: 1, overflowY: "auto", padding: 18, display: "flex", flexDirection: "column", gap: 14 }}>
          <PanelHead icon="bot" title="运营助手" sub="发起动作 · 右侧看汇总" />
          {[
            { who: "user", t: "拉本周数据 + 排下周选题" },
            { who: "ai", t: "已更新右侧看板与日历 ✅ 最高赞是「搬家式装备清单」，套路已拆解。" },
            { who: "user", t: "把避坑那篇的真实数据回填一下" },
            { who: "ai", t: "右侧「数据回填」已就绪，录入后同步飞书。" },
          ].map((m, i) => (
            <div key={i} style={{ display: "flex", gap: 9, flexDirection: m.who === "user" ? "row-reverse" : "row" }}>
              {m.who === "user" ? <Avatar name="我" variant="solid" size={26} /> : <Avatar glyph="🍠" variant="agent" size={26} />}
              <div style={{ background: m.who === "user" ? "var(--accent-surface)" : "var(--oats-light)", border: "1px solid var(--border)", borderRadius: "var(--radius-md)", padding: "8px 11px", fontSize: "var(--text-xs)", lineHeight: 1.5 }}>{m.t}</div>
            </div>
          ))}
        </div>
        <div style={{ padding: 14, borderTop: "1px solid var(--border)" }}>
          <Textarea rows={1} placeholder="发起运营动作…" footer={<><span style={{ fontSize: 10, color: "var(--text-subtle)" }}>agent 会更新右侧看板</span><Button variant="primary" size="sm">发送</Button></>} />
        </div>
      </section>
      <div className="cs" style={{ flex: 1, overflowY: "auto" }}><DashboardBody dense /></div>
    </div>
  );
}

Object.assign(window, { Operations });
