"""registry 驱动的 BaseChatModel 子类:让 rubric 评分子 agent 也吃模型热重载。

背景:deepagents 的 RubricMiddleware 在内部用 create_agent(model=resolve_model(self._model),
response_format=GraderResponse) 构造一个 grader 子图,且 self._grader 一次构建后缓存、
永不重建,完全不经过我们的 ModelRouterMiddleware。所以 grader 用的 model 实例就是构造时
传进去那个——若传 env 占位实例,admin 改了 config-center 白名单后,主/子 agent 立刻切到新
最强模型,唯独 rubric 评分还钉在旧模型上。这是"单一数据源"在运行时链里的唯一破口。

官方扩展点:resolve_model 对 BaseChatModel 实例**原样返回**(deepagents/_models.py),
文档明示接受 "a pre-configured BaseChatModel subclass instance"。langchain 自己的
_ConfigurableModel(init_chat_model(configurable_fields=...) 的产物)正是用这个扩展点做
"运行时换模型":把 bind_tools/with_structured_output 这类声明式方法排队,每次解析出当轮真实
model 后重放(langchain/chat_models/base.py 的 _queued_declarative_operations / _model)。

本类照该范式做一个 registry 驱动版:解析时取 registry 当前池最强候选(白名单序=质量序),
registry 空(填充前/测试态/全挂保留旧池)时回退到 import-time 占位实例。这样 rubric 评分
随 config-center 热重载即时切换到当前最强模型,env 在 rubric 路径退为纯占位。
"""
from __future__ import annotations

from typing import Any

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import BaseMessage
from langchain_core.outputs import ChatResult
from langchain_core.runnables import Runnable, RunnableConfig
from pydantic import PrivateAttr

from models import ModelPoolProvider


class RegistryRoutedChatModel(BaseChatModel):
    """委托给 registry 当前最强候选的 BaseChatModel。registry 空则回退占位。

    满足 resolve_model 的 isinstance(model, BaseChatModel) 检查(原样返回),
    故可直接传给 RubricMiddleware(model=...)。_generate/_agenerate 透明委托;
    bind_tools/with_structured_output 不立即作用于某个具体 model,而是排队,
    每次调用时对当轮解析出的真实 model 重放——完全复刻 _ConfigurableModel 的设计。
    """

    _registry: ModelPoolProvider = PrivateAttr()
    _placeholder: BaseChatModel = PrivateAttr()

    def __init__(self, registry: ModelPoolProvider, placeholder: BaseChatModel, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._registry = registry
        self._placeholder = placeholder

    def _resolve(self) -> BaseChatModel:
        """取 registry 当前池最强(质量序首个);空池回退到 import-time 占位。"""
        pool = self._registry.get_pool()
        return pool[0].model if pool else self._placeholder

    @property
    def _llm_type(self) -> str:
        return "registry-routed"

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: Any = None,
        **kwargs: Any,
    ) -> ChatResult:
        return self._resolve()._generate(messages, stop=stop, run_manager=run_manager, **kwargs)

    async def _agenerate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: Any = None,
        **kwargs: Any,
    ) -> ChatResult:
        return await self._resolve()._agenerate(messages, stop=stop, run_manager=run_manager, **kwargs)

    def bind_tools(self, tools: Any, **kwargs: Any) -> Runnable:
        return _RegistryRoutedBound(self, [("bind_tools", (tools,), kwargs)])

    def with_structured_output(self, schema: Any, **kwargs: Any) -> Runnable:
        return _RegistryRoutedBound(self, [("with_structured_output", (schema,), kwargs)])


class _RegistryRoutedBound(Runnable):
    """RegistryRoutedChatModel 的声明式操作队列重放器(复刻 _ConfigurableModel 行为)。

    bind_tools/with_structured_output 不能在解析前作用于具体 model(那会绑死一个模型),
    故记录 (方法名, args, kwargs) 到队列;每次 invoke/ainvoke 时解析当轮真实 model 并按序
    重放队列,再 invoke。链式调用继续追加队列。这样热重载替换 registry 池后,下次评分即生效。
    """

    def __init__(self, parent: RegistryRoutedChatModel, queue: list[tuple[str, tuple, dict]]) -> None:
        self._parent = parent
        self._queue = queue

    def _resolved(self) -> Runnable:
        model: Runnable = self._parent._resolve()
        for method, args, kwargs in self._queue:
            model = getattr(model, method)(*args, **kwargs)
        return model

    def bind_tools(self, tools: Any, **kwargs: Any) -> "_RegistryRoutedBound":
        return _RegistryRoutedBound(self._parent, [*self._queue, ("bind_tools", (tools,), kwargs)])

    def with_structured_output(self, schema: Any, **kwargs: Any) -> "_RegistryRoutedBound":
        return _RegistryRoutedBound(self._parent, [*self._queue, ("with_structured_output", (schema,), kwargs)])

    def invoke(self, input: Any, config: RunnableConfig | None = None, **kwargs: Any) -> Any:
        return self._resolved().invoke(input, config, **kwargs)

    async def ainvoke(self, input: Any, config: RunnableConfig | None = None, **kwargs: Any) -> Any:
        return await self._resolved().ainvoke(input, config, **kwargs)
