import assert from "node:assert/strict";
import { mkdtemp, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";
import test from "node:test";

import { forwardToInternalServer } from "../src/lib/server/internal-client";

test("forwards internal request over HTTP with internal headers", async () => {
  const originalBaseUrl = process.env.XHS_INTERNAL_BASE_URL;
  const originalSecret = process.env.XHS_INTERNAL_SECRET;
  const originalFetch = globalThis.fetch;
  const calls: Array<{ url: string; init: RequestInit }> = [];

  process.env.XHS_INTERNAL_BASE_URL = "http://127.0.0.1:2024";
  process.env.XHS_INTERNAL_SECRET = "internal-secret";
  globalThis.fetch = (async (url: string | URL | Request, init?: RequestInit) => {
    calls.push({ url: String(url), init: init || {} });
    return new Response(JSON.stringify({ ok: true, configs: { LLM_API_KEY: "sk" }, version: "v1" }), {
      status: 200,
      headers: { "Content-Type": "application/json" },
    });
  }) as typeof fetch;

  try {
    const response = await forwardToInternalServer("/_internal/config-status", "GET", "ou_admin", undefined, {
      isAdmin: true,
    });
    const payload = await response.json();

    assert.equal(response.status, 200);
    assert.equal(payload.configs.LLM_API_KEY, "sk");
    assert.equal(calls[0].url, "http://127.0.0.1:2024/internal/config");
    assert.equal((calls[0].init.headers as Record<string, string>)["X-XHS-Internal-Key"], "internal-secret");
    assert.equal((calls[0].init.headers as Record<string, string>)["X-XHS-Open-Id"], "ou_admin");
    assert.equal((calls[0].init.headers as Record<string, string>)["X-XHS-Is-Admin"], "true");
  } finally {
    globalThis.fetch = originalFetch;
    if (originalBaseUrl === undefined) delete process.env.XHS_INTERNAL_BASE_URL;
    else process.env.XHS_INTERNAL_BASE_URL = originalBaseUrl;
    if (originalSecret === undefined) delete process.env.XHS_INTERNAL_SECRET;
    else process.env.XHS_INTERNAL_SECRET = originalSecret;
  }
});

test("returns degraded config fallback only for config status when internal http is unavailable", async () => {
  const originalBaseUrl = process.env.XHS_INTERNAL_BASE_URL;
  const originalSecret = process.env.XHS_INTERNAL_SECRET;

  delete process.env.XHS_INTERNAL_BASE_URL;
  process.env.XHS_INTERNAL_SECRET = "internal-secret";

  try {
    const configResponse = await forwardToInternalServer("/_internal/config-status", "GET", "ou_admin", undefined, {
      isAdmin: true,
      allowConfigFallback: true,
    });
    const configPayload = await configResponse.json();
    assert.equal(configResponse.status, 503);
    assert.equal(configPayload.degraded, true);

    const chatsResponse = await forwardToInternalServer("/_internal/chats", "GET", "ou_user", undefined, {
      allowConfigFallback: true,
    });
    const chatsPayload = await chatsResponse.json();
    assert.equal(chatsResponse.status, 503);
    assert.equal(chatsPayload.degraded, undefined);
  } finally {
    if (originalBaseUrl === undefined) delete process.env.XHS_INTERNAL_BASE_URL;
    else process.env.XHS_INTERNAL_BASE_URL = originalBaseUrl;
    if (originalSecret === undefined) delete process.env.XHS_INTERNAL_SECRET;
    else process.env.XHS_INTERNAL_SECRET = originalSecret;
  }
});

test("uses the local config recovery runner when internal http is unavailable", async () => {
  const originalEnv = { ...process.env };
  const tempDir = await mkdtemp(path.join(tmpdir(), "xhs-config-recovery-"));

  delete process.env.XHS_INTERNAL_BASE_URL;
  process.env.XHS_CONFIG_CENTER_PATH = path.join(tempDir, "config-center.enc");
  process.env.XHS_CONFIG_ENCRYPTION_KEY = "MDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDA=";

  try {
    const saveResponse = await forwardToInternalServer(
      "/_internal/config-set",
      "POST",
      "ou_admin",
      { configs: { LLM_PROVIDER: "openai", LLM_API_KEY: "sk-recovery" } },
      { isAdmin: true, allowConfigFallback: true },
    );
    const savePayload = await saveResponse.json();

    assert.equal(saveResponse.status, 200);
    assert.equal(savePayload.ok, true);
    assert.equal(savePayload.degraded, true);
    assert.equal(savePayload.recovery, "local-config-center");
    assert.equal(savePayload.degraded_reason, "Internal HTTP unavailable");

    const readResponse = await forwardToInternalServer(
      "/_internal/config-status",
      "GET",
      "ou_admin",
      undefined,
      { isAdmin: true, allowConfigFallback: true },
    );
    const readPayload = await readResponse.json();

    assert.equal(readResponse.status, 200);
    assert.equal(readPayload.ok, true);
    assert.equal(readPayload.degraded, true);
    assert.equal(readPayload.configs.LLM_API_KEY, "sk-recovery");
  } finally {
    process.env = originalEnv;
    await rm(tempDir, { recursive: true, force: true });
  }
});
