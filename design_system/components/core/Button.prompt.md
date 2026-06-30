Primary action control — coral CTA for "生成 / 同步 / 开启全新灵感对话", with neutral, soft, and ghost variants for secondary actions.

```jsx
<Button variant="primary" leftIcon={<SquarePen />}>开启全新灵感对话</Button>
<Button variant="secondary">取消</Button>
<Button variant="soft" size="sm">一键复制纯文案</Button>
<Button variant="ghost" size="sm">展开分析详情</Button>
<Button variant="primary" loading>生成中…</Button>
```

- **variant**: `primary` (coral fill + glow), `secondary` (white/border), `soft` (coral-tint fill — used for copy/secondary CTAs), `ghost` (text-only).
- **size**: `sm` · `md` · `lg`. Use `sm` inside cards/badges.
- `block` stretches full width (sidebar new-chat button, sync button).
- `loading` swaps the label-leading slot for a spinner and disables.
