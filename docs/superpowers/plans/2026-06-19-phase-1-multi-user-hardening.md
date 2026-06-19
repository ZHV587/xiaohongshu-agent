# Phase 1 Multi-User Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement phase 1 from the architecture spec: admin-only configuration, truthful config application state, UAT-only Feishu operations, safe draft creation, sensitive-log cleanup, and quality gates.

**Architecture:** Keep DeepAgents/LangGraph as the runtime. Next.js owns browser-facing auth/config routes; Python owns agent/tools and Feishu execution. Configuration remains `.env`-backed in phase 1, with explicit `manual|pm2|systemd` apply modes and no arbitrary restart command.

**Tech Stack:** Next.js App Router, TypeScript, LangGraph SDK JWT cookie auth, Python 3.12, pytest, lark-cli, DeepAgents, PowerShell/Windows local commands.

---

## File Map

- Create `web/src/lib/server/authz.ts`: shared `requireUser`, `requireAdmin`, admin open_id parsing, and no-store response helper.
- Create `web/src/app/api/me/route.ts`: returns current user and admin status.
- Create `web/src/lib/server/config-store.ts`: config key allowlists, `.env` update, generated `XHS_CONFIG_VERSION`, safe public config response.
- Create `web/src/lib/server/backend-apply.ts`: fixed `manual|pm2|systemd` apply mode logic with no arbitrary shell.
- Modify `web/src/app/api/config/route.ts`: use admin auth, field allowlist, no-store, config version, apply status.
- Modify `web/src/app/api/config/test/route.ts`: require admin.
- Create `web/src/app/api/backend/status/route.ts`: admin-only, no-store status for config version and apply mode support.
- Modify `web/src/components/thread/history/index.tsx`: only show config buttons to admins using `/api/me`.
- Modify `web/src/components/thread/history/LlmConfigPage.tsx`: save/read `LLM_QUALITY_MODELS` instead of treating `LLM_MODEL` as the backend contract.
- Modify `tools/lark_cli.py`: split server user-required execution from CLI/dev bot fallback.
- Modify `tools/feishu_bitable.py`: remove debug token logging.
- Modify `tools/cli_runner.py`: change sync action from update fixed record to create draft record.
- Modify `web/src/app/api/feishu/status/route.ts`: return current-user Feishu/UAT diagnostics.
- Modify `web/src/lib/server/internal-client.ts`: add internal runner actions for UAT status and sync draft fields.
- Modify `web/src/app/api/feishu/sync/route.ts`: stop requiring `recordId`; create draft record.
- Modify `web/src/components/thread/index.tsx`: remove fixed `rec_default_4`; display draft creation state.
- Modify `web/eslint.config.js`: ignore generated files.
- Add/modify tests under `tests/`: lark CLI server-mode UAT-only behavior, bitable debug cleanup, draft record creation, config helper behavior where practical.

## Task 1: Admin Auth Foundation

**Files:**
- Create: `web/src/lib/server/authz.ts`
- Create: `web/src/app/api/me/route.ts`
- Modify: `web/src/components/thread/history/index.tsx`

- [ ] **Step 1: Create shared server auth helper**

Create `web/src/lib/server/authz.ts`:

```ts
import { cookies } from "next/headers";
import { NextResponse } from "next/server";
import { AUTH_COOKIE, getFeishuConfig } from "@/lib/server/feishu";
import { verifyJwt, type XhsJwtPayload } from "@/lib/server/jwt";

export interface CurrentServerUser {
  openId: string;
  name?: string;
  isAdmin: boolean;
}

export class ApiError extends Error {
  constructor(
    public readonly status: number,
    message: string,
  ) {
    super(message);
  }
}

export function parseAdminOpenIds(raw = process.env.XHS_ADMIN_OPEN_IDS ?? ""): Set<string> {
  return new Set(
    raw
      .split(",")
      .map((item) => item.trim())
      .filter(Boolean),
  );
}

export function isAdminOpenId(openId: string): boolean {
  return parseAdminOpenIds().has(openId);
}

export async function requireUser(): Promise<CurrentServerUser> {
  const cookieStore = await cookies();
  const token = cookieStore.get(AUTH_COOKIE)?.value;
  if (!token) throw new ApiError(401, "Unauthorized");

  const cfg = getFeishuConfig();
  const payload: XhsJwtPayload | null = verifyJwt(token, cfg.jwtSecret);
  if (!payload?.sub) throw new ApiError(401, "Unauthorized");

  return {
    openId: payload.sub,
    name: payload.name,
    isAdmin: isAdminOpenId(payload.sub),
  };
}

export async function requireAdmin(): Promise<CurrentServerUser> {
  const user = await requireUser();
  if (!user.isAdmin) throw new ApiError(403, "Forbidden");
  return user;
}

export function jsonNoStore(body: unknown, init?: ResponseInit): NextResponse {
  const res = NextResponse.json(body, init);
  res.headers.set("Cache-Control", "no-store");
  return res;
}

export function apiErrorResponse(error: unknown): NextResponse {
  if (error instanceof ApiError) {
    return NextResponse.json({ error: error.message }, { status: error.status });
  }
  return NextResponse.json({ error: (error as Error).message }, { status: 500 });
}
```

- [ ] **Step 2: Add `/api/me`**

Create `web/src/app/api/me/route.ts`:

```ts
import { NextResponse } from "next/server";
import { apiErrorResponse, requireUser } from "@/lib/server/authz";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function GET() {
  try {
    const user = await requireUser();
    return NextResponse.json({
      ok: true,
      user: {
        openId: user.openId,
        name: user.name,
        isAdmin: user.isAdmin,
      },
    });
  } catch (error) {
    return apiErrorResponse(error);
  }
}
```

- [ ] **Step 3: Update sidebar admin visibility**

In `web/src/components/thread/history/index.tsx`, add local admin state inside `SidebarBody`:

```tsx
const [isAdmin, setIsAdmin] = useState(false);

useEffect(() => {
  fetch("/api/me")
    .then((res) => (res.ok ? res.json() : null))
    .then((data) => setIsAdmin(Boolean(data?.user?.isAdmin)))
    .catch(() => setIsAdmin(false));
}, []);
```

Wrap the two config buttons:

```tsx
{isAdmin && (
  <>
    <Button
      variant="ghost"
      size="icon"
      title="AI模型配置"
      onClick={onLlmConfigOpen}
      className="size-8 text-gray-400 hover:text-coral transition-colors"
    >
      <Sparkles className="size-4" />
    </Button>
    <Button
      variant="ghost"
      size="icon"
      title="飞书对接配置"
      onClick={onFeishuConfigOpen}
      className="size-8 text-gray-400 hover:text-coral transition-colors"
    >
      <SlidersHorizontal className="size-4" />
    </Button>
  </>
)}
```

- [ ] **Step 4: Run typecheck**

Run: `web/node_modules/.bin/tsc.CMD --noEmit` from `web`.

Expected: PASS. If it fails because of import paths, fix `authz.ts` imports before continuing.

- [ ] **Step 5: Commit**

```bash
git add web/src/lib/server/authz.ts web/src/app/api/me/route.ts web/src/components/thread/history/index.tsx
git commit -m "feat: add admin identity gate"
```

## Task 2: Admin-Only Config API and Field Allowlist

**Files:**
- Create: `web/src/lib/server/config-store.ts`
- Create: `web/src/lib/server/backend-apply.ts`
- Create: `web/src/app/api/backend/status/route.ts`
- Modify: `web/src/app/api/config/route.ts`
- Modify: `web/src/app/api/config/test/route.ts`

- [ ] **Step 1: Create config store helper**

Create `web/src/lib/server/config-store.ts`:

```ts
import fs from "node:fs";
import path from "node:path";
import crypto from "node:crypto";

export const llmConfigKeys = new Set([
  "LLM_PROVIDER",
  "LLM_BASE_URL",
  "LLM_API_KEY",
  "LLM_QUALITY_MODELS",
  "LLM_GATEWAY_2_BASE_URL",
  "LLM_GATEWAY_2_API_KEY",
  "LLM_GATEWAY_3_BASE_URL",
  "LLM_GATEWAY_3_API_KEY",
]);

export const feishuConfigKeys = new Set([
  "FEISHU_APP_ID",
  "FEISHU_APP_SECRET",
  "FEISHU_BITABLE_APP_TOKEN",
  "FEISHU_BITABLE_TABLE_ID",
  "XHS_BITABLE_FIELD_TITLE",
  "XHS_BITABLE_FIELD_BODY",
  "XHS_BITABLE_FIELD_TAGS",
  "XHS_BITABLE_FIELD_AUTHOR",
  "XHS_BITABLE_FIELD_STATUS",
]);

export const runtimeApplyKeys = new Set([
  "XHS_BACKEND_APPLY_MODE",
  "XHS_BACKEND_PM2_NAME",
  "XHS_BACKEND_SYSTEMD_SERVICE",
  "XHS_PUBLIC_ORIGIN",
  "XHS_PYTHON_BIN",
]);

export const deployOnlyKeys = new Set([
  "XHS_ADMIN_OPEN_IDS",
  "XHS_JWT_SECRET",
  "XHS_INTERNAL_SECRET",
  "PATH",
  "NODE_OPTIONS",
]);

export function assertAllowedConfigKeys(configs: Record<string, unknown>): Record<string, string> {
  const allowed = new Set([...llmConfigKeys, ...feishuConfigKeys, ...runtimeApplyKeys]);
  const sanitized: Record<string, string> = {};
  for (const [key, value] of Object.entries(configs)) {
    if (deployOnlyKeys.has(key) || !allowed.has(key)) {
      throw new Error(`Config key is not editable: ${key}`);
    }
    sanitized[key] = String(value ?? "");
  }
  return sanitized;
}

export function generateConfigVersion(updates: Record<string, string>): string {
  const hash = crypto
    .createHash("sha256")
    .update(JSON.stringify(Object.keys(updates).sort().map((key) => [key, updates[key]])))
    .digest("hex")
    .slice(0, 12);
  return `${new Date().toISOString().replace(/[-:.TZ]/g, "")}-${hash}`;
}

export function updateEnvFile(filePath: string, updates: Record<string, string>) {
  if (!fs.existsSync(filePath)) fs.writeFileSync(filePath, "", "utf-8");

  const content = fs.readFileSync(filePath, "utf-8");
  const lines = content.split(/\r?\n/);
  const nextLines: string[] = [];
  const applied = new Set<string>();

  for (const line of lines) {
    const stripped = line.trim();
    if (!stripped || stripped.startsWith("#") || !stripped.includes("=")) {
      nextLines.push(line);
      continue;
    }
    const key = stripped.split("=")[0].trim();
    if (Object.prototype.hasOwnProperty.call(updates, key)) {
      nextLines.push(`${key}=${updates[key]}`);
      applied.add(key);
    } else {
      nextLines.push(line);
    }
  }

  for (const [key, value] of Object.entries(updates)) {
    if (!applied.has(key)) nextLines.push(`${key}=${value}`);
  }

  fs.writeFileSync(filePath, nextLines.join("\n"), "utf-8");
}

export function envPaths() {
  return {
    webEnvPath: path.join(process.cwd(), ".env"),
    rootEnvPath: path.join(process.cwd(), "../.env"),
  };
}

export function readConfigResponse() {
  const keys = [
    ...llmConfigKeys,
    ...feishuConfigKeys,
    ...runtimeApplyKeys,
    "XHS_CONFIG_VERSION",
  ];
  return Object.fromEntries(keys.map((key) => [key, process.env[key] || ""]));
}
```

- [ ] **Step 2: Create backend apply helper**

Create `web/src/lib/server/backend-apply.ts`:

```ts
import { execFile } from "node:child_process";
import { promisify } from "node:util";

const execFileAsync = promisify(execFile);

export interface ApplyResult {
  mode: "manual" | "pm2" | "systemd";
  applied: boolean;
  message: string;
}

export async function applyBackendConfig(): Promise<ApplyResult> {
  const mode = (process.env.XHS_BACKEND_APPLY_MODE || "manual").trim().toLowerCase();

  if (mode === "manual" || !mode) {
    return {
      mode: "manual",
      applied: false,
      message: "配置已保存。当前为 manual apply 模式，请手动重启 Python 后端。",
    };
  }

  if (mode === "pm2") {
    const name = process.env.XHS_BACKEND_PM2_NAME || "xhs-backend";
    await execFileAsync("pm2", ["restart", name], { windowsHide: true });
    return { mode: "pm2", applied: true, message: `已执行 pm2 restart ${name}` };
  }

  if (mode === "systemd") {
    const service = process.env.XHS_BACKEND_SYSTEMD_SERVICE || "xhs-backend.service";
    await execFileAsync("systemctl", ["restart", service], { windowsHide: true });
    return { mode: "systemd", applied: true, message: `已执行 systemctl restart ${service}` };
  }

  throw new Error(`Unsupported XHS_BACKEND_APPLY_MODE: ${mode}`);
}
```

- [ ] **Step 3: Rewrite `/api/config` route**

Replace `web/src/app/api/config/route.ts` with a version that uses `requireAdmin`, `jsonNoStore`, `assertAllowedConfigKeys`, `generateConfigVersion`, `updateEnvFile`, and `applyBackendConfig`.

Use this structure:

```ts
import { NextRequest, NextResponse } from "next/server";
import { apiErrorResponse, jsonNoStore, requireAdmin } from "@/lib/server/authz";
import {
  assertAllowedConfigKeys,
  envPaths,
  generateConfigVersion,
  readConfigResponse,
  updateEnvFile,
} from "@/lib/server/config-store";
import { applyBackendConfig } from "@/lib/server/backend-apply";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function GET() {
  try {
    await requireAdmin();
    return jsonNoStore({ ok: true, configs: readConfigResponse() });
  } catch (error) {
    return apiErrorResponse(error);
  }
}

export async function POST(req: NextRequest) {
  try {
    const user = await requireAdmin();
    const body = await req.json();
    const configs = assertAllowedConfigKeys(body.configs || {});
    const version = generateConfigVersion(configs);
    const updates = { ...configs, XHS_CONFIG_VERSION: version };

    for (const [key, value] of Object.entries(updates)) {
      process.env[key] = value;
    }

    const { webEnvPath, rootEnvPath } = envPaths();
    updateEnvFile(webEnvPath, updates);
    updateEnvFile(rootEnvPath, updates);

    let apply;
    try {
      apply = await applyBackendConfig();
    } catch (error) {
      apply = {
        mode: process.env.XHS_BACKEND_APPLY_MODE || "manual",
        applied: false,
        message: (error as Error).message,
      };
    }

    console.info("[config] saved", {
      actor: user.openId,
      version,
      keys: Object.keys(configs),
      apply,
    });

    return NextResponse.json({ ok: true, version, apply });
  } catch (error) {
    return apiErrorResponse(error);
  }
}
```

- [ ] **Step 4: Require admin for config test**

At the top of `web/src/app/api/config/test/route.ts`, import `apiErrorResponse` and `requireAdmin`. If the route has no `try/catch`, wrap the full handler body with this shape:

```ts
export async function POST(req: NextRequest) {
  try {
    await requireAdmin();
    const body = await req.json();
    const result = await runProviderConnectivityTest(body);
    return NextResponse.json(result);
  } catch (e: any) {
    return apiErrorResponse(e);
  }
}
```

If the current route uses inline provider-test logic instead of `runProviderConnectivityTest`, keep that inline logic inside the `try` block after `await requireAdmin();`, and replace its catch response with `return apiErrorResponse(e);`.

- [ ] **Step 5: Add backend status route**

Create `web/src/app/api/backend/status/route.ts`:

```ts
import { apiErrorResponse, jsonNoStore, requireAdmin } from "@/lib/server/authz";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function GET() {
  try {
    await requireAdmin();
    const applyMode = (process.env.XHS_BACKEND_APPLY_MODE || "manual").trim().toLowerCase();
    return jsonNoStore({
      ok: true,
      config_version: process.env.XHS_CONFIG_VERSION || "",
      apply_mode: applyMode,
      hot_apply_supported: false,
      status_message:
        applyMode === "manual"
          ? "配置已保存到环境文件；Python 后端需要手动重启后才会加载新版本。"
          : "配置保存后会通过固定 apply mode 触发后端重启。",
    });
  } catch (error) {
    return apiErrorResponse(error);
  }
}
```

- [ ] **Step 6: Run checks**

Run:

```powershell
cd E:\小红书智能体\web
.\node_modules\.bin\tsc.CMD --noEmit
.\node_modules\.bin\eslint.CMD src
```

Expected: TypeScript passes. ESLint has no errors.

- [ ] **Step 7: Commit**

```bash
git add web/src/lib/server/config-store.ts web/src/lib/server/backend-apply.ts web/src/app/api/backend/status/route.ts web/src/app/api/config/route.ts web/src/app/api/config/test/route.ts
git commit -m "feat: protect configuration management"
```

## Task 3: Align LLM UI With `LLM_QUALITY_MODELS`

**Files:**
- Modify: `web/src/components/thread/history/LlmConfigPage.tsx`
- Modify: `.env.example`

- [ ] **Step 1: Replace single model save contract**

In `LlmConfigPage.tsx`, keep the UI minimal for phase 1: use the existing model input, but save it as a one-or-more comma-separated quality model list.

When loading config, read:

```ts
const qualityModels = c.LLM_QUALITY_MODELS || c.LLM_MODEL || "";
```

When populating provider config, set:

```ts
model: qualityModels || providerDefaults[current]?.model || "",
```

- [ ] **Step 2: Save `LLM_QUALITY_MODELS`**

In `handleSave`, replace `LLM_MODEL: activeConfig.model?.trim() || ""` with:

```ts
LLM_QUALITY_MODELS: activeConfig.model
  ?.split(",")
  .map((item) => item.trim())
  .filter(Boolean)
  .join(",") || "",
```

Keep `LLM_PROVIDER`, `LLM_API_KEY`, and `LLM_BASE_URL`.

- [ ] **Step 3: Update visible copy**

Change labels from `模型名称 (Model)` to:

```tsx
高质量模型池 (LLM_QUALITY_MODELS)
```

Set the model input placeholder to:

```tsx
请输入模型 ID，多个模型用英文逗号分隔，如 gpt-4o,claude-sonnet-4-6
```

- [ ] **Step 4: Update `.env.example`**

Ensure `.env.example` contains:

```env
LLM_PROVIDER=openai
LLM_BASE_URL=https://your-gateway/v1
LLM_API_KEY=your-gateway-key
LLM_QUALITY_MODELS=claude-sonnet-4-6,gpt-4o
XHS_ADMIN_OPEN_IDS=
XHS_BACKEND_APPLY_MODE=manual
XHS_BACKEND_PM2_NAME=xhs-backend
XHS_BACKEND_SYSTEMD_SERVICE=xhs-backend.service
XHS_PUBLIC_ORIGIN=http://localhost:3000
XHS_CONFIG_VERSION=
```

- [ ] **Step 5: Run checks**

Run:

```powershell
cd E:\小红书智能体\web
.\node_modules\.bin\tsc.CMD --noEmit
.\node_modules\.bin\eslint.CMD src
```

Expected: PASS or warnings only.

- [ ] **Step 6: Commit**

```bash
git add .env.example web/src/components/thread/history/LlmConfigPage.tsx
git commit -m "feat: align model config with quality pool"
```

## Task 4: Enforce UAT-Only Feishu Execution in Server Mode

**Files:**
- Modify: `tools/lark_cli.py`
- Modify: `tools/feishu_bitable.py`
- Test: `tests/test_lark_cli.py`
- Test: `tests/test_feishu_bitable.py`

- [ ] **Step 1: Add failing tests for server mode no bot fallback**

Append to `tests/test_lark_cli.py`:

```python
class _MockUser:
    identity = "ou_missing_uat"


class _MockServerInfo:
    user = _MockUser()


class _MockConfig:
    server_info = _MockServerInfo()


@patch("tools.lark_cli.get_uat", return_value=None)
@patch("tools.lark_cli.subprocess.run")
def test_lark_cli_server_mode_requires_user_uat(mock_run, mock_get_uat):
    res = lark_cli.func("im +chat-list", config=_MockConfig())
    assert "Please authorize Feishu access first" in res
    mock_get_uat.assert_called_once_with("ou_missing_uat")
    mock_run.assert_not_called()
```

Append to `tests/test_feishu_bitable.py`:

```python
def test_read_xhs_data_does_not_print_tokens(capsys):
    with patch.dict(os.environ, {
        "FEISHU_BITABLE_APP_TOKEN": "mock_app_token",
        "FEISHU_BITABLE_TABLE_ID": "mock_table_id",
    }):
        with patch("tools.lark_cli.lark_cli") as mock_lark_cli:
            mock_lark_cli.func.return_value = "Error: stop"
            read_xhs_data.func()
    captured = capsys.readouterr()
    assert "mock_app_token" not in captured.out
    assert "mock_table_id" not in captured.out
```

- [ ] **Step 2: Run tests and verify failure**

Run:

```powershell
uv run pytest tests/test_lark_cli.py::test_lark_cli_server_mode_requires_user_uat tests/test_feishu_bitable.py::test_read_xhs_data_does_not_print_tokens -q
```

Expected: at least the print-token test fails before implementation if the debug print remains.

- [ ] **Step 3: Remove debug print**

In `tools/feishu_bitable.py`, delete:

```python
print("DEBUG inside function: app_token =", repr(app_token), "table_id =", repr(table_id))
```

- [ ] **Step 4: Make server mode require UAT**

In `tools/lark_cli.py`, replace the identity resolution branch with this logic:

```python
    server_mode = server_info is not None

    if open_id and not force_bot:
        token = get_uat(open_id)
        if not token:
            return "Please authorize Feishu access first. Please log in again using the UI panel to grant permissions."
        if brand == "feishu":
            run_env["LARK_USER_ACCESS_TOKEN"] = token
            run_env["LARK_DEFAULT_AS"] = "user"
        else:
            run_env["LARKSUITE_CLI_USER_ACCESS_TOKEN"] = token
            run_env["LARKSUITE_CLI_DEFAULT_AS"] = "user"
    elif server_mode and not force_bot:
        return "Please authorize Feishu access first. Current server request has no Feishu user identity."
    else:
        app_id = os.environ.get("FEISHU_APP_ID")
        app_secret = os.environ.get("FEISHU_APP_SECRET")
        if not app_id or not app_secret:
            return "Error: Bot credentials (FEISHU_APP_ID/SECRET) not configured."
        if brand == "feishu":
            run_env["LARK_APP_ID"] = app_id
            run_env["LARK_APP_SECRET"] = app_secret
            run_env["LARK_DEFAULT_AS"] = "bot"
        else:
            run_env["LARKSUITE_CLI_APP_ID"] = app_id
            run_env["LARKSUITE_CLI_APP_SECRET"] = app_secret
            run_env["LARKSUITE_CLI_DEFAULT_AS"] = "bot"
```

- [ ] **Step 5: Run tests**

Run:

```powershell
uv run pytest tests/test_lark_cli.py tests/test_feishu_bitable.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add tools/lark_cli.py tools/feishu_bitable.py tests/test_lark_cli.py tests/test_feishu_bitable.py
git commit -m "fix: require user Feishu authorization in server mode"
```

## Task 5: Feishu Status Diagnostics

**Files:**
- Modify: `web/src/app/api/feishu/status/route.ts`
- Modify: `web/src/lib/server/internal-client.ts`
- Modify: `tools/cli_runner.py`

- [ ] **Step 1: Replace bot-only status route**

Replace `web/src/app/api/feishu/status/route.ts` with:

```ts
import { NextResponse } from "next/server";
import { apiErrorResponse, requireUser } from "@/lib/server/authz";
import { forwardToInternalServer } from "@/lib/server/internal-client";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function GET() {
  try {
    const user = await requireUser();
    const appConfigured = Boolean(process.env.FEISHU_APP_ID && process.env.FEISHU_APP_SECRET);
    const bitableConfigured = Boolean(
      process.env.FEISHU_BITABLE_APP_TOKEN && process.env.FEISHU_BITABLE_TABLE_ID,
    );

    let uat: { ok?: boolean; error?: string } = {};
    try {
      const resp = await forwardToInternalServer("/_internal/uat-status", "GET", user.openId);
      uat = await resp.json();
    } catch (error) {
      uat = { ok: false, error: (error as Error).message };
    }

    return NextResponse.json({
      ok: true,
      user: { openId: user.openId, name: user.name },
      app_configured: appConfigured,
      bitable_configured: bitableConfigured,
      uat,
    });
  } catch (error) {
    return apiErrorResponse(error);
  }
}
```

- [ ] **Step 2: Add `uat-status` action to bridge**

In `web/src/lib/server/internal-client.ts`, add a branch:

```ts
  } else if (pathName === "/_internal/uat-status") {
    action = "uat-status";
    runnerArgs.push("--action", "uat-status");
```

In `tools/cli_runner.py`, add action choice:

```python
parser.add_argument("--action", choices=["save-uat", "uat-status", "chats", "sync", "notify"], required=True)
```

Add handler:

```python
def handle_uat_status(args):
    token = get_uat(args.open_id)
    if token:
        print(json.dumps({"ok": True, "authorized": True}))
    else:
        print(json.dumps({"ok": True, "authorized": False, "error": "Feishu user authorization is missing or expired."}))
```

Wire it:

```python
    elif args.action == "uat-status":
        handle_uat_status(args)
```

- [ ] **Step 3: Run checks**

Run:

```powershell
uv run pytest tests/test_uat_store.py -q
cd E:\小红书智能体\web
.\node_modules\.bin\tsc.CMD --noEmit
```

Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add web/src/app/api/feishu/status/route.ts web/src/lib/server/internal-client.ts tools/cli_runner.py
git commit -m "feat: add Feishu authorization diagnostics"
```

## Task 6: Create Draft Records Instead of Updating Fixed Records

**Files:**
- Modify: `tools/cli_runner.py`
- Modify: `web/src/lib/server/internal-client.ts`
- Modify: `web/src/app/api/feishu/sync/route.ts`
- Modify: `web/src/components/thread/index.tsx`

- [ ] **Step 1: Change sync API input**

In `web/src/app/api/feishu/sync/route.ts`, remove `recordId` from required input:

```ts
const { title, content, tags, threadId } = body;
if (!title || !content) {
  return NextResponse.json({ error: "Bad Request: Missing title or content" }, { status: 400 });
}

const resp = await forwardToInternalServer("/_internal/sync", "POST", payload.sub, {
  title,
  content,
  tags,
  threadId,
});
```

- [ ] **Step 2: Update `cli_runner.py` sync handler**

Change `handle_sync` to create a record. Use field names first, with environment overrides:

```python
    title_field = os.environ.get("XHS_BITABLE_FIELD_TITLE", "标题")
    body_field = os.environ.get("XHS_BITABLE_FIELD_BODY", "正文内容")
    tags_field = os.environ.get("XHS_BITABLE_FIELD_TAGS", "标签")
    author_field = os.environ.get("XHS_BITABLE_FIELD_AUTHOR", "创建人")
    status_field = os.environ.get("XHS_BITABLE_FIELD_STATUS", "状态")

    fields_payload = {
        title_field: title,
        body_field: content,
        author_field: open_id,
        status_field: "草稿",
    }
    if getattr(args, "tags", None):
        fields_payload[tags_field] = args.tags

    create_payload = {"fields": fields_payload}

    sync_cmd = shlex.join([
        "base",
        "+record-create",
        "--base-token", app_token,
        "--table-id", table_id,
        "--json", json.dumps(create_payload, ensure_ascii=False)
    ])
```

Parse `record_id`:

```python
        res_data = json.loads(sync_resp)
        record_id = (
            res_data.get("data", {}).get("record", {}).get("record_id")
            or res_data.get("data", {}).get("record_id")
            or ""
        )
```

Return:

```python
        print(json.dumps({
            "ok": True,
            "record_id": record_id,
            "redirect_url": f"https://feishu.cn/base/{app_token}?table={table_id}"
        }, ensure_ascii=False))
```

Add parser args:

```python
parser.add_argument("--tags")
parser.add_argument("--thread-id")
```

In `internal-client.ts`, pass tags/threadId to runner args when present:

```ts
const { title, content, tags, threadId } = extraBody || {};
runnerArgs.push("--action", "sync", "--title", String(title), "--content", String(content));
if (tags) runnerArgs.push("--tags", String(tags));
if (threadId) runnerArgs.push("--thread-id", String(threadId));
```

- [ ] **Step 3: Remove fixed record ID in UI**

In `web/src/components/thread/index.tsx`, delete:

```tsx
const [recordId] = useState("rec_default_4");
const [rowNum] = useState("4");
```

Add:

```tsx
const [syncedRecordId, setSyncedRecordId] = useState<string | null>(null);
```

When calling `/api/feishu/sync`, remove `recordId` and include `threadId`:

```tsx
body: JSON.stringify({
  title: draftTitle,
  content: draftContent,
  threadId,
})
```

On success:

```tsx
if (data.record_id) setSyncedRecordId(data.record_id);
```

Replace “已绑定选题行” text with:

```tsx
<span className="font-semibold text-charcoal">
  {syncedRecordId ? `已创建草稿记录：${syncedRecordId}` : "尚未入库"}
</span>
```

- [ ] **Step 4: Run checks**

Run:

```powershell
uv run pytest tests/test_lark_cli.py tests/test_uat_store.py -q
cd E:\小红书智能体\web
.\node_modules\.bin\tsc.CMD --noEmit
.\node_modules\.bin\eslint.CMD src
```

Expected: PASS or warnings only.

- [ ] **Step 5: Commit**

```bash
git add tools/cli_runner.py web/src/lib/server/internal-client.ts web/src/app/api/feishu/sync/route.ts web/src/components/thread/index.tsx
git commit -m "feat: sync drafts by creating Feishu records"
```

## Task 7: Clean Deployment Hardcoding and ESLint Scope

**Files:**
- Modify: `web/src/lib/server/internal-client.ts`
- Modify: `web/src/app/api/auth/feishu/login/route.ts`
- Modify: `web/src/app/api/auth/feishu/callback/route.ts`
- Modify: `web/eslint.config.js`

- [ ] **Step 1: Replace Linux Python hardcode**

In `web/src/lib/server/internal-client.ts`, replace:

```ts
executable = "/home/ubuntu/xiaohongshu-agent/.venv/bin/python3";
```

with:

```ts
executable = process.env.XHS_PYTHON_BIN || "/home/ubuntu/xiaohongshu-agent/.venv/bin/python3";
```

This preserves current deployment while making the path configurable.

- [ ] **Step 2: Centralize public origin**

In both Feishu auth routes, use:

```ts
function getActualOrigin(req: NextRequest): string {
  if (process.env.XHS_PUBLIC_ORIGIN) return process.env.XHS_PUBLIC_ORIGIN.replace(/\/$/, "");
  const host = req.headers.get("x-forwarded-host") || req.headers.get("host") || "localhost:3000";
  const protocol = req.headers.get("x-forwarded-proto") || "http";
  const actualHost = host.split(",")[0].trim();
  return `${protocol}://${actualHost}`;
}
```

Remove hardcoded `124.221.173.80:9091`.

- [ ] **Step 3: Ignore generated files in ESLint**

In `web/eslint.config.js`, change:

```ts
{ ignores: ["dist"] },
```

to:

```ts
{ ignores: ["dist", ".next", "next-env.d.ts", "tsconfig.test.tsbuildinfo"] },
```

- [ ] **Step 4: Run frontend checks**

Run:

```powershell
cd E:\小红书智能体\web
.\node_modules\.bin\tsc.CMD --noEmit
.\node_modules\.bin\eslint.CMD .
```

Expected: ESLint no longer fails on `.next/types`.

- [ ] **Step 5: Commit**

```bash
git add web/src/lib/server/internal-client.ts web/src/app/api/auth/feishu/login/route.ts web/src/app/api/auth/feishu/callback/route.ts web/eslint.config.js
git commit -m "chore: remove deployment hardcoding"
```

## Task 8: Final Quality Gate and Documentation Pass

**Files:**
- Modify: `README.md`
- Modify: `.env.example`

- [ ] **Step 1: Update README phase 1 configuration**

Add a section:

```md
## 多用户部署关键配置

- `XHS_ADMIN_OPEN_IDS`: 逗号分隔的飞书 open_id，只有这些用户能访问系统配置。
- `XHS_BACKEND_APPLY_MODE`: `manual`、`pm2` 或 `systemd`。默认 `manual`，不会自动重启后端。
- `LLM_PROVIDER`: 第一阶段生产路径建议固定为 `openai`。
- `LLM_QUALITY_MODELS`: 高质量模型池，逗号分隔；第一项是首选模型。
- 飞书操作在 server 模式下默认使用当前用户 UAT，缺授权时不会静默退回 bot。
```

- [ ] **Step 2: Run complete backend tests**

Run:

```powershell
uv run pytest
```

Expected: all tests pass.

- [ ] **Step 3: Run frontend checks**

Run:

```powershell
cd E:\小红书智能体\web
.\node_modules\.bin\tsc.CMD --noEmit
.\node_modules\.bin\eslint.CMD src
.\node_modules\.bin\eslint.CMD .
```

Expected: TypeScript passes. `eslint .` does not scan `.next` errors.

- [ ] **Step 4: Commit**

```bash
git add README.md .env.example
git commit -m "docs: document multi-user phase one setup"
```

- [ ] **Step 5: Final status**

Run:

```powershell
git status --short
```

Expected: only unrelated pre-existing changes remain. Do not stage unrelated files.
