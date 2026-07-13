import type {
  SkillAction,
  SkillRegistryItem,
  SkillApiErrorPayload,
  UserSkillDefinition,
  UserSkillDetail,
  UserSkillSummary,
} from "./types";

export class SkillApiError extends Error {
  constructor(
    message: string,
    public readonly status: number,
    public readonly code?: string,
    public readonly fieldErrors: Record<string, string> = {},
  ) {
    super(message);
  }
}

async function requestJson<T>(url: string, init?: RequestInit): Promise<T> {
  const response = await fetch(url, {
    cache: "no-store",
    ...init,
    headers: init?.body
      ? { "Content-Type": "application/json", ...(init.headers ?? {}) }
      : init?.headers,
  });
  const payload = (await response.json().catch(() => ({}))) as T & SkillApiErrorPayload;
  if (!response.ok || payload.ok === false) {
    throw new SkillApiError(
      friendlySkillError(payload.code, payload.error, response.status),
      response.status,
      payload.code,
      payload.fieldErrors,
    );
  }
  return payload;
}

export function friendlySkillError(code?: string, fallback?: string, status?: number): string {
  const messages: Record<string, string> = {
    SKILL_NAME_CONFLICT: "已有同名能力，请换一个名称。",
    SKILL_VERSION_CONFLICT: "这个能力已在别处更新，请刷新后再试。",
    SKILL_NOT_FOUND: "这个能力不存在，或你没有访问权限。",
    SKILL_PAYLOAD_TOO_LARGE: "能力说明过长，请精简后再保存。",
    SKILL_FIELD_NOT_ALLOWED: "自定义能力不能申请工具、脚本或额外权限。",
    SKILL_INVALID_INPUT: "能力定义不完整，请检查标红字段。",
    SKILL_INVALID_JSON: "提交内容格式有误，请刷新后重试。",
    SKILL_INVALID_BODY: "提交内容格式有误，请刷新后重试。",
    SKILL_CONFLICT: "当前状态不允许执行这个操作，请刷新后再试。",
    SKILL_INTERNAL_ERROR: "能力服务暂时不可用，请稍后重试。",
  };
  if (code && messages[code]) return messages[code];
  if (status === 401) return "登录已过期，请重新登录。";
  if (status === 403) return "你没有权限执行这项操作。";
  if (status && status >= 500) return "能力服务暂时不可用，请稍后重试。";
  return fallback && /[\u3400-\u9fff]/.test(fallback) ? fallback : "能力操作失败，请稍后重试。";
}

export async function listUserSkills(includeArchived = true): Promise<{ skills: UserSkillSummary[]; revision: number }> {
  return requestJson(`/api/skills?includeArchived=${String(includeArchived)}`);
}

export async function listSkillRegistry(): Promise<{ items: SkillRegistryItem[] }> {
  return requestJson("/api/skills/registry");
}

export async function getUserSkill(skillId: string): Promise<{ skill: UserSkillDetail }> {
  return requestJson(`/api/skills/${encodeURIComponent(skillId)}`);
}

export async function validateUserSkill(definition: UserSkillDefinition): Promise<{ definition: UserSkillDefinition; skillMd: string }> {
  return requestJson("/api/skills/validate", {
    method: "POST",
    body: JSON.stringify(definition),
  });
}

export async function createUserSkill(definition: UserSkillDefinition): Promise<{ skill: UserSkillDetail }> {
  return requestJson("/api/skills", {
    method: "POST",
    body: JSON.stringify(definition),
  });
}

export async function appendUserSkillVersion(
  skillId: string,
  expectedLatestVersion: number,
  definition: UserSkillDefinition,
): Promise<{ skill: UserSkillDetail }> {
  return requestJson(`/api/skills/${encodeURIComponent(skillId)}`, {
    method: "PATCH",
    body: JSON.stringify({ ...definition, expectedLatestVersion }),
  });
}

export async function runUserSkillAction(
  skillId: string,
  action: SkillAction,
  version?: number,
): Promise<{ skill: UserSkillDetail; revision: number }> {
  return requestJson(`/api/skills/${encodeURIComponent(skillId)}/${action}`, {
    method: "POST",
    body: JSON.stringify(version == null ? {} : { version }),
  });
}
