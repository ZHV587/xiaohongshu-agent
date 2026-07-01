Multi-line copy editor with a coral focus ring and optional footer toolbar — the building block of the composer and the in-place note editor.

```jsx
<Textarea
  placeholder="说说你想写什么方向，或按 Ctrl+P 调起润色工具箱..."
  footer={<>
    <Button variant="ghost" size="sm">Ctrl+P 润色工具箱</Button>
    <Button variant="primary" size="sm">生成</Button>
  </>}
/>
```

- `footer` sits below a divider on an oats strip — use for char counts and submit actions.
- Relaxed line-height (1.7) suits long-form 小红书 copy.
