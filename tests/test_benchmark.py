from pathlib import Path

import pytest

from case_memory_eval.benchmark import (
    EvaluationMode,
    RegressionThresholds,
    compare_reports,
    run_benchmark,
)
from case_memory_eval.contracts import FailureLabel
from case_memory_eval.corpus import build_corpus
from case_memory_eval.memory import ReviewedCaseMemory


def test_golden_benchmark_retains_confusion_components_and_metrics() -> None:
    report = run_benchmark(build_corpus())
    assert report.severe_recall == 1.0
    assert report.exact_match_accuracy == 1.0
    assert report.reviewer_agreement == 1.0
    assert report.abstention_rate == 0.0
    assert report.calibration_error < 0.02
    assert len(report.class_metrics) == 4
    for metric in report.class_metrics:
        assert metric.true_positive == 8
        assert metric.false_positive == 0
        assert metric.false_negative == 0
        assert metric.true_negative == 28
        assert metric.f1 == 1.0


def test_retrieval_ablation_is_reproducible_and_changes_influence(tmp_path: Path) -> None:
    corpus = build_corpus()
    with ReviewedCaseMemory(tmp_path / "memory.duckdb") as memory:
        for case in corpus.cases[:18]:
            memory.add(case)
        baseline = run_benchmark(corpus, mode=EvaluationMode.RETRIEVAL_GROUNDED, memory=memory)
        removed = baseline.outcomes[18].precedent_ids[0]
        first = run_benchmark(
            corpus,
            mode=EvaluationMode.RETRIEVAL_GROUNDED,
            memory=memory,
            excluded_precedents=frozenset({removed}),
        )
        second = run_benchmark(
            corpus,
            mode=EvaluationMode.RETRIEVAL_GROUNDED,
            memory=memory,
            excluded_precedents=frozenset({removed}),
        )
    assert first == second
    assert first.report_id != baseline.report_id
    assert removed not in first.outcomes[18].precedent_ids


def test_retrieval_mode_requires_memory() -> None:
    with pytest.raises(ValueError, match="requires reviewed-case memory"):
        run_benchmark(build_corpus(), mode=EvaluationMode.RETRIEVAL_GROUNDED)


def test_severe_regression_fails_even_if_aggregate_score_looks_high() -> None:
    baseline = run_benchmark(build_corpus())
    outcomes = list(baseline.outcomes)
    target = next(index for index, item in enumerate(outcomes) if item.expected)
    outcomes[target] = outcomes[target].model_copy(update={"predicted": (), "confidences": ()})
    current = baseline.model_copy(
        update={
            "severe_recall": 0.99,
            "exact_match_accuracy": 1.0,
            "outcomes": tuple(outcomes),
        }
    )
    decision = compare_reports(baseline, current)
    assert not decision.passed
    assert "severe recall regressed" in decision.violations


def test_calibration_and_class_regressions_are_gated() -> None:
    baseline = run_benchmark(build_corpus())
    metrics = list(baseline.class_metrics)
    metrics[0] = metrics[0].model_copy(update={"f1": 0.5})
    current = baseline.model_copy(
        update={"class_metrics": tuple(metrics), "calibration_error": 0.4}
    )
    decision = compare_reports(baseline, current)
    assert not decision.passed
    assert any("F1 regressed" in item for item in decision.violations)
    assert "calibration error exceeds the configured maximum" in decision.violations


def test_new_failure_modes_require_human_acceptance() -> None:
    report = run_benchmark(build_corpus())
    approved = frozenset(set(FailureLabel) - {FailureLabel.UNSAFE_CERTAINTY})
    decision = compare_reports(
        report, report, RegressionThresholds(approved_failure_modes=approved)
    )
    assert not decision.passed
    assert "unsafe_certainty" in decision.violations[-1]


def test_different_golden_sets_are_not_compared() -> None:
    report = run_benchmark(build_corpus())
    changed = report.model_copy(update={"golden_set_id": "different"})
    assert "golden set changed" in compare_reports(report, changed).violations[0]
