"use client";

// 创作 screen — recents · chat · right panel (选题卡 + 创作栏).

import { useEffect, useRef, useState, type CSSProperties, type KeyboardEvent as ReactKeyboardEvent, type ReactNode } from "react";
import Image from "next/image";
import { Avatar, Badge, Button, Card, ThinkingAura, Textarea, Icon } from "@/components/ds";
import { Eyebrow, PanelHead } from "@/components/studio/ui";
import { useStudio } from "@/components/studio/useStudio";
import { useDismiss } from "@/components/studio/useDismiss";
import { Recents } from "./Shell";
import { DeepEditor } from "./DeepEditor";
import type { Topic } from "@/components/studio/types";
import type { HITLRequest, HITLDecision } from "@/components/thread/ThreadContext";
import { coverProxyUrl } from "@/lib/cover-image";
import type { DiscoveryNote, AdoptionRow } from "@/lib/thinking-trace";

const RESPONSE_LOADING_TEXT = "正在查素材和历史数据";
const RESPONSE_ERROR_TEXT = "响应失败，请稍后重试";

// v2 双栏:左=对话式选题+流式;右=选题起稿后**就地**变正文编辑器(note.status !== "idle"),
// 起稿前是参考素材栏。右栏宽度随态变化——素材栏 400,编辑态放宽到 560 给写作更多空间。
export function CreationScreen() {
  const { actions, editing } = useStudio();
  // editing 来自 store:只由「点选题起稿/仿写」或已产出成品驱动,不再看 note.status/t.isLoading。
  // 纯搜索、出选题时右栏保持「参考素材栏」,点了选题或仿写才切成深度编辑器(修复搜索即弹创作 UI)。
  return (
    <div style={{ flex: 1, display: "flex", minHeight: 0 }}>
      <Recents onNew={() => actions.newChat()} compact />
      <ChatColumn showTopics />
      <section
        style={{
          width: editing ? 560 : 400,
          borderLeft: "1px solid var(--border)",
          background: "var(--surface-card)",
          display: "flex",
          flexDirection: "column",
          flexShrink: 0,
          boxShadow: "var(--shadow-lg)",
          transition: "width var(--dur-slow) var(--ease-out)",
        }}
      >
        {/* 起稿后右栏原地渲染编辑器(生成横幅 + 仿写拆解常驻其上);未起稿是参考素材栏。
            两态间切换带 pane-in 滑入 + 上面的宽度过渡。 */}
        {editing ? (
          <div className="pane-in" style={{ flex: 1, minHeight: 0, display: "flex", flexDirection: "column" }}>
            <GeneratingBanner />
            <ImitationTeardownBanner />
            <DeepEditor />
          </div>
        ) : (
          <div className="pane-in" style={{ flex: 1, minHeight: 0, display: "flex", flexDirection: "column" }}>
            <RefMaterialRail />
          </div>
        )}
      </section>
    </div>
  );
}

// 生成中状态条:note.status==="writing"(真实 stream isLoading 派生)时常驻编辑器顶部。
// 检索取证阶段(正文还没开始流)也显示,让"在不在生成"始终可见;带停止入口。
function GeneratingBanner() {
  const { note, actions, progressLabel } = useStudio();
  if (note.status !== "writing") return null;
  const streaming = Boolean(note.body && note.body.trim());
  const label = streaming ? "正在写正文" : progressLabel ? `正在${progressLabel}` : "正在查素材、拆依据";
  return (
    <div style={{ flexShrink: 0, display: "flex", alignItems: "center", gap: 10, padding: "9px 16px", background: "var(--accent-surface)", borderBottom: "1px solid var(--border-coral)" }}>
      <span className="pulse-dot" style={{ width: 9, height: 9, borderRadius: 999, background: "var(--primary)", flexShrink: 0 }} />
      <span style={{ fontSize: "var(--text-xs)", fontWeight: 700, color: "var(--primary)", display: "inline-flex", alignItems: "center" }}>
        🍠 {label}<span className="typing-dots" aria-hidden />
      </span>
      <span style={{ fontSize: 11, color: "var(--text-muted)" }}>{streaming ? "内容实时出现在下方" : "取证完就开始逐字生成"}</span>
      <button onClick={() => actions.stop()} style={{ marginLeft: "auto", display: "inline-flex", alignItems: "center", gap: 5, background: "var(--surface-card)", border: "1px solid var(--border)", borderRadius: "var(--radius-sm)", padding: "4px 10px", cursor: "pointer", fontSize: 11, color: "var(--text-muted)", fontWeight: 600 }}>
        <Icon name="circle" size={11} /> 停止生成
      </button>
    </div>
  );
}

// 仿写第一段:范本拆解横幅。仅在本会话是仿写(imitation 非空)时显示,可折叠。
// 显性呈现切入角度/痛点/钩子机制/结构节奏(需求 §5:分析必须让用户看得见)。第二段成品走下方编辑器。
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
      <button onClick={() => setOpen((v) => !v)} style={{ width: "100%", display: "flex", alignItems: "center", gap: 8, padding: "10px 16px", background: "none", border: "none", cursor: "pointer", textAlign: "left" }}>
        <Icon name="feather" size={14} color="var(--primary)" />
        <span style={{ fontSize: "var(--text-xs)", fontWeight: 700, color: "var(--primary)" }}>仿写第一段 · 范本套路拆解</span>
        {imitation.referenceTitle && <span style={{ fontSize: 11, color: "var(--text-muted)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", maxWidth: 200 }}>仿自《{imitation.referenceTitle}》</span>}
        <span style={{ marginLeft: "auto", fontSize: 10, color: "var(--text-subtle)" }}>{open ? "收起" : "展开"}</span>
        <Icon name={open ? "chevron-up" : "chevron-down"} size={13} color="var(--text-subtle)" />
      </button>
      {open && (
        <div style={{ padding: "0 16px 12px", display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8 }}>
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

// 右边栏素材工作台 —— 专职展示检索出的参考素材笔记(线上+本地混排),固定可操作(需求 §1/§3)。
// 三个平行动作(需求 §4,彼此无因果):① 批量收录(勾选框+底部主按钮)② 单张仿写(卡上按钮)。
// 出选题不在此(智能体独立行为,结果进对话)。已收录卡:显示"已收录"、勾选禁用、仿写仍可点。
function RefMaterialRail() {
  const { materials, actions, note } = useStudio();
  const [picked, setPicked] = useState<Record<string, boolean>>({});
  const [submitting, setSubmitting] = useState(false);
  const [query, setQuery] = useState("");
  const searching = note.status === "writing";

  const adoptable = materials.filter((n) => !n.already_local);
  const pickedNotes = adoptable.filter((n) => picked[n.note_id]);
  const savedCount = materials.filter((n) => n.already_local).length;
  const toggle = (id: string) => setPicked((p) => ({ ...p, [id]: !p[id] }));
  const runSearch = () => {
    const q = query.trim();
    if (!q || searching) return;
    actions.searchMaterials(q);
    setQuery("");
  };
  const adopt = () => {
    if (submitting || pickedNotes.length === 0) return;
    setSubmitting(true);
    actions.adoptNotes(pickedNotes);
    setPicked({});
    setTimeout(() => setSubmitting(false), 8000);
  };

  return (
    <div style={{ flex: 1, display: "flex", flexDirection: "column", minHeight: 0 }}>
      <div style={{ padding: "14px 16px 10px", borderBottom: "1px solid var(--border)", display: "flex", flexDirection: "column", gap: 10 }}>
        <PanelHead
          icon="layers"
          title="参考素材笔记"
          sub={materials.length ? `线上 + 本地混排 · 共 ${materials.length} 条` : "线上 + 本地混排"}
          right={savedCount > 0 ? <Badge tone="synced" shape="chip">已入库 {savedCount}</Badge> : undefined}
        />
        {/* 搜索框:发「检索素材」指令给 agent(走检索工具),命中笔记流回累积进工作台。
            生成中禁用,避免打断当前流。这是真检索,不是本地假 seed 池过滤。 */}
        <div style={{ display: "flex", gap: 6 }}>
          <div style={{ flex: 1, display: "flex", alignItems: "center", gap: 7, background: "var(--input-bg)", border: "1px solid var(--border-strong)", borderRadius: "var(--radius-md)", padding: "7px 10px", opacity: searching ? 0.55 : 1 }}>
            <Icon name="search" size={13} color="var(--text-subtle)" />
            <input
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              onKeyDown={(e) => { if (e.key === "Enter") runSearch(); }}
              disabled={searching}
              placeholder={searching ? "🍠 正在检索…" : "搜索更多参考素材…"}
              aria-label="搜索参考素材"
              style={{ flex: 1, minWidth: 0, border: "none", outline: "none", background: "transparent", fontSize: "var(--text-xs)", color: "var(--text-body)" }}
            />
          </div>
          <Button variant="primary" size="sm" disabled={searching || !query.trim()} onClick={runSearch}>搜索</Button>
        </div>
      </div>
      <div className="cs" style={{ flex: 1, overflowY: "auto", padding: 16 }}>
        {materials.length === 0 ? (
          <div style={{ margin: "24px auto", maxWidth: 260, textAlign: "center", display: "flex", flexDirection: "column", gap: 10, color: "var(--text-subtle)" }}>
            <div style={{ margin: "0 auto", width: 44, height: 44, borderRadius: "var(--radius-lg)", background: "var(--oats-light)", display: "flex", alignItems: "center", justifyContent: "center" }}>
              <Icon name="layers" size={20} color="var(--text-subtle)" />
            </div>
            <div style={{ fontSize: "var(--text-sm)", fontWeight: 700, color: "var(--text-muted)" }}>还没有参考素材</div>
            <p style={{ margin: 0, fontSize: 11, lineHeight: 1.7 }}>说一个方向让我找爆款(线上+本地),检索到的参考笔记会固定在这里——可勾选收录入库,或挑一篇仿写。</p>
          </div>
        ) : (
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10, alignItems: "start" }}>
            {materials.map((n) => (
              <MaterialCard
                key={n.note_id}
                note={n}
                picked={!!picked[n.note_id]}
                onToggle={() => !n.already_local && toggle(n.note_id)}
                onImitate={() => actions.imitate(n)}
                onOpen={() => actions.openDetail({ kind: "material", noteId: n.note_id })}
              />
            ))}
          </div>
        )}
      </div>
      {adoptable.length > 0 && (
        <div style={{ padding: 14, borderTop: "1px solid var(--border)", background: "var(--surface-card)", display: "flex", alignItems: "center", gap: 10 }}>
          <span style={{ flex: 1, fontSize: 11, color: "var(--text-subtle)" }}>
            {pickedNotes.length ? `已选 ${pickedNotes.length} / ${adoptable.length} 篇` : "勾选线上笔记批量收录入库"}
          </span>
          <Button variant="primary" size="sm" disabled={submitting || pickedNotes.length === 0} leftIcon={<Icon name={submitting ? "loader" : "cloud-upload"} size={13} />} onClick={adopt}>
            {submitting ? "收录中…" : `收录选中 ${pickedNotes.length || ""} 篇`}
          </Button>
        </div>
      )}
    </div>
  );
}

// 单张素材卡:封面 + 来源 badge(线上/本地库) + 勾选框(批量收录) + 仿写按钮(单张即走)。
function MaterialCard({ note: n, picked, onToggle, onImitate, onOpen }: {
  note: DiscoveryNote;
  picked: boolean;
  onToggle: () => void;
  onImitate: () => void;
  onOpen: () => void;
}) {
  const locked = !!n.already_local;
  const isLocal = n.source === "local";
  return (
    <div className="lift pop-in" style={{ position: "relative", background: "var(--surface-card)", border: "1px solid var(--border)", borderRadius: "var(--radius-md)", overflow: "hidden", boxShadow: picked ? "var(--shadow-md)" : "var(--shadow-xs)", outline: picked ? "2px solid var(--primary)" : "2px solid transparent", transition: "outline-color var(--dur-fast), box-shadow var(--dur-fast)", display: "flex", flexDirection: "column" }}>
      {/* 封面盒:所有卡统一 3:4 定尺 + object-fit:cover。无封面图时用同尺寸的居中占位(🍠),
          绝不塌成空盒或异形 —— 配合网格 align-items:start(卡片不被同行拉伸),整栏封面像素级一致。 */}
      <div onClick={onOpen} style={{ position: "relative", width: "100%", aspectRatio: "3 / 4", overflow: "hidden", background: "var(--accent-surface)", cursor: "pointer", display: "flex", alignItems: "center", justifyContent: "center" }}>
        {n.cover_url ? (
          <Image src={coverProxyUrl(n.cover_url)!} alt={n.title} fill sizes="180px" unoptimized style={{ objectFit: "cover" }} />
        ) : (
          <span aria-hidden style={{ fontSize: 26, opacity: 0.5, lineHeight: 1 }}>🍠</span>
        )}
        <div style={{ position: "absolute", inset: 0, background: "linear-gradient(180deg, rgba(0,0,0,0) 60%, rgba(0,0,0,0.34))" }} />
        <span style={{ position: "absolute", top: 6, left: 6, fontSize: 8, fontWeight: 700, color: "#fff", background: isLocal ? "rgba(52,120,90,0.9)" : "rgba(0,0,0,0.42)", padding: "2px 7px", borderRadius: 999 }}>{isLocal ? "本地库" : "线上"}</span>
        {locked ? (
          <span style={{ position: "absolute", top: 6, right: 6, fontSize: 8, fontWeight: 700, color: "var(--success)", background: "#fff", padding: "2px 6px", borderRadius: 999, boxShadow: "var(--shadow-xs)" }}>已收录</span>
        ) : (
          <button
            data-testid="material-check"
            aria-label={picked ? "取消勾选" : "勾选收录"}
            onClick={(e) => { e.stopPropagation(); onToggle(); }}
            style={{ position: "absolute", top: 6, right: 6, width: 20, height: 20, borderRadius: 999, background: picked ? "var(--primary)" : "rgba(255,255,255,0.92)", border: picked ? "none" : "1px solid var(--border)", display: "inline-flex", alignItems: "center", justifyContent: "center", cursor: "pointer", boxShadow: "var(--shadow-xs)", padding: 0 }}
          >
            {picked && <Icon name="check" size={12} color="#fff" />}
          </button>
        )}
      </div>
      <div style={{ padding: "8px 9px", display: "flex", flexDirection: "column", gap: 6 }}>
        <div style={{ fontSize: 11, fontWeight: 700, color: "var(--text-body)", lineHeight: 1.35, display: "-webkit-box", WebkitLineClamp: 2, WebkitBoxOrient: "vertical", overflow: "hidden", cursor: "pointer", minHeight: "calc(1.35em * 2)" }} onClick={onOpen}>{n.title}</div>
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", fontSize: 9, color: "var(--text-subtle)" }}>
          <span style={{ maxWidth: 78, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{n.author || ""}</span>
          {n.likes != null && <span>♥ {n.likes}</span>}
        </div>
        <button
          data-testid="material-imitate"
          onClick={(e) => { e.stopPropagation(); onImitate(); }}
          style={{ display: "inline-flex", alignItems: "center", justifyContent: "center", gap: 4, width: "100%", border: "1px solid var(--border-coral)", background: "var(--accent-surface)", color: "var(--primary)", borderRadius: "var(--radius-sm)", padding: "5px 0", cursor: "pointer", fontSize: 11, fontWeight: 700 }}
        >
          <Icon name="feather" size={12} /> 仿写
        </button>
      </div>
    </div>
  );
}

function StateNote({ tone = "muted", children }: { tone?: "muted" | "warning"; children: ReactNode }) {
  return (
    <div style={{
      border: `1px solid ${tone === "warning" ? "var(--border-coral)" : "var(--border)"}`,
      background: tone === "warning" ? "var(--accent-surface)" : "var(--oats-light)",
      color: tone === "warning" ? "var(--primary)" : "var(--text-muted)",
      borderRadius: "var(--radius-md)",
      padding: "9px 12px",
      fontSize: "var(--text-xs)",
      lineHeight: "var(--leading-relaxed)",
    }}>
      {children}
    </div>
  );
}

// Center chat column — base proposal + dynamic store messages
// 工具审批中断卡。后端 HumanInTheLoopMiddleware 对写类工具中断,发来 HITLRequest
// (action_requests + review_configs);用户对每个动作批准/驳回,按序汇成 decisions 提交恢复。
// 无此卡时,中断后前端无端口应答 → 会话永久挂起(死锁)。这是修复 #16 的关键交互。
function InterruptApprovalCard({
  interrupt,
  onRespond,
}: {
  interrupt: HITLRequest;
  onRespond: (decisions: HITLDecision[]) => void;
}) {
  const [submitting, setSubmitting] = useState(false);
  const reqs = interrupt.action_requests ?? [];
  const configs = interrupt.review_configs ?? [];
  // 成功恢复后本卡会因 interrupt→null 卸载。若恢复失败(如决定数不匹配/网络错),interrupt 仍在、
  // 本卡仍挂载:此时必须解除按钮禁用,否则用户被永久锁死无法重试(评审 HIGH)。超时兜底:提交后
  // 若一定时间内卡未卸载(未恢复),重新放开按钮供重试。新中断到达时,调用点用 key 重挂本卡,
  // submitting 随新实例天然归零(无需在 effect 里同步 setState)。
  useEffect(() => {
    if (!submitting) return;
    const timer = setTimeout(() => setSubmitting(false), 8000);
    return () => clearTimeout(timer);
  }, [submitting]);
  const allowedFor = (i: number): string[] =>
    configs[i]?.allowed_decisions ?? configs.find((c) => c.action_name === reqs[i]?.action)?.allowed_decisions ?? ["approve", "reject"];

  const decide = (type: "approve" | "reject") => {
    if (submitting) return;
    setSubmitting(true);
    // 一次中断可批量多个动作;此处对全部动作统一批准或统一驳回(按序一一对应)。
    const decisions: HITLDecision[] = reqs.map((_, i) => {
      const allowed = allowedFor(i);
      if (type === "approve" && allowed.includes("approve")) return { type: "approve" };
      if (type === "reject" && allowed.includes("reject")) return { type: "reject" };
      // 兜底:该动作不允许所选决定时,退回其首个允许项(避免决定数与动作数不匹配报错)。
      return allowed.includes("approve") ? { type: "approve" } : { type: "reject" };
    });
    onRespond(decisions);
  };

  return (
    <Card padding="md" style={{ border: "1px solid var(--border-coral)" }}>
      <div style={{ display: "flex", alignItems: "center", gap: 7, marginBottom: 8 }}>
        <Icon name="shield-check" size={15} color="var(--primary)" />
        <span style={{ fontSize: "var(--text-sm)", fontWeight: 700 }}>需要你确认这些写操作</span>
      </div>
      <p style={{ margin: "0 0 10px", fontSize: 11, color: "var(--text-muted)", lineHeight: 1.6 }}>
        智能体准备执行以下会写入外部系统(飞书/线上)的动作,已暂停等待你的批准。
      </p>
      <div style={{ display: "flex", flexDirection: "column", gap: 7, marginBottom: 12 }}>
        {reqs.map((r, i) => (
          <div key={i} style={{ border: "1px solid var(--border)", borderRadius: "var(--radius-sm)", padding: "7px 9px", background: "var(--oats-light)" }}>
            <div style={{ fontSize: 11, fontWeight: 700, color: "var(--text-body)" }}>{r.action}</div>
            {r.args && Object.keys(r.args).length > 0 && (
              <div style={{ fontSize: 9, color: "var(--text-subtle)", marginTop: 3, fontFamily: "var(--font-mono)", wordBreak: "break-all", maxHeight: 72, overflowY: "auto" }}>
                {JSON.stringify(r.args).slice(0, 300)}
              </div>
            )}
          </div>
        ))}
      </div>
      <div style={{ display: "flex", gap: 8 }}>
        <Button variant="primary" size="sm" style={{ flex: 1 }} disabled={submitting} leftIcon={<Icon name="check" size={13} />} onClick={() => decide("approve")}>全部批准</Button>
        <Button variant="secondary" size="sm" style={{ flex: 1 }} disabled={submitting} leftIcon={<Icon name="x" size={13} />} onClick={() => decide("reject")}>全部驳回</Button>
      </div>
    </Card>
  );
}

function ChatColumn({ showTopics }: { showTopics: boolean }) {
  const { topics, evidence, timeline, trends, actions, interrupt, note } = useStudio();
  const generating = note.status === "writing";
  const [draft, setDraft] = useState("");
  const scrollRef = useRef<HTMLDivElement>(null);
  const sendDraft = () => {
    if (!draft.trim()) return;
    actions.say(draft);
    setDraft("");
  };
  const handleComposerKeyDown = (event: ReactKeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key !== "Enter" || event.shiftKey || event.nativeEvent.isComposing) return;
    event.preventDefault();
    sendDraft();
  };
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
            <div style={{ fontFamily: "var(--font-display)", fontWeight: 800, fontSize: "var(--text-lg)", color: "var(--text-body)" }}>先说一个方向</div>
            <p style={{ margin: 0, fontSize: "var(--text-sm)", lineHeight: "var(--leading-relaxed)" }}>
              比如「按露营装备出选题」。我先找素材、拆依据，再给你几张可继续写的选题卡。
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
                    title={item.run.presentation?.userSummary ?? (item.run.done ? undefined : RESPONSE_LOADING_TEXT)}
                    currentStep={item.run.currentStep}
                    totalSteps={item.run.totalSteps}
                    running={!item.run.done}
                    defaultOpen={Boolean(item.run.presentation)}
                    defaultCollapsed={(item.run.presentation?.collapsedByDefault ?? false) || item.run.done}
                  />
                </div>
              </div>
            );
          }
          if (item.kind === "error") {
            return (
              <div key={key} style={{ display: "flex", gap: 11, maxWidth: "92%" }}>
                <Avatar glyph="🍠" variant="agent" size={32} />
                <div style={{ flex: 1, maxWidth: 440 }}>
                  <StateNote tone="warning">{item.text || RESPONSE_ERROR_TEXT}</StateNote>
                </div>
              </div>
            );
          }
          if (item.kind === "ai") {
            return (
              <div key={key} style={{ display: "flex", gap: 11, maxWidth: "92%" }}>
                <Avatar glyph="🍠" variant="agent" size={32} />
                <div style={{ background: "var(--surface-card)", border: "1px solid var(--border-coral)", borderRadius: "var(--radius-xl)", padding: "11px 15px", fontSize: "var(--text-sm)", lineHeight: "var(--leading-relaxed)", boxShadow: "var(--shadow-sm)", alignSelf: "flex-start", whiteSpace: "pre-wrap", overflowWrap: "anywhere" }}>{item.text}</div>
              </div>
            );
          }
          if (item.kind === "discovery") {
            // 检索出的参考素材笔记不再进对话流(会滚走),改由右边栏「参考素材工作台」固定展示
            // (需求 §1/§3)。此处只给一句轻量提示,把用户视线引到右栏。
            return (
              <div key={key} style={{ display: "flex", gap: 11, maxWidth: "92%" }}>
                <Avatar glyph="🍠" variant="agent" size={32} />
                <div style={{ display: "inline-flex", alignItems: "center", gap: 7, background: "var(--surface-card)", border: "1px solid var(--border-coral)", borderRadius: "var(--radius-xl)", padding: "10px 14px", fontSize: "var(--text-sm)", boxShadow: "var(--shadow-sm)", color: "var(--text-body)" }}>
                  <Icon name="layers" size={14} color="var(--primary)" />
                  找到 {item.notes.length} 篇参考素材,已放到右侧工作台 —— 可勾选收录,或挑一篇仿写。
                </div>
              </div>
            );
          }
          if (item.kind === "panel") {
            // 意图分流(§2):模糊创作请求时给可点选项(如「让 AI 出选题」/「找爆款来仿写」),
            // 用户点一下直接进对应流程,不用打字。这是主控"请求模糊直接给最合理假设"的**有意例外**。
            return (
              <div key={key} style={{ display: "flex", gap: 11, maxWidth: "92%" }}>
                <Avatar glyph="🍠" variant="agent" size={32} />
                <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
                  {item.actions.map((a, ai) => (
                    <button key={ai} data-testid="intent-choice" onClick={() => actions.say(a.text)}
                      style={{ display: "inline-flex", alignItems: "center", gap: 6, border: "1px solid var(--border-coral)", background: "var(--surface-card)", color: "var(--primary)", borderRadius: "var(--radius-lg)", padding: "9px 15px", cursor: "pointer", fontSize: "var(--text-sm)", fontWeight: 700, boxShadow: "var(--shadow-xs)" }}>
                      <Icon name="sparkles" size={13} /> {a.label}
                    </button>
                  ))}
                </div>
              </div>
            );
          }
          return null;
        })}

        {/* 选题卡:仅当真实产出选题时,在助手气泡内渲染(showTopics 布局下);无选题不显示 */}
        {showTopics && topics.length > 0 && (
          <div style={{ display: "flex", gap: 11, maxWidth: "92%" }}>
            <Avatar glyph="🍠" variant="agent" size={32} />
            <Card padding="md">
              <p style={{ margin: 0, fontSize: "var(--text-sm)", lineHeight: "var(--leading-relaxed)" }}>我按相关素材整理了几个方向。每张卡都带依据，点进去看详情再起稿。</p>
              {/* 3:4 海报卡栅格(对齐原型的内联选题卡):角度徽章 + 🔥爆款率 + 文字大字报版式 + 依据数。
                  点卡 → 详情弹窗(DetailModal)看依据后起稿。无真实封面图源:用 angle/title 文字版式,
                  绝不塞假图(原型的 CSS 渐变占位按铁律不搬)。 */}
              <div className="stagger" style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10, marginTop: 11 }}>
                {topics.map((t, i) => (
                  <PosterTopicCard
                    key={t.id}
                    topic={t}
                    index={i}
                    evidenceCount={evidence[t.id]?.items.length ?? 0}
                    onClick={() => actions.openDetail({ kind: "topic", topicId: t.id })}
                  />
                ))}
              </div>
            </Card>
          </div>
        )}

        {/* 热点趋势雷达:仅当有真实趋势数据时显示 */}
        {trends.length > 0 && (
          <div style={{ display: "flex", gap: 11, maxWidth: "92%" }}>
            <Avatar glyph="🍠" variant="agent" size={32} />
            <div style={{ flex: 1, minWidth: 0 }}><TrendingTopics /></div>
          </div>
        )}

        {/* 工具审批中断卡:后端对写类工具中断等待人工批准;无此卡则中断后会话死锁。 */}
        {interrupt && (
          <div style={{ display: "flex", gap: 11, maxWidth: "92%" }}>
            <Avatar glyph="🍠" variant="agent" size={32} />
            <div style={{ flex: 1, minWidth: 0 }}>
              <InterruptApprovalCard
                key={(interrupt.action_requests ?? []).map((r) => r.action).join("|")}
                interrupt={interrupt}
                onRespond={actions.respondToInterrupt}
              />
            </div>
          </div>
        )}
      </div>

      <div style={{ padding: "14px 22px 16px", borderTop: "1px solid var(--border)", background: "var(--surface-card)", flexShrink: 0 }}>
        <div style={{ maxWidth: 720, margin: "0 auto" }}>
          <Textarea rows={2} value={draft} onChange={(e) => setDraft(e.target.value)} onKeyDown={handleComposerKeyDown} placeholder="比如：按职场穿搭出 3 个选题，要有依据…" footer={<>
            <button onClick={() => actions.polish()} style={{ display: "inline-flex", alignItems: "center", gap: 6, background: "var(--surface-card)", border: "1px solid var(--border)", borderRadius: "var(--radius-sm)", padding: "5px 9px", cursor: "pointer" }}>
              <kbd style={{ fontSize: 8, background: "var(--oats-light)", border: "1px solid var(--border)", padding: "1px 4px", borderRadius: 4, fontFamily: "var(--font-mono)" }}>Ctrl+P</kbd>
              <span style={{ fontSize: "var(--text-xs)", color: "var(--text-muted)" }}>润色工具箱</span>
            </button>
            {generating ? (
              <Button variant="secondary" size="sm" leftIcon={<Icon name="circle" size={13} />} onClick={() => actions.stop()}>停止生成</Button>
            ) : (
              <Button variant="primary" size="sm" rightIcon={<Icon name="send" size={14} />} onClick={sendDraft}>发送</Button>
            )}
          </>} />
        </div>
      </div>
    </section>
  );
}

// 3:4 海报选题卡(对齐原型的内联选题卡设计)。无真实封面图源:封面区用「角度 + 标题」文字大字报
// 版式 + 暖色渐变底(装饰性排版,非伪装成真实照片的假数据)。角度徽章 + 🔥爆款率 + 依据数皆真实。
function PosterTopicCard({
  topic,
  index,
  evidenceCount,
  onClick,
}: {
  topic: Topic;
  index: number;
  evidenceCount: number;
  onClick: () => void;
}) {
  const [hover, setHover] = useState(false);
  // 三档暖色渐变,仅按序轮换做视觉区分(装饰,非数据)。
  const grads = [
    "linear-gradient(150deg, var(--accent-surface), color-mix(in srgb, var(--primary) 22%, var(--oats-light)))",
    "linear-gradient(150deg, var(--topicblue-light), color-mix(in srgb, var(--topicblue-default) 16%, var(--oats-light)))",
    "linear-gradient(150deg, var(--oats-dark), color-mix(in srgb, var(--warning) 16%, var(--oats-light)))",
  ];
  return (
    <div
      data-testid="topic-card"
      onClick={onClick}
      onMouseEnter={() => setHover(true)}
      onMouseLeave={() => setHover(false)}
      style={{ "--i": index, borderRadius: "var(--radius-md)", overflow: "hidden", cursor: "pointer", border: `1px solid ${hover ? "var(--primary)" : "var(--border)"}`, background: "var(--surface-card)", boxShadow: hover ? "var(--shadow-md)" : "var(--shadow-xs)", transform: hover ? "translateY(-2px)" : "none", transition: "all var(--dur-fast) var(--ease-out)", display: "flex", flexDirection: "column" } as CSSProperties}
    >
      {/* 封面版式区(3:4):角度徽章 + 🔥 + 大字标题排版 */}
      <div style={{ position: "relative", width: "100%", aspectRatio: "3 / 4", overflow: "hidden", background: grads[index % 3], display: "flex", alignItems: "flex-end", padding: 11 }}>
        {topic.angle && <span style={{ position: "absolute", top: 7, left: 7, fontSize: 8, fontWeight: 700, color: "var(--text-body)", background: "rgba(255,255,255,0.86)", backdropFilter: "blur(4px)", padding: "2px 7px", borderRadius: 999 }}>{topic.angle}</span>}
        {topic.hotRate != null && (
          <span className="font-tabular" style={{ position: "absolute", top: 7, right: 7, fontSize: 9, fontWeight: 700, color: "var(--hot)", background: "rgba(255,255,255,0.92)", backdropFilter: "blur(4px)", padding: "2px 7px", borderRadius: 999, boxShadow: "0 1px 2px rgba(0,0,0,.1)" }}>🔥 {topic.hotRate}</span>
        )}
        <span style={{ fontFamily: "var(--font-display)", fontWeight: 800, fontSize: "var(--text-base)", lineHeight: 1.25, color: "var(--text-body)", letterSpacing: "var(--tracking-tight)", display: "-webkit-box", WebkitLineClamp: 3, WebkitBoxOrient: "vertical", overflow: "hidden", textShadow: "0 1px 0 rgba(255,255,255,0.4)" }}>{topic.title}</span>
      </div>
      {/* 卡脚:推荐理由首句 + 依据数 */}
      <div style={{ padding: "9px 11px 10px", display: "flex", alignItems: "center", justifyContent: "space-between", gap: 6 }}>
        <span style={{ minWidth: 0, fontSize: 9, color: "var(--text-subtle)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{(topic.rationale || "").split(/[·,，]/)[0] || "点开看依据"}</span>
        {evidenceCount > 0 && (
          <span className="font-tabular" style={{ flexShrink: 0, display: "inline-flex", alignItems: "center", gap: 3, fontSize: 9, fontWeight: 600, color: "var(--topicblue-default)", background: "var(--topicblue-light)", borderRadius: 999, padding: "1px 6px" }}>
            <Icon name="database" size={9} /> 依据 {evidenceCount}
          </span>
        )}
      </div>
    </div>
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
              <EvidenceScoreBar label="相关度 Relevance" val={e.relevance} color="var(--primary)" testid="evidence-relevance" />
              <EvidenceScoreBar label="时效性 Freshness · e⁻⁰·⁰⁵ᵗ" val={e.freshness} color="var(--success)" />
              <EvidenceScoreBar label="爆款表现 Engagement · tanh" val={e.performance} color="var(--amber-500)" />
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

function EvidenceScoreBar({ label, val, color, testid }: { label: string; val: number; color: string; testid?: string }) {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 5 }}>
      <div style={{ display: "flex", justifyContent: "space-between", fontSize: 10, color: "var(--text-muted)" }}><span>{label}</span><span data-testid={testid} className="font-tabular" style={{ fontWeight: 600, color: "var(--text-body)" }}>{(val * 100).toFixed(1)}%</span></div>
      <div style={{ height: 6, background: "var(--oats-dark)", borderRadius: 999, overflow: "hidden" }}><div style={{ height: "100%", width: `${val * 100}%`, background: color, transition: "width var(--dur-slow) var(--ease-out)" }} /></div>
    </div>
  );
}

// 热点趋势雷达 — 外部实时信号（区别于内部历史沉淀），驱动实时选题。
function TrendingTopics() {
  const { trends, actions } = useStudio();
  const toneBg: Record<string, string> = { hot: "var(--hot-surface)", coral: "var(--accent-surface)", topic: "var(--topicblue-light)" };
  const toneFg: Record<string, string> = { hot: "var(--hot)", coral: "var(--primary)", topic: "var(--topicblue-default)" };
  return (
    <div style={{ background: "var(--surface-card)", border: "1px solid var(--border-coral)", borderRadius: "var(--radius-lg)", padding: 12, display: "flex", flexDirection: "column", gap: 9, boxShadow: "var(--shadow-sm)" }}>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
        <div style={{ display: "flex", alignItems: "center", gap: 7 }}><Icon name="radar" size={15} color="var(--primary)" /><span style={{ fontSize: "var(--text-xs)", fontWeight: 700 }}>热点趋势雷达</span><span style={{ fontSize: 9, color: "var(--text-subtle)" }}>· 平台实时上升</span></div>
        <span style={{ fontSize: 9, color: "var(--text-subtle)" }}>实时信号 · 辅助选题</span>
      </div>
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 7 }}>
        {trends.map((t) => (
          <button key={t.tag} data-testid="trend-row" onClick={() => actions.say(`基于热点「${t.tag}」出几个可发布选题`)} style={{ display: "flex", alignItems: "center", gap: 8, padding: "7px 9px", borderRadius: "var(--radius-sm)", border: "1px solid var(--border)", background: "var(--oats-light)", cursor: "pointer", textAlign: "left" }}>
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

// 统一详情/仿写弹层(居中对话框,1:1 对齐设计稿 openModal)—— 素材卡或选题卡点开后看详情,
// 并直接触发动作。由 store.detail 驱动,从 StudioShell 挂载(与 EvidencePanel 同级)。
// 素材:看封面/来源/摘录 + 收录/仿写;选题:看角度/依据 + 支撑素材 + 起稿。
export function DetailModal() {
  const { detail, actions } = useStudio();
  const { closing, dismiss } = useDismiss(actions.closeDetail);
  // Esc 关闭(对齐设计稿 openModal 的 onModalKey);仅在弹层打开时挂监听。
  useEffect(() => {
    if (!detail) return undefined;
    const onKey = (e: globalThis.KeyboardEvent) => { if (e.key === "Escape") dismiss(); };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [detail, dismiss]);
  if (!detail) return null;
  const label = detail.kind === "material" ? "参考素材详情" : "选题详情";
  return (
    <div onClick={dismiss} className={closing ? "scrim-out" : "scrim-in"} style={{ position: "fixed", inset: 0, zIndex: 56, display: "flex", alignItems: "center", justifyContent: "center", padding: 32, background: "rgba(20,18,16,0.42)", backdropFilter: "blur(3px)", WebkitBackdropFilter: "blur(3px)" }}>
      <div onClick={(e) => e.stopPropagation()} role="dialog" aria-modal="true" aria-label={label} className={closing ? "pop-out" : "pop-in"} style={{ width: "min(720px, 100%)", maxHeight: "88vh", overflow: "hidden", background: "var(--surface-card)", border: "1px solid var(--border)", borderRadius: "var(--radius-xl)", boxShadow: "var(--shadow-2xl)", display: "flex", flexDirection: "column" }}>
        {detail.kind === "material" ? <MaterialDetailBody noteId={detail.noteId} onClose={dismiss} /> : <TopicDetailBody topicId={detail.topicId} onClose={dismiss} />}
      </div>
    </div>
  );
}

// 悬浮关闭按钮(对齐设计稿 modalClose):浮在封面带右上角的圆形 ×。
function ModalCloseButton({ onClose }: { onClose: () => void }) {
  return (
    <button onClick={onClose} aria-label="关闭" style={{ position: "absolute", top: 14, right: 14, width: 30, height: 30, borderRadius: 999, border: 0, background: "rgba(255,255,255,0.9)", color: "var(--text-body)", cursor: "pointer", display: "grid", placeItems: "center", boxShadow: "var(--shadow-sm)" }}>
      <Icon name="x" size={16} />
    </button>
  );
}

function MaterialDetailBody({ noteId, onClose }: { noteId: string; onClose: () => void }) {
  const { materials, actions } = useStudio();
  const n = materials.find((m) => m.note_id === noteId);
  if (!n) return null;
  const isLocal = n.source === "local";
  return (
    <>
      {/* 封面带:16/9 满宽(对齐设计稿),真实封面走同源代理裁切;无图源退化为中性底色,绝不塞假图。 */}
      <div style={{ position: "relative", width: "100%", aspectRatio: "16 / 9", maxHeight: 280, overflow: "hidden", background: "var(--accent-surface)", flexShrink: 0 }}>
        {n.cover_url && <Image src={coverProxyUrl(n.cover_url)!} alt={n.title} fill sizes="720px" unoptimized style={{ objectFit: "cover" }} />}
        <span style={{ position: "absolute", top: 16, left: 18, fontSize: "var(--text-xs)", fontWeight: 600, color: "#fff", background: isLocal ? "var(--success)" : "var(--charcoal-default)", padding: "3px 10px", borderRadius: "var(--radius-sm)" }}>{isLocal ? "本地库" : "线上"}</span>
        <ModalCloseButton onClose={onClose} />
      </div>
      {/* 可滚动正文(flex:1 + minHeight:0 才能在 maxHeight 卡片内真正滚动,否则会撑破卡片顶走页脚) */}
      <div className="cs" style={{ flex: 1, minHeight: 0, padding: "20px 22px", overflowY: "auto", display: "flex", flexDirection: "column", gap: 14 }}>
        <h2 style={{ margin: 0, fontFamily: "var(--font-display)", fontWeight: 800, fontSize: "var(--text-xl)", lineHeight: 1.3, letterSpacing: "var(--tracking-tight)", color: "var(--text-body)" }}>{n.title}</h2>
        <div style={{ display: "flex", flexWrap: "wrap", alignItems: "center", gap: 12, fontSize: "var(--text-xs)", color: "var(--text-muted)" }}>
          {n.author && (
            <span style={{ display: "inline-flex", alignItems: "center", gap: 5 }}>
              <span style={{ width: 22, height: 22, borderRadius: 999, background: "var(--accent-surface)", color: "var(--coral-default)", display: "grid", placeItems: "center", fontSize: 10, fontWeight: 700 }}>{n.author.charAt(0)}</span>
              {n.author}
            </span>
          )}
          {n.likes != null && <span>♥ {n.likes}</span>}
          {n.collects != null && <span>★ {n.collects}</span>}
          {n.comments != null && <span>💬 {n.comments}</span>}
          {n.already_local && (
            <span style={{ display: "inline-flex", alignItems: "center", gap: 4, background: "var(--success-surface)", color: "var(--success)", border: "1px solid var(--success-border)", borderRadius: 999, padding: "3px 10px", fontSize: "var(--text-xs)", fontWeight: 600 }}><Icon name="check" size={12} />已收录入库</span>
          )}
        </div>
        {n.summary && (
          <div>
            <Eyebrow style={{ marginBottom: 6 }}>正文摘录</Eyebrow>
            <p style={{ margin: 0, fontSize: "var(--text-sm)", lineHeight: 1.75, color: "var(--text-body)", whiteSpace: "pre-wrap" }}>{n.summary}</p>
          </div>
        )}
        {n.tags && n.tags.length > 0 && (
          <div style={{ display: "flex", flexWrap: "wrap", gap: 5 }}>
            {n.tags.map((tg) => <span key={tg} style={{ fontSize: 10, color: "var(--topicblue-default)", background: "var(--topicblue-light)", borderRadius: 999, padding: "2px 8px" }}>#{tg}</span>)}
          </div>
        )}
      </div>
      {/* 页脚:带上边框的操作行(对齐设计稿) */}
      <div style={{ padding: "14px 22px", borderTop: "1px solid var(--border)", display: "flex", alignItems: "center", justifyContent: "flex-end", gap: 10, flexShrink: 0 }}>
        {n.note_url && <a href={n.note_url} target="_blank" rel="noopener noreferrer" style={{ marginRight: "auto", fontSize: 11, color: "var(--text-subtle)", textDecoration: "none" }}>查看原文 ↗</a>}
        <Button variant="secondary" onClick={onClose}>关闭</Button>
        {!n.already_local && (
          <Button variant="soft" leftIcon={<Icon name="cloud-upload" size={14} />} onClick={() => { actions.adoptNotes([n]); actions.closeDetail(); }}>收录入库</Button>
        )}
        <Button variant="primary" leftIcon={<Icon name="feather" size={14} />} onClick={() => { actions.imitate(n); actions.closeDetail(); }}>仿写这篇</Button>
      </div>
    </>
  );
}

function TopicDetailBody({ topicId, onClose }: { topicId: number; onClose: () => void }) {
  const { topics, evidence, actions } = useStudio();
  const topic = topics.find((t) => t.id === topicId);
  const ev = (evidence || {})[topicId];
  if (!topic) return null;
  const evCount = ev ? ev.items.length : 0;
  return (
    <>
      {/* 封面带:中性底色 + 左上角度徽章 + 右上关闭(标题落在下方正文,对齐已确认的居中弹窗版式)。 */}
      <div style={{ position: "relative", height: 132, background: "var(--accent-surface)", flexShrink: 0 }}>
        {topic.angle && <span style={{ position: "absolute", top: 16, left: 18, background: "rgba(26,26,28,0.72)", color: "#fff", borderRadius: "var(--radius-sm)", padding: "3px 10px", fontSize: "var(--text-xs)", fontWeight: 600 }}>{topic.angle}</span>}
        <ModalCloseButton onClose={onClose} />
      </div>
      {/* 可滚动正文(flex:1 + minHeight:0 才能在 maxHeight 卡片内真正滚动,否则依据多了会撑破卡片顶走页脚) */}
      <div className="cs" style={{ flex: 1, minHeight: 0, padding: "20px 22px", overflowY: "auto", display: "flex", flexDirection: "column", gap: 16 }}>
        <h2 style={{ margin: 0, fontFamily: "var(--font-display)", fontWeight: 800, fontSize: "var(--text-2xl)", lineHeight: 1.2, letterSpacing: "var(--tracking-tight)", color: "var(--text-body)" }}>{topic.title}</h2>
        <div style={{ display: "flex", alignItems: "center", flexWrap: "wrap", gap: 10 }}>
          {topic.hotRate != null && <span style={{ display: "inline-flex", alignItems: "center", gap: 3, background: "var(--hot-surface)", color: "var(--hot)", borderRadius: 999, padding: "3px 10px", fontSize: "var(--text-xs)", fontWeight: 700 }}>🔥 爆款率 {topic.hotRate}%</span>}
          <span data-testid="detail-evidence-count" data-count={evCount} style={{ display: "inline-flex", alignItems: "center", gap: 4, background: "var(--topicblue-light)", color: "var(--topicblue-default)", borderRadius: 999, padding: "3px 10px", fontSize: "var(--text-xs)", fontWeight: 600 }}><Icon name="database" size={13} />依据 {evCount} 条</span>
          {topic.kw && <span style={{ marginLeft: "auto", display: "inline-flex", alignItems: "center", gap: 6, fontSize: 11 }}><span style={{ color: "var(--text-subtle)" }}>核心搜索词</span><span style={{ fontWeight: 600, color: "var(--topicblue-default)", background: "var(--topicblue-light)", borderRadius: 999, padding: "2px 8px" }}>{topic.kw}</span></span>}
        </div>
        {topic.rationale && (
          <div>
            <Eyebrow style={{ marginBottom: 6 }}>选题依据</Eyebrow>
            <p style={{ margin: 0, fontSize: "var(--text-sm)", lineHeight: 1.7, color: "var(--text-body)" }}>{topic.rationale}</p>
          </div>
        )}
        <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
          <Eyebrow>支撑素材（{evCount}）· 数据底座检索</Eyebrow>
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
      </div>
      {/* 页脚:带上边框的操作行(对齐设计稿) */}
      <div style={{ padding: "14px 22px", borderTop: "1px solid var(--border)", display: "flex", alignItems: "center", justifyContent: "flex-end", gap: 10, flexShrink: 0 }}>
        <Button variant="secondary" onClick={onClose}>关闭</Button>
        <Button variant="primary" leftIcon={<Icon name="feather" size={14} />} onClick={() => { actions.chooseTopic(topic); actions.closeDetail(); }}>用这个选题起稿</Button>
      </div>
    </>
  );
}

// 收录结果弹窗(居中对话框,对齐设计稿「部分收录完成」)—— 采纳线上笔记后展示本次结局:
// 成功/跳过/失败计数 + 逐条列出(✓ 已入库 / ! 失败·可重试)+ 失败可一键重试。由 store.adoptionModal
// 驱动(最新一次采纳、未被手动关闭时非 null),从 StudioShell 挂载(与 DetailModal 同级)。
// 修复:此前 adopt_online_notes 是写类工具,结果只在思考链显示中文 label,采纳后屏上毫无反馈。
export function AdoptionResultModal() {
  const { adoptionModal, actions } = useStudio();
  const { closing, dismiss } = useDismiss(actions.dismissAdoptionModal);
  // Esc 关闭(对齐 DetailModal);仅在弹层打开时挂监听。
  useEffect(() => {
    if (!adoptionModal) return undefined;
    const onKey = (e: globalThis.KeyboardEvent) => { if (e.key === "Escape") dismiss(); };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [adoptionModal, dismiss]);
  if (!adoptionModal) return null;

  const { successCount, skippedCount, failedCount, rows } = adoptionModal;
  const hasFailure = failedCount > 0;
  const allFailed = successCount === 0 && skippedCount === 0 && failedCount > 0;
  // 标题按结局分档:全失败=收录失败;有失败但也有成功/跳过=部分收录完成;否则=收录完成。
  const title = allFailed ? "收录失败" : hasFailure ? "部分收录完成" : "收录完成";
  // 副标题如实分述三态计数,有失败项时点明「可重试失败项」。
  const summaryParts = [`成功 ${successCount}`, `跳过 ${skippedCount}`, `失败 ${failedCount}`];
  const summary = summaryParts.join(" · ") + (hasFailure ? "，可重试失败项" : "");

  return (
    <div onClick={dismiss} className={closing ? "scrim-out" : "scrim-in"} style={{ position: "fixed", inset: 0, zIndex: 57, display: "flex", alignItems: "center", justifyContent: "center", padding: 32, background: "rgba(20,18,16,0.42)", backdropFilter: "blur(3px)", WebkitBackdropFilter: "blur(3px)" }}>
      <div onClick={(e) => e.stopPropagation()} role="dialog" aria-modal="true" aria-label={title} data-testid="adoption-result-modal" className={closing ? "pop-out" : "pop-in"} style={{ width: "min(460px, 100%)", maxHeight: "82vh", overflow: "hidden", background: "var(--surface-card)", border: "1px solid var(--border)", borderRadius: "var(--radius-xl)", boxShadow: "var(--shadow-2xl)", display: "flex", flexDirection: "column" }}>
        {/* 头部:状态图标 + 标题 + 计数副标题 + 分档色条(有失败=珊瑚红,全成功=绿) */}
        <div style={{ padding: "22px 24px 0", display: "flex", flexDirection: "column", gap: 4 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 9 }}>
            <Icon name={hasFailure ? "alert-circle" : "check-circle-2"} size={20} color={hasFailure ? "var(--primary)" : "var(--success)"} />
            <span style={{ fontFamily: "var(--font-display)", fontWeight: 800, fontSize: "var(--text-lg)", color: "var(--text-body)" }}>{title}</span>
          </div>
          <span data-testid="adoption-result-summary" style={{ fontSize: "var(--text-xs)", color: "var(--text-muted)", paddingLeft: 29 }}>{summary}</span>
        </div>
        <div style={{ height: 3, margin: "14px 24px 0", borderRadius: 999, background: hasFailure ? "var(--primary)" : "var(--success)" }} />
        {/* 逐条结果:每行 状态图标 + 标题 + 右侧结局标签 */}
        <div className="cs" style={{ flex: 1, minHeight: 0, overflowY: "auto", padding: "12px 12px", display: "flex", flexDirection: "column" }}>
          {rows.map((r, i) => (
            <AdoptionRowItem key={`${r.note_id}-${i}`} row={r} />
          ))}
        </div>
        {/* 页脚:关闭 + 有失败时「重试失败 N 篇」 */}
        <div style={{ padding: "12px 24px 18px", borderTop: "1px solid var(--border)", display: "flex", alignItems: "center", justifyContent: "flex-end", gap: 10, flexShrink: 0 }}>
          <Button variant="secondary" onClick={dismiss}>关闭</Button>
          {hasFailure && (
            <Button data-testid="adoption-retry" variant="primary" leftIcon={<Icon name="refresh-cw" size={14} />} onClick={() => { actions.retryFailedAdoptions(); }}>
              重试失败 {failedCount} 篇
            </Button>
          )}
        </div>
      </div>
    </div>
  );
}

// 收录结果单行:成功=绿 ✓「已入库」,跳过=中性「库里已有」,失败=珊瑚 !「失败·可重试」+ 原因。
function AdoptionRowItem({ row }: { row: AdoptionRow }) {
  const conf = {
    success: { icon: "check" as const, iconColor: "var(--success)", label: "已入库", labelColor: "var(--success)" },
    skipped: { icon: "check" as const, iconColor: "var(--text-subtle)", label: "库里已有", labelColor: "var(--text-subtle)" },
    failed: { icon: "alert-circle" as const, iconColor: "var(--primary)", label: "失败·可重试", labelColor: "var(--primary)" },
  }[row.outcome];
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 10, padding: "9px 12px", borderRadius: "var(--radius-sm)" }}>
      <Icon name={conf.icon} size={15} color={conf.iconColor} />
      <div style={{ flex: 1, minWidth: 0, display: "flex", flexDirection: "column", gap: 1 }}>
        <span style={{ fontSize: "var(--text-sm)", color: "var(--text-body)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{row.title}</span>
        {row.outcome === "failed" && row.error && (
          <span style={{ fontSize: 10, color: "var(--text-subtle)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{row.error}</span>
        )}
      </div>
      <span style={{ flexShrink: 0, fontSize: "var(--text-xs)", fontWeight: 600, color: conf.labelColor }}>{conf.label}</span>
    </div>
  );
}
