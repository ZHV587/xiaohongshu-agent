"use client";

// 通用右侧滑出抽屉 —— v2 编辑器工具条点开的容器(版本/大纲/依据/文案体检/风控/标题优化)。
// 忠实移植自「小红书文案助手 Design System」studio-components.js 的 Drawer:内容多时不挤压
// 编辑区,遮罩点击 / 关闭按钮 / Esc 都走对称退场动画(复用 useDismiss,prefers-reduced-motion
// 兜底立即关闭)。同一时刻只开一个抽屉由调用方(DeepEditor 的单值 tool 状态)保证。

import { useEffect, type ReactNode } from "react";
import { Icon } from "@/components/ds";
import { useDismiss } from "@/components/studio/useDismiss";

export interface DrawerProps {
  open: boolean;
  onClose: () => void;
  title: ReactNode;
  icon?: string;
  /** 抽屉右侧宽度(px);默认 360,与原型一致。 */
  width?: number;
  children: ReactNode;
}

export function Drawer({ open, onClose, title, icon, width = 360, children }: DrawerProps) {
  const { closing, dismiss } = useDismiss(onClose);
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") dismiss();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, dismiss]);
  if (!open) return null;
  return (
    <div
      onClick={dismiss}
      className={closing ? "scrim-out" : "scrim-in"}
      style={{ position: "fixed", inset: 0, background: "rgba(15,15,16,0.35)", zIndex: 55, display: "flex", justifyContent: "flex-end" }}
    >
      <div
        onClick={(e) => e.stopPropagation()}
        className={`cs ${closing ? "slide-out-right" : "slide-in-right"}`}
        role="dialog"
        aria-label={typeof title === "string" ? title : undefined}
        style={{ width, maxWidth: "94vw", height: "100%", background: "var(--background)", boxShadow: "var(--shadow-2xl)", overflowY: "auto", display: "flex", flexDirection: "column" }}
      >
        <div style={{ position: "sticky", top: 0, background: "var(--surface-card)", borderBottom: "1px solid var(--border)", padding: "13px 16px", display: "flex", alignItems: "center", justifyContent: "space-between", zIndex: 1, flexShrink: 0 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 7 }}>
            {icon && <Icon name={icon} size={16} color="var(--primary)" />}
            <span style={{ fontSize: "var(--text-sm)", fontWeight: 700 }}>{title}</span>
          </div>
          <button onClick={dismiss} aria-label="关闭" title="关闭" style={{ border: "none", background: "none", cursor: "pointer", color: "var(--text-subtle)", display: "inline-flex" }}>
            <Icon name="x" size={16} />
          </button>
        </div>
        <div style={{ padding: 16, display: "flex", flexDirection: "column", gap: 14 }}>{children}</div>
      </div>
    </div>
  );
}
