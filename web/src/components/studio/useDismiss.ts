"use client";

// useDismiss — 让弹层/抽屉关闭时先播退出动画再真正卸载(对称进出场),而非硬切。
// 尊重 prefers-reduced-motion:用户关动效时立即关闭,不等动画。
// 用法:const { closing, dismiss } = useDismiss(onClose); 把 closing 映射到 .scrim-out/
// .slide-out-right 等退出类,所有关闭入口(遮罩点击/关闭按钮/Esc)都调 dismiss()。

import { useCallback, useRef, useState } from "react";

const EXIT_MS = 220;

export function useDismiss(onClose: () => void, exitMs: number = EXIT_MS) {
  const [closing, setClosing] = useState(false);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const dismiss = useCallback(() => {
    if (closing) return;
    const reduce =
      typeof window !== "undefined" &&
      typeof window.matchMedia === "function" &&
      window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    if (reduce) {
      onClose();
      return;
    }
    setClosing(true);
    timer.current = setTimeout(() => {
      onClose();
    }, exitMs);
  }, [closing, onClose, exitMs]);

  return { closing, dismiss };
}
