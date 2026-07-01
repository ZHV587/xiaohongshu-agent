import * as React from "react";

export interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  /** Visual style. @default "primary" */
  variant?: "primary" | "secondary" | "soft" | "ghost";
  /** Size. @default "md" */
  size?: "sm" | "md" | "lg";
  /** Stretch to full container width. */
  block?: boolean;
  /** Show a spinner and disable. */
  loading?: boolean;
  disabled?: boolean;
  /** Icon node rendered before the label. */
  leftIcon?: React.ReactNode;
  /** Icon node rendered after the label. */
  rightIcon?: React.ReactNode;
  children?: React.ReactNode;
}

/**
 * Primary action control for the 小红书 workbench.
 *
 * @startingPoint section="Core" subtitle="Coral CTA with 4 variants & 3 sizes" viewport="700x180"
 */
export function Button(props: ButtonProps): React.ReactElement;
