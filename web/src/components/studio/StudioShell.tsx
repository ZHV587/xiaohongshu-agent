"use client";

// StudioShell — the 创作运营工作室 root composition. Faithful to
// 小红书文案助手 Design System, with prototype-only exploration controls removed
// from the production surface.

import { useStudio } from "./useStudio";
import { StudioTopBar } from "./Shell";
import { CreationScreen, EvidencePanel, DetailModal } from "./CreationScreen";
import { DeepCreation } from "./DeepCreation";
import { Operations } from "./Operations";

export function StudioShell() {
  const { section, setSection, selectedEvidence, detail } = useStudio();

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
      {/* 三个工作区常驻挂载、按 section 切 display,而非条件渲染/换 key 重挂 ——
          否则每次切换都卸载重建屏幕,丢失屏内本地态(创作区草稿输入框、已展开的选题详情、
          深创的编辑/对比模式等),用户返回时以为"生成的内容没了"。数据本身在 StudioProvider,
          常驻不会重复拉取。仅对当前可见区加一次进入动画。 */}
      {(["create", "deep", "ops"] as const).map((s) => (
        <div
          key={s}
          style={{
            flex: section === s ? 1 : undefined,
            display: section === s ? "flex" : "none",
            flexDirection: "column",
            minHeight: 0,
            animation: section === s ? "secIn 0.3s var(--ease-out)" : undefined,
          }}
        >
          {s === "create" && <CreationScreen />}
          {s === "deep" && <DeepCreation />}
          {s === "ops" && <Operations />}
        </div>
      ))}

      {selectedEvidence && <EvidencePanel />}
      {detail && <DetailModal />}
    </main>
  );
}
