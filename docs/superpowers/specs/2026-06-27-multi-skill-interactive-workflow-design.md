# 多技能协作互动工作流设计方案

## 1. 目标描述

为了解决小红书智能体目前以 `topic-content` 为主体的单体式（Monolithic）大技能模式所导致的职责重叠、缺乏人机互动等问题，本设计方案旨在将“选题 ➔ 创作 ➔ 润色”拆分为一个由多个专业化技能组合而成分工明确的**互动式共创工作流**。

### 预期效果与交互流程：
1. **索要选题 ➔ 发现先行**：当用户请求“给我几个健身的选题”时，主控底座拦截并运行【发现式搜索】，从本地和线上各找 10 篇真实爆款笔记卡片进行展示，并完全停下等待用户浏览。
2. **多篇/单篇素材 ➔ 生成选题卡（`topic-content`）**：用户选择多篇或单篇素材点击“出选题”，触发 `topic-content` 技能，通过精读综合分析产出 3~5 个具体的选题卡片（`xhs_topics`），然后完全停下。
3. **卡片内含双按钮 ➔ 路径分流与持久化收紧**：
   * **写文案路径**：点击卡片文字主体，发送“写文案”文本并注入 `selected_topic` 状态。自动路由拉起 `xhs-copywriting`。在打磨确认完文案前，数据库**绝不提前落库**；只有当文案最终被用户发送【确定/存档】时，才在同一 Turn 中先调用 `save_generated_topic` 存选题，再调用 `save_generated_copy` 存文案。
   * **存选题路径**：点击卡片右侧的【保存】按钮，发送“保存选题”文本并注入 `selected_topic` 状态。直接调用 `save_generated_topic` + `sync_topic_to_feishu`，保存并同步飞书后，停下等待，不进入文案创作。
4. **文案质检（`xhs-audit`）**：文案完成后，提示并转入 `xhs-audit` 质检专家进行 AI 指纹检测与追问润色。

---

## 2. 变更详情

### Component 1: 主控路由规约 (`prompts.py`)

#### [MODIFY] [prompts.py](file:///e:/%E5%B0%8F%E7%BA%A2%E4%B9%A6%E6%99%BA%E8%83%BD%E4%BD%93/prompts.py)
* **修改 1**：在 `## 2. 语义路由消歧` 中，更新 `topic-content` 技能的触发与重定向逻辑：
  ```
  - 给定一个内容方向/要选题/看看有什么热门/做选题：绝对不要直接调用 topic-content，必须优先走底座的 §6.5 发现式搜索，先检索本地与线上各 10 篇爆款展示给用户，然后完全停下。只有当用户明确说“写文案”或针对具体某篇卡片发起单篇选题创作时，才路由到 topic-content。
  ```
* **修改 2**：在 `## 6.5 发现式搜索` 中，注入关键词清洗和并发调用逻辑：
  ```
  1. 关键词清洗：从用户输入中提取最核心 of 1 个名词/短词（例如从“给我几个健身的选题”中提取“健身”），去除无意义修饰词与指令词，避免堆叠导致检索 0 命中。
  2. 双路并行召回:
     - 本地一路 search_local_note_cards(keyword, limit=10) —— 我们已收录内容的细致卡片。
     - 线上一路 search_xhs_online(keyword, limit=10) —— 小红书线上实时热门笔记。
  ```

---

### Component 2: 选题到内容生成技能 (`topic-content`)

#### [MODIFY] [SKILL.md](file:///e:/%E5%B0%8F%E7%BA%A2%E4%B9%A6%E6%99%BA%E8%83%BD%E4%BD%93/.agents/skills/topic-content/SKILL.md)
* **修改 1**：将 Skill 的 description 触发词中关于“写文案/文案创作”的词组剔除，使其只响应“选题/选题脑暴”的生成。
* **修改 2**：**彻底移除** `## 第二步:写文案` 及 `## 第三步:打磨` 章节。选题生成后仅进行展示，不在此技能中落库（落库由后面的 `xhs-copywriting` 在选题被选中时触发）。
* **修改 3**：重构选题生成的触发流：
  * **单篇 ➔ 单选题**：保留并优化 `## 基于单篇原文出选题` 流程，仅基于单篇素材输出 1 个选题卡。
  * **多篇/选定素材 ➔ 选题菜单**：重构原有的批量出题步骤为 `## 基于选定素材出选题`。该步骤**不再执行任何新的检索或线上搜索**，而是直接综合选定的一批素材，产出 3~5 个选题卡片（`xhs_topics`），引导用户选择一个。

---

### Component 3: 文案创作技能 (`xhs-copywriting`)

#### [MODIFY] [SKILL.md](file:///e:/%E5%B0%8F%E7%BA%A2%E4%B9%A6%E6%99%BA%E8%83%BD%E4%BD%93/.agents/skills/xhs-copywriting/SKILL.md)
* **修改 1**：在 `## Phase 1：接收选题与背景` 注入**“状态穿透直读”**逻辑，但不在此处落库：
  ```markdown
  【状态穿透规则（极重要）】：
  在开始追问前，请优先检查运行状态或上下文（如 `selected_topic` 字段）。如果已存在用户选中的选题：
  1. 直接将 `selected_topic.topic` 作为创作主题，提取其 `selected_topic.evidence` 作为对标依据；
  2. 自动免去 Phase 1 的所有问题收集与追问，直接携带选题与依据跳入 Phase 2（备选标题）或 Phase 3 开始创作。此时不需要做任何落库，保留状态数据到内存。
  
  只有在状态为空时，才执行 Phase 1 的常规对话追问。
  ```
* **修改 2**：重构 `## Phase 5：持久化` 为用户确认落库流程：
  ```markdown
  【用户确认持久化规则（极重要）】：
  只有当文案创作全部完成，且用户发送了“确定”、“保存”、“存档”或“同步”等明确指令后，你才能调用持久化工具：
  1. 如果该文案是基于选题卡生成的（上下文存在 `selected_topic` 且尚未落库），你必须首先调用 `save_generated_topic` 工具对该选题进行落库，并记录工具返回的 UUID `resource_id` 作为选题 ID；
  2. 调用 `save_generated_copy` 工具对文案进行落库，对于 `source_topic` 参数，传入上一步生成的选题 `resource_id`；
  3. 调用 `sync_copy_to_feishu` 同步飞书草稿，并向用户返回保存成功的提示及飞书草稿链接。
  
  如果用户中途没有发送保存指令，或者对内容不满意要求修改，绝对不能在后台擅自调用任何保存工具，防止数据库被垃圾草稿塞满。
  ```

---

### Component 4: 选题卡前端组件 (`topic-cards.tsx`)

#### [MODIFY] [topic-cards.tsx](file:///e:/%E5%B0%8F%E7%BA%A2%E4%B9%A6%E6%99%BA%E8%83%BD%E4%BD%93/web/src/components/thread/messages/topic-cards.tsx)
将卡片渲染重构为双功能分流容器，点击主体执行“写文案”，点击右侧“保存”按钮单独持久化：
```typescript
// 将外层 button 改为 div 容器，避免嵌套交互元素触发 hydration 错误
<div className="group/topic relative flex items-center justify-between gap-4 rounded-2xl border border-border bg-card p-4 hover:border-coral/30 hover:shadow-[0_6px_20px_-8px_rgba(229,46,64,0.12)] transition-all duration-300">
  {/* 文字主体：点击触发写文案 */}
  <div 
    onClick={() => submitText(`我选第 ${i + 1} 个选题："${topic}"。请帮我围绕这个选题写一篇完整的小红书爆款文案。`, { selected_topic: { topic, evidence: data.evidence } })}
    className="flex items-center gap-4 flex-1 cursor-pointer"
  >
    <span className="bg-muted text-muted-foreground group-hover/topic:bg-coral group-hover/topic:text-white flex size-7 flex-shrink-0 items-center justify-center rounded-full text-xs font-semibold transition-colors duration-300">{i + 1}</span>
    <span className="text-foreground/90 flex-1 text-sm font-medium leading-relaxed font-sans transition-colors">{topic}</span>
  </div>
  {/* 新增独立全圆角小红书红保存按钮，高抗挤压 */}
  <button
    type="button"
    onClick={(e) => {
      e.stopPropagation();
      submitText(`保存第 ${i + 1} 个选题："${topic}"。`, { selected_topic: { topic, evidence: data.evidence } });
    }}
    className="z-10 flex-shrink-0 px-2.5 py-1 text-[11px] font-semibold text-coral border border-coral/20 rounded-full bg-coral/5 hover:bg-coral hover:text-white transition-all duration-300 active:scale-95 cursor-pointer"
  >
    保存
  </button>
</div>
```

---

## 3. 验证计划

### 自动化测试
* 运行全量单元测试 `.venv\Scripts\pytest`，确保所有原先的测试依然绿灯，没有对主控路由或契约产生破坏。

### 手动交互验证
* 启动交互测试，输入 `给我几个美白的选题`，验证：
  1. 是否调用了 `search_local_note_cards(limit=10)` 和 `search_xhs_online(limit=10)`；
  2. 智能体是否输出了一句简短摘要，没有 AI 脑暴生成选题，且完全停止；
  3. 点击卡片或点击“出选题”后，是否顺利进入 `topic-content`；
  4. 选题选定保存后，是否如期引导用户发起 `xhs-copywriting` 工作流。
