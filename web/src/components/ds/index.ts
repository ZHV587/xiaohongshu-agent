// 小红书文案助手 Design System — production component barrel.
// Faithful 1:1 TSX ports of 小红书文案助手 Design System/components/* (inline-style,
// token-driven). Replaces the prototype's `window.DesignSystem_71831b`
// global namespace — kit screens import from "@/components/ds".

export { Button, type ButtonProps } from "./core/Button";
export { IconButton, type IconButtonProps } from "./core/IconButton";
export { Badge, type BadgeProps } from "./core/Badge";
export { Avatar, type AvatarProps } from "./core/Avatar";
export { Card, type CardProps } from "./core/Card";

export { Input, type InputProps } from "./forms/Input";
export { Select, type SelectProps } from "./forms/Select";
export { Textarea, type TextareaProps } from "./forms/Textarea";

export { HashtagTag, type HashtagTagProps } from "./content/HashtagTag";
export { TopicCard, type TopicCardProps } from "./content/TopicCard";
export {
  ThinkingAura,
  type ThinkingAuraProps,
  type ThinkingStep,
  type ThinkingLog,
} from "./content/ThinkingAura";

export { PhoneFrame, type PhoneFrameProps } from "./device/PhoneFrame";
export { NoteCard, type NoteCardProps } from "./device/NoteCard";

export { StatCard, type StatCardProps } from "./data/StatCard";

export { Icon, type IconProps } from "./Icon";
