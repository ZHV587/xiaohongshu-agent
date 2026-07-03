"use client";

// 深度创作 screen — a focused long-form environment bound to the shared note.

import { useState } from "react";
import { Badge, Button, Card, HashtagTag, TopicCard, Icon } from "@/components/ds";
import { useStudio } from "@/components/studio/useStudio";
import { computeChecks, scoreOf } from "@/components/studio/rubric";
import { type VersionId } from "@/components/studio/types";
import { EvidenceChips } from "./CreationScreen";
import { DeepEditor } from "./DeepEditor";
import { CopyDoctor } from "./Composer";
import { Eyebrow, PanelHead } from "./ui";

export type DeepForm = "immersive" | "flow" | "workspace";
type DeepMode = "edit" | "compare";

export function DeepCreation({ form = "immersive" }: { form?: DeepForm }) {
  const { note, setSection } = useStudio();
  const [mode, setMode] = useState<DeepMode>("edit");
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
function DeepTopicBar({ mode, setMode }: { mode: DeepMode; setMode: (m: DeepMode) => void }) {
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
        <button onClick={() => setSection("create")} style={{ display: "inline-flex", alignItems: "center", gap: 5, background: "none", border: "1px solid var(--border)", borderRadius: "var(--radius-sm)", padding: "5px 10px", cursor: "pointer", fontSize: "var(--text-xs)", color: "var(--text-muted)", whiteSpace: "nowrap" }}>
          <Icon name="repeat" size={12} /> 换题
        </button>
      </div>
    </div>
  );
}

function DeepImmersive() {
  return <DeepEditor />;
}

function BigEditor({ maxWidth = 720 }: { maxWidth?: number }) {
  const { note, actions } = useStudio();
  return (
    <div style={{ maxWidth, margin: "0 auto", width: "100%", background: "var(--surface-card)", border: "1px solid var(--border)", borderRadius: "var(--radius-lg)", boxShadow: "var(--shadow-md)", padding: 28, display: "flex", flexDirection: "column", gap: 16 }}>
      <input
        value={note.title}
        placeholder="写个钩子标题…（≤20 字）"
        onChange={(e) => actions.updateField("title", e.target.value)}
        style={{ border: "none", outline: "none", background: "transparent", fontFamily: "var(--font-display)", fontWeight: 800, fontSize: "var(--text-xl)", color: "var(--text-body)", letterSpacing: "var(--tracking-tight)" }}
      />
      <div style={{ height: 1, background: "var(--border)" }} />
      <textarea
        value={note.body}
        placeholder="正文从一句共情钩子开始，再用 1️⃣2️⃣3️⃣ 分点干货，最后引导互动…"
        onChange={(e) => actions.updateField("body", e.target.value)}
        style={{ border: "none", outline: "none", resize: "none", background: "transparent", fontFamily: "var(--font-sans)", fontSize: "var(--text-sm)", lineHeight: "var(--leading-relaxed)", color: "var(--text-body)", minHeight: 320, flex: 1 }}
      />
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", fontSize: 11, color: "var(--text-subtle)" }}>
        <span>自动保存 · 当前草稿</span>
        <span className="font-tabular">{note.body.length} / 1000 字</span>
      </div>
    </div>
  );
}

function AssistantPanel() {
  const { note, actions } = useStudio();
  const checks = computeChecks(note);
  const kwSuggestions = (note.kw || "")
    .split(/[\s,，、]+/)
    .map((s) => s.trim())
    .filter(Boolean)
    .filter((s, i, arr) => arr.indexOf(s) === i)
    .slice(0, 8);
  return (
    <div className="cs" style={{ display: "flex", flexDirection: "column", gap: 14, height: "100%", overflowY: "auto" }}>
      <PanelHead icon="sparkles" title="AI 创作助手" sub="随写随帮 · 质检同步" />
      <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
        <Button variant="soft" size="sm" leftIcon={<Icon name="sparkles" size={12} />} onClick={actions.polish}>润色语气</Button>
        <Button variant="soft" size="sm" leftIcon={<Icon name="scissors" size={12} />} onClick={actions.shorten}>一键瘦身</Button>
        <Button variant="soft" size="sm" leftIcon={<Icon name="hash" size={12} />} onClick={actions.addTags}>配标签</Button>
      </div>
      {kwSuggestions.length > 0 && (
        <div>
          <Eyebrow style={{ marginBottom: 7 }}>推荐话题标签</Eyebrow>
          <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
            {kwSuggestions.filter((tag) => !note.tags.includes(tag)).map((tag) => <HashtagTag key={tag} addable onAdd={() => actions.addTag(tag)}>{tag}</HashtagTag>)}
          </div>
        </div>
      )}
      <CopyDoctor checks={checks} score={scoreOf(checks)} />
    </div>
  );
}

function EvidenceRail() {
  const { note, evidence, actions } = useStudio();
  const items = note.topicId ? evidence[note.topicId]?.items ?? [] : [];
  return (
    <div className="cs" style={{ display: "flex", flexDirection: "column", gap: 12, height: "100%", overflowY: "auto" }}>
      <PanelHead icon="database" title="飞书资料 · 证据" sub="选题依据来源" />
      {items.length === 0 && <Card padding="md" tone="sunken"><span style={{ fontSize: "var(--text-xs)", color: "var(--text-subtle)" }}>暂无证据条目，生成选题后会在这里显示。</span></Card>}
      {items.map((item) => (
        <Card key={item.resource_id} padding="sm" tone="sunken" interactive onClick={() => actions.openEvidence({ ...item, mode: evidence[note.topicId!].mode })}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 5 }}>
            <Badge tone="topic" shape="chip">{item.type}</Badge>
            <span style={{ fontSize: 9, color: "var(--text-subtle)" }}>{item.source_updated_at || "源端时间"}</span>
          </div>
          <div style={{ fontSize: "var(--text-xs)", fontWeight: 600, color: "var(--text-body)" }}>{item.title}</div>
          <div style={{ fontSize: 10, color: "var(--text-muted)", marginTop: 3, lineHeight: 1.5 }}>{item.summary}</div>
        </Card>
      ))}
    </div>
  );
}

function DeepFlow() {
  const [active, setActive] = useState(2);
  const outline = [
    { step: "选题", detail: "从爆款数据挑方向" },
    { step: "大纲", detail: "钩子 → 清单 → TIPS → 互动" },
    { step: "正文", detail: "逐段撰写 + 实时体检" },
    { step: "润色", detail: "/polish 语气 · /shorten 瘦身" },
    { step: "配图", detail: "封面大字 + 内容图" },
  ];
  return (
    <div style={{ flex: 1, display: "flex", flexDirection: "column", minHeight: 0, background: "var(--background)" }}>
      <div style={{ display: "flex", alignItems: "center", gap: 8, padding: "16px 28px", borderBottom: "1px solid var(--border)", background: "var(--surface-card)", flexShrink: 0, justifyContent: "center" }}>
        {outline.map((item, i) => {
          const done = i < active;
          const on = i === active;
          return (
            <button key={item.step} onClick={() => setActive(i)} style={{ display: "inline-flex", alignItems: "center", gap: 7, cursor: "pointer", background: "none", border: "none" }}>
              <span style={{ width: 26, height: 26, borderRadius: "999px", display: "inline-flex", alignItems: "center", justifyContent: "center", fontSize: 12, fontWeight: 700, fontFamily: "var(--font-display)", background: on ? "var(--primary)" : done ? "var(--success-surface)" : "var(--oats-dark)", color: on ? "#fff" : done ? "var(--success)" : "var(--text-subtle)", border: done ? "1px solid var(--success)" : "none" }}>{done ? "✓" : i + 1}</span>
              <span style={{ fontSize: "var(--text-xs)", fontWeight: on ? 700 : 500, color: on ? "var(--primary)" : done ? "var(--text-body)" : "var(--text-subtle)" }}>{item.step}</span>
            </button>
          );
        })}
      </div>
      <div className="cs" style={{ flex: 1, overflowY: "auto", padding: 28 }}>
        <div style={{ maxWidth: 880, margin: "0 auto" }}>
          <div style={{ textAlign: "center", marginBottom: 18 }}>
            <div style={{ fontFamily: "var(--font-display)", fontWeight: 800, fontSize: "var(--text-lg)" }}>第 {active + 1} 步 · {outline[active].step}</div>
            <div style={{ fontSize: "var(--text-xs)", color: "var(--text-muted)", marginTop: 4 }}>{outline[active].detail}</div>
          </div>
          {active === 2 ? <div style={{ display: "flex", gap: 16, alignItems: "flex-start" }}><div style={{ flex: 1 }}><BigEditor maxWidth={9999} /></div><div style={{ width: 300, flexShrink: 0 }}><AssistantPanel /></div></div> : <StepCards step={active} />}
        </div>
      </div>
      <div style={{ padding: 14, borderTop: "1px solid var(--border)", background: "var(--surface-card)", display: "flex", justifyContent: "center", gap: 10, flexShrink: 0 }}>
        <Button variant="secondary" onClick={() => setActive((value) => Math.max(0, value - 1))}>上一步</Button>
        <Button variant="primary" rightIcon={<Icon name="arrow-right" size={14} />} onClick={() => setActive((value) => Math.min(outline.length - 1, value + 1))}>下一步</Button>
      </div>
    </div>
  );
}

function StepCards({ step }: { step: number }) {
  const { note, topics } = useStudio();
  if (step === 0) {
    const topic = topics.find((item) => item.id === note.topicId) || topics[0];
    return topic ? (
      <div style={{ maxWidth: 460, margin: "0 auto", display: "flex", flexDirection: "column", gap: 10 }}>
        <TopicCard index={topic.id} title={topic.title} rationale={topic.rationale} hotRate={topic.hotRate} />
        <div style={{ display: "flex", alignItems: "center", justifyContent: "center", gap: 5, fontSize: 11, color: "var(--success)", fontWeight: 600 }}><Icon name="check-circle-2" size={13} color="var(--success)" /> 已选定该选题，进入下一步撰写大纲</div>
      </div>
    ) : null;
  }
  if (step === 1) {
    const lines = ["① 共情钩子：身份标签 + 场景痛点", "② 编号清单：核心信息分点", "③ 选购 TIPS：建议与避坑", "④ 互动收口：评论 + 话题标签矩阵"];
    return <Card padding="lg"><div style={{ display: "flex", flexDirection: "column", gap: 10 }}>{lines.map((line) => <div key={line} style={{ display: "flex", gap: 10, fontSize: "var(--text-sm)" }}><Icon name="check-circle-2" size={16} color="var(--success)" /><span>{line}</span></div>)}</div></Card>;
  }
  return <Card padding="lg"><div style={{ fontSize: "var(--text-sm)", color: "var(--text-muted)", lineHeight: "var(--leading-relaxed)" }}>{step === 3 ? "AI 正在按小红书语气润色，并裁剪到 1000 字内。可对比多版本草稿后定稿。" : "封面：暖色实拍大全景 + 大字报；建议再出内容图（产品特写 · 场景氛围 · 清单合影 · 选购对比）。"}</div></Card>;
}

function DeepWorkspace() {
  return (
    <div style={{ flex: 1, minHeight: 0, display: "grid", gridTemplateColumns: "260px minmax(0, 1fr) 340px", gap: 0, background: "var(--background)" }}>
      <aside style={{ borderRight: "1px solid var(--border)", background: "var(--surface-card)", padding: 16, minHeight: 0 }}><EvidenceRail /></aside>
      <main className="cs" style={{ overflowY: "auto", padding: 22 }}><BigEditor maxWidth={760} /></main>
      <aside style={{ borderLeft: "1px solid var(--border)", background: "var(--surface-card)", padding: 16, minHeight: 0, boxShadow: "var(--shadow-lg)" }}>
        <div style={{ display: "flex", flexDirection: "column", gap: 14, height: "100%" }}>
          <AssistantPanel />
        </div>
      </aside>
    </div>
  );
}

// A·B 版本并排对比
function ABCompare() {
  const { note } = useStudio();
  const [pair, setPair] = useState<[VersionId, VersionId]>(["A", "B"]);
  if (!note.versions) return null;
  const setSide = (i: number, v: VersionId) => setPair((p) => { const n = [...p] as [VersionId, VersionId]; n[i] = v; return n; });
  return (
    <div style={{ flex: 1, display: "flex", flexDirection: "column", minHeight: 0, background: "var(--background)" }}>
      <div style={{ textAlign: "center", padding: "12px 0 4px", fontSize: "var(--text-xs)", color: "var(--text-muted)" }}>A·B 并排对比 · 体检分数实时计算，选更优的一版定稿</div>
      <div style={{ flex: 1, minHeight: 0, display: "flex", gap: 14, padding: 16 }}>
        <ABCompareColumn id={pair[0]} side={0} onSelect={setSide} />
        <ABCompareColumn id={pair[1]} side={1} onSelect={setSide} />
      </div>
    </div>
  );
}

function ABCompareColumn({ id, side, onSelect }: { id: VersionId; side: number; onSelect: (side: number, version: VersionId) => void }) {
  const { note, actions } = useStudio();
  if (!note.versions) return null;
  const v = note.versions[id];
  if (!v) return null;
  const n = { ...note, title: v.title, body: v.body, tags: v.tags, cover: v.cover, kw: note.kw };
  const checks = computeChecks(n);
  const score = scoreOf(checks);
  const active = note.activeVersion === id;
  return (
    <div style={{ flex: 1, minWidth: 0, display: "flex", flexDirection: "column", background: "var(--surface-card)", border: `1px solid ${active ? "var(--primary)" : "var(--border)"}`, borderRadius: "var(--radius-lg)", overflow: "hidden" }}>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", padding: "10px 12px", borderBottom: "1px solid var(--border)", background: active ? "var(--accent-surface)" : "var(--oats-light)" }}>
        <select value={id} onChange={(e) => onSelect(side, e.target.value as VersionId)} style={{ border: "1px solid var(--border)", borderRadius: "var(--radius-sm)", padding: "3px 6px", fontSize: 11, fontWeight: 700, background: "var(--surface-card)", color: "var(--text-body)", cursor: "pointer" }}>
          {(["A", "B", "C"] as VersionId[]).filter((k) => note.versions?.[k]).map((k) => <option key={k} value={k}>{note.versions![k]!.label}</option>)}
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
}
