---
name: xiaohongshu-agent-design
description: Use this skill to generate well-branded interfaces and assets for 小红书文案助手 (Xiaohongshu Copywriting Assistant), either for production or throwaway prototypes/mocks/etc. Contains essential design guidelines, colors, type, fonts, assets, and UI kit components for prototyping.
user-invocable: true
---

Read the `readme.md` file within this skill, and explore the other available files.

If creating visual artifacts (slides, mocks, throwaway prototypes, etc), copy assets out and create static HTML files for the user to view. If working on production code, you can copy assets and read the rules here to become an expert in designing with this brand.

If the user invokes this skill without any other guidance, ask them what they want to build or design, ask some questions, and act as an expert designer who outputs HTML artifacts _or_ production code, depending on the need.

## Quick orientation

- **`readme.md`** — full design guide: product context, content
  fundamentals (two registers: calm zh-CN chrome vs. exuberant emoji-rich
  小红书 copy), visual foundations, iconography, and a file index.
- **`styles.css`** — the one stylesheet to link; it `@import`s every
  token file in `tokens/` (colors, type, spacing, radius, shadows,
  motion) and the webfonts.
- **`tokens/`** — CSS custom properties. Use the semantic aliases
  (`--primary`, `--background`, `--surface-card`, `--text-body`,
  `--border`, `--accent-surface`) in product UI; the raw ramps
  (`--coral-500`, `--oats-default`, `--charcoal-default`) for specimens.
- **`components/`** — React primitives. Each has a `.prompt.md` with a
  one-line "what & when" plus a usage example. In HTML, load the compiled
  bundle (`_ds_bundle.js`) and read components from
  `window.DesignSystem_71831b`. (Do not `<script src>` the `.jsx` files.)
- **`ui_kits/workbench/`** — the full interactive workbench recreation;
  the best reference for how components compose into a real screen, and a
  copy-paste starting point.
- **`guidelines/*.card.html`** — visual specimens for colors, type,
  spacing, and brand.

## House rules (the short version)

- App canvas is warm **oats** `#faf8f5`, never pure white. White is for
  cards on top of oats.
- **One action color:** coral `#e52e40` (hover `#c81d33`). Topic-blue is
  data/hashtag only; never an action. Logo mark uses `#ff2442`.
- **Outfit** for display/numerics, **Inter** for body; CJK fallback is
  built into the families.
- Soft rounded surfaces, light warm shadows, pill badges, coral focus
  ring. Clickable cards lift + go coral on hover.
- Keep operator chrome calm and emoji-light; keep generated 小红书 copy
  exuberant and emoji-rich. Don't mix the registers.
- Icons = Lucide (stroke). Use the `Icon` mask helper in
  `ui_kits/workbench/ui.jsx` inside React.
