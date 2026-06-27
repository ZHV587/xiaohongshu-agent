# 多技能协作互动工作流实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将小红书选题生成到文案创作流程重构为以“发现先行、多技能分工、用户确认持久化”为核心的多技能协作工作流。

**Architecture:** 
1. 优化主控路由（`prompts.py`），在用户索要选题时重定向至底座的【发现式搜索】并停止；
2. 简化 `topic-content`，移除文案与打磨流程，使之聚焦于选题生成，并在选题确认后引导用户前往文案创作；
3. 优化 `xhs-copywriting` 实现 InjectedState 状态穿透读取，自动跳过 Phase 1，并在 Phase 5 由用户显式确认才落库（前置选题与后续文案的级联持久化）；
4. 重构前端 `topic-cards.tsx` 页面卡片，将外层 button 更改为 div 容器并添加独立的圆角“保存”按钮。

**Tech Stack:** Python, LangGraph, React, TypeScript, Tailwind CSS

---

### Task 1: 主控路由规约与发现机制优化

**Files:**
- Modify: `prompts.py`
- Test: `tests/test_agent_assembly.py`

- [ ] **Step 1: 编写单元测试**
  在 `tests/test_agent_assembly.py` 中，编写一个用于验证主控提示词中含有发现式检索关键词清洗和路由消歧规约的测试用例：
  ```python
  def test_main_prompt_has_routing_and_cleansing_rules(monkeypatch):
      _set_assembly_env(monkeypatch)
      import importlib
      import agent as agent_module
      importlib.reload(agent_module)
      prompt = agent_module.MAIN_SYSTEM_PROMPT
      assert "关键词清洗" in prompt
      assert "search_local_note_cards(keyword, limit=10)" in prompt
      assert "search_xhs_online(keyword, limit=10)" in prompt
  ```

- [ ] **Step 2: 运行测试以确保失败**
  运行 pytest：
  `pytest tests/test_agent_assembly.py::test_main_prompt_has_routing_and_cleansing_rules -v`
  预期：FAIL（提示断言错误，提示词中缺少对应条目）

- [ ] **Step 3: 修改 `prompts.py`**
  修改 `prompts.py`，更新 `MAIN_SYSTEM_PROMPT` 中 `## 2. 语义路由消歧` 和 `## 6.5 发现式搜索` 两处段落。
  
  在 `## 2. 语义路由消歧` 中：
  ```diff
  - - 给定一个方向/主题、要选题菜单/做选题/脑暴选题、或要完整文案(端到端创作主流程)：优先 topic-content(方向→选题→文案两步流，带数据依据)。仅做整库素材工程/主题地图：xhs-content-system。
  + - 给定一个内容方向/要选题/看看有什么热门/做选题：绝对不要直接调用 topic-content，必须优先走底座的 §6.5 发现式搜索，先检索本地与线上各 10 篇爆款展示给用户，然后完全停下。只有当用户明确说“写文案”或针对具体某篇卡片/已选中素材发起选题创作时，才路由到 topic-content。仅做整库素材工程/主题地图：xhs-content-system。
  ```
  
  在 `## 6.5 发现式搜索(出选题第一步:双路召回 + 选择性采纳)` 中：
  ```diff
  - 1. **双路并行召回**:
  -    - 本地一路 `search_local_note_cards(keyword)` —— 我们已收录内容的细致卡片(封面/互动/标签)。
  -    - 线上一路 `search_xhs_online(keyword)` —— 小红书线上实时热门笔记。线上结果**瞬态、不落库**。**关键词用简短核心词**(1 个名词/短词,如「握力圈」「敏感肌护肤」),**勿堆叠修饰词**(「秋冬握力圈正确用法」往往 0 命中)。
  + 1. **双路并行召回**:
  +    - 关键词清洗：从用户输入中提取最核心的 1 个名词/短词（例如从“给我几个健身的选题”中提取“健身”），去除无意义修饰词与指令词，避免堆叠导致检索 0 命中。
  +    - 本地一路 `search_local_note_cards(keyword, limit=10)` —— 我们已收录内容的细致卡片(封面/互动/标签)。
  +    - 线上一路 `search_xhs_online(keyword, limit=10)` —— 小红书线上实时热门笔记。线上结果**瞬态、不落库**。
  +    - 展示后必须完全停下，不进行任何 AI 选题生成或下一步的自动落库动作。
  ```

- [ ] **Step 4: 运行测试以确保通过**
  运行 pytest：
  `pytest tests/test_agent_assembly.py::test_main_prompt_has_routing_and_cleansing_rules -v`
  预期：PASS

- [ ] **Step 5: 提交更改**
  ```bash
  git add prompts.py tests/test_agent_assembly.py
  git commit -m "feat(prompt): route general topic queries to discovery search and add keyword cleansing"
  ```

---

### Task 2: 选题内容技能重构与衔接引导

**Files:**
- Modify: `.agents/skills/topic-content/SKILL.md`

- [ ] **Step 1: 修改 `.agents/skills/topic-content/SKILL.md`**
  彻底精简该技能，剔除文案创作与打磨，专注于选定素材的出选题，以及保存时的转移动作。
  
  修改后的完整内容见下方：
  ```markdown
  ---
  name: topic-content
  description: 根据选定的笔记素材，从数据中提炼选题。当用户要求“基于这篇/基于这几篇笔记出选题”、“生成选题卡”或“脑暴选题”时使用。
  ---
  
  # 按选定素材产出选题
  
  这是一个选题提炼工作流：基于用户已选中或已采纳的笔记素材，为用户产出精准的选题卡。
  
  ## 基于单篇原文出选题(搜索卡片「✨出选题」入口)
  
  当用户从搜索卡片点「出选题」时,消息会带**一篇**笔记的 JSON(含 title/summary/author/互动/tags/note_url,本地笔记还带 resource_id)。此时走**单篇 → 单选题**快路:
  
  1. **分析这一篇**:它的切入角度、戳中的痛点、标题/开头钩子、为什么这组互动数据成立(高赞/高藏说明什么)。
  2. 产出 **1 个**可执行选题,按 `xhs_topics` 格式输出(topics 数组仅 1 条),intro 一句话说明"基于〈这篇标题〉提炼"。
  3. **依据(evidence)**:
     - 笔记带 `resource_id`(本地已收录)→ evidence 直接引用该 resource_id + 标题 + 摘要 + 时效。
     - 笔记只有 `note_url`(线上、未采纳)→ **不编 resource_id**;在 intro 或选题角度里注明"(线上实时:note_url)",并提示用户"这篇是线上实时的,采纳收录后我可以把它补成正式依据"。
  4. **只展示,不落库**:不调 `save_generated_topic`/`sync_topic_to_feishu`。用户认可这个选题后(选定/说存档)才存,且只存这一个;若它基于线上笔记,提示先 `adopt_online_notes` 采纳那篇再补依据。
  
  ## 基于选定素材出选题
  
  当用户在界面上勾选了多篇笔记，或显式要求“基于这几篇笔记出选题”时触发：
  
  1. **不要再执行任何新的线上检索或本地全文搜索**。直接综合分析当前选中的这一批素材。
  2. 提炼爆款规律，产出 **3~5 个选题方向**，按 `xhs_topics` 代码块格式输出。
  3. **只展示，不在此技能中落库**。
  
  ## 选题选定引导
  
  如果用户明确发送指令“保存该选题”、“存选题”或点击卡片右侧的【保存】按钮，你才需要调用持久化工具：
  1. 调用 `save_generated_topic` 保存选题并记录生成的选题 ID。
  2. 调用 `sync_topic_to_feishu` 同步到飞书。
  
  当用户确定选题或表示要开始“写文案”时，你必须向其输出以下引导词，将工作流引向专门的文案创作技能，**且本技能不做任何落库动作**：
  ```
  已为您锁定该选题。
  
  接下来，我们可以使用专门的 `xhs-copywriting`（文案创作专家）技能来为您撰写这篇笔记的完整正文。它会以更互动的形式为您设计爆款标题与开头。
  
  您可以直接对我说：**【写完整文案】**。
  ```
  ```

- [ ] **Step 2: 运行测试以验证整体装配不受影响**
  运行 pytest：
  `.venv\Scripts\pytest tests/test_agent_assembly.py -v`
  预期：PASS

- [ ] **Step 3: 提交更改**
  ```bash
  git add .agents/skills/topic-content/SKILL.md
  git commit -m "refactor(skill): strip copywriting from topic-content and focus on ideation and handoff"
  ```

---

### Task 3: 文案创作技能重构与状态穿透

**Files:**
- Modify: `.agents/skills/xhs-copywriting/SKILL.md`

- [ ] **Step 1: 修改 `.agents/skills/xhs-copywriting/SKILL.md`**
  引入 `selected_topic` 状态穿透，跳过 Phase 1 的追问。同时重构 Phase 5 的持久化逻辑，仅在用户最终发送“保存/存档”等指令时，才级联持久化选题和文案。
  
  修改 `.agents/skills/xhs-copywriting/SKILL.md` 的 Phase 1 和 Phase 5：
  
  在 `## Phase 1：接收选题与背景`：
  ```diff
   收集以下信息（如果用户没说，逐一追问）：
   - 选题方向或具体标题
   - 目标受众
   - 核心痛点
   - 有无对标 resource_id（有的话调用 `get_resource` 精读）
+  
+  【状态穿透规则（极重要）】：
+  在开始追问前，请优先检查运行状态或上下文（如 `selected_topic` 字段）。如果已存在用户选中的选题：
+  1. 直接将 `selected_topic.topic` 作为创作主题，提取其 `selected_topic.evidence` 作为对标依据；
+  2. 自动免去 Phase 1 的所有问题收集与追问，直接携带选题与依据跳入 Phase 2（备选标题）或 Phase 3 开始创作。此时不需要做任何落库，保留状态数据到内存。
+  
+  只有在状态为空时，才执行 Phase 1 的常规对话追问。
  ```
  
  在 `## Phase 5：持久化`：
  ```diff
-  文案确认后，调用 `save_generated_copy(title, body, tags, source_topic, evidence)` 存入数据库，再调用 `sync_copy_to_feishu(title, content, tags)` 同步飞书。
-  
-  返回：resource_id + 飞书草稿链接。
+  【用户确认持久化规则（极重要）】：
+  只有当文案创作全部完成，且用户发送了“确定”、“保存”、“存档”或“同步”等明确指令后，你才能调用持久化工具：
+  1. 如果该文案是基于选题卡生成的（上下文存在 `selected_topic` 且尚未落库），你必须首先调用 `save_generated_topic` 工具对该选题进行落库，并记录工具返回的 UUID `resource_id` 作为选题 ID；
+  2. 调用 `save_generated_copy` 工具对文案进行落库，对于 `source_topic` 参数，传入上一步生成的选题 `resource_id`；
+  3. 调用 `sync_copy_to_feishu` 同步飞书草稿，并向用户返回保存成功的提示及飞书草稿链接。
+  
+  如果用户中途没有发送保存指令，或者对内容不满意要求修改，绝对不能在后台擅自调用任何保存工具，防止数据库被垃圾草稿塞满。
  ```

- [ ] **Step 2: 运行测试以验证**
  运行 pytest：
  `.venv\Scripts\pytest tests/test_agent_assembly.py -v`
  预期：PASS

- [ ] **Step 3: 提交更改**
  ```bash
  git add .agents/skills/xhs-copywriting/SKILL.md
  git commit -m "feat(skill): implement state penetration and user-confirmed cascade persistence in xhs-copywriting"
  ```

---

### Task 4: 前端选题卡片组件重构

**Files:**
- Modify: `web/src/components/thread/messages/topic-cards.tsx`

- [ ] **Step 1: 重构 `web/src/components/thread/messages/topic-cards.tsx`**
  将最外层渲染的 `button` 容器变更为 `div` 容器，以防嵌套按钮产生的 HTML 无效语法。内部分拆成两个可点击区域：左侧大文字主体触发“写文案”交互，右侧独立展示采用品牌色的“保存”按钮。
  
  使用 replace_file_content 替换以下代码：
  ```typescript
  <<<<
          {data.topics.map((topic, i) => (
            <button
              key={i}
              type="button"
              onClick={() =>
                submitText(
                  `我选第 ${i + 1} 个选题："${topic}"。请帮我围绕这个选题写一篇完整的小红书爆款文案。`,
                  // 选题依据(evidence,含 resource_id)经 graph state(selected_topic)直传工具,
                  // 绝不进对话文本/不经 LLM 重填,杜绝静默丢 resource_id。topic 取用户点的这张卡。
                  { selected_topic: { topic, evidence: data.evidence } },
                )
              }
              className="group/topic relative overflow-hidden flex items-center gap-4 rounded-2xl border border-border bg-card p-4 text-left transition-all duration-300 hover:border-primary/30 hover:shadow-[0_6px_20px_-8px_rgba(229,46,64,0.12)] active:scale-[0.995]"
            >
              {/* Left glowing accent line */}
              <div className="absolute left-0 top-0 bottom-0 w-[3px] bg-primary scale-y-0 group-hover/topic:scale-y-100 transition-transform origin-center duration-300 rounded-l-2xl" />
              
              {/* Index badge with scale and subtle rotate animation */}
              <span className="bg-muted text-muted-foreground group-hover/topic:bg-primary group-hover/topic:text-primary-foreground group-hover/topic:scale-110 group-hover/topic:rotate-6 flex size-7 flex-shrink-0 items-center justify-center rounded-full font-display text-xs font-semibold transition-all duration-300 shadow-2xs group-hover/topic:shadow-xs">
                {i + 1}
              </span>
              
              {/* Topic content text */}
              <span className="text-foreground/90 group-hover/topic:text-foreground flex-1 text-sm font-medium leading-relaxed transition-colors font-sans">
                {topic}
              </span>
              
              {/* Action Arrow with transition */}
              <ChevronRight className="text-muted-foreground/60 size-5 flex-shrink-0 transition-all duration-300 ease-out group-hover/topic:translate-x-1 group-hover/topic:text-primary" />
            </button>
          ))}
  ====
          {data.topics.map((topic, i) => (
            <div
              key={i}
              className="group/topic relative overflow-hidden flex items-center justify-between gap-4 rounded-2xl border border-border bg-card p-4 hover:border-coral/30 hover:shadow-[0_6px_20px_-8px_rgba(229,46,64,0.12)] transition-all duration-300"
            >
              {/* Left glowing accent line */}
              <div className="absolute left-0 top-0 bottom-0 w-[3px] bg-coral scale-y-0 group-hover/topic:scale-y-100 transition-transform origin-center duration-300 rounded-l-2xl" />
              
              {/* Main content area: clicks trigger copywriting workflow */}
              <div
                onClick={() =>
                  submitText(
                    `我选第 ${i + 1} 个选题："${topic}"。请帮我围绕这个选题写一篇完整的小红书爆款文案。`,
                    { selected_topic: { topic, evidence: data.evidence } },
                  )
                }
                className="flex items-center gap-4 flex-1 cursor-pointer"
              >
                <span className="bg-muted text-muted-foreground group-hover/topic:bg-coral group-hover/topic:text-white flex size-7 flex-shrink-0 items-center justify-center rounded-full font-display text-xs font-semibold transition-colors duration-300 shadow-2xs">
                  {i + 1}
                </span>
                <span className="text-foreground/90 flex-1 text-sm font-medium leading-relaxed font-sans transition-colors">
                  {topic}
                </span>
              </div>
              
              {/* Save button: directly saves the topic card to DB/Feishu */}
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
          ))}
  >>>>
  ```

- [ ] **Step 2: 编译/构建前端项目以确保无语法及 TypeScript 报错**
  在 `web` 目录下运行：
  `npm run build`
  预期：Build 完成且无错误。

- [ ] **Step 3: 提交更改**
  ```bash
  git add web/src/components/thread/messages/topic-cards.tsx
  git commit -m "style(frontend): refactor topic card component to support save button and fix nesting buttons"
  ```
