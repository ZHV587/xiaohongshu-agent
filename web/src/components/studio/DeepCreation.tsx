"use client";

// 深度创作 screen — a focused long-form environment bound to the shared note.

import { useMemo, useState } from "react";
import { Badge, Button, TopicCard, Icon } from "@/components/ds";
import { Eyebrow } from "@/components/studio/ui";
import { useStudio } from "@/components/studio/useStudio";
import { computeChecks, scoreOf } from "@/components/studio/rubric";
import { TITLE_FORMULAS, type VersionId } from "@/components/studio/types";
import { EvidenceChips } from "./CreationScreen";
import { DeepEditor } from "./DeepEditor";

type DeepMode = "edit" | "compare" | "title";

export function DeepCreation() {
  const { note, setSection } = useStudio();
  const [mode, setMode] = useState<DeepMode>("edit");
  const [processOpen, setProcessOpen] = useState(false);
  if (note.status === "idle") return <DeepEmpty onGo={() => setSection("create")} />;
  // 标题优化是整屏子界面(mode=title),替换整个编辑区(非弹层),从编辑器"优化标题"进入。
  if (mode === "title") return <TitleScreen onBack={() => setMode("edit")} />;
  const body = mode === "compare" ? <ABCompare /> : <DeepEditor onOptimizeTitle={() => setMode("title")} />;
  return (
    <div style={{ flex: 1, display: "flex", flexDirection: "column", minHeight: 0 }}>
      <DeepTopicBar mode={mode} setMode={setMode} onOpenProcess={() => setProcessOpen(true)} />
      {/* 两段式仿写第一段:范本套路拆解显性呈现在成品之上(需求 §5——让用户看到"它凭什么这么仿")。 */}
      <ImitationTeardownBanner />
      {body}
      {processOpen && <CreationProcessDrawer onClose={() => setProcessOpen(false)} />}
    </div>
  );
}

// 仿写第一段:范本拆解横幅。仅在本会话是仿写(imitation 非空)时显示,可折叠。
// 显性呈现切入角度/痛点/钩子机制/结构节奏 —— 需求 §5 铁律:分析必须让用户看得见,
// 不能后台默默做掉直接吐成品。第二段成品仍走下方编辑器/对比区(note.versions)。
function ImitationTeardownBanner() {
  const { imitation } = useStudio();
  const [open, setOpen] = useState(true);
  if (!imitation) return null;
  const t = imitation.teardown;
  const rows: [string, string, string][] = [
    ["compass", "切入角度", t.angle],
    ["target", "戳中痛点", t.painpoint],
    ["anchor", "钩子机制", t.hook_mechanism],
    ["list", "结构节奏", t.structure],
  ];
  return (
    <div style={{ flexShrink: 0, background: "var(--accent-surface)", borderBottom: "1px solid var(--border-coral)" }}>
      <button onClick={() => setOpen((v) => !v)} style={{ width: "100%", display: "flex", alignItems: "center", gap: 8, padding: "10px 20px", background: "none", border: "none", cursor: "pointer", textAlign: "left" }}>
        <Icon name="feather" size={14} color="var(--primary)" />
        <span style={{ fontSize: "var(--text-xs)", fontWeight: 700, color: "var(--primary)" }}>仿写第一段 · 范本套路拆解</span>
        {imitation.referenceTitle && <span style={{ fontSize: 11, color: "var(--text-muted)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", maxWidth: 280 }}>仿自《{imitation.referenceTitle}》</span>}
        <span style={{ marginLeft: "auto", fontSize: 10, color: "var(--text-subtle)" }}>{open ? "收起" : "展开"}</span>
        <Icon name={open ? "chevron-up" : "chevron-down"} size={13} color="var(--text-subtle)" />
      </button>
      {open && (
        <div style={{ padding: "0 20px 12px", display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8 }}>
          {rows.map(([icon, label, val]) => (
            <div key={label} style={{ background: "var(--surface-card)", border: "1px solid var(--border)", borderRadius: "var(--radius-sm)", padding: "8px 10px", display: "flex", flexDirection: "column", gap: 3 }}>
              <span style={{ display: "inline-flex", alignItems: "center", gap: 5, fontSize: 10, fontWeight: 700, color: "var(--primary)" }}><Icon name={icon} size={11} /> {label}</span>
              <span style={{ fontSize: 11, color: "var(--text-body)", lineHeight: 1.6 }}>{val || "—"}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

// 深度创作必须基于选中的选题；未选时引导回创作区
function DeepEmpty({ onGo }: { onGo: () => void }) {
  const { actions, topics } = useStudio();
  return (
    <div className="cs" style={{ flex: 1, overflowY: "auto", background: "var(--background)", padding: 28 }}>
      <div style={{ maxWidth: 580, margin: "0 auto", textAlign: "center", display: "flex", flexDirection: "column", alignItems: "center", gap: 10 }}>
        <div style={{ width: 54, height: 54, borderRadius: "var(--radius-lg)", background: "var(--accent-surface)", display: "flex", alignItems: "center", justifyContent: "center", fontSize: 26 }}>🪶</div>
        <div style={{ fontFamily: "var(--font-display)", fontWeight: 800, fontSize: "var(--text-lg)" }}>深度创作 · 从一个选题进入</div>
        <div style={{ fontSize: "var(--text-sm)", color: "var(--text-muted)", maxWidth: 400, lineHeight: "var(--leading-relaxed)" }}>选一个选题直接进入深度创作，🍠 会带着它的依据流式起稿；也可以先去「创作」区用对话起稿再来打磨。</div>
        <Button variant="ghost" size="sm" leftIcon={<Icon name="arrow-left" size={13} />} onClick={onGo}>或去创作区用对话起稿</Button>
      </div>
      <div style={{ maxWidth: 820, margin: "20px auto 0", display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 12 }}>
        {topics.map((t) => <div key={t.id} style={{ display: "flex" }}><TopicCard index={t.id} title={t.title} rationale={t.rationale} hotRate={t.hotRate} onClick={() => actions.chooseTopic(t, "deep")} /></div>)}
      </div>
    </div>
  );
}

// 顶部「基于选题」上下文条
function DeepTopicBar({ mode, setMode, onOpenProcess }: { mode: DeepMode; setMode: (m: DeepMode) => void; onOpenProcess: () => void }) {
  const { note, setSection, topics } = useStudio();
  const topic = (topics || []).find((t) => t.id === note.topicId);
  return (
    <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 12, padding: "10px 20px", background: "var(--surface-card)", borderBottom: "1px solid var(--border)", flexShrink: 0 }}>
      <div style={{ display: "flex", alignItems: "center", gap: 10, minWidth: 0 }}>
        <button onClick={() => setSection("create")} title="返回创作" style={{ display: "inline-flex", alignItems: "center", gap: 4, background: "none", border: "1px solid var(--border)", borderRadius: "var(--radius-sm)", padding: "5px 10px", cursor: "pointer", fontSize: "var(--text-xs)", color: "var(--text-body)", fontWeight: 600, whiteSpace: "nowrap", flexShrink: 0 }}><Icon name="arrow-left" size={13} /> 返回</button>
        <span style={{ width: 1, height: 18, background: "var(--border)", flexShrink: 0 }} />
        <span style={{ fontSize: 10, color: "var(--text-subtle)", fontWeight: 600, whiteSpace: "nowrap" }}>基于选题</span>
        {topic && <Badge tone="topic" shape="chip">{topic.angle}</Badge>}
        <span style={{ fontSize: "var(--text-sm)", fontWeight: 700, color: "var(--text-body)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{topic ? topic.title : (note.title || "未命名草稿")}</span>
        {topic && topic.hotRate != null && <span style={{ fontSize: 10, fontWeight: 700, color: "var(--hot)", whiteSpace: "nowrap" }}>🔥 {topic.hotRate}%</span>}
        {topic && <EvidenceChips topicId={topic.id} />}
      </div>
      <div style={{ display: "flex", alignItems: "center", gap: 8, flexShrink: 0 }}>
        <div style={{ display: "flex", gap: 3, background: "var(--oats-dark)", borderRadius: "var(--radius-sm)", padding: 3 }}>
          {([["edit", "编辑"], ["compare", "A·B 对比"]] as [DeepMode, string][]).map(([k, l]) => (
            <button key={k} onClick={() => setMode(k)} style={{ padding: "4px 10px", borderRadius: "var(--radius-xs)", border: "none", cursor: "pointer", fontSize: 11, fontWeight: mode === k ? 700 : 500, background: mode === k ? "var(--surface-card)" : "transparent", color: mode === k ? "var(--primary)" : "var(--text-muted)", boxShadow: mode === k ? "var(--shadow-xs)" : "none" }}>{l}</button>
          ))}
        </div>
        {note.process && (
          <button onClick={onOpenProcess} title="查看本版的创作过程:对标依据 + AI 腔自审纠偏" style={{ display: "inline-flex", alignItems: "center", gap: 5, background: "none", border: "1px solid var(--border-coral)", borderRadius: "var(--radius-sm)", padding: "5px 10px", cursor: "pointer", fontSize: "var(--text-xs)", color: "var(--primary)", whiteSpace: "nowrap" }}>
            <Icon name="history" size={12} /> 创作过程
          </button>
        )}
        <button onClick={() => setSection("create")} style={{ display: "inline-flex", alignItems: "center", gap: 5, background: "none", border: "1px solid var(--border)", borderRadius: "var(--radius-sm)", padding: "5px 10px", cursor: "pointer", fontSize: "var(--text-xs)", color: "var(--text-muted)", whiteSpace: "nowrap" }}>
          <Icon name="repeat" size={12} /> 换题
        </button>
      </div>
    </div>
  );
}

// A·B 版本并排对比 —— 永不白屏:① ≥2 版 → 并排模块卡;② 仅 1 版 → 单卡 + 再生成一版入口;
// ③ 无 versions 但有草稿 → 草稿卡 + 提示;④ 全空 → 友好空态(回创作区)。
// 每版独立计算体检分/字数/标签数,互不混搭(不再出现「A 版正文 + 全局 tags」的错位打分)。
function ABCompare() {
  const { note, actions } = useStudio();
  const versions = note.versions;
  const ids = useMemo(
    () =>
      versions
        ? (["A", "B", "C"] as VersionId[]).filter((k) => {
            const v = versions[k];
            return !!v && (!!v.title || !!v.body);
          })
        : [],
    [versions],
  );
  const hasDraft = Boolean(note.title || note.body);

  // ④ 完全没有可对比内容 → 友好空态(不再白屏)。
  if (ids.length === 0 && !hasDraft) {
    return (
      <div style={{ flex: 1, display: "flex", alignItems: "center", justifyContent: "center", background: "var(--background)", padding: 28 }}>
        <div style={{ maxWidth: 420, textAlign: "center", display: "flex", flexDirection: "column", alignItems: "center", gap: 10 }}>
          <div style={{ width: 48, height: 48, borderRadius: "var(--radius-lg)", background: "var(--accent-surface)", display: "flex", alignItems: "center", justifyContent: "center", fontSize: 22 }}>🗒️</div>
          <div style={{ fontFamily: "var(--font-display)", fontWeight: 800, fontSize: "var(--text-base)" }}>还没有可对比的文案</div>
          <div style={{ fontSize: "var(--text-xs)", color: "var(--text-muted)", lineHeight: "var(--leading-relaxed)" }}>先在「编辑」里基于选题生成一版文案,再来这里做 A·B 对比。</div>
          <Button variant="soft" size="sm" leftIcon={<Icon name="arrow-left" size={13} />} onClick={() => actions.setSection("create")}>去创作区起稿</Button>
        </div>
      </div>
    );
  }

  // ②/③ 仅一版 → 单卡 + 「再生成一版」入口,凑齐两版即可并排对比。
  if (ids.length < 2) {
    const singleId = ids[0] ?? note.activeVersion;
    return (
      <div style={{ flex: 1, display: "flex", flexDirection: "column", minHeight: 0, background: "var(--background)" }}>
        <div style={{ textAlign: "center", padding: "12px 0 4px", fontSize: "var(--text-xs)", color: "var(--text-muted)" }}>目前只有一版文案,再生成一版不同角度的即可并排对比</div>
        <div className="cs" style={{ flex: 1, minHeight: 0, overflowY: "auto", display: "flex", justifyContent: "center", padding: 16 }}>
          <div style={{ width: 560, maxWidth: "100%" }}>
            <ABVersionCard id={singleId} />
          </div>
        </div>
        <div style={{ padding: "0 16px 16px", display: "flex", justifyContent: "center" }}>
          <Button variant="primary" size="sm" leftIcon={<Icon name="sparkles" size={13} />} onClick={() => actions.say("请基于当前选题再写一版不同角度的文案作为 B 版,和现有这版做对比;用 xhs_copy 的 versions 数组同时输出这两版。")}>让🍠再生成一版做对比</Button>
        </div>
      </div>
    );
  }

  // ① ≥2 版 → 并排模块卡,每版独立体检分/字数/标签数。
  return (
    <div style={{ flex: 1, display: "flex", flexDirection: "column", minHeight: 0, background: "var(--background)" }}>
      <div style={{ textAlign: "center", padding: "12px 0 4px", fontSize: "var(--text-xs)", color: "var(--text-muted)" }}>A·B 并排对比 · 每版体检分/字数独立计算,选更优的一版定稿</div>
      <div className="cs" style={{ flex: 1, minHeight: 0, overflowY: "auto", display: "flex", gap: 14, padding: 16, alignItems: "stretch" }}>
        {ids.slice(0, 2).map((id) => (
          <div key={id} style={{ flex: 1, minWidth: 0, display: "flex" }}>
            <ABVersionCard id={id} />
          </div>
        ))}
      </div>
    </div>
  );
}

// 单版模块卡:头部(版本标识 + 差异说明 + 体检分) · 正文(标题/正文/标签) · 模块化指标底栏(本版字数/标签数/体检分) · 采用此版。
// 内容来源:优先 note.versions[id];无 versions(单版草稿态)回退 canonical draft,故单版也能正常渲染。
function ABVersionCard({ id }: { id: VersionId }) {
  const { note, actions } = useStudio();
  const v = note.versions?.[id];
  const title = v?.title ?? note.title;
  const body = v?.body ?? note.body;
  const tags = v?.tags ?? note.tags;
  const cover = v?.cover ?? note.cover;
  const label = v?.label ?? id;
  const noteText = v?.note ?? null;
  const checks = computeChecks({ title, body, tags, cover, kw: note.kw });
  const score = scoreOf(checks);
  const wordCount = body.length;
  const active = note.activeVersion === id;
  const scoreColor = score >= 80 ? "var(--success)" : score >= 60 ? "var(--warning)" : "var(--text-muted)";

  return (
    <div style={{ flex: 1, minWidth: 0, display: "flex", flexDirection: "column", background: "var(--surface-card)", border: `1px solid ${active ? "var(--primary)" : "var(--border)"}`, borderRadius: "var(--radius-lg)", overflow: "hidden", boxShadow: active ? "var(--shadow-md)" : "var(--shadow-xs)" }}>
      {/* 头部:版本标识 + 差异说明 + 体检分 */}
      <div style={{ padding: "11px 14px", borderBottom: "1px solid var(--border)", background: active ? "var(--accent-surface)" : "var(--oats-light)", display: "flex", alignItems: "center", justifyContent: "space-between", gap: 8 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 8, minWidth: 0 }}>
          <span style={{ width: 22, height: 22, borderRadius: 6, background: active ? "var(--primary)" : "var(--oats-dark)", color: active ? "#fff" : "var(--text-muted)", fontSize: 11, fontWeight: 800, display: "inline-flex", alignItems: "center", justifyContent: "center", flexShrink: 0, fontFamily: "var(--font-display)" }}>{id}</span>
          <span style={{ fontSize: 11, fontWeight: 700, color: "var(--text-body)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{label.replace(/^版本\s*/, "")}{noteText ? <span style={{ color: "var(--text-muted)", fontWeight: 500 }}> · {noteText}</span> : null}</span>
        </div>
        <span style={{ display: "inline-flex", alignItems: "baseline", gap: 4, flexShrink: 0 }}>
          <span style={{ fontFamily: "var(--font-display)", fontWeight: 800, fontSize: "var(--text-lg)", color: scoreColor }}>{score}</span>
          <span style={{ fontSize: 10, color: "var(--text-subtle)" }}>分</span>
          {active && <span style={{ marginLeft: 4, fontSize: 9, color: "var(--primary)", fontWeight: 700, background: "var(--surface-card)", padding: "1px 6px", borderRadius: 999 }}>当前</span>}
        </span>
      </div>

      {/* 正文区:标题 / 正文 / 标签,各自成块 */}
      <div className="cs" style={{ flex: 1, overflowY: "auto", padding: 16, display: "flex", flexDirection: "column", gap: 12 }}>
        <h3 style={{ margin: 0, fontFamily: "var(--font-display)", fontWeight: 800, fontSize: "var(--text-base)", lineHeight: 1.3, color: title ? "var(--text-body)" : "var(--text-subtle)" }}>{title || "(无标题)"}</h3>
        <p style={{ margin: 0, fontSize: "var(--text-sm)", lineHeight: "var(--leading-relaxed)", color: "var(--text-body)", whiteSpace: "pre-wrap", overflowWrap: "anywhere" }}>{body || "(无正文)"}</p>
        {tags.length > 0 && (
          <div style={{ display: "flex", flexWrap: "wrap", gap: 5 }}>
            {tags.map((tg) => <span key={tg} style={{ fontSize: 10, color: "var(--topicblue-default)", background: "var(--topicblue-light)", borderRadius: 999, padding: "2px 8px" }}>#{tg}</span>)}
          </div>
        )}
      </div>

      {/* 模块化指标底栏:本版字数 / 标签数 / 体检分 —— 每版独立,不再混搭 */}
      <div style={{ padding: "8px 14px", borderTop: "1px solid var(--border)", display: "flex", alignItems: "center", gap: 14, fontSize: 10, color: "var(--text-subtle)", background: "var(--oats-light)" }}>
        <span style={{ display: "inline-flex", alignItems: "center", gap: 4 }}><Icon name="file-text" size={11} /> 字数 <b className="font-tabular" style={{ color: wordCount > 1000 ? "var(--warning)" : "var(--text-body)" }}>{wordCount}</b>/1000</span>
        <span style={{ display: "inline-flex", alignItems: "center", gap: 4 }}><Icon name="hash" size={11} /> 标签 <b className="font-tabular" style={{ color: tags.length >= 5 ? "var(--success)" : "var(--text-body)" }}>{tags.length}</b></span>
        <span style={{ display: "inline-flex", alignItems: "center", gap: 4, marginLeft: "auto" }}><Icon name="stethoscope" size={11} /> 体检 <b className="font-tabular" style={{ color: scoreColor }}>{score}</b> 分</span>
      </div>

      <div style={{ padding: 10, borderTop: "1px solid var(--border)" }}>
        <Button variant={active ? "secondary" : "primary"} size="sm" block disabled={active} onClick={() => { actions.setVersion(id); actions.toast(`✅ 已采用「${label}」为当前稿`); }}>{active ? "当前采用中" : "采用此版"}</Button>
      </div>
    </div>
  );
}

// 标题优化整屏子界面(§4.5):左栏公式列表,右栏该公式的候选(LLM 按公式意图生成,非模板拼接)。
// 顶部返回编辑 + 当前标题回显 + n/20 字数校验。选公式 → 委派 xhs-title 出候选 → 每条可编辑、
// 独立字数校验,"采用这条"写回标题并自动返回编辑。候选来自真实 stream(titleSuggestions),不造假。
function TitleScreen({ onBack }: { onBack: () => void }) {
  const { note, actions, titleSuggestions } = useStudio();
  const [formula, setFormula] = useState<string | null>(null);
  const [drafts, setDrafts] = useState<Record<number, string>>({});
  const generating = note.status === "writing";
  // 候选属于当前所选公式时才展示(避免上一个公式的候选串台)。
  const candidates = titleSuggestions && (!formula || titleSuggestions.formula === formula) ? titleSuggestions.candidates : [];

  const pickFormula = (name: string) => {
    setFormula(name);
    setDrafts({});
    const kw = note.kw ? `,核心词「${note.kw}」` : "";
    const base = note.title ? `现有标题《${note.title}》` : "还没有标题";
    actions.say(`用「${name}」这个标题公式,给我出 5 个小红书标题候选。${base}${kw}。每个都要 ≤20 字、有点击欲。只用 xhs_titles 代码块返回候选,不要别的话。`);
  };

  return (
    <div style={{ flex: 1, display: "flex", flexDirection: "column", minHeight: 0, background: "var(--background)" }}>
      {/* 顶部:返回 + 当前标题回显 + n/20 */}
      <div style={{ display: "flex", alignItems: "center", gap: 12, padding: "10px 20px", background: "var(--surface-card)", borderBottom: "1px solid var(--border)", flexShrink: 0 }}>
        <button onClick={onBack} style={{ display: "inline-flex", alignItems: "center", gap: 4, background: "none", border: "1px solid var(--border)", borderRadius: "var(--radius-sm)", padding: "5px 10px", cursor: "pointer", fontSize: "var(--text-xs)", color: "var(--text-body)", fontWeight: 600 }}><Icon name="arrow-left" size={13} /> 返回编辑</button>
        <span style={{ width: 1, height: 18, background: "var(--border)" }} />
        <Icon name="type" size={14} color="var(--primary)" />
        <span style={{ fontSize: "var(--text-sm)", fontWeight: 700 }}>标题优化</span>
        <span style={{ flex: 1, minWidth: 0, fontSize: 12, color: "var(--text-muted)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{note.title || "还没有标题"}</span>
        <span className="font-tabular" style={{ fontSize: 11, color: note.title.length > 20 ? "var(--warning)" : "var(--text-subtle)" }}>{note.title.length}/20</span>
      </div>
      <div style={{ flex: 1, display: "flex", minHeight: 0 }}>
        {/* 左栏:标题公式列表 */}
        <aside className="cs" style={{ width: 200, borderRight: "1px solid var(--border)", background: "var(--surface-card)", overflowY: "auto", padding: 14, display: "flex", flexDirection: "column", gap: 7, flexShrink: 0 }}>
          <Eyebrow>标题公式</Eyebrow>
          {TITLE_FORMULAS.map((f) => {
            const on = formula === f.name;
            return (
              <button key={f.name} onClick={() => pickFormula(f.name)} disabled={generating} title={f.hint}
                style={{ display: "flex", flexDirection: "column", gap: 2, textAlign: "left", padding: "8px 10px", borderRadius: "var(--radius-sm)", cursor: generating ? "default" : "pointer", border: `1px solid ${on ? "var(--primary)" : "var(--border)"}`, background: on ? "var(--accent-surface)" : "var(--surface-card)", opacity: generating && !on ? 0.6 : 1 }}>
                <span style={{ fontSize: 12, fontWeight: 700, color: on ? "var(--primary)" : "var(--text-body)" }}>{f.name}</span>
                <span style={{ fontSize: 9, color: "var(--text-subtle)", lineHeight: 1.4 }}>{f.hint}</span>
              </button>
            );
          })}
        </aside>
        {/* 右栏:候选(可编辑 + 独立字数校验 + 采用这条) */}
        <div className="cs" style={{ flex: 1, minWidth: 0, overflowY: "auto", padding: "20px 28px" }}>
          <div style={{ maxWidth: 560, margin: "0 auto", display: "flex", flexDirection: "column", gap: 14 }}>
            {!formula ? (
              <div style={{ textAlign: "center", color: "var(--text-subtle)", fontSize: "var(--text-sm)", padding: "48px 20px", lineHeight: 1.7 }}>
                <div style={{ fontSize: 30, marginBottom: 8 }}>✍️</div>
                左边选一个标题公式,🍠 会按它的套路给你出几个候选标题。
              </div>
            ) : generating && candidates.length === 0 ? (
              <div style={{ display: "flex", alignItems: "center", gap: 10, color: "var(--text-muted)", fontSize: "var(--text-sm)", padding: "40px 0", justifyContent: "center" }}>
                <Icon name="loader" size={16} color="var(--primary)" /> 正在按「{formula}」生成候选…
              </div>
            ) : candidates.length === 0 ? (
              <div style={{ textAlign: "center", color: "var(--text-subtle)", fontSize: "var(--text-sm)", padding: "40px 20px" }}>还没拿到候选,可再点一次公式重试。</div>
            ) : (
              <>
                <Eyebrow>「{formula}」候选 · 可改后采用</Eyebrow>
                {candidates.map((c, i) => {
                  const val = drafts[i] ?? c;
                  const over = val.length > 20;
                  return (
                    <div key={i} style={{ background: "var(--surface-card)", border: "1px solid var(--border)", borderRadius: "var(--radius-md)", padding: 12, display: "flex", flexDirection: "column", gap: 8 }}>
                      <textarea value={val} onChange={(e) => setDrafts((d) => ({ ...d, [i]: e.target.value }))} rows={2}
                        style={{ border: "none", background: "transparent", resize: "none", fontFamily: "var(--font-display)", fontWeight: 700, fontSize: "var(--text-base)", lineHeight: 1.3, color: "var(--text-body)", outline: "none" }} />
                      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
                        <span className="font-tabular" style={{ fontSize: 10, color: over ? "var(--warning)" : "var(--text-subtle)" }}>{val.length}/20{over ? " · 偏长" : ""}</span>
                        <Button variant="primary" size="sm" leftIcon={<Icon name="check" size={12} />} onClick={() => { actions.updateField("title", val); actions.toast("✅ 已采用为标题"); onBack(); }}>采用这条</Button>
                      </div>
                    </div>
                  );
                })}
                <button onClick={() => pickFormula(formula)} disabled={generating} style={{ alignSelf: "center", display: "inline-flex", alignItems: "center", gap: 5, background: "none", border: "none", cursor: "pointer", color: "var(--primary)", fontSize: 11, fontWeight: 600 }}>
                  <Icon name="refresh-cw" size={12} /> 换一批候选
                </button>
              </>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

// 创作过程抽屉(P2-b):回看本次文案生成的"大纲与对标依据 + AI 腔自审纠偏",与成品正文分两条道。
// 数据来自 note.process(从 xhs_copy 块的 outline/ai_audit_log 字段解析),缺失时优雅降级,永不崩。
function CreationProcessDrawer({ onClose }: { onClose: () => void }) {
  const { note } = useStudio();
  const p = note.process;
  const empty = !p || (!p.outline && !p.audit);
  return (
    <div onClick={onClose} style={{ position: "fixed", inset: 0, background: "rgba(15,15,16,0.35)", zIndex: 55, display: "flex", justifyContent: "flex-end" }}>
      <div onClick={(e) => e.stopPropagation()} className="cs slide-in-right" style={{ width: 420, maxWidth: "92vw", height: "100%", background: "var(--background)", boxShadow: "var(--shadow-2xl)", overflowY: "auto", display: "flex", flexDirection: "column" }}>
        <div style={{ position: "sticky", top: 0, background: "var(--surface-card)", borderBottom: "1px solid var(--border)", padding: "14px 16px", display: "flex", alignItems: "center", justifyContent: "space-between", zIndex: 1 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 7 }}>
            <Icon name="history" size={16} color="var(--primary)" />
            <span style={{ fontSize: "var(--text-sm)", fontWeight: 700 }}>创作过程</span>
            <span style={{ fontSize: 9, color: "var(--text-subtle)" }}>· 对标依据 + 去AI腔自审</span>
          </div>
          <button onClick={onClose} aria-label="关闭" style={{ border: "none", background: "none", cursor: "pointer", color: "var(--text-subtle)", display: "inline-flex" }}><Icon name="x" size={16} /></button>
        </div>
        <div className="cs" style={{ padding: 16, display: "flex", flexDirection: "column", gap: 14 }}>
          {empty ? (
            <div style={{ textAlign: "center", color: "var(--text-muted)", fontSize: "var(--text-sm)", padding: "40px 20px", lineHeight: "var(--leading-relaxed)" }}>
              <div style={{ fontSize: 30, marginBottom: 8 }}>🗂️</div>
              本版没有可回看的创作过程记录。
              <div style={{ fontSize: 11, color: "var(--text-subtle)", marginTop: 6 }}>委派 🍠 写文案时会带对标依据与自审纠偏记录;直接手写或旧会话的文案可能没有。</div>
            </div>
          ) : (
            <>
              {p?.outline && (
                <section style={{ background: "var(--surface-card)", border: "1px solid var(--border)", borderRadius: "var(--radius-md)", padding: 12 }}>
                  <div style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 8 }}>
                    <Icon name="clipboard-pen" size={13} color="var(--primary)" />
                    <span style={{ fontSize: "var(--text-xs)", fontWeight: 700 }}>大纲与对标依据</span>
                  </div>
                  <p style={{ margin: 0, fontSize: "var(--text-xs)", color: "var(--text-body)", lineHeight: "var(--leading-relaxed)", whiteSpace: "pre-wrap", overflowWrap: "anywhere" }}>{p?.outline}</p>
                </section>
              )}
              {p?.audit && (
                <section style={{ background: "var(--surface-card)", border: "1px solid var(--border)", borderRadius: "var(--radius-md)", padding: 12 }}>
                  <div style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 8 }}>
                    <Icon name="shield-check" size={13} color="var(--primary)" />
                    <span style={{ fontSize: "var(--text-xs)", fontWeight: 700 }}>AI 腔自审纠偏</span>
                    <span style={{ fontSize: 9, color: "var(--text-subtle)" }}>· 22 条指纹逐条</span>
                  </div>
                  <p style={{ margin: 0, fontSize: 11, color: "var(--text-body)", lineHeight: "var(--leading-relaxed)", whiteSpace: "pre-wrap", overflowWrap: "anywhere" }}>{p?.audit}</p>
                </section>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  );
}
