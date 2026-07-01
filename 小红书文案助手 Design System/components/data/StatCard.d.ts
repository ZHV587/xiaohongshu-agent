import * as React from "react";

export interface StatCardProps extends React.HTMLAttributes<HTMLDivElement> {
  /** Metric name ("点赞", "收藏", "新增粉丝"). */
  label: string;
  /** The value (string or number; formatted upstream, e.g. "1.2k"). */
  value: string | number;
  /** Trailing unit ("次", "人"). */
  unit?: string;
  /** Trend: a number (percent, +/- → up/down) or a label string. */
  delta?: number | string | null;
  /** Leading icon chip. */
  icon?: React.ReactNode;
  /** Value color. @default "neutral" */
  tone?: "neutral" | "coral" | "topic" | "success";
  /** Render the value as an editable field (数据回填). */
  editable?: boolean;
  onValueChange?: (value: string) => void;
}

/**
 * Metric tile for the 数据看板 dashboard; `editable` powers 数据回填.
 *
 * @startingPoint section="Data" subtitle="Metric tile with trend & editable backfill" viewport="700x150"
 */
export function StatCard(props: StatCardProps): React.ReactElement;
