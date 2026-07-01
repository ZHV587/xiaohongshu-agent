小红书 hashtag chip. Blue topic chips for note tags; coral for emphasis. Add `addable` for the smart-tag picker.

```jsx
<HashtagTag>露营清单</HashtagTag>
<HashtagTag tone="coral">精致露营</HashtagTag>
<HashtagTag addable onAdd={() => append("户外美学")}>户外美学</HashtagTag>
```

- A leading `#` is prepended automatically if the label doesn't have one.
- `addable` renders a ＋ and makes the chip clickable (recommendation list).
