from pathlib import Path

import pytest

from case_memory_eval.contracts import FailureLabel, ScenarioFamily
from case_memory_eval.corpus import build_corpus
from case_memory_eval.memory import HashEmbedding, ReviewedCaseMemory


def test_hash_embedding_is_deterministic_and_normalized() -> None:
    embedder = HashEmbedding(32)
    first = embedder.embed("repeatable clinical case text")
    assert first == embedder.embed("repeatable clinical case text")
    assert len(first) == 32
    assert sum(value * value for value in first) == pytest.approx(1.0)
    with pytest.raises(ValueError, match="at least 8"):
        HashEmbedding(4)


def test_retrieval_is_ranked_filtered_and_explainable(tmp_path: Path) -> None:
    cases = build_corpus().cases
    with ReviewedCaseMemory(tmp_path / "memory.duckdb") as memory:
        for case in cases[:18]:
            memory.add(case)
        query = cases[8]
        first = memory.retrieve(
            query,
            top_k=4,
            family=ScenarioFamily.HEADACHE,
            failure_mode=FailureLabel.UNSAFE_CERTAINTY,
        )
        second = memory.retrieve(
            query,
            top_k=4,
            family=ScenarioFamily.HEADACHE,
            failure_mode=FailureLabel.UNSAFE_CERTAINTY,
        )
    assert first == second
    assert all(item.case_id != query.case_id for item in first.precedents)
    assert all(item.scenario_family is ScenarioFamily.HEADACHE for item in first.precedents)
    assert all(FailureLabel.UNSAFE_CERTAINTY in item.failure_modes for item in first.precedents)
    assert all("vector=" in item.influence for item in first.precedents)
    assert [item.score for item in first.precedents] == sorted(
        (item.score for item in first.precedents), reverse=True
    )


def test_memory_persists_and_blocks_holdout_leakage(tmp_path: Path) -> None:
    path = tmp_path / "memory.duckdb"
    train, validation, holdout = build_corpus().cases[:3]
    with ReviewedCaseMemory(path) as memory:
        memory.add(train, split="train")
        memory.add(validation, split="validation")
        memory.add(holdout, split="holdout")
    with ReviewedCaseMemory(path) as reopened:
        result = reopened.retrieve(holdout, top_k=10, query_split="holdout")
    assert [item.case_id for item in result.precedents] == [train.case_id]


def test_unpromoted_and_self_cases_never_influence_results(tmp_path: Path) -> None:
    cases = build_corpus().cases
    query, promoted, unpromoted = cases[0], cases[1], cases[2]
    with ReviewedCaseMemory(tmp_path / "memory.duckdb") as memory:
        memory.add(query)
        memory.add(promoted)
        memory.add(unpromoted, promoted=False)
        result = memory.retrieve(query, top_k=10, query_split="train")
    assert [item.case_id for item in result.precedents] == [promoted.case_id]


def test_precedent_removal_ablation_is_reportable(tmp_path: Path) -> None:
    cases = build_corpus().cases
    query = cases[8]
    with ReviewedCaseMemory(tmp_path / "memory.duckdb") as memory:
        for case in cases[:8]:
            memory.add(case)
        baseline = memory.retrieve(query, top_k=3)
        removed_id = baseline.precedents[0].case_id
        ablated = memory.retrieve(query, top_k=3, excluded_case_ids=frozenset({removed_id}))
    assert removed_id not in {item.case_id for item in ablated.precedents}
    assert baseline.precedents != ablated.precedents


def test_retrieve_rejects_non_positive_limit(tmp_path: Path) -> None:
    query = build_corpus().cases[0]
    with (
        ReviewedCaseMemory(tmp_path / "memory.duckdb") as memory,
        pytest.raises(ValueError, match="positive"),
    ):
        memory.retrieve(query, top_k=0)
