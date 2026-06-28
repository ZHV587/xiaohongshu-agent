// JWT 跨语言契约驱动:直接调用生产 jwt.ts 的 signJwt / verifyJwt,供 Python 契约测试驱动。
// Node 23.6+ 默认类型擦除,可直接 import .ts。用法:
//   node scripts/jwt-contract.mjs sign   <secret> <sub> [name] [ttlSeconds]
//   node scripts/jwt-contract.mjs verify <secret> <token>
// sign 打印 token;verify 打印 payload 的 JSON(验签失败打印 "null")。
import { signJwt, verifyJwt } from "../src/lib/server/jwt.ts";

const [action, ...rest] = process.argv.slice(2);

if (action === "sign") {
  const [secret, sub, name, ttl] = rest;
  const payload = { sub };
  if (name) payload.name = name;
  const token = ttl ? signJwt(payload, secret, Number(ttl)) : signJwt(payload, secret);
  process.stdout.write(token);
} else if (action === "verify") {
  const [secret, token] = rest;
  process.stdout.write(JSON.stringify(verifyJwt(token, secret)));
} else {
  process.stderr.write("unknown action");
  process.exit(2);
}
