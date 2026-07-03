"use client";

import Image from "next/image";
import type { CSSProperties, HTMLAttributes, ReactNode } from "react";

/**
 * NoteCard — a 小红书 waterfall-feed card: cover image, 2-line
 * clamped title, author + like count. `dim` renders a faded
 * placeholder (neighbouring feed cards).
 *
 * Faithfully ported 1:1 from 小红书文案助手 Design System/components/device/NoteCard.jsx.
 */
export interface NoteCardProps extends Omit<HTMLAttributes<HTMLDivElement>, "title"> {
  image?: string | null;
  title?: ReactNode;
  author?: ReactNode;
  authorInitial?: ReactNode;
  likes?: ReactNode;
  ratio?: string;
  dim?: boolean;
}

export function NoteCard({
  image = null,
  title = "",
  author = "",
  authorInitial = "",
  likes = "",
  ratio = "3 / 4",
  dim = false,
  style = {},
  ...rest
}: NoteCardProps) {
  if (dim) {
    return (
      <div style={{ background: "var(--surface-card)", borderRadius: "var(--radius-md)", overflow: "hidden", border: "1px solid var(--border)", opacity: 0.55, ...style }} {...rest}>
        <div style={{ width: "100%", aspectRatio: ratio, background: "var(--gray-200)" }} />
        <div style={{ padding: "0.5rem" }}>
          <div style={{ height: 10, width: "80%", background: "var(--gray-200)", borderRadius: 4, marginBottom: 6 }} />
          <div style={{ height: 8, width: "40%", background: "var(--gray-200)", borderRadius: 4 }} />
        </div>
      </div>
    );
  }

  return (
    <div
      style={{
        background: "var(--surface-card)",
        borderRadius: "var(--radius-md)",
        overflow: "hidden",
        border: "1px solid var(--border)",
        boxShadow: "var(--shadow-xs)",
        display: "flex",
        flexDirection: "column",
        ...style,
      }}
      {...rest}
    >
      <div style={{ position: "relative", width: "100%", aspectRatio: ratio, overflow: "hidden", background: "var(--accent-surface)" }}>
        {image && <Image src={image} alt={typeof title === "string" ? title : ""} fill sizes="220px" unoptimized style={{ objectFit: "cover" }} />}
      </div>
      <div style={{ padding: "0.5rem", display: "flex", flexDirection: "column", gap: "0.4rem" }}>
        <div
          style={{
            fontFamily: "var(--font-sans)",
            fontSize: "var(--text-2xs)",
            fontWeight: "var(--weight-bold)" as CSSProperties["fontWeight"],
            lineHeight: "var(--leading-snug)",
            color: "var(--text-body)",
            display: "-webkit-box",
            WebkitLineClamp: 2,
            WebkitBoxOrient: "vertical",
            overflow: "hidden",
          }}
        >
          {title}
        </div>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", fontSize: 9, color: "var(--text-subtle)" }}>
          <span style={{ display: "inline-flex", alignItems: "center", gap: 4 }}>
            <span style={{ width: 14, height: 14, borderRadius: "var(--radius-full)", background: "var(--oats-dark)", color: "var(--text-body)", display: "inline-flex", alignItems: "center", justifyContent: "center", fontWeight: 700, fontSize: 8 }}>{authorInitial}</span>
            <span style={{ maxWidth: 48, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{author}</span>
          </span>
          <span style={{ display: "inline-flex", alignItems: "center", gap: 2 }}>♥ {likes}</span>
        </div>
      </div>
    </div>
  );
}
