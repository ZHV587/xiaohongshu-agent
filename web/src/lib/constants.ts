// 客户端与服务端均可安全 import 的共享常量。
// 注意：不要在此文件中 import 任何只能在服务端运行的模块。

/** 身份令牌 Cookie 名（客户端可读，非 httpOnly）。 */
export const AUTH_COOKIE = "xhs_auth";

/** CSRF 防护 State Cookie 名（httpOnly）。 */
export const STATE_COOKIE = "xhs_oauth_state";
