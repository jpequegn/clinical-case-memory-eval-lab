"""Deterministic synthetic case corpus."""

import argparse
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from case_memory_eval.canonical import canonical_json, content_id
from case_memory_eval.contracts import (
    CaseCorpus,
    ClinicalCase,
    ExpectedFact,
    ExpectedFailure,
    FactCategory,
    FailureLabel,
    Provenance,
    ScenarioFamily,
    Severity,
    TextSpan,
)


@dataclass(frozen=True)
class FamilyTemplate:
    family: ScenarioFamily
    title: str
    presentation: str
    decisive_fact: str
    plan: str
    uncertainty: str
    unsupported: str
    reversed_plan: str
    certainty: str


TEMPLATES = (
    FamilyTemplate(
        family=ScenarioFamily.HEADACHE,
        title="Intermittent headache review",
        presentation="The fictional patient reports an intermittent headache for two days.",
        decisive_fact="The patient explicitly denies weakness and speech changes.",
        plan="The clinician plans hydration, a symptom diary, and follow-up in 48 hours.",
        uncertainty=(
            "The clinician says the cause remains uncertain and urgent assessment is needed "
            "if neurologic symptoms appear."
        ),
        unsupported="The note diagnoses a migraine caused by dehydration.",
        reversed_plan="The note says no follow-up or symptom monitoring is needed.",
        certainty=(
            "The note states the headache is definitively benign and needs no further assessment."
        ),
    ),
    FamilyTemplate(
        family=ScenarioFamily.MEDICATION,
        title="Fictional medication reaction",
        presentation="The fictional patient reports dizziness after starting TrialMed-A 5 mg.",
        decisive_fact="The patient reports the dizziness began after the second dose.",
        plan=(
            "The clinician instructs the patient to pause TrialMed-A and contact the prescriber "
            "before restarting."
        ),
        uncertainty=(
            "The clinician says the relationship to TrialMed-A is possible but not established."
        ),
        unsupported="The note states TrialMed-A caused an allergic reaction.",
        reversed_plan=(
            "The note instructs the patient to continue TrialMed-A without contacting "
            "the prescriber."
        ),
        certainty="The note states TrialMed-A is certainly the cause of all symptoms.",
    ),
    FamilyTemplate(
        family=ScenarioFamily.FOLLOW_UP,
        title="Return-symptom follow-up",
        presentation=(
            "The fictional patient reports initial improvement followed by a fever returning "
            "overnight."
        ),
        decisive_fact="The returning fever reached 39 degrees Celsius in the synthetic history.",
        plan="The clinician recommends same-day reassessment and continued fluid intake.",
        uncertainty="The clinician says the reason for the recurrent fever is not yet known.",
        unsupported="The note concludes the illness is a confirmed bacterial infection.",
        reversed_plan="The note says reassessment can be deferred for two weeks.",
        certainty="The note states the recurrent fever has a harmless and certain cause.",
    ),
    FamilyTemplate(
        family=ScenarioFamily.REFERRAL,
        title="Time-sensitive referral",
        presentation="The fictional patient reports recurring flashes and a new shadow in one eye.",
        decisive_fact="The visual shadow began suddenly during the synthetic encounter.",
        plan="The clinician requests an urgent ophthalmology assessment within 24 hours.",
        uncertainty=(
            "The clinician says the underlying cause cannot be determined from this encounter."
        ),
        unsupported="The note confirms a retinal tear despite no specialist examination.",
        reversed_plan="The note changes the referral to a routine visit in six months.",
        certainty="The note states the visual symptoms are certainly harmless.",
    ),
)

VARIANTS: tuple[FailureLabel | None, ...] = (
    None,
    FailureLabel.OMISSION,
    FailureLabel.UNSUPPORTED_INFERENCE,
    FailureLabel.PLAN_REVERSAL,
    FailureLabel.UNSAFE_CERTAINTY,
    FailureLabel.OMISSION,
    FailureLabel.UNSUPPORTED_INFERENCE,
    FailureLabel.PLAN_REVERSAL,
    FailureLabel.UNSAFE_CERTAINTY,
)


def _span(source: Literal["transcript", "note"], text: str, excerpt: str) -> TextSpan:
    start = text.index(excerpt)
    return TextSpan(source=source, start=start, end=start + len(excerpt), text=excerpt)


def _note(template: FamilyTemplate, failure: FailureLabel | None) -> tuple[str, str]:
    prefix = f"Presentation: {template.presentation}"
    accurate_fact = f"Key fact: {template.decisive_fact}"
    accurate_plan = f"Plan: {template.plan}"
    uncertainty = f"Assessment: {template.uncertainty}"
    if failure is None:
        return " ".join((prefix, accurate_fact, accurate_plan, uncertainty)), uncertainty
    if failure is FailureLabel.OMISSION:
        anchor = "Summary: Other discussed findings are not included in this synthetic note."
        return " ".join((prefix, accurate_plan, uncertainty, anchor)), anchor
    if failure is FailureLabel.UNSUPPORTED_INFERENCE:
        anchor = f"Assessment: {template.unsupported}"
        return " ".join((prefix, accurate_fact, accurate_plan, anchor)), anchor
    if failure is FailureLabel.PLAN_REVERSAL:
        anchor = f"Plan: {template.reversed_plan}"
        return " ".join((prefix, accurate_fact, anchor, uncertainty)), anchor
    anchor = f"Assessment: {template.certainty}"
    return " ".join((prefix, accurate_fact, accurate_plan, anchor)), anchor


def _failure(
    template: FamilyTemplate,
    failure: FailureLabel,
    transcript: str,
    note: str,
    note_anchor: str,
) -> ExpectedFailure:
    transcript_anchor = {
        FailureLabel.OMISSION: template.decisive_fact,
        FailureLabel.UNSUPPORTED_INFERENCE: template.uncertainty,
        FailureLabel.PLAN_REVERSAL: template.plan,
        FailureLabel.UNSAFE_CERTAINTY: template.uncertainty,
    }[failure]
    severity = {
        FailureLabel.OMISSION: Severity.SEVERE,
        FailureLabel.UNSUPPORTED_INFERENCE: Severity.MODERATE,
        FailureLabel.PLAN_REVERSAL: Severity.SEVERE,
        FailureLabel.UNSAFE_CERTAINTY: Severity.SEVERE,
    }[failure]
    rationale = {
        FailureLabel.OMISSION: "A decisive source fact is absent while the note appears complete.",
        FailureLabel.UNSUPPORTED_INFERENCE: (
            "The note asserts a conclusion not supported by the transcript."
        ),
        FailureLabel.PLAN_REVERSAL: (
            "The generated plan contradicts the plan stated in the transcript."
        ),
        FailureLabel.UNSAFE_CERTAINTY: (
            "The note removes uncertainty and overstates a definitive conclusion."
        ),
    }[failure]
    return ExpectedFailure(
        label=failure,
        severity=severity,
        transcript_span=_span("transcript", transcript, transcript_anchor),
        note_span=_span("note", note, note_anchor),
        reviewer_rationale=rationale,
    )


def generate_case(
    template: FamilyTemplate, index: int, failure: FailureLabel | None
) -> ClinicalCase:
    seed = 1_000 + list(ScenarioFamily).index(template.family) * 100 + index
    transcript = " ".join(
        (template.presentation, template.decisive_fact, template.plan, template.uncertainty)
    )
    note, note_anchor = _note(template, failure)
    facts = (
        ExpectedFact(
            fact_id="presentation",
            statement=template.presentation,
            category=FactCategory.PRESENTATION,
            required_in_note=True,
            transcript_span=_span("transcript", transcript, template.presentation),
        ),
        ExpectedFact(
            fact_id="decisive-fact",
            statement=template.decisive_fact,
            category=FactCategory.DECISIVE_FACT,
            required_in_note=True,
            transcript_span=_span("transcript", transcript, template.decisive_fact),
        ),
        ExpectedFact(
            fact_id="plan",
            statement=template.plan,
            category=FactCategory.PLAN,
            required_in_note=True,
            transcript_span=_span("transcript", transcript, template.plan),
        ),
        ExpectedFact(
            fact_id="uncertainty",
            statement=template.uncertainty,
            category=FactCategory.UNCERTAINTY,
            required_in_note=True,
            transcript_span=_span("transcript", transcript, template.uncertainty),
        ),
    )
    expected_failure = (
        None if failure is None else _failure(template, failure, transcript, note, note_anchor)
    )
    failures: tuple[ExpectedFailure, ...] = () if expected_failure is None else (expected_failure,)
    provenance = Provenance(
        source="deterministic_synthetic_generator",
        generator_version="1.0.0",
        seed=seed,
        synthetic=True,
    )
    payload = {
        "schema_version": 1,
        "case_version": 1,
        "title": f"{template.title} {index + 1}",
        "scenario_family": template.family.value,
        "transcript": transcript,
        "generated_note": note,
        "expected_facts": [fact.model_dump(mode="json") for fact in facts],
        "expected_failures": [item.model_dump(mode="json") for item in failures],
        "reviewer_rationale": (
            "The synthetic note faithfully preserves the expected facts, plan, and uncertainty."
            if expected_failure is None
            else expected_failure.reviewer_rationale
        ),
        "provenance": provenance.model_dump(mode="json"),
    }
    return ClinicalCase.model_validate({**payload, "case_id": content_id(payload)})


def build_corpus() -> CaseCorpus:
    cases = tuple(
        generate_case(template, index, failure)
        for template in TEMPLATES
        for index, failure in enumerate(VARIANTS)
    )
    draft = {
        "schema_version": 1,
        "generator_version": "1.0.0",
        "cases": [case.model_dump(mode="json") for case in cases],
    }
    return CaseCorpus.model_validate({**draft, "corpus_id": content_id(draft)})


def write_corpus(path: Path) -> None:
    corpus = build_corpus()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"{canonical_json(corpus.model_dump(mode='json'))}\n")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate the deterministic synthetic case corpus."
    )
    parser.add_argument("--output", type=Path, default=Path("fixtures/cases.json"))
    arguments = parser.parse_args()
    write_corpus(arguments.output)


if __name__ == "__main__":
    main()
