// Typed data contracts for the 创作运营工作室. These mirror the REAL
// backend models (data_foundation: resources, EvidencePackage,
// performance_metric, accounts) — NOT the prototype's mock shapes. The
// StudioProvider fills them from the live LangGraph stream + /api/backend/*.

export type RetrievalMode =
  | "hybrid"
  | "semantic_only"
  | "keyword_only"
  | "insufficient_relevance";

/** One ranked evidence resource — all four signals are authoritative backend values. */
export interface EvidenceItem {
  resource_id: string;
  resource_version: number;
  type: string;
  asset_kind: string;
  source_kind: string;
  niche?: string;
  title: string;
  summary: string;
  score: number;
  /** 知识资产质量；正式检索必填且只能在 [0,1]，前端不得补默认值。 */
  quality: number;
  relevance: number;
  freshness: number;
  performance: number;
  source_updated_at: string;
  indexed_at: string;
  retrieval_sources: ("semantic" | "keyword" | "graph")[];
  why_selected: string;
}

export interface EvidenceBundle {
  mode: RetrievalMode;
  items: EvidenceItem[];
  /** insufficient_relevance 时的缺口说明，供面板渲染「当前数据不足」。 */
  gaps?: string;
}

/** Evidence selected for the slide-over panel (item + its retrieval mode). */
export type SelectedEvidence = EvidenceItem & { mode: RetrievalMode };

/** A viral-topic suggestion. Backend `xhs_topics` is being enriched to emit
 *  these structured fields (angle / hotRate / kw / per-topic evidence). */
export interface NoteSeed {
  title: string;
  cover: string;
  body: string;
  tags: string[];
}

export interface Topic {
  id: number;
  title: string;
  rationale: string;
  /** 爆款率 1–100；后端无法得出时为 null（选题卡隐藏 🔥 标记，绝不显示 🔥0）。 */
  hotRate: number | null;
  angle: string;
  kw: string;
  emotional: string;
  draft: NoteSeed;
}

export type VersionId = "A" | "B" | "C";

export interface DraftVersion {
  label: string;
  note: string;
  title: string;
  cover: string;
  body: string;
  tags: string[];
  /** 后端 resource_versions 的不可变版本号；缺失时不得猜测或执行生命周期写操作。 */
  resourceVersion?: number;
}

/** lifecycle GET 返回的权威不可变版本快照；字段必须完整，不能由流消息补齐。 */
export interface CopyVersionSnapshot extends DraftVersion {
  resourceVersion: number;
}

export type Versions = Record<VersionId, DraftVersion>;

export type NoteStatus = "idle" | "writing" | "draft" | "scheduled";

/** 一次文案生成的「创作过程」:供深度创作页"查看创作过程"抽屉回看,
 *  让创作者知道这份文案对标了什么、按哪些去AI腔指纹自审纠偏过。
 *  与成品文案分两条道:正文只渲染 title/body/tags/versions,process 永远不进正文。 */
export interface StudioProcess {
  outline: string;
  audit: string;
}

/** The shared note that flows across 创作 / 深度创作 / 运营. Title & body are
 *  the canonical draft (bound to useThreadDraftState); the rest is studio
 *  overlay (versions, tags, cover, status). */
export interface StudioNote {
  topicId: number | null;
  kw: string;
  title: string;
  body: string;
  tags: string[];
  cover: string;
  status: NoteStatus;
  activeVersion: VersionId;
  /** 多版本草稿（来自 xhs_copy 多版本）。可能仅含真实存在的版本（A/B/C 子集），
   *  无多版本时为 null（保持单版本编辑态）。消费组件按实际存在的键渲染，不补造缺失版本。 */
  versions: Partial<Versions> | null;
  /** 本次生成的创作过程(outline 对标依据/论证链 + audit 22 条自审纠偏),从 xhs_copy 块
   *  的 outline/ai_audit_log 字段解析;仅供"创作过程"抽屉回看,不渲染进正文。无则 null。 */
  process: StudioProcess | null;
  /** 同一篇 generated_copy 的稳定资源标识；旧消息可能没有，写动作必须据此禁用。 */
  resourceId: string | null;
}

export type CopyLifecycleStatus =
  | "candidate"
  | "selected"
  | "adopted"
  | "finalized"
  | "published"
  | "measured";

/** generated_copy 的权威版本指针与乐观并发令牌。 */
export interface CopyLifecycle {
  resourceId: string;
  status: CopyLifecycleStatus;
  selectedVersion: number | null;
  selectedLabel: string | null;
  adoptedVersion: number | null;
  finalizedVersion: number | null;
  publishedVersion: number | null;
  knowledgeTargetVersion: number | null;
  latestResourceVersion: number;
  stateVersion: number;
  versions: CopyVersionSnapshot[];
}

/** 排期写入的三重 CAS：目标是当前选中的精确快照，latest/state 是并发基线。 */
export interface ScheduleVersionContract {
  targetResourceVersion: number;
  expectedLatestResourceVersion: number;
  expectedStateVersion: number;
}

export interface StudioUser {
  name: string;
  team: string;
  initial: string;
  handle: string;
  fans: string;
}

/** 两段式仿写的第一段:对范本的套路拆解(§5),必须显性呈现给用户——让用户看到
 *  "它凭什么这么仿"。从 xhs_imitation 块的 teardown 字段解析。四维对齐后端 ReferenceTeardown。 */
export interface ImitationTeardown {
  angle: string;
  painpoint: string;
  hook_mechanism: string;
  structure: string;
}

/** 一次仿写产出的元信息:所仿范本 + 第一段拆解。第二段成品走 note.versions(与 xhs_copy 同构)。
 *  非仿写会话为 null。 */
export interface StudioImitation {
  referenceResourceId: string;
  referenceResourceVersion: number;
  referenceTitle: string;
  teardown: ImitationTeardown;
}

// ── 账号运营 ──
export interface DashboardStat {
  label: string;
  value: string;
  unit?: string;
  delta: number;
  tone: "coral" | "success" | "neutral" | "topic";
  icon: string;
}

export interface LibraryItem {
  id: number;
  title: string;
  angle: string;
  hot: number;
  likes: string;
  saves: string;
  status: string;
}

export interface TeardownPoint {
  label: string;
  detail: string;
}

export interface Teardown {
  title: string;
  points: TeardownPoint[];
}

export interface Account {
  id: string;
  handle: string;
  niche: string;
  writingNiche?: string | null;
  initial: string;
  fans: string;
  fansNum: number;
  dFans: number;
  posts: number;
  hot: number;
  status: string;
  tone: "coral" | "topic" | "draft";
}

export interface CalendarItem {
  t: string;
  time: string;
  tone: "coral" | "topic" | "draft";
  acct: string;
  resourceId?: string;
  resourceVersion?: number;
}

export interface CalendarDay {
  date: number;
  items: CalendarItem[];
}

export interface MonthInfo {
  label: string;
  days: number;
  firstOffset: number;
}

export type PublishStage = "scheduled" | "published" | "measured";

export interface PublishItem {
  id: number;
  title: string;
  acct: string;
  stage: PublishStage;
  link?: string;
  time: string;
  /** 后端资源 id（用于推进 stage 写动作）；后端未提供时省略。 */
  resourceId?: string;
  /** 排期/发布/效果回填都绑定到这个精确不可变版本。 */
  resourceVersion?: number;
}

export interface Trend {
  tag: string;
  rising: number;
  heat: string;
  note: string;
  tone: "hot" | "coral" | "topic";
}

// v2:原独立 deep 深度创作整屏已并入 create 右栏就地编辑,section 只剩两个工作区。
export type StudioSection = "create" | "ops";

/** 统一详情弹层的目标:一张选题卡,或一篇参考素材笔记。DetailModal 据 kind 分渲染。 */
export type DetailTarget =
  | { kind: "topic"; topicId: number }
  | { kind: "material"; noteId: string };

/** Static UI config (image roles, quick emoji, weekday labels) — not business
 *  data; safe to keep client-side. Ported from data.js. */
export const IMAGE_ROLES = ["封面 · 大字报", "产品特写", "场景氛围", "清单合影", "选购对比"];

/** 标题公式库(§4.5 TitleScreen 左栏)。这是**运营可维护的 prompt 意图预设**(半固定可配,
 *  同 IMAGE_ROLES/QUICK_EMOJI),不是业务数据 —— 真实候选由 LLM 按该公式意图生成(走 xhs-title),
 *  绝不本地模板拼接假候选。真实产品这批由飞书表格配置、接口拉取;此处作为前端默认意图集。 */
export interface TitleFormula {
  name: string;
  hint: string;
}
export const TITLE_FORMULAS: TitleFormula[] = [
  { name: "数字清单", hint: "用具体数字制造信息密度,如「5 个」「3 步」" },
  { name: "痛点前置", hint: "开头直戳读者的坑/焦虑,引发「这说的就是我」" },
  { name: "身份代入", hint: "点名目标人群,如「新手」「打工人」「学生党」" },
  { name: "情绪钩子", hint: "用强情绪词制造点击冲动,如「谁懂」「绝了」" },
  { name: "结果承诺", hint: "承诺读完能得到的确定结果/收益" },
  { name: "反差悬念", hint: "制造反常识对比或悬念,吊起好奇" },
];
export const QUICK_EMOJI = ["🍠", "⛺", "☕", "✨", "🌿", "👇", "📝", "🔥", "🌅", "✅", "❌", "1️⃣", "2️⃣", "💛"];
export const WEEKDAYS = ["一", "二", "三", "四", "五", "六", "日"];
