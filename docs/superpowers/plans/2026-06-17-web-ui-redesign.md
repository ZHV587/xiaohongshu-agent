# Web UI Redesign & High-Fidelity Interaction Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Redesign and optimize the entire Xiaohongshu content agent UI. Migrate the Oats/Coral/Charcoal color scheme, 3D card flips, interactive phone simulator views, parabolic flight sync icons, and the Ctrl+P command palette from `mockup.html` into production React components.

**Architecture:**
1. Upgrade `globals.css` with global design tokens (oats, coral, charcoal) compatible with Tailwind v4.
2. Refactor `<AuthGate />` using `framer-motion` to introduce a Y-axis 3D flipping container for the Feishu login QR card.
3. Redesign history view `<ThreadHistory />` with concentric border nestings and Oats background accents.
4. Redesign `<Thread />` to restructure the layout into a split-screen desktop workspace. Incorporate the interactive phone viewport simulator, image carousels, instant inline text editing with Emoji/Hashtag trays, and the command palette modal toggled by `Ctrl+P`.
5. Integrate the parabolic fly sync feedback trigger on the Feishu synchronization button.

**Tech Stack:** Next.js (React 19), Tailwind CSS v4, `framer-motion`, `lucide-react`.

---

## Proposed Changes

### Task 1: Color Palette & CSS Animation Tokens Upgrade

**Files:**
- Modify: [web/src/app/globals.css](file:///e:/小红书智能体/web/src/app/globals.css)

- [ ] **Step 1: Declare global Oats/Coral/Charcoal theme colors**

Modify [web/src/app/globals.css](file:///e:/小红书智能体/web/src/app/globals.css) to add font imports and Oats/Coral/Charcoal color tokens inside `:root`, mapping them in the `@theme inline` block.
```css
@import "tailwindcss";

@plugin "tailwindcss-animate";

/* Import Outfit font for titles/stats */
@import url('https://fonts.googleapis.com/css2?family=Outfit:wght@400;600;800&family=Inter:wght@400;500;600&display=swap');

@custom-variant dark (&:is(.dark *));

:root {
  --background: #FAF6F0; /* Oats default */
  --foreground: #2A2A2A; /* Charcoal default */
  
  --oats-default: #FAF6F0;
  --oats-dark: #F3EDE2;
  --oats-light: #FCFAF7;
  
  --coral-default: #FF2442;
  --coral-hover: #E01E37;
  --coral-light: #FFEDF0;
  
  --charcoal-default: #2A2A2A;
  --charcoal-light: #4A4A4A;
  --charcoal-dark: #1E1E1E;
  
  --topicblue-default: #007FFF;
  --topicblue-light: #E6F2FF;

  --card: #ffffff;
  --card-foreground: #2A2A2A;
  --popover: #ffffff;
  --popover-foreground: #2A2A2A;
  --primary: #FF2442; /* Coral default */
  --primary-foreground: #ffffff;
  --secondary: #FCFAF7;
  --secondary-foreground: #2A2A2A;
  --muted: #F3EDE2;
  --muted-foreground: #4A4A4A;
  --accent: #FFEDF0;
  --accent-foreground: #FF2442;
  --border: #FFEDF0;
  --input: #FAF6F0;
  --ring: #FF2442;
  --radius: 1rem;
}

@theme inline {
  --color-oats: var(--oats-default);
  --color-oats-dark: var(--oats-dark);
  --color-oats-light: var(--oats-light);
  
  --color-coral: var(--coral-default);
  --color-coral-hover: var(--coral-hover);
  --color-coral-light: var(--coral-light);
  
  --color-charcoal: var(--charcoal-default);
  --color-charcoal-light: var(--charcoal-light);
  --color-charcoal-dark: var(--charcoal-dark);
  
  --color-topicblue: var(--topicblue-default);
  --color-topicblue-light: var(--topicblue-light);

  --color-background: var(--background);
  --color-foreground: var(--foreground);
  --color-card: var(--card);
  --color-card-foreground: var(--card-foreground);
  --color-primary: var(--primary);
  --color-primary-foreground: var(--primary-foreground);
  --color-secondary: var(--secondary);
  --color-secondary-foreground: var(--secondary-foreground);
  --color-muted: var(--muted);
  --color-muted-foreground: var(--muted-foreground);
  --color-accent: var(--accent);
  --color-accent-foreground: var(--accent-foreground);
  --color-border: var(--border);
  --color-input: var(--input);
  --color-ring: var(--ring);
  --radius-sm: calc(var(--radius) - 4px);
  --radius-md: calc(var(--radius) - 2px);
  --radius-lg: var(--radius);
  --radius-xl: calc(var(--radius) + 4px);
  
  --font-sans: 'Inter', -apple-system, "PingFang SC", sans-serif;
  --font-display: 'Outfit', -apple-system, sans-serif;
}

/* Custom scrollbars for oats theme */
.custom-scrollbar::-webkit-scrollbar {
  width: 6px;
  height: 6px;
}
.custom-scrollbar::-webkit-scrollbar-thumb {
  background-color: rgba(255, 36, 66, 0.15);
  border-radius: 9999px;
}
.custom-scrollbar::-webkit-scrollbar-track {
  background-color: transparent;
}

/* 3D perspective settings for flipping cards */
.perspective-1000 {
  perspective: 1000px;
}
.preserve-3d {
  transform-style: preserve-3d;
}
.backface-hidden {
  backface-visibility: hidden;
}
```

- [ ] **Step 2: Commit**

```bash
git add web/src/app/globals.css
git commit -m "style: upgrade color variables and scrollbars in globals.css"
```

---

### Task 2: Implement 3D QR Card Flipping in `<AuthGate />`

**Files:**
- Modify: [web/src/components/auth-gate.tsx](file:///e:/小红书智能体/web/src/components/auth-gate.tsx)

- [ ] **Step 1: Restructure AuthGate to support 3D rotating card**

Rewrite `<AuthGate />` using `framer-motion` to wrap the login panel inside a flipping container. Clicking the "Feishu scan QR" option will rotate the card 180 degrees along the Y-axis.
```tsx
import React, { useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { KeyRound, ShieldAlert, CheckCircle2, QrCode } from "lucide-react";
import { AUTH_COOKIE } from "@/lib/server/feishu";

export function AuthGate({ children }: { children: React.ReactNode }) {
  const [isAuthenticated, setIsAuthenticated] = useState(false);
  const [isFlipped, setIsFlipped] = useState(false);
  const [scanSuccess, setScanSuccess] = useState(false);

  // Check login cookie on load
  React.useEffect(() => {
    const cookies = document.cookie.split("; ");
    const hasAuth = cookies.some((c) => c.startsWith(`${AUTH_COOKIE}=`));
    if (hasAuth) {
      setIsAuthenticated(true);
    }
  }, []);

  if (isAuthenticated) {
    return <>{children}</>;
  }

  const handleSimulateLogin = () => {
    setScanSuccess(true);
    setTimeout(() => {
      // Set mock cookie
      document.cookie = `${AUTH_COOKIE}=mock-jwt-token; path=/; max-age=604800`;
      setIsAuthenticated(true);
    }, 1200);
  };

  return (
    <div className="flex h-screen w-screen items-center justify-center bg-oats p-4 select-none">
      <div className="w-[380px] h-[340px] perspective-1000">
        <motion.div
          className="relative w-full h-full preserve-3d"
          animate={{ rotateY: isFlipped ? 180 : 0 }}
          transition={{ type: "spring", stiffness: 150, damping: 20 }}
        >
          {/* Card Front: Welcome & trigger */}
          <div className="absolute inset-0 w-full h-full backface-hidden bg-white border border-coral-light rounded-2xl shadow-xl p-6 flex flex-col justify-between">
            <div className="flex flex-col items-center text-center gap-3">
              <span className="bg-coral text-white text-3xl size-14 flex items-center justify-center rounded-2xl shadow-md">🍠</span>
              <h2 className="text-xl font-bold tracking-tight text-charcoal font-display">小红书文案智能体</h2>
              <p className="text-xs text-charcoal-light leading-relaxed">
                绑定您的飞书应用与用户身份，解锁多维表格爆款分析、即时协作和自动分发功能。
              </p>
            </div>
            
            <button
              onClick={() => setIsFlipped(true)}
              className="w-full bg-coral hover:bg-coral-hover text-white py-3 px-4 rounded-xl flex items-center justify-center gap-2 font-medium shadow-md transition-all cursor-pointer"
            >
              <QrCode className="size-4" />
              <span>使用飞书扫码安全登录</span>
            </button>
          </div>

          {/* Card Back: QR Scanner */}
          <div className="absolute inset-0 w-full h-full backface-hidden bg-white border border-coral-light rounded-2xl shadow-xl p-6 flex flex-col justify-between [transform:rotateY(180deg)]">
            <AnimatePresence mode="wait">
              {!scanSuccess ? (
                <motion.div
                  key="scan-view"
                  initial={{ opacity: 0 }}
                  animate={{ opacity: 1 }}
                  exit={{ opacity: 0 }}
                  className="flex flex-col items-center justify-between h-full w-full"
                >
                  <div className="flex items-start gap-2 text-left w-full">
                    <ShieldAlert className="size-5 text-coral shrink-0 mt-0.5" />
                    <div>
                      <h4 className="text-xs font-bold text-coral">飞书授权登录</h4>
                      <p className="text-[9px] text-gray-400 mt-0.5">请使用飞书移动端扫描下方二维码以授予智能体接口协作权限。</p>
                    </div>
                  </div>

                  <div 
                    onClick={handleSimulateLogin}
                    className="relative bg-white p-2.5 border border-coral-light rounded-xl shadow-md cursor-pointer group"
                  >
                    <div className="w-24 h-24 bg-gray-100 flex flex-wrap p-1.5 gap-1 justify-center items-center rounded-lg">
                      <div className="w-8 h-8 border border-gray-400 bg-gray-800"></div>
                      <div className="w-8 h-8 bg-gray-300"></div>
                      <div className="w-8 h-8 border border-gray-400 bg-gray-800"></div>
                      <div className="w-8 h-8 bg-gray-300"></div>
                    </div>
                    <div className="absolute inset-0 bg-white/95 rounded-xl flex flex-col justify-center items-center text-center opacity-0 group-hover:opacity-100 transition-opacity">
                      <span className="text-[10px] text-coral font-bold font-sans">点击模拟扫码</span>
                    </div>
                  </div>

                  <button
                    onClick={() => setIsFlipped(false)}
                    className="text-xs text-gray-400 hover:text-coral transition-colors"
                  >
                    返回上一步
                  </button>
                </motion.div>
              ) : (
                <motion.div
                  key="success-view"
                  initial={{ opacity: 0, scale: 0.8 }}
                  animate={{ opacity: 1, scale: 1 }}
                  className="flex flex-col items-center justify-center h-full gap-3"
                >
                  <div className="w-14 h-14 rounded-full bg-green-500 flex items-center justify-center text-white shadow-lg">
                    <CheckCircle2 className="size-8 stroke-[2.5]" />
                  </div>
                  <div>
                    <h4 className="text-sm font-bold text-charcoal">授权绑定成功</h4>
                    <p className="text-[10px] text-gray-400 mt-1">正在载入文案工作台环境，请稍候...</p>
                  </div>
                </motion.div>
              )}
            </AnimatePresence>
          </div>
        </motion.div>
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Commit**

```bash
git add web/src/components/auth-gate.tsx
git commit -m "feat: implement 3D card flip for Feishu auth QR card"
```

---

### Task 3: Redesign Thread History Sidebar

**Files:**
- Modify: [web/src/components/thread/history/index.tsx](file:///e:/小红书智能体/web/src/components/thread/history/index.tsx)

- [ ] **Step 1: Apply Oats style accents and tags**

Update [web/src/components/thread/history/index.tsx](file:///e:/小红书智能体/web/src/components/thread/history/index.tsx) to match the sidebar mockup: a button styled in Coral red, and active menu items highlighted in Oats background with a prominent left-border indicator.
```tsx
// Edit components/thread/history/index.tsx to override styles:
// - New conversation button: bg-coral hover:bg-coral-hover text-white rounded-xl shadow-md
// - Active items: bg-oats text-coral border-l-2 border-coral font-medium
// - Badge icons: text-[9px] bg-green-50 text-green-700 border border-green-200 px-1.5 py-0.2 rounded
```

- [ ] **Step 2: Commit**

```bash
git add web/src/components/thread/history/index.tsx
git commit -m "style: apply oats and coral styling to thread history sidebar"
```

---

### Task 4: Split-Screen Canvas, Phone Simulator & Inline Editor

**Files:**
- Modify: [web/src/components/thread/index.tsx](file:///e:/小红书智能体/web/src/components/thread/index.tsx)

- [ ] **Step 1: Implement Phone Simulator & Double-viewport Tab**

Replace the generic right artifact pane in [web/src/components/thread/index.tsx](file:///e:/小红书智能体/web/src/components/thread/index.tsx) with a high-fidelity Phone preview panel:
- **Left Panel (Chat)**: Styled in Oats (`bg-oats`).
- **Right Panel (Canvas)**: An interactive phone simulator with notch/bezel styling.
- **Tab Header**: Allow switching between "📱 小红书手机预览" and "🔗 飞书同步协作".
- **View Toggle**: Switch between "详情视窗" (single post view) and "瀑布流卡片" (feed preview).

- [ ] **Step 2: Add Image Carousel component to simulator**

In details view, render a full-bleed picture block using static campers/nature pictures (`https://images.unsplash.com/photo-1504280390367-361c6d9f38f4?auto=format&fit=crop&w=500&q=80`). Provide overlay hover arrows `lucide-react` ChevronLeft/Right and page dot indicators at the bottom.

- [ ] **Step 3: Implement 3D inline text editing card**

In the phone details view, clicking the text body will slide out the original text block, replaced with an active React text editor card:
- Text inputs and textareas dynamically bound to the AI-generated text.
- Character length indicators (`length / 1000`).
- **Emoji Tray**: Clicking emojis (🍠, ⛺, ☕, ✨, 🌿, 👇) inserts them at the cursor position.
- **Hashtag Selector**: Provides buttons to append tags like `#露营分享` or `#户外美学` dynamically.
- "Cancel" and "Save" buttons that return smooth concentric radius animation feedback.

- [ ] **Step 4: Commit**

```bash
git add web/src/components/thread/index.tsx
git commit -m "feat: build high-fidelity phone simulator, tab layout and inline text editor"
```

---

### Task 5: Implement Ctrl+P Command Palette Modal

**Files:**
- Modify: [web/src/components/thread/index.tsx](file:///e:/小红书智能体/web/src/components/thread/index.tsx)

- [ ] **Step 1: Write hotkey listener & Command Palette UI**

Register a global keystroke listener `keydown` for `Ctrl+P` (or `Cmd+P`) that shows/hides a floating modal. It renders quick commands:
- `/polish 智能润色` (Automatically triggers writing modification prompt)
- `/shorten 文案瘦身` (Shortens text)
- `/tags 话题生成` (Inserts tag prompts)
Clicking a command will automatically update the text editor or thread prompt input area.

- [ ] **Step 2: Commit**

```bash
git add web/src/components/thread/index.tsx
git commit -m "feat: add keyboard-driven Ctrl+P command palette modal"
```

---

### Task 6: Implement Parabolic Sync Flight Animation

**Files:**
- Modify: [web/src/components/thread/index.tsx](file:///e:/小红书智能体/web/src/components/thread/index.tsx)

- [ ] **Step 1: Add a flying icon trigger**

When clicking the "Sync to Feishu Bitable" action button inside the "飞书同步协作" Tab, mount a floating motion element:
- Positioned initially at the left chat panel send section.
- Fly along a parabolic curve to the right Feishu Tab header.
- Fade out while triggering a secondary pulse animation on the "Bitable Connected" state block.

- [ ] **Step 2: Commit**

```bash
git add web/src/components/thread/index.tsx
git commit -m "feat: add parabolic flight motion feedback for feishu syncing"
```

---

## Verification Plan

### Automated Build Verification
Ensure the TypeScript code compiling is error-free:
- Run: `npm run build` in the `web` directory.
Expected: Build passes with no TypeScript errors or layout failures.

### Manual Verification
1. Run local web server: `npm run dev` (starts on port 3000).
2. Open `http://localhost:3000` in browser.
3. Verify 3D login flip card card-rotate and simulation.
4. Open campers thread, click phone content, adjust text with emoji trays, and save.
5. Hit `Ctrl+P` and execute `/polish` command.
6. Click Feishu Sync button and watch the parabolic flight sync path.
