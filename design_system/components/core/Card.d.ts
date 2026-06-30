import * as React from "react";

export interface CardProps extends React.HTMLAttributes<HTMLDivElement> {
  /** Add coral hover lift for clickable cards. */
  interactive?: boolean;
  /** Surface tint. @default "default" */
  tone?: "default" | "sunken" | "coral";
  /** Inner padding. @default "md" */
  padding?: "none" | "sm" | "md" | "lg";
  children?: React.ReactNode;
}

/** White surface container on the oats canvas (panels, message bubbles, topic cards). */
export function Card(props: CardProps): React.ReactElement;
