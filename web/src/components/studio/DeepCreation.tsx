"use client";

// 深度创作 screen — a focused long-form environment bound to the shared note.

import { useState } from "react";
import { Badge, Button, TopicCard, Icon } from "@/components/ds";
import { useStudio } from "@/components/studio/useStudio";
import { computeChecks, scoreOf } from "@/components/studio/rubric";
import { type VersionId } from "@/components/studio/types";
import { EvidenceChips } from "./CreationScreen";
import { DeepEditor } from "./DeepEditor";

type DeepMode = "edit" | "compare";

export function DeepCreation() {
  const { note, setSection } = useStudio();
  const [mode, setMode] = useState<DeepMode>("edit");
  if (note.status === "idle") return <DeepEmpty onGo={() => setSection("create")} />;
  const body = mode === "compare" ? <ABCompare /> : <DeepEditor />;
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
