// 深度创作 screen — a focused long-form environment bound to the
// shared note. form: "immersive" | "flow" | "workspace"
function DeepCreation({ form }) {
  const { note, setSection } = useStudio();
  const [mode, setMode] = React.useState("edit");
  if (note.status === "idle") return <DeepEmpty onGo={() => setSection("create")} />;
  const body = mode === "compare" ? <ABCompare /> : (form === "flow" ? <DeepFlow /> : form === "workspace" ? <DeepWorkspace /> : <DeepImmersive />);
  return (
    <div style={{ flex: 1, display: "flex", flexDirection: "column", minHeight: 0 }}>
      <DeepTopicBar mode={mode} setMode={setMode} />
      {body}
    </div>
  );
}

// 深度创作必须基于选中的选题；未选时引导回创作区
function DeepEmpty({ onGo }) {
  const { Button, TopicCard } = window.DesignSystem_71831b;
  const { actions } = useStudio();
  const S = window.STUDIO;
  return (
    <div className="cs" style={{ flex: 1, overflowY: "auto", background: "var(--background)", padding: 28 }}>
      <div style={{ maxWidth: 580, margin: "0 auto", textAlign: "center", display: "flex", flexDirection: "column", alignItems: "center", gap: 10 }}>
        <div style={{ width: 54, height: 54, borderRadius: "var(--radius-lg)", background: "var(--accent-surface)", display: "flex", alignItems: "center", justifyContent: "center", fontSize: 26 }}>🪶</div>
        <div style={{ fontFamily: "var(--font-display)", fontWeight: 800, fontSize: "var(--text-lg)" }}>深度创作 · 从一个选题进入</div>
        <div style={{ fontSize: "var(--text-sm)", color: "var(--text-muted)", maxWidth: 400, lineHeight: "var(--leading-relaxed)" }}>选一个选题直接进入深度创作，🍠 会带着它的依据流式起稿；也可以先去「创作」区用对话起稿再来打磨。</div>
        <Button variant="ghost" size="sm" leftIcon={<Icon name="arrow-left" size={13} />} onClick={onGo}>或去创作区用对话起稿</Button>
      </div>
      <div style={{ maxWidth: 820, margin: "20px auto 0", display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 12 }}>
        {S.topics.map((t) => <div key={t.id} style={{ display: "flex" }}><TopicCard index={t.id} title={t.title} rationale={t.rationale} hotRate={t.hotRate} onClick={() => actions.chooseTopic(t, "deep")} /></div>)}
      </div>
    </div>
  );
}

// 顶部「基于选题」上下文条
function DeepTopicBar({ mode, setMode }) {
  const { note, setSection } = useStudio();
  const { Badge } = window.DesignSystem_71831b;
  const topic = (window.STUDIO.topics || []).find((t) => t.id === note.topicId);
  return (
    <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 12, padding: "10px 20px", background: "var(--surface-card)", borderBottom: "1px solid var(--border)", flexShrink: 0 }}>
      <div style={{ display: "flex", alignItems: "center", gap: 10, minWidth: 0 }}>
        <button onClick={() => setSection("create")} title="返回创作" style={{ display: "inline-flex", alignItems: "center", gap: 4, background: "none", border: "1px solid var(--border)", borderRadius: "var(--radius-sm)", padding: "5px 10px", cursor: "pointer", fontSize: "var(--text-xs)", color: "var(--text-body)", fontWeight: 600, whiteSpace: "nowrap", flexShrink: 0 }}><Icon name="arrow-left" size={13} /> 返回</button>
        <span style={{ width: 1, height: 18, background: "var(--border)", flexShrink: 0 }} />
        <span style={{ fontSize: 10, color: "var(--text-subtle)", fontWeight: 600, whiteSpace: "nowrap" }}>基于选题</span>
        {topic && <Badge tone="topic" shape="chip">{topic.angle}</Badge>}
        <span style={{ fontSize: "var(--text-sm)", fontWeight: 700, color: "var(--text-body)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{topic ? topic.title : (note.title || "未命名草稿")}</span>
        {topic && <span style={{ fontSize: 10, fontWeight: 700, color: "var(--hot)", whiteSpace: "nowrap" }}>🔥 {topic.hotRate}%</span>}
        {topic && <EvidenceChips topicId={topic.id} />}
      </div>
      <div style={{ display: "flex", alignItems: "center", gap: 8, flexShrink: 0 }}>
        <div style={{ display: "flex", gap: 3, background: "var(--oats-dark)", borderRadius: "var(--radius-sm)", padding: 3 }}>
          {[["edit", "编辑"], ["compare", "A·B 对比"]].map(([k, l]) => (
            <button key={k} onClick={() => setMode(k)} style={{ padding: "4px 10px", borderRadius: "var(--radius-xs)", border: "none", cursor: "pointer", fontSize: 11, fontWeight: mode === k ? 700 : 500, background: mode === k ? "var(--surface-card)" : "transparent", color: mode === k ? "var(--primary)" : "var(--text-muted)", boxShadow: mode === k ? "var(--shadow-xs)" : "none" }}>{l}</button>
          ))}
        </div>
        <button onClick={() => setSection("create")} style={{ display: "inline-flex", alignItems: "center", gap: 5, background: "none", border: "1px solid var(--border)", borderRadius: "var(--radius-sm)", padding: "5px 10px", cursor: "pointer", fontSize: "var(--text-xs)", color: "var(--text-muted)", whiteSpace: "nowrap" }}>
          <Icon name="repeat" size={12} /> 换题
        </button>
      </div>
    </div>
  );
}

// Big editor bound to the shared note
function BigEditor({ maxWidth = 720 }) {
  const { note, actions } = useStudio();
  return (
    <div style={{ maxWidth, margin: "0 auto", width: "100%", background: "var(--surface-card)", border: "1px solid var(--border)", borderRadius: "var(--radius-lg)", boxShadow: "var(--shadow-md)", padding: 28, display: "flex", flexDirection: "column", gap: 16 }}>
      <input value={note.title} placeholder="写个钩子标题…（≤20 字）" onChange={(e) => actions.updateField("title", e.target.value)}
        style={{ border: "none", outline: "none", background: "transparent", fontFamily: "var(--font-display)", fontWeight: 800, fontSize: "var(--text-xl)", color: "var(--text-body)", letterSpacing: "var(--tracking-tight)" }} />
      <div style={{ height: 1, background: "var(--border)" }} />
      <textarea value={note.body} placeholder="正文从一句共情钩子开始，再用 1️⃣2️⃣3️⃣ 分点干货，最后引导互动…" onChange={(e) => actions.updateField("body", e.target.value)}
        style={{ border: "none", outline: "none", resize: "none", background: "transparent", fontFamily: "var(--font-sans)", fontSize: "var(--text-sm)", lineHeight: "var(--leading-relaxed)", color: "var(--text-body)", minHeight: 320, flex: 1 }} />
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", fontSize: 11, color: "var(--text-subtle)" }}>
        <span>自动保存 · 刚刚</span>
        <span className="font-tabular">{note.body.length} / 1000 字</span>
      </div>
    </div>
  );
}

function AssistantPanel() {
  const { Button, HashtagTag } = window.DesignSystem_71831b;
  const { note, actions } = useStudio();
  const S = window.STUDIO;
  const checks = computeChecks(note);
  return (
    <div className="cs" style={{ display: "flex", flexDirection: "column", gap: 14, height: "100%", overflowY: "auto" }}>
      <PanelHead icon="sparkles" title="AI 创作助手" sub="🍠 随写随帮" />
      <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
        <Button variant="soft" size="sm" leftIcon={<Icon name="sparkles" size={12} />} onClick={actions.polish}>润色语气</Button>
        <Button variant="soft" size="sm" leftIcon={<Icon name="scissors" size={12} />} onClick={actions.shorten}>一键瘦身</Button>
        <Button variant="soft" size="sm" leftIcon={<Icon name="hash" size={12} />} onClick={actions.addTags}>配标签</Button>
      </div>
      <div>
        <Eyebrow style={{ marginBottom: 7 }}>推荐话题标签</Eyebrow>
        <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
          {S.recommendedTags.filter((tg) => !note.tags.includes(tg)).map((tg) => <HashtagTag key={tg} addable onAdd={() => actions.addTag(tg)}>{tg}</HashtagTag>)}
        </div>
      </div>
      <CopyDoctor checks={checks} score={scoreOf(checks)} />
    </div>
  );
}

function EvidenceRail() {
  const { Card, Badge } = window.DesignSystem_71831b;
  return (
    <div className="cs" style={{ display: "flex", flexDirection: "column", gap: 12, height: "100%", overflowY: "auto" }}>
      <PanelHead icon="database" title="飞书资料 · 证据" sub="选题依据来源" />
      {[
        { src: "多维表格 · 第 4 行", t: "搬家式露营装备清单", m: "赞 3.2w · 藏 1.8w", time: "源 06-20" },
        { src: "爆款拆解库", t: "新手避坑极简装备", m: "藏 > 赞，收藏导向", time: "源 06-18" },
        { src: "Wiki · 露营选品", t: "天幕 / 蛋卷桌 / 氛围灯", m: "高频出现单品", time: "本地索引" },
      ].map((e, i) => (
        <Card key={i} padding="sm" tone="sunken">
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 5 }}>
            <Badge tone="topic" shape="chip">{e.src}</Badge>
            <span style={{ fontSize: 9, color: "var(--text-subtle)" }}>{e.time}</span>
          </div>
          <div style={{ fontSize: "var(--text-xs)", fontWeight: 600, color: "var(--text-body)" }}>{e.t}</div>
          <div style={{ fontSize: 10, color: "var(--text-muted)", marginTop: 3 }}>{e.m}</div>
        </Card>
      ))}
    </div>
  );
}

function DeepImmersive() {
  return <DeepEditor />;
}

// 小红书笔记实时预览（深度创作右栏）
function NotePreview({ note }) {
  const { PhoneFrame } = window.DesignSystem_71831b;
  const S = window.STUDIO;
  const img = S.images[(note.topicId || 1) - 1] || S.images[0];
  return (
    <PhoneFrame width={300}>
      <div className="cs" style={{ paddingTop: 30, height: "100%", overflowY: "auto", background: "#fff", display: "flex", flexDirection: "column" }}>
        <div style={{ position: "relative", width: "100%", aspectRatio: "3 / 4", flexShrink: 0, background: "var(--accent-surface)" }}>
          <img src={img} alt="cover" style={{ width: "100%", height: "100%", objectFit: "cover" }} />
          <div style={{ position: "absolute", inset: 0, background: "linear-gradient(180deg,rgba(0,0,0,.05),rgba(0,0,0,.42))" }} />
          <div style={{ position: "absolute", top: 10, left: 12, right: 12, color: "#fff", fontFamily: "var(--font-display)", fontWeight: 800, fontSize: 20, lineHeight: 1.15, textShadow: "0 1px 5px rgba(0,0,0,.5)", whiteSpace: "pre-line" }}>{note.cover}</div>
        </div>
        <div style={{ padding: 12 }}>
          <h3 style={{ margin: "0 0 8px", fontSize: 13, fontWeight: 700, lineHeight: 1.35, color: "var(--charcoal-default)" }}>{note.title}</h3>
          <p style={{ margin: 0, fontSize: 11, lineHeight: 1.7, color: "var(--charcoal-light)", whiteSpace: "pre-wrap" }}>{note.body}</p>
        </div>
      </div>
    </PhoneFrame>
  );
}

function DeepFlow() {
  const S = window.STUDIO;
  const [active, setActive] = React.useState(2);
  const outline = [
    { step: "选题", detail: "从爆款数据挑方向" },
    { step: "大纲", detail: "钩子 → 清单 → TIPS → 互动" },
    { step: "正文", detail: "逐段撰写 + 实时体检" },
    { step: "润色", detail: "/polish 语气 · /shorten 瘦身" },
    { step: "配图", detail: "封面大字 + 4 张内容图" },
  ];
  return (
    <div style={{ flex: 1, display: "flex", flexDirection: "column", minHeight: 0, background: "var(--background)" }}>
      <div style={{ display: "flex", alignItems: "center", gap: 8, padding: "16px 28px", borderBottom: "1px solid var(--border)", background: "var(--surface-card)", flexShrink: 0, justifyContent: "center" }}>
        {outline.map((o, i) => {
          const done = i < active, on = i === active;
          return (
            <React.Fragment key={o.step}>
              <button onClick={() => setActive(i)} style={{ display: "flex", alignItems: "center", gap: 7, cursor: "pointer", background: "none", border: "none" }}>
                <span style={{ width: 26, height: 26, borderRadius: "999px", display: "flex", alignItems: "center", justifyContent: "center", fontSize: 12, fontWeight: 700, fontFamily: "var(--font-display)",
                  background: on ? "var(--primary)" : done ? "var(--success-surface)" : "var(--oats-dark)", color: on ? "#fff" : done ? "var(--success)" : "var(--text-subtle)", border: done ? "1px solid var(--success)" : "none" }}>{done ? "✓" : i + 1}</span>
                <span style={{ fontSize: "var(--text-xs)", fontWeight: on ? 700 : 500, color: on ? "var(--primary)" : done ? "var(--text-body)" : "var(--text-subtle)" }}>{o.step}</span>
              </button>
              {i < outline.length - 1 && <span style={{ width: 28, height: 2, background: done ? "var(--success)" : "var(--border)", borderRadius: 2 }} />}
            </React.Fragment>
          );
        })}
      </div>
      <div className="cs" style={{ flex: 1, overflowY: "auto", padding: 28 }}>
        <div style={{ maxWidth: 880, margin: "0 auto" }}>
          <div style={{ textAlign: "center", marginBottom: 18 }}>
            <div style={{ fontFamily: "var(--font-display)", fontWeight: 800, fontSize: "var(--text-lg)" }}>第 {active + 1} 步 · {outline[active].step}</div>
            <div style={{ fontSize: "var(--text-xs)", color: "var(--text-muted)", marginTop: 4 }}>{outline[active].detail}</div>
          </div>
          {active === 2
            ? <div style={{ display: "flex", gap: 16, alignItems: "flex-start" }}>
                <div style={{ flex: 1 }}><BigEditor maxWidth={9999} /></div>
                <div style={{ width: 300, flexShrink: 0 }}><AssistantPanel /></div>
              </div>
            : <StepCards step={active} />}
        </div>
      </div>
      <div style={{ padding: 14, borderTop: "1px solid var(--border)", background: "var(--surface-card)", display: "flex", justifyContent: "center", gap: 10, flexShrink: 0 }}>
        <BtnSecondary onClick={() => setActive((a) => Math.max(0, a - 1))}>上一步</BtnSecondary>
        <BtnPrimary onClick={() => setActive((a) => Math.min(outline.length - 1, a + 1))}>下一步</BtnPrimary>
      </div>
    </div>
  );
}

function BtnPrimary({ children, onClick }) { const { Button } = window.DesignSystem_71831b; return <Button variant="primary" onClick={onClick} rightIcon={<Icon name="arrow-right" size={14} />}>{children}</Button>; }
function BtnSecondary({ children, onClick }) { const { Button } = window.DesignSystem_71831b; return <Button variant="secondary" onClick={onClick}>{children}</Button>; }

function StepCards({ step }) {
  const { Card, TopicCard } = window.DesignSystem_71831b;
  const { actions, note } = useStudio();
  const S = window.STUDIO;
  if (step === 0) {
    const t = S.topics.find((x) => x.id === note.topicId) || S.topics[0];
    return (
      <div style={{ maxWidth: 460, margin: "0 auto", display: "flex", flexDirection: "column", gap: 10 }}>
        <TopicCard index={t.id} title={t.title} rationale={t.rationale} hotRate={t.hotRate} />
        <div style={{ display: "flex", alignItems: "center", justifyContent: "center", gap: 5, fontSize: 11, color: "var(--success)", fontWeight: 600 }}><Icon name="check-circle-2" size={13} color="var(--success)" /> 已选定该选题，进入下一步撰写大纲</div>
      </div>
    );
  }
  if (step === 1) {
    const lines = ["① 共情钩子：夏天太适合露营啦 + 身份标签", "② 编号清单：天幕 / 蛋卷桌 / 氛围灯 / 制冰机", "③ 选购 TIPS：折叠收纳体积", "④ 互动收口：求评论 + 话题标签矩阵"];
    return <Card padding="lg"><div style={{ display: "flex", flexDirection: "column", gap: 10 }}>{lines.map((l, i) => <div key={i} style={{ display: "flex", gap: 10, fontSize: "var(--text-sm)" }}><Icon name="check-circle-2" size={16} color="var(--success)" /><span>{l}</span></div>)}</div></Card>;
  }
  return <Card padding="lg"><div style={{ fontSize: "var(--text-sm)", color: "var(--text-muted)", lineHeight: "var(--leading-relaxed)" }}>{step === 3 ? "AI 正在按小红书语气润色，并裁剪到 1000 字内。可对比多版本草稿后定稿。" : "封面：暖色实拍大全景 + 「搬家式露营 / 必带清单」大字报；建议再出 4 张内容图（产品特写 · 场景氛围 · 清单合影 · 选购对比）。"}</div></Card>;
}

function DeepWorkspace() {
  return <DeepEditor />;
}

// A·B 版本并排对比
function ABCompare() {
  const { note, actions } = useStudio();
  const [pair, setPair] = React.useState(["A", "B"]);
  if (!note.versions) return null;
  const setSide = (i, v) => setPair((p) => { const n = [...p]; n[i] = v; return n; });
  const Col = ({ id, side }) => {
    const { Button } = window.DesignSystem_71831b;
    const v = note.versions[id];
    const n = { ...note, title: v.title, body: v.body, tags: v.tags, cover: v.cover, kw: note.kw };
    const checks = computeChecks(n); const score = scoreOf(checks);
    const active = note.activeVersion === id;
    return (
      <div style={{ flex: 1, minWidth: 0, display: "flex", flexDirection: "column", background: "var(--surface-card)", border: `1px solid ${active ? "var(--primary)" : "var(--border)"}`, borderRadius: "var(--radius-lg)", overflow: "hidden" }}>
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", padding: "10px 12px", borderBottom: "1px solid var(--border)", background: active ? "var(--accent-surface)" : "var(--oats-light)" }}>
          <select value={id} onChange={(e) => setSide(side, e.target.value)} style={{ border: "1px solid var(--border)", borderRadius: "var(--radius-sm)", padding: "3px 6px", fontSize: 11, fontWeight: 700, background: "var(--surface-card)", color: "var(--text-body)", cursor: "pointer" }}>
            {["A", "B", "C"].map((k) => <option key={k} value={k}>{note.versions[k].label}</option>)}
          </select>
          <span style={{ display: "inline-flex", alignItems: "center", gap: 6 }}>
            <span style={{ fontFamily: "var(--font-display)", fontWeight: 800, fontSize: "var(--text-base)", color: score >= 80 ? "var(--success)" : "var(--warning)" }}>{score}<span style={{ fontSize: 10, color: "var(--text-subtle)", fontWeight: 400 }}>分</span></span>
            {active && <span style={{ fontSize: 9, color: "var(--primary)", fontWeight: 700 }}>当前</span>}
          </span>
        </div>
        <div className="cs" style={{ flex: 1, overflowY: "auto", padding: 16 }}>
          <h3 style={{ margin: "0 0 10px", fontFamily: "var(--font-display)", fontWeight: 800, fontSize: "var(--text-base)", lineHeight: 1.3 }}>{v.title}</h3>
          <p style={{ margin: 0, fontSize: "var(--text-xs)", lineHeight: "var(--leading-relaxed)", color: "var(--text-body)", whiteSpace: "pre-wrap" }}>{v.body}</p>
          <div style={{ display: "flex", flexWrap: "wrap", gap: 5, marginTop: 12 }}>
            {v.tags.map((tg) => <span key={tg} style={{ fontSize: 9, color: "var(--topicblue-default)", background: "var(--topicblue-light)", borderRadius: 999, padding: "2px 7px" }}>#{tg}</span>)}
          </div>
        </div>
        <div style={{ padding: 10, borderTop: "1px solid var(--border)" }}>
          <Button variant={active ? "secondary" : "primary"} size="sm" block disabled={active} onClick={() => { actions.setVersion(id); actions.toast(`✅ 已采用「${v.label}」为当前稿`); }}>{active ? "当前采用中" : "采用此版"}</Button>
        </div>
      </div>
    );
  };
  return (
    <div style={{ flex: 1, display: "flex", flexDirection: "column", minHeight: 0, background: "var(--background)" }}>
      <div style={{ textAlign: "center", padding: "12px 0 4px", fontSize: "var(--text-xs)", color: "var(--text-muted)" }}>A·B 并排对比 · 体检分数实时计算，选更优的一版定稿</div>
      <div style={{ flex: 1, minHeight: 0, display: "flex", gap: 14, padding: 16 }}>
        <Col id={pair[0]} side={0} />
        <Col id={pair[1]} side={1} />
      </div>
    </div>
  );
}

Object.assign(window, { DeepCreation });
