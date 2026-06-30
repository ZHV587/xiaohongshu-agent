"use client";

// DEV-ONLY preview provider for /studio-preview. Implements the StudioStore
// contract over the design-package fixture with the prototype's interactive
// store logic (streaming draft, A/B/C versions, schedule), so the studio can
// be pixel-compared to design_system/ui_kits/studio WITHOUT the backend.
// NOT shipped — only /studio-preview imports it; that route is removed before
// production. The real product uses StudioProvider (live stream + APIs).

import { useCallback, useMemo, useRef, useState, type ReactNode } from "react";
import { toast } from "sonner";
import { StudioContext, type StudioStore } from "./StudioContext";
import type {
  CalendarDay,
  ChatMsg,
  SelectedEvidence,
  StudioNote,
  StudioSection,
  Topic,
  VersionId,
  Versions,
} from "./types";
import {
  FX_ACCOUNTS,
  FX_CALENDAR,
  FX_DASHBOARD,
  FX_EVIDENCE,
  FX_IMAGES,
  FX_LIBRARY,
  FX_MONTH,
  FX_PUBLISH_QUEUE,
  FX_RECENTS,
  FX_TEARDOWN,
  FX_TOPICS,
  FX_TRENDS,
  FX_USER,
} from "./preview-fixture";

const cut = (s: string) => (s.length > 20 ? s.slice(0, 20) : s);

function buildVersions(topic: Topic): Versions {
  const d = topic.draft;
  return {
    A: { ...d, label: "版本 A · 种草向", note: "原稿" },
    B: {
      label: "版本 B · 避坑向",
      note: "AI 改写",
      title: cut(`新手别乱买！${topic.kw}避坑清单`),
      cover: "避坑\n清单",
      body: `❌ 先说结论，这几样真的别冲！踩过坑才懂～\n\n` + d.body,
      tags: [...d.tags, "避坑指南", "平价平替"].slice(0, 9),
    },
    C: {
      label: "版本 C · 情绪向",
      note: "AI 改写",
      title: cut(`${topic.emotional} 🌿`),
      cover: d.cover,
      body: `🌅 有些瞬间，值得被认真记录下来。\n\n` + d.body,
      tags: [...d.tags, "氛围感", "治愈系"].slice(0, 9),
    },
  };
}

const IDLE_NOTE: StudioNote = { topicId: null, kw: "", title: "", body: "", tags: [], cover: "", status: "idle", activeVersion: "A", versions: null };

export function StudioPreviewProvider({ children }: { children: ReactNode }) {
  const [section, setSection] = useState<StudioSection>("create");
  const [activeRecent, setActiveRecent] = useState<number | null>(1);
  const [note, setNote] = useState<StudioNote>(IDLE_NOTE);
  const [calendar, setCalendar] = useState<CalendarDay[]>(FX_CALENDAR);
  const [chatExtra, setChatExtra] = useState<ChatMsg[]>([]);
  const [selectedEvidence, setSelectedEvidence] = useState<SelectedEvidence | null>(null);
  const [selectedAccount, setSelectedAccount] = useState<string | null>(null);
  const streamRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const showToast = useCallback((msg: string) => toast(msg), []);

  const chooseTopic = useCallback((topic: Topic, goSection: StudioSection = "create") => {
    if (streamRef.current) clearInterval(streamRef.current);
    const versions = buildVersions(topic);
    const full = versions.A;
    setSection(goSection);
    setActiveRecent(topic.id);
    setChatExtra([
      { who: "user", text: `写第 ${topic.id} 个：${topic.title}` },
      { who: "ai", thinking: true, text: `正在按小红书风格撰写《${topic.title}》，右侧创作栏流式生成中…` },
    ]);
    setNote({ topicId: topic.id, kw: topic.kw, title: "", body: "", tags: [], cover: full.cover, status: "writing", activeVersion: "A", versions });
    setTimeout(() => setNote((n) => (n.topicId === topic.id ? { ...n, title: full.title } : n)), 220);
    let i = 0;
    setTimeout(() => {
      streamRef.current = setInterval(() => {
        i += 6;
        const done = i >= full.body.length;
        setNote((n) => (n.topicId !== topic.id ? n : { ...n, body: full.body.slice(0, i), tags: done ? full.tags : n.tags, status: done ? "draft" : "writing" }));
        if (done) {
          if (streamRef.current) clearInterval(streamRef.current);
          setChatExtra((prev) => prev.map((m) => (m.thinking ? { who: "ai", text: `✅ 已生成《${full.title}》草稿。右侧可继续精修，文案体检达标即可定稿排期 →` } : m)));
        }
      }, 22);
    }, 420);
  }, []);

  const setVersion = useCallback((v: VersionId) => {
    setNote((n) => {
      const ver = n.versions?.[v];
      if (!ver) return n;
      return { ...n, title: ver.title, body: ver.body, tags: ver.tags, cover: ver.cover, activeVersion: v, status: "draft" };
    });
  }, []);

  const updateField = useCallback((field: keyof StudioNote, value: unknown) => {
    setNote((n) => ({ ...n, [field]: value, status: n.status === "writing" ? "writing" : "draft" }));
  }, []);

  const addTag = useCallback((tag: string) => setNote((n) => (n.tags.includes(tag) ? n : { ...n, tags: [...n.tags, tag].slice(0, 10), status: "draft" })), []);
  const removeTag = useCallback((tag: string) => setNote((n) => ({ ...n, tags: n.tags.filter((x) => x !== tag), status: "draft" })), []);

  const polish = useCallback(() => {
    setNote((n) => {
      if (!n.title) return n;
      const hook = "⛺ 夏日露营天花板，姐妹们冲鸭！✨\n\n";
      const body = n.body.startsWith("⛺ 夏日露营天花板") ? n.body : hook + n.body;
      const title = /\p{Extended_Pictographic}/u.test(n.title) || n.title.length > 18 ? n.title : n.title + " ✨";
      return { ...n, body, title, status: "draft" };
    });
    showToast("🍠 已按小红书语气润色，更有种草感 ✨");
  }, [showToast]);

  const shorten = useCallback(() => {
    setNote((n) => {
      if (!n.body) return n;
      const tagline = n.tags.slice(0, 4).map((x) => "#" + x).join(" ");
      return { ...n, body: n.body.slice(0, 240).trimEnd() + "…\n\n" + tagline, status: "draft" };
    });
    showToast("✂️ 已瘦身到精华段落");
  }, [showToast]);

  const addTags = useCallback(() => {
    setNote((n) => {
      const add = ["露营好物", "周末去哪儿", "夏日露营"].filter((x) => !n.tags.includes(x)).slice(0, 2);
      return { ...n, tags: [...n.tags, ...add].slice(0, 10), status: "draft" };
    });
    showToast("# 已补充长尾话题标签");
  }, [showToast]);

  const schedule = useCallback((date: number) => {
    setCalendar((cal) => {
      const item = { t: (note.title || "新笔记").slice(0, 8), time: "19:00", tone: "coral" as const, acct: "露" };
      return cal.some((d) => d.date === date) ? cal.map((d) => (d.date === date ? { ...d, items: [...d.items, item] } : d)) : [...cal, { date, items: [item] }];
    });
    setNote((n) => ({ ...n, status: "scheduled" }));
    showToast(`📅 已定稿并排期到 6 月 ${date} 日 19:00`);
  }, [note.title, showToast]);

  const newChat = useCallback(() => {
    if (streamRef.current) clearInterval(streamRef.current);
    setNote(IDLE_NOTE);
    setChatExtra([]);
    setSection("create");
    showToast("🆕 已开启新的创作会话");
  }, [showToast]);

  const say = useCallback((text: string) => {
    setChatExtra((prev) => [...prev, { who: "user", text }, { who: "ai", text: "收到～已结合你的补充在数据底座重新检索，更新了右侧选题卡 👉" }]);
  }, []);

  const store: StudioStore = useMemo(
    () => ({
      section,
      setSection,
      activeRecent,
      setActiveRecent,
      note,
      chatExtra,
      calendar,
      selectedEvidence,
      topics: FX_TOPICS,
      evidence: FX_EVIDENCE,
      user: FX_USER,
      images: FX_IMAGES,
      recents: FX_RECENTS,
      trends: FX_TRENDS,
      dashboard: FX_DASHBOARD,
      library: FX_LIBRARY,
      teardown: FX_TEARDOWN,
      accounts: FX_ACCOUNTS,
      month: FX_MONTH,
      publishQueue: FX_PUBLISH_QUEUE,
      selectedAccount,
      setSelectedAccount,
      loadState: {
        analytics: "ready",
        calendar: "ready",
        accounts: "ready",
        library: "ready",
        teardown: "ready",
        pipeline: "ready",
        recents: "ready",
        trends: "ready",
        images: "ready",
      },
      actions: {
        setSection,
        chooseTopic,
        setVersion,
        updateField,
        addTag,
        removeTag,
        polish,
        shorten,
        addTags,
        schedule,
        syncFeishu: () => showToast("🔗 已同步至飞书多维表格"),
        backfillSave: () => showToast("💾 真实数据已回填并沉淀飞书，将用于优化下一轮选题"),
        advanceStage: () => showToast("🚀 已推进发布管线阶段（示意）"),
        reuse: (id: number) => { const t = FX_TOPICS.find((x) => x.id === id); if (t) chooseTopic(t); },
        newChat,
        say,
        toast: showToast,
        openEvidence: setSelectedEvidence,
        closeEvidence: () => setSelectedEvidence(null),
      },
    }),
    [section, activeRecent, note, chatExtra, calendar, selectedEvidence, selectedAccount, chooseTopic, setVersion, updateField, addTag, removeTag, polish, shorten, addTags, schedule, newChat, say, showToast],
  );

  return <StudioContext.Provider value={store}>{children}</StudioContext.Provider>;
}
