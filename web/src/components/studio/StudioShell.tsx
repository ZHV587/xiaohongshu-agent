"use client";

// StudioShell — the 创作运营工作室 root composition. Faithful to
// design_system/ui_kits/studio/app.jsx (StudioApp) MINUS the prototype
// scaffolding: no Scaler (real responsive instead of 1360px letterbox),
// no Tweaks panel (production ships the default config only), no
// ReactDOM.render (Next mounts via AppShell → page.tsx).

import { useStudio } from "./StudioContext";
import { StudioTopBar } from "./Shell";
import { CreationScreen, EvidencePanel } from "./CreationScreen";
import { DeepCreation } from "./DeepCreation";
import { Operations } from "./Operations";

export function StudioShell() {
  const { section, setSection, selectedEvidence } = useStudio();
  return (
    <div
      style={{
        height: "100vh",
        width: "100%",
        display: "flex",
        flexDirection: "column",
        overflow: "hidden",
        fontFamily: "var(--font-sans)",
        color: "var(--text-body)",
        background: "var(--background)",
      }}
    >
      {section !== "deep" && <StudioTopBar section={section} setSection={setSection} />}
      <div
        key={section}
        style={{ flex: 1, display: "flex", flexDirection: "column", minHeight: 0, animation: "secIn 0.3s var(--ease-out)" }}
      >
        {section === "create" && <CreationScreen />}
        {section === "deep" && <DeepCreation />}
        {section === "ops" && <Operations />}
      </div>

      {selectedEvidence && <EvidencePanel />}
    </div>
  );
}
