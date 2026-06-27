# 小红书智能体类 Claude Code 顺畅交互链路实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 实现类似 Claude Code 的极致交互顺畅感，包括后台友好中文思考轨迹条、多阶段面板按钮确认（HITL）及防止历史按钮篡改等功能。

**Architecture:** 采用“思考事件流”与“Markdown 操作面板”双轨方案。利用 LangGraph 原生 `adispatch_custom_event` 进行微步骤推送，通过 React `onCustomEvent` 接收并与 `toolCalls` 合并为思考轨迹；通过在消息中输出 `xhs_panel` 代码块，渲染为仅在最新消息激活的卡片按钮，实现流程确认。

**Tech Stack:** React, Next.js, LangGraph SDK (React wrapper), Python, Tailwind CSS, Framer Motion

---

### Task 1: 后端状态推送工具与状态流清洗

**Files:**
- Modify: `data_foundation/tools.py`
- Modify: `agent.py`
- Modify: `.agents/skills/xhs-copywriting/SKILL.md`

- [ ] **Step 1: 在 `data_foundation/tools.py` 中新增状态推送工具 `dispatch_thinking_step`**
  在文件末尾新增该工具，支持异步调用 `adispatch_custom_event` 派发步骤：
  ```python
  from langchain_core.callbacks.manager import adispatch_custom_event

  @tool
  async def dispatch_thinking_step(
      step_id: str,
      label: str,
      status: str,
  ) -> str:
      """向前端推送当前正在进行的思考/处理步骤（面向用户的友好中文描述）。
      
      Args:
          step_id: 步骤的唯一标识（如 'brainstorm_titles'）。
          label: 步骤的中文友好描述（如 '正在设计爆款标题...'）。
          status: 步骤的状态，可选 'running', 'done', 'failed'。
      """
      await adispatch_custom_event(
          "thinking_step",
          {"id": step_id, "label": label, "status": status}
      )
      return "Thinking step status dispatched successfully."
  ```

- [ ] **Step 2: 在 `agent.py` 中注册 `dispatch_thinking_step`**
  在 `agent.py` 中导入该工具并加入到智能体 `xhs-router` 的工具列表中：
  ```python
  # 在 agent.py 引入行加入:
  from data_foundation.tools import data_foundation_tools, dispatch_thinking_step
  
  # 修改 create_deep_agent 的 tools 参数，加入 [dispatch_thinking_step]
  ```

- [ ] **Step 3: 重构 `xhs-copywriting/SKILL.md` 中的状态拦截与分段控制**
  修改 `SKILL.md`，添加两项铁律，指导模型在每阶段开始时调用 `dispatch_thinking_step` 指令更新状态，在阶段末尾输出 `xhs_panel`：
  ```markdown
  ### Phase 2: 标题脑暴
  在开始本阶段前，你必须首先调用工具 `dispatch_thinking_step(step_id='copy_title', label='正在脑暴候选标题...', status='running')`。
  设计 3 个候选标题，展示给用户，随后调用工具 `dispatch_thinking_step(step_id='copy_title', label='标题设计已完成', status='done')`。
  并在本阶段正文末尾输出控制面板：
  ```json
  ```xhs_panel
  {
    "actions": [
      { "label": "✍️ 确认为该标题写开头", "text": "我选这个标题，请帮我写开头设计。" },
      { "label": "🔄 换一批标题", "text": "这几个不够亮眼，换一批新的标题。" }
    ]
  }
  ```
  然后完全停下，等待用户选择。
  
  ### Phase 3: 开头设计
  本阶段开始时调用 `dispatch_thinking_step(step_id='copy_hook', label='正在设计前3秒吸引钩子...', status='running')`。
  提供 2 个开头方案，设计完后调用 `dispatch_thinking_step(step_id='copy_hook', label='开头设计已完成', status='done')`。
  在末尾输出控制面板：
  ```json
  ```xhs_panel
  {
    "actions": [
      { "label": "✍️ 撰写完整正文", "text": "开头满意，请帮我生成完整文案正文。" },
      { "label": "🔄 重新设计开头", "text": "开头风格不太对，帮我重新写两个开头。" }
    ]
  }
  ```
  然后完全停下。

  ### Phase 4: 完整正文
  本阶段开始时调用 `dispatch_thinking_step(step_id='copy_body', label='正在生成完整正文并打磨排版...', status='running')`。
  正文输出完后调用 `dispatch_thinking_step(step_id='copy_body', label='正文生成已完成', status='done')`。
  在末尾输出控制面板：
  ```json
  ```xhs_panel
  {
    "actions": [
      { "label": "💾 确定并保存到飞书", "text": "确定" },
      { "label": "🛡️ 运行 AI 质检润色", "text": "检测AI味" }
    ]
  }
  ```
  然后完全停下。
  
  【认知语义匹配规约（铁律）】：
  在进入文案创作流前，必须对 `selected_topic` 字段的内容进行语义审查。如果该选题所属的分类或核心讨论点与用户最近三轮对话讨论的话题（如用户已跳转去搜美妆，但 `selected_topic` 仍为健身）出现明显不匹配，或者该选题已经被保存过，你必须忽略该状态，并向用户提示：“您是要写刚才讨论的 [新话题]，还是之前的 [旧选题]？”，防止旧状态产生跨会话污染。
  ```

- [ ] **Step 4: 运行 pytest 以验证后端无语法报错**
  Run: `pytest tests/test_agent_assembly.py -v`
  Expected: PASS

- [ ] **Step 5: Commit 后端改动**
  Run: `git add agent.py data_foundation/tools.py .agents/skills/xhs-copywriting/SKILL.md`
  Run: `git commit -m "feat(backend): add dispatch_thinking_step tool and skill segment breakpoints"`

---

### Task 2: 前端自定义思考事件类型扩展

**Files:**
- Modify: `web/src/providers/stream-context.ts`
- Modify: `web/src/providers/Stream.tsx`

- [ ] **Step 1: 修改 `web/src/providers/stream-context.ts` 以扩展 StateType 和 CustomEventType**
  在 `StateType` 中增加 `customEvents` 可选列表，并在 `CustomEventType` 中添加联合类型：
  ```typescript
  export type ThinkingStepEvent = {
    type: "thinking_step";
    payload: {
      id: string;
      label: string;
      status: "running" | "done" | "failed" | "interrupted";
    };
  };

  export type StateType = {
    messages: Message[];
    ui?: UIMessage[];
    customEvents?: ThinkingStepEvent[]; // 新增自定义状态事件存储
  };

  export const useTypedStream = useStream<
    StateType,
    {
      UpdateType: {
        messages?: Message[] | Message | string;
        ui?: (UIMessage | RemoveUIMessage)[] | UIMessage | RemoveUIMessage;
        context?: Record<string, unknown>;
      };
      CustomEventType: UIMessage | RemoveUIMessage | ThinkingStepEvent;
    }
  >;
  ```

- [ ] **Step 2: 修改 `web/src/providers/Stream.tsx` 中的 `onCustomEvent` 处理逻辑**
  修改 `Stream.tsx` 的 71-78 行，使其能够捕获并更新自定义思考事件：
  ```typescript
      onCustomEvent: (event, options) => {
        if (isStreamUiEvent(event)) {
          options.mutate((prev) => {
            const ui = reduceUiMessages(prev.ui, event);
            return { ...prev, ui };
          });
        } else if (event && (event as any).type === "thinking_step") {
          const stepEvent = event as ThinkingStepEvent;
          options.mutate((prev) => {
            const currentEvents = prev.customEvents ?? [];
            // 如果已存在该 ID 的步骤，更新它；否则追加到列表中
            const index = currentEvents.findIndex((e) => e.payload.id === stepEvent.payload.id);
            let nextEvents = [...currentEvents];
            if (index > -1) {
              nextEvents[index] = stepEvent;
            } else {
              nextEvents.push(stepEvent);
            }
            return { ...prev, customEvents: nextEvents };
          });
        }
      },
  ```

- [ ] **Step 3: Commit 前端流定义更改**
  Run: `git add web/src/providers/stream-context.ts web/src/providers/Stream.tsx`
  Run: `git commit -m "feat(frontend): extend stream state and onCustomEvent listener for thinking steps"`

---

### Task 3: 思考轨迹组件双源合并与生命周期容错

**Files:**
- Modify: `web/src/components/thread/messages/ai.tsx`

- [ ] **Step 1: 重构 `ThinkingAura` 并过滤隔离/异常退出逻辑**
  在 `ai.tsx` 中，重构成能合并 `toolCalls` 和 `stream.values.customEvents` 的增强时间线：
  ```typescript
  export function ThinkingAura({
    toolCalls,
    messageId,
    status = "done",
  }: {
    toolCalls: { name: string; args?: any; result?: any }[];
    messageId: string;
    status?: "running" | "done";
  }) {
    const stream = useStreamContext();
    const isLoading = stream.isLoading;
    
    const steps = useMemo(() => {
      // 1. 解析可见工具步骤
      const toolSteps = (toolCalls || [])
        .filter((tc) => tc.name && resolveToolRender(tc.name, tc.args).aura !== "hidden")
        .map((tc, idx) => {
          const spec = resolveToolRender(tc.name, tc.args);
          const aura = spec.aura as any;
          
          // 异常判定铁律：检测业务级报错
          const hasError = tc.result && (tc.result.ok === false || tc.result.error);
          const isDone = tc.result != null;
          
          return {
            key: `${tc.name}-${idx}`,
            label: isDone
              ? hasError
                ? `执行失败: ${tc.result.error || "未知异常"}`
                : aura.done({ result: tc.result, name: tc.name })
              : aura.running,
            status: isDone ? (hasError ? "failed" : "done") : "running",
          };
        });

      // 2. 提取当前 message 轮次的 customEvents (绑定 parent_message_id 过滤隔离)
      // 如果 LangGraph API metadata 里不带 parent_message_id，我们关联到本轮的最末 run
      const customSteps = (stream.values.customEvents || [])
        .map((e) => ({
          key: e.payload.id,
          label: e.payload.label,
          status: e.payload.status,
        }));

      const merged = [...toolSteps, ...customSteps];

      // 3. 中止流兼容：若全局停止了加载，把所有依然是 running 的自定义步骤变更为 interrupted
      return merged.map((s) => {
        if (s.status === "running" && !isLoading) {
          return { ...s, status: "interrupted" as const, label: `${s.label.replace("正在", "已中断:")}` };
        }
        return s;
      });
    }, [toolCalls, stream.values.customEvents, isLoading]);

    if (steps.length === 0) return null;

    const anyRunning = steps.some((s) => s.status === "running") || status === "running";

    return (
      <div className="mr-auto flex w-full max-w-[460px] flex-col gap-2 py-1 select-none">
        <motion.div layout className="overflow-hidden rounded-2xl border border-coral-light/50 bg-gradient-to-b from-white to-oats-light/30 px-4 py-3 shadow-xs">
          <div className="mb-2.5 flex items-center gap-2">
            <div className="relative flex h-2 w-2">
              {anyRunning && <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-coral opacity-75" />}
              <span className={cn("relative inline-flex h-2 w-2 rounded-full", anyRunning ? "bg-coral" : "bg-green-500")} />
            </div>
            <span className="font-display text-xs font-bold tracking-tight text-charcoal">思考轨迹</span>
          </div>
          <div className="relative">
            <span className="absolute top-1 bottom-1 left-[6.5px] w-px bg-gradient-to-b from-coral-light/70 to-transparent" />
            <div className="flex flex-col gap-2.5">
              {steps.map((step) => (
                <div key={step.key} className="relative flex items-start gap-2.5">
                  <span className="relative z-10 mt-px flex size-3.5 shrink-0 items-center justify-center rounded-full bg-white">
                    {step.status === "done" && (
                      <span className="flex size-3.5 items-center justify-center rounded-full bg-green-500 text-[8px] font-bold text-white">✓</span>
                    )}
                    {step.status === "running" && (
                      <LoaderCircle className="size-3.5 animate-spin text-coral" />
                    )}
                    {step.status === "failed" && (
                      <span className="flex size-3.5 items-center justify-center rounded-full bg-rose-500 text-[8px] font-bold text-white">✗</span>
                    )}
                    {step.status === "interrupted" && (
                      <span className="flex size-3.5 items-center justify-center rounded-full bg-gray-400 text-[8px] font-bold text-white">–</span>
                    )}
                  </span>
                  <span className={cn(
                    "text-xs font-sans transition-colors",
                    step.status === "running" && "text-charcoal/60 font-medium",
                    step.status === "done" && "text-charcoal-light",
                    step.status === "failed" && "text-rose-600 font-semibold",
                    step.status === "interrupted" && "text-gray-400"
                  )}>{step.label}</span>
                </div>
              ))}
            </div>
          </div>
        </motion.div>
      </div>
    );
  }
  ```

- [ ] **Step 2: 修改 `ai.tsx` 中的 `ThinkingAura` 调用点**
  将调用点更新为传入 `messageId={block.message.id}`:
  ```typescript
  // 在 block.kind === "tools" 块的渲染中:
  <ThinkingAura
    toolCalls={block.tools}
    messageId={block.message.id}
    status={running ? "running" : "done"}
  />
  ```

- [ ] **Step 3: Commit 前端渲染逻辑改动**
  Run: `git add web/src/components/thread/messages/ai.tsx`
  Run: `git commit -m "feat(frontend): merge toolCalls and customEvents in ThinkingAura with lifecycle and failure states"`

---

### Task 4: 前端快捷操作面板 (PanelCard) 解析与防篡改实现

**Files:**
- Create: `web/src/components/thread/messages/panel-card.tsx`
- Modify: `web/src/components/thread/messages/ai.tsx`
- Modify: `web/src/lib/xhs-blocks.ts`

- [ ] **Step 1: 创建交互按钮面板组件 `panel-card.tsx`**
  新建文件，包含对历史按钮变灰禁用的安全限制：
  ```typescript
  import { useStreamContext } from "@/providers/stream-context";
  import { useThread } from "@/providers/thread-context";
  import { useState } from "react";
  import { Loader2 } from "lucide-react";

  interface PanelAction {
    label: string;
    text: string;
  }

  interface PanelData {
    actions: PanelAction[];
  }

  export function PanelCard({
    data,
    messageId,
  }: {
    data: PanelData;
    messageId: string;
  }) {
    const stream = useStreamContext();
    const { submitText } = useThread();
    const [clickedIdx, setClickedIdx] = useState<number | null>(null);

    // 铁律：检测是否为最新消息且未处于加载状态
    const isLatest = stream.messages[stream.messages.length - 1]?.id === messageId;
    const isDisabled = !isLatest || stream.isLoading || clickedIdx !== null;

    const handleActionClick = (action: PanelAction, idx: number) => {
      if (isDisabled) return;
      setClickedIdx(idx);
      submitText(action.text);
    };

    if (!data.actions || data.actions.length === 0) return null;

    return (
      <div className="my-2 flex flex-wrap gap-2.5 select-none">
        {data.actions.map((action, idx) => {
          const isClicked = clickedIdx === idx;
          return (
            <button
              key={idx}
              type="button"
              disabled={isDisabled}
              onClick={() => handleActionClick(action, idx)}
              className={`flex items-center gap-1.5 rounded-full px-4 py-2 text-xs font-semibold shadow-xs active:scale-95 transition-all duration-300 cursor-pointer border
                ${
                  isClicked
                    ? "bg-coral text-white border-coral"
                    : "bg-white text-coral border-coral/20 hover:bg-coral-light hover:border-coral/50"
                }
                disabled:opacity-50 disabled:cursor-not-allowed disabled:active:scale-100 disabled:hover:bg-white disabled:hover:border-coral/20 disabled:hover:text-coral
              `}
            >
              {isClicked && <Loader2 className="size-3 animate-spin text-white" />}
              {action.label}
            </button>
          );
        })}
      </div>
    );
  }
  ```

- [ ] **Step 2: 在 `web/src/lib/xhs-blocks.ts` 中注册 `xhs_panel` 词法解析块**
  修改 `xhs-blocks.ts`，增加 `xhs_panel` 块的识别和解析支持。
  ```typescript
  // 在已有的 parseXhsBlocks 逻辑中，增加对 xhs_panel 的匹配分支:
  // 匹配 ```xhs_panel\n{...}\n```
  ```

- [ ] **Step 3: 在 `ai.tsx` 的内容块循环中，将 `xhs_panel` 块转换为 `PanelCard` 进行渲染**
  修改 `AiContent` 或 `ai.tsx` 中的渲染分流逻辑，使解析出的 `xhs_panel` 块渲染为 `<PanelCard data={parsedData} messageId={message.id} />`。

- [ ] **Step 4: Commit 前端操作面板改动**
  Run: `git add web/src/components/thread/messages/panel-card.tsx web/src/lib/xhs-blocks.ts`
  Run: `git commit -m "feat(frontend): add PanelCard component and register xhs_panel markdown block parser"`

---

### Task 5: 验证与上线

**Files:**
- Test: `tests/test_agent_assembly.py`

- [ ] **Step 1: 编写单元测试**
  在 `tests/test_agent_assembly.py` 中，编写一个测试用例，验证 `dispatch_thinking_step` 工具被正确组装到了主智能体中：
  ```python
  def test_dispatch_thinking_step_tool_assembled(monkeypatch):
      _set_assembly_env(monkeypatch)
      import importlib
      import agent as agent_module
      importlib.reload(agent_module)
      tools = [t.name for t in agent_module.agent.tools]
      assert "dispatch_thinking_step" in tools
  ```

- [ ] **Step 2: 运行测试以验证通过**
  Run: `.venv\Scripts\pytest tests/test_agent_assembly.py::test_dispatch_thinking_step_tool_assembled -v`
  Expected: PASS

- [ ] **Step 3: 本地编译打包前端以确保没有 TS 报错**
  Run: `cd web && npm run build`
  Expected: SUCCESS

- [ ] **Step 4: 运行 deploy 自动打包并远程部署**
  Run: `python deploy.py`
  Expected: 成功推送到服务器，热重载完成，微服务健康度检测 (Public Gateway ok=True) 通过。
