// 封面图统一走同源图片代理(/api/img),由服务端注入 Referer 规避小红书/美团/飞书 CDN 防盗链。
// 前端所有素材卡/笔记封面渲染都用它,不要直接把外链塞进 <img src>(浏览器直连会被防盗链拒,破图)。
export function coverProxyUrl(rawUrl: string | undefined | null): string | undefined {
  if (!rawUrl) return undefined;
  const url = rawUrl.trim();
  if (!url) return undefined;
  // 只代理 http(s) 外链;data: / blob: 等本地源直接放行(代理无意义)。
  if (!/^https?:\/\//i.test(url)) return url;
  return `/api/img?u=${encodeURIComponent(url)}`;
}
