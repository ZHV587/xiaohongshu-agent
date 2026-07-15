"""主智能体共享 middleware。

agent 节点级的重试兜底:模型层(init_chat_model 的 max_retries)在 SDK 内部
重试单次 HTTP 调用,这里在 langgraph 节点层再兜一道——SDK 重试耗尽后整轮
model call 仍可重来,对中转(43.255.157.166)偶发 502 多一层保护。

注意:本 middleware 只作用于挂载它的那个 agent 的模型调用。子智能体(task)
持有自己的模型实例,不在此保护范围内 —— 故 subagents.py 的 init_chat_model
仍需自带 max_retries,不可删。

**渠道无关**:项目主/子智能体可能跑 Claude、GPT 或任意 OpenAI 兼容中转,
故不绑定某家 SDK 的异常类,改用鸭子类型谓词按语义判定是否该重试:
看 HTTP 状态码(各家 APIStatusError 都暴露 .status_code)+ httpx 传输层异常
(连接/超时各家底层都走 httpx)。换渠道无需改这里。
"""
import httpx
from langchain.agents.middleware import AgentMiddleware, AgentState, ModelRetryMiddleware
from typing_extensions import NotRequired

# 服务端/限流/瞬时类状态码 —— 重试有意义。
# 408 请求超时 / 409 冲突 / 425 too early / 429 限流 / 5xx 服务端(含中转 502)。
# 刻意不含 400/401/403/404/422 —— 参数、鉴权、内容策略类,重试也不会变好。
_RETRYABLE_STATUS = {408, 409, 425, 429, 500, 502, 503, 504}


def is_retryable_error(exc: Exception) -> bool:
    """渠道无关地判断异常是否值得**对同一端点重试**(ModelRetryMiddleware 用)。"""
    # 各家 SDK 的 APIStatusError 都把 HTTP 状态码挂在 .status_code 上。
    status = getattr(exc, "status_code", None)
    if isinstance(status, int) and status in _RETRYABLE_STATUS:
        return True
    # 连接断开 / 各类超时 —— anthropic/openai 底层都用 httpx,统一兜住。
    if isinstance(exc, httpx.TransportError):
        return True
    # SDK 自己包装的连接/超时异常(如 APIConnectionError/APITimeoutError),
    # 不一定继承 httpx,按类名兜底。
    name = type(exc).__name__.lower()
    if "connection" in name or "timeout" in name:
        return True
    # 结构化输出解析失败(StructuredOutputValidationError):模型确实回了(非 HTTP 错),
    # 但原生结构化 payload 偶发为空/非 JSON(opus+扩展思考+中转网关组合下观察到)。
    # 一次解析失败就挂掉整轮(如 copywriting-coprocessor 跑 11 分钟后白费)太脆,重试一次大概率成功。
    # 渠道无关(类名判定);只匹配结构化输出校验失败,不波及普通 Pydantic/业务校验。
    return "structuredoutputvalidation" in name


# 鉴权类状态码:401 未授权 / 403 禁止。对**单个端点**重试无意义(同 key 再试还是 401),
# 但鉴权是**按网关**的 —— gateway_1 的 key 失效/过期不代表 gateway_2 也失效。
_GATEWAY_AUTH_STATUS = {401, 403}


def is_gateway_failover_error(exc: Exception) -> bool:
    """ModelRouterMiddleware 用:判断是否该**切到下一个网关候选**。

    比 is_retryable_error 多含 401/403 —— 因为换网关换的是 base_url+key,鉴权失败在
    新网关可能恢复。仍排除 400/404/422(请求级错误,换网关也一样错,不 failover)。
    """
    if is_retryable_error(exc):
        return True
    status = getattr(exc, "status_code", None)
    return isinstance(status, int) and status in _GATEWAY_AUTH_STATUS


def build_retry_middleware() -> ModelRetryMiddleware:
    """构造 agent 节点级重试 middleware(指数退避 + jitter,渠道无关)。"""
    return ModelRetryMiddleware(
        max_retries=2,
        retry_on=is_retryable_error,
        backoff_factor=2.0,
        initial_delay=1.0,
        max_delay=30.0,
        jitter=True,
        # 重试耗尽仍失败则抛错,交给上层(CLI try/except、前端错误提示)处理,
        # 而非吞掉错误塞条假消息继续('continue')。
        on_failure="error",
    )


class FrontendDirectState(AgentState):
    """扩展 agent state:承载前端在用户操作时经 submit 直传的**权威结构化数据**。

    这些字段由前端在用户点选卡片时经 `stream.submit({...})`(官方 state-update 通道)直传,
    工具用 `InjectedState("字段名")` 注入,**完全绕过对话文本/LLM 转写**,杜绝静默丢字段
    (尤其 resource_id 这类依据)。

    - `selected_notes`:用户在搜索卡片勾选要采纳的线上笔记的权威副本。
      `adopt_online_notes` 经 `InjectedState("selected_notes")` 注入它落库。
    - `selected_topic`:用户点选的那张选题卡的权威数据 `{topic, evidence}`,evidence 即卡片
      上展示的库内依据(每条带精确 resource_id + resource_version)。`save_generated_topic` 经 `InjectedState("selected_topic")`
      注入它落库 —— 即「卡片展示的依据 = 落库的依据」,evidence 不再由 LLM 重填。
    - `selected_reference`:用户在素材卡点「仿写」时,该范本的权威标识 `{resource_id?, resource_version?, note?}`。
      本地已入库素材必须同时带 `resource_id` 与 `resource_version`;线上未入库笔记只带 `note`
      (主控须先 `adopt_online_notes` 收录并取得精确身份再仿)。委派 `imitation-writer` 时
      把范本精确身份放进 brief,子代理按不可变版本精读范本原文。
    """

    selected_notes: NotRequired[list[dict]]
    selected_topic: NotRequired[dict]
    selected_reference: NotRequired[dict]
    selected_user_skill: NotRequired[dict | None]
    current_account_id: NotRequired[str | None]
    current_niche: NotRequired[str | None]


class FrontendStateMiddleware(AgentMiddleware):
    """向 agent state 注册前端直传字段(官方:经 middleware 扩 state_schema)。

    只声明 state 形状,不拦截任何节点;让 deepagents 把这些字段并入 graph state,
    从而工具能用 `InjectedState(...)` 拿到前端直传的权威数据(采纳笔记 / 选定选题)。
    """

    state_schema = FrontendDirectState
