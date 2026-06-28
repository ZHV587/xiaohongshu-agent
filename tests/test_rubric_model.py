"""RegistryRoutedChatModel:rubric 评分子 agent 吃模型热重载的验证。"""
from __future__ import annotations

import asyncio

from langchain_core.outputs import ChatResult

from rubric_model import RegistryRoutedChatModel


class _FakePool:
    """最小 ModelPoolProvider:get_pool 返回可变列表,模拟热重载替换。"""

    def __init__(self, candidates):
        self._candidates = candidates

    def get_pool(self):
        return list(self._candidates)

    def set(self, candidates):
        self._candidates = candidates


class _Cand:
    def __init__(self, model):
        self.model = model


class _FakeModel:
    """记录被调用的假 BaseChatModel,声明式方法返回带标签的绑定对象。"""

    def __init__(self, tag):
        self.tag = tag

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        return f"gen:{self.tag}"

    async def _agenerate(self, messages, stop=None, run_manager=None, **kwargs):
        return f"agen:{self.tag}"

    def bind_tools(self, tools, **kwargs):
        return _FakeBound(self.tag, [("bind_tools", tools)])

    def with_structured_output(self, schema, **kwargs):
        return _FakeBound(self.tag, [("structured", schema)])


class _FakeBound:
    def __init__(self, tag, ops):
        self.tag = tag
        self.ops = ops

    def bind_tools(self, tools, **kwargs):
        return _FakeBound(self.tag, [*self.ops, ("bind_tools", tools)])

    def with_structured_output(self, schema, **kwargs):
        return _FakeBound(self.tag, [*self.ops, ("structured", schema)])

    def invoke(self, input, config=None, **kwargs):
        return {"tag": self.tag, "ops": self.ops, "input": input}

    async def ainvoke(self, input, config=None, **kwargs):
        return {"tag": self.tag, "ops": self.ops, "input": input}


def _routed(pool, placeholder):
    # registry 与 placeholder 是 PrivateAttr,pydantic 下不可直接传位置参,经 __init__ 注入。
    return RegistryRoutedChatModel(registry=pool, placeholder=placeholder)


def test_generate_delegates_to_strongest():
    pool = _FakePool([_Cand(_FakeModel("strong")), _Cand(_FakeModel("weak"))])
    m = _routed(pool, _FakeModel("placeholder"))
    assert m._generate([]) == "gen:strong"


def test_generate_falls_back_to_placeholder_when_empty():
    pool = _FakePool([])
    m = _routed(pool, _FakeModel("placeholder"))
    assert m._generate([]) == "gen:placeholder"


def test_hot_reload_switches_model_between_calls():
    """registry 池被热重载替换后,下次评分即用新最强模型(不缓存旧实例)。"""
    pool = _FakePool([_Cand(_FakeModel("opus"))])
    m = _routed(pool, _FakeModel("placeholder"))
    assert m._generate([]) == "gen:opus"

    pool.set([_Cand(_FakeModel("sonnet"))])  # admin 改白名单/探测刷新
    assert m._generate([]) == "gen:sonnet"


def test_agenerate_delegates():
    pool = _FakePool([_Cand(_FakeModel("strong"))])
    m = _routed(pool, _FakeModel("placeholder"))
    assert asyncio.run(m._agenerate([])) == "agen:strong"


def test_structured_output_queues_and_replays_on_current_model():
    """with_structured_output 不绑死构造时的模型:invoke 时对当轮最强模型重放。"""
    pool = _FakePool([_Cand(_FakeModel("opus"))])
    m = _routed(pool, _FakeModel("placeholder"))
    bound = m.with_structured_output(dict).bind_tools(["t1"])

    out1 = bound.invoke("x")
    assert out1["tag"] == "opus"
    assert out1["ops"] == [("structured", dict), ("bind_tools", ["t1"])]

    pool.set([_Cand(_FakeModel("sonnet"))])  # 热重载后同一 bound 重放到新模型
    out2 = bound.invoke("y")
    assert out2["tag"] == "sonnet"
    assert out2["ops"] == [("structured", dict), ("bind_tools", ["t1"])]


def test_bound_ainvoke_replays():
    pool = _FakePool([_Cand(_FakeModel("opus"))])
    m = _routed(pool, _FakeModel("placeholder"))
    bound = m.with_structured_output(dict)
    out = asyncio.run(bound.ainvoke("z"))
    assert out["tag"] == "opus"
    assert out["ops"] == [("structured", dict)]


def test_is_base_chat_model_instance():
    """resolve_model 靠 isinstance(model, BaseChatModel) 原样返回——必须真子类。"""
    from langchain_core.language_models import BaseChatModel
    m = _routed(_FakePool([]), _FakeModel("p"))
    assert isinstance(m, BaseChatModel)


def test_grader_uses_configured_rubric_model_when_in_pool(monkeypatch):
    """配置 XHS_RUBRIC_MODEL 且池中有该 model_id → 分层 grader 用它(不烧最强模型)。"""
    strong = _Cand(_FakeModel("strong")); strong.model_id = "strong-id"
    weak = _Cand(_FakeModel("weak")); weak.model_id = "weak-id"
    m = _routed(_FakePool([strong, weak]), _FakeModel("placeholder"))
    monkeypatch.setenv("XHS_RUBRIC_MODEL", "weak-id")
    assert m._generate([]) == "gen:weak"


def test_grader_falls_back_to_strongest_when_rubric_model_unset_or_absent(monkeypatch):
    """XHS_RUBRIC_MODEL 未配置或不在池中 → 回退池首(最强),不破坏既有行为。"""
    strong = _Cand(_FakeModel("strong")); strong.model_id = "strong-id"
    m = _routed(_FakePool([strong]), _FakeModel("placeholder"))
    monkeypatch.delenv("XHS_RUBRIC_MODEL", raising=False)
    assert m._generate([]) == "gen:strong"
    monkeypatch.setenv("XHS_RUBRIC_MODEL", "nonexistent-id")
    assert m._generate([]) == "gen:strong"
