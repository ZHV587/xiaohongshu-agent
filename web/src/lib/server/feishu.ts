// 飞书 OAuth 服务端配置与端点常量。仅服务端使用(读 client_secret)。
// 端点参考飞书开放平台「网页应用 OAuth 2.0」新版:
//   授权:   GET  https://open.feishu.cn/open-apis/authen/v1/authorize
//   换token: POST https://open.feishu.cn/open-apis/authen/v2/oauth/token
//   用户信息:GET  https://open.feishu.cn/open-apis/authen/v1/user_info
const FEISHU_OPEN = "https://open.feishu.cn/open-apis";

export const FEISHU_AUTHORIZE_URL = `${FEISHU_OPEN}/authen/v1/authorize`;
export const FEISHU_TOKEN_URL = `${FEISHU_OPEN}/authen/v2/oauth/token`;
export const FEISHU_USER_INFO_URL = `${FEISHU_OPEN}/authen/v1/user_info`;

export interface FeishuOAuthConfig {
  appId: string;
  appSecret: string;
  redirectUri: string;
  jwtSecret: string;
}

/** 从环境变量读取并校验飞书 OAuth 配置;**仅强校 XHS_JWT_SECRET**(部署级、web 与后端共享)。
 *  app_id/app_secret 不在此强校 —— config-center 模式下它们的权威源是后端(经
 *  getFeishuOAuthCredentials 取),web/.env 可不配;此处返回的 env 值仅作内部接口不可达时的回退。 */
export function getFeishuConfig(): FeishuOAuthConfig {
  const jwtSecret = process.env.XHS_JWT_SECRET;
  // 回调地址:默认本地 localhost:3000,可由 FEISHU_REDIRECT_URI 覆盖(上云时换公网域名)。
  const redirectUri =
    process.env.FEISHU_REDIRECT_URI ??
    "http://localhost:3000/api/auth/feishu/callback";

  if (!jwtSecret) {
    throw new Error("飞书 OAuth 配置缺失:XHS_JWT_SECRET");
  }

  return {
    appId: process.env.FEISHU_APP_ID ?? "",
    appSecret: process.env.FEISHU_APP_SECRET ?? "",
    redirectUri,
    jwtSecret,
  };
}

// 前端可读的身份 cookie(JWT,发给后端当 Bearer)与 CSRF state cookie 名。
// 从共享常量 re-export，避免客户端组件直接 import 服务端模块。
export { AUTH_COOKIE, STATE_COOKIE } from "@/lib/constants";

// ── OAuth 路由共享 helper(单一实现,login/callback/logout 统一引用,杜绝各自副本漂移)──
import type { NextRequest } from "next/server";

/** 实际对外 Origin:优先 XHS_PUBLIC_ORIGIN,否则按 x-forwarded-host/proto 还原(TLS 上游终止场景)。 */
export function getActualOrigin(req: NextRequest): string {
  if (process.env.XHS_PUBLIC_ORIGIN) return process.env.XHS_PUBLIC_ORIGIN.replace(/\/$/, "");
  const host = req.headers.get("x-forwarded-host") || req.headers.get("host") || "localhost:3000";
  const protocol = req.headers.get("x-forwarded-proto") || "http";
  const actualHost = host.split(",")[0].trim();
  return `${protocol}://${actualHost}`;
}

/** cookie Secure 标志按**实际对外协议**判定,而非 req.nextUrl.protocol —— TLS 在上游终止、
 *  到达 Next 的是明文 http 时,用 nextUrl.protocol 会让身份 JWT 不带 Secure、可被嗅探。 */
export function isSecureRequest(req: NextRequest): boolean {
  if (process.env.XHS_PUBLIC_ORIGIN) return process.env.XHS_PUBLIC_ORIGIN.startsWith("https:");
  return (req.headers.get("x-forwarded-proto") || req.nextUrl.protocol.replace(":", "")) === "https";
}

/** 只接受站内绝对路径,挡开放重定向:"/foo" 放行;"//evil.com"、"/\evil.com"、非 / 开头一律退回 "/"。 */
export function safeNextPath(value: string | undefined): string {
  if (!value || !value.startsWith("/")) return "/";
  if (value.startsWith("//") || value.startsWith("/\\")) return "/";
  return value;
}

/** 取飞书 OAuth 应用凭证的**权威值**:优先后端(config-center 投影后的 os.environ,经内部接口),
 *  内部不可达时回退本进程 process.env。OAuth 在用户登录前发生(无身份),故走 require_internal
 *  的 /internal/feishu/oauth-config。这样 web 与 langgraph 对飞书凭证强一致,改 config-center 即生效。
 *  延迟 import internal-client,避免与服务端模块的加载顺序耦合。 */
export async function getFeishuOAuthCredentials(): Promise<{ appId: string; appSecret: string }> {
  try {
    const { forwardToInternalServer } = await import("@/lib/server/internal-client");
    const resp = await forwardToInternalServer("/_internal/feishu-oauth-config", "GET", "", undefined, {});
    if (resp.ok) {
      const data = await resp.json().catch(() => null);
      if (data?.ok && typeof data.app_id === "string" && data.app_id) {
        return { appId: data.app_id, appSecret: typeof data.app_secret === "string" ? data.app_secret : "" };
      }
    }
  } catch {
    // 内部接口不可达(本地单进程 / 未配 internal HTTP):回退本进程 env。
  }
  return { appId: process.env.FEISHU_APP_ID ?? "", appSecret: process.env.FEISHU_APP_SECRET ?? "" };
}
