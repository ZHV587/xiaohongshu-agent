# lark-cli 集成设计(bot + user 双身份)

日期:2026-06-17
状态:待实现
作者:Kiro + 用户

## 背景与目标

小红书文案智能体当前与飞书的唯一连接是 `tools/feishu_bitable.py` 的 `read_xhs_data` —— 用 `app_id/secret` 换 `tenant_access_token`,**只读**多维表格。agent 无法执行任何飞书写操作,也触达不到多维表格之外的业务域。

[lark-cli](https://github.com/larksuite/cli) 是飞书官方 CLI,覆盖 18 个业务域、200+ 命令,为 Agent 原生设计(统一 JSON envelope、清晰退出码、可纯环境变量驱动)。本设计将其接入智能体,补齐飞书全业务域操作能力,**bot 应用身份与 user 用户身份都在本次一起实现**。

**核心洞察(为什么 Claude Code 能直接用而当前 agent 不能)**:Claude Code / Codex 靠两个通用能力用 lark-cli —— ① 能读文件的工具(Read)② 能跑命令的工具(Bash)—— 加 Agent Skills 加载器把 SKILL.md 说明书装进来。当前 agent 缺的是"能跑命令的工具";`read_file`、`SkillsMiddleware` 已具备。

### 边界变更声明

本设计**正式废除**项目此前的边界约定「明确不做:配图、自动发布、飞书写回」。接入 lark-cli 写能力即跨过这条线。为控制风险,所有飞书**写操作默认需要真人确认**(见"错误与确认数据流")。

## 范围

**接入点**:`cli.py`(单机终端)与 `agent.py`(LangGraph server + web)。

**两种身份,本次都做**:
- **bot 应用身份**(`tenant_access_token`):复用 `.env` 的 `FEISHU_APP_ID/SECRET`,无需用户登录,立即可用。操作应用拥有的资源、以应用身份发消息。
- **user 用户身份**(`user_access_token`/UAT):复用现有 web 飞书 OAuth 登录,按 open_id 服务端存储 UAT,以登录用户身份操作飞书。

**身份选择规则**:某请求若能按当前用户 open_id 取到有效 UAT,则该用户的飞书命令默认走 user 身份;取不到则退回 bot 身份。模型也可在 args 里显式带 `--as user`/`--as bot`。

**不在本设计范围**:
- 不改现有 backend(CompositeBackend/FilesystemBackend 照旧)。
- 不改子智能体、前端契约、前端卡片渲染(仅必要的登录态/错误提示沿用现有机制)。
- 不引入 `LocalShellBackend`(裸 shell)—— 多租户 web 官方禁用,风险过大。
- 不引入 HITL 中断审批 UI —— 确认走对话流。
- 不上 Postgres/不依赖正式部署 —— UAT 存储用独立加密文件,本地 dev 即可完整跑通(存储层接口抽象,未来换 Postgres 不改上层)。

## 架构总览

```
              ┌─────────────────────── web 登录(一次性/过期重授权)──────────────────────┐
              │  login(带全量 scope) → 飞书授权页 → callback                              │
              │      callback: code 换 UAT+refresh → 按 open_id 存进【UAT 存储层(加密文件)】 │
              │      JWT 仍只放 open_id(可读 cookie 不碰令牌)                              │
              └──────────────────────────────────────────────────────────────────────────┘
                                              │
  用户对话 → JWT(open_id) → auth.py 验签取 identity=open_id
                                              │
                          agent 调 lark 工具 → 身份解析:
                              按 open_id 从【UAT 存储层】取 UAT(必要时 refresh 自动刷新)
                                  ├─ 取到 → 注入 LARKSUITE_CLI_USER_ACCESS_TOKEN(user 身份)
                                  └─ 取不到 → 注入 APP_ID/SECRET(bot 身份)
                                              │
                          subprocess 执行 lark-cli → 解析 JSON envelope → 返回模型

  知识层:skills/lark-*/(26 个官方 SKILL.md,全量搬) → 现有 SkillsMiddleware 加载摘要进 prompt
          模型按需 read_file 读全文学命令
```

## 文件变更清单

**新增**
- `tools/lark_cli.py` —— lark 工具(命令执行 + 身份注入 + exit10/exit3 处理)
- `tools/lark_scopes.py` —— 全量 user scope 清单常量
- `tools/uat_store.py` —— UAT 加密存储层(按 open_id 存取 + 自动刷新,接口抽象)
- `tests/test_lark_cli.py` —— lark 工具单元测试(mock subprocess)
- `tests/test_uat_store.py` —— UAT 存储层单元测试(临时文件,无网络)
- `verify_lark.py` —— 手动冒烟(真调 lark-cli)
- `skills/lark-*/` —— 26 个官方 skill 目录(SKILL.md + references/ + assets/,搬运)

**修改**
- `agent.py` / `cli.py` —— 挂载 lark 工具;agent.py 注入按 open_id 取 UAT 的身份解析
- `prompts.py` —— 加一小段 lark 工具使用说明(不破坏 xhs_topics/xhs_copy 契约)
- `web/src/app/api/auth/feishu/login/route.ts` —— authorize URL 加全量 `scope`
- `web/src/app/api/auth/feishu/callback/route.ts` —— 换到 UAT 后存进 UAT 存储层(经一个服务端接口),而非用完即焚
- `.env.example` —— 说明 lark 复用 FEISHU_APP_ID/SECRET;新增 UAT 存储路径等配置项

## 组件 1:lark 工具(tools/lark_cli.py)

### 签名

```python
@tool
def lark(args: list[str], yes: bool = False) -> str:
    """执行 lark-cli 飞书命令。
    args: lark-cli 参数数组,如 ["im","+messages-send","--chat-id","oc_x","--text","hi"]。
          不含 "lark-cli" 本身;不要自己加 --format(工具自动补)。
    yes:  仅当上一次调用返回"需要确认"且用户已明确同意时,传 True 重试同一命令。
    """
```

单一通用工具。模型靠读 SKILL.md + 跑 `lark schema`/`--help` 自查命令。身份不由模型决定,由工具内部按当前请求解析(见组件 4)。

### 内部职责(每条对应一条安全红线)

1. **argv 数组直传,`shell=False`**:`subprocess.run(["lark-cli", *args, ...], shell=False)`,参数当数据不当 shell 语法,堵命令注入。Windows 下确认可执行名(可能是 `lark-cli.cmd` 或解析全路径)。
2. **env 白名单注入,不继承父进程全部环境**:只给 lark-cli 必需项 —— 身份令牌(见组件 4)、`LARKSUITE_CLI_DEFAULT_AS`、`LARKSUITE_CLI_CONTENT_SAFETY_MODE=warn`、`PATH`。**显式不传** `ANTHROPIC_API_KEY`/`OPENAI_API_KEY`/`XHS_JWT_SECRET` 到子进程。
3. **format 处理(修正:不再无脑追加)**:仅当 args 中**不含** `--format`、且不是 `--help`/`schema`/`--version` 这类元命令时,才补 `--format json`。元命令原样执行。
4. **黑名单拦截**:`args[0]` 落在 `{auth, config}` 时直接拒绝、不执行(防 agent 改登录态/碰凭证 —— 身份由工具固定)。其余服务域放行。写操作不靠自维护清单,交由 exit 10 闸门。
5. **stdout 与 stderr 都捕获(关键修正)**:lark-cli 成功 envelope 在 **stdout**,错误/确认 envelope(含 exit 10)在 **stderr**。按退出码决定解析哪一路,否则确认信息丢失。
6. **exit 10 处理(关键红线)**:高风险写操作待确认。
   - `yes=False`(默认):**不**追加 `--yes`,把 `risk`/`action`/`hint` 包装成确认提示返回模型,引导其向用户复述并等待。
   - `yes=True`(人已确认):args 追加 `--yes` 重新执行。
7. **exit 3 处理(权限不足/缺 scope)**:返回 `error.message`/`hint`/`console_url` 与 `permission_violations`。若是 user 身份缺 scope,提示走增量授权(见数据流情况 D)。
8. **结果裁剪**:`ok:true` 返 `data`;`ok:false` 返 `error.type/message/hint`。超大输出截断到远低于 deepagents 转存阈值(`TOOL_RESULT_TOKEN_LIMIT*4=80000 字符`),避免触发转存死循环。

### 已定默认

- 超时 60 秒(对齐现有模型调用风格)。
- content-safety = `warn`(飞书数据喂回模型是注入靶场;warn 留痕不阻断,block 会 exit 6 打断)。

## 组件 2:UAT 存储层(tools/uat_store.py)

UAT 有效期约 2 小时,靠 refresh_token 续命,**必须可靠落盘**。但这是项目自有数据,与 LangGraph 的 inmem checkpoint 无关,故用独立加密文件存储,不依赖 Postgres/部署。

- **存储内容**:按 open_id 存 `{user_access_token, refresh_token, expires_at, scopes, name}`。
- **加密**:用现有 `XHS_JWT_SECRET` 派生对称密钥(如 HKDF/SHA256),对文件内容 AES-GCM 加密。文件权限 0600,路径由 `XHS_UAT_STORE_PATH` 配置(默认项目下 gitignore 的 `.uat_store.enc`)。
- **接口(抽象,未来换 Postgres 只改实现)**:
  - `save_uat(open_id, uat, refresh_token, expires_at, scopes, name)`
  - `get_uat(open_id) -> UAT | None`:取时若 `expires_at` 临近,用 refresh_token 调飞书刷新、回存、返回新 UAT;刷新失败返回 None(退回 bot / 提示重新登录)。
- **刷新**:调飞书 `authen/v2/oauth/token`(grant_type=refresh_token),用 `FEISHU_APP_ID/SECRET`。并发安全:同 open_id 刷新加进程内锁(单进程 dev 够用;生产换存储时一并处理跨进程锁)。
- **写入入口**:callback 不能直接写 Python 文件(它是 Next.js 服务端)。约定一个**内部 HTTP 端点或共享写法**让 callback 把 UAT 交给存储层 —— 见组件 3。

## 组件 3:web OAuth 改造

### login/route.ts

authorize URL 当前**完全没有 scope 参数**。改为带上全量 scope(组件 5 清单,空格分隔)。用户将看到完整授权页并需重新授权。

### callback/route.ts

当前换到 `userToken` 后**取完 open_id 即丢弃**。改为:换到 UAT 后,把 `{open_id, uat, refresh_token, expires_at, scopes, name}` 交给 UAT 存储层持久化,再签发 JWT(JWT 内容不变,仍只含 open_id/name —— 可读 cookie 绝不放令牌)。

**callback → UAT 存储层的写入通道**(二选一,实现期定):
- 方案 a:Python 后端暴露一个仅本机、带 `XHS_JWT_SECRET`/HMAC 校验的内部端点 `POST /_internal/uat`,callback 调它写入。
- 方案 b:callback 直接写同一个加密文件(用相同密钥派生 + 相同格式),Python 端只读。
- 倾向 **方案 b**(无需多跑一个服务、dev 简单);但需保证 TS 与 Python 的加密格式严格一致(同 KDF、同 AES-GCM 参数)。实现期先验证格式互通,不通则退方案 a。

## 组件 4:后端身份注入(auth.py + agent.py)

- `auth.py` 已能从 JWT 解出 `ctx.user.identity`(= open_id),**无需改鉴权逻辑**。
- agent 侧需把"当前请求的 open_id"传到 lark 工具内部,用于 `get_uat(open_id)`。LangGraph 工具运行时可经 `ToolRuntime`/runtime 上下文拿到当前用户身份(与 backends.py 的 `_user_memory_namespace` 取 `rt.server_info.user.identity` 同源)。lark 工具内部:
  - 解析当前 open_id → `get_uat(open_id)`。
  - 取到 UAT → env 注入 `LARKSUITE_CLI_USER_ACCESS_TOKEN` + `DEFAULT_AS=user`。
  - 取不到 → env 注入 `LARKSUITE_CLI_APP_ID/SECRET` + `DEFAULT_AS=bot`。
- **CLI 场景**:无 server 用户身份,直接 bot(或读本机某约定 open_id 的 UAT,实现期定;默认 bot)。

## 组件 5:全量 scope 清单(tools/lark_scopes.py)

从 26 个 skill 文档 grep 提取去重得约 100 个 scope(覆盖 im/docs/drive/sheets/base/wiki/task/calendar/contact/mail/vc/minutes/search/okr/attendance/board 等域)。完整数组写入 `tools/lark_scopes.py` 常量,login 与文档共用同一份。

**已知局限(必须正视)**:
- grep 对跨行/特殊字符有截断(如 `im:feed_group_v` 应为 `im:feed_group_v1:write`、`im:message.p`、`search:abc` 疑似占位)——实现时人工核对修正。
- 清单**不保证穷尽**飞书全部 scope,文档未提及的会漏。
- 这些 scope **须在飞书开放平台后台逐个开通**,代码声明了而后台没开,授权仍失败。
- 兜底:用某功能时若仍缺 scope,靠 exit 3 增量提示补授权(数据流情况 D)。

完整清单见本 spec 附录。

## 错误与确认数据流

- **情况 A — 成功**:返回 `data`,模型正常往下。
- **情况 B — 写操作 exit 10(需确认)**:返回确认提示文本(risk/action/hint),不加 `--yes`。模型向用户复述并停下;用户在**对话流**回"确认",模型再调 `lark` 且 `yes=True`。确认人:CLI 是终端前的你,web 是聊天框里的用户。复用现有对话机制,不动前端。
- **情况 C — 参数错(exit 2)等**:返回 `error` 供模型转述。
- **情况 D — 权限/scope 不足(exit 3)**:返回 `permission_violations`/`console_url`/`hint`。user 身份缺 scope 时,提示用户去重新登录授权(增量补 scope);bot 身份缺权限时,提示去飞书后台开通。

## 测试方案

### 单元测试(无网络,CI 可跑)
`tests/test_lark_cli.py`(mock subprocess):
1. argv 正确拼装、`shell=False`。
2. env 只注入必需项,断言子进程 env **不含** `ANTHROPIC_API_KEY`/`XHS_JWT_SECRET`/`OPENAI_API_KEY`。
3. 黑名单:`auth`/`config` 被拒且不调 subprocess。
4. format:含 `--format` 或元命令时不重复追加;否则补 `--format json`。
5. stdout/stderr 按退出码正确取用。
6. exit 10:`yes=False` 不加 `--yes` 且返回含确认提示;`yes=True` 追加 `--yes`。
7. 身份注入:有 UAT 走 user 并注入 UAT env;无 UAT 走 bot 并注入 APP_ID/SECRET。
8. JSON 解析:成功取 data、失败取 error、超大截断。

`tests/test_uat_store.py`(临时文件):
9. save→get 往返;加密文件非明文(断言密文不含原始 token 子串)。
10. 过期触发刷新路径(mock 刷新请求);刷新失败返回 None。

### 冒烟测试(verify_lark.py,手动,真调 lark-cli)
- bot 身份跑一条无害只读命令,确认换 token + JSON envelope 解析。
- 先断言 `FEISHU_APP_ID/SECRET` 非空。
- 写操作正确性靠 `--dry-run` 手动验。不进 CI。

### 不测
- 不写"真发消息/真写表格"的自动化测试(有副作用、污染真实飞书)。

## 风险与缓解

| 风险 | 缓解 |
|---|---|
| agent 借命令执行越权(读密钥、删文件) | 受限工具只跑 lark-cli;env 不泄敏感变量;`auth`/`config` 拉黑 |
| web 多用户驱动飞书乱写 | 写操作经 exit 10 → 对话流确认,需真人点头 |
| 命令注入 | argv 数组 + `shell=False` |
| UAT 泄漏(可读 cookie/明文落盘) | UAT 永不进 JWT;服务端加密文件 0600;JWT 只含 open_id |
| UAT 过期致命令失败 | refresh_token 自动刷新;失败退回 bot/提示重登 |
| 全量 scope 授权页过长 / 后台未开通 | 用户一次性授权;后台逐个开通;缺失靠 exit 3 增量补 |
| 飞书数据藏注入指令污染模型 | content-safety=warn 留痕 |
| 超大输出触发转存死循环 | 结果截断到远低于 80000 字符阈值 |
| 跨过"不做写回"旧边界 | 记忆与 spec 显式声明;写操作默认需确认 |
| TS/Python 加密格式不互通 | 实现期先验证;不通退"内部端点"方案 a |

## 实现顺序

1. `tools/lark_cli.py` + `tests/test_lark_cli.py`(核心工具与安全红线,bot 身份先跑通)
2. `tools/lark_scopes.py`(人工核对清单)
3. `tools/uat_store.py` + `tests/test_uat_store.py`(UAT 加密存储 + 刷新)
4. web `login`/`callback` 改造(加 scope + 存 UAT);验证 TS↔Python 加密互通
5. `agent.py`/`cli.py` 挂工具 + 身份注入;`prompts.py` 加说明
6. 搬运 26 个 SKILL.md 进 `skills/`
7. `verify_lark.py` 冒烟,手动跑通 bot + user 两条链路

## 实现前的手工前置(用户操作)

1. 飞书开放平台后台:为应用开通组件 5 清单里的 user scope(逐个/批量,部分可能需审核)。
2. 确认飞书后台重定向 URL 仍为 `http://localhost:3000/api/auth/feishu/callback`。
3. 确认 `.env` 的 `FEISHU_APP_ID/SECRET` 有效、`XHS_JWT_SECRET` 两端一致。

## 附录:全量 scope 清单(grep 提取,需人工核对)

> 截断/存疑项已标注,实现期修正后写入 `tools/lark_scopes.py`。

```
attendance:task:readonly
base:form:update
board:whiteboard:node
calendar:calendar.event:create / read / reply / update
calendar:calendar.free_busy:read
calendar:calendar:read / readonly
contact:user.base:readonly
contact:user:search
docs:document.media:upload
docs:permission.member:apply
drive:drive
drive:drive.metadata:readonly
drive:file:download / upload
im:chat.managers:write_only
im:chat.members:read / write_only
im:chat.moderation:read
im:chat.user_setting:read / write
im:chat:create / create_by_user / moderation / operate_as_owner / read / update
im:feed.flag:read / write
im:feed.shortcut:read / write
im:feed_group_v1:write            # grep 截断为 im:feed_group_v,需核对
im:message
im:message.group_msg / group_msg:get_as_user
im:message.p…                     # grep 截断,需核对
im:message.pins:read / write_only
im:message.reactions:read / write_only
im:message.send_as_user
im:message.urgent / urgent:phone / urgent:sms
im:message:readonly / recall / send_as_bot
im:resource
mail:event
mail:user_mailbox.folder:read / write
mail:user_mailbox.mail_contact:read / write
mail:user_mailbox.message.address:read
mail:user_mailbox.message.body:read
mail:user_mailbox.message.subject:read
mail:user_mailbox.message:modify / readonly / send
mail:user_mailbox.rule:read / write
mail:user_mailbox:readonly
minutes:minutes.artifacts:read
minutes:minutes.basic:read
minutes:minutes.media:export
minutes:minutes.search:read
minutes:minutes.transcript:export
minutes:minutes:readonly / update
okr:okr.content:readonly / writeonly
okr:okr.period:readonly
okr:okr.progress.file:upload
okr:okr.progress:delete / readonly / writeonly
okr:okr.setting:read
search:docs:read
search:message
search:abc                        # 疑似文档占位符,需核对剔除
space:document:delete
space:folder:create
task:custom_field:read / write
task:section:read / write
task:task:read / write
task:tasklist:read / write
vc:meeting.meetingevent:read
vc:meeting.search:read
vc:note:read
vc:record:readonly
wiki:member:create / retrieve / update
wiki:node:copy / create / move / read / retrieve
wiki:space:read / retrieve / write_only
```
