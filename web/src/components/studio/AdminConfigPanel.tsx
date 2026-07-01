"use client";

// 管理员配置面板:承载飞书配置 / LLM 模型配置 / 运行事实 三页(复用 thread/history 下现成组件)。
// studio 侧边栏「管理员配置」入口打开;各页鉴权由后端 config API 把关。作为覆盖层浮窗渲染。

import { useState, type CSSProperties } from "react";
import { Icon } from "@/components/ds";
import { FeishuConfigPage } from "@/components/thread/history/FeishuConfigPage";
import { LlmConfigPage } from "@/components/thread/history/LlmConfigPage";
import { RuntimeFactsPage } from "@/components/thread/history/RuntimeFactsPage";

type Tab = "feishu" | "llm" | "facts";

const TABS: { id: Tab; label: string; icon: string }[] = [
  { id: "llm", label: "模型配置", icon: "settings-2" },
  { id: "feishu", label: "飞书配置", icon: "database" },
  { id: "facts", label: "运行事实", icon: "activity" },
];

export function AdminConfigPanel({ onClose }: { onClose: () => void }) {
  const [tab, setTab] = useState<Tab>("llm");

  const overlay: CSSProperties = {
    position: "fixed", inset: 0, background: "rgba(15,15,16,0.35)", zIndex: 60,
    display: "flex", justifyContent: "center", alignItems: "flex-start", padding: "5vh 16px",
  };
  const panel: CSSProperties = {
    width: "min(920px, 96vw)", maxHeight: "90vh", background: "var(--background)",
    borderRadius: "var(--radius-lg)", boxShadow: "var(--shadow-2xl)", overflow: "hidden",
    display: "flex", flexDirection: "column",
  };

  return (
    <div onClick={onClose} style={overlay}>
      <div onClick={(e) => e.stopPropagation()} style={panel}>
        <header style={{ display: "flex", alignItems: "center", justifyContent: "space-between", padding: "14px 18px", borderBottom: "1px solid var(--border)", background: "var(--surface-card)" }}>
          <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
            <span style={{ fontSize: "var(--text-sm)", fontWeight: 700 }}>管理员配置</span>
            <nav style={{ display: "flex", gap: 2, background: "var(--oats-dark)", borderRadius: "var(--radius-md)", padding: 3 }}>
              {TABS.map((t) => {
                const on = tab === t.id;
                return (
                  <button key={t.id} onClick={() => setTab(t.id)} style={{
                    display: "inline-flex", alignItems: "center", gap: 6, padding: "6px 12px", borderRadius: "var(--radius-sm)", border: "none", cursor: "pointer",
                    fontSize: "var(--text-xs)", fontWeight: on ? 700 : 500,
                    background: on ? "var(--surface-card)" : "transparent", color: on ? "var(--primary)" : "var(--text-muted)",
                    boxShadow: on ? "var(--shadow-xs)" : "none",
                  }}>
                    <Icon name={t.icon} size={13} /> {t.label}
                  </button>
                );
              })}
            </nav>
          </div>
          <button onClick={onClose} title="关闭" style={{ border: "none", background: "none", cursor: "pointer", color: "var(--text-subtle)", display: "inline-flex" }}><Icon name="x" size={18} /></button>
        </header>
        <div style={{ flex: 1, overflowY: "auto", padding: 18, background: "var(--background)" }}>
          {tab === "llm" && <LlmConfigPage onClose={onClose} />}
          {tab === "feishu" && <FeishuConfigPage onClose={onClose} />}
          {tab === "facts" && <RuntimeFactsPage onClose={onClose} />}
        </div>
      </div>
    </div>
  );
}
