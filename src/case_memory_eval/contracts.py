"""Versioned contracts for synthetic cases and expected failures."""

from enum import StrEnum
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from case_memory_eval.canonical import content_id


class StrictModel(BaseModel):
    """Reject undeclared fields in durable artifacts."""

    model_config = ConfigDict(extra="forbid", frozen=True)


class ScenarioFamily(StrEnum):
    HEADACHE = "headache"
    MEDICATION = "medication"
    FOLLOW_UP = "follow_up"
    REFERRAL = "referral"


class FailureLabel(StrEnum):
    OMISSION = "omission"
    UNSUPPORTED_INFERENCE = "unsupported_inference"
    PLAN_REVERSAL = "plan_reversal"
    UNSAFE_CERTAINTY = "unsafe_certainty"


class Severity(StrEnum):
    LOW = "low"
    MODERATE = "moderate"
    SEVERE = "severe"


class FactCategory(StrEnum):
    PRESENTATION = "presentation"
    DECISIVE_FACT = "decisive_fact"
    PLAN = "plan"
    UNCERTAINTY = "uncertainty"


class TextSpan(StrictModel):
    source: Literal["transcript", "note"]
    start: int = Field(ge=0)
    end: int = Field(gt=0)
    text: str = Field(min_length=1)

    @model_validator(mode="after")
    def end_after_start(self) -> Self:
        if self.end <= self.start:
            raise ValueError("span end must be greater than start")
        return self


class ExpectedFact(StrictModel):
    fact_id: str = Field(pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
    statement: str = Field(min_length=3)
    category: FactCategory
    required_in_note: bool
    transcript_span: TextSpan


class ExpectedFailure(StrictModel):
    label: FailureLabel
    severity: Severity
    transcript_span: TextSpan
    note_span: TextSpan
    reviewer_rationale: str = Field(min_length=10)


class Provenance(StrictModel):
    source: Literal["deterministic_synthetic_generator"]
    generator_version: Literal["1.0.0"]
    seed: int = Field(ge=0)
    synthetic: Literal[True]


class ClinicalCase(StrictModel):
    schema_version: Literal[1]
    case_id: str = Field(pattern=r"^[a-f0-9]{64}$")
    case_version: Literal[1]
    title: str = Field(min_length=3, max_length=120)
    scenario_family: ScenarioFamily
    transcript: str = Field(min_length=20)
    generated_note: str = Field(min_length=20)
    expected_facts: tuple[ExpectedFact, ...] = Field(min_length=1)
    expected_failures: tuple[ExpectedFailure, ...]
    reviewer_rationale: str = Field(min_length=10)
    provenance: Provenance

    @model_validator(mode="after")
    def validate_evidence_and_identity(self) -> Self:
        for fact in self.expected_facts:
            self._validate_span(fact.transcript_span)
            if fact.transcript_span.source != "transcript":
                raise ValueError("expected facts must cite transcript spans")
        for failure in self.expected_failures:
            self._validate_span(failure.transcript_span)
            self._validate_span(failure.note_span)
            if failure.transcript_span.source != "transcript":
                raise ValueError("failure transcript evidence must cite the transcript")
            if failure.note_span.source != "note":
                raise ValueError("failure note evidence must cite the note")
        payload = self.model_dump(mode="json", exclude={"case_id"})
        if self.case_id != content_id(payload):
            raise ValueError("case_id does not match canonical case content")
        return self

    def _validate_span(self, span: TextSpan) -> None:
        source_text = self.transcript if span.source == "transcript" else self.generated_note
        if span.end > len(source_text) or source_text[span.start : span.end] != span.text:
            raise ValueError(f"invalid {span.source} evidence span: {span.text!r}")


class CaseCorpus(StrictModel):
    schema_version: Literal[1]
    corpus_id: str = Field(pattern=r"^[a-f0-9]{64}$")
    generator_version: Literal["1.0.0"]
    cases: tuple[ClinicalCase, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_identity(self) -> Self:
        ids = [case.case_id for case in self.cases]
        if len(ids) != len(set(ids)):
            raise ValueError("case IDs must be unique")
        payload = self.model_dump(mode="json", exclude={"corpus_id"})
        if self.corpus_id != content_id(payload):
            raise ValueError("corpus_id does not match canonical corpus content")
        return self
