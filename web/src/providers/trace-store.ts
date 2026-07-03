import { createContext, useContext } from "react";

import type { TracePresentation, XhsTraceEvent } from "@/lib/agent-trace";

export interface TraceContextValue {
  presentationsByTurnId: Record<string, TracePresentation>;
  appendTraceEvent: (event: XhsTraceEvent) => void;
  clearTraceEvents: () => void;
}

export const TraceContext = createContext<TraceContextValue | null>(null);

export function useTraceContext(): TraceContextValue {
  const value = useContext(TraceContext);
  if (!value)
    throw new Error("useTraceContext must be used within TraceProvider");
  return value;
}
