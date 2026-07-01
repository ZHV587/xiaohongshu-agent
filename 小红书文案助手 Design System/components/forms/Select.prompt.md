Native dropdown in the system field shell — used for picking the Feishu chat to notify, field mappings, etc.

```jsx
<Select options={[
  "小红书文案运营审核群 (oc_chat_10293)",
  "露营项目内容策划小组 (oc_chat_88301)",
]} />

<Select options={[{ value: "body", label: "「正文内容」字段" }]} />
```

- Pass `options` (strings or `{value,label}`) or render `<option>` children directly.
- Custom chevron + coral focus ring match Input/Textarea.
