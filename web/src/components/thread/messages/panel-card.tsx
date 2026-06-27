import { useStreamContext } from "@/providers/stream-context";
import { useThread } from "../ThreadContext";
import { useState } from "react";
import { Loader2 } from "lucide-react";

interface PanelAction {
  label: string;
  text: string;
}

interface PanelData {
  actions: PanelAction[];
}

export function PanelCard({
  data,
  messageId,
}: {
  data: PanelData;
  messageId?: string;
}) {
  const stream = useStreamContext();
  const { submitText } = useThread();
  const [clickedIdx, setClickedIdx] = useState<number | null>(null);

  // 铁律：检测是否为最新消息且未处于加载状态
  const isLatest = !!messageId && stream.messages[stream.messages.length - 1]?.id === messageId;
  const isDisabled = !isLatest || stream.isLoading || clickedIdx !== null;

  const handleActionClick = (action: PanelAction, idx: number) => {
    if (isDisabled) return;
    setClickedIdx(idx);
    submitText(action.text);
  };

  if (!data.actions || data.actions.length === 0) return null;

  return (
    <div className="my-2 flex flex-wrap gap-2.5 select-none">
      {data.actions.map((action, idx) => {
        const isClicked = clickedIdx === idx;
        return (
          <button
            key={idx}
            type="button"
            disabled={isDisabled}
            onClick={() => handleActionClick(action, idx)}
            className={`flex items-center gap-1.5 rounded-full px-4 py-2 text-xs font-semibold shadow-xs active:scale-95 transition-all duration-300 cursor-pointer border
              ${
                isClicked
                  ? "bg-coral text-white border-coral"
                  : "bg-white text-coral border-coral/20 hover:bg-coral-light hover:border-coral/50"
              }
              disabled:opacity-50 disabled:cursor-not-allowed disabled:active:scale-100 disabled:hover:bg-white disabled:hover:border-coral/20 disabled:hover:text-coral
            `}
          >
            {isClicked && <Loader2 className="size-3 animate-spin text-white" />}
            {action.label}
          </button>
        );
      })}
    </div>
  );
}
