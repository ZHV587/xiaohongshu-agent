import { createContext, useContext } from "react";
import { type Message } from "@langchain/langgraph-sdk";
import { useStream } from "@langchain/langgraph-sdk/react";
import {
  uiMessageReducer,
  isUIMessage,
  isRemoveUIMessage,
  type UIMessage,
  type RemoveUIMessage,
} from "@langchain/langgraph-sdk/react-ui";

export type ThinkingStepEvent = {
  type: "thinking_step";
  payload: {
    id: string;
    label: string;
    status: "running" | "done" | "failed" | "interrupted";
  };
};

export type StateType = {
  messages: Message[];
  ui?: UIMessage[];
  customEvents?: ThinkingStepEvent[]; // 新增自定义状态事件存储
};

export const useTypedStream = useStream<
  StateType,
  {
    UpdateType: {
      messages?: Message[] | Message | string;
      ui?: (UIMessage | RemoveUIMessage)[] | UIMessage | RemoveUIMessage;
      context?: Record<string, unknown>;
    };
    CustomEventType: UIMessage | RemoveUIMessage | ThinkingStepEvent;
  }
>;

export type StreamContextType = ReturnType<typeof useTypedStream>;
export const StreamContext = createContext<StreamContextType | undefined>(
  undefined,
);

export function reduceUiMessages(
  previous: UIMessage[] | undefined,
  event: UIMessage | RemoveUIMessage,
) {
  if (isUIMessage(event) || isRemoveUIMessage(event)) {
    return uiMessageReducer(previous ?? [], event);
  }
  return previous ?? [];
}

export function isStreamUiEvent(event: unknown): event is UIMessage | RemoveUIMessage {
  return isUIMessage(event) || isRemoveUIMessage(event);
}

export function isThinkingStepEvent(event: unknown): event is ThinkingStepEvent {
  return (
    typeof event === "object" &&
    event !== null &&
    "type" in event &&
    (event as any).type === "thinking_step"
  );
}

export const useStreamContext = (): StreamContextType => {
  const context = useContext(StreamContext);
  if (context === undefined) {
    throw new Error("useStreamContext must be used within a StreamProvider");
  }
  return context;
};
