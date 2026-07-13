import assert from "node:assert/strict";
import test from "node:test";

import {
  parseCurrentDocumentBinding,
  resolveCurrentDocumentBinding,
  resolveLifecycleWriteBinding,
  validateBindingAgainstLifecycle,
} from "../src/components/studio/current-document-binding";

const lifecycle = (resourceId: string, resourceVersions: number[]) => ({
  resourceId,
  stateVersion: 9,
  versions: resourceVersions.map((resourceVersion, index) => ({
    label: String.fromCharCode(65 + index),
    note: "",
    title: `版本 ${resourceVersion}`,
    cover: "",
    body: "正文",
    tags: [],
    resourceVersion,
  })),
});

test("current document binding requires an atomic id/version pair", () => {
  assert.equal(parseCurrentDocumentBinding({ resourceId: "res-1" }), null);
  assert.equal(parseCurrentDocumentBinding({ resourceId: "res-1", resourceVersion: 2 }), null);
  assert.equal(parseCurrentDocumentBinding({ resourceVersion: 2 }), null);
  assert.equal(parseCurrentDocumentBinding({ ownerThreadId: "thread-1", resourceId: "res-1", resourceVersion: "2" }), null);
  assert.deepEqual(
    parseCurrentDocumentBinding({ ownerThreadId: " thread-1 ", resourceId: " res-1 ", resourceVersion: 2, stateVersion: 4 }),
    { ownerThreadId: "thread-1", resourceId: "res-1", resourceVersion: 2, stateVersion: 4 },
  );
});

test("non-copy turn keeps the persisted exact binding", () => {
  const persisted = { ownerThreadId: "thread-1", resourceId: "res-1", resourceVersion: 3, stateVersion: 7 };
  assert.deepEqual(resolveCurrentDocumentBinding(null, persisted), persisted);
});

test("new copy exact binding atomically replaces the persisted document", () => {
  const persisted = { ownerThreadId: "thread-1", resourceId: "res-old", resourceVersion: 3, stateVersion: 7 };
  const stream = { ownerThreadId: "thread-1", resourceId: "res-new", resourceVersion: 1, stateVersion: 1 };
  assert.deepEqual(resolveCurrentDocumentBinding(stream, persisted), stream);
});

test("partial stream identity cannot overwrite a valid persisted binding", () => {
  const persisted = { ownerThreadId: "thread-1", resourceId: "res-old", resourceVersion: 3 };
  assert.deepEqual(
    resolveCurrentDocumentBinding({ ownerThreadId: "thread-1", resourceId: "res-new" }, persisted),
    persisted,
  );
});

test("stream exact pair must exist in authoritative lifecycle snapshots", () => {
  const binding = { ownerThreadId: "thread-1", resourceId: "res-1", resourceVersion: 3, stateVersion: 1 };
  assert.deepEqual(
    validateBindingAgainstLifecycle(binding, lifecycle("res-1", [1, 2, 3])),
    binding,
  );
  assert.equal(
    validateBindingAgainstLifecycle(binding, lifecycle("res-1", [1, 2, 4])),
    null,
  );
  assert.equal(
    validateBindingAgainstLifecycle(binding, lifecycle("res-other", [3])),
    null,
  );
});

test("mixed id/version pair fails closed even when both fields are individually valid", () => {
  const oldDocument = lifecycle("res-old", [1, 2]);
  const mixedPair = { ownerThreadId: "thread-1", resourceId: "res-old", resourceVersion: 7 };

  assert.deepEqual(parseCurrentDocumentBinding(mixedPair), mixedPair);
  assert.equal(validateBindingAgainstLifecycle(mixedPair, oldDocument), null);
});

test("new stream candidate cannot borrow the previous lifecycle during the effect gap", () => {
  const oldLifecycle = lifecycle("res-old", [1, 2]);
  const verified = { ownerThreadId: "thread-1", resourceId: "res-old", resourceVersion: 2, stateVersion: 9 };
  const pendingNew = { ownerThreadId: "thread-1", resourceId: "res-new", resourceVersion: 1, stateVersion: 1 };

  assert.equal(
    resolveLifecycleWriteBinding(pendingNew, verified, oldLifecycle, true, "thread-1"),
    null,
  );
});

test("thread switch disables the previous binding in the first render", () => {
  const oldLifecycle = lifecycle("res-old", [1, 2]);
  const oldBinding = {
    ownerThreadId: "thread-a",
    resourceId: "res-old",
    resourceVersion: 2,
    stateVersion: 9,
  };

  assert.equal(
    resolveLifecycleWriteBinding(
      oldBinding,
      oldBinding,
      oldLifecycle,
      true,
      "thread-b",
    ),
    null,
  );
});

test("verified binding may advance while the original stream snapshot remains authoritative", () => {
  const authoritative = lifecycle("res-1", [1, 2, 3]);
  const originalStream = { ownerThreadId: "thread-1", resourceId: "res-1", resourceVersion: 1, stateVersion: 1 };
  const verifiedCurrent = { ownerThreadId: "thread-1", resourceId: "res-1", resourceVersion: 3, stateVersion: 9 };

  assert.deepEqual(
    resolveLifecycleWriteBinding(originalStream, verifiedCurrent, authoritative, true, "thread-1"),
    verifiedCurrent,
  );
  assert.equal(
    resolveLifecycleWriteBinding(
      originalStream,
      { ...verifiedCurrent, stateVersion: 8 },
      authoritative,
      true,
      "thread-1",
    ),
    null,
  );
  assert.equal(
    resolveLifecycleWriteBinding(originalStream, verifiedCurrent, authoritative, false, "thread-1"),
    null,
  );
});
