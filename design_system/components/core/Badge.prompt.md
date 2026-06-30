Compact status / meta pill — sync state, draft flags, connection status, viral-rate callouts.

```jsx
<Badge tone="synced">已同步</Badge>
<Badge tone="draft">草稿</Badge>
<Badge tone="synced" dot>连接成功</Badge>
<Badge tone="hot">🔥 爆款率 96%</Badge>
<Badge tone="topic" shape="chip">正文内容</Badge>
```

- **tone**: `synced` (green) · `draft`/`neutral` (gray) · `hot`/`coral` (coral) · `topic` (blue) · `info`.
- **shape**: `pill` (default) or `chip` (squared 4px radius — used for tiny inline tags).
- `dot` prepends a same-color status dot (CLI ready, connection live).
