import { type Dispatch, type SetStateAction, useState } from "react";

export type PreviewMode = "detail" | "feed";

export interface PreviewSnapshot {
  viewMode: PreviewMode;
  isEditingText: boolean;
  carouselIndex: number;
  carouselImages: string[];
}

export interface PreviewState extends PreviewSnapshot {
  setViewMode: Dispatch<SetStateAction<PreviewMode>>;
  setIsEditingText: Dispatch<SetStateAction<boolean>>;
  setCarouselIndex: Dispatch<SetStateAction<number>>;
}

export function createPreviewInitialState(): PreviewSnapshot {
  return {
    viewMode: "detail",
    isEditingText: false,
    carouselIndex: 0,
    carouselImages: [
      "https://images.unsplash.com/photo-1504280390367-361c6d9f38f4?auto=format&fit=crop&w=500&q=80",
      "https://images.unsplash.com/photo-1533873984035-25970ab07461?auto=format&fit=crop&w=500&q=80",
      "https://images.unsplash.com/photo-1478131143081-80f7f84ca84d?auto=format&fit=crop&w=500&q=80",
    ],
  };
}

export function usePreviewState(): PreviewState {
  const initial = createPreviewInitialState();
  const [viewMode, setViewMode] = useState<PreviewMode>(initial.viewMode);
  const [isEditingText, setIsEditingText] = useState(initial.isEditingText);
  const [carouselIndex, setCarouselIndex] = useState(initial.carouselIndex);

  return {
    viewMode,
    setViewMode,
    isEditingText,
    setIsEditingText,
    carouselIndex,
    setCarouselIndex,
    carouselImages: initial.carouselImages,
  };
}
