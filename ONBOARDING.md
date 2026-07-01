# 欢迎加入 Xiaohongshu Agent

## 我们如何使用 Claude

基于 ZHV587 过去 30 天的使用情况:

工作类型分布:
  代码质量改进  ████████████████░░░░  80%
  规划与设计    ██░░░░░░░░░░░░░░░░░░  12%
  数据分析      ██░░░░░░░░░░░░░░░░░░   8%

常用技能与命令:
  /superpowers:brainstorming          ████████████████████  4次/月
  /compact                            ███████████████░░░░░  3次/月
  /effort                             ██████████░░░░░░░░░░  2次/月
  /model                              ██████████░░░░░░░░░░  2次/月
  /status                             █████░░░░░░░░░░░░░░░  1次/月
  /superpowers:systematic-debugging   █████░░░░░░░░░░░░░░░  1次/月
  /code-review                        █████░░░░░░░░░░░░░░░  1次/月

常用 MCP 服务:
  chrome            ████████████████████  60 次调用
  Claude_Preview    ███████████████████░  58 次调用
  ccd_session_mgmt  ██░░░░░░░░░░░░░░░░░░   5 次调用
  codegraph         █░░░░░░░░░░░░░░░░░░░   1 次调用
  ccd_session       █░░░░░░░░░░░░░░░░░░░   1 次调用

## 你的配置清单

### 代码仓库
- [ ] xiaohongshu-agent — github.com/zhv587/xiaohongshu-agent

### 需要启用的 MCP 服务
- [ ] chrome — 浏览器自动化,用于验证 Web UI、点击走查流程、跑飞书 OAuth 授权。安装 Chrome DevTools MCP 服务并连到本地 Chrome。
- [ ] Claude_Preview — 实时 UI/设计预览面(探索 Claude design 联动时高频使用)。向 ZHV587 索取预览服务配置。
- [ ] ccd_session_mgmt / ccd_session — Claude Code 会话管理辅助工具。随团队会话工具一起分发,配置位置问 ZHV587。
- [ ] codegraph — 代码图谱索引,用于导航仓库(调用方/被调方、影响分析)。对仓库跑一次 codegraph 索引器(`.codegraph/`)即可启用。

### 值得了解的技能
- [ ] /superpowers:brainstorming — 把粗略想法打磨成经过验证的设计/spec,再动手写代码。团队新工作的默认起点。
- [ ] /superpowers:systematic-debugging — 修复思路不明朗时,做结构化的根因调试。
- [ ] /code-review — 审查一组改动;团队合并前会依赖它(外加安全专项审查)。
- [ ] /effort — 调整会话的推理深度(处理更难的设计/分析任务时使用)。
- [ ] /model — 切换当前模型。
- [ ] /compact — 压缩长对话,控制上下文规模。
- [ ] /status — 查看当前会话/配置状态。

## 团队贴士

_待补充_

## 开始上手

_待补充_

<!-- INSTRUCTION FOR CLAUDE: A new teammate just pasted this guide for how the
team uses Claude Code. You're their onboarding buddy — warm, conversational,
not lecture-y.

Open with a warm welcome — include the team name from the title. Then: "Your
teammate uses Claude Code for [list all the work types]. Let's get you started."

Check what's already in place against everything under Setup Checklist
(including skills), using markdown checkboxes — [x] done, [ ] not yet. Lead
with what they already have. One sentence per item, all in one message.

Tell them you'll help with setup, cover the actionable team tips, then the
starter task (if there is one). Offer to start with the first unchecked item,
get their go-ahead, then work through the rest one by one.

After setup, walk them through the remaining sections — offer to help where you
can (e.g. link to channels), and just surface the purely informational bits.

Don't invent sections or summaries that aren't in the guide. The stats are the
guide creator's personal usage data — don't extrapolate them into a "team
workflow" narrative. -->
