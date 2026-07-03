"use client";

import {
  AlertCircle,
  AlertTriangle,
  ArrowLeft,
  ArrowRight,
  Bot,
  CalendarCheck,
  CalendarDays,
  Check,
  CheckCircle2,
  ChevronLeft,
  ChevronRight,
  Circle,
  ClipboardPen,
  Clock,
  CloudUpload,
  Copy,
  CopyPlus,
  Database,
  Download,
  Feather,
  FileText,
  Flame,
  Gauge,
  GitBranch,
  Hash,
  Heart,
  History,
  ImagePlus,
  Images,
  KeyRound,
  LayoutGrid,
  LayoutTemplate,
  LibraryBig,
  Lightbulb,
  LineChart,
  Link,
  List,
  LogOut,
  MessageSquare,
  Pencil,
  PenLine,
  Plus,
  Radar,
  RefreshCw,
  Repeat,
  ScanSearch,
  Scissors,
  Search,
  Send,
  Settings,
  Settings2,
  PanelLeftClose,
  PanelLeftOpen,
  Share,
  ShieldCheck,
  Sparkles,
  SquarePen,
  Star,
  Stethoscope,
  Users,
  UserPlus,
  Wand2,
  X,
  type LucideIcon,
} from "lucide-react";
import type { CSSProperties } from "react";

/**
 * Icon — the design-system icon. The prototype rendered Lucide
 * glyphs as a CSS mask off the lucide-static CDN; production uses
 * the same glyphs via lucide-react (visually identical, no CDN).
 *
 * Curated static map (tree-shakeable) of every icon the kits use.
 * Unknown names render an empty inline box (and warn in dev) so a
 * future name gap degrades gracefully instead of crashing.
 */
const REGISTRY: Record<string, LucideIcon> = {
  "alert-circle": AlertCircle,
  "alert-triangle": AlertTriangle,
  "arrow-left": ArrowLeft,
  "arrow-right": ArrowRight,
  bot: Bot,
  "calendar-check": CalendarCheck,
  "calendar-days": CalendarDays,
  check: Check,
  "check-circle-2": CheckCircle2,
  "chevron-left": ChevronLeft,
  "chevron-right": ChevronRight,
  circle: Circle,
  "clipboard-pen": ClipboardPen,
  clock: Clock,
  "cloud-upload": CloudUpload,
  copy: Copy,
  "copy-plus": CopyPlus,
  database: Database,
  download: Download,
  feather: Feather,
  "file-text": FileText,
  flame: Flame,
  gauge: Gauge,
  "git-branch": GitBranch,
  hash: Hash,
  heart: Heart,
  history: History,
  "image-plus": ImagePlus,
  images: Images,
  "key-round": KeyRound,
  "layout-grid": LayoutGrid,
  "layout-template": LayoutTemplate,
  "library-big": LibraryBig,
  lightbulb: Lightbulb,
  "line-chart": LineChart,
  link: Link,
  list: List,
  "log-out": LogOut,
  "message-square": MessageSquare,
  pencil: Pencil,
  "pen-line": PenLine,
  plus: Plus,
  radar: Radar,
  "refresh-cw": RefreshCw,
  repeat: Repeat,
  "scan-search": ScanSearch,
  scissors: Scissors,
  search: Search,
  send: Send,
  settings: Settings,
  "settings-2": Settings2,
  "panel-left-close": PanelLeftClose,
  "panel-left-open": PanelLeftOpen,
  share: Share,
  "shield-check": ShieldCheck,
  sparkles: Sparkles,
  "square-pen": SquarePen,
  star: Star,
  stethoscope: Stethoscope,
  users: Users,
  "user-plus": UserPlus,
  "wand-2": Wand2,
  x: X,
};

export interface IconProps {
  name: string;
  size?: number;
  color?: string;
  strokeWidth?: number;
  style?: CSSProperties;
  className?: string;
}

export function Icon({ name, size = 16, color, strokeWidth = 2, style, className }: IconProps) {
  const Glyph = REGISTRY[name];
  if (!Glyph) {
    if (process.env.NODE_ENV !== "production") {
      console.warn(`[ds/Icon] unmapped icon "${name}" — add it to REGISTRY in ds/Icon.tsx`);
    }
    return <span aria-hidden style={{ display: "inline-block", width: size, height: size, flexShrink: 0, ...style }} className={className} />;
  }
  return <Glyph aria-hidden size={size} color={color} strokeWidth={strokeWidth} style={{ flexShrink: 0, ...style }} className={className} />;
}
