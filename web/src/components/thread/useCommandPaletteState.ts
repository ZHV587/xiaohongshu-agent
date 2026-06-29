import { type Dispatch, type SetStateAction, useEffect, useState } from "react";

export type CommandPaletteKeyboardAction = "toggle" | "close";

interface KeyboardLike {
  ctrlKey: boolean;
  metaKey: boolean;
  key: string;
}

export function getCommandPaletteKeyboardAction(
  event: KeyboardLike,
): CommandPaletteKeyboardAction | null {
  if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "p") {
    return "toggle";
  }
  if (event.key === "Escape") return "close";
  return null;
}

export interface CommandPaletteState {
  showCommandPalette: boolean;
  setShowCommandPalette: Dispatch<SetStateAction<boolean>>;
  cmdSearch: string;
  setCmdSearch: Dispatch<SetStateAction<string>>;
}

export function useCommandPaletteState(): CommandPaletteState {
  const [showCommandPalette, setShowCommandPalette] = useState(false);
  const [cmdSearch, setCmdSearch] = useState("");

  useEffect(() => {
    const handleKeyDown = (event: KeyboardEvent) => {
      const action = getCommandPaletteKeyboardAction(event);
      if (action === "toggle") {
        event.preventDefault();
        setShowCommandPalette((prev) => !prev);
      } else if (action === "close") {
        setShowCommandPalette(false);
      }
    };

    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, []);

  return {
    showCommandPalette,
    setShowCommandPalette,
    cmdSearch,
    setCmdSearch,
  };
}
