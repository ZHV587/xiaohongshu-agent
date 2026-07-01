// Typed data contracts for the 创作运营工作室. These mirror the REAL
// backend models (data_foundation: resources, evidence.py rank_evidence,
// performance_metric, accounts) — NOT the prototype's mock shapes. The
// StudioProvider fills them from the live LangGraph stream + /api/backend/*.

export type RetrievalMode = "semantic" | "keyword_fallback" | "insufficient_relevance";

/** One ranked evidence resource — aligns with evidence.py EvidenceItem +
 *  rank_evidence three-signal model (relevance / freshness / performance). */
export interface EvidenceItem {
  resource_id: string;
  type: string;
  title: string;
  summary: string;
  score: number;
  relevance: number;
  freshness: number;
  performance: number;
  source_updated_at: string;
  indexed_at: string;
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
}

export type Versions = Record<VersionId, DraftVersion>;

export type NoteStatus = "idle" | "writing" | "draft" | "scheduled";

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
}

export interface StudioUser {
  name: string;
  team: string;
  initial: string;
  handle: string;
  fans: string;
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
}

export interface Trend {
  tag: string;
  rising: number;
  heat: string;
  note: string;
  tone: "hot" | "coral" | "topic";
}

export type StudioSection = "create" | "deep" | "ops";

/** Static UI config (image roles, quick emoji, weekday labels) — not business
 *  data; safe to keep client-side. Ported from data.js. */
export const IMAGE_ROLES = ["封面 · 大字报", "产品特写", "场景氛围", "清单合影", "选购对比"];
export const QUICK_EMOJI = ["🍠", "⛺", "☕", "✨", "🌿", "👇", "📝", "🔥", "🌅", "✅", "❌", "1️⃣", "2️⃣", "💛"];
export const WEEKDAYS = ["一", "二", "三", "四", "五", "六", "日"];
