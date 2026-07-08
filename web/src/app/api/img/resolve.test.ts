import assert from "node:assert/strict";
import test from "node:test";

import { isAllowedHost, refererFor, resolveImageTarget } from "./resolve";

test("allows known image CDN hosts and their subdomains", () => {
  assert.equal(isAllowedHost("sns-na-i11.xhscdn.com"), true);
  assert.equal(isAllowedHost("sns-img-hw.xhscdn.net"), true);
  assert.equal(isAllowedHost("ci.xiaohongshu.com"), true);
  assert.equal(isAllowedHost("p1.meituan.net"), true);
  assert.equal(isAllowedHost("open.feishu.cn"), true);
  // 新增:小红书新 CDN(rednotecdn)、抖音图床、视频号封面 —— 这些是本地库里"有的显示有的不显示"
  // 的破图根因(封面直链指向这些域,旧白名单没收 → /api/img 返回 403)。
  assert.equal(isAllowedHost("sns-i14-ae.rednotecdn.com"), true);
  assert.equal(isAllowedHost("sns-i11.rednotecdn.com"), true);
  assert.equal(isAllowedHost("p3-pc-sign.douyinpic.com"), true);
  assert.equal(isAllowedHost("finder.video.qq.com"), true);
});

test("rejects non-allowlisted hosts (SSRF guard)", () => {
  assert.equal(isAllowedHost("localhost"), false);
  assert.equal(isAllowedHost("169.254.169.254"), false);
  assert.equal(isAllowedHost("evil.com"), false);
  // 不能被 xhscdn.com.evil.com 这类后缀伪装绕过。
  assert.equal(isAllowedHost("xhscdn.com.evil.com"), false);
});

test("missing param → 400", () => {
  const r = resolveImageTarget(null);
  assert.equal(r.ok, false);
  assert.equal(r.ok === false && r.status, 400);
});

test("non-http protocol → 400", () => {
  const r = resolveImageTarget("ftp://sns-na-i11.xhscdn.com/x.jpg");
  assert.equal(r.ok, false);
  assert.equal(r.ok === false && r.status, 400);
});

test("disallowed host → 403", () => {
  const r = resolveImageTarget("https://evil.com/x.jpg");
  assert.equal(r.ok, false);
  assert.equal(r.ok === false && r.status, 403);
});

test("http upstream from allowlisted host is accepted (mixed-content is why we proxy)", () => {
  const r = resolveImageTarget("http://sns-img-hw.xhscdn.net/notes/abc?imageView2/2/w/1080/format/webp");
  assert.equal(r.ok, true);
});

test("rewrites xhscdn format/heif → format/jpg so browsers can render it", () => {
  const r = resolveImageTarget(
    "https://sns-na-i11.xhscdn.com/abc?imageView2/2/w/576/format/heif/q/58",
  );
  assert.equal(r.ok, true);
  assert.ok(r.ok && !r.target.toString().includes("format/heif"));
  assert.ok(r.ok && r.target.toString().includes("format/jpg"));
});

test("non-heif urls pass through untouched", () => {
  const url = "https://sns-img-hw.xhscdn.net/notes/abc?imageView2/2/w/1080/format/webp";
  const r = resolveImageTarget(url);
  assert.equal(r.ok, true);
  assert.ok(r.ok && r.target.toString().includes("format/webp"));
});

test("referer targets xiaohongshu for xhs cdn hosts", () => {
  assert.equal(refererFor(new URL("https://sns-na-i11.xhscdn.com/x")), "https://www.xiaohongshu.com/");
  assert.equal(refererFor(new URL("https://open.feishu.cn/x")), "https://open.feishu.cn/");
});

test("rednotecdn is treated as xhs family: xiaohongshu referer + heif rewrite", () => {
  assert.equal(refererFor(new URL("https://sns-i14-ae.rednotecdn.com/x")), "https://www.xiaohongshu.com/");
  const r = resolveImageTarget(
    "https://sns-i14-ae.rednotecdn.com/abc?imageView2/2/w/1080/format/heif/q/58",
  );
  assert.equal(r.ok, true);
  assert.ok(r.ok && !r.target.toString().includes("format/heif"));
  assert.ok(r.ok && r.target.toString().includes("format/jpg"));
});

test("douyinpic + video.qq.com covers resolve (no longer 403)", () => {
  assert.equal(resolveImageTarget("https://p3-pc-sign.douyinpic.com/x.jpg").ok, true);
  assert.equal(resolveImageTarget("https://finder.video.qq.com/x.jpg").ok, true);
});
