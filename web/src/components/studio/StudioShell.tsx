"use client";

// StudioShell — the 创作运营工作室 root composition. Faithful to
// 小红书文案助手 Design System/ui_kits/studio/app.jsx (StudioApp) MINUS the prototype
// scaffolding: no Scaler (real responsive instead of 1360px letterbox),
// ReactDOM.render (Next mounts via AppShell → page.tsx).

import { useState } from "react";
import { useStudio } from "./StudioContext";
import { StudioTopBar } from "./Shell";
import { CreationScreen, EvidencePanel, type RightLayout } from "./CreationScreen";
import { DeepCreation, type DeepForm } from "./DeepCreation";
import { Operations, type OpsHosting } from "./Operations";
import { TweaksPanel, TweakRadio, TweakSection } from "./TweaksPanel";

type StudioTweaks = {
  rightLayout: RightLayout;
  deepForm: DeepForm;
  opsHosting: OpsHosting;
};

const TWEAK_DEFAULTS: StudioTweaks = {
  rightLayout: "stack",
  deepForm: "immersive",
  opsHosting: "page",
};

export function StudioShell() {
  const { section, setSection, selectedEvidence } = useStudio();
  const [tweaks, setTweaks] = useState<StudioTweaks>(TWEAK_DEFAULTS);
  const setTweak = <K extends keyof StudioTweaks>(key: K, value: StudioTweaks[K]) => {
    setTweaks((prev) => ({ ...prev, [key]: value }));
  };

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
        {section === "create" && <CreationScreen rightLayout={tweaks.rightLayout} />}
        {section === "deep" && <DeepCreation form={tweaks.deepForm} />}
        {section === "ops" && <Operations hosting={tweaks.opsHosting} />}
      </div>

      {selectedEvidence && <EvidencePanel />}
      <TweaksPanel title="Tweaks · 方案探索">
        <TweakSection label="① 创作 · 右侧布局（选题卡 + 创作栏）" />
        <TweakRadio
          label="布局"
          value={tweaks.rightLayout}
          options={[
            { value: "stack", label: "上下堆叠" },
            { value: "split", label: "左右分栏" },
            { value: "composer", label: "仅创作栏" },
          ]}
          onChange={(rightLayout) => {
            setTweak("rightLayout", rightLayout);
            setSection("create");
          }}
        />
        <TweakSection label="② 深度创作 · 形态" />
        <TweakRadio
          label="形态"
          value={tweaks.deepForm}
          options={[
            { value: "immersive", label: "沉浸双栏" },
            { value: "flow", label: "分步流程" },
            { value: "workspace", label: "多栏工作台" },
          ]}
          onChange={(deepForm) => {
            setTweak("deepForm", deepForm);
            setSection("deep");
          }}
        />
        <TweakSection label="③ 账号运营 · 承载方式" />
        <TweakRadio
          label="承载"
          value={tweaks.opsHosting}
          options={[
            { value: "page", label: "独立页面" },
            { value: "inline", label: "会话内" },
            { value: "hybrid", label: "同屏融合" },
          ]}
          onChange={(opsHosting) => {
            setTweak("opsHosting", opsHosting);
            setSection("ops");
          }}
        />
      </TweaksPanel>
    </main>
  );
}
