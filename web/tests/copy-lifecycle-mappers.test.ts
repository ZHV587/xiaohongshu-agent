import assert from "node:assert/strict";
import test from "node:test";

import {
  copyLifecycleSnapshot,
  mapLifecycleVersions,
  mapVersions,
  parseCopyLifecycle,
} from "../src/components/studio/backend-mappers";

function lifecyclePayload(): Record<string, unknown> {
  return {
    resourceId: "11111111-1111-4111-8111-111111111111",
    status: "finalized",
    selectedVersion: 3,
    selectedLabel: "A",
    adoptedVersion: 3,
    finalizedVersion: 3,
    publishedVersion: null,
    knowledgeTargetVersion: 3,
    latestResourceVersion: 3,
    stateVersion: 8,
    versions: [
      { resourceVersion: 1, label: "A", title: "旧 A", body: "旧正文", tags: ["#旧"], cover: "旧封面", note: "初稿" },
      { resourceVersion: 2, label: "B", title: "B", body: "B 正文", tags: ["#B"], cover: "B 封面", note: "B 版" },
      { resourceVersion: 3, label: "A", title: "最终 A", body: "最终正文", tags: ["#最终"], cover: "最终封面", note: "最终版" },
    ],
  };
}

test("mapVersions 将 snake/camel resource version 映射到对应 A/B/C，不给缺失项编版本", () => {
  const mapped = mapVersions([
    { label: "A", title: "A", body: "正文A", resource_version: 3 },
    { label: "B", title: "B", body: "正文B", resourceVersion: 4 },
    { label: "C", title: "C", body: "正文C" },
  ]);
  assert.equal(mapped?.A?.resourceVersion, 3);
  assert.equal(mapped?.B?.resourceVersion, 4);
  assert.equal(Object.hasOwn(mapped?.C ?? {}, "resourceVersion"), false);
});

test("mapVersions 拒绝非正整数版本，不把小数/零/字符串当不可变版本", () => {
  const mapped = mapVersions([
    { title: "A", body: "A", resource_version: 0 },
    { title: "B", body: "B", resourceVersion: 1.5 },
    { title: "C", body: "C", resource_version: "9" as unknown as number },
  ]);
  for (const id of ["A", "B", "C"] as const) {
    assert.equal(mapped?.[id]?.resourceVersion, undefined);
  }
});

test("parseCopyLifecycle 只接受完整 exact snapshots，并按 selectedVersion 恢复最终修订", () => {
  const lifecycle = parseCopyLifecycle(lifecyclePayload());
  assert.ok(lifecycle);
  assert.deepEqual(copyLifecycleSnapshot(lifecycle!, 3), {
    resourceVersion: 3,
    label: "A",
    title: "最终 A",
    body: "最终正文",
    tags: ["#最终"],
    cover: "最终封面",
    note: "最终版",
  });
  const mapped = mapLifecycleVersions(lifecycle!);
  assert.equal(mapped.A?.resourceVersion, 3, "同 label 的最终修订必须覆盖旧 A，并按 selectedVersion 恢复精确快照");
  assert.equal(mapped.A?.title, "最终 A");
  assert.equal(mapped.B?.resourceVersion, 2);
});

test("parseCopyLifecycle 对旧、乱序、重复、缺字段及悬空指针 payload 一律 fail closed", () => {
  const base = lifecyclePayload();
  const cases: unknown[] = [
    { ...base, versions: undefined },
    { ...base, versions: [] },
    { ...base, versions: [...(base.versions as unknown[])].reverse() },
    { ...base, versions: [
      ...(base.versions as unknown[]),
      { ...(base.versions as Record<string, unknown>[])[2] },
    ] },
      { ...base, versions: (base.versions as Record<string, unknown>[]).map((item, index) => index === 2 ? { ...item, cover: undefined } : item) },
      { ...base, selectedVersion: 99 },
      { ...base, latestResourceVersion: 99 },
      { ...base, latestResourceVersion: 2 },
      { ...base, selectedLabel: null },
      { ...base, selectedLabel: "B" },
      { ...base, selectedVersion: null },
      Object.fromEntries(Object.entries(base).filter(([field]) => field !== "knowledgeTargetVersion")),
      Object.fromEntries(Object.entries(base).filter(([field]) => field !== "selectedLabel")),
    ];
  for (const payload of cases) assert.equal(parseCopyLifecycle(payload), null);
});
