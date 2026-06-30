// 创作栏 Composer — 小红书-native editor bound to the shared note.
// Live 文案体检, working AI actions, tag matrix, multi-version, 定稿排期.
function Composer({ layout }) {
  const { Input, Textarea, Button, HashtagTag, Badge } = window.DesignSystem_71831b;
  const { note, actions } = useStudio();
  const S = window.STUDIO;
  const bodyRef = React.useRef(null);

  if (note.status === "idle") return <EmptyComposer />;

  const writing = note.status === "writing";
  const checks = computeChecks(note);
  const score = scoreOf(checks);

  const insertEmoji = (e) => {
    const el = bodyRef.current;
    if (!el) { actions.updateField("body", (note.body || "") + e); return; }
    const s = el.selectionStart, en = el.selectionEnd;
    actions.updateField("body", note.body.slice(0, s) + e + note.body.slice(en));
    requestAnimationFrame(() => { el.focus(); el.selectionStart = el.selectionEnd = s + e.length; });
  };

  return (
    <div className="cs" style={{ display: "flex", flexDirection: "column", gap: 14, height: "100%", overflowY: "auto" }}>
      <PanelHead icon="pen-line" title="创作栏" sub="小红书笔记 · 边写边体检"
        right={layout === "deep" ? null : <Button variant="ghost" size="sm" leftIcon={<Icon name="feather" size={13} />} onClick={() => actions.setSection("deep")}>深度创作</Button>} />

      {/* 多版本草稿 */}
      {note.versions && (
        <div style={{ display: "flex", gap: 6 }}>
          {["A", "B", "C"].map((id) => {
            const v = note.versions[id], on = id === note.activeVersion;
            return (
              <button key={id} onClick={() => actions.setVersion(id)} title={v.title} style={{
                flex: 1, textAlign: "left", padding: "7px 9px", borderRadius: "var(--radius-sm)", cursor: "pointer",
                border: `1px solid ${on ? "var(--primary)" : "var(--border)"}`, background: on ? "var(--accent-surface)" : "var(--surface-card)" }}>
                <div style={{ fontSize: 10, fontWeight: 700, color: on ? "var(--primary)" : "var(--text-body)" }}>{v.label}</div>
                <div style={{ fontSize: 9, color: "var(--text-subtle)", marginTop: 2 }}>{v.note}</div>
              </button>
            );
          })}
        </div>
      )}

      <VisualStudio />

      {/* 标题 */}
      <div style={{ display: "flex", flexDirection: "column", gap: 5 }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
          <Eyebrow>标题 · 钩子优先</Eyebrow>
          <span className="font-tabular" style={{ fontSize: 10, color: note.title.length > 20 ? "var(--warning)" : "var(--text-subtle)" }}>{note.title.length} / 20</span>
        </div>
        <Input value={note.title} onChange={(e) => actions.updateField("title", e.target.value)} />
      </div>

      {/* 正文 */}
      <div style={{ display: "flex", flexDirection: "column", gap: 5 }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
          <Eyebrow>正文 {writing && <span style={{ color: "var(--primary)", marginLeft: 6 }}>🍠 撰写中…</span>}</Eyebrow>
          <div style={{ display: "flex", gap: 5 }}>
            <Button variant="soft" size="sm" leftIcon={<Icon name="sparkles" size={12} />} onClick={actions.polish} disabled={writing}>润色</Button>
            <Button variant="soft" size="sm" leftIcon={<Icon name="scissors" size={12} />} onClick={actions.shorten} disabled={writing}>瘦身</Button>
            <Button variant="soft" size="sm" leftIcon={<Icon name="hash" size={12} />} onClick={actions.addTags} disabled={writing}>配标签</Button>
          </div>
        </div>
        <Textarea innerRef={bodyRef} value={writing ? note.body + " ▍" : note.body} onChange={(e) => actions.updateField("body", e.target.value)} rows={layout === "split" ? 7 : 9} readOnly={writing}
          footer={<>
            <div style={{ display: "flex", gap: 3, flexWrap: "wrap" }}>
              {S.quickEmoji.slice(0, 10).map((e) => <button key={e} onClick={() => insertEmoji(e)} disabled={writing} style={{ border: "none", background: "transparent", cursor: "pointer", fontSize: 15, lineHeight: 1, padding: 1, opacity: writing ? 0.4 : 1 }}>{e}</button>)}
            </div>
            <Badge tone={note.body.length > 1000 ? "hot" : "synced"} shape="chip">{note.body.length} / 1000</Badge>
          </>} />
      </div>

      {/* 话题标签 */}
      <div style={{ display: "flex", flexDirection: "column", gap: 7 }}>
        <Eyebrow>话题标签 · {note.tags.length} 个（建议 5–10，大词+长尾）</Eyebrow>
        <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
          {note.tags.map((t) => (
            <span key={t} onClick={() => actions.removeTag(t)} title="点击移除" style={{ cursor: "pointer" }}>
              <HashtagTag>{t}</HashtagTag>
            </span>
          ))}
          {note.tags.length === 0 && <span style={{ fontSize: 11, color: "var(--text-subtle)" }}>暂无，点下方推荐添加</span>}
        </div>
        <div style={{ display: "flex", flexWrap: "wrap", gap: 6, paddingTop: 2 }}>
          <span style={{ fontSize: 10, color: "var(--text-subtle)", alignSelf: "center" }}>推荐：</span>
          {S.recommendedTags.filter((t) => !note.tags.includes(t)).slice(0, 5).map((t) => <HashtagTag key={t} addable onAdd={() => actions.addTag(t)}>{t}</HashtagTag>)}
        </div>
      </div>

      {layout !== "deep" && (<>
        <CopyDoctor checks={checks} score={score} />
        <RiskPanel note={note} />
        <ScheduleBar score={score} status={note.status} />
      </>)}
    </div>
  );
}

function EmptyComposer() {
  return (
    <div style={{ height: "100%", display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", textAlign: "center", gap: 12, padding: 24, color: "var(--text-subtle)" }}>
      <div style={{ width: 56, height: 56, borderRadius: "var(--radius-lg)", background: "var(--accent-surface)", display: "flex", alignItems: "center", justifyContent: "center", fontSize: 26 }}>🍠</div>
      <div style={{ fontSize: "var(--text-sm)", fontWeight: 700, color: "var(--text-body)" }}>从选题卡开始创作</div>
      <div style={{ fontSize: "var(--text-xs)", maxWidth: 240, lineHeight: "var(--leading-relaxed)" }}>点任意一张<b style={{ color: "var(--primary)" }}>选题卡</b>，🍠 会按小红书风格流式生成草稿到这里，然后边改边体检。</div>
    </div>
  );
}

// 文案体检 scorecard — grouped, driven by the extensible rule library
function CopyDoctor({ checks, score }) {
  const store = useStudio();
  const groups = [];
  checks.forEach((c) => { let g = groups.find((x) => x.name === c.group); if (!g) { g = { name: c.group, items: [] }; groups.push(g); } g.items.push(c); });
  return (
    <div style={{ background: "var(--surface-card)", border: "1px solid var(--border-coral)", borderRadius: "var(--radius-lg)", padding: 12, display: "flex", flexDirection: "column", gap: 10 }}>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
        <div style={{ display: "flex", alignItems: "center", gap: 7 }}>
          <Icon name="stethoscope" size={15} color="var(--primary)" />
          <span style={{ fontSize: "var(--text-xs)", fontWeight: 700 }}>小红书文案体检</span>
          <span style={{ fontSize: 10, color: "var(--text-subtle)" }}>· {checks.length} 项规则</span>
        </div>
        <span style={{ fontFamily: "var(--font-display)", fontWeight: 800, fontSize: "var(--text-lg)", color: score >= 80 ? "var(--success)" : score >= 60 ? "var(--warning)" : "var(--text-muted)" }}>{score}<span style={{ fontSize: 11, color: "var(--text-subtle)", fontWeight: 400 }}> 分</span></span>
      </div>
      <div className="cs" style={{ display: "flex", flexDirection: "column", gap: 9, maxHeight: 240, overflowY: "auto" }}>
        {groups.map((g) => {
          const ok = g.items.filter((i) => i.pass).length;
          return (
            <div key={g.name} style={{ display: "flex", flexDirection: "column", gap: 5 }}>
              <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
                <Eyebrow>{g.name}</Eyebrow>
                <span style={{ fontSize: 9, color: ok === g.items.length ? "var(--success)" : "var(--text-subtle)", fontWeight: 600 }}>{ok}/{g.items.length}</span>
              </div>
              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 6 }}>
                {g.items.map((c) => (
                  <div key={c.key} title={c.hint} style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 11, padding: "5px 8px", borderRadius: "var(--radius-sm)", background: c.pass ? "var(--success-surface)" : "var(--warning-surface)", transition: "background var(--dur-base) var(--ease-out)" }}>
                    <Icon name={c.pass ? "check-circle-2" : "alert-circle"} size={13} color={c.pass ? "var(--success)" : "var(--warning)"} />
                    <span style={{ color: "var(--text-body)", fontWeight: 500, whiteSpace: "nowrap" }}>{c.label}</span>
                    <span style={{ marginLeft: "auto", color: "var(--text-subtle)", fontSize: 10, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis", maxWidth: 66 }}>{c.value}</span>
                  </div>
                ))}
              </div>
            </div>
          );
        })}
      </div>
      <button onClick={() => store?.actions?.toast?.("规则库可持续扩展：在 data.js 的 checkRules 里增删规则即可（已内置 12 项）")} style={{ alignSelf: "flex-start", display: "inline-flex", alignItems: "center", gap: 5, background: "none", border: "none", cursor: "pointer", color: "var(--primary)", fontSize: 10, fontWeight: 600, padding: 0 }}>
        <Icon name="settings-2" size={12} /> 管理体检规则库
      </button>
    </div>
  );
}

// 定稿 → 排期 bar
function ScheduleBar({ score, status }) {
  const { Button, Badge } = window.DesignSystem_71831b;
  const { actions } = useStudio();
  const [picking, setPicking] = React.useState(false);
  const ready = score >= 80;
  const scheduled = status === "scheduled";

  return (
    <div style={{ borderTop: "1px solid var(--border)", paddingTop: 12, display: "flex", flexDirection: "column", gap: 8, position: "sticky", bottom: 0, background: "var(--surface-card)" }}>
      {scheduled ? (
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
          <Badge tone="synced" dot>已定稿并排期</Badge>
          <Button variant="ghost" size="sm" leftIcon={<Icon name="line-chart" size={13} />} onClick={() => actions.setSection("ops")}>去运营看排期</Button>
        </div>
      ) : picking ? (
        <div style={{ display: "flex", flexDirection: "column", gap: 7 }}>
          <div style={{ fontSize: 11, color: "var(--text-muted)" }}>排期到 {window.STUDIO.month.label} 哪天发布？</div>
          <div className="cs" style={{ display: "grid", gridTemplateColumns: "repeat(7, 1fr)", gap: 4, maxHeight: 140, overflowY: "auto" }}>
            {Array.from({ length: window.STUDIO.month.days }, (_, i) => i + 1).map((d) => (
              <button key={d} onClick={() => { actions.schedule(d); setPicking(false); }} style={{ padding: "6px 0", borderRadius: "var(--radius-xs)", border: "1px solid var(--border)", background: "var(--oats-light)", cursor: "pointer", fontSize: 11, fontWeight: 600, color: "var(--text-body)" }}>{d}</button>
            ))}
          </div>
        </div>
      ) : (
        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <span style={{ fontSize: 11, color: "var(--text-subtle)", flex: 1 }}>{ready ? "体检达标，可以定稿啦 🎉" : `体检 ${score} 分，建议 ≥80 再发`}</span>
          <Button variant="secondary" size="sm" leftIcon={<Icon name="cloud-upload" size={13} />} onClick={actions.syncFeishu}>同步飞书</Button>
          <Button variant="primary" size="sm" leftIcon={<Icon name="calendar-check" size={13} />} onClick={() => setPicking(true)} disabled={!ready}>定稿并排期</Button>
        </div>
      )}
    </div>
  );
}

// 封面 + 图集 · 图文工作台（小红书第一要素是图：封面权重 > 正文）
function VisualStudio() {
  const { Button } = window.DesignSystem_71831b;
  const { note, actions } = useStudio();
  const S = window.STUDIO;
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
        <Eyebrow>封面 + 图集 · 图文工作台</Eyebrow>
        <span style={{ fontSize: 9, color: "var(--text-subtle)" }}>封面决定点击率</span>
      </div>
      <div className="cs" style={{ display: "flex", gap: 8, overflowX: "auto", paddingBottom: 2 }}>
        {S.imageRoles.map((role, i) => {
          const isCover = i === 0;
          return (
            <div key={role} style={{ width: 80, flexShrink: 0, display: "flex", flexDirection: "column", gap: 4 }}>
              <div style={{ position: "relative", width: 80, height: 107, borderRadius: "var(--radius-md)", overflow: "hidden", border: isCover ? "2px solid var(--primary)" : "1px solid var(--border)" }}>
                <img src={S.images[i % S.images.length]} alt={role} style={{ width: "100%", height: "100%", objectFit: "cover" }} />
                {isCover && (<>
                  <div style={{ position: "absolute", inset: 0, background: "linear-gradient(180deg,rgba(0,0,0,.05),rgba(0,0,0,.42))" }} />
                  <div style={{ position: "absolute", top: 6, left: 6, right: 6, color: "#fff", fontFamily: "var(--font-display)", fontWeight: 800, fontSize: 12, lineHeight: 1.12, textShadow: "0 1px 4px rgba(0,0,0,.45)", whiteSpace: "pre-line" }}>{note.cover}</div>
                  <span style={{ position: "absolute", bottom: 5, left: 5, fontSize: 8, fontWeight: 700, color: "var(--primary)", background: "#fff", borderRadius: 4, padding: "1px 4px" }}>封面</span>
                </>)}
              </div>
              <span style={{ fontSize: 8, color: "var(--text-subtle)", textAlign: "center", lineHeight: 1.2 }}>{role}</span>
            </div>
          );
        })}
        <button onClick={() => actions.toast("🖼️ AI 配图建议生成中（示意）")} style={{ width: 80, height: 107, flexShrink: 0, borderRadius: "var(--radius-md)", border: "1px dashed var(--border-strong)", background: "var(--oats-light)", display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", gap: 4, cursor: "pointer", color: "var(--text-subtle)" }}>
          <Icon name="image-plus" size={16} /><span style={{ fontSize: 8 }}>AI 出图</span>
        </button>
      </div>
      <div style={{ display: "flex", gap: 6 }}>
        <Button variant="secondary" size="sm" leftIcon={<Icon name="wand-2" size={13} />} onClick={() => actions.updateField("cover", note.versions ? note.versions[note.activeVersion].cover : (note.cover || "爆点\n大字"))}>换封面文案</Button>
        <Button variant="ghost" size="sm" leftIcon={<Icon name="layout-template" size={13} />} onClick={() => actions.toast("🎨 已套用爆款版式（示意）")}>套版式</Button>
      </div>
    </div>
  );
}

// 原创度 + 限流风控
function RiskPanel({ note }) {
  const text = (note.title || "") + (note.body || "");
  const polished = (note.body || "").startsWith("⛺ 夏日露营天花板");
  const originality = note.topicId ? (polished ? 88 : 72) : 90;
  const risks = [
    { label: "导流/外链", bad: /http|www\.|公众号|微信|加我|私信|vx|v信|留链|主页链接/i.test(text), hint: "小红书限制站外导流" },
    { label: "极限词", bad: /最佳|最好|第一名|国家级|绝对|100%|顶级|纯天然|永久/.test(text), hint: "广告法违禁词" },
    { label: "敏感品类", bad: /医美|减肥|瘦身|药效|代购|烟|酒精/.test(text), hint: "需报备 / 可能限流" },
  ];
  const riskCount = risks.filter((r) => r.bad).length;
  return (
    <div style={{ background: "var(--surface-card)", border: "1px solid var(--border-coral)", borderRadius: "var(--radius-lg)", padding: 12, display: "flex", flexDirection: "column", gap: 10 }}>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
        <div style={{ display: "flex", alignItems: "center", gap: 7 }}><Icon name="shield-check" size={15} color="var(--primary)" /><span style={{ fontSize: "var(--text-xs)", fontWeight: 700 }}>原创度 · 限流风控</span></div>
        <span style={{ fontSize: 10, color: riskCount ? "var(--warning)" : "var(--success)", fontWeight: 600 }}>{riskCount ? `${riskCount} 项风险` : "无明显风险"}</span>
      </div>
      <div style={{ display: "flex", flexDirection: "column", gap: 5 }}>
        <div style={{ display: "flex", justifyContent: "space-between", fontSize: 10, color: "var(--text-muted)" }}>
          <span>原创度（vs 检索到的爆款）</span>
          <span className="font-tabular" style={{ fontWeight: 700, color: originality >= 80 ? "var(--success)" : "var(--warning)" }}>{originality}%</span>
        </div>
        <div style={{ height: 6, background: "var(--oats-dark)", borderRadius: 999, overflow: "hidden" }}><div style={{ height: "100%", width: `${originality}%`, background: originality >= 80 ? "var(--success)" : "var(--warning)", transition: "width var(--dur-slow) var(--ease-out)" }} /></div>
        {originality < 80 && <span style={{ fontSize: 9, color: "var(--warning)", lineHeight: 1.5 }}>⚠️ 与爆款结构相似度偏高，建议点「润色」改写提升原创度，规避查重限流</span>}
      </div>
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 6 }}>
        {risks.map((r) => (
          <div key={r.label} title={r.hint} style={{ display: "flex", alignItems: "center", gap: 5, fontSize: 10, padding: "5px 7px", borderRadius: "var(--radius-sm)", background: r.bad ? "var(--warning-surface)" : "var(--success-surface)" }}>
            <Icon name={r.bad ? "alert-triangle" : "check-circle-2"} size={12} color={r.bad ? "var(--warning)" : "var(--success)"} />
            <span style={{ fontWeight: 500 }}>{r.label}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

Object.assign(window, { Composer, CopyDoctor, RiskPanel, ScheduleBar });
