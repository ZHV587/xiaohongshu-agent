import { type Dispatch, type SetStateAction, useEffect, useState } from "react";
import { toast } from "sonner";
import type { WorkbenchTab } from "./useWorkbenchTabsState";

export interface FeishuChat {
  chat_id: string;
  name: string;
}

export interface FeishuWorkspaceSnapshot {
  feishuChats: FeishuChat[];
  selectedChatId: string;
  isFetchingChats: boolean;
  isSendingNotification: boolean;
  isFeishuActionPending: boolean;
}

export interface FeishuWorkspaceState extends FeishuWorkspaceSnapshot {
  setFeishuChats: Dispatch<SetStateAction<FeishuChat[]>>;
  setSelectedChatId: Dispatch<SetStateAction<string>>;
  setIsFetchingChats: Dispatch<SetStateAction<boolean>>;
  setIsSendingNotification: Dispatch<SetStateAction<boolean>>;
  setIsFeishuActionPending: Dispatch<SetStateAction<boolean>>;
}

export function createFeishuWorkspaceInitialState(): FeishuWorkspaceSnapshot {
  return {
    feishuChats: [],
    selectedChatId: "",
    isFetchingChats: false,
    isSendingNotification: false,
    isFeishuActionPending: false,
  };
}

export function shouldFetchFeishuChats(
  rightTab: WorkbenchTab,
  chatCount: number,
): boolean {
  return rightTab === "feishu" && chatCount === 0;
}

export function pickInitialChatId(chats: FeishuChat[]): string {
  return chats[0]?.chat_id ?? "";
}

export function useFeishuWorkspaceState(
  rightTab: WorkbenchTab,
): FeishuWorkspaceState {
  const initial = createFeishuWorkspaceInitialState();
  const [feishuChats, setFeishuChats] = useState<FeishuChat[]>(
    initial.feishuChats,
  );
  const [selectedChatId, setSelectedChatId] = useState(initial.selectedChatId);
  const [isFetchingChats, setIsFetchingChats] = useState(
    initial.isFetchingChats,
  );
  const [isSendingNotification, setIsSendingNotification] = useState(
    initial.isSendingNotification,
  );
  const [isFeishuActionPending, setIsFeishuActionPending] = useState(
    initial.isFeishuActionPending,
  );

  useEffect(() => {
    if (!shouldFetchFeishuChats(rightTab, feishuChats.length)) return;

    setIsFetchingChats(true);
    fetch("/api/feishu/chats")
      .then((res) => {
        if (res.ok) return res.json();
        throw new Error("Unauthorized");
      })
      .then((data) => {
        if (data.ok && data.chats) {
          setFeishuChats(data.chats);
          setSelectedChatId(pickInitialChatId(data.chats));
        }
      })
      .catch(() => {
        toast.error("获取飞书群聊列表失败，请检查授权状态");
        setFeishuChats([]);
      })
      .finally(() => {
        setIsFetchingChats(false);
      });
  }, [rightTab, feishuChats.length]);

  return {
    feishuChats,
    setFeishuChats,
    selectedChatId,
    setSelectedChatId,
    isFetchingChats,
    setIsFetchingChats,
    isSendingNotification,
    setIsSendingNotification,
    isFeishuActionPending,
    setIsFeishuActionPending,
  };
}
