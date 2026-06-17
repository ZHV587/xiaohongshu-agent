# lark-cli 集成设计

日期:2026-06-17
状态:待实现
作者:Kiro + 用户

## 背景与目标

小红书文案智能体当前与飞书的唯一连接是 `tools/feishu_bitable.py` 的 `read_xhs_data` —— 用 `app_id/secret` 换 `tenant_access_token`,**只读**多维表格。这导致 agent 无法执行任何飞书写操作(发消息、写文档、写回多维表格等),也无法触达多维表格之外的飞书业务域。

[lark-cli](https://github.com/larksuite/cli) 是飞书官方 CLI,覆盖 18 个业务域、200+ 命令,**为 Agent 原生设计**(统一 JSON envelope、清晰退出码、可纯环境变量驱动)。本设计将其接入智能体,补齐飞书操作能力。

**核心洞察(为什么 Claude Code 能直接用而当前 agent 不能)**:Claude Code / Codex 能"直接用" lark-cli,靠的是两个通用能力 —— ① 能读文件的工具(Read)② 能跑命令的工具(Bash)—— 加上 Agent Skills 加载器把 lark-cli 的 SKILL.md 说明书装进来。当前 agent 缺的不是"对 lark-cli 的特殊适配",而是缺一个"能跑命令的工具"。deepagents 的 `read_file`、`SkillsMiddleware` 已具备,只需补上受限的命令执行工具。

### 边界变更声明

本设计**正式废除**项目此前的边界约定「明确不做:配图、自动发布、飞书写回」。接入 lark-cli 写能力即跨过这条线。为控制风险,所有飞书**写操作默认需要真人确认**(见"错误与确认数据流")。

## 范围

**接入点**:`cli.py`(单机终端)与 `agent.py`(LangGraph server + web)两处,统一同一套受限工具。

**飞书身份**:bot 应用身份(`tenant_access_token`),复用 `.env` 现有的 `FEISHU_APP_ID` / `FEISHU_APP_SECRET`。bot 是应用级单一身份,web 多用户共用,天然规避"用户身份串号"问题,无需用户级 OAuth。

**不在本设计范围**:
- 不改现有 backend(CompositeBackend / FilesystemBackend 那套照旧)。
- 不改 auth.py、子智能体、前端契约、前端 UI。
- 不引入 deepagents 的 `LocalShellBackend`(裸 shell)—— 多租户 web 场景下官方明确禁用,且裸 shell 能读 `.env`、`rm -rf`,风险过大。
- 不引入 HITL 中断审批 UI —— 确认走对话流,不动前端。

## 架构

复刻 Claude Code 的"读说明书 + 跑命令"双能力,三个部件:

```
①  skills/lark-*/SKILL.md  (26 个官方说明书,搬进来)
        │  现有 SkillsMiddleware 自动加载摘要进 system prompt(渐进式披露)
        ▼
②  模型识别任务 → 用现有 read_file 读对应 SKILL.md 全文(临场学命令)
        │
        ▼
③  模型调新增 lark 工具执行 → tools/lark_cli.py(受限命令执行)
```

- **部件①(纯文件搬运)**:把 lark-cli 官方 26 个 skill 目录全量搬进 `skills/`。现有 skills 加载逻辑(CLI 与 server 两套 backend 都从 `skills/` 读)原样生效,**backend 一行不改**。
- **部件②(零新增)**:完全复用现有 `read_file` 工具。
- **部件③(唯一新代码)**:`tools/lark_cli.py`,一个受限的单一通用工具。

**文件变更清单**:
- 新增:`tools/lark_cli.py`、`tests/test_lark_cli.py`、`verify_lark.py`
- 新增:`skills/lark-*/`(26 个官方 SKILL.md 目录,搬运)
- 修改:`agent.py`(挂载 lark 工具,+1 import +1 列表项)
- 修改:`cli.py`(挂载 lark 工具,+1 import +1 列表项;render 加 lark 工具的友好提示)
- 修改:`prompts.py`(加一小段 lark 工具使用说明)
- 修改:`.env.example`(说明 lark 复用 FEISHU_APP_ID/SECRET,无需新增凭证)

## 组件设计:lark 工具(tools/lark_cli.py)

### 工具签名

```python
@tool
def lark(args: list[str], yes: bool = False) -> str:
    """执行 lark-cli 飞书命令。

    args: lark-cli 参数数组,如 ["im","+messages-send","--chat-id","oc_x","--text","hi"]。
          不要包含 "lark-cli" 本身,也不要加 --format(工具自动补 --format json)。
    yes:  仅当某次调用返回"需要确认"且用户已明确同意时,才传 True 重试同一命令。
    """
```

单一通用工具(粒度选择:不为 200+ 命令各包一个工具)。模型通过读 SKILL.md + 跑 `lark schema` / `--help` 自查具体命令怎么拼。

### 内部职责(每条对应一条安全红线)

1. **argv 数组直传,绝不拼 shell 字符串**:`subprocess.run(["lark-cli", *args, ...], shell=False)`。模型生成的参数当数据,不当 shell 语法,堵命令注入。
2. **强制注入 bot 身份环境变量,且不继承父进程全部环境**:`env` 只给必需项 —— `LARKSUITE_CLI_APP_ID`(=FEISHU_APP_ID)、`LARKSUITE_CLI_APP_SECRET`(=FEISHU_APP_SECRET)、`LARKSUITE_CLI_DEFAULT_AS=bot`、`LARKSUITE_CLI_CONTENT_SAFETY_MODE=warn`,以及 `PATH`(供找到 lark-cli)。**显式不传** `ANTHROPIC_API_KEY` / `XHS_JWT_SECRET` / `OPENAI_API_KEY` 等敏感变量到子进程。
3. **强制 `--format json`**:自动补到 args,保证拿到结构化 envelope 而非给人看的表格。
4. **黑名单拦截**:采用"黑名单 + 其余放行"而非白名单 —— `args[0]`(服务域)落在黑名单 `{auth, config}` 时直接拒绝、不执行(防 agent 改登录态、碰凭证 —— bot 身份由环境变量固定),其余服务域一律放行。不用白名单是因为 lark-cli 有 18 个业务域、200+ 命令,正向枚举易漏且维护成本高。**写操作不靠自维护清单拦截,改由 exit 10 闸门处理(见下)。**
5. **exit 10 特殊处理(关键红线)**:退出码 10 表示高风险写操作待确认。
   - 当 `yes=False`(默认):**不**追加 `--yes`,把 lark-cli 返回的 `risk` / `action` / `hint` 包装成确认提示文本返回给模型,引导其向用户复述并等待确认。
   - 当 `yes=True`(代表人已确认):在 args 追加 `--yes` 重新执行。
6. **结果裁剪**:解析 JSON envelope。`ok:true` 返回 `data`;`ok:false` 返回 `error.type` / `message` / `hint`(权限错误带 `console_url`)。超大输出截断到安全长度(远低于 deepagents 转存阈值 `TOOL_RESULT_TOKEN_LIMIT*4=80000 字符`,避免触发转存死循环 —— 此前 read_xhs_data 已踩过此坑)。

### 已定默认值

- **超时**:60 秒(对齐现有模型调用 timeout 风格)。
- **content-safety**:`warn`(飞书数据喂回模型是注入靶场;warn 留痕但不阻断;block 会 exit 6 打断流程)。

## 错误与确认数据流

**情况 A — 读操作 / 写操作成功**:返回 `data`,模型正常往下走。

**情况 B — 写操作撞 exit 10(需确认)**:`lark` 工具返回确认提示文本(含 risk/action/hint),不加 `--yes`。模型向用户复述待确认操作并停下。用户在**对话流**里回"确认",模型再次调 `lark` 且 `yes=True` 执行。

- 确认的"人":CLI 场景是终端前的你;web 场景是聊天框里的用户。两者都走**对话流**,复用现有对话机制,**不动前端、不走 HITL 中断**。

**情况 C — 其他错误**:权限不足(exit 3,带 `console_url`/`hint` 引导去飞书后台开 scope)、参数错(exit 2)等,返回 `error` 字段供模型转述给用户。

## Skills 接入(部件①)

把 lark-cli 官方 26 个 skill 目录全量搬进项目 `skills/`(与现有 `skills/<自有 skill>/` 并列)。现有 `SkillsMiddleware` 启动时扫描 `skills/`,把每个 SKILL.md 的 name+description 注入 system prompt,模型按需 `read_file` 读全文。

- 搬运来源:lark-cli 仓库 `skills/` 目录(`lark-shared`、`lark-im`、`lark-base`、`lark-doc` 等 26 个)。
- `lark-shared` 是基础 skill,其余 skill 约定"使用前先读 lark-shared"(认证/安全/exit-10 协议)。搬运时保留 references/ 子目录。
- 不破坏现有自有 skills 的加载。

## prompts.py 改动

在 `MAIN_SYSTEM_PROMPT` 增加一小段:告知 agent 现在具备飞书操作能力(通过 `lark` 工具),何时用、读 `lark-shared`/对应 skill 学命令、写操作需经用户确认(exit 10 → 复述 → yes=True)。措辞保持精简,**不破坏现有 xhs_topics / xhs_copy 前后端契约**。

## 测试方案

### 单元测试(tests/test_lark_cli.py,mock subprocess,无网络、CI 可跑)

1. argv 正确拼装(`["lark-cli", *args, "--format", "json"]`),`shell=False`。
2. env 只注入必需项,断言子进程 env **不含** `ANTHROPIC_API_KEY` / `XHS_JWT_SECRET` / `OPENAI_API_KEY`。
3. 白名单:`auth` / `config` 被拒且不调用 subprocess;读类服务放行。
4. exit 10:`yes=False` 不加 `--yes` 且返回含确认提示;`yes=True` 追加 `--yes`。
5. JSON 解析:成功取 `data`、失败取 `error`、超大输出截断。

### 冒烟测试(verify_lark.py,手动跑,真调 lark-cli)

- 跑一条无害**只读**命令,确认 bot 身份能换 token、JSON envelope 能解析。
- 写操作正确性靠 `--dry-run` 手动验,不写有副作用的自动化测试。
- 不进 CI(依赖网络 + 真凭证)。

### 不测

- 不写"真发飞书消息/真写表格"的自动化测试(有副作用、污染真实飞书)。

## 风险与缓解

| 风险 | 缓解 |
|---|---|
| agent 借命令执行越权(读密钥、删文件) | 受限工具只跑 lark-cli;env 不泄敏感变量;`auth`/`config` 拉黑 |
| web 多用户驱动公共 bot 乱写飞书 | 所有写操作经 exit 10 → 对话流确认,需真人点头 |
| 命令注入 | argv 数组 + `shell=False`,参数当数据 |
| 飞书数据藏注入指令污染模型 | content-safety=warn 留痕 |
| 超大输出触发 deepagents 转存死循环 | 结果截断到远低于 80000 字符阈值 |
| 跨过"不做写回"旧边界 | 已在记忆与本 spec 显式声明;写操作默认需确认 |

## 实现顺序

1. `tools/lark_cli.py`(核心工具)
2. `tests/test_lark_cli.py`(单元测试,验证安全红线)
3. 搬运 26 个 SKILL.md 进 `skills/`
4. `agent.py` / `cli.py` 挂载工具 + `prompts.py` 加说明
5. `verify_lark.py`(冒烟,手动跑确认链路)
