# Web Production Final Design System Alignment Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Align the production web desktop UI to the final approved design-system direction without shipping prototype exploration controls.

**Architecture:** Treat `小红书文案助手 Design System/tokens`, `guidelines`, DS primitives, and stable workbench/studio references as design input. Production code in `web/src` must expose only fixed final screen composition: creation, deep creation, operations, Workbench chat, Feishu sync, command palette, thinking UI, and response UI.

**Tech Stack:** Next.js 15, React, TypeScript, CSS custom properties, existing `web/src/components/ds` primitives, Node test runner, Playwright.

---

## Final Source Boundary

- Design tokens and visual rules: `小红书文案助手 Design System/tokens/*.css`, `styles.css`, `guidelines/*.card.html`, and `web/src/app/globals.css`.
- Component vocabulary: `小红书文案助手 Design System/components/**` and production `web/src/components/ds/**`.
- Stable production references: `ui_kits/workbench` for desktop workbench composition and stable portions of `ui_kits/studio` for creation/deep/operations information architecture.
- Prototype-only references: `ui_kits/studio/Tweaks` controls, multi-layout switches, exploration labels, CDN prototype runtime, and phone preview surfaces. These must not ship in production.

## Production Prohibitions

- No `TweaksPanel`, `TweakRadio`, `TweakSection`, `TweakSelect`, `TweakToggle`, `TweakNumber`, or `TweakColor` under `web/src`.
- No visible `Tweaks · 方案探索`, `方案探索`, or `探索性选题` copy in production.
- No production API props or branches named `rightLayout`, `deepForm`, `opsHosting`, `RightLayout`, `DeepForm`, or `OpsHosting`.
- No `DeepFlow`, `DeepWorkspace`, `OpsInline`, or `OpsHybrid` production branches.
- No desktop phone preview feature: `PhonePreview`, `手机预览`, `详情视窗`, `瀑布流卡片`, production `PhoneFrame`/`NoteCard` usage.

---

## Tasks

### Task 1: Lock Production Boundary With Tests

**Files:**
- Modify: `web/tests/ds-production-adherence.test.ts`
- Modify: `web/tests/ds-ui-kit-alignment.test.ts`
- Modify: `web/tests/e2e/ds-desktop-helpers.ts`
- Modify: `web/tests/e2e/ds-desktop-parity.spec.ts`
- Modify: `web/tests/e2e/ds-desktop-visual.spec.ts`

- [x] Replace tests that required Studio Tweaks with tests that require fixed final screen composition.
- [x] Add static source guards against exploration controls and non-final variant names.
- [x] Update browser UAT helpers to assert exploration controls are absent.
- [x] Verify the new tests fail before implementation.

Run:

```powershell
npm run test:unit -- --test-name-pattern "fixed final|prototype exploration|production desktop"
```

Expected red state before implementation: failures for `StudioShell`, `CreationScreen`, `DeepCreation`, `Operations`, and prototype exploration markers.

### Task 2: Remove Prototype Exploration From Production Studio

**Files:**
- Modify: `web/src/components/studio/StudioShell.tsx`
- Delete: `web/src/components/studio/TweaksPanel.tsx`
- Modify: `web/src/components/studio/CreationScreen.tsx`
- Modify: `web/src/components/studio/DeepCreation.tsx`
- Modify: `web/src/components/studio/Operations.tsx`

- [x] Render `<CreationScreen />`, `<DeepCreation />`, and `<Operations />` with no variant props.
- [x] Delete `TweaksPanel.tsx`.
- [x] Fix `CreationScreen` to the final right-panel layout.
- [x] Fix `DeepCreation` to the immersive editor plus A/B comparison.
- [x] Fix `Operations` to the standalone page/matrix mode.
- [x] Rename trend prompts from exploration wording to production-ready topic wording.

### Task 3: Verify Web Quality Gates

**Files:**
- Read: `web/package.json`
- Read: `web/playwright.config.ts`

- [x] Run targeted unit tests.
- [x] Run full web unit tests.
- [x] Run lint with no warning output.
- [x] Run production build with no application warnings.
- [x] Run desktop Playwright UAT for Studio and Workbench.

Commands:

```powershell
npm run test:unit -- --test-name-pattern "fixed final|prototype exploration|production desktop"
npm run test:unit
npm run lint
npm run build
npx playwright test tests/e2e/ds-desktop-parity.spec.ts tests/e2e/ds-desktop-visual.spec.ts
```

### Task 4: Repository And Production Deployment

**Files:**
- Read: `scripts/deploy.py`
- Read: `docker-compose.yml`
- Read: `langgraph.json`

- [ ] Confirm `git status --short` contains only intended files.
- [ ] Commit with a production-scoped message.
- [ ] Push to `origin/master`.
- [ ] Deploy with `uv run python scripts/deploy.py`.
- [ ] Run production health checks after deploy.

Commands:

```powershell
git status --short
git add web docs
git commit -m "fix(web): remove prototype exploration from production ui"
git push origin master
uv run python scripts/deploy.py
```

---

## Self-Review

- Spec coverage: Covers design source boundary, production prohibitions, Studio final composition, Workbench phone-preview removal, test guards, browser UAT, and deployment.
- Placeholder scan: No TBD/TODO placeholders. All files and commands are explicit.
- Type consistency: Final production component names are `StudioShell`, `CreationScreen`, `DeepCreation`, `Operations`, `WorkbenchShell`, `ThinkingAura`, `FeishuSync`, and `CommandPalette`. Removed names are explicitly listed as prohibited.
