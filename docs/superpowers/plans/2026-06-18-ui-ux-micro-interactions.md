# UI/UX Micro-interactions & Feishu Integration Polish Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Refine the UI styling and micro-interactions of the Xiaohongshu copywriting workspace on desktop web, including AuthGate radial gradients, macOS segmented tab slider, interactive phone likes/favorites, autogrowing editor height, circle progress and shake warning, and direct Bitable document links. (Excluding keyboard-driven command palette navigation as requested).

**Architecture:**
1. Implement Framer Motion animation layouts for segment tabs and active indicators.
2. Refactor state values in `<Thread />` to add interactive heart/star triggers and state persistence.
3. Upgrade SVG circular drawing component bound to textarea input length.
4. Display a clickable link pointing to the real Feishu Bitable document upon sync success.

**Tech Stack:** Next.js, Framer Motion, Tailwind CSS, Lucide icons.

---

## Proposed Changes

### Task 1: AuthGate Background & Glassmorphic Style Upgrade

**Files:**
- Modify: [web/src/components/auth-gate.tsx](file:///e:/小红书智能体/web/src/components/auth-gate.tsx)

- [ ] **Step 1: Apply radial background gradient and backdrop-blur glass styling**

Update the container div of the `AuthGate` component with a radial background gradient and add backdrop-blur glass panel styles to the front and back card divs.

Modify [web/src/components/auth-gate.tsx](file:///e:/小红书智能体/web/src/components/auth-gate.tsx):
```tsx
// Around line 74: Replace the main layout wrapper and the front/back card containers:
return (
  <div 
    className="flex h-screen w-screen items-center justify-center p-4 select-none"
    style={{
      background: "radial-gradient(circle, #FFEDF0 0%, #FAF6F0 100%)"
    }}
  >
    <div className="w-[380px] h-[400px] perspective-1000">
      <motion.div
        className="relative w-full h-full preserve-3d"
        animate={{ rotateY: isFlipped ? 180 : 0 }}
        transition={{ type: "spring", stiffness: 120, damping: 14 }}
        style={{ width: "100%", height: "100%" }}
      >
        {/* Card Front */}
        <div className="absolute inset-0 w-full h-full backface-hidden bg-white/75 backdrop-blur-md border border-white/50 rounded-2xl shadow-2xl p-8 flex flex-col justify-between">
          ...
        </div>

        {/* Card Back */}
        <div className="absolute inset-0 w-full h-full backface-hidden bg-white/75 backdrop-blur-md border border-white/50 rounded-2xl shadow-2xl p-8 flex flex-col justify-between [transform:rotateY(180deg)]">
          ...
        </div>
      </motion.div>
    </div>
  </div>
);
```

- [ ] **Step 2: Commit changes**

Run:
```bash
git add web/src/components/auth-gate.tsx
git commit -m "style: upgrade AuthGate with radial gradient background and glassmorphism styling"
```

---

### Task 2: macOS Segmented Tab Slider using Framer Motion

**Files:**
- Modify: [web/src/components/thread/index.tsx](file:///e:/小红书智能体/web/src/components/thread/index.tsx)

- [ ] **Step 1: Update tab switcher styling and add shared layoutId indicator**

Modify the Tab header buttons section in [web/src/components/thread/index.tsx](file:///e:/小红书智能体/web/src/components/thread/index.tsx) to use a Segmented Control style where a white hover card slides under the active option.

Modify [web/src/components/thread/index.tsx](file:///e:/小红书智能体/web/src/components/thread/index.tsx) around line 848:
```tsx
            {/* 右侧 Tab 页头 */}
            <div className="flex items-center justify-between border-b border-coral-light/60 bg-oats-light/20 px-4 py-2 shrink-0 select-none">
              <div className="flex bg-oats-dark/60 p-1 rounded-xl gap-1 relative border border-coral-light/40">
                <button
                  onClick={() => setRightTab("mock")}
                  className="relative px-4 py-1.5 rounded-lg text-xs font-bold transition-all cursor-pointer z-10 border-none bg-transparent outline-none"
                >
                  {rightTab === "mock" && (
                    <motion.div
                      layoutId="activeTabIndicator"
                      className="absolute inset-0 bg-white rounded-lg shadow-sm z-[-1]"
                      transition={{ type: "spring", stiffness: 380, damping: 30 }}
                    />
                  )}
                  <span className={cn("transition-colors duration-200", rightTab === "mock" ? "text-coral" : "text-gray-500 hover:text-charcoal")}>
                    📱 小红书手机预览
                  </span>
                </button>
                <button
                  onClick={() => setRightTab("feishu")}
                  className="relative px-4 py-1.5 rounded-lg text-xs font-bold transition-all cursor-pointer z-10 border-none bg-transparent outline-none"
                >
                  {rightTab === "feishu" && (
                    <motion.div
                      layoutId="activeTabIndicator"
                      className="absolute inset-0 bg-white rounded-lg shadow-sm z-[-1]"
                      transition={{ type: "spring", stiffness: 380, damping: 30 }}
                    />
                  )}
                  <span className={cn("transition-colors duration-200", rightTab === "feishu" ? "text-coral" : "text-gray-500 hover:text-charcoal")}>
                    🔗 飞书同步协作
                  </span>
                </button>
              </div>
```

- [ ] **Step 2: Commit changes**

Run:
```bash
git add web/src/components/thread/index.tsx
git commit -m "style: implement macOS segmented tab slider in workspace header using framer-motion layoutId"
```

---

### Task 3: Interactive Phone Likes and Favorites with Spring bounce

**Files:**
- Modify: [web/src/components/thread/index.tsx](file:///e:/小红书智能体/web/src/components/thread/index.tsx)

- [ ] **Step 1: Declare state variables for Likes and Favorites**

Add state variables inside the `Thread` component function body.

Modify [web/src/components/thread/index.tsx](file:///e:/小红书智能体/web/src/components/thread/index.tsx):
```tsx
// Around line 125: Add state variables
  const [likeCount, setLikeCount] = useState(1280);
  const [isLiked, setIsLiked] = useState(false);
  const [collectCount, setCollectCount] = useState(342);
  const [isCollected, setIsCollected] = useState(false);
  const [showPlusOne, setShowPlusOne] = useState(false);
```

- [ ] **Step 2: Refactor phone simulator bottom interaction bar**

Update the simulator interaction bar to bind these states and trigger click animations.

Modify [web/src/components/thread/index.tsx](file:///e:/小红书智能体/web/src/components/thread/index.tsx) around line 1060:
```tsx
                    {/* 模拟器底部互动栏 */}
                    <div className="h-10 border-t border-gray-100 flex items-center justify-between px-6 bg-white shrink-0 text-gray-400 select-none relative">
                      
                      {/* Plus One floating animation */}
                      <AnimatePresence>
                        {showPlusOne && (
                          <motion.span
                            initial={{ opacity: 0, y: 0 }}
                            animate={{ opacity: 1, y: -25 }}
                            exit={{ opacity: 0 }}
                            className="absolute left-6 text-[10px] font-bold text-coral"
                          >
                            +1
                          </motion.span>
                        )}
                      </AnimatePresence>

                      <button 
                        onClick={() => {
                          if (!isLiked) {
                            setShowPlusOne(true);
                            setTimeout(() => setShowPlusOne(false), 800);
                          }
                          setIsLiked(!isLiked);
                          setLikeCount((c) => isLiked ? c - 1 : c + 1);
                        }}
                        className="flex items-center gap-1 cursor-pointer hover:text-coral transition-colors outline-none border-none bg-transparent"
                      >
                        <motion.div
                          animate={{ scale: isLiked ? [1, 1.45, 0.9, 1.1, 1] : 1 }}
                          transition={{ duration: 0.4 }}
                        >
                          <Heart className={cn("size-3.5 transition-colors", isLiked ? "text-coral fill-coral" : "text-gray-400")} />
                        </motion.div>
                        <span className={cn("text-[8px] font-medium", isLiked ? "text-coral" : "text-gray-400")}>
                          {likeCount >= 1000 ? `${(likeCount / 1000).toFixed(1)}k` : likeCount}
                        </span>
                      </button>

                      <button
                        onClick={() => {
                          setIsCollected(!isCollected);
                          setCollectCount((c) => isCollected ? c - 1 : c + 1);
                        }}
                        className="flex items-center gap-1 cursor-pointer hover:text-coral transition-colors outline-none border-none bg-transparent"
                      >
                        <motion.div
                          animate={{ scale: isCollected ? [1, 1.45, 0.9, 1.1, 1] : 1 }}
                          transition={{ duration: 0.4 }}
                        >
                          <Star className={cn("size-3.5 transition-colors", isCollected ? "text-coral fill-coral" : "text-gray-400")} />
                        </motion.div>
                        <span className={cn("text-[8px] font-medium", isCollected ? "text-coral" : "text-gray-400")}>
                          {collectCount}
                        </span>
                      </button>

                      <div className="flex items-center gap-1 cursor-pointer text-gray-400">
                        <MessageSquare className="size-3.5" />
                        <span className="text-[8px] font-medium">88</span>
                      </div>
                    </div>
```

- [ ] **Step 3: Commit changes**

Run:
```bash
git add web/src/components/thread/index.tsx
git commit -m "feat: make phone simulator interaction bar fully interactive with spring bounce animations"
```

---

### Task 4: Circular Character Progress Ring and Shake Warning in Text Editor

**Files:**
- Modify: [web/src/components/thread/index.tsx](file:///e:/小红书智能体/web/src/components/thread/index.tsx)
- Modify: [web/src/app/globals.css](file:///e:/小红书智能体/web/src/app/globals.css)

- [ ] **Step 1: Replace character count badge with circular progress ring and shake keyframe animation**

Add a custom keyframes shake definition in globals.css, then implement the SVG progress wheel in the editor state header of the simulator.

Modify [web/src/components/thread/index.tsx](file:///e:/小红书智能体/web/src/components/thread/index.tsx) around line 981:
```tsx
                          <div className="flex justify-between items-center text-[10px] select-none">
                            <span className="font-bold text-gray-500">✏️ 原位修改文案</span>
                            <div className="flex items-center gap-1.5">
                              {/* SVG Circle progress */}
                              <svg className="size-4 -rotate-90">
                                <circle 
                                  cx="8" cy="8" r="6" 
                                  className="stroke-gray-100 fill-none" 
                                  strokeWidth="1.5"
                                />
                                <circle 
                                  cx="8" cy="8" r="6" 
                                  className="fill-none transition-all duration-300" 
                                  strokeWidth="1.5"
                                  stroke={draftContent.length > 1000 ? "#ff2442" : (draftContent.length > 800 ? "#f97316" : "#22c55e")}
                                  strokeDasharray={2 * Math.PI * 6}
                                  strokeDashoffset={2 * Math.PI * 6 * (1 - Math.min(draftContent.length, 1000) / 1000)}
                                />
                              </svg>
                              <span
                                className={cn(
                                  "text-[9px] border px-2 py-0.5 rounded transition-all",
                                  draftContent.length > 1000
                                    ? "bg-red-50 text-red-700 border-red-200 animate-[shake_0.5s_ease-in-out_infinite]"
                                    : "bg-green-50 text-green-700 border-green-200"
                                )}
                              >
                                字数：{draftContent.length} / 1000 字 {draftContent.length > 1000 && "⚠️"}
                              </span>
                            </div>
                          </div>
```

- [ ] **Step 2: Add shake animation definition in globals.css**

Modify [web/src/app/globals.css](file:///e:/小红书智能体/web/src/app/globals.css) to append the shake keyframes:
```css
@keyframes shake {
  0%, 100% { transform: translateX(0); }
  25% { transform: translateX(-4px); }
  75% { transform: translateX(4px); }
}
```

- [ ] **Step 3: Commit changes**

Run:
```bash
git add web/src/app/globals.css web/src/components/thread/index.tsx
git commit -m "feat: add circular SVG progress ring and shake warning animation for word count limit"
```

---

### Task 5: Feishu Bitable Document Link & Log Stream

**Files:**
- Modify: [web/src/components/thread/index.tsx](file:///e:/小红书智能体/web/src/components/thread/index.tsx)

- [ ] **Step 1: Check environment vars and add Lark Bitable direct link**

Add the app token redirect link underneath the success button in the Feishu Tab when `syncStep === 4`.

Modify [web/src/components/thread/index.tsx](file:///e:/小红书智能体/web/src/components/thread/index.tsx) around line 1180:
```tsx
                  <div className="pt-1 flex flex-col gap-2">
                    <button
                      onClick={handleSyncToFeishu}
                      disabled={isSyncing}
                      className={cn(
                        "w-full text-white text-xs py-2 px-3 rounded-xl flex items-center justify-center gap-2 font-medium shadow-md transition-all cursor-pointer border-none outline-none",
                        syncStep === 4 ? "bg-green-500 hover:bg-green-600" : "bg-coral hover:bg-coral-hover"
                      )}
                    >
                      <CloudUpload className="size-4" />
                      <span>{syncStep === 4 ? "多维表格写入成功！" : "立即同步至飞书多维表格"}</span>
                    </button>

                    {syncStep === 4 && (
                      <motion.a
                        initial={{ opacity: 0, y: 5 }}
                        animate={{ opacity: 1, y: 0 }}
                        href="https://feishu.cn/base/"
                        target="_blank"
                        rel="noreferrer"
                        className="w-full bg-green-50 hover:bg-green-100 text-green-700 border border-green-200 text-center text-xs py-1.5 rounded-lg font-bold transition-all shadow-xs block"
                      >
                        🔗 立即打开飞书多维表格文档
                      </motion.a>
                    )}
                  </div>
```

- [ ] **Step 2: Commit changes**

Run:
```bash
git add web/src/components/thread/index.tsx
git commit -m "feat: add direct clickable link to open Feishu Bitable document upon successful sync"
```

---

## Verification Plan

### Automated Build Verification
Verify everything builds and compiles correctly with TypeScript:
- Run: `cd web && npm run build`
Expected: Build succeeds with 0 errors.

### Manual Verification
1. Run `python tools/deploy.py` to upload and redeploy.
2. Load page in browser.
3. Check AuthGate backdrop-blur.
4. Verify Segmented control Tab header sliding.
5. Click Hearts icon on details preview and check scale transition and +1 text.
6. Run Bitable Sync to check the direct link redirect.
