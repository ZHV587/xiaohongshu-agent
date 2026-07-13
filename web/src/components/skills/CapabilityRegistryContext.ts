"use client";

import { createContext, useContext } from "react";
import type {
  BuiltinCapability,
  UserSkillDetail,
  UserSkillRegistryItem,
  UserSkillSummary,
} from "./types";

export interface CapabilityRegistryValue {
  builtinCapabilities: BuiltinCapability[];
  publishedUserCapabilities: UserSkillRegistryItem[];
  userSkills: UserSkillSummary[];
  loading: boolean;
  error: string | null;
  toolboxOpen: boolean;
  managerOpen: boolean;
  managerSkillId: string | null;
  openToolbox: () => void;
  closeToolbox: () => void;
  openManager: (skillId?: string | null) => void;
  closeManager: () => void;
  refreshSkills: () => Promise<void>;
  loadSkillDetail: (skillId: string, force?: boolean) => Promise<UserSkillDetail>;
  executeBuiltin: (capability: BuiltinCapability, request?: string) => void;
  executeUser: (skill: UserSkillSummary | UserSkillDetail | UserSkillRegistryItem, mode: "execute" | "test", request?: string) => Promise<void>;
}

export const CapabilityRegistryContext = createContext<CapabilityRegistryValue | null>(null);

export function useCapabilityRegistry(): CapabilityRegistryValue {
  const value = useContext(CapabilityRegistryContext);
  if (!value) throw new Error("useCapabilityRegistry must be used within CapabilityRegistryProvider");
  return value;
}
