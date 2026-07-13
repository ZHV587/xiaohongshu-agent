import type { BuiltinCapability, UserSkillSummary } from "./types";

export function filterCapabilities(
  builtin: BuiltinCapability[],
  userSkills: UserSkillSummary[],
  query: string,
): { builtin: BuiltinCapability[]; user: UserSkillSummary[] } {
  const normalized = query.trim().toLocaleLowerCase();
  const matches = (name: string, description: string, tags: string[] = []) =>
    !normalized || `${name} ${description} ${tags.join(" ")}`.toLocaleLowerCase().includes(normalized);
  return {
    builtin: builtin.filter((item) => matches(item.displayName, item.description)),
    user: userSkills.filter((item) => item.status !== "archived" && matches(item.displayName, item.description, item.tags)),
  };
}
