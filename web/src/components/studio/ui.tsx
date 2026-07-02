"use client";

// Studio shared UI helpers — faithfully ported from
// 小红书文案助手 Design System/ui_kits/studio/ui.jsx (Eyebrow / PanelHead) +
// the workbench ui.jsx. The prototype's CSS-mask Icon is replaced
// by ds/Icon (lucide-react). Inline styles preserved 1:1.

import type { CSSProperties, ReactNode } from "react";
import { Icon } from "@/components/ds";

export function Eyebrow({ children, style = {} }: { children: ReactNode; style?: CSSProperties }) {
  return (
    <div
      style={{
        fontSize: "var(--text-2xs)",
        fontWeight: 600,
        letterSpacing: "var(--tracking-wide)",
        textTransform: "uppercase",
        color: "var(--text-subtle)",
        ...style,
      }}
    >
      {children}
    </div>
  );
}

export function PanelHead({
  icon,
  title,
  sub,
  right,
}: {
  icon?: string;
  title: ReactNode;
  sub?: ReactNode;
  right?: ReactNode;
}) {
  return (
    <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 12 }}>
      <div style={{ display: "flex", alignItems: "center", gap: 8, minWidth: 0 }}>
        {icon && <Icon name={icon} size={16} color="var(--primary)" />}
        <div style={{ minWidth: 0 }}>
          <div style={{ fontSize: "var(--text-sm)", fontWeight: 700, color: "var(--text-body)" }}>{title}</div>
          {sub && <div style={{ fontSize: "var(--text-2xs)", color: "var(--text-subtle)", marginTop: 1 }}>{sub}</div>}
        </div>
      </div>
      {right}
    </div>
  );
}
