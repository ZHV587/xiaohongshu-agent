"use client";

import { useState, type CSSProperties, type ReactNode, type Ref, type TextareaHTMLAttributes } from "react";

/**
 * Textarea — multi-line copy editor. Same focus treatment as
 * Input. Optional footer slot for char-count / actions, matching
 * the workbench composer and the in-place note editor.
 *
 * Faithfully ported 1:1 from design_system/components/forms/Textarea.jsx.
 */
export interface TextareaProps extends TextareaHTMLAttributes<HTMLTextAreaElement> {
  footer?: ReactNode;
  invalid?: boolean;
  innerRef?: Ref<HTMLTextAreaElement> | null;
  containerStyle?: CSSProperties;
}

export function Textarea({
  footer = null,
  invalid = false,
  rows = 4,
  innerRef = null,
  style = {},
  containerStyle = {},
  ...rest
}: TextareaProps) {
  const [focus, setFocus] = useState(false);

  return (
    <div
      style={{
        display: "flex",
        flexDirection: "column",
        background: "var(--surface-card)",
        border: `1px solid ${invalid ? "var(--primary)" : focus ? "var(--primary)" : "var(--border)"}`,
        borderRadius: "var(--radius-lg)",
        boxShadow: focus ? "var(--ring-focus)" : "var(--shadow-xs)",
        overflow: "hidden",
        transition: "border-color var(--dur-fast) var(--ease-out), box-shadow var(--dur-fast) var(--ease-out)",
        ...containerStyle,
      }}
    >
      <textarea
        ref={innerRef ?? undefined}
        rows={rows}
        onFocus={(e) => {
          setFocus(true);
          rest.onFocus?.(e);
        }}
        onBlur={(e) => {
          setFocus(false);
          rest.onBlur?.(e);
        }}
        style={{
          border: "none",
          outline: "none",
          resize: "none",
          background: "transparent",
          fontFamily: "var(--font-sans)",
          fontSize: "var(--text-sm)",
          lineHeight: "var(--leading-relaxed)",
          color: "var(--text-body)",
          padding: "0.875rem",
          ...style,
        }}
        {...rest}
      />
      {footer && (
        <div
          style={{
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            gap: "0.5rem",
            padding: "0.5rem 0.75rem",
            borderTop: "1px solid var(--border)",
            background: "var(--oats-light)",
          }}
        >
          {footer}
        </div>
      )}
    </div>
  );
}
