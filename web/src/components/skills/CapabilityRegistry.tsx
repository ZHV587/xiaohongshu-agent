"use client";

import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { toast } from "sonner";
import { useThread } from "@/components/thread/ThreadContext";
import { getUserSkill, listSkillRegistry, listUserSkills } from "./api";
import { CapabilityRegistryContext, type CapabilityRegistryValue } from "./CapabilityRegistryContext";
import type {
  BuiltinCapability,
  SkillRegistryItem,
  UserSkillDetail,
  UserSkillRegistryItem,
  UserSkillSummary,
} from "./types";

const SYSTEM_PRESENTATION: Record<string, Pick<BuiltinCapability, "displayName" | "prompt" | "icon">> = {
  "xhs-audit": { displayName: "内容质检与润色", prompt: "请检测当前内容的 AI 味和表达问题，并在保留原意的前提下给出润色建议。", icon: "sparkles" },
  "xhs-title": { displayName: "标题优化", prompt: "请根据当前内容优化小红书标题，给出不同角度的候选并说明差异。", icon: "type" },
  "xhs-hook": { displayName: "开头钩子优化", prompt: "请诊断当前内容的开头和首图钩子，并给出可直接替换的优化方案。", icon: "anchor" },
  "xhs-content": { displayName: "内容质量诊断", prompt: "请从内容形式、封面标题、表达效率、认知落差和转化动作诊断当前内容。", icon: "stethoscope" },
  "xhs-positioning": { displayName: "账号定位诊断", prompt: "请帮我诊断账号定位、目标人群、变现路径和内容转化动作。", icon: "compass" },
  "xhs-decision": { displayName: "运营决策复盘", prompt: "请帮我把当前运营问题整理成可验证的决策，并明确后续回填标准。", icon: "git-branch" },
};

function systemCapability(item: Extract<SkillRegistryItem, { source: "system" }>): BuiltinCapability {
  const presentation = SYSTEM_PRESENTATION[item.name];
  const displayName = presentation?.displayName ?? item.displayName;
  return {
    id: item.name,
    displayName,
    description: item.description,
    prompt: presentation?.prompt ?? `请使用「${displayName}」能力处理我的请求和当前上下文。`,
    icon: presentation?.icon ?? "wand-2",
  };
}

export function CapabilityRegistryProvider({ children }: { children: ReactNode }) {
  const thread = useThread();
  const [registry, setRegistry] = useState<SkillRegistryItem[]>([]);
  const [userSkills, setUserSkills] = useState<UserSkillSummary[]>([]);
  const detailsRef = useRef<Record<string, UserSkillDetail>>({});
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [toolboxOpen, setToolboxOpen] = useState(false);
  const [managerOpen, setManagerOpen] = useState(false);
  const [managerSkillId, setManagerSkillId] = useState<string | null>(null);

  const refreshSkills = useCallback(async () => {
    setLoading(true);
    try {
      const [management, available] = await Promise.all([listUserSkills(true), listSkillRegistry()]);
      setUserSkills(management.skills);
      setRegistry(available.items);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "能力列表加载失败，请稍后重试。");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    const timeout = window.setTimeout(() => void refreshSkills(), 0);
    return () => window.clearTimeout(timeout);
  }, [refreshSkills]);

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "p") {
        event.preventDefault();
        setManagerOpen(false);
        setToolboxOpen((open) => !open);
      } else if (event.key === "Escape") {
        setToolboxOpen(false);
        setManagerOpen(false);
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, []);

  const loadSkillDetail = useCallback(async (skillId: string, force = false) => {
    if (!force && detailsRef.current[skillId]) return detailsRef.current[skillId];
    const payload = await getUserSkill(skillId);
    detailsRef.current[skillId] = payload.skill;
    return payload.skill;
  }, []);

  const executeBuiltin = useCallback((capability: BuiltinCapability, request?: string) => {
    const extra = request?.trim();
    thread.submitText(extra ? `${capability.prompt}\n\n这次的具体要求：${extra}` : capability.prompt);
    setToolboxOpen(false);
  }, [thread]);

  const executeUser = useCallback(async (
    skill: UserSkillSummary | UserSkillDetail | UserSkillRegistryItem,
    mode: "execute" | "test",
    request?: string,
  ) => {
    try {
      const skillId = "skillId" in skill ? skill.skillId : skill.id;
      const registeredVersionId = "versionId" in skill ? skill.versionId : null;
      const detail = registeredVersionId && mode === "execute" ? null : await loadSkillDetail(skillId, true);
      if (mode === "execute" && !registeredVersionId && detail?.status !== "published") {
        throw new Error("只有已发布的能力可以正式执行；草稿可以先试运行。");
      }
      if (mode === "test" && !detail) throw new Error("找不到试运行版本，请刷新后重试。");
      const targetVersionId = registeredVersionId ?? (mode === "execute"
        ? detail?.versions.find((version) => version.version === detail.publishedVersion)?.versionId
        : detail?.latest.versionId);
      if (!targetVersionId) throw new Error("找不到可执行版本，请刷新后重试。");
      thread.executeUserSkill(
        request?.trim() || (mode === "test" ? "请试运行这项能力，并处理当前内容。" : "请使用我选择的能力处理当前内容。"),
        { skillId, versionId: targetVersionId, mode },
      );
      setToolboxOpen(false);
      setManagerOpen(false);
      toast.success(mode === "test" ? "已开始试运行" : "已开始执行能力");
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "能力执行失败，请稍后重试。");
    }
  }, [loadSkillDetail, thread]);

  const builtinCapabilities = useMemo(
    () => registry.filter((item): item is Extract<SkillRegistryItem, { source: "system" }> => item.source === "system").map(systemCapability),
    [registry],
  );
  const publishedUserCapabilities = useMemo(
    () => registry.filter((item): item is UserSkillRegistryItem => item.source === "user"),
    [registry],
  );

  const value = useMemo<CapabilityRegistryValue>(() => ({
    builtinCapabilities,
    publishedUserCapabilities,
    userSkills,
    loading,
    error,
    toolboxOpen,
    managerOpen,
    managerSkillId,
    openToolbox: () => { setManagerOpen(false); setToolboxOpen(true); },
    closeToolbox: () => setToolboxOpen(false),
    openManager: (skillId = null) => { setManagerSkillId(skillId); setToolboxOpen(false); setManagerOpen(true); },
    closeManager: () => setManagerOpen(false),
    refreshSkills,
    loadSkillDetail,
    executeBuiltin,
    executeUser,
  }), [
    builtinCapabilities, publishedUserCapabilities, userSkills, loading, error, toolboxOpen, managerOpen, managerSkillId,
    refreshSkills, loadSkillDetail, executeBuiltin, executeUser,
  ]);

  return <CapabilityRegistryContext.Provider value={value}>{children}</CapabilityRegistryContext.Provider>;
}
