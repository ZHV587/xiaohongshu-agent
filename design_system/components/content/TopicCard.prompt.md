The agent's viral-topic suggestion card — numbered, with a rationale and a 爆款率 (viral-rate) badge. Clicking picks the topic to write.

```jsx
<TopicCard
  index={1}
  title="精致露营「搬家式」装备清单"
  rationale="主打：视觉冲击、高互动分享率。分析显示赞藏比极高。"
  hotRate={96}
  onClick={() => writeTopic(1)}
/>
```

- Lifts to a coral border + tint on hover (the workbench's signature affordance).
- Omit `hotRate` to hide the badge.
