from pathlib import Path

from fastapi.testclient import TestClient

from case_memory_eval.api import create_app
from case_memory_eval.corpus import build_corpus


def _ingest(client: TestClient, index: int = 1) -> tuple[str, str]:
    case = build_corpus().cases[index]
    payload = {
        "case": case.model_dump(mode="json"),
        "declaration": "synthetic",
        "attested": True,
        "actor": "test-suite",
    }
    response = client.post("/cases", json=payload)
    assert response.status_code == 200
    evaluated = client.post(f"/cases/{case.case_id}/evaluate")
    assert evaluated.status_code == 200
    return case.case_id, evaluated.json()["result"]["result_id"]


def test_complete_review_and_promotion_workflow(tmp_path: Path) -> None:
    with TestClient(create_app(tmp_path / "workflow.duckdb")) as client:
        case_id, result_id = _ingest(client)
        queue = client.get("/reviews/queue").json()
        assert queue[0]["case_id"] == case_id
        diff = client.get(f"/reviews/{result_id}/diff").json()
        assert diff["transcript"] and diff["note"] and diff["findings"]
        review = client.post(
            f"/reviews/{result_id}/decisions",
            json={
                "reviewer": "reviewer@example.test",
                "decision": "accepted",
                "rationale": "The cited evidence supports this evaluation finding.",
                "idempotency_key": "review-case-1",
            },
        )
        assert review.status_code == 200
        promotion = client.post(
            f"/reviews/{review.json()['review_id']}/promote",
            json={"actor": "reviewer@example.test"},
        )
        assert promotion.status_code == 200
        assert client.get("/reviews/queue").json() == []
        audit = client.get("/audit").json()
        assert audit["chain_valid"] is True
        assert [item["event_type"] for item in audit["events"]] == [
            "case.ingested",
            "verdict.created",
            "review.decided",
            "memory.promoted",
        ]


def test_ingestion_and_evaluation_are_idempotent(tmp_path: Path) -> None:
    case = build_corpus().cases[0]
    payload = {
        "case": case.model_dump(mode="json"),
        "declaration": "synthetic",
        "attested": True,
        "actor": "test-suite",
    }
    with TestClient(create_app(tmp_path / "workflow.duckdb")) as client:
        assert client.post("/cases", json=payload).json()["created"] is True
        assert client.post("/cases", json=payload).json()["created"] is False
        first = client.post(f"/cases/{case.case_id}/evaluate").json()
        second = client.post(f"/cases/{case.case_id}/evaluate").json()
        assert first["result"] == second["result"]
        assert second["created"] is False


def test_review_idempotency_conflict_fails_closed(tmp_path: Path) -> None:
    with TestClient(create_app(tmp_path / "workflow.duckdb")) as client:
        _, result_id = _ingest(client)
        payload = {
            "reviewer": "reviewer@example.test",
            "decision": "accepted",
            "rationale": "The cited evidence supports this evaluation finding.",
            "idempotency_key": "same-key-123",
        }
        first = client.post(f"/reviews/{result_id}/decisions", json=payload)
        assert first.status_code == 200
        assert client.post(f"/reviews/{result_id}/decisions", json=payload).json() == first.json()
        payload["decision"] = "rejected"
        assert client.post(f"/reviews/{result_id}/decisions", json=payload).status_code == 409


def test_rejected_review_cannot_promote(tmp_path: Path) -> None:
    with TestClient(create_app(tmp_path / "workflow.duckdb")) as client:
        _, result_id = _ingest(client)
        review = client.post(
            f"/reviews/{result_id}/decisions",
            json={
                "reviewer": "reviewer@example.test",
                "decision": "rejected",
                "rationale": "The evidence does not support promotion into memory.",
                "idempotency_key": "reject-key-1",
            },
        ).json()
        response = client.post(
            f"/reviews/{review['review_id']}/promote", json={"actor": "reviewer@example.test"}
        )
        assert response.status_code == 409


def test_state_and_audit_chain_persist_across_restart(tmp_path: Path) -> None:
    path = tmp_path / "workflow.duckdb"
    with TestClient(create_app(path)) as client:
        case_id, result_id = _ingest(client)
    with TestClient(create_app(path)) as client:
        assert client.get("/healthz").json() == {"status": "ok"}
        assert client.get(f"/reviews/{result_id}/diff").json()["case_id"] == case_id
        assert client.get("/audit").json()["chain_valid"] is True


def test_missing_attestation_and_resources_are_rejected(tmp_path: Path) -> None:
    case = build_corpus().cases[0]
    with TestClient(create_app(tmp_path / "workflow.duckdb")) as client:
        response = client.post(
            "/cases",
            json={
                "case": case.model_dump(mode="json"),
                "declaration": "synthetic",
                "attested": False,
                "actor": "test-suite",
            },
        )
        assert response.status_code == 422
        assert client.post("/cases/missing/evaluate").status_code == 404
        assert client.get("/reviews/missing/diff").status_code == 404
        assert (
            client.post(
                "/reviews/missing/promote", json={"actor": "reviewer@example.test"}
            ).status_code
            == 404
        )
