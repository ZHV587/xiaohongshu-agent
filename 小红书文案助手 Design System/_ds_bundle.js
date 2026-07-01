/* @ds-bundle: {"format":3,"namespace":"DesignSystem_71831b","components":[{"name":"HashtagTag","sourcePath":"components/content/HashtagTag.jsx"},{"name":"ThinkingAura","sourcePath":"components/content/ThinkingAura.jsx"},{"name":"TopicCard","sourcePath":"components/content/TopicCard.jsx"},{"name":"Avatar","sourcePath":"components/core/Avatar.jsx"},{"name":"Badge","sourcePath":"components/core/Badge.jsx"},{"name":"Button","sourcePath":"components/core/Button.jsx"},{"name":"Card","sourcePath":"components/core/Card.jsx"},{"name":"IconButton","sourcePath":"components/core/IconButton.jsx"},{"name":"StatCard","sourcePath":"components/data/StatCard.jsx"},{"name":"NoteCard","sourcePath":"components/device/NoteCard.jsx"},{"name":"PhoneFrame","sourcePath":"components/device/PhoneFrame.jsx"},{"name":"Input","sourcePath":"components/forms/Input.jsx"},{"name":"Select","sourcePath":"components/forms/Select.jsx"},{"name":"Textarea","sourcePath":"components/forms/Textarea.jsx"}],"sourceHashes":{"components/content/HashtagTag.jsx":"470a154276c5","components/content/ThinkingAura.jsx":"7e6b9f1212c7","components/content/TopicCard.jsx":"015d4add2fe0","components/core/Avatar.jsx":"09f97a3ab6e1","components/core/Badge.jsx":"6b81d457a9bd","components/core/Button.jsx":"03f2b64d3d8e","components/core/Card.jsx":"0edb87070232","components/core/IconButton.jsx":"577d09976c98","components/data/StatCard.jsx":"2f93e0c3d58c","components/device/NoteCard.jsx":"d028b47eb613","components/device/PhoneFrame.jsx":"f3046835994d","components/forms/Input.jsx":"927334ed204c","components/forms/Select.jsx":"2a376896bf71","components/forms/Textarea.jsx":"32e49c2d384c","ui_kits/studio/Composer.jsx":"21c3f909dd29","ui_kits/studio/CreationScreen.jsx":"2edc1207281e","ui_kits/studio/DeepCreation.jsx":"cd248300799b","ui_kits/studio/DeepEditor.jsx":"287e6d48eb5a","ui_kits/studio/Operations.jsx":"76b733db9c5a","ui_kits/studio/Shell.jsx":"0fc59d6ce640","ui_kits/studio/app.jsx":"33bcda32199d","ui_kits/studio/data.js":"41361c37314b","ui_kits/studio/tweaks-panel.jsx":"6591467622ed","ui_kits/studio/ui.jsx":"a0fc9877b183","ui_kits/workbench/ChatPane.jsx":"3fdefd792c7a","ui_kits/workbench/CommandPalette.jsx":"75d9b9060a8b","ui_kits/workbench/FeishuSync.jsx":"a9b81915d09f","ui_kits/workbench/PhonePreview.jsx":"f0ceab76f72a","ui_kits/workbench/RightCanvas.jsx":"71d69c28d667","ui_kits/workbench/Sidebar.jsx":"e2df9c7870a8","ui_kits/workbench/TopBar.jsx":"77b8567cc760","ui_kits/workbench/app.jsx":"c45596206ed5","ui_kits/workbench/data.js":"e7bd81fa0f3b","ui_kits/workbench/ui.jsx":"23346dfa0729"},"inlinedExternals":[],"unexposedExports":[]} */

(() => {

const __ds_ns = (window.DesignSystem_71831b = window.DesignSystem_71831b || {});

const __ds_scope = {};

(__ds_ns.__errors = __ds_ns.__errors || []);

// components/content/HashtagTag.jsx
try { (() => {
function _extends() { return _extends = Object.assign ? Object.assign.bind() : function (n) { for (var e = 1; e < arguments.length; e++) { var t = arguments[e]; for (var r in t) ({}).hasOwnProperty.call(t, r) && (n[r] = t[r]); } return n; }, _extends.apply(null, arguments); }
/**
 * HashtagTag — a 小红书 topic chip (#话题). Topic-blue by default,
 * coral when emphasised. `addable` shows a + affordance for the
 * smart-recommendation tag picker.
 */
function HashtagTag({
  children,
  tone = "topic",
  addable = false,
  onAdd,
  style = {},
  ...rest
}) {
  const [hover, setHover] = React.useState(false);
  const tones = {
    topic: {
      bg: "var(--topicblue-light)",
      fg: "var(--topicblue-default)",
      bd: "color-mix(in srgb, var(--topicblue-default) 22%, transparent)"
    },
    coral: {
      bg: "var(--accent-surface)",
      fg: "var(--accent-foreground)",
      bd: "var(--border-coral)"
    },
    plain: {
      bg: "var(--oats-dark)",
      fg: "var(--text-muted)",
      bd: "var(--border)"
    }
  };
  const t = tones[tone] || tones.topic;
  const label = typeof children === "string" && !children.startsWith("#") ? `#${children}` : children;
  return /*#__PURE__*/React.createElement("span", _extends({
    onMouseEnter: () => setHover(true),
    onMouseLeave: () => setHover(false),
    onClick: addable ? onAdd : undefined,
    style: {
      display: "inline-flex",
      alignItems: "center",
      gap: "0.25rem",
      fontFamily: "var(--font-sans)",
      fontSize: "var(--text-2xs)",
      fontWeight: "var(--weight-medium)",
      lineHeight: 1,
      padding: "0.3rem 0.55rem",
      borderRadius: "var(--radius-full)",
      background: hover && addable ? "color-mix(in srgb, " + t.fg + " 14%, var(--surface-card))" : t.bg,
      color: t.fg,
      border: `1px solid ${t.bd}`,
      cursor: addable ? "pointer" : "default",
      transition: "background var(--dur-fast) var(--ease-out)",
      whiteSpace: "nowrap",
      ...style
    }
  }, rest), label, addable && /*#__PURE__*/React.createElement("span", {
    style: {
      fontSize: 12,
      lineHeight: 1,
      opacity: 0.8
    }
  }, "\uFF0B"));
}
Object.assign(__ds_scope, { HashtagTag });
})(); } catch (e) { __ds_ns.__errors.push({ path: "components/content/HashtagTag.jsx", error: String((e && e.message) || e) }); }

// components/content/ThinkingAura.jsx
try { (() => {
function _extends() { return _extends = Object.assign ? Object.assign.bind() : function (n) { for (var e = 1; e < arguments.length; e++) { var t = arguments[e]; for (var r in t) ({}).hasOwnProperty.call(t, r) && (n[r] = t[r]); } return n; }, _extends.apply(null, arguments); }
/**
 * ThinkingAura (思维微光) — the agent's live reasoning panel. A
 * breathing coral dot, a stepper of statuses (done / active /
 * pending), and an optional collapsible log of raw thoughts.
 */
function ThinkingAura({
  title = "思考轨迹 (Thinking Aura)",
  steps = [],
  logs = null,
  defaultOpen = false,
  style = {},
  ...rest
}) {
  const [open, setOpen] = React.useState(defaultOpen);
  const stateColor = {
    done: "var(--success)",
    active: "var(--primary)",
    pending: "var(--text-subtle)"
  };
  const stateIcon = {
    done: "✓",
    active: "◐",
    pending: "○"
  };
  return /*#__PURE__*/React.createElement("div", _extends({
    style: {
      background: "var(--surface-card)",
      border: "1px solid var(--border-coral)",
      borderRadius: "var(--radius-xl)",
      boxShadow: "var(--shadow-sm)",
      padding: "0.875rem",
      width: "100%",
      ...style
    }
  }, rest), /*#__PURE__*/React.createElement("div", {
    style: {
      display: "flex",
      alignItems: "center",
      justifyContent: "space-between",
      marginBottom: "0.75rem"
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      display: "flex",
      alignItems: "center",
      gap: "0.6rem"
    }
  }, /*#__PURE__*/React.createElement("span", {
    style: {
      position: "relative",
      display: "inline-flex",
      width: 10,
      height: 10
    }
  }, /*#__PURE__*/React.createElement("span", {
    style: {
      position: "absolute",
      inset: 0,
      borderRadius: "var(--radius-full)",
      background: "var(--primary)",
      animation: "xhs-ping 1.4s var(--ease-out) infinite"
    }
  }), /*#__PURE__*/React.createElement("span", {
    style: {
      position: "relative",
      borderRadius: "var(--radius-full)",
      width: 10,
      height: 10,
      background: "var(--primary)"
    }
  })), /*#__PURE__*/React.createElement("span", {
    style: {
      fontFamily: "var(--font-sans)",
      fontWeight: "var(--weight-bold)",
      fontSize: "var(--text-xs)",
      color: "var(--text-body)"
    }
  }, title)), logs && /*#__PURE__*/React.createElement("button", {
    onClick: () => setOpen(o => !o),
    style: {
      background: "none",
      border: "none",
      cursor: "pointer",
      color: "var(--primary)",
      fontFamily: "var(--font-sans)",
      fontWeight: "var(--weight-semibold)",
      fontSize: "var(--text-2xs)",
      display: "inline-flex",
      alignItems: "center",
      gap: "0.2rem"
    }
  }, open ? "收起分析详情 ▴" : "展开分析详情 ▾")), /*#__PURE__*/React.createElement("div", {
    style: {
      display: "flex",
      flexDirection: "column",
      gap: "0.5rem"
    }
  }, steps.map((s, i) => {
    const st = s.state || "pending";
    return /*#__PURE__*/React.createElement("div", {
      key: i,
      style: {
        display: "flex",
        alignItems: "center",
        gap: "0.5rem",
        fontSize: "var(--text-xs)",
        color: stateColor[st],
        fontWeight: st === "active" ? "var(--weight-semibold)" : "var(--weight-regular)"
      }
    }, /*#__PURE__*/React.createElement("span", {
      style: {
        width: 14,
        textAlign: "center",
        display: "inline-block",
        animation: st === "active" ? "spin 1.4s linear infinite" : "none"
      }
    }, stateIcon[st]), /*#__PURE__*/React.createElement("span", null, s.label));
  })), logs && open && /*#__PURE__*/React.createElement("div", {
    style: {
      marginTop: "0.7rem",
      borderTop: "1px solid var(--border)",
      paddingTop: "0.6rem",
      display: "flex",
      flexDirection: "column",
      gap: "0.4rem",
      fontFamily: "var(--font-mono)",
      fontSize: "var(--text-2xs)",
      color: "var(--text-subtle)",
      background: "var(--oats-light)",
      borderRadius: "var(--radius-sm)",
      padding: "0.6rem",
      maxHeight: 140,
      overflowY: "auto"
    }
  }, logs.map((l, i) => /*#__PURE__*/React.createElement("div", {
    key: i,
    style: {
      display: "flex",
      gap: "0.4rem"
    }
  }, l.time && /*#__PURE__*/React.createElement("span", {
    style: {
      color: "var(--primary)",
      fontWeight: "var(--weight-bold)",
      flexShrink: 0
    }
  }, "[", l.time, "]"), /*#__PURE__*/React.createElement("span", null, l.text || l)))));
}
Object.assign(__ds_scope, { ThinkingAura });
})(); } catch (e) { __ds_ns.__errors.push({ path: "components/content/ThinkingAura.jsx", error: String((e && e.message) || e) }); }

// components/content/TopicCard.jsx
try { (() => {
function _extends() { return _extends = Object.assign ? Object.assign.bind() : function (n) { for (var e = 1; e < arguments.length; e++) { var t = arguments[e]; for (var r in t) ({}).hasOwnProperty.call(t, r) && (n[r] = t[r]); } return n; }, _extends.apply(null, arguments); }
/**
 * TopicCard — a viral-topic suggestion the agent proposes. Numbered
 * coral index, title + rationale, and a "hot rate" 爆款率 badge.
 * Clickable; lifts to coral on hover (the signature interaction).
 */
function TopicCard({
  index = 1,
  title,
  rationale,
  hotRate = null,
  onClick,
  style = {},
  ...rest
}) {
  const [hover, setHover] = React.useState(false);
  return /*#__PURE__*/React.createElement("div", _extends({
    onClick: onClick,
    onMouseEnter: () => setHover(true),
    onMouseLeave: () => setHover(false),
    style: {
      display: "flex",
      alignItems: "center",
      gap: "0.75rem",
      padding: "0.875rem",
      borderRadius: "var(--radius-md)",
      background: hover ? "color-mix(in srgb, var(--accent-surface) 55%, var(--surface-card))" : "var(--oats-light)",
      border: `1px solid ${hover ? "var(--primary)" : "var(--border-coral)"}`,
      cursor: "pointer",
      transition: "all var(--dur-base) var(--ease-out)",
      ...style
    }
  }, rest), /*#__PURE__*/React.createElement("span", {
    style: {
      flexShrink: 0,
      width: 28,
      height: 28,
      borderRadius: "var(--radius-sm)",
      background: "var(--accent-surface)",
      color: "var(--accent-foreground)",
      display: "flex",
      alignItems: "center",
      justifyContent: "center",
      fontFamily: "var(--font-display)",
      fontWeight: "var(--weight-bold)",
      fontSize: "var(--text-xs)",
      transform: hover ? "scale(1.08)" : "none",
      transition: "transform var(--dur-base) var(--ease-out)"
    }
  }, index), /*#__PURE__*/React.createElement("div", {
    style: {
      flex: 1,
      minWidth: 0
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      fontFamily: "var(--font-sans)",
      fontWeight: "var(--weight-semibold)",
      fontSize: "var(--text-sm)",
      color: "var(--text-body)"
    }
  }, title), rationale && /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: "var(--text-xs)",
      color: "var(--text-subtle)",
      marginTop: 2,
      lineHeight: "var(--leading-snug)"
    }
  }, rationale)), hotRate != null && /*#__PURE__*/React.createElement("span", {
    style: {
      flexShrink: 0,
      display: "inline-flex",
      alignItems: "center",
      gap: "0.25rem",
      fontSize: "var(--text-2xs)",
      fontWeight: "var(--weight-bold)",
      color: "var(--hot)",
      background: "var(--hot-surface)",
      border: "1px solid var(--border-coral)",
      padding: "0.2rem 0.5rem",
      borderRadius: "var(--radius-xs)"
    }
  }, /*#__PURE__*/React.createElement("span", null, "\uD83D\uDD25"), " \u7206\u6B3E\u7387 ", hotRate, "%"));
}
Object.assign(__ds_scope, { TopicCard });
})(); } catch (e) { __ds_ns.__errors.push({ path: "components/content/TopicCard.jsx", error: String((e && e.message) || e) }); }

// components/core/Avatar.jsx
try { (() => {
function _extends() { return _extends = Object.assign ? Object.assign.bind() : function (n) { for (var e = 1; e < arguments.length; e++) { var t = arguments[e]; for (var r in t) ({}).hasOwnProperty.call(t, r) && (n[r] = t[r]); } return n; }, _extends.apply(null, arguments); }
/**
 * Avatar — circular user/agent mark. Renders initials on a
 * coral-tint disc by default, or the 🍠 agent glyph, or an image.
 */
function Avatar({
  name = "",
  src = null,
  glyph = null,
  size = 32,
  variant = "coral",
  style = {},
  ...rest
}) {
  const initials = name.trim().split(/\s+/).map(w => w[0]).slice(0, 2).join("").toUpperCase();
  const variants = {
    coral: {
      background: "var(--accent-surface)",
      color: "var(--accent-foreground)"
    },
    solid: {
      background: "var(--primary)",
      color: "var(--primary-foreground)"
    },
    neutral: {
      background: "var(--oats-dark)",
      color: "var(--text-body)"
    },
    agent: {
      background: "var(--surface-card)",
      color: "inherit",
      border: "1px solid var(--border-coral)"
    }
  };
  return /*#__PURE__*/React.createElement("div", _extends({
    style: {
      width: size,
      height: size,
      flexShrink: 0,
      borderRadius: "var(--radius-full)",
      display: "inline-flex",
      alignItems: "center",
      justifyContent: "center",
      fontFamily: "var(--font-display)",
      fontWeight: "var(--weight-bold)",
      fontSize: Math.round(size * 0.4),
      overflow: "hidden",
      boxShadow: "var(--shadow-xs)",
      ...variants[variant],
      ...style
    }
  }, rest), src ? /*#__PURE__*/React.createElement("img", {
    src: src,
    alt: name,
    style: {
      width: "100%",
      height: "100%",
      objectFit: "cover"
    }
  }) : glyph ? /*#__PURE__*/React.createElement("span", {
    style: {
      fontSize: Math.round(size * 0.56)
    }
  }, glyph) : initials);
}
Object.assign(__ds_scope, { Avatar });
})(); } catch (e) { __ds_ns.__errors.push({ path: "components/core/Avatar.jsx", error: String((e && e.message) || e) }); }

// components/core/Badge.jsx
try { (() => {
function _extends() { return _extends = Object.assign ? Object.assign.bind() : function (n) { for (var e = 1; e < arguments.length; e++) { var t = arguments[e]; for (var r in t) ({}).hasOwnProperty.call(t, r) && (n[r] = t[r]); } return n; }, _extends.apply(null, arguments); }
/**
 * Badge — compact status / meta pill. Tones map to the system's
 * semantic surfaces: synced (green), draft (gray), hot (coral),
 * topic (blue), info. Pill or chip (squared) shape.
 */
function Badge({
  children,
  tone = "neutral",
  shape = "pill",
  dot = false,
  style = {},
  ...rest
}) {
  const tones = {
    neutral: {
      bg: "var(--oats-dark)",
      fg: "var(--text-muted)",
      bd: "var(--border)"
    },
    synced: {
      bg: "var(--success-surface)",
      fg: "var(--success)",
      bd: "var(--success-border)"
    },
    hot: {
      bg: "var(--hot-surface)",
      fg: "var(--hot)",
      bd: "var(--border-coral)"
    },
    topic: {
      bg: "var(--topicblue-light)",
      fg: "var(--topicblue-default)",
      bd: "color-mix(in srgb, var(--topicblue-default) 18%, transparent)"
    },
    info: {
      bg: "var(--info-surface)",
      fg: "var(--info)",
      bd: "var(--info-border)"
    },
    coral: {
      bg: "var(--accent-surface)",
      fg: "var(--accent-foreground)",
      bd: "var(--border-coral)"
    },
    draft: {
      bg: "#f8f7f4",
      fg: "var(--text-subtle)",
      bd: "var(--border)"
    }
  };
  const t = tones[tone] || tones.neutral;
  return /*#__PURE__*/React.createElement("span", _extends({
    style: {
      display: "inline-flex",
      alignItems: "center",
      gap: "0.3rem",
      fontFamily: "var(--font-sans)",
      fontSize: "var(--text-2xs)",
      fontWeight: "var(--weight-semibold)",
      lineHeight: 1,
      padding: shape === "pill" ? "0.25rem 0.55rem" : "0.2rem 0.4rem",
      borderRadius: shape === "pill" ? "var(--radius-full)" : "var(--radius-xs)",
      background: t.bg,
      color: t.fg,
      border: `1px solid ${t.bd}`,
      whiteSpace: "nowrap",
      ...style
    }
  }, rest), dot && /*#__PURE__*/React.createElement("span", {
    style: {
      width: 6,
      height: 6,
      borderRadius: "var(--radius-full)",
      background: "currentColor",
      flexShrink: 0
    }
  }), children);
}
Object.assign(__ds_scope, { Badge });
})(); } catch (e) { __ds_ns.__errors.push({ path: "components/core/Badge.jsx", error: String((e && e.message) || e) }); }

// components/core/Button.jsx
try { (() => {
function _extends() { return _extends = Object.assign ? Object.assign.bind() : function (n) { for (var e = 1; e < arguments.length; e++) { var t = arguments[e]; for (var r in t) ({}).hasOwnProperty.call(t, r) && (n[r] = t[r]); } return n; }, _extends.apply(null, arguments); }
/**
 * Button — 小红书文案助手 primary action control.
 * Coral-filled CTA, neutral secondary, quiet ghost, and soft
 * (coral-tint) variants. Press shrinks slightly; primary carries
 * a coral glow shadow.
 */
function Button({
  children,
  variant = "primary",
  size = "md",
  block = false,
  disabled = false,
  loading = false,
  leftIcon = null,
  rightIcon = null,
  style = {},
  ...rest
}) {
  const sizes = {
    sm: {
      fontSize: "var(--text-xs)",
      padding: "0.375rem 0.75rem",
      gap: "0.375rem",
      minHeight: 32
    },
    md: {
      fontSize: "var(--text-sm)",
      padding: "0.55rem 1.1rem",
      gap: "0.5rem",
      minHeight: 40
    },
    lg: {
      fontSize: "var(--text-base)",
      padding: "0.7rem 1.4rem",
      gap: "0.6rem",
      minHeight: 48
    }
  };
  const variants = {
    primary: {
      background: "var(--primary)",
      color: "var(--primary-foreground)",
      border: "1px solid transparent",
      boxShadow: "var(--shadow-coral)"
    },
    secondary: {
      background: "var(--surface-card)",
      color: "var(--text-body)",
      border: "1px solid var(--border)",
      boxShadow: "var(--shadow-xs)"
    },
    soft: {
      background: "var(--accent-surface)",
      color: "var(--accent-foreground)",
      border: "1px solid var(--border-coral)",
      boxShadow: "none"
    },
    ghost: {
      background: "transparent",
      color: "var(--text-muted)",
      border: "1px solid transparent",
      boxShadow: "none"
    }
  };
  const [hover, setHover] = React.useState(false);
  const isDisabled = disabled || loading;
  const hoverBg = {
    primary: "var(--primary-hover)",
    secondary: "var(--oats-default)",
    soft: "color-mix(in srgb, var(--primary) 15%, transparent)",
    ghost: "var(--oats-dark)"
  };
  return /*#__PURE__*/React.createElement("button", _extends({
    disabled: isDisabled,
    onMouseEnter: () => setHover(true),
    onMouseLeave: () => setHover(false),
    style: {
      display: block ? "flex" : "inline-flex",
      width: block ? "100%" : "auto",
      alignItems: "center",
      justifyContent: "center",
      fontFamily: "var(--font-sans)",
      fontWeight: "var(--weight-semibold)",
      borderRadius: "var(--radius-md)",
      cursor: isDisabled ? "not-allowed" : "pointer",
      opacity: isDisabled ? 0.55 : 1,
      transition: "background var(--dur-fast) var(--ease-out), transform var(--dur-fast) var(--ease-out)",
      transform: hover && !isDisabled ? "translateY(-1px)" : "none",
      whiteSpace: "nowrap",
      ...sizes[size],
      ...variants[variant],
      ...(hover && !isDisabled ? {
        background: hoverBg[variant]
      } : {}),
      ...style
    }
  }, rest), loading ? /*#__PURE__*/React.createElement(Spinner, null) : leftIcon, children, rightIcon);
}
function Spinner() {
  return /*#__PURE__*/React.createElement("span", {
    style: {
      width: 14,
      height: 14,
      borderRadius: "var(--radius-full)",
      border: "2px solid currentColor",
      borderTopColor: "transparent",
      display: "inline-block",
      animation: "spin 0.7s linear infinite"
    }
  });
}
Object.assign(__ds_scope, { Button });
})(); } catch (e) { __ds_ns.__errors.push({ path: "components/core/Button.jsx", error: String((e && e.message) || e) }); }

// components/core/Card.jsx
try { (() => {
function _extends() { return _extends = Object.assign ? Object.assign.bind() : function (n) { for (var e = 1; e < arguments.length; e++) { var t = arguments[e]; for (var r in t) ({}).hasOwnProperty.call(t, r) && (n[r] = t[r]); } return n; }, _extends.apply(null, arguments); }
/**
 * Card — white surface container on the oats canvas. Soft border
 * + low shadow. `interactive` adds a coral hover lift (used for
 * clickable topic / sync cards). `tone` tints the whole card.
 */
function Card({
  children,
  interactive = false,
  tone = "default",
  padding = "md",
  style = {},
  ...rest
}) {
  const [hover, setHover] = React.useState(false);
  const pads = {
    none: 0,
    sm: "0.875rem",
    md: "1.25rem",
    lg: "1.5rem"
  };
  const tones = {
    default: {
      background: "var(--surface-card)",
      border: "var(--border)"
    },
    sunken: {
      background: "var(--oats-light)",
      border: "var(--border-coral)"
    },
    coral: {
      background: "var(--accent-surface)",
      border: "var(--border-coral)"
    }
  };
  const t = tones[tone] || tones.default;
  return /*#__PURE__*/React.createElement("div", _extends({
    onMouseEnter: () => setHover(true),
    onMouseLeave: () => setHover(false),
    style: {
      background: t.background,
      border: `1px solid ${interactive && hover ? "var(--primary)" : t.border}`,
      borderRadius: "var(--radius-lg)",
      boxShadow: "var(--shadow-sm)",
      padding: pads[padding],
      cursor: interactive ? "pointer" : "default",
      transition: "border-color var(--dur-base) var(--ease-out), transform var(--dur-base) var(--ease-out), background var(--dur-base) var(--ease-out)",
      transform: interactive && hover ? "translateY(-2px)" : "none",
      ...(interactive && hover ? {
        background: "color-mix(in srgb, var(--accent-surface) 60%, var(--surface-card))"
      } : {}),
      ...style
    }
  }, rest), children);
}
Object.assign(__ds_scope, { Card });
})(); } catch (e) { __ds_ns.__errors.push({ path: "components/core/Card.jsx", error: String((e && e.message) || e) }); }

// components/core/IconButton.jsx
try { (() => {
function _extends() { return _extends = Object.assign ? Object.assign.bind() : function (n) { for (var e = 1; e < arguments.length; e++) { var t = arguments[e]; for (var r in t) ({}).hasOwnProperty.call(t, r) && (n[r] = t[r]); } return n; }, _extends.apply(null, arguments); }
/**
 * IconButton — square, icon-only control. Used for sidebar
 * affordances (log-out, share, carousel arrows). Defaults to a
 * quiet ghost that warms to coral on hover.
 */
function IconButton({
  children,
  size = "md",
  variant = "ghost",
  rounded = "md",
  label,
  style = {},
  ...rest
}) {
  const dims = {
    sm: 28,
    md: 36,
    lg: 44
  }[size];
  const [hover, setHover] = React.useState(false);
  const variants = {
    ghost: {
      background: hover ? "var(--oats-dark)" : "transparent",
      color: hover ? "var(--primary)" : "var(--text-muted)",
      border: "1px solid transparent"
    },
    soft: {
      background: "var(--accent-surface)",
      color: "var(--accent-foreground)",
      border: "1px solid var(--border-coral)"
    },
    solid: {
      background: hover ? "var(--primary-hover)" : "var(--primary)",
      color: "var(--primary-foreground)",
      border: "1px solid transparent",
      boxShadow: "var(--shadow-sm)"
    },
    surface: {
      background: hover ? "#ffffff" : "rgba(255,255,255,0.75)",
      color: "var(--text-body)",
      border: "1px solid var(--border)",
      boxShadow: "var(--shadow-sm)"
    }
  };
  return /*#__PURE__*/React.createElement("button", _extends({
    "aria-label": label,
    title: label,
    onMouseEnter: () => setHover(true),
    onMouseLeave: () => setHover(false),
    style: {
      width: dims,
      height: dims,
      display: "inline-flex",
      alignItems: "center",
      justifyContent: "center",
      borderRadius: rounded === "full" ? "var(--radius-full)" : "var(--radius-md)",
      cursor: "pointer",
      flexShrink: 0,
      transition: "background var(--dur-fast) var(--ease-out), color var(--dur-fast) var(--ease-out)",
      ...variants[variant],
      ...style
    }
  }, rest), children);
}
Object.assign(__ds_scope, { IconButton });
})(); } catch (e) { __ds_ns.__errors.push({ path: "components/core/IconButton.jsx", error: String((e && e.message) || e) }); }

// components/data/StatCard.jsx
try { (() => {
function _extends() { return _extends = Object.assign ? Object.assign.bind() : function (n) { for (var e = 1; e < arguments.length; e++) { var t = arguments[e]; for (var r in t) ({}).hasOwnProperty.call(t, r) && (n[r] = t[r]); } return n; }, _extends.apply(null, arguments); }
/**
 * StatCard — a metric tile for the 数据看板. Shows a label, a big
 * tabular value, an optional delta (up = success, down = muted/coral),
 * and an optional leading icon chip. `editable` renders the value as
 * an inline field for 数据回填 (manual metric entry).
 */
function StatCard({
  label,
  value,
  unit = "",
  delta = null,
  icon = null,
  tone = "neutral",
  editable = false,
  onValueChange,
  style = {},
  ...rest
}) {
  const tones = {
    neutral: "var(--text-body)",
    coral: "var(--primary)",
    topic: "var(--topicblue-default)",
    success: "var(--success)"
  };
  const deltaUp = typeof delta === "number" ? delta >= 0 : null;
  return /*#__PURE__*/React.createElement("div", _extends({
    style: {
      background: "var(--surface-card)",
      border: "1px solid var(--border)",
      borderRadius: "var(--radius-lg)",
      boxShadow: "var(--shadow-sm)",
      padding: "var(--space-3-5)",
      display: "flex",
      flexDirection: "column",
      gap: 8,
      minWidth: 0,
      ...style
    }
  }, rest), /*#__PURE__*/React.createElement("div", {
    style: {
      display: "flex",
      alignItems: "center",
      justifyContent: "space-between",
      gap: 8
    }
  }, /*#__PURE__*/React.createElement("span", {
    style: {
      fontSize: "var(--text-xs)",
      color: "var(--text-muted)",
      fontWeight: "var(--weight-medium)",
      whiteSpace: "nowrap",
      overflow: "hidden",
      textOverflow: "ellipsis"
    }
  }, label), icon && /*#__PURE__*/React.createElement("span", {
    style: {
      width: 26,
      height: 26,
      borderRadius: "var(--radius-sm)",
      background: "var(--accent-surface)",
      color: "var(--primary)",
      display: "inline-flex",
      alignItems: "center",
      justifyContent: "center",
      flexShrink: 0
    }
  }, icon)), /*#__PURE__*/React.createElement("div", {
    style: {
      display: "flex",
      alignItems: "baseline",
      gap: 4
    }
  }, editable ? /*#__PURE__*/React.createElement("input", {
    value: value,
    onChange: e => onValueChange?.(e.target.value),
    inputMode: "numeric",
    style: {
      width: "100%",
      border: "1px dashed var(--border-strong)",
      borderRadius: "var(--radius-sm)",
      background: "var(--oats-light)",
      fontFamily: "var(--font-display)",
      fontWeight: "var(--weight-bold)",
      fontSize: "var(--text-2xl)",
      color: tones[tone],
      padding: "2px 8px",
      outline: "none"
    },
    className: "font-tabular"
  }) : /*#__PURE__*/React.createElement("span", {
    className: "font-tabular",
    style: {
      fontFamily: "var(--font-display)",
      fontWeight: "var(--weight-black)",
      fontSize: "var(--text-2xl)",
      color: tones[tone],
      lineHeight: 1
    }
  }, value), unit && /*#__PURE__*/React.createElement("span", {
    style: {
      fontSize: "var(--text-xs)",
      color: "var(--text-subtle)"
    }
  }, unit)), delta != null && /*#__PURE__*/React.createElement("span", {
    style: {
      display: "inline-flex",
      alignItems: "center",
      gap: 3,
      fontSize: "var(--text-2xs)",
      fontWeight: "var(--weight-semibold)",
      color: deltaUp ? "var(--success)" : "var(--text-muted)"
    }
  }, /*#__PURE__*/React.createElement("span", null, deltaUp ? "▲" : "▼"), typeof delta === "number" ? `${Math.abs(delta)}%` : delta, /*#__PURE__*/React.createElement("span", {
    style: {
      color: "var(--text-subtle)",
      fontWeight: 400,
      marginLeft: 2
    }
  }, "\u8FD17\u5929")));
}
Object.assign(__ds_scope, { StatCard });
})(); } catch (e) { __ds_ns.__errors.push({ path: "components/data/StatCard.jsx", error: String((e && e.message) || e) }); }

// components/device/NoteCard.jsx
try { (() => {
function _extends() { return _extends = Object.assign ? Object.assign.bind() : function (n) { for (var e = 1; e < arguments.length; e++) { var t = arguments[e]; for (var r in t) ({}).hasOwnProperty.call(t, r) && (n[r] = t[r]); } return n; }, _extends.apply(null, arguments); }
/**
 * NoteCard — a 小红书 waterfall-feed card: cover image, 2-line
 * clamped title, author + like count. `dim` renders a faded
 * placeholder (neighbouring feed cards).
 */
function NoteCard({
  image = null,
  title = "",
  author = "",
  authorInitial = "",
  likes = "",
  ratio = "3 / 4",
  dim = false,
  style = {},
  ...rest
}) {
  if (dim) {
    return /*#__PURE__*/React.createElement("div", _extends({
      style: {
        background: "var(--surface-card)",
        borderRadius: "var(--radius-md)",
        overflow: "hidden",
        border: "1px solid var(--border)",
        opacity: 0.55,
        ...style
      }
    }, rest), /*#__PURE__*/React.createElement("div", {
      style: {
        width: "100%",
        aspectRatio: ratio,
        background: "var(--gray-200)"
      }
    }), /*#__PURE__*/React.createElement("div", {
      style: {
        padding: "0.5rem"
      }
    }, /*#__PURE__*/React.createElement("div", {
      style: {
        height: 10,
        width: "80%",
        background: "var(--gray-200)",
        borderRadius: 4,
        marginBottom: 6
      }
    }), /*#__PURE__*/React.createElement("div", {
      style: {
        height: 8,
        width: "40%",
        background: "var(--gray-200)",
        borderRadius: 4
      }
    })));
  }
  return /*#__PURE__*/React.createElement("div", _extends({
    style: {
      background: "var(--surface-card)",
      borderRadius: "var(--radius-md)",
      overflow: "hidden",
      border: "1px solid var(--border)",
      boxShadow: "var(--shadow-xs)",
      display: "flex",
      flexDirection: "column",
      ...style
    }
  }, rest), /*#__PURE__*/React.createElement("div", {
    style: {
      width: "100%",
      aspectRatio: ratio,
      overflow: "hidden",
      background: "var(--accent-surface)"
    }
  }, image && /*#__PURE__*/React.createElement("img", {
    src: image,
    alt: title,
    style: {
      width: "100%",
      height: "100%",
      objectFit: "cover"
    }
  })), /*#__PURE__*/React.createElement("div", {
    style: {
      padding: "0.5rem",
      display: "flex",
      flexDirection: "column",
      gap: "0.4rem"
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      fontFamily: "var(--font-sans)",
      fontSize: "var(--text-2xs)",
      fontWeight: "var(--weight-bold)",
      lineHeight: "var(--leading-snug)",
      color: "var(--text-body)",
      display: "-webkit-box",
      WebkitLineClamp: 2,
      WebkitBoxOrient: "vertical",
      overflow: "hidden"
    }
  }, title), /*#__PURE__*/React.createElement("div", {
    style: {
      display: "flex",
      justifyContent: "space-between",
      alignItems: "center",
      fontSize: 9,
      color: "var(--text-subtle)"
    }
  }, /*#__PURE__*/React.createElement("span", {
    style: {
      display: "inline-flex",
      alignItems: "center",
      gap: 4
    }
  }, /*#__PURE__*/React.createElement("span", {
    style: {
      width: 14,
      height: 14,
      borderRadius: "var(--radius-full)",
      background: "var(--oats-dark)",
      color: "var(--text-body)",
      display: "inline-flex",
      alignItems: "center",
      justifyContent: "center",
      fontWeight: 700,
      fontSize: 8
    }
  }, authorInitial), /*#__PURE__*/React.createElement("span", {
    style: {
      maxWidth: 48,
      overflow: "hidden",
      textOverflow: "ellipsis",
      whiteSpace: "nowrap"
    }
  }, author)), /*#__PURE__*/React.createElement("span", {
    style: {
      display: "inline-flex",
      alignItems: "center",
      gap: 2
    }
  }, "\u2665 ", likes))));
}
Object.assign(__ds_scope, { NoteCard });
})(); } catch (e) { __ds_ns.__errors.push({ path: "components/device/NoteCard.jsx", error: String((e && e.message) || e) }); }

// components/device/PhoneFrame.jsx
try { (() => {
function _extends() { return _extends = Object.assign ? Object.assign.bind() : function (n) { for (var e = 1; e < arguments.length; e++) { var t = arguments[e]; for (var r in t) ({}).hasOwnProperty.call(t, r) && (n[r] = t[r]); } return n; }, _extends.apply(null, arguments); }
/**
 * PhoneFrame — the 小红书 mobile-preview bezel. A charcoal iPhone
 * shell with a notch; children render as the screen. Used by the
 * right-canvas note preview.
 */
function PhoneFrame({
  children,
  width = 340,
  style = {},
  ...rest
}) {
  return /*#__PURE__*/React.createElement("div", _extends({
    style: {
      width,
      aspectRatio: "9 / 18.5",
      border: "8px solid var(--charcoal-default)",
      borderRadius: "var(--radius-phone)",
      background: "#ffffff",
      boxShadow: "var(--shadow-2xl)",
      overflow: "hidden",
      position: "relative",
      display: "flex",
      flexDirection: "column",
      flexShrink: 0,
      ...style
    }
  }, rest), /*#__PURE__*/React.createElement("div", {
    style: {
      position: "absolute",
      top: 0,
      left: "50%",
      transform: "translateX(-50%)",
      width: 120,
      height: 22,
      background: "var(--charcoal-default)",
      borderBottomLeftRadius: 16,
      borderBottomRightRadius: 16,
      zIndex: 20
    }
  }), children);
}
Object.assign(__ds_scope, { PhoneFrame });
})(); } catch (e) { __ds_ns.__errors.push({ path: "components/device/PhoneFrame.jsx", error: String((e && e.message) || e) }); }

// components/forms/Input.jsx
try { (() => {
function _extends() { return _extends = Object.assign ? Object.assign.bind() : function (n) { for (var e = 1; e < arguments.length; e++) { var t = arguments[e]; for (var r in t) ({}).hasOwnProperty.call(t, r) && (n[r] = t[r]); } return n; }, _extends.apply(null, arguments); }
/**
 * Input — single-line text field. Oats-tinted rest state that
 * brightens to white with a coral ring on focus. Optional
 * leading icon and trailing slot (e.g. kbd hint / char count).
 */
function Input({
  leadingIcon = null,
  trailing = null,
  invalid = false,
  style = {},
  containerStyle = {},
  ...rest
}) {
  const [focus, setFocus] = React.useState(false);
  return /*#__PURE__*/React.createElement("div", {
    style: {
      display: "flex",
      alignItems: "center",
      gap: "0.5rem",
      background: focus ? "var(--surface-card)" : "var(--input-bg)",
      border: `1px solid ${invalid ? "var(--primary)" : focus ? "var(--primary)" : "var(--border)"}`,
      borderRadius: "var(--radius-md)",
      padding: "0 0.75rem",
      boxShadow: focus ? "var(--ring-focus)" : "none",
      transition: "border-color var(--dur-fast) var(--ease-out), box-shadow var(--dur-fast) var(--ease-out), background var(--dur-fast) var(--ease-out)",
      ...containerStyle
    }
  }, leadingIcon && /*#__PURE__*/React.createElement("span", {
    style: {
      color: "var(--text-subtle)",
      display: "inline-flex"
    }
  }, leadingIcon), /*#__PURE__*/React.createElement("input", _extends({
    onFocus: e => {
      setFocus(true);
      rest.onFocus?.(e);
    },
    onBlur: e => {
      setFocus(false);
      rest.onBlur?.(e);
    },
    style: {
      flex: 1,
      minWidth: 0,
      border: "none",
      outline: "none",
      background: "transparent",
      fontFamily: "var(--font-sans)",
      fontSize: "var(--text-sm)",
      color: "var(--text-body)",
      padding: "0.55rem 0",
      ...style
    }
  }, rest)), trailing && /*#__PURE__*/React.createElement("span", {
    style: {
      color: "var(--text-subtle)",
      display: "inline-flex",
      flexShrink: 0
    }
  }, trailing));
}
Object.assign(__ds_scope, { Input });
})(); } catch (e) { __ds_ns.__errors.push({ path: "components/forms/Input.jsx", error: String((e && e.message) || e) }); }

// components/forms/Select.jsx
try { (() => {
function _extends() { return _extends = Object.assign ? Object.assign.bind() : function (n) { for (var e = 1; e < arguments.length; e++) { var t = arguments[e]; for (var r in t) ({}).hasOwnProperty.call(t, r) && (n[r] = t[r]); } return n; }, _extends.apply(null, arguments); }
/**
 * Select — native dropdown wrapped in the system's field shell
 * (oats rest, coral focus, chevron affordance). Pass an `options`
 * array of {value,label} or plain strings, or use children.
 */
function Select({
  options = null,
  invalid = false,
  style = {},
  containerStyle = {},
  children,
  ...rest
}) {
  const [focus, setFocus] = React.useState(false);
  const opts = options ? options.map(o => typeof o === "string" ? {
    value: o,
    label: o
  } : o) : null;
  return /*#__PURE__*/React.createElement("div", {
    style: {
      position: "relative",
      display: "flex",
      alignItems: "center",
      background: focus ? "var(--surface-card)" : "var(--input-bg)",
      border: `1px solid ${invalid ? "var(--primary)" : focus ? "var(--primary)" : "var(--border)"}`,
      borderRadius: "var(--radius-md)",
      boxShadow: focus ? "var(--ring-focus)" : "none",
      transition: "border-color var(--dur-fast) var(--ease-out), box-shadow var(--dur-fast) var(--ease-out)",
      ...containerStyle
    }
  }, /*#__PURE__*/React.createElement("select", _extends({
    onFocus: () => setFocus(true),
    onBlur: () => setFocus(false),
    style: {
      appearance: "none",
      WebkitAppearance: "none",
      border: "none",
      outline: "none",
      background: "transparent",
      fontFamily: "var(--font-sans)",
      fontSize: "var(--text-sm)",
      color: "var(--text-body)",
      padding: "0.55rem 2rem 0.55rem 0.75rem",
      width: "100%",
      cursor: "pointer",
      ...style
    }
  }, rest), opts ? opts.map(o => /*#__PURE__*/React.createElement("option", {
    key: o.value,
    value: o.value
  }, o.label)) : children), /*#__PURE__*/React.createElement("span", {
    "aria-hidden": true,
    style: {
      position: "absolute",
      right: "0.7rem",
      pointerEvents: "none",
      color: "var(--text-subtle)",
      fontSize: 11
    }
  }, "\u25BE"));
}
Object.assign(__ds_scope, { Select });
})(); } catch (e) { __ds_ns.__errors.push({ path: "components/forms/Select.jsx", error: String((e && e.message) || e) }); }

// components/forms/Textarea.jsx
try { (() => {
function _extends() { return _extends = Object.assign ? Object.assign.bind() : function (n) { for (var e = 1; e < arguments.length; e++) { var t = arguments[e]; for (var r in t) ({}).hasOwnProperty.call(t, r) && (n[r] = t[r]); } return n; }, _extends.apply(null, arguments); }
/**
 * Textarea — multi-line copy editor. Same focus treatment as
 * Input. Optional footer slot for char-count / actions, matching
 * the workbench composer and the in-place note editor.
 */
function Textarea({
  footer = null,
  invalid = false,
  rows = 4,
  innerRef = null,
  style = {},
  containerStyle = {},
  ...rest
}) {
  const [focus, setFocus] = React.useState(false);
  return /*#__PURE__*/React.createElement("div", {
    style: {
      display: "flex",
      flexDirection: "column",
      background: "var(--surface-card)",
      border: `1px solid ${invalid ? "var(--primary)" : focus ? "var(--primary)" : "var(--border)"}`,
      borderRadius: "var(--radius-lg)",
      boxShadow: focus ? "var(--ring-focus)" : "var(--shadow-xs)",
      overflow: "hidden",
      transition: "border-color var(--dur-fast) var(--ease-out), box-shadow var(--dur-fast) var(--ease-out)",
      ...containerStyle
    }
  }, /*#__PURE__*/React.createElement("textarea", _extends({
    ref: innerRef,
    rows: rows,
    onFocus: e => {
      setFocus(true);
      rest.onFocus?.(e);
    },
    onBlur: e => {
      setFocus(false);
      rest.onBlur?.(e);
    },
    style: {
      border: "none",
      outline: "none",
      resize: "none",
      background: "transparent",
      fontFamily: "var(--font-sans)",
      fontSize: "var(--text-sm)",
      lineHeight: "var(--leading-relaxed)",
      color: "var(--text-body)",
      padding: "0.875rem",
      ...style
    }
  }, rest)), footer && /*#__PURE__*/React.createElement("div", {
    style: {
      display: "flex",
      alignItems: "center",
      justifyContent: "space-between",
      gap: "0.5rem",
      padding: "0.5rem 0.75rem",
      borderTop: "1px solid var(--border)",
      background: "var(--oats-light)"
    }
  }, footer));
}
Object.assign(__ds_scope, { Textarea });
})(); } catch (e) { __ds_ns.__errors.push({ path: "components/forms/Textarea.jsx", error: String((e && e.message) || e) }); }

// ui_kits/studio/Composer.jsx
try { (() => {
// 创作栏 Composer — 小红书-native editor bound to the shared note.
// Live 文案体检, working AI actions, tag matrix, multi-version, 定稿排期.
function Composer({
  layout
}) {
  const {
    Input,
    Textarea,
    Button,
    HashtagTag,
    Badge
  } = window.DesignSystem_71831b;
  const {
    note,
    actions
  } = useStudio();
  const S = window.STUDIO;
  const bodyRef = React.useRef(null);
  if (note.status === "idle") return /*#__PURE__*/React.createElement(EmptyComposer, null);
  const writing = note.status === "writing";
  const checks = computeChecks(note);
  const score = scoreOf(checks);
  const insertEmoji = e => {
    const el = bodyRef.current;
    if (!el) {
      actions.updateField("body", (note.body || "") + e);
      return;
    }
    const s = el.selectionStart,
      en = el.selectionEnd;
    actions.updateField("body", note.body.slice(0, s) + e + note.body.slice(en));
    requestAnimationFrame(() => {
      el.focus();
      el.selectionStart = el.selectionEnd = s + e.length;
    });
  };
  return /*#__PURE__*/React.createElement("div", {
    className: "cs",
    style: {
      display: "flex",
      flexDirection: "column",
      gap: 14,
      height: "100%",
      overflowY: "auto"
    }
  }, /*#__PURE__*/React.createElement(PanelHead, {
    icon: "pen-line",
    title: "\u521B\u4F5C\u680F",
    sub: "\u5C0F\u7EA2\u4E66\u7B14\u8BB0 \xB7 \u8FB9\u5199\u8FB9\u4F53\u68C0",
    right: layout === "deep" ? null : /*#__PURE__*/React.createElement(Button, {
      variant: "ghost",
      size: "sm",
      leftIcon: /*#__PURE__*/React.createElement(Icon, {
        name: "feather",
        size: 13
      }),
      onClick: () => actions.setSection("deep")
    }, "\u6DF1\u5EA6\u521B\u4F5C")
  }), note.versions && /*#__PURE__*/React.createElement("div", {
    style: {
      display: "flex",
      gap: 6
    }
  }, ["A", "B", "C"].map(id => {
    const v = note.versions[id],
      on = id === note.activeVersion;
    return /*#__PURE__*/React.createElement("button", {
      key: id,
      onClick: () => actions.setVersion(id),
      title: v.title,
      style: {
        flex: 1,
        textAlign: "left",
        padding: "7px 9px",
        borderRadius: "var(--radius-sm)",
        cursor: "pointer",
        border: `1px solid ${on ? "var(--primary)" : "var(--border)"}`,
        background: on ? "var(--accent-surface)" : "var(--surface-card)"
      }
    }, /*#__PURE__*/React.createElement("div", {
      style: {
        fontSize: 10,
        fontWeight: 700,
        color: on ? "var(--primary)" : "var(--text-body)"
      }
    }, v.label), /*#__PURE__*/React.createElement("div", {
      style: {
        fontSize: 9,
        color: "var(--text-subtle)",
        marginTop: 2
      }
    }, v.note));
  })), /*#__PURE__*/React.createElement(VisualStudio, null), /*#__PURE__*/React.createElement("div", {
    style: {
      display: "flex",
      flexDirection: "column",
      gap: 5
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      display: "flex",
      justifyContent: "space-between",
      alignItems: "center"
    }
  }, /*#__PURE__*/React.createElement(Eyebrow, null, "\u6807\u9898 \xB7 \u94A9\u5B50\u4F18\u5148"), /*#__PURE__*/React.createElement("span", {
    className: "font-tabular",
    style: {
      fontSize: 10,
      color: note.title.length > 20 ? "var(--warning)" : "var(--text-subtle)"
    }
  }, note.title.length, " / 20")), /*#__PURE__*/React.createElement(Input, {
    value: note.title,
    onChange: e => actions.updateField("title", e.target.value)
  })), /*#__PURE__*/React.createElement("div", {
    style: {
      display: "flex",
      flexDirection: "column",
      gap: 5
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      display: "flex",
      justifyContent: "space-between",
      alignItems: "center"
    }
  }, /*#__PURE__*/React.createElement(Eyebrow, null, "\u6B63\u6587 ", writing && /*#__PURE__*/React.createElement("span", {
    style: {
      color: "var(--primary)",
      marginLeft: 6
    }
  }, "\uD83C\uDF60 \u64B0\u5199\u4E2D\u2026")), /*#__PURE__*/React.createElement("div", {
    style: {
      display: "flex",
      gap: 5
    }
  }, /*#__PURE__*/React.createElement(Button, {
    variant: "soft",
    size: "sm",
    leftIcon: /*#__PURE__*/React.createElement(Icon, {
      name: "sparkles",
      size: 12
    }),
    onClick: actions.polish,
    disabled: writing
  }, "\u6DA6\u8272"), /*#__PURE__*/React.createElement(Button, {
    variant: "soft",
    size: "sm",
    leftIcon: /*#__PURE__*/React.createElement(Icon, {
      name: "scissors",
      size: 12
    }),
    onClick: actions.shorten,
    disabled: writing
  }, "\u7626\u8EAB"), /*#__PURE__*/React.createElement(Button, {
    variant: "soft",
    size: "sm",
    leftIcon: /*#__PURE__*/React.createElement(Icon, {
      name: "hash",
      size: 12
    }),
    onClick: actions.addTags,
    disabled: writing
  }, "\u914D\u6807\u7B7E"))), /*#__PURE__*/React.createElement(Textarea, {
    innerRef: bodyRef,
    value: writing ? note.body + " ▍" : note.body,
    onChange: e => actions.updateField("body", e.target.value),
    rows: layout === "split" ? 7 : 9,
    readOnly: writing,
    footer: /*#__PURE__*/React.createElement(React.Fragment, null, /*#__PURE__*/React.createElement("div", {
      style: {
        display: "flex",
        gap: 3,
        flexWrap: "wrap"
      }
    }, S.quickEmoji.slice(0, 10).map(e => /*#__PURE__*/React.createElement("button", {
      key: e,
      onClick: () => insertEmoji(e),
      disabled: writing,
      style: {
        border: "none",
        background: "transparent",
        cursor: "pointer",
        fontSize: 15,
        lineHeight: 1,
        padding: 1,
        opacity: writing ? 0.4 : 1
      }
    }, e))), /*#__PURE__*/React.createElement(Badge, {
      tone: note.body.length > 1000 ? "hot" : "synced",
      shape: "chip"
    }, note.body.length, " / 1000"))
  })), /*#__PURE__*/React.createElement("div", {
    style: {
      display: "flex",
      flexDirection: "column",
      gap: 7
    }
  }, /*#__PURE__*/React.createElement(Eyebrow, null, "\u8BDD\u9898\u6807\u7B7E \xB7 ", note.tags.length, " \u4E2A\uFF08\u5EFA\u8BAE 5\u201310\uFF0C\u5927\u8BCD+\u957F\u5C3E\uFF09"), /*#__PURE__*/React.createElement("div", {
    style: {
      display: "flex",
      flexWrap: "wrap",
      gap: 6
    }
  }, note.tags.map(t => /*#__PURE__*/React.createElement("span", {
    key: t,
    onClick: () => actions.removeTag(t),
    title: "\u70B9\u51FB\u79FB\u9664",
    style: {
      cursor: "pointer"
    }
  }, /*#__PURE__*/React.createElement(HashtagTag, null, t))), note.tags.length === 0 && /*#__PURE__*/React.createElement("span", {
    style: {
      fontSize: 11,
      color: "var(--text-subtle)"
    }
  }, "\u6682\u65E0\uFF0C\u70B9\u4E0B\u65B9\u63A8\u8350\u6DFB\u52A0")), /*#__PURE__*/React.createElement("div", {
    style: {
      display: "flex",
      flexWrap: "wrap",
      gap: 6,
      paddingTop: 2
    }
  }, /*#__PURE__*/React.createElement("span", {
    style: {
      fontSize: 10,
      color: "var(--text-subtle)",
      alignSelf: "center"
    }
  }, "\u63A8\u8350\uFF1A"), S.recommendedTags.filter(t => !note.tags.includes(t)).slice(0, 5).map(t => /*#__PURE__*/React.createElement(HashtagTag, {
    key: t,
    addable: true,
    onAdd: () => actions.addTag(t)
  }, t)))), layout !== "deep" && /*#__PURE__*/React.createElement(React.Fragment, null, /*#__PURE__*/React.createElement(CopyDoctor, {
    checks: checks,
    score: score
  }), /*#__PURE__*/React.createElement(RiskPanel, {
    note: note
  }), /*#__PURE__*/React.createElement(ScheduleBar, {
    score: score,
    status: note.status
  })));
}
function EmptyComposer() {
  return /*#__PURE__*/React.createElement("div", {
    style: {
      height: "100%",
      display: "flex",
      flexDirection: "column",
      alignItems: "center",
      justifyContent: "center",
      textAlign: "center",
      gap: 12,
      padding: 24,
      color: "var(--text-subtle)"
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      width: 56,
      height: 56,
      borderRadius: "var(--radius-lg)",
      background: "var(--accent-surface)",
      display: "flex",
      alignItems: "center",
      justifyContent: "center",
      fontSize: 26
    }
  }, "\uD83C\uDF60"), /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: "var(--text-sm)",
      fontWeight: 700,
      color: "var(--text-body)"
    }
  }, "\u4ECE\u9009\u9898\u5361\u5F00\u59CB\u521B\u4F5C"), /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: "var(--text-xs)",
      maxWidth: 240,
      lineHeight: "var(--leading-relaxed)"
    }
  }, "\u70B9\u4EFB\u610F\u4E00\u5F20", /*#__PURE__*/React.createElement("b", {
    style: {
      color: "var(--primary)"
    }
  }, "\u9009\u9898\u5361"), "\uFF0C\uD83C\uDF60 \u4F1A\u6309\u5C0F\u7EA2\u4E66\u98CE\u683C\u6D41\u5F0F\u751F\u6210\u8349\u7A3F\u5230\u8FD9\u91CC\uFF0C\u7136\u540E\u8FB9\u6539\u8FB9\u4F53\u68C0\u3002"));
}

// 文案体检 scorecard — grouped, driven by the extensible rule library
function CopyDoctor({
  checks,
  score
}) {
  const store = useStudio();
  const groups = [];
  checks.forEach(c => {
    let g = groups.find(x => x.name === c.group);
    if (!g) {
      g = {
        name: c.group,
        items: []
      };
      groups.push(g);
    }
    g.items.push(c);
  });
  return /*#__PURE__*/React.createElement("div", {
    style: {
      background: "var(--surface-card)",
      border: "1px solid var(--border-coral)",
      borderRadius: "var(--radius-lg)",
      padding: 12,
      display: "flex",
      flexDirection: "column",
      gap: 10
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      display: "flex",
      alignItems: "center",
      justifyContent: "space-between"
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      display: "flex",
      alignItems: "center",
      gap: 7
    }
  }, /*#__PURE__*/React.createElement(Icon, {
    name: "stethoscope",
    size: 15,
    color: "var(--primary)"
  }), /*#__PURE__*/React.createElement("span", {
    style: {
      fontSize: "var(--text-xs)",
      fontWeight: 700
    }
  }, "\u5C0F\u7EA2\u4E66\u6587\u6848\u4F53\u68C0"), /*#__PURE__*/React.createElement("span", {
    style: {
      fontSize: 10,
      color: "var(--text-subtle)"
    }
  }, "\xB7 ", checks.length, " \u9879\u89C4\u5219")), /*#__PURE__*/React.createElement("span", {
    style: {
      fontFamily: "var(--font-display)",
      fontWeight: 800,
      fontSize: "var(--text-lg)",
      color: score >= 80 ? "var(--success)" : score >= 60 ? "var(--warning)" : "var(--text-muted)"
    }
  }, score, /*#__PURE__*/React.createElement("span", {
    style: {
      fontSize: 11,
      color: "var(--text-subtle)",
      fontWeight: 400
    }
  }, " \u5206"))), /*#__PURE__*/React.createElement("div", {
    className: "cs",
    style: {
      display: "flex",
      flexDirection: "column",
      gap: 9,
      maxHeight: 240,
      overflowY: "auto"
    }
  }, groups.map(g => {
    const ok = g.items.filter(i => i.pass).length;
    return /*#__PURE__*/React.createElement("div", {
      key: g.name,
      style: {
        display: "flex",
        flexDirection: "column",
        gap: 5
      }
    }, /*#__PURE__*/React.createElement("div", {
      style: {
        display: "flex",
        alignItems: "center",
        justifyContent: "space-between"
      }
    }, /*#__PURE__*/React.createElement(Eyebrow, null, g.name), /*#__PURE__*/React.createElement("span", {
      style: {
        fontSize: 9,
        color: ok === g.items.length ? "var(--success)" : "var(--text-subtle)",
        fontWeight: 600
      }
    }, ok, "/", g.items.length)), /*#__PURE__*/React.createElement("div", {
      style: {
        display: "grid",
        gridTemplateColumns: "1fr 1fr",
        gap: 6
      }
    }, g.items.map(c => /*#__PURE__*/React.createElement("div", {
      key: c.key,
      title: c.hint,
      style: {
        display: "flex",
        alignItems: "center",
        gap: 6,
        fontSize: 11,
        padding: "5px 8px",
        borderRadius: "var(--radius-sm)",
        background: c.pass ? "var(--success-surface)" : "var(--warning-surface)",
        transition: "background var(--dur-base) var(--ease-out)"
      }
    }, /*#__PURE__*/React.createElement(Icon, {
      name: c.pass ? "check-circle-2" : "alert-circle",
      size: 13,
      color: c.pass ? "var(--success)" : "var(--warning)"
    }), /*#__PURE__*/React.createElement("span", {
      style: {
        color: "var(--text-body)",
        fontWeight: 500,
        whiteSpace: "nowrap"
      }
    }, c.label), /*#__PURE__*/React.createElement("span", {
      style: {
        marginLeft: "auto",
        color: "var(--text-subtle)",
        fontSize: 10,
        whiteSpace: "nowrap",
        overflow: "hidden",
        textOverflow: "ellipsis",
        maxWidth: 66
      }
    }, c.value)))));
  })), /*#__PURE__*/React.createElement("button", {
    onClick: () => store?.actions?.toast?.("规则库可持续扩展：在 data.js 的 checkRules 里增删规则即可（已内置 12 项）"),
    style: {
      alignSelf: "flex-start",
      display: "inline-flex",
      alignItems: "center",
      gap: 5,
      background: "none",
      border: "none",
      cursor: "pointer",
      color: "var(--primary)",
      fontSize: 10,
      fontWeight: 600,
      padding: 0
    }
  }, /*#__PURE__*/React.createElement(Icon, {
    name: "settings-2",
    size: 12
  }), " \u7BA1\u7406\u4F53\u68C0\u89C4\u5219\u5E93"));
}

// 定稿 → 排期 bar
function ScheduleBar({
  score,
  status
}) {
  const {
    Button,
    Badge
  } = window.DesignSystem_71831b;
  const {
    actions
  } = useStudio();
  const [picking, setPicking] = React.useState(false);
  const ready = score >= 80;
  const scheduled = status === "scheduled";
  return /*#__PURE__*/React.createElement("div", {
    style: {
      borderTop: "1px solid var(--border)",
      paddingTop: 12,
      display: "flex",
      flexDirection: "column",
      gap: 8,
      position: "sticky",
      bottom: 0,
      background: "var(--surface-card)"
    }
  }, scheduled ? /*#__PURE__*/React.createElement("div", {
    style: {
      display: "flex",
      alignItems: "center",
      justifyContent: "space-between"
    }
  }, /*#__PURE__*/React.createElement(Badge, {
    tone: "synced",
    dot: true
  }, "\u5DF2\u5B9A\u7A3F\u5E76\u6392\u671F"), /*#__PURE__*/React.createElement(Button, {
    variant: "ghost",
    size: "sm",
    leftIcon: /*#__PURE__*/React.createElement(Icon, {
      name: "line-chart",
      size: 13
    }),
    onClick: () => actions.setSection("ops")
  }, "\u53BB\u8FD0\u8425\u770B\u6392\u671F")) : picking ? /*#__PURE__*/React.createElement("div", {
    style: {
      display: "flex",
      flexDirection: "column",
      gap: 7
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: 11,
      color: "var(--text-muted)"
    }
  }, "\u6392\u671F\u5230 ", window.STUDIO.month.label, " \u54EA\u5929\u53D1\u5E03\uFF1F"), /*#__PURE__*/React.createElement("div", {
    className: "cs",
    style: {
      display: "grid",
      gridTemplateColumns: "repeat(7, 1fr)",
      gap: 4,
      maxHeight: 140,
      overflowY: "auto"
    }
  }, Array.from({
    length: window.STUDIO.month.days
  }, (_, i) => i + 1).map(d => /*#__PURE__*/React.createElement("button", {
    key: d,
    onClick: () => {
      actions.schedule(d);
      setPicking(false);
    },
    style: {
      padding: "6px 0",
      borderRadius: "var(--radius-xs)",
      border: "1px solid var(--border)",
      background: "var(--oats-light)",
      cursor: "pointer",
      fontSize: 11,
      fontWeight: 600,
      color: "var(--text-body)"
    }
  }, d)))) : /*#__PURE__*/React.createElement("div", {
    style: {
      display: "flex",
      alignItems: "center",
      gap: 8
    }
  }, /*#__PURE__*/React.createElement("span", {
    style: {
      fontSize: 11,
      color: "var(--text-subtle)",
      flex: 1
    }
  }, ready ? "体检达标，可以定稿啦 🎉" : `体检 ${score} 分，建议 ≥80 再发`), /*#__PURE__*/React.createElement(Button, {
    variant: "secondary",
    size: "sm",
    leftIcon: /*#__PURE__*/React.createElement(Icon, {
      name: "cloud-upload",
      size: 13
    }),
    onClick: actions.syncFeishu
  }, "\u540C\u6B65\u98DE\u4E66"), /*#__PURE__*/React.createElement(Button, {
    variant: "primary",
    size: "sm",
    leftIcon: /*#__PURE__*/React.createElement(Icon, {
      name: "calendar-check",
      size: 13
    }),
    onClick: () => setPicking(true),
    disabled: !ready
  }, "\u5B9A\u7A3F\u5E76\u6392\u671F")));
}

// 封面 + 图集 · 图文工作台（小红书第一要素是图：封面权重 > 正文）
function VisualStudio() {
  const {
    Button
  } = window.DesignSystem_71831b;
  const {
    note,
    actions
  } = useStudio();
  const S = window.STUDIO;
  return /*#__PURE__*/React.createElement("div", {
    style: {
      display: "flex",
      flexDirection: "column",
      gap: 8
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      display: "flex",
      alignItems: "center",
      justifyContent: "space-between"
    }
  }, /*#__PURE__*/React.createElement(Eyebrow, null, "\u5C01\u9762 + \u56FE\u96C6 \xB7 \u56FE\u6587\u5DE5\u4F5C\u53F0"), /*#__PURE__*/React.createElement("span", {
    style: {
      fontSize: 9,
      color: "var(--text-subtle)"
    }
  }, "\u5C01\u9762\u51B3\u5B9A\u70B9\u51FB\u7387")), /*#__PURE__*/React.createElement("div", {
    className: "cs",
    style: {
      display: "flex",
      gap: 8,
      overflowX: "auto",
      paddingBottom: 2
    }
  }, S.imageRoles.map((role, i) => {
    const isCover = i === 0;
    return /*#__PURE__*/React.createElement("div", {
      key: role,
      style: {
        width: 80,
        flexShrink: 0,
        display: "flex",
        flexDirection: "column",
        gap: 4
      }
    }, /*#__PURE__*/React.createElement("div", {
      style: {
        position: "relative",
        width: 80,
        height: 107,
        borderRadius: "var(--radius-md)",
        overflow: "hidden",
        border: isCover ? "2px solid var(--primary)" : "1px solid var(--border)"
      }
    }, /*#__PURE__*/React.createElement("img", {
      src: S.images[i % S.images.length],
      alt: role,
      style: {
        width: "100%",
        height: "100%",
        objectFit: "cover"
      }
    }), isCover && /*#__PURE__*/React.createElement(React.Fragment, null, /*#__PURE__*/React.createElement("div", {
      style: {
        position: "absolute",
        inset: 0,
        background: "linear-gradient(180deg,rgba(0,0,0,.05),rgba(0,0,0,.42))"
      }
    }), /*#__PURE__*/React.createElement("div", {
      style: {
        position: "absolute",
        top: 6,
        left: 6,
        right: 6,
        color: "#fff",
        fontFamily: "var(--font-display)",
        fontWeight: 800,
        fontSize: 12,
        lineHeight: 1.12,
        textShadow: "0 1px 4px rgba(0,0,0,.45)",
        whiteSpace: "pre-line"
      }
    }, note.cover), /*#__PURE__*/React.createElement("span", {
      style: {
        position: "absolute",
        bottom: 5,
        left: 5,
        fontSize: 8,
        fontWeight: 700,
        color: "var(--primary)",
        background: "#fff",
        borderRadius: 4,
        padding: "1px 4px"
      }
    }, "\u5C01\u9762"))), /*#__PURE__*/React.createElement("span", {
      style: {
        fontSize: 8,
        color: "var(--text-subtle)",
        textAlign: "center",
        lineHeight: 1.2
      }
    }, role));
  }), /*#__PURE__*/React.createElement("button", {
    onClick: () => actions.toast("🖼️ AI 配图建议生成中（示意）"),
    style: {
      width: 80,
      height: 107,
      flexShrink: 0,
      borderRadius: "var(--radius-md)",
      border: "1px dashed var(--border-strong)",
      background: "var(--oats-light)",
      display: "flex",
      flexDirection: "column",
      alignItems: "center",
      justifyContent: "center",
      gap: 4,
      cursor: "pointer",
      color: "var(--text-subtle)"
    }
  }, /*#__PURE__*/React.createElement(Icon, {
    name: "image-plus",
    size: 16
  }), /*#__PURE__*/React.createElement("span", {
    style: {
      fontSize: 8
    }
  }, "AI \u51FA\u56FE"))), /*#__PURE__*/React.createElement("div", {
    style: {
      display: "flex",
      gap: 6
    }
  }, /*#__PURE__*/React.createElement(Button, {
    variant: "secondary",
    size: "sm",
    leftIcon: /*#__PURE__*/React.createElement(Icon, {
      name: "wand-2",
      size: 13
    }),
    onClick: () => actions.updateField("cover", note.versions ? note.versions[note.activeVersion].cover : note.cover || "爆点\n大字")
  }, "\u6362\u5C01\u9762\u6587\u6848"), /*#__PURE__*/React.createElement(Button, {
    variant: "ghost",
    size: "sm",
    leftIcon: /*#__PURE__*/React.createElement(Icon, {
      name: "layout-template",
      size: 13
    }),
    onClick: () => actions.toast("🎨 已套用爆款版式（示意）")
  }, "\u5957\u7248\u5F0F")));
}

// 原创度 + 限流风控
function RiskPanel({
  note
}) {
  const text = (note.title || "") + (note.body || "");
  const polished = (note.body || "").startsWith("⛺ 夏日露营天花板");
  const originality = note.topicId ? polished ? 88 : 72 : 90;
  const risks = [{
    label: "导流/外链",
    bad: /http|www\.|公众号|微信|加我|私信|vx|v信|留链|主页链接/i.test(text),
    hint: "小红书限制站外导流"
  }, {
    label: "极限词",
    bad: /最佳|最好|第一名|国家级|绝对|100%|顶级|纯天然|永久/.test(text),
    hint: "广告法违禁词"
  }, {
    label: "敏感品类",
    bad: /医美|减肥|瘦身|药效|代购|烟|酒精/.test(text),
    hint: "需报备 / 可能限流"
  }];
  const riskCount = risks.filter(r => r.bad).length;
  return /*#__PURE__*/React.createElement("div", {
    style: {
      background: "var(--surface-card)",
      border: "1px solid var(--border-coral)",
      borderRadius: "var(--radius-lg)",
      padding: 12,
      display: "flex",
      flexDirection: "column",
      gap: 10
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      display: "flex",
      alignItems: "center",
      justifyContent: "space-between"
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      display: "flex",
      alignItems: "center",
      gap: 7
    }
  }, /*#__PURE__*/React.createElement(Icon, {
    name: "shield-check",
    size: 15,
    color: "var(--primary)"
  }), /*#__PURE__*/React.createElement("span", {
    style: {
      fontSize: "var(--text-xs)",
      fontWeight: 700
    }
  }, "\u539F\u521B\u5EA6 \xB7 \u9650\u6D41\u98CE\u63A7")), /*#__PURE__*/React.createElement("span", {
    style: {
      fontSize: 10,
      color: riskCount ? "var(--warning)" : "var(--success)",
      fontWeight: 600
    }
  }, riskCount ? `${riskCount} 项风险` : "无明显风险")), /*#__PURE__*/React.createElement("div", {
    style: {
      display: "flex",
      flexDirection: "column",
      gap: 5
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      display: "flex",
      justifyContent: "space-between",
      fontSize: 10,
      color: "var(--text-muted)"
    }
  }, /*#__PURE__*/React.createElement("span", null, "\u539F\u521B\u5EA6\uFF08vs \u68C0\u7D22\u5230\u7684\u7206\u6B3E\uFF09"), /*#__PURE__*/React.createElement("span", {
    className: "font-tabular",
    style: {
      fontWeight: 700,
      color: originality >= 80 ? "var(--success)" : "var(--warning)"
    }
  }, originality, "%")), /*#__PURE__*/React.createElement("div", {
    style: {
      height: 6,
      background: "var(--oats-dark)",
      borderRadius: 999,
      overflow: "hidden"
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      height: "100%",
      width: `${originality}%`,
      background: originality >= 80 ? "var(--success)" : "var(--warning)",
      transition: "width var(--dur-slow) var(--ease-out)"
    }
  })), originality < 80 && /*#__PURE__*/React.createElement("span", {
    style: {
      fontSize: 9,
      color: "var(--warning)",
      lineHeight: 1.5
    }
  }, "\u26A0\uFE0F \u4E0E\u7206\u6B3E\u7ED3\u6784\u76F8\u4F3C\u5EA6\u504F\u9AD8\uFF0C\u5EFA\u8BAE\u70B9\u300C\u6DA6\u8272\u300D\u6539\u5199\u63D0\u5347\u539F\u521B\u5EA6\uFF0C\u89C4\u907F\u67E5\u91CD\u9650\u6D41")), /*#__PURE__*/React.createElement("div", {
    style: {
      display: "grid",
      gridTemplateColumns: "1fr 1fr 1fr",
      gap: 6
    }
  }, risks.map(r => /*#__PURE__*/React.createElement("div", {
    key: r.label,
    title: r.hint,
    style: {
      display: "flex",
      alignItems: "center",
      gap: 5,
      fontSize: 10,
      padding: "5px 7px",
      borderRadius: "var(--radius-sm)",
      background: r.bad ? "var(--warning-surface)" : "var(--success-surface)"
    }
  }, /*#__PURE__*/React.createElement(Icon, {
    name: r.bad ? "alert-triangle" : "check-circle-2",
    size: 12,
    color: r.bad ? "var(--warning)" : "var(--success)"
  }), /*#__PURE__*/React.createElement("span", {
    style: {
      fontWeight: 500
    }
  }, r.label)))));
}
Object.assign(window, {
  Composer,
  CopyDoctor,
  RiskPanel,
  ScheduleBar
});
})(); } catch (e) { __ds_ns.__errors.push({ path: "ui_kits/studio/Composer.jsx", error: String((e && e.message) || e) }); }

// ui_kits/studio/CreationScreen.jsx
try { (() => {
// 创作 screen — recents · chat · right panel (选题卡 + 创作栏).
// rightLayout: "stack" | "split" | "composer"
function CreationScreen() {
  const {
    note,
    activeRecent,
    setActiveRecent,
    actions
  } = useStudio();
  const [detailId, setDetailId] = React.useState(null);
  return /*#__PURE__*/React.createElement("div", {
    style: {
      flex: 1,
      display: "flex",
      minHeight: 0
    }
  }, /*#__PURE__*/React.createElement(Recents, {
    activeId: activeRecent,
    onSelect: id => {
      setActiveRecent(id);
      const r = (window.STUDIO.recents || []).find(x => x.id === id);
      if (r) actions.toast(`📂 已打开《${r.title}》草稿`);
    },
    onNew: () => {
      setDetailId(null);
      actions.newChat();
    },
    compact: true
  }), /*#__PURE__*/React.createElement(ChatColumn, {
    showTopics: false
  }), /*#__PURE__*/React.createElement("section", {
    style: {
      width: 400,
      borderLeft: "1px solid var(--border)",
      background: "var(--surface-card)",
      display: "flex",
      flexDirection: "column",
      flexShrink: 0,
      boxShadow: "var(--shadow-lg)"
    }
  }, /*#__PURE__*/React.createElement("div", {
    className: "cs",
    style: {
      flex: 1,
      overflowY: "auto",
      padding: 16
    }
  }, detailId ? /*#__PURE__*/React.createElement(TopicDetail, {
    topicId: detailId,
    onBack: () => setDetailId(null)
  }) : /*#__PURE__*/React.createElement("div", {
    style: {
      display: "flex",
      flexDirection: "column",
      gap: 12
    }
  }, /*#__PURE__*/React.createElement(TopicRail, {
    orientation: "vertical",
    chosen: note.topicId,
    onChoose: t => setDetailId(t.id)
  }), /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: 11,
      color: "var(--text-subtle)",
      textAlign: "center",
      lineHeight: 1.6,
      padding: "6px 8px",
      background: "var(--oats-light)",
      borderRadius: "var(--radius-sm)"
    }
  }, "\u70B9\u9009\u9898\u5361\u770B\u8BE6\u60C5 \u2192 \u518D\u8FDB\u5165", /*#__PURE__*/React.createElement("b", {
    style: {
      color: "var(--primary)"
    }
  }, "\u6DF1\u5EA6\u521B\u4F5C"))))));
}

// 选题卡 rail
function TopicRail({
  orientation,
  chosen,
  onChoose
}) {
  const {
    Button
  } = window.DesignSystem_71831b;
  const {
    actions
  } = useStudio();
  const S = window.STUDIO;
  const horizontal = orientation === "horizontal";
  return /*#__PURE__*/React.createElement("div", {
    style: {
      display: "flex",
      flexDirection: "column",
      gap: 9
    }
  }, /*#__PURE__*/React.createElement(PanelHead, {
    icon: "lightbulb",
    title: "\u9009\u9898\u5361",
    sub: "\u6570\u636E\u5E95\u5EA7\u68C0\u7D22 \xB7 \u52A0\u6743\u6392\u5E8F \xB7 \u70B9\u51FB\u8FDB\u5165\u521B\u4F5C",
    right: /*#__PURE__*/React.createElement(Button, {
      variant: "ghost",
      size: "sm",
      leftIcon: /*#__PURE__*/React.createElement(Icon, {
        name: "refresh-cw",
        size: 12
      }),
      onClick: () => actions.toast("🔄 已基于数据底座重新检索一批选题")
    }, "\u6362\u4E00\u6279")
  }), /*#__PURE__*/React.createElement("div", {
    style: {
      display: "grid",
      gridTemplateColumns: "1fr 1fr",
      gap: 10
    }
  }, S.topics.map(t => {
    const on = t.id === chosen;
    const evCount = (window.STUDIO.evidence[t.id] || {
      items: []
    }).items.length;
    return /*#__PURE__*/React.createElement("div", {
      key: t.id,
      onClick: () => onChoose(t),
      className: "lift pop-in",
      style: {
        borderRadius: "var(--radius-md)",
        overflow: "hidden",
        cursor: "pointer",
        border: `1px solid ${on ? "var(--primary)" : "var(--border)"}`,
        background: "var(--surface-card)",
        boxShadow: on ? "var(--shadow-md)" : "var(--shadow-xs)",
        display: "flex",
        flexDirection: "column"
      }
    }, /*#__PURE__*/React.createElement("div", {
      style: {
        position: "relative",
        width: "100%",
        aspectRatio: "3 / 4",
        overflow: "hidden",
        background: "var(--accent-surface)"
      }
    }, /*#__PURE__*/React.createElement("img", {
      src: S.images[(t.id - 1) % S.images.length],
      alt: t.title,
      style: {
        width: "100%",
        height: "100%",
        objectFit: "cover"
      }
    }), /*#__PURE__*/React.createElement("div", {
      style: {
        position: "absolute",
        inset: 0,
        background: "linear-gradient(180deg, rgba(0,0,0,0) 58%, rgba(0,0,0,0.42))"
      }
    }), /*#__PURE__*/React.createElement("span", {
      style: {
        position: "absolute",
        top: 7,
        left: 7,
        fontSize: 8,
        fontWeight: 700,
        color: "#fff",
        background: "rgba(0,0,0,0.36)",
        padding: "2px 7px",
        borderRadius: 999
      }
    }, t.angle), /*#__PURE__*/React.createElement("span", {
      style: {
        position: "absolute",
        top: 7,
        right: 7,
        fontSize: 9,
        fontWeight: 800,
        color: "#fff",
        background: "var(--coral-500)",
        padding: "2px 6px",
        borderRadius: 999
      }
    }, "\uD83D\uDD25", t.hotRate), on && /*#__PURE__*/React.createElement("span", {
      style: {
        position: "absolute",
        bottom: 7,
        right: 7,
        display: "inline-flex",
        alignItems: "center",
        gap: 2,
        fontSize: 8,
        fontWeight: 700,
        color: "var(--primary)",
        background: "#fff",
        padding: "2px 6px",
        borderRadius: 999
      }
    }, /*#__PURE__*/React.createElement(Icon, {
      name: "check",
      size: 9
    }), " \u5DF2\u9009")), /*#__PURE__*/React.createElement("div", {
      style: {
        padding: "8px 9px",
        display: "flex",
        flexDirection: "column",
        gap: 5
      }
    }, /*#__PURE__*/React.createElement("div", {
      style: {
        fontSize: 11,
        fontWeight: 700,
        color: "var(--text-body)",
        lineHeight: 1.35,
        display: "-webkit-box",
        WebkitLineClamp: 2,
        WebkitBoxOrient: "vertical",
        overflow: "hidden"
      }
    }, t.title), /*#__PURE__*/React.createElement("div", {
      style: {
        display: "flex",
        alignItems: "center",
        justifyContent: "space-between",
        fontSize: 9,
        color: "var(--text-subtle)"
      }
    }, /*#__PURE__*/React.createElement("span", null, t.rationale.split(" · ")[0]), /*#__PURE__*/React.createElement("span", {
      style: {
        display: "inline-flex",
        alignItems: "center",
        gap: 3
      }
    }, /*#__PURE__*/React.createElement(Icon, {
      name: "database",
      size: 9
    }), " \u4F9D\u636E ", evCount))));
  })));
}

// Center chat column — base proposal + dynamic store messages
function ChatColumn({
  showTopics
}) {
  const {
    Avatar,
    Card,
    Textarea,
    Button,
    ThinkingAura,
    TopicCard
  } = window.DesignSystem_71831b;
  const {
    chatExtra,
    actions
  } = useStudio();
  const [draft, setDraft] = React.useState("");
  const S = window.STUDIO;
  const scrollRef = React.useRef(null);
  React.useEffect(() => {
    const el = scrollRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [chatExtra]);
  return /*#__PURE__*/React.createElement("section", {
    style: {
      flex: 1,
      display: "flex",
      flexDirection: "column",
      background: "var(--background)",
      minWidth: 0
    }
  }, /*#__PURE__*/React.createElement("div", {
    ref: scrollRef,
    className: "cs",
    style: {
      flex: 1,
      overflowY: "auto",
      padding: 22,
      display: "flex",
      flexDirection: "column",
      gap: 18
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      display: "flex",
      gap: 11,
      maxWidth: "86%",
      alignSelf: "flex-end",
      flexDirection: "row-reverse"
    }
  }, /*#__PURE__*/React.createElement(Avatar, {
    name: "\u6211",
    variant: "solid",
    size: 30
  }), /*#__PURE__*/React.createElement("div", {
    style: {
      background: "var(--surface-card)",
      border: "1px solid var(--border-coral)",
      borderRadius: "var(--radius-xl)",
      padding: "11px 15px",
      fontSize: "var(--text-sm)",
      lineHeight: "var(--leading-relaxed)",
      boxShadow: "var(--shadow-sm)"
    }
  }, "\u5E2E\u6211\u6309\u9732\u8425\u88C5\u5907\u65B9\u5411\u51FA\u9009\u9898\uFF0C\u5E76\u7B5B\u9009\u98DE\u4E66\u91CC\u9AD8\u8D5E\u7684\u7206\u6B3E\u3002")), /*#__PURE__*/React.createElement("div", {
    style: {
      display: "flex",
      gap: 11,
      maxWidth: "92%"
    }
  }, /*#__PURE__*/React.createElement(Avatar, {
    glyph: "\uD83C\uDF60",
    variant: "agent",
    size: 32
  }), /*#__PURE__*/React.createElement("div", {
    style: {
      display: "flex",
      flexDirection: "column",
      gap: 10,
      minWidth: 0,
      flex: 1
    }
  }, /*#__PURE__*/React.createElement(ThinkingAura, {
    steps: [{
      label: "数据底座语义检索：命中 12 条相关资源 (pgvector)",
      state: "done"
    }, {
      label: "图谱扩展 + rank_evidence 加权排序（相关度·时效·表现）",
      state: "done"
    }, {
      label: "飞书 Bitable / Wiki 已接入并沉淀入库",
      state: "done"
    }]
  }), /*#__PURE__*/React.createElement(Card, {
    padding: "md"
  }, /*#__PURE__*/React.createElement("p", {
    style: {
      margin: 0,
      fontSize: "var(--text-sm)",
      lineHeight: "var(--leading-relaxed)"
    }
  }, "\u57FA\u4E8E\u6570\u636E\u5E95\u5EA7\u68C0\u7D22\u5230\u7684\u7206\u6B3E\u8D44\u6E90\uFF0C\u63D0\u70BC 3 \u4E2A\u65B9\u5411\uFF0C\u6BCF\u4E2A\u90FD\u9644\u300C\u521B\u4F5C\u4F9D\u636E\u300D", showTopics ? "，点击卡片进入创作：" : "，已放到右侧「选题卡」，点任意一张进入创作 👉"), showTopics && /*#__PURE__*/React.createElement("div", {
    style: {
      display: "flex",
      flexDirection: "column",
      gap: 9,
      marginTop: 11
    }
  }, S.topics.map(t => /*#__PURE__*/React.createElement(TopicCard, {
    key: t.id,
    index: t.id,
    title: t.title,
    rationale: t.rationale,
    hotRate: t.hotRate,
    onClick: () => actions.chooseTopic(t)
  })))))), /*#__PURE__*/React.createElement("div", {
    style: {
      display: "flex",
      gap: 11,
      maxWidth: "92%"
    }
  }, /*#__PURE__*/React.createElement(Avatar, {
    glyph: "\uD83C\uDF60",
    variant: "agent",
    size: 32
  }), /*#__PURE__*/React.createElement("div", {
    style: {
      flex: 1,
      minWidth: 0
    }
  }, /*#__PURE__*/React.createElement(TrendRadar, null))), chatExtra.map((m, i) => m.who === "user" ? /*#__PURE__*/React.createElement("div", {
    key: i,
    style: {
      display: "flex",
      gap: 11,
      maxWidth: "86%",
      alignSelf: "flex-end",
      flexDirection: "row-reverse"
    }
  }, /*#__PURE__*/React.createElement(Avatar, {
    name: "\u6211",
    variant: "solid",
    size: 30
  }), /*#__PURE__*/React.createElement("div", {
    style: {
      background: "var(--surface-card)",
      border: "1px solid var(--border-coral)",
      borderRadius: "var(--radius-xl)",
      padding: "11px 15px",
      fontSize: "var(--text-sm)",
      boxShadow: "var(--shadow-sm)"
    }
  }, m.text)) : /*#__PURE__*/React.createElement("div", {
    key: i,
    style: {
      display: "flex",
      gap: 11,
      maxWidth: "92%"
    }
  }, /*#__PURE__*/React.createElement(Avatar, {
    glyph: "\uD83C\uDF60",
    variant: "agent",
    size: 32
  }), m.thinking ? /*#__PURE__*/React.createElement("div", {
    style: {
      flex: 1,
      maxWidth: 440
    }
  }, /*#__PURE__*/React.createElement(ThinkingAura, {
    steps: [{
      label: m.text,
      state: "active"
    }]
  })) : /*#__PURE__*/React.createElement("div", {
    style: {
      background: "var(--surface-card)",
      border: "1px solid var(--border-coral)",
      borderRadius: "var(--radius-xl)",
      padding: "11px 15px",
      fontSize: "var(--text-sm)",
      lineHeight: "var(--leading-relaxed)",
      boxShadow: "var(--shadow-sm)",
      alignSelf: "flex-start"
    }
  }, m.text)))), /*#__PURE__*/React.createElement("div", {
    style: {
      padding: 18,
      borderTop: "1px solid var(--border)",
      flexShrink: 0
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      maxWidth: 720,
      margin: "0 auto"
    }
  }, /*#__PURE__*/React.createElement(Textarea, {
    rows: 2,
    value: draft,
    onChange: e => setDraft(e.target.value),
    placeholder: "\u7EE7\u7EED\u8FFD\u95EE\uFF0C\u6216\u8BA9 \uD83C\uDF60 \u8C03\u6574\u9009\u9898\u65B9\u5411 / \u6539\u5199\u6587\u6848\u2026",
    footer: /*#__PURE__*/React.createElement(React.Fragment, null, /*#__PURE__*/React.createElement("button", {
      onClick: () => actions.toast("⌨️ 润色工具箱（Ctrl+P）— 示意"),
      style: {
        display: "inline-flex",
        alignItems: "center",
        gap: 6,
        background: "var(--surface-card)",
        border: "1px solid var(--border)",
        borderRadius: "var(--radius-sm)",
        padding: "5px 9px",
        cursor: "pointer"
      }
    }, /*#__PURE__*/React.createElement("kbd", {
      style: {
        fontSize: 8,
        background: "var(--oats-light)",
        border: "1px solid var(--border)",
        padding: "1px 4px",
        borderRadius: 4,
        fontFamily: "var(--font-mono)"
      }
    }, "Ctrl+P"), /*#__PURE__*/React.createElement("span", {
      style: {
        fontSize: "var(--text-xs)",
        color: "var(--text-muted)"
      }
    }, "\u6DA6\u8272\u5DE5\u5177\u7BB1")), /*#__PURE__*/React.createElement(Button, {
      variant: "primary",
      size: "sm",
      rightIcon: /*#__PURE__*/React.createElement(Icon, {
        name: "send",
        size: 14
      }),
      onClick: () => {
        if (draft.trim()) {
          actions.say(draft);
          setDraft("");
        }
      }
    }, "\u751F\u6210"))
  }))));
}

// 选题卡上的「创作依据」chips → 打开依据相关度分析
function EvidenceChips({
  topicId
}) {
  const {
    actions
  } = useStudio();
  const ev = (window.STUDIO.evidence || {})[topicId];
  if (!ev) return null;
  return /*#__PURE__*/React.createElement("div", {
    style: {
      display: "flex",
      alignItems: "center",
      gap: 5,
      flexWrap: "wrap",
      paddingTop: 2
    }
  }, /*#__PURE__*/React.createElement("span", {
    style: {
      display: "inline-flex",
      alignItems: "center",
      gap: 3,
      fontSize: 9,
      color: "var(--text-subtle)"
    }
  }, /*#__PURE__*/React.createElement(Icon, {
    name: "database",
    size: 10
  }), " \u4F9D\u636E ", ev.items.length, " \u6761"), ev.items.map(it => /*#__PURE__*/React.createElement("button", {
    key: it.resource_id,
    onClick: e => {
      e.stopPropagation();
      actions.openEvidence({
        ...it,
        mode: ev.mode
      });
    },
    title: it.title,
    style: {
      display: "inline-flex",
      alignItems: "center",
      gap: 3,
      fontSize: 9,
      color: "var(--topicblue-default)",
      background: "var(--topicblue-light)",
      border: "1px solid color-mix(in srgb, var(--topicblue-default) 20%, transparent)",
      borderRadius: 999,
      padding: "1px 6px",
      cursor: "pointer"
    }
  }, it.type)), ev.mode === "keyword_fallback" && /*#__PURE__*/React.createElement("span", {
    style: {
      fontSize: 9,
      color: "var(--warning)"
    }
  }, "\xB7 \u5173\u952E\u8BCD\u515C\u5E95"));
}

// 依据相关度分析 — slide-over，对齐 EvidenceInspector（relevance/freshness/performance + 时效跟踪）
function EvidencePanel() {
  const {
    Badge
  } = window.DesignSystem_71831b;
  const {
    selectedEvidence: e,
    actions
  } = useStudio();
  if (!e) return null;
  const modeLabel = {
    semantic: "语义检索 (pgvector)",
    keyword_fallback: "关键词兜底 (Meilisearch)",
    insufficient_relevance: "数据不足"
  }[e.mode] || "检索";
  const card = {
    background: "var(--surface-card)",
    border: "1px solid var(--border)",
    borderRadius: "var(--radius-md)",
    padding: 12,
    boxShadow: "var(--shadow-xs)"
  };
  const Bar = ({
    label,
    val,
    color
  }) => /*#__PURE__*/React.createElement("div", {
    style: {
      display: "flex",
      flexDirection: "column",
      gap: 5
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      display: "flex",
      justifyContent: "space-between",
      fontSize: 10,
      color: "var(--text-muted)"
    }
  }, /*#__PURE__*/React.createElement("span", null, label), /*#__PURE__*/React.createElement("span", {
    className: "font-tabular",
    style: {
      fontWeight: 600,
      color: "var(--text-body)"
    }
  }, (val * 100).toFixed(1), "%")), /*#__PURE__*/React.createElement("div", {
    style: {
      height: 6,
      background: "var(--oats-dark)",
      borderRadius: 999,
      overflow: "hidden"
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      height: "100%",
      width: `${val * 100}%`,
      background: color,
      transition: "width var(--dur-slow) var(--ease-out)"
    }
  })));
  return /*#__PURE__*/React.createElement("div", {
    onClick: actions.closeEvidence,
    style: {
      position: "fixed",
      inset: 0,
      background: "rgba(15,15,16,0.35)",
      zIndex: 55,
      display: "flex",
      justifyContent: "flex-end"
    }
  }, /*#__PURE__*/React.createElement("div", {
    onClick: ev => ev.stopPropagation(),
    className: "cs slide-in-right",
    style: {
      width: 380,
      maxWidth: "92vw",
      height: "100%",
      background: "var(--background)",
      boxShadow: "var(--shadow-2xl)",
      overflowY: "auto"
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      position: "sticky",
      top: 0,
      background: "var(--surface-card)",
      borderBottom: "1px solid var(--border)",
      padding: "14px 16px",
      display: "flex",
      alignItems: "center",
      justifyContent: "space-between",
      zIndex: 1
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      display: "flex",
      alignItems: "center",
      gap: 7
    }
  }, /*#__PURE__*/React.createElement(Icon, {
    name: "database",
    size: 16,
    color: "var(--primary)"
  }), /*#__PURE__*/React.createElement("span", {
    style: {
      fontSize: "var(--text-sm)",
      fontWeight: 700
    }
  }, "\u4F9D\u636E\u76F8\u5173\u5EA6\u5206\u6790")), /*#__PURE__*/React.createElement("button", {
    onClick: actions.closeEvidence,
    style: {
      border: "none",
      background: "none",
      cursor: "pointer",
      color: "var(--text-subtle)",
      display: "inline-flex"
    }
  }, /*#__PURE__*/React.createElement(Icon, {
    name: "x",
    size: 16
  }))), /*#__PURE__*/React.createElement("div", {
    style: {
      padding: 16,
      display: "flex",
      flexDirection: "column",
      gap: 14
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: card
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      display: "flex",
      alignItems: "center",
      gap: 6
    }
  }, /*#__PURE__*/React.createElement(Icon, {
    name: "file-text",
    size: 13,
    color: "var(--primary)"
  }), /*#__PURE__*/React.createElement("span", {
    style: {
      fontSize: "var(--text-xs)",
      fontWeight: 700
    }
  }, e.title)), /*#__PURE__*/React.createElement("p", {
    style: {
      fontSize: 10,
      color: "var(--text-muted)",
      lineHeight: 1.6,
      margin: "6px 0 0"
    }
  }, e.summary), /*#__PURE__*/React.createElement("div", {
    style: {
      display: "flex",
      gap: 6,
      marginTop: 9,
      alignItems: "center"
    }
  }, /*#__PURE__*/React.createElement(Badge, {
    tone: "topic",
    shape: "chip"
  }, e.type), /*#__PURE__*/React.createElement(Badge, {
    tone: e.mode === "keyword_fallback" ? "neutral" : "synced",
    shape: "chip"
  }, modeLabel), /*#__PURE__*/React.createElement("span", {
    style: {
      fontSize: 9,
      fontFamily: "var(--font-mono)",
      color: "var(--text-subtle)",
      marginLeft: "auto"
    }
  }, e.resource_id))), /*#__PURE__*/React.createElement("div", {
    style: {
      background: "var(--accent-surface)",
      border: "1px solid var(--border-coral)",
      borderRadius: "var(--radius-md)",
      padding: 12
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      display: "flex",
      alignItems: "center",
      gap: 5,
      fontSize: 10,
      fontWeight: 700,
      color: "var(--primary)"
    }
  }, /*#__PURE__*/React.createElement(Icon, {
    name: "sparkles",
    size: 12
  }), " \u63A8\u8350\u7406\u7531 why_selected"), /*#__PURE__*/React.createElement("p", {
    style: {
      fontSize: 10,
      color: "var(--text-body)",
      lineHeight: 1.6,
      margin: "5px 0 0"
    }
  }, e.why_selected)), /*#__PURE__*/React.createElement("div", {
    style: card
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      display: "flex",
      justifyContent: "space-between",
      alignItems: "center",
      borderBottom: "1px solid var(--border)",
      paddingBottom: 8,
      marginBottom: 12
    }
  }, /*#__PURE__*/React.createElement("span", {
    style: {
      fontSize: "var(--text-xs)",
      fontWeight: 700
    }
  }, "\u7EFC\u5408\u6392\u5E8F\u5F97\u5206"), /*#__PURE__*/React.createElement("span", {
    className: "font-tabular",
    style: {
      fontFamily: "var(--font-display)",
      fontWeight: 800,
      color: "var(--primary)",
      fontSize: "var(--text-base)"
    }
  }, e.score.toFixed(4))), /*#__PURE__*/React.createElement("div", {
    style: {
      display: "flex",
      flexDirection: "column",
      gap: 12
    }
  }, /*#__PURE__*/React.createElement(Bar, {
    label: "\u76F8\u5173\u5EA6 Relevance",
    val: e.relevance,
    color: "var(--primary)"
  }), /*#__PURE__*/React.createElement(Bar, {
    label: "\u65F6\u6548\u6027 Freshness \xB7 e\u207B\u2070\xB7\u2070\u2075\u1D57",
    val: e.freshness,
    color: "var(--success)"
  }), /*#__PURE__*/React.createElement(Bar, {
    label: "\u7206\u6B3E\u8868\u73B0 Engagement \xB7 tanh",
    val: e.performance,
    color: "var(--amber-500)"
  }))), /*#__PURE__*/React.createElement("div", {
    style: {
      ...card,
      fontSize: 10
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      display: "flex",
      alignItems: "center",
      gap: 5,
      fontWeight: 700,
      color: "var(--text-muted)",
      borderBottom: "1px solid var(--border)",
      paddingBottom: 6,
      marginBottom: 6
    }
  }, /*#__PURE__*/React.createElement(Icon, {
    name: "history",
    size: 12
  }), " \u65F6\u6548\u8DDF\u8E2A"), /*#__PURE__*/React.createElement("div", {
    style: {
      display: "flex",
      justifyContent: "space-between",
      padding: "2px 0"
    }
  }, /*#__PURE__*/React.createElement("span", {
    style: {
      color: "var(--text-subtle)"
    }
  }, "\u6E90\u7AEF\u66F4\u65B0 source_updated_at"), /*#__PURE__*/React.createElement("span", {
    className: "font-tabular",
    style: {
      fontWeight: 600
    }
  }, e.source_updated_at)), /*#__PURE__*/React.createElement("div", {
    style: {
      display: "flex",
      justifyContent: "space-between",
      padding: "2px 0"
    }
  }, /*#__PURE__*/React.createElement("span", {
    style: {
      color: "var(--text-subtle)"
    }
  }, "\u672C\u5730\u7D22\u5F15 indexed_at"), /*#__PURE__*/React.createElement("span", {
    className: "font-tabular",
    style: {
      fontWeight: 600
    }
  }, e.indexed_at))))));
}

// 热点趋势雷达 — 外部实时信号（区别于内部历史沉淀），驱动探索型选题
function TrendRadar() {
  const {
    actions
  } = useStudio();
  const S = window.STUDIO;
  const toneBg = {
    hot: "var(--hot-surface)",
    coral: "var(--accent-surface)",
    topic: "var(--topicblue-light)"
  };
  const toneFg = {
    hot: "var(--hot)",
    coral: "var(--primary)",
    topic: "var(--topicblue-default)"
  };
  return /*#__PURE__*/React.createElement("div", {
    style: {
      background: "var(--surface-card)",
      border: "1px solid var(--border-coral)",
      borderRadius: "var(--radius-lg)",
      padding: 12,
      display: "flex",
      flexDirection: "column",
      gap: 9,
      boxShadow: "var(--shadow-sm)"
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      display: "flex",
      alignItems: "center",
      justifyContent: "space-between"
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      display: "flex",
      alignItems: "center",
      gap: 7
    }
  }, /*#__PURE__*/React.createElement(Icon, {
    name: "radar",
    size: 15,
    color: "var(--primary)"
  }), /*#__PURE__*/React.createElement("span", {
    style: {
      fontSize: "var(--text-xs)",
      fontWeight: 700
    }
  }, "\u70ED\u70B9\u8D8B\u52BF\u96F7\u8FBE"), /*#__PURE__*/React.createElement("span", {
    style: {
      fontSize: 9,
      color: "var(--text-subtle)"
    }
  }, "\xB7 \u5E73\u53F0\u5B9E\u65F6\u4E0A\u5347")), /*#__PURE__*/React.createElement("span", {
    style: {
      fontSize: 9,
      color: "var(--text-subtle)"
    }
  }, "\u63A2\u7D22\u65B0\u9898\u6750 \xB7 \u4E0D\u53EA\u8FFD\u5386\u53F2")), /*#__PURE__*/React.createElement("div", {
    style: {
      display: "grid",
      gridTemplateColumns: "1fr 1fr",
      gap: 7
    }
  }, S.trends.map(t => /*#__PURE__*/React.createElement("button", {
    key: t.tag,
    onClick: () => actions.toast(`🛰️ 已据热点「${t.tag}」生成探索性选题（exploration）`),
    style: {
      display: "flex",
      alignItems: "center",
      gap: 8,
      padding: "7px 9px",
      borderRadius: "var(--radius-sm)",
      border: "1px solid var(--border)",
      background: "var(--oats-light)",
      cursor: "pointer",
      textAlign: "left"
    }
  }, /*#__PURE__*/React.createElement("span", {
    style: {
      fontSize: 9,
      fontWeight: 700,
      color: toneFg[t.tone],
      background: toneBg[t.tone],
      borderRadius: 6,
      padding: "2px 6px",
      flexShrink: 0
    }
  }, t.heat), /*#__PURE__*/React.createElement("span", {
    style: {
      flex: 1,
      minWidth: 0
    }
  }, /*#__PURE__*/React.createElement("span", {
    style: {
      display: "block",
      fontSize: "var(--text-xs)",
      fontWeight: 600,
      color: "var(--text-body)"
    }
  }, "#", t.tag), /*#__PURE__*/React.createElement("span", {
    style: {
      display: "block",
      fontSize: 9,
      color: "var(--text-subtle)"
    }
  }, t.note)), /*#__PURE__*/React.createElement("span", {
    style: {
      fontSize: 10,
      fontWeight: 700,
      color: "var(--success)",
      whiteSpace: "nowrap"
    }
  }, "\u2191", t.rising, "%")))));
}

// 选题选定后的收起条（钉取感：列表→详情）+ 深度创作入口
function SelectedTopicBar({
  onBrowse
}) {
  const {
    note,
    actions
  } = useStudio();
  const {
    Badge,
    Button
  } = window.DesignSystem_71831b;
  const topic = (window.STUDIO.topics || []).find(t => t.id === note.topicId);
  if (!topic) return null;
  return /*#__PURE__*/React.createElement("div", {
    style: {
      display: "flex",
      alignItems: "center",
      gap: 9,
      padding: "9px 11px",
      borderRadius: "var(--radius-md)",
      border: "1px solid var(--border-coral)",
      background: "color-mix(in srgb, var(--accent-surface) 55%, white)"
    }
  }, /*#__PURE__*/React.createElement(Badge, {
    tone: "topic",
    shape: "chip"
  }, topic.angle), /*#__PURE__*/React.createElement("span", {
    style: {
      flex: 1,
      minWidth: 0,
      fontSize: "var(--text-xs)",
      fontWeight: 700,
      color: "var(--text-body)",
      overflow: "hidden",
      textOverflow: "ellipsis",
      whiteSpace: "nowrap"
    }
  }, topic.title), /*#__PURE__*/React.createElement("span", {
    style: {
      fontSize: 10,
      fontWeight: 700,
      color: "var(--hot)",
      whiteSpace: "nowrap"
    }
  }, "\uD83D\uDD25 ", topic.hotRate, "%"), /*#__PURE__*/React.createElement("button", {
    onClick: onBrowse,
    style: {
      display: "inline-flex",
      alignItems: "center",
      gap: 4,
      border: "1px solid var(--border)",
      background: "var(--surface-card)",
      borderRadius: "var(--radius-sm)",
      padding: "4px 9px",
      cursor: "pointer",
      fontSize: 11,
      color: "var(--text-muted)",
      whiteSpace: "nowrap"
    }
  }, /*#__PURE__*/React.createElement(Icon, {
    name: "list",
    size: 12
  }), " \u6362\u9898"), /*#__PURE__*/React.createElement(Button, {
    variant: "soft",
    size: "sm",
    leftIcon: /*#__PURE__*/React.createElement(Icon, {
      name: "feather",
      size: 12
    }),
    onClick: () => actions.setSection("deep")
  }, "\u6DF1\u5EA6\u521B\u4F5C"));
}

// 选题详情 — 点选题卡先看各类信息，再进入深度创作
function TopicDetail({
  topicId,
  onBack
}) {
  const {
    Button,
    Badge
  } = window.DesignSystem_71831b;
  const {
    actions
  } = useStudio();
  const S = window.STUDIO;
  const topic = S.topics.find(t => t.id === topicId);
  const ev = (S.evidence || {})[topicId];
  if (!topic) return null;
  return /*#__PURE__*/React.createElement("div", {
    className: "fade-up",
    style: {
      display: "flex",
      flexDirection: "column",
      gap: 14
    }
  }, /*#__PURE__*/React.createElement("button", {
    onClick: onBack,
    style: {
      alignSelf: "flex-start",
      display: "inline-flex",
      alignItems: "center",
      gap: 4,
      background: "none",
      border: "none",
      cursor: "pointer",
      color: "var(--text-muted)",
      fontSize: 11
    }
  }, /*#__PURE__*/React.createElement(Icon, {
    name: "chevron-left",
    size: 13
  }), " \u8FD4\u56DE\u9009\u9898"), /*#__PURE__*/React.createElement("div", {
    style: {
      display: "flex",
      flexDirection: "column",
      gap: 8
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      display: "flex",
      alignItems: "center",
      gap: 8
    }
  }, /*#__PURE__*/React.createElement(Badge, {
    tone: "topic",
    shape: "chip"
  }, topic.angle), /*#__PURE__*/React.createElement("span", {
    style: {
      fontSize: 11,
      fontWeight: 700,
      color: "var(--hot)"
    }
  }, "\uD83D\uDD25 \u7206\u6B3E\u7387 ", topic.hotRate, "%")), /*#__PURE__*/React.createElement("h2", {
    style: {
      margin: 0,
      fontFamily: "var(--font-display)",
      fontWeight: 800,
      fontSize: "var(--text-lg)",
      lineHeight: 1.3
    }
  }, topic.title), /*#__PURE__*/React.createElement("p", {
    style: {
      margin: 0,
      fontSize: "var(--text-xs)",
      color: "var(--text-muted)",
      lineHeight: "var(--leading-relaxed)"
    }
  }, topic.rationale)), /*#__PURE__*/React.createElement("div", {
    style: {
      display: "flex",
      alignItems: "center",
      gap: 8,
      fontSize: 11
    }
  }, /*#__PURE__*/React.createElement("span", {
    style: {
      color: "var(--text-subtle)"
    }
  }, "\u6838\u5FC3\u641C\u7D22\u8BCD"), /*#__PURE__*/React.createElement("span", {
    style: {
      fontWeight: 600,
      color: "var(--topicblue-default)",
      background: "var(--topicblue-light)",
      borderRadius: 999,
      padding: "2px 8px"
    }
  }, topic.kw), ev && /*#__PURE__*/React.createElement("span", {
    style: {
      marginLeft: "auto",
      fontSize: 10,
      color: ev.mode === "keyword_fallback" ? "var(--warning)" : "var(--success)"
    }
  }, ev.mode === "semantic" ? "语义命中" : "关键词兑底")), /*#__PURE__*/React.createElement("div", {
    style: {
      display: "flex",
      flexDirection: "column",
      gap: 8
    }
  }, /*#__PURE__*/React.createElement(Eyebrow, null, "\u521B\u4F5C\u4F9D\u636E \xB7 ", ev ? ev.items.length : 0, " \u6761\uFF08\u6570\u636E\u5E95\u5EA7\u68C0\u7D22\uFF09"), ev && ev.items.map(it => /*#__PURE__*/React.createElement("button", {
    key: it.resource_id,
    onClick: () => actions.openEvidence({
      ...it,
      mode: ev.mode
    }),
    style: {
      textAlign: "left",
      border: "1px solid var(--border)",
      borderRadius: "var(--radius-md)",
      padding: 10,
      background: "var(--oats-light)",
      cursor: "pointer",
      display: "flex",
      flexDirection: "column",
      gap: 5
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      display: "flex",
      alignItems: "center",
      gap: 6
    }
  }, /*#__PURE__*/React.createElement("span", {
    style: {
      fontSize: 9,
      fontWeight: 700,
      color: "var(--topicblue-default)",
      background: "var(--topicblue-light)",
      borderRadius: 4,
      padding: "1px 5px",
      flexShrink: 0
    }
  }, it.type), /*#__PURE__*/React.createElement("span", {
    style: {
      fontSize: 11,
      fontWeight: 600,
      color: "var(--text-body)",
      overflow: "hidden",
      textOverflow: "ellipsis",
      whiteSpace: "nowrap",
      flex: 1
    }
  }, it.title), /*#__PURE__*/React.createElement("span", {
    className: "font-tabular",
    style: {
      fontSize: 10,
      color: "var(--primary)",
      fontWeight: 700
    }
  }, it.score.toFixed(2))), /*#__PURE__*/React.createElement("div", {
    style: {
      display: "flex",
      gap: 10,
      fontSize: 9,
      color: "var(--text-subtle)"
    }
  }, /*#__PURE__*/React.createElement("span", null, "\u76F8\u5173 ", (it.relevance * 100).toFixed(0), "%"), /*#__PURE__*/React.createElement("span", null, "\u65F6\u6548 ", (it.freshness * 100).toFixed(0), "%"), /*#__PURE__*/React.createElement("span", null, "\u8868\u73B0 ", (it.performance * 100).toFixed(0), "%"))))), /*#__PURE__*/React.createElement("div", {
    style: {
      display: "flex",
      flexDirection: "column",
      gap: 6
    }
  }, /*#__PURE__*/React.createElement(Eyebrow, null, "\u5EFA\u8BAE\u7ED3\u6784"), /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: 11,
      color: "var(--text-muted)",
      lineHeight: 1.7
    }
  }, "\u2460 \u5171\u60C5\u94A9\u5B50 \u2192 \u2461 \u7F16\u53F7\u6E05\u5355\u5E72\u8D27 \u2192 \u2462 \u9009\u8D2D TIPS \u2192 \u2463 \u4E92\u52A8\u6536\u53E3 + \u8BDD\u9898\u77E9\u9635")), /*#__PURE__*/React.createElement("div", {
    style: {
      position: "sticky",
      bottom: 0,
      background: "var(--surface-card)",
      paddingTop: 10,
      borderTop: "1px solid var(--border)"
    }
  }, /*#__PURE__*/React.createElement(Button, {
    variant: "primary",
    block: true,
    leftIcon: /*#__PURE__*/React.createElement(Icon, {
      name: "feather",
      size: 14
    }),
    onClick: () => actions.chooseTopic(topic, "deep")
  }, "\u8FDB\u5165\u6DF1\u5EA6\u521B\u4F5C")));
}
Object.assign(window, {
  CreationScreen,
  EvidencePanel
});
})(); } catch (e) { __ds_ns.__errors.push({ path: "ui_kits/studio/CreationScreen.jsx", error: String((e && e.message) || e) }); }

// ui_kits/studio/DeepCreation.jsx
try { (() => {
// 深度创作 screen — a focused long-form environment bound to the
// shared note. form: "immersive" | "flow" | "workspace"
function DeepCreation({
  form
}) {
  const {
    note,
    setSection
  } = useStudio();
  const [mode, setMode] = React.useState("edit");
  if (note.status === "idle") return /*#__PURE__*/React.createElement(DeepEmpty, {
    onGo: () => setSection("create")
  });
  const body = mode === "compare" ? /*#__PURE__*/React.createElement(ABCompare, null) : form === "flow" ? /*#__PURE__*/React.createElement(DeepFlow, null) : form === "workspace" ? /*#__PURE__*/React.createElement(DeepWorkspace, null) : /*#__PURE__*/React.createElement(DeepImmersive, null);
  return /*#__PURE__*/React.createElement("div", {
    style: {
      flex: 1,
      display: "flex",
      flexDirection: "column",
      minHeight: 0
    }
  }, /*#__PURE__*/React.createElement(DeepTopicBar, {
    mode: mode,
    setMode: setMode
  }), body);
}

// 深度创作必须基于选中的选题；未选时引导回创作区
function DeepEmpty({
  onGo
}) {
  const {
    Button,
    TopicCard
  } = window.DesignSystem_71831b;
  const {
    actions
  } = useStudio();
  const S = window.STUDIO;
  return /*#__PURE__*/React.createElement("div", {
    className: "cs",
    style: {
      flex: 1,
      overflowY: "auto",
      background: "var(--background)",
      padding: 28
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      maxWidth: 580,
      margin: "0 auto",
      textAlign: "center",
      display: "flex",
      flexDirection: "column",
      alignItems: "center",
      gap: 10
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      width: 54,
      height: 54,
      borderRadius: "var(--radius-lg)",
      background: "var(--accent-surface)",
      display: "flex",
      alignItems: "center",
      justifyContent: "center",
      fontSize: 26
    }
  }, "\uD83E\uDEB6"), /*#__PURE__*/React.createElement("div", {
    style: {
      fontFamily: "var(--font-display)",
      fontWeight: 800,
      fontSize: "var(--text-lg)"
    }
  }, "\u6DF1\u5EA6\u521B\u4F5C \xB7 \u4ECE\u4E00\u4E2A\u9009\u9898\u8FDB\u5165"), /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: "var(--text-sm)",
      color: "var(--text-muted)",
      maxWidth: 400,
      lineHeight: "var(--leading-relaxed)"
    }
  }, "\u9009\u4E00\u4E2A\u9009\u9898\u76F4\u63A5\u8FDB\u5165\u6DF1\u5EA6\u521B\u4F5C\uFF0C\uD83C\uDF60 \u4F1A\u5E26\u7740\u5B83\u7684\u4F9D\u636E\u6D41\u5F0F\u8D77\u7A3F\uFF1B\u4E5F\u53EF\u4EE5\u5148\u53BB\u300C\u521B\u4F5C\u300D\u533A\u7528\u5BF9\u8BDD\u8D77\u7A3F\u518D\u6765\u6253\u78E8\u3002"), /*#__PURE__*/React.createElement(Button, {
    variant: "ghost",
    size: "sm",
    leftIcon: /*#__PURE__*/React.createElement(Icon, {
      name: "arrow-left",
      size: 13
    }),
    onClick: onGo
  }, "\u6216\u53BB\u521B\u4F5C\u533A\u7528\u5BF9\u8BDD\u8D77\u7A3F")), /*#__PURE__*/React.createElement("div", {
    style: {
      maxWidth: 820,
      margin: "20px auto 0",
      display: "grid",
      gridTemplateColumns: "1fr 1fr 1fr",
      gap: 12
    }
  }, S.topics.map(t => /*#__PURE__*/React.createElement("div", {
    key: t.id,
    style: {
      display: "flex"
    }
  }, /*#__PURE__*/React.createElement(TopicCard, {
    index: t.id,
    title: t.title,
    rationale: t.rationale,
    hotRate: t.hotRate,
    onClick: () => actions.chooseTopic(t, "deep")
  })))));
}

// 顶部「基于选题」上下文条
function DeepTopicBar({
  mode,
  setMode
}) {
  const {
    note,
    setSection
  } = useStudio();
  const {
    Badge
  } = window.DesignSystem_71831b;
  const topic = (window.STUDIO.topics || []).find(t => t.id === note.topicId);
  return /*#__PURE__*/React.createElement("div", {
    style: {
      display: "flex",
      alignItems: "center",
      justifyContent: "space-between",
      gap: 12,
      padding: "10px 20px",
      background: "var(--surface-card)",
      borderBottom: "1px solid var(--border)",
      flexShrink: 0
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      display: "flex",
      alignItems: "center",
      gap: 10,
      minWidth: 0
    }
  }, /*#__PURE__*/React.createElement("button", {
    onClick: () => setSection("create"),
    title: "\u8FD4\u56DE\u521B\u4F5C",
    style: {
      display: "inline-flex",
      alignItems: "center",
      gap: 4,
      background: "none",
      border: "1px solid var(--border)",
      borderRadius: "var(--radius-sm)",
      padding: "5px 10px",
      cursor: "pointer",
      fontSize: "var(--text-xs)",
      color: "var(--text-body)",
      fontWeight: 600,
      whiteSpace: "nowrap",
      flexShrink: 0
    }
  }, /*#__PURE__*/React.createElement(Icon, {
    name: "arrow-left",
    size: 13
  }), " \u8FD4\u56DE"), /*#__PURE__*/React.createElement("span", {
    style: {
      width: 1,
      height: 18,
      background: "var(--border)",
      flexShrink: 0
    }
  }), /*#__PURE__*/React.createElement("span", {
    style: {
      fontSize: 10,
      color: "var(--text-subtle)",
      fontWeight: 600,
      whiteSpace: "nowrap"
    }
  }, "\u57FA\u4E8E\u9009\u9898"), topic && /*#__PURE__*/React.createElement(Badge, {
    tone: "topic",
    shape: "chip"
  }, topic.angle), /*#__PURE__*/React.createElement("span", {
    style: {
      fontSize: "var(--text-sm)",
      fontWeight: 700,
      color: "var(--text-body)",
      overflow: "hidden",
      textOverflow: "ellipsis",
      whiteSpace: "nowrap"
    }
  }, topic ? topic.title : note.title || "未命名草稿"), topic && /*#__PURE__*/React.createElement("span", {
    style: {
      fontSize: 10,
      fontWeight: 700,
      color: "var(--hot)",
      whiteSpace: "nowrap"
    }
  }, "\uD83D\uDD25 ", topic.hotRate, "%"), topic && /*#__PURE__*/React.createElement(EvidenceChips, {
    topicId: topic.id
  })), /*#__PURE__*/React.createElement("div", {
    style: {
      display: "flex",
      alignItems: "center",
      gap: 8,
      flexShrink: 0
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      display: "flex",
      gap: 3,
      background: "var(--oats-dark)",
      borderRadius: "var(--radius-sm)",
      padding: 3
    }
  }, [["edit", "编辑"], ["compare", "A·B 对比"]].map(([k, l]) => /*#__PURE__*/React.createElement("button", {
    key: k,
    onClick: () => setMode(k),
    style: {
      padding: "4px 10px",
      borderRadius: "var(--radius-xs)",
      border: "none",
      cursor: "pointer",
      fontSize: 11,
      fontWeight: mode === k ? 700 : 500,
      background: mode === k ? "var(--surface-card)" : "transparent",
      color: mode === k ? "var(--primary)" : "var(--text-muted)",
      boxShadow: mode === k ? "var(--shadow-xs)" : "none"
    }
  }, l))), /*#__PURE__*/React.createElement("button", {
    onClick: () => setSection("create"),
    style: {
      display: "inline-flex",
      alignItems: "center",
      gap: 5,
      background: "none",
      border: "1px solid var(--border)",
      borderRadius: "var(--radius-sm)",
      padding: "5px 10px",
      cursor: "pointer",
      fontSize: "var(--text-xs)",
      color: "var(--text-muted)",
      whiteSpace: "nowrap"
    }
  }, /*#__PURE__*/React.createElement(Icon, {
    name: "repeat",
    size: 12
  }), " \u6362\u9898")));
}

// Big editor bound to the shared note
function BigEditor({
  maxWidth = 720
}) {
  const {
    note,
    actions
  } = useStudio();
  return /*#__PURE__*/React.createElement("div", {
    style: {
      maxWidth,
      margin: "0 auto",
      width: "100%",
      background: "var(--surface-card)",
      border: "1px solid var(--border)",
      borderRadius: "var(--radius-lg)",
      boxShadow: "var(--shadow-md)",
      padding: 28,
      display: "flex",
      flexDirection: "column",
      gap: 16
    }
  }, /*#__PURE__*/React.createElement("input", {
    value: note.title,
    placeholder: "\u5199\u4E2A\u94A9\u5B50\u6807\u9898\u2026\uFF08\u226420 \u5B57\uFF09",
    onChange: e => actions.updateField("title", e.target.value),
    style: {
      border: "none",
      outline: "none",
      background: "transparent",
      fontFamily: "var(--font-display)",
      fontWeight: 800,
      fontSize: "var(--text-xl)",
      color: "var(--text-body)",
      letterSpacing: "var(--tracking-tight)"
    }
  }), /*#__PURE__*/React.createElement("div", {
    style: {
      height: 1,
      background: "var(--border)"
    }
  }), /*#__PURE__*/React.createElement("textarea", {
    value: note.body,
    placeholder: "\u6B63\u6587\u4ECE\u4E00\u53E5\u5171\u60C5\u94A9\u5B50\u5F00\u59CB\uFF0C\u518D\u7528 1\uFE0F\u20E32\uFE0F\u20E33\uFE0F\u20E3 \u5206\u70B9\u5E72\u8D27\uFF0C\u6700\u540E\u5F15\u5BFC\u4E92\u52A8\u2026",
    onChange: e => actions.updateField("body", e.target.value),
    style: {
      border: "none",
      outline: "none",
      resize: "none",
      background: "transparent",
      fontFamily: "var(--font-sans)",
      fontSize: "var(--text-sm)",
      lineHeight: "var(--leading-relaxed)",
      color: "var(--text-body)",
      minHeight: 320,
      flex: 1
    }
  }), /*#__PURE__*/React.createElement("div", {
    style: {
      display: "flex",
      justifyContent: "space-between",
      alignItems: "center",
      fontSize: 11,
      color: "var(--text-subtle)"
    }
  }, /*#__PURE__*/React.createElement("span", null, "\u81EA\u52A8\u4FDD\u5B58 \xB7 \u521A\u521A"), /*#__PURE__*/React.createElement("span", {
    className: "font-tabular"
  }, note.body.length, " / 1000 \u5B57")));
}
function AssistantPanel() {
  const {
    Button,
    HashtagTag
  } = window.DesignSystem_71831b;
  const {
    note,
    actions
  } = useStudio();
  const S = window.STUDIO;
  const checks = computeChecks(note);
  return /*#__PURE__*/React.createElement("div", {
    className: "cs",
    style: {
      display: "flex",
      flexDirection: "column",
      gap: 14,
      height: "100%",
      overflowY: "auto"
    }
  }, /*#__PURE__*/React.createElement(PanelHead, {
    icon: "sparkles",
    title: "AI \u521B\u4F5C\u52A9\u624B",
    sub: "\uD83C\uDF60 \u968F\u5199\u968F\u5E2E"
  }), /*#__PURE__*/React.createElement("div", {
    style: {
      display: "flex",
      flexWrap: "wrap",
      gap: 6
    }
  }, /*#__PURE__*/React.createElement(Button, {
    variant: "soft",
    size: "sm",
    leftIcon: /*#__PURE__*/React.createElement(Icon, {
      name: "sparkles",
      size: 12
    }),
    onClick: actions.polish
  }, "\u6DA6\u8272\u8BED\u6C14"), /*#__PURE__*/React.createElement(Button, {
    variant: "soft",
    size: "sm",
    leftIcon: /*#__PURE__*/React.createElement(Icon, {
      name: "scissors",
      size: 12
    }),
    onClick: actions.shorten
  }, "\u4E00\u952E\u7626\u8EAB"), /*#__PURE__*/React.createElement(Button, {
    variant: "soft",
    size: "sm",
    leftIcon: /*#__PURE__*/React.createElement(Icon, {
      name: "hash",
      size: 12
    }),
    onClick: actions.addTags
  }, "\u914D\u6807\u7B7E")), /*#__PURE__*/React.createElement("div", null, /*#__PURE__*/React.createElement(Eyebrow, {
    style: {
      marginBottom: 7
    }
  }, "\u63A8\u8350\u8BDD\u9898\u6807\u7B7E"), /*#__PURE__*/React.createElement("div", {
    style: {
      display: "flex",
      flexWrap: "wrap",
      gap: 6
    }
  }, S.recommendedTags.filter(tg => !note.tags.includes(tg)).map(tg => /*#__PURE__*/React.createElement(HashtagTag, {
    key: tg,
    addable: true,
    onAdd: () => actions.addTag(tg)
  }, tg)))), /*#__PURE__*/React.createElement(CopyDoctor, {
    checks: checks,
    score: scoreOf(checks)
  }));
}
function EvidenceRail() {
  const {
    Card,
    Badge
  } = window.DesignSystem_71831b;
  return /*#__PURE__*/React.createElement("div", {
    className: "cs",
    style: {
      display: "flex",
      flexDirection: "column",
      gap: 12,
      height: "100%",
      overflowY: "auto"
    }
  }, /*#__PURE__*/React.createElement(PanelHead, {
    icon: "database",
    title: "\u98DE\u4E66\u8D44\u6599 \xB7 \u8BC1\u636E",
    sub: "\u9009\u9898\u4F9D\u636E\u6765\u6E90"
  }), [{
    src: "多维表格 · 第 4 行",
    t: "搬家式露营装备清单",
    m: "赞 3.2w · 藏 1.8w",
    time: "源 06-20"
  }, {
    src: "爆款拆解库",
    t: "新手避坑极简装备",
    m: "藏 > 赞，收藏导向",
    time: "源 06-18"
  }, {
    src: "Wiki · 露营选品",
    t: "天幕 / 蛋卷桌 / 氛围灯",
    m: "高频出现单品",
    time: "本地索引"
  }].map((e, i) => /*#__PURE__*/React.createElement(Card, {
    key: i,
    padding: "sm",
    tone: "sunken"
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      display: "flex",
      justifyContent: "space-between",
      alignItems: "center",
      marginBottom: 5
    }
  }, /*#__PURE__*/React.createElement(Badge, {
    tone: "topic",
    shape: "chip"
  }, e.src), /*#__PURE__*/React.createElement("span", {
    style: {
      fontSize: 9,
      color: "var(--text-subtle)"
    }
  }, e.time)), /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: "var(--text-xs)",
      fontWeight: 600,
      color: "var(--text-body)"
    }
  }, e.t), /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: 10,
      color: "var(--text-muted)",
      marginTop: 3
    }
  }, e.m))));
}
function DeepImmersive() {
  return /*#__PURE__*/React.createElement(DeepEditor, null);
}

// 小红书笔记实时预览（深度创作右栏）
function NotePreview({
  note
}) {
  const {
    PhoneFrame
  } = window.DesignSystem_71831b;
  const S = window.STUDIO;
  const img = S.images[(note.topicId || 1) - 1] || S.images[0];
  return /*#__PURE__*/React.createElement(PhoneFrame, {
    width: 300
  }, /*#__PURE__*/React.createElement("div", {
    className: "cs",
    style: {
      paddingTop: 30,
      height: "100%",
      overflowY: "auto",
      background: "#fff",
      display: "flex",
      flexDirection: "column"
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      position: "relative",
      width: "100%",
      aspectRatio: "3 / 4",
      flexShrink: 0,
      background: "var(--accent-surface)"
    }
  }, /*#__PURE__*/React.createElement("img", {
    src: img,
    alt: "cover",
    style: {
      width: "100%",
      height: "100%",
      objectFit: "cover"
    }
  }), /*#__PURE__*/React.createElement("div", {
    style: {
      position: "absolute",
      inset: 0,
      background: "linear-gradient(180deg,rgba(0,0,0,.05),rgba(0,0,0,.42))"
    }
  }), /*#__PURE__*/React.createElement("div", {
    style: {
      position: "absolute",
      top: 10,
      left: 12,
      right: 12,
      color: "#fff",
      fontFamily: "var(--font-display)",
      fontWeight: 800,
      fontSize: 20,
      lineHeight: 1.15,
      textShadow: "0 1px 5px rgba(0,0,0,.5)",
      whiteSpace: "pre-line"
    }
  }, note.cover)), /*#__PURE__*/React.createElement("div", {
    style: {
      padding: 12
    }
  }, /*#__PURE__*/React.createElement("h3", {
    style: {
      margin: "0 0 8px",
      fontSize: 13,
      fontWeight: 700,
      lineHeight: 1.35,
      color: "var(--charcoal-default)"
    }
  }, note.title), /*#__PURE__*/React.createElement("p", {
    style: {
      margin: 0,
      fontSize: 11,
      lineHeight: 1.7,
      color: "var(--charcoal-light)",
      whiteSpace: "pre-wrap"
    }
  }, note.body))));
}
function DeepFlow() {
  const S = window.STUDIO;
  const [active, setActive] = React.useState(2);
  const outline = [{
    step: "选题",
    detail: "从爆款数据挑方向"
  }, {
    step: "大纲",
    detail: "钩子 → 清单 → TIPS → 互动"
  }, {
    step: "正文",
    detail: "逐段撰写 + 实时体检"
  }, {
    step: "润色",
    detail: "/polish 语气 · /shorten 瘦身"
  }, {
    step: "配图",
    detail: "封面大字 + 4 张内容图"
  }];
  return /*#__PURE__*/React.createElement("div", {
    style: {
      flex: 1,
      display: "flex",
      flexDirection: "column",
      minHeight: 0,
      background: "var(--background)"
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      display: "flex",
      alignItems: "center",
      gap: 8,
      padding: "16px 28px",
      borderBottom: "1px solid var(--border)",
      background: "var(--surface-card)",
      flexShrink: 0,
      justifyContent: "center"
    }
  }, outline.map((o, i) => {
    const done = i < active,
      on = i === active;
    return /*#__PURE__*/React.createElement(React.Fragment, {
      key: o.step
    }, /*#__PURE__*/React.createElement("button", {
      onClick: () => setActive(i),
      style: {
        display: "flex",
        alignItems: "center",
        gap: 7,
        cursor: "pointer",
        background: "none",
        border: "none"
      }
    }, /*#__PURE__*/React.createElement("span", {
      style: {
        width: 26,
        height: 26,
        borderRadius: "999px",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        fontSize: 12,
        fontWeight: 700,
        fontFamily: "var(--font-display)",
        background: on ? "var(--primary)" : done ? "var(--success-surface)" : "var(--oats-dark)",
        color: on ? "#fff" : done ? "var(--success)" : "var(--text-subtle)",
        border: done ? "1px solid var(--success)" : "none"
      }
    }, done ? "✓" : i + 1), /*#__PURE__*/React.createElement("span", {
      style: {
        fontSize: "var(--text-xs)",
        fontWeight: on ? 700 : 500,
        color: on ? "var(--primary)" : done ? "var(--text-body)" : "var(--text-subtle)"
      }
    }, o.step)), i < outline.length - 1 && /*#__PURE__*/React.createElement("span", {
      style: {
        width: 28,
        height: 2,
        background: done ? "var(--success)" : "var(--border)",
        borderRadius: 2
      }
    }));
  })), /*#__PURE__*/React.createElement("div", {
    className: "cs",
    style: {
      flex: 1,
      overflowY: "auto",
      padding: 28
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      maxWidth: 880,
      margin: "0 auto"
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      textAlign: "center",
      marginBottom: 18
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      fontFamily: "var(--font-display)",
      fontWeight: 800,
      fontSize: "var(--text-lg)"
    }
  }, "\u7B2C ", active + 1, " \u6B65 \xB7 ", outline[active].step), /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: "var(--text-xs)",
      color: "var(--text-muted)",
      marginTop: 4
    }
  }, outline[active].detail)), active === 2 ? /*#__PURE__*/React.createElement("div", {
    style: {
      display: "flex",
      gap: 16,
      alignItems: "flex-start"
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      flex: 1
    }
  }, /*#__PURE__*/React.createElement(BigEditor, {
    maxWidth: 9999
  })), /*#__PURE__*/React.createElement("div", {
    style: {
      width: 300,
      flexShrink: 0
    }
  }, /*#__PURE__*/React.createElement(AssistantPanel, null))) : /*#__PURE__*/React.createElement(StepCards, {
    step: active
  }))), /*#__PURE__*/React.createElement("div", {
    style: {
      padding: 14,
      borderTop: "1px solid var(--border)",
      background: "var(--surface-card)",
      display: "flex",
      justifyContent: "center",
      gap: 10,
      flexShrink: 0
    }
  }, /*#__PURE__*/React.createElement(BtnSecondary, {
    onClick: () => setActive(a => Math.max(0, a - 1))
  }, "\u4E0A\u4E00\u6B65"), /*#__PURE__*/React.createElement(BtnPrimary, {
    onClick: () => setActive(a => Math.min(outline.length - 1, a + 1))
  }, "\u4E0B\u4E00\u6B65")));
}
function BtnPrimary({
  children,
  onClick
}) {
  const {
    Button
  } = window.DesignSystem_71831b;
  return /*#__PURE__*/React.createElement(Button, {
    variant: "primary",
    onClick: onClick,
    rightIcon: /*#__PURE__*/React.createElement(Icon, {
      name: "arrow-right",
      size: 14
    })
  }, children);
}
function BtnSecondary({
  children,
  onClick
}) {
  const {
    Button
  } = window.DesignSystem_71831b;
  return /*#__PURE__*/React.createElement(Button, {
    variant: "secondary",
    onClick: onClick
  }, children);
}
function StepCards({
  step
}) {
  const {
    Card,
    TopicCard
  } = window.DesignSystem_71831b;
  const {
    actions,
    note
  } = useStudio();
  const S = window.STUDIO;
  if (step === 0) {
    const t = S.topics.find(x => x.id === note.topicId) || S.topics[0];
    return /*#__PURE__*/React.createElement("div", {
      style: {
        maxWidth: 460,
        margin: "0 auto",
        display: "flex",
        flexDirection: "column",
        gap: 10
      }
    }, /*#__PURE__*/React.createElement(TopicCard, {
      index: t.id,
      title: t.title,
      rationale: t.rationale,
      hotRate: t.hotRate
    }), /*#__PURE__*/React.createElement("div", {
      style: {
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        gap: 5,
        fontSize: 11,
        color: "var(--success)",
        fontWeight: 600
      }
    }, /*#__PURE__*/React.createElement(Icon, {
      name: "check-circle-2",
      size: 13,
      color: "var(--success)"
    }), " \u5DF2\u9009\u5B9A\u8BE5\u9009\u9898\uFF0C\u8FDB\u5165\u4E0B\u4E00\u6B65\u64B0\u5199\u5927\u7EB2"));
  }
  if (step === 1) {
    const lines = ["① 共情钩子：夏天太适合露营啦 + 身份标签", "② 编号清单：天幕 / 蛋卷桌 / 氛围灯 / 制冰机", "③ 选购 TIPS：折叠收纳体积", "④ 互动收口：求评论 + 话题标签矩阵"];
    return /*#__PURE__*/React.createElement(Card, {
      padding: "lg"
    }, /*#__PURE__*/React.createElement("div", {
      style: {
        display: "flex",
        flexDirection: "column",
        gap: 10
      }
    }, lines.map((l, i) => /*#__PURE__*/React.createElement("div", {
      key: i,
      style: {
        display: "flex",
        gap: 10,
        fontSize: "var(--text-sm)"
      }
    }, /*#__PURE__*/React.createElement(Icon, {
      name: "check-circle-2",
      size: 16,
      color: "var(--success)"
    }), /*#__PURE__*/React.createElement("span", null, l)))));
  }
  return /*#__PURE__*/React.createElement(Card, {
    padding: "lg"
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: "var(--text-sm)",
      color: "var(--text-muted)",
      lineHeight: "var(--leading-relaxed)"
    }
  }, step === 3 ? "AI 正在按小红书语气润色，并裁剪到 1000 字内。可对比多版本草稿后定稿。" : "封面：暖色实拍大全景 + 「搬家式露营 / 必带清单」大字报；建议再出 4 张内容图（产品特写 · 场景氛围 · 清单合影 · 选购对比）。"));
}
function DeepWorkspace() {
  return /*#__PURE__*/React.createElement(DeepEditor, null);
}

// A·B 版本并排对比
function ABCompare() {
  const {
    note,
    actions
  } = useStudio();
  const [pair, setPair] = React.useState(["A", "B"]);
  if (!note.versions) return null;
  const setSide = (i, v) => setPair(p => {
    const n = [...p];
    n[i] = v;
    return n;
  });
  const Col = ({
    id,
    side
  }) => {
    const {
      Button
    } = window.DesignSystem_71831b;
    const v = note.versions[id];
    const n = {
      ...note,
      title: v.title,
      body: v.body,
      tags: v.tags,
      cover: v.cover,
      kw: note.kw
    };
    const checks = computeChecks(n);
    const score = scoreOf(checks);
    const active = note.activeVersion === id;
    return /*#__PURE__*/React.createElement("div", {
      style: {
        flex: 1,
        minWidth: 0,
        display: "flex",
        flexDirection: "column",
        background: "var(--surface-card)",
        border: `1px solid ${active ? "var(--primary)" : "var(--border)"}`,
        borderRadius: "var(--radius-lg)",
        overflow: "hidden"
      }
    }, /*#__PURE__*/React.createElement("div", {
      style: {
        display: "flex",
        alignItems: "center",
        justifyContent: "space-between",
        padding: "10px 12px",
        borderBottom: "1px solid var(--border)",
        background: active ? "var(--accent-surface)" : "var(--oats-light)"
      }
    }, /*#__PURE__*/React.createElement("select", {
      value: id,
      onChange: e => setSide(side, e.target.value),
      style: {
        border: "1px solid var(--border)",
        borderRadius: "var(--radius-sm)",
        padding: "3px 6px",
        fontSize: 11,
        fontWeight: 700,
        background: "var(--surface-card)",
        color: "var(--text-body)",
        cursor: "pointer"
      }
    }, ["A", "B", "C"].map(k => /*#__PURE__*/React.createElement("option", {
      key: k,
      value: k
    }, note.versions[k].label))), /*#__PURE__*/React.createElement("span", {
      style: {
        display: "inline-flex",
        alignItems: "center",
        gap: 6
      }
    }, /*#__PURE__*/React.createElement("span", {
      style: {
        fontFamily: "var(--font-display)",
        fontWeight: 800,
        fontSize: "var(--text-base)",
        color: score >= 80 ? "var(--success)" : "var(--warning)"
      }
    }, score, /*#__PURE__*/React.createElement("span", {
      style: {
        fontSize: 10,
        color: "var(--text-subtle)",
        fontWeight: 400
      }
    }, "\u5206")), active && /*#__PURE__*/React.createElement("span", {
      style: {
        fontSize: 9,
        color: "var(--primary)",
        fontWeight: 700
      }
    }, "\u5F53\u524D"))), /*#__PURE__*/React.createElement("div", {
      className: "cs",
      style: {
        flex: 1,
        overflowY: "auto",
        padding: 16
      }
    }, /*#__PURE__*/React.createElement("h3", {
      style: {
        margin: "0 0 10px",
        fontFamily: "var(--font-display)",
        fontWeight: 800,
        fontSize: "var(--text-base)",
        lineHeight: 1.3
      }
    }, v.title), /*#__PURE__*/React.createElement("p", {
      style: {
        margin: 0,
        fontSize: "var(--text-xs)",
        lineHeight: "var(--leading-relaxed)",
        color: "var(--text-body)",
        whiteSpace: "pre-wrap"
      }
    }, v.body), /*#__PURE__*/React.createElement("div", {
      style: {
        display: "flex",
        flexWrap: "wrap",
        gap: 5,
        marginTop: 12
      }
    }, v.tags.map(tg => /*#__PURE__*/React.createElement("span", {
      key: tg,
      style: {
        fontSize: 9,
        color: "var(--topicblue-default)",
        background: "var(--topicblue-light)",
        borderRadius: 999,
        padding: "2px 7px"
      }
    }, "#", tg)))), /*#__PURE__*/React.createElement("div", {
      style: {
        padding: 10,
        borderTop: "1px solid var(--border)"
      }
    }, /*#__PURE__*/React.createElement(Button, {
      variant: active ? "secondary" : "primary",
      size: "sm",
      block: true,
      disabled: active,
      onClick: () => {
        actions.setVersion(id);
        actions.toast(`✅ 已采用「${v.label}」为当前稿`);
      }
    }, active ? "当前采用中" : "采用此版")));
  };
  return /*#__PURE__*/React.createElement("div", {
    style: {
      flex: 1,
      display: "flex",
      flexDirection: "column",
      minHeight: 0,
      background: "var(--background)"
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      textAlign: "center",
      padding: "12px 0 4px",
      fontSize: "var(--text-xs)",
      color: "var(--text-muted)"
    }
  }, "A\xB7B \u5E76\u6392\u5BF9\u6BD4 \xB7 \u4F53\u68C0\u5206\u6570\u5B9E\u65F6\u8BA1\u7B97\uFF0C\u9009\u66F4\u4F18\u7684\u4E00\u7248\u5B9A\u7A3F"), /*#__PURE__*/React.createElement("div", {
    style: {
      flex: 1,
      minHeight: 0,
      display: "flex",
      gap: 14,
      padding: 16
    }
  }, /*#__PURE__*/React.createElement(Col, {
    id: pair[0],
    side: 0
  }), /*#__PURE__*/React.createElement(Col, {
    id: pair[1],
    side: 1
  })));
}
Object.assign(window, {
  DeepCreation
});
})(); } catch (e) { __ds_ns.__errors.push({ path: "ui_kits/studio/DeepCreation.jsx", error: String((e && e.message) || e) }); }

// ui_kits/studio/DeepEditor.jsx
try { (() => {
// 全功能深度创作编辑器 — 三区工作台：结构 | 写作画布 | 质检定稿
// 复用 CopyDoctor / RiskPanel / ScheduleBar / EvidenceChips（全局）。
function DeepEditor() {
  const {
    Button,
    HashtagTag
  } = window.DesignSystem_71831b;
  const {
    note,
    actions
  } = useStudio();
  const S = window.STUDIO;
  const bodyRef = React.useRef(null);
  const checks = computeChecks(note);
  const score = scoreOf(checks);
  const writing = note.status === "writing";
  const body = note.body || "";
  const insertEmoji = e => {
    const el = bodyRef.current;
    if (!el) {
      actions.updateField("body", body + e);
      return;
    }
    const s = el.selectionStart,
      en = el.selectionEnd;
    actions.updateField("body", body.slice(0, s) + e + body.slice(en));
    requestAnimationFrame(() => {
      el.focus();
      el.selectionStart = el.selectionEnd = s + e.length;
    });
  };
  const outline = [{
    k: "共情钩子",
    ok: /谁懂|绝了|天花板|后悔|啦！|冲鸭|姐妹/.test(body.slice(0, 50)) || /\p{Extended_Pictographic}/u.test(body.slice(0, 30))
  }, {
    k: "分点清单",
    ok: /1️⃣|2️⃣|✅|❌/.test(body)
  }, {
    k: "选购 TIPS",
    ok: /TIPS|tips|📝|挑选|建议|避坑/.test(body)
  }, {
    k: "互动收口",
    ok: /评论|收藏|关注|交流|码住|抄作业/.test(body)
  }, {
    k: "话题标签",
    ok: note.tags.length >= 5
  }];
  const versionScore = id => {
    if (!note.versions) return null;
    const v = note.versions[id];
    return scoreOf(computeChecks({
      ...note,
      title: v.title,
      body: v.body,
      tags: v.tags,
      cover: v.cover
    }));
  };
  const img = S.images[(note.topicId || 1) - 1] || S.images[0];
  return /*#__PURE__*/React.createElement("div", {
    style: {
      flex: 1,
      minHeight: 0,
      display: "flex",
      background: "var(--background)"
    }
  }, /*#__PURE__*/React.createElement("aside", {
    className: "cs",
    style: {
      width: 224,
      borderRight: "1px solid var(--border)",
      background: "var(--surface-card)",
      overflowY: "auto",
      padding: 14,
      display: "flex",
      flexDirection: "column",
      gap: 18,
      flexShrink: 0
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      display: "flex",
      flexDirection: "column",
      gap: 7
    }
  }, /*#__PURE__*/React.createElement(Eyebrow, null, "\u8349\u7A3F\u7248\u672C"), note.versions ? ["A", "B", "C"].map(id => {
    const v = note.versions[id],
      on = note.activeVersion === id,
      sc = versionScore(id);
    return /*#__PURE__*/React.createElement("button", {
      key: id,
      onClick: () => actions.setVersion(id),
      style: {
        display: "flex",
        alignItems: "center",
        gap: 8,
        textAlign: "left",
        padding: "8px 9px",
        borderRadius: "var(--radius-sm)",
        cursor: "pointer",
        border: `1px solid ${on ? "var(--primary)" : "var(--border)"}`,
        background: on ? "var(--accent-surface)" : "var(--surface-card)"
      }
    }, /*#__PURE__*/React.createElement("span", {
      style: {
        width: 20,
        height: 20,
        borderRadius: 6,
        background: on ? "var(--primary)" : "var(--oats-dark)",
        color: on ? "#fff" : "var(--text-muted)",
        fontSize: 11,
        fontWeight: 800,
        display: "inline-flex",
        alignItems: "center",
        justifyContent: "center",
        flexShrink: 0,
        fontFamily: "var(--font-display)"
      }
    }, id), /*#__PURE__*/React.createElement("span", {
      style: {
        flex: 1,
        minWidth: 0,
        fontSize: 11,
        fontWeight: 600,
        color: on ? "var(--primary)" : "var(--text-body)",
        overflow: "hidden",
        textOverflow: "ellipsis",
        whiteSpace: "nowrap"
      }
    }, v.label.replace("版本 ", "")), sc != null && /*#__PURE__*/React.createElement("span", {
      style: {
        fontSize: 10,
        fontWeight: 700,
        color: sc >= 80 ? "var(--success)" : "var(--warning)"
      }
    }, sc));
  }) : /*#__PURE__*/React.createElement("span", {
    style: {
      fontSize: 10,
      color: "var(--text-subtle)"
    }
  }, "\u2014")), /*#__PURE__*/React.createElement("div", {
    style: {
      display: "flex",
      flexDirection: "column",
      gap: 8
    }
  }, /*#__PURE__*/React.createElement(Eyebrow, null, "\u521B\u4F5C\u5927\u7EB2"), outline.map(o => /*#__PURE__*/React.createElement("div", {
    key: o.k,
    style: {
      display: "flex",
      alignItems: "center",
      gap: 7,
      fontSize: 11,
      color: o.ok ? "var(--text-body)" : "var(--text-subtle)"
    }
  }, /*#__PURE__*/React.createElement(Icon, {
    name: o.ok ? "check-circle-2" : "circle",
    size: 13,
    color: o.ok ? "var(--success)" : "var(--border-strong)"
  }), o.k))), /*#__PURE__*/React.createElement("div", {
    style: {
      display: "flex",
      flexDirection: "column",
      gap: 7
    }
  }, /*#__PURE__*/React.createElement(Eyebrow, null, "\u521B\u4F5C\u4F9D\u636E"), /*#__PURE__*/React.createElement(EvidenceChips, {
    topicId: note.topicId
  }))), /*#__PURE__*/React.createElement("div", {
    className: "cs",
    style: {
      flex: 1,
      minWidth: 0,
      overflowY: "auto",
      display: "flex",
      justifyContent: "center",
      padding: "20px 28px"
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      width: 600,
      maxWidth: "100%",
      display: "flex",
      flexDirection: "column",
      gap: 16
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      display: "flex",
      flexDirection: "column",
      gap: 8
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      display: "flex",
      alignItems: "center",
      justifyContent: "space-between"
    }
  }, /*#__PURE__*/React.createElement(Eyebrow, null, "\u5C01\u9762 + \u56FE\u96C6 \xB7 3:4\uFF081080\xD71440\uFF09"), /*#__PURE__*/React.createElement("span", {
    style: {
      fontSize: 9,
      color: "var(--text-subtle)"
    }
  }, "\u5C01\u9762\u51B3\u5B9A\u70B9\u51FB\u7387")), /*#__PURE__*/React.createElement("div", {
    className: "cs",
    style: {
      display: "flex",
      gap: 10,
      overflowX: "auto",
      paddingBottom: 4
    }
  }, S.imageRoles.map((role, i) => {
    const cover = i === 0;
    return /*#__PURE__*/React.createElement("div", {
      key: role,
      style: {
        width: 148,
        flexShrink: 0,
        display: "flex",
        flexDirection: "column",
        gap: 5
      }
    }, /*#__PURE__*/React.createElement("div", {
      style: {
        position: "relative",
        width: 148,
        aspectRatio: "3 / 4",
        borderRadius: "var(--radius-md)",
        overflow: "hidden",
        border: cover ? "2px solid var(--primary)" : "1px solid var(--border)"
      }
    }, /*#__PURE__*/React.createElement("img", {
      src: S.images[i % S.images.length],
      alt: role,
      style: {
        width: "100%",
        height: "100%",
        objectFit: "cover"
      }
    }), /*#__PURE__*/React.createElement("div", {
      style: {
        position: "absolute",
        inset: 0,
        background: "linear-gradient(180deg, rgba(0,0,0,0.04), rgba(0,0,0,0.4))"
      }
    }), cover && /*#__PURE__*/React.createElement("textarea", {
      value: note.cover,
      onChange: e => actions.updateField("cover", e.target.value),
      rows: 3,
      placeholder: "\u5C01\u9762\u5927\u5B57\u62A5\u2026",
      style: {
        position: "absolute",
        top: 10,
        left: 10,
        right: 10,
        border: "none",
        background: "transparent",
        resize: "none",
        color: "#fff",
        fontFamily: "var(--font-display)",
        fontWeight: 800,
        fontSize: 17,
        lineHeight: 1.15,
        textShadow: "0 2px 6px rgba(0,0,0,0.55)",
        outline: "none"
      }
    }), /*#__PURE__*/React.createElement("span", {
      style: {
        position: "absolute",
        bottom: 7,
        left: 7,
        fontSize: 8,
        fontWeight: 700,
        color: cover ? "var(--primary)" : "#fff",
        background: cover ? "#fff" : "rgba(0,0,0,0.34)",
        padding: "1px 6px",
        borderRadius: 999
      }
    }, cover ? "封面" : role), /*#__PURE__*/React.createElement("button", {
      onClick: () => actions.toast(`🎨 已为「${cover ? "封面" : role}」AI 重新生图（示意）`),
      title: "AI \u91CD\u65B0\u751F\u56FE",
      style: {
        position: "absolute",
        top: 6,
        right: 6,
        width: 22,
        height: 22,
        borderRadius: 999,
        border: "none",
        background: "rgba(255,255,255,0.92)",
        cursor: "pointer",
        display: "inline-flex",
        alignItems: "center",
        justifyContent: "center"
      }
    }, /*#__PURE__*/React.createElement(Icon, {
      name: "wand-2",
      size: 11,
      color: "var(--primary)"
    }))));
  }), /*#__PURE__*/React.createElement("button", {
    onClick: () => actions.toast("🖼️ AI 正在生成新配图（示意）"),
    style: {
      width: 148,
      flexShrink: 0,
      aspectRatio: "3 / 4",
      borderRadius: "var(--radius-md)",
      border: "1px dashed var(--border-strong)",
      background: "var(--oats-light)",
      cursor: "pointer",
      display: "flex",
      flexDirection: "column",
      alignItems: "center",
      justifyContent: "center",
      gap: 6,
      color: "var(--text-subtle)"
    }
  }, /*#__PURE__*/React.createElement(Icon, {
    name: "image-plus",
    size: 20
  }), /*#__PURE__*/React.createElement("span", {
    style: {
      fontSize: 10,
      fontWeight: 600
    }
  }, "AI \u751F\u6210\u914D\u56FE"), /*#__PURE__*/React.createElement("span", {
    style: {
      fontSize: 8
    }
  }, "3:4 \xB7 1080\xD71440"))), /*#__PURE__*/React.createElement("div", {
    style: {
      display: "flex",
      gap: 6
    }
  }, /*#__PURE__*/React.createElement(Button, {
    variant: "soft",
    size: "sm",
    leftIcon: /*#__PURE__*/React.createElement(Icon, {
      name: "wand-2",
      size: 13
    }),
    onClick: () => actions.toast("🎨 AI 已生成封面方案（示意）")
  }, "AI \u751F\u6210\u5C01\u9762"), /*#__PURE__*/React.createElement(Button, {
    variant: "ghost",
    size: "sm",
    leftIcon: /*#__PURE__*/React.createElement(Icon, {
      name: "images",
      size: 13
    }),
    onClick: () => actions.toast("🖼️ 已生成全套图集（封面 + 4 张内容图，示意）")
  }, "\u4E00\u952E\u751F\u6210\u5168\u5957\u56FE\u96C6"))), /*#__PURE__*/React.createElement("div", {
    style: {
      display: "flex",
      flexDirection: "column",
      gap: 5
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      display: "flex",
      justifyContent: "space-between",
      alignItems: "center"
    }
  }, /*#__PURE__*/React.createElement(Eyebrow, null, "\u6807\u9898 \xB7 \u94A9\u5B50\u4F18\u5148"), /*#__PURE__*/React.createElement("span", {
    className: "font-tabular",
    style: {
      fontSize: 10,
      color: note.title.length > 20 ? "var(--warning)" : "var(--text-subtle)"
    }
  }, note.title.length, " / 20")), /*#__PURE__*/React.createElement("input", {
    value: note.title,
    onChange: e => actions.updateField("title", e.target.value),
    placeholder: "\u5199\u4E2A\u94A9\u5B50\u6807\u9898\u2026",
    style: {
      border: "none",
      borderBottom: "2px solid var(--border)",
      background: "transparent",
      fontFamily: "var(--font-display)",
      fontWeight: 800,
      fontSize: "var(--text-xl)",
      color: "var(--text-body)",
      padding: "4px 0",
      outline: "none",
      letterSpacing: "var(--tracking-tight)"
    }
  })), /*#__PURE__*/React.createElement("div", {
    style: {
      position: "sticky",
      top: 0,
      zIndex: 1,
      display: "flex",
      flexWrap: "wrap",
      alignItems: "center",
      gap: 6,
      padding: "8px 0",
      background: "var(--background)",
      borderBottom: "1px solid var(--border)"
    }
  }, /*#__PURE__*/React.createElement(Button, {
    variant: "soft",
    size: "sm",
    leftIcon: /*#__PURE__*/React.createElement(Icon, {
      name: "sparkles",
      size: 12
    }),
    onClick: actions.polish,
    disabled: writing
  }, "\u6DA6\u8272"), /*#__PURE__*/React.createElement(Button, {
    variant: "soft",
    size: "sm",
    leftIcon: /*#__PURE__*/React.createElement(Icon, {
      name: "scissors",
      size: 12
    }),
    onClick: actions.shorten,
    disabled: writing
  }, "\u7626\u8EAB"), /*#__PURE__*/React.createElement(Button, {
    variant: "soft",
    size: "sm",
    leftIcon: /*#__PURE__*/React.createElement(Icon, {
      name: "hash",
      size: 12
    }),
    onClick: actions.addTags,
    disabled: writing
  }, "\u914D\u6807\u7B7E"), /*#__PURE__*/React.createElement("span", {
    style: {
      width: 1,
      height: 18,
      background: "var(--border)",
      margin: "0 3px"
    }
  }), S.quickEmoji.slice(0, 8).map(e => /*#__PURE__*/React.createElement("button", {
    key: e,
    onClick: () => insertEmoji(e),
    disabled: writing,
    style: {
      border: "none",
      background: "transparent",
      cursor: "pointer",
      fontSize: 16,
      lineHeight: 1,
      padding: 1,
      opacity: writing ? 0.4 : 1
    }
  }, e)), /*#__PURE__*/React.createElement("span", {
    style: {
      marginLeft: "auto",
      fontSize: 10,
      color: body.length > 1000 ? "var(--warning)" : "var(--text-subtle)"
    },
    className: "font-tabular"
  }, writing ? "🍠 生成中…" : `${body.length} / 1000`)), /*#__PURE__*/React.createElement("textarea", {
    ref: bodyRef,
    value: writing ? body + " ▍" : body,
    onChange: e => actions.updateField("body", e.target.value),
    readOnly: writing,
    placeholder: "\u6B63\u6587\u4ECE\u4E00\u53E5\u5171\u60C5\u94A9\u5B50\u5F00\u59CB\uFF0C\u518D\u7528 1\uFE0F\u20E32\uFE0F\u20E33\uFE0F\u20E3 \u5206\u70B9\u5E72\u8D27\uFF0C\u6700\u540E\u5F15\u5BFC\u4E92\u52A8\u2026",
    style: {
      border: "none",
      background: "transparent",
      resize: "none",
      minHeight: 300,
      fontFamily: "var(--font-sans)",
      fontSize: "var(--text-sm)",
      lineHeight: "var(--leading-relaxed)",
      color: "var(--text-body)",
      outline: "none"
    }
  }), /*#__PURE__*/React.createElement("div", {
    style: {
      display: "flex",
      flexDirection: "column",
      gap: 8,
      borderTop: "1px solid var(--border)",
      paddingTop: 14
    }
  }, /*#__PURE__*/React.createElement(Eyebrow, null, "\u8BDD\u9898\u6807\u7B7E \xB7 ", note.tags.length, " \u4E2A\uFF08\u5EFA\u8BAE 5\u201310\uFF0C\u5927\u8BCD+\u957F\u5C3E\uFF09"), /*#__PURE__*/React.createElement("div", {
    style: {
      display: "flex",
      flexWrap: "wrap",
      gap: 6
    }
  }, note.tags.map(t => /*#__PURE__*/React.createElement("span", {
    key: t,
    onClick: () => actions.removeTag(t),
    style: {
      cursor: "pointer"
    },
    title: "\u70B9\u51FB\u79FB\u9664"
  }, /*#__PURE__*/React.createElement(HashtagTag, null, t))), note.tags.length === 0 && /*#__PURE__*/React.createElement("span", {
    style: {
      fontSize: 11,
      color: "var(--text-subtle)"
    }
  }, "\u6682\u65E0\uFF0C\u70B9\u4E0B\u65B9\u63A8\u8350\u6DFB\u52A0")), /*#__PURE__*/React.createElement("div", {
    style: {
      display: "flex",
      flexWrap: "wrap",
      gap: 6
    }
  }, /*#__PURE__*/React.createElement("span", {
    style: {
      fontSize: 10,
      color: "var(--text-subtle)",
      alignSelf: "center"
    }
  }, "\u63A8\u8350\uFF1A"), S.recommendedTags.filter(t => !note.tags.includes(t)).slice(0, 6).map(t => /*#__PURE__*/React.createElement(HashtagTag, {
    key: t,
    addable: true,
    onAdd: () => actions.addTag(t)
  }, t)))))), /*#__PURE__*/React.createElement("aside", {
    className: "cs",
    style: {
      width: 332,
      borderLeft: "1px solid var(--border)",
      background: "var(--surface-card)",
      overflowY: "auto",
      padding: 16,
      display: "flex",
      flexDirection: "column",
      gap: 14,
      flexShrink: 0,
      boxShadow: "var(--shadow-lg)"
    }
  }, /*#__PURE__*/React.createElement(PanelHead, {
    icon: "gauge",
    title: "\u8D28\u68C0 \xB7 \u5B9A\u7A3F",
    sub: "\u4F53\u68C0 / \u539F\u521B\u5EA6 / \u6392\u671F\u53D1\u5E03"
  }), /*#__PURE__*/React.createElement(CopyDoctor, {
    checks: checks,
    score: score
  }), /*#__PURE__*/React.createElement(RiskPanel, {
    note: note
  }), /*#__PURE__*/React.createElement(ScheduleBar, {
    score: score,
    status: note.status
  })));
}
Object.assign(window, {
  DeepEditor
});
})(); } catch (e) { __ds_ns.__errors.push({ path: "ui_kits/studio/DeepEditor.jsx", error: String((e && e.message) || e) }); }

// ui_kits/studio/Operations.jsx
try { (() => {
// 账号运营 screen — 数据看板 · 选题库/爆款拆解 · 内容日历/排期 · 数据回填.
// hosting tweak: "page" (独立页面) | "inline" (会话内 agent 驱动) | "hybrid" (同屏融合)
function Operations({
  hosting
}) {
  if (hosting === "inline") return /*#__PURE__*/React.createElement(OpsInline, null);
  if (hosting === "hybrid") return /*#__PURE__*/React.createElement(OpsHybrid, null);
  return /*#__PURE__*/React.createElement(OpsPage, null);
}

// 多账号页：左侧账号矩阵栏 + （矩阵总览 / 单账号看板）
function OpsPage() {
  const S = window.STUDIO;
  const [acct, setAcct] = React.useState("all");
  const account = S.accounts.find(a => a.id === acct);
  return /*#__PURE__*/React.createElement("div", {
    style: {
      flex: 1,
      display: "flex",
      minHeight: 0,
      background: "var(--background)"
    }
  }, /*#__PURE__*/React.createElement(AccountRail, {
    selected: acct,
    onSelect: setAcct
  }), /*#__PURE__*/React.createElement("div", {
    className: "cs",
    style: {
      flex: 1,
      overflowY: "auto"
    }
  }, acct === "all" ? /*#__PURE__*/React.createElement(MatrixOverview, {
    onOpen: setAcct
  }) : /*#__PURE__*/React.createElement(DashboardBody, {
    account: account
  })));
}
function AccountRail({
  selected,
  onSelect
}) {
  const {
    actions
  } = useStudio();
  const S = window.STUDIO;
  const dot = (initial, tone) => ({
    width: 26,
    height: 26,
    borderRadius: "999px",
    flexShrink: 0,
    display: "inline-flex",
    alignItems: "center",
    justifyContent: "center",
    fontSize: 11,
    fontWeight: 700,
    background: tone === "coral" ? "var(--accent-surface)" : tone === "topic" ? "var(--topicblue-light)" : "var(--oats-dark)",
    color: tone === "coral" ? "var(--primary)" : tone === "topic" ? "var(--topicblue-default)" : "var(--text-body)"
  });
  const Item = ({
    id,
    label,
    sub,
    initial,
    tone,
    active
  }) => /*#__PURE__*/React.createElement("button", {
    onClick: () => onSelect(id),
    style: {
      display: "flex",
      alignItems: "center",
      gap: 9,
      width: "100%",
      textAlign: "left",
      padding: "9px 11px",
      borderRadius: "var(--radius-sm)",
      border: "none",
      cursor: "pointer",
      borderLeft: active ? "2px solid var(--primary)" : "2px solid transparent",
      background: active ? "var(--oats-dark)" : "transparent"
    }
  }, /*#__PURE__*/React.createElement("span", {
    style: dot(initial, tone)
  }, initial), /*#__PURE__*/React.createElement("span", {
    style: {
      flex: 1,
      minWidth: 0
    }
  }, /*#__PURE__*/React.createElement("span", {
    style: {
      display: "block",
      fontSize: "var(--text-xs)",
      fontWeight: 600,
      color: active ? "var(--primary)" : "var(--text-body)",
      overflow: "hidden",
      textOverflow: "ellipsis",
      whiteSpace: "nowrap"
    }
  }, label), /*#__PURE__*/React.createElement("span", {
    style: {
      display: "block",
      fontSize: 9,
      color: "var(--text-subtle)"
    }
  }, sub)));
  return /*#__PURE__*/React.createElement("aside", {
    className: "cs",
    style: {
      width: 208,
      borderRight: "1px solid var(--border)",
      background: "var(--surface-card)",
      flexShrink: 0,
      overflowY: "auto"
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      padding: 14,
      display: "flex",
      flexDirection: "column",
      gap: 6
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      display: "flex",
      alignItems: "center",
      justifyContent: "space-between"
    }
  }, /*#__PURE__*/React.createElement(Eyebrow, null, "\u8D26\u53F7\u77E9\u9635"), /*#__PURE__*/React.createElement("span", {
    style: {
      fontSize: 9,
      color: "var(--text-subtle)"
    }
  }, S.accounts.length, " \u4E2A")), /*#__PURE__*/React.createElement(Item, {
    id: "all",
    label: "\u77E9\u9635\u603B\u89C8",
    sub: "\u805A\u5408 \xB7 \u6A2A\u5411\u5BF9\u6BD4",
    initial: "\u2211",
    tone: "topic",
    active: selected === "all"
  }), /*#__PURE__*/React.createElement("div", {
    style: {
      height: 1,
      background: "var(--border)",
      margin: "4px 0"
    }
  }), S.accounts.map(a => /*#__PURE__*/React.createElement(Item, {
    key: a.id,
    id: a.id,
    label: a.handle,
    sub: `${a.niche} · ${a.fans}`,
    initial: a.initial,
    tone: a.tone,
    active: selected === a.id
  })), /*#__PURE__*/React.createElement("button", {
    onClick: () => actions.toast("➕ 接入新账号：扫码授权小红书账号（示意）"),
    style: {
      display: "flex",
      alignItems: "center",
      gap: 6,
      marginTop: 4,
      padding: "8px 11px",
      border: "1px dashed var(--border-strong)",
      borderRadius: "var(--radius-sm)",
      background: "transparent",
      cursor: "pointer",
      color: "var(--text-subtle)",
      fontSize: "var(--text-xs)"
    }
  }, /*#__PURE__*/React.createElement(Icon, {
    name: "plus",
    size: 13
  }), " \u63A5\u5165\u65B0\u8D26\u53F7")));
}
function MatrixOverview({
  onOpen
}) {
  const {
    StatCard,
    Card,
    Badge,
    Button
  } = window.DesignSystem_71831b;
  const {
    actions
  } = useStudio();
  const S = window.STUDIO;
  const sum = k => S.accounts.reduce((s, a) => s + a[k], 0);
  const fmt = n => n >= 10000 ? (n / 10000).toFixed(1) + "w" : n.toLocaleString();
  const avgHot = Math.round(sum("hot") / S.accounts.length);
  const statusTone = {
    "主力": "synced",
    "成长": "info",
    "孵化": "draft"
  };
  const col = "2fr 1fr 0.9fr 0.8fr 0.7fr 0.8fr";
  return /*#__PURE__*/React.createElement("div", {
    style: {
      padding: 28,
      maxWidth: 1180,
      margin: "0 auto",
      display: "flex",
      flexDirection: "column",
      gap: 20
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      display: "flex",
      alignItems: "center",
      justifyContent: "space-between"
    }
  }, /*#__PURE__*/React.createElement("div", null, /*#__PURE__*/React.createElement("div", {
    style: {
      fontFamily: "var(--font-display)",
      fontWeight: 800,
      fontSize: "var(--text-xl)"
    }
  }, "\u8D26\u53F7\u77E9\u9635\u603B\u89C8"), /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: "var(--text-xs)",
      color: "var(--text-muted)",
      marginTop: 3
    }
  }, S.accounts.length, " \u4E2A\u8D26\u53F7 \xB7 \u8FD1 7 \u5929 \xB7 \u6570\u636E\u5E95\u5EA7\u805A\u5408\uFF08performance_metric\uFF09")), /*#__PURE__*/React.createElement(Button, {
    variant: "secondary",
    size: "sm",
    leftIcon: /*#__PURE__*/React.createElement(Icon, {
      name: "download",
      size: 13
    }),
    onClick: () => actions.toast("📊 矩阵周报已导出（示意）")
  }, "\u5BFC\u51FA\u77E9\u9635\u5468\u62A5")), /*#__PURE__*/React.createElement("section", null, /*#__PURE__*/React.createElement(Eyebrow, {
    style: {
      marginBottom: 10
    }
  }, "\u77E9\u9635\u805A\u5408"), /*#__PURE__*/React.createElement("div", {
    style: {
      display: "grid",
      gridTemplateColumns: "repeat(4, 1fr)",
      gap: 12
    }
  }, /*#__PURE__*/React.createElement(StatCard, {
    label: "\u77E9\u9635\u603B\u7C89\u4E1D",
    value: fmt(sum("fansNum")),
    delta: 14,
    tone: "coral",
    icon: /*#__PURE__*/React.createElement(Icon, {
      name: "users",
      size: 15
    })
  }), /*#__PURE__*/React.createElement(StatCard, {
    label: "\u672C\u5468\u65B0\u589E\u7C89\u4E1D",
    value: "+" + sum("dFans"),
    unit: "\u4EBA",
    delta: 22,
    tone: "success",
    icon: /*#__PURE__*/React.createElement(Icon, {
      name: "user-plus",
      size: 15
    })
  }), /*#__PURE__*/React.createElement(StatCard, {
    label: "\u672C\u5468\u53D1\u5E03",
    value: sum("posts"),
    unit: "\u7BC7",
    delta: 8,
    tone: "topic",
    icon: /*#__PURE__*/React.createElement(Icon, {
      name: "file-text",
      size: 15
    })
  }), /*#__PURE__*/React.createElement(StatCard, {
    label: "\u5E73\u5747\u7206\u6B3E\u7387",
    value: avgHot,
    unit: "%",
    delta: 5,
    icon: /*#__PURE__*/React.createElement(Icon, {
      name: "flame",
      size: 15
    })
  }))), /*#__PURE__*/React.createElement("section", {
    style: {
      display: "flex",
      flexDirection: "column",
      gap: 10
    }
  }, /*#__PURE__*/React.createElement(PanelHead, {
    icon: "layout-grid",
    title: "\u8D26\u53F7\u6A2A\u5411\u5BF9\u6BD4",
    sub: "\u70B9\u4EFB\u610F\u8D26\u53F7\u8FDB\u5165\u5B83\u7684\u8FD0\u8425\u770B\u677F"
  }), /*#__PURE__*/React.createElement(Card, {
    padding: "none",
    style: {
      overflow: "hidden"
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      display: "grid",
      gridTemplateColumns: col,
      padding: "9px 14px",
      borderBottom: "1px solid var(--border)",
      fontSize: 9,
      fontWeight: 700,
      color: "var(--text-subtle)",
      letterSpacing: "var(--tracking-wide)"
    }
  }, /*#__PURE__*/React.createElement("span", null, "\u8D26\u53F7"), /*#__PURE__*/React.createElement("span", null, "\u5782\u7C7B"), /*#__PURE__*/React.createElement("span", null, "\u7C89\u4E1D"), /*#__PURE__*/React.createElement("span", null, "\u8FD17\u5929"), /*#__PURE__*/React.createElement("span", null, "\u7206\u6B3E\u7387"), /*#__PURE__*/React.createElement("span", null, "\u72B6\u6001")), S.accounts.map((a, i) => /*#__PURE__*/React.createElement("button", {
    key: a.id,
    onClick: () => onOpen(a.id),
    style: {
      display: "grid",
      gridTemplateColumns: col,
      alignItems: "center",
      width: "100%",
      textAlign: "left",
      padding: "11px 14px",
      border: "none",
      borderTop: i ? "1px solid var(--border)" : "none",
      background: "transparent",
      cursor: "pointer",
      fontSize: "var(--text-xs)"
    }
  }, /*#__PURE__*/React.createElement("span", {
    style: {
      display: "flex",
      alignItems: "center",
      gap: 8,
      minWidth: 0
    }
  }, /*#__PURE__*/React.createElement("span", {
    style: {
      width: 24,
      height: 24,
      borderRadius: "999px",
      flexShrink: 0,
      display: "inline-flex",
      alignItems: "center",
      justifyContent: "center",
      fontSize: 10,
      fontWeight: 700,
      background: a.tone === "coral" ? "var(--accent-surface)" : a.tone === "topic" ? "var(--topicblue-light)" : "var(--oats-dark)",
      color: a.tone === "coral" ? "var(--primary)" : a.tone === "topic" ? "var(--topicblue-default)" : "var(--text-body)"
    }
  }, a.initial), /*#__PURE__*/React.createElement("span", {
    style: {
      fontWeight: 600,
      color: "var(--text-body)",
      overflow: "hidden",
      textOverflow: "ellipsis",
      whiteSpace: "nowrap"
    }
  }, a.handle)), /*#__PURE__*/React.createElement("span", {
    style: {
      color: "var(--text-muted)"
    }
  }, a.niche), /*#__PURE__*/React.createElement("span", {
    className: "font-tabular",
    style: {
      fontWeight: 600
    }
  }, a.fans), /*#__PURE__*/React.createElement("span", {
    className: "font-tabular",
    style: {
      color: "var(--success)",
      fontWeight: 600
    }
  }, "+", a.dFans), /*#__PURE__*/React.createElement("span", {
    style: {
      color: "var(--hot)",
      fontWeight: 700
    }
  }, "\uD83D\uDD25", a.hot), /*#__PURE__*/React.createElement("span", null, /*#__PURE__*/React.createElement(Badge, {
    tone: statusTone[a.status],
    shape: "chip"
  }, a.status)))))), /*#__PURE__*/React.createElement(CalendarSection, null));
}
function DashboardBody({
  dense = false,
  account = null
}) {
  const {
    StatCard,
    Button
  } = window.DesignSystem_71831b;
  const {
    actions
  } = useStudio();
  const S = window.STUDIO;
  const acct = account || {
    handle: S.user.handle,
    fans: S.user.fans,
    niche: ""
  };
  return /*#__PURE__*/React.createElement("div", {
    style: {
      padding: dense ? 16 : 28,
      maxWidth: 1180,
      margin: "0 auto",
      display: "flex",
      flexDirection: "column",
      gap: 20
    }
  }, !dense && /*#__PURE__*/React.createElement("div", {
    style: {
      display: "flex",
      alignItems: "center",
      justifyContent: "space-between"
    }
  }, /*#__PURE__*/React.createElement("div", null, /*#__PURE__*/React.createElement("div", {
    style: {
      fontFamily: "var(--font-display)",
      fontWeight: 800,
      fontSize: "var(--text-xl)"
    }
  }, acct.handle), /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: "var(--text-xs)",
      color: "var(--text-muted)",
      marginTop: 3
    }
  }, "\u7C89\u4E1D ", acct.fans, acct.niche ? ` · ${acct.niche}` : "", " \xB7 \u8FD1 7 \u5929 \xB7 \u6570\u636E\u5E95\u5EA7 / \u98DE\u4E66\u540C\u6B65")), /*#__PURE__*/React.createElement("div", {
    style: {
      display: "flex",
      gap: 8
    }
  }, /*#__PURE__*/React.createElement(Button, {
    variant: "secondary",
    size: "sm",
    leftIcon: /*#__PURE__*/React.createElement(Icon, {
      name: "download",
      size: 13
    }),
    onClick: () => actions.toast("📄 该账号周报已导出（示意）")
  }, "\u5BFC\u51FA\u5468\u62A5"), /*#__PURE__*/React.createElement(Button, {
    variant: "primary",
    size: "sm",
    leftIcon: /*#__PURE__*/React.createElement(Icon, {
      name: "pencil",
      size: 13
    }),
    onClick: () => actions.toast("✏️ 下拉到「数据回填」即可录入真实表现")
  }, "\u6570\u636E\u56DE\u586B"))), /*#__PURE__*/React.createElement("section", null, /*#__PURE__*/React.createElement(Eyebrow, {
    style: {
      marginBottom: 10
    }
  }, "\u6570\u636E\u770B\u677F"), /*#__PURE__*/React.createElement("div", {
    style: {
      display: "grid",
      gridTemplateColumns: "repeat(4, 1fr)",
      gap: 12
    }
  }, S.dashboard.map(d => /*#__PURE__*/React.createElement(StatCard, {
    key: d.label,
    label: d.label,
    value: d.value,
    unit: d.unit,
    delta: d.delta,
    tone: d.tone,
    icon: /*#__PURE__*/React.createElement(Icon, {
      name: d.icon,
      size: 15
    })
  })))), /*#__PURE__*/React.createElement(LibrarySection, null), /*#__PURE__*/React.createElement(CalendarSection, {
    accountFilter: account ? account.initial : null
  }), !dense && /*#__PURE__*/React.createElement(PublishPipeline, {
    account: account
  }), !dense && /*#__PURE__*/React.createElement(BackfillSection, null));
}

// 选题库 / 爆款拆解
function LibrarySection() {
  const {
    Card,
    Badge,
    Button
  } = window.DesignSystem_71831b;
  const {
    actions
  } = useStudio();
  const S = window.STUDIO;
  const [sel, setSel] = React.useState(1);
  const td = S.teardown;
  const selItem = S.library.find(x => x.id === sel);
  const statusTone = {
    "已发布": "synced",
    "排期中": "info",
    "草稿": "draft"
  };
  return /*#__PURE__*/React.createElement("section", {
    style: {
      display: "flex",
      flexDirection: "column",
      gap: 10
    }
  }, /*#__PURE__*/React.createElement(PanelHead, {
    icon: "library-big",
    title: "\u9009\u9898\u5E93 \xB7 \u7206\u6B3E\u62C6\u89E3",
    sub: "\u6C89\u6DC0\u7684\u9009\u9898\u4E0E\u8868\u73B0\uFF0C\u70B9\u51FB\u62C6\u89E3\u7206\u6B3E\u5957\u8DEF"
  }), /*#__PURE__*/React.createElement(Card, {
    padding: "none",
    style: {
      overflow: "hidden"
    }
  }, S.library.map((it, i) => {
    const on = it.id === sel;
    return /*#__PURE__*/React.createElement("button", {
      key: it.id,
      onClick: () => setSel(it.id),
      style: {
        display: "flex",
        alignItems: "center",
        gap: 10,
        width: "100%",
        textAlign: "left",
        padding: "11px 13px",
        border: "none",
        borderTop: i ? "1px solid var(--border)" : "none",
        cursor: "pointer",
        background: on ? "var(--accent-surface)" : "transparent"
      }
    }, /*#__PURE__*/React.createElement("span", {
      style: {
        fontSize: 11,
        fontWeight: 700,
        color: "var(--hot)",
        width: 38,
        flexShrink: 0
      }
    }, "\uD83D\uDD25", it.hot), /*#__PURE__*/React.createElement("span", {
      style: {
        flex: 1,
        minWidth: 0
      }
    }, /*#__PURE__*/React.createElement("span", {
      style: {
        display: "block",
        fontSize: "var(--text-xs)",
        fontWeight: 600,
        color: "var(--text-body)",
        overflow: "hidden",
        textOverflow: "ellipsis",
        whiteSpace: "nowrap"
      }
    }, it.title), /*#__PURE__*/React.createElement("span", {
      style: {
        display: "block",
        fontSize: 10,
        color: "var(--text-subtle)",
        marginTop: 2
      }
    }, it.angle, " \xB7 \u8D5E ", it.likes, " \xB7 \u85CF ", it.saves)), /*#__PURE__*/React.createElement(Badge, {
      tone: statusTone[it.status],
      shape: "chip"
    }, it.status));
  })), /*#__PURE__*/React.createElement(Card, {
    padding: "md",
    tone: "sunken"
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      display: "flex",
      alignItems: "center",
      justifyContent: "space-between",
      marginBottom: 9
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      display: "flex",
      alignItems: "center",
      gap: 7,
      minWidth: 0
    }
  }, /*#__PURE__*/React.createElement(Icon, {
    name: "scan-search",
    size: 15,
    color: "var(--primary)"
  }), /*#__PURE__*/React.createElement("span", {
    style: {
      fontSize: "var(--text-xs)",
      fontWeight: 700,
      overflow: "hidden",
      textOverflow: "ellipsis",
      whiteSpace: "nowrap"
    }
  }, "\u7206\u6B3E\u62C6\u89E3 \xB7 ", selItem ? selItem.title : td.title)), /*#__PURE__*/React.createElement(Button, {
    variant: "soft",
    size: "sm",
    leftIcon: /*#__PURE__*/React.createElement(Icon, {
      name: "copy-plus",
      size: 12
    }),
    onClick: () => actions.reuse(sel <= 3 ? sel : 1)
  }, "\u590D\u7528\u9009\u9898")), /*#__PURE__*/React.createElement("div", {
    style: {
      display: "flex",
      flexDirection: "column",
      gap: 8
    }
  }, td.points.map(p => /*#__PURE__*/React.createElement("div", {
    key: p.label,
    style: {
      display: "flex",
      gap: 9
    }
  }, /*#__PURE__*/React.createElement("span", {
    style: {
      fontSize: 10,
      fontWeight: 700,
      color: "var(--primary)",
      background: "var(--accent-surface)",
      border: "1px solid var(--border-coral)",
      borderRadius: 6,
      padding: "2px 7px",
      height: "fit-content",
      flexShrink: 0
    }
  }, p.label), /*#__PURE__*/React.createElement("span", {
    style: {
      fontSize: 11,
      color: "var(--text-muted)",
      lineHeight: 1.5
    }
  }, p.detail))))));
}

// 内容日历 / 发布排期
function CalendarSection({
  accountFilter = null
}) {
  const {
    Card
  } = window.DesignSystem_71831b;
  const {
    calendar
  } = useStudio();
  const S = window.STUDIO;
  const toneColor = {
    coral: "var(--primary)",
    topic: "var(--topicblue-default)",
    draft: "var(--text-subtle)"
  };
  const toneBg = {
    coral: "var(--accent-surface)",
    topic: "var(--topicblue-light)",
    draft: "var(--oats-dark)"
  };
  const byDate = {};
  calendar.forEach(d => {
    byDate[d.date] = accountFilter ? d.items.filter(it => !it.acct || it.acct === accountFilter) : d.items;
  });
  const m = S.month;
  const cells = [];
  for (let i = 0; i < m.firstOffset; i++) cells.push(null);
  for (let d = 1; d <= m.days; d++) cells.push(d);
  return /*#__PURE__*/React.createElement("section", {
    style: {
      display: "flex",
      flexDirection: "column",
      gap: 10
    }
  }, /*#__PURE__*/React.createElement(PanelHead, {
    icon: "calendar-days",
    title: "\u5185\u5BB9\u65E5\u5386 \xB7 \u53D1\u5E03\u6392\u671F",
    sub: `${m.label} · ${accountFilter ? "该账号" : "跨账号矩阵"}排期`,
    right: /*#__PURE__*/React.createElement("span", {
      style: {
        display: "inline-flex",
        gap: 6,
        color: "var(--text-subtle)"
      }
    }, /*#__PURE__*/React.createElement(Icon, {
      name: "chevron-left",
      size: 15
    }), /*#__PURE__*/React.createElement(Icon, {
      name: "chevron-right",
      size: 15
    }))
  }), /*#__PURE__*/React.createElement(Card, {
    padding: "md"
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      display: "grid",
      gridTemplateColumns: "repeat(7, 1fr)",
      gap: 5
    }
  }, S.weekdays.map(w => /*#__PURE__*/React.createElement("div", {
    key: w,
    style: {
      textAlign: "center",
      fontSize: 10,
      fontWeight: 600,
      color: "var(--text-subtle)",
      paddingBottom: 4
    }
  }, w)), cells.map((d, idx) => d === null ? /*#__PURE__*/React.createElement("div", {
    key: "b" + idx
  }) : /*#__PURE__*/React.createElement("div", {
    key: d,
    style: {
      minHeight: 66,
      borderRadius: "var(--radius-sm)",
      border: "1px solid var(--border)",
      background: byDate[d] && byDate[d].length ? "var(--surface-card)" : "var(--oats-light)",
      padding: 4,
      display: "flex",
      flexDirection: "column",
      gap: 3
    }
  }, /*#__PURE__*/React.createElement("span", {
    style: {
      fontSize: 10,
      color: "var(--text-subtle)",
      fontWeight: 600
    }
  }, d), (byDate[d] || []).map((it, i) => /*#__PURE__*/React.createElement("div", {
    key: i,
    style: {
      background: toneBg[it.tone],
      borderLeft: `2px solid ${toneColor[it.tone]}`,
      borderRadius: 3,
      padding: "2px 3px"
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      display: "flex",
      alignItems: "center",
      gap: 2
    }
  }, it.acct && /*#__PURE__*/React.createElement("span", {
    style: {
      width: 11,
      height: 11,
      borderRadius: "999px",
      background: toneColor[it.tone],
      color: "#fff",
      fontSize: 7,
      display: "inline-flex",
      alignItems: "center",
      justifyContent: "center",
      flexShrink: 0
    }
  }, it.acct), /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: 8,
      fontWeight: 600,
      color: "var(--text-body)",
      overflow: "hidden",
      textOverflow: "ellipsis",
      whiteSpace: "nowrap"
    }
  }, it.t))))))), /*#__PURE__*/React.createElement("div", {
    style: {
      display: "flex",
      gap: 14,
      marginTop: 10,
      fontSize: 10,
      color: "var(--text-subtle)"
    }
  }, /*#__PURE__*/React.createElement("span", {
    style: {
      display: "inline-flex",
      alignItems: "center",
      gap: 4
    }
  }, /*#__PURE__*/React.createElement("span", {
    style: {
      width: 8,
      height: 8,
      borderRadius: 2,
      background: "var(--primary)"
    }
  }), "\u5DF2\u6392\u671F"), /*#__PURE__*/React.createElement("span", {
    style: {
      display: "inline-flex",
      alignItems: "center",
      gap: 4
    }
  }, /*#__PURE__*/React.createElement("span", {
    style: {
      width: 8,
      height: 8,
      borderRadius: 2,
      background: "var(--topicblue-default)"
    }
  }), "\u8DE8\u8D26\u53F7"), /*#__PURE__*/React.createElement("span", {
    style: {
      display: "inline-flex",
      alignItems: "center",
      gap: 4
    }
  }, /*#__PURE__*/React.createElement("span", {
    style: {
      width: 8,
      height: 8,
      borderRadius: 2,
      background: "var(--text-subtle)"
    }
  }), "\u8349\u7A3F\u5F85\u5B9A"))));
}

// 数据回填
function BackfillSection() {
  const {
    StatCard,
    Card,
    Button,
    Badge
  } = window.DesignSystem_71831b;
  const {
    actions
  } = useStudio();
  const [vals, setVals] = React.useState({
    views: "12480",
    likes: "1240",
    saves: "864",
    comments: "207"
  });
  const set = k => v => setVals(p => ({
    ...p,
    [k]: v
  }));
  return /*#__PURE__*/React.createElement("section", {
    style: {
      display: "flex",
      flexDirection: "column",
      gap: 10
    }
  }, /*#__PURE__*/React.createElement(PanelHead, {
    icon: "clipboard-pen",
    title: "\u6570\u636E\u56DE\u586B",
    sub: "\u53D1\u5E03\u540E\u5F55\u5165\u771F\u5B9E\u8868\u73B0\uFF0C\u6C89\u6DC0\u56DE\u98DE\u4E66 \u2192 \u8BAD\u7EC3\u4E0B\u4E00\u8F6E\u9009\u9898",
    right: /*#__PURE__*/React.createElement(Badge, {
      tone: "info"
    }, "\u6548\u679C\u53CD\u9988\u95ED\u73AF")
  }), /*#__PURE__*/React.createElement(Card, {
    padding: "md"
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      display: "grid",
      gridTemplateColumns: "repeat(4, 1fr)",
      gap: 12,
      marginBottom: 12
    }
  }, /*#__PURE__*/React.createElement(StatCard, {
    label: "\u5B9E\u9645\u6D4F\u89C8\u91CF",
    value: vals.views,
    editable: true,
    onValueChange: set("views")
  }), /*#__PURE__*/React.createElement(StatCard, {
    label: "\u70B9\u8D5E",
    value: vals.likes,
    editable: true,
    onValueChange: set("likes"),
    tone: "coral"
  }), /*#__PURE__*/React.createElement(StatCard, {
    label: "\u6536\u85CF",
    value: vals.saves,
    editable: true,
    onValueChange: set("saves"),
    tone: "success"
  }), /*#__PURE__*/React.createElement(StatCard, {
    label: "\u8BC4\u8BBA",
    value: vals.comments,
    editable: true,
    onValueChange: set("comments")
  })), /*#__PURE__*/React.createElement("div", {
    style: {
      display: "flex",
      justifyContent: "flex-end",
      gap: 8
    }
  }, /*#__PURE__*/React.createElement(Button, {
    variant: "ghost",
    size: "sm",
    onClick: () => actions.toast("📥 已从小红书后台导入近 7 天数据")
  }, "\u4ECE\u5C0F\u7EA2\u4E66\u540E\u53F0\u5BFC\u5165"), /*#__PURE__*/React.createElement(Button, {
    variant: "primary",
    size: "sm",
    leftIcon: /*#__PURE__*/React.createElement(Icon, {
      name: "cloud-upload",
      size: 13
    }),
    onClick: actions.backfillSave
  }, "\u4FDD\u5B58\u5E76\u540C\u6B65\u98DE\u4E66"))));
}

// 发布管线 · 回链闭环（待发布 → 已发布·回链 → 已回填）
function PublishPipeline({
  account
}) {
  const {
    Card,
    Badge,
    Button
  } = window.DesignSystem_71831b;
  const S = window.STUDIO;
  const filter = account ? account.initial : null;
  const q = filter ? S.publishQueue.filter(x => x.acct === filter) : S.publishQueue;
  const stages = [{
    key: "scheduled",
    label: "待发布",
    icon: "clock"
  }, {
    key: "published",
    label: "已发布 · 回链",
    icon: "link"
  }, {
    key: "measured",
    label: "已回填",
    icon: "check-circle-2"
  }];
  return /*#__PURE__*/React.createElement("section", {
    style: {
      display: "flex",
      flexDirection: "column",
      gap: 10
    }
  }, /*#__PURE__*/React.createElement(PanelHead, {
    icon: "git-branch",
    title: "\u53D1\u5E03\u7BA1\u7EBF \xB7 \u56DE\u94FE\u95ED\u73AF",
    sub: "\u5C0F\u7EA2\u4E66\u65E0\u5F00\u653E\u53D1\u5E03 API\uFF1A\u4EBA\u5DE5/\u534A\u81EA\u52A8\u53D1\u5E03\u540E\u8D34\u56DE\u94FE \u2192 \u62FF\u5230\u6570\u636E\u56DE\u586B",
    right: /*#__PURE__*/React.createElement(Badge, {
      tone: "info"
    }, "\u6700\u540E\u4E00\u516C\u91CC")
  }), /*#__PURE__*/React.createElement("div", {
    style: {
      display: "grid",
      gridTemplateColumns: "1fr 1fr 1fr",
      gap: 12
    }
  }, stages.map(st => {
    const items = q.filter(x => x.stage === st.key);
    return /*#__PURE__*/React.createElement(Card, {
      key: st.key,
      padding: "sm"
    }, /*#__PURE__*/React.createElement("div", {
      style: {
        display: "flex",
        alignItems: "center",
        gap: 6,
        marginBottom: 8
      }
    }, /*#__PURE__*/React.createElement(Icon, {
      name: st.icon,
      size: 13,
      color: "var(--text-muted)"
    }), /*#__PURE__*/React.createElement("span", {
      style: {
        fontSize: 11,
        fontWeight: 700
      }
    }, st.label), /*#__PURE__*/React.createElement("span", {
      style: {
        marginLeft: "auto",
        fontSize: 10,
        color: "var(--text-subtle)"
      }
    }, items.length)), /*#__PURE__*/React.createElement("div", {
      style: {
        display: "flex",
        flexDirection: "column",
        gap: 7
      }
    }, items.length === 0 && /*#__PURE__*/React.createElement("span", {
      style: {
        fontSize: 10,
        color: "var(--text-subtle)"
      }
    }, "\u2014"), items.map(it => /*#__PURE__*/React.createElement("div", {
      key: it.id,
      style: {
        border: "1px solid var(--border)",
        borderRadius: "var(--radius-sm)",
        padding: "7px 8px",
        background: "var(--oats-light)"
      }
    }, /*#__PURE__*/React.createElement("div", {
      style: {
        display: "flex",
        alignItems: "center",
        gap: 5
      }
    }, /*#__PURE__*/React.createElement("span", {
      style: {
        width: 14,
        height: 14,
        borderRadius: 999,
        background: "var(--accent-surface)",
        color: "var(--primary)",
        fontSize: 8,
        fontWeight: 700,
        display: "inline-flex",
        alignItems: "center",
        justifyContent: "center",
        flexShrink: 0
      }
    }, it.acct), /*#__PURE__*/React.createElement("span", {
      style: {
        fontSize: 10,
        fontWeight: 600,
        color: "var(--text-body)",
        overflow: "hidden",
        textOverflow: "ellipsis",
        whiteSpace: "nowrap"
      }
    }, it.title)), /*#__PURE__*/React.createElement("div", {
      style: {
        fontSize: 9,
        color: "var(--text-subtle)",
        marginTop: 3,
        overflow: "hidden",
        textOverflow: "ellipsis",
        whiteSpace: "nowrap"
      }
    }, it.link ? `🔗 ${it.link}` : it.time), st.key === "scheduled" && /*#__PURE__*/React.createElement(Button, {
      variant: "soft",
      size: "sm",
      block: true,
      style: {
        marginTop: 6
      },
      leftIcon: /*#__PURE__*/React.createElement(Icon, {
        name: "send",
        size: 11
      })
    }, "\u6807\u8BB0\u5DF2\u53D1 \xB7 \u8D34\u56DE\u94FE"), st.key === "published" && /*#__PURE__*/React.createElement(Button, {
      variant: "soft",
      size: "sm",
      block: true,
      style: {
        marginTop: 6
      },
      leftIcon: /*#__PURE__*/React.createElement(Icon, {
        name: "clipboard-pen",
        size: 11
      })
    }, "\u56DE\u586B\u6570\u636E")))));
  })));
}

// hosting: 会话内 (agent-driven, single conversation does everything)
function OpsInline() {
  const {
    Avatar,
    Card
  } = window.DesignSystem_71831b;
  const msgs = [{
    who: "user",
    text: "看下我账号本周的数据，再把下周露营选题排上。"
  }, {
    who: "ai",
    text: "已从飞书拉取近 7 天数据 👇",
    module: "stats"
  }, {
    who: "ai",
    text: "帮你拆解了本周最高赞笔记的套路，并排好了下周内容日历：",
    module: "cal"
  }, {
    who: "user",
    text: "「露营避坑」那篇发布了，帮我回填真实数据。"
  }, {
    who: "ai",
    text: "好的，录入后我会沉淀回飞书、用于优化下一轮选题：",
    module: "backfill"
  }];
  return /*#__PURE__*/React.createElement("div", {
    className: "cs",
    style: {
      flex: 1,
      overflowY: "auto",
      background: "var(--background)"
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      maxWidth: 760,
      margin: "0 auto",
      padding: 24,
      display: "flex",
      flexDirection: "column",
      gap: 16
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      textAlign: "center",
      fontSize: "var(--text-xs)",
      color: "var(--text-subtle)",
      background: "var(--oats-dark)",
      borderRadius: 999,
      padding: "5px 12px",
      alignSelf: "center"
    }
  }, "\u4E00\u4E2A\u4F1A\u8BDD\u91CC\u5B8C\u6210\u5168\u90E8\u8FD0\u8425\u52A8\u4F5C \xB7 agent \u9A71\u52A8"), msgs.map((m, i) => m.who === "user" ? /*#__PURE__*/React.createElement("div", {
    key: i,
    style: {
      display: "flex",
      gap: 11,
      alignSelf: "flex-end",
      flexDirection: "row-reverse",
      maxWidth: "85%"
    }
  }, /*#__PURE__*/React.createElement(Avatar, {
    name: "\u6211",
    variant: "solid",
    size: 30
  }), /*#__PURE__*/React.createElement("div", {
    style: {
      background: "var(--surface-card)",
      border: "1px solid var(--border-coral)",
      borderRadius: "var(--radius-xl)",
      padding: "11px 15px",
      fontSize: "var(--text-sm)",
      boxShadow: "var(--shadow-sm)"
    }
  }, m.text)) : /*#__PURE__*/React.createElement("div", {
    key: i,
    style: {
      display: "flex",
      gap: 11,
      maxWidth: "94%"
    }
  }, /*#__PURE__*/React.createElement(Avatar, {
    glyph: "\uD83C\uDF60",
    variant: "agent",
    size: 32
  }), /*#__PURE__*/React.createElement("div", {
    style: {
      flex: 1,
      display: "flex",
      flexDirection: "column",
      gap: 9,
      minWidth: 0
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      background: "var(--surface-card)",
      border: "1px solid var(--border-coral)",
      borderRadius: "var(--radius-xl)",
      padding: "11px 15px",
      fontSize: "var(--text-sm)",
      boxShadow: "var(--shadow-sm)",
      alignSelf: "flex-start"
    }
  }, m.text), m.module === "stats" && /*#__PURE__*/React.createElement(StatsMini, null), m.module === "cal" && /*#__PURE__*/React.createElement(Card, {
    padding: "md"
  }, /*#__PURE__*/React.createElement(CalInline, null)), m.module === "backfill" && /*#__PURE__*/React.createElement(BackfillSection, null))))));
}
function StatsMini() {
  const {
    StatCard
  } = window.DesignSystem_71831b;
  const S = window.STUDIO;
  return /*#__PURE__*/React.createElement("div", {
    style: {
      display: "grid",
      gridTemplateColumns: "repeat(4, 1fr)",
      gap: 10
    }
  }, S.dashboard.map(d => /*#__PURE__*/React.createElement(StatCard, {
    key: d.label,
    label: d.label,
    value: d.value,
    unit: d.unit,
    delta: d.delta,
    tone: d.tone,
    icon: /*#__PURE__*/React.createElement(Icon, {
      name: d.icon,
      size: 15
    })
  })));
}
function CalInline() {
  return /*#__PURE__*/React.createElement(CalendarSection, null);
}

// hosting: 同屏融合 (chat + dashboard side by side)
function OpsHybrid() {
  const {
    Avatar,
    Textarea,
    Button
  } = window.DesignSystem_71831b;
  return /*#__PURE__*/React.createElement("div", {
    style: {
      flex: 1,
      display: "flex",
      minHeight: 0,
      background: "var(--background)"
    }
  }, /*#__PURE__*/React.createElement("section", {
    style: {
      width: 380,
      borderRight: "1px solid var(--border)",
      background: "var(--surface-card)",
      display: "flex",
      flexDirection: "column",
      flexShrink: 0
    }
  }, /*#__PURE__*/React.createElement("div", {
    className: "cs",
    style: {
      flex: 1,
      overflowY: "auto",
      padding: 18,
      display: "flex",
      flexDirection: "column",
      gap: 14
    }
  }, /*#__PURE__*/React.createElement(PanelHead, {
    icon: "bot",
    title: "\u8FD0\u8425\u52A9\u624B",
    sub: "\u53D1\u8D77\u52A8\u4F5C \xB7 \u53F3\u4FA7\u770B\u6C47\u603B"
  }), [{
    who: "user",
    t: "拉本周数据 + 排下周选题"
  }, {
    who: "ai",
    t: "已更新右侧看板与日历 ✅ 最高赞是「搬家式装备清单」，套路已拆解。"
  }, {
    who: "user",
    t: "把避坑那篇的真实数据回填一下"
  }, {
    who: "ai",
    t: "右侧「数据回填」已就绪，录入后同步飞书。"
  }].map((m, i) => /*#__PURE__*/React.createElement("div", {
    key: i,
    style: {
      display: "flex",
      gap: 9,
      flexDirection: m.who === "user" ? "row-reverse" : "row"
    }
  }, m.who === "user" ? /*#__PURE__*/React.createElement(Avatar, {
    name: "\u6211",
    variant: "solid",
    size: 26
  }) : /*#__PURE__*/React.createElement(Avatar, {
    glyph: "\uD83C\uDF60",
    variant: "agent",
    size: 26
  }), /*#__PURE__*/React.createElement("div", {
    style: {
      background: m.who === "user" ? "var(--accent-surface)" : "var(--oats-light)",
      border: "1px solid var(--border)",
      borderRadius: "var(--radius-md)",
      padding: "8px 11px",
      fontSize: "var(--text-xs)",
      lineHeight: 1.5
    }
  }, m.t)))), /*#__PURE__*/React.createElement("div", {
    style: {
      padding: 14,
      borderTop: "1px solid var(--border)"
    }
  }, /*#__PURE__*/React.createElement(Textarea, {
    rows: 1,
    placeholder: "\u53D1\u8D77\u8FD0\u8425\u52A8\u4F5C\u2026",
    footer: /*#__PURE__*/React.createElement(React.Fragment, null, /*#__PURE__*/React.createElement("span", {
      style: {
        fontSize: 10,
        color: "var(--text-subtle)"
      }
    }, "agent \u4F1A\u66F4\u65B0\u53F3\u4FA7\u770B\u677F"), /*#__PURE__*/React.createElement(Button, {
      variant: "primary",
      size: "sm"
    }, "\u53D1\u9001"))
  }))), /*#__PURE__*/React.createElement("div", {
    className: "cs",
    style: {
      flex: 1,
      overflowY: "auto"
    }
  }, /*#__PURE__*/React.createElement(DashboardBody, {
    dense: true
  })));
}
Object.assign(window, {
  Operations
});
})(); } catch (e) { __ds_ns.__errors.push({ path: "ui_kits/studio/Operations.jsx", error: String((e && e.message) || e) }); }

// ui_kits/studio/Shell.jsx
try { (() => {
// Studio shell — top bar with brand, section switcher, account chip;
// and the recents sidebar reused by the creation/deep screens.
function StudioTopBar({
  section,
  setSection
}) {
  const {
    Badge,
    Avatar
  } = window.DesignSystem_71831b;
  const S = window.STUDIO;
  const sections = [{
    id: "create",
    label: "创作",
    icon: "pen-line"
  }, {
    id: "ops",
    label: "账号运营",
    icon: "line-chart"
  }];
  return /*#__PURE__*/React.createElement("header", {
    style: {
      height: 56,
      background: "rgba(255,255,255,0.88)",
      backdropFilter: "blur(8px)",
      borderBottom: "1px solid var(--border)",
      padding: "0 20px",
      display: "flex",
      alignItems: "center",
      justifyContent: "space-between",
      flexShrink: 0,
      zIndex: 20
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      display: "flex",
      alignItems: "center",
      gap: 18
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      display: "flex",
      alignItems: "center",
      gap: 9
    }
  }, /*#__PURE__*/React.createElement("span", {
    style: {
      width: 30,
      height: 30,
      borderRadius: "var(--radius-md)",
      background: "var(--coral-brand)",
      display: "flex",
      alignItems: "center",
      justifyContent: "center",
      fontSize: 16,
      boxShadow: "var(--shadow-coral)"
    }
  }, "\uD83C\uDF60"), /*#__PURE__*/React.createElement("span", {
    style: {
      fontFamily: "var(--font-display)",
      fontWeight: 800,
      fontSize: "var(--text-base)",
      letterSpacing: "var(--tracking-tight)"
    }
  }, "\u5C0F\u7EA2\u4E66\u521B\u4F5C\u8FD0\u8425\u5DE5\u4F5C\u5BA4")), /*#__PURE__*/React.createElement("nav", {
    style: {
      display: "flex",
      gap: 2,
      background: "var(--oats-dark)",
      borderRadius: "var(--radius-md)",
      padding: 3
    }
  }, sections.map(s => {
    const on = section === s.id || s.id === "create" && section === "deep";
    return /*#__PURE__*/React.createElement("button", {
      key: s.id,
      onClick: () => setSection(s.id),
      style: {
        display: "inline-flex",
        alignItems: "center",
        gap: 6,
        padding: "6px 12px",
        borderRadius: "var(--radius-sm)",
        border: "none",
        cursor: "pointer",
        fontFamily: "var(--font-sans)",
        fontSize: "var(--text-xs)",
        fontWeight: on ? 700 : 500,
        background: on ? "var(--surface-card)" : "transparent",
        color: on ? "var(--primary)" : "var(--text-muted)",
        boxShadow: on ? "var(--shadow-xs)" : "none"
      }
    }, /*#__PURE__*/React.createElement(Icon, {
      name: s.icon,
      size: 14
    }), " ", s.label);
  }))), /*#__PURE__*/React.createElement("div", {
    style: {
      display: "flex",
      alignItems: "center",
      gap: 14
    }
  }, /*#__PURE__*/React.createElement(Badge, {
    tone: "synced",
    dot: true
  }, "\u98DE\u4E66 CLI \xB7 Ready"), /*#__PURE__*/React.createElement("div", {
    style: {
      display: "flex",
      alignItems: "center",
      gap: 8
    }
  }, /*#__PURE__*/React.createElement(Avatar, {
    name: "Z",
    size: 28
  }), /*#__PURE__*/React.createElement("div", {
    style: {
      lineHeight: 1.25
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: "var(--text-xs)",
      fontWeight: 600
    }
  }, S.user.handle), /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: 10,
      color: "var(--text-subtle)"
    }
  }, "\u7C89\u4E1D ", S.user.fans, " \xB7 ", S.user.team)))));
}
function Recents({
  activeId,
  onSelect,
  onNew,
  compact = false
}) {
  const {
    Button,
    Badge
  } = window.DesignSystem_71831b;
  const S = window.STUDIO;
  return /*#__PURE__*/React.createElement("aside", {
    style: {
      width: compact ? 220 : 260,
      background: "var(--surface-sidebar)",
      borderRight: "1px solid var(--border)",
      display: "flex",
      flexDirection: "column",
      flexShrink: 0
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      padding: 14,
      display: "flex",
      flexDirection: "column",
      gap: 14,
      flex: 1,
      overflow: "hidden"
    }
  }, /*#__PURE__*/React.createElement(Button, {
    variant: "primary",
    block: true,
    size: "sm",
    leftIcon: /*#__PURE__*/React.createElement(Icon, {
      name: "square-pen",
      size: 15
    }),
    onClick: onNew
  }, "\u5F00\u542F\u5168\u65B0\u7075\u611F\u5BF9\u8BDD"), /*#__PURE__*/React.createElement(Eyebrow, null, "\u6700\u8FD1\u521B\u4F5C"), /*#__PURE__*/React.createElement("div", {
    className: "cs",
    style: {
      display: "flex",
      flexDirection: "column",
      gap: 4,
      overflowY: "auto"
    }
  }, S.recents.map(r => {
    const on = r.id === activeId;
    return /*#__PURE__*/React.createElement("button", {
      key: r.id,
      onClick: () => onSelect(r.id),
      style: {
        display: "flex",
        alignItems: "center",
        justifyContent: "space-between",
        gap: 8,
        width: "100%",
        textAlign: "left",
        padding: "9px 11px",
        fontSize: "var(--text-sm)",
        borderRadius: "var(--radius-sm)",
        cursor: "pointer",
        border: "none",
        borderLeft: on ? "2px solid var(--primary)" : "2px solid transparent",
        background: on ? "var(--oats-dark)" : "transparent",
        color: on ? "var(--primary)" : "var(--text-muted)",
        fontWeight: on ? 600 : 400
      }
    }, /*#__PURE__*/React.createElement("span", {
      style: {
        overflow: "hidden",
        textOverflow: "ellipsis",
        whiteSpace: "nowrap"
      }
    }, r.icon, " ", r.title), /*#__PURE__*/React.createElement(Badge, {
      tone: r.status === "synced" ? "synced" : "draft",
      shape: "chip"
    }, r.status === "synced" ? "已同步" : "草稿"));
  }))));
}
Object.assign(window, {
  StudioTopBar,
  Recents
});
})(); } catch (e) { __ds_ns.__errors.push({ path: "ui_kits/studio/Shell.jsx", error: String((e && e.message) || e) }); }

// ui_kits/studio/app.jsx
try { (() => {
// Root — shared note store (one note flows across the 3 sections) +
// Tweaks for the explore-decisions.
const TWEAK_DEFAULTS = /*EDITMODE-BEGIN*/{
  "rightLayout": "stack",
  "deepForm": "immersive",
  "opsHosting": "page"
} /*EDITMODE-END*/;
const WD = ["一", "二", "三", "四", "五", "六", "日"];

// Scale-to-fit: the workbench is designed at 1360px wide; on a narrower
// viewport it scales down uniformly (letterboxed) so the full three-pane
// layout is always visible & proportional instead of cramped + scrolling.
function Scaler({
  children
}) {
  const [s, setS] = React.useState(1);
  React.useEffect(() => {
    const calc = () => setS(Math.min(1, window.innerWidth / 1360));
    calc();
    window.addEventListener("resize", calc);
    return () => window.removeEventListener("resize", calc);
  }, []);
  return /*#__PURE__*/React.createElement("div", {
    style: {
      width: "100vw",
      height: "100vh",
      overflow: "hidden",
      background: "var(--oats-dark)",
      display: "flex",
      justifyContent: "center"
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      width: 1360,
      height: `calc(100vh / ${s})`,
      flexShrink: 0,
      transform: `scale(${s})`,
      transformOrigin: "top center"
    }
  }, children));
}
function StudioApp() {
  const S = window.STUDIO;
  const [t, setTweak] = useTweaks(TWEAK_DEFAULTS);
  const [section, setSection] = React.useState("create");
  const [activeRecent, setActiveRecent] = React.useState(1);
  const [note, setNote] = React.useState({
    topicId: null,
    kw: "",
    title: "",
    body: "",
    tags: [],
    cover: "",
    status: "idle",
    activeVersion: "A",
    versions: null
  });
  const [calendar, setCalendar] = React.useState(S.calendar);
  const [chatExtra, setChatExtra] = React.useState([]);
  const [toast, setToast] = React.useState(null);
  const [selectedEvidence, setSelectedEvidence] = React.useState(null);
  const streamRef = React.useRef(null);
  const toastRef = React.useRef(null);
  const showToast = msg => {
    setToast(msg);
    clearTimeout(toastRef.current);
    toastRef.current = setTimeout(() => setToast(null), 2800);
  };
  React.useEffect(() => {
    const onKey = e => {
      if (e.key === "Escape") setSelectedEvidence(null);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  // 选题卡 → 创作栏：stream a real draft in
  const chooseTopic = (topic, goSection = "create") => {
    clearInterval(streamRef.current);
    const versions = buildVersions(topic);
    const full = versions.A;
    setSection(goSection);
    setActiveRecent(topic.id);
    setChatExtra([{
      who: "user",
      text: `写第 ${topic.id} 个：${topic.title}`
    }, {
      who: "ai",
      thinking: true,
      text: `正在按小红书风格撰写《${topic.title}》，右侧创作栏流式生成中…`
    }]);
    setNote({
      topicId: topic.id,
      kw: topic.kw,
      title: "",
      body: "",
      tags: [],
      cover: full.cover,
      status: "writing",
      activeVersion: "A",
      versions
    });
    setTimeout(() => setNote(n => n.topicId === topic.id ? {
      ...n,
      title: full.title
    } : n), 220);
    let i = 0;
    setTimeout(() => {
      streamRef.current = setInterval(() => {
        i += 6;
        const done = i >= full.body.length;
        setNote(n => n.topicId !== topic.id ? n : {
          ...n,
          body: full.body.slice(0, i),
          tags: done ? full.tags : n.tags,
          status: done ? "draft" : "writing"
        });
        if (done) {
          clearInterval(streamRef.current);
          setChatExtra(prev => prev.map(m => m.thinking ? {
            who: "ai",
            text: `✅ 已生成《${full.title}》草稿。右侧可继续精修，文案体检达标即可定稿排期 →`
          } : m));
        }
      }, 22);
    }, 420);
  };
  const setVersion = v => setNote(n => {
    if (!n.versions) return n;
    const ver = n.versions[v];
    return {
      ...n,
      title: ver.title,
      body: ver.body,
      tags: ver.tags,
      cover: ver.cover,
      activeVersion: v,
      status: "draft"
    };
  });
  const updateField = (f, val) => setNote(n => ({
    ...n,
    [f]: val,
    status: n.status === "writing" ? "writing" : "draft"
  }));
  const addTag = tag => setNote(n => n.tags.includes(tag) ? n : {
    ...n,
    tags: [...n.tags, tag].slice(0, 10),
    status: "draft"
  });
  const removeTag = tag => setNote(n => ({
    ...n,
    tags: n.tags.filter(x => x !== tag),
    status: "draft"
  }));
  const polish = () => {
    setNote(n => {
      if (!n.title) return n;
      const hook = "⛺ 夏日露营天花板，姐妹们冲鸭！✨\n\n";
      const body = n.body.startsWith("⛺ 夏日露营天花板") ? n.body : hook + n.body;
      const title = /\p{Extended_Pictographic}/u.test(n.title) || n.title.length > 18 ? n.title : n.title + " ✨";
      return {
        ...n,
        body,
        title,
        status: "draft"
      };
    });
    showToast("🍠 已按小红书语气润色，更有种草感 ✨");
  };
  const shorten = () => {
    setNote(n => {
      if (!n.body) return n;
      const tagline = n.tags.slice(0, 4).map(x => "#" + x).join(" ");
      return {
        ...n,
        body: n.body.slice(0, 240).trimEnd() + "…\n\n" + tagline,
        status: "draft"
      };
    });
    showToast("✂️ 已瘦身到精华段落");
  };
  const addTags = () => {
    setNote(n => {
      const add = S.recommendedTags.filter(x => !n.tags.includes(x) && x.length >= 4).slice(0, 2);
      return {
        ...n,
        tags: [...n.tags, ...add].slice(0, 10),
        status: "draft"
      };
    });
    showToast("# 已补充长尾话题标签");
  };
  const schedule = date => {
    setCalendar(cal => {
      const item = {
        t: (note.title || "新笔记").slice(0, 8),
        time: "19:00",
        tone: "coral",
        acct: "露"
      };
      return cal.some(d => d.date === date) ? cal.map(d => d.date === date ? {
        ...d,
        items: [...d.items, item]
      } : d) : [...cal, {
        date,
        items: [item]
      }];
    });
    setNote(n => ({
      ...n,
      status: "scheduled"
    }));
    showToast(`📅 已定稿并排期到 6 月 ${date} 日 19:00`);
  };
  const syncFeishu = () => showToast("🔗 已同步至飞书多维表格");
  const backfillSave = () => showToast("💾 真实数据已回填并沉淀飞书，将用于优化下一轮选题");
  const reuse = topicId => {
    const topic = S.topics.find(x => x.id === topicId);
    if (topic) chooseTopic(topic);
  };
  const newChat = () => {
    clearInterval(streamRef.current);
    setNote({
      topicId: null,
      kw: "",
      title: "",
      body: "",
      tags: [],
      cover: "",
      status: "idle",
      activeVersion: "A",
      versions: null
    });
    setChatExtra([]);
    setSection("create");
    showToast("🆕 已开启新的创作会话");
  };
  const say = text => {
    setChatExtra(prev => [...prev, {
      who: "user",
      text
    }, {
      who: "ai",
      text: "收到～已结合你的补充在数据底座重新检索，更新了右侧选题卡 👉"
    }]);
  };
  const store = {
    section,
    setSection,
    activeRecent,
    setActiveRecent,
    note,
    calendar,
    chatExtra,
    selectedEvidence,
    actions: {
      chooseTopic,
      setVersion,
      updateField,
      addTag,
      removeTag,
      polish,
      shorten,
      addTags,
      schedule,
      syncFeishu,
      backfillSave,
      reuse,
      newChat,
      say,
      toast: showToast,
      openEvidence: setSelectedEvidence,
      closeEvidence: () => setSelectedEvidence(null)
    }
  };
  return /*#__PURE__*/React.createElement(StudioContext.Provider, {
    value: store
  }, /*#__PURE__*/React.createElement(Scaler, null, /*#__PURE__*/React.createElement("div", {
    style: {
      height: "100%",
      width: "100%",
      display: "flex",
      flexDirection: "column",
      overflow: "hidden",
      fontFamily: "var(--font-sans)",
      color: "var(--text-body)",
      background: "var(--background)"
    }
  }, section !== "deep" && /*#__PURE__*/React.createElement(StudioTopBar, {
    section: section,
    setSection: setSection
  }), /*#__PURE__*/React.createElement("div", {
    key: section,
    style: {
      flex: 1,
      display: "flex",
      flexDirection: "column",
      minHeight: 0,
      animation: "secIn 0.3s var(--ease-out)"
    }
  }, section === "create" && /*#__PURE__*/React.createElement(CreationScreen, {
    rightLayout: t.rightLayout
  }), section === "deep" && /*#__PURE__*/React.createElement(DeepCreation, {
    form: t.deepForm
  }), section === "ops" && /*#__PURE__*/React.createElement(Operations, {
    hosting: t.opsHosting
  })), toast && /*#__PURE__*/React.createElement("div", {
    style: {
      position: "fixed",
      bottom: 26,
      left: "50%",
      transform: "translateX(-50%)",
      background: "var(--charcoal-default)",
      color: "#fff",
      padding: "11px 18px",
      borderRadius: "var(--radius-full)",
      fontSize: "var(--text-sm)",
      fontWeight: 500,
      boxShadow: "var(--shadow-lg)",
      zIndex: 60,
      animation: "toastIn 0.3s var(--ease-out)"
    }
  }, toast), selectedEvidence && /*#__PURE__*/React.createElement(EvidencePanel, null))), /*#__PURE__*/React.createElement(TweaksPanel, {
    title: "Tweaks \xB7 \u65B9\u6848\u63A2\u7D22"
  }, /*#__PURE__*/React.createElement(TweakSection, {
    label: "\u2460 \u521B\u4F5C \xB7 \u53F3\u4FA7\u5E03\u5C40\uFF08\u9009\u9898\u5361 + \u521B\u4F5C\u680F\uFF09"
  }), /*#__PURE__*/React.createElement(TweakRadio, {
    label: "\u5E03\u5C40",
    value: t.rightLayout,
    options: [{
      value: "stack",
      label: "上下堆叠"
    }, {
      value: "split",
      label: "左右分栏"
    }, {
      value: "composer",
      label: "仅创作栏"
    }],
    onChange: v => {
      setTweak("rightLayout", v);
      setSection("create");
    }
  }), /*#__PURE__*/React.createElement(TweakSection, {
    label: "\u2461 \u6DF1\u5EA6\u521B\u4F5C \xB7 \u5F62\u6001"
  }), /*#__PURE__*/React.createElement(TweakRadio, {
    label: "\u5F62\u6001",
    value: t.deepForm,
    options: [{
      value: "immersive",
      label: "沉浸双栏"
    }, {
      value: "flow",
      label: "分步流程"
    }, {
      value: "workspace",
      label: "多栏工作台"
    }],
    onChange: v => {
      setTweak("deepForm", v);
      setSection("deep");
    }
  }), /*#__PURE__*/React.createElement(TweakSection, {
    label: "\u2462 \u8D26\u53F7\u8FD0\u8425 \xB7 \u627F\u8F7D\u65B9\u5F0F"
  }), /*#__PURE__*/React.createElement(TweakRadio, {
    label: "\u627F\u8F7D",
    value: t.opsHosting,
    options: [{
      value: "page",
      label: "独立页面"
    }, {
      value: "inline",
      label: "会话内"
    }, {
      value: "hybrid",
      label: "同屏融合"
    }],
    onChange: v => {
      setTweak("opsHosting", v);
      setSection("ops");
    }
  })));
}
ReactDOM.createRoot(document.getElementById("root")).render(/*#__PURE__*/React.createElement(StudioApp, null));
})(); } catch (e) { __ds_ns.__errors.push({ path: "ui_kits/studio/app.jsx", error: String((e && e.message) || e) }); }

// ui_kits/studio/data.js
try { (() => {
// Content for the 小红书创作运营工作室 (Studio) prototype.
window.STUDIO = {
  user: {
    name: "张潇潇",
    team: "运营组",
    initial: "Z",
    handle: "@潇潇的露营笔记",
    fans: "2.4w"
  },
  images: ["https://images.unsplash.com/photo-1504280390367-361c6d9f38f4?auto=format&fit=crop&w=600&q=80", "https://images.unsplash.com/photo-1523987355523-c7b5b0dd90a7?auto=format&fit=crop&w=600&q=80", "https://images.unsplash.com/photo-1510312305653-8ed496efae75?auto=format&fit=crop&w=600&q=80"],
  recents: [{
    id: 1,
    icon: "⛺",
    title: "露营装备好物推荐",
    status: "synced"
  }, {
    id: 2,
    icon: "☕",
    title: "咖啡探店爆款草稿",
    status: "draft"
  }, {
    id: 3,
    icon: "👗",
    title: "夏季轻熟风穿搭笔记",
    status: "draft"
  }],
  // Viral topic suggestions. Each carries a full version-A draft so a
  // click can stream a real note into the composer.
  topics: [{
    id: 1,
    title: "精致露营「搬家式」装备清单",
    rationale: "视觉冲击 · 高分享率 · 赞藏比极高",
    hotRate: 96,
    angle: "种草清单",
    kw: "露营装备",
    emotional: "把山野过成向往的生活",
    draft: {
      title: "精致露营搬家式装备清单｜少带一件都后悔",
      cover: "搬家式露营\n必带清单",
      body: `夏天太适合露营啦！⛺ 作为一个精致的搬家式露营玩家，带什么装备真的大有讲究！今天把我私藏的露营装备好物全分享给你们，少带一件体验感都打折！

👇 精致露营必带清单：
1️⃣ 双顶充气天幕：防雨防晒，拍照超出片，8 人也宽敞
2️⃣ 蛋卷桌 + 月亮椅：精致露营的灵魂，放上咖啡机格调拉满
3️⃣ 氛围串灯 / 汽灯：天黑挂起暖黄灯串，氛围感封神 ✨
4️⃣ 便携制冰机：山野里来一口冰冷萃，这就是向往的生活

📝 挑选 TIPS：买前先看折叠收纳体积！我后备箱就是这么满的（笑哭）

你还有什么露营神器？评论区一起交流呀～`,
      tags: ["精致露营", "露营清单", "户外好物", "露营装备", "周末去哪儿", "搬家式露营"]
    }
  }, {
    id: 2,
    title: "百元搞定！新手露营避坑极简装备",
    rationale: "强实用 · 痛点防坑 · 收藏导向",
    hotRate: 92,
    angle: "避坑干货",
    kw: "新手露营",
    emotional: "第一次露营也能很从容",
    draft: {
      title: "百元搞定！新手露营避坑极简清单",
      cover: "新手露营\n避坑清单",
      body: `别被大几千的装备劝退！新手第一次露营，主打性价比和实用 ✅ 今天教你用几百块搞定一整套，少花冤枉钱！

❌ 千万别买的雷区：
- 百元以下简易帐篷：防雨差、一吹就倒
- 巨重实木蛋卷桌：搬一次就想扔

✅ 闭眼入平替清单：
1️⃣ 自动速开帐篷（￥200）：省心省力不满头汗
2️⃣ 铝合金桌 + 月亮椅（￥150）：轻便好带、坐着舒服
3️⃣ 防风卡式炉（￥50）：煮面烧水性价比天花板

觉得有用赶紧收藏，露营时翻出来对着买！`,
      tags: ["新手露营", "露营避坑", "性价比", "露营装备", "省钱攻略"]
    }
  }, {
    id: 3,
    title: "山野落日下的星空篝火美学",
    rationale: "视觉种草 · 情绪共鸣 · 高吸睛",
    hotRate: 88,
    angle: "氛围情绪",
    kw: "露营氛围感",
    emotional: "在山野落日里把日子过成诗",
    draft: {
      title: "山野落日 + 星空篝火，氛围感封神 🌅",
      cover: "落日篝火\n氛围感",
      body: `当太阳缓缓落进山头，把整片山野染成蜜橘色的那一刻，我就知道这趟露营值了。🌅

夜幕降临，串灯亮起，篝火噼啪作响，朋友围坐聊到深夜——这种慢下来的露营氛围感，才是真正的奢侈。✨

📷 出片小心机：
1️⃣ 落日逆光拍剪影，氛围拉满
2️⃣ 串灯绕在天幕支架，夜景随手出片
3️⃣ 篝火 + 热饮特写，温暖治愈

愿你也能在山野里，找到属于自己的星空。点赞收藏，下次照着拍 🌿`,
      tags: ["露营氛围感", "星空露营", "落日", "治愈系", "露营拍照"]
    }
  }],
  recommendedTags: ["新手必看", "露营好物", "氛围感", "夏日露营", "搬家式露营", "露营避坑指南", "周末去哪儿", "出片攻略"],
  quickEmoji: ["🍠", "⛺", "☕", "✨", "🌿", "👇", "📝", "🔥", "🌅", "✅", "❌", "1️⃣", "2️⃣", "💛"],
  // ── 账号运营 ──
  dashboard: [{
    label: "点赞",
    value: "1.2k",
    delta: 18,
    tone: "coral",
    icon: "heart"
  }, {
    label: "收藏",
    value: "864",
    delta: 32,
    tone: "success",
    icon: "star"
  }, {
    label: "评论",
    value: "207",
    delta: -4,
    tone: "neutral",
    icon: "message-square"
  }, {
    label: "新增粉丝",
    value: "312",
    unit: "人",
    delta: 26,
    tone: "topic",
    icon: "user-plus"
  }],
  library: [{
    id: 1,
    title: "精致露营搬家式装备清单",
    angle: "种草清单",
    hot: 96,
    likes: "3.2w",
    saves: "1.8w",
    status: "已发布"
  }, {
    id: 2,
    title: "新手露营避坑极简装备",
    angle: "避坑干货",
    hot: 92,
    likes: "2.1w",
    saves: "2.4w",
    status: "排期中"
  }, {
    id: 3,
    title: "山野落日星空篝火美学",
    angle: "氛围情绪",
    hot: 88,
    likes: "1.5w",
    saves: "6.2k",
    status: "草稿"
  }, {
    id: 4,
    title: "露营咖啡仪式感 3 件套",
    angle: "好物种草",
    hot: 85,
    likes: "9.8k",
    saves: "7.1k",
    status: "草稿"
  }],
  teardown: {
    title: "精致露营搬家式装备清单",
    points: [{
      label: "标题",
      detail: "「精致」+「搬家式」身份标签 + 痛点暗示，搜索词「露营装备」前置"
    }, {
      label: "封面",
      detail: "暖色实拍大全景 + 4 字大字报，信息密度高"
    }, {
      label: "结构",
      detail: "共情钩子 → 编号清单 → 选购 TIPS → 互动收口"
    }, {
      label: "标签",
      detail: "大词(露营) + 中词(精致露营) + 长尾(搬家式露营) 矩阵"
    }]
  },
  weekdays: ["一", "二", "三", "四", "五", "六", "日"],
  month: {
    label: "2026 年 6 月",
    days: 30,
    firstOffset: 0
  },
  calendar: [{
    date: 4,
    items: [{
      t: "露营避坑装备",
      time: "19:30",
      tone: "coral",
      acct: "露"
    }]
  }, {
    date: 6,
    items: [{
      t: "咖啡仪式感",
      time: "12:00",
      tone: "topic",
      acct: "咖"
    }]
  }, {
    date: 11,
    items: [{
      t: "轻熟风穿搭",
      time: "20:00",
      tone: "draft",
      acct: "穿"
    }]
  }, {
    date: 14,
    items: [{
      t: "落日篝火美学",
      time: "18:00",
      tone: "coral",
      acct: "露"
    }, {
      t: "山野炉饭",
      time: "21:00",
      tone: "draft",
      acct: "食"
    }]
  }, {
    date: 18,
    items: [{
      t: "防晒装备测评",
      time: "19:00",
      tone: "coral",
      acct: "露"
    }]
  }, {
    date: 22,
    items: [{
      t: "公园露营 vlog",
      time: "20:30",
      tone: "topic",
      acct: "露"
    }]
  }, {
    date: 25,
    items: [{
      t: "一人露营",
      time: "19:00",
      tone: "draft",
      acct: "露"
    }]
  }]
};

// 热点趋势雷达（外部实时信号，区别于内部历史沉淀；探索 exploration 的输入）
window.STUDIO.trends = [{
  tag: "防晒装备",
  rising: 210,
  heat: "爆",
  note: "季节性 · 夏季峰值",
  tone: "hot"
}, {
  tag: "公园露营",
  rising: 132,
  heat: "高",
  note: "城市近郊 · 低门槛",
  tone: "coral"
}, {
  tag: "露营咖啡",
  rising: 88,
  heat: "中",
  note: "仪式感 · 出片",
  tone: "topic"
}, {
  tag: "一人露营",
  rising: 64,
  heat: "中",
  note: "孤独经济 · 上升",
  tone: "topic"
}];

// 图集角色（小红书是图文：封面权重 > 正文）
window.STUDIO.imageRoles = ["封面 · 大字报", "产品特写", "场景氛围", "清单合影", "选购对比"];

// 发布 → 回链 → 回填 状态机（打通效果闭环最后一公里；小红书无开放发布 API）
window.STUDIO.publishQueue = [{
  id: 1,
  title: "新手露营避坑极简清单",
  acct: "露",
  stage: "scheduled",
  time: "周二 19:30"
}, {
  id: 2,
  title: "露营咖啡仪式感 3 件套",
  acct: "咖",
  stage: "published",
  link: "xhslink.com/a/8Kd2",
  time: "06-26 已发"
}, {
  id: 3,
  title: "精致露营搬家式装备清单",
  acct: "露",
  stage: "measured",
  link: "xhslink.com/a/3Fa9",
  time: "06-20 已回填"
}];

// 多账号矩阵（账号作为一等公民：各自垂类/人设/粉丝/状态）
window.STUDIO.accounts = [{
  id: "camp",
  handle: "@潇潇的露营笔记",
  niche: "露营 / 户外",
  initial: "露",
  fans: "2.4w",
  fansNum: 24000,
  dFans: 312,
  posts: 12,
  hot: 91,
  status: "主力",
  tone: "coral"
}, {
  id: "outfit",
  handle: "@轻熟风穿搭笔记",
  niche: "穿搭 / 时尚",
  initial: "穿",
  fans: "1.9w",
  fansNum: 19000,
  dFans: 540,
  posts: 15,
  hot: 88,
  status: "主力",
  tone: "coral"
}, {
  id: "coffee",
  handle: "@潇潇的咖啡日记",
  niche: "咖啡 / 探店",
  initial: "咖",
  fans: "8,600",
  fansNum: 8600,
  dFans: 120,
  posts: 8,
  hot: 84,
  status: "成长",
  tone: "topic"
}, {
  id: "food",
  handle: "@山野食验室",
  niche: "露营美食",
  initial: "食",
  fans: "4,200",
  fansNum: 4200,
  dFans: 88,
  posts: 6,
  hot: 79,
  status: "孵化",
  tone: "draft"
}];

// ── 创作依据（数据底座检索到的资源 + rank_evidence 三信号）──
// 对齐 evidence.py 的 EvidenceItem 契约：source_updated_at vs indexed_at、
// score、why_selected；retrieval_mode ∈ semantic/keyword_fallback/insufficient_relevance。
window.STUDIO.evidence = {
  1: {
    mode: "semantic",
    items: [{
      resource_id: "res_note_0421",
      type: "爆款笔记",
      title: "搬家式露营装备清单（多维表格 第 4 行）",
      summary: "赞 3.2w · 藏 1.8w，赞藏比 0.56；「天幕 / 蛋卷桌 / 氛围灯」为高频单品。",
      score: 0.9132,
      relevance: 0.94,
      freshness: 0.82,
      performance: 0.88,
      source_updated_at: "2026-06-20",
      indexed_at: "2026-06-21",
      why_selected: "与「露营装备」语义最相关，且历史赞藏表现位列类目前 5%。"
    }, {
      resource_id: "res_perf_2207",
      type: "效果指标",
      title: "露营类目 · 近 30 天表现基线",
      summary: "收藏导向内容互动率高于类目均值 38%，清单体裁转发占比最高。",
      score: 0.7841,
      relevance: 0.71,
      freshness: 0.96,
      performance: 0.80,
      source_updated_at: "2026-06-27",
      indexed_at: "2026-06-27",
      why_selected: "提供时效性最强的类目表现基线，支撑「清单 + 收藏导向」判断。"
    }, {
      resource_id: "res_wiki_0098",
      type: "选品库 · Wiki",
      title: "露营选品笔记 · 天幕 / 蛋卷桌 / 氛围灯",
      summary: "各单品卖点与价格带，飞书 Wiki 接入沉淀。",
      score: 0.6627,
      relevance: 0.69,
      freshness: 0.74,
      performance: 0.55,
      source_updated_at: "2026-05-30",
      indexed_at: "2026-06-02",
      why_selected: "补全清单单品的卖点细节，图谱 measured_by 关联爆款笔记。"
    }]
  },
  2: {
    mode: "semantic",
    items: [{
      resource_id: "res_note_0377",
      type: "爆款笔记",
      title: "新手露营避坑（藏 2.4w）",
      summary: "收藏 > 点赞，强收藏导向；平价平替清单结构。",
      score: 0.8714,
      relevance: 0.90,
      freshness: 0.78,
      performance: 0.84,
      source_updated_at: "2026-06-18",
      indexed_at: "2026-06-19",
      why_selected: "避坑 + 平替结构的高收藏样本，命中「新手露营」语义。"
    }, {
      resource_id: "res_fb_0142",
      type: "用户反馈",
      title: "上条避坑笔记评论高频词",
      summary: "「求清单」「跟着买」高频，价格敏感。",
      score: 0.7012,
      relevance: 0.74,
      freshness: 0.88,
      performance: 0.61,
      source_updated_at: "2026-06-22",
      indexed_at: "2026-06-22",
      why_selected: "反馈资源（feedback_on 边）佐证价格敏感与清单诉求。"
    }]
  },
  3: {
    mode: "keyword_fallback",
    items: [{
      resource_id: "res_note_0290",
      type: "爆款笔记",
      title: "落日篝火氛围感笔记",
      summary: "情绪向图文，点赞高、收藏中等；语义相关度偏低，关键词兜底命中。",
      score: 0.5933,
      relevance: 0.58,
      freshness: 0.70,
      performance: 0.66,
      source_updated_at: "2026-06-12",
      indexed_at: "2026-06-14",
      why_selected: "语义检索未达阈值，按「露营氛围感」关键词兜底召回。"
    }]
  }
};

// ── 文案体检规则库（可持续扩充：往这个数组追加规则即可）──
// 每条规则 = { key, group, label, hint, test(note) -> { pass, value } }
(function () {
  const G = /\p{Extended_Pictographic}/gu,
    ONE = /\p{Extended_Pictographic}/u;
  const banned = /最佳|最好|第一名|国家级|绝对|100%|顶级|纯天然|永久|官方认证|最便宜/;
  const benefit = /防雨|防晒|省|平价|搞定|避坑|出片|氛围|必带|轻便|性价比|治愈|宽敞|不踩雷/;
  const first = n => (n.body || "").slice(0, 120);
  window.STUDIO.checkRules = [{
    key: "title_len",
    group: "标题",
    label: "标题长度",
    hint: "≤20 字最易读",
    test: n => ({
      pass: n.title.length > 0 && n.title.length <= 20,
      value: n.title.length ? `${n.title.length} 字` : "—"
    })
  }, {
    key: "title_hook",
    group: "标题",
    label: "标题钩子",
    hint: "数字/痛点/情绪/emoji",
    test: n => ({
      pass: /[0-9０-９！!?？]|绝了|谁懂|必看|后悔|攻略|清单|避坑|收藏|平替|天花板|宝藏|封神/.test(n.title) || ONE.test(n.title),
      value: ONE.test(n.title) ? "含 emoji" : /[0-9]/.test(n.title) ? "含数字" : "—"
    })
  }, {
    key: "keyword_front",
    group: "标题",
    label: "关键词前置",
    hint: "核心搜索词进标题+首段",
    test: n => {
      const k = (n.kw || "").slice(0, 2);
      return {
        pass: !!k && n.title.includes(k) && first(n).includes(k),
        value: n.kw || "—"
      };
    }
  }, {
    key: "emoji",
    group: "正文",
    label: "Emoji 密度",
    hint: "每段 1–2 个",
    test: n => {
      const c = (n.body.match(G) || []).length;
      return {
        pass: c >= 6,
        value: `${c} 个`
      };
    }
  }, {
    key: "structure",
    group: "正文",
    label: "分点结构",
    hint: "编号清单 / ✅❌",
    test: n => ({
      pass: /1️⃣|2️⃣|3️⃣|✅|❌/.test(n.body),
      value: /1️⃣/.test(n.body) ? "清单" : "—"
    })
  }, {
    key: "benefit_front",
    group: "正文",
    label: "利益点前置",
    hint: "前 120 字给到利益/痛点",
    test: n => ({
      pass: benefit.test(first(n)),
      value: benefit.test(first(n)) ? "已前置" : "—"
    })
  }, {
    key: "interact",
    group: "正文",
    label: "互动引导",
    hint: "求评论/收藏/关注",
    test: n => ({
      pass: /评论|收藏|关注|点赞|交流|码住|抄作业|蹲一个/.test(n.body),
      value: /收藏/.test(n.body) ? "已加" : "—"
    })
  }, {
    key: "length",
    group: "正文",
    label: "字数",
    hint: "≤1000 字",
    test: n => ({
      pass: n.body.length > 0 && n.body.length <= 1000,
      value: `${n.body.length}/1000`
    })
  }, {
    key: "tag_count",
    group: "标签",
    label: "标签数量",
    hint: "5–10 个",
    test: n => ({
      pass: n.tags.length >= 5 && n.tags.length <= 10,
      value: `${n.tags.length} 个`
    })
  }, {
    key: "tag_longtail",
    group: "标签",
    label: "长尾标签",
    hint: "含 ≥4 字长尾词",
    test: n => ({
      pass: n.tags.some(t => t.length >= 4),
      value: n.tags.some(t => t.length >= 4) ? "已含" : "缺长尾"
    })
  }, {
    key: "cover",
    group: "封面",
    label: "封面文案",
    hint: "3–6 字大字报",
    test: n => ({
      pass: !!n.cover,
      value: n.cover ? "已设" : "—"
    })
  }, {
    key: "compliance",
    group: "合规",
    label: "违禁词规避",
    hint: "无极限词/违禁词",
    test: n => ({
      pass: !banned.test((n.title || "") + (n.body || "")),
      value: banned.test((n.title || "") + (n.body || "")) ? "含违禁词" : "无违禁词"
    })
  }];
})();
})(); } catch (e) { __ds_ns.__errors.push({ path: "ui_kits/studio/data.js", error: String((e && e.message) || e) }); }

// ui_kits/studio/tweaks-panel.jsx
try { (() => {
// @ds-adherence-ignore -- omelette starter scaffold (raw elements/hex/px by design)

/* BEGIN USAGE */
// tweaks-panel.jsx
// Reusable Tweaks shell + form-control helpers.
// Exports (to window): useTweaks, TweaksPanel, TweakSection, TweakRow, TweakSlider,
//   TweakToggle, TweakRadio, TweakSelect, TweakText, TweakNumber, TweakColor, TweakButton.
//
// Owns the host protocol (listens for __activate_edit_mode / __deactivate_edit_mode,
// posts __edit_mode_available / __edit_mode_set_keys / __edit_mode_dismissed) so
// individual prototypes don't re-roll it. Ships a consistent set of controls so you
// don't hand-draw <input type="range">, segmented radios, steppers, etc.
//
// Usage (in an HTML file that loads React + Babel):
//
//   const TWEAK_DEFAULTS = /*EDITMODE-BEGIN*/{
//     "primaryColor": "#D97757",
//     "palette": ["#D97757", "#29261b", "#f6f4ef"],
//     "fontSize": 16,
//     "density": "regular",
//     "dark": false
//   }/*EDITMODE-END*/;
//
//   function App() {
//     const [t, setTweak] = useTweaks(TWEAK_DEFAULTS);
//     return (
//       <div style={{ fontSize: t.fontSize, color: t.primaryColor }}>
//         Hello
//         <TweaksPanel>
//           <TweakSection label="Typography" />
//           <TweakSlider label="Font size" value={t.fontSize} min={10} max={32} unit="px"
//                        onChange={(v) => setTweak('fontSize', v)} />
//           <TweakRadio  label="Density" value={t.density}
//                        options={['compact', 'regular', 'comfy']}
//                        onChange={(v) => setTweak('density', v)} />
//           <TweakSection label="Theme" />
//           <TweakColor  label="Primary" value={t.primaryColor}
//                        options={['#D97757', '#2A6FDB', '#1F8A5B', '#7A5AE0']}
//                        onChange={(v) => setTweak('primaryColor', v)} />
//           <TweakColor  label="Palette" value={t.palette}
//                        options={[['#D97757', '#29261b', '#f6f4ef'],
//                                  ['#475569', '#0f172a', '#f1f5f9']]}
//                        onChange={(v) => setTweak('palette', v)} />
//           <TweakToggle label="Dark mode" value={t.dark}
//                        onChange={(v) => setTweak('dark', v)} />
//         </TweaksPanel>
//       </div>
//     );
//   }
//
// TweakRadio is the segmented control for 2–3 short options (auto-falls-back to
// TweakSelect past ~16/~10 chars per label); reach for TweakSelect directly when
// options are many or long. For color tweaks always curate 3-4 options rather than
// a free picker; an option can also be a whole 2–5 color palette (the stored value
// is the array). The Tweak* controls are a floor, not a ceiling — build custom
// controls inside the panel if a tweak calls for UI they don't cover.
/* END USAGE */
// ─────────────────────────────────────────────────────────────────────────────

const __TWEAKS_STYLE = `
  .twk-panel{position:fixed;right:16px;bottom:16px;z-index:2147483646;width:280px;
    max-height:calc(100vh - 32px);display:flex;flex-direction:column;
    transform:scale(var(--dc-inv-zoom,1));transform-origin:bottom right;
    background:rgba(250,249,247,.78);color:#29261b;
    -webkit-backdrop-filter:blur(24px) saturate(160%);backdrop-filter:blur(24px) saturate(160%);
    border:.5px solid rgba(255,255,255,.6);border-radius:14px;
    box-shadow:0 1px 0 rgba(255,255,255,.5) inset,0 12px 40px rgba(0,0,0,.18);
    font:11.5px/1.4 ui-sans-serif,system-ui,-apple-system,sans-serif;overflow:hidden}
  .twk-hd{display:flex;align-items:center;justify-content:space-between;
    padding:10px 8px 10px 14px;cursor:move;user-select:none}
  .twk-hd b{font-size:12px;font-weight:600;letter-spacing:.01em}
  .twk-x{appearance:none;border:0;background:transparent;color:rgba(41,38,27,.55);
    width:22px;height:22px;border-radius:6px;cursor:default;font-size:13px;line-height:1}
  .twk-x:hover{background:rgba(0,0,0,.06);color:#29261b}
  .twk-body{padding:2px 14px 14px;display:flex;flex-direction:column;gap:10px;
    overflow-y:auto;overflow-x:hidden;min-height:0;
    scrollbar-width:thin;scrollbar-color:rgba(0,0,0,.15) transparent}
  .twk-body::-webkit-scrollbar{width:8px}
  .twk-body::-webkit-scrollbar-track{background:transparent;margin:2px}
  .twk-body::-webkit-scrollbar-thumb{background:rgba(0,0,0,.15);border-radius:4px;
    border:2px solid transparent;background-clip:content-box}
  .twk-body::-webkit-scrollbar-thumb:hover{background:rgba(0,0,0,.25);
    border:2px solid transparent;background-clip:content-box}
  .twk-row{display:flex;flex-direction:column;gap:5px}
  .twk-row-h{flex-direction:row;align-items:center;justify-content:space-between;gap:10px}
  .twk-lbl{display:flex;justify-content:space-between;align-items:baseline;
    color:rgba(41,38,27,.72)}
  .twk-lbl>span:first-child{font-weight:500}
  .twk-val{color:rgba(41,38,27,.5);font-variant-numeric:tabular-nums}

  .twk-sect{font-size:10px;font-weight:600;letter-spacing:.06em;text-transform:uppercase;
    color:rgba(41,38,27,.45);padding:10px 0 0}
  .twk-sect:first-child{padding-top:0}

  .twk-field{appearance:none;box-sizing:border-box;width:100%;min-width:0;height:26px;padding:0 8px;
    border:.5px solid rgba(0,0,0,.1);border-radius:7px;
    background:rgba(255,255,255,.6);color:inherit;font:inherit;outline:none}
  .twk-field:focus{border-color:rgba(0,0,0,.25);background:rgba(255,255,255,.85)}
  select.twk-field{padding-right:22px;
    background-image:url("data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' width='10' height='6' viewBox='0 0 10 6'><path fill='rgba(0,0,0,.5)' d='M0 0h10L5 6z'/></svg>");
    background-repeat:no-repeat;background-position:right 8px center}

  .twk-slider{appearance:none;-webkit-appearance:none;width:100%;height:4px;margin:6px 0;
    border-radius:999px;background:rgba(0,0,0,.12);outline:none}
  .twk-slider::-webkit-slider-thumb{-webkit-appearance:none;appearance:none;
    width:14px;height:14px;border-radius:50%;background:#fff;
    border:.5px solid rgba(0,0,0,.12);box-shadow:0 1px 3px rgba(0,0,0,.2);cursor:default}
  .twk-slider::-moz-range-thumb{width:14px;height:14px;border-radius:50%;
    background:#fff;border:.5px solid rgba(0,0,0,.12);box-shadow:0 1px 3px rgba(0,0,0,.2);cursor:default}

  .twk-seg{position:relative;display:flex;padding:2px;border-radius:8px;
    background:rgba(0,0,0,.06);user-select:none}
  .twk-seg-thumb{position:absolute;top:2px;bottom:2px;border-radius:6px;
    background:rgba(255,255,255,.9);box-shadow:0 1px 2px rgba(0,0,0,.12);
    transition:left .15s cubic-bezier(.3,.7,.4,1),width .15s}
  .twk-seg.dragging .twk-seg-thumb{transition:none}
  .twk-seg button{appearance:none;position:relative;z-index:1;flex:1;border:0;
    background:transparent;color:inherit;font:inherit;font-weight:500;min-height:22px;
    border-radius:6px;cursor:default;padding:4px 6px;line-height:1.2;
    overflow-wrap:anywhere}

  .twk-toggle{position:relative;width:32px;height:18px;border:0;border-radius:999px;
    background:rgba(0,0,0,.15);transition:background .15s;cursor:default;padding:0}
  .twk-toggle[data-on="1"]{background:#34c759}
  .twk-toggle i{position:absolute;top:2px;left:2px;width:14px;height:14px;border-radius:50%;
    background:#fff;box-shadow:0 1px 2px rgba(0,0,0,.25);transition:transform .15s}
  .twk-toggle[data-on="1"] i{transform:translateX(14px)}

  .twk-num{display:flex;align-items:center;box-sizing:border-box;min-width:0;height:26px;padding:0 0 0 8px;
    border:.5px solid rgba(0,0,0,.1);border-radius:7px;background:rgba(255,255,255,.6)}
  .twk-num-lbl{font-weight:500;color:rgba(41,38,27,.6);cursor:ew-resize;
    user-select:none;padding-right:8px}
  .twk-num input{flex:1;min-width:0;height:100%;border:0;background:transparent;
    font:inherit;font-variant-numeric:tabular-nums;text-align:right;padding:0 8px 0 0;
    outline:none;color:inherit;-moz-appearance:textfield}
  .twk-num input::-webkit-inner-spin-button,.twk-num input::-webkit-outer-spin-button{
    -webkit-appearance:none;margin:0}
  .twk-num-unit{padding-right:8px;color:rgba(41,38,27,.45)}

  .twk-btn{appearance:none;height:26px;padding:0 12px;border:0;border-radius:7px;
    background:rgba(0,0,0,.78);color:#fff;font:inherit;font-weight:500;cursor:default}
  .twk-btn:hover{background:rgba(0,0,0,.88)}
  .twk-btn.secondary{background:rgba(0,0,0,.06);color:inherit}
  .twk-btn.secondary:hover{background:rgba(0,0,0,.1)}

  .twk-swatch{appearance:none;-webkit-appearance:none;width:56px;height:22px;
    border:.5px solid rgba(0,0,0,.1);border-radius:6px;padding:0;cursor:default;
    background:transparent;flex-shrink:0}
  .twk-swatch::-webkit-color-swatch-wrapper{padding:0}
  .twk-swatch::-webkit-color-swatch{border:0;border-radius:5.5px}
  .twk-swatch::-moz-color-swatch{border:0;border-radius:5.5px}

  .twk-chips{display:flex;gap:6px}
  .twk-chip{position:relative;appearance:none;flex:1;min-width:0;height:46px;
    padding:0;border:0;border-radius:6px;overflow:hidden;cursor:default;
    box-shadow:0 0 0 .5px rgba(0,0,0,.12),0 1px 2px rgba(0,0,0,.06);
    transition:transform .12s cubic-bezier(.3,.7,.4,1),box-shadow .12s}
  .twk-chip:hover{transform:translateY(-1px);
    box-shadow:0 0 0 .5px rgba(0,0,0,.18),0 4px 10px rgba(0,0,0,.12)}
  .twk-chip[data-on="1"]{box-shadow:0 0 0 1.5px rgba(0,0,0,.85),
    0 2px 6px rgba(0,0,0,.15)}
  .twk-chip>span{position:absolute;top:0;bottom:0;right:0;width:34%;
    display:flex;flex-direction:column;box-shadow:-1px 0 0 rgba(0,0,0,.1)}
  .twk-chip>span>i{flex:1;box-shadow:0 -1px 0 rgba(0,0,0,.1)}
  .twk-chip>span>i:first-child{box-shadow:none}
  .twk-chip svg{position:absolute;top:6px;left:6px;width:13px;height:13px;
    filter:drop-shadow(0 1px 1px rgba(0,0,0,.3))}
`;

// ── useTweaks ───────────────────────────────────────────────────────────────
// Single source of truth for tweak values. setTweak persists via the host
// (__edit_mode_set_keys → host rewrites the EDITMODE block on disk).
function useTweaks(defaults) {
  const [values, setValues] = React.useState(defaults);
  // Accepts either setTweak('key', value) or setTweak({ key: value, ... }) so a
  // useState-style call doesn't write a "[object Object]" key into the persisted
  // JSON block.
  const setTweak = React.useCallback((keyOrEdits, val) => {
    const edits = typeof keyOrEdits === 'object' && keyOrEdits !== null ? keyOrEdits : {
      [keyOrEdits]: val
    };
    setValues(prev => ({
      ...prev,
      ...edits
    }));
    window.parent.postMessage({
      type: '__edit_mode_set_keys',
      edits
    }, '*');
    // Same-window signal so in-page listeners (deck-stage rail thumbnails)
    // can react — the parent message only reaches the host, not peers.
    window.dispatchEvent(new CustomEvent('tweakchange', {
      detail: edits
    }));
  }, []);
  return [values, setTweak];
}

// ── TweaksPanel ─────────────────────────────────────────────────────────────
// Floating shell. Registers the protocol listener BEFORE announcing
// availability — if the announce ran first, the host's activate could land
// before our handler exists and the toolbar toggle would silently no-op.
// The close button posts __edit_mode_dismissed so the host's toolbar toggle
// flips off in lockstep; the host echoes __deactivate_edit_mode back which
// is what actually hides the panel.
function TweaksPanel({
  title = 'Tweaks',
  children
}) {
  const [open, setOpen] = React.useState(false);
  const dragRef = React.useRef(null);
  const offsetRef = React.useRef({
    x: 16,
    y: 16
  });
  const PAD = 16;
  const clampToViewport = React.useCallback(() => {
    const panel = dragRef.current;
    if (!panel) return;
    const w = panel.offsetWidth,
      h = panel.offsetHeight;
    const maxRight = Math.max(PAD, window.innerWidth - w - PAD);
    const maxBottom = Math.max(PAD, window.innerHeight - h - PAD);
    offsetRef.current = {
      x: Math.min(maxRight, Math.max(PAD, offsetRef.current.x)),
      y: Math.min(maxBottom, Math.max(PAD, offsetRef.current.y))
    };
    panel.style.right = offsetRef.current.x + 'px';
    panel.style.bottom = offsetRef.current.y + 'px';
  }, []);
  React.useEffect(() => {
    if (!open) return;
    clampToViewport();
    if (typeof ResizeObserver === 'undefined') {
      window.addEventListener('resize', clampToViewport);
      return () => window.removeEventListener('resize', clampToViewport);
    }
    const ro = new ResizeObserver(clampToViewport);
    ro.observe(document.documentElement);
    return () => ro.disconnect();
  }, [open, clampToViewport]);
  React.useEffect(() => {
    const onMsg = e => {
      const t = e?.data?.type;
      if (t === '__activate_edit_mode') setOpen(true);else if (t === '__deactivate_edit_mode') setOpen(false);
    };
    window.addEventListener('message', onMsg);
    window.parent.postMessage({
      type: '__edit_mode_available'
    }, '*');
    return () => window.removeEventListener('message', onMsg);
  }, []);
  const dismiss = () => {
    setOpen(false);
    window.parent.postMessage({
      type: '__edit_mode_dismissed'
    }, '*');
  };
  const onDragStart = e => {
    const panel = dragRef.current;
    if (!panel) return;
    const r = panel.getBoundingClientRect();
    const sx = e.clientX,
      sy = e.clientY;
    const startRight = window.innerWidth - r.right;
    const startBottom = window.innerHeight - r.bottom;
    const move = ev => {
      offsetRef.current = {
        x: startRight - (ev.clientX - sx),
        y: startBottom - (ev.clientY - sy)
      };
      clampToViewport();
    };
    const up = () => {
      window.removeEventListener('mousemove', move);
      window.removeEventListener('mouseup', up);
    };
    window.addEventListener('mousemove', move);
    window.addEventListener('mouseup', up);
  };
  if (!open) return null;
  return /*#__PURE__*/React.createElement(React.Fragment, null, /*#__PURE__*/React.createElement("style", null, __TWEAKS_STYLE), /*#__PURE__*/React.createElement("div", {
    ref: dragRef,
    className: "twk-panel",
    "data-omelette-chrome": "",
    style: {
      right: offsetRef.current.x,
      bottom: offsetRef.current.y
    }
  }, /*#__PURE__*/React.createElement("div", {
    className: "twk-hd",
    onMouseDown: onDragStart
  }, /*#__PURE__*/React.createElement("b", null, title), /*#__PURE__*/React.createElement("button", {
    className: "twk-x",
    "aria-label": "Close tweaks",
    onMouseDown: e => e.stopPropagation(),
    onClick: dismiss
  }, "\u2715")), /*#__PURE__*/React.createElement("div", {
    className: "twk-body"
  }, children)));
}

// ── Layout helpers ──────────────────────────────────────────────────────────

function TweakSection({
  label,
  children
}) {
  return /*#__PURE__*/React.createElement(React.Fragment, null, /*#__PURE__*/React.createElement("div", {
    className: "twk-sect"
  }, label), children);
}
function TweakRow({
  label,
  value,
  children,
  inline = false
}) {
  return /*#__PURE__*/React.createElement("div", {
    className: inline ? 'twk-row twk-row-h' : 'twk-row'
  }, /*#__PURE__*/React.createElement("div", {
    className: "twk-lbl"
  }, /*#__PURE__*/React.createElement("span", null, label), value != null && /*#__PURE__*/React.createElement("span", {
    className: "twk-val"
  }, value)), children);
}

// ── Controls ────────────────────────────────────────────────────────────────

function TweakSlider({
  label,
  value,
  min = 0,
  max = 100,
  step = 1,
  unit = '',
  onChange
}) {
  return /*#__PURE__*/React.createElement(TweakRow, {
    label: label,
    value: `${value}${unit}`
  }, /*#__PURE__*/React.createElement("input", {
    type: "range",
    className: "twk-slider",
    min: min,
    max: max,
    step: step,
    value: value,
    onChange: e => onChange(Number(e.target.value))
  }));
}
function TweakToggle({
  label,
  value,
  onChange
}) {
  return /*#__PURE__*/React.createElement("div", {
    className: "twk-row twk-row-h"
  }, /*#__PURE__*/React.createElement("div", {
    className: "twk-lbl"
  }, /*#__PURE__*/React.createElement("span", null, label)), /*#__PURE__*/React.createElement("button", {
    type: "button",
    className: "twk-toggle",
    "data-on": value ? '1' : '0',
    role: "switch",
    "aria-checked": !!value,
    onClick: () => onChange(!value)
  }, /*#__PURE__*/React.createElement("i", null)));
}
function TweakRadio({
  label,
  value,
  options,
  onChange
}) {
  const trackRef = React.useRef(null);
  const [dragging, setDragging] = React.useState(false);
  // The active value is read by pointer-move handlers attached for the lifetime
  // of a drag — ref it so a stale closure doesn't fire onChange for every move.
  const valueRef = React.useRef(value);
  valueRef.current = value;

  // Segments wrap mid-word once per-segment width runs out. The track is
  // ~248px (280 panel − 28 body pad − 4 seg pad), each button loses 12px
  // to its own padding, and 11.5px system-ui averages ~6.3px/char — so 2
  // options fit ~16 chars each, 3 fit ~10. Past that (or >3 options), fall
  // back to a dropdown rather than wrap.
  const labelLen = o => String(typeof o === 'object' ? o.label : o).length;
  const maxLen = options.reduce((m, o) => Math.max(m, labelLen(o)), 0);
  const fitsAsSegments = maxLen <= ({
    2: 16,
    3: 10
  }[options.length] ?? 0);
  if (!fitsAsSegments) {
    // <select> emits strings — map back to the original option value so the
    // fallback stays type-preserving (numbers, booleans) like the segment path.
    const resolve = s => {
      const m = options.find(o => String(typeof o === 'object' ? o.value : o) === s);
      return m === undefined ? s : typeof m === 'object' ? m.value : m;
    };
    return /*#__PURE__*/React.createElement(TweakSelect, {
      label: label,
      value: value,
      options: options,
      onChange: s => onChange(resolve(s))
    });
  }
  const opts = options.map(o => typeof o === 'object' ? o : {
    value: o,
    label: o
  });
  const idx = Math.max(0, opts.findIndex(o => o.value === value));
  const n = opts.length;
  const segAt = clientX => {
    const r = trackRef.current.getBoundingClientRect();
    const inner = r.width - 4;
    const i = Math.floor((clientX - r.left - 2) / inner * n);
    return opts[Math.max(0, Math.min(n - 1, i))].value;
  };
  const onPointerDown = e => {
    setDragging(true);
    const v0 = segAt(e.clientX);
    if (v0 !== valueRef.current) onChange(v0);
    const move = ev => {
      if (!trackRef.current) return;
      const v = segAt(ev.clientX);
      if (v !== valueRef.current) onChange(v);
    };
    const up = () => {
      setDragging(false);
      window.removeEventListener('pointermove', move);
      window.removeEventListener('pointerup', up);
    };
    window.addEventListener('pointermove', move);
    window.addEventListener('pointerup', up);
  };
  return /*#__PURE__*/React.createElement(TweakRow, {
    label: label
  }, /*#__PURE__*/React.createElement("div", {
    ref: trackRef,
    role: "radiogroup",
    onPointerDown: onPointerDown,
    className: dragging ? 'twk-seg dragging' : 'twk-seg'
  }, /*#__PURE__*/React.createElement("div", {
    className: "twk-seg-thumb",
    style: {
      left: `calc(2px + ${idx} * (100% - 4px) / ${n})`,
      width: `calc((100% - 4px) / ${n})`
    }
  }), opts.map(o => /*#__PURE__*/React.createElement("button", {
    key: o.value,
    type: "button",
    role: "radio",
    "aria-checked": o.value === value
  }, o.label))));
}
function TweakSelect({
  label,
  value,
  options,
  onChange
}) {
  return /*#__PURE__*/React.createElement(TweakRow, {
    label: label
  }, /*#__PURE__*/React.createElement("select", {
    className: "twk-field",
    value: value,
    onChange: e => onChange(e.target.value)
  }, options.map(o => {
    const v = typeof o === 'object' ? o.value : o;
    const l = typeof o === 'object' ? o.label : o;
    return /*#__PURE__*/React.createElement("option", {
      key: v,
      value: v
    }, l);
  })));
}
function TweakText({
  label,
  value,
  placeholder,
  onChange
}) {
  return /*#__PURE__*/React.createElement(TweakRow, {
    label: label
  }, /*#__PURE__*/React.createElement("input", {
    className: "twk-field",
    type: "text",
    value: value,
    placeholder: placeholder,
    onChange: e => onChange(e.target.value)
  }));
}
function TweakNumber({
  label,
  value,
  min,
  max,
  step = 1,
  unit = '',
  onChange
}) {
  const clamp = n => {
    if (min != null && n < min) return min;
    if (max != null && n > max) return max;
    return n;
  };
  const startRef = React.useRef({
    x: 0,
    val: 0
  });
  const onScrubStart = e => {
    e.preventDefault();
    startRef.current = {
      x: e.clientX,
      val: value
    };
    const decimals = (String(step).split('.')[1] || '').length;
    const move = ev => {
      const dx = ev.clientX - startRef.current.x;
      const raw = startRef.current.val + dx * step;
      const snapped = Math.round(raw / step) * step;
      onChange(clamp(Number(snapped.toFixed(decimals))));
    };
    const up = () => {
      window.removeEventListener('pointermove', move);
      window.removeEventListener('pointerup', up);
    };
    window.addEventListener('pointermove', move);
    window.addEventListener('pointerup', up);
  };
  return /*#__PURE__*/React.createElement("div", {
    className: "twk-num"
  }, /*#__PURE__*/React.createElement("span", {
    className: "twk-num-lbl",
    onPointerDown: onScrubStart
  }, label), /*#__PURE__*/React.createElement("input", {
    type: "number",
    value: value,
    min: min,
    max: max,
    step: step,
    onChange: e => onChange(clamp(Number(e.target.value)))
  }), unit && /*#__PURE__*/React.createElement("span", {
    className: "twk-num-unit"
  }, unit));
}

// Relative-luminance contrast pick — checkmarks drawn over a swatch need to
// read on both #111 and #fafafa without per-option configuration. Hex input
// only (#rgb / #rrggbb); named or rgb()/hsl() colors fall through to "light".
function __twkIsLight(hex) {
  const h = String(hex).replace('#', '');
  const x = h.length === 3 ? h.replace(/./g, c => c + c) : h.padEnd(6, '0');
  const n = parseInt(x.slice(0, 6), 16);
  if (Number.isNaN(n)) return true;
  const r = n >> 16 & 255,
    g = n >> 8 & 255,
    b = n & 255;
  return r * 299 + g * 587 + b * 114 > 148000;
}
const __TwkCheck = ({
  light
}) => /*#__PURE__*/React.createElement("svg", {
  viewBox: "0 0 14 14",
  "aria-hidden": "true"
}, /*#__PURE__*/React.createElement("path", {
  d: "M3 7.2 5.8 10 11 4.2",
  fill: "none",
  strokeWidth: "2.2",
  strokeLinecap: "round",
  strokeLinejoin: "round",
  stroke: light ? 'rgba(0,0,0,.78)' : '#fff'
}));

// TweakColor — curated color/palette picker. Each option is either a single
// hex string or an array of 1-5 hex strings; the card adapts — a lone color
// renders solid, a palette renders colors[0] as the hero (left ~2/3) with the
// rest stacked in a sharp column on the right. onChange emits the
// option in the shape it was passed (string stays string, array stays array).
// Without options it falls back to the native color input for back-compat.
function TweakColor({
  label,
  value,
  options,
  onChange
}) {
  if (!options || !options.length) {
    return /*#__PURE__*/React.createElement("div", {
      className: "twk-row twk-row-h"
    }, /*#__PURE__*/React.createElement("div", {
      className: "twk-lbl"
    }, /*#__PURE__*/React.createElement("span", null, label)), /*#__PURE__*/React.createElement("input", {
      type: "color",
      className: "twk-swatch",
      value: value,
      onChange: e => onChange(e.target.value)
    }));
  }
  // Native <input type=color> emits lowercase hex per the HTML spec, so
  // compare case-insensitively. String() guards JSON.stringify(undefined),
  // which returns the primitive undefined (no .toLowerCase).
  const key = o => String(JSON.stringify(o)).toLowerCase();
  const cur = key(value);
  return /*#__PURE__*/React.createElement(TweakRow, {
    label: label
  }, /*#__PURE__*/React.createElement("div", {
    className: "twk-chips",
    role: "radiogroup"
  }, options.map((o, i) => {
    const colors = Array.isArray(o) ? o : [o];
    const [hero, ...rest] = colors;
    const sup = rest.slice(0, 4);
    const on = key(o) === cur;
    return /*#__PURE__*/React.createElement("button", {
      key: i,
      type: "button",
      className: "twk-chip",
      role: "radio",
      "aria-checked": on,
      "data-on": on ? '1' : '0',
      "aria-label": colors.join(', '),
      title: colors.join(' · '),
      style: {
        background: hero
      },
      onClick: () => onChange(o)
    }, sup.length > 0 && /*#__PURE__*/React.createElement("span", null, sup.map((c, j) => /*#__PURE__*/React.createElement("i", {
      key: j,
      style: {
        background: c
      }
    }))), on && /*#__PURE__*/React.createElement(__TwkCheck, {
      light: __twkIsLight(hero)
    }));
  })));
}
function TweakButton({
  label,
  onClick,
  secondary = false
}) {
  return /*#__PURE__*/React.createElement("button", {
    type: "button",
    className: secondary ? 'twk-btn secondary' : 'twk-btn',
    onClick: onClick
  }, label);
}
Object.assign(window, {
  useTweaks,
  TweaksPanel,
  TweakSection,
  TweakRow,
  TweakSlider,
  TweakToggle,
  TweakRadio,
  TweakSelect,
  TweakText,
  TweakNumber,
  TweakColor,
  TweakButton
});
})(); } catch (e) { __ds_ns.__errors.push({ path: "ui_kits/studio/tweaks-panel.jsx", error: String((e && e.message) || e) }); }

// ui_kits/studio/ui.jsx
try { (() => {
// Shared helpers + store for the Studio prototype.
const LUCIDE = "https://unpkg.com/lucide-static@0.460.0/icons/";
function Icon({
  name,
  size = 16,
  color,
  style = {}
}) {
  return /*#__PURE__*/React.createElement("span", {
    "aria-hidden": "true",
    style: {
      width: size,
      height: size,
      display: "inline-block",
      flexShrink: 0,
      backgroundColor: color || "currentColor",
      WebkitMaskImage: `url("${LUCIDE}${name}.svg")`,
      maskImage: `url("${LUCIDE}${name}.svg")`,
      WebkitMaskRepeat: "no-repeat",
      maskRepeat: "no-repeat",
      WebkitMaskPosition: "center",
      maskPosition: "center",
      WebkitMaskSize: "contain",
      maskSize: "contain",
      ...style
    }
  });
}
function Eyebrow({
  children,
  style = {}
}) {
  return /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: "var(--text-2xs)",
      fontWeight: 600,
      letterSpacing: "var(--tracking-wide)",
      textTransform: "uppercase",
      color: "var(--text-subtle)",
      ...style
    }
  }, children);
}
function PanelHead({
  icon,
  title,
  sub,
  right
}) {
  return /*#__PURE__*/React.createElement("div", {
    style: {
      display: "flex",
      alignItems: "center",
      justifyContent: "space-between",
      gap: 12
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      display: "flex",
      alignItems: "center",
      gap: 8,
      minWidth: 0
    }
  }, icon && /*#__PURE__*/React.createElement(Icon, {
    name: icon,
    size: 16,
    color: "var(--primary)"
  }), /*#__PURE__*/React.createElement("div", {
    style: {
      minWidth: 0
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: "var(--text-sm)",
      fontWeight: 700,
      color: "var(--text-body)"
    }
  }, title), sub && /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: "var(--text-2xs)",
      color: "var(--text-subtle)",
      marginTop: 1
    }
  }, sub))), right);
}

// ── Shared store (one note flows across 创作 / 深度创作 / 运营) ──
const StudioContext = React.createContext(null);
const useStudio = () => React.useContext(StudioContext);

// Build version A/B/C from a topic's base draft
function buildVersions(topic) {
  const d = topic.draft;
  const cut = s => s.length > 20 ? s.slice(0, 20) : s;
  return {
    A: {
      ...d,
      label: "版本 A · 种草向",
      note: "原稿"
    },
    B: {
      label: "版本 B · 避坑向",
      note: "AI 改写",
      title: cut(`新手别乱买！${topic.kw}避坑清单`),
      cover: "避坑\n清单",
      body: `❌ 先说结论，这几样真的别冲！踩过坑才懂～\n\n` + d.body,
      tags: [...d.tags, "避坑指南", "平价平替"].slice(0, 9)
    },
    C: {
      label: "版本 C · 情绪向",
      note: "AI 改写",
      title: cut(`${topic.emotional} 🌿`),
      cover: d.cover,
      body: `🌅 有些瞬间，值得被认真记录下来。\n\n` + d.body,
      tags: [...d.tags, "氛围感", "治愈系"].slice(0, 9)
    }
  };
}

// 小红书 文案体检 — driven by an EXTENSIBLE rule library
// (window.STUDIO.checkRules). Add a rule = append one object there.
function computeChecks(note) {
  const rules = window.STUDIO && window.STUDIO.checkRules || [];
  return rules.map(r => {
    let res = {};
    try {
      res = r.test(note) || {};
    } catch (e) {
      res = {};
    }
    return {
      key: r.key,
      group: r.group || "其他",
      label: r.label,
      hint: r.hint,
      pass: !!res.pass,
      value: res.value || "—"
    };
  });
}
const scoreOf = checks => Math.round(checks.filter(c => c.pass).length / checks.length * 100);
Object.assign(window, {
  Icon,
  Eyebrow,
  PanelHead,
  StudioContext,
  useStudio,
  buildVersions,
  computeChecks,
  scoreOf
});
})(); } catch (e) { __ds_ns.__errors.push({ path: "ui_kits/studio/ui.jsx", error: String((e && e.message) || e) }); }

// ui_kits/workbench/ChatPane.jsx
try { (() => {
// ChatPane — the center conversation column + composer.
function ChatPane({
  chosenId,
  writing,
  onSelectTopic,
  onOpenPalette,
  input,
  setInput,
  onSend
}) {
  const {
    Card,
    Avatar,
    Button,
    Textarea,
    TopicCard,
    ThinkingAura
  } = window.DesignSystem_71831b;
  const D = window.XHS_DATA;
  const scrollRef = React.useRef(null);
  React.useEffect(() => {
    const el = scrollRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [chosenId, writing]);
  const chosen = D.topics.find(t => t.id === chosenId);
  return /*#__PURE__*/React.createElement("section", {
    style: {
      flex: 1,
      display: "flex",
      flexDirection: "column",
      background: "var(--background)",
      minWidth: 0
    }
  }, /*#__PURE__*/React.createElement("div", {
    ref: scrollRef,
    className: "custom-scrollbar",
    style: {
      flex: 1,
      overflowY: "auto",
      padding: 24,
      display: "flex",
      flexDirection: "column",
      gap: 22
    }
  }, /*#__PURE__*/React.createElement(Bubble, {
    side: "user"
  }, "\u5E2E\u6211\u6309\u9732\u8425\u88C5\u5907\u65B9\u5411\u51FA\u9009\u9898\uFF0C\u5E76\u4ECE\u98DE\u4E66\u591A\u7EF4\u8868\u683C\u4E2D\u7B5B\u9009\u9AD8\u8D5E\u7684\u7206\u6B3E\u3002"), /*#__PURE__*/React.createElement("div", {
    style: {
      display: "flex",
      gap: 12,
      maxWidth: "88%"
    }
  }, /*#__PURE__*/React.createElement(Avatar, {
    glyph: "\uD83C\uDF60",
    variant: "agent"
  }), /*#__PURE__*/React.createElement("div", {
    style: {
      display: "flex",
      flexDirection: "column",
      gap: 10,
      minWidth: 0
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      width: 460,
      maxWidth: "100%"
    }
  }, /*#__PURE__*/React.createElement(ThinkingAura, {
    steps: D.thinkingSteps,
    logs: D.thinkingLogs
  })), /*#__PURE__*/React.createElement(Card, {
    padding: "md",
    style: {
      borderColor: "var(--border-coral)"
    }
  }, /*#__PURE__*/React.createElement("p", {
    style: {
      margin: "0 0 12px",
      fontSize: "var(--text-sm)",
      lineHeight: "var(--leading-relaxed)",
      color: "var(--text-body)"
    }
  }, "\u5206\u6790\u4E86\u98DE\u4E66\u591A\u7EF4\u8868\u683C\u4E2D\u4E92\u52A8\u91CF\u524D 10% \u7684\u9732\u8425\u88C5\u5907\u76F8\u5173\u7B14\u8BB0\uFF0C\u6211\u63D0\u70BC\u51FA\u4EE5\u4E0B 3 \u4E2A\u9AD8\u7206\u6B3E\u6982\u7387\u7684\u9009\u9898\u65B9\u5411\u3002\u70B9\u51FB\u5361\u7247\u5373\u53EF\u8BA9\u6211\u64B0\u5199\u6B63\u6587\uFF1A"), /*#__PURE__*/React.createElement("div", {
    style: {
      display: "flex",
      flexDirection: "column",
      gap: 10
    }
  }, D.topics.map(t => /*#__PURE__*/React.createElement(TopicCard, {
    key: t.id,
    index: t.id,
    title: t.title,
    rationale: t.rationale,
    hotRate: t.hotRate,
    onClick: () => onSelectTopic(t.id)
  })))))), chosen && /*#__PURE__*/React.createElement(Bubble, {
    side: "user"
  }, "\u5199\u7B2C ", chosen.id, " \u4E2A\u9009\u9898\u3002"), writing && /*#__PURE__*/React.createElement("div", {
    style: {
      display: "flex",
      gap: 12,
      maxWidth: "88%"
    }
  }, /*#__PURE__*/React.createElement(Avatar, {
    glyph: "\uD83C\uDF60",
    variant: "agent"
  }), /*#__PURE__*/React.createElement("div", {
    style: {
      display: "inline-flex",
      alignItems: "center",
      gap: 10,
      background: "var(--surface-card)",
      border: "1px solid var(--border-coral)",
      borderRadius: "var(--radius-xl)",
      padding: "12px 16px",
      fontSize: "var(--text-sm)",
      color: "var(--text-muted)",
      boxShadow: "var(--shadow-sm)"
    }
  }, /*#__PURE__*/React.createElement("span", {
    style: {
      width: 16,
      height: 16,
      borderRadius: "999px",
      border: "2px solid var(--primary)",
      borderTopColor: "transparent",
      animation: "spin 0.7s linear infinite"
    }
  }), "\u6B63\u5728\u9488\u5BF9\u300A", chosen?.title, "\u300B\u64B0\u5199\u5C0F\u7EA2\u4E66\u98CE\u683C\u6587\u6848\uFF0C\u5E76\u6D41\u5F0F\u540C\u6B65\u81F3\u53F3\u4FA7\u9884\u89C8\u2026")), chosen && !writing && /*#__PURE__*/React.createElement("div", {
    style: {
      display: "flex",
      gap: 12,
      maxWidth: "88%"
    }
  }, /*#__PURE__*/React.createElement(Avatar, {
    glyph: "\uD83C\uDF60",
    variant: "agent"
  }), /*#__PURE__*/React.createElement(Card, {
    padding: "md"
  }, /*#__PURE__*/React.createElement("p", {
    style: {
      margin: 0,
      fontSize: "var(--text-sm)",
      lineHeight: "var(--leading-relaxed)",
      color: "var(--text-body)"
    }
  }, "\u2705 \u5DF2\u5B8C\u6210\u300A", chosen.title, "\u300B\u7684\u6B63\u6587\u64B0\u5199\uFF0C\u53F3\u4FA7\u624B\u673A\u9884\u89C8\u5DF2\u66F4\u65B0\u3002\u53EF\u7EE7\u7EED\u5FAE\u8C03\uFF0C\u6216\u5207\u5230\u300C\u98DE\u4E66\u540C\u6B65\u534F\u4F5C\u300D\u4E00\u952E\u5199\u5165\u591A\u7EF4\u8868\u683C\u3002")))), /*#__PURE__*/React.createElement("div", {
    style: {
      padding: 24,
      borderTop: "1px solid var(--border)",
      flexShrink: 0
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      maxWidth: "var(--composer-max)",
      margin: "0 auto"
    }
  }, /*#__PURE__*/React.createElement(Textarea, {
    rows: 2,
    value: input,
    onChange: e => setInput(e.target.value),
    placeholder: "\u8BF4\u8BF4\u4F60\u60F3\u5199\u4EC0\u4E48\u65B9\u5411\uFF0C\u6216\u6309 Ctrl+P \u8C03\u8D77\u6DA6\u8272\u5DE5\u5177\u7BB1...",
    footer: /*#__PURE__*/React.createElement(React.Fragment, null, /*#__PURE__*/React.createElement("div", {
      style: {
        display: "flex",
        alignItems: "center",
        gap: 18
      }
    }, /*#__PURE__*/React.createElement("button", {
      onClick: onOpenPalette,
      style: {
        display: "inline-flex",
        alignItems: "center",
        gap: 6,
        background: "var(--surface-card)",
        border: "1px solid var(--border)",
        borderRadius: "var(--radius-sm)",
        padding: "5px 9px",
        cursor: "pointer",
        fontFamily: "var(--font-sans)"
      }
    }, /*#__PURE__*/React.createElement("kbd", {
      style: {
        fontSize: 8,
        background: "var(--oats-light)",
        border: "1px solid var(--border)",
        padding: "1px 4px",
        borderRadius: 4,
        fontFamily: "var(--font-mono)"
      }
    }, "Ctrl+P"), /*#__PURE__*/React.createElement("span", {
      style: {
        fontSize: "var(--text-xs)",
        color: "var(--text-muted)"
      }
    }, "\u6DA6\u8272\u5DE5\u5177\u7BB1")), /*#__PURE__*/React.createElement("span", {
      style: {
        display: "inline-flex",
        alignItems: "center",
        gap: 6,
        fontSize: "var(--text-xs)",
        color: "var(--text-muted)"
      }
    }, /*#__PURE__*/React.createElement(Icon, {
      name: "plus",
      size: 15
    }), " \u56FE\u7247\u6216 PDF")), /*#__PURE__*/React.createElement(Button, {
      variant: "primary",
      size: "sm",
      rightIcon: /*#__PURE__*/React.createElement(Icon, {
        name: "send",
        size: 14
      }),
      onClick: onSend
    }, "\u751F\u6210"))
  }))));
}
function Bubble({
  side,
  children
}) {
  const {
    Avatar
  } = window.DesignSystem_71831b;
  const isUser = side === "user";
  return /*#__PURE__*/React.createElement("div", {
    style: {
      display: "flex",
      gap: 12,
      maxWidth: "85%",
      alignSelf: isUser ? "flex-end" : "flex-start",
      flexDirection: isUser ? "row-reverse" : "row"
    }
  }, isUser ? /*#__PURE__*/React.createElement(Avatar, {
    name: "\u6211",
    variant: "solid",
    size: 32
  }) : /*#__PURE__*/React.createElement(Avatar, {
    glyph: "\uD83C\uDF60",
    variant: "agent"
  }), /*#__PURE__*/React.createElement("div", {
    style: {
      background: "var(--surface-card)",
      border: "1px solid var(--border-coral)",
      borderRadius: "var(--radius-xl)",
      padding: "12px 16px",
      fontSize: "var(--text-sm)",
      lineHeight: "var(--leading-relaxed)",
      color: "var(--text-body)",
      boxShadow: "var(--shadow-sm)"
    }
  }, children));
}
Object.assign(window, {
  ChatPane
});
})(); } catch (e) { __ds_ns.__errors.push({ path: "ui_kits/workbench/ChatPane.jsx", error: String((e && e.message) || e) }); }

// ui_kits/workbench/CommandPalette.jsx
try { (() => {
// CommandPalette — Ctrl+P modal of polish commands.
function CommandPalette({
  open,
  onClose,
  onRun
}) {
  const {
    Input
  } = window.DesignSystem_71831b;
  const D = window.XHS_DATA;
  const [q, setQ] = React.useState("");
  if (!open) return null;
  const list = D.commands.filter(c => (c.name + c.desc).toLowerCase().includes(q.toLowerCase()));
  return /*#__PURE__*/React.createElement("div", {
    onClick: onClose,
    style: {
      position: "fixed",
      inset: 0,
      background: "rgba(15,15,16,0.4)",
      backdropFilter: "blur(3px)",
      display: "flex",
      justifyContent: "center",
      alignItems: "flex-start",
      paddingTop: 96,
      zIndex: 50
    }
  }, /*#__PURE__*/React.createElement("div", {
    onClick: e => e.stopPropagation(),
    style: {
      width: 500,
      maxWidth: "90vw",
      background: "var(--surface-card)",
      borderRadius: "var(--radius-lg)",
      border: "1px solid var(--border-coral)",
      boxShadow: "var(--shadow-2xl)",
      overflow: "hidden"
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      padding: 12,
      borderBottom: "1px solid var(--oats-dark)"
    }
  }, /*#__PURE__*/React.createElement(Input, {
    autoFocus: true,
    value: q,
    onChange: e => setQ(e.target.value),
    placeholder: "\u8F93\u5165\u547D\u4EE4\u6216\u641C\u7D22\u52A8\u4F5C...",
    leadingIcon: /*#__PURE__*/React.createElement(Icon, {
      name: "search",
      size: 16
    }),
    trailing: /*#__PURE__*/React.createElement("kbd", {
      onClick: onClose,
      style: {
        fontSize: 10,
        background: "var(--oats-dark)",
        border: "1px solid var(--border)",
        color: "var(--text-subtle)",
        padding: "1px 6px",
        borderRadius: 4,
        cursor: "pointer",
        fontFamily: "var(--font-mono)"
      }
    }, "ESC")
  })), /*#__PURE__*/React.createElement("div", {
    style: {
      padding: 8,
      display: "flex",
      flexDirection: "column",
      maxHeight: 260,
      overflowY: "auto"
    },
    className: "custom-scrollbar"
  }, list.map(c => /*#__PURE__*/React.createElement("button", {
    key: c.id,
    onClick: () => onRun(c.id),
    style: {
      display: "flex",
      alignItems: "center",
      gap: 12,
      width: "100%",
      textAlign: "left",
      padding: "10px 12px",
      borderRadius: "var(--radius-sm)",
      border: "none",
      background: "transparent",
      cursor: "pointer",
      fontFamily: "var(--font-sans)"
    },
    onMouseEnter: e => e.currentTarget.style.background = "var(--oats-default)",
    onMouseLeave: e => e.currentTarget.style.background = "transparent"
  }, /*#__PURE__*/React.createElement(Icon, {
    name: c.icon,
    size: 16,
    color: c.color
  }), /*#__PURE__*/React.createElement("span", {
    style: {
      fontSize: "var(--text-xs)"
    }
  }, /*#__PURE__*/React.createElement("span", {
    style: {
      fontWeight: 600,
      color: "var(--text-body)"
    }
  }, c.name), /*#__PURE__*/React.createElement("span", {
    style: {
      color: "var(--text-subtle)",
      marginLeft: 8
    }
  }, c.desc)))), list.length === 0 && /*#__PURE__*/React.createElement("div", {
    style: {
      padding: 16,
      fontSize: "var(--text-xs)",
      color: "var(--text-subtle)",
      textAlign: "center"
    }
  }, "\u65E0\u5339\u914D\u547D\u4EE4"))));
}
Object.assign(window, {
  CommandPalette
});
})(); } catch (e) { __ds_ns.__errors.push({ path: "ui_kits/workbench/CommandPalette.jsx", error: String((e && e.message) || e) }); }

// ui_kits/workbench/FeishuSync.jsx
try { (() => {
// FeishuSync — the right-canvas "飞书同步协作" tab: bitable write,
// group-notify, and the flip-card re-auth.
function FeishuSync({
  note,
  scanned,
  onScan
}) {
  const {
    Card,
    Button,
    Select,
    Badge
  } = window.DesignSystem_71831b;
  const D = window.XHS_DATA;
  const [steps, setSteps] = React.useState(0); // 0 idle, 1-3 progress, 4 done
  const [syncing, setSyncing] = React.useState(false);
  const runSync = () => {
    if (syncing) return;
    setSyncing(true);
    setSteps(1);
    let s = 1;
    const tick = () => {
      s += 1;
      setSteps(s);
      if (s <= 3) setTimeout(tick, 850);else {
        setTimeout(() => {
          setSyncing(false);
          setSteps(0);
        }, 2600);
      }
    };
    setTimeout(tick, 850);
  };
  const stepLabels = ["正在验证飞书 CLI 环境配置...", "正在解析多维表格行结构与空字段映射...", "正在写入文案至多维表格..."];
  return /*#__PURE__*/React.createElement("div", {
    style: {
      flex: 1,
      overflowY: "auto",
      padding: 24,
      display: "flex",
      flexDirection: "column",
      gap: 20
    },
    className: "custom-scrollbar"
  }, /*#__PURE__*/React.createElement(Card, {
    padding: "md"
  }, /*#__PURE__*/React.createElement(Row, {
    icon: "database",
    iconTone: "green",
    title: "\u540C\u6B65\u5230\u98DE\u4E66\u591A\u7EF4\u8868\u683C",
    sub: "APP Token: bascnu\u2026 | Table ID: tblx\u2026",
    badge: /*#__PURE__*/React.createElement(Badge, {
      tone: "synced"
    }, "\u8FDE\u63A5\u6210\u529F")
  }), /*#__PURE__*/React.createElement("div", {
    style: {
      display: "flex",
      flexDirection: "column",
      gap: 10,
      fontSize: "var(--text-xs)",
      marginTop: 14
    }
  }, /*#__PURE__*/React.createElement(KV, {
    k: "\u7ED1\u5B9A\u9009\u9898\u8BB0\u5F55\uFF1A",
    v: `${note.title} (第 4 行)`
  }), /*#__PURE__*/React.createElement(KV, {
    k: "\u98DE\u4E66\u6587\u6863\u5217\u6620\u5C04\uFF1A",
    v: "\u300C\u6B63\u6587\u5185\u5BB9\u300D\u5B57\u6BB5",
    muted: true
  }), /*#__PURE__*/React.createElement(KV, {
    k: "\u5B57\u6570\u68C0\u6D4B\uFF1A",
    v: `${note.body.length} 字 (符合限制)`,
    ok: true
  })), steps > 0 && /*#__PURE__*/React.createElement("div", {
    style: {
      marginTop: 14,
      border: "1px solid var(--border-coral)",
      borderRadius: "var(--radius-md)",
      padding: 12,
      background: "var(--oats-light)",
      display: "flex",
      flexDirection: "column",
      gap: 8
    }
  }, stepLabels.map((label, i) => {
    const n = i + 1;
    const done = steps > n || steps === 4;
    const active = steps === n;
    return /*#__PURE__*/React.createElement("div", {
      key: i,
      style: {
        display: "flex",
        alignItems: "center",
        gap: 8,
        fontSize: "var(--text-xs)",
        color: done ? "var(--success)" : active ? "var(--primary)" : "var(--text-subtle)",
        fontWeight: active ? 600 : 400
      }
    }, /*#__PURE__*/React.createElement("span", {
      style: {
        width: 14,
        textAlign: "center",
        animation: active ? "spin 1s linear infinite" : "none"
      }
    }, done ? "✓" : active ? "◐" : "○"), label);
  })), /*#__PURE__*/React.createElement("div", {
    style: {
      marginTop: 14
    }
  }, /*#__PURE__*/React.createElement(Button, {
    variant: "primary",
    block: true,
    leftIcon: /*#__PURE__*/React.createElement(Icon, {
      name: "cloud-upload",
      size: 16
    }),
    onClick: runSync,
    loading: syncing
  }, syncing ? "同步中…" : "立即同步至飞书多维表格"))), /*#__PURE__*/React.createElement(Card, {
    padding: "md"
  }, /*#__PURE__*/React.createElement(Row, {
    icon: "message-square",
    iconTone: "blue",
    title: "\u7FA4\u53D1\u901A\u77E5\u4E0E\u534F\u540C\u5BA1\u6838",
    sub: "\u673A\u5668\u4EBA\u6D88\u606F / \u4E2A\u4EBA\u5361\u7247\u7FA4\u53D1",
    badge: /*#__PURE__*/React.createElement(Badge, {
      tone: "info"
    }, "\u914D\u7F6E\u53EF\u7528")
  }), /*#__PURE__*/React.createElement("div", {
    style: {
      display: "flex",
      flexDirection: "column",
      gap: 8,
      marginTop: 14
    }
  }, /*#__PURE__*/React.createElement("label", {
    style: {
      fontSize: "var(--text-xs)",
      color: "var(--text-muted)",
      fontWeight: 600
    }
  }, "\u9009\u62E9\u63A5\u6536\u901A\u77E5\u7684\u98DE\u4E66\u7FA4\u804A\uFF1A"), /*#__PURE__*/React.createElement(Select, {
    options: ["小红书文案运营审核群 (oc_chat_10293)", "露营项目内容策划小组 (oc_chat_88301)", "博主内容备份群 (oc_chat_73229)"]
  })), /*#__PURE__*/React.createElement("div", {
    style: {
      marginTop: 14
    }
  }, /*#__PURE__*/React.createElement(Button, {
    variant: "secondary",
    block: true,
    leftIcon: /*#__PURE__*/React.createElement(Icon, {
      name: "send",
      size: 16
    })
  }, "\u4E00\u952E\u53D1\u9001\u901A\u77E5\u81F3\u98DE\u4E66\u7FA4\u804A"))), /*#__PURE__*/React.createElement("div", {
    style: {
      perspective: 1000,
      height: 240
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      position: "relative",
      width: "100%",
      height: "100%",
      transformStyle: "preserve-3d",
      transition: "transform var(--dur-slow) var(--ease-out)",
      transform: scanned ? "rotateY(180deg)" : "none"
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      position: "absolute",
      inset: 0,
      backfaceVisibility: "hidden",
      background: "color-mix(in srgb, var(--hot-surface) 70%, white)",
      border: "1px solid var(--coral-300)",
      borderRadius: "var(--radius-lg)",
      padding: 18,
      display: "flex",
      flexDirection: "column",
      gap: 10
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      display: "flex",
      gap: 8
    }
  }, /*#__PURE__*/React.createElement(Icon, {
    name: "alert-triangle",
    size: 17,
    color: "var(--coral-600)"
  }), /*#__PURE__*/React.createElement("div", null, /*#__PURE__*/React.createElement("h4", {
    style: {
      margin: 0,
      fontSize: "var(--text-xs)",
      fontWeight: 700,
      color: "var(--coral-700)"
    }
  }, "\u98DE\u4E66\u4E2A\u4EBA\u8EAB\u4EFD\u5DF2\u8FC7\u671F"), /*#__PURE__*/React.createElement("p", {
    style: {
      margin: "2px 0 0",
      fontSize: 9,
      color: "var(--coral-600)"
    }
  }, "\u82E5\u9700\u4EE5\u60A8\u7684\u4E2A\u4EBA\u540D\u4E49\u5C06\u6587\u6848\u5BFC\u51FA\u81F3\u98DE\u4E66\u4E91\u6587\u6863\uFF0C\u8BF7\u626B\u7801\u8FDB\u884C User \u8EAB\u4EFD\u91CD\u8FDE\u3002"))), /*#__PURE__*/React.createElement("div", {
    style: {
      display: "flex",
      flexDirection: "column",
      alignItems: "center",
      gap: 8
    }
  }, /*#__PURE__*/React.createElement("button", {
    onClick: onScan,
    style: {
      background: "#fff",
      padding: 8,
      border: "1px solid var(--coral-300)",
      borderRadius: "var(--radius-md)",
      boxShadow: "var(--shadow-md)",
      cursor: "pointer"
    },
    title: "\u70B9\u6B64\u6A21\u62DF\u626B\u7801\u6210\u529F"
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      width: 84,
      height: 84,
      display: "grid",
      gridTemplateColumns: "repeat(3,1fr)",
      gap: 4,
      placeItems: "center"
    }
  }, [1, 0, 1, 0, 1, 0, 1, 0, 1].map((b, i) => /*#__PURE__*/React.createElement("div", {
    key: i,
    style: {
      width: 22,
      height: 22,
      background: b ? "var(--charcoal-default)" : "var(--gray-200)",
      borderRadius: 3
    }
  })))), /*#__PURE__*/React.createElement("span", {
    style: {
      fontSize: 8,
      color: "var(--coral-600)"
    }
  }, "\u4F7F\u7528\u98DE\u4E66\u626B\u7801\uFF0C\u6388\u6743 Scope \u6743\u9650"))), /*#__PURE__*/React.createElement("div", {
    style: {
      position: "absolute",
      inset: 0,
      backfaceVisibility: "hidden",
      transform: "rotateY(180deg)",
      background: "var(--green-500)",
      color: "#fff",
      borderRadius: "var(--radius-lg)",
      padding: 18,
      display: "flex",
      flexDirection: "column",
      alignItems: "center",
      justifyContent: "center",
      gap: 10,
      textAlign: "center"
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      width: 48,
      height: 48,
      borderRadius: "999px",
      background: "#fff",
      color: "var(--green-600)",
      display: "flex",
      alignItems: "center",
      justifyContent: "center",
      boxShadow: "var(--shadow-md)"
    }
  }, /*#__PURE__*/React.createElement(Icon, {
    name: "check",
    size: 24
  })), /*#__PURE__*/React.createElement("div", null, /*#__PURE__*/React.createElement("h4", {
    style: {
      margin: 0,
      fontSize: "var(--text-sm)",
      fontWeight: 700
    }
  }, "\u98DE\u4E66\u4E2A\u4EBA\u8EAB\u4EFD\u91CD\u8FDE\u6210\u529F"), /*#__PURE__*/React.createElement("p", {
    style: {
      margin: "4px 0 0",
      fontSize: 10,
      color: "rgba(255,255,255,0.85)"
    }
  }, "\u6B22\u8FCE\u56DE\u6765\uFF0C\u5F20\u6F47\u6F47\uFF01\u5DF2\u83B7\u53D6\u6240\u6709\u4E91\u7AEF\u6743\u9650\u3002"))))));
}
function Row({
  icon,
  iconTone,
  title,
  sub,
  badge
}) {
  const tones = {
    green: {
      bg: "var(--success-surface)",
      fg: "var(--success)",
      bd: "var(--success-border)"
    },
    blue: {
      bg: "var(--info-surface)",
      fg: "var(--info)",
      bd: "var(--info-border)"
    }
  };
  const t = tones[iconTone] || tones.green;
  return /*#__PURE__*/React.createElement("div", {
    style: {
      display: "flex",
      alignItems: "center",
      justifyContent: "space-between",
      borderBottom: "1px solid var(--oats-dark)",
      paddingBottom: 12
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      display: "flex",
      alignItems: "center",
      gap: 10
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      width: 32,
      height: 32,
      borderRadius: "var(--radius-sm)",
      background: t.bg,
      border: `1px solid ${t.bd}`,
      color: t.fg,
      display: "flex",
      alignItems: "center",
      justifyContent: "center"
    }
  }, /*#__PURE__*/React.createElement(Icon, {
    name: icon,
    size: 17
  })), /*#__PURE__*/React.createElement("div", null, /*#__PURE__*/React.createElement("h4", {
    style: {
      margin: 0,
      fontSize: "var(--text-sm)",
      fontWeight: 700,
      color: "var(--text-body)"
    }
  }, title), /*#__PURE__*/React.createElement("p", {
    style: {
      margin: "2px 0 0",
      fontSize: 10,
      color: "var(--text-subtle)"
    }
  }, sub))), badge);
}
function KV({
  k,
  v,
  muted,
  ok
}) {
  return /*#__PURE__*/React.createElement("div", {
    style: {
      display: "flex",
      justifyContent: "space-between"
    }
  }, /*#__PURE__*/React.createElement("span", {
    style: {
      color: "var(--text-muted)"
    }
  }, k), /*#__PURE__*/React.createElement("span", {
    style: {
      fontWeight: 500,
      color: ok ? "var(--success)" : muted ? "var(--text-muted)" : "var(--text-body)"
    }
  }, v));
}
Object.assign(window, {
  FeishuSync
});
})(); } catch (e) { __ds_ns.__errors.push({ path: "ui_kits/workbench/FeishuSync.jsx", error: String((e && e.message) || e) }); }

// ui_kits/workbench/PhonePreview.jsx
try { (() => {
// PhonePreview — the 小红书 mobile simulator (detail + feed modes).
function PhonePreview({
  note,
  mode,
  imgIdx,
  onPrev,
  onNext
}) {
  const {
    PhoneFrame,
    NoteCard,
    IconButton,
    Avatar
  } = window.DesignSystem_71831b;
  const D = window.XHS_DATA;
  return /*#__PURE__*/React.createElement("div", {
    style: {
      flex: 1,
      overflowY: "auto",
      padding: 24,
      background: "color-mix(in srgb, var(--oats-default) 60%, white)",
      display: "flex",
      justifyContent: "center",
      alignItems: "flex-start"
    },
    className: "custom-scrollbar"
  }, /*#__PURE__*/React.createElement(PhoneFrame, {
    width: 330
  }, mode === "detail" ? /*#__PURE__*/React.createElement(React.Fragment, null, /*#__PURE__*/React.createElement("div", {
    style: {
      paddingTop: 32,
      paddingBottom: 12,
      paddingLeft: 16,
      paddingRight: 16,
      borderBottom: "1px solid var(--gray-100)",
      display: "flex",
      alignItems: "center",
      justifyContent: "space-between",
      background: "rgba(255,255,255,0.95)",
      flexShrink: 0
    }
  }, /*#__PURE__*/React.createElement(Icon, {
    name: "chevron-left",
    size: 20,
    color: "var(--charcoal-default)"
  }), /*#__PURE__*/React.createElement("span", {
    style: {
      fontSize: "var(--text-sm)",
      fontWeight: "var(--weight-bold)"
    }
  }, "\u7B14\u8BB0\u8BE6\u60C5"), /*#__PURE__*/React.createElement(Icon, {
    name: "share",
    size: 16,
    color: "var(--charcoal-default)"
  })), /*#__PURE__*/React.createElement("div", {
    style: {
      flex: 1,
      overflowY: "auto",
      display: "flex",
      flexDirection: "column"
    },
    className: "custom-scrollbar"
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      width: "100%",
      aspectRatio: "1 / 1",
      position: "relative",
      overflow: "hidden",
      flexShrink: 0,
      background: "var(--accent-surface)"
    }
  }, /*#__PURE__*/React.createElement("img", {
    src: D.images[imgIdx],
    alt: "cover",
    style: {
      width: "100%",
      height: "100%",
      objectFit: "cover"
    }
  }), /*#__PURE__*/React.createElement("div", {
    style: {
      position: "absolute",
      left: 10,
      top: "50%",
      transform: "translateY(-50%)"
    }
  }, /*#__PURE__*/React.createElement(IconButton, {
    variant: "surface",
    rounded: "full",
    size: "sm",
    label: "\u4E0A\u4E00\u5F20",
    onClick: onPrev
  }, /*#__PURE__*/React.createElement(Icon, {
    name: "chevron-left",
    size: 15
  }))), /*#__PURE__*/React.createElement("div", {
    style: {
      position: "absolute",
      right: 10,
      top: "50%",
      transform: "translateY(-50%)"
    }
  }, /*#__PURE__*/React.createElement(IconButton, {
    variant: "surface",
    rounded: "full",
    size: "sm",
    label: "\u4E0B\u4E00\u5F20",
    onClick: onNext
  }, /*#__PURE__*/React.createElement(Icon, {
    name: "chevron-right",
    size: 15
  }))), /*#__PURE__*/React.createElement("div", {
    style: {
      position: "absolute",
      bottom: 12,
      left: "50%",
      transform: "translateX(-50%)",
      display: "flex",
      gap: 6
    }
  }, D.images.map((_, i) => /*#__PURE__*/React.createElement("span", {
    key: i,
    style: {
      width: 6,
      height: 6,
      borderRadius: "999px",
      background: i === imgIdx ? "#fff" : "rgba(255,255,255,0.55)"
    }
  })))), /*#__PURE__*/React.createElement("div", {
    style: {
      padding: "12px 16px",
      borderBottom: "1px solid var(--gray-100)",
      display: "flex",
      alignItems: "center",
      justifyContent: "space-between",
      flexShrink: 0
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      display: "flex",
      alignItems: "center",
      gap: 8
    }
  }, /*#__PURE__*/React.createElement(Avatar, {
    name: "Z",
    variant: "neutral",
    size: 28
  }), /*#__PURE__*/React.createElement("div", null, /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: 11,
      fontWeight: "var(--weight-bold)"
    }
  }, D.user.name), /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: 9,
      color: "var(--text-subtle)"
    }
  }, "\u521A\u624D\u5173\u8054\u4E86\u591A\u7EF4\u8868\u683C\u7B2C 4 \u884C"))), /*#__PURE__*/React.createElement("button", {
    style: {
      border: "1px solid var(--primary)",
      color: "var(--primary)",
      background: "transparent",
      padding: "2px 12px",
      borderRadius: "999px",
      fontSize: 10,
      fontWeight: "var(--weight-semibold)",
      cursor: "pointer"
    }
  }, "\u5173\u6CE8")), /*#__PURE__*/React.createElement("div", {
    style: {
      padding: 16,
      flex: 1
    }
  }, /*#__PURE__*/React.createElement("h3", {
    style: {
      margin: "0 0 12px",
      fontSize: "var(--text-sm)",
      fontWeight: "var(--weight-bold)",
      lineHeight: "var(--leading-snug)"
    }
  }, note.title), /*#__PURE__*/React.createElement("p", {
    style: {
      margin: 0,
      fontSize: "var(--text-xs)",
      color: "var(--charcoal-light)",
      lineHeight: "var(--leading-relaxed)",
      whiteSpace: "pre-wrap"
    }
  }, note.body))), /*#__PURE__*/React.createElement("div", {
    style: {
      height: 48,
      borderTop: "1px solid var(--gray-100)",
      display: "flex",
      alignItems: "center",
      justifyContent: "space-between",
      padding: "0 24px",
      background: "#fff",
      flexShrink: 0,
      color: "var(--text-muted)"
    }
  }, /*#__PURE__*/React.createElement("span", {
    style: {
      display: "inline-flex",
      alignItems: "center",
      gap: 6,
      fontSize: 10
    }
  }, /*#__PURE__*/React.createElement(Icon, {
    name: "heart",
    size: 16
  }), " \u70B9\u8D5E"), /*#__PURE__*/React.createElement("span", {
    style: {
      display: "inline-flex",
      alignItems: "center",
      gap: 6,
      fontSize: 10
    }
  }, /*#__PURE__*/React.createElement(Icon, {
    name: "star",
    size: 16
  }), " \u6536\u85CF"), /*#__PURE__*/React.createElement("span", {
    style: {
      display: "inline-flex",
      alignItems: "center",
      gap: 6,
      fontSize: 10
    }
  }, /*#__PURE__*/React.createElement(Icon, {
    name: "message-square",
    size: 16
  }), " \u8BC4\u8BBA"))) : /*#__PURE__*/React.createElement(React.Fragment, null, /*#__PURE__*/React.createElement("div", {
    style: {
      paddingTop: 32,
      paddingBottom: 12,
      display: "flex",
      alignItems: "center",
      justifyContent: "center",
      gap: 16,
      background: "rgba(255,255,255,0.97)",
      borderBottom: "1px solid var(--gray-100)",
      flexShrink: 0,
      fontSize: "var(--text-xs)"
    }
  }, /*#__PURE__*/React.createElement("span", {
    style: {
      color: "var(--text-subtle)"
    }
  }, "\u5173\u6CE8"), /*#__PURE__*/React.createElement("span", {
    style: {
      fontWeight: "var(--weight-bold)",
      borderBottom: "2px solid var(--primary)",
      paddingBottom: 4
    }
  }, "\u53D1\u73B0"), /*#__PURE__*/React.createElement("span", {
    style: {
      color: "var(--text-subtle)"
    }
  }, "\u9644\u8FD1")), /*#__PURE__*/React.createElement("div", {
    style: {
      flex: 1,
      overflowY: "auto",
      padding: 8,
      display: "grid",
      gridTemplateColumns: "1fr 1fr",
      gap: 8,
      alignContent: "start",
      background: "var(--oats-dark)"
    },
    className: "custom-scrollbar"
  }, /*#__PURE__*/React.createElement(NoteCard, {
    image: D.images[imgIdx],
    title: note.title,
    author: "\u5F20\u6F47\u6F47",
    authorInitial: "Z",
    likes: "1.2k"
  }), /*#__PURE__*/React.createElement(NoteCard, {
    dim: true,
    ratio: "4 / 5"
  }), /*#__PURE__*/React.createElement(NoteCard, {
    dim: true,
    ratio: "1 / 1"
  }), /*#__PURE__*/React.createElement(NoteCard, {
    dim: true,
    ratio: "3 / 4"
  }), /*#__PURE__*/React.createElement(NoteCard, {
    dim: true,
    ratio: "4 / 5"
  }), /*#__PURE__*/React.createElement(NoteCard, {
    dim: true,
    ratio: "3 / 4"
  })))));
}
Object.assign(window, {
  PhonePreview
});
})(); } catch (e) { __ds_ns.__errors.push({ path: "ui_kits/workbench/PhonePreview.jsx", error: String((e && e.message) || e) }); }

// ui_kits/workbench/RightCanvas.jsx
try { (() => {
// RightCanvas — tab shell (phone preview / Feishu sync) + bottom bar.
function RightCanvas({
  note,
  tab,
  setTab,
  mode,
  setMode,
  imgIdx,
  onPrev,
  onNext,
  scanned,
  onScan
}) {
  return /*#__PURE__*/React.createElement("section", {
    style: {
      width: "var(--rail-canvas)",
      borderLeft: "1px solid var(--border)",
      background: "var(--surface-card)",
      display: "flex",
      flexDirection: "column",
      flexShrink: 0,
      boxShadow: "var(--shadow-lg)",
      zIndex: 10
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      display: "flex",
      alignItems: "center",
      justifyContent: "space-between",
      borderBottom: "1px solid var(--border)",
      background: "color-mix(in srgb, var(--oats-light) 50%, white)",
      padding: "0 16px",
      flexShrink: 0
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      display: "flex",
      gap: 8,
      padding: "8px 0"
    }
  }, /*#__PURE__*/React.createElement(Tab, {
    active: tab === "mock",
    onClick: () => setTab("mock")
  }, "\uD83D\uDCF1 \u5C0F\u7EA2\u4E66\u624B\u673A\u9884\u89C8"), /*#__PURE__*/React.createElement(Tab, {
    active: tab === "feishu",
    onClick: () => setTab("feishu")
  }, "\uD83D\uDD17 \u98DE\u4E66\u540C\u6B65\u534F\u4F5C")), tab === "mock" && /*#__PURE__*/React.createElement("div", {
    style: {
      display: "flex",
      gap: 4,
      background: "var(--oats-default)",
      border: "1px solid var(--border)",
      borderRadius: "var(--radius-md)",
      padding: 3
    }
  }, /*#__PURE__*/React.createElement(Seg, {
    active: mode === "detail",
    onClick: () => setMode("detail")
  }, "\u8BE6\u60C5\u89C6\u7A97"), /*#__PURE__*/React.createElement(Seg, {
    active: mode === "feed",
    onClick: () => setMode("feed")
  }, "\u7011\u5E03\u6D41\u5361\u7247"))), tab === "mock" ? /*#__PURE__*/React.createElement(PhonePreview, {
    note: note,
    mode: mode,
    imgIdx: imgIdx,
    onPrev: onPrev,
    onNext: onNext
  }) : /*#__PURE__*/React.createElement(FeishuSync, {
    note: note,
    scanned: scanned,
    onScan: onScan
  }), /*#__PURE__*/React.createElement("div", {
    style: {
      height: 60,
      borderTop: "1px solid var(--border)",
      padding: "0 24px",
      background: "var(--surface-card)",
      display: "flex",
      alignItems: "center",
      justifyContent: "space-between",
      flexShrink: 0
    }
  }, /*#__PURE__*/React.createElement("span", {
    style: {
      fontSize: "var(--text-xs)",
      color: "var(--text-subtle)"
    },
    className: "font-tabular"
  }, "\u6587\u6848\u957F\u5EA6\uFF1A", note.body.length, " / 1000 \u5B57"), /*#__PURE__*/React.createElement(CopyButton, null)));
}
function Tab({
  active,
  onClick,
  children
}) {
  return /*#__PURE__*/React.createElement("button", {
    onClick: onClick,
    style: {
      padding: "6px 16px",
      borderRadius: "var(--radius-sm)",
      fontFamily: "var(--font-sans)",
      fontSize: "var(--text-sm)",
      fontWeight: active ? 600 : 500,
      cursor: "pointer",
      border: active ? "1px solid var(--border-coral)" : "1px solid transparent",
      background: active ? "var(--accent-surface)" : "transparent",
      color: active ? "var(--primary)" : "var(--text-muted)"
    }
  }, children);
}
function Seg({
  active,
  onClick,
  children
}) {
  return /*#__PURE__*/React.createElement("button", {
    onClick: onClick,
    style: {
      padding: "4px 10px",
      borderRadius: "var(--radius-sm)",
      border: "none",
      cursor: "pointer",
      fontSize: 10,
      fontFamily: "var(--font-sans)",
      fontWeight: active ? 600 : 400,
      background: active ? "#fff" : "transparent",
      color: active ? "var(--primary)" : "var(--text-muted)",
      boxShadow: active ? "var(--shadow-xs)" : "none"
    }
  }, children);
}
function CopyButton() {
  const {
    Button
  } = window.DesignSystem_71831b;
  const [done, setDone] = React.useState(false);
  return /*#__PURE__*/React.createElement(Button, {
    variant: "soft",
    size: "sm",
    leftIcon: /*#__PURE__*/React.createElement(Icon, {
      name: done ? "check" : "copy",
      size: 14
    }),
    onClick: () => {
      setDone(true);
      setTimeout(() => setDone(false), 1600);
    }
  }, done ? "已复制" : "一键复制纯文案");
}
Object.assign(window, {
  RightCanvas
});
})(); } catch (e) { __ds_ns.__errors.push({ path: "ui_kits/workbench/RightCanvas.jsx", error: String((e && e.message) || e) }); }

// ui_kits/workbench/Sidebar.jsx
try { (() => {
// Sidebar — new-chat CTA, recent creations list, user footer.
function Sidebar({
  activeId,
  onSelect,
  onNewChat
}) {
  const {
    Button,
    Badge,
    Avatar,
    IconButton
  } = window.DesignSystem_71831b;
  const D = window.XHS_DATA;
  return /*#__PURE__*/React.createElement("aside", {
    style: {
      width: "var(--rail-sidebar)",
      background: "var(--surface-sidebar)",
      borderRight: "1px solid var(--border)",
      display: "flex",
      flexDirection: "column",
      justifyContent: "space-between",
      flexShrink: 0
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      display: "flex",
      flexDirection: "column",
      padding: 16,
      gap: 16,
      overflow: "hidden",
      height: "100%"
    }
  }, /*#__PURE__*/React.createElement(Button, {
    variant: "primary",
    block: true,
    leftIcon: /*#__PURE__*/React.createElement(Icon, {
      name: "square-pen",
      size: 16
    }),
    onClick: onNewChat
  }, "\u5F00\u542F\u5168\u65B0\u7075\u611F\u5BF9\u8BDD"), /*#__PURE__*/React.createElement("div", {
    style: {
      display: "flex",
      alignItems: "center",
      justifyContent: "space-between",
      marginTop: 4
    }
  }, /*#__PURE__*/React.createElement(Eyebrow, null, "\u6700\u8FD1\u521B\u4F5C"), /*#__PURE__*/React.createElement("span", {
    style: {
      fontSize: 10,
      color: "var(--gray-300)"
    }
  }, "\u6309 Ctrl+J \u9690\u85CF")), /*#__PURE__*/React.createElement("div", {
    style: {
      display: "flex",
      flexDirection: "column",
      gap: 4,
      overflowY: "auto"
    },
    className: "custom-scrollbar"
  }, D.recents.map(r => {
    const active = r.id === activeId;
    return /*#__PURE__*/React.createElement("button", {
      key: r.id,
      onClick: () => onSelect(r.id),
      style: {
        display: "flex",
        alignItems: "center",
        justifyContent: "space-between",
        gap: 8,
        width: "100%",
        textAlign: "left",
        padding: "10px 12px",
        fontSize: "var(--text-sm)",
        borderRadius: "var(--radius-sm)",
        cursor: "pointer",
        border: "none",
        borderLeft: active ? "2px solid var(--primary)" : "2px solid transparent",
        background: active ? "var(--oats-dark)" : "transparent",
        color: active ? "var(--primary)" : "var(--text-muted)",
        fontWeight: active ? "var(--weight-semibold)" : "var(--weight-regular)",
        fontFamily: "var(--font-sans)"
      }
    }, /*#__PURE__*/React.createElement("span", {
      style: {
        overflow: "hidden",
        textOverflow: "ellipsis",
        whiteSpace: "nowrap"
      }
    }, r.icon, " ", r.title), /*#__PURE__*/React.createElement(Badge, {
      tone: r.status === "synced" ? "synced" : "draft",
      shape: "chip"
    }, r.status === "synced" ? "已同步" : "草稿"));
  }))), /*#__PURE__*/React.createElement("div", {
    style: {
      padding: 16,
      borderTop: "1px solid var(--oats-dark)",
      display: "flex",
      alignItems: "center",
      justifyContent: "space-between"
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      display: "flex",
      alignItems: "center",
      gap: 12
    }
  }, /*#__PURE__*/React.createElement(Avatar, {
    name: "Z"
  }), /*#__PURE__*/React.createElement("span", {
    style: {
      fontSize: "var(--text-sm)",
      fontWeight: "var(--weight-medium)",
      color: "var(--text-body)"
    }
  }, D.user.name)), /*#__PURE__*/React.createElement(IconButton, {
    label: "\u9000\u51FA\u767B\u5F55"
  }, /*#__PURE__*/React.createElement(Icon, {
    name: "log-out"
  }))));
}
Object.assign(window, {
  Sidebar
});
})(); } catch (e) { __ds_ns.__errors.push({ path: "ui_kits/workbench/Sidebar.jsx", error: String((e && e.message) || e) }); }

// ui_kits/workbench/TopBar.jsx
try { (() => {
// TopBar — brand lockup, Feishu CLI status, and the expired-identity
// re-auth prompt that flips the right canvas to the scan card.
function TopBar({
  onReauth
}) {
  const {
    Badge
  } = window.DesignSystem_71831b;
  return /*#__PURE__*/React.createElement("header", {
    style: {
      height: "var(--topbar-height)",
      background: "rgba(255,255,255,0.85)",
      backdropFilter: "blur(8px)",
      borderBottom: "1px solid var(--border)",
      padding: "0 24px",
      display: "flex",
      alignItems: "center",
      justifyContent: "space-between",
      flexShrink: 0,
      zIndex: 10
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      display: "flex",
      alignItems: "center",
      gap: 10
    }
  }, /*#__PURE__*/React.createElement("span", {
    style: {
      width: 32,
      height: 32,
      borderRadius: "var(--radius-md)",
      background: "var(--coral-brand)",
      display: "flex",
      alignItems: "center",
      justifyContent: "center",
      fontSize: 18,
      boxShadow: "var(--shadow-coral)"
    }
  }, "\uD83C\uDF60"), /*#__PURE__*/React.createElement("h1", {
    style: {
      margin: 0,
      fontFamily: "var(--font-display)",
      fontWeight: "var(--weight-bold)",
      fontSize: "var(--text-lg)",
      letterSpacing: "var(--tracking-tight)",
      color: "var(--text-body)"
    }
  }, "\u5C0F\u7EA2\u4E66\u6587\u6848\u52A9\u624B", /*#__PURE__*/React.createElement("span", {
    style: {
      fontFamily: "var(--font-sans)",
      fontSize: "var(--text-xs)",
      fontWeight: 400,
      color: "var(--text-subtle)",
      marginLeft: 8
    }
  }, "v1.2 \u5DE5\u4F5C\u53F0"))), /*#__PURE__*/React.createElement("div", {
    style: {
      display: "flex",
      alignItems: "center",
      gap: 14
    }
  }, /*#__PURE__*/React.createElement(Badge, {
    tone: "synced",
    dot: true
  }, "\u98DE\u4E66 CLI \u72B6\u6001\uFF1AReady (bot)"), /*#__PURE__*/React.createElement("button", {
    onClick: onReauth,
    style: {
      display: "inline-flex",
      alignItems: "center",
      gap: 6,
      background: "var(--accent-surface)",
      border: "1px solid var(--border-coral)",
      color: "var(--primary)",
      padding: "5px 10px",
      borderRadius: "var(--radius-full)",
      fontSize: "var(--text-xs)",
      fontFamily: "var(--font-sans)",
      cursor: "pointer"
    }
  }, /*#__PURE__*/React.createElement(Icon, {
    name: "key-round",
    size: 12
  }), "User \u8EAB\u4EFD\u5DF2\u8FC7\u671F\uFF0C\u70B9\u6B64\u626B\u7801\u91CD\u8FDE")));
}
Object.assign(window, {
  TopBar
});
})(); } catch (e) { __ds_ns.__errors.push({ path: "ui_kits/workbench/TopBar.jsx", error: String((e && e.message) || e) }); }

// ui_kits/workbench/app.jsx
try { (() => {
// App — root of the 小红书文案助手 workbench recreation.
function App() {
  const D = window.XHS_DATA;
  const [activeRecent, setActiveRecent] = React.useState(1);
  const [note, setNote] = React.useState(D.topics[0]);
  const [chosenId, setChosenId] = React.useState(null);
  const [writing, setWriting] = React.useState(false);
  const [tab, setTab] = React.useState("mock");
  const [mode, setMode] = React.useState("detail");
  const [imgIdx, setImgIdx] = React.useState(0);
  const [paletteOpen, setPaletteOpen] = React.useState(false);
  const [scanned, setScanned] = React.useState(false);
  const [input, setInput] = React.useState("");

  // Ctrl+P / Esc
  React.useEffect(() => {
    const onKey = e => {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "p") {
        e.preventDefault();
        setPaletteOpen(o => !o);
      } else if (e.key === "Escape") {
        setPaletteOpen(false);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);
  const selectTopic = id => {
    const topic = D.topics.find(t => t.id === id);
    setChosenId(id);
    setWriting(true);
    setTab("mock");
    setMode("detail");
    setTimeout(() => {
      setNote(topic);
      setImgIdx(0);
      setWriting(false);
    }, 1500);
  };
  const runCommand = cmd => {
    setPaletteOpen(false);
    setNote(n => {
      if (cmd === "polish") {
        return {
          ...n,
          body: "⛺ 夏日避暑天花板！露营党看过来！✨\n\n" + n.body
        };
      }
      if (cmd === "shorten") {
        return {
          ...n,
          body: n.body.slice(0, 300).trimEnd() + "…\n\n#露营必备 #户外美学"
        };
      }
      if (cmd === "tags") {
        return {
          ...n,
          body: n.body.trimEnd() + " #夏日避暑指南 #爆款露营装备"
        };
      }
      return n;
    });
  };
  const nextImg = () => setImgIdx(i => (i + 1) % D.images.length);
  const prevImg = () => setImgIdx(i => (i - 1 + D.images.length) % D.images.length);
  return /*#__PURE__*/React.createElement("div", {
    style: {
      height: "100vh",
      width: "100vw",
      display: "flex",
      flexDirection: "column",
      overflow: "hidden",
      color: "var(--text-body)",
      fontFamily: "var(--font-sans)"
    }
  }, /*#__PURE__*/React.createElement(TopBar, {
    onReauth: () => {
      setTab("feishu");
      setScanned(false);
    }
  }), /*#__PURE__*/React.createElement("main", {
    style: {
      flex: 1,
      display: "flex",
      minHeight: 0
    }
  }, /*#__PURE__*/React.createElement(Sidebar, {
    activeId: activeRecent,
    onSelect: setActiveRecent,
    onNewChat: () => {
      setChosenId(null);
      setWriting(false);
    }
  }), /*#__PURE__*/React.createElement(ChatPane, {
    chosenId: chosenId,
    writing: writing,
    onSelectTopic: selectTopic,
    onOpenPalette: () => setPaletteOpen(true),
    input: input,
    setInput: setInput,
    onSend: () => {
      if (input.trim()) {
        setInput("");
      }
    }
  }), /*#__PURE__*/React.createElement(RightCanvas, {
    note: note,
    tab: tab,
    setTab: setTab,
    mode: mode,
    setMode: setMode,
    imgIdx: imgIdx,
    onPrev: prevImg,
    onNext: nextImg,
    scanned: scanned,
    onScan: () => setScanned(true)
  })), /*#__PURE__*/React.createElement(CommandPalette, {
    open: paletteOpen,
    onClose: () => setPaletteOpen(false),
    onRun: runCommand
  }));
}
ReactDOM.createRoot(document.getElementById("root")).render(/*#__PURE__*/React.createElement(App, null));
})(); } catch (e) { __ds_ns.__errors.push({ path: "ui_kits/workbench/app.jsx", error: String((e && e.message) || e) }); }

// ui_kits/workbench/data.js
try { (() => {
// Sample content for the 小红书文案助手 workbench recreation.
// Mirrors the data in the source product's mockup.

window.XHS_DATA = {
  user: {
    name: "张潇潇 (运营组)",
    initial: "Z",
    team: "运营组"
  },
  recents: [{
    id: 1,
    icon: "⛺",
    title: "露营装备好物推荐",
    status: "synced"
  }, {
    id: 2,
    icon: "☕",
    title: "咖啡探店爆款草稿",
    status: "draft"
  }, {
    id: 3,
    icon: "👗",
    title: "夏季轻熟风穿搭笔记",
    status: "draft"
  }],
  images: ["https://images.unsplash.com/photo-1504280390367-361c6d9f38f4?auto=format&fit=crop&w=600&q=80", "https://images.unsplash.com/photo-1523987355523-c7b5b0dd90a7?auto=format&fit=crop&w=600&q=80", "https://images.unsplash.com/photo-1510312305653-8ed496efae75?auto=format&fit=crop&w=600&q=80"],
  thinkingSteps: [{
    label: "已成功连接并解析飞书多维表格 (45 条数据)",
    state: "done"
  }, {
    label: "正在计算博主点赞权重并提炼选题规律...",
    state: "active"
  }],
  thinkingLogs: [{
    time: "12:25:01",
    text: "开始拉取多维表格，自动过滤附件大字段以保护上下文..."
  }, {
    time: "12:25:03",
    text: "数学统计分析：高互动博主具有「实用避坑」「极简平替」倾向。"
  }, {
    time: "12:25:04",
    text: "提取高频热词：精致露营、搬家式装备、新手避坑。"
  }, {
    time: "12:25:05",
    text: "已为用户规划 3 条候选爆款选题方案..."
  }],
  topics: [{
    id: 1,
    title: "精致露营「搬家式」装备清单",
    rationale: "主打：视觉冲击、高互动分享率。分析显示赞藏比极高。",
    hotRate: 96,
    body: `夏天太适合露营啦！⛺但是作为一个精致的搬家式露营玩家，带什么装备去真的大有讲究！今天就给大家盘点一下我私藏的「搬家式」露营好物，少带一件体验感都打折！

👇精致露营必带清单：
1️⃣ 双顶充气天幕：不仅防雨防晒，最重要是拍照真的超出片！空间很大，容纳8个人也宽敞。
2️⃣ 蛋卷桌+双人折叠椅：别带简易折叠椅了，蛋卷桌才是精致露营的灵魂。放上咖啡机和多功能气罐，格调拉满。
3️⃣ 露营氛围灯（汽灯/串灯）：天黑的那一刻，把暖黄色的灯串挂起来，配上篝火，氛围感直接封神！✨
4️⃣ 便携制冰机+露营保温箱：炎热的夏天，在山野里喝上一口带冰块的冷萃咖啡，这才是向往的生活啊！

📝装备挑选TIPS：
购买前一定要看折叠后的收纳体积！我的车后备箱就是这么被塞满的（笑哭）
大家还有什么必带的露营神器？在评论区一起交流呀！

#露营清单 #精致露营 #户外好物 #周末去哪玩 #露营穿搭 #夏天去露营 #露营好物`
  }, {
    id: 2,
    title: "百元搞定！新手露营避坑极简装备",
    rationale: "主打：极高实用价值、痛点防坑、收藏导向。",
    hotRate: 92,
    body: `别被那些大几千的露营装备劝退了！新手第一次去露营，主打一个性价比和实用！今天就教大家用几百块搞定一整套防坑装备，少花冤枉钱！

❌千万别买的避坑雷区：
- 百元以下的简易帐篷：防雨差风一吹就倒，睡在里面就是蒸桑拿。
- 巨重无比的实木蛋卷桌：除非你有壮汉帮你搬，否则带去一次就想扔。

✅新手闭眼入平替清单：
1️⃣ 自动速开帐篷（￥200左右）：新手最怕搭帐篷满头大汗，速开帐篷省心省力。
2️⃣ 铝合金折叠桌+月亮椅（￥150一套）：轻便好携带，月亮椅包裹性强，坐着贼舒服。
3️⃣ 便携防风卡式炉（￥50）：野外煮个泡面、烧个热水太方便了，性价比天花板。

觉得有用赶紧收藏起来，露营时翻出来对着买！

#露营避坑 #新手露营 #性价比露营装备 #省钱露营 #露营指南`
  }, {
    id: 3,
    title: "氛围感拉满：山野落日下的星空篝火美学",
    rationale: "主打：视觉种草、情绪共鸣、高吸睛图文。",
    hotRate: 88,
    body: `当太阳缓缓落下山头，把整片山野染成蜜橘色的那一刻，我就知道这趟露营值了。🌅

夜幕降临，串灯亮起，篝火噼啪作响，朋友们围坐着聊到深夜——这种慢下来的氛围感，才是露营真正的奢侈。✨

📷出片小心机：
· 落日时分逆光拍剪影，氛围感直接拉满
· 串灯绕在天幕支架上，夜景随手一拍都是大片
· 篝火 + 热饮的特写，温暖治愈

愿你也能在山野里，找到属于自己的星空。🌿

#露营氛围感 #星空露营 #落日 #治愈系 #山野生活`
  }],
  commands: [{
    id: "polish",
    icon: "sparkles",
    color: "var(--coral-500)",
    name: "/polish 智能润色",
    desc: "自动优化语气，使其更有种草感"
  }, {
    id: "shorten",
    icon: "scissors",
    color: "var(--amber-500)",
    name: "/shorten 文案瘦身",
    desc: "裁剪段落篇幅以符合 1000 字限制"
  }, {
    id: "tags",
    icon: "hash",
    color: "var(--topicblue-default)",
    name: "/tags 话题生成",
    desc: "智能抓取当下高流量露营 tag"
  }],
  recommendedTags: ["露营分享", "户外美学", "夏日避暑指南", "爆款露营装备"]
};
})(); } catch (e) { __ds_ns.__errors.push({ path: "ui_kits/workbench/data.js", error: String((e && e.message) || e) }); }

// ui_kits/workbench/ui.jsx
try { (() => {
// Shared UI helpers for the workbench kit.
//
// Icon — renders a Lucide glyph as a CSS mask over a <span>, so it
// inherits `currentColor`, is fully React-controlled (no DOM-node
// replacement à la lucide.createIcons), and swaps cleanly on
// re-render. Backed by the lucide-static CDN.
const LUCIDE_BASE = "https://unpkg.com/lucide-static@0.460.0/icons/";
function Icon({
  name,
  size = 16,
  color,
  style = {}
}) {
  const url = `${LUCIDE_BASE}${name}.svg`;
  return /*#__PURE__*/React.createElement("span", {
    "aria-hidden": "true",
    style: {
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
      ...style
    }
  });
}

// Eyebrow / section label
function Eyebrow({
  children,
  style = {}
}) {
  return /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: "var(--text-2xs)",
      fontWeight: "var(--weight-semibold)",
      letterSpacing: "var(--tracking-wide)",
      textTransform: "uppercase",
      color: "var(--text-subtle)",
      ...style
    }
  }, children);
}
Object.assign(window, {
  Icon,
  Eyebrow
});
})(); } catch (e) { __ds_ns.__errors.push({ path: "ui_kits/workbench/ui.jsx", error: String((e && e.message) || e) }); }

__ds_ns.HashtagTag = __ds_scope.HashtagTag;

__ds_ns.ThinkingAura = __ds_scope.ThinkingAura;

__ds_ns.TopicCard = __ds_scope.TopicCard;

__ds_ns.Avatar = __ds_scope.Avatar;

__ds_ns.Badge = __ds_scope.Badge;

__ds_ns.Button = __ds_scope.Button;

__ds_ns.Card = __ds_scope.Card;

__ds_ns.IconButton = __ds_scope.IconButton;

__ds_ns.StatCard = __ds_scope.StatCard;

__ds_ns.NoteCard = __ds_scope.NoteCard;

__ds_ns.PhoneFrame = __ds_scope.PhoneFrame;

__ds_ns.Input = __ds_scope.Input;

__ds_ns.Select = __ds_scope.Select;

__ds_ns.Textarea = __ds_scope.Textarea;

})();
