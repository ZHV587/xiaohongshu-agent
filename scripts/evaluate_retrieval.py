#!/usr/bin/env python3
"""离线评测统一知识检索，并执行 Qdrant 量化决策门。

示例：
    python scripts/evaluate_retrieval.py evaluate \
      --annotations examples/retrieval_eval/annotations.json \
      --results examples/retrieval_eval/results.json

    python scripts/evaluate_retrieval.py qdrant-gate \
      --input examples/retrieval_eval/qdrant_decision.json
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any

from pydantic import ValidationError

_PROJECT_ROOT = str(Path(__file__).resolve().parent.parent)
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from data_foundation.qdrant_gate import QdrantDecisionInput, decide_qdrant
from data_foundation.retrieval_eval import (
    RetrievalEvaluationDataset,
    RetrievalEvaluationResults,
    evaluate_retrieval_results,
)


def _read_json(path: str) -> Any:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _emit(payload: Any, output: str | None) -> None:
    if hasattr(payload, "model_dump"):
        serializable = payload.model_dump(mode="json")
    else:
        serializable = payload
    rendered = json.dumps(serializable, ensure_ascii=False, indent=2) + "\n"
    if output:
        Path(output).write_text(rendered, encoding="utf-8")
    else:
        sys.stdout.write(rendered)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="统一知识检索离线评测")
    subparsers = parser.add_subparsers(dest="command", required=True)

    evaluate = subparsers.add_parser(
        "evaluate", help="回放 RetrievalService 的 EvidencePackage 结果并计算指标"
    )
    evaluate.add_argument("--annotations", required=True, help="retrieval-eval-v1 标注集")
    evaluate.add_argument(
        "--results", required=True, help="retrieval-eval-results-v1 检索结果"
    )
    evaluate.add_argument("--output", help="报告 JSON 输出路径；省略时写到 stdout")

    gate = subparsers.add_parser(
        "qdrant-gate", help="根据连续 pgvector 窗口与配对实验执行 Qdrant 决策门"
    )
    gate.add_argument("--input", required=True, help="qdrant-decision-v1 输入")
    gate.add_argument("--output", help="决策 JSON 输出路径；省略时写到 stdout")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        if args.command == "evaluate":
            dataset = RetrievalEvaluationDataset.model_validate(
                _read_json(args.annotations)
            )
            results = RetrievalEvaluationResults.model_validate(
                _read_json(args.results)
            )
            report = evaluate_retrieval_results(dataset, results)
            _emit(report, args.output)
            # 版本、ACL、家族重复或引擎契约违规是 CI 硬失败。
            return 3 if report.hard_failure else 0

        decision_input = QdrantDecisionInput.model_validate(_read_json(args.input))
        _emit(decide_qdrant(decision_input), args.output)
        return 0
    except (OSError, json.JSONDecodeError, ValidationError, ValueError) as exc:
        # 不回显原始 JSON；输入可能来自真实租户并含用户文案。
        sys.stderr.write(f"评测输入无效（{type(exc).__name__}）\n")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
