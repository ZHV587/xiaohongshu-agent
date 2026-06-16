# 小红书文案助手 · 前端 UI 改造设计

日期：2026-06-15
状态：已确认，进入实现计划
适用范围：`web/`（基于 langchain-ai/agent-chat-ui 的 Next.js 15 + React 19 + Tailwind v4 + shadcn/ui 前端）

---

## 一、背景

当前 `web/` 是 LangChain 官方 agent-chat-ui 的原样，呈现「开发者工具」观感：

- 配色为纯灰阶（`globals.css` 里所有 oklch 变量彩度为 0），主色近黑 `oklch(0.205 0 0)`。
- 字体为 `Inter`（仅 latin 子集，中文走 fallback）。
- 顶部挂 LangGraph logo + 「Agent Chat」字样，附一个指向官方 GitHub 仓库的图标。
- 选题以纯文本列出，无法点选；文案与普通消息无视觉区分；欢迎页是英文占位。

后端集成（LangGraph 流式、auth 多用户隔离、飞书数据、/shared 风格沉淀）已完成并验证，**本次改造不碰后端，只换前端观感与交互**。

## 二、目标

把前端从「开发者工具」变成有产品识别度的「舒服简约」界面：

- 产品名：**小红书文案助手**
- Slogan：**你的小红书爆款搭子🍠**
- 视觉风格：**暖白极简**（米白底 + 赤陶橙主色）
- 改造程度：**换皮肤 + 重做组件**（不仅改配色字体，还重做核心交互组件）

五个重点交互环节，逐个打磨：

1. **选题卡片可点选** —— agent 给的选题菜单渲染成可点击卡片，点一下自动把「写第 N 个」作为新消息发出，无需手动打字。
2. **文案卡片 + 一键复制** —— 最终文案（标题/正文/话题标签）以独立卡片呈现，带一键复制按钮。
3. **欢迎页 + 示例问题** —— 新对话时显示品牌名 + slogan + 4 个示例问题 chip，点一下即开聊。
4. **侧栏会话列表** —— 暖色侧栏，品牌区 + 新对话按钮 + 最近会话 + 底部用户信息。
5. **工具调用友好化** —— 把开发者风格的原始 JSON 表格，改成「折叠友好状态条 + 展开朴素呈现」，前端不猜数据语义（详见第 5.8 节）。

## 三、关键设计决策

### 3.1 不换框架，沿用 shadcn 体系

经调研，lobe-chat（antd + CSS-in-JS）、Vercel ai-chatbot（绑 Vercel AI SDK）等都与本项目技术栈异构，整包替换等于换框架并丢掉现有 LangGraph 集成。本项目本就是 shadcn/ui + Tailwind v4，换皮肤的 80% 收益来自改 `globals.css` 的 oklch 变量 + 换字体/logo，组件级优化在现有 `Thread` 消息流上叠加即可。**结论：保留 agent-chat-ui 的后端集成与数据流，只改视觉层与交互组件。**

### 3.2 选题/文案的「结构化渲染」靠约定标记，而非改协议

核心难点：前端怎么知道某条 AI 消息是「选题菜单」还是「文案成品」，从而渲染成卡片？

权衡过三种方案：

- **A. 解析 markdown 结构**（如识别有序列表 → 选题卡）：脆弱，agent 措辞一变就失效。
- **B. agent 输出带语义标记的代码块**（如 ` ```xhs_topics ` / ` ```xhs_copy ` 包裹 JSON）：在 AI 消息渲染前预解析抽取这两类块，渲染成卡片，其余文本走正常 markdown；抽取/解析失败就整体降级为普通 markdown。**← 采用**
- **C. 走 LangGraph Custom UI / interrupt 机制**：能力最强但改动最大，且要动后端图结构，与「只改前端」目标冲突。

选 **B 方案**：在 `prompts.py` / `SKILL.md` 里约定 agent 用约定 fenced code block 输出选题与文案；前端在 `ai.tsx` 拿到 `contentString` 后，用正则抽取 ` ```xhs_topics ` / ` ```xhs_copy ` 块，按出现顺序渲染卡片，块之间/前后的普通文本仍交给 `MarkdownText`；**抽取不到或 JSON 解析失败时整段走正常 markdown**，保证健壮性与向后兼容。前后端解耦——agent 只要遵守输出约定，前端只认标记不认措辞。

> **两个实现要点（自查发现）**：
> 1. **fence 语言名用下划线** `xhs_topics` / `xhs_copy`，不用连字符。现有 markdown `code` 组件的语言正则是 `/language-(\w+)/`，`\w` 不含 `-`，`xhs-topics` 只会被截成 `xhs`；下划线在 `\w` 内，安全。
> 2. **不在 markdown 的 `code`/`pre` 组件里渲染卡片**。react-markdown 把 fenced code 包进外层 `<pre>`（黑底 `bg-black text-white` 样式），卡片塞进去会被破坏。因此在 `ai.tsx` 的 `contentString` 层预抽取，卡片作为独立 UI 块与 markdown 片段并列渲染。

### 3.3 暖白风的实现 = 改 oklch 变量 + 换字体 + 换品牌元素

shadcn 主题完全由 `globals.css` 的 CSS 变量驱动。改造落点：

- 替换 `:root` 的 oklch 变量为暖白色板（见设计令牌）。
- `.dark` 暂不投入精力（本期聚焦亮色；保留官方暗色变量不动，避免破坏）。
- `layout.tsx` 字体由 `Inter` 换为带中文支持的字体栈。
- 替换 logo、标题文案，移除官方 GitHub 仓库图标。

## 四、设计令牌（暖白极简）

落到 `web/src/app/globals.css` 的 `:root`（同时保留 `tailwind.config.js` 里 `hsl(var(--x))` 的映射约定——注意现有配置有 oklch/hsl 混用，实现时统一为 oklch 直引用）：

| 语义 | 值（近似） | 用途 |
|---|---|---|
| `--background` | `#FAF9F7` 微暖白 | 页面主底 |
| `--foreground` | `#3A352F` 暖深灰 | 主文字 |
| `--primary` | `#E07856` 赤陶橙 | 主色：按钮、发送、用户气泡、强调 |
| `--primary-foreground` | `#FFFFFF` | 主色上的文字 |
| `--secondary` / `--muted` | `#F3F1EC` 暖米 | 侧栏、助手气泡、输入框底 |
| `--accent` | `#FBEDE6` 浅橙 | 卡片序号底、标签底 |
| `--border` | `#EADFD4` 暖边框 | 卡片/输入框描边 |
| `--muted-foreground` | `#9A9389` 暖灰 | 次要文字、placeholder |
| `--radius` | `0.875rem`（14px） | 圆角加大，更柔和 |

字体栈（`layout.tsx`）：优先系统中文字体，保证中文观感与零额外加载成本：
`-apple-system, "PingFang SC", "Microsoft YaHei", "Noto Sans SC", system-ui, sans-serif`
（可选引入 `Plus Jakarta Sans` 作为拉丁字体，但中文场景以系统字体栈为主。）

## 五、组件设计

### 5.1 品牌常量（新增 `web/src/lib/brand.ts`）

集中存放产品名、slogan、示例问题，供 layout / 欢迎页 / 侧栏 / topbar 复用，避免散落硬编码。

```ts
export const BRAND = {
  name: "小红书文案助手",
  slogan: "你的小红书爆款搭子🍠",
  mark: "🍠", // 或一个 SVG logo
  examples: [
    "帮我出「夏日防晒」的选题",
    "写一篇露营装备种草",
    "咖啡探店文案，给我 3 个标题",
    "穿搭｜平价单品穿出高级感",
  ],
} as const;
```

### 5.2 选题卡片 `TopicCards`（新增）

- **输入约定**：agent 输出 ` ```xhs_topics ` 代码块，内容为 JSON：`{ "intro": "...", "topics": ["选题1", "选题2", "选题3"] }`。
- **渲染**：intro 文字 + 每个选题一张可点卡片（序号徽标 + 文字 + 右侧 › 箭头）。
- **交互**：点击某卡 → 通过 `ThreadActionsContext` 的 `submitText("写第 N 个")` 发送人类消息，复用 `Thread` 现有提交逻辑。
- **降级**：JSON 解析失败时，该块回退为普通 markdown 渲染，不报错。

### 5.3 文案卡片 `CopyCard`（新增）

- **输入约定**：agent 输出 ` ```xhs_copy ` 代码块，JSON：`{ "title": "...", "body": "...", "tags": ["#x", "#y"] }`。
- **渲染**：卡片头（「完成文案」标签 + 「⧉ 一键复制」按钮）+ 标题 + 正文 + 话题标签区。
- **一键复制**：复制「标题 + 空行 + 正文 + 空行 + 标签」的完整纯文本到剪贴板，复制后按钮短暂变「已复制 ✓」。用 `navigator.clipboard.writeText`（已有 `useCopyToClipboard` 可参考/复用）。
- **降级**：解析失败回退普通 markdown。

### 5.4 AI 消息预抽取（改 `messages/ai.tsx`，不改 `markdown-text.tsx` 的 code 组件）

在 `ai.tsx` 拿到 `contentString` 后、渲染前，加一个解析函数把字符串切成有序片段数组：普通文本段、`xhs_topics` 段、`xhs_copy` 段。按序渲染——文本段交给 `MarkdownText`，两类卡片段交给 `TopicCards` / `CopyCard`。解析整体失败则原样把 `contentString` 交给 `MarkdownText`。

- 抽取用正则匹配 ` ```xhs_topics\n...\n``` ` / ` ```xhs_copy\n...\n``` `，对捕获内容 `JSON.parse`，失败则把该段当普通文本。
- 这样**不动 `markdown-text.tsx` 的 `code`/`pre` 渲染逻辑**，规避 `<pre>` 黑底包裹与 `\w` 正则截断两个坑。

### 5.5 欢迎页（改 `thread/index.tsx` 的 `!chatStarted` 分支）

替换现有底部居中的 LangGraph logo + 「Agent Chat」：

- 居中：品牌图标徽标 + `BRAND.name`（h1）+ `BRAND.slogan`（副标题）。
- 下方：`BRAND.examples` 渲染为一排可点 chip，点击即 `submitText(example)`。

### 5.6 侧栏 `ThreadHistory`（改 `history/index.tsx` + `thread/index.tsx` 侧栏容器）

- 顶部品牌区：图标 + `BRAND.name`（替换「Thread History」英文标题）。
- 「+ 新对话」主色按钮（现有「New thread」按钮语义迁移过来，中文化）。
- 「最近」分组小标题（中文化）。
- 会话项：选中态用 `--accent` 底色高亮。
- 底部用户区：头像（用户名首字）+ 用户名 + 角色（数据来自 auth 注入的 identity；本地 mock 用户显示占位名）。

### 5.7 顶栏与杂项清理

- 移除 `OpenGitHubRepo`（指向官方仓库的图标）。
- 顶栏品牌从 `LangGraphLogoSVG` + 「Agent Chat」换为本产品 logo + `BRAND.name`。
- 「Hide Tool Calls」开关：见 5.8（友好化后默认显示，开关移除/收次）。
- 输入框 placeholder、「Upload PDF or Image」、「Send」「Cancel」等文案中文化。
- `layout.tsx` 的 `metadata.title/description` 改为产品名与 slogan。

### 5.8 工具调用友好化（重做 `tool-calls.tsx`）

现状：`ToolCalls` / `ToolResult` 把工具调用渲染成开发者风格的原始表格——英文工具名、`call_xxx` 编码 ID、JSON 键值表、灰底等宽字体。对文案运营用户是纯噪音，也是暖白风里最扎眼的开发者味残留。

**核心原则：前端只渲染，从不猜数据语义。** 这与 5.2/5.3 一致——凡是给用户看的结构化内容（选题、文案），语义都由 agent 通过标记输出（做法 B 的延伸：agent 读懂数据，前端不重复解析）。工具调用的原始返回（如 32 行爆款数据）本质是 **agent 思考的输入/中间数据**，不是面向用户的成品；用户真正要的成品（选题/文案）已由 5.2/5.3 的卡片呈现。所以工具结果**不需要前端精修、不去识别"哪列是标题/点赞"**。

**不采用「完全隐藏」**：本产品的工具调用（读飞书爆款库可能耗时几秒）承载「正在为你做事」的反馈感，隐藏会让用户以为卡住。但也**不为中间数据做精致解析**。定位：状态条是核心（有反馈价值），展开细节是次要（想看就能看，不花力气精修）。

**两层呈现**：

- **① 折叠状态条（默认，核心）**：一行友好中文 + 状态。进行中转圈「⟳ 正在读取你的爆款库…」，完成打勾「✓ 已读取爆款库（N 条）」。
- **② 点开 → 朴素呈现（次要）**：把结果朴素地展示出来即可，**不猜字段、不做高亮标签**——`read_xhs_data` 的 `{columns, rows}` 按「列名：值」平铺成行卡（中文列名、卡片化、留白，比原始 JSON 表友好且永不错位）；文本类结果（子agent 分析、风格库写入）保留换行排版展示；仍提供「⧉ 查看原始（开发用）」回到原始 JSON。

**工具名 → 友好文案映射**（集中在常量表，新增 `web/src/lib/tool-display.ts`）：

| 工具 | 进行中 | 完成 | 展开②呈现 |
|---|---|---|---|
| `read_xhs_data` | 正在读取你的爆款库… | 已读取爆款库（N 条） | `{columns, rows}` 平铺为「列名：值」行卡 |
| `baokuan_analyst`（子agent） | 正在分析爆款规律… | 已总结这批爆款的共性 | 文本排版（保留换行） |
| 写 `/shared/xhs-style.md`（write/edit_file 命中该路径） | 正在更新你的风格库… | 已更新你的风格库 | 文本排版 |
| skills 内部操作（`ls`/`read_file` 等命中 `/skills/`） | —— | —— | **完全不显示**（纯内部噪音） |
| 未在表中的其它工具 | 正在处理… | 已完成 | 文本排版兜底 |

- 完成态计数用 `rows.length`（「已读取爆款库（N 条）」），不臆测"N 篇笔记"。
- 工具识别：`ToolCalls` 用 `tc.name` 匹配映射表；`ToolResult` 用 `message.name` 匹配；写文件类工具靠 args 里的路径判断是否命中 `/shared/`。skills 内部操作直接 `return null` 不渲染。
- **未来若要"漂亮的爆款库预览"**：正确做法是让 agent 像输出选题卡那样、用一个标记把它结构化吐出来（agent 懂语义），而非前端猜——与 5.2/5.3 同一套思路。本期不做。

**进行中 / 完成的状态判断（实现关键）**：`ToolCalls`（来自 AI 消息的 `tool_calls`）和 `ToolResult`（来自独立的 tool 消息）在消息流里是**两条独立消息**，分别渲染——mockup 里"同一条状态条从转圈变打勾"是视觉示意，实际由两条消息体现：

- **进行中**：渲染了 `ToolCalls`、但消息流里还没有 `tool_call_id` 匹配的 `ToolResult`，且 `stream.isLoading` 为真 → 状态条显示「⟳ 进行中文案」（转圈）。
- **完成**：出现了匹配的 `ToolResult` → 由 `ToolResult` 渲染「✓ 完成文案」状态条 + 可展开内容；此时对应的 `ToolCalls` 可不再单独显示进行中条（避免重复），即「ToolCalls 仅在无匹配 ToolResult 时显示进行中」。
- 配对靠 `tc.id`（ToolCalls）↔ `message.tool_call_id`（ToolResult）。实现时在 `ai.tsx` 渲染 `ToolCalls` 处传入"是否已有匹配结果"，或在 `ToolResult` 内承载完成态、`ToolCalls` 内仅承载进行中态。

> 做了友好化后工具调用默认**显示**（已经友好），5.7 那个开发者向的「Hide Tool Calls」开关随之移除/收次。


## 六、文件改动清单

| 文件 | 改动 | 类型 |
|---|---|---|
| `web/src/app/globals.css` | 替换 `:root` oklch 暖白色板、`--radius` | 改 |
| `web/src/app/layout.tsx` | 字体栈、metadata 标题描述 | 改 |
| `web/src/lib/brand.ts` | 品牌常量 | 新增 |
| `web/src/lib/thread-actions.tsx` | `ThreadActionsContext`（提供 `submitText`） | 新增 |
| `web/src/components/thread/index.tsx` | 顶栏品牌、欢迎页、移除 GitHub 图标、文案中文化、provide actions context | 改 |
| `web/src/components/thread/history/index.tsx` | 侧栏品牌区、新对话按钮、最近分组、选中态、底部用户区、中文化 | 改 |
| `web/src/components/thread/messages/ai.tsx` | `contentString` 预抽取 `xhs_topics`/`xhs_copy` 段，分派给卡片组件，其余走 MarkdownText | 改 |
| `web/src/components/thread/messages/topic-cards.tsx` | 选题卡片组件 | 新增 |
| `web/src/components/thread/messages/copy-card.tsx` | 文案卡片组件 | 新增 |
| `web/src/components/thread/messages/human.tsx` | 用户气泡用主色（现为 `bg-muted`） | 改 |
| `web/src/components/thread/messages/tool-calls.tsx` | 重做 `ToolCalls`/`ToolResult`：友好状态条 + 朴素展开，skills 内部操作不显示 | 改 |
| `web/src/lib/tool-display.ts` | 工具名→友好文案映射表 | 新增 |
| `prompts.py` / `skills/topic-content/SKILL.md` | 约定 agent 用 `xhs_topics`/`xhs_copy` fence 输出 | 改（后端文案，非逻辑） |

> `prompts.py` / `SKILL.md` 的改动只是给 agent 加输出格式约定（让它把选题/文案包进约定 fence），不改后端图结构与工具，属于「提示词层」，与「不碰后端逻辑」原则不冲突。`markdown-text.tsx` 的 `code` 组件**不改**（见 5.4）。

## 七、测试与验证

前端目前无测试框架。本期不引入重型测试体系，采用如下验证（与项目既有「能跑通 + 人工核对」的节奏一致）：

1. **构建校验**：`pnpm build`（或 `pnpm lint` + `tsc --noEmit`）通过，无类型/编译错误。
2. **手动冒烟**（`pnpm dev` 起前端 + `langgraph dev` 起后端，单一干净进程——遵守 Windows 先杀残留 python 进程的纪律）：
   - 欢迎页：品牌名、slogan、示例 chip 显示正确，点 chip 能发起对话。
   - 选题：让 agent 出选题菜单，确认渲染成可点卡片；点卡片自动发「写第 N 个」。
   - 文案：确认最终文案渲染成 `CopyCard`；点「一键复制」剪贴板内容正确、按钮变「已复制」。
   - 降级：构造一段不含约定 fence 的普通回复，确认正常 markdown 渲染、不报错。
   - 工具调用：触发读爆款库，确认进行中显示「正在读取你的爆款库…」、完成显示「✓ 已读取爆款库（N 条）」；点开看到「列名：值」平铺行卡；再点「查看原始」能看到 JSON；skills 内部操作不出现在界面上。
   - 侧栏：会话列表、选中态、底部用户名显示正常。
   - 暖白配色、中文字体、圆角整体观感符合 mockup。
3. **多用户回归**：确认改前端后 auth 隔离仍生效（沿用既有 `verify_1b3.py` 思路，前端改动不应影响）。

## 八、范围边界（YAGNI）

**本期做**：暖白换肤、品牌化、选题卡片、文案卡片、欢迎页、侧栏、文案中文化、工具调用友好化（友好状态条为核心；展开为朴素呈现，前端不猜数据语义；skills 内部操作不显示）。

**本期不做**：
- 暗色模式打磨（保留官方暗色变量不动）。
- 移动端深度适配（沿用官方响应式，不专门优化）。
- 配图 / 图片生成（既定延后）。
- 引入新的前端测试框架。
- 真实飞书 OAuth 登录界面（仍用 mock 用户；属阶段二）。
- artifact 面板的视觉重做（保留现状，本期不动）。

## 九、风险与回滚

- **fence 预抽取**可能与现有 markdown 渲染冲突——按 5.4，抽取在 `ai.tsx` 的 `contentString` 层完成，不动 `markdown-text.tsx`；只识别 `xhs_topics`/`xhs_copy` 两个标签，其余整段交给 `MarkdownText`。
- **agent 输出不稳定**（不总按约定包 fence）——靠降级渲染兜底，最差退化为纯 markdown，不影响可用性；并在 prompt 里强约定 + 给示例。
- **工具消息配对**：`ToolCalls`（AI 消息的 tool_calls）与 `ToolResult`（独立 tool 消息）是两条消息，进行中/完成态靠 `tc.id ↔ tool_call_id` 配对（见 5.8）。实现时注意流式中途、配对失败（只有 calls 无 result）的兜底——此时保留"进行中"态即可，不报错。
- **Tailwind v4 oklch/hsl 混用**：现有 `globals.css`（oklch）与 `tailwind.config.js`（`hsl(var())`）写法不一致，改色时需统一，否则颜色不生效。实现首步先理清这层映射。
- 回滚：所有改动集中在 `web/` 与提示词文案，git 可整体回退；后端逻辑零改动，无数据风险。


