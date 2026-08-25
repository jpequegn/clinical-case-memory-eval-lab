from collections import Counter
from pathlib import Path

import pytest
from pydantic import ValidationError

from case_memory_eval.contracts import CaseCorpus, FailureLabel, ScenarioFamily
from case_memory_eval.corpus import build_corpus

FIXTURE_PATH = Path(__file__).parents[1] / "fixtures" / "cases.json"


def test_corpus_is_stable_balanced_and_complete() -> None:
    first = build_corpus()
    second = build_corpus()
    assert first == second
    assert first.corpus_id == second.corpus_id
    assert len(first.cases) == 36
    assert len({case.case_id for case in first.cases}) == 36
    assert Counter(case.scenario_family for case in first.cases) == {
        family: 9 for family in ScenarioFamily
    }
    labels = Counter(failure.label for case in first.cases for failure in case.expected_failures)
    assert labels == {
        FailureLabel.OMISSION: 8,
        FailureLabel.UNSUPPORTED_INFERENCE: 8,
        FailureLabel.PLAN_REVERSAL: 8,
        FailureLabel.UNSAFE_CERTAINTY: 8,
    }
    assert sum(not case.expected_failures for case in first.cases) == 4


def test_checked_in_fixture_matches_generator() -> None:
    fixture = CaseCorpus.model_validate_json(FIXTURE_PATH.read_text())
    assert fixture == build_corpus()


def test_every_failure_has_valid_dual_source_evidence() -> None:
    corpus = build_corpus()
    for case in corpus.cases:
        assert case.provenance.synthetic is True
        assert len(case.expected_facts) == 4
        for failure in case.expected_failures:
            assert (
                failure.transcript_span.text
                == case.transcript[failure.transcript_span.start : failure.transcript_span.end]
            )
            assert (
                failure.note_span.text
                == case.generated_note[failure.note_span.start : failure.note_span.end]
            )


def test_rejects_tampered_span_and_content_identity() -> None:
    corpus = build_corpus()
    payload = corpus.model_dump(mode="json")
    payload["cases"][0]["transcript"] = "tampered transcript content long enough for validation"
    with pytest.raises(ValidationError, match="invalid transcript evidence span"):
        CaseCorpus.model_validate(payload)

    payload = corpus.model_dump(mode="json")
    payload["corpus_id"] = "0" * 64
    with pytest.raises(ValidationError, match="corpus_id"):
        CaseCorpus.model_validate(payload)
