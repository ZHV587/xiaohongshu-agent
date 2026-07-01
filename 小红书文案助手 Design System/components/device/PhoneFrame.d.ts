import * as React from "react";

export interface PhoneFrameProps extends React.HTMLAttributes<HTMLDivElement> {
  /** Bezel width in px (height follows a 9:18.5 ratio). @default 340 */
  width?: number;
  children?: React.ReactNode;
}

/** Charcoal iPhone bezel with notch for the 小红书 mobile preview. */
export function PhoneFrame(props: PhoneFrameProps): React.ReactElement;
