"use client";

// 账号运营 screen — 数据看板 · 选题库/爆款拆解 · 内容日历/排期 · 数据回填.

import { useRef, useState, type CSSProperties, type ReactNode } from "react";
import { Avatar, Badge, Button, Card, Icon, StatCard, Textarea, type BadgeProps } from "@/components/ds";
import { Eyebrow, PanelHead } from "@/components/studio/ui";
import { useStudio } from "@/components/studio/StudioContext";
import { WEEKDAYS } from "@/components/studio/types";
import type { Account, LibraryItem } from "@/components/studio/types";
import type { LoadStatus } from "@/components/studio/useBackendResource";

export type OpsHosting = "page" | "inline" | "hybrid";

export function Operations({ hosting = "page" }: { hosting?: OpsHosting }) {
  if (hosting === "inline") return <OpsInline />;
  if (hosting === "hybrid") return <OpsHybrid />;
  return <OpsPage />;
}

// 统一空态/错误态/加载态占位（真实数据铁律：empty/error 时渲染文案，绝不渲染占位业务数据）。
function StateNote({ status, empty, error }: { status: LoadStatus; empty: string; error?: string }) {
  if (status === "loading" || status === "idle") {
    return <div style={{ padding: 16, fontSize: 11, color: "var(--text-subtle)", textAlign: "center" }}>加载中…</div>;
  }
  if (status === "error") {
    return <div style={{ padding: 16, fontSize: 11, color: "var(--warning)", textAlign: "center" }}>{error || "数据加载失败，请稍后重试"}</div>;
  }
  return <div style={{ padding: 16, fontSize: 11, color: "var(--text-subtle)", textAlign: "center" }}>{empty}</div>;
}

// 多账号页：左侧账号矩阵栏 + （矩阵总览 / 单账号看板）
function OpsPage() {
  const { accounts, selectedAccount, setSelectedAccount } = useStudio();
  const account = accounts.find((a) => a.id === selectedAccount) ?? null;
  return (
    <div style={{ flex: 1, display: "flex", minHeight: 0, background: "var(--background)" }}>
      <AccountRail selected={selectedAccount ?? "all"} onSelect={(id) => setSelectedAccount(id === "all" ? null : id)} />
      <div className="cs" style={{ flex: 1, overflowY: "auto" }}>
        {selectedAccount === null ? <MatrixOverview onOpen={(id) => setSelectedAccount(id)} /> : <DashboardBody account={account} />}
      </div>
    </div>
  );
}

type Tone = Account["tone"];

interface AccountRailProps {
  selected: string;
  onSelect: (id: string) => void;
}

function AccountRail({ selected, onSelect }: AccountRailProps) {
  const { accounts, loadState } = useStudio();
  const dot = (tone: Tone): CSSProperties => ({ width: 26, height: 26, borderRadius: "999px", flexShrink: 0, display: "inline-flex", alignItems: "center", justifyContent: "center", fontSize: 11, fontWeight: 700, background: tone === "coral" ? "var(--accent-surface)" : tone === "topic" ? "var(--topicblue-light)" : "var(--oats-dark)", color: tone === "coral" ? "var(--primary)" : tone === "topic" ? "var(--topicblue-default)" : "var(--text-body)" });
  const Item = ({ id, label, sub, initial, tone, active }: { id: string; label: string; sub: string; initial: string; tone: Tone; active: boolean }) => (
    <button onClick={() => onSelect(id)} style={{ display: "flex", alignItems: "center", gap: 9, width: "100%", textAlign: "left", padding: "9px 11px", borderRadius: "var(--radius-sm)", border: "none", cursor: "pointer", borderLeft: active ? "2px solid var(--primary)" : "2px solid transparent", background: active ? "var(--oats-dark)" : "transparent" }}>
      <span style={dot(tone)}>{initial}</span>
      <span style={{ flex: 1, minWidth: 0 }}>
        <span style={{ display: "block", fontSize: "var(--text-xs)", fontWeight: 600, color: active ? "var(--primary)" : "var(--text-body)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{label}</span>
        <span style={{ display: "block", fontSize: 9, color: "var(--text-subtle)" }}>{sub}</span>
      </span>
    </button>
  );
  return (
    <aside className="cs" style={{ width: 208, borderRight: "1px solid var(--border)", background: "var(--surface-card)", flexShrink: 0, overflowY: "auto" }}>
      <div style={{ padding: 14, display: "flex", flexDirection: "column", gap: 6 }}>
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
          <Eyebrow>账号矩阵</Eyebrow>
          <span style={{ fontSize: 9, color: "var(--text-subtle)" }}>{accounts.length} 个</span>
        </div>
        <Item id="all" label="矩阵总览" sub="聚合 · 横向对比" initial="∑" tone="topic" active={selected === "all"} />
        <div style={{ height: 1, background: "var(--border)", margin: "4px 0" }} />
        {accounts.map((a) => <Item key={a.id} id={a.id} label={a.handle} sub={`${a.niche} · ${a.fans}`} initial={a.initial} tone={a.tone} active={selected === a.id} />)}
        {loadState.accounts !== "ready" && <StateNote status={loadState.accounts} empty="暂无账号" />}
      </div>
    </aside>
  );
}

interface MatrixOverviewProps {
  onOpen: (id: string) => void;
}

function MatrixOverview({ onOpen }: MatrixOverviewProps) {
  const { accounts, loadState } = useStudio();
  const sum = (k: "fansNum" | "dFans" | "posts" | "hot") => accounts.reduce((s, a) => s + a[k], 0);
  const fmt = (n: number) => (n >= 10000 ? (n / 10000).toFixed(1) + "w" : n.toLocaleString());
  const avgHot = accounts.length ? Math.round(sum("hot") / accounts.length) : 0;
  const statusTone: Record<string, BadgeProps["tone"]> = { "主力": "synced", "成长": "info", "孵化": "draft" };
  const col = "2fr 1fr 0.9fr 0.8fr 0.7fr 0.8fr";
  return (
    <div style={{ padding: 28, maxWidth: 1180, margin: "0 auto", display: "flex", flexDirection: "column", gap: 20 }}>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
        <div>
          <div style={{ fontFamily: "var(--font-display)", fontWeight: 800, fontSize: "var(--text-xl)" }}>账号矩阵总览</div>
          <div style={{ fontSize: "var(--text-xs)", color: "var(--text-muted)", marginTop: 3 }}>{accounts.length} 个账号 · 近 7 天 · 数据底座聚合（performance_metric）</div>
        </div>
      </div>
      <section>
        <Eyebrow style={{ marginBottom: 10 }}>矩阵聚合</Eyebrow>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 12 }}>
          <StatCard label="矩阵总粉丝" value={fmt(sum("fansNum"))} tone="coral" icon={<Icon name="users" size={15} />} />
          <StatCard label="本周新增粉丝" value={"+" + sum("dFans")} unit="人" tone="success" icon={<Icon name="user-plus" size={15} />} />
          <StatCard label="本周发布" value={sum("posts")} unit="篇" tone="topic" icon={<Icon name="file-text" size={15} />} />
          <StatCard label="平均爆款率" value={avgHot} unit="%" icon={<Icon name="flame" size={15} />} />
        </div>
      </section>
      <section style={{ display: "flex", flexDirection: "column", gap: 10 }}>
        <PanelHead icon="layout-grid" title="账号横向对比" sub="点任意账号进入它的运营看板" />
        <Card padding="none" style={{ overflow: "hidden" }}>
          <div style={{ display: "grid", gridTemplateColumns: col, padding: "9px 14px", borderBottom: "1px solid var(--border)", fontSize: 9, fontWeight: 700, color: "var(--text-subtle)", letterSpacing: "var(--tracking-wide)" }}>
            <span>账号</span><span>垂类</span><span>粉丝</span><span>近7天</span><span>爆款率</span><span>状态</span>
          </div>
          {loadState.accounts !== "ready" && <StateNote status={loadState.accounts} empty="暂无账号 · 接入账号后展示矩阵对比" />}
          {accounts.map((a, i) => (
            <button key={a.id} data-testid="account-row" onClick={() => onOpen(a.id)} style={{ display: "grid", gridTemplateColumns: col, alignItems: "center", width: "100%", textAlign: "left", padding: "11px 14px", border: "none", borderTop: i ? "1px solid var(--border)" : "none", background: "transparent", cursor: "pointer", fontSize: "var(--text-xs)" }}>
              <span style={{ display: "flex", alignItems: "center", gap: 8, minWidth: 0 }}>
                <span style={{ width: 24, height: 24, borderRadius: "999px", flexShrink: 0, display: "inline-flex", alignItems: "center", justifyContent: "center", fontSize: 10, fontWeight: 700, background: a.tone === "coral" ? "var(--accent-surface)" : a.tone === "topic" ? "var(--topicblue-light)" : "var(--oats-dark)", color: a.tone === "coral" ? "var(--primary)" : a.tone === "topic" ? "var(--topicblue-default)" : "var(--text-body)" }}>{a.initial}</span>
                <span style={{ fontWeight: 600, color: "var(--text-body)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{a.handle}</span>
              </span>
              <span style={{ color: "var(--text-muted)" }}>{a.niche}</span>
              <span className="font-tabular" style={{ fontWeight: 600 }}>{a.fans}</span>
              <span className="font-tabular" style={{ color: "var(--success)", fontWeight: 600 }}>+{a.dFans}</span>
              <span style={{ color: "var(--hot)", fontWeight: 700 }}>🔥{a.hot}</span>
              <span><Badge tone={statusTone[a.status]} shape="chip">{a.status}</Badge></span>
            </button>
          ))}
        </Card>
      </section>
      <CalendarSection />
    </div>
  );
}

interface DashboardBodyProps {
  dense?: boolean;
  account?: Account | null;
}

function DashboardBody({ dense = false, account = null }: DashboardBodyProps) {
  const { dashboard, user, loadState } = useStudio();
  const backfillRef = useRef<HTMLElement>(null);
  const focusBackfill = () => {
    const node = backfillRef.current;
    if (!node) return;
    node.scrollIntoView({ behavior: "smooth", block: "start" });
    // 聚焦回填表单首个可编辑输入,产生真实可观察结果(而非「示意」toast)。
    node.querySelector<HTMLElement>("input, textarea, [contenteditable]")?.focus();
  };
  const acct = account || { handle: user.handle, fans: user.fans, niche: "" };
  return (
    <div style={{ padding: dense ? 16 : 28, maxWidth: 1180, margin: "0 auto", display: "flex", flexDirection: "column", gap: 20 }}>
      {!dense && (
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
          <div>
            <div style={{ fontFamily: "var(--font-display)", fontWeight: 800, fontSize: "var(--text-xl)" }}>{acct.handle}</div>
            <div style={{ fontSize: "var(--text-xs)", color: "var(--text-muted)", marginTop: 3 }}>粉丝 {acct.fans}{acct.niche ? ` · ${acct.niche}` : ""} · 近 7 天 · 数据底座 / 飞书同步</div>
          </div>
          <div style={{ display: "flex", gap: 8 }}>
            <Button variant="primary" size="sm" leftIcon={<Icon name="pencil" size={13} />} onClick={focusBackfill}>数据回填</Button>
          </div>
        </div>
      )}

      {/* 数据看板 */}
      <section>
        <Eyebrow style={{ marginBottom: 10 }}>数据看板</Eyebrow>
        {loadState.analytics === "ready" ? (
          <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 12 }}>
            {dashboard.map((d) => <StatCard key={d.label} label={d.label} value={d.value} unit={d.unit} delta={d.delta} tone={d.tone} icon={<Icon name={d.icon} size={15} />} />)}
          </div>
        ) : (
          <Card padding="none" style={{ overflow: "hidden" }}>
            <StateNote status={loadState.analytics} empty="该账号暂无表现数据 · 发布并回填后展示" />
          </Card>
        )}
      </section>

      <LibrarySection />
      <CalendarSection accountFilter={account ? account.initial : null} />

      {!dense && <PipelineSection account={account} />}
      {!dense && <BackfillSection sectionRef={backfillRef} />}
    </div>
  );
}

// 选题库 / 爆款拆解
function LibrarySection() {
  const { actions, library, teardown, loadState } = useStudio();
  const [sel, setSel] = useState<number>(1);
  const td = teardown;
  const selItem = library.find((x) => x.id === sel) as LibraryItem | undefined;
  const statusTone: Record<string, BadgeProps["tone"]> = { "已发布": "synced", "排期中": "info", "草稿": "draft", "已回填": "synced" };
  return (
    <section style={{ display: "flex", flexDirection: "column", gap: 10 }}>
      <PanelHead icon="library-big" title="选题库 · 爆款拆解" sub="沉淀的选题与表现，点击拆解爆款套路" />
      <Card padding="none" style={{ overflow: "hidden" }}>
        {loadState.library !== "ready" && <StateNote status={loadState.library} empty="暂无沉淀选题 · 创作并回填后入库" />}
        {library.map((it, i) => {
          const on = it.id === sel;
          return (
            <button key={it.id} onClick={() => setSel(it.id)} style={{ display: "flex", alignItems: "center", gap: 10, width: "100%", textAlign: "left", padding: "11px 13px", border: "none", borderTop: i ? "1px solid var(--border)" : "none", cursor: "pointer", background: on ? "var(--accent-surface)" : "transparent" }}>
              <span style={{ fontSize: 11, fontWeight: 700, color: "var(--hot)", width: 38, flexShrink: 0 }}>🔥{it.hot}</span>
              <span style={{ flex: 1, minWidth: 0 }}>
                <span style={{ display: "block", fontSize: "var(--text-xs)", fontWeight: 600, color: "var(--text-body)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{it.title}</span>
                <span style={{ display: "block", fontSize: 10, color: "var(--text-subtle)", marginTop: 2 }}>{it.angle} · 赞 {it.likes} · 藏 {it.saves}</span>
              </span>
              <Badge tone={statusTone[it.status]} shape="chip">{it.status}</Badge>
            </button>
          );
        })}
      </Card>
      {/* teardown */}
      <Card padding="md" tone="sunken">
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 9 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 7, minWidth: 0 }}>
            <Icon name="scan-search" size={15} color="var(--primary)" />
            <span style={{ fontSize: "var(--text-xs)", fontWeight: 700, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>爆款拆解 · {selItem ? selItem.title : td.title}</span>
          </div>
          <Button variant="soft" size="sm" leftIcon={<Icon name="copy-plus" size={12} />} onClick={() => actions.reuse(sel <= 3 ? sel : 1)}>复用选题</Button>
        </div>
        <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
          {loadState.teardown !== "ready" && <StateNote status={loadState.teardown} empty="暂无可拆解的爆款 · 回填表现后生成拆解" />}
          {td.points.map((p) => (
            <div key={p.label} style={{ display: "flex", gap: 9 }}>
              <span style={{ fontSize: 10, fontWeight: 700, color: "var(--primary)", background: "var(--accent-surface)", border: "1px solid var(--border-coral)", borderRadius: 6, padding: "2px 7px", height: "fit-content", flexShrink: 0 }}>{p.label}</span>
              <span style={{ fontSize: 11, color: "var(--text-muted)", lineHeight: 1.5 }}>{p.detail}</span>
            </div>
          ))}
        </div>
      </Card>
    </section>
  );
}

// 内容日历 / 发布排期
interface CalendarSectionProps {
  accountFilter?: string | null;
}

function CalendarSection({ accountFilter = null }: CalendarSectionProps) {
  const { calendar, month, loadState } = useStudio();
  const toneColor: Record<string, string> = { coral: "var(--primary)", topic: "var(--topicblue-default)", draft: "var(--text-subtle)" };
  const toneBg: Record<string, string> = { coral: "var(--accent-surface)", topic: "var(--topicblue-light)", draft: "var(--oats-dark)" };
  // 数据已由后端按 selectedAccount 维度过滤（单账号视图仅含该账号排期项），此处直接按天分组渲染。
  const byDate: Record<number, { t: string; time: string; tone: string; acct: string }[]> = {};
  calendar.forEach((d) => { byDate[d.date] = d.items; });
  const m = month;
  const cells: (number | null)[] = [];
  for (let i = 0; i < m.firstOffset; i++) cells.push(null);
  for (let d = 1; d <= m.days; d++) cells.push(d);
  return (
    <section style={{ display: "flex", flexDirection: "column", gap: 10 }}>
      <PanelHead icon="calendar-days" title="内容日历 · 发布排期" sub={`${m.label} · ${accountFilter ? "该账号" : "跨账号矩阵"}排期`} right={<span style={{ display: "inline-flex", gap: 6, color: "var(--text-subtle)" }}><Icon name="chevron-left" size={15} /><Icon name="chevron-right" size={15} /></span>} />
      <Card padding="md">
        {loadState.calendar === "error" && <StateNote status="error" empty="" error="排期数据加载失败，请稍后重试" />}
        <div style={{ display: "grid", gridTemplateColumns: "repeat(7, 1fr)", gap: 5 }}>
          {WEEKDAYS.map((w) => <div key={w} style={{ textAlign: "center", fontSize: 10, fontWeight: 600, color: "var(--text-subtle)", paddingBottom: 4 }}>{w}</div>)}
          {cells.map((d, idx) => d === null
            ? <div key={"b" + idx} />
            : (
              <div key={d} data-testid={`calendar-day-${d}`} style={{ minHeight: 66, borderRadius: "var(--radius-sm)", border: "1px solid var(--border)", background: (byDate[d] && byDate[d].length) ? "var(--surface-card)" : "var(--oats-light)", padding: 4, display: "flex", flexDirection: "column", gap: 3 }}>
                <span style={{ fontSize: 10, color: "var(--text-subtle)", fontWeight: 600 }}>{d}</span>
                {(byDate[d] || []).map((it, i) => (
                  <div key={i} data-testid="calendar-item" style={{ background: toneBg[it.tone], borderLeft: `2px solid ${toneColor[it.tone]}`, borderRadius: 3, padding: "2px 3px" }}>
                    <div style={{ display: "flex", alignItems: "center", gap: 2 }}>
                      {it.acct && <span style={{ width: 11, height: 11, borderRadius: "999px", background: toneColor[it.tone], color: "#fff", fontSize: 7, display: "inline-flex", alignItems: "center", justifyContent: "center", flexShrink: 0 }}>{it.acct}</span>}
                      <div style={{ fontSize: 8, fontWeight: 600, color: "var(--text-body)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{it.t}</div>
                    </div>
                  </div>
                ))}
              </div>
            ))}
        </div>
        <div style={{ display: "flex", gap: 14, marginTop: 10, fontSize: 10, color: "var(--text-subtle)" }}>
          <span style={{ display: "inline-flex", alignItems: "center", gap: 4 }}><span style={{ width: 8, height: 8, borderRadius: 2, background: "var(--primary)" }} />已排期</span>
          <span style={{ display: "inline-flex", alignItems: "center", gap: 4 }}><span style={{ width: 8, height: 8, borderRadius: 2, background: "var(--topicblue-default)" }} />跨账号</span>
          <span style={{ display: "inline-flex", alignItems: "center", gap: 4 }}><span style={{ width: 8, height: 8, borderRadius: 2, background: "var(--text-subtle)" }} />草稿待定</span>
        </div>
      </Card>
    </section>
  );
}

// 数据回填
function BackfillSection({ sectionRef }: { sectionRef?: React.Ref<HTMLElement> }) {
  const { actions } = useStudio();
  const [vals, setVals] = useState<{ views: string; likes: string; saves: string; comments: string }>({ views: "", likes: "", saves: "", comments: "" });
  const set = (k: "views" | "likes" | "saves" | "comments") => (v: string) => setVals((p) => ({ ...p, [k]: v }));
  return (
    <section ref={sectionRef} style={{ display: "flex", flexDirection: "column", gap: 10 }}>
      <PanelHead icon="clipboard-pen" title="数据回填" sub="发布后录入真实表现，沉淀回飞书 → 训练下一轮选题" right={<Badge tone="info">效果反馈闭环</Badge>} />
      <Card padding="md">
        <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 12, marginBottom: 12 }}>
          <StatCard label="实际浏览量" value={vals.views} editable onValueChange={set("views")} />
          <StatCard label="点赞" value={vals.likes} editable onValueChange={set("likes")} tone="coral" />
          <StatCard label="收藏" value={vals.saves} editable onValueChange={set("saves")} tone="success" />
          <StatCard label="评论" value={vals.comments} editable onValueChange={set("comments")} />
        </div>
        <div style={{ display: "flex", justifyContent: "flex-end", gap: 8 }}>
          <Button variant="primary" size="sm" leftIcon={<Icon name="cloud-upload" size={13} />} onClick={() => actions.backfillSave({ views: vals.views, likes: vals.likes, collects: vals.saves, comments: vals.comments })}>保存并同步飞书</Button>
        </div>
      </Card>
    </section>
  );
}

// 发布管线 · 回链闭环（待发布 → 已发布·回链 → 已回填）
interface PublishPipelineProps {
  account?: Account | null;
}

function PipelineSection({ account }: PublishPipelineProps) {
  const { publishQueue, actions, loadState } = useStudio();
  // 队列已由后端按 selectedAccount 维度过滤，此处直接按 stage 分列渲染。
  void account;
  const q = publishQueue;
  const stages: { key: "scheduled" | "published" | "measured"; label: string; icon: string }[] = [
    { key: "scheduled", label: "待发布", icon: "clock" },
    { key: "published", label: "已发布 · 回链", icon: "link" },
    { key: "measured", label: "已回填", icon: "check-circle-2" },
  ];
  return (
    <section style={{ display: "flex", flexDirection: "column", gap: 10 }}>
      <PanelHead icon="git-branch" title="发布管线 · 回链闭环" sub="小红书无开放发布 API：人工/半自动发布后贴回链 → 拿到数据回填" right={<Badge tone="info">最后一公里</Badge>} />
      {loadState.pipeline !== "ready" && <StateNote status={loadState.pipeline} empty="暂无发布管线条目 · 排期/发布后展示" />}
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 12 }}>
        {stages.map((st) => {
          const items = q.filter((x) => x.stage === st.key);
          return (
            <Card key={st.key} padding="sm">
              <div style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 8 }}>
                <Icon name={st.icon} size={13} color="var(--text-muted)" />
                <span style={{ fontSize: 11, fontWeight: 700 }}>{st.label}</span>
                <span style={{ marginLeft: "auto", fontSize: 10, color: "var(--text-subtle)" }}>{items.length}</span>
              </div>
              <div style={{ display: "flex", flexDirection: "column", gap: 7 }}>
                {items.length === 0 && <span style={{ fontSize: 10, color: "var(--text-subtle)" }}>—</span>}
                {items.map((it) => (
                  <div key={it.id} style={{ border: "1px solid var(--border)", borderRadius: "var(--radius-sm)", padding: "7px 8px", background: "var(--oats-light)" }}>
                    <div style={{ display: "flex", alignItems: "center", gap: 5 }}>
                      <span style={{ width: 14, height: 14, borderRadius: 999, background: "var(--accent-surface)", color: "var(--primary)", fontSize: 8, fontWeight: 700, display: "inline-flex", alignItems: "center", justifyContent: "center", flexShrink: 0 }}>{it.acct}</span>
                      <span style={{ fontSize: 10, fontWeight: 600, color: "var(--text-body)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{it.title}</span>
                    </div>
                    <div style={{ fontSize: 9, color: "var(--text-subtle)", marginTop: 3, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{it.link ? `🔗 ${it.link}` : it.time}</div>
                    {st.key === "scheduled" && <Button variant="soft" size="sm" block style={{ marginTop: 6 }} leftIcon={<Icon name="send" size={11} />} onClick={() => actions.advanceStage(it, "published")}>标记已发 · 贴回链</Button>}
                    {st.key === "published" && <Button variant="soft" size="sm" block style={{ marginTop: 6 }} leftIcon={<Icon name="clipboard-pen" size={11} />} onClick={() => actions.advanceStage(it, "measured")}>回填数据</Button>}
                  </div>
                ))}
              </div>
            </Card>
          );
        })}
      </div>
    </section>
  );
}

function OpsInline() {
  return (
    <div className="cs" style={{ flex: 1, overflowY: "auto", background: "var(--background)" }}>
      <div style={{ maxWidth: 760, margin: "0 auto", padding: 24, display: "flex", flexDirection: "column", gap: 16 }}>
        <div style={{ textAlign: "center", fontSize: "var(--text-xs)", color: "var(--text-subtle)", background: "var(--oats-dark)", borderRadius: 999, padding: "5px 12px", alignSelf: "center" }}>一个会话里完成全部运营动作 · agent 驱动</div>
        <OpsBubble who="user">看下我账号本周的数据，再把下周选题排上。</OpsBubble>
        <OpsBubble who="ai">已从飞书拉取近 7 天数据。</OpsBubble>
        <StatsMini />
        <OpsBubble who="ai">帮你拆解了本周最高赞笔记的套路，并排好了下周内容日历。</OpsBubble>
        <Card padding="md"><CalInline /></Card>
        <OpsBubble who="user">发布后帮我回填真实数据。</OpsBubble>
        <OpsBubble who="ai">录入后会沉淀回飞书，用于优化下一轮选题。</OpsBubble>
        <BackfillSection />
      </div>
    </div>
  );
}

function OpsBubble({ who, children }: { who: "user" | "ai"; children: ReactNode }) {
  const user = who === "user";
  return (
    <div style={{ display: "flex", gap: 11, alignSelf: user ? "flex-end" : "flex-start", flexDirection: user ? "row-reverse" : "row", maxWidth: user ? "85%" : "94%" }}>
      {user ? <Avatar name="我" variant="solid" size={30} /> : <Avatar glyph="🍠" variant="agent" size={32} />}
      <div style={{ background: "var(--surface-card)", border: "1px solid var(--border-coral)", borderRadius: "var(--radius-xl)", padding: "11px 15px", fontSize: "var(--text-sm)", boxShadow: "var(--shadow-sm)", lineHeight: "var(--leading-relaxed)" }}>{children}</div>
    </div>
  );
}

function StatsMini() {
  const { dashboard, loadState } = useStudio();
  if (loadState.analytics !== "ready") return <Card padding="none"><StateNote status={loadState.analytics} empty="暂无表现数据 · 发布并回填后展示" /></Card>;
  return (
    <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 10 }}>
      {dashboard.map((d) => <StatCard key={d.label} label={d.label} value={d.value} unit={d.unit} delta={d.delta} tone={d.tone} icon={<Icon name={d.icon} size={15} />} />)}
    </div>
  );
}

function CalInline() {
  return <CalendarSection />;
}

function OpsHybrid() {
  const { actions } = useStudio();
  const [draft, setDraft] = useState("");
  return (
    <div style={{ flex: 1, display: "flex", minHeight: 0, background: "var(--background)" }}>
      <section style={{ width: 380, borderRight: "1px solid var(--border)", background: "var(--surface-card)", display: "flex", flexDirection: "column", flexShrink: 0 }}>
        <div className="cs" style={{ flex: 1, overflowY: "auto", padding: 18, display: "flex", flexDirection: "column", gap: 14 }}>
          <PanelHead icon="bot" title="运营助手" sub="发起动作 · 右侧看汇总" />
          <OpsBubble who="user">拉本周数据 + 排下周选题</OpsBubble>
          <OpsBubble who="ai">已更新右侧看板与日历，最高表现内容已进入拆解库。</OpsBubble>
          <OpsBubble who="user">把发布后的真实数据回填一下</OpsBubble>
          <OpsBubble who="ai">右侧「数据回填」已就绪，录入后同步飞书。</OpsBubble>
        </div>
        <div style={{ padding: 14, borderTop: "1px solid var(--border)" }}>
          <Textarea
            rows={1}
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            placeholder="发起运营动作…"
            footer={<><span style={{ fontSize: 10, color: "var(--text-subtle)" }}>agent 会更新右侧看板</span><Button variant="primary" size="sm" onClick={() => { if (draft.trim()) { actions.say(draft); setDraft(""); } }}>发送</Button></>}
          />
        </div>
      </section>
      <div className="cs" style={{ flex: 1, overflowY: "auto" }}><DashboardBody dense /></div>
    </div>
  );
}
