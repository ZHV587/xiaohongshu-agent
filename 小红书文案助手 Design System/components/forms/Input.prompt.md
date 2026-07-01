Single-line text field with oats rest state and a coral focus ring. Supports a leading icon and a trailing slot.

```jsx
<Input placeholder="输入命令或搜索动作..." leadingIcon={<Search size={16} />} trailing={<kbd>ESC</kbd>} />
<Input defaultValue="精致露营「搬家式」装备清单" />
<Input invalid placeholder="必填项" />
```

- `leadingIcon` / `trailing` render inline; trailing is handy for kbd hints and live char counts.
- `invalid` paints the border coral for error states.
