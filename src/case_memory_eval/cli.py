"""Command-line workflows for the local evaluation lab."""

from pathlib import Path
from typing import Annotated, Literal

import typer

from case_memory_eval.benchmark import EvaluationMode, run_benchmark
from case_memory_eval.canonical import canonical_json
from case_memory_eval.contracts import CaseCorpus, ClinicalCase
from case_memory_eval.corpus import build_corpus, write_corpus
from case_memory_eval.evaluator import RuleEvaluator
from case_memory_eval.memory import ReviewedCaseMemory
from case_memory_eval.provenance import (
    RunRecord,
    evidence_packet_json,
    evidence_packet_markdown,
    execute_run,
)
from case_memory_eval.provenance import replay as replay_record
from case_memory_eval.version import __version__
from case_memory_eval.workflow import WorkflowStore

app = typer.Typer(
    name="case-memory-eval",
    help="Evaluate generated notes against synthetic clinical transcripts.",
    no_args_is_help=True,
)


@app.callback()
def main() -> None:
    """Run synthetic clinical-note evaluation workflows."""


def _echo(value: object) -> None:
    typer.echo(canonical_json(value))


def _case(index: int) -> tuple[CaseCorpus, ClinicalCase]:
    corpus = build_corpus()
    if index < 0 or index >= len(corpus.cases):
        raise typer.BadParameter(f"case index must be between 0 and {len(corpus.cases) - 1}")
    return corpus, corpus.cases[index]


@app.command()
def version(
    json_output: Annotated[
        bool, typer.Option("--json", help="Emit machine-readable output.")
    ] = False,
) -> None:
    """Print the package version."""
    if json_output:
        _echo({"version": __version__})
    else:
        typer.echo(__version__)


@app.command("corpus")
def corpus_command(
    output: Annotated[Path, typer.Option(help="Destination JSON path.")] = Path(
        "fixtures/cases.json"
    ),
) -> None:
    """Generate the deterministic synthetic golden corpus."""
    write_corpus(output)
    _echo({"cases": len(build_corpus().cases), "output": str(output)})


@app.command()
def evaluate(
    index: Annotated[int, typer.Option(help="Zero-based fixture case index.")] = 1,
) -> None:
    """Evaluate one fixture case with the evidence-first baseline."""
    _, case = _case(index)
    _echo(RuleEvaluator().evaluate(case).model_dump(mode="json"))


@app.command()
def retrieve(
    database: Annotated[Path, typer.Option(help="DuckDB memory path.")],
    index: Annotated[int, typer.Option(help="Zero-based fixture case index.")] = 18,
    top_k: Annotated[int, typer.Option(min=1, max=20)] = 3,
) -> None:
    """Retrieve reviewed training precedents for one fixture case."""
    _, case = _case(index)
    with ReviewedCaseMemory(database) as memory:
        _echo(memory.retrieve(case, top_k=top_k).model_dump(mode="json"))


@app.command()
def benchmark(
    output: Annotated[Path | None, typer.Option(help="Optional report JSON path.")] = None,
    database: Annotated[Path | None, typer.Option(help="DuckDB path for retrieval mode.")] = None,
    mode: Annotated[EvaluationMode, typer.Option()] = EvaluationMode.STATIC_RULES,
) -> None:
    """Run the versioned golden benchmark."""
    corpus = build_corpus()
    memory = ReviewedCaseMemory(database) if database is not None else None
    try:
        benchmark_report = run_benchmark(corpus, mode=mode, memory=memory)
    finally:
        if memory is not None:
            memory.close()
    serialized = canonical_json(benchmark_report.model_dump(mode="json"))
    if output is not None:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(f"{serialized}\n")
    typer.echo(serialized)


@app.command()
def ingest(
    database: Annotated[Path, typer.Option(help="Workflow DuckDB path.")],
    index: Annotated[int, typer.Option(help="Zero-based fixture case index.")] = 1,
    actor: Annotated[str, typer.Option()] = "local-cli",
) -> None:
    """Ingest an attested synthetic fixture into the review workflow."""
    _, case = _case(index)
    store = WorkflowStore(database)
    try:
        created = store.ingest(case, "synthetic", actor)
        result = RuleEvaluator().evaluate(case)
        verdict_created = store.save_verdict(result, actor="local-evaluator")
    finally:
        store.close()
    _echo(
        {
            "case_id": case.case_id,
            "created": created,
            "result_id": result.result_id,
            "verdict_created": verdict_created,
        }
    )


@app.command()
def review(
    database: Annotated[Path, typer.Option(help="Workflow DuckDB path.")],
    result_id: Annotated[str | None, typer.Option()] = None,
    decision: Annotated[Literal["accepted", "rejected", "deferred"] | None, typer.Option()] = None,
    reviewer: Annotated[str, typer.Option()] = "local-reviewer",
    rationale: Annotated[str, typer.Option()] = "Evidence citations inspected by local reviewer.",
    idempotency_key: Annotated[str, typer.Option()] = "local-review-decision",
) -> None:
    """List the queue or record an attributable review decision."""
    store = WorkflowStore(database)
    try:
        if result_id is None and decision is None:
            _echo(store.review_queue())
            return
        if result_id is None or decision is None:
            raise typer.BadParameter("--result-id and --decision must be provided together")
        review_id = store.decide(
            result_id,
            reviewer=reviewer,
            decision=decision,
            rationale=rationale,
            idempotency_key=idempotency_key,
        )
        _echo({"review_id": review_id, "decision": decision})
    finally:
        store.close()


@app.command()
def promote(
    database: Annotated[Path, typer.Option(help="Workflow DuckDB path.")],
    review_id: Annotated[str, typer.Option()],
    actor: Annotated[str, typer.Option()] = "local-reviewer",
) -> None:
    """Promote a case from an accepted human review."""
    store = WorkflowStore(database)
    try:
        promotion_id = store.promote(review_id, actor)
    finally:
        store.close()
    _echo({"promotion_id": promotion_id})


@app.command()
def replay(
    record: Annotated[Path, typer.Option(help="Historical run record JSON.")],
    database: Annotated[Path | None, typer.Option(help="Optional reviewed-memory DuckDB.")] = None,
) -> None:
    """Replay a run after checking every provenance input."""
    historical = RunRecord.model_validate_json(record.read_text())
    corpus = build_corpus()
    case = next((item for item in corpus.cases if item.case_id == historical.result.case_id), None)
    if case is None:
        raise typer.BadParameter("historical case is absent from the current corpus")
    memory = ReviewedCaseMemory(database) if database is not None else None
    try:
        current = replay_record(historical, case, corpus_id=corpus.corpus_id, memory=memory)
    finally:
        if memory is not None:
            memory.close()
    _echo({"replayed": True, "record_id": current.record_id})


@app.command()
def report(
    record: Annotated[Path, typer.Option(help="Run record JSON.")],
    output: Annotated[Path, typer.Option(help="Evidence packet path.")],
    format: Annotated[Literal["json", "markdown"], typer.Option()] = "markdown",
) -> None:
    """Render a compact evidence packet from an immutable run."""
    run = RunRecord.model_validate_json(record.read_text())
    content = (
        evidence_packet_json(run) + "\n" if format == "json" else evidence_packet_markdown(run)
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(content)
    _echo({"format": format, "output": str(output)})


@app.command()
def serve(
    database: Annotated[Path, typer.Option(help="Workflow DuckDB path.")] = Path(
        "case-memory-eval.duckdb"
    ),
    host: Annotated[str, typer.Option()] = "127.0.0.1",
    port: Annotated[int, typer.Option(min=1, max=65535)] = 4320,
) -> None:
    """Serve the audited API and reviewer interface."""
    import uvicorn

    from case_memory_eval.api import create_app

    uvicorn.run(create_app(database), host=host, port=port)


@app.command()
def demo(
    output: Annotated[Path, typer.Option(help="Demo artifact directory.")] = Path("demo-output"),
) -> None:
    """Run the deterministic suite and seed a review workflow without API keys."""
    output.mkdir(parents=True, exist_ok=True)
    corpus = build_corpus()
    database = output / "clinical-case-memory.duckdb"
    with ReviewedCaseMemory(database) as memory:
        for case in corpus.cases[:18]:
            memory.add(case)
        benchmark_report = run_benchmark(
            corpus, mode=EvaluationMode.RETRIEVAL_GROUNDED, memory=memory
        )
        run = execute_run(corpus.cases[19], corpus_id=corpus.corpus_id, memory=memory)
    store = WorkflowStore(database)
    try:
        store.ingest(corpus.cases[19], "synthetic", "demo")
        store.save_verdict(run.result, "demo-evaluator")
    finally:
        store.close()
    artifacts = {
        "benchmark.json": canonical_json(benchmark_report.model_dump(mode="json")) + "\n",
        "run.json": canonical_json(run.model_dump(mode="json")) + "\n",
        "evidence.json": evidence_packet_json(run) + "\n",
        "evidence.md": evidence_packet_markdown(run),
    }
    for name, content in artifacts.items():
        (output / name).write_text(content)
    _echo(
        {
            "database": str(database),
            "exact_match_accuracy": benchmark_report.exact_match_accuracy,
            "queued_case_id": corpus.cases[19].case_id,
            "artifacts": sorted(artifacts),
        }
    )
