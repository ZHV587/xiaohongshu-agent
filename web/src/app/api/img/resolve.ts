// 图片代理的纯逻辑:校验来源(白名单 + 协议)与规整目标 URL(heif→jpg)。抽出便于单测,route 只做 IO。

// 允许的图片来源域后缀(小写、含前导点便于 endsWith 精确匹配子域,根域单列)。
export const ALLOWED_HOST_SUFFIXES = [
  ".xhscdn.com", // 小红书图片 CDN(sns-na-i11.xhscdn.com 等)
  ".xhscdn.net", // 小红书另一图片 CDN 域(sns-img-hw.xhscdn.net,常以 http 下发)
  ".xiaohongshu.com", // ci.xiaohongshu.com 等
  ".meituan.net", // 部分封面走美团 CDN
  ".sankuai.com",
  ".feishu.cn", // 飞书封面直链
  ".feishucdn.com",
  ".larksuite.com",
  ".larksuitecdn.com",
];

export function isAllowedHost(hostname: string): boolean {
  const host = hostname.toLowerCase();
  return ALLOWED_HOST_SUFFIXES.some(
    (suffix) => host === suffix.slice(1) || host.endsWith(suffix),
  );
}

// 依来源域给出合适的 Referer(防盗链校验的正是它)。
export function refererFor(url: URL): string {
  if (url.hostname.endsWith("xhscdn.com") || url.hostname.endsWith("xiaohongshu.com")) {
    return "https://www.xiaohongshu.com/";
  }
  return `${url.protocol}//${url.hostname}/`;
}

export type ResolveResult =
  | { ok: true; target: URL }
  | { ok: false; status: number; error: string };

// 校验并规整来源图片 URL。返回可直接 fetch 的 target,或带状态码的错误。
export function resolveImageTarget(raw: string | null): ResolveResult {
  if (!raw) return { ok: false, status: 400, error: "缺少图片地址参数 u" };

  let target: URL;
  try {
    target = new URL(raw);
  } catch {
    return { ok: false, status: 400, error: "图片地址不合法" };
  }

  // 协议限 http/https。小红书部分 CDN(xhscdn.net)以 http 下发,页面是 https 时浏览器会拦混合内容,
  // 正是走服务端代理消除;SSRF 由 host 白名单严格兜底,http 本身不放大风险。
  if (target.protocol !== "https:" && target.protocol !== "http:") {
    return { ok: false, status: 400, error: "仅支持 http/https 图片地址" };
  }
  if (!isAllowedHost(target.hostname)) {
    // 非白名单来源直接拒绝,避免被当作任意 URL 拉取器(SSRF)。
    return { ok: false, status: 403, error: "图片来源不在允许列表" };
  }

  // 小红书 CDN 默认下发 image/heif —— 浏览器 <img> 无法渲染(灰白破图)。改写为 jpg 让浏览器可显示。
  if (target.hostname.endsWith("xhscdn.com") || target.hostname.endsWith("xhscdn.net")) {
    if (target.search.includes("format/heif")) {
      target.search = target.search.replace("format/heif", "format/jpg");
    }
  }

  return { ok: true, target };
}
