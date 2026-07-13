"use client";

import { useMemo, useState, type CSSProperties, type ReactNode } from "react";
import { Badge, Button, Icon, Input } from "@/components/ds";
import { useCapabilityRegistry } from "./CapabilityRegistryContext";
import { filterCapabilities } from "./filters";
import { SkillManager } from "./SkillManager";
import { SkillStatus } from "./SkillStatus";
import type { BuiltinCapability, UserSkillRegistryItem, UserSkillSummary } from "./types";

export function CapabilityToolbox() {
  const registry = useCapabilityRegistry();
  const [query, setQuery] = useState("");
  const [request, setRequest] = useState("");
  const filtered = useMemo(
    () => filterCapabilities(registry.builtinCapabilities, registry.userSkills, query),
    [registry.builtinCapabilities, registry.userSkills, query],
  );
  const publishedById = useMemo(
    () => new Map(registry.publishedUserCapabilities.map((item) => [item.skillId, item])),
    [registry.publishedUserCapabilities],
  );

  if (registry.managerOpen) return <SkillManager />;
  if (!registry.toolboxOpen) return null;

  return (
    <div
      data-testid="capability-toolbox"
      onClick={registry.closeToolbox}
      style={{ position: "fixed", inset: 0, zIndex: 120, display: "flex", justifyContent: "center", alignItems: "flex-start", padding: "7vh 16px", background: "rgba(15,15,16,0.38)" }}
    >
      <section
        role="dialog"
        aria-modal="true"
        aria-label="能力工具箱"
        onClick={(event) => event.stopPropagation()}
        style={{ width: "min(760px, 96vw)", maxHeight: "86vh", display: "flex", flexDirection: "column", overflow: "hidden", borderRadius: "var(--radius-xl)", border: "1px solid var(--border-coral)", background: "var(--surface-card)", boxShadow: "var(--shadow-2xl)" }}
      >
        <header style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 12, padding: "14px 16px", borderBottom: "1px solid var(--border)" }}>
          <div>
            <div style={{ display: "flex", alignItems: "center", gap: 8, fontSize: "var(--text-sm)", fontWeight: 800 }}><Icon name="wand-2" size={16} color="var(--primary)" /> 能力工具箱</div>
            <div style={{ marginTop: 3, fontSize: 10, color: "var(--text-subtle)" }}>系统能力与个人 Skill 共用同一个入口 · Ctrl+P</div>
          </div>
          <div style={{ display: "flex", gap: 6 }}>
            <Button variant="soft" size="sm" leftIcon={<Icon name="settings-2" size={13} />} onClick={() => registry.openManager()}>管理我的 Skill</Button>
            <Button variant="ghost" size="sm" leftIcon={<Icon name="x" size={14} />} onClick={registry.closeToolbox}>关闭</Button>
          </div>
        </header>

        <div style={{ padding: 14, display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10, borderBottom: "1px solid var(--border)", background: "var(--oats-light)" }}>
          <Input autoFocus value={query} onChange={(event) => setQuery(event.target.value)} placeholder="搜索能力名称或说明…" leadingIcon={<Icon name="search" size={15} />} />
          <Input value={request} onChange={(event) => setRequest(event.target.value)} placeholder="这次想处理什么（可选）" leadingIcon={<Icon name="message-square" size={15} />} />
        </div>

        <div className="cs" style={{ flex: 1, overflowY: "auto", padding: 14, display: "flex", flexDirection: "column", gap: 16 }}>
          {registry.error && (
            <Notice tone="error">
              {registry.error}
              <button onClick={() => void registry.refreshSkills()} style={linkButtonStyle}>重新加载</button>
            </Notice>
          )}
          {registry.loading && <Notice>正在加载可用能力…</Notice>}

          <CapabilitySection title="系统内置能力" count={filtered.builtin.length}>
            {filtered.builtin.map((capability) => (
              <BuiltinRow key={capability.id} capability={capability} onRun={() => registry.executeBuiltin(capability, request)} />
            ))}
          </CapabilitySection>

          <CapabilitySection title="我的 Skill" count={filtered.user.length} action={<button onClick={() => registry.openManager()} style={linkButtonStyle}>新建或管理</button>}>
            {filtered.user.length === 0 ? (
              <EmptySkillState onCreate={() => registry.openManager()} />
            ) : filtered.user.map((skill) => (
              <UserSkillRow
                key={skill.id}
                skill={skill}
                published={publishedById.get(skill.id)}
                onExecute={(published) => void registry.executeUser(published, "execute", request)}
                onTest={() => void registry.executeUser(skill, "test", request)}
                onManage={() => registry.openManager(skill.id)}
              />
            ))}
          </CapabilitySection>

          {!registry.loading && filtered.builtin.length === 0 && filtered.user.length === 0 && (
            <Notice>没有匹配的能力，换个关键词试试。</Notice>
          )}
        </div>
      </section>
    </div>
  );
}

function CapabilitySection({ title, count, action, children }: { title: string; count: number; action?: ReactNode; children: ReactNode }) {
  return (
    <section>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 7 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 7 }}>
          <span style={{ fontSize: 10, fontWeight: 800, letterSpacing: "0.08em", color: "var(--text-subtle)" }}>{title}</span>
          <Badge tone="draft" shape="chip">{count}</Badge>
        </div>
        {action}
      </div>
      <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>{children}</div>
    </section>
  );
}

function BuiltinRow({ capability, onRun }: { capability: BuiltinCapability; onRun: () => void }) {
  return (
    <div style={rowStyle}>
      <div style={iconBoxStyle}><Icon name={capability.icon} size={16} color="var(--primary)" /></div>
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 7 }}>
          <strong style={{ fontSize: "var(--text-sm)" }}>{capability.displayName}</strong>
          <Badge tone="synced" shape="chip">内置</Badge>
        </div>
        <p style={descriptionStyle}>{capability.description}</p>
      </div>
      <Button variant="secondary" size="sm" onClick={onRun}>执行</Button>
    </div>
  );
}

function UserSkillRow({ skill, published, onExecute, onTest, onManage }: {
  skill: UserSkillSummary;
  published?: UserSkillRegistryItem;
  onExecute: (item: UserSkillRegistryItem) => void;
  onTest: () => void;
  onManage: () => void;
}) {
  return (
    <div style={rowStyle}>
      <div style={{ ...iconBoxStyle, background: "var(--topicblue-light)" }}><Icon name="bot" size={16} color="var(--topicblue-default)" /></div>
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 7 }}>
          <strong style={{ fontSize: "var(--text-sm)" }}>{skill.displayName}</strong>
          <SkillStatus status={skill.status} />
          <span style={{ fontSize: 9, color: "var(--text-subtle)" }}>v{skill.latestVersion}</span>
        </div>
        <p style={descriptionStyle}>{skill.description}</p>
      </div>
      <div style={{ display: "flex", gap: 5 }}>
        {skill.status === "published" && published && <Button size="sm" onClick={() => onExecute(published)}>执行</Button>}
        {skill.status === "draft" && <Button variant="soft" size="sm" onClick={onTest}>试运行</Button>}
        <Button variant="ghost" size="sm" onClick={onManage}>管理</Button>
      </div>
    </div>
  );
}

function EmptySkillState({ onCreate }: { onCreate: () => void }) {
  return (
    <button onClick={onCreate} style={{ ...rowStyle, borderStyle: "dashed", cursor: "pointer", textAlign: "left", color: "var(--text-muted)" }}>
      <div style={iconBoxStyle}><Icon name="plus" size={16} /></div>
      <span style={{ fontSize: "var(--text-xs)" }}>还没有个人 Skill，创建一个自己的工作流</span>
    </button>
  );
}

function Notice({ tone = "normal", children }: { tone?: "normal" | "error"; children: ReactNode }) {
  return <div style={{ padding: "10px 12px", borderRadius: "var(--radius-md)", background: tone === "error" ? "var(--accent-surface)" : "var(--oats-light)", color: tone === "error" ? "var(--primary)" : "var(--text-muted)", fontSize: "var(--text-xs)", display: "flex", justifyContent: "space-between", gap: 8 }}>{children}</div>;
}

const rowStyle: CSSProperties = { display: "flex", alignItems: "center", gap: 10, padding: "10px 11px", border: "1px solid var(--border)", borderRadius: "var(--radius-md)", background: "var(--surface-card)" };
const iconBoxStyle: CSSProperties = { width: 34, height: 34, borderRadius: "var(--radius-sm)", display: "flex", alignItems: "center", justifyContent: "center", background: "var(--accent-surface)", flexShrink: 0 };
const descriptionStyle: CSSProperties = { margin: "3px 0 0", fontSize: 10, color: "var(--text-subtle)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" };
const linkButtonStyle: CSSProperties = { border: "none", background: "transparent", padding: 0, color: "var(--primary)", cursor: "pointer", fontSize: 10, fontWeight: 700 };
