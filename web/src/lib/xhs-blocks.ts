// web/src/lib/xhs-blocks.ts

/**
 * 剥离字面 `<thinking>…</thinking>` / `<think>…</think>` 推理块。
 *
 * 背景:结构化输出(response_format)在 opus+扩展思考+中转网关下偶发失败时,子代理会把
 * 整份内部报告连同思考过程当**大白话正文**吐出来(deepagents 回退取最后一条 AIMessage 文本);
 * 模型有时把扩展思考写成字面 `<thinking>` 标签混进正文。Anthropic 原生 thinking 走独立
 * content_block(getContentString 已过滤),但这种"写进 text 的字面标签"过滤不到。此处按文本
 * 清洗兜底:未闭合标签(流式中途)也一并从开标签起截掉,避免半个标签糊屏。
 */
export function stripThinkingTags(text: string): string {
  if (!text) return text;
  return text
    // 成对闭合的 <thinking>…</thinking> / <think>…</think>(大小写不敏感,跨行)
    .replace(/<(thinking|think)\b[^>]*>[\s\S]*?<\/\1>/gi, "")
    // 未闭合的开标签(流式中途 flush):从开标签到结尾整段截掉
    .replace(/<(thinking|think)\b[^>]*>[\s\S]*$/gi, "")
    .trim();
}

export interface TextSegment { kind: "text"; text: string }
export interface SourceEvidence {
  resource_id: string;
  title: string;
  summary: string;
  source_updated_at?: string;
  indexed_at?: string;
}

/** 检索模式，与 data_foundation 证据契约及 web/src/components/studio/types.ts 对齐。 */
export type RetrievalMode = "semantic" | "keyword_fallback" | "insufficient_relevance";

/**
 * 富证据：对齐后端 search_ranker.rank_evidence 输出与 evidence.py 的 EvidenceItem。
 * 数值三信号 relevance/freshness/performance ∈ [0,1]，score 为加权总分。
 * 严格区分 source_updated_at（源端更新）与 indexed_at（本地索引）两个时间字段。
 */
export interface RichEvidence {
  resource_id: string;
  type?: string;
  title: string;
  summary: string;
  score?: number;
  relevance?: number;
  freshness?: number;
  performance?: number;
  why_selected?: string;
  source_updated_at?: string;
  indexed_at?: string;
}

/**
 * 富选题：携带结构化富字段与每选题独立证据。
 * hotRate 仅在 1–100 的整数时存在，无法得出则省略（绝不输出 0）。
 */
export interface RichTopic {
  title: string;
  hotRate?: number;
  angle?: string;
  kw?: string;
  rationale?: string;
  emotional?: string;
  evidence?: RichEvidence[];
  evidence_mode?: RetrievalMode;
  gaps?: string;
}

export interface TopicsSegment {
  kind: "topics";
  // topics 为字符串 = 旧格式；为对象 = 富选题。顶层 evidence 为旧格式共享证据，保留以向后兼容。
  data: { intro?: string; topics: (string | RichTopic)[]; evidence: SourceEvidence[] };
  isPending?: boolean;
}
export interface CopySegment {
  kind: "copy";
  data: { title: string; body: string; tags: string[]; evidence: SourceEvidence[] };
  isPending?: boolean;
}
export interface PanelAction {
  label: string;
  text: string;
}
export interface PanelSegment {
  kind: "panel";
  data: { actions: PanelAction[] };
}
export interface PendingSegment { kind: "pending"; lang: "xhs_topics" | "xhs_copy" }
export type Segment = TextSegment | TopicsSegment | CopySegment | PanelSegment | PendingSegment;

// 语言标签后允许「换行」或「同行空格紧跟 JSON」两种写法 —— 不同模型(OpenAI 兼容网关 vs
// Anthropic 原生 /v1/messages)对围栏后换行习惯不同,Claude 常把 JSON 写在标签同一行,
// 故标签后用 [ \t]*\r?\n? 兼容两者(不强制换行),否则同行写法会整块漏解析。
const OPEN_FENCE_RE = /```(xhs_topics|xhs_copy|xhs_panel)[ \t]*\r?\n?/g;

/**
 * 把内容字符串切成有序片段。
 * 支持在流式输出（未闭合或非法 JSON 状态）时，增量提取局部字段进行平滑渲染，解决页面闪烁或无流式吐字的问题。
 */
export function parseXhsBlocks(content: string): Segment[] {
  const segments: Segment[] = [];
  let cursor = 0;

  const pushText = (text: string) => {
    // 文本段统一剥离字面 <thinking> 标签(见 stripThinkingTags);清洗后为空则不产生空段。
    const cleaned = stripThinkingTags(text);
    if (cleaned.length > 0) segments.push({ kind: "text", text: cleaned });
  };

  const pushPartial = (lang: string, inner: string) => {
    if (lang === "xhs_topics") {
      const partialData = parsePartialXhsTopics(inner);
      segments.push({ kind: "topics", data: partialData, isPending: true });
    } else if (lang === "xhs_copy") {
      const partialData = parsePartialXhsCopy(inner);
      segments.push({ kind: "copy", data: partialData, isPending: true });
    } else if (lang === "xhs_panel") {
      const partialData = parsePartialXhsPanel(inner);
      segments.push({ kind: "panel", data: partialData });
    }
  };

  while (cursor < content.length) {
    OPEN_FENCE_RE.lastIndex = cursor;
    const open = OPEN_FENCE_RE.exec(content);
    if (!open) {
      pushText(content.slice(cursor));
      break;
    }

    const lang = open[1];
    const innerStart = open.index + open[0].length;
    let searchFrom = innerStart;
    let firstClose = -1;
    let matched = false;

    while (searchFrom < content.length) {
      const close = content.indexOf("```", searchFrom);
      if (close === -1) break;
      if (firstClose === -1) firstClose = close;

      const inner = content.slice(innerStart, close);
      const parsed = tryParse(lang, inner);
      if (parsed) {
        pushText(content.slice(cursor, open.index));
        segments.push(parsed);
        cursor = close + 3;
        matched = true;
        break;
      }
      searchFrom = close + 3;
    }

    if (!matched) {
      // JSON 仍未闭合/非法时，降级到局部解析以保持流式输出可见。
      pushText(content.slice(cursor, open.index));
      const partialEnd = firstClose === -1 ? content.length : firstClose;
      pushPartial(lang, content.slice(innerStart, partialEnd));
      cursor = firstClose === -1 ? content.length : firstClose + 3;
    }
  }

  // 兜底:全程未产出任何段(无围栏、纯文本)时,补一个已清洗的文本段(同样剥离 <thinking>)。
  if (segments.length === 0) {
    const cleaned = stripThinkingTags(content);
    if (cleaned.length > 0) segments.push({ kind: "text", text: cleaned });
  }
  return segments;
}

function tryParse(lang: string, inner: string): TopicsSegment | CopySegment | PanelSegment | null {
  let obj: any;
  try {
    obj = JSON.parse(inner.trim());
  } catch {
    return null;
  }
  if (lang === "xhs_topics") {
    if (obj && Array.isArray(obj.topics)) {
      const topLevelEvidence = parseEvidence(obj.evidence);
      const fallbackRich = toRichEvidence(topLevelEvidence);
      const topics = obj.topics.map((t: unknown): string | RichTopic => {
        // 字符串走旧格式（富字段缺省、证据取顶层共享数组）
        if (typeof t === "string") return t;
        // 对象走富选题（读富字段，证据优先选题内、否则回退顶层）
        if (t && typeof t === "object") {
          return parseRichTopic(t as Record<string, unknown>, fallbackRich);
        }
        // 其它类型按降级处理，保证选题数量守恒、不抛错
        return String(t);
      });
      return {
        kind: "topics",
        data: {
          intro: typeof obj.intro === "string" ? obj.intro : undefined,
          topics,
          evidence: topLevelEvidence,
        },
      };
    }
    return null;
  }
  if (lang === "xhs_copy") {
    if (obj && typeof obj.title === "string" && typeof obj.body === "string") {
      const tags = Array.isArray(obj.tags) ? obj.tags.filter((t: unknown) => typeof t === "string") : [];
      return {
        kind: "copy",
        data: { title: obj.title, body: obj.body, tags, evidence: parseEvidence(obj.evidence) },
      };
    }
    return null;
  }
  if (lang === "xhs_panel") {
    if (obj && Array.isArray(obj.actions)) {
      const actions = obj.actions.flatMap((act: any): PanelAction[] => {
        if (act && typeof act.label === "string" && typeof act.text === "string") {
          return [{ label: act.label, text: act.text }];
        }
        return [];
      });
      return {
        kind: "panel",
        data: { actions }
      };
    }
    return null;
  }
  return null;
}

function parseEvidence(value: unknown): SourceEvidence[] {
  if (!Array.isArray(value)) return [];

  return value.flatMap((item): SourceEvidence[] => {
    if (!item || typeof item !== "object") return [];

    const source = item as Record<string, unknown>;
    if (
      typeof source.resource_id !== "string" || !source.resource_id.trim() ||
      typeof source.title !== "string" || !source.title.trim() ||
      typeof source.summary !== "string" || !source.summary.trim()
    ) {
      return [];
    }

    const evidence: SourceEvidence = {
      resource_id: source.resource_id,
      title: source.title,
      summary: source.summary,
    };
    const sourceUpdatedAt = parseIsoTimestamp(source.source_updated_at);
    const indexedAt = parseIsoTimestamp(source.indexed_at);
    if (sourceUpdatedAt) evidence.source_updated_at = sourceUpdatedAt;
    if (indexedAt) evidence.indexed_at = indexedAt;
    return [evidence];
  });
}

function parseIsoTimestamp(value: unknown): string | undefined {
  if (typeof value !== "string" || !value.trim()) return undefined;
  if (!/^\d{4}-\d{2}-\d{2}T/.test(value)) return undefined;
  return Number.isNaN(Date.parse(value)) ? undefined : value;
}

const RETRIEVAL_MODES: readonly RetrievalMode[] = ["semantic", "keyword_fallback", "insufficient_relevance"];

function parseRetrievalMode(value: unknown): RetrievalMode | undefined {
  return typeof value === "string" && (RETRIEVAL_MODES as readonly string[]).includes(value)
    ? (value as RetrievalMode)
    : undefined;
}

/** 顶层共享证据（SourceEvidence）转富证据，供富选题缺省时回退使用。 */
function toRichEvidence(items: SourceEvidence[]): RichEvidence[] {
  return items.map((item) => {
    const evidence: RichEvidence = {
      resource_id: item.resource_id,
      title: item.title,
      summary: item.summary,
    };
    if (item.source_updated_at) evidence.source_updated_at = item.source_updated_at;
    if (item.indexed_at) evidence.indexed_at = item.indexed_at;
    return evidence;
  });
}

/** 解析每选题独立的富证据列表，对齐 rank_evidence 三信号；缺/错字段降级而非抛错。 */
function parseRichEvidence(value: unknown): RichEvidence[] {
  if (!Array.isArray(value)) return [];

  return value.flatMap((item): RichEvidence[] => {
    if (!item || typeof item !== "object") return [];

    const source = item as Record<string, unknown>;
    if (
      typeof source.resource_id !== "string" || !source.resource_id.trim() ||
      typeof source.title !== "string" || !source.title.trim() ||
      typeof source.summary !== "string" || !source.summary.trim()
    ) {
      return [];
    }

    const evidence: RichEvidence = {
      resource_id: source.resource_id,
      title: source.title,
      summary: source.summary,
    };
    if (typeof source.type === "string") evidence.type = source.type;
    if (typeof source.score === "number" && Number.isFinite(source.score)) evidence.score = source.score;
    if (typeof source.relevance === "number" && Number.isFinite(source.relevance)) evidence.relevance = source.relevance;
    if (typeof source.freshness === "number" && Number.isFinite(source.freshness)) evidence.freshness = source.freshness;
    if (typeof source.performance === "number" && Number.isFinite(source.performance)) evidence.performance = source.performance;
    if (typeof source.why_selected === "string") evidence.why_selected = source.why_selected;
    const sourceUpdatedAt = parseIsoTimestamp(source.source_updated_at);
    const indexedAt = parseIsoTimestamp(source.indexed_at);
    if (sourceUpdatedAt) evidence.source_updated_at = sourceUpdatedAt;
    if (indexedAt) evidence.indexed_at = indexedAt;
    return [evidence];
  });
}

/**
 * 解析单个富选题对象。
 * - hotRate 仅当为 1≤n≤100 的整数时保留，否则省略（绝不渲染 🔥0）。
 * - 证据优先取选题内 evidence（含空数组，如 insufficient_relevance）；缺省该键时回退顶层共享证据。
 * - 富字段缺失/类型错配按降级处理（省略对应键），不抛错。
 */
function parseRichTopic(source: Record<string, unknown>, fallbackEvidence: RichEvidence[]): RichTopic {
  const topic: RichTopic = {
    title: typeof source.title === "string" ? source.title : "",
  };

  const hotRate = source.hotRate;
  if (typeof hotRate === "number" && Number.isInteger(hotRate) && hotRate >= 1 && hotRate <= 100) {
    topic.hotRate = hotRate;
  }
  if (typeof source.angle === "string") topic.angle = source.angle;
  if (typeof source.kw === "string") topic.kw = source.kw;
  if (typeof source.rationale === "string") topic.rationale = source.rationale;
  if (typeof source.emotional === "string") topic.emotional = source.emotional;

  const mode = parseRetrievalMode(source.evidence_mode);
  if (mode) topic.evidence_mode = mode;
  if (typeof source.gaps === "string") topic.gaps = source.gaps;

  if (Array.isArray(source.evidence)) {
    topic.evidence = parseRichEvidence(source.evidence);
  } else if (fallbackEvidence.length > 0) {
    topic.evidence = fallbackEvidence;
  }

  return topic;
}

// 增量容错 JSON 字段解析器 - 提取 Copy
function parsePartialXhsCopy(inner: string) {
  let title = "";
  let body = "";
  let tags: string[] = [];

  const titleClosedMatch = /"title"\s*:\s*"([^"\\]*(?:\\.[^"\\]*)*)"/.exec(inner);
  if (titleClosedMatch) {
    title = titleClosedMatch[1];
  } else {
    const titleOpenMatch = /"title"\s*:\s*"([^"\\]*(?:\\.[^"\\]*)*)$/.exec(inner);
    if (titleOpenMatch) {
      title = titleOpenMatch[1];
    }
  }

  const bodyClosedMatch = /"body"\s*:\s*"([^"\\]*(?:\\.[^"\\]*)*)"/.exec(inner);
  if (bodyClosedMatch) {
    body = bodyClosedMatch[1];
  } else {
    const bodyOpenMatch = /"body"\s*:\s*"([^"\\]*(?:\\.[^"\\]*)*)$/.exec(inner);
    if (bodyOpenMatch) {
      body = bodyOpenMatch[1];
    }
  }

  const tagsSegmentMatch = /"tags"\s*:\s*\[([^\]]*)/.exec(inner);
  if (tagsSegmentMatch) {
    const tagsContent = tagsSegmentMatch[1];
    const tagMatches = tagsContent.match(/"[^"\\]*(?:\\.[^"\\]*)*"/g) || [];
    tags = tagMatches.map(t => t.slice(1, -1));
    const lastTagOpenMatch = /"([^"\\]*(?:\\.[^"\\]*)*)$/.exec(tagsContent);
    if (lastTagOpenMatch && !tagsContent.trim().endsWith('"') && !tagsContent.trim().endsWith(',')) {
      tags.push(lastTagOpenMatch[1]);
    }
  }

  const cleanString = (str: string) => {
    try {
      return JSON.parse(`"${str.replace(/\n/g, "\\n")}"`);
    } catch {
      return str
        .replace(/\\n/g, "\n")
        .replace(/\\"/g, '"')
        .replace(/\\\\/g, "\\")
        .replace(/\\t/g, "\t");
    }
  };

  return {
    title: cleanString(title),
    body: cleanString(body),
    tags: tags.map(cleanString),
    evidence: [],
  };
}

// 增量容错 JSON 字段解析器 - 提取 Topics
function parsePartialXhsTopics(inner: string) {
  let intro = "";
  let topics: string[] = [];

  const introClosedMatch = /"intro"\s*:\s*"([^"\\]*(?:\\.[^"\\]*)*)"/.exec(inner);
  if (introClosedMatch) {
    intro = introClosedMatch[1];
  } else {
    const introOpenMatch = /"intro"\s*:\s*"([^"\\]*(?:\\.[^"\\]*)*)$/.exec(inner);
    if (introOpenMatch) {
      intro = introOpenMatch[1];
    }
  }

  const topicsSegmentMatch = /"topics"\s*:\s*\[([^\]]*)/.exec(inner);
  if (topicsSegmentMatch) {
    const topicsContent = topicsSegmentMatch[1];
    const topicMatches = topicsContent.match(/"[^"\\]*(?:\\.[^"\\]*)*"/g) || [];
    topics = topicMatches.map(t => t.slice(1, -1));
    const lastTopicOpenMatch = /"([^"\\]*(?:\\.[^"\\]*)*)$/.exec(topicsContent);
    if (lastTopicOpenMatch && !topicsContent.trim().endsWith('"') && !topicsContent.trim().endsWith(',')) {
      topics.push(lastTopicOpenMatch[1]);
    }
  }

  const cleanString = (str: string) => {
    try {
      return JSON.parse(`"${str.replace(/\n/g, "\\n")}"`);
    } catch {
      return str
        .replace(/\\n/g, "\n")
        .replace(/\\"/g, '"')
        .replace(/\\\\/g, "\\");
    }
  };

  return {
    intro: cleanString(intro),
    topics: topics.map(cleanString),
    evidence: [],
  };
}

// 增量容错 JSON 字段解析器 - 提取 Panel
function parsePartialXhsPanel(inner: string) {
  const actions: PanelAction[] = [];
  const cleanString = (str: string) => {
    try {
      return JSON.parse(`"${str.replace(/\n/g, "\\n")}"`);
    } catch {
      return str
        .replace(/\\n/g, "\n")
        .replace(/\\"/g, '"')
        .replace(/\\\\/g, "\\")
        .replace(/\\t/g, "\t");
    }
  };

  const actionsSegmentMatch = /"actions"\s*:\s*\[([\s\S]*?)(?:\]|$)/.exec(inner);
  if (actionsSegmentMatch) {
    const actionsContent = actionsSegmentMatch[1];
    const objRe = /\{\s*"label"\s*:\s*"([^"\\]*(?:\\.[^"\\]*)*)"\s*,\s*"text"\s*:\s*"([^"\\]*(?:\\.[^"\\]*)*)"\s*\}/g;
    let match;
    while ((match = objRe.exec(actionsContent)) !== null) {
      actions.push({
        label: cleanString(match[1]),
        text: cleanString(match[2]),
      });
    }
  }
  return { actions };
}
