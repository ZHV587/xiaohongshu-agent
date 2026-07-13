import type { CopyLifecycle } from "./types";

/** 当前 Studio 画布绑定的后端文档与不可变版本。 */
export interface CurrentDocumentBinding {
  ownerThreadId: string;
  resourceId: string;
  resourceVersion: number;
  stateVersion?: number;
}

function positiveInteger(value: unknown): number | null {
  return typeof value === "number" && Number.isInteger(value) && value > 0
    ? value
    : null;
}

/** 外部消息或 localStorage 一律重新校验，半对 identity 直接拒绝。 */
export function parseCurrentDocumentBinding(value: unknown): CurrentDocumentBinding | null {
  if (!value || typeof value !== "object" || Array.isArray(value)) return null;
  const raw = value as Record<string, unknown>;
  const ownerThreadId = typeof raw.ownerThreadId === "string" ? raw.ownerThreadId.trim() : "";
  const resourceId = typeof raw.resourceId === "string" ? raw.resourceId.trim() : "";
  const resourceVersion = positiveInteger(raw.resourceVersion);
  if (!ownerThreadId || !resourceId || resourceVersion == null) return null;
  const stateVersion = positiveInteger(raw.stateVersion);
  return {
    ownerThreadId,
    resourceId,
    resourceVersion,
    ...(stateVersion == null ? {} : { stateVersion }),
  };
}

/**
 * 当前回合有新成品时以新 exact binding 为准；普通问答/存档等非成品回合没有新身份，继续
 * 使用按 thread 恢复的绑定。新创作意图由调用方显式传 null 清除，而不是靠 human 边界猜测。
 */
export function resolveCurrentDocumentBinding(
  streamBinding: unknown,
  persistedBinding: unknown,
): CurrentDocumentBinding | null {
  return parseCurrentDocumentBinding(streamBinding) ?? parseCurrentDocumentBinding(persistedBinding);
}

/**
 * 模型输出的 exact pair 只是待验证声明，不是权威身份。只有后端 lifecycle 同时返回同一
 * stable resourceId，且 exact snapshots 中确实存在该 resourceVersion，才允许把它绑定到
 * 当前画布。stateVersion 是会推进的并发令牌，不参与历史快照归属判断，验证通过后由
 * lifecycle 的权威值覆盖。
 */
export function validateBindingAgainstLifecycle(
  binding: unknown,
  lifecycle: Pick<CopyLifecycle, "resourceId" | "versions"> | null | undefined,
): CurrentDocumentBinding | null {
  const exact = parseCurrentDocumentBinding(binding);
  if (!exact || !lifecycle || lifecycle.resourceId !== exact.resourceId) return null;
  return lifecycle.versions.some(
    (snapshot) => snapshot.resourceVersion === exact.resourceVersion,
  )
    ? exact
    : null;
}

/**
 * A stream identity is only a pending claim.  A lifecycle mutation may use the
 * persisted binding only when both the pending claim and that binding belong to the
 * same authoritative lifecycle, and the binding still carries its current CAS token.
 * This is evaluated during render, so a new stream cannot borrow the previous
 * lifecycle during the effect gap before the new GET completes.
 */
export function resolveLifecycleWriteBinding(
  pendingBinding: unknown,
  verifiedBinding: unknown,
  lifecycle: Pick<CopyLifecycle, "resourceId" | "versions" | "stateVersion"> | null | undefined,
  lifecycleReady: boolean,
  currentThreadId: string,
): CurrentDocumentBinding | null {
  if (!lifecycleReady || !lifecycle) return null;
  const pending = validateBindingAgainstLifecycle(pendingBinding, lifecycle);
  const verified = validateBindingAgainstLifecycle(verifiedBinding, lifecycle);
  if (
    !pending ||
    !verified ||
    pending.ownerThreadId !== currentThreadId ||
    verified.ownerThreadId !== currentThreadId ||
    pending.resourceId !== verified.resourceId
  ) return null;
  if (verified.stateVersion !== lifecycle.stateVersion) return null;
  return verified;
}
