# 小红书文案助手 — Design System

A design system for **小红书文案助手** (*Xiaohongshu Copywriting
Assistant*) — an AI **content-creation agent workbench**. Operators
point it at viral-note data in a **Feishu (飞书) Bitable**, the agent
analyzes what makes posts perform, proposes scored topic ideas, writes
小红书-native copy, previews it in a phone mock, and syncs the result
back to Feishu for the team.

> 小红书 ("Little Red Book" / RED) is China's dominant lifestyle
> discovery platform. Its community nickname is 小红薯 — "little red
> sweet-potato" — which is why this product's mark is a 🍠.

The brand personality: **warm, confident, editorial**. A clean
alabaster ("oats") canvas, a single decisive coral-red action color, an
Outfit/Inter type pairing, soft rounded surfaces, and playful, tactile
motion (a breathing "thinking" dot, a parabolic fly-to-sync, a flip-card
re-auth). Operator-facing chrome is calm and precise; the *content* the
agent produces is exuberant, emoji-rich 小红书 copy.

---

## Sources

This system was reverse-engineered from the product's own front-end and
a high-fidelity interaction mockup. Explore these to build more
faithful 小红书文案助手 designs:

- **GitHub — `ZHV587/xiaohongshu-agent`** (private): the LangGraph
  agent backend + Next.js `web/` front-end.
  - `web/src/app/globals.css` — the authoritative design tokens
    (oats / coral / charcoal / topic-blue, Outfit + Inter, radius 1rem).
    Values here are the source of truth and are reproduced in `tokens/`.
  - `web/mockup.html` — a 1,000-line standalone interaction mockup of the
    full three-pane workbench. The `ui_kits/workbench/` recreation is a
    componentized, token-driven version of this file.
  - `web/src/components/thread/*` — the production React panels
    (`ChatTimeline`, `ComposerPanel`, `EvidenceInspector`,
    `RightInspector`, `CommandPalette`). Confirmed the production styling
    matches the mockup vocabulary (coral CTAs, oats composer, Ctrl+P
    palette).
  - The repo's chat shell descends from `langchain-ai/agent-chat-ui`.

> Note: the mockup uses the more saturated official 小红书 red `#ff2442`;
> the shipped app refined the UI primary to `#e52e40`. This system uses
> **`#e52e40` as the UI primary** and reserves **`#ff2442` for the logo
> mark** (`--coral-brand`).

---

## Content fundamentals

The product speaks **two distinct registers** — keep them apart.

### 1. Operator-facing UI copy — calm, precise, Chinese-first
- **Language:** Simplified Chinese (zh-CN) throughout the chrome.
  Technical nouns stay in English/code (`Ctrl+P`, `APP Token`,
  `oc_chat_10293`, `bot`, `Ready`).
- **Tone:** factual status, present-progressive for live work. No hype,
  no exclamation marks in chrome.
  - *"已成功连接并解析飞书多维表格 (45 条数据)"*
  - *"正在计算博主点赞权重并提炼选题规律…"*
  - *"表格同步成功！已写入第 4 行"* (a single ! is the most excitement
    the chrome ever shows)
- **Address:** the agent refers to the user as **您** (polite "you") and
  itself implicitly in the first person ("我提炼出以下 3 个选题方向").
- **Microcopy is action-led:** buttons are verb phrases — *开启全新灵感
  对话*, *立即同步至飞书多维表格*, *一键复制纯文案*, *生成*.
- **Bilingual labels** appear where a concept is a feature name:
  *思考轨迹 (Thinking Aura)*. Chinese leads, English clarifies.
- **Numbers are tabular** and always bounded: *540 / 1000 字*,
  *爆款率 96%*, *45 条数据*.

### 2. Generated 小红书 copy — exuberant, native, emoji-rich
This is the *output*, rendered in the phone preview — it follows real
小红书 conventions and must NOT be sanitized:
- Hook-first opening line, heavy emoji as bullets and emphasis
  (⛺ 1️⃣ ✅ ❌ 👇 📝 ✨ 🔥), short punchy lines, lots of line breaks.
- A *清单* (listicle) body, a *TIPS* section, a call to engage
  (*"评论区一起交流呀！"* / *"赶紧收藏起来"*).
- A trailing block of **# hashtags** (`#精致露营 #户外好物 #露营清单`).
- Bounded to **1000 字** — the editor surfaces a live count that turns
  amber/red past the limit.

**Emoji policy:** intentional and heavy *inside content*; sparse in
chrome (the 🍠 mark, the 📱/🔗 tab glyphs, category emoji on history
items ⛺/☕/👗). Never use decorative emoji in buttons, status, or labels.

---

## Visual foundations

### Color
- **Canvas = warm "oats" alabaster** (`#faf8f5`), not white. White is
  reserved for cards/surfaces that sit *on* the oats. This warmth is
  the system's signature — never put the app on pure `#fff`.
- **One primary: coral crimson** (`#e52e40`). Used for the single most
  important action in any region (生成, 开启新对话, 同步), active
  states, the breathing thinking dot, and focus rings. Hover →
  `#c81d33`. Do not introduce a second accent for actions.
- **Topic-blue** (`#007fff`) is a *data/hashtag* accent only — hashtag
  chips, field-mapping chips, the `/tags` command. Never an action.
- **Charcoal** (`#1a1a1c`) ink — body text is charcoal, never pure
  black; muted text is `#5e5e62`; subtle/meta is `#a1a09a`.
- **Semantics:** success green (`#16a34a`, "已同步/连接成功"), warning
  amber (over-length), info blue (config). Status always renders as a
  tinted pill: soft surface + saturated text + hairline border.
- **Dark theme** exists (deep `#0b0b0c` space, brighter `#ff3b54`
  coral) — apply via a `.dark` ancestor.

### Type
- **Outfit** (display) — app title, big numerics, the logo wordmark,
  topic-card index chips. Weights 700–800, tight tracking (−0.02em).
- **Inter** (body) — all UI text and long-form copy. 400/500/600.
- **CJK fallback** is baked into every family
  (PingFang SC → Microsoft YaHei → Noto Sans SC) so 中文 always renders
  cleanly even though Outfit/Inter are Latin fonts.
- **Long-form copy uses relaxed 1.7 line-height**; UI text 1.5.
- Min UI sizes: body 14px, meta 12px, badges 10px.

### Space, radius, surfaces
- **4px grid.** Pane padding 24px, card padding 14–20px, chip insets
  2–8px.
- **Soft corners:** 16px base for cards & the composer, 12px for
  buttons/inputs, 20px for message bubbles, **full pills** for badges &
  status, 40px for the phone bezel.
- **Cards** = white surface, **1px `#ebeae4` border**, **soft low
  shadow** (`--shadow-sm`), 16px radius. Clickable cards (topic, sync)
  swap their border to **coral** and **lift 2px** on hover — the single
  most repeated interaction in the product. Nested cards use the
  `sunken` oats-light tint with a coral hairline.
- **Shadows are light and warm-tinted**; the system avoids heavy drops.
  The only pronounced shadow is the right-canvas phone preview
  (`--shadow-2xl`). Primary CTAs carry a soft **coral glow**
  (`--shadow-coral`) instead of a neutral shadow.

### Backgrounds & imagery
- No gradients in chrome, no textures, no patterns. Flatness + warmth.
  The topbar uses a subtle `blur(8px)` translucent white over content.
- Note imagery is **warm, bright lifestyle photography** (user-supplied;
  demos use Unsplash). Imagery lives only inside note previews/cards,
  never as page background.

### Motion & states
- **Easing:** `cubic-bezier(0.16,1,0.3,1)` for UI; a springier
  `(0.25,1,0.5,1)` for pops/flights. Durations 140ms (hover) →
  240ms (most) → 400ms (panels/flips) → 800ms (the sync flight).
- **Signature flourishes:** a "breathing" ping ring on live/thinking
  states; a parabolic 🍠 fly-to-sync; a Y-axis flip-card for Feishu
  re-auth (red warning → green success).
- **Hover** = warm to coral / lift up 1–2px / slight bg tint.
  **Press** = settle back down. **Focus** = coral border + soft coral
  ring (`--ring-focus`). All motion respects `prefers-reduced-motion`.

---

## Iconography

- **Lucide** (https://lucide.dev) is the system icon set — it matches
  the product (`lucide-react`). Stroke ~2px, sized 14–20px, inherits
  `currentColor`.
  - Static cards convert `<i data-lucide="…">` with
    `lucide.createIcons()`.
  - **In React (the UI kit) use the `Icon` helper in
    `ui_kits/workbench/ui.jsx`** — it renders Lucide as a CSS *mask* over
    a span (colorable, fully React-controlled, no node-replacement
    crashes). Backed by the `lucide-static` CDN.
- **Emoji** carry brand meaning (🍠 mark; ⛺☕👗 categories; the
  🔥 on 爆款率). They are content, not decoration — see the emoji policy
  above.
- No custom-drawn SVG iconography, no icon font of its own. See
  `assets/README.md`.

---

## Index / manifest

**Root**
- `styles.css` — global entry point (consumers link this one file). A
  list of `@import`s only.
- `tokens/` — `fonts.css`, `colors.css`, `typography.css`,
  `spacing.css`, `radius.css`, `shadows.css`, `motion.css`.
- `assets/README.md` — iconography & imagery policy (no raster brand
  assets ship).
- `SKILL.md` — Agent-Skills-compatible entry for using this system.

**Components** (`components/<group>/` — `.jsx` + `.d.ts` + `.prompt.md`
+ one `@dsCard` HTML per group). Reach them at
`window.DesignSystem_71831b.<Name>`:
- **core/** — `Button`, `IconButton`, `Badge`, `Avatar`, `Card`
- **forms/** — `Input`, `Textarea`, `Select`
- **content/** — `HashtagTag`, `TopicCard`, `ThinkingAura`
- **device/** — `PhoneFrame`, `NoteCard`
- **data/** — `StatCard` (engagement metric tile; `editable` powers 数据回填)

**Foundation cards** (`guidelines/*.card.html`) — Colors, Type, Spacing,
Brand specimens shown in the Design System tab.

**UI kits** (`ui_kits/<product>/`):
- **`workbench/`** — the original three-pane content workbench (top bar ·
  history sidebar · chat + composer · phone preview / Feishu sync canvas ·
  Ctrl+P command palette).
- **`studio/`** — the **创作运营工作室**: one interactive prototype with a
  top section switcher and a **Tweaks** panel (toolbar → Tweaks) that flips
  between in-progress directions. Three sections:
  - **创作** — recents · chat · right panel = **选题卡 + 创作栏**. The
    composer is fully 小红书-native (hook title ≤20 字 · body · emoji
    quick-insert · hashtag matrix · 多版本草稿 · 封面建议 · AI 润色/瘦身)
    and carries a **文案体检** scorecard (标题钩子 · 关键词埋词 · emoji 密度
    · 分点结构 · 互动引导 · 话题标签 · 字数 · 封面). Tweak `右侧布局`:
    上下堆叠 / 左右分栏 / 仅创作栏.
  - **深度创作** — a focused long-form environment. Tweak `形态`:
    沉浸双栏（左写右助手）/ 分步流程（选题→大纲→正文→润色→配图）/
    多栏工作台（飞书证据 + 编辑 + 质检）.
  - **账号运营** — 数据看板 · 选题库/爆款拆解 · 内容日历/发布排期 · 数据回填
    (effect-feedback loop). Tweak `承载`: 独立页面 / 会话内（agent 驱动，
    一个会话完成所有运营动作）/ 同屏融合（chat + 看板）.
  Both kits are also registered as **Starting Points**.

---

## UI kit 运行依赖与「仅联网可用」限制

`ui_kits/studio/` 与 `ui_kits/workbench/` 两个原型都是**浏览器内直出**的
React 原型:`.jsx` 通过 `type="text/babel"` 在浏览器里即时转译运行。它们
依赖以下从 CDN(unpkg)加载的运行时,逐项如下:

| 依赖 | 版本 | 来源 | 用途 |
|---|---|---|---|
| `react` | `18.3.1` | unpkg(`react.development.js`,development UMD) | React 运行时 |
| `react-dom` | `18.3.1` | unpkg(`react-dom.development.js`,development UMD) | DOM 渲染 |
| `@babel/standalone` | `7.29.0` | unpkg(`babel.min.js`) | 浏览器内 JSX 转译 |

本地资源(**不依赖网络**,随仓库提供):

- `_ds_bundle.js` — 设计系统组件包(`window.DesignSystem_71831b.*`)。
- `../../styles.css` — 设计令牌与全局样式入口。

> **⚠️ UI kit 为原型参考,依赖上述 CDN,仅联网可用。** 断网环境下 react /
> react-dom / @babel/standalone 无法从 unpkg 加载,原型将无法渲染。这些 kit
> 定位为设计参考产物,不是生产交付物;生产前端在 `web/` 中以打包方式独立构建,
> 不依赖这些 CDN。

### 离线/联网决策(状态记录)

- **决策:** 采纳「仅文档化 CDN 限制」的轻量路径 —— **不做离线 vendoring**
  (不把 react / react-dom / @babel/standalone 下载为本地产物,也不引入构建步骤)。
- **结论:** UI kit 保持当前 CDN 加载方式,「仅联网可用」作为**已知限制**在此
  文档记录;同时在两个 `index.html` 注入纯内联的渲染错误兜底,使断网时向用户
  呈现可读错误提示而非白屏(见各 `index.html` 内联脚本)。
- **理由:** UI kit 为原型参考而非生产交付物,离线 vendoring 需引入约 2MB 本地
  产物与额外构建步骤,收益低于成本。
- **日期:** 2026-07-02

---

## 规格状态（Spec status）

- **thinking-chain-wiring:已实现并关闭(思考链为 deepagents 原生流真实投影)。** 详见 `.kiro/specs/thinking-chain-wiring/CLOSURE.md`;占位交互清理归属 `design-system-hardening` 规格 R5。
