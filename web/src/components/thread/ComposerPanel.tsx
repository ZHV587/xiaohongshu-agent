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
        "relative z-10 mx-auto mb-8 w-full max-w-3xl rounded-2xl bg-white shadow-md transition-all",
        dragOver
          ? "border-coral border-2 border-dotted"
          : "border-coral-light/60 focus-within:border-coral focus-within:ring-coral/15 border border-solid focus-within:ring-1",
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
          className="text-charcoal custom-scrollbar field-sizing-content min-h-[50px] resize-none border-none bg-transparent p-3.5 pb-0 text-sm leading-relaxed shadow-none ring-0 outline-none focus:ring-0 focus:outline-none"
        />

        <div className="border-oats-dark/60 bg-oats-light/30 flex items-center gap-6 rounded-b-2xl border-t p-2 pt-2">
          <button
            type="button"
            onClick={() => setShowCommandPalette(true)}
            className="border-coral-light/60 hover:text-coral flex min-h-11 cursor-pointer items-center gap-1.5 rounded-lg border bg-white px-3 py-2 text-xs shadow-xs transition-colors"
          >
            <kbd className="bg-oats-light rounded border px-1 font-mono text-[8px] shadow-xs">
              Ctrl+P
            </kbd>
            <span className="text-gray-500">润色工具箱</span>
          </button>

          <Label
            htmlFor="file-input"
            className="flex min-h-11 cursor-pointer items-center gap-2 px-2"
          >
            <Plus className="hover:text-coral size-4.5 text-gray-500 transition-colors" />
            <span className="hover:text-coral text-xs text-gray-500 transition-colors">
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
              className="bg-coral hover:bg-coral-hover ml-auto min-h-11 rounded-xl px-4 py-2 text-xs text-white shadow-xs"
            >
              <LoaderCircle className="h-3.5 w-3.5 animate-spin" />
              停止
            </Button>
          ) : (
            <Button
              type="submit"
              className="bg-coral hover:bg-coral-hover ml-auto min-h-11 rounded-xl px-5 py-2 text-xs font-semibold text-white shadow-md transition-all"
              disabled={
                isLoading || (!input.trim() && contentBlocks.length === 0)
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
