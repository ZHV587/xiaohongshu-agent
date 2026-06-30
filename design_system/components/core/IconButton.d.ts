import * as React from "react";

export interface IconButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  /** @default "md" (28 / 36 / 44px) */
  size?: "sm" | "md" | "lg";
  /** @default "ghost" */
  variant?: "ghost" | "soft" | "solid" | "surface";
  /** Corner style. @default "md" */
  rounded?: "md" | "full";
  /** Accessible label (also the tooltip title). */
  label?: string;
  children?: React.ReactNode;
}

/** Square icon-only button (log-out, share, carousel arrows). */
export function IconButton(props: IconButtonProps): React.ReactElement;
