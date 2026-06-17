// 服务端 JWT(HS256)签发/验证。仅在 Next.js 服务端使用 —— 依赖 node:crypto。
// 与后端 auth.py 的 _verify_jwt 对齐:alg=HS256,payload 含 sub(飞书 open_id)、name、exp。
import crypto from "node:crypto";

function b64url(input: Buffer | string): string {
  return Buffer.from(input)
    .toString("base64")
    .replace(/=/g, "")
    .replace(/\+/g, "-")
    .replace(/\//g, "_");
}

function b64urlJson(obj: unknown): string {
  return b64url(JSON.stringify(obj));
}

export interface XhsJwtPayload {
  sub: string; // 飞书 open_id
  name?: string; // 显示名
  exp: number; // 过期时间(秒)
  iat: number; // 签发时间(秒)
}

/** 用共享密钥签发 HS256 JWT。ttlSeconds 默认 7 天。 */
export function signJwt(
  payload: { sub: string; name?: string },
  secret: string,
  ttlSeconds = 7 * 24 * 3600,
): string {
  const now = Math.floor(Date.now() / 1000);
  const header = { alg: "HS256", typ: "JWT" };
  const body: XhsJwtPayload = {
    sub: payload.sub,
    name: payload.name,
    iat: now,
    exp: now + ttlSeconds,
  };
  const signingInput = `${b64urlJson(header)}.${b64urlJson(body)}`;
  const sig = crypto
    .createHmac("sha256", secret)
    .update(signingInput)
    .digest();
  return `${signingInput}.${b64url(sig)}`;
}

/** 验证 JWT,通过返回 payload,否则 null。 */
export function verifyJwt(token: string, secret: string): XhsJwtPayload | null {
  const parts = token.split(".");
  if (parts.length !== 3) return null;
  const [headerSeg, payloadSeg, sigSeg] = parts;

  let header: { alg?: string };
  try {
    header = JSON.parse(Buffer.from(headerSeg, "base64url").toString());
  } catch {
    return null;
  }
  if (header.alg !== "HS256") return null;

  const expected = crypto
    .createHmac("sha256", secret)
    .update(`${headerSeg}.${payloadSeg}`)
    .digest();
  let actual: Buffer;
  try {
    actual = Buffer.from(sigSeg, "base64url");
  } catch {
    return null;
  }
  if (expected.length !== actual.length) return null;
  if (!crypto.timingSafeEqual(expected, actual)) return null;

  let payload: XhsJwtPayload;
  try {
    payload = JSON.parse(Buffer.from(payloadSeg, "base64url").toString());
  } catch {
    return null;
  }
  if (payload.exp && Date.now() / 1000 > payload.exp) return null;
  return payload;
}
