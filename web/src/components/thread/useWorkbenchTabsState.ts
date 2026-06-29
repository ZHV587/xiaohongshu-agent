import { type Dispatch, type SetStateAction, useState } from "react";
import type { SourceEvidence } from "./types";

export type WorkbenchTab = "mock" | "feishu" | "evidence";

export interface WorkbenchTabsSnapshot {
  rightTab: WorkbenchTab;
  selectedEvidence: SourceEvidence | null;
}

export interface WorkbenchTabsState extends WorkbenchTabsSnapshot {
  setRightTab: Dispatch<SetStateAction<WorkbenchTab>>;
  setSelectedEvidence: Dispatch<SetStateAction<SourceEvidence | null>>;
}

export function createWorkbenchTabsInitialState(): WorkbenchTabsSnapshot {
  return {
    rightTab: "mock",
    selectedEvidence: null,
  };
}

export function useWorkbenchTabsState(): WorkbenchTabsState {
  const initial = createWorkbenchTabsInitialState();
  const [rightTab, setRightTab] = useState<WorkbenchTab>(initial.rightTab);
  const [selectedEvidence, setSelectedEvidence] =
    useState<SourceEvidence | null>(initial.selectedEvidence);

  return {
    rightTab,
    setRightTab,
    selectedEvidence,
    setSelectedEvidence,
  };
}
