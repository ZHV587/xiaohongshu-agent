"use client";

// StudioShell — the 创作运营工作室 root composition. Faithful to
// 小红书文案助手 Design System, with prototype-only exploration controls removed
// from the production surface.

import { useStudio } from "./useStudio";
import { StudioTopBar } from "./Shell";
import { CreationScreen, EvidencePanel } from "./CreationScreen";
import { DeepCreation } from "./DeepCreation";
import { Operations } from "./Operations";

export function StudioShell() {
  const { section, setSection, selectedEvidence } = useStudio();

  return (
    <main
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
      <h1 className="sr-only">小红书创作运营工作室</h1>
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
    </main>
  );
}
