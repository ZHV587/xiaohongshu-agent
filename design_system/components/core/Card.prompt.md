White surface container — the workbench's panels, message bubbles, and Feishu sync cards all sit on Card.

```jsx
<Card>同步到飞书多维表格 …</Card>
<Card tone="sunken" interactive>可点击的选题方向卡片</Card>
<Card padding="sm" tone="coral">软性强调内容</Card>
```

- **interactive**: adds the signature coral border + lift on hover (clickable topic cards, sync rows).
- **tone**: `default` (white) · `sunken` (oats-light, for nested cards) · `coral` (accent tint).
- **padding**: `none` · `sm` (14px) · `md` (20px) · `lg` (24px).
