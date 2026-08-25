import json

import pytest
from pydantic import ValidationError

from case_memory_eval.contracts import FailureLabel
from case_memory_eval.corpus import build_corpus
from case_memory_eval.evaluator import RuleEvaluator, StructuredProviderJudge


class StubProvider:
    name = "stub-v1"

    def __init__(self, response: str) -> None:
        self.response = response
        self.request = ""

    def generate(self, request_json: str) -> str:
        self.request = request_json
        return self.response


def test_rules_match_the_golden_corpus_without_reading_labels() -> None:
    evaluator = RuleEvaluator()
    for case in build_corpus().cases:
        result = evaluator.evaluate(case)
        assert {finding.label for finding in result.findings} == {
            expected.label for expected in case.expected_failures
        }
        assert not result.abstained
        for finding in result.findings:
            assert finding.transcript_span.text in case.transcript
            assert finding.note_span.text in case.generated_note


def test_adversarial_mutation_is_reason_coded() -> None:
    case = build_corpus().cases[0]
    mutated = case.model_copy(
        update={
            "generated_note": case.generated_note
            + " Assessment: The note states the condition is certainly harmless."
        }
    )
    result = RuleEvaluator().evaluate(mutated)
    assert [finding.label for finding in result.findings] == [FailureLabel.UNSAFE_CERTAINTY]


def test_provider_can_explicitly_abstain() -> None:
    case = build_corpus().cases[0]
    provider = StubProvider(
        json.dumps(
            {
                "findings": [],
                "abstained": True,
                "rationale": "The available evidence is insufficient for a supported verdict.",
            }
        )
    )
    result = StructuredProviderJudge(provider).evaluate(case)
    assert result.abstained
    assert not result.findings
    assert json.loads(provider.request)["case_id"] == case.case_id


def test_malformed_provider_response_is_rejected() -> None:
    case = build_corpus().cases[0]
    with pytest.raises(ValidationError):
        StructuredProviderJudge(StubProvider("not-json")).evaluate(case)


def test_provider_cannot_cite_fabricated_evidence() -> None:
    case = build_corpus().cases[0]
    response = {
        "findings": [
            {
                "label": "unsupported_inference",
                "severity": "moderate",
                "confidence": 0.9,
                "transcript_span": {
                    "source": "transcript",
                    "start": 0,
                    "end": 4,
                    "text": "fake",
                },
                "note_span": {"source": "note", "start": 0, "end": 4, "text": "fake"},
                "rationale": "The provider claims unsupported content is present.",
            }
        ],
        "abstained": False,
        "rationale": "The provider claims to have found a supported failure.",
    }
    with pytest.raises(ValidationError, match="invalid transcript"):
        StructuredProviderJudge(StubProvider(json.dumps(response))).evaluate(case)


def test_abstention_cannot_include_findings() -> None:
    case = build_corpus().cases[1]
    expected = RuleEvaluator().evaluate(case).findings
    response = {
        "findings": [item.model_dump(mode="json") for item in expected],
        "abstained": True,
        "rationale": "This invalid response both abstains and reports a finding.",
    }
    with pytest.raises(ValidationError, match="abstained verdict"):
        StructuredProviderJudge(StubProvider(json.dumps(response))).evaluate(case)
