"use client";

// StudioProvider — the real bridge. Implements the prototype's useStudio()
// store contract on top of the LIVE production wiring: ThreadContext
// (submitText / useThreadDraftState draft / stream evidence / Ctrl+P
// commands), the parsed LangGraph stream, and the same-origin BFF
// (/api/backend/* · /api/me). NO mock business data — topics & evidence come
// from the real stream; ops collections come from /api/backend/*; the shell
// user comes from /api/me. Screens consume useStudio().

import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";
import { toast } from "sonner";
import { useQueryState } from "nuqs";
import { useThread, type HITLRequest, type HITLDecision } from "@/components/thread/ThreadContext";
import { getContentString } from "@/components/thread/utils";
import { parseXhsBlocks } from "@/lib/xhs-blocks";
import { useTraceContext } from "@/providers/trace-store";
import { useBackendResource, type LoadStatus } from "./useBackendResource";
import { deriveTimeline, type TimelineItem, type DiscoveryNote } from "@/lib/thinking-trace";
import { StudioContext } from "./useStudio";
import {
  applyOptimisticSchedule,
  canAdvanceStage,
  deriveInitial,
  mapVersions,
  rollbackSchedule,
  validateBackfillMetrics,
  type DraftVersionInput,
} from "./backend-mappers";
import type {
  Account,
  CalendarDay,
  DashboardStat,
  DetailTarget,
  EvidenceBundle,
  EvidenceItem,
  LibraryItem,
  MonthInfo,
  PublishItem,
  PublishStage,
  SelectedEvidence,
  StudioImitation,
  StudioNote,
  StudioProcess,
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
  timeline: TimelineItem[];
  /** 当前进度短语(最新思考链里正在做的那一步的真实 label);无思考链时 null。生成中动态文案用。 */
  progressLabel: string | null;
  calendar: CalendarDay[];
  selectedEvidence: SelectedEvidence | null;
  topics: Topic[];
  evidence: Record<number, EvidenceBundle>;
  // 右边栏素材工作台:检索出的参考素材笔记(线上+本地混排),从 timeline 的 discovery 项
  // 按 note_id 去重累积。区别于 topics(选题只进对话气泡)。
  materials: DiscoveryNote[];
  // 素材/选题详情弹层(统一 DetailModal):null=不显示。
  detail: DetailTarget | null;
  // 两段式仿写元信息(范本 + 第一段拆解);非仿写会话为 null。第二段成品走 note.versions。
  imitation: StudioImitation | null;
  // 标题优化候选(§4.5 TitleScreen):最新一次按公式生成的候选标题(LLM 产出);无则 null。
  titleSuggestions: { formula: string; candidates: string[] } | null;
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
    chooseTopic: (topic: Topic) => void;
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
    advanceStage: (item: PublishItem, toStage: PublishStage, linkInput?: string) => void;
    reuse: (topicId: number) => void;
    newChat: () => void;
    say: (text: string) => void;
    stop: () => void;
    toast: (msg: string) => void;
    openEvidence: (ev: SelectedEvidence) => void;
    closeEvidence: () => void;
    respondToInterrupt: (decisions: HITLDecision[]) => void;
    adoptNotes: (notes: DiscoveryNote[]) => void;
    // 素材栏搜索:发一条明确的「检索参考素材」指令给 agent(走 search_local_note_cards /
    // search_xhs_online 工具),命中的笔记作为 discovery 项流回、累积进 materials 工作台。
    searchMaterials: (query: string) => void;
    // 仿写:对单篇范本触发两段式仿写。本地已入库素材直接带 resource_id;线上未入库笔记
    // 同时直传 selected_notes(供后端先收录拿 id 再仿),满足「范本可追溯」§5。
    imitate: (note: DiscoveryNote) => void;
    // 统一详情/仿写弹层(素材或选题)。
    openDetail: (target: DetailTarget) => void;
    closeDetail: () => void;
  };
  // HITL 工具审批中断:非 null 时聊天区渲染审批卡,用户批准/驳回后经 respondToInterrupt 恢复。
  interrupt: HITLRequest | null;
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
  const { presentationsByTurnId } = useTraceContext();
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
  // 统一详情/仿写弹层目标(素材或选题);null=不显示。
  const [detail, setDetail] = useState<DetailTarget | null>(null);

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
  const backendCalendar = useMemo(() => calendarRes.data.calendar ?? [], [calendarRes.data.calendar]);
  const [calendarOverride, setCalendarOverride] = useState<{
    source: CalendarDay[];
    value: CalendarDay[];
  } | null>(null);
  const calendar = calendarOverride?.source === backendCalendar ? calendarOverride.value : backendCalendar;
  const setCalendar = useCallback(
    (updater: CalendarDay[] | ((current: CalendarDay[]) => CalendarDay[])) => {
      setCalendarOverride({
        source: backendCalendar,
        value: typeof updater === "function" ? updater(calendar) : updater,
      });
    },
    [backendCalendar, calendar],
  );

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

  // ── studio overlay 持久化(按 threadId 隔离) ──
  // 草稿 title/body 已由 useThreadDraftState 持久化;这里持久化不被草稿拥有的 overlay 态
  // (选题绑定 topicId / 关键词 kw / 标签 tags / 封面 cover / 当前版本 activeVersion)。
  // 此前这套态是裸 useState:刷新或切到别的会话再回来,正文虽能从消息流恢复,但选题绑定与
  // 版本选择全丢 → 用户看到的「生成的内容消失」。现在按 threadId 落本地、挂载/切会话时恢复。
  const prevOverlayThreadRef = useRef<string | null | undefined>(undefined);
  const overlayBootedRef = useRef(false);
  useEffect(() => {
    const prev = prevOverlayThreadRef.current;
    prevOverlayThreadRef.current = t.threadId;
    // 新建对话首次拿到 id(null→id),属于同一会话内容刚落定,不是切换 → 不动 overlay。
    if (prev === null && t.threadId != null) return;
    const snap = readStudioOverlay(t.threadId);
    // 刚切会话/挂载:跳过紧随其后的那次 persist,避免用旧值 transient 覆盖新会话已存快照。
    // 必须同步置位:persist effect 在同一渲染周期紧随本 effect 执行,依赖它已为 false。
    overlayBootedRef.current = false;
    // setState 延到微任务:满足 react-hooks/set-state-in-effect(禁止在 effect 同步体内直接
    // setState 触发级联渲染),与 useThreadDraftState 同款做法。行为等价——effect 本就会触发
    // 一次重渲染,微任务只是把它挪出同步体。
    queueMicrotask(() => {
      if (snap) {
        setTopicId(snap.topicId);
        setKw(snap.kw);
        setTags(snap.tags);
        setCover(snap.cover);
        setActiveVersion(snap.activeVersion);
      } else if (prev !== undefined) {
        // 切到一个无 overlay 记录的会话 → 重置默认,避免与上一会话串台。
        setTopicId(null);
        setKw("");
        setTags([]);
        setCover("");
        setActiveVersion("A");
      }
    });
  }, [t.threadId]);

  useEffect(() => {
    if (!overlayBootedRef.current) {
      overlayBootedRef.current = true;
      return;
    }
    writeStudioOverlay(t.threadId, {
      v: OVERLAY_LATEST_VERSION,
      topicId,
      kw,
      tags,
      cover,
      activeVersion,
    });
  }, [t.threadId, topicId, kw, tags, cover, activeVersion]);

  const setSection = useCallback((s: StudioSection) => void setSectionRaw(s), [setSectionRaw]);
  // 白名单校验:URL ?section=任意值 不应被透传(消费组件 switch 不中会渲染空白)。
  // v2 只剩 create/ops;历史 ?section=deep 链接归一到 create(深创已并入创作屏右栏)。
  const sectionVal: StudioSection = section === "ops" ? "ops" : "create";

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
  const { versions, copyResourceId, process, imitation } = useMemo(() => parseCopyFromMessages(t.messages), [t.messages]);

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
      process,
    }),
    [topicId, kw, t.draftTitle, t.draftContent, tags, cover, status, activeVersion, versions, process],
  );

  // ── topics & evidence parsed from the LIVE stream (rich fields, no mock) ──
  const { topics, evidence } = useMemo(() => parseTopicsFromMessages(t.messages), [t.messages]);

  // ── 标题优化候选:最新一个 xhs_titles 块(LLM 按公式产出的候选标题) ──
  const titleSuggestions = useMemo(() => parseTitlesFromMessages(t.messages), [t.messages]);

  // 测试可观测钩子:暴露后端解析出的真实 topics 长度,供 e2e 断言「选题卡数 == topics 长度」
  // (需求 3.4)。仅写 window,生产无副作用。
  useEffect(() => {
    if (typeof window !== "undefined") {
      (window as unknown as { __XHS_TOPICS_LEN__?: number }).__XHS_TOPICS_LEN__ = topics.length;
    }
  }, [topics.length]);

  // ── chat transcript as timeline items derived from the real messages ──
  const timeline: TimelineItem[] = useMemo(
    () =>
      deriveTimeline(t.messages, {
        loading: t.isLoading,
        error: t.error,
        tracePresentationsByTurnId: presentationsByTurnId,
      }),
    [t.messages, t.isLoading, t.error, presentationsByTurnId],
  );

  // 当前进度短语:取最新一条 thinking run 里"正在做的那一步"的真实 label(active 优先,
  // 否则取最后一个 done),用于生成中动态文案。全是真实工具调用派生,不编造进度。
  const progressLabel: string | null = useMemo(() => {
    for (let i = timeline.length - 1; i >= 0; i--) {
      const it = timeline[i];
      if (it.kind !== "thinking") continue;
      const steps = it.run.steps;
      const active = steps.find((s) => s.state === "active");
      if (active) return active.label;
      const done = [...steps].reverse().find((s) => s.state === "done");
      return done ? done.label : null;
    }
    return null;
  }, [timeline]);

  // ── 参考素材笔记:从 timeline 的 discovery 项按 note_id 去重累积 ──
  // 右边栏素材工作台专职展示这批(线上+本地混排);选题只进对话气泡,不进右栏(需求 §3)。
  // 累积而非只取最后一批:多轮检索的素材都留在工作台,不随对话滚走(需求 §1 痛点)。
  // 已入库(already_local)优先保留其记录(带 resource_id,可直接仿写)。
  const materials: DiscoveryNote[] = useMemo(() => {
    const byId = new Map<string, DiscoveryNote>();
    for (const item of timeline) {
      if (item.kind !== "discovery") continue;
      for (const n of item.notes) {
        const existing = byId.get(n.note_id);
        // 后到的同 id 覆盖(通常更新);但已带 resource_id/already_local 的记录不被无 id 的覆盖掉。
        if (!existing || (!existing.resource_id && n.resource_id) || (!existing.already_local && n.already_local)) {
          byId.set(n.note_id, { ...existing, ...n });
        }
      }
    }
    return Array.from(byId.values());
  }, [timeline]);

  // 测试可观测钩子:暴露思考链总步数,供 e2e 断言思考 UI 已渲染。仅写 window,生产无副作用。
  useEffect(() => {
    if (typeof window !== "undefined") {
      const steps = timeline.reduce(
        (n, it) => n + (it.kind === "thinking" ? it.run.steps.length : 0),
        0,
      );
      (window as unknown as { __XHS_THINKING_STEPS__?: number }).__XHS_THINKING_STEPS__ = steps;
    }
  }, [timeline]);

  const showToast = useCallback((msg: string) => toast(msg), []);

  const chooseTopic = useCallback(
    (topic: Topic) => {
      // 绑定选题总是执行(轻量本地态,无副作用)。v2:起稿不跳屏,留在 create,
      // 右栏随 note.status 从 idle → writing 原地变编辑器。
      setTopicId(topic.id);
      setKw(topic.kw);
      setActiveRecent(topic.id);
      setActiveVersion("A");
      setSection("create");

      // 「进入深度创作/写选题」与「触发生成」解耦,但必须**按选题区分**:
      // - 重进**当前已绑定、且已生成过内容的同一选题** → 保留,绝不重跑(否则退出再进就把
      //   已生成的 A/B 版覆盖重写,历史反馈的坑,commit 77af33e)。
      // - 换成**另一个选题**(或同选题但还没内容)→ 必须重新生成。此前守卫只看"本会话有没有
      //   任何文案",不看是哪个选题的 → 生成过选题 A 后点选题 B,守卫误判"已有文案"直接早返回,
      //   B 永不生成、深创页还显示 A 的旧正文(用户报告的 bug:新选题点进去是以前的东西)。
      // topicId 此刻仍是**上一次绑定**的选题(本次 setTopicId 的更新还没生效到这个闭包)。
      const sameTopicAsLoaded = topicId === topic.id;
      const alreadyHasCopy = Boolean(t.draftTitle.trim() || t.draftContent.trim() || versions);
      if (sameTopicAsLoaded && alreadyHasCopy) return;

      // 换了不同选题 → 先清掉上一个选题的残留草稿(标题/正文/标签/封面),避免新选题生成期间
      // 编辑器还显示上一个选题的旧文案。清空后 status 进 writing → 显示"正在生成",B 的文案流
      // 到后由 parseCopyFromMessages 取最新块填入,与选题 B 对齐。
      if (!sameTopicAsLoaded) {
        t.setDraftTitle("");
        t.setDraftContent("");
        setTags([]);
        setCover("");
      }

      // 首次生成:经官方 state-update 通道把选中选题卡的**权威依据**直传 graph(与 adoptNotes
      // 同机制,完全不经 LLM 转写)。带上卡片上展示的 evidence(含真实 resource_id):后端
      // save_generated_topic 经 InjectedState("selected_topic") 读它落库,主控委派
      // copywriting-coprocessor 时也从中取 resource_id 让子代理 get_resource 精读对标原文。
      // 缺了这一传递,主控拿不到真实 id 只能凭空编造 → 子代理精读必然 "not found"(历史根因)。
      // 字段形状对齐后端 _clean_evidence:resource_id/title/summary/source_updated_at/indexed_at。
      const bundle = evidence[topic.id];
      const selectedEvidence = (bundle?.items ?? []).map((it) => ({
        resource_id: it.resource_id,
        title: it.title,
        summary: it.summary,
        source_updated_at: it.source_updated_at,
        indexed_at: it.indexed_at,
      }));
      t.submitText(`写第 ${topic.id} 个选题：${topic.title}`, {
        selected_topic: { topic: topic.title, evidence: selectedEvidence },
      });
    },
    [setSection, t, evidence, versions, topicId],
  );

  // 采纳用户在发现卡勾选的笔记:经官方 state-update 通道把 selected_notes 直传 graph
  // (不经 LLM 转写),后端 adopt_online_notes 用 InjectedState 读它落库,成功后按 prompt
  // 走出选题流程。文本只给指令,笔记数据走 stateUpdate。
  const adoptNotes = useCallback(
    (notes: DiscoveryNote[]) => {
      if (!notes.length) return;
      t.submitText(
        "请采纳我在面板勾选的这些线上笔记(收录入库),然后基于这批 + 本地相关内容出选题。",
        { selected_notes: notes },
      );
    },
    [t],
  );

  // 素材栏搜索:用户在参考素材工作台输入关键词,发一条明确的「只检索参考素材、先别出选题/写文案」
  // 指令给 agent。agent 走检索工具(本地笔记卡 + 线上),命中的笔记以 discovery 项流回,由
  // materials 去重累积到工作台(不覆盖已入库记录)。留在 create,不跳屏。这是走 deepagents 工具
  // 机制的真实检索,不在前端造假 seed 池。
  const searchMaterials = useCallback(
    (query: string) => {
      const q = query.trim();
      if (!q) return;
      setSection("create");
      t.submitText(`帮我检索「${q}」相关的参考素材笔记(本地库 + 线上都找),只把找到的笔记列出来放进参考素材工作台,先不要出选题、也先别写文案。`);
    },
    [setSection, t],
  );

  // 仿写:对单篇范本触发两段式仿写(§5)。经 state 直传 selected_reference(权威标识,不经
  // LLM 转写);v2 留在创作屏——仿写流一起,右栏随 status 原地变编辑器,顶部仿写拆解横幅显性
  // 呈现第一段套路,成品在下方编辑器。
  // · 本地已入库素材(有 resource_id):直接带 resource_id,后端可即刻 get_resource 精读范本。
  // · 线上未入库笔记(无 resource_id):同时直传 selected_notes,后端先 adopt 收录拿 id 再仿
  //   (满足「范本可追溯」——线上笔记仿写要求范本能追溯到库内一条真实素材)。
  const imitate = useCallback(
    (note: DiscoveryNote) => {
      if (!note || !note.note_id) return;
      setSection("create");
      const label = note.title ? `《${note.title}》` : "这篇";
      if (note.resource_id) {
        t.submitText(`照着${label}的套路,仿写成我自己的一篇。先拆解它的选题方向与套路,再据此写成品。`, {
          selected_reference: { resource_id: note.resource_id, note },
        });
      } else {
        // 线上未入库:范本本身作为 selected_notes 直传,后端先收录拿 id 再仿。
        t.submitText(`照着${label}的套路,仿写成我自己的一篇(这是线上笔记,请先收录入库以便可追溯,再拆解套路写成品)。`, {
          selected_reference: { note },
          selected_notes: [note],
        });
      }
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
  // 切版本时连 tags/cover 一起回写——否则编辑区 + 右侧体检面板会拿到「A 版正文 + 全局 tags」
  // 的混搭(打分/字数错位、排版看似混乱)。每个版本作为完整一体回写,体检始终对齐当前版。
  const setVersion = useCallback(
    (v: VersionId) => {
      const ver = versions?.[v];
      if (!ver) {
        showToast("该版本暂不可用");
        return;
      }
      t.setDraftTitle(ver.title);
      t.setDraftContent(ver.body);
      setTags(ver.tags);
      setCover(ver.cover);
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
        setCalendarOverride(null);
        calendarRes.reload();
      } catch (err) {
        setCalendar(rollbackSchedule(snapshot));
        setScheduled(false);
        showToast(`排期失败：${err instanceof Error ? err.message : "未知错误"}`);
      }
    },
    [calendar, selectedAccount, note.title, copyResourceId, showToast, calendarRes, month.label, setCalendar],
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
    async (item: PublishItem, toStage: PublishStage, linkInput?: string) => {
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
      // 回链由调用方(发布管线的内联输入框)传入,不再用 window.prompt 阻塞式弹窗打断页面。
      // 已有 link 直接沿用;标记已发但既无既有 link 又无传入 link 时,提示需要回链后返回,
      // 由 UI 展开内联输入框收集(非阻塞)。
      let link: string | undefined = item.link;
      if (toStage === "published" && (!link || !link.trim())) {
        const entered = (linkInput ?? "").trim();
        if (!entered) {
          showToast("已取消：标记已发需要回链");
          return;
        }
        link = entered;
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

  // polish：走既有 handleExecuteCommand("polish") 真实润色流式链路（R5.2 已接入）。
  // R5.3 失败态：
  //  · 异步失败/超时 —— submitText → stream.submit 的错误经 ThreadStateProvider 监听
  //    stream.error 的副作用统一弹 toast（与 chooseTopic/say/schedule/backfill 同源的
  //    失败提示模式），polish 天然继承。
  //  · 同步抛错 —— 此处 try/catch 兜底，避免事件处理器内未捕获抛出而无任何用户可见提示。
  //  · 草稿保全 —— 全程不写 draftTitle/draftContent；草稿仅由成功的 AI 响应经
  //    useThreadDraftState.parseAiDraft 派生更新，失败时用户既有草稿保持不变
  //    （不产生部分写入或状态丢失）。
  const polish = useCallback(() => {
    try {
      t.handleExecuteCommand("polish");
    } catch (err) {
      showToast(`润色失败：${err instanceof Error ? err.message : "未知错误"}`);
    }
  }, [t, showToast]);

  const store: StudioStore = {
    section: sectionVal,
    setSection,
    activeRecent,
    setActiveRecent,
    note,
    timeline,
    progressLabel,
    calendar,
    selectedEvidence,
    topics,
    evidence,
    materials,
    detail,
    imitation,
    titleSuggestions,
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
      polish,
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
      stop: () => t.stopGeneration(),
      toast: showToast,
      openEvidence: setSelectedEvidence,
      closeEvidence: () => setSelectedEvidence(null),
      respondToInterrupt: t.respondToInterrupt,
      adoptNotes,
      searchMaterials,
      imitate,
      openDetail: setDetail,
      closeDetail: () => setDetail(null),
    },
    interrupt: t.interrupt,
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
    // 流式未闭合(isPending)时,局部解析器对**富选题对象数组**只能按引号乱抓,会把
    // title/hotRate/angle/evidence/resource_id 等 key+value 打散成一堆碎字符串 —— 直接当选题
    // 渲染就是"一张卡里全是字段名"的糊屏(用户实测)。故只认**完整闭合并成功 JSON 解析**的
    // 选题块(isPending 为假)才产出卡片;流式期不出卡(顶部思考链/生成条已表明在进行),
    // 块闭合后一次性出正确的富选题卡。与 xhs_copy 只认闭合块取 versions 同策略。
    if (topicSeg && topicSeg.kind === "topics" && !topicSeg.isPending) {
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

// Parse the latest xhs_titles block (title-optimization candidates by formula).
// Returns null when none present. Robust: never throws.
function parseTitlesFromMessages(
  messages: ReturnType<typeof useThread>["messages"],
): { formula: string; candidates: string[] } | null {
  for (let i = messages.length - 1; i >= 0; i--) {
    const m = messages[i];
    if (m.type !== "ai") continue;
    const content = getContentString(m.content);
    if (!content) continue;
    for (const seg of parseXhsBlocks(content)) {
      if (seg.kind === "titles" && seg.data.candidates.length) return seg.data;
    }
  }
  return null;
}

// Parse the latest xhs_copy / xhs_imitation block from the stream for multi-version
// drafts + the draft's backend resource id (schedule / backfill writers) + 两段式仿写
// 的第一段拆解(teardown)。xhs_imitation 与 xhs_copy 成品结构同构,额外携带 teardown/
// reference_* —— 取两类块里**最后出现**的那个(最新产出)。Robust: never throws.
function parseCopyFromMessages(messages: ReturnType<typeof useThread>["messages"]): {
  versions: Partial<Versions> | null;
  copyResourceId: string | null;
  process: StudioProcess | null;
  imitation: StudioImitation | null;
} {
  // 与 xhs-blocks.ts 的 FENCE_RE 同口径:标签后允许换行或同行空格紧跟 JSON(兼容 Claude 同行写法)。
  // 同时匹配 xhs_copy 与 xhs_imitation,捕获组 1=lang、组 2=JSON。
  const fence = /```(xhs_copy|xhs_imitation)[ \t]*\r?\n?([\s\S]*?)```/g;
  for (let i = messages.length - 1; i >= 0; i--) {
    const m = messages[i];
    // 回合边界:遇到用户消息即停,只取**本轮**的成品块(versions/仿写拆解/创作过程)。否则换选题
    // 生成期间会回捞上一个选题的 xhs_copy → A·B 对比/创作过程显示上一个选题的旧版本(与草稿正文
    // 同源的"新选题显示旧内容"问题)。与 latestDraftFromMessages 同边界口径。
    if (m.type === "human") break;
    if (m.type !== "ai") continue;
    // 经 getContentString 取文本:兼容 string 与 Anthropic /v1/messages 的内容块数组。
    const content = getContentString(m.content);
    if (!content) continue;
    fence.lastIndex = 0;
    let match: RegExpExecArray | null;
    let last: RegExpExecArray | null = null;
    while ((match = fence.exec(content)) !== null) last = match;
    if (!last) continue;
    const lang = last[1];
    try {
      const obj = JSON.parse(last[2].trim()) as Record<string, unknown>;
      const rawId = obj.resource_id ?? obj.resourceId;
      const copyResourceId = typeof rawId === "string" && rawId.trim() ? rawId.trim() : null;
      const versions = Array.isArray(obj.versions)
        ? mapVersions(obj.versions as DraftVersionInput[])
        : null;
      // 创作过程(outline + ai_audit_log)与成品同块携带,供"创作过程"抽屉回看;不进正文。
      const outline = typeof obj.outline === "string" ? obj.outline : "";
      const auditRaw = obj.ai_audit_log ?? obj.ai_audit_self_correction_log;
      const audit = typeof auditRaw === "string" ? auditRaw : "";
      const process = outline || audit ? { outline, audit } : null;
      // 仿写块:解析第一段拆解(teardown)+ 范本标识,供深创页显性呈现"它凭什么这么仿"。
      let imitation: StudioImitation | null = null;
      if (lang === "xhs_imitation") {
        const td = obj.teardown;
        const refId = obj.reference_resource_id;
        if (td && typeof td === "object") {
          const t = td as Record<string, unknown>;
          const str = (v: unknown) => (typeof v === "string" ? v : "");
          imitation = {
            referenceResourceId: typeof refId === "string" ? refId : "",
            referenceTitle: typeof obj.reference_title === "string" ? obj.reference_title : "",
            teardown: {
              angle: str(t.angle),
              painpoint: str(t.painpoint),
              hook_mechanism: str(t.hook_mechanism),
              structure: str(t.structure),
            },
          };
        }
      }
      return { versions, copyResourceId, process, imitation };
    } catch {
      // 非法 JSON（流式未闭合等）→ 继续扫描更早的消息。
      continue;
    }
  }
  return { versions: null, copyResourceId: null, process: null, imitation: null };
}

// ── studio overlay 本地持久化(按 threadId 隔离) ──────────────────────────────
// 与 useThreadDraftState 的草稿 autosave 同思路:每个会话一份 overlay 快照,
// 刷新/切会话后据此恢复选题绑定、版本选择、标签等,避免「内容消失」。
const OVERLAY_LATEST_VERSION = 1;

interface StudioOverlaySnapshot {
  v: number;
  topicId: number | null;
  kw: string;
  tags: string[];
  cover: string;
  activeVersion: VersionId;
}

function buildStudioOverlayKey(threadId: string | null): string {
  return `xhs_studio_overlay_${threadId ?? "new"}`;
}

function readStudioOverlay(threadId: string | null): StudioOverlaySnapshot | null {
  if (typeof window === "undefined") return null;
  // null threadId = 会话 id 尚未落定的临时态,不读不写,避免新会话误继承上次的 overlay。
  if (threadId == null) return null;
  try {
    const raw = window.localStorage.getItem(buildStudioOverlayKey(threadId));
    if (!raw) return null;
    const o = JSON.parse(raw) as Partial<StudioOverlaySnapshot>;
    const av = o.activeVersion;
    return {
      v: OVERLAY_LATEST_VERSION,
      topicId: typeof o.topicId === "number" ? o.topicId : null,
      kw: typeof o.kw === "string" ? o.kw : "",
      tags: Array.isArray(o.tags) ? o.tags.filter((x): x is string => typeof x === "string") : [],
      cover: typeof o.cover === "string" ? o.cover : "",
      activeVersion: av === "A" || av === "B" || av === "C" ? av : "A",
    };
  } catch {
    return null;
  }
}

function writeStudioOverlay(threadId: string | null, snap: StudioOverlaySnapshot): void {
  if (typeof window === "undefined") return;
  // 同 readStudioOverlay:null threadId 不落本地。
  if (threadId == null) return;
  try {
    window.localStorage.setItem(buildStudioOverlayKey(threadId), JSON.stringify(snap));
  } catch {
    // localStorage 不可用/超限 → 静默降级,不影响创作主流程。
  }
}
