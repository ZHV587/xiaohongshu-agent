"use client";

// 全功能深度创作编辑器 — 三区工作台：结构 | 写作画布 | 质检定稿
// 复用 CopyDoctor / RiskPanel / ScheduleBar / EvidenceChips（全局）。

import { useRef, type ChangeEvent } from "react";
import { Button, HashtagTag, Icon } from "@/components/ds";
import { Eyebrow, PanelHead } from "@/components/studio/ui";
import { useStudio } from "./StudioContext";
import { computeChecks, scoreOf } from "./rubric";
import { QUICK_EMOJI, type VersionId } from "./types";
import { CopyDoctor, EmptyComposer, RiskPanel, ScheduleBar, VisualStudio } from "./Composer";
import { EvidenceChips } from "./CreationScreen";

const quickEmoji = QUICK_EMOJI;

export function DeepEditor() {
  const { note, actions } = useStudio();
  const bodyRef = useRef<HTMLTextAreaElement>(null);
  const checks = computeChecks(note);
  const score = scoreOf(checks);
  const writing = note.status === "writing";
  const body = note.body || "";
  // 推荐标签来自选中选题的真实关键词(note.kw,agent 产出的空格分隔词),去重、去掉已选,取前 6;
  // 无 kw(未选选题/agent 未给)→ 空,不写死假标签,由「配标签」按钮让 AI 生成。
  const kwSuggestions = (note.kw || "")
    .split(/[\s,，、]+/)
    .map((s) => s.trim())
    .filter((s) => s && !note.tags.includes(s))
    .filter((s, i, arr) => arr.indexOf(s) === i)
    .slice(0, 6);

  const insertEmoji = (e: string) => {
    const el = bodyRef.current;
    if (!el) { actions.updateField("body", body + e); return; }
    const s = el.selectionStart, en = el.selectionEnd;
    actions.updateField("body", body.slice(0, s) + e + body.slice(en));
    requestAnimationFrame(() => { el.focus(); el.selectionStart = el.selectionEnd = s + e.length; });
  };

  const outline: { k: string; ok: boolean }[] = [
    { k: "共情钩子", ok: /谁懂|绝了|天花板|后悔|啦！|冲鸭|姐妹/.test(body.slice(0, 50)) || /\p{Extended_Pictographic}/u.test(body.slice(0, 30)) },
    { k: "分点清单", ok: /1️⃣|2️⃣|✅|❌/.test(body) },
    { k: "选购 TIPS", ok: /TIPS|tips|📝|挑选|建议|避坑/.test(body) },
    { k: "互动收口", ok: /评论|收藏|关注|交流|码住|抄作业/.test(body) },
    { k: "话题标签", ok: note.tags.length >= 5 },
  ];
  const versionScore = (id: VersionId): number | null => {
    if (!note.versions) return null;
    const v = note.versions[id];
    if (!v) return null;
    return scoreOf(computeChecks({ ...note, title: v.title, body: v.body, tags: v.tags, cover: v.cover }));
  };

  return (
    <div style={{ flex: 1, minHeight: 0, display: "flex", background: "var(--background)" }}>
      {/* ── 左区：结构 ── */}
      <aside className="cs" style={{ width: 224, borderRight: "1px solid var(--border)", background: "var(--surface-card)", overflowY: "auto", padding: 14, display: "flex", flexDirection: "column", gap: 18, flexShrink: 0 }}>
        <div style={{ display: "flex", flexDirection: "column", gap: 7 }}>
          <Eyebrow>草稿版本</Eyebrow>
          {note.versions ? (["A", "B", "C"] as VersionId[]).filter((id) => note.versions?.[id]).map((id) => {
            const v = note.versions![id]!, on = note.activeVersion === id, sc = versionScore(id);
            return (
              <button key={id} data-testid={`version-${id}`} onClick={() => actions.setVersion(id)} style={{ display: "flex", alignItems: "center", gap: 8, textAlign: "left", padding: "8px 9px", borderRadius: "var(--radius-sm)", cursor: "pointer", border: `1px solid ${on ? "var(--primary)" : "var(--border)"}`, background: on ? "var(--accent-surface)" : "var(--surface-card)" }}>
                <span style={{ width: 20, height: 20, borderRadius: 6, background: on ? "var(--primary)" : "var(--oats-dark)", color: on ? "#fff" : "var(--text-muted)", fontSize: 11, fontWeight: 800, display: "inline-flex", alignItems: "center", justifyContent: "center", flexShrink: 0, fontFamily: "var(--font-display)" }}>{id}</span>
                <span style={{ flex: 1, minWidth: 0, fontSize: 11, fontWeight: 600, color: on ? "var(--primary)" : "var(--text-body)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{v.label.replace("版本 ", "")}</span>
                {sc != null && <span style={{ fontSize: 10, fontWeight: 700, color: sc >= 80 ? "var(--success)" : "var(--warning)" }}>{sc}</span>}
              </button>
            );
          }) : <span style={{ fontSize: 10, color: "var(--text-subtle)" }}>—</span>}
        </div>
        <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
          <Eyebrow>创作大纲</Eyebrow>
          {outline.map((o) => (
            <div key={o.k} style={{ display: "flex", alignItems: "center", gap: 7, fontSize: 11, color: o.ok ? "var(--text-body)" : "var(--text-subtle)" }}>
              <Icon name={o.ok ? "check-circle-2" : "circle"} size={13} color={o.ok ? "var(--success)" : "var(--border-strong)"} />
              {o.k}
            </div>
          ))}
        </div>
        <div style={{ display: "flex", flexDirection: "column", gap: 7 }}>
          <Eyebrow>创作依据</Eyebrow>
          <EvidenceChips topicId={note.topicId} />
        </div>
      </aside>

      {/* ── 中区：写作画布 ── */}
      <div className="cs" style={{ flex: 1, minWidth: 0, overflowY: "auto", display: "flex", justifyContent: "center", padding: "20px 28px" }}>
        <div style={{ width: 600, maxWidth: "100%", display: "flex", flexDirection: "column", gap: 16 }}>
          {/* 封面 + 图集 · 小红书 3:4 */}
          {!note.title && !body ? <EmptyComposer /> : null}
          <VisualStudio />
          {/* 标题 */}
          <div style={{ display: "flex", flexDirection: "column", gap: 5 }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
              <Eyebrow>标题 · 钩子优先</Eyebrow>
              <span className="font-tabular" style={{ fontSize: 10, color: note.title.length > 20 ? "var(--warning)" : "var(--text-subtle)" }}>{note.title.length} / 20</span>
            </div>
            <input value={note.title} onChange={(e: ChangeEvent<HTMLInputElement>) => actions.updateField("title", e.target.value)} placeholder="写个钩子标题…" style={{ border: "none", borderBottom: "2px solid var(--border)", background: "transparent", fontFamily: "var(--font-display)", fontWeight: 800, fontSize: "var(--text-xl)", color: "var(--text-body)", padding: "4px 0", outline: "none", letterSpacing: "var(--tracking-tight)" }} />
          </div>
          {/* 工具条（吸顶） */}
          <div style={{ position: "sticky", top: 0, zIndex: 1, display: "flex", flexWrap: "wrap", alignItems: "center", gap: 6, padding: "8px 0", background: "var(--background)", borderBottom: "1px solid var(--border)" }}>
            <Button variant="soft" size="sm" leftIcon={<Icon name="sparkles" size={12} />} onClick={actions.polish} disabled={writing}>润色</Button>
            <Button variant="soft" size="sm" leftIcon={<Icon name="scissors" size={12} />} onClick={actions.shorten} disabled={writing}>瘦身</Button>
            <Button variant="soft" size="sm" leftIcon={<Icon name="hash" size={12} />} onClick={actions.addTags} disabled={writing}>配标签</Button>
            <span style={{ width: 1, height: 18, background: "var(--border)", margin: "0 3px" }} />
            {quickEmoji.slice(0, 8).map((e) => <button key={e} onClick={() => insertEmoji(e)} disabled={writing} style={{ border: "none", background: "transparent", cursor: "pointer", fontSize: 16, lineHeight: 1, padding: 1, opacity: writing ? 0.4 : 1 }}>{e}</button>)}
            <span style={{ marginLeft: "auto", fontSize: 10, color: body.length > 1000 ? "var(--warning)" : "var(--text-subtle)" }} className="font-tabular">{writing ? "🍠 生成中…" : `${body.length} / 1000`}</span>
          </div>
          {/* 正文 */}
          <textarea data-testid="draft-body" ref={bodyRef} value={writing ? body + " ▍" : body} onChange={(e: ChangeEvent<HTMLTextAreaElement>) => actions.updateField("body", e.target.value)} readOnly={writing} placeholder="正文从一句共情钩子开始，再用 1️⃣2️⃣3️⃣ 分点干货，最后引导互动…" style={{ border: "none", background: "transparent", resize: "none", minHeight: 300, fontFamily: "var(--font-sans)", fontSize: "var(--text-sm)", lineHeight: "var(--leading-relaxed)", color: "var(--text-body)", outline: "none" }} />
          {/* 话题标签 */}
          <div style={{ display: "flex", flexDirection: "column", gap: 8, borderTop: "1px solid var(--border)", paddingTop: 14 }}>
            <Eyebrow>话题标签 · {note.tags.length} 个（建议 5–10，大词+长尾）</Eyebrow>
            <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
              {note.tags.map((t) => <span key={t} onClick={() => actions.removeTag(t)} style={{ cursor: "pointer" }} title="点击移除"><HashtagTag>{t}</HashtagTag></span>)}
              {note.tags.length === 0 && <span style={{ fontSize: 11, color: "var(--text-subtle)" }}>暂无，点上方「配标签」让 AI 基于正文生成</span>}
            </div>
            {/* 推荐标签来自选中选题的真实关键词(note.kw,agent 产出);无则引导用「配标签」让 AI 生成,不写死假标签 */}
            {kwSuggestions.length > 0 && (
              <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
                <span style={{ fontSize: 10, color: "var(--text-subtle)", alignSelf: "center" }}>选题关键词：</span>
                {kwSuggestions.map((t) => <HashtagTag key={t} addable onAdd={() => actions.addTag(t)}>{t}</HashtagTag>)}
              </div>
            )}
          </div>
        </div>
      </div>

      {/* ── 右区：质检定稿 ── */}
      <aside className="cs" style={{ width: 332, borderLeft: "1px solid var(--border)", background: "var(--surface-card)", overflowY: "auto", padding: 16, display: "flex", flexDirection: "column", gap: 14, flexShrink: 0, boxShadow: "var(--shadow-lg)" }}>
        <PanelHead icon="gauge" title="文案体检 · 定稿" sub="体检 / 原创度 / 排期发布" />
        <CopyDoctor checks={checks} score={score} />
        <RiskPanel note={note} />
        <ScheduleBar score={score} status={note.status} />
      </aside>
    </div>
  );
}
