import json
from pathlib import Path

from typer.testing import CliRunner

from case_memory_eval.cli import app

runner = CliRunner()


def test_cli_exposes_complete_workflow() -> None:
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    for command in (
        "corpus",
        "evaluate",
        "retrieve",
        "benchmark",
        "ingest",
        "review",
        "promote",
        "replay",
        "report",
        "serve",
        "demo",
    ):
        assert command in result.stdout


def test_demo_generates_replayable_evidence_and_review_state(tmp_path: Path) -> None:
    output = tmp_path / "demo"
    demo = runner.invoke(app, ["demo", "--output", str(output)])
    assert demo.exit_code == 0, demo.stdout
    summary = json.loads(demo.stdout)
    assert summary["exact_match_accuracy"] == 1.0
    for name in ("benchmark.json", "run.json", "evidence.json", "evidence.md"):
        assert (output / name).is_file()

    replay = runner.invoke(
        app,
        [
            "replay",
            "--record",
            str(output / "run.json"),
            "--database",
            str(output / "clinical-case-memory.duckdb"),
        ],
    )
    assert replay.exit_code == 0, replay.stdout
    assert json.loads(replay.stdout)["replayed"] is True

    packet = tmp_path / "packet.md"
    report = runner.invoke(
        app,
        ["report", "--record", str(output / "run.json"), "--output", str(packet)],
    )
    assert report.exit_code == 0
    assert packet.read_text().startswith("# Evidence Packet")


def test_cli_review_and_promotion(tmp_path: Path) -> None:
    database = tmp_path / "workflow.duckdb"
    ingested = runner.invoke(app, ["ingest", "--database", str(database), "--index", "1"])
    assert ingested.exit_code == 0, ingested.stdout
    result_id = json.loads(ingested.stdout)["result_id"]
    reviewed = runner.invoke(
        app,
        [
            "review",
            "--database",
            str(database),
            "--result-id",
            result_id,
            "--decision",
            "accepted",
            "--idempotency-key",
            "cli-review-001",
        ],
    )
    assert reviewed.exit_code == 0, reviewed.stdout
    review_id = json.loads(reviewed.stdout)["review_id"]
    promoted = runner.invoke(
        app,
        ["promote", "--database", str(database), "--review-id", review_id],
    )
    assert promoted.exit_code == 0, promoted.stdout
    assert len(json.loads(promoted.stdout)["promotion_id"]) == 64


def test_evaluate_rejects_invalid_case_index() -> None:
    result = runner.invoke(app, ["evaluate", "--index", "99"])
    assert result.exit_code != 0
    assert "between 0 and 35" in result.stderr
