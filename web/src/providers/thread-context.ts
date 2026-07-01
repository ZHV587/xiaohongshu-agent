import { Thread } from "@langchain/langgraph-sdk";
import {
  createContext,
  useContext,
  type Dispatch,
  type SetStateAction,
} from "react";

export interface ThreadContextType {
  getThreads: () => Promise<Thread[]>;
  deleteThread: (threadId: string) => Promise<void>;
  threads: Thread[];
  setThreads: Dispatch<SetStateAction<Thread[]>>;
  threadsLoading: boolean;
  setThreadsLoading: Dispatch<SetStateAction<boolean>>;
}

export const ThreadContext = createContext<ThreadContextType | undefined>(
  undefined,
);

export function useThreads() {
  const context = useContext(ThreadContext);
  if (context === undefined) {
    throw new Error("useThreads must be used within a ThreadProvider");
  }
  return context;
}

/** 非抛出版:provider 不存在时返回 null(供 DEV 预览路由等无 ThreadProvider 的场景优雅降级)。 */
export function useThreadsOptional(): ThreadContextType | null {
  return useContext(ThreadContext) ?? null;
}
