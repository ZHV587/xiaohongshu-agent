import assert from "node:assert/strict";

import {
  buildBackendStatusPayload,
  configCenterRunnerArgs,
  configCenterSaveApplyStatus,
  isConfigCenterEnabled,
} from "../src/lib/server/config-store";

const originalPath = process.env.XHS_CONFIG_CENTER_PATH;
const originalKey = process.env.XHS_CONFIG_ENCRYPTION_KEY;

try {
  delete process.env.XHS_CONFIG_CENTER_PATH;
  delete process.env.XHS_CONFIG_ENCRYPTION_KEY;
  assert.equal(isConfigCenterEnabled(), false);

  process.env.XHS_CONFIG_CENTER_PATH = ".xhs-config/config-center.enc";
  process.env.XHS_CONFIG_ENCRYPTION_KEY = "fernet-key";
  assert.equal(isConfigCenterEnabled(), true);
  assert.deepEqual(configCenterRunnerArgs("config-status"), [
    "--action",
    "config-status",
    "--config-path",
    ".xhs-config/config-center.enc",
    "--encryption-key",
    "fernet-key",
  ]);
  assert.deepEqual(configCenterRunnerArgs("config-set"), [
    "--action",
    "config-set",
    "--config-path",
    ".xhs-config/config-center.enc",
    "--encryption-key",
    "fernet-key",
  ]);

  const apply = configCenterSaveApplyStatus();
  assert.equal(apply.mode, "config-center");
  assert.equal(apply.applied, true);
  assert.match(apply.message, /scheduler/);
  assert.match(apply.message, /新索引/);
  assert.doesNotMatch(apply.message, /重启|restart/i);

  const status = buildBackendStatusPayload({
    applyMode: "manual",
    configCenterEnabled: true,
    configVersion: "cfg-1",
  });
  assert.equal(status.config_version, "cfg-1");
  assert.equal(status.config_center_enabled, true);
  assert.equal(status.hot_apply_supported, true);
  assert.equal(status.hot_reload_supported_paths.embedding_index_profiles, true);
  assert.match(status.hot_reload_message, /scheduler/);
  assert.match(status.status_message, /自动创建/);
  assert.doesNotMatch(status.status_message, /重启|restart/i);
} finally {
  if (originalPath === undefined) {
    delete process.env.XHS_CONFIG_CENTER_PATH;
  } else {
    process.env.XHS_CONFIG_CENTER_PATH = originalPath;
  }
  if (originalKey === undefined) {
    delete process.env.XHS_CONFIG_ENCRYPTION_KEY;
  } else {
    process.env.XHS_CONFIG_ENCRYPTION_KEY = originalKey;
  }
}
