Icon-only square button for compact affordances — sidebar log-out, note share, phone-preview carousel arrows. Pair with a Lucide icon child.

```jsx
<IconButton label="退出登录"><LogOut size={16} /></IconButton>
<IconButton variant="surface" rounded="full" label="上一张"><ChevronLeft size={16} /></IconButton>
<IconButton variant="solid" label="发送"><Send size={16} /></IconButton>
```

- **variant**: `ghost` (default, warms to coral), `soft` (coral tint), `solid` (coral fill), `surface` (translucent white — use over imagery, e.g. carousel arrows).
- Always pass `label` for accessibility + tooltip.
