import socket
import threading
import time
from pathlib import Path

import pytest
import uvicorn
from playwright.sync_api import expect, sync_playwright

from case_memory_eval.api import create_app
from case_memory_eval.corpus import build_corpus
from case_memory_eval.evaluator import RuleEvaluator
from case_memory_eval.workflow import WorkflowStore


def _free_port() -> int:
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        return int(listener.getsockname()[1])


@pytest.mark.browser
def test_reviewer_can_inspect_accept_and_promote_in_a_browser(tmp_path: Path) -> None:
    database = tmp_path / "browser.duckdb"
    case = build_corpus().cases[1]
    store = WorkflowStore(database)
    store.ingest(case, "synthetic", "browser-test")
    store.save_verdict(RuleEvaluator().evaluate(case), "browser-test")
    store.close()

    port = _free_port()
    server = uvicorn.Server(
        uvicorn.Config(create_app(database), host="127.0.0.1", port=port, log_level="error")
    )
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    deadline = time.monotonic() + 10
    while not server.started and time.monotonic() < deadline:
        time.sleep(0.02)
    assert server.started
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            page = browser.new_page(viewport={"width": 1280, "height": 820})
            page.goto(f"http://127.0.0.1:{port}/")
            expect(
                page.get_by_role("heading", name="Clinical Case Memory Eval Lab")
            ).to_be_visible()
            expect(page.locator("#queue-count")).to_have_text("1")
            expect(page.locator("#transcript")).to_contain_text("fictional patient")
            expect(page.locator("#findings")).to_contain_text("omission")
            page.get_by_role("button", name="Accept and promote").click()
            expect(page.locator("#queue-count")).to_have_text("0")
            browser.close()
    finally:
        server.should_exit = True
        thread.join(timeout=10)
    persisted = WorkflowStore(database)
    assert [item["event_type"] for item in persisted.audit_events()][-2:] == [
        "review.decided",
        "memory.promoted",
    ]
    persisted.close()
