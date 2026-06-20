import assert from "node:assert/strict";

import {
  assertAllowedConfigKeys,
  deployOnlyKeys,
  embeddingConfigKeys,
  readConfigResponse,
} from "../src/lib/server/config-store";

assert.equal(deployOnlyKeys.has("XHS_CONFIG_ENCRYPTION_KEY"), true);
assert.equal(deployOnlyKeys.has("XHS_CONFIG_CENTER_PATH"), true);
assert.equal(deployOnlyKeys.has("XHS_INTERNAL_SECRET"), true);
assert.equal(deployOnlyKeys.has("XHS_INTERNAL_BASE_URL"), true);

assert.throws(
  () => assertAllowedConfigKeys({ XHS_CONFIG_ENCRYPTION_KEY: "secret" }),
  /not editable/,
);

assert.throws(
  () => assertAllowedConfigKeys({ XHS_CONFIG_CENTER_PATH: ".xhs-config/config-center.enc" }),
  /not editable/,
);

assert.throws(
  () => assertAllowedConfigKeys({ XHS_INTERNAL_SECRET: "secret" }),
  /not editable/,
);

assert.throws(
  () => assertAllowedConfigKeys({ XHS_INTERNAL_BASE_URL: "http://127.0.0.1:2024" }),
  /not editable/,
);

assert.equal(embeddingConfigKeys.has("XHS_EMBEDDING_API_KEY"), true);
assert.deepEqual(
  assertAllowedConfigKeys({ XHS_BACKEND_APPLY_MODE: "manual" }),
  { XHS_BACKEND_APPLY_MODE: "manual" },
);
assert.throws(
  () => assertAllowedConfigKeys({ XHS_BACKEND_APPLY_MODE: "manual" }, { configCenterEnabled: true }),
  /not editable/,
);
assert.deepEqual(
  assertAllowedConfigKeys({
    XHS_EMBEDDING_BASE_URL: "https://embedding.example/v1",
    XHS_EMBEDDING_API_KEY: "embedding-key",
    XHS_EMBEDDING_MODEL: "text-embedding-3-small",
    XHS_EMBEDDING_DIMENSIONS: "1536",
    XHS_EMBEDDING_BATCH_SIZE: "64",
    XHS_EMBEDDING_TIMEOUT_SECONDS: "30",
  }),
  {
    XHS_EMBEDDING_BASE_URL: "https://embedding.example/v1",
    XHS_EMBEDDING_API_KEY: "embedding-key",
    XHS_EMBEDDING_MODEL: "text-embedding-3-small",
    XHS_EMBEDDING_DIMENSIONS: "1536",
    XHS_EMBEDDING_BATCH_SIZE: "64",
    XHS_EMBEDDING_TIMEOUT_SECONDS: "30",
  },
);

const originalEmbeddingKey = process.env.XHS_EMBEDDING_API_KEY;
const originalLlmKey = process.env.LLM_API_KEY;

try {
  process.env.XHS_EMBEDDING_API_KEY = "embedding-secret";
  process.env.LLM_API_KEY = "llm-secret";

  const configs = readConfigResponse();

  assert.equal(configs.XHS_EMBEDDING_API_KEY, "embedding-secret");
  assert.equal(configs.LLM_API_KEY, "llm-secret");
} finally {
  if (originalEmbeddingKey === undefined) {
    delete process.env.XHS_EMBEDDING_API_KEY;
  } else {
    process.env.XHS_EMBEDDING_API_KEY = originalEmbeddingKey;
  }
  if (originalLlmKey === undefined) {
    delete process.env.LLM_API_KEY;
  } else {
    process.env.LLM_API_KEY = originalLlmKey;
  }
}
