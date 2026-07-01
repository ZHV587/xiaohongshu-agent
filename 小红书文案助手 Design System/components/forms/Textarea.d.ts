import * as React from "react";

export interface TextareaProps extends React.TextareaHTMLAttributes<HTMLTextAreaElement> {
  /** Footer slot (char count, action buttons) rendered below a divider. */
  footer?: React.ReactNode;
  /** Coral error border. */
  invalid?: boolean;
  /** @default 4 */
  rows?: number;
  /** Ref forwarded to the inner <textarea> (e.g. for cursor insertion). */
  innerRef?: React.Ref<HTMLTextAreaElement>;
  containerStyle?: React.CSSProperties;
}

/** Multi-line copy editor with optional footer (composer / in-place note editor). */
export function Textarea(props: TextareaProps): React.ReactElement;
