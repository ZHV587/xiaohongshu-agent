import * as React from "react";

export interface SelectOption {
  value: string;
  label: string;
}

export interface SelectProps extends React.SelectHTMLAttributes<HTMLSelectElement> {
  /** Options as objects or plain strings; omit to use children <option>s. */
  options?: Array<SelectOption | string> | null;
  /** Coral error border. */
  invalid?: boolean;
  containerStyle?: React.CSSProperties;
  children?: React.ReactNode;
}

/** Native dropdown in the system field shell (oats rest, coral focus). */
export function Select(props: SelectProps): React.ReactElement;
