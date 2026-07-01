// Shared UI helpers for the workbench kit.
//
// Icon — renders a Lucide glyph as a CSS mask over a <span>, so it
// inherits `currentColor`, is fully React-controlled (no DOM-node
// replacement à la lucide.createIcons), and swaps cleanly on
// re-render. Backed by the lucide-static CDN.
const LUCIDE_BASE = "https://unpkg.com/lucide-static@0.460.0/icons/";

function Icon({ name, size = 16, color, style = {} }) {
  const url = `${LUCIDE_BASE}${name}.svg`;
  return (
    <span
      aria-hidden="true"
      style={{
        width: size,
        height: size,
        display: "inline-block",
        flexShrink: 0,
        backgroundColor: color || "currentColor",
        WebkitMaskImage: `url("${url}")`,
        maskImage: `url("${url}")`,
        WebkitMaskRepeat: "no-repeat",
        maskRepeat: "no-repeat",
        WebkitMaskPosition: "center",
        maskPosition: "center",
        WebkitMaskSize: "contain",
        maskSize: "contain",
        ...style,
      }}
    />
  );
}

// Eyebrow / section label
function Eyebrow({ children, style = {} }) {
  return (
    <div
      style={{
        fontSize: "var(--text-2xs)",
        fontWeight: "var(--weight-semibold)",
        letterSpacing: "var(--tracking-wide)",
        textTransform: "uppercase",
        color: "var(--text-subtle)",
        ...style,
      }}
    >
      {children}
    </div>
  );
}

Object.assign(window, { Icon, Eyebrow });
