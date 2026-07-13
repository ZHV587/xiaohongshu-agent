"use client";

// v2 就地编辑器 — 创作屏右栏在 note.status !== "idle" 时原地渲染。
// 单列编辑区(封面折叠 + 标题 + 工具条 + 正文 + 内联体检 + 标签)+ 顶部工具按钮条(点开右侧抽屉:
// 版本 / 大纲 / 依据 / 文案体检 / 风控 / 标题优化 / 创作过程,同一时刻只开一个,按钮带实时角标)+
// 底部 ScheduleBar 常驻。原 v1 的左「结构」aside 与右「质检」aside 全部收进抽屉(DEV-SPEC §4.5)。

import { useRef, useState, type ChangeEvent, type ReactNode } from "react";
import { Button, HashtagTag, Icon } from "@/components/ds";
import { Eyebrow } from "@/components/studio/ui";
import { useStudio } from "./useStudio";
import { computeChecks, scoreOf } from "./rubric";
import { QUICK_EMOJI, TITLE_FORMULAS, type VersionId } from "./types";
import { CopyDoctor, EmptyComposer, RiskPanel, ScheduleBar, VisualStudio } from "./Composer";
import { EvidenceChips } from "./CreationScreen";
import { Drawer } from "./Drawer";

const quickEmoji = QUICK_EMOJI;

// 单值工具态:同一时刻只开一个抽屉(DEV-SPEC §4.5「tool 单值状态」)。
type Tool = null | "versions" | "outline" | "evidence" | "doctor" | "risk" | "title" | "process";

export function DeepEditor() {
  const { note, actions } = useStudio();
  const [tool, setTool] = useState<Tool>(null);
  const [showImages, setShowImages] = useState(false); // 配图区默认折叠:写作优先(对齐原型 DEV-SPEC §4.5)
  const bodyRef = useRef<HTMLTextAreaElement>(null);
  const checks = computeChecks(note);
  const score = scoreOf(checks);
  const remaining = checks.filter((c) => !c.pass).length;
  const inlineTodo = checks.filter((c) => !c.pass && (c.group === "正文" || c.group === "标题"));
  const writing = note.status === "writing";
  const body = note.body || "";
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
  const outlineDone = outline.filter((o) => o.ok).length;
  const versionIds = note.versions ? (["A", "B", "C"] as VersionId[]).filter((id) => note.versions?.[id]) : [];
  const evidenceCount = note.topicId != null ? undefined : undefined; // 依据角标由 EvidenceChips 自身守卫,这里只标"有/无"
  void evidenceCount;
  const riskText = (note.title || "") + (note.body || "");
  const riskCount = [
    /http|www\.|公众号|微信|加我|私信|vx|v信|留链|主页链接/i,
    /最佳|最好|第一名|国家级|绝对|100%|顶级|纯天然|永久/,
    /医美|减肥|瘦身|药效|代购|烟|酒精/,
  ].filter((re) => re.test(riskText)).length;

  return (
    <div className="pane-in" style={{ flex: 1, minHeight: 0, display: "flex", flexDirection: "column", background: "var(--background)" }}>
      {/* ── 顶部工具按钮条:点开右侧抽屉,按钮带实时角标 ── */}
      <div style={{ flexShrink: 0, display: "flex", flexWrap: "wrap", alignItems: "center", gap: 6, padding: "9px 16px", borderBottom: "1px solid var(--border)", background: "var(--surface-card)" }}>
        <ToolBtn icon="layers" label="版本" active={tool === "versions"} badge={note.versions ? note.activeVersion : undefined} onClick={() => setTool(tool === "versions" ? null : "versions")} />
        <ToolBtn icon="list-checks" label="大纲" active={tool === "outline"} badge={`${outlineDone}/${outline.length}`} onClick={() => setTool(tool === "outline" ? null : "outline")} />
        <ToolBtn icon="database" label="依据" active={tool === "evidence"} onClick={() => setTool(tool === "evidence" ? null : "evidence")} />
        <ToolBtn icon="stethoscope" label="文案体检" active={tool === "doctor"} badge={String(score)} badgeTone={score >= 80 ? "success" : "warning"} onClick={() => setTool(tool === "doctor" ? null : "doctor")} />
        <ToolBtn icon="shield-check" label="风控" active={tool === "risk"} badge={riskCount ? String(riskCount) : undefined} badgeTone="warning" onClick={() => setTool(tool === "risk" ? null : "risk")} />
        <ToolBtn icon="wand-2" label="标题优化" active={tool === "title"} onClick={() => setTool(tool === "title" ? null : "title")} />
        {note.process && <ToolBtn icon="history" label="创作过程" active={tool === "process"} onClick={() => setTool(tool === "process" ? null : "process")} />}
        {/* 右侧总览:生成中显示脉冲,否则显示全量达标进度(对齐原型工具条右端「还差 N 项达标」)。 */}
        {writing ? (
          <span style={{ marginLeft: "auto", display: "inline-flex", alignItems: "center", gap: 6, fontSize: 11, color: "var(--primary)", fontWeight: 700 }}>
            <span className="pulse-dot" style={{ width: 7, height: 7, borderRadius: 999, background: "var(--primary)" }} /> 生成中
          </span>
        ) : (
          <span style={{ marginLeft: "auto", flexShrink: 0, fontSize: 10, color: remaining === 0 ? "var(--success)" : "var(--text-subtle)", fontWeight: remaining === 0 ? 700 : 400, whiteSpace: "nowrap" }}>
            {remaining === 0 ? "全部达标" : `还差 ${remaining} 项达标`}
          </span>
        )}
      </div>

      {/* ── 单列写作画布 ── */}
      <div className="cs" style={{ flex: 1, minWidth: 0, overflowY: "auto", display: "flex", justifyContent: "center", padding: "18px 24px" }}>
        <div style={{ width: 640, maxWidth: "100%", display: "flex", flexDirection: "column", gap: 14 }}>
          {!note.title && !body ? <EmptyComposer /> : null}
          {/* 配图区默认折叠(写作优先);点标题展开图集 —— 对齐原型「写完文案再配图·点击展开」。
              折叠头常驻,展开后才渲染 VisualStudio(内部按真实 images 守卫,无图不造假占位)。 */}
          <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
            <button onClick={() => setShowImages((v) => !v)} style={{ display: "flex", alignItems: "center", justifyContent: "space-between", width: "100%", background: "none", border: "none", padding: 0, cursor: "pointer", textAlign: "left" }}>
              <span style={{ display: "inline-flex", alignItems: "center", gap: 6 }}>
                <span style={{ color: "var(--text-subtle)", display: "inline-flex", transform: showImages ? "rotate(90deg)" : "none", transition: "transform var(--dur-fast) var(--ease-out)" }}><Icon name="chevron-right" size={13} /></span>
                <Eyebrow>封面 + 图集 · 3:4（1080×1440）</Eyebrow>
              </span>
              <span style={{ fontSize: 9, color: "var(--text-subtle)" }}>{showImages ? "封面决定点击率" : "写完文案再配图 · 点击展开"}</span>
            </button>
            {showImages && <VisualStudio />}
          </div>
          {/* 标题 */}
          <div style={{ display: "flex", flexDirection: "column", gap: 5 }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
              <Eyebrow>标题 · 钩子优先</Eyebrow>
              <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                <button data-testid="optimize-title" onClick={() => setTool("title")} disabled={writing} style={{ display: "inline-flex", alignItems: "center", gap: 4, background: "none", border: "none", cursor: writing ? "default" : "pointer", color: "var(--primary)", fontSize: 11, fontWeight: 600, opacity: writing ? 0.5 : 1 }}>
                  <Icon name="wand-2" size={12} /> 优化标题
                </button>
                <span className="font-tabular" style={{ fontSize: 10, color: note.title.length > 20 ? "var(--warning)" : "var(--text-subtle)" }}>{note.title.length} / 20</span>
              </div>
            </div>
            <input value={note.title} onChange={(e: ChangeEvent<HTMLInputElement>) => actions.updateField("title", e.target.value)} placeholder="写个钩子标题…" style={{ border: "none", borderBottom: "2px solid var(--border)", background: "transparent", fontFamily: "var(--font-display)", fontWeight: 800, fontSize: "var(--text-xl)", color: "var(--text-body)", padding: "4px 0", outline: "none", letterSpacing: "var(--tracking-tight)" }} />
          </div>
          {/* 正文工具条(吸顶) */}
          <div style={{ position: "sticky", top: 0, zIndex: 1, display: "flex", flexWrap: "wrap", alignItems: "center", gap: 6, padding: "8px 0", background: "var(--background)", borderBottom: "1px solid var(--border)" }}>
            <Button variant="soft" size="sm" leftIcon={<Icon name="sparkles" size={12} />} onClick={actions.polish} disabled={writing}>润色</Button>
            <Button variant="soft" size="sm" leftIcon={<Icon name="scissors" size={12} />} onClick={actions.shorten} disabled={writing}>瘦身</Button>
            <Button variant="soft" size="sm" leftIcon={<Icon name="hash" size={12} />} onClick={actions.addTags} disabled={writing}>配标签</Button>
            <span style={{ width: 1, height: 18, background: "var(--border)", margin: "0 3px" }} />
            {quickEmoji.slice(0, 8).map((e) => <button key={e} onClick={() => insertEmoji(e)} disabled={writing} style={{ border: "none", background: "transparent", cursor: "pointer", fontSize: 16, lineHeight: 1, padding: 1, opacity: writing ? 0.4 : 1 }}>{e}</button>)}
            {writing ? (
              <Button variant="secondary" size="sm" style={{ marginLeft: "auto" }} leftIcon={<Icon name="circle" size={12} />} onClick={() => actions.stop()}>停止生成</Button>
            ) : (
              <span style={{ marginLeft: "auto", fontSize: 10, color: body.length > 1000 ? "var(--warning)" : "var(--text-subtle)" }} className="font-tabular">{`${body.length} / 1000`}</span>
            )}
          </div>
          {/* 正文 */}
          <textarea data-testid="draft-body" ref={bodyRef} value={writing ? body + " ▍" : body} onChange={(e: ChangeEvent<HTMLTextAreaElement>) => actions.updateField("body", e.target.value)} readOnly={writing} placeholder="正文从一句共情钩子开始，再用 1️⃣2️⃣3️⃣ 分点干货，最后引导互动…" style={{ border: "none", background: "transparent", resize: "none", minHeight: 320, fontFamily: "var(--font-sans)", fontSize: "var(--text-sm)", lineHeight: "var(--leading-relaxed)", color: "var(--text-body)", outline: "none" }} />
          {/* 正文内联体检:就近显示未通过的标题/正文项("边写边看");全通过显示达标态。
              「文案体检」抽屉是全量总览,二者同源不同位。 */}
          {!writing && (
            inlineTodo.length === 0 ? (
              <div data-testid="inline-check-ok" style={{ display: "inline-flex", alignItems: "center", gap: 6, fontSize: 11, color: "var(--success)", background: "var(--success-surface)", borderRadius: "var(--radius-sm)", padding: "6px 10px", alignSelf: "flex-start" }}>
                <Icon name="check-circle-2" size={13} /> 正文各项已达标
              </div>
            ) : (
              <div data-testid="inline-check-todo" style={{ display: "flex", flexWrap: "wrap", alignItems: "center", gap: 6, padding: "8px 10px", background: "var(--warning-surface)", borderRadius: "var(--radius-sm)" }}>
                <span style={{ fontSize: 11, fontWeight: 700, color: "var(--warning)" }}>还差 {inlineTodo.length} 项:</span>
                {inlineTodo.map((c) => (
                  <span key={c.key} title={c.hint} style={{ display: "inline-flex", alignItems: "center", gap: 4, fontSize: 10, color: "var(--text-body)", background: "var(--surface-card)", border: "1px solid var(--border)", borderRadius: 999, padding: "2px 8px" }}>
                    <Icon name="alert-circle" size={11} color="var(--warning)" /> {c.label}
                  </span>
                ))}
              </div>
            )
          )}
          {/* 话题标签 */}
          <div style={{ display: "flex", flexDirection: "column", gap: 8, borderTop: "1px solid var(--border)", paddingTop: 14 }}>
            <Eyebrow>话题标签 · {note.tags.length} 个（建议 5–10，大词+长尾）</Eyebrow>
            <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
              {note.tags.map((t) => <span key={t} onClick={() => actions.removeTag(t)} style={{ cursor: "pointer" }} title="点击移除"><HashtagTag>{t}</HashtagTag></span>)}
              {note.tags.length === 0 && <span style={{ fontSize: 11, color: "var(--text-subtle)" }}>暂无，点上方「配标签」让 AI 基于正文生成</span>}
            </div>
            {kwSuggestions.length > 0 && (
              <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
                <span style={{ fontSize: 10, color: "var(--text-subtle)", alignSelf: "center" }}>选题关键词：</span>
                {kwSuggestions.map((t) => <HashtagTag key={t} addable onAdd={() => actions.addTag(t)}>{t}</HashtagTag>)}
              </div>
            )}
          </div>
        </div>
      </div>

      {/* ── 底部定稿区常驻(唯一不收进抽屉的出口动作) ── */}
      <div style={{ flexShrink: 0, borderTop: "1px solid var(--border)", background: "var(--surface-card)", padding: "10px 24px" }}>
        <ScheduleBar score={score} status={note.status} remaining={remaining} />
      </div>

      {/* ── 工具抽屉(同一时刻只开一个) ── */}
      <Drawer open={tool === "versions"} onClose={() => setTool(null)} title="草稿版本" icon="layers">
        <VersionsDrawerBody ids={versionIds} />
      </Drawer>
      <Drawer open={tool === "outline"} onClose={() => setTool(null)} title="创作大纲" icon="list-checks">
        <OutlineDrawerBody outline={outline} onFocusBody={() => { const el = bodyRef.current; if (el) { el.focus(); el.scrollIntoView({ block: "center", behavior: "smooth" }); } }} />
      </Drawer>
      <Drawer open={tool === "evidence"} onClose={() => setTool(null)} title="创作依据" icon="database">
        <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
          <span style={{ fontSize: 11, color: "var(--text-muted)", lineHeight: 1.6 }}>本篇对标的数据底座依据(点开看相关度分析)。</span>
          <EvidenceChips topicId={note.topicId} />
        </div>
      </Drawer>
      <Drawer open={tool === "doctor"} onClose={() => setTool(null)} title="文案体检 · 全量" icon="stethoscope" width={380}>
        <CopyDoctor checks={checks} score={score} />
      </Drawer>
      <Drawer open={tool === "risk"} onClose={() => setTool(null)} title="限流风控" icon="shield-check">
        <RiskPanel note={note} />
      </Drawer>
      <Drawer open={tool === "title"} onClose={() => setTool(null)} title="标题优化" icon="wand-2" width={400}>
        <TitleToolBody onDone={() => setTool(null)} />
      </Drawer>
      <Drawer open={tool === "process"} onClose={() => setTool(null)} title="创作过程" icon="history" width={400}>
        <ProcessDrawerBody />
      </Drawer>
    </div>
  );
}

// ── 顶部工具按钮 ──
function ToolBtn({ icon, label, active, badge, badgeTone = "primary", onClick }: { icon: string; label: string; active: boolean; badge?: string; badgeTone?: "primary" | "success" | "warning"; onClick: () => void }) {
  const badgeColor = { primary: "var(--primary)", success: "var(--success)", warning: "var(--warning)" }[badgeTone];
  const badgeBg = { primary: "var(--accent-surface)", success: "var(--success-surface)", warning: "var(--warning-surface)" }[badgeTone];
  return (
    <button onClick={onClick} style={{ display: "inline-flex", alignItems: "center", gap: 5, padding: "5px 10px", borderRadius: "var(--radius-sm)", cursor: "pointer", border: `1px solid ${active ? "var(--primary)" : "var(--border)"}`, background: active ? "var(--accent-surface)" : "var(--surface-card)", color: active ? "var(--primary)" : "var(--text-body)", fontSize: "var(--text-xs)", fontWeight: active ? 700 : 500, whiteSpace: "nowrap" }}>
      <Icon name={icon} size={13} color={active ? "var(--primary)" : "var(--text-muted)"} /> {label}
      {badge != null && <span className="font-tabular" style={{ fontSize: 9, fontWeight: 700, color: badgeColor, background: badgeBg, borderRadius: 999, padding: "0 5px", lineHeight: 1.6 }}>{badge}</span>}
    </button>
  );
}

// ── 版本抽屉:A/B/C 列表点选即切换(收纳原 v1 左栏草稿版本区 + 并排对比屏的能力) ──
function VersionsDrawerBody({ ids }: { ids: VersionId[] }) {
  const { note, actions, copyLifecycle, copyLifecycleStatus } = useStudio();
  if (!note.versions || ids.length === 0) {
    return (
      <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
        <span style={{ fontSize: "var(--text-xs)", color: "var(--text-muted)", lineHeight: 1.7 }}>当前只有单版草稿。让 🍠 再写一版不同角度的,即可在这里切换对比。</span>
        <Button variant="primary" size="sm" leftIcon={<Icon name="sparkles" size={13} />} onClick={() => actions.say("请基于当前选题再写一版不同角度的文案作为 B 版,和现有这版做对比;用 xhs_copy 的 versions 数组同时输出这两版。")}>让🍠再生成一版</Button>
      </div>
    );
  }
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
      {ids.map((id) => {
        const v = note.versions![id]!;
        const on = note.activeVersion === id;
        const adopted = v.resourceVersion != null && copyLifecycle?.adoptedVersion === v.resourceVersion;
        const canAdopt = Boolean(note.resourceId && v.resourceVersion && copyLifecycle && copyLifecycleStatus === "ready");
        const sc = scoreOf(computeChecks({ ...note, title: v.title, body: v.body, tags: v.tags, cover: v.cover }));
        return (
          <div key={id} style={{ display: "flex", flexDirection: "column", gap: 7, padding: "10px 11px", borderRadius: "var(--radius-md)", border: `1px solid ${on ? "var(--primary)" : "var(--border)"}`, background: on ? "var(--accent-surface)" : "var(--surface-card)" }}>
            <button data-testid={`version-${id}`} onClick={() => actions.setVersion(id)} style={{ display: "flex", alignItems: "flex-start", gap: 9, textAlign: "left", padding: 0, border: "none", cursor: "pointer", background: "transparent" }}>
              <span style={{ width: 22, height: 22, borderRadius: 6, background: on ? "var(--primary)" : "var(--oats-dark)", color: on ? "#fff" : "var(--text-muted)", fontSize: 11, fontWeight: 800, display: "inline-flex", alignItems: "center", justifyContent: "center", flexShrink: 0, fontFamily: "var(--font-display)" }}>{id}</span>
              <span style={{ flex: 1, minWidth: 0 }}>
                <span style={{ display: "flex", alignItems: "center", gap: 6 }}>
                  <span style={{ fontSize: 12, fontWeight: 700, color: on ? "var(--primary)" : "var(--text-body)" }}>{v.label.replace(/^版本\s*/, "")}</span>
                  <span style={{ marginLeft: "auto", fontSize: 10, fontWeight: 700, color: sc >= 80 ? "var(--success)" : "var(--warning)" }}>{sc} 分</span>
                  {on && <span style={{ fontSize: 9, color: "var(--primary)", fontWeight: 700, background: "var(--surface-card)", padding: "1px 6px", borderRadius: 999 }}>当前</span>}
                </span>
                <span style={{ display: "block", fontSize: 11, color: "var(--text-muted)", marginTop: 3, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{v.title || "(无标题)"}</span>
              </span>
            </button>
            <div style={{ display: "flex", alignItems: "center", gap: 7, paddingLeft: 31 }}>
              <span className="font-tabular" style={{ flex: 1, fontSize: 9, color: v.resourceVersion ? "var(--text-subtle)" : "var(--warning)" }}>
                {v.resourceVersion ? `不可变版本 v${v.resourceVersion}` : "旧稿缺少精确版本"}
              </span>
              <Button
                variant={adopted ? "secondary" : "primary"}
                size="sm"
                leftIcon={<Icon name={adopted ? "check-circle-2" : "check"} size={11} />}
                disabled={!canAdopt || adopted}
                onClick={() => actions.adoptVersion(id)}
              >
                {adopted ? "已采用" : "采用此版本"}
              </Button>
            </div>
          </div>
        );
      })}
    </div>
  );
}

// ── 大纲抽屉:结构完成度 + 点击聚焦正文(替代原 v1 左栏创作大纲) ──
function OutlineDrawerBody({ outline, onFocusBody }: { outline: { k: string; ok: boolean }[]; onFocusBody: () => void }) {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 9 }}>
      {outline.map((o) => (
        <button key={o.k} onClick={onFocusBody} title="点此聚焦正文编辑区" style={{ display: "flex", alignItems: "center", gap: 8, fontSize: "var(--text-xs)", color: o.ok ? "var(--text-body)" : "var(--text-subtle)", background: "none", border: "none", padding: "4px 0", cursor: "pointer", textAlign: "left" }}>
          <Icon name={o.ok ? "check-circle-2" : "circle"} size={15} color={o.ok ? "var(--success)" : "var(--border-strong)"} />
          {o.k}
        </button>
      ))}
    </div>
  );
}

// ── 标题优化抽屉(收纳原 v1 整屏标题优化能力):公式选择 → LLM 出候选 → 可编辑 → 采用写回 ──
function TitleToolBody({ onDone }: { onDone: () => void }): ReactNode {
  const { note, actions, titleSuggestions } = useStudio();
  const [formula, setFormula] = useState<string | null>(null);
  const [drafts, setDrafts] = useState<Record<number, string>>({});
  const generating = note.status === "writing";
  const candidates = titleSuggestions && (!formula || titleSuggestions.formula === formula) ? titleSuggestions.candidates : [];

  const pickFormula = (name: string) => {
    setFormula(name);
    setDrafts({});
    const kw = note.kw ? `,核心词「${note.kw}」` : "";
    const base = note.title ? `现有标题《${note.title}》` : "还没有标题";
    actions.say(`用「${name}」这个标题公式,给我出 5 个小红书标题候选。${base}${kw}。每个都要 ≤20 字、有点击欲。只用 xhs_titles 代码块返回候选,不要别的话。`);
  };

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
      {/* 当前标题回显 + n/20 */}
      <div style={{ display: "flex", alignItems: "center", gap: 8, fontSize: 11, color: "var(--text-muted)", background: "var(--oats-light)", borderRadius: "var(--radius-sm)", padding: "8px 10px" }}>
        <span style={{ flex: 1, minWidth: 0, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{note.title || "还没有标题"}</span>
        <span className="font-tabular" style={{ color: note.title.length > 20 ? "var(--warning)" : "var(--text-subtle)" }}>{note.title.length}/20</span>
      </div>
      {/* 公式横向选择条 */}
      <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
        {TITLE_FORMULAS.map((f) => {
          const on = formula === f.name;
          return (
            <button key={f.name} onClick={() => pickFormula(f.name)} disabled={generating} title={f.hint} style={{ padding: "5px 10px", borderRadius: "var(--radius-full)", cursor: generating ? "default" : "pointer", border: `1px solid ${on ? "var(--primary)" : "var(--border)"}`, background: on ? "var(--accent-surface)" : "var(--surface-card)", color: on ? "var(--primary)" : "var(--text-body)", fontSize: 11, fontWeight: on ? 700 : 500, opacity: generating && !on ? 0.6 : 1 }}>{f.name}</button>
          );
        })}
      </div>
      {/* 候选(可编辑 + 独立字数校验 + 采用) */}
      {!formula ? (
        <div style={{ textAlign: "center", color: "var(--text-subtle)", fontSize: "var(--text-xs)", padding: "28px 12px", lineHeight: 1.7 }}>
          <div style={{ fontSize: 26, marginBottom: 6 }}>✍️</div>
          选一个标题公式,🍠 会按它的套路给你出几个候选。
        </div>
      ) : generating && candidates.length === 0 ? (
        <div style={{ display: "flex", alignItems: "center", gap: 8, color: "var(--text-muted)", fontSize: "var(--text-xs)", padding: "24px 0", justifyContent: "center" }}>
          <Icon name="loader" size={14} color="var(--primary)" /> 正在按「{formula}」生成候选…
        </div>
      ) : candidates.length === 0 ? (
        <div style={{ textAlign: "center", color: "var(--text-subtle)", fontSize: "var(--text-xs)", padding: "24px 12px" }}>还没拿到候选,可再点一次公式重试。</div>
      ) : (
        <>
          <Eyebrow>「{formula}」候选 · 可改后采用</Eyebrow>
          {candidates.map((c, i) => {
            const val = drafts[i] ?? c;
            const over = val.length > 20;
            return (
              <div key={i} style={{ background: "var(--surface-card)", border: "1px solid var(--border)", borderRadius: "var(--radius-md)", padding: 10, display: "flex", flexDirection: "column", gap: 7 }}>
                <textarea value={val} onChange={(e) => setDrafts((d) => ({ ...d, [i]: e.target.value }))} rows={2} style={{ border: "none", background: "transparent", resize: "none", fontFamily: "var(--font-display)", fontWeight: 700, fontSize: "var(--text-sm)", lineHeight: 1.35, color: "var(--text-body)", outline: "none" }} />
                <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
                  <span className="font-tabular" style={{ fontSize: 10, color: over ? "var(--warning)" : "var(--text-subtle)" }}>{val.length}/20{over ? " · 偏长" : ""}</span>
                  <Button variant="primary" size="sm" leftIcon={<Icon name="check" size={12} />} onClick={() => { actions.updateField("title", val); actions.toast("✅ 已采用为标题"); onDone(); }}>采用这条</Button>
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
  );
}

// ── 创作过程抽屉:大纲对标依据 + 去 AI 腔自审纠偏(从 note.process 解析) ──
function ProcessDrawerBody(): ReactNode {
  const { note } = useStudio();
  const p = note.process;
  const empty = !p || (!p.outline && !p.audit);
  if (empty) {
    return (
      <div style={{ textAlign: "center", color: "var(--text-muted)", fontSize: "var(--text-xs)", padding: "36px 16px", lineHeight: 1.7 }}>
        <div style={{ fontSize: 28, marginBottom: 8 }}>🗂️</div>
        本版没有可回看的创作过程记录。
        <div style={{ fontSize: 11, color: "var(--text-subtle)", marginTop: 6 }}>委派 🍠 写文案时会带对标依据与自审纠偏记录;直接手写或旧会话的文案可能没有。</div>
      </div>
    );
  }
  return (
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
  );
}
