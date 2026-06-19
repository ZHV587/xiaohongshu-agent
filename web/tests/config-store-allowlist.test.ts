import assert from "node:assert/strict";

import { assertAllowedConfigKeys, deployOnlyKeys } from "../src/lib/server/config-store";

assert.equal(deployOnlyKeys.has("XHS_CONFIG_ENCRYPTION_KEY"), true);
assert.equal(deployOnlyKeys.has("XHS_CONFIG_CENTER_PATH"), true);

assert.throws(
  () => assertAllowedConfigKeys({ XHS_CONFIG_ENCRYPTION_KEY: "secret" }),
  /not editable/,
);

assert.throws(
  () => assertAllowedConfigKeys({ XHS_CONFIG_CENTER_PATH: ".xhs-config/config-center.enc" }),
  /not editable/,
);
