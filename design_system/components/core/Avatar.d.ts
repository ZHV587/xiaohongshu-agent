import * as React from "react";

export interface AvatarProps extends React.HTMLAttributes<HTMLDivElement> {
  /** Display name — initials are derived when no src/glyph. */
  name?: string;
  /** Image URL. */
  src?: string | null;
  /** Emoji/text glyph (e.g. "🍠" for the agent). */
  glyph?: string | null;
  /** Pixel diameter. @default 32 */
  size?: number;
  /** @default "coral" */
  variant?: "coral" | "solid" | "neutral" | "agent";
}

/** Circular user / agent avatar (initials, 🍠 glyph, or image). */
export function Avatar(props: AvatarProps): React.ReactElement;
