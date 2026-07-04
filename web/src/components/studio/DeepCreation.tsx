"use client";

// 深度创作 screen — a focused long-form environment bound to the shared note.

import { useMemo, useState } from "react";
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
