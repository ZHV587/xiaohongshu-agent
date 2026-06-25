import * as Dialog from "@radix-ui/react-dialog";
import { useThread } from "./ThreadContext";

export function CommandPalette() {
  const {
    showCommandPalette,
    setShowCommandPalette,
    cmdSearch,
    setCmdSearch,
    handleExecuteCommand,
  } = useThread();

  return (
    <Dialog.Root
      open={showCommandPalette}
      onOpenChange={setShowCommandPalette}
    >
      <Dialog.Portal>
        <Dialog.Overlay className="bg-charcoal-dark/30 data-[state=closed]:animate-out data-[state=open]:animate-in data-[state=closed]:fade-out-0 data-[state=open]:fade-in-0 fixed inset-0 z-50 backdrop-blur-xs" />
        <Dialog.Content
          aria-modal="true"
          className="border-coral-light data-[state=closed]:animate-out data-[state=open]:animate-in data-[state=closed]:fade-out-0 data-[state=open]:fade-in-0 data-[state=closed]:zoom-out-95 data-[state=open]:zoom-in-95 fixed top-1/2 left-1/2 z-50 flex max-h-[min(70vh,520px)] w-[min(500px,calc(100vw-32px))] -translate-x-1/2 -translate-y-1/2 flex-col gap-3 overflow-hidden rounded-2xl border bg-white p-4 shadow-2xl outline-none"
        >
          <Dialog.Title className="sr-only">智能润色工具箱</Dialog.Title>
          <Dialog.Description className="sr-only">
            搜索并执行小红书文案润色、精简和话题推荐指令。
          </Dialog.Description>
          <div className="flex items-center gap-2 border-b pb-2">
            <span className="bg-coral-light text-coral rounded px-2 py-1 text-sm font-bold">
              Ctrl+P
            </span>
            <input
              type="text"
              placeholder="搜索润色指令 (e.g. /polish, /shorten)..."
              value={cmdSearch}
              onChange={(e) => setCmdSearch(e.target.value)}
              className="min-h-12 flex-1 border-none text-sm outline-none focus:ring-0"
              autoFocus
            />
          </div>
          <div className="flex flex-col gap-1 overflow-y-auto text-xs">
            <button
              type="button"
              onClick={() => handleExecuteCommand("polish")}
              className="group hover:bg-oats flex min-h-12 cursor-pointer items-center justify-between rounded-xl p-3 text-left transition-colors"
            >
              <span>
                <span className="text-coral font-bold">/polish</span>
                <span className="text-charcoal-light ml-2">
                  智能精细润色文案
                </span>
              </span>
              <span className="group-hover:text-coral text-[10px] font-medium text-gray-400">
                执行 Enter
              </span>
            </button>
            <button
              type="button"
              onClick={() => handleExecuteCommand("shorten")}
              className="group hover:bg-oats flex min-h-12 cursor-pointer items-center justify-between rounded-xl p-3 text-left transition-colors"
            >
              <span>
                <span className="text-coral font-bold">/shorten</span>
                <span className="text-charcoal-light ml-2">
                  文案精简瘦身
                </span>
              </span>
              <span className="group-hover:text-coral text-[10px] font-medium text-gray-400">
                执行 Enter
              </span>
            </button>
            <button
              type="button"
              onClick={() => handleExecuteCommand("tags")}
              className="group hover:bg-oats flex min-h-12 cursor-pointer items-center justify-between rounded-xl p-3 text-left transition-colors"
            >
              <span>
                <span className="text-coral font-bold">/tags</span>
                <span className="text-charcoal-light ml-2">
                  自动匹配热门话题
                </span>
              </span>
              <span className="group-hover:text-coral text-[10px] font-medium text-gray-400">
                执行 Enter
              </span>
            </button>
          </div>
          <div className="flex justify-end border-t pt-2 text-[10px] text-gray-400">
            按 Esc 键或点击空白关闭
          </div>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
