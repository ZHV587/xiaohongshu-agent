// Root — shared note store (one note flows across the 3 sections) +
// Tweaks for the explore-decisions.
const TWEAK_DEFAULTS = /*EDITMODE-BEGIN*/{
  "rightLayout": "stack",
  "deepForm": "immersive",
  "opsHosting": "page"
}/*EDITMODE-END*/;

const WD = ["一", "二", "三", "四", "五", "六", "日"];

// Scale-to-fit: the workbench is designed at 1360px wide; on a narrower
// viewport it scales down uniformly (letterboxed) so the full three-pane
// layout is always visible & proportional instead of cramped + scrolling.
function Scaler({ children }) {
  const [s, setS] = React.useState(1);
  React.useEffect(() => {
    const calc = () => setS(Math.min(1, window.innerWidth / 1360));
    calc();
    window.addEventListener("resize", calc);
    return () => window.removeEventListener("resize", calc);
  }, []);
  return (
    <div style={{ width: "100vw", height: "100vh", overflow: "hidden", background: "var(--oats-dark)", display: "flex", justifyContent: "center" }}>
      <div style={{ width: 1360, height: `calc(100vh / ${s})`, flexShrink: 0, transform: `scale(${s})`, transformOrigin: "top center" }}>
        {children}
      </div>
    </div>
  );
}

function StudioApp() {
  const S = window.STUDIO;
  const [t, setTweak] = useTweaks(TWEAK_DEFAULTS);
  const [section, setSection] = React.useState("create");
  const [activeRecent, setActiveRecent] = React.useState(1);
  const [note, setNote] = React.useState({ topicId: null, kw: "", title: "", body: "", tags: [], cover: "", status: "idle", activeVersion: "A", versions: null });
  const [calendar, setCalendar] = React.useState(S.calendar);
  const [chatExtra, setChatExtra] = React.useState([]);
  const [toast, setToast] = React.useState(null);
  const [selectedEvidence, setSelectedEvidence] = React.useState(null);
  const streamRef = React.useRef(null);
  const toastRef = React.useRef(null);

  const showToast = (msg) => { setToast(msg); clearTimeout(toastRef.current); toastRef.current = setTimeout(() => setToast(null), 2800); };

  React.useEffect(() => {
    const onKey = (e) => { if (e.key === "Escape") setSelectedEvidence(null); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  // 选题卡 → 创作栏：stream a real draft in
  const chooseTopic = (topic, goSection = "create") => {
    clearInterval(streamRef.current);
    const versions = buildVersions(topic);
    const full = versions.A;
    setSection(goSection);
    setActiveRecent(topic.id);
    setChatExtra([
      { who: "user", text: `写第 ${topic.id} 个：${topic.title}` },
      { who: "ai", thinking: true, text: `正在按小红书风格撰写《${topic.title}》，右侧创作栏流式生成中…` },
    ]);
    setNote({ topicId: topic.id, kw: topic.kw, title: "", body: "", tags: [], cover: full.cover, status: "writing", activeVersion: "A", versions });
    setTimeout(() => setNote((n) => (n.topicId === topic.id ? { ...n, title: full.title } : n)), 220);
    let i = 0;
    setTimeout(() => {
      streamRef.current = setInterval(() => {
        i += 6;
        const done = i >= full.body.length;
        setNote((n) => (n.topicId !== topic.id ? n : { ...n, body: full.body.slice(0, i), tags: done ? full.tags : n.tags, status: done ? "draft" : "writing" }));
        if (done) {
          clearInterval(streamRef.current);
          setChatExtra((prev) => prev.map((m) => (m.thinking ? { who: "ai", text: `✅ 已生成《${full.title}》草稿。右侧可继续精修，文案体检达标即可定稿排期 →` } : m)));
        }
      }, 22);
    }, 420);
  };

  const setVersion = (v) => setNote((n) => { if (!n.versions) return n; const ver = n.versions[v]; return { ...n, title: ver.title, body: ver.body, tags: ver.tags, cover: ver.cover, activeVersion: v, status: "draft" }; });
  const updateField = (f, val) => setNote((n) => ({ ...n, [f]: val, status: n.status === "writing" ? "writing" : "draft" }));
  const addTag = (tag) => setNote((n) => (n.tags.includes(tag) ? n : { ...n, tags: [...n.tags, tag].slice(0, 10), status: "draft" }));
  const removeTag = (tag) => setNote((n) => ({ ...n, tags: n.tags.filter((x) => x !== tag), status: "draft" }));

  const polish = () => { setNote((n) => { if (!n.title) return n; const hook = "⛺ 夏日露营天花板，姐妹们冲鸭！✨\n\n"; const body = n.body.startsWith("⛺ 夏日露营天花板") ? n.body : hook + n.body; const title = /\p{Extended_Pictographic}/u.test(n.title) || n.title.length > 18 ? n.title : n.title + " ✨"; return { ...n, body, title, status: "draft" }; }); showToast("🍠 已按小红书语气润色，更有种草感 ✨"); };
  const shorten = () => { setNote((n) => { if (!n.body) return n; const tagline = n.tags.slice(0, 4).map((x) => "#" + x).join(" "); return { ...n, body: n.body.slice(0, 240).trimEnd() + "…\n\n" + tagline, status: "draft" }; }); showToast("✂️ 已瘦身到精华段落"); };
  const addTags = () => { setNote((n) => { const add = S.recommendedTags.filter((x) => !n.tags.includes(x) && x.length >= 4).slice(0, 2); return { ...n, tags: [...n.tags, ...add].slice(0, 10), status: "draft" }; }); showToast("# 已补充长尾话题标签"); };

  const schedule = (date) => { setCalendar((cal) => { const item = { t: (note.title || "新笔记").slice(0, 8), time: "19:00", tone: "coral", acct: "露" }; return cal.some((d) => d.date === date) ? cal.map((d) => (d.date === date ? { ...d, items: [...d.items, item] } : d)) : [...cal, { date, items: [item] }]; }); setNote((n) => ({ ...n, status: "scheduled" })); showToast(`📅 已定稿并排期到 6 月 ${date} 日 19:00`); };
  const syncFeishu = () => showToast("🔗 已同步至飞书多维表格");
  const backfillSave = () => showToast("💾 真实数据已回填并沉淀飞书，将用于优化下一轮选题");
  const reuse = (topicId) => { const topic = S.topics.find((x) => x.id === topicId); if (topic) chooseTopic(topic); };
  const newChat = () => { clearInterval(streamRef.current); setNote({ topicId: null, kw: "", title: "", body: "", tags: [], cover: "", status: "idle", activeVersion: "A", versions: null }); setChatExtra([]); setSection("create"); showToast("🆕 已开启新的创作会话"); };
  const say = (text) => { setChatExtra((prev) => [...prev, { who: "user", text }, { who: "ai", text: "收到～已结合你的补充在数据底座重新检索，更新了右侧选题卡 👉" }]); };

  const store = { section, setSection, activeRecent, setActiveRecent, note, calendar, chatExtra, selectedEvidence,
    actions: { chooseTopic, setVersion, updateField, addTag, removeTag, polish, shorten, addTags, schedule, syncFeishu, backfillSave, reuse, newChat, say, toast: showToast, openEvidence: setSelectedEvidence, closeEvidence: () => setSelectedEvidence(null) } };

  return (
    <StudioContext.Provider value={store}>
      <Scaler>
        <div style={{ height: "100%", width: "100%", display: "flex", flexDirection: "column", overflow: "hidden", fontFamily: "var(--font-sans)", color: "var(--text-body)", background: "var(--background)" }}>
          {section !== "deep" && <StudioTopBar section={section} setSection={setSection} />}
          <div key={section} style={{ flex: 1, display: "flex", flexDirection: "column", minHeight: 0, animation: "secIn 0.3s var(--ease-out)" }}>
            {section === "create" && <CreationScreen rightLayout={t.rightLayout} />}
            {section === "deep" && <DeepCreation form={t.deepForm} />}
            {section === "ops" && <Operations hosting={t.opsHosting} />}
          </div>

          {toast && (
            <div style={{ position: "fixed", bottom: 26, left: "50%", transform: "translateX(-50%)", background: "var(--charcoal-default)", color: "#fff", padding: "11px 18px", borderRadius: "var(--radius-full)", fontSize: "var(--text-sm)", fontWeight: 500, boxShadow: "var(--shadow-lg)", zIndex: 60, animation: "toastIn 0.3s var(--ease-out)" }}>
              {toast}
            </div>
          )}

          {selectedEvidence && <EvidencePanel />}
        </div>
      </Scaler>

      <TweaksPanel title="Tweaks · 方案探索">
        <TweakSection label="① 创作 · 右侧布局（选题卡 + 创作栏）" />
        <TweakRadio label="布局" value={t.rightLayout}
          options={[{ value: "stack", label: "上下堆叠" }, { value: "split", label: "左右分栏" }, { value: "composer", label: "仅创作栏" }]}
          onChange={(v) => { setTweak("rightLayout", v); setSection("create"); }} />
        <TweakSection label="② 深度创作 · 形态" />
        <TweakRadio label="形态" value={t.deepForm}
          options={[{ value: "immersive", label: "沉浸双栏" }, { value: "flow", label: "分步流程" }, { value: "workspace", label: "多栏工作台" }]}
          onChange={(v) => { setTweak("deepForm", v); setSection("deep"); }} />
        <TweakSection label="③ 账号运营 · 承载方式" />
        <TweakRadio label="承载" value={t.opsHosting}
          options={[{ value: "page", label: "独立页面" }, { value: "inline", label: "会话内" }, { value: "hybrid", label: "同屏融合" }]}
          onChange={(v) => { setTweak("opsHosting", v); setSection("ops"); }} />
      </TweaksPanel>
    </StudioContext.Provider>
  );
}

ReactDOM.createRoot(document.getElementById("root")).render(<StudioApp />);
