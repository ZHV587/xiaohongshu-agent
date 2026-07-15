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
import {
  deriveTimeline,
  parseLatestAdoption,
  adoptedNoteResourceIdentities,
  mergeDiscoveryMaterials,
  type TimelineItem,
  type DiscoveryNote,
  type AdoptionOutcome,
} from "@/lib/thinking-trace";
import { StudioContext } from "./useStudio";
import {
  parseCurrentDocumentBinding,
  resolveLifecycleWriteBinding,
  resolveCurrentDocumentBinding,
  validateBindingAgainstLifecycle,
  type CurrentDocumentBinding,
} from "./current-document-binding";
import {
  applyOptimisticSchedule,
  canAdvanceStage,
  deriveInitial,
  copyLifecycleSnapshot,
  mapVersions,
  mapLifecycleVersions,
  parseCopyLifecycle,
  rollbackSchedule,
  validateBackfillMetrics,
  type DraftVersionInput,
} from "./backend-mappers";
import type {
  Account,
  CalendarDay,
  CopyLifecycle,
  DashboardStat,
  DetailTarget,
  DraftVersion,
  EvidenceBundle,
  EvidenceItem,
  LibraryItem,
  MonthInfo,
  PublishItem,
  PublishStage,
  ScheduleVersionContract,
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
  // 右栏是否处于深度编辑器态。只由显式创作意图(点选题起稿/仿写)或本轮已产出成品(versions)
  // 决定 —— 不看 t.isLoading,故纯搜索/出选题不会翻成编辑器。
  editing: boolean;
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
  /** 当前 generated_copy 的后端权威生命周期；未加载/旧稿缺 ID 时为 null。 */
  copyLifecycle: CopyLifecycle | null;
  copyLifecycleStatus: LoadStatus;
  loadState: StudioLoadState;
  actions: {
    setSection: (s: StudioSection) => void;
    chooseTopic: (topic: Topic) => void;
    setVersion: (v: VersionId) => void;
    adoptVersion: (v: VersionId) => void;
    updateField: (field: keyof StudioNote, value: unknown) => void;
    addTag: (tag: string) => void;
    removeTag: (tag: string) => void;
    polish: () => void;
    shorten: () => void;
    addTags: () => void;
    schedule: (date: number) => void;
    syncFeishu: () => void;
    backfillSave: (target: PublishItem, metrics?: Record<string, unknown>) => void;
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
    // 关闭收录结果弹窗(记住本次 callId,不再自动重弹)。
    dismissAdoptionModal: () => void;
    // 重试收录失败的笔记(把失败项重新走 adoptNotes;需从 materials 回取原始笔记数据)。
    retryFailedAdoptions: () => void;
  };
  // 收录(adopt_online_notes)结果弹窗:最新一次采纳的结局(成功/跳过/失败逐条 + 计数);
  // 无采纳、结果为空、或用户已手动关闭本次结果 → null。驱动居中「收录完成」结果弹窗。
  adoptionModal: AdoptionOutcome | null;
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

function positiveInteger(value: unknown): number | null {
  return typeof value === "number" && Number.isInteger(value) && value > 0 ? value : null;
}

class StudioWriteError extends Error {
  constructor(message: string, readonly status: number) {
    super(message);
  }
}

export function StudioProvider({ children }: { children: ReactNode }) {
  const t = useThread();
  const documentThreadId = t.threadId ?? "__new__";
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
  const [copyLifecycle, setCopyLifecycle] = useState<CopyLifecycle | null>(null);
  const [copyLifecycleStatus, setCopyLifecycleStatus] = useState<LoadStatus>("idle");
  const [currentDocumentBinding, setCurrentDocumentBinding] =
    useState<CurrentDocumentBinding | null>(null);
  // 用户修订会生成新的不可变 resource_version；流里的原始 xhs_copy 不会被改写，故按
  // A/B/C 保存后端确认后的修订快照，后续采纳/排期始终使用精确版本与对应内容。
  const [revisionSnapshots, setRevisionSnapshots] = useState<Partial<Record<VersionId, DraftVersion>>>({});
  const lifecycleWriteBusyRef = useRef(false);
  const dirtyScheduleAttemptRef = useRef<{ fingerprint: string; requestId: string } | null>(null);
  const [hasLocalEdits, setHasLocalEdits] = useState(false);
  const localEditsRef = useRef(false);
  // 创作意图开关:右栏是否切成深度编辑器,只由「点选题起稿 / 点仿写」显式置真
  // (chooseTopic/imitate),newChat/切到无记录会话复位。绝不看 t.isLoading —— 否则纯搜索
  // /出选题(也在跑流)会误把右栏从「参考素材栏」翻成编辑器,即用户报的「搜索就弹创作 UI」bug。
  // 按 threadId 持久化进 overlay,刷新/切回同一会话仍在编辑态。
  const [creationMode, setCreationMode] = useState(false);
  const [selectedEvidence, setSelectedEvidence] = useState<SelectedEvidence | null>(null);
  // 统一详情/仿写弹层目标(素材或选题);null=不显示。
  const [detail, setDetail] = useState<DetailTarget | null>(null);
  // 已手动关闭的收录结果 callId:用户点「关闭」后记住本次采纳的 tool_call_id,不再自动重弹
  // (下一次新采纳的 callId 不同 → 会重新弹)。
  const [dismissedAdoptionId, setDismissedAdoptionId] = useState<string | null>(null);

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
  const selectedAccountRecord = accounts.find((item) => item.id === selectedAccount);
  const writingContextState = useMemo(
    () => ({
      current_account_id: selectedAccount,
      current_niche: selectedAccountRecord?.writingNiche ?? null,
    }),
    [selectedAccount, selectedAccountRecord?.writingNiche],
  );
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
        setCreationMode(snap.creationMode);
        setScheduled(snap.scheduled);
        setHasLocalEdits(snap.hasLocalEdits);
        setCurrentDocumentBinding(snap.currentDocumentBinding);
        localEditsRef.current = snap.hasLocalEdits;
      } else if (prev !== undefined) {
        // 切到一个无 overlay 记录的会话 → 重置默认,避免与上一会话串台。
        setTopicId(null);
        setKw("");
        setTags([]);
        setCover("");
        setActiveVersion("A");
        setCreationMode(false);
        // scheduled 同样按会话隔离复位:否则会话 A 排期成功后切到会话 B,editing 派生仍为 true,
        // 右栏误弹深度编辑器(「没点选题/仿写也弹创作 UI」的残留形态)。
        setScheduled(false);
        setHasLocalEdits(false);
        setCurrentDocumentBinding(null);
        localEditsRef.current = false;
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
      creationMode,
      scheduled,
      hasLocalEdits,
      currentDocumentBinding,
    });
  }, [t.threadId, topicId, kw, tags, cover, activeVersion, creationMode, scheduled, hasLocalEdits, currentDocumentBinding]);

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
  const parsedCopy = useMemo(() => parseCopyFromMessages(t.messages), [t.messages]);
  const { versions, process, imitation } = parsedCopy;
  const streamDocumentBinding = useMemo(
    () => parseCurrentDocumentBinding({
      ownerThreadId: documentThreadId,
      resourceId: parsedCopy.copyResourceId,
      resourceVersion: parsedCopy.copyResourceVersion,
      stateVersion: parsedCopy.copyStateVersion,
    }),
    [documentThreadId, parsedCopy.copyResourceId, parsedCopy.copyResourceVersion, parsedCopy.copyStateVersion],
  );
  const pendingDocumentBinding = useMemo(
    () => {
      const candidate = resolveCurrentDocumentBinding(streamDocumentBinding, currentDocumentBinding);
      return candidate?.ownerThreadId === documentThreadId ? candidate : null;
    },
    [documentThreadId, streamDocumentBinding, currentDocumentBinding],
  );
  // Stream identity is only the candidate used for lifecycle GET.  Mutations never use
  // it directly; they remain bound to the last lifecycle-verified exact document.
  const pendingResourceId = pendingDocumentBinding?.resourceId ?? null;
  const verifiedDocumentBinding = currentDocumentBinding?.ownerThreadId === documentThreadId
    ? currentDocumentBinding
    : null;
  const copyResourceId = verifiedDocumentBinding?.resourceId ?? null;
  const lifecycleWriteBinding = useMemo(
    () => resolveLifecycleWriteBinding(
      pendingDocumentBinding,
      verifiedDocumentBinding,
      copyLifecycle,
      copyLifecycleStatus === "ready",
      documentThreadId,
    ),
    [pendingDocumentBinding, verifiedDocumentBinding, copyLifecycle, copyLifecycleStatus, documentThreadId],
  );
  const visibleVersions = useMemo<Partial<Versions> | null>(() => {
    // lifecycle 一旦就绪，UI 只展示后端 exact snapshots；绝不再把流里的旧 A/B/C
    // 与已修订版本混合。加载失败时流版本仅供只读预览，所有写动作仍被状态闸门禁用。
    if (copyLifecycle) {
      return Object.keys(revisionSnapshots).length ? revisionSnapshots : null;
    }
    if (!versions && Object.keys(revisionSnapshots).length === 0) return null;
    return { ...(versions ?? {}), ...revisionSnapshots };
  }, [copyLifecycle, versions, revisionSnapshots]);

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
      versions: visibleVersions,
      process,
      resourceId: copyResourceId,
    }),
    [topicId, kw, t.draftTitle, t.draftContent, tags, cover, status, activeVersion, visibleVersions, process, copyResourceId],
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
  // 全流程已成功采纳的 note_id → resource_id 映射:采纳成功后,素材栏对应卡应立即标「已收录」
  // (already_local)并带上真实 resource_id(可直接仿写,不必再走「先收录再仿」)。这也让底部
  // 「收录选中 N 篇」的可采纳集合把刚入库的排除掉,不会重复勾选采纳。
  const adoptedIdentities = useMemo(() => adoptedNoteResourceIdentities(t.messages), [t.messages]);

  const materials: DiscoveryNote[] = useMemo(() => {
    return mergeDiscoveryMaterials(timeline, adoptedIdentities);
  }, [timeline, adoptedIdentities]);

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
  const setCanonicalTitle = t.setDraftTitle;
  const setCanonicalBody = t.setDraftContent;
  const setLocalEditState = useCallback((dirty: boolean) => {
    // 响应丢失后的同稿重试必须复用幂等键；只有用户再次编辑才废弃上一次尝试。
    if (dirty) dirtyScheduleAttemptRef.current = null;
    localEditsRef.current = dirty;
    setHasLocalEdits(dirty);
  }, []);

  const applyAuthoritativeLifecycle = useCallback((lifecycle: CopyLifecycle) => {
    const authoritativeVersions = mapLifecycleVersions(lifecycle);
    const selectedSnapshot = copyLifecycleSnapshot(lifecycle, lifecycle.selectedVersion);
    const selectedEntry = (Object.entries(authoritativeVersions) as Array<[VersionId, DraftVersion]>).find(
      ([, snapshot]) => snapshot.resourceVersion === lifecycle.selectedVersion,
    );
    setCopyLifecycle(lifecycle);
    setCurrentDocumentBinding({
      ownerThreadId: documentThreadId,
      resourceId: lifecycle.resourceId,
      resourceVersion: lifecycle.selectedVersion ?? lifecycle.latestResourceVersion,
      stateVersion: lifecycle.stateVersion,
    });
    setRevisionSnapshots(authoritativeVersions);
    setCopyLifecycleStatus(lifecycle.selectedVersion == null || selectedEntry ? "ready" : "error");
    // 本地未保存编辑优先：权威状态/快照照常更新，但画布只在干净时切到 selected exact snapshot。
    if (!localEditsRef.current && selectedSnapshot) {
      if (selectedEntry) setActiveVersion(selectedEntry[0]);
      setCanonicalTitle(selectedSnapshot.title);
      setCanonicalBody(selectedSnapshot.body);
      setTags([...selectedSnapshot.tags]);
      setCover(selectedSnapshot.cover);
      setLocalEditState(false);
    }
  }, [documentThreadId, setCanonicalBody, setCanonicalTitle, setLocalEditState]);

  const requestCopyLifecycle = useCallback(async (
    binding: CurrentDocumentBinding,
    signal?: AbortSignal,
  ): Promise<CopyLifecycle> => {
    const { resourceId } = binding;
    const res = await fetch(`/api/backend/copies/${encodeURIComponent(resourceId)}/lifecycle`, {
      headers: { Accept: "application/json" },
      cache: "no-store",
      signal,
    });
    const payload = await res.json().catch(() => null);
    const lifecycle = parseCopyLifecycle(payload?.lifecycle);
    if (!res.ok || payload?.ok === false || !lifecycle) {
      throw new Error(payload?.error || `版本状态加载失败（${res.status}）`);
    }
    if (lifecycle.resourceId !== resourceId) throw new Error("版本状态与当前文案不匹配");
    if (!validateBindingAgainstLifecycle(binding, lifecycle)) {
      throw new Error("版本状态不包含当前成品的精确版本");
    }
    return lifecycle;
  }, []);

  // xhs_copy 只提供 ID/精确候选版本；selected/adopted/stateVersion 一律回读后端权威状态。
  useEffect(() => {
    const controller = new AbortController();
    queueMicrotask(() => {
      setCopyLifecycle(null);
      setRevisionSnapshots({});
      setCopyLifecycleStatus(pendingResourceId ? "loading" : "idle");
    });
    if (!pendingDocumentBinding) return () => controller.abort();
    void requestCopyLifecycle(pendingDocumentBinding, controller.signal)
      .then((lifecycle) => {
        if (controller.signal.aborted) return;
        applyAuthoritativeLifecycle(lifecycle);
      })
      .catch((error) => {
        if (controller.signal.aborted || (error instanceof DOMException && error.name === "AbortError")) return;
        setCopyLifecycle(null);
        setCopyLifecycleStatus("error");
      });
    return () => controller.abort();
  }, [applyAuthoritativeLifecycle, pendingDocumentBinding, pendingResourceId, requestCopyLifecycle]);

  const refreshCopyLifecycle = useCallback(async (): Promise<CopyLifecycle | null> => {
    if (!pendingDocumentBinding) return null;
    setCopyLifecycleStatus("loading");
    try {
      const lifecycle = await requestCopyLifecycle(pendingDocumentBinding);
      applyAuthoritativeLifecycle(lifecycle);
      return lifecycle;
    } catch {
      setCopyLifecycle(null);
      setCopyLifecycleStatus("error");
      return null;
    }
  }, [applyAuthoritativeLifecycle, pendingDocumentBinding, requestCopyLifecycle]);

  const chooseTopic = useCallback(
    (topic: Topic) => {
      // 绑定选题总是执行(轻量本地态,无副作用)。v2:起稿不跳屏,留在 create,
      // 右栏随 note.status 从 idle → writing 原地变编辑器。
      setTopicId(topic.id);
      setKw(topic.kw);
      setActiveRecent(topic.id);
      setSection("create");
      // 显式进入创作态:右栏此刻起变深度编辑器(区别于搜索/出选题只更新对话与素材栏)。
      setCreationMode(true);

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
      // 这是明确的新成品意图：先解除上一份文档绑定。后续只有新 xhs_copy 的 exact identity
      // 能建立新绑定，绝不把上一选题的 resourceId 带进本轮。
      setCurrentDocumentBinding(null);
      setActiveVersion("A");

      // 换了不同选题 → 先清掉上一个选题的残留草稿(标题/正文/标签/封面),避免新选题生成期间
      // 编辑器还显示上一个选题的旧文案。清空后 status 进 writing → 显示"正在生成",B 的文案流
      // 到后由 parseCopyFromMessages 取最新块填入,与选题 B 对齐。
      if (!sameTopicAsLoaded) {
        setLocalEditState(false);
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
      // 字段形状对齐后端 _clean_evidence，并保留不可变的 (resource_id, resource_version)。
      const bundle = evidence[topic.id];
      const selectedEvidence = (bundle?.items ?? []).map((it) => ({
        resource_id: it.resource_id,
        resource_version: it.resource_version,
        title: it.title,
        summary: it.summary,
        source_updated_at: it.source_updated_at,
        indexed_at: it.indexed_at,
      }));
      t.submitText(`写第 ${topic.id} 个选题：${topic.title}`, {
        ...writingContextState,
        selected_topic: { topic: topic.title, evidence: selectedEvidence },
      });
    },
    [setLocalEditState, setSection, t, evidence, versions, topicId, writingContextState],
  );

  // 采纳用户在发现卡勾选的笔记:经官方 state-update 通道把 selected_notes 直传 graph
  // (不经 LLM 转写),后端 adopt_online_notes 用 InjectedState 读它落库,成功后按 prompt
  // 走出选题流程。文本只给指令,笔记数据走 stateUpdate。
  const adoptNotes = useCallback(
    (notes: DiscoveryNote[]) => {
      if (!notes.length) return;
      t.submitText(
        "请采纳我在面板勾选的这些线上笔记(收录入库),然后基于这批 + 本地相关内容出选题。",
        { ...writingContextState, selected_notes: notes },
      );
    },
    [t, writingContextState],
  );

  // ── 收录结果弹窗:最新一次 adopt_online_notes 的结局(计数 + 逐条 + 失败项) ──
  // 写类工具的结果此前无 UI 消费(只在思考链显示中文 label),用户点「收录」后屏上毫无反馈。
  // 这里把结果解析成结局对象,失败行的 title 从素材栏(materials)回填(后端失败行只回带 note_id)。
  const latestAdoption = useMemo(() => parseLatestAdoption(t.messages), [t.messages]);
  const adoptionModal: AdoptionOutcome | null = useMemo(() => {
    if (!latestAdoption) return null;
    // 用户已手动关闭本次结果(按 callId 去重)→ 不再自动重弹。重试会产生新 callId,自动重新出现。
    if (latestAdoption.callId === dismissedAdoptionId) return null;
    // 失败行标题回填:后端失败行只回带 note_id,尽量用素材栏里的真实标题让用户认得是哪篇。
    const byId = new Map(materials.map((m) => [m.note_id, m] as const));
    const rows = latestAdoption.rows.map((r) => {
      if (r.outcome !== "failed") return r;
      const mat = byId.get(r.note_id);
      return mat && mat.title ? { ...r, title: mat.title } : r;
    });
    return { ...latestAdoption, rows };
  }, [latestAdoption, dismissedAdoptionId, materials]);

  const dismissAdoptionModal = useCallback(() => {
    if (latestAdoption) setDismissedAdoptionId(latestAdoption.callId);
  }, [latestAdoption]);

  // 重试收录失败项:从素材栏按 note_id 回取原始笔记数据,重新走 adoptNotes(产生新 callId,
  // 结果弹窗自动重新出现)。素材栏已无该笔记(理论上罕见)则跳过,至少不报错。
  const retryFailedAdoptions = useCallback(() => {
    if (!adoptionModal || adoptionModal.failedNoteIds.length === 0) return;
    const byId = new Map(materials.map((m) => [m.note_id, m] as const));
    const notes = adoptionModal.failedNoteIds
      .map((id) => byId.get(id))
      .filter((n): n is DiscoveryNote => !!n);
    if (!notes.length) {
      showToast("找不到失败笔记的原始数据,请回素材栏重新勾选收录");
      return;
    }
    // 关闭当前结果弹窗(会被新采纳的结果替换),重发采纳。
    setDismissedAdoptionId(adoptionModal.callId);
    t.submitText(
      "请重新采纳我上次收录失败的这些线上笔记(仅这几篇,收录入库即可)。",
      { ...writingContextState, selected_notes: notes },
    );
  }, [adoptionModal, materials, t, showToast, writingContextState]);

  // 素材栏搜索:用户在参考素材工作台输入关键词,发一条明确的「只检索参考素材、先别出选题/写文案」
  // 指令给 agent。agent 走检索工具(本地笔记卡 + 线上),命中的笔记以 discovery 项流回,由
  // materials 去重累积到工作台(不覆盖已入库记录)。留在 create,不跳屏。这是走 deepagents 工具
  // 机制的真实检索,不在前端造假 seed 池。
  const searchMaterials = useCallback(
    (query: string) => {
      const q = query.trim();
      if (!q) return;
      setSection("create");
      t.submitText(`帮我检索「${q}」相关的参考素材笔记(本地库 + 线上都找),只把找到的笔记列出来放进参考素材工作台,先不要出选题、也先别写文案。`, writingContextState);
    },
    [setSection, t, writingContextState],
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
      // 仿写同样是显式创作意图:右栏切成编辑器(顶部仿写拆解横幅 + 下方成品)。
      setCreationMode(true);
      setLocalEditState(false);
      // 仿写每次都创建新成品，必须显式解除上一份 current-document binding。
      setCurrentDocumentBinding(null);
      // 先清掉上一次创作/仿写的残留草稿(标题/正文/标签/封面)。仿写每次都是全新成品,无「重进
      // 同一篇不重跑」的场景 —— 不清会在新仿写流出前一直显示上一篇的旧正文(与 chooseTopic 换选题
      // 同类的「新意图显示旧内容」泄漏;配合 useThreadDraftState 的 `_new` 槽守卫一并根治)。
      t.setDraftTitle("");
      t.setDraftContent("");
      setTags([]);
      setCover("");
      const label = note.title ? `《${note.title}》` : "这篇";
      if (
        typeof note.resource_id === "string" &&
        note.resource_id.trim().length > 0 &&
        Number.isInteger(note.resource_version) &&
        (note.resource_version ?? 0) > 0
      ) {
        t.submitText(`照着${label}的套路,仿写成我自己的一篇。先拆解它的选题方向与套路,再据此写成品。`, {
          ...writingContextState,
          selected_reference: {
            resource_id: note.resource_id,
            resource_version: note.resource_version,
            note,
          },
        });
      } else {
        // 线上未入库:范本本身作为 selected_notes 直传,后端先收录拿 id 再仿。
        t.submitText(`照着${label}的套路,仿写成我自己的一篇(这是线上笔记,请先收录入库以便可追溯,再拆解套路写成品)。`, {
          ...writingContextState,
          selected_reference: { note },
          selected_notes: [note],
        });
      }
    },
    [setLocalEditState, setSection, t, writingContextState],
  );
  // 注:setTags/setCover 是 useState setter,恒稳定(React 保证),无需列入 imitate 依赖;
  // t 已在依赖内(其 setDraft* 亦稳定)。此处保持与 chooseTopic 同样的依赖口径。

  const updateField = useCallback(
    (field: keyof StudioNote, value: unknown) => {
      setLocalEditState(true);
      if (field === "title") t.setDraftTitle(String(value));
      else if (field === "body") t.setDraftContent(String(value));
      else if (field === "cover") setCover(String(value));
      else if (field === "kw") setKw(String(value));
      else if (field === "tags") setTags(value as string[]);
    },
    [setLocalEditState, t],
  );

  const addTag = useCallback((tag: string) => {
    setLocalEditState(true);
    setTags((previous) => previous.includes(tag) ? previous : [...previous, tag].slice(0, 10));
  }, [setLocalEditState]);
  const removeTag = useCallback((tag: string) => {
    setLocalEditState(true);
    setTags((previous) => previous.filter((item) => item !== tag));
  }, [setLocalEditState]);

  const currentVersionSnapshot = useCallback(
    (v: VersionId): DraftVersion | undefined => visibleVersions?.[v],
    [visibleVersions],
  );

  const postCopyLifecycle = useCallback(
    async (action: "select" | "revision" | "adopt", payload: Record<string, unknown>): Promise<CopyLifecycle> => {
      const res = await fetch(`/api/backend/copies/${action}`, {
        method: "POST",
        headers: { "Content-Type": "application/json", Accept: "application/json" },
        body: JSON.stringify(payload),
      });
      const body = await res.json().catch(() => null);
      const lifecycle = parseCopyLifecycle(body?.lifecycle);
      if (
        !res.ok || body?.ok === false || !lifecycle ||
        lifecycle.resourceId !== payload.resourceId
      ) {
        throw new StudioWriteError(body?.error || `版本操作失败（${res.status}）`, res.status);
      }
      return lifecycle;
    },
    [],
  );

  const handleLifecycleConflict = useCallback(async () => {
    await refreshCopyLifecycle();
    showToast("文案版本已在别处更新，已刷新状态，请重试");
  }, [refreshCopyLifecycle, showToast]);

  const draftDiffersFromSnapshot = useCallback(
    (v: VersionId): boolean => {
      const saved = currentVersionSnapshot(v);
      if (!saved) return false;
      return (
        t.draftTitle !== saved.title ||
        t.draftContent !== saved.body ||
        JSON.stringify(tags) !== JSON.stringify(saved.tags) ||
        cover !== saved.cover
      );
    },
    [cover, currentVersionSnapshot, t.draftTitle, t.draftContent, tags],
  );

  /** 只在“采用”这一明确边界保存一次不可变修订；输入期间绝不逐键写库。 */
  const saveRevisionAtBoundary = useCallback(
    async (v: VersionId, lifecycle: CopyLifecycle): Promise<CopyLifecycle> => {
      const saved = currentVersionSnapshot(v);
      if (!saved || v !== activeVersion || !draftDiffersFromSnapshot(v)) return lifecycle;
      const revised = await postCopyLifecycle("revision", {
        resourceId: lifecycle.resourceId,
        expectedResourceVersion: lifecycle.latestResourceVersion,
        expectedStateVersion: lifecycle.stateVersion,
        title: t.draftTitle,
        body: t.draftContent,
        tags,
        cover,
        note: saved.note,
        label: saved.label || v,
        ...(selectedAccount ? { account: selectedAccount } : {}),
      });
      if (!revised.selectedVersion) throw new StudioWriteError("修订未返回精确版本", 502);
      setLocalEditState(false);
      applyAuthoritativeLifecycle(revised);
      return revised;
    },
    [activeVersion, applyAuthoritativeLifecycle, cover, currentVersionSnapshot, draftDiffersFromSnapshot, postCopyLifecycle, selectedAccount, setLocalEditState, t.draftTitle, t.draftContent, tags],
  );

  // 切版本身是一个保存边界：当前版有编辑时必须先追加不可变修订，再用修订响应里的
  // 新 stateVersion 选择目标版。整个序列串行执行，任一步失败都保留当前画布。
  const setVersion = useCallback(
    async (v: VersionId) => {
      if (lifecycleWriteBusyRef.current) {
        showToast("版本操作正在处理中，请稍候");
        return;
      }
      const target = currentVersionSnapshot(v);
      if (!target) {
        showToast("该版本暂不可用");
        return;
      }
      if (v === activeVersion) return;

      const currentDirty = draftDiffersFromSnapshot(activeVersion);
      if (!lifecycleWriteBinding || !copyLifecycle || !target.resourceVersion) {
        if (currentDirty) {
          showToast("当前版本有未保存编辑，但缺少可追溯版本状态，不能切换以免丢失内容");
          return;
        }
        // 历史消息缺生命周期时仍允许只读对比；明确提示该选择不会写入后端。
        t.setDraftTitle(target.title);
        t.setDraftContent(target.body);
        setTags(target.tags);
        setCover(target.cover);
        setActiveVersion(v);
        setLocalEditState(false);
        showToast("该旧草稿缺少精确版本信息，本次只做本地预览");
        return;
      }

      lifecycleWriteBusyRef.current = true;
      try {
        const ready = currentDirty
          ? await saveRevisionAtBoundary(activeVersion, copyLifecycle)
          : copyLifecycle;
        const selected = await postCopyLifecycle("select", {
          resourceId: lifecycleWriteBinding.resourceId,
          resourceVersion: target.resourceVersion,
          expectedStateVersion: ready.stateVersion,
          label: target.label || v,
        });
        setLocalEditState(false);
        // POST 返回的 exact snapshot 是唯一画布来源；流里的 target 只用于提交其已验证版本号。
        applyAuthoritativeLifecycle(selected);
      } catch (error) {
        if (error instanceof StudioWriteError && error.status === 409) {
          await handleLifecycleConflict();
        } else {
          showToast(`版本切换失败：${error instanceof Error ? error.message : "未知错误"}`);
        }
      } finally {
        lifecycleWriteBusyRef.current = false;
      }
    },
    [activeVersion, applyAuthoritativeLifecycle, copyLifecycle, currentVersionSnapshot, draftDiffersFromSnapshot, handleLifecycleConflict, lifecycleWriteBinding, postCopyLifecycle, saveRevisionAtBoundary, setLocalEditState, showToast, t],
  );

  const adoptVersion = useCallback(
    async (v: VersionId) => {
      if (lifecycleWriteBusyRef.current) {
        showToast("版本操作正在处理中，请稍候");
        return;
      }
      const saved = currentVersionSnapshot(v);
      if (!lifecycleWriteBinding || !copyLifecycle || !saved?.resourceVersion) {
        showToast("当前草稿缺少可追溯的资源版本，暂不能采用");
        return;
      }
      lifecycleWriteBusyRef.current = true;
      try {
        const wasDirty = v === activeVersion && draftDiffersFromSnapshot(v);
        const ready = await saveRevisionAtBoundary(v, copyLifecycle);
        const resourceVersion = wasDirty && ready.selectedVersion
          ? ready.selectedVersion
          : saved.resourceVersion;
        const adopted = await postCopyLifecycle("adopt", {
          resourceId: lifecycleWriteBinding.resourceId,
          resourceVersion,
          expectedStateVersion: ready.stateVersion,
          ...(selectedAccount ? { account: selectedAccount } : {}),
        });
        setLocalEditState(false);
        applyAuthoritativeLifecycle(adopted);
        showToast("已采用此版本，后续会按该精确版本沉淀与回填");
      } catch (error) {
        if (error instanceof StudioWriteError && error.status === 409) {
          await handleLifecycleConflict();
        } else {
          showToast(`采用失败：${error instanceof Error ? error.message : "未知错误"}`);
        }
      } finally {
        lifecycleWriteBusyRef.current = false;
      }
    },
    [activeVersion, applyAuthoritativeLifecycle, copyLifecycle, currentVersionSnapshot, draftDiffersFromSnapshot, handleLifecycleConflict, lifecycleWriteBinding, postCopyLifecycle, saveRevisionAtBoundary, selectedAccount, setLocalEditState, showToast],
  );

  // schedule：乐观更新 + await POST /api/backend/schedule，成功保留、失败回滚。
  const schedule = useCallback(
    async (date: number) => {
      if (lifecycleWriteBusyRef.current) {
        showToast("版本操作正在处理中，请稍候再排期");
        return;
      }
      const selected = currentVersionSnapshot(activeVersion);
      if (!lifecycleWriteBinding) {
        showToast("这篇草稿没有后端资源标识，无法安全排期，请重新生成后再试");
        return;
      }
      if (!selected?.resourceVersion) {
        showToast("当前版本缺少精确版本号，无法排期，不能用其他版本代替");
        return;
      }
      if (!copyLifecycle) {
        showToast("版本状态尚未就绪，暂不能排期，请稍后重试");
        return;
      }
      if (copyLifecycle.selectedVersion !== selected.resourceVersion) {
        showToast("当前画布版本与后端选中版本不一致，已刷新版本状态，请重新排期");
        await handleLifecycleConflict();
        return;
      }
      const snapshot = calendar;
      const time = "19:00";
      const acct = selectedAccount ?? "";
      if (!acct) {
        showToast("请先选择要发布的小红书账号");
        return;
      }
      lifecycleWriteBusyRef.current = true;
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
      const dirty = draftDiffersFromSnapshot(activeVersion);
      // 目标快照与 latest 并发基线是两个独立维度：即使用户选回历史 A 版，也必须从
      // 该 selected 精确快照追加最终修订，同时用 latest/state 阻止并发覆盖。
      const versionContract: ScheduleVersionContract = {
        targetResourceVersion: selected.resourceVersion,
        expectedLatestResourceVersion: copyLifecycle.latestResourceVersion,
        expectedStateVersion: copyLifecycle.stateVersion,
      };
      const finalDraft = dirty ? {
        title: note.title,
        body: note.body,
        tags: note.tags,
        cover: note.cover,
        note: selected.note,
      } : null;
      // requestId 绑定一次“脏稿定稿尝试”：同一内容、同一目标快照与 CAS 基线在网络
      // 失败/响应丢失后继续复用；任一版本维度变化时才生成新的 UUID。
      const attemptFingerprint = finalDraft == null ? null : JSON.stringify({
        resourceId: lifecycleWriteBinding.resourceId,
        ...versionContract,
        date: dateStr,
        time,
        account: acct,
        finalDraft,
      });
      let requestId: string | null = null;
      try {
        if (attemptFingerprint != null) {
          const existingAttempt = dirtyScheduleAttemptRef.current;
          if (existingAttempt?.fingerprint === attemptFingerprint) {
            requestId = existingAttempt.requestId;
          } else {
            requestId = crypto.randomUUID();
            dirtyScheduleAttemptRef.current = { fingerprint: attemptFingerprint, requestId };
          }
        }
        const res = await fetch("/api/backend/schedule", {
          method: "POST",
          headers: { "Content-Type": "application/json", Accept: "application/json" },
          body: JSON.stringify({
            resourceId: lifecycleWriteBinding.resourceId,
            ...versionContract,
            date: dateStr,
            time,
            account: acct,
            ...(finalDraft == null ? {} : { finalDraft, requestId }),
          }),
        });
        const body = await res.json().catch(() => null);
        if (!res.ok || !body || body.ok === false) {
          throw new StudioWriteError(body?.error || `排期失败（${res.status}）`, res.status);
        }
        const finalizedVersion = positiveInteger(body?.scheduled?.resourceVersion);
        const nextStateVersion = positiveInteger(body?.scheduled?.stateVersion);
        if (!finalizedVersion || !nextStateVersion) throw new StudioWriteError("排期响应缺少精确版本状态", 502);
        // schedule 响应不携带版本快照；定稿成功后必须回读 GET，不能在前端合成“权威”版本。
        dirtyScheduleAttemptRef.current = null;
        setLocalEditState(false);
        await refreshCopyLifecycle();
        showToast(`已定稿并排期到 ${date} 日 ${time}`);
        setCalendarOverride(null);
        calendarRes.reload();
      } catch (err) {
        setCalendar(rollbackSchedule(snapshot));
        setScheduled(false);
        // 4xx 表示本次完整排期意图已被服务端明确拒绝，下一次点击必须使用新 key；
        // 只有网络错误、响应丢失或 5xx 才保留 key，以便安全重放同一 payload。
        if (err instanceof StudioWriteError && err.status >= 400 && err.status < 500) {
          dirtyScheduleAttemptRef.current = null;
        }
        if (err instanceof StudioWriteError && err.status === 409) {
          await handleLifecycleConflict();
        } else {
          showToast(`排期失败：${err instanceof Error ? err.message : "未知错误"}`);
        }
      } finally {
        lifecycleWriteBusyRef.current = false;
      }
    },
    [activeVersion, calendar, selectedAccount, note.title, note.body, note.tags, note.cover, copyLifecycle, currentVersionSnapshot, draftDiffersFromSnapshot, handleLifecycleConflict, lifecycleWriteBinding, refreshCopyLifecycle, setLocalEditState, showToast, calendarRes, month.label, setCalendar],
  );

  // backfillSave：先本地校验（口径同后端 _clean_metrics），再 await POST /api/backend/backfill。
  const backfillSave = useCallback(
    async (target: PublishItem, metrics?: Record<string, unknown>) => {
      const payload = metrics ?? {};
      const validation = validateBackfillMetrics(payload);
      if (!validation.ok) {
        showToast(`回填校验失败：该字段需为非负数值（${validation.error}）`);
        return;
      }
      if (target.stage !== "published") {
        showToast("只能给发布管线中“已发布”的文案回填表现");
        return;
      }
      if (!target.resourceId || !target.resourceVersion) {
        showToast("所选发布条目缺少精确文案版本，暂不能回填表现");
        return;
      }
      try {
        const res = await fetch("/api/backend/backfill", {
          method: "POST",
          headers: { "Content-Type": "application/json", Accept: "application/json" },
          body: JSON.stringify({
            resourceId: target.resourceId,
            resourceVersion: target.resourceVersion,
            metrics: validation.cleaned,
          }),
        });
        const body = await res.json().catch(() => null);
        if (!res.ok || !body || body.ok === false) {
          throw new StudioWriteError(body?.error || `回填失败（${res.status}）`, res.status);
        }
        showToast("数据已回填并沉淀飞书");
        analyticsRes.reload();
        pipelineRes.reload();
      } catch (err) {
        if (err instanceof StudioWriteError && err.status === 409) {
          pipelineRes.reload();
          showToast("所选发布版本已变化，已刷新发布队列，请重新选择");
        } else {
          showToast(`回填失败：${err instanceof Error ? err.message : "未知错误"}`);
        }
      }
    },
    [showToast, analyticsRes, pipelineRes],
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
          body: JSON.stringify({ resourceId, resourceVersion: item.resourceVersion, toStage, link }),
        });
        const body = await res.json().catch(() => null);
        if (!res.ok || !body || body.ok === false) {
          throw new Error(body?.error || `推进失败（${res.status}）`);
        }
        showToast(toStage === "published" ? "已标记发布并贴回链" : "已推进至已回填");
        pipelineRes.reload();
        if (resourceId === copyResourceId) void refreshCopyLifecycle();
      } catch (err) {
        showToast(`推进失败：${err instanceof Error ? err.message : "未知错误"}`);
      }
    },
    [copyResourceId, refreshCopyLifecycle, showToast, pipelineRes],
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

  // 右栏编辑器态:显式创作意图,或本轮真的产出了成品(versions),或已定稿排期。
  // 与「有没有流在跑」彻底解耦 —— 搜索/出选题期间 t.isLoading 为真但这里仍为假,右栏留在素材栏。
  const editing = creationMode || note.versions != null || scheduled;

  const store: StudioStore = {
    section: sectionVal,
    setSection,
    activeRecent,
    setActiveRecent,
    note,
    editing,
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
    copyLifecycle,
    copyLifecycleStatus,
    loadState,
    actions: {
      setSection,
      chooseTopic,
      setVersion,
      adoptVersion,
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
        setLocalEditState(false);
        // 复位创作态:新会话回到「先搜索/出选题」的参考素材栏,不直接进编辑器。
        setCreationMode(false);
        t.setThreadId(null);
        setSection("create");
      },
      say: (text: string) => t.submitText(text, writingContextState),
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
      dismissAdoptionModal,
      retryFailedAdoptions,
    },
    adoptionModal,
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

        // 统一检索证据只接受完整 EvidencePackage 子契约：精确身份、四项质量信号和
        // retrieval_mode 缺一不可。旧顶层共享 evidence 没有质量信号，不能再补 0 冒充证据。
        const richEvidence = isRich && Array.isArray(topic.evidence) ? topic.evidence : null;
        const mode = isRich ? topic.retrieval_mode : undefined;
        if (richEvidence && mode) {
          const items: EvidenceItem[] = richEvidence.map((e) => ({
            resource_id: e.resource_id,
            resource_version: e.resource_version,
            type: e.type,
            asset_kind: e.asset_kind,
            source_kind: e.source_kind,
            ...(e.niche ? { niche: e.niche } : {}),
            title: e.title,
            summary: e.summary,
            score: e.score,
            quality: e.quality,
            relevance: e.relevance,
            freshness: e.freshness,
            performance: e.performance,
            source_updated_at: e.source_updated_at,
            indexed_at: e.indexed_at,
            retrieval_sources: e.retrieval_sources,
            why_selected: e.why_selected,
          }));
          const bundle: EvidenceBundle = { mode, items };
          if (isRich && typeof topic.gaps === "string" && topic.gaps) bundle.gaps = topic.gaps;
          // 数据不足或有证据条目都暴露 bundle（面板据 mode/gaps 渲染「当前数据不足」）。
          if (items.length || bundle.gaps || mode === "insufficient_relevance") evidence[id] = bundle;
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
  copyResourceVersion: number | null;
  copyStateVersion: number | null;
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
      const copyResourceVersion = positiveInteger(obj.resource_version ?? obj.resourceVersion);
      const copyStateVersion = positiveInteger(obj.state_version ?? obj.stateVersion);
      const rawVersions = Array.isArray(obj.versions) ? obj.versions as DraftVersionInput[] : null;
      let versions = rawVersions
        ? mapVersions(rawVersions)
        : null;
      if (!rawVersions && copyResourceVersion != null) {
        // 单版新契约不要求额外输出 versions 数组；顶层成品与顶层 resource_version
        // 本就一一对应，因此把它规整为 UI 的 A 槽，不是猜测版本。
        versions = mapVersions([{
          label: "A",
          title: typeof obj.title === "string" ? obj.title : "",
          body: typeof obj.body === "string" ? obj.body : "",
          tags: Array.isArray(obj.tags) ? obj.tags.filter((tag): tag is string => typeof tag === "string") : [],
          cover: typeof obj.cover === "string" ? obj.cover : "",
          note: "",
          resource_version: copyResourceVersion,
        }]);
      }
      // 单版本块里顶层 resource_version 就是顶层 title/body 对应的版本，可安全绑定 A；
      // 多版本缺各自版本号时绝不把同一个顶层版本冒充成 A/B/C。
      if (
        versions?.A && rawVersions?.length === 1 &&
        versions.A.resourceVersion == null && copyResourceVersion != null
      ) {
        versions = { ...versions, A: { ...versions.A, resourceVersion: copyResourceVersion } };
      }
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
        const refVersion = obj.reference_resource_version;
        if (
          td && typeof td === "object" &&
          typeof refId === "string" && refId.trim() &&
          typeof refVersion === "number" && Number.isInteger(refVersion) && refVersion > 0
        ) {
          const t = td as Record<string, unknown>;
          const str = (v: unknown) => (typeof v === "string" ? v : "");
          imitation = {
            referenceResourceId: refId,
            referenceResourceVersion: refVersion,
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
      return { versions, copyResourceId, copyResourceVersion, copyStateVersion, process, imitation };
    } catch {
      // 非法 JSON（流式未闭合等）→ 继续扫描更早的消息。
      continue;
    }
  }
  return {
    versions: null,
    copyResourceId: null,
    copyResourceVersion: null,
    copyStateVersion: null,
    process: null,
    imitation: null,
  };
}

// ── studio overlay 本地持久化(按 threadId 隔离) ──────────────────────────────
// 与 useThreadDraftState 的草稿 autosave 同思路:每个会话一份 overlay 快照,
// 刷新/切会话后据此恢复选题绑定、版本选择、标签等,避免「内容消失」。
const OVERLAY_LATEST_VERSION = 4;

interface StudioOverlaySnapshot {
  v: number;
  topicId: number | null;
  kw: string;
  tags: string[];
  cover: string;
  activeVersion: VersionId;
  // 该会话是否已进入创作态(点过选题起稿/仿写)。刷新/切回后据此决定右栏是编辑器还是素材栏。
  creationMode: boolean;
  // 该会话是否已排期定稿。此前是全局裸 state,不随会话切换复位 → 跨会话泄漏误弹编辑器。
  scheduled: boolean;
  // 用户在 Studio 画布上的编辑是否尚未形成后端不可变快照；刷新/切回时保护本地稿。
  hasLocalEdits: boolean;
  // 当前画布绑定的后端文档 exact identity；普通非成品回合不得清空。
  currentDocumentBinding: CurrentDocumentBinding | null;
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
    if (o.v !== OVERLAY_LATEST_VERSION) return null;
    const av = o.activeVersion;
    return {
      v: OVERLAY_LATEST_VERSION,
      topicId: typeof o.topicId === "number" ? o.topicId : null,
      kw: typeof o.kw === "string" ? o.kw : "",
      tags: Array.isArray(o.tags) ? o.tags.filter((x): x is string => typeof x === "string") : [],
      cover: typeof o.cover === "string" ? o.cover : "",
      activeVersion: av === "A" || av === "B" || av === "C" ? av : "A",
      creationMode: o.creationMode === true,
      scheduled: o.scheduled === true,
      hasLocalEdits: o.hasLocalEdits === true,
      currentDocumentBinding: parseCurrentDocumentBinding(o.currentDocumentBinding),
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
