import * as React from "react";

export interface ThinkingStep {
  label: string;
  /** @default "pending" */
  state?: "done" | "active" | "pending";
}

export interface ThinkingLog {
  /** Timestamp string ("12:25:01"). */
  time?: string;
  text: string;
}

export interface ThinkingAuraProps extends React.HTMLAttributes<HTMLDivElement> {
  /** Panel heading. @default "思考轨迹 (Thinking Aura)" */
  title?: string;
  /** Stepper rows. */
  steps?: ThinkingStep[];
  /** Raw thought log lines; presence enables the expand toggle. */
  logs?: Array<ThinkingLog | string> | null;
  defaultOpen?: boolean;
}

/** The agent's live reasoning panel — breathing dot, stepper, collapsible log. */
export function ThinkingAura(props: ThinkingAuraProps): React.ReactElement;
