"use client";

import {
  createContext,
  useCallback,
  useContext,
  useMemo,
  useState,
  type ReactNode,
} from "react";

import {
  isXhsTraceEvent,
  reduceTraceEvents,
  toTracePresentation,
  type TracePresentation,
  type TraceRunState,
  type XhsTraceEvent,
} from "@/lib/agent-trace";

interface TraceContextValue {
  presentationsByTurnId: Record<string, TracePresentation>;
  appendTraceEvent: (event: XhsTraceEvent) => void;
  clearTraceEvents: () => void;
}

const TraceContext = createContext<TraceContextValue | null>(null);

export function TraceProvider({ children }: { children: ReactNode }) {
  const [states, setStates] = useState<Record<string, TraceRunState>>({});

  const appendTraceEvent = useCallback((event: XhsTraceEvent) => {
    if (!isXhsTraceEvent(event)) return;
    setStates((prev) => ({
      ...prev,
      [event.trace_id]: reduceTraceEvents(prev[event.trace_id], [event]),
    }));
  }, []);

  const clearTraceEvents = useCallback(() => setStates({}), []);

  const presentationsByTurnId = useMemo(() => {
    const out: Record<string, TracePresentation> = {};
    for (const state of Object.values(states)) {
      const presentation = toTracePresentation(state);
      out[presentation.turnId] = presentation;
    }
    return out;
  }, [states]);

  return (
    <TraceContext.Provider
      value={{ presentationsByTurnId, appendTraceEvent, clearTraceEvents }}
    >
      {children}
    </TraceContext.Provider>
  );
}

export function useTraceContext(): TraceContextValue {
  const value = useContext(TraceContext);
  if (!value)
    throw new Error("useTraceContext must be used within TraceProvider");
  return value;
}
