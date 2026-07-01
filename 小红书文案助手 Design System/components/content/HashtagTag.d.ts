import * as React from "react";

export interface HashtagTagProps extends React.HTMLAttributes<HTMLSpanElement> {
  /** Color. @default "topic" (blue) */
  tone?: "topic" | "coral" | "plain";
  /** Render a + affordance for the recommendation picker. */
  addable?: boolean;
  /** Click handler when addable. */
  onAdd?: () => void;
  children?: React.ReactNode;
}

/** 小红书 hashtag chip (#露营分享). A leading # is added if missing. */
export function HashtagTag(props: HashtagTagProps): React.ReactElement;
