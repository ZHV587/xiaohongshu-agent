The agent's live reasoning panel (思维微光). A breathing coral dot, a stepper of statuses, and an optional collapsible raw-thought log.

```jsx
<ThinkingAura
  steps={[
    { label: "已成功连接并解析飞书多维表格 (45 条数据)", state: "done" },
    { label: "正在计算博主点赞权重并提炼选题规律...", state: "active" },
  ]}
  logs={[
    { time: "12:25:01", text: "开始拉取多维表格，自动过滤附件大字段..." },
    { time: "12:25:04", text: "提取高频热词：精致露营、搬家式装备、新手避坑。" },
  ]}
/>
```

- **step.state**: `done` (green ✓) · `active` (coral, spinning) · `pending` (gray ○).
- Pass `logs` to enable the 展开分析详情 toggle.
