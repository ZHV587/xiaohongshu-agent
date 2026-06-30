Circular avatar for users and the agent. Initials by default, the 🍠 glyph for the assistant, or an image.

```jsx
<Avatar name="张潇潇" />                         {/* coral-tint initials */}
<Avatar glyph="🍠" variant="agent" />            {/* assistant mark */}
<Avatar name="我" variant="solid" size={28} />    {/* user bubble mark */}
<Avatar src="/photo.jpg" name="Z" />
```

- **variant**: `coral` (tint disc) · `solid` (coral fill) · `neutral` (oats) · `agent` (white w/ coral border, for 🍠).
- `size` is the pixel diameter; font scales automatically.
