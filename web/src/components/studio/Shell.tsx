"use client";

// Studio shell — top bar with brand, section switcher, account chip;
// and the recents sidebar reused by the creation/deep screens.

import { useEffect, useState, type CSSProperties } from "react";
import { Avatar, Badge, Button, Icon } from "@/components/ds";
import { Eyebrow } from "@/components/studio/ui";
import { useStudio } from "@/components/studio/useStudio";
import { useThreadOptional } from "@/components/thread/ThreadContext";
import { useThreadsOptional } from "@/providers/thread-context";
import { getContentString } from "@/components/thread/utils";
import { AdminConfigPanel } from "@/components/studio/AdminConfigPanel";
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
        <nav aria-label="工作区切换" style={{ display: "flex", gap: 2, background: "var(--oats-dark)", borderRadius: "var(--radius-md)", padding: 3 }}>
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
  onNew: () => void;
  compact?: boolean;
}

/** 会话历史侧边栏:列真实 LangGraph 会话(useThreads),点击 setThreadId 切换加载;
 * 可收缩/展开;底部为管理员配置入口。取代旧的「内容资源 recents」列表。 */
export function Recents({ onNew, compact = false }: RecentsProps) {
  const thread = useThreadOptional();
  const threadsCtx = useThreadsOptional();
  const threadId = thread?.threadId ?? null;
  const setThreadId = thread?.setThreadId;
  const threads = threadsCtx?.threads ?? [];
  const getThreads = threadsCtx?.getThreads;
  const setThreads = threadsCtx?.setThreads;
  const setThreadsLoading = threadsCtx?.setThreadsLoading;
  const deleteThread = threadsCtx?.deleteThread;
  const threadsLoading = threadsCtx?.threadsLoading ?? false;
  const [collapsed, setCollapsed] = useState(false);
  const [configOpen, setConfigOpen] = useState(false);
  const [hoveredThread, setHoveredThread] = useState<string | null>(null);
  const [confirmDelete, setConfirmDelete] = useState<string | null>(null);
  const [deletingThread, setDeletingThread] = useState<string | null>(null);

  const handleDeleteThread = async (e: React.MouseEvent, targetId: string) => {
    e.stopPropagation(); // 不要触发行的 setThreadId(切换会话)
    if (!deleteThread || deletingThread) return;
    if (confirmDelete !== targetId) {
      setConfirmDelete(targetId); // 两击确认:首次点亮确认态,再点执行删除
      return;
    }
    setDeletingThread(targetId);
    try {
      await deleteThread(targetId);
      // 删的是当前会话:切回新对话空态(deleteThread 已从列表移除该项)
      if (targetId === threadId) onNew();
    } catch {
      /* 失败保持列表不变;deleteThread 内成功才移除,无需回滚 */
    } finally {
      setDeletingThread(null);
      setConfirmDelete(null);
    }
  };

  // 挂载时拉取真实会话列表并写入 context state(getThreads 只返回不写 state,须自行 setThreads,
  // 与旧 history 面板同款)。切换会话后 threadId 变化时刷新列表。空态由 threads.length===0 呈现,不 mock。
  // 无 ThreadProvider(DEV 预览路由)时 getThreads 为 undefined,跳过。
  useEffect(() => {
    if (!getThreads || !setThreads) return;
    let alive = true;
    setThreadsLoading?.(true);
    getThreads()
      .then((list) => { if (alive) setThreads(list); })
      .catch(() => { /* 拉取失败保持空态,不 mock */ })
      .finally(() => { if (alive) setThreadsLoading?.(false); });
    return () => { alive = false; };
  }, [getThreads, setThreads, setThreadsLoading, threadId]);

  const threadTitle = (t: (typeof threads)[number]): string => {
    const v = t.values as { messages?: Array<{ content: unknown }> } | undefined;
    if (v && Array.isArray(v.messages) && v.messages.length > 0) {
      const first = getContentString(v.messages[0].content as never).trim();
      if (first) return first;
    }
    return "未命名对话";
  };

  if (collapsed) {
    return (
      <aside style={{ width: 52, background: "var(--surface-sidebar)", borderRight: "1px solid var(--border)", display: "flex", flexDirection: "column", alignItems: "center", gap: 10, padding: "14px 0", flexShrink: 0 }}>
        <button title="展开侧边栏" onClick={() => setCollapsed(false)} style={{ border: "none", background: "transparent", cursor: "pointer", color: "var(--text-muted)", display: "inline-flex", padding: 6 }}><Icon name="panel-left-open" size={18} /></button>
        <button title="开启全新灵感对话" onClick={onNew} style={{ border: "none", background: "var(--accent-surface)", color: "var(--primary)", cursor: "pointer", borderRadius: "var(--radius-sm)", display: "inline-flex", padding: 8 }}><Icon name="square-pen" size={16} /></button>
        <div style={{ marginTop: "auto" }}>
          <button title="管理员配置" onClick={() => setConfigOpen(true)} style={{ border: "none", background: "transparent", cursor: "pointer", color: "var(--text-muted)", display: "inline-flex", padding: 6 }}><Icon name="settings" size={18} /></button>
        </div>
        {configOpen && <AdminConfigPanel onClose={() => setConfigOpen(false)} />}
      </aside>
    );
  }

  return (
    <aside style={{ width: compact ? 220 : 260, background: "var(--surface-sidebar)", borderRight: "1px solid var(--border)", display: "flex", flexDirection: "column", flexShrink: 0 }}>
      <div style={{ padding: 14, display: "flex", flexDirection: "column", gap: 14, flex: 1, overflow: "hidden" }}>
        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <Button variant="primary" block size="sm" leftIcon={<Icon name="square-pen" size={15} />} onClick={onNew}>开启全新灵感对话</Button>
          <button title="收起侧边栏" onClick={() => setCollapsed(true)} style={{ border: "none", background: "transparent", cursor: "pointer", color: "var(--text-muted)", display: "inline-flex", padding: 4, flexShrink: 0 }}><Icon name="panel-left-close" size={17} /></button>
        </div>
        <Eyebrow>历史会话</Eyebrow>
        <div className="cs" style={{ display: "flex", flexDirection: "column", gap: 4, overflowY: "auto", flex: 1 }}>
          {threads.length === 0 && (
            <span style={{ fontSize: 11, color: "var(--text-subtle)", padding: "8px 11px", lineHeight: 1.6 }}>
              {threadsLoading ? "加载中…" : "暂无历史会话,点上方开启新对话"}
            </span>
          )}
          {threads.map((t) => {
            const on = t.thread_id === threadId;
            const hovered = hoveredThread === t.thread_id;
            const confirming = confirmDelete === t.thread_id;
            const deleting = deletingThread === t.thread_id;
            return (
              <div
                key={t.thread_id}
                onMouseEnter={() => setHoveredThread(t.thread_id)}
                onMouseLeave={() => { setHoveredThread(null); if (confirmDelete === t.thread_id) setConfirmDelete(null); }}
                onClick={() => setThreadId?.(t.thread_id)}
                title={threadTitle(t)}
                style={{
                  display: "flex", alignItems: "center", gap: 8, width: "100%", textAlign: "left",
                  padding: "9px 11px", fontSize: "var(--text-sm)", borderRadius: "var(--radius-sm)", cursor: "pointer",
                  borderLeft: on ? "2px solid var(--primary)" : "2px solid transparent",
                  background: on ? "var(--oats-dark)" : hovered ? "var(--oats-light)" : "transparent",
                  color: on ? "var(--primary)" : "var(--text-muted)", fontWeight: on ? 600 : 400,
                } as CSSProperties}
              >
                <Icon name="message-square" size={13} />
                <span style={{ flex: 1, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{threadTitle(t)}</span>
                {deleteThread && (hovered || confirming || deleting) && (
                  <button
                    onClick={(e) => handleDeleteThread(e, t.thread_id)}
                    title={confirming ? "再次点击确认删除" : "删除会话"}
                    aria-label={confirming ? "确认删除会话" : "删除会话"}
                    disabled={deleting}
                    style={{
                      border: "none", background: "transparent", cursor: deleting ? "default" : "pointer",
                      color: confirming ? "var(--danger, #e5484d)" : "var(--text-subtle)",
                      display: "inline-flex", alignItems: "center", padding: 2, flexShrink: 0,
                    }}
                  >
                    <Icon name={deleting ? "loader" : confirming ? "check" : "trash-2"} size={13} />
                  </button>
                )}
              </div>
            );
          })}
        </div>
      </div>
      {/* 管理员配置入口(侧边栏下方) */}
      <div style={{ borderTop: "1px solid var(--border)", padding: 12 }}>
        <button onClick={() => setConfigOpen(true)} style={{ display: "flex", alignItems: "center", gap: 8, width: "100%", padding: "8px 11px", fontSize: "var(--text-sm)", borderRadius: "var(--radius-sm)", cursor: "pointer", border: "none", background: "transparent", color: "var(--text-muted)" }}>
          <Icon name="settings" size={15} /> 管理员配置
        </button>
      </div>
      {configOpen && <AdminConfigPanel onClose={() => setConfigOpen(false)} />}
    </aside>
  );
}
