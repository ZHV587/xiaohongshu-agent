import { createContext, useContext } from "react";

export interface ThreadActions {
  /** 以编程方式提交一条人类文本消息（复用 Thread 的提交逻辑） */
  submitText: (text: string) => void;
}

export const ThreadActionsContext = createContext<ThreadActions | null>(null);

/** 消费 submitText。不在 Provider 内时返回 no-op，保证组件在任何上下文都不崩。 */
export function useThreadActions(): ThreadActions {
  const ctx = useContext(ThreadActionsContext);
  return ctx ?? { submitText: () => {} };
}
