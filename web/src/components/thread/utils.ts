import type { Message } from "@langchain/langgraph-sdk";

/**
 * Extracts a string summary from a message's content, supporting multimodal (text, image, file, etc.).
 * - If text is present, returns the joined text.
 * - If not, returns a label for the first non-text modality (e.g., 'Image', 'Other').
 * - If unknown, returns 'Multimodal message'.
 */
export function getContentString(content: Message["content"]): string {
  if (typeof content === "string") return content;
  // 仅含 tool_call 的 AI 消息在部分 SDK 形态下 content 可能为 null/undefined;
  // 守卫避免 .filter 抛 TypeError 冒泡拖垮上层 useMemo 渲染。
  if (!Array.isArray(content)) return "";
  const texts = content
    .filter((c): c is { type: "text"; text: string } => c.type === "text")
    .map((c) => c.text);
  return texts.join(" ");
}
