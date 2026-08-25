"""Content-addressed manifests, deterministic replay, traces, and evidence packets."""

from collections.abc import Mapping
from typing import Any, Literal, Self

from pydantic import Field, model_validator

from case_memory_eval.canonical import canonical_json, content_id
from case_memory_eval.contracts import ClinicalCase, StrictModel
from case_memory_eval.evaluator import EvaluationArtifact, RuleEvaluator
from case_memory_eval.memory import RetrievedPrecedent, ReviewedCaseMemory


class RetrievalManifest(StrictModel):
    enabled: bool
    embedding_provider: str | None
    memory_snapshot_id: str | None
    top_k: int = Field(ge=0)
    precedent_ids: tuple[str, ...]


class RunManifest(StrictModel):
    schema_version: Literal[1]
    manifest_id: str = Field(pattern=r"^[a-f0-9]{64}$")
    case_id: str
    corpus_id: str
    evaluator: str
    prompt_version: str
    model_version: str
    policy_version: str
    retrieval: RetrievalManifest
    trace_id: str = Field(pattern=r"^[a-f0-9]{32}$")

    @model_validator(mode="after")
    def validate_identity(self) -> Self:
        payload = self.model_dump(mode="json", exclude={"manifest_id"})
        if self.manifest_id != content_id(payload):
            raise ValueError("manifest_id does not match canonical manifest content")
        return self


class TraceSpan(StrictModel):
    trace_id: str = Field(pattern=r"^[a-f0-9]{32}$")
    span_id: str = Field(pattern=r"^[a-f0-9]{16}$")
    parent_span_id: str | None = Field(default=None, pattern=r"^[a-f0-9]{16}$")
    name: str
    start_time_unix_nano: int = Field(default=0, ge=0)
    end_time_unix_nano: int = Field(default=0, ge=0)
    attributes: dict[str, str | int | float | bool]


class RunRecord(StrictModel):
    schema_version: Literal[1]
    record_id: str = Field(pattern=r"^[a-f0-9]{64}$")
    manifest: RunManifest
    result: EvaluationArtifact
    precedents: tuple[RetrievedPrecedent, ...]
    spans: tuple[TraceSpan, ...]

    @model_validator(mode="after")
    def validate_identity(self) -> Self:
        payload = self.model_dump(mode="json", exclude={"record_id"})
        if self.record_id != content_id(payload):
            raise ValueError("record_id does not match canonical run content")
        return self


class ProvenanceChange(StrictModel):
    field: str
    before: Any
    after: Any


class EvidencePacket(StrictModel):
    schema_version: Literal[1]
    packet_id: str
    run_record_id: str
    case_id: str
    uncertainty: str
    precedents: tuple[RetrievedPrecedent, ...]
    findings: tuple[dict[str, Any], ...]
    handoff: str
    remediation: tuple[str, ...]


class ProvenanceMismatch(ValueError):
    def __init__(self, changes: tuple[ProvenanceChange, ...]) -> None:
        self.changes = changes
        fields = ", ".join(change.field for change in changes)
        super().__init__(f"replay inputs changed: {fields}")


def _trace_id(config: Mapping[str, object]) -> str:
    return content_id(config)[:32]


def _span(trace_id: str, name: str, parent: str | None, **attributes: Any) -> TraceSpan:
    span_id = content_id({"trace_id": trace_id, "name": name})[:16]
    return TraceSpan(
        trace_id=trace_id,
        span_id=span_id,
        parent_span_id=parent,
        name=name,
        attributes=attributes,
    )


def execute_run(
    case: ClinicalCase,
    *,
    corpus_id: str,
    evaluator: RuleEvaluator | None = None,
    memory: ReviewedCaseMemory | None = None,
    top_k: int = 3,
    prompt_version: str = "local-rules-v1",
    model_version: str = "deterministic-local-v1",
    policy_version: str = "clinical-safety-v1",
) -> RunRecord:
    active_evaluator = evaluator or RuleEvaluator()
    precedents: tuple[RetrievedPrecedent, ...] = ()
    snapshot_id = None
    embedding_provider = None
    if memory is not None:
        snapshot_id = memory.snapshot_id()
        embedding_provider = memory.embedder.name
        precedents = memory.retrieve(case, top_k=top_k).precedents
    config = {
        "case_id": case.case_id,
        "corpus_id": corpus_id,
        "evaluator": active_evaluator.name,
        "prompt_version": prompt_version,
        "model_version": model_version,
        "policy_version": policy_version,
        "memory_snapshot_id": snapshot_id,
        "top_k": top_k if memory is not None else 0,
    }
    trace_id = _trace_id(config)
    retrieval = RetrievalManifest(
        enabled=memory is not None,
        embedding_provider=embedding_provider,
        memory_snapshot_id=snapshot_id,
        top_k=top_k if memory is not None else 0,
        precedent_ids=tuple(item.case_id for item in precedents),
    )
    manifest_draft = {
        "schema_version": 1,
        "case_id": case.case_id,
        "corpus_id": corpus_id,
        "evaluator": active_evaluator.name,
        "prompt_version": prompt_version,
        "model_version": model_version,
        "policy_version": policy_version,
        "retrieval": retrieval.model_dump(mode="json"),
        "trace_id": trace_id,
    }
    manifest = RunManifest.model_validate(
        {**manifest_draft, "manifest_id": content_id(manifest_draft)}
    )
    result = active_evaluator.evaluate(case)
    root_id = content_id({"trace_id": trace_id, "name": "evaluation.run"})[:16]
    spans = (
        _span(trace_id, "evaluation.run", None, case_id=case.case_id),
        _span(trace_id, "retrieval.query", root_id, precedent_count=len(precedents)),
        _span(trace_id, "judge.evaluate", root_id, evaluator=active_evaluator.name),
        _span(trace_id, "aggregation.verdict", root_id, finding_count=len(result.findings)),
        _span(trace_id, "review.handoff", root_id, status="pending"),
    )
    record_draft = {
        "schema_version": 1,
        "manifest": manifest.model_dump(mode="json"),
        "result": result.model_dump(mode="json"),
        "precedents": [item.model_dump(mode="json") for item in precedents],
        "spans": [item.model_dump(mode="json") for item in spans],
    }
    return RunRecord.model_validate({**record_draft, "record_id": content_id(record_draft)})


def provenance_diff(before: RunManifest, after: RunManifest) -> tuple[ProvenanceChange, ...]:
    before_data = before.model_dump(mode="json", exclude={"manifest_id", "trace_id"})
    after_data = after.model_dump(mode="json", exclude={"manifest_id", "trace_id"})
    changes = []

    def visit(prefix: str, left: Any, right: Any) -> None:
        if isinstance(left, dict) and isinstance(right, dict):
            for key in sorted(left.keys() | right.keys()):
                visit(f"{prefix}.{key}" if prefix else key, left.get(key), right.get(key))
        elif left != right:
            changes.append(ProvenanceChange(field=prefix, before=left, after=right))

    visit("", before_data, after_data)
    return tuple(changes)


def replay(
    historical: RunRecord,
    case: ClinicalCase,
    *,
    corpus_id: str,
    evaluator: RuleEvaluator | None = None,
    memory: ReviewedCaseMemory | None = None,
) -> RunRecord:
    current = execute_run(
        case,
        corpus_id=corpus_id,
        evaluator=evaluator,
        memory=memory,
        top_k=historical.manifest.retrieval.top_k or 3,
        prompt_version=historical.manifest.prompt_version,
        model_version=historical.manifest.model_version,
        policy_version=historical.manifest.policy_version,
    )
    changes = provenance_diff(historical.manifest, current.manifest)
    if changes:
        raise ProvenanceMismatch(changes)
    if current.result.result_id != historical.result.result_id:
        raise ProvenanceMismatch(
            (
                ProvenanceChange(
                    field="result.result_id",
                    before=historical.result.result_id,
                    after=current.result.result_id,
                ),
            )
        )
    return current


def evidence_packet(record: RunRecord) -> EvidencePacket:
    findings = tuple(item.model_dump(mode="json") for item in record.result.findings)
    uncertainty = (
        "Judge abstained; human determination is required."
        if record.result.abstained
        else "Confidence is reported per finding; no clinical conclusion is produced."
    )
    handoff = "Human review required before memory promotion."
    remediation = tuple(
        f"Review and correct {item.label.value}: {item.rationale}"
        for item in record.result.findings
    ) or ("Retain as a reviewed clean control if a human confirms the verdict.",)
    draft = {
        "schema_version": 1,
        "run_record_id": record.record_id,
        "case_id": record.result.case_id,
        "uncertainty": uncertainty,
        "precedents": [item.model_dump(mode="json") for item in record.precedents],
        "findings": findings,
        "handoff": handoff,
        "remediation": remediation,
    }
    return EvidencePacket.model_validate({**draft, "packet_id": content_id(draft)})


def evidence_packet_json(record: RunRecord) -> str:
    return canonical_json(evidence_packet(record).model_dump(mode="json"))


def evidence_packet_markdown(record: RunRecord) -> str:
    packet = evidence_packet(record)
    precedent_lines = [
        f"- `{item.case_id}` ({item.scenario_family.value}, score {item.score:.3f})"
        for item in packet.precedents
    ] or ["- None"]
    finding_lines = [
        f"- **{item['label']}** ({item['severity']}, confidence {item['confidence']:.2f}): "
        f"{item['rationale']}"
        for item in packet.findings
    ] or ["- No supported findings"]
    remediation_lines = [f"- {item}" for item in packet.remediation]
    return "\n".join(
        [
            "# Evidence Packet",
            "",
            f"- Packet: `{packet.packet_id}`",
            f"- Run: `{packet.run_record_id}`",
            f"- Case: `{packet.case_id}`",
            "",
            "## Uncertainty",
            "",
            packet.uncertainty,
            "",
            "## Reviewed Precedents",
            "",
            *precedent_lines,
            "",
            "## Findings",
            "",
            *finding_lines,
            "",
            "## Handoff",
            "",
            packet.handoff,
            "",
            "## Remediation",
            "",
            *remediation_lines,
            "",
        ]
    )
