// web/src/lib/thread-actions.tsx
import { ReactNode } from "react";
import { ThreadActionsContext, type ThreadActions } from "./thread-actions-context";

export function ThreadActionsProvider({
  value,
  children,
}: {
  value: ThreadActions;
  children: ReactNode;
}) {
  return (
    <ThreadActionsContext.Provider value={value}>
      {children}
    </ThreadActionsContext.Provider>
  );
}
