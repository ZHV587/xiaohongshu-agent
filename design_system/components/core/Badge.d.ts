import * as React from "react";

export interface BadgeProps extends React.HTMLAttributes<HTMLSpanElement> {
  /** Semantic tone. @default "neutral" */
  tone?: "neutral" | "synced" | "hot" | "topic" | "info" | "coral" | "draft";
  /** @default "pill" */
  shape?: "pill" | "chip";
  /** Show a leading status dot in the current color. */
  dot?: boolean;
  children?: React.ReactNode;
}

/** Compact status / meta pill (已同步, 草稿, 爆款率, 连接成功). */
export function Badge(props: BadgeProps): React.ReactElement;
