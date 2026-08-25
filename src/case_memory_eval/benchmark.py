"""Versioned benchmark metrics, retrieval comparisons, and safety regression gates."""

from collections import defaultdict
from enum import StrEnum
from typing import Protocol

from pydantic import Field

from case_memory_eval.canonical import content_id
from case_memory_eval.contracts import CaseCorpus, ClinicalCase, FailureLabel, Severity, StrictModel
from case_memory_eval.evaluator import EvaluationArtifact, RuleEvaluator
from case_memory_eval.memory import ReviewedCaseMemory


class EvaluationMode(StrEnum):
    STATIC_RULES = "static_rules"
    JUDGE_ONLY = "judge_only"
    RETRIEVAL_GROUNDED = "retrieval_grounded"


class Evaluator(Protocol):
    @property
    def name(self) -> str: ...

    def evaluate(self, case: ClinicalCase) -> EvaluationArtifact: ...


class ClassMetrics(StrictModel):
    label: FailureLabel
    true_positive: int = Field(ge=0)
    false_positive: int = Field(ge=0)
    false_negative: int = Field(ge=0)
    true_negative: int = Field(ge=0)
    precision: float = Field(ge=0, le=1)
    recall: float = Field(ge=0, le=1)
    f1: float = Field(ge=0, le=1)


class CaseOutcome(StrictModel):
    case_id: str
    expected: tuple[FailureLabel, ...]
    predicted: tuple[FailureLabel, ...]
    confidences: tuple[float, ...]
    abstained: bool
    precedent_ids: tuple[str, ...] = ()


class BenchmarkReport(StrictModel):
    schema_version: int = 1
    report_id: str
    golden_set_id: str
    mode: EvaluationMode
    evaluator: str
    prompt_version: str
    embedding_provider: str | None
    class_metrics: tuple[ClassMetrics, ...]
    severe_recall: float = Field(ge=0, le=1)
    exact_match_accuracy: float = Field(ge=0, le=1)
    abstention_rate: float = Field(ge=0, le=1)
    reviewer_agreement: float = Field(ge=0, le=1)
    calibration_error: float = Field(ge=0, le=1)
    outcomes: tuple[CaseOutcome, ...]


class RegressionThresholds(StrictModel):
    minimum_severe_recall: float = Field(default=0.95, ge=0, le=1)
    maximum_severe_recall_drop: float = Field(default=0.0, ge=0, le=1)
    maximum_class_f1_drop: float = Field(default=0.05, ge=0, le=1)
    maximum_calibration_error: float = Field(default=0.20, ge=0, le=1)
    approved_failure_modes: frozenset[FailureLabel] = frozenset(FailureLabel)


class RegressionDecision(StrictModel):
    passed: bool
    violations: tuple[str, ...]


def _ratio(numerator: float, denominator: float) -> float:
    return numerator / denominator if denominator else 0.0


def _class_metrics(outcomes: tuple[CaseOutcome, ...]) -> tuple[ClassMetrics, ...]:
    metrics = []
    for label in FailureLabel:
        tp = sum(label in item.expected and label in item.predicted for item in outcomes)
        fp = sum(label not in item.expected and label in item.predicted for item in outcomes)
        fn = sum(label in item.expected and label not in item.predicted for item in outcomes)
        tn = len(outcomes) - tp - fp - fn
        precision = _ratio(tp, tp + fp)
        recall = _ratio(tp, tp + fn)
        metrics.append(
            ClassMetrics(
                label=label,
                true_positive=tp,
                false_positive=fp,
                false_negative=fn,
                true_negative=tn,
                precision=precision,
                recall=recall,
                f1=_ratio(2 * precision * recall, precision + recall),
            )
        )
    return tuple(metrics)


def _calibration_error(outcomes: tuple[CaseOutcome, ...], bins: int = 10) -> float:
    observations: list[tuple[float, bool]] = []
    for outcome in outcomes:
        confidence_by_label = dict(zip(outcome.predicted, outcome.confidences, strict=True))
        for label in FailureLabel:
            observations.append((confidence_by_label.get(label, 0.0), label in outcome.expected))
    grouped: dict[int, list[tuple[float, bool]]] = defaultdict(list)
    for confidence, actual in observations:
        grouped[min(int(confidence * bins), bins - 1)].append((confidence, actual))
    total = len(observations)
    return sum(
        len(items)
        / total
        * abs(
            sum(confidence for confidence, _ in items) / len(items)
            - sum(actual for _, actual in items) / len(items)
        )
        for items in grouped.values()
    )


def run_benchmark(
    corpus: CaseCorpus,
    *,
    mode: EvaluationMode = EvaluationMode.STATIC_RULES,
    evaluator: Evaluator | None = None,
    memory: ReviewedCaseMemory | None = None,
    prompt_version: str = "local-rules-v1",
    excluded_precedents: frozenset[str] = frozenset(),
) -> BenchmarkReport:
    active_evaluator = evaluator or RuleEvaluator()
    if mode is EvaluationMode.RETRIEVAL_GROUNDED and memory is None:
        raise ValueError("retrieval-grounded mode requires reviewed-case memory")
    outcomes = []
    severe_expected = 0
    severe_found = 0
    for case in corpus.cases:
        result = active_evaluator.evaluate(case)
        expected = tuple(item.label for item in case.expected_failures)
        predicted = tuple(item.label for item in result.findings)
        confidences = tuple(item.confidence for item in result.findings)
        precedent_ids: tuple[str, ...] = ()
        if mode is EvaluationMode.RETRIEVAL_GROUNDED:
            assert memory is not None
            retrieval = memory.retrieve(case, top_k=3, excluded_case_ids=excluded_precedents)
            precedent_ids = tuple(item.case_id for item in retrieval.precedents)
        outcomes.append(
            CaseOutcome(
                case_id=case.case_id,
                expected=expected,
                predicted=predicted,
                confidences=confidences,
                abstained=result.abstained,
                precedent_ids=precedent_ids,
            )
        )
        severe = {item.label for item in case.expected_failures if item.severity is Severity.SEVERE}
        severe_expected += len(severe)
        severe_found += len(severe & set(predicted))
    outcome_tuple = tuple(outcomes)
    class_metrics = _class_metrics(outcome_tuple)
    exact = sum(item.expected == item.predicted for item in outcome_tuple)
    abstained = sum(item.abstained for item in outcome_tuple)
    draft = {
        "schema_version": 1,
        "golden_set_id": corpus.corpus_id,
        "mode": mode.value,
        "evaluator": active_evaluator.name,
        "prompt_version": prompt_version,
        "embedding_provider": memory.embedder.name if memory is not None else None,
        "class_metrics": [item.model_dump(mode="json") for item in class_metrics],
        "severe_recall": _ratio(severe_found, severe_expected),
        "exact_match_accuracy": _ratio(exact, len(outcome_tuple)),
        "abstention_rate": _ratio(abstained, len(outcome_tuple)),
        "reviewer_agreement": _ratio(exact, len(outcome_tuple)),
        "calibration_error": _calibration_error(outcome_tuple),
        "outcomes": [item.model_dump(mode="json") for item in outcome_tuple],
    }
    return BenchmarkReport.model_validate({**draft, "report_id": content_id(draft)})


def compare_reports(
    baseline: BenchmarkReport,
    current: BenchmarkReport,
    thresholds: RegressionThresholds | None = None,
) -> RegressionDecision:
    thresholds = thresholds or RegressionThresholds()
    violations = []
    if current.golden_set_id != baseline.golden_set_id:
        violations.append("golden set changed; comparison is not valid")
    if current.severe_recall < thresholds.minimum_severe_recall:
        violations.append("severe recall is below the configured minimum")
    if baseline.severe_recall - current.severe_recall > thresholds.maximum_severe_recall_drop:
        violations.append("severe recall regressed")
    baseline_metrics = {item.label: item for item in baseline.class_metrics}
    for metric in current.class_metrics:
        if baseline_metrics[metric.label].f1 - metric.f1 > thresholds.maximum_class_f1_drop:
            violations.append(f"{metric.label.value} F1 regressed")
    if current.calibration_error > thresholds.maximum_calibration_error:
        violations.append("calibration error exceeds the configured maximum")
    observed_modes = {label for item in current.outcomes for label in item.expected}
    unapproved = observed_modes - thresholds.approved_failure_modes
    if unapproved:
        violations.append(
            "unapproved failure modes require human acceptance: "
            + ", ".join(sorted(label.value for label in unapproved))
        )
    return RegressionDecision(passed=not violations, violations=tuple(violations))
