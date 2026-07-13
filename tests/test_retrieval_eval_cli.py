"""离线评测 CLI 只暴露聚合结果，并以退出码执行安全硬门。"""
from __future__ import annotations

import json
from pathlib import Path

from scripts.evaluate_retrieval import main


ROOT = Path(__file__).resolve().parents[1]


def test_cli_output_is_aggregate_and_contains_no_case_or_evidence(capsys) -> None:
    example_dir = ROOT / "examples" / "retrieval_eval"
    code = main(
        [
            "evaluate",
            "--annotations",
            str(example_dir / "annotations.json"),
            "--results",
            str(example_dir / "results.json"),
        ]
    )
    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert code == 0
    assert payload["hard_failure"] is False
    assert "queries" not in payload
    assert "observations" not in payload
    assert "case_id" not in captured.out
    assert "synthetic_query" not in captured.out
    assert "synthetic-actor" not in captured.out
    assert "synthetic-title" not in captured.out


def test_cli_returns_three_for_any_safety_hard_failure(tmp_path, capsys) -> None:
    example_dir = ROOT / "examples" / "retrieval_eval"
    payload = json.loads((example_dir / "results.json").read_text(encoding="utf-8"))
    payload["observations"][0]["result"]["evidence"][0]["resource_version"] = 99
    results_path = tmp_path / "unsafe-results.json"
    results_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    code = main(
        [
            "evaluate",
            "--annotations",
            str(example_dir / "annotations.json"),
            "--results",
            str(results_path),
        ]
    )
    report = json.loads(capsys.readouterr().out)
    assert code == 3
    assert report["hard_failure"] is True
    assert "EXACT_VERSION_VIOLATION" in report["hard_failure_reasons"]
    assert "ACL_VIOLATION" in report["hard_failure_reasons"]


def test_qdrant_cli_outputs_decision_only_without_input_fingerprints(capsys) -> None:
    input_path = (
        ROOT / "examples" / "retrieval_eval" / "qdrant_decision.json"
    )
    code = main(["qdrant-gate", "--input", str(input_path)])
    captured = capsys.readouterr()
    payload = json.loads(captured.out)

    assert code == 0
    assert payload["status"] == "recommend_qdrant"
    assert "dataset_fingerprint" not in captured.out
    assert "query_set_fingerprint" not in captured.out
    assert "corpus_snapshot_fingerprint" not in captured.out
    assert "embedding_profile_fingerprint" not in captured.out
    assert "qdrant-shadow-2026-07" not in captured.out
