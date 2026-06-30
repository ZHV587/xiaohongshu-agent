import { cookies } from "next/headers";
import { apiErrorResponse, jsonNoStore, requireUser } from "@/lib/server/authz";
import { AUTH_COOKIE, getFeishuConfig } from "@/lib/server/feishu";
import { verifyJwt } from "@/lib/server/jwt";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

// 登录会话(httpOnly cookie 中的 JWT)是登录用户账号档案的权威载体:除 sub/name 外,
// 还可携带 team/handle/fans 等档案声明(claim)。本端点在既有 openId/name/isAdmin 之外,
// 读取这些可选档案字段并按需求 8.3 处理:字段缺失时省略键(绝不输出空串占位)。
// 铁律:只回带真实会话数据,不 mock;响应 Cache-Control: no-store,不暴露身份令牌本体。
type ProfileFields = {
  team?: string;
  handle?: string;
  fans?: string;
};

/** 从已验签的 JWT 载荷中拣选 team/handle/fans 档案声明,仅保留非空字符串。 */
function pickProfileFields(payload: Record<string, unknown> | null): ProfileFields {
  const out: ProfileFields = {};
  if (!payload) return out;
  for (const key of ["team", "handle", "fans"] as const) {
    const value = payload[key];
    if (typeof value === "string" && value.trim()) {
      out[key] = value.trim();
    }
  }
  return out;
}

/** 复用既有验签读出登录会话档案声明(与 requireUser 同源,杜绝伪造)。 */
async function readProfileFields(): Promise<ProfileFields> {
  const token = (await cookies()).get(AUTH_COOKIE)?.value;
  if (!token) return {};
  const payload = verifyJwt(token, getFeishuConfig().jwtSecret);
  return pickProfileFields(payload as Record<string, unknown> | null);
}

export async function GET() {
  try {
    const user = await requireUser();
    const profile = await readProfileFields();
    return jsonNoStore({
      ok: true,
      user: {
        openId: user.openId,
        name: user.name,
        isAdmin: user.isAdmin,
        // team/handle/fans 取自登录用户账号档案;缺失字段省略键而非空串(需求 8.3)。
        ...profile,
      },
    });
  } catch (error) {
    return apiErrorResponse(error);
  }
}
