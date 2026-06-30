"use client";

// Studio shell — top bar with brand, section switcher, account chip;
// and the recents sidebar reused by the creation/deep screens.

import type { CSSProperties } from "react";
import { Avatar, Badge, Button, Icon } from "@/components/ds";
import { Eyebrow } from "@/components/studio/ui";
import { useStudio } from "@/components/studio/StudioContext";
import type { StudioSection } from "@/components/studio/types";

interface StudioTopBarProps {
  section: StudioSection;
  setSection: (s: StudioSection) => void;
}

interface SectionDef {
  id: "create" | "ops";
  label: string;
  icon: string;
}

export function StudioTopBar({ section, setSection }: StudioTopBarProps) {
  const { user } = useStudio();
  const sections: SectionDef[] = [
    { id: "create", label: "创作", icon: "pen-line" },
    { id: "ops", label: "账号运营", icon: "line-chart" },
  ];
  return (
    <header style={{ height: 56, background: "rgba(255,255,255,0.88)", backdropFilter: "blur(8px)", borderBottom: "1px solid var(--border)", padding: "0 20px", display: "flex", alignItems: "center", justifyContent: "space-between", flexShrink: 0, zIndex: 20 }}>
      <div style={{ display: "flex", alignItems: "center", gap: 18 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 9 }}>
          <span style={{ width: 30, height: 30, borderRadius: "var(--radius-md)", background: "var(--coral-brand)", display: "flex", alignItems: "center", justifyContent: "center", fontSize: 16, boxShadow: "var(--shadow-coral)" }}>🍠</span>
          <span style={{ fontFamily: "var(--font-display)", fontWeight: 800, fontSize: "var(--text-base)", letterSpacing: "var(--tracking-tight)" }}>小红书创作运营工作室</span>
        </div>
        {/* section switcher */}
        <nav style={{ display: "flex", gap: 2, background: "var(--oats-dark)", borderRadius: "var(--radius-md)", padding: 3 }}>
          {sections.map((s) => {
            const on = section === s.id || (s.id === "create" && section === "deep");
            return (
              <button key={s.id} onClick={() => setSection(s.id)} style={{
                display: "inline-flex", alignItems: "center", gap: 6, padding: "6px 12px", borderRadius: "var(--radius-sm)", border: "none", cursor: "pointer",
                fontFamily: "var(--font-sans)", fontSize: "var(--text-xs)", fontWeight: on ? 700 : 500,
                background: on ? "var(--surface-card)" : "transparent", color: on ? "var(--primary)" : "var(--text-muted)",
                boxShadow: on ? "var(--shadow-xs)" : "none",
              }}>
                <Icon name={s.icon} size={14} /> {s.label}
              </button>
            );
          })}
        </nav>
      </div>
      <div style={{ display: "flex", alignItems: "center", gap: 14 }}>
        <Badge tone="synced" dot>飞书 CLI · Ready</Badge>
        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <Avatar name={user.initial || user.name} size={28} />
          <div style={{ lineHeight: 1.25 }}>
            <div style={{ fontSize: "var(--text-xs)", fontWeight: 600 }}>{user.name || user.handle}</div>
            <div style={{ fontSize: 10, color: "var(--text-subtle)" }}>粉丝 {user.fans} · {user.team}</div>
          </div>
        </div>
      </div>
    </header>
  );
}

interface RecentsProps {
  activeId: number | null;
  onSelect: (id: number) => void;
  onNew: () => void;
  compact?: boolean;
}

export function Recents({ activeId, onSelect, onNew, compact = false }: RecentsProps) {
  const { recents } = useStudio();
  return (
    <aside style={{ width: compact ? 220 : 260, background: "var(--surface-sidebar)", borderRight: "1px solid var(--border)", display: "flex", flexDirection: "column", flexShrink: 0 }}>
      <div style={{ padding: 14, display: "flex", flexDirection: "column", gap: 14, flex: 1, overflow: "hidden" }}>
        <Button variant="primary" block size="sm" leftIcon={<Icon name="square-pen" size={15} />} onClick={onNew}>开启全新灵感对话</Button>
        <Eyebrow>最近创作</Eyebrow>
        <div className="cs" style={{ display: "flex", flexDirection: "column", gap: 4, overflowY: "auto" }}>
          {recents.map((r) => {
            const on = r.id === activeId;
            return (
              <button key={r.id} onClick={() => onSelect(r.id)} style={{
                display: "flex", alignItems: "center", justifyContent: "space-between", gap: 8, width: "100%", textAlign: "left",
                padding: "9px 11px", fontSize: "var(--text-sm)", borderRadius: "var(--radius-sm)", cursor: "pointer", border: "none",
                borderLeft: on ? "2px solid var(--primary)" : "2px solid transparent",
                background: on ? "var(--oats-dark)" : "transparent", color: on ? "var(--primary)" : "var(--text-muted)", fontWeight: on ? 600 : 400,
              } as CSSProperties}>
                <span style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{r.icon} {r.title}</span>
                <Badge tone={r.status === "synced" ? "synced" : "draft"} shape="chip">{r.status === "synced" ? "已同步" : "草稿"}</Badge>
              </button>
            );
          })}
        </div>
      </div>
    </aside>
  );
}
