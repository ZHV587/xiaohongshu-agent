Metric tile for the 数据看板 (engagement dashboard). Shows a label, a big tabular value, an optional trend delta, and an icon chip. Set `editable` for 数据回填 — operators type the real post-performance numbers back in.

```jsx
<StatCard label="点赞" value="1.2k" delta={18} icon={<Heart />} tone="coral" />
<StatCard label="收藏" value="864" delta={-4} />
<StatCard label="新增粉丝" value="312" unit="人" delta={26} tone="success" />

{/* 数据回填 — manual entry of real metrics */}
<StatCard label="实际浏览量" value={views} editable onValueChange={setViews} />
```

- **delta**: number → ▲/▼ + percent (positive = green up); or a label string.
- **tone**: `neutral` · `coral` · `topic` · `success` colors the value.
- **editable** swaps the value for a dashed inline field.
