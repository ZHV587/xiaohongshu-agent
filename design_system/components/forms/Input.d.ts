import * as React from "react";

export interface InputProps extends React.InputHTMLAttributes<HTMLInputElement> {
  /** Icon node before the field (e.g. search). */
  leadingIcon?: React.ReactNode;
  /** Node after the field (kbd hint, char count, clear button). */
  trailing?: React.ReactNode;
  /** Coral error border. */
  invalid?: boolean;
  /** Override styles on the wrapper. */
  containerStyle?: React.CSSProperties;
}

/** Single-line text field — oats rest, coral focus ring. */
export function Input(props: InputProps): React.ReactElement;
