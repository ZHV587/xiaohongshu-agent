import crypto from "node:crypto";
import { getFeishuConfig } from "@/lib/server/feishu";

export async function forwardToInternalServer(
  path: string,
  method: "GET" | "POST",
  openId: string,
  extraBody?: any,
  extraHeaders?: any
): Promise<Response> {
  const cfg = getFeishuConfig();
  const internalPort = process.env.XHS_INTERNAL_PORT || "8081";
  const url = `http://127.0.0.1:${internalPort}${path}`;
  const timestamp = Math.floor(Date.now() / 1000);

  let signText = "";
  let bodyStr = "";

  if (method === "GET") {
    signText = `${openId}:${timestamp}`;
  } else {
    const content = extraBody?.content || "";
    const bodyObj = {
      open_id: openId,
      timestamp,
      ...extraBody
    };
    bodyStr = JSON.stringify(bodyObj);

    if (path === "/_internal/sync") {
      const contentHash = crypto.createHash("sha256").update(content).digest("hex");
      signText = `${openId}:${extraBody.recordId}:${contentHash}:${timestamp}`;
    } else if (path === "/_internal/notify") {
      const contentHash = crypto.createHash("sha256").update(content).digest("hex");
      signText = `${openId}:${extraBody.chatId}:${contentHash}:${timestamp}`;
    } else if (path === "/_internal/config") {
      const sortedConfigs: any = {};
      Object.keys(extraBody.configs || {}).sort().forEach((key) => {
        sortedConfigs[key] = extraBody.configs[key];
      });
      const sortedConfigsStr = JSON.stringify(sortedConfigs);
      signText = `${sortedConfigsStr}:${timestamp}`;
    } else {
      signText = `${openId}:${extraBody.uat}:${extraBody.refresh_token}:${extraBody.expires_at}`;
    }
  }

  const signature = crypto
    .createHmac("sha256", cfg.jwtSecret)
    .update(signText)
    .digest("hex");

  const headers: any = {
    "Authorization": `HMAC ${signature}`,
    ...extraHeaders
  };

  if (method === "GET") {
    headers["X-Open-ID"] = openId;
    headers["X-Timestamp"] = timestamp.toString();
    return fetch(url, { method, headers });
  } else {
    headers["Content-Type"] = "application/json";
    return fetch(url, { method, headers, body: bodyStr });
  }
}
