"use client";

// StudioProvider — the real bridge. Implements the prototype's useStudio()
// store contract on top of the LIVE production wiring: ThreadContext
// (submitText / useThreadDraftState draft / stream evidence / Ctrl+P
// commands), the parsed LangGraph stream, and the same-origin BFF
// (/api/backend/* · /api/me). NO mock business data — topics & evidence come
// from the real stream; ops collections come from /api/backend/*; the shell
// user comes from /api/me. Screens consume useStudio().

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import { toast } from "sonner";
import { useQueryState } from "nuqs";
import { useThread } from "@/components/thread/ThreadContext";
import { getContentString } from "@/components/thread/utils";
import { parseXhsBlocks } from "@/lib/xhs-blocks";
import { useBackendResource, type LoadStatus } from "./useBackendResource";
import {
  applyOptimisticSchedule,
  canAdvanceStage,
  deriveInitial,
  mapVersions,
  rollbackSchedule,
  selectVersionDraft,
  validateBackfillMetrics,
  type DraftVersionInput,
} from "./backend-mappers";
import type {
  Account,
  CalendarDay,
  ChatMsg,
  DashboardStat,
  EvidenceBundle,
  EvidenceItem,
  LibraryItem,
  MonthInfo,
  PublishItem,
  PublishStage,
  SelectedEvidence,
  StudioNote,
  StudioSection,
  StudioUser,
  Teardown,
  Topic,
  Trend,
  Versions,
  VersionId,
} from "./types";

/** 每个运营 collection 的加载/空态/错误态，驱动 UI 渲染骨架/空态文案/错误态。 */
export interface StudioLoadState {
  analytics: LoadStatus;
  calendar: LoadStatus;
  accounts: LoadStatus;
  library: LoadStatus;
  teardown: LoadStatus;
  pipeline: LoadStatus;
  trends: LoadStatus;
  images: LoadStatus;
}

export interface StudioStore {
  section: StudioSection;
  setSection: (s: StudioSection) => void;
  activeRecent: number | null;
  setActiveRecent: (id: number | null) => void;
  note: StudioNote;
  chatExtra: ChatMsg[];
  calendar: CalendarDay[];
  selectedEvidence: SelectedEvidence | null;
  topics: Topic[];
  evidence: Record<number, EvidenceBundle>;
  // shell + 账号运营 collections (real-sourced; see StudioProvider)
  user: StudioUser;
  images: string[];
  trends: Trend[];
  dashboard: DashboardStat[];
  library: LibraryItem[];
  teardown: Teardown;
  accounts: Account[];
  month: MonthInfo;
  publishQueue: PublishItem[];
  // account 维度 + 每 collection 加载态（真实数据驱动空态/错误态）
  selectedAccount: string | null;
  setSelectedAccount: (id: string | null) => void;
  loadState: StudioLoadState;
  actions: {
    setSection: (s: StudioSection) => void;
    chooseTopic: (topic: Topic, goSection?: StudioSection) => void;
    setVersion: (v: VersionId) => void;
    updateField: (field: keyof StudioNote, value: unknown) => void;
    addTag: (tag: string) => void;
    removeTag: (tag: string) => void;
    polish: () => void;
    shorten: () => void;
    addTags: () => void;
    schedule: (date: number) => void;
    syncFeishu: () => void;
    backfillSave: (metrics?: Record<string, unknown>) => void;
    advanceStage: (item: PublishItem, toStage: PublishStage) => void;
    reuse: (topicId: number) => void;
    newChat: () => void;
    say: (text: string) => void;
    toast: (msg: string) => void;
    openEvidence: (ev: SelectedEvidence) => void;
    closeEvidence: () => void;
  };
}

export const StudioContext = createContext<StudioStore | null>(null);

export function useStudio(): StudioStore {
  const ctx = useContext(StudioContext);
  if (!ctx) throw new Error("useStudio must be used within a StudioProvider");
  return ctx;
}

// ── 各 /api/backend/* GET 的响应体形状（顶层带 ok/account，业务字段如下）。 ──
interface AnalyticsData {
  dashboard?: DashboardStat[];
  library?: LibraryItem[];
  teardown?: Teardown;
}
interface CalendarData {
  month?: MonthInfo;
  calendar?: CalendarDay[];
}
interface AccountsData {
  accounts?: Account[];
}
interface PipelineData {
  queue?: PublishItem[];
}
interface TrendsData {
  trends?: Trend[];
}

const EMPTY_MONTH: MonthInfo = { label: "", days: 30, firstOffset: 0 };
const EMPTY_TEARDOWN: Teardown = { title: "", points: [] };

/** 由底层资源加载态 + 子集合是否为空，派生该 collection 的对外加载态。 */
function statusFor(resource: LoadStatus, empty: boolean): LoadStatus {
  if (resource === "loading" || resource === "idle" || resource === "error") return resource;
  return empty ? "empty" : "ready";
}

function pad2(n: number): string {
  return String(n).padStart(2, "0");
}

export function StudioProvider({ children }: { children: ReactNode }) {
  const t = useThread();
  const [section, setSectionRaw] = useQueryState("section");
  const [activeRecent, setActiveRecent] = useState<number | null>(null);

  // studio-overlay local state (the parts not owned by the canonical draft)
  const [topicId, setTopicId] = useState<number | null>(null);
  const [kw, setKw] = useState("");
  const [tags, setTags] = useState<string[]>([]);
  const [cover, setCover] = useState("");
  const [scheduled, setScheduled] = useState(false);
  const [activeVersion, setActiveVersion] = useState<VersionId>("A");
  const [selectedEvidence, setSelectedEvidence] = useState<SelectedEvidence | null>(null);

  // account 维度：null = 矩阵总览（跨账号聚合，requireAdmin）；指定 id = 单账号视图。
  const [selectedAccount, setSelectedAccount] = useState<string | null>(null);
  const accountParam = selectedAccount ?? undefined;

  // shell user — real session via /api/me（含 team/handle/fans，缺失字段后端已省略键）。
  const [user, setUser] = useState<StudioUser>({ name: "", team: "", initial: "", handle: "", fans: "" });

  // ── 账号运营 collections —— 全部经 useBackendResource 拉 /api/backend/*（真实数据）。 ──
  const analyticsRes = useBackendResource<AnalyticsData>(
    "/api/backend/analytics",
    { dashboard: [], library: [], teardown: EMPTY_TEARDOWN },
    { account: accountParam },
  );
  const calendarRes = useBackendResource<CalendarData>(
    "/api/backend/calendar",
    { month: EMPTY_MONTH, calendar: [] },
    { account: accountParam },
  );
  const accountsRes = useBackendResource<AccountsData>("/api/backend/accounts", { accounts: [] });
  const pipelineRes = useBackendResource<PipelineData>(
    "/api/backend/pipeline",
    { queue: [] },
    { account: accountParam },
  );
  const trendsRes = useBackendResource<TrendsData>("/api/backend/trends", { trends: [] });

  const dashboard = analyticsRes.data.dashboard ?? [];
  const library = analyticsRes.data.library ?? [];
  const teardown = analyticsRes.data.teardown ?? EMPTY_TEARDOWN;
  const month = calendarRes.data.month ?? EMPTY_MONTH;
  const accounts = accountsRes.data.accounts ?? [];
  const publishQueue = pipelineRes.data.queue ?? [];
  const trends = trendsRes.data.trends ?? [];
  // 暂无配图后端来源 —— 真实空容器（组件按 images.length 守卫，不渲染占位图）。
  const images: string[] = useMemo(() => [], []);

  // 内容日历本地态：以后端排期为准，schedule 写动作做乐观更新 / 失败回滚。
  const [calendar, setCalendar] = useState<CalendarDay[]>([]);
  useEffect(() => {
    setCalendar(calendarRes.data.calendar ?? []);
  }, [calendarRes.data]);

  const loadState: StudioLoadState = {
    analytics: statusFor(analyticsRes.status, dashboard.length === 0),
    calendar: statusFor(calendarRes.status, calendar.length === 0),
    accounts: statusFor(accountsRes.status, accounts.length === 0),
    library: statusFor(analyticsRes.status, library.length === 0),
    teardown: statusFor(analyticsRes.status, teardown.points.length === 0),
    pipeline: statusFor(pipelineRes.status, publishQueue.length === 0),
    trends: statusFor(trendsRes.status, trends.length === 0),
    images: images.length === 0 ? "empty" : "ready",
  };

  useEffect(() => {
    let alive = true;
    fetch("/api/me", { headers: { Accept: "application/json" } })
      .then((r) => r.json())
      .then((d) => {
        if (!alive || !d?.user) return;
        const u = d.user as { name?: string; team?: string; handle?: string; fans?: string };
        setUser({
          name: u.name ?? "",
          team: u.team ?? "",
          handle: u.handle ?? "",
          fans: u.fans ?? "",
          initial: deriveInitial(u.name ?? ""),
        });
      })
      .catch(() => {});
    return () => {
      alive = false;
    };
  }, []);

  const setSection = useCallback((s: StudioSection) => void setSectionRaw(s), [setSectionRaw]);
  // 白名单校验:URL ?section=任意值 不应被透传(消费组件 switch 不中会渲染空白)。
  const sectionVal: StudioSection =
    section === "create" || section === "deep" || section === "ops" ? section : "create";

  // ── derive the live note status from the real stream ──
  const status: StudioNote["status"] = t.isLoading
    ? "writing"
    : scheduled
      ? "scheduled"
      : t.draftTitle || t.draftContent
        ? "draft"
        : "idle";

  // 测试可观测钩子:暴露真实流是否在产出中,供 e2e 等流落定再导航(避免读流式中间态)。
  useEffect(() => {
    if (typeof window !== "undefined") {
      (window as unknown as { __XHS_STREAMING__?: boolean }).__XHS_STREAMING__ = t.isLoading;
    }
  }, [t.isLoading]);

  // ── multi-version draft + its backend resource id parsed from the live stream ──
  const { versions, copyResourceId } = useMemo(() => parseCopyFromMessages(t.messages), [t.messages]);

  const note: StudioNote = useMemo(
    () => ({
      topicId,
      kw,
      title: t.draftTitle,
      body: t.draftContent,
      tags,
      cover,
      status,
      activeVersion,
      versions,
    }),
    [topicId, kw, t.draftTitle, t.draftContent, tags, cover, status, activeVersion, versions],
  );

  // ── topics & evidence parsed from the LIVE stream (rich fields, no mock) ──
  const { topics, evidence } = useMemo(() => parseTopicsFromMessages(t.messages), [t.messages]);

  // 测试可观测钩子:暴露后端解析出的真实 topics 长度,供 e2e 断言「选题卡数 == topics 长度」
  // (需求 3.4)。仅写 window,生产无副作用。
  useEffect(() => {
    if (typeof window !== "undefined") {
      (window as unknown as { __XHS_TOPICS_LEN__?: number }).__XHS_TOPICS_LEN__ = topics.length;
    }
  }, [topics.length]);

  // ── chat transcript derived from the real messages ──
  const chatExtra: ChatMsg[] = useMemo(() => deriveChat(t.messages), [t.messages]);

  const showToast = useCallback((msg: string) => toast(msg), []);

  const chooseTopic = useCallback(
    (topic: Topic, goSection: StudioSection = "create") => {
      setTopicId(topic.id);
      setKw(topic.kw);
      setActiveRecent(topic.id);
      setActiveVersion("A");
      setSection(goSection);
      // real round-trip: ask the agent to write this topic into the draft
      t.submitText(`写第 ${topic.id} 个选题：${topic.title}`);
    },
    [setSection, t],
  );

  const updateField = useCallback(
    (field: keyof StudioNote, value: unknown) => {
      if (field === "title") t.setDraftTitle(String(value));
      else if (field === "body") t.setDraftContent(String(value));
      else if (field === "cover") setCover(String(value));
      else if (field === "kw") setKw(String(value));
      else if (field === "tags") setTags(value as string[]);
    },
    [t],
  );

  const addTag = useCallback((tag: string) => setTags((prev) => (prev.includes(tag) ? prev : [...prev, tag].slice(0, 10))), []);
  const removeTag = useCallback((tag: string) => setTags((prev) => prev.filter((x) => x !== tag)), []);

  // setVersion：从 note.versions 选 A/B/C，把对应版本 title/body 写回 canonical draft。
  const setVersion = useCallback(
    (v: VersionId) => {
      const draft = selectVersionDraft(versions, v);
      if (!draft) {
        showToast("该版本暂不可用");
        return;
      }
      t.setDraftTitle(draft.title);
      t.setDraftContent(draft.body);
      setActiveVersion(v);
    },
    [versions, t, showToast],
  );

  // schedule：乐观更新 + await POST /api/backend/schedule，成功保留、失败回滚。
  const schedule = useCallback(
    async (date: number) => {
      const snapshot = calendar;
      const time = "19:00";
      const acct = selectedAccount ?? "";
      const item = { t: (note.title || "新笔记").slice(0, 8), time, tone: "coral" as const, acct };
      setCalendar((cal) => applyOptimisticSchedule(cal, date, item));
      setScheduled(true);
      // 年/月取自当前展示的 month(后端 label 形如 "2026 年 6 月"),而非系统时钟 —— 否则
      // 当日历展示非当前月时,排期日期串会落到错误的月份/年份(M4)。解析失败回退 now。
      const ym = /(\d{4})\D+(\d{1,2})/.exec(month.label);
      const now = new Date();
      const yyyy = ym ? Number(ym[1]) : now.getFullYear();
      const mm = ym ? Number(ym[2]) : now.getMonth() + 1;
      const dateStr = `${yyyy}-${pad2(mm)}-${pad2(date)}`;
      try {
        const res = await fetch("/api/backend/schedule", {
          method: "POST",
          headers: { "Content-Type": "application/json", Accept: "application/json" },
          body: JSON.stringify({ resourceId: copyResourceId ?? "", date: dateStr, time, account: acct }),
        });
        const body = await res.json().catch(() => null);
        if (!res.ok || !body || body.ok === false) {
          throw new Error(body?.error || `排期失败（${res.status}）`);
        }
        showToast(`已定稿并排期到 ${date} 日 ${time}`);
        calendarRes.reload();
      } catch (err) {
        setCalendar(rollbackSchedule(snapshot));
        setScheduled(false);
        showToast(`排期失败：${err instanceof Error ? err.message : "未知错误"}`);
      }
    },
    [calendar, selectedAccount, note.title, copyResourceId, showToast, calendarRes, month.label],
  );

  // backfillSave：先本地校验（口径同后端 _clean_metrics），再 await POST /api/backend/backfill。
  const backfillSave = useCallback(
    async (metrics?: Record<string, unknown>) => {
      const payload = metrics ?? {};
      const validation = validateBackfillMetrics(payload);
      if (!validation.ok) {
        showToast(`回填校验失败：该字段需为非负数值（${validation.error}）`);
        return;
      }
      try {
        const res = await fetch("/api/backend/backfill", {
          method: "POST",
          headers: { "Content-Type": "application/json", Accept: "application/json" },
          body: JSON.stringify({ resourceId: copyResourceId ?? "", metrics: validation.cleaned }),
        });
        const body = await res.json().catch(() => null);
        if (!res.ok || !body || body.ok === false) {
          throw new Error(body?.error || `回填失败（${res.status}）`);
        }
        showToast("数据已回填并沉淀飞书");
        analyticsRes.reload();
        pipelineRes.reload();
      } catch (err) {
        showToast(`回填失败：${err instanceof Error ? err.message : "未知错误"}`);
      }
    },
    [copyResourceId, showToast, analyticsRes, pipelineRes],
  );

  // advanceStage：POST /api/backend/pipeline 推进发布管线 stage，成功后由 GET 重读真实 stage。
  const advanceStage = useCallback(
    async (item: PublishItem, toStage: PublishStage) => {
      const resourceId = item.resourceId;
      if (!resourceId) {
        showToast("无法定位该笔记的资源，暂不能推进");
        return;
      }
      // 客户端先按单向状态机守卫(scheduled→published→measured),逆向/跨级直接拦,
      // 不依赖后端兜底,与「发布管线 stage 不变量」一致。
      if (!canAdvanceStage(item.stage, toStage)) {
        showToast(`不能从「${item.stage}」推进到「${toStage}」`);
        return;
      }
      let link: string | undefined = item.link;
      if (toStage === "published" && (!link || !link.trim())) {
        const entered = typeof window !== "undefined" ? window.prompt("贴入小红书回链 URL") : null;
        if (!entered || !entered.trim()) {
          showToast("已取消：标记已发需要回链");
          return;
        }
        link = entered.trim();
      }
      try {
        const res = await fetch("/api/backend/pipeline", {
          method: "POST",
          headers: { "Content-Type": "application/json", Accept: "application/json" },
          body: JSON.stringify({ resourceId, toStage, link }),
        });
        const body = await res.json().catch(() => null);
        if (!res.ok || !body || body.ok === false) {
          throw new Error(body?.error || `推进失败（${res.status}）`);
        }
        showToast(toStage === "published" ? "已标记发布并贴回链" : "已推进至已回填");
        pipelineRes.reload();
      } catch (err) {
        showToast(`推进失败：${err instanceof Error ? err.message : "未知错误"}`);
      }
    },
    [showToast, pipelineRes],
  );

  const store: StudioStore = {
    section: sectionVal,
    setSection,
    activeRecent,
    setActiveRecent,
    note,
    chatExtra,
    calendar,
    selectedEvidence,
    topics,
    evidence,
    user,
    images,
    trends,
    dashboard,
    library,
    teardown,
    accounts,
    month,
    publishQueue,
    selectedAccount,
    setSelectedAccount,
    loadState,
    actions: {
      setSection,
      chooseTopic,
      setVersion,
      updateField,
      addTag,
      removeTag,
      polish: () => t.handleExecuteCommand("polish"),
      shorten: () => t.handleExecuteCommand("shorten"),
      addTags: () => t.handleExecuteCommand("tags"),
      schedule,
      syncFeishu: () => t.handleSyncToFeishu(),
      backfillSave,
      advanceStage,
      reuse: (id: number) => {
        const topic = topics.find((x) => x.id === id);
        if (topic) chooseTopic(topic);
      },
      newChat: () => {
        setTopicId(null);
        setKw("");
        setTags([]);
        setCover("");
        setScheduled(false);
        setActiveVersion("A");
        t.setThreadId(null);
        setSection("create");
      },
      say: (text: string) => t.submitText(text),
      toast: showToast,
      openEvidence: setSelectedEvidence,
      closeEvidence: () => setSelectedEvidence(null),
    },
  };

  return <StudioContext.Provider value={store}>{children}</StudioContext.Provider>;
}

// Parse the latest topic suggestions + per-topic evidence from the real stream.
// Consumes the rich xhs_topics schema (RichTopic + RichEvidence three-signal);
// rich fields are surfaced when present and omitted otherwise (no fabricated
// values / no 0 padding). hotRate is null when the backend can't derive it
// (the topic card then hides the 🔥 marker).
function parseTopicsFromMessages(messages: ReturnType<typeof useThread>["messages"]): {
  topics: Topic[];
  evidence: Record<number, EvidenceBundle>;
} {
  const topics: Topic[] = [];
  const evidence: Record<number, EvidenceBundle> = {};
  for (let i = messages.length - 1; i >= 0; i--) {
    const m = messages[i];
    if (m.type !== "ai") continue;
    // 经 getContentString 取文本:兼容 string 与 Anthropic /v1/messages 的内容块数组,
    // 否则数组态消息会被当空串丢弃 → xhs 代码块整块漏解析。
    const content = getContentString(m.content);
    if (!content) continue;
    const segs = parseXhsBlocks(content);
    const topicSeg = segs.find((s) => s.kind === "topics");
    if (topicSeg && topicSeg.kind === "topics") {
      topicSeg.data.topics.forEach((topic, idx) => {
        const id = idx + 1;
        const isRich = typeof topic !== "string";
        const title = typeof topic === "string" ? topic : topic.title;
        // 富字段：缺省即留空/留 null（隐藏 🔥），绝不写 0 占位。
        topics.push({
          id,
          title,
          rationale: isRich ? topic.rationale ?? "" : "",
          hotRate: isRich && typeof topic.hotRate === "number" ? topic.hotRate : null,
          angle: isRich ? topic.angle ?? "" : "",
          kw: isRich ? topic.kw ?? "" : "",
          emotional: isRich ? topic.emotional ?? "" : "",
          draft: { title: "", cover: "", body: "", tags: [] },
        });

        // 每选题独立证据：优先用富选题内 evidence；旧格式回退顶层共享证据。
        const richEvidence = isRich && topic.evidence ? topic.evidence : null;
        const mode: EvidenceBundle["mode"] = isRich && topic.evidence_mode ? topic.evidence_mode : "semantic";
        if (richEvidence) {
          const items: EvidenceItem[] = richEvidence.map((e) => ({
            resource_id: e.resource_id,
            type: e.type ?? "资源",
            title: e.title,
            summary: e.summary,
            score: e.score ?? 0,
            relevance: e.relevance ?? 0,
            freshness: e.freshness ?? 0,
            performance: e.performance ?? 0,
            source_updated_at: e.source_updated_at ?? "",
            indexed_at: e.indexed_at ?? "",
            why_selected: e.why_selected ?? "",
          }));
          const bundle: EvidenceBundle = { mode, items };
          if (isRich && typeof topic.gaps === "string" && topic.gaps) bundle.gaps = topic.gaps;
          // 数据不足或有证据条目都暴露 bundle（面板据 mode/gaps 渲染「当前数据不足」）。
          if (items.length || bundle.gaps || mode === "insufficient_relevance") evidence[id] = bundle;
        } else {
          const items: EvidenceItem[] = topicSeg.data.evidence.map((e) => ({
            resource_id: e.resource_id,
            type: "资源",
            title: e.title,
            summary: e.summary,
            score: 0,
            relevance: 0,
            freshness: 0,
            performance: 0,
            source_updated_at: e.source_updated_at ?? "",
            indexed_at: e.indexed_at ?? "",
            why_selected: "",
          }));
          if (items.length) evidence[id] = { mode, items };
        }
      });
      break;
    }
  }
  return { topics, evidence };
}

// Parse the latest xhs_copy block from the stream for multi-version drafts +
// the draft's backend resource id (used by the schedule / backfill writers).
// Robust: never throws; missing/invalid versions → null (single-version mode).
function parseCopyFromMessages(messages: ReturnType<typeof useThread>["messages"]): {
  versions: Partial<Versions> | null;
  copyResourceId: string | null;
} {
  // 与 xhs-blocks.ts 的 FENCE_RE 同口径:标签后允许换行或同行空格紧跟 JSON。
  // Claude 原生 /v1/messages 常把 JSON 写在 ```xhs_copy 同一行,旧的 \s*\n 会整块漏解析
  // → versions/copyResourceId 失效,排期/回填无法关联资源。
  const fence = /```xhs_copy[ \t]*\r?\n?([\s\S]*?)```/g;
  for (let i = messages.length - 1; i >= 0; i--) {
    const m = messages[i];
    if (m.type !== "ai") continue;
    // 经 getContentString 取文本:兼容 string 与 Anthropic /v1/messages 的内容块数组,
    // 否则数组态消息会被当空串丢弃 → xhs 代码块整块漏解析。
    const content = getContentString(m.content);
    if (!content) continue;
    fence.lastIndex = 0;
    let match: RegExpExecArray | null;
    let last: RegExpExecArray | null = null;
    while ((match = fence.exec(content)) !== null) last = match;
    if (!last) continue;
    try {
      const obj = JSON.parse(last[1].trim()) as Record<string, unknown>;
      const rawId = obj.resource_id ?? obj.resourceId;
      const copyResourceId = typeof rawId === "string" && rawId.trim() ? rawId.trim() : null;
      const versions = Array.isArray(obj.versions)
        ? mapVersions(obj.versions as DraftVersionInput[])
        : null;
      return { versions, copyResourceId };
    } catch {
      // 非法 JSON（流式未闭合等）→ 单版本，继续扫描更早的消息。
      continue;
    }
  }
  return { versions: null, copyResourceId: null };
}

function deriveChat(messages: ReturnType<typeof useThread>["messages"]): ChatMsg[] {
  const out: ChatMsg[] = [];
  for (const m of messages) {
    const content = getContentString(m.content);
    if (m.type === "human") out.push({ who: "user", text: content });
    else if (m.type === "ai" && content.trim()) out.push({ who: "ai", text: content });
  }
  return out;
}
