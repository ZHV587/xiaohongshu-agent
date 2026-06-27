import { createContext, useContext } from "react";

export interface ThreadActions {
  /** 以编程方式提交一条人类文本消息(复用 Thread 的提交逻辑)。
   *  stateUpdate:可选,把结构化数据直传 graph state(官方 state-update 通道),
   *  供工具经 InjectedState 注入、绕过 LLM 转写(如采纳的 selected_notes)。 */
  submitText: (text: string, stateUpdate?: Record<string, unknown>) => void;
}

export const ThreadActionsContext = createContext<ThreadActions | null>(null);

/** 消费 submitText。不在 Provider 内时返回 no-op，保证组件在任何上下文都不崩。 */
export function useThreadActions(): ThreadActions {
  const ctx = useContext(ThreadActionsContext);
  return ctx ?? { submitText: () => {} };
}
