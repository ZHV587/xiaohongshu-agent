"use client";

import { useEffect, useMemo, useState, type ReactNode } from "react";
import { Avatar, Badge, Button, Card, Icon, IconButton, Input, Select, Textarea, ThinkingAura, TopicCard } from "@/components/ds";
import { useStudio } from "@/components/studio/useStudio";
import { AdminConfigPanel } from "@/components/studio/AdminConfigPanel";
import { useThreadOptional } from "@/components/thread/ThreadContext";
import { getContentString } from "@/components/thread/utils";
import { logout } from "@/lib/auth";
import { useThreadsOptional } from "@/providers/thread-context";

export function WorkbenchShell() {
  const { topics, timeline, actions, user } = useStudio();
  const [paletteOpen, setPaletteOpen] = useState(false);
  const [scanned, setScanned] = useState(false);
  const [flyKey, setFlyKey] = useState(0);

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "p") {
        event.preventDefault();
        setPaletteOpen((open) => !open);
      } else if (event.key === "Escape") {
        setPaletteOpen(false);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  const runCommand = (cmd: string) => {
    setPaletteOpen(false);
    if (cmd === "polish") actions.polish();
    if (cmd === "shorten") actions.shorten();
    if (cmd === "tags") actions.addTags();
  };

  return (
    <div style={{ height: "100vh", width: "100vw", display: "flex", flexDirection: "column", overflow: "hidden", color: "var(--text-body)", fontFamily: "var(--font-sans)", background: "var(--background)", position: "relative" }}>
      <h1 className="sr-only">小红书文案助手 Workbench</h1>
      <WorkbenchTopBar onReauth={() => setScanned(false)} onFly={() => { setFlyKey((value) => value + 1); actions.syncFeishu(); }} />
      <main style={{ flex: 1, display: "flex", minHeight: 0 }}>
        <WorkbenchSidebar onNew={actions.newChat} />
        <ChatPane onOpenPalette={() => setPaletteOpen(true)} />
        <RightCanvas
          scanned={scanned}
          onScan={() => setScanned(true)}
        />
      </main>
      {flyKey > 0 && <span key={flyKey} className="xhs-fly-to-sync" style={{ position: "fixed", left: 152, bottom: 92, zIndex: 90, fontSize: 22, pointerEvents: "none", animation: "xhs-fly-to-sync var(--dur-fly) var(--ease-spring) both" }}>🍠</span>}
      <CommandPalette open={paletteOpen} onClose={() => setPaletteOpen(false)} onRun={runCommand} />
      <div style={{ position: "fixed", left: 16, bottom: 12, fontSize: 10, color: "var(--text-subtle)" }}>
        Workbench · {user.handle || user.name || "未命名账号"} · {topics.length} topics · {timeline.length} turns
      </div>
    </div>
  );
}

function WorkbenchSidebar({ onNew }: { onNew: () => void }) {
  const { user } = useStudio();
  const thread = useThreadOptional();
  const threadsCtx = useThreadsOptional();
  const threadId = thread?.threadId ?? null;
  const setThreadId = thread?.setThreadId;
  const threads = threadsCtx?.threads ?? [];
  const getThreads = threadsCtx?.getThreads;
  const setThreads = threadsCtx?.setThreads;
  const setThreadsLoading = threadsCtx?.setThreadsLoading;
  const threadsLoading = threadsCtx?.threadsLoading ?? false;
  const [collapsed, setCollapsed] = useState(false);
  const [configOpen, setConfigOpen] = useState(false);

  useEffect(() => {
    if (!getThreads || !setThreads) return;
    let alive = true;
    setThreadsLoading?.(true);
    getThreads()
      .then((list) => { if (alive) setThreads(list); })
      .catch(() => {})
      .finally(() => { if (alive) setThreadsLoading?.(false); });
    return () => { alive = false; };
  }, [getThreads, setThreads, setThreadsLoading, threadId]);

  const threadTitle = (t: (typeof threads)[number]): string => {
    const values = t.values as { messages?: Array<{ content: unknown }> } | undefined;
    if (values && Array.isArray(values.messages) && values.messages.length > 0) {
      const first = getContentString(values.messages[0].content as never).trim();
      if (first) return first;
    }
    return "未命名创作";
  };

  if (collapsed) {
    return (
      <aside style={{ width: 52, background: "var(--surface-sidebar)", borderRight: "1px solid var(--border)", display: "flex", flexDirection: "column", alignItems: "center", gap: 10, padding: "14px 0", flexShrink: 0 }}>
        <button title="展开侧边栏" onClick={() => setCollapsed(false)} style={{ border: "none", background: "transparent", cursor: "pointer", color: "var(--text-muted)", display: "inline-flex", padding: 6 }}><Icon name="panel-left-open" size={18} /></button>
        <button title="开启全新灵感对话" onClick={onNew} style={{ border: "none", background: "var(--accent-surface)", color: "var(--primary)", cursor: "pointer", borderRadius: "var(--radius-sm)", display: "inline-flex", padding: 8 }}><Icon name="square-pen" size={16} /></button>
        <div style={{ marginTop: "auto" }}>
          <button title="管理员配置" onClick={() => setConfigOpen(true)} style={{ border: "none", background: "transparent", cursor: "pointer", color: "var(--text-muted)", display: "inline-flex", padding: 6 }}><Icon name="settings" size={18} /></button>
          <button title="退出登录" onClick={logout} style={{ border: "none", background: "transparent", cursor: "pointer", color: "var(--text-muted)", display: "inline-flex", padding: 6 }}><Icon name="log-out" size={18} /></button>
        </div>
        {configOpen && <AdminConfigPanel onClose={() => setConfigOpen(false)} />}
      </aside>
    );
  }

  return (
    <aside style={{ width: "var(--rail-sidebar)", background: "var(--surface-sidebar)", borderRight: "1px solid var(--border)", display: "flex", flexDirection: "column", justifyContent: "space-between", flexShrink: 0 }}>
      <div style={{ display: "flex", flexDirection: "column", padding: 16, gap: 16, overflow: "hidden", height: "100%" }}>
        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <Button variant="primary" block leftIcon={<Icon name="square-pen" size={16} />} onClick={onNew}>开启全新灵感对话</Button>
          <IconButton label="收起侧边栏" onClick={() => setCollapsed(true)}><Icon name="panel-left-close" size={16} /></IconButton>
        </div>

        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginTop: 4 }}>
          <span style={{ fontSize: 10, fontWeight: 800, letterSpacing: "0.08em", color: "var(--text-subtle)" }}>最近创作</span>
          <span style={{ fontSize: 10, color: "var(--gray-300)" }}>按 Ctrl+J 隐藏</span>
        </div>

        <div style={{ display: "flex", flexDirection: "column", gap: 4, overflowY: "auto", flex: 1 }} className="custom-scrollbar">
          {threads.length === 0 && (
            <span style={{ fontSize: 11, color: "var(--text-subtle)", padding: "8px 11px", lineHeight: 1.6 }}>
              {threadsLoading ? "加载中…" : "暂无最近创作，点上方开启新对话"}
            </span>
          )}
          {threads.map((item) => {
            const active = item.thread_id === threadId;
            return (
              <button
                key={item.thread_id}
                onClick={() => setThreadId?.(item.thread_id)}
                title={threadTitle(item)}
                style={{
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "space-between",
                  gap: 8,
                  width: "100%",
                  textAlign: "left",
                  padding: "10px 12px",
                  fontSize: "var(--text-sm)",
                  borderRadius: "var(--radius-sm)",
                  cursor: "pointer",
                  border: "none",
                  borderLeft: active ? "2px solid var(--primary)" : "2px solid transparent",
                  background: active ? "var(--oats-dark)" : "transparent",
                  color: active ? "var(--primary)" : "var(--text-muted)",
                  fontWeight: active ? "var(--weight-semibold)" : "var(--weight-regular)",
                  fontFamily: "var(--font-sans)",
                }}
              >
                <span style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                  🍠 {threadTitle(item)}
                </span>
                <Badge tone={active ? "synced" : "draft"} shape="chip">{active ? "当前" : "草稿"}</Badge>
              </button>
            );
          })}
        </div>
      </div>

      <div style={{ padding: 16, borderTop: "1px solid var(--oats-dark)", display: "flex", alignItems: "center", justifyContent: "space-between", gap: 8 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 12, minWidth: 0 }}>
          <Avatar name={user.initial || user.name || "Z"} />
          <span style={{ fontSize: "var(--text-sm)", fontWeight: "var(--weight-medium)", color: "var(--text-body)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{user.name || user.handle || "未命名账号"}</span>
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: 4, flexShrink: 0 }}>
          <IconButton label="管理员配置" onClick={() => setConfigOpen(true)}><Icon name="settings" /></IconButton>
          <IconButton label="退出登录" onClick={logout}><Icon name="log-out" /></IconButton>
        </div>
      </div>
      {configOpen && <AdminConfigPanel onClose={() => setConfigOpen(false)} />}
    </aside>
  );
}

function WorkbenchTopBar({ onReauth, onFly }: { onReauth: () => void; onFly: () => void }) {
  return (
    <header style={{ height: 56, background: "rgba(255,255,255,0.88)", backdropFilter: "blur(8px)", borderBottom: "1px solid var(--border)", padding: "0 20px", display: "flex", alignItems: "center", justifyContent: "space-between", flexShrink: 0, zIndex: 20 }}>
      <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
        <span style={{ width: 30, height: 30, borderRadius: "var(--radius-md)", background: "var(--coral-brand)", display: "flex", alignItems: "center", justifyContent: "center", fontSize: 16, boxShadow: "var(--shadow-coral)" }}>🍠</span>
        <span style={{ fontFamily: "var(--font-display)", fontWeight: 800, fontSize: "var(--text-base)", letterSpacing: "var(--tracking-tight)" }}>
          小红书文案助手
          <span style={{ fontFamily: "var(--font-sans)", fontSize: "var(--text-xs)", fontWeight: 400, color: "var(--text-subtle)", marginLeft: 8 }}>v1.2 工作台</span>
        </span>
        <Badge tone="synced" dot>飞书 CLI 状态：Ready (bot)</Badge>
      </div>
      <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
        <Button variant="soft" size="sm" leftIcon={<Icon name="key-round" size={13} />} onClick={onReauth}>User 身份已过期，点此扫码重连</Button>
        <Button variant="primary" size="sm" leftIcon={<Icon name="cloud-upload" size={13} />} onClick={onFly}>飞书同步</Button>
      </div>
    </header>
  );
}

function ChatPane({ onOpenPalette }: { onOpenPalette: () => void }) {
  const { timeline, topics, note, actions } = useStudio();
  const [draft, setDraft] = useState("");
  const writing = timeline.some((item) => item.kind === "thinking" && !item.run.done);
  const selectedTopic = topics.find((topic) => topic.id === note.topicId);
  return (
    <section style={{ flex: 1, display: "flex", flexDirection: "column", minWidth: 0, background: "var(--background)" }}>
      <div className="cs" style={{ flex: 1, overflowY: "auto", padding: 22, display: "flex", flexDirection: "column", gap: 18 }}>
        {timeline.length === 0 && (
          <div style={{ margin: "auto", maxWidth: 520, display: "flex", flexDirection: "column", alignItems: "center", gap: 12, textAlign: "center", color: "var(--text-muted)" }}>
            <Avatar glyph="🍠" variant="agent" size={44} />
            <div style={{ fontFamily: "var(--font-display)", fontWeight: 800, fontSize: "var(--text-lg)", color: "var(--text-body)" }}>三栏 Workbench 已就绪</div>
            <p style={{ margin: 0, fontSize: "var(--text-sm)", lineHeight: "var(--leading-relaxed)" }}>左侧历史 · 中间对话 · 右侧飞书同步协作。按 Ctrl+P 打开润色命令面板。</p>
          </div>
        )}
        {timeline.map((item, index) => {
          const key = `${item.kind}-${index}`;
          if (item.kind === "user") {
            return (
              <div key={key} style={{ display: "flex", gap: 11, maxWidth: "86%", alignSelf: "flex-end", flexDirection: "row-reverse" }}>
                <Avatar name="我" variant="solid" size={30} />
                <Bubble>{item.text}</Bubble>
              </div>
            );
          }
          if (item.kind === "thinking") {
            return (
              <div key={key} style={{ display: "flex", gap: 11, maxWidth: "92%" }}>
                <Avatar glyph="🍠" variant="agent" size={32} />
                <div style={{ flex: 1, maxWidth: 520 }}>
                  <ThinkingAura
                    steps={item.run.steps}
                    logs={item.run.logs.length ? item.run.logs : null}
                    defaultCollapsed={item.run.done}
                  />
                </div>
              </div>
            );
          }
          if (item.kind === "error") {
            return (
              <div key={key} style={{ display: "flex", gap: 11, maxWidth: "92%" }}>
                <Avatar glyph="🍠" variant="agent" size={32} />
                <StateNote tone="warning">{item.text || "响应失败，请稍后重试"}</StateNote>
              </div>
            );
          }
          if (item.kind === "ai") {
            return (
              <div key={key} style={{ display: "flex", gap: 11, maxWidth: "92%" }}>
                <Avatar glyph="🍠" variant="agent" size={32} />
                <Bubble>{item.text}</Bubble>
              </div>
            );
          }
          return null;
        })}
        {topics.length > 0 && (
          <Card padding="md">
            <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
              {topics.slice(0, 3).map((topic) => (
                <TopicCard key={topic.id} index={topic.id} title={topic.title} rationale={topic.rationale} hotRate={topic.hotRate} onClick={() => actions.chooseTopic(topic)} />
              ))}
            </div>
          </Card>
        )}
        {writing && (
          <div style={{ display: "flex", gap: 11, maxWidth: "92%" }}>
            <Avatar glyph="🍠" variant="agent" size={32} />
            <StateNote>
              正在针对《{selectedTopic?.title || note.title || "当前方向"}》撰写小红书风格文案，完成后可在右侧飞书同步协作。
            </StateNote>
          </div>
        )}
        {!writing && note.body && (
          <div style={{ display: "flex", gap: 11, maxWidth: "92%" }}>
            <Avatar glyph="🍠" variant="agent" size={32} />
            <StateNote>✅ 已完成，可继续润色或同步飞书。</StateNote>
          </div>
        )}
      </div>
      <div style={{ padding: 18, borderTop: "1px solid var(--border)", flexShrink: 0 }}>
        <Textarea
          rows={2}
          value={draft}
          onChange={(event) => setDraft(event.target.value)}
          placeholder="继续追问，或让 🍠 调整选题方向 / 改写文案…"
          footer={<>
            <button onClick={onOpenPalette} style={{ display: "inline-flex", alignItems: "center", gap: 6, background: "var(--surface-card)", border: "1px solid var(--border)", borderRadius: "var(--radius-sm)", padding: "5px 9px", cursor: "pointer" }}><kbd style={{ fontSize: 8, background: "var(--oats-light)", border: "1px solid var(--border)", padding: "1px 4px", borderRadius: 4, fontFamily: "var(--font-mono)" }}>Ctrl+P</kbd><span style={{ fontSize: "var(--text-xs)", color: "var(--text-muted)" }}>润色工具箱</span></button>
            <button type="button" style={{ display: "inline-flex", alignItems: "center", gap: 6, background: "var(--surface-card)", border: "1px solid var(--border)", borderRadius: "var(--radius-sm)", padding: "5px 9px", cursor: "pointer", color: "var(--text-muted)", fontSize: "var(--text-xs)" }}><Icon name="paperclip" size={12} /> 图片或 PDF</button>
            <Button variant="primary" size="sm" rightIcon={<Icon name="send" size={14} />} onClick={() => { if (draft.trim()) { actions.say(draft); setDraft(""); } }}>生成</Button>
          </>}
        />
      </div>
    </section>
  );
}

function Bubble({ children }: { children: ReactNode }) {
  return (
    <div style={{ background: "var(--surface-card)", border: "1px solid var(--border-coral)", borderRadius: "var(--radius-xl)", padding: "11px 15px", fontSize: "var(--text-sm)", lineHeight: "var(--leading-relaxed)", boxShadow: "var(--shadow-sm)", whiteSpace: "pre-wrap", overflowWrap: "anywhere" }}>
      {children}
    </div>
  );
}

function StateNote({ tone = "muted", children }: { tone?: "muted" | "warning"; children: ReactNode }) {
  return (
    <div style={{ border: `1px solid ${tone === "warning" ? "var(--border-coral)" : "var(--border)"}`, background: tone === "warning" ? "var(--accent-surface)" : "var(--oats-light)", color: tone === "warning" ? "var(--primary)" : "var(--text-muted)", borderRadius: "var(--radius-md)", padding: "9px 12px", fontSize: "var(--text-xs)", lineHeight: "var(--leading-relaxed)", flex: 1 }}>
      {children}
    </div>
  );
}

function RightCanvas({
  scanned,
  onScan,
}: {
  scanned: boolean;
  onScan: () => void;
}) {
  const { note } = useStudio();
  return (
    <section style={{ width: "var(--rail-canvas)", borderLeft: "1px solid var(--border)", background: "var(--surface-card)", display: "flex", flexDirection: "column", flexShrink: 0, boxShadow: "var(--shadow-lg)", zIndex: 10 }}>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 8, padding: "8px 10px", borderBottom: "1px solid var(--border)", background: "color-mix(in srgb, var(--oats-light) 50%, white)" }}>
        <div style={{ display: "inline-flex", alignItems: "center", gap: 6, padding: "7px 10px", borderRadius: "var(--radius-sm)", background: "var(--oats-dark)", color: "var(--primary)", boxShadow: "var(--shadow-xs)", fontSize: "var(--text-xs)", fontWeight: 700 }}>
          <Icon name="cloud-upload" size={13} /> 🔗 飞书同步协作
        </div>
      </div>
      <FeishuSync scanned={scanned} onScan={onScan} />
      <RightCanvasBottomBar body={note.body} />
    </section>
  );
}

function RightCanvasBottomBar({ body }: { body: string }) {
  return (
    <div style={{ height: 60, borderTop: "1px solid var(--border)", padding: "0 24px", background: "var(--surface-card)", display: "flex", alignItems: "center", justifyContent: "space-between", flexShrink: 0 }}>
      <span style={{ fontSize: "var(--text-xs)", color: "var(--text-subtle)" }} className="font-tabular">
        文案长度：{body.length} / 1000 字
      </span>
      <CopyButton body={body} />
    </div>
  );
}

function CopyButton({ body }: { body: string }) {
  const [done, setDone] = useState(false);
  const copy = async () => {
    await navigator.clipboard.writeText(body);
    setDone(true);
    window.setTimeout(() => setDone(false), 1600);
  };
  return (
    <Button variant="soft" size="sm" leftIcon={<Icon name={done ? "check" : "copy"} size={14} />} onClick={copy}>
      {done ? "已复制" : "一键复制纯文案"}
    </Button>
  );
}

function FeishuSync({ scanned, onScan }: { scanned: boolean; onScan: () => void }) {
  const { note } = useStudio();
  const [steps, setSteps] = useState(0);
  const [syncing, setSyncing] = useState(false);
  const stepLabels = ["正在验证飞书 CLI 环境配置...", "正在解析多维表格行结构与空字段映射...", "正在写入文案至多维表格..."];
  const runSync = () => {
    if (syncing) return;
    setSyncing(true);
    setSteps(1);
    let next = 1;
    const tick = () => {
      next += 1;
      setSteps(next);
      if (next <= 3) window.setTimeout(tick, 850);
      else window.setTimeout(() => { setSyncing(false); setSteps(0); }, 1800);
    };
    window.setTimeout(tick, 850);
  };

  return (
    <div className="cs" style={{ flex: 1, overflowY: "auto", padding: 20, display: "flex", flexDirection: "column", gap: 16 }}>
      <Card padding="md">
        <Row icon="database" iconTone="green" title="同步到飞书多维表格" sub="APP Token: bascnu… | Table ID: tblx…" badge={<Badge tone="synced">连接成功</Badge>} />
        <div style={{ display: "flex", flexDirection: "column", gap: 10, fontSize: "var(--text-xs)", marginTop: 14 }}>
          <KV k="绑定选题记录：" v={`${note.title || "当前草稿"} (草稿记录)`} />
          <KV k="飞书文档列映射：" v="「正文内容」字段" muted />
          <KV k="字数检测：" v={`${note.body.length} 字 (符合限制)`} ok />
        </div>
        {steps > 0 && (
          <div style={{ marginTop: 14, border: "1px solid var(--border-coral)", borderRadius: "var(--radius-md)", padding: 12, background: "var(--oats-light)", display: "flex", flexDirection: "column", gap: 8 }}>
            {stepLabels.map((label, index) => {
              const n = index + 1;
              const done = steps > n || steps === 4;
              const active = steps === n;
              return (
                <div key={label} style={{ display: "flex", alignItems: "center", gap: 8, fontSize: "var(--text-xs)", color: done ? "var(--success)" : active ? "var(--primary)" : "var(--text-subtle)", fontWeight: active ? 700 : 500 }}>
                  <span style={{ width: 14, textAlign: "center", animation: active ? "spin 1s linear infinite" : "none" }}>{done ? "✓" : active ? "◐" : "○"}</span>
                  {label}
                </div>
              );
            })}
          </div>
        )}
        <div style={{ marginTop: 14 }}>
          <Button variant="primary" block leftIcon={<Icon name="cloud-upload" size={16} />} onClick={runSync} loading={syncing}>
            {syncing ? "同步中…" : "立即同步至飞书多维表格"}
          </Button>
        </div>
      </Card>

      <Card padding="md">
        <Row icon="message-square" iconTone="blue" title="群发通知与协同审核" sub="机器人消息 / 个人卡片群发" badge={<Badge tone="info">配置可用</Badge>} />
        <div style={{ display: "flex", flexDirection: "column", gap: 8, marginTop: 14 }}>
          <label style={{ fontSize: "var(--text-xs)", color: "var(--text-muted)", fontWeight: 700 }}>选择接收通知的飞书群聊：</label>
          <Select options={["小红书文案运营审核群 (oc_chat_10293)", "露营项目内容策划小组 (oc_chat_88301)", "博主内容备份群 (oc_chat_73229)"]} />
        </div>
        <div style={{ marginTop: 14 }}>
          <Button variant="secondary" block leftIcon={<Icon name="send" size={16} />}>一键发送通知至飞书群聊</Button>
        </div>
      </Card>

      <div style={{ height: 240, perspective: 1000 }}>
        <div style={{ position: "relative", width: "100%", height: "100%", transformStyle: "preserve-3d", transition: "transform var(--dur-slow) var(--ease-out)", transform: scanned ? "rotateY(180deg)" : "none" }}>
          <div style={{ position: "absolute", inset: 0, backfaceVisibility: "hidden", background: "color-mix(in srgb, var(--hot-surface) 70%, white)", border: "1px solid var(--coral-300)", borderRadius: "var(--radius-lg)", padding: 18, display: "flex", flexDirection: "column", gap: 10 }}>
            <div style={{ display: "flex", gap: 8 }}>
              <Icon name="alert-triangle" size={17} color="var(--coral-600)" />
              <div>
                <h4 style={{ margin: 0, fontSize: "var(--text-xs)", fontWeight: 700, color: "var(--coral-700)" }}>飞书个人身份已过期</h4>
                <p style={{ margin: "2px 0 0", fontSize: 9, color: "var(--coral-600)" }}>若需以您的个人名义将文案导出至飞书云文档，请扫码进行 User 身份重连。</p>
              </div>
            </div>
            <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 8 }}>
              <button onClick={onScan} style={{ background: "#fff", padding: 8, border: "1px solid var(--coral-300)", borderRadius: "var(--radius-md)", boxShadow: "var(--shadow-md)", cursor: "pointer" }} title="点此模拟扫码成功">
                <div style={{ width: 84, height: 84, display: "grid", gridTemplateColumns: "repeat(3,1fr)", gap: 4, placeItems: "center" }}>
                  {[1, 0, 1, 0, 1, 0, 1, 0, 1].map((value, index) => (
                    <div key={index} style={{ width: 22, height: 22, background: value ? "var(--charcoal-default)" : "var(--gray-200)", borderRadius: 3 }} />
                  ))}
                </div>
              </button>
              <span style={{ fontSize: 8, color: "var(--coral-600)" }}>使用飞书扫码，授权 Scope 权限</span>
            </div>
          </div>
          <div style={{ position: "absolute", inset: 0, backfaceVisibility: "hidden", transform: "rotateY(180deg)", background: "var(--green-500)", color: "#fff", borderRadius: "var(--radius-lg)", padding: 18, display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", gap: 10, textAlign: "center" }}>
            <div style={{ width: 48, height: 48, borderRadius: "999px", background: "#fff", color: "var(--green-600)", display: "flex", alignItems: "center", justifyContent: "center", boxShadow: "var(--shadow-md)" }}><Icon name="check" size={28} /></div>
            <strong>飞书个人身份重连成功</strong>
            <span style={{ fontSize: "var(--text-xs)" }}>{note.title || "当前草稿"} 可继续同步。</span>
          </div>
        </div>
      </div>
    </div>
  );
}

function Row({ icon, iconTone, title, sub, badge }: { icon: string; iconTone: "green" | "blue"; title: string; sub: string; badge: ReactNode }) {
  const tones = {
    green: { bg: "var(--success-surface)", fg: "var(--success)", bd: "var(--success-border)" },
    blue: { bg: "var(--info-surface)", fg: "var(--info)", bd: "var(--info-border)" },
  };
  const tone = tones[iconTone];
  return (
    <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", borderBottom: "1px solid var(--oats-dark)", paddingBottom: 12 }}>
      <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
        <div style={{ width: 32, height: 32, borderRadius: "var(--radius-sm)", background: tone.bg, border: `1px solid ${tone.bd}`, color: tone.fg, display: "flex", alignItems: "center", justifyContent: "center" }}>
          <Icon name={icon} size={17} />
        </div>
        <div>
          <h4 style={{ margin: 0, fontSize: "var(--text-sm)", fontWeight: 700, color: "var(--text-body)" }}>{title}</h4>
          <p style={{ margin: "2px 0 0", fontSize: 10, color: "var(--text-subtle)" }}>{sub}</p>
        </div>
      </div>
      {badge}
    </div>
  );
}

function KV({ k, v, muted, ok }: { k: string; v: string; muted?: boolean; ok?: boolean }) {
  return (
    <div style={{ display: "flex", justifyContent: "space-between", gap: 12 }}>
      <span style={{ color: "var(--text-muted)" }}>{k}</span>
      <span style={{ fontWeight: 600, color: ok ? "var(--success)" : muted ? "var(--text-muted)" : "var(--text-body)", textAlign: "right" }}>{v}</span>
    </div>
  );
}

function CommandPalette({ open, onClose, onRun }: { open: boolean; onClose: () => void; onRun: (cmd: string) => void }) {
  const commands = useMemo(() => [
    { id: "polish", name: "润色语气", desc: "让正文更像小红书真人表达", icon: "sparkles", color: "var(--primary)" },
    { id: "shorten", name: "一键瘦身", desc: "压缩啰嗦段落和重复表达", icon: "scissors", color: "var(--success)" },
    { id: "tags", name: "补充话题标签", desc: "生成适配平台流量入口的话题", icon: "hash", color: "var(--topicblue-default)" },
  ], []);
  const [query, setQuery] = useState("");
  const filteredCommands = commands.filter((command) => (command.name + command.desc).toLowerCase().includes(query.toLowerCase()));
  if (!open) return null;
  return (
    <div onClick={onClose} style={{ position: "fixed", inset: 0, background: "rgba(15,15,16,0.32)", zIndex: 100, display: "flex", justifyContent: "center", alignItems: "flex-start", paddingTop: 88 }}>
      <div onClick={(event) => event.stopPropagation()} style={{ width: 500, maxWidth: "90vw", background: "var(--surface-card)", borderRadius: "var(--radius-lg)", border: "1px solid var(--border-coral)", boxShadow: "var(--shadow-2xl)", overflow: "hidden" }}>
        <div style={{ padding: 12, borderBottom: "1px solid var(--border)" }}>
          <Input
            autoFocus
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="输入命令或搜索动作..."
            leadingIcon={<Icon name="search" size={16} />}
            trailing={<kbd onClick={onClose} style={{ fontSize: 10, background: "var(--oats-dark)", border: "1px solid var(--border)", color: "var(--text-subtle)", padding: "1px 6px", borderRadius: 4, cursor: "pointer", fontFamily: "var(--font-mono)" }}>ESC</kbd>}
          />
        </div>
        <div style={{ padding: 8, display: "flex", flexDirection: "column", gap: 4, maxHeight: 260, overflowY: "auto" }}>
          {filteredCommands.map((command) => (
            <button key={command.id} onClick={() => onRun(command.id)} style={{ display: "flex", alignItems: "center", gap: 10, border: "none", background: "transparent", borderRadius: "var(--radius-md)", padding: "10px 12px", cursor: "pointer", textAlign: "left", color: "var(--text-body)" }}>
              <Icon name={command.icon} size={15} color={command.color} />
              <span style={{ fontSize: "var(--text-xs)" }}>
                <span style={{ fontWeight: 700, color: "var(--text-body)" }}>{command.name}</span>
                <span style={{ color: "var(--text-subtle)", marginLeft: 8 }}>{command.desc}</span>
              </span>
            </button>
          ))}
          {filteredCommands.length === 0 && <div style={{ padding: 16, fontSize: "var(--text-xs)", color: "var(--text-subtle)", textAlign: "center" }}>无匹配命令</div>}
        </div>
      </div>
    </div>
  );
}
