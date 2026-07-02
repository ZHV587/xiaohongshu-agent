"use client";

// 创作 screen — recents · chat · right panel (选题卡 + 创作栏).
// CreationScreen 固定走默认「上下堆叠」结构（无 rightLayout 变体）。

import { useEffect, useRef, useState, type CSSProperties } from "react";
import { Avatar, Badge, Button, Card, TopicCard, ThinkingAura, Textarea, Icon } from "@/components/ds";
import { Eyebrow, PanelHead } from "@/components/studio/ui";
import { useStudio } from "@/components/studio/StudioContext";
import { Recents } from "./Shell";
import type { Topic } from "@/components/studio/types";

export function CreationScreen() {
  const { note, actions } = useStudio();
  const [detailId, setDetailId] = useState<number | null>(null);
  return (
    <div style={{ flex: 1, display: "flex", minHeight: 0 }}>
      <Recents onNew={() => { setDetailId(null); actions.newChat(); }} compact />
      <ChatColumn showTopics={false} />
      <section style={{ width: 400, borderLeft: "1px solid var(--border)", background: "var(--surface-card)", display: "flex", flexDirection: "column", flexShrink: 0, boxShadow: "var(--shadow-lg)" }}>
        <div className="cs" style={{ flex: 1, overflowY: "auto", padding: 16 }}>
          {detailId
            ? <TopicDetail topicId={detailId} onBack={() => setDetailId(null)} />
            : <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
                <TopicRail orientation="vertical" chosen={note.topicId} onChoose={(t) => setDetailId(t.id)} />
                <div style={{ fontSize: 11, color: "var(--text-subtle)", textAlign: "center", lineHeight: 1.6, padding: "6px 8px", background: "var(--oats-light)", borderRadius: "var(--radius-sm)" }}>点选题卡看详情 → 再进入<b style={{ color: "var(--primary)" }}>深度创作</b></div>
              </div>}
        </div>
      </section>
    </div>
  );
}

// 选题卡 rail
function TopicRail({ orientation, chosen, onChoose }: { orientation: "horizontal" | "vertical"; chosen: number | null; onChoose: (t: Topic) => void }) {
  const { topics, evidence, images, actions } = useStudio();
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 9 }}>
      <PanelHead icon="lightbulb" title="选题卡" sub="数据底座检索 · 加权排序 · 点击进入创作" right={<Button variant="ghost" size="sm" leftIcon={<Icon name="refresh-cw" size={12} />} onClick={() => actions.say("再换一批不同角度的选题")}>换一批</Button>} />
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10 }}>
        {topics.map((t) => {
          const on = t.id === chosen;
          const evCount = (evidence[t.id] || { items: [] }).items.length;
          return (
            <div key={t.id} data-testid="topic-card" onClick={() => onChoose(t)} className="lift pop-in" style={{
              borderRadius: "var(--radius-md)", overflow: "hidden", cursor: "pointer",
              border: `1px solid ${on ? "var(--primary)" : "var(--border)"}`, background: "var(--surface-card)",
              boxShadow: on ? "var(--shadow-md)" : "var(--shadow-xs)", display: "flex", flexDirection: "column" }}>
              <div style={{ position: "relative", width: "100%", aspectRatio: "3 / 4", overflow: "hidden", background: "var(--accent-surface)" }}>
                {images.length > 0 && <img src={images[(t.id - 1) % images.length]} alt={t.title} style={{ width: "100%", height: "100%", objectFit: "cover" }} />}
                <div style={{ position: "absolute", inset: 0, background: "linear-gradient(180deg, rgba(0,0,0,0) 58%, rgba(0,0,0,0.42))" }} />
                <span style={{ position: "absolute", top: 7, left: 7, fontSize: 8, fontWeight: 700, color: "#fff", background: "rgba(0,0,0,0.36)", padding: "2px 7px", borderRadius: 999 }}>{t.angle}</span>
                {t.hotRate != null && <span data-testid="topic-hot" style={{ position: "absolute", top: 7, right: 7, fontSize: 9, fontWeight: 800, color: "#fff", background: "var(--coral-500)", padding: "2px 6px", borderRadius: 999 }}>🔥{t.hotRate}</span>}
                {on && <span style={{ position: "absolute", bottom: 7, right: 7, display: "inline-flex", alignItems: "center", gap: 2, fontSize: 8, fontWeight: 700, color: "var(--primary)", background: "#fff", padding: "2px 6px", borderRadius: 999 }}><Icon name="check" size={9} /> 已选</span>}
              </div>
              <div style={{ padding: "8px 9px", display: "flex", flexDirection: "column", gap: 5 }}>
                <div style={{ fontSize: 11, fontWeight: 700, color: "var(--text-body)", lineHeight: 1.35, display: "-webkit-box", WebkitLineClamp: 2, WebkitBoxOrient: "vertical", overflow: "hidden" }}>{t.title}</div>
                <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", fontSize: 9, color: "var(--text-subtle)" }}>
                  <span>{t.rationale.split(" · ")[0]}</span>
                  <span style={{ display: "inline-flex", alignItems: "center", gap: 3 }}><Icon name="database" size={9} /> 依据 {evCount}</span>
                </div>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

// Center chat column — base proposal + dynamic store messages
function ChatColumn({ showTopics }: { showTopics: boolean }) {
  const { topics, timeline, trends, actions } = useStudio();
  const [draft, setDraft] = useState("");
  const scrollRef = useRef<HTMLDivElement>(null);
  const lastRunSteps = (() => {
    for (let i = timeline.length - 1; i >= 0; i--) {
      const it = timeline[i];
      if (it.kind === "thinking") return it.run.steps.length;
    }
    return 0;
  })();
  useEffect(() => {
    const el = scrollRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [timeline.length, lastRunSteps]);

  return (
    <section style={{ flex: 1, display: "flex", flexDirection: "column", background: "var(--background)", minWidth: 0 }}>
      <div ref={scrollRef} className="cs" style={{ flex: 1, overflowY: "auto", padding: 22, display: "flex", flexDirection: "column", gap: 18 }}>
        {/* 真实数据铁律:聊天区只渲染真实 stream 派生的消息(timeline);无消息=空会话,显示欢迎引导,不 mock 假对话。 */}
        {timeline.length === 0 && (
          <div style={{ margin: "auto", maxWidth: 460, textAlign: "center", display: "flex", flexDirection: "column", gap: 12, color: "var(--text-muted)" }}>
            <Avatar glyph="🍠" variant="agent" size={44} />
            <div style={{ fontFamily: "var(--font-display)", fontWeight: 800, fontSize: "var(--text-lg)", color: "var(--text-body)" }}>开始一场创作对话</div>
            <p style={{ margin: 0, fontSize: "var(--text-sm)", lineHeight: "var(--leading-relaxed)" }}>
              说出你的方向(如「按露营装备出选题」),🍠 会基于数据底座检索爆款、提炼带「创作依据」的选题卡,点任意一张进入深度创作。
            </p>
          </div>
        )}

        {/* 动态消息(来自真实 LangGraph 流) */}
        {timeline.map((item, i) => {
          const key = `${item.kind}-${i}`;
          if (item.kind === "user") {
            return (
              <div key={key} style={{ display: "flex", gap: 11, maxWidth: "86%", alignSelf: "flex-end", flexDirection: "row-reverse" }}>
                <Avatar name="我" variant="solid" size={30} />
                <div style={{ background: "var(--surface-card)", border: "1px solid var(--border-coral)", borderRadius: "var(--radius-xl)", padding: "11px 15px", fontSize: "var(--text-sm)", boxShadow: "var(--shadow-sm)" }}>{item.text}</div>
              </div>
            );
          }
          if (item.kind === "thinking") {
            return (
              <div key={key} style={{ display: "flex", gap: 11, maxWidth: "92%" }}>
                <Avatar glyph="🍠" variant="agent" size={32} />
                <div style={{ flex: 1, maxWidth: 440 }}>
                  <ThinkingAura
                    steps={item.run.steps}
                    logs={item.run.logs.length ? item.run.logs : null}
                    defaultCollapsed={item.run.done}
                  />
                </div>
              </div>
            );
          }
          // item.kind === "ai"
          return (
            <div key={key} style={{ display: "flex", gap: 11, maxWidth: "92%" }}>
              <Avatar glyph="🍠" variant="agent" size={32} />
              <div style={{ background: "var(--surface-card)", border: "1px solid var(--border-coral)", borderRadius: "var(--radius-xl)", padding: "11px 15px", fontSize: "var(--text-sm)", lineHeight: "var(--leading-relaxed)", boxShadow: "var(--shadow-sm)", alignSelf: "flex-start" }}>{item.text}</div>
            </div>
          );
        })}

        {/* 选题卡:仅当真实产出选题时,在助手气泡内渲染(showTopics 布局下);无选题不显示 */}
        {showTopics && topics.length > 0 && (
          <div style={{ display: "flex", gap: 11, maxWidth: "92%" }}>
            <Avatar glyph="🍠" variant="agent" size={32} />
            <Card padding="md">
              <p style={{ margin: 0, fontSize: "var(--text-sm)", lineHeight: "var(--leading-relaxed)" }}>基于数据底座检索到的爆款资源,提炼了以下方向,每个都附「创作依据」,点击卡片进入创作:</p>
              <div style={{ display: "flex", flexDirection: "column", gap: 9, marginTop: 11 }}>
                {topics.map((t) => <TopicCard key={t.id} index={t.id} title={t.title} rationale={t.rationale} hotRate={t.hotRate} onClick={() => actions.chooseTopic(t)} />)}
              </div>
            </Card>
          </div>
        )}

        {/* 热点趋势雷达:仅当有真实趋势数据时显示 */}
        {trends.length > 0 && (
          <div style={{ display: "flex", gap: 11, maxWidth: "92%" }}>
            <Avatar glyph="🍠" variant="agent" size={32} />
            <div style={{ flex: 1, minWidth: 0 }}><TrendRadar /></div>
          </div>
        )}
      </div>

      <div style={{ padding: 18, borderTop: "1px solid var(--border)", flexShrink: 0 }}>
        <div style={{ maxWidth: 720, margin: "0 auto" }}>
          <Textarea rows={2} value={draft} onChange={(e) => setDraft(e.target.value)} placeholder="继续追问，或让 🍠 调整选题方向 / 改写文案…" footer={<>
            <button onClick={() => actions.polish()} style={{ display: "inline-flex", alignItems: "center", gap: 6, background: "var(--surface-card)", border: "1px solid var(--border)", borderRadius: "var(--radius-sm)", padding: "5px 9px", cursor: "pointer" }}>
              <kbd style={{ fontSize: 8, background: "var(--oats-light)", border: "1px solid var(--border)", padding: "1px 4px", borderRadius: 4, fontFamily: "var(--font-mono)" }}>Ctrl+P</kbd>
              <span style={{ fontSize: "var(--text-xs)", color: "var(--text-muted)" }}>润色工具箱</span>
            </button>
            <Button variant="primary" size="sm" rightIcon={<Icon name="send" size={14} />} onClick={() => { if (draft.trim()) { actions.say(draft); setDraft(""); } }}>生成</Button>
          </>} />
        </div>
      </div>
    </section>
  );
}

// 选题卡上的「创作依据」chips → 打开依据相关度分析
export function EvidenceChips({ topicId }: { topicId: number | null }) {
  const { evidence, actions } = useStudio();
  const ev = topicId == null ? undefined : (evidence || {})[topicId];
  if (!ev) return null;
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 5, flexWrap: "wrap", paddingTop: 2 }}>
      <span style={{ display: "inline-flex", alignItems: "center", gap: 3, fontSize: 9, color: "var(--text-subtle)" }}><Icon name="database" size={10} /> 依据 {ev.items.length} 条</span>
      {ev.items.map((it) => (
        <button key={it.resource_id} data-testid="evidence-chip" onClick={(e) => { e.stopPropagation(); actions.openEvidence({ ...it, mode: ev.mode }); }} title={it.title}
          style={{ display: "inline-flex", alignItems: "center", gap: 3, fontSize: 9, color: "var(--topicblue-default)", background: "var(--topicblue-light)", border: "1px solid color-mix(in srgb, var(--topicblue-default) 20%, transparent)", borderRadius: 999, padding: "1px 6px", cursor: "pointer" }}>
          {it.type}
        </button>
      ))}
      {ev.mode === "keyword_fallback" && <span style={{ fontSize: 9, color: "var(--warning)" }}>· 关键词兜底</span>}
    </div>
  );
}

// 依据相关度分析 — slide-over，对齐 EvidenceInspector（relevance/freshness/performance + 时效跟踪）
export function EvidencePanel() {
  const { selectedEvidence: e, actions } = useStudio();
  if (!e) return null;
  const modeLabel = ({ semantic: "语义检索 (pgvector)", keyword_fallback: "关键词兜底 (Meilisearch)", insufficient_relevance: "数据不足" } as Record<string, string>)[e.mode] || "检索";
  const card: CSSProperties = { background: "var(--surface-card)", border: "1px solid var(--border)", borderRadius: "var(--radius-md)", padding: 12, boxShadow: "var(--shadow-xs)" };
  const Bar = ({ label, val, color, testid }: { label: string; val: number; color: string; testid?: string }) => (
    <div style={{ display: "flex", flexDirection: "column", gap: 5 }}>
      <div style={{ display: "flex", justifyContent: "space-between", fontSize: 10, color: "var(--text-muted)" }}><span>{label}</span><span data-testid={testid} className="font-tabular" style={{ fontWeight: 600, color: "var(--text-body)" }}>{(val * 100).toFixed(1)}%</span></div>
      <div style={{ height: 6, background: "var(--oats-dark)", borderRadius: 999, overflow: "hidden" }}><div style={{ height: "100%", width: `${val * 100}%`, background: color, transition: "width var(--dur-slow) var(--ease-out)" }} /></div>
    </div>
  );
  return (
    <div onClick={actions.closeEvidence} style={{ position: "fixed", inset: 0, background: "rgba(15,15,16,0.35)", zIndex: 55, display: "flex", justifyContent: "flex-end" }}>
      <div onClick={(ev) => ev.stopPropagation()} className="cs slide-in-right" style={{ width: 380, maxWidth: "92vw", height: "100%", background: "var(--background)", boxShadow: "var(--shadow-2xl)", overflowY: "auto" }}>
        <div style={{ position: "sticky", top: 0, background: "var(--surface-card)", borderBottom: "1px solid var(--border)", padding: "14px 16px", display: "flex", alignItems: "center", justifyContent: "space-between", zIndex: 1 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 7 }}><Icon name="database" size={16} color="var(--primary)" /><span style={{ fontSize: "var(--text-sm)", fontWeight: 700 }}>依据相关度分析</span></div>
          <button data-testid="evidence-panel-close" onClick={actions.closeEvidence} style={{ border: "none", background: "none", cursor: "pointer", color: "var(--text-subtle)", display: "inline-flex" }}><Icon name="x" size={16} /></button>
        </div>
        <div style={{ padding: 16, display: "flex", flexDirection: "column", gap: 14 }}>
          <div style={card}>
            <div style={{ display: "flex", alignItems: "center", gap: 6 }}><Icon name="file-text" size={13} color="var(--primary)" /><span style={{ fontSize: "var(--text-xs)", fontWeight: 700 }}>{e.title}</span></div>
            <p style={{ fontSize: 10, color: "var(--text-muted)", lineHeight: 1.6, margin: "6px 0 0" }}>{e.summary}</p>
            <div style={{ display: "flex", gap: 6, marginTop: 9, alignItems: "center" }}>
              <Badge tone="topic" shape="chip">{e.type}</Badge>
              <Badge tone={e.mode === "keyword_fallback" ? "neutral" : "synced"} shape="chip">{modeLabel}</Badge>
              <span style={{ fontSize: 9, fontFamily: "var(--font-mono)", color: "var(--text-subtle)", marginLeft: "auto" }}>{e.resource_id}</span>
            </div>
          </div>
          <div style={{ background: "var(--accent-surface)", border: "1px solid var(--border-coral)", borderRadius: "var(--radius-md)", padding: 12 }}>
            <div style={{ display: "flex", alignItems: "center", gap: 5, fontSize: 10, fontWeight: 700, color: "var(--primary)" }}><Icon name="sparkles" size={12} /> 推荐理由 why_selected</div>
            <p style={{ fontSize: 10, color: "var(--text-body)", lineHeight: 1.6, margin: "5px 0 0" }}>{e.why_selected}</p>
          </div>
          <div style={card}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", borderBottom: "1px solid var(--border)", paddingBottom: 8, marginBottom: 12 }}><span style={{ fontSize: "var(--text-xs)", fontWeight: 700 }}>综合排序得分</span><span className="font-tabular" style={{ fontFamily: "var(--font-display)", fontWeight: 800, color: "var(--primary)", fontSize: "var(--text-base)" }}>{e.score.toFixed(4)}</span></div>
            <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
              <Bar label="相关度 Relevance" val={e.relevance} color="var(--primary)" testid="evidence-relevance" />
              <Bar label="时效性 Freshness · e⁻⁰·⁰⁵ᵗ" val={e.freshness} color="var(--success)" />
              <Bar label="爆款表现 Engagement · tanh" val={e.performance} color="var(--amber-500)" />
            </div>
          </div>
          <div style={{ ...card, fontSize: 10 }}>
            <div style={{ display: "flex", alignItems: "center", gap: 5, fontWeight: 700, color: "var(--text-muted)", borderBottom: "1px solid var(--border)", paddingBottom: 6, marginBottom: 6 }}><Icon name="history" size={12} /> 时效跟踪</div>
            <div style={{ display: "flex", justifyContent: "space-between", padding: "2px 0" }}><span style={{ color: "var(--text-subtle)" }}>源端更新 source_updated_at</span><span className="font-tabular" style={{ fontWeight: 600 }}>{e.source_updated_at}</span></div>
            <div style={{ display: "flex", justifyContent: "space-between", padding: "2px 0" }}><span style={{ color: "var(--text-subtle)" }}>本地索引 indexed_at</span><span className="font-tabular" style={{ fontWeight: 600 }}>{e.indexed_at}</span></div>
          </div>
        </div>
      </div>
    </div>
  );
}

// 热点趋势雷达 — 外部实时信号（区别于内部历史沉淀），驱动探索型选题
function TrendRadar() {
  const { trends, actions } = useStudio();
  const toneBg: Record<string, string> = { hot: "var(--hot-surface)", coral: "var(--accent-surface)", topic: "var(--topicblue-light)" };
  const toneFg: Record<string, string> = { hot: "var(--hot)", coral: "var(--primary)", topic: "var(--topicblue-default)" };
  return (
    <div style={{ background: "var(--surface-card)", border: "1px solid var(--border-coral)", borderRadius: "var(--radius-lg)", padding: 12, display: "flex", flexDirection: "column", gap: 9, boxShadow: "var(--shadow-sm)" }}>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
        <div style={{ display: "flex", alignItems: "center", gap: 7 }}><Icon name="radar" size={15} color="var(--primary)" /><span style={{ fontSize: "var(--text-xs)", fontWeight: 700 }}>热点趋势雷达</span><span style={{ fontSize: 9, color: "var(--text-subtle)" }}>· 平台实时上升</span></div>
        <span style={{ fontSize: 9, color: "var(--text-subtle)" }}>探索新题材 · 不只追历史</span>
      </div>
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 7 }}>
        {trends.map((t) => (
          <button key={t.tag} data-testid="trend-row" onClick={() => actions.say(`基于热点「${t.tag}」出几个探索性选题`)} style={{ display: "flex", alignItems: "center", gap: 8, padding: "7px 9px", borderRadius: "var(--radius-sm)", border: "1px solid var(--border)", background: "var(--oats-light)", cursor: "pointer", textAlign: "left" }}>
            <span style={{ fontSize: 9, fontWeight: 700, color: toneFg[t.tone], background: toneBg[t.tone], borderRadius: 6, padding: "2px 6px", flexShrink: 0 }}>{t.heat}</span>
            <span style={{ flex: 1, minWidth: 0 }}>
              <span style={{ display: "block", fontSize: "var(--text-xs)", fontWeight: 600, color: "var(--text-body)" }}>#{t.tag}</span>
              <span style={{ display: "block", fontSize: 9, color: "var(--text-subtle)" }}>{t.note}</span>
            </span>
            <span style={{ fontSize: 10, fontWeight: 700, color: "var(--success)", whiteSpace: "nowrap" }}>↑{t.rising}%</span>
          </button>
        ))}
      </div>
    </div>
  );
}

// 选题详情 — 点选题卡先看各类信息，再进入深度创作
function TopicDetail({ topicId, onBack }: { topicId: number; onBack: () => void }) {
  const { topics, evidence, actions } = useStudio();
  const topic = topics.find((t) => t.id === topicId);
  const ev = (evidence || {})[topicId];
  if (!topic) return null;
  return (
    <div className="fade-up" style={{ display: "flex", flexDirection: "column", gap: 14 }}>
      <button onClick={onBack} style={{ alignSelf: "flex-start", display: "inline-flex", alignItems: "center", gap: 4, background: "none", border: "none", cursor: "pointer", color: "var(--text-muted)", fontSize: 11 }}><Icon name="chevron-left" size={13} /> 返回选题</button>
      <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <Badge tone="topic" shape="chip">{topic.angle}</Badge>
          {topic.hotRate != null && <span style={{ fontSize: 11, fontWeight: 700, color: "var(--hot)" }}>🔥 爆款率 {topic.hotRate}%</span>}
        </div>
        <h2 style={{ margin: 0, fontFamily: "var(--font-display)", fontWeight: 800, fontSize: "var(--text-lg)", lineHeight: 1.3 }}>{topic.title}</h2>
        <p style={{ margin: 0, fontSize: "var(--text-xs)", color: "var(--text-muted)", lineHeight: "var(--leading-relaxed)" }}>{topic.rationale}</p>
      </div>
      <div style={{ display: "flex", alignItems: "center", gap: 8, fontSize: 11 }}>
        <span style={{ color: "var(--text-subtle)" }}>核心搜索词</span>
        <span style={{ fontWeight: 600, color: "var(--topicblue-default)", background: "var(--topicblue-light)", borderRadius: 999, padding: "2px 8px" }}>{topic.kw}</span>
        {ev && <span style={{ marginLeft: "auto", fontSize: 10, color: ev.mode === "keyword_fallback" ? "var(--warning)" : "var(--success)" }}>{ev.mode === "semantic" ? "语义命中" : "关键词兑底"}</span>}
      </div>
      <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
        <Eyebrow><span data-testid="detail-evidence-count" data-count={ev ? ev.items.length : 0}>创作依据 · {ev ? ev.items.length : 0} 条（数据底座检索）</span></Eyebrow>
        {ev && ev.mode === "insufficient_relevance" && (
          <div style={{ display: "flex", flexDirection: "column", gap: 4, padding: 10, borderRadius: "var(--radius-md)", border: "1px solid var(--border-coral)", background: "var(--accent-surface)" }}>
            <span style={{ fontSize: 11, fontWeight: 700, color: "var(--primary)" }}>当前数据不足</span>
            {ev.gaps && <span style={{ fontSize: 10, color: "var(--text-muted)", lineHeight: 1.6 }}>{ev.gaps}</span>}
          </div>
        )}
        {ev && ev.items.map((it) => (
          <button key={it.resource_id} data-testid="detail-evidence-item" onClick={() => actions.openEvidence({ ...it, mode: ev.mode })} style={{ textAlign: "left", border: "1px solid var(--border)", borderRadius: "var(--radius-md)", padding: 10, background: "var(--oats-light)", cursor: "pointer", display: "flex", flexDirection: "column", gap: 5 }}>
            <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
              <span style={{ fontSize: 9, fontWeight: 700, color: "var(--topicblue-default)", background: "var(--topicblue-light)", borderRadius: 4, padding: "1px 5px", flexShrink: 0 }}>{it.type}</span>
              <span style={{ fontSize: 11, fontWeight: 600, color: "var(--text-body)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", flex: 1 }}>{it.title}</span>
              <span className="font-tabular" style={{ fontSize: 10, color: "var(--primary)", fontWeight: 700 }}>{it.score.toFixed(2)}</span>
            </div>
            <div style={{ display: "flex", gap: 10, fontSize: 9, color: "var(--text-subtle)" }}>
              <span>相关 {(it.relevance * 100).toFixed(0)}%</span><span>时效 {(it.freshness * 100).toFixed(0)}%</span><span>表现 {(it.performance * 100).toFixed(0)}%</span>
            </div>
          </button>
        ))}
      </div>
      <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
        <Eyebrow>建议结构</Eyebrow>
        <div style={{ fontSize: 11, color: "var(--text-muted)", lineHeight: 1.7 }}>① 共情钩子 → ② 编号清单干货 → ③ 选购 TIPS → ④ 互动收口 + 话题矩阵</div>
      </div>
      <div style={{ position: "sticky", bottom: 0, background: "var(--surface-card)", paddingTop: 10, borderTop: "1px solid var(--border)" }}>
        <Button variant="primary" block leftIcon={<Icon name="feather" size={14} />} onClick={() => actions.chooseTopic(topic, "deep")}>进入深度创作</Button>
      </div>
    </div>
  );
}
