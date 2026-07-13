# 知识检索离线评测与 Qdrant 决策门

## 目标

统一检索上线后，架构选择必须由可重复的证据驱动。本套评测覆盖两件事：

1. 用同一份精确版本标注集回归 `RetrievalService`，计算相关性、权限、版本、去重和降级指标。
2. 在不接入 Qdrant 生产依赖的前提下，判断是否值得启动或采纳 Qdrant 实验。

当前生产检索仍是 PostgreSQL/pgvector + Meilisearch + FalkorDB。评测代码没有 Qdrant
SDK、客户端、连接配置或运行时分支；决策样例通过门槛只用于验证规则，不代表当前生产
数据已经满足换库条件。

## 标注集契约

标注文件使用 `retrieval-eval-v1`，结果文件使用
`retrieval-eval-results-v1`。完整样例位于
`examples/retrieval_eval/annotations.json` 与
`examples/retrieval_eval/results.json`。

每个 case 固定以下上下文：

- `tenant_id`、`actor_open_id`：权限判断必须与真实调用身份一致。
- `query`、`limit`、`filters`：原样传给统一 `RetrievalService.retrieve`。
- `expected_engines`：本次检索应参与的召回引擎，用作降级率分母和引擎契约校验。
- `judgments`：候选快照的完整精确身份清单。

每个 judgment 必须提供：

- `(resource_id, resource_version)`：不可只标资源 ID。
- `relevance_grade`：0-3 级相关性，nDCG 使用分级增益。
- `acl_allowed`：该 actor 是否可读。
- `current_version`：是否为当前知识指针指向的版本。
- `duplicate_family_id`：相同内容家族；同一家族多条返回会计为重复违规。

正相关标注只能指向当前且 ACL 可读的版本。每个 resource 最多有一个当前版本，case 中的
精确身份不可重复。`judgments=[]` 表示知识快照中确实没有候选；有候选但均不相关时，保留
候选并把 `relevance_grade` 全标为 0。两者都是合法的 no-answer case，用来验证智能体能否
在无合格证据时拒答，而不是强行召回一篇不相关文案。

每个结果的 `engines_used ∪ degraded_engines` 必须与 case 的 `expected_engines` 完全相等。
引擎既没有返回结果、也没有显式报告降级属于静默缺失，不能被当成正常的低召回。

## 生成与回放

生产或隔离测试环境可直接调用统一服务生成结果：

```python
from data_foundation.retrieval import build_runtime_retrieval_service
from data_foundation.retrieval_eval import (
    RetrievalEvaluationDataset,
    collect_retrieval_results,
)

dataset = RetrievalEvaluationDataset.model_validate(annotation_payload)
service = build_runtime_retrieval_service(resource_repository)
results = collect_retrieval_results(dataset, service)
```

保存的结果只承载公开 `EvidencePackage`，离线回归不再访问数据库或外部引擎。仓库样例的
tenant、actor、query、title、summary 全是合成占位符，不含生产查询、用户身份或正文。
在 Compose
环境中运行样例：

```bash
docker compose exec -T langgraph python scripts/evaluate_retrieval.py evaluate \
  --annotations examples/retrieval_eval/annotations.json \
  --results examples/retrieval_eval/results.json
```

也可以用 `--output /path/to/report.json` 写入报告。CLI 只输出聚合报告，不输出 case、query、
actor、逐条证据或实验输入指纹；Qdrant 决策输出中的窗口 ID 也受安全字符集限制。校验失败
时只输出异常类型，不回显 JSON 正文。真实标注和原始结果应按租户私有数据保存，禁止提交
仓库或写入日志。

## 指标定义

- `precision_at_k`：前 K 位中首次命中的相关精确版本数除以 K。
- `recall_at_k`：前 K 位命中的相关精确版本数除以全部当前、可读相关版本数。
- `mrr`：首个相关精确版本的倒数排名，先对每个 query 计算再做宏平均。
- `ndcg_at_k`：使用 `2^grade - 1` 增益的分级 nDCG，重复精确身份不重复得分。
- `abstention_precision`：全部拒答中，确实属于 no-answer 的比例。
- `abstention_recall` / `no_answer_accuracy`：全部 no-answer case 中正确拒答的比例。
- `exact_version_violation_rate`：返回不是标注快照当前版本的条目数 / 返回总数。
- `acl_violation_rate`：返回 ACL 不可读或未在完整候选清单中的条目数 / 返回总数。
- `family_duplicate_violation_rate`：同一家族第二条及以后条目数 / 返回总数。
- `degradation_rate`：降级引擎次数 / case 期望引擎次数；另报发生过降级的 query 比例。
- `latency_observation_count`、`latency_observation_coverage`：明确延迟分位数实际覆盖了多少 case。
- `latency_p50_ms`、`latency_p95_ms`、`latency_p99_ms`：仅对带延迟的结果计算，采用 nearest-rank，且必须满足 P50 ≤ P95 ≤ P99。

安全违规统计检索返回的全部条目，相关性指标只取前 K。这样超量返回、旧版本或越权条目
不会因排在 K 之外而逃过审计。no-answer case 不参与 Precision/Recall/MRR/nDCG 宏平均，
避免用人为 0/1 污染相关性；只进入拒答指标。旧版本、ACL、家族重复或引擎契约违规任一
计数非 0 时，报告设置 `hard_failure=true`，CLI 返回退出码 3，可直接阻断 CI。缺少延迟
不会伪造为 0，而是降低覆盖率并令相应分位数仅代表实际观测子集。

## Qdrant 决策门

决策输入使用 `qdrant-decision-v1`。运行方式：

```bash
docker compose exec -T langgraph python scripts/evaluate_retrieval.py qdrant-gate \
  --input examples/retrieval_eval/qdrant_decision.json
```

默认门槛是不可放宽的生产下限，可在决策 JSON 中显式收紧并随评测数据一同评审。规模、
目标质量、连续窗口数、样本量、hard-case 占比、显著性、P95/P99 改善幅度、质量置信度和
回退上限都由 schema 阻止向更宽松方向修改：

- 语料至少 200,000 条。
- 先完成并记录 pgvector 调优；未调优不能用来论证换库。
- 全链路 P95 高于 300ms 或 P99 高于 600ms，同时 Recall@K 低于 0.75 或 nDCG@K 低于 0.70。
- 上述失败连续出现 3 个无间隙、无重叠且等长的半开窗口，每个窗口至少 500 条离线查询和 10,000 条线上查询。
- 连续窗口必须保持同一 `K`、评测数据集、查询集、嵌入配置和检索契约；语料快照可以随知识增长更新。每个窗口及配对实验两侧至少 99% 查询必须有端到端延迟观测，否则 P95/P99 不具代表性。
- 每个窗口及配对实验至少 20% 是 no-answer 或强过滤场景，避免只测容易的正例。
- 任一窗口出现精确版本或 ACL 违规时停止换库判断，先修 PostgreSQL 资格门。
- 每组指标必须声明同一 `K`、评测数据集 SHA-256、查询集 SHA-256、语料快照 SHA-256、嵌入配置 SHA-256 和检索契约版本。指纹只接受 64 位小写十六进制，既保证可比性，也禁止把查询或凭据塞进决策输出。
- Qdrant 必须绑定最后一个 pgvector 窗口的完整基线快照，做同语料、同查询、同配置的全链路配对影子实验；离线至少 500 条查询，线上 shadow 至少 10,000 次。
- P95 至少降低 30%、P99 至少降低 25%，两者 p 值不高于 0.05，并回到线上目标内。
- P95 必须不高于 P99；任何反序分位数直接视为无效输入。
- Recall 和 nDCG 都达到线上目标，点估计不得比同批 pgvector 基线回退超过 1 个百分点；同时使用至少 95% 的逐查询配对置信区间，其差值下界也不得低于 -1 个百分点。
- `no_answer_accuracy`、`abstention_precision`、`abstention_recall` 都必须达到 0.90，且均不得低于同批 pgvector 基线。
- pgvector 窗口、实验基线与 Qdrant 结果的精确版本、ACL、家族重复和引擎契约违规都必须为 0；
  Qdrant 降级率不得回退。
- 建议采用前必须完成 Qdrant 自动备份、恢复演练、监控告警、容量评审、Compose 拓扑验证和回滚演练；六项任一缺失都返回 `QDRANT_OPERATIONS_NOT_READY`。

状态只有三种：

- `keep_pgvector`：连续失败条件未成立，或实验任一质量/显著性/安全门未通过。
- `run_qdrant_experiment`：pgvector 连续失败已成立，但还没有合格配对实验。
- `recommend_qdrant`：全部门槛通过。该状态只是架构评审输入，不会自动改生产配置。

“Qdrant 更流行”或单次压测更快都不能触发引入。先积累连续窗口，再做隔离影子实验，
最后由同一离线标注集验证相关性和安全性。
