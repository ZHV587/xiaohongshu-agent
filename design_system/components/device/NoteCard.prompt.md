小红书 waterfall-feed card — cover image, 2-line-clamped title, author + like count. The title clamp mirrors the real feed's truncation.

```jsx
<NoteCard
  image="https://…/camp.jpg"
  title="精致露营「搬家式」装备清单"
  author="张潇潇" authorInitial="Z" likes="1.2k"
/>
<NoteCard dim ratio="4 / 5" />   {/* neighbouring placeholder */}
```

- `dim` renders a faded skeleton for surrounding feed cards.
- Vary `ratio` (3/4, 4/5, 1/1) for a natural masonry rhythm.
