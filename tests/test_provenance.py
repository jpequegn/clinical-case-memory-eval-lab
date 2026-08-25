from pathlib import Path

import pytest

from case_memory_eval.corpus import build_corpus
from case_memory_eval.memory import ReviewedCaseMemory
from case_memory_eval.provenance import (
    ProvenanceMismatch,
    evidence_packet_json,
    evidence_packet_markdown,
    execute_run,
    provenance_diff,
    replay,
)


def test_unchanged_run_replays_with_identical_content_ids(tmp_path: Path) -> None:
    corpus = build_corpus()
    with ReviewedCaseMemory(tmp_path / "memory.duckdb") as memory:
        for case in corpus.cases[:9]:
            memory.add(case)
        historical = execute_run(corpus.cases[10], corpus_id=corpus.corpus_id, memory=memory)
        repeated = replay(historical, corpus.cases[10], corpus_id=corpus.corpus_id, memory=memory)
    assert repeated == historical
    assert repeated.record_id == historical.record_id
    assert repeated.result.result_id == historical.result.result_id


def test_changed_memory_is_surfaced_without_rewriting_history(tmp_path: Path) -> None:
    corpus = build_corpus()
    with ReviewedCaseMemory(tmp_path / "memory.duckdb") as memory:
        memory.add(corpus.cases[0])
        historical = execute_run(corpus.cases[10], corpus_id=corpus.corpus_id, memory=memory)
        original_id = historical.record_id
        memory.add(corpus.cases[1])
        with pytest.raises(ProvenanceMismatch, match="memory_snapshot_id") as captured:
            replay(historical, corpus.cases[10], corpus_id=corpus.corpus_id, memory=memory)
    assert historical.record_id == original_id
    assert any(change.field == "retrieval.memory_snapshot_id" for change in captured.value.changes)


def test_prompt_model_and_corpus_changes_are_diffed() -> None:
    corpus = build_corpus()
    baseline = execute_run(corpus.cases[0], corpus_id=corpus.corpus_id)
    changed = execute_run(
        corpus.cases[0],
        corpus_id="corpus-v2",
        prompt_version="prompt-v2",
        model_version="model-v2",
    )
    assert {item.field for item in provenance_diff(baseline.manifest, changed.manifest)} == {
        "corpus_id",
        "model_version",
        "prompt_version",
    }


def test_trace_spans_are_correlated_and_otel_compatible() -> None:
    corpus = build_corpus()
    record = execute_run(corpus.cases[1], corpus_id=corpus.corpus_id)
    assert {span.name for span in record.spans} == {
        "evaluation.run",
        "retrieval.query",
        "judge.evaluate",
        "aggregation.verdict",
        "review.handoff",
    }
    assert {span.trace_id for span in record.spans} == {record.manifest.trace_id}
    assert all(len(span.span_id) == 16 for span in record.spans)
    assert all(span.start_time_unix_nano == 0 for span in record.spans)


def test_evidence_packet_json_and_markdown_are_stable() -> None:
    corpus = build_corpus()
    record = execute_run(corpus.cases[1], corpus_id=corpus.corpus_id)
    assert evidence_packet_json(record) == evidence_packet_json(record)
    markdown = evidence_packet_markdown(record)
    assert markdown.startswith("# Evidence Packet\n")
    assert "## Uncertainty" in markdown
    assert "## Reviewed Precedents\n\n- None" in markdown
    assert "**omission** (severe, confidence 0.95)" in markdown
    assert "## Handoff" in markdown
    assert "## Remediation" in markdown
