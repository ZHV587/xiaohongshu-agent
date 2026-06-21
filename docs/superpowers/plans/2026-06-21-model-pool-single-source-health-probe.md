# 模型池单一数据源 + 定时健康探测 + 三引线热重载

## 根因(已查实)

Phase 2(commit `cd69106`)只造了热重载的"零件"(`reload_from_config`、
`build_pool_from_config`、registry),**从未接任何运行时触发器**。plan 文档
第 995 行白纸黑字承认 "does not reload the LangGraph process"。同时存在两个
与"单一数据源 + 自动探测"冲突的旧物:

- **env 平行配置源**:`agent.py:43-46` 用 `build_pool()`(LazyPool,读 env)
  灌进运行时权威 registry,使 registry 启动装的是 env 池而非 config-center。
- **探测永久缓存**:`_DISCOVER_CACHE` 按 (base_url,key) 命中即返回、永不过期,
  定时探测拿不到新鲜结果。

## 目标架构(单一数据源)

```
ModelRegistry = 运行时唯一模型源(池来自 config-center,经"探测∩白名单按质量序")
   ↑ 三条引线,都调 reload_from_config / build_pool_from_config:
   ├── 启动对齐:lifespan 首次构池(config-center 空→env bootstrap 写入再构)
   ├── 事件驱动:admin 改配置 → verify_gateway → save → reload(0 延迟)
   └── 定时健康:独立后台任务每 300s 探测,按白名单质量序刷新活跃可用池
router(ModelRouterMiddleware):在 registry 活跃池轮换 + 被动冷却 30s(复用)
```

env 不再是平行运行时源,仅作 `create_deep_agent` 装配占位 + config-center 空时
的 bootstrap 种子。

## 已定决策

1. 全挂(白名单模型全探测不可用):**保留旧活跃池 + record_error**,绝不塞
   未探测确认的模型。
2. `_DISCOVER_CACHE`:**加 TTL=250s**(略小于 300s 探测周期),过期重探。
3. `initial_model`:**env 快路径作装配占位**,不进 registry、非配置源,运行时
   被 registry 池覆盖。
4. 健康探测:**独立后台任务**,http_app lifespan 与 supervisor 一道 start/stop,
   不绑 XHS_SYNC_ENABLED。

## 复用判定

- 复用:`ModelCandidate`、`ModelRouterMiddleware`(轮换+冷却)、`ModelRegistry`、
  `build_pool_from_config`(探测∩白名单逻辑)、`StaticModelPoolProvider`(测试夹具)、
  `LazyPool`(降级为仅 build_primary_model 占位用,退出运行时配置链)。
- 接线(Phase 2 半成品):`reload_from_config`、`build_pool_from_config`。
- 重构:`_DISCOVER_CACHE` 加 TTL;`agent.py` 拆 env 灌池;`build_pool_from_config`
  全挂时不再"降级白名单首个"。

## 改动清单(精确到文件/函数)

### 1. `models.py` — 探测缓存加 TTL + 全挂不降级
- `_DISCOVER_CACHE`:值改为 `(timestamp, result)`;新增 `_DISCOVER_TTL=250.0`。
  `discover_models` 命中且未过期才返回缓存,否则重探。新增 `force: bool=False`
  参数(定时探测/verify 传 True 强制重探)。
- `build_pool_from_config`:删除"池为空降级到白名单首个"分支(345-352)。
  池为空直接 `raise RuntimeError`(由调用方按"保留旧池+记错"处理)。
- 保留 `LazyPool`/`build_primary_model`/`StaticModelPoolProvider`(测试与占位用)。

### 2. `config_center.py` — 已加 `latest_config_snapshot()`(只读最新快照,供启动/探测/事件统一读)

### 3. `model_registry.py` — reload 幂等 + 全挂保留旧池
- `reload_from_config`:`build_pool_from_config` 抛错时(全挂)`record_error`
  但**不 replace**(保留旧池),不再 re-raise(由调用方决定是否致命)。改为
  返回 bool(是否成功换池),供探测任务判断。
- 新增 `current_version()` 便捷读当前版本(比对用)。

### 4. 新增 `model_health.py` — 独立健康探测后台任务
- `ModelHealthProbe`:类似 BackgroundServiceSupervisor 的轻量循环,
  `interval_seconds`(默认 300,env `XHS_MODEL_PROBE_INTERVAL_SECONDS`)、
  `start()`/`stop()`、`enabled`(默认 True,env `XHS_MODEL_PROBE_ENABLED`)。
- 每轮:`latest_config_snapshot()` → `registry.reload_from_config(snapshot)`
  (reload 内部走 force 探测)。失败已由 registry record_error,任务不崩。
- `build_model_health_probe(model_registry)` 工厂。

### 5. `agent.py` — 拆 env 灌池
- 删 `pool = build_pool()` 灌 registry 的 `model_registry.replace(env池)`(46 行)。
- registry 创建即空;`initial_model = build_primary_model(build_pool())`
  仅作三处(主/rubric/sub)装配占位。
- registry 由 lifespan/探测/事件填充。

### 6. `models.py::ModelRouterMiddleware` — 空池回退装配占位
- `wrap_model_call`/`awrap_model_call`:registry 池为空时(lifespan 填充前/
  测试态)直接 `handler(request)`(用装配占位 model),不 raise。server 态
  lifespan 接客前已填池,不命中此路径。

### 7. `internal_api.py::internal_config_post` — 事件驱动 reload
- save 前:对 LLM 网关配置 `verify_gateway(base_url, api_key)`(force 探测),
  验证不通过返回 400(配置中心只存验证过能用的)。
- save 后:`from agent import model_registry; model_registry.reload_from_config(
  latest_config_snapshot())`(同进程,0 延迟)。

### 8. `http_app.py::lifespan` — 启动对齐 + 探测任务启停
- 延迟 `from agent import model_registry`(N_WORKERS=1 同进程)。
- 启动对齐:`model_registry.reload_from_config(latest_config_snapshot())`
  (config-center 空则跳过,registry 保留 env 占位池;有则构 config-center 池)。
- `probe = build_model_health_probe(model_registry); await probe.start()`,
  finally `await probe.stop()`。

### 9. 测试(根本性修复,相关测试一并重写)
- `tests/test_models.py`:TTL 缓存行为、force 重探、全挂 raise(不降级)。
- `tests/test_model_registry.py`:全挂保留旧池 + record_error + 返回 False。
- 新增 `tests/test_model_health.py`:探测任务每轮调 reload、失败不崩、enabled 门控。
- `tests/test_internal_api.py`:config-post verify 通过才 save+reload、verify 失败 400。
- `tests/data_foundation/test_http_app.py`:lifespan 启动对齐调 reload、探测任务启停。
- `tests/test_agent_assembly.py`:确认 registry 启动为空(不灌 env)、占位 model 仍可装配。

## 验证(服务器真实环境)
1. 全量 pytest(DB/redis 相关 ERROR 为端口未暴露的环境问题,非回归)。
2. langgraph build + compose up langgraph:
   - 启动后读 registry.status().version == config-center 最新版本(不再是 env-bootstrap)。
   - 模拟 admin 改配置 → 立即(非 30s)读到 version 变化。
   - 等 300s 探测一轮,确认 active_models 反映当前网关可用集。
```
