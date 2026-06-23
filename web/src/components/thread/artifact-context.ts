import { createContext } from "react";

export type ArtifactSetter<T> = (value: T | ((value: T) => T)) => void;

export const ArtifactSlotContext = createContext<{
  open: [string | null, ArtifactSetter<string | null>];
  mounted: [string | null, ArtifactSetter<string | null>];

  title: [HTMLElement | null, ArtifactSetter<HTMLElement | null>];
  content: [HTMLElement | null, ArtifactSetter<HTMLElement | null>];

  context: [Record<string, unknown>, ArtifactSetter<Record<string, unknown>>];
}>(null!);
