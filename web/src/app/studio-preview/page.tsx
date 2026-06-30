"use client";

// DEV-ONLY visual-verification route for the 创作运营工作室. Mounts StudioShell
// with the design-package fixture (no AuthGate / no backend) so the studio can
// be pixel-compared against design_system/ui_kits/studio. Removed before prod.

import { StudioPreviewProvider } from "@/components/studio/StudioPreviewProvider";
import { StudioShell } from "@/components/studio/StudioShell";

export default function StudioPreviewPage() {
  return (
    <StudioPreviewProvider>
      <StudioShell />
    </StudioPreviewProvider>
  );
}
