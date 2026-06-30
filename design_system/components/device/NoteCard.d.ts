import * as React from "react";

export interface NoteCardProps extends React.HTMLAttributes<HTMLDivElement> {
  /** Cover image URL. */
  image?: string | null;
  /** Note title (clamped to 2 lines, like the real feed). */
  title?: string;
  author?: string;
  /** Single-char author avatar initial. */
  authorInitial?: string;
  /** Like count display ("1.2k"). */
  likes?: string;
  /** Cover aspect ratio. @default "3 / 4" */
  ratio?: string;
  /** Render a faded skeleton placeholder (neighbouring cards). */
  dim?: boolean;
}

/** 小红书 waterfall-feed note card (cover, clamped title, author, likes). */
export function NoteCard(props: NoteCardProps): React.ReactElement;
