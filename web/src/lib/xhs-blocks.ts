// web/src/lib/xhs-blocks.ts
export interface TextSegment { kind: "text"; text: string }
export interface TopicsSegment {
  kind: "topics";
  data: { intro?: string; topics: string[] };
}
export interface CopySegment {
  kind: "copy";
  data: { title: string; body: string; tags: string[] };
}
export type Segment = TextSegment | TopicsSegment | CopySegment;

// 匹配 ```xhs_topics ... ``` 或 ```xhs_copy ... ```（含语言行后的换行）
const FENCE_RE = /```(xhs_topics|xhs_copy)\s*\n([\s\S]*?)```/g;

/**
 * 把内容字符串切成有序片段。
 * - 命中 fence 且 JSON.parse 成功且结构合法 → topics/copy 段
 * - 解析失败 → 该 fence 原样并入文本段（降级）
 * - 无 fence → 整体一个 text 段
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
    }
    // parsed 为 null 时不前移 lastIndex，fence 留在文本里降级
  }
  pushText(content.slice(lastIndex));
  // 全是空 → 至少回一个 text 段，保证调用方有内容渲染
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
      return { kind: "topics", data: { intro: typeof obj.intro === "string" ? obj.intro : undefined, topics: obj.topics } };
    }
    return null;
  }
  // xhs_copy
  if (obj && typeof obj.title === "string" && typeof obj.body === "string") {
    const tags = Array.isArray(obj.tags) ? obj.tags.filter((t: unknown) => typeof t === "string") : [];
    return { kind: "copy", data: { title: obj.title, body: obj.body, tags } };
  }
  return null;
}
