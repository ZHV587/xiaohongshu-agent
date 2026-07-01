// Shared helpers + store for the Studio prototype.
const LUCIDE = "https://unpkg.com/lucide-static@0.460.0/icons/";

function Icon({ name, size = 16, color, style = {} }) {
  return (
    <span aria-hidden="true" style={{
      width: size, height: size, display: "inline-block", flexShrink: 0,
      backgroundColor: color || "currentColor",
      WebkitMaskImage: `url("${LUCIDE}${name}.svg")`, maskImage: `url("${LUCIDE}${name}.svg")`,
      WebkitMaskRepeat: "no-repeat", maskRepeat: "no-repeat",
      WebkitMaskPosition: "center", maskPosition: "center",
      WebkitMaskSize: "contain", maskSize: "contain", ...style,
    }} />
  );
}

function Eyebrow({ children, style = {} }) {
  return <div style={{ fontSize: "var(--text-2xs)", fontWeight: 600, letterSpacing: "var(--tracking-wide)", textTransform: "uppercase", color: "var(--text-subtle)", ...style }}>{children}</div>;
}

function PanelHead({ icon, title, sub, right }) {
  return (
    <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 12 }}>
      <div style={{ display: "flex", alignItems: "center", gap: 8, minWidth: 0 }}>
        {icon && <Icon name={icon} size={16} color="var(--primary)" />}
        <div style={{ minWidth: 0 }}>
          <div style={{ fontSize: "var(--text-sm)", fontWeight: 700, color: "var(--text-body)" }}>{title}</div>
          {sub && <div style={{ fontSize: "var(--text-2xs)", color: "var(--text-subtle)", marginTop: 1 }}>{sub}</div>}
        </div>
      </div>
      {right}
    </div>
  );
}

// ── Shared store (one note flows across 创作 / 深度创作 / 运营) ──
const StudioContext = React.createContext(null);
const useStudio = () => React.useContext(StudioContext);

// Build version A/B/C from a topic's base draft
function buildVersions(topic) {
  const d = topic.draft;
  const cut = (s) => (s.length > 20 ? s.slice(0, 20) : s);
  return {
    A: { ...d, label: "版本 A · 种草向", note: "原稿" },
    B: {
      label: "版本 B · 避坑向", note: "AI 改写",
      title: cut(`新手别乱买！${topic.kw}避坑清单`),
      cover: "避坑\n清单",
      body: `❌ 先说结论，这几样真的别冲！踩过坑才懂～\n\n` + d.body,
      tags: [...d.tags, "避坑指南", "平价平替"].slice(0, 9),
    },
    C: {
      label: "版本 C · 情绪向", note: "AI 改写",
      title: cut(`${topic.emotional} 🌿`),
      cover: d.cover,
      body: `🌅 有些瞬间，值得被认真记录下来。\n\n` + d.body,
      tags: [...d.tags, "氛围感", "治愈系"].slice(0, 9),
    },
  };
}

// 小红书 文案体检 — driven by an EXTENSIBLE rule library
// (window.STUDIO.checkRules). Add a rule = append one object there.
function computeChecks(note) {
  const rules = (window.STUDIO && window.STUDIO.checkRules) || [];
  return rules.map((r) => {
    let res = {};
    try { res = r.test(note) || {}; } catch (e) { res = {}; }
    return { key: r.key, group: r.group || "其他", label: r.label, hint: r.hint, pass: !!res.pass, value: res.value || "—" };
  });
}
const scoreOf = (checks) => Math.round((checks.filter((c) => c.pass).length / checks.length) * 100);

Object.assign(window, { Icon, Eyebrow, PanelHead, StudioContext, useStudio, buildVersions, computeChecks, scoreOf });
