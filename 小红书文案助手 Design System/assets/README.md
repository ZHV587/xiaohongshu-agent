# Assets — 小红书文案助手

This product ships **no proprietary raster brand assets**. The source
repo (`web/`) contained only a favicon and vendor icons (LangGraph /
GitHub), which are not part of this brand.

## Brand mark
The logo is the **🍠 sweet-potato emoji** set on a coral rounded square
— a nod to 小红书 ("Little Red Book", whose nickname is 小红薯 /
"little red sweet-potato"). Reproduce it with the emoji + a
`var(--coral-brand)` (#ff2442) tile; do not redraw it as an SVG. See
`guidelines/brand-logo.card.html`.

## Iconography
- **Lucide** (https://lucide.dev) is the system icon set — matching the
  product, which uses `lucide-react`. Load from CDN in static artifacts:
  `<script src="https://unpkg.com/lucide@latest"></script>` then
  `lucide.createIcons()`. Stroke icons at 1.5–2px, sized 14–20px.
- **Emoji** are used intentionally and heavily inside *generated 小红书
  copy* and as content category markers (⛺ ☕ 👗 🔥 ✨ 🌿 👇 📝). They
  are part of the brand's voice — do not strip them from note content.
  Keep operator-facing **UI chrome** emoji-light (the 🍠 mark and tab
  glyphs are the main exceptions).

## Imagery
Note cover images are **user-supplied photography** (warm, bright,
lifestyle). Demos use Unsplash placeholders (e.g. camping/coffee/outfit
scenes) referenced by URL — swap for real uploads in production.
