import { cn } from "@/lib/utils";
import { useStreamContext } from "@/providers/stream-context";
import { Button } from "../ui/button";
import { LoaderCircle, Plus } from "lucide-react";
import { Label } from "../ui/label";
import { useThread } from "./ThreadContext";
import { ContentBlocksPreview } from "./ContentBlocksPreview";

export function ComposerPanel() {
  const stream = useStreamContext();
  const {
    input,
    setInput,
    contentBlocks,
    handleSubmit,
    handleFileUpload,
    dropRef,
    removeBlock,
    dragOver,
    handlePaste,
    setShowCommandPalette,
    isLoading,
  } = useThread();

  return (
    <div
      ref={dropRef}
      className={cn(
        "bg-white relative z-10 mx-auto mb-8 w-full max-w-3xl rounded-2xl shadow-md transition-all",
        dragOver
          ? "border-coral border-2 border-dotted"
          : "border border-solid border-coral-light/60 focus-within:border-coral focus-within:ring-1 focus-within:ring-coral/15"
      )}
    >
      <form
        onSubmit={handleSubmit}
        className="mx-auto grid max-w-3xl grid-rows-[1fr_auto] gap-2"
      >
        <ContentBlocksPreview
          blocks={contentBlocks}
          onRemove={removeBlock}
        />
        <textarea
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onPaste={handlePaste}
          onKeyDown={(e) => {
            if (
              e.key === "Enter" &&
              !e.shiftKey &&
              !e.metaKey &&
              !e.nativeEvent.isComposing
            ) {
              e.preventDefault();
              const el = e.target as HTMLElement | undefined;
              const form = el?.closest("form");
              form?.requestSubmit();
            }
          }}
          placeholder="说说你想写什么方向，或按 Ctrl+P 调起润色工具箱..."
          className="field-sizing-content resize-none border-none bg-transparent p-3.5 pb-0 shadow-none ring-0 outline-none focus:ring-0 focus:outline-none text-charcoal text-sm leading-relaxed min-h-[50px] custom-scrollbar"
        />

        <div className="flex items-center gap-6 p-2 pt-2 border-t border-oats-dark/60 bg-oats-light/30 rounded-b-2xl">
          <button
            type="button"
            onClick={() => setShowCommandPalette(true)}
            className="hover:text-coral transition-colors flex items-center gap-1.5 text-xs border border-coral-light/60 px-2 py-0.5 rounded-lg bg-white shadow-xs cursor-pointer"
          >
            <kbd className="text-[8px] bg-oats-light border px-1 rounded shadow-xs font-mono">Ctrl+P</kbd>
            <span className="text-gray-500">润色工具箱</span>
          </button>

          <Label
            htmlFor="file-input"
            className="flex cursor-pointer items-center gap-2"
          >
            <Plus className="size-4.5 text-gray-500 hover:text-coral transition-colors" />
            <span className="text-xs text-gray-500 hover:text-coral transition-colors">
              图片或 PDF
            </span>
          </Label>
          <input
            id="file-input"
            type="file"
            onChange={handleFileUpload}
            multiple
            accept="image/jpeg,image/png,image/gif,image/webp,application/pdf"
            className="hidden"
          />
          {stream.isLoading ? (
            <Button
              key="stop"
              type="button"
              onClick={() => stream.stop()}
              className="ml-auto bg-coral hover:bg-coral-hover text-white text-xs px-4 py-1.5 rounded-xl shadow-xs"
            >
              <LoaderCircle className="h-3.5 w-3.5 animate-spin" />
              停止
            </Button>
          ) : (
            <Button
              type="submit"
              className="ml-auto bg-coral hover:bg-coral-hover text-white text-xs px-5 py-1.5 rounded-xl shadow-md transition-all font-semibold"
              disabled={
                isLoading ||
                (!input.trim() && contentBlocks.length === 0)
              }
            >
              生成
            </Button>
          )}
        </div>
      </form>
    </div>
  );
}
