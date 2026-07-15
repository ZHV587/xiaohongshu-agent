import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { join } from "node:path";
import test from "node:test";

const studio = readFileSync(join(process.cwd(), "src", "components", "studio", "StudioContext.tsx"), "utf8");
const editor = readFileSync(join(process.cwd(), "src", "components", "studio", "DeepEditor.tsx"), "utf8");
const operations = readFileSync(join(process.cwd(), "src", "components", "studio", "Operations.tsx"), "utf8");

test("Studio 同时解析稳定 resource_id、顶层 state/version 与每个候选的 resource_version", () => {
  assert.match(studio, /obj\.resource_id \?\? obj\.resourceId/);
  assert.match(studio, /obj\.resource_version \?\? obj\.resourceVersion/);
  assert.match(studio, /obj\.state_version \?\? obj\.stateVersion/);
  assert.match(studio, /rawVersions\?\.length === 1/);
  assert.match(studio, /多版本缺各自版本号时绝不/);
});

test("用户编辑不逐键写库，只在采用或排期边界创建修订/最终快照", () => {
  const updateFieldBody = studio.slice(studio.indexOf("const updateField"), studio.indexOf("const addTag"));
  assert.doesNotMatch(updateFieldBody, /fetch\(|postCopyLifecycle/);
  assert.match(studio, /saveRevisionAtBoundary/);
  assert.match(studio, /postCopyLifecycle\("revision",[\s\S]*?selectedAccount \? \{ account: selectedAccount \}/);
  assert.match(studio, /postCopyLifecycle\("adopt",[\s\S]*?selectedAccount \? \{ account: selectedAccount \}/);
  assert.match(studio, /const finalDraft = dirty \? \{/);
  assert.match(studio, /cover: note\.cover/);
  assert.match(studio, /note: selected\.note/);
  assert.match(editor, /采用此版本/);
  assert.match(editor, /actions\.adoptVersion\(id\)/);
});

test("排期缺 resourceId/精确版本时在乐观更新前中止，409 回读 lifecycle", () => {
  const scheduleBody = studio.slice(studio.indexOf("const schedule ="), studio.indexOf("const backfillSave"));
  assert.ok(scheduleBody.indexOf("if (!copyResourceId)") < scheduleBody.indexOf("applyOptimisticSchedule"));
  assert.ok(scheduleBody.indexOf("if (!selected?.resourceVersion)") < scheduleBody.indexOf("applyOptimisticSchedule"));
  assert.match(scheduleBody, /targetResourceVersion: selected\.resourceVersion/);
  assert.match(scheduleBody, /expectedLatestResourceVersion: copyLifecycle\.latestResourceVersion/);
  assert.match(scheduleBody, /expectedStateVersion: copyLifecycle\.stateVersion/);
  assert.doesNotMatch(scheduleBody, /baseResourceVersion/);
  assert.match(scheduleBody, /handleLifecycleConflict/);
  assert.match(scheduleBody, /dirtyScheduleAttemptRef\.current/);
  assert.match(scheduleBody, /existingAttempt\?\.fingerprint === attemptFingerprint/);
  assert.match(scheduleBody, /crypto\.randomUUID\(\)/);
  assert.match(scheduleBody, /\{ finalDraft, requestId \}/);
  assert.match(scheduleBody, /date: dateStr,[\s\S]*?time,[\s\S]*?account: acct,[\s\S]*?finalDraft/);
  assert.match(scheduleBody, /err\.status >= 400 && err\.status < 500[\s\S]*?dirtyScheduleAttemptRef\.current = null/);
  assert.ok(
    scheduleBody.indexOf("dirtyScheduleAttemptRef.current = null") > scheduleBody.indexOf("if (!finalizedVersion"),
    "只有收到明确成功响应后才清理 dirty schedule requestId",
  );
});

test("切版先保存当前脏版本，再用新 stateVersion 选择目标；快速连点被串行闸门拒绝", () => {
  const setVersionBody = studio.slice(studio.indexOf("const setVersion ="), studio.indexOf("const adoptVersion ="));
  const revisionAt = setVersionBody.indexOf("saveRevisionAtBoundary(activeVersion, copyLifecycle)");
  const selectAt = setVersionBody.indexOf('postCopyLifecycle("select"');
  const applyAuthorityAt = setVersionBody.indexOf("applyAuthoritativeLifecycle(selected)");
  assert.ok(revisionAt >= 0 && revisionAt < selectAt, "dirty 当前版必须先 revision 再 select");
  assert.ok(selectAt < applyAuthorityAt, "后端 select 成功后必须用响应里的 exact snapshot 切画布");
  assert.doesNotMatch(setVersionBody.slice(selectAt), /setDraftTitle\(target\.title\)/);
  assert.match(setVersionBody, /lifecycleWriteBusyRef\.current/);
  assert.match(setVersionBody, /finally \{\s*lifecycleWriteBusyRef\.current = false/);
  assert.match(studio, /cover !== saved\.cover/);
  assert.match(studio, /cover,\s*note: saved\.note/);
});

test("刷新与切回会话只用 lifecycle exact snapshots 恢复画布，本地脏稿不被覆盖", () => {
  assert.match(studio, /mapLifecycleVersions\(lifecycle\)/);
  assert.match(studio, /copyLifecycleSnapshot\(lifecycle, lifecycle\.selectedVersion\)/);
  assert.match(studio, /setRevisionSnapshots\(authoritativeVersions\)/);
  assert.match(studio, /if \(!localEditsRef\.current && selectedSnapshot\)/);
  assert.match(studio, /setCanonicalTitle\(selectedSnapshot\.title\)/);
  assert.match(studio, /setCanonicalBody\(selectedSnapshot\.body\)/);
  assert.match(studio, /if \(copyLifecycle\) \{[\s\S]*?return Object\.keys\(revisionSnapshots\)/);
  assert.doesNotMatch(studio, /const selected = versions\?\.\[selectedId\]/);
});

test("current-document exact binding 经 lifecycle 快照验证后才持久化，非 copy 回合保留，新创作显式清空", () => {
  assert.match(studio, /currentDocumentBinding: CurrentDocumentBinding \| null/);
  assert.match(studio, /currentDocumentBinding: parseCurrentDocumentBinding\(o\.currentDocumentBinding\)/);
  assert.match(studio, /resolveCurrentDocumentBinding\(streamDocumentBinding, currentDocumentBinding\)/);
  assert.match(studio, /requestCopyLifecycle\(pendingDocumentBinding/);
  assert.match(studio, /resolveLifecycleWriteBinding\([\s\S]*?pendingDocumentBinding,[\s\S]*?currentDocumentBinding/);
  assert.match(studio, /const copyResourceId = verifiedDocumentBinding\?\.resourceId \?\? null/);
  assert.match(studio, /validateBindingAgainstLifecycle\(binding, lifecycle\)/);
  assert.match(studio, /ownerThreadId: documentThreadId/);
  assert.match(studio, /版本状态不包含当前成品的精确版本/);

  const bindingLoadBody = studio.slice(
    studio.indexOf("const streamDocumentBinding"),
    studio.indexOf("const visibleVersions"),
  );
  assert.doesNotMatch(
    bindingLoadBody,
    /setCurrentDocumentBinding\([\s\S]*?streamDocumentBinding/,
    "stream 声明在 lifecycle 验证前不得写入 thread 持久化绑定",
  );
  for (const actionName of ["setVersion", "adoptVersion", "schedule"]) {
    const start = studio.indexOf(`const ${actionName} =`);
    const end = studio.indexOf("\n  const ", start + 1);
    const body = studio.slice(start, end < 0 ? undefined : end);
    assert.match(body, /lifecycleWriteBinding/);
  }

  const chooseTopicBody = studio.slice(studio.indexOf("const chooseTopic ="), studio.indexOf("const adoptNotes ="));
  assert.ok(
    chooseTopicBody.indexOf("setCurrentDocumentBinding(null)") >
      chooseTopicBody.indexOf("if (sameTopicAsLoaded && alreadyHasCopy) return"),
    "只有真正启动新选题成品时才解除旧文档绑定",
  );
  const imitateBody = studio.slice(studio.indexOf("const imitate ="), studio.indexOf("const updateField ="));
  assert.match(imitateBody, /setCurrentDocumentBinding\(null\)/);
});

test("表现回填必须从已发布管线显式选择精确版本，不得沿用当前编辑器文案", () => {
  const backfillBody = studio.slice(studio.indexOf("const backfillSave ="), studio.indexOf("const advanceStage ="));
  assert.match(operations, /aria-label="选择回填目标文案"/);
  assert.match(operations, /item\.stage === "published"/);
  assert.match(operations, /actions\.backfillSave\(target,/);
  assert.match(operations, /onBackfill\(item\)/);
  assert.doesNotMatch(operations, /onAdvance\(item,\s*"measured"\)/);
  assert.match(backfillBody, /target\.resourceId/);
  assert.match(backfillBody, /target\.resourceVersion/);
  assert.doesNotMatch(backfillBody, /copyResourceId|copyLifecycle/);
});
