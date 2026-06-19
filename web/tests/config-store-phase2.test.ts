import assert from "node:assert/strict";

import {
  configCenterRunnerArgs,
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
