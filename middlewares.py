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
from langchain.agents.middleware import ModelRetryMiddleware

# 服务端/限流/瞬时类状态码 —— 重试有意义。
# 408 请求超时 / 409 冲突 / 425 too early / 429 限流 / 5xx 服务端(含中转 502)。
# 刻意不含 400/401/403/404/422 —— 参数、鉴权、内容策略类,重试也不会变好。
_RETRYABLE_STATUS = {408, 409, 425, 429, 500, 502, 503, 504}


def is_retryable_error(exc: Exception) -> bool:
    """渠道无关地判断异常是否值得重试。"""
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
    return "connection" in name or "timeout" in name


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
