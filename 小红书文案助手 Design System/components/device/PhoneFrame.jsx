import React from "react";

/**
 * PhoneFrame — the 小红书 mobile-preview bezel. A charcoal iPhone
 * shell with a notch; children render as the screen. Used by the
 * right-canvas note preview.
 */
export function PhoneFrame({ children, width = 340, style = {}, ...rest }) {
  return (
    <div
      style={{
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
        ...style,
      }}
      {...rest}
    >
      {/* notch */}
      <div
        style={{
          position: "absolute",
          top: 0,
          left: "50%",
          transform: "translateX(-50%)",
          width: 120,
          height: 22,
          background: "var(--charcoal-default)",
          borderBottomLeftRadius: 16,
          borderBottomRightRadius: 16,
          zIndex: 20,
        }}
      />
      {children}
    </div>
  );
}
