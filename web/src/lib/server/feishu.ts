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

/** 从环境变量读取并校验飞书 OAuth 配置;缺项时抛错(便于在路由里返回 500 提示)。 */
export function getFeishuConfig(): FeishuOAuthConfig {
  const appId = process.env.FEISHU_APP_ID;
  const appSecret = process.env.FEISHU_APP_SECRET;
  const jwtSecret = process.env.XHS_JWT_SECRET;
  // 回调地址:默认本地 localhost:3000,可由 FEISHU_REDIRECT_URI 覆盖(上云时换公网域名)。
  const redirectUri =
    process.env.FEISHU_REDIRECT_URI ??
    "http://localhost:3000/api/auth/feishu/callback";

  const missing: string[] = [];
  if (!appId) missing.push("FEISHU_APP_ID");
  if (!appSecret) missing.push("FEISHU_APP_SECRET");
  if (!jwtSecret) missing.push("XHS_JWT_SECRET");
  if (missing.length) {
    throw new Error(`飞书 OAuth 配置缺失:${missing.join(", ")}`);
  }

  return {
    appId: appId!,
    appSecret: appSecret!,
    redirectUri,
    jwtSecret: jwtSecret!,
  };
}

// 前端可读的身份 cookie(JWT,发给后端当 Bearer)与 CSRF state cookie 名。
// 从共享常量 re-export，避免客户端组件直接 import 服务端模块。
export { AUTH_COOKIE, STATE_COOKIE } from "@/lib/constants";
