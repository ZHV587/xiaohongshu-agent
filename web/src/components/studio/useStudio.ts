"use client";

import { createContext, useContext } from "react";
import type { StudioStore } from "./StudioContext";

export const StudioContext = createContext<StudioStore | null>(null);

export function useStudio(): StudioStore {
  const ctx = useContext(StudioContext);
  if (!ctx) throw new Error("useStudio must be used within a StudioProvider");
  return ctx;
}
