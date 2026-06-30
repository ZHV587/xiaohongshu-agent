import * as React from "react";

export interface TopicCardProps extends React.HTMLAttributes<HTMLDivElement> {
  /** 1-based position shown in the coral index chip. */
  index?: number;
  /** Topic headline. */
  title: string;
  /** One-line rationale ("主打：视觉冲击、高互动分享率"). */
  rationale?: string;
  /** Predicted viral rate 0–100; omit to hide the 爆款率 badge. */
  hotRate?: number | null;
  onClick?: () => void;
}

/**
 * Clickable viral-topic suggestion card with a 爆款率 badge.
 *
 * @startingPoint section="Content" subtitle="Agent-proposed viral topic with hot-rate" viewport="700x110"
 */
export function TopicCard(props: TopicCardProps): React.ReactElement;
