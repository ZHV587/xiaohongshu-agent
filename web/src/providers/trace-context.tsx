"use client";

import {
  useCallback,
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
import { TraceContext } from "./trace-store";

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
