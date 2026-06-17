// 客户端身份读取:从可读 cookie 取 JWT,解出显示名,提供登录/登出跳转。
// JWT 仅用于「读 payload 展示」与「作为 Bearer 转发给后端」,验签在后端 auth.py。
"use client";

const AUTH_COOKIE = "xhs_auth";

function readCookie(name: string): string | null {
  if (typeof document === "undefined") return null;
  const match = document.cookie
    .split("; ")
    .find((row) => row.startsWith(`${name}=`));
  return match ? decodeURIComponent(match.slice(name.length + 1)) : null;
}

/** 取当前身份 JWT(发给后端当 Authorization: Bearer)。未登录返回 null。 */
export function getAuthToken(): string | null {
  return readCookie(AUTH_COOKIE);
}

export interface CurrentUser {
  openId: string;
  name?: string;
}

/** 解析 JWT payload 拿到当前用户(仅用于 UI 显示,不校验签名)。 */
export function getCurrentUser(): CurrentUser | null {
  const token = getAuthToken();
  if (!token) return null;
  const parts = token.split(".");
  if (parts.length !== 3) return null;
  try {
    // atob 产出 latin1 字节串,中文名需再按 UTF-8 解码,否则显示乱码(如 à¾ æ··)。
    const binary = atob(parts[1].replace(/-/g, "+").replace(/_/g, "/"));
    const bytes = Uint8Array.from(binary, (ch) => ch.charCodeAt(0));
    const json = JSON.parse(new TextDecoder("utf-8").decode(bytes));
    if (!json.sub) return null;
    if (json.exp && Date.now() / 1000 > json.exp) return null; // 过期视为未登录
    return { openId: json.sub, name: json.name };
  } catch {
    return null;
  }
}

/** 跳转到飞书登录(带回跳目标)。 */
export function loginWithFeishu(next = "/") {
  const url = `/api/auth/feishu/login?next=${encodeURIComponent(next)}`;
  window.location.href = url;
}

/** 退出登录。 */
export function logout() {
  window.location.href = "/api/auth/feishu/logout";
}
