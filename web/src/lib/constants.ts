// 客户端与服务端均可安全 import 的共享常量。
// 注意：不要在此文件中 import 任何只能在服务端运行的模块。

/** 身份令牌 Cookie 名(httpOnly：仅服务端 BFF 代理读取并注入 Bearer，浏览器 JS 不可读，消除 XSS 窃取面）。 */
export const AUTH_COOKIE = "xhs_auth";

/** CSRF 防护 State Cookie 名（httpOnly）。 */
export const STATE_COOKIE = "xhs_oauth_state";
