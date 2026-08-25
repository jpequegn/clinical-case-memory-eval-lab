"""Durable review workflow and hash-chained audit persistence."""

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

import duckdb

from case_memory_eval.canonical import canonical_json, content_id
from case_memory_eval.contracts import ClinicalCase
from case_memory_eval.evaluator import EvaluationArtifact
from case_memory_eval.memory import ReviewedCaseMemory

ReviewDecision = Literal["accepted", "rejected", "deferred"]
DataDeclaration = Literal["synthetic", "redacted"]


class WorkflowConflict(ValueError):
    pass


class WorkflowNotFound(LookupError):
    pass


def _now() -> str:
    return datetime.now(UTC).isoformat()


class WorkflowStore:
    def __init__(self, path: Path | str) -> None:
        self.path = str(path)
        self.connection = duckdb.connect(self.path)
        self.memory = ReviewedCaseMemory(path)
        self.connection.execute(
            """
            CREATE TABLE IF NOT EXISTS cases (
                case_id VARCHAR PRIMARY KEY,
                case_json VARCHAR NOT NULL,
                declaration VARCHAR NOT NULL,
                ingested_at VARCHAR NOT NULL
            );
            CREATE TABLE IF NOT EXISTS verdicts (
                result_id VARCHAR PRIMARY KEY,
                case_id VARCHAR NOT NULL,
                result_json VARCHAR NOT NULL,
                created_at VARCHAR NOT NULL
            );
            CREATE TABLE IF NOT EXISTS reviews (
                review_id VARCHAR PRIMARY KEY,
                idempotency_key VARCHAR UNIQUE NOT NULL,
                result_id VARCHAR NOT NULL,
                reviewer VARCHAR NOT NULL,
                decision VARCHAR NOT NULL,
                rationale VARCHAR NOT NULL,
                reviewed_at VARCHAR NOT NULL
            );
            CREATE TABLE IF NOT EXISTS promotions (
                promotion_id VARCHAR PRIMARY KEY,
                review_id VARCHAR UNIQUE NOT NULL,
                case_id VARCHAR NOT NULL,
                actor VARCHAR NOT NULL,
                promoted_at VARCHAR NOT NULL
            );
            CREATE TABLE IF NOT EXISTS audit_log (
                sequence BIGINT PRIMARY KEY,
                event_id VARCHAR UNIQUE NOT NULL,
                previous_hash VARCHAR NOT NULL,
                event_hash VARCHAR NOT NULL,
                event_type VARCHAR NOT NULL,
                actor VARCHAR NOT NULL,
                payload_json VARCHAR NOT NULL,
                created_at VARCHAR NOT NULL
            )
            """
        )

    def close(self) -> None:
        self.memory.close()
        self.connection.close()

    def ingest(self, case: ClinicalCase, declaration: DataDeclaration, actor: str = "api") -> bool:
        if declaration == "synthetic" and not case.provenance.synthetic:
            raise WorkflowConflict("synthetic declaration conflicts with case provenance")
        serialized = canonical_json(case.model_dump(mode="json"))
        existing = self.connection.execute(
            "SELECT case_json, declaration FROM cases WHERE case_id = ?", [case.case_id]
        ).fetchone()
        if existing:
            if existing != (serialized, declaration):
                raise WorkflowConflict("case identity already exists with conflicting content")
            return False
        self.connection.execute(
            "INSERT INTO cases VALUES (?, ?, ?, ?)",
            [case.case_id, serialized, declaration, _now()],
        )
        self._audit("case.ingested", actor, {"case_id": case.case_id, "declaration": declaration})
        return True

    def get_case(self, case_id: str) -> ClinicalCase:
        row = self.connection.execute(
            "SELECT case_json FROM cases WHERE case_id = ?", [case_id]
        ).fetchone()
        if not row:
            raise WorkflowNotFound("case not found")
        return ClinicalCase.model_validate_json(row[0])

    def save_verdict(self, result: EvaluationArtifact, actor: str = "evaluator") -> bool:
        if self.get_case(result.case_id).case_id != result.case_id:
            raise WorkflowConflict("verdict case identity does not match")
        serialized = canonical_json(result.model_dump(mode="json"))
        row = self.connection.execute(
            "SELECT result_json FROM verdicts WHERE result_id = ?", [result.result_id]
        ).fetchone()
        if row:
            if row[0] != serialized:
                raise WorkflowConflict("result identity already exists with conflicting content")
            return False
        self.connection.execute(
            "INSERT INTO verdicts VALUES (?, ?, ?, ?)",
            [result.result_id, result.case_id, serialized, _now()],
        )
        self._audit(
            "verdict.created",
            actor,
            {"case_id": result.case_id, "result_id": result.result_id},
        )
        return True

    def get_verdict(self, result_id: str) -> EvaluationArtifact:
        row = self.connection.execute(
            "SELECT result_json FROM verdicts WHERE result_id = ?", [result_id]
        ).fetchone()
        if not row:
            raise WorkflowNotFound("verdict not found")
        return EvaluationArtifact.model_validate_json(row[0])

    def review_queue(self) -> list[dict[str, object]]:
        rows = self.connection.execute(
            """
            SELECT v.result_id, v.case_id, c.case_json, v.result_json
            FROM verdicts v
            JOIN cases c ON c.case_id = v.case_id
            LEFT JOIN reviews r
              ON r.result_id = v.result_id
             AND r.decision IN ('accepted', 'rejected')
            WHERE r.review_id IS NULL
            ORDER BY v.created_at, v.result_id
            """
        ).fetchall()
        queue = []
        for result_id, case_id, case_json, result_json in rows:
            case = ClinicalCase.model_validate_json(case_json)
            precedents = self.memory.retrieve(case, top_k=3).precedents
            queue.append(
                {
                    "result_id": result_id,
                    "case_id": case_id,
                    "case": case.model_dump(mode="json"),
                    "verdict": json.loads(result_json),
                    "precedents": [item.model_dump(mode="json") for item in precedents],
                }
            )
        return queue

    def decide(
        self,
        result_id: str,
        *,
        reviewer: str,
        decision: ReviewDecision,
        rationale: str,
        idempotency_key: str,
    ) -> str:
        self.get_verdict(result_id)
        payload = {
            "result_id": result_id,
            "reviewer": reviewer,
            "decision": decision,
            "rationale": rationale,
            "idempotency_key": idempotency_key,
        }
        review_id = content_id(payload)
        existing = self.connection.execute(
            "SELECT review_id, result_id, reviewer, decision, rationale FROM reviews "
            "WHERE idempotency_key = ?",
            [idempotency_key],
        ).fetchone()
        if existing:
            expected = (review_id, result_id, reviewer, decision, rationale)
            if existing != expected:
                raise WorkflowConflict("idempotency key was reused with different review content")
            return review_id
        self.connection.execute(
            "INSERT INTO reviews VALUES (?, ?, ?, ?, ?, ?, ?)",
            [review_id, idempotency_key, result_id, reviewer, decision, rationale, _now()],
        )
        self._audit("review.decided", reviewer, {**payload, "review_id": review_id})
        return review_id

    def promote(self, review_id: str, actor: str) -> str:
        row = self.connection.execute(
            """
            SELECT r.decision, v.case_id, c.case_json
            FROM reviews r
            JOIN verdicts v ON v.result_id = r.result_id
            JOIN cases c ON c.case_id = v.case_id
            WHERE r.review_id = ?
            """,
            [review_id],
        ).fetchone()
        if not row:
            raise WorkflowNotFound("review not found")
        decision, case_id, case_json = row
        if decision != "accepted":
            raise WorkflowConflict("only accepted reviews can be promoted")
        promotion_id = content_id({"review_id": review_id, "case_id": case_id})
        existing = self.connection.execute(
            "SELECT promotion_id FROM promotions WHERE review_id = ?", [review_id]
        ).fetchone()
        if existing:
            return str(existing[0])
        case = ClinicalCase.model_validate_json(case_json)
        self.memory.add(case, split="train", intervention="accepted", promoted=True)
        self.connection.execute(
            "INSERT INTO promotions VALUES (?, ?, ?, ?, ?)",
            [promotion_id, review_id, case_id, actor, _now()],
        )
        self._audit(
            "memory.promoted",
            actor,
            {"promotion_id": promotion_id, "review_id": review_id, "case_id": case_id},
        )
        return promotion_id

    def audit_events(self) -> list[dict[str, object]]:
        rows = self.connection.execute(
            "SELECT sequence, event_id, previous_hash, event_hash, event_type, actor, "
            "payload_json, created_at FROM audit_log ORDER BY sequence"
        ).fetchall()
        events = []
        for row in rows:
            sequence, event_id, previous_hash, event_hash = row[:4]
            event_type, actor, payload, created_at = row[4:]
            events.append(
                {
                    "sequence": sequence,
                    "event_id": event_id,
                    "previous_hash": previous_hash,
                    "event_hash": event_hash,
                    "event_type": event_type,
                    "actor": actor,
                    "payload": json.loads(payload),
                    "created_at": created_at,
                }
            )
        return events

    def verify_audit_chain(self) -> bool:
        previous = "0" * 64
        for event in self.audit_events():
            if event["previous_hash"] != previous:
                return False
            payload = {
                key: event[key]
                for key in (
                    "sequence",
                    "event_id",
                    "previous_hash",
                    "event_type",
                    "actor",
                    "payload",
                    "created_at",
                )
            }
            if content_id(payload) != event["event_hash"]:
                return False
            previous = str(event["event_hash"])
        return True

    def _audit(self, event_type: str, actor: str, payload: dict[str, object]) -> None:
        row = self.connection.execute(
            "SELECT sequence, event_hash FROM audit_log ORDER BY sequence DESC LIMIT 1"
        ).fetchone()
        sequence = 1 if row is None else int(row[0]) + 1
        previous_hash = "0" * 64 if row is None else str(row[1])
        created_at = _now()
        event_id = content_id(
            {"sequence": sequence, "event_type": event_type, "actor": actor, "payload": payload}
        )
        event = {
            "sequence": sequence,
            "event_id": event_id,
            "previous_hash": previous_hash,
            "event_type": event_type,
            "actor": actor,
            "payload": payload,
            "created_at": created_at,
        }
        event_hash = content_id(event)
        self.connection.execute(
            "INSERT INTO audit_log VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            [
                sequence,
                event_id,
                previous_hash,
                event_hash,
                event_type,
                actor,
                canonical_json(payload),
                created_at,
            ],
        )
