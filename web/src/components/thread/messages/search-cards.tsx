// web/src/components/thread/messages/search-cards.tsx
import { useMemo, useState } from "react";
import { motion } from "framer-motion";
import { Heart, Star, MessageCircle, Share2, Flame, ExternalLink, Check, BookmarkCheck, Sparkles } from "lucide-react";
import { useThreadActions } from "@/lib/thread-actions-context";
import { cn } from "@/lib/utils";

export interface NoteCard {
  note_id: string;
  resource_id?: string;
  title?: string;
  summary?: string;
  author?: string;
  author_fans?: number;
  cover_url?: string;
  note_url?: string;
  likes?: number;
  collects?: number;
  comments?: number;
  shares?: number;
  interactive?: number;
  created_at?: string;
  tags?: string[];
  scores?: { relevance?: number; popularity?: number; recency?: number; total?: number };
  source?: "online" | "local";
  already_local?: boolean;
}

export interface SearchToolResult {
  ok?: boolean;
  reason?: string;
  error?: string;
  results?: NoteCard[];
  related_searches?: string[];
}

function fmt(n?: number): string {
  const v = n ?? 0;
  if (v >= 10000) return `${(v / 10000).toFixed(1)}万`;
  if (v >= 1000) return `${(v / 1000).toFixed(1)}k`;
  return String(v);
}

function CoverImage({ url, title }: { url?: string; title?: string }) {
  const [errored, setErrored] = useState(false);
  if (!url || errored) {
    return (
      <div className="flex aspect-[3/4] w-[88px] flex-shrink-0 self-start items-center justify-center rounded-2xl border border-black/5 bg-oats-dark/50 text-[10px] text-charcoal-light">
        无封面
      </div>
    );
  }
  return (
    <img
      src={url}
      alt={title || "封面"}
      loading="lazy"
      referrerPolicy="no-referrer"
      onError={() => setErrored(true)}
      className="aspect-[3/4] w-[88px] flex-shrink-0 self-start rounded-2xl object-cover border border-black/5 shadow-2xs bg-oats-dark/40 hover:scale-[1.02] transition-transform duration-300"
    />
  );
}

function InteractionChips({ note }: { note: NoteCard }) {
  return (
    <div className="flex flex-wrap items-center gap-1.5 text-[10px] text-muted-foreground">
      {note.interactive ? (
        <span className="inline-flex items-center gap-1 rounded-md bg-coral/5 px-1.5 py-0.5 font-medium text-coral">
          <Flame className="size-3" /> {fmt(note.interactive)}
        </span>
      ) : null}
      <span className="inline-flex items-center gap-1 rounded-md bg-muted/60 px-1.5 py-0.5">
        <Heart className="size-3 text-muted-foreground/70" /> {fmt(note.likes)}
      </span>
      <span className="inline-flex items-center gap-1 rounded-md bg-muted/60 px-1.5 py-0.5">
        <Star className="size-3 text-muted-foreground/70" /> {fmt(note.collects)}
      </span>
      <span className="inline-flex items-center gap-1 rounded-md bg-muted/60 px-1.5 py-0.5">
        <MessageCircle className="size-3 text-muted-foreground/70" /> {fmt(note.comments)}
      </span>
      {note.shares ? (
        <span className="inline-flex items-center gap-1 rounded-md bg-muted/60 px-1.5 py-0.5">
          <Share2 className="size-3 text-muted-foreground/70" /> {fmt(note.shares)}
        </span>
      ) : null}
    </div>
  );
}

function Card({
  note,
  selectable,
  selected,
  onToggle,
  onGenTopic,
}: {
  note: NoteCard;
  selectable: boolean;
  selected: boolean;
  onToggle: () => void;
  onGenTopic: () => void;
}) {
  const collected = note.already_local === true;
  return (
    <motion.div
      initial={{ opacity: 0, y: 6 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.2 }}
      className={cn(
        "flex gap-3 rounded-2xl border bg-card p-3 shadow-xs transition-all hover:-translate-y-0.5 hover:shadow-[0_6px_20px_-8px_rgba(229,46,64,0.15)]",
        selected ? "border-coral ring-1 ring-coral/30" : "border-border",
      )}
    >
      <CoverImage url={note.cover_url} title={note.title} />
      <div className="flex min-w-0 flex-1 flex-col gap-1.5">
        <div className="flex items-start gap-2">
          <p className="line-clamp-2 flex-1 text-sm font-semibold text-charcoal">{note.title || "(无标题)"}</p>
          {collected ? (
            <span className="inline-flex flex-shrink-0 items-center gap-0.5 rounded-full bg-oats-dark/60 px-1.5 py-0.5 text-[10px] text-charcoal-light">
              <BookmarkCheck className="size-3" /> 已收录
            </span>
          ) : note.source === "online" ? (
            <span className="inline-flex flex-shrink-0 items-center gap-0.5 rounded-full bg-coral-light/40 px-1.5 py-0.5 text-[10px] text-coral">
              🔥 实时
            </span>
          ) : (
            <span className="inline-flex flex-shrink-0 items-center gap-0.5 rounded-full bg-oats-dark/50 px-1.5 py-0.5 text-[10px] text-charcoal-light">
              📚 已收录
            </span>
          )}
        </div>
        {(note.author || note.author_fans) && (
          <p className="text-[11px] text-charcoal-light">
            @{note.author || "佚名"}{note.author_fans ? ` · ${fmt(note.author_fans)} 粉` : ""}
          </p>
        )}
        {note.summary && <p className="line-clamp-2 text-[11px] leading-relaxed text-charcoal-light">{note.summary}</p>}
        <InteractionChips note={note} />
        {note.tags && note.tags.length > 0 && (
          <div className="flex flex-wrap gap-1">
            {note.tags.map((t, i) => (
              <span key={i} className="rounded-full bg-oats-light/60 px-1.5 py-0.5 text-[10px] text-charcoal-light">
                #{String(t).replace(/^#/, "")}
              </span>
            ))}
          </div>
        )}
        {note.scores?.total ? (
          <div className="flex flex-wrap gap-2 text-[10px] text-charcoal-light/80">
            <span>相关 {note.scores.relevance ?? 0}</span>
            <span>热度 {note.scores.popularity ?? 0}</span>
            <span>时效 {note.scores.recency ?? 0}</span>
          </div>
        ) : null}
        <div className="mt-0.5 flex flex-wrap items-center justify-between gap-2">
          {note.note_url ? (
            <a
              href={note.note_url}
              target="_blank"
              rel="noreferrer"
              className="inline-flex items-center gap-0.5 text-[11px] text-coral hover:underline hover:text-coral/80 transition-colors duration-300"
            >
              查看原文 <ExternalLink className="size-3" />
            </a>
          ) : <span />}
          <div className="flex items-center gap-1.5">
            <button
              type="button"
              onClick={onGenTopic}
              className="inline-flex items-center gap-1 rounded-full border border-coral/40 bg-coral-light/30 px-2.5 py-1 text-[11px] font-medium text-coral transition-all duration-300 ease-[cubic-bezier(0.16,1,0.3,1)] hover:bg-coral hover:text-white hover:shadow-2xs active:scale-95 cursor-pointer"
            >
              <Sparkles className="size-3" /> 出选题
            </button>
            {selectable && (
              collected ? (
                <span className="text-[11px] text-charcoal-light">已在库中</span>
              ) : (
                <button
                  type="button"
                  onClick={onToggle}
                  className={cn(
                    "inline-flex items-center gap-1 rounded-full border px-2.5 py-1 text-[11px] font-medium transition-all duration-300 ease-[cubic-bezier(0.16,1,0.3,1)] active:scale-95 cursor-pointer",
                    selected ? "border-coral bg-coral text-white hover:bg-coral/95" : "border-border bg-white text-charcoal hover:border-coral",
                  )}
                >
                  {selected ? <><Check className="size-3" /> 已选</> : "选择"}
                </button>
              )
            )}
          </div>
        </div>
      </div>
    </motion.div>
  );
}

export function SearchCards({ toolName, data }: { toolName: string; data: SearchToolResult }) {
  const { submitText } = useThreadActions();
  const isOnline = toolName === "search_xhs_online";
  const results = useMemo(() => data?.results ?? [], [data]);
  const [selected, setSelected] = useState<Set<string>>(new Set());

  if (isOnline && data?.ok === false) {
    return (
      <div className="mx-auto my-2 max-w-3xl rounded-xl border border-border bg-oats-light/30 px-3.5 py-2 text-xs text-charcoal-light">
        线上检索服务暂时不可用,仅展示本地结果。
      </div>
    );
  }
  if (!results.length) {
    return (
      <div className="mx-auto my-2 max-w-3xl rounded-xl border border-border bg-oats-light/30 px-3.5 py-2 text-xs text-charcoal-light">
        {isOnline
          ? "红狐线上暂无该关键词的近期热门笔记(小众/长词组常见;换更宽泛的核心词可能有结果)。"
          : "本地暂无相关已收录笔记。"}
      </div>
    );
  }

  const adoptable = results.filter((n) => isOnline && !n.already_local && n.note_id);
  const allSelected = adoptable.length > 0 && adoptable.every((n) => selected.has(n.note_id));

  const toggle = (id: string) =>
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });

  const toggleAll = () =>
    setSelected((prev) => (allSelected ? new Set() : new Set(adoptable.map((n) => n.note_id))));

  const adopt = () => {
    const picked = results.filter((n) => selected.has(n.note_id));
    if (!picked.length) return;
    const payload = picked.map((n) => ({
      note_id: n.note_id,
      title: n.title,
      summary: n.summary,
      author: n.author,
      author_fans: n.author_fans,
      cover_url: n.cover_url,
      note_url: n.note_url,
      likes: n.likes,
      collects: n.collects,
      comments: n.comments,
      shares: n.shares,
      interactive: n.interactive,
      created_at: n.created_at,
      tags: n.tags,
    }));
    // 选中的笔记经 graph state(selected_notes)直传工具,绝不进对话文本/不经 LLM 转写。
    // 消息只是触发指令 + 给 HITL/思考链一个可读意图。
    submitText(
      `采纳收录选中的 ${picked.length} 条线上笔记到数据库和飞书爆款采集库,请调用 adopt_online_notes。`,
      { selected_notes: payload },
    );
    setSelected(new Set());
  };

  const genTopic = (note: NoteCard) => {
    const payload = {
      note_id: note.note_id,
      resource_id: note.resource_id,   // 本地有;线上无
      title: note.title,
      summary: note.summary,
      author: note.author,
      author_fans: note.author_fans,
      cover_url: note.cover_url,
      note_url: note.note_url,
      likes: note.likes,
      collects: note.collects,
      comments: note.comments,
      shares: note.shares,
      interactive: note.interactive,
      created_at: note.created_at,
      tags: note.tags,
      source: note.source,
    };
    submitText(
      "我选这篇笔记,基于它帮我出一个选题。请分析它的角度/痛点/钩子,产出 1 个可执行的小红书选题" +
        "(一句话角度 + 预期爆点),并说明依据;本地笔记引用其 resource_id,线上笔记(无 resource_id)" +
        "在角度里注明(线上实时:note_url)并提示我采纳收录后可作正式依据。出选题只展示,我认可了再落库。\n\n" +
        "笔记数据:\n```json\n" +
        JSON.stringify(payload, null, 2) +
        "\n```",
    );
  };

  return (
    <div className="mx-auto my-2 flex max-w-3xl flex-col gap-2.5">
      <div className="flex items-center justify-between px-1">
        <h4 className="text-xs font-bold text-charcoal">
          {isOnline ? "🔥 线上实时发现" : "📚 我们已收录"}
          <span className="ml-1 font-normal text-charcoal-light">({results.length})</span>
        </h4>
        {isOnline && adoptable.length > 0 && (
          <div className="flex items-center gap-2">
            <button type="button" onClick={toggleAll} className="text-[11px] text-charcoal-light hover:text-coral">
              {allSelected ? "取消全选" : "全选"}
            </button>
            <button
              type="button"
              onClick={adopt}
              disabled={selected.size === 0}
              className="rounded-full bg-coral px-3 py-1 text-[11px] font-semibold text-white shadow-xs transition-all hover:bg-coral-hover active:scale-95 disabled:opacity-40"
            >
              采纳选中 ({selected.size})
            </button>
          </div>
        )}
      </div>
      <div className="grid grid-cols-1 gap-2.5 sm:grid-cols-2">
        {results.map((note, i) => (
          <Card
            key={note.note_id || i}
            note={note}
            selectable={isOnline}
            selected={selected.has(note.note_id)}
            onToggle={() => toggle(note.note_id)}
            onGenTopic={() => genTopic(note)}
          />
        ))}
      </div>
      {data?.related_searches && data.related_searches.length > 0 && (
        <div className="flex flex-wrap items-center gap-1.5 px-1 pt-1">
          <span className="text-[11px] text-charcoal-light">相关搜索:</span>
          {data.related_searches.slice(0, 6).map((s, i) => (
            <button
              key={i}
              type="button"
              onClick={() => submitText(`帮我搜索"${s}"的本地和线上笔记。`)}
              className="rounded-full border border-border bg-white px-2 py-0.5 text-[11px] text-charcoal-light hover:border-coral hover:text-coral"
            >
              {s}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
