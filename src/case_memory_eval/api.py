"""FastAPI review workflow for synthetic or explicitly redacted cases."""

from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated, Literal

from fastapi import FastAPI, HTTPException, Query, status
from fastapi.responses import HTMLResponse, PlainTextResponse
from pydantic import Field

from case_memory_eval.contracts import ClinicalCase, StrictModel
from case_memory_eval.evaluator import RuleEvaluator
from case_memory_eval.ui import CSS, HTML, JS
from case_memory_eval.workflow import WorkflowConflict, WorkflowNotFound, WorkflowStore


class IngestRequest(StrictModel):
    case: ClinicalCase
    declaration: Literal["synthetic", "redacted"]
    attested: Literal[True]
    actor: str = Field(min_length=2)


class ReviewRequest(StrictModel):
    reviewer: str = Field(min_length=2)
    decision: Literal["accepted", "rejected", "deferred"]
    rationale: str = Field(min_length=10)
    idempotency_key: str = Field(min_length=8)


class PromotionRequest(StrictModel):
    actor: str = Field(min_length=2)


def create_app(database_path: Path | str = "case-memory-eval.duckdb") -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):  # type: ignore[no-untyped-def]
        app.state.store = WorkflowStore(database_path)
        yield
        app.state.store.close()

    app = FastAPI(title="Clinical Case Memory Eval Lab", version="0.1.0", lifespan=lifespan)

    def store() -> WorkflowStore:
        return app.state.store  # type: ignore[no-any-return]

    @app.get("/", response_class=HTMLResponse)
    def reviewer_ui() -> str:
        return HTML

    @app.get("/assets/styles.css", response_class=PlainTextResponse)
    def reviewer_styles() -> PlainTextResponse:
        return PlainTextResponse(CSS, media_type="text/css")

    @app.get("/assets/app.js", response_class=PlainTextResponse)
    def reviewer_script() -> PlainTextResponse:
        return PlainTextResponse(JS, media_type="application/javascript")

    @app.get("/healthz")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.post("/cases")
    def ingest(request: IngestRequest) -> dict[str, object]:
        try:
            created = store().ingest(request.case, request.declaration, request.actor)
        except WorkflowConflict as error:
            raise HTTPException(status.HTTP_409_CONFLICT, str(error)) from error
        return {"case_id": request.case.case_id, "created": created}

    @app.post("/cases/{case_id}/evaluate")
    def evaluate(case_id: str) -> dict[str, object]:
        try:
            case = store().get_case(case_id)
        except WorkflowNotFound as error:
            raise HTTPException(status.HTTP_404_NOT_FOUND, str(error)) from error
        result = RuleEvaluator().evaluate(case)
        created = store().save_verdict(result)
        return {"result": result.model_dump(mode="json"), "created": created}

    @app.get("/reviews/queue")
    def queue() -> list[dict[str, object]]:
        return store().review_queue()

    @app.get("/reviews/{result_id}/diff")
    def diff(result_id: str) -> dict[str, object]:
        try:
            result = store().get_verdict(result_id)
        except WorkflowNotFound as error:
            raise HTTPException(status.HTTP_404_NOT_FOUND, str(error)) from error
        return {
            "case_id": result.case_id,
            "transcript": result.transcript,
            "note": result.note,
            "findings": [item.model_dump(mode="json") for item in result.findings],
        }

    @app.post("/reviews/{result_id}/decisions")
    def decide(result_id: str, request: ReviewRequest) -> dict[str, str]:
        try:
            review_id = store().decide(result_id, **request.model_dump())
        except WorkflowNotFound as error:
            raise HTTPException(status.HTTP_404_NOT_FOUND, str(error)) from error
        except WorkflowConflict as error:
            raise HTTPException(status.HTTP_409_CONFLICT, str(error)) from error
        return {"review_id": review_id, "decision": request.decision}

    @app.post("/reviews/{review_id}/promote")
    def promote(review_id: str, request: PromotionRequest) -> dict[str, str]:
        try:
            promotion_id = store().promote(review_id, request.actor)
        except WorkflowNotFound as error:
            raise HTTPException(status.HTTP_404_NOT_FOUND, str(error)) from error
        except WorkflowConflict as error:
            raise HTTPException(status.HTTP_409_CONFLICT, str(error)) from error
        return {"promotion_id": promotion_id}

    @app.get("/audit")
    def audit(
        verify: Annotated[bool, Query(description="Verify the full hash chain.")] = True,
    ) -> dict[str, object]:
        return {
            "chain_valid": store().verify_audit_chain() if verify else None,
            "events": store().audit_events(),
        }

    return app
