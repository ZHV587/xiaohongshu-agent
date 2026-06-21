// 客户端身份:身份 JWT 现存于 httpOnly cookie,前端 JS 读不到也不再持有 token。
// 所有后端请求走同源 BFF 代理(/api/*),由服务端从 cookie 注入 Bearer。
// 这里只负责:向 /api/me 询问当前身份(服务端验签后返回),以及登录/登出跳转。
"use client";

export interface CurrentUser {
  openId: string;
  name?: string;
  isAdmin?: boolean;
}

/**
 * 取当前登录用户。改为询问服务端 /api/me(httpOnly cookie 由浏览器自动携带,
 * 服务端验签后返回身份)。未登录或失效返回 null。
 */
export async function getCurrentUser(): Promise<CurrentUser | null> {
  try {
    const res = await fetch("/api/me", {
      credentials: "same-origin",
      cache: "no-store",
    });
    if (!res.ok) return null;
    const data = await res.json();
    if (!data?.ok || !data?.user?.openId) return null;
    return {
      openId: data.user.openId,
      name: data.user.name,
      isAdmin: data.user.isAdmin,
    };
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
