# 小红书智能体类 Claude Code 顺畅交互链路设计规范

## 1. 目标描述

为了将小红书智能体打造成像 Claude Code 般丝滑、敏捷且有掌控感的终端式交互体验，本设计方案提出**“Thought Ticker 原生事件流”**与**“Markdown 渐进式操作面板”**双轨融合交互架构。

### 预期效果：
1. **无感思考轨迹化**：大模型进行后台推理、读写飞书或库检索时，前端以高灵敏的中文步骤条（Aura Steps）展示当前微动作（如：`正在分析爆款受众痛点...`），无任何英文工具名泄露，消除等待焦虑。
2. **多阶段人机对齐（HITL Checkpoints）**：文案生成严格切碎为：起标题 ➔ 写开头 ➔ 写正文 ➔ 确认存档。每个阶段生成完毕后，智能体输出一个快捷操作面板，完全停下等待用户确认后才进行下一阶段，实现增量式内容打磨。
3. **一键快捷回复（Action Shortcuts）**：操作面板在前端渲染为气泡按钮（如 `✍️ 撰写正文`、`🔄 重新脑暴`），用户点击即自动回复后续动作，消灭打字成本。

---

## 2. 变更详情

### Component 1: 后端原生状态事件派发规约

#### ⚠️【铁律一】：后端状态推送必须使用面向普通用户的友好中文，绝对禁止直接发送英文工具名或底层技术术语。

当后端技能或工具在执行耗时逻辑、跨多源综合精读时，必须使用 LangGraph 原生的 `dispatch_custom_event` 接口实时向客户端推送中文状态事件：
```python
from langchain_core.callbacks.manager import adispatch_custom_event

# 派发运行中状态
await adispatch_custom_event(
    "thinking_step",
    {
        "id": "read_lark_table",
        "label": "正在读取飞书爆款多维表格...",
        "status": "running"
    }
)

# 派发成功完成状态
await adispatch_custom_event(
    "thinking_step",
    {
        "id": "read_lark_table",
        "label": "已成功解析飞书多维表格数据",
        "status": "done"
    }
)

# 派发失败状态
await adispatch_custom_event(
    "thinking_step",
    {
        "id": "read_lark_table",
        "label": "读取飞书多维表格失败，网络连接超时",
        "status": "failed"
    }
)
```

#### ⚠️【铁律二】：当主控路由识别到用户指令偏离了当前的文案创作流（例如触发了发现式搜索、账号定位诊断等），主控必须在进入下一个节点前，主动清空 `selected_topic` 状态，防止旧状态产生跨 Turn 污染。

---

### Component 2: 前端自定义事件扩展 (`stream-context.ts`)

#### [MODIFY] [stream-context.ts](file:///e:/%E5%B0%8F%E7%BA%A2%E4%B9%A6%E6%99%BA%E8%83%BD%E4%BD%93/web/src/providers/stream-context.ts)
在 `useTypedStream` 声明中，将 `CustomEventType` 联合类型扩展为支持后端自定义推送的思考事件：
```typescript
export type ThinkingStepEvent = {
  type: "thinking_step";
  payload: {
    id: string;
    label: string;
    status: "running" | "done" | "failed" | "interrupted";
  };
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

---

### Component 3: 思考轨迹组件重构与双源合并 (`ai.tsx`)

#### [MODIFY] [ai.tsx](file:///e:/%E5%B0%8F%E7%BA%A2%E4%B9%A6%E6%99%BA%E8%83%BD%E4%BD%93/web/src/components/thread/messages/ai.tsx)
重构 `ThinkingAura` 组件。通过 `useStreamContext()` 获取 `customEvents` 队列，将其中的 `thinking_step` 元素与已有的 `toolCalls` 进行时间戳/顺序合并，形成一条统一的中文“思考轨迹”时间线。

* **隔离与容错机制（铁律）**：
  1. **隔离渲染**：`ThinkingAura` 必须通过 `message.id` 或 `run_id` 精确过滤思考事件，严禁非当前消息的思考事件泄露进历史消息。
  2. **手动中止兼容**：若检测到全局 `isLoading` 为 `false` 且当前步骤仍为 `"running"`，界面上必须将其强行收敛为 `"interrupted"`（展示为灰色减号 `–`），禁止无限旋转。
  3. **工具报错处理**：若工具的 `tc.result` 包含明确的错误信息（如 `ok: false`），图标降级为红叉 `✗`，步骤显示为红色报错文案，不予显示绿勾。
  4. **状态渲染规范**：
     * **进行中**：前置 LoaderCircle 旋转，文本置灰。
     * **已完成**：前置绿色勾，文本加深。
     * **已失败**：前置红叉 `✗`，文本显红并可展开详情。
     * **已中断**：前置灰色减号 `–`，文本显灰色。

---

### Component 4: 渐进式控制面板块解析与渲染

#### [NEW] [PanelCard Component](file:///e:/%E5%B0%8F%E7%BA%A2%E4%B9%A6%E6%99%BA%E8%83%BD%E4%BD%93/web/src/components/thread/messages/panel-card.tsx)
创建 `PanelCard` React 组件，用于解析并渲染 ```` ```xhs_panel ```` 代码块中的 JSON 内容。
```json
{
  "actions": [
    { "label": "✍️ 写完整正文", "text": "我选这个选题，请帮我围绕它写完整文案。" },
    { "label": "🔄 换一批选题", "text": "这几个不太合适，重新换一批脑暴。" }
  ]
}
```

* **安全与时效机制（铁律）**：
  * 面板中的操作按钮**仅在会话最新一条消息上处于可点击状态**。
  * 若消息不是最新消息，或会话正处于加载等待状态（`isLoading=true`），所有操作按钮自动呈现 Disabled（禁用置灰）状态，杜绝历史状态回溯篡改风险。

---

### Component 5: 技能分段确认规约 (`xhs-copywriting/SKILL.md`)

#### [MODIFY] [SKILL.md](file:///e:/%E5%B0%8F%E7%BA%A2%E4%B9%A6%E6%99%BA%E8%83%BD%E4%BD%93/.agents/skills/xhs-copywriting/SKILL.md)
更新 `xhs-copywriting` 的执行状态规约。规定每个 Phase 必须伴随 `xhs_panel` 的输出并主动挂起（暂停）：
1. **标题脑暴 Phase** ➔ 输出 3 个候选标题 ➔ 输出 `xhs_panel` ➔ 停止等待。
2. **开头脑暴 Phase** ➔ 输出 2 个开头设计 ➔ 输出 `xhs_panel` ➔ 停止等待。
3. **正文生成 Phase** ➔ 输出完整文案 ➔ 输出包含 `[确定存档]`、`[去AI味质检]` 的 `xhs_panel` ➔ 停止等待。

---

### Component 6: 前端 UI 状态流设计（UX States Coverage）

#### ⚠️【铁律一】：点击即时响应（Pending State）。当用户点击卡片的【保存】或面板的任何快捷气泡按钮时，该组件必须立刻在本地设置 `isSubmitting=true`，显示局部旋转加载动画并禁用所有兄弟按钮，直至服务端数据流建立并接收到首个事件后才解除。

#### ⚠️【铁律二】：异常捕获与断线错误态（Connection/Error State）。如果 LangGraph Stream 流非正常中断（捕获到 onError）或服务端返回 500，必须在时间线最末尾渲染 `ErrorCard`，并提供 `[🔄 重新连接]` 或 `[↩️ 撤销重试]` 的中文交互。

#### ⚠️【铁律三】：首字骨架屏闪烁（TTFT Skeleton）。在发送消息后到大模型吐出首个正文 Token 的“思考空档期”，正文区域必须呈现柔和的微闪烁骨架屏（Skeleton Loader），在首字到达时淡出。

---

## 3. 验证计划

### 自动化测试
* 运行 `.venv\Scripts\pytest` 确保编译通过。
* 编写前端单元测试，验证 `xhs_panel` 代码块对交互组件的正确渲染与点击回调。

### 交互体验验证
* 点击选题卡“写文案”后，进入 `xhs-copywriting`：
  1. 验证时间线（ThinkingAura）是否流式滚动出：`正在脑暴候选标题...` 等友好中文步骤；
  2. 验证智能体输出 3 条标题后是否伴随出现了气泡按钮面板，且完全停止；
  3. 点击其中一个气泡标题，验证是否直接流转触发智能体开始 Phase 3（开头生成）。
