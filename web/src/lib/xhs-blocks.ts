// web/src/lib/xhs-blocks.ts
export interface TextSegment { kind: "text"; text: string }
export interface SourceEvidence {
  resource_id: string;
  title: string;
  summary: string;
  source_updated_at?: string;
  indexed_at?: string;
}
export interface TopicsSegment {
  kind: "topics";
  data: { intro?: string; topics: string[]; evidence: SourceEvidence[] };
  isPending?: boolean;
}
export interface CopySegment {
  kind: "copy";
  data: { title: string; body: string; tags: string[]; evidence: SourceEvidence[] };
  isPending?: boolean;
}
export interface PendingSegment { kind: "pending"; lang: "xhs_topics" | "xhs_copy" }
export type Segment = TextSegment | TopicsSegment | CopySegment | PendingSegment;

// 匹配 ```xhs_topics ... ``` 或 ```xhs_copy ... ```（含语言行后的换行）
const FENCE_RE = /```(xhs_topics|xhs_copy)\s*\n([\s\S]*?)```/g;

/**
 * 把内容字符串切成有序片段。
 * 支持在流式输出（未闭合或非法 JSON 状态）时，增量提取局部字段进行平滑渲染，解决页面闪烁或无流式吐字的问题。
 */
export function parseXhsBlocks(content: string): Segment[] {
  const segments: Segment[] = [];
  let lastIndex = 0;
  let m: RegExpExecArray | null;
  FENCE_RE.lastIndex = 0;

  const pushText = (text: string) => {
    if (text.length > 0) segments.push({ kind: "text", text });
  };

  while ((m = FENCE_RE.exec(content)) !== null) {
    const [full, lang, inner] = m;
    const parsed = tryParse(lang, inner);
    if (parsed) {
      pushText(content.slice(lastIndex, m.index));
      segments.push(parsed);
      lastIndex = m.index + full.length;
    } else {
      // 即使闭合，如果 JSON 解析失败（可能带有未闭合转义符），我们也采用增量解析挽救，避免降级为裸露 JSON
      pushText(content.slice(lastIndex, m.index));
      if (lang === "xhs_topics") {
        const partialData = parsePartialXhsTopics(inner);
        segments.push({ kind: "topics", data: partialData, isPending: true });
      } else {
        const partialData = parsePartialXhsCopy(inner);
        segments.push({ kind: "copy", data: partialData, isPending: true });
      }
      lastIndex = m.index + full.length;
    }
  }

  // 处理未闭合流式文本检测
  const rest = content.slice(lastIndex);
  const openRe = /```(xhs_topics|xhs_copy)\b/g;
  let lastOpen: RegExpExecArray | null = null;
  let mm: RegExpExecArray | null;
  while ((mm = openRe.exec(rest)) !== null) lastOpen = mm;

  if (lastOpen) {
    const afterOpen = rest.slice(lastOpen.index + lastOpen[0].length);
    const hasClosing = afterOpen.includes("```");
    if (!hasClosing) {
      // 未闭合状态（大模型正在吐字）：将前段文本 push，后段正在流动的 JSON 部分增量提取渲染
      pushText(rest.slice(0, lastOpen.index));
      const lang = lastOpen[1];
      if (lang === "xhs_topics") {
        const partialData = parsePartialXhsTopics(afterOpen);
        segments.push({ kind: "topics", data: partialData, isPending: true });
      } else {
        const partialData = parsePartialXhsCopy(afterOpen);
        segments.push({ kind: "copy", data: partialData, isPending: true });
      }
    } else {
      // 虽包含闭合标记但主正则未匹配上（JSON 暂时非法），依然用增量解析降噪
      const inner = afterOpen.split("```")[0];
      pushText(rest.slice(0, lastOpen.index));
      const lang = lastOpen[1];
      if (lang === "xhs_topics") {
        const partialData = parsePartialXhsTopics(inner);
        segments.push({ kind: "topics", data: partialData, isPending: true });
      } else {
        const partialData = parsePartialXhsCopy(inner);
        segments.push({ kind: "copy", data: partialData, isPending: true });
      }
    }
  } else {
    pushText(rest);
  }

  if (segments.length === 0) segments.push({ kind: "text", text: content });
  return segments;
}

function tryParse(lang: string, inner: string): TopicsSegment | CopySegment | null {
  let obj: any;
  try {
    obj = JSON.parse(inner.trim());
  } catch {
    return null;
  }
  if (lang === "xhs_topics") {
    if (obj && Array.isArray(obj.topics) && obj.topics.every((t: unknown) => typeof t === "string")) {
      return {
        kind: "topics",
        data: {
          intro: typeof obj.intro === "string" ? obj.intro : undefined,
          topics: obj.topics,
          evidence: parseEvidence(obj.evidence),
        },
      };
    }
    return null;
  }
  if (obj && typeof obj.title === "string" && typeof obj.body === "string") {
    const tags = Array.isArray(obj.tags) ? obj.tags.filter((t: unknown) => typeof t === "string") : [];
    return {
      kind: "copy",
      data: { title: obj.title, body: obj.body, tags, evidence: parseEvidence(obj.evidence) },
    };
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
