export type UserSkillStatus = "draft" | "published" | "disabled" | "archived";

export interface UserSkillDefinition {
  displayName: string;
  description: string;
  instructions: string;
  triggerExamples: string[];
  nonTriggerExamples: string[];
  tags: string[];
}

export interface UserSkillVersion {
  versionId: string;
  version: number;
  contentHash: string;
  createdAt: string;
  definition: UserSkillDefinition;
  skillMd: string;
}

export interface UserSkillSummary {
  id: string;
  runtimeName: string;
  status: UserSkillStatus;
  latestVersion: number;
  publishedVersion: number | null;
  displayName: string;
  description: string;
  tags: string[];
  updatedAt: string;
}

export interface UserSkillDetail {
  id: string;
  runtimeName: string;
  status: UserSkillStatus;
  latestVersion: number;
  publishedVersion: number | null;
  createdAt: string;
  updatedAt: string;
  latest: UserSkillVersion;
  versions: UserSkillVersion[];
}

export interface BuiltinCapability {
  id: string;
  displayName: string;
  description: string;
  prompt: string;
  icon: string;
}

export interface SystemSkillRegistryItem {
  name: string;
  displayName: string;
  description: string;
  source: "system";
  readonly: true;
}

export interface UserSkillRegistryItem {
  skillId: string;
  versionId: string;
  runtimeName: string;
  displayName: string;
  description: string;
  tags: string[];
  source: "user";
  readonly: false;
}

export type SkillRegistryItem = SystemSkillRegistryItem | UserSkillRegistryItem;

export type SkillAction = "publish" | "rollback" | "enable" | "disable" | "archive";

export interface SkillApiErrorPayload {
  ok?: false;
  error?: string;
  code?: string;
  fieldErrors?: Record<string, string>;
}

export const EMPTY_SKILL_DEFINITION: UserSkillDefinition = {
  displayName: "",
  description: "",
  instructions: "",
  triggerExamples: [],
  nonTriggerExamples: [],
  tags: [],
};
