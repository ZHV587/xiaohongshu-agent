// web/src/components/studio/backend-mappers.ts
//
// 纯函数 helper —— 供 StudioContext 接线（任务 9.x）与属性测试（任务 8.3–8.10）引用。
// 全部无副作用、不读写外部状态、不依赖时钟/随机源；字段口径严格对齐
// web/src/components/studio/types.ts，并与后端
// data_foundation/performance_feedback.py 的 _clean_metrics 校验口径一致。
//
// 真实数据铁律：这些 helper 只做映射/聚合/过滤/校验，绝不编造业务数据。
// 空输入返回空结构或 0，而非占位值。

import type {
  Account,
  CalendarDay,
  CalendarItem,
  DraftVersion,
  PublishItem,
  PublishStage,
  Versions,
  VersionId,
} from "./types";

// ──────────────────────────────────────────────────────────────────────────
// Property 6：多版本数组 → Versions（A/B/C）映射 + 选择应用
// ──────────────────────────────────────────────────────────────────────────

/** A/B/C 的固定顺序，多版本数组按此顺序落位。 */
export const VERSION_IDS: readonly VersionId[] = ["A", "B", "C"];

/** 后端 xhs_copy 多版本草稿项的原始形状（字段可缺省，缺省按降级补默认值）。 */
export interface DraftVersionInput {
  label?: string;
  note?: string;
  title?: string;
  cover?: string;
  body?: string;
  tags?: string[];
}

/** 把单个原始版本规整为完整 DraftVersion（缺失字段补安全默认值，不编造内容）。 */
function normalizeDraftVersion(input: DraftVersionInput, id: VersionId): DraftVersion {
  return {
    label: typeof input.label === "string" && input.label.length > 0 ? input.label : id,
    note: typeof input.note === "string" ? input.note : "",
    title: typeof input.title === "string" ? input.title : "",
    cover: typeof input.cover === "string" ? input.cover : "",
    body: typeof input.body === "string" ? input.body : "",
    tags: Array.isArray(input.tags) ? input.tags.filter((t): t is string => typeof t === "string") : [],
  };
}

/**
 * 1–3 个版本组成的版本数组 → `Versions` 映射（键 A/B/C 与各版本内容一一对应）。
 * 超过 3 个的多余版本被截断（UI 仅 A/B/C 三档）；空数组返回 `null`（保持单版本编辑态）。
 * 返回 `Partial<Versions>`：仅包含实际存在的版本键，绝不为缺失版本编造内容。
 */
export function mapVersions(versions: readonly DraftVersionInput[]): Partial<Versions> | null {
  if (!Array.isArray(versions) || versions.length === 0) return null;
  const out: Partial<Versions> = {};
  for (let i = 0; i < versions.length && i < VERSION_IDS.length; i++) {
    const id = VERSION_IDS[i];
    out[id] = normalizeDraftVersion(versions[i] ?? {}, id);
  }
  return out;
}

/**
 * 选择某个版本后应回写 canonical draft 的 `title`/`body`。
 * 选中版本不存在时返回 `null`（调用方保持当前草稿不变）。
 */
export function selectVersionDraft(
  versions: Partial<Versions> | null | undefined,
  id: VersionId,
): { title: string; body: string } | null {
  const v = versions?.[id];
  if (!v) return null;
  return { title: v.title, body: v.body };
}

// ──────────────────────────────────────────────────────────────────────────
// Property 7：最近创作按时间倒序
// ──────────────────────────────────────────────────────────────────────────

/**
 * 按时间戳降序（最新在前）稳定排序。
 * 纯函数：不修改入参，返回新数组；`getTime` 抽取每项的可比较时间戳（epoch 毫秒）。
 * 相等时保持原相对顺序（稳定），相邻项时间戳单调非递增。
 */
export function sortByTimeDesc<T>(items: readonly T[], getTime: (item: T) => number): T[] {
  return items
    .map((item, index) => ({ item, index, ts: getTime(item) }))
    .sort((a, b) => (b.ts - a.ts) || (a.index - b.index))
    .map((x) => x.item);
}

// ──────────────────────────────────────────────────────────────────────────
// Property 8：name → initial 首字符
// ──────────────────────────────────────────────────────────────────────────

/**
 * 取 `name` 的首字符作为头像 initial。
 * 使用码点切分（Array.from）以正确处理 CJK / emoji / 代理对；
 * 空字符串返回空字符串（调用方据此渲染空态，不编造占位字母）。
 */
export function deriveInitial(name: string): string {
  if (typeof name !== "string" || name.length === 0) return "";
  return Array.from(name)[0] ?? "";
}

// ──────────────────────────────────────────────────────────────────────────
// Property 9：账号 overview 聚合
// ──────────────────────────────────────────────────────────────────────────

export interface AccountsOverview {
  /** Σ fansNum */
  totalFans: number;
  /** Σ dFans */
  weekNewFans: number;
  /** Σ posts */
  weekPosts: number;
  /** avg(hot)，空列表为 0（不产生 NaN） */
  avgHotRate: number;
}

/**
 * 由真实账号列表计算总览聚合：
 * totalFans = Σ fansNum、weekNewFans = Σ dFans、weekPosts = Σ posts、avgHotRate = avg(hot)。
 * 空列表各项为 0（空态，不编造数值）。
 */
export function computeAccountsOverview(accounts: readonly Account[]): AccountsOverview {
  const totalFans = accounts.reduce((sum, a) => sum + (Number.isFinite(a.fansNum) ? a.fansNum : 0), 0);
  const weekNewFans = accounts.reduce((sum, a) => sum + (Number.isFinite(a.dFans) ? a.dFans : 0), 0);
  const weekPosts = accounts.reduce((sum, a) => sum + (Number.isFinite(a.posts) ? a.posts : 0), 0);
  const hotSum = accounts.reduce((sum, a) => sum + (Number.isFinite(a.hot) ? a.hot : 0), 0);
  const avgHotRate = accounts.length > 0 ? hotSum / accounts.length : 0;
  return { totalFans, weekNewFans, weekPosts, avgHotRate };
}

// ──────────────────────────────────────────────────────────────────────────
// Property 10：单账号视图过滤（看板/日历/发布队列按 acct 归属）
// ──────────────────────────────────────────────────────────────────────────

/** 通用：按 acct 归属过滤含 `acct` 字段的条目（日历项 / 发布队列项等）。 */
export function filterByAccount<T extends { acct: string }>(items: readonly T[], account: string): T[] {
  return items.filter((item) => item.acct === account);
}

/**
 * 日历按账号过滤：保留每天归属该账号的 items；过滤后无 items 的日期被剔除。
 * 不修改入参；返回结构中所有 item 均归属选定账号。
 */
export function filterCalendarByAccount(calendar: readonly CalendarDay[], account: string): CalendarDay[] {
  return calendar
    .map((day) => ({ ...day, items: filterByAccount(day.items, account) }))
    .filter((day) => day.items.length > 0);
}

// ──────────────────────────────────────────────────────────────────────────
// Property 11：发布队列按 stage 分组 + stage 不变量 + 单向状态机守卫
// ──────────────────────────────────────────────────────────────────────────

/** 发布管线三阶段的固定顺序。 */
export const PUBLISH_STAGES: readonly PublishStage[] = ["scheduled", "published", "measured"];

/**
 * 按 stage 分组（每列内所有条目的 stage 与列标识一致；分组前后条目总数守恒）。
 * 未知 stage 的条目被忽略（容错降级，不抛错）；返回对象始终含全部三个键。
 */
export function groupQueueByStage(queue: readonly PublishItem[]): Record<PublishStage, PublishItem[]> {
  const groups: Record<PublishStage, PublishItem[]> = {
    scheduled: [],
    published: [],
    measured: [],
  };
  for (const item of queue) {
    const bucket = groups[item.stage];
    if (bucket) bucket.push(item);
  }
  return groups;
}

/**
 * stage 推进守卫：当且仅当为相邻正向转移时允许。
 * 允许：scheduled→published、published→measured；逆向 / 跨级 / 自环一律拒绝。
 */
export function canAdvanceStage(from: PublishStage, to: PublishStage): boolean {
  return (from === "scheduled" && to === "published") || (from === "published" && to === "measured");
}

/**
 * 单条不变量：处于 `published` 或 `measured` 阶段的条目必须含非空 `link`。
 * `scheduled` 阶段不要求 link。
 */
export function publishItemHasRequiredLink(item: PublishItem): boolean {
  if (item.stage === "published" || item.stage === "measured") {
    return typeof item.link === "string" && item.link.trim().length > 0;
  }
  return true;
}

/** 整个队列是否满足 link 不变量（published/measured 必有非空 link）。 */
export function queueSatisfiesLinkInvariant(queue: readonly PublishItem[]): boolean {
  return queue.every(publishItemHasRequiredLink);
}

// ──────────────────────────────────────────────────────────────────────────
// Property 12：排期失败回滚 reducer
// ──────────────────────────────────────────────────────────────────────────

/** 深拷贝日历状态，确保回滚返回与后续乐观更新互不别名。 */
function cloneCalendar(calendar: readonly CalendarDay[]): CalendarDay[] {
  return calendar.map((day) => ({ ...day, items: day.items.map((item) => ({ ...item })) }));
}

/**
 * 乐观排期：把一条排期项加入对应日期（已有该日期则追加，否则新建日期）。
 * 纯函数：不修改入参（保留调用方持有的「操作前」快照用于回滚）。
 */
export function applyOptimisticSchedule(
  calendar: readonly CalendarDay[],
  date: number,
  item: CalendarItem,
): CalendarDay[] {
  const exists = calendar.some((d) => d.date === date);
  if (exists) {
    return calendar.map((d) => (d.date === date ? { ...d, items: [...d.items, item] } : { ...d }));
  }
  return [...calendar.map((d) => ({ ...d })), { date, items: [item] }];
}

/**
 * 排期持久化失败时回滚：返回与「操作前」快照恒等（深相等）的状态，
 * 完全撤销乐观更新。返回深拷贝避免与原快照别名。
 */
export function rollbackSchedule(snapshotBefore: readonly CalendarDay[]): CalendarDay[] {
  return cloneCalendar(snapshotBefore);
}

// ──────────────────────────────────────────────────────────────────────────
// Property 13：回填 metrics 校验（口径对齐后端 _clean_metrics）
// ──────────────────────────────────────────────────────────────────────────

/** 后端 ALLOWED_METRICS（performance_feedback.py）—— 仅这些指标参与校验/落库。 */
export const ALLOWED_BACKFILL_METRICS = [
  "likes",
  "collects",
  "comments",
  "shares",
  "views",
  "conversions",
] as const;
export type BackfillMetricKey = (typeof ALLOWED_BACKFILL_METRICS)[number];

const ALLOWED_BACKFILL_METRIC_SET: ReadonlySet<string> = new Set(ALLOWED_BACKFILL_METRICS);

export interface BackfillValidationResult {
  ok: boolean;
  /** 校验错误信息（与后端 _clean_metrics 抛出的 ValueError 文案对齐）。 */
  error?: string;
  /** 校验通过时的规整结果（整数化，仅含受支持指标）。 */
  cleaned?: Record<string, number>;
}

/**
 * 仿后端 float() 的数值强制：返回有限/非有限 number 或 null（无法转换）。
 * - boolean → 1/0（与 Python float(True/False) 一致）
 * - number  → 原值（NaN/Infinity 交由后续 isFinite 判定）
 * - string  → 去空白后解析；空串 / 不可解析 → null；支持 inf/nan 字面量
 * - 其它（null/undefined/对象/数组）→ null（对应后端 TypeError）
 */
function coerceMetricNumber(value: unknown): number | null {
  if (typeof value === "boolean") return value ? 1 : 0;
  if (typeof value === "number") return value;
  if (typeof value === "string") {
    const s = value.trim();
    if (s === "") return null;
    const lower = s.toLowerCase();
    if (["inf", "+inf", "-inf", "infinity", "+infinity", "-infinity"].includes(lower)) {
      return lower.startsWith("-") ? -Infinity : Infinity;
    }
    if (["nan", "+nan", "-nan"].includes(lower)) return NaN;
    const n = Number(s);
    return Number.isNaN(n) ? null : n;
  }
  return null;
}

/**
 * 回填指标校验，口径对齐 data_foundation/performance_feedback.py 的 `_clean_metrics`：
 * - 入参非对象 → 拒绝（"metrics must be a mapping"）
 * - 仅受支持指标（ALLOWED_BACKFILL_METRICS）参与校验，其它键被忽略
 * - 受支持指标值无法转为数值 / 非有限 → 拒绝（"metrics must be finite non-negative numbers"）
 * - 受支持指标值为负 → 拒绝（"metrics must be non-negative"）
 * - 不含任何受支持指标 → 拒绝（"metrics must contain at least one supported metric"）
 *
 * 当且仅当全部受支持指标均为有限非负数值、且至少含一个受支持指标时通过。
 */
export function validateBackfillMetrics(metrics: unknown): BackfillValidationResult {
  if (metrics === null || typeof metrics !== "object" || Array.isArray(metrics)) {
    return { ok: false, error: "metrics must be a mapping" };
  }
  const cleaned: Record<string, number> = {};
  for (const [key, value] of Object.entries(metrics as Record<string, unknown>)) {
    if (!ALLOWED_BACKFILL_METRIC_SET.has(key)) continue;
    const number = coerceMetricNumber(value);
    if (number === null || !Number.isFinite(number)) {
      return { ok: false, error: "metrics must be finite non-negative numbers" };
    }
    if (number < 0) {
      return { ok: false, error: "metrics must be non-negative" };
    }
    cleaned[key] = number;
  }
  if (Object.keys(cleaned).length === 0) {
    return { ok: false, error: "metrics must contain at least one supported metric" };
  }
  return { ok: true, cleaned };
}
