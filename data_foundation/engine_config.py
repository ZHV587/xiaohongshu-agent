from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Literal, Mapping


@dataclass(frozen=True)
class MeiliConfig:
    state: Literal["enabled", "disabled"]
    url: str
    api_key: str


@dataclass(frozen=True)
class FalkorConfig:
    state: Literal["enabled", "disabled"]
    url: str
    graph_name: str


def meili_config(values: Mapping[str, str]) -> MeiliConfig:
    url = str(values.get("XHS_MEILI_URL", "") or "").strip()
    api_key = str(values.get("XHS_MEILI_KEY", "") or "").strip()
    state = "enabled" if url and api_key else "disabled"
    return MeiliConfig(state=state, url=url, api_key=api_key)


def falkor_config(values: Mapping[str, str]) -> FalkorConfig:
    url = str(values.get("XHS_FALKOR_URL", "") or "").strip()
    graph_name = str(values.get("XHS_FALKOR_GRAPH", "") or "").strip() or "xhs"
    state = "enabled" if url else "disabled"
    return FalkorConfig(state=state, url=url, graph_name=graph_name)


def meili_config_from_env() -> MeiliConfig:
    return meili_config({k: os.environ.get(k, "") for k in ("XHS_MEILI_URL", "XHS_MEILI_KEY")})


def falkor_config_from_env() -> FalkorConfig:
    return falkor_config({k: os.environ.get(k, "") for k in ("XHS_FALKOR_URL", "XHS_FALKOR_GRAPH")})
