"""Two-pass extraction preserves a complete local draft before bounded AI review."""
import asyncio
from io import BytesIO
from pathlib import Path
from threading import Event
import time
from zipfile import ZipFile

from fastapi.testclient import TestClient
import pytest

from tenderproof.main import create_app
from tenderproof.models import ExtractionBatch, PageRecord, Position, SourceSpan


PACKAGE = Path(__file__).resolve().parents[1] / "Schulhaus_Oberglatt_Hackathon_Starter_Package_v2"


@pytest.mark.parametrize("use_ai", [False, True])
def test_import_passes_selected_processing_mode_to_workflow(tmp_path, monkeypatch, use_ai):
    monkeypatch.setenv("OPENAI_API_KEY", "offline-test-placeholder")
    app = create_app(tmp_path)
    starts = []
    archive = BytesIO()
    with ZipFile(archive, "w") as package:
        for name in ("catalog.csv", "productivity.csv", "project_parameters.json"):
            package.writestr(name, (PACKAGE / name).read_bytes())
        package.writestr("source.pdf", b"%PDF-1.4\n% Import routing test; extraction is replaced.")
    with TestClient(app) as client:
        async def capture_start(project_id, selected):
            starts.append(selected)
            return {"project_id": project_id, "run_id": "stub-run"}
        monkeypatch.setattr(app.state.workflow, "start", capture_start)
        response = client.post("/api/projects/import", data={"use_ai": str(use_ai).lower()},
                               files={"files": ("tender.zip", archive.getvalue(), "application/zip")})
        assert response.status_code == 202, response.text
        assert starts == [use_ai]
        assert "local_then_ai" in client.get("/api/health").json()["processing_modes"]


def install_local_parser(monkeypatch, *, missing_quantities=(), omitted_pages=()):
    from tenderproof import ingestion

    calls = {"parse": 0, "local": [], "events": []}

    def parse(path, document_id, progress=None):
        calls["parse"] += 1
        pages, spans = [], []
        for number in range(1, 9):
            span = SourceSpan(
                id=f"{document_id}-row-{number}", document_id=document_id, page=number,
                text="Zuluft - Tellerventil DN100 Stk 1", x0=50, top=100, x1=400,
                bottom=115, page_width=595, page_height=842,
            )
            spans.append(span)
            pages.append(PageRecord(
                page=number, width=595, height=842, text=span.text,
                span_ids=[span.id], system="LA01" if number <= 4 else "LA02",
            ))
            if progress:
                progress(number, 8)
        return pages, spans

    def extract(pages, spans, catalog):
        calls["local"].append(pages[0].page)
        calls["events"].append(("local", pages[0].page))
        positions = [source_position(span, quantity=None if span.page in missing_quantities else "1")
                     for span in spans if span.page not in omitted_pages]
        covered = {source for row in positions for source in row.source_span_ids}
        return ExtractionBatch(
            positions=positions,
            dispositions={span.id: "position" if span.id in covered else "unresolved" for span in spans},
        )

    monkeypatch.setattr(ingestion, "parse_pdf", parse)
    monkeypatch.setattr(ingestion, "extract_local_batch", extract)
    monkeypatch.setenv("OPENAI_API_KEY", "offline-test-placeholder")
    return calls


def source_position(span, *, quantity="1"):
    return Position(
        id=f"position-{span.page}", document_id=span.document_id, source_page=span.page,
        system="LA01" if span.page <= 4 else "LA02", category="Air terminal",
        description=span.text, original_description=span.text, quantity=quantity, unit="pc",
        source_span_ids=[span.id], product_id="P-AIR-001", install_code="DIFFUSER",
        pricing_basis="catalogue", match_evidence_band="strong",
    )


def reviewed_batch(local_batch):
    batch = local_batch.model_copy(deep=True)
    for position in batch.positions:
        if position.quantity is None:
            position.quantity = "1"
    batch.usage = {"total_tokens": 120, "input_tokens": 100, "output_tokens": 20}
    return batch


def start_hybrid(client, project_id):
    response = client.post(f"/api/projects/{project_id}/runs", json={"use_ai": True})
    assert response.status_code == 202, response.text
    return response.json()["run_id"]


def wait_run(client, run_id):
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        response = client.get(f"/api/runs/{run_id}")
        assert response.status_code == 200
        run = response.json()
        if run["status"] not in {"queued", "running"}:
            return run
        time.sleep(0.02)
    raise AssertionError("Hybrid workflow did not reach a review or terminal state")


def test_all_local_pages_finish_before_ai_receives_targeted_gaps(tmp_path, monkeypatch):
    from tenderproof import ai

    calls = install_local_parser(monkeypatch, missing_quantities={2})
    reviews = []
    app = create_app(tmp_path)

    async def review(pages, spans, catalog, model, *, local_batch, review):
        calls["events"].append(("ai", pages[0].page))
        assert calls["local"] == [1, 5], "AI started before the complete local pass"
        saved = app.state.repo.project(project_id)
        assert {row["id"] for row in saved["positions"]} == {f"position-{n}" for n in range(1, 9)}
        progress = app.state.repo.run(saved["latest_run_id"])
        assert progress["pages_processed"] == progress["total_pages"] == 8
        assert progress["local_positions_found"] == 8
        assert review["position_ids"] == ["position-2"]
        assert review["target_source_ids"] == [f"{saved['document']['id']}-row-2"]
        assert any(reason["kind"] == "missing_quantity" and reason["field"] == "quantity"
                   for reason in review["reasons"])
        target = next(row for row in local_batch.positions if row.id == "position-2")
        assert target.quantity is None
        reviews.append(review)
        return reviewed_batch(local_batch)

    monkeypatch.setattr(ai, "extract_ai_batch", review)
    with TestClient(app) as client:
        project_id = app.state.service.create_project(PACKAGE)["id"]
        run = wait_run(client, start_hybrid(client, project_id))
        assert run["status"] == "awaiting_review", run
        assert run["extraction_mode"] == "local_then_ai"
        assert len(reviews) == 1
        assert run["ai_batches_done"] == run["ai_batches_total"] == 1
        positions = client.get(f"/api/projects/{project_id}/positions").json()["items"]
        assert len(positions) == 8
        assert next(row for row in positions if row["id"] == "position-2")["quantity"] == "1"
        assert run["usage"]["total_tokens"] == 120
    assert calls["events"][:2] == [("local", 1), ("local", 5)]


def test_fully_identified_local_positions_skip_all_model_requests(tmp_path, monkeypatch):
    from tenderproof import ai

    calls = install_local_parser(monkeypatch)
    model_calls = []

    async def unexpected_model_request(*args, **kwargs):
        model_calls.append(True)
        raise AssertionError("Clean local extraction must not be sent to the model")

    monkeypatch.setattr(ai, "extract_ai_batch", unexpected_model_request)
    app = create_app(tmp_path)
    with TestClient(app) as client:
        project_id = app.state.service.create_project(PACKAGE)["id"]
        run = wait_run(client, start_hybrid(client, project_id))
        assert run["status"] == "awaiting_review", run
        assert run["local_positions_found"] == run["positions_found"] == 8
        assert run["ai_batches_done"] == run["ai_batches_total"] == 0
        assert run["usage"].get("total_tokens", 0) == 0
        assert not run["errors"]
        assert client.get(f"/api/projects/{project_id}/positions").json()["total"] == 8
    assert model_calls == []
    assert calls["local"] == [1, 5]


def test_uncovered_source_is_reviewed_and_recovered_without_losing_local_rows(tmp_path, monkeypatch):
    from tenderproof import ai

    calls = install_local_parser(monkeypatch, omitted_pages={6})
    reviews = []

    async def recover(pages, spans, catalog, model, *, local_batch, review):
        assert calls["local"] == [1, 5]
        source = next(span for span in spans if span.page == 6)
        assert review["target_source_ids"] == [source.id]
        assert review["position_ids"] == []
        assert review["reasons"]
        assert all(source.id in reason["source_span_ids"] for reason in review["reasons"])
        batch = reviewed_batch(local_batch)
        batch.positions.append(source_position(source))
        batch.dispositions[source.id] = "position"
        reviews.append(review)
        return batch

    monkeypatch.setattr(ai, "extract_ai_batch", recover)
    app = create_app(tmp_path)
    with TestClient(app) as client:
        project_id = app.state.service.create_project(PACKAGE)["id"]
        run = wait_run(client, start_hybrid(client, project_id))
        assert run["status"] == "awaiting_review", run
        assert run["local_positions_found"] == 7
        assert run["positions_found"] == 8
        assert len(reviews) == 1
        positions = client.get(f"/api/projects/{project_id}/positions").json()["items"]
        assert {row["id"] for row in positions} == {f"position-{n}" for n in range(1, 9)}
        summary = client.get(f"/api/projects/{project_id}/summary").json()
        assert summary["coverage"]["positions_extracted"] == 8


@pytest.mark.parametrize("permanent", [False, True], ids=["invalid-evidence", "rejected-configuration"])
def test_model_failures_keep_every_local_position_and_report_reason(tmp_path, monkeypatch, permanent):
    from tenderproof import ai

    calls = install_local_parser(monkeypatch, missing_quantities={2, 6})
    model_calls = []

    class RejectedConfiguration(Exception):
        status_code = 400

    async def fail(pages, spans, catalog, model, *, local_batch, review):
        assert calls["local"] == [1, 5]
        model_calls.append(review)
        if permanent:
            raise RejectedConfiguration("provider-secret-must-not-be-exposed")
        raise ai.AIOutputValidationError("unknown_source_ids", "Unknown source IDs: invented-source")

    monkeypatch.setattr(ai, "extract_ai_batch", fail)
    app = create_app(tmp_path)
    with TestClient(app) as client:
        project_id = app.state.service.create_project(PACKAGE)["id"]
        run = wait_run(client, start_hybrid(client, project_id))
        assert run["status"] == "awaiting_review", run
        assert run["pages_processed"] == run["total_pages"] == 8
        assert run["local_positions_found"] == run["positions_found"] == 8
        assert len(model_calls) == (1 if permanent else 2)
        assert run["usage"]["failed_ai_batches"] == len(model_calls)
        errors = " ".join(run["errors"])
        assert errors
        assert "provider-secret-must-not-be-exposed" not in errors
        if permanent:
            assert run["usage"]["ai_disabled_configuration"] == 1
        else:
            assert "unknown_source_ids" in errors and "invented-source" in errors
        positions = client.get(f"/api/projects/{project_id}/positions").json()["items"]
        assert {row["id"] for row in positions} == {f"position-{n}" for n in range(1, 9)}
        assert all(row["quantity"] is None for row in positions if row["id"] in {"position-2", "position-6"})


def test_cancelled_ai_review_resumes_from_cached_response_after_restart(tmp_path, monkeypatch):
    from tenderproof import ai

    calls = install_local_parser(monkeypatch, missing_quantities={2})
    entered, release = Event(), Event()
    model_calls = []

    async def gated_review(pages, spans, catalog, model, *, local_batch, review):
        model_calls.append(review)
        entered.set()
        assert await asyncio.to_thread(release.wait, 10), "The test did not release AI review"
        return reviewed_batch(local_batch)

    monkeypatch.setattr(ai, "extract_ai_batch", gated_review)
    app = create_app(tmp_path)
    with TestClient(app) as client:
        project_id = app.state.service.create_project(PACKAGE)["id"]
        run_id = start_hybrid(client, project_id)
        try:
            assert entered.wait(10), "Workflow did not reach AI review"
            response = client.post(f"/api/runs/{run_id}/cancel")
            assert response.status_code == 200, response.text
        finally:
            release.set()
        stopped = wait_run(client, run_id)
        assert stopped["status"] == "cancelled", stopped
        assert stopped["pages_processed"] == 8
        assert stopped["local_positions_found"] == 8
        assert client.get(f"/api/projects/{project_id}/positions").json()["total"] == 8
        assert stopped["usage"]["total_tokens"] == 120

    restarted = create_app(tmp_path)
    with TestClient(restarted) as client:
        response = client.post(f"/api/runs/{run_id}/resume", json={
            "expected_revision": 0, "reason": "Resume targeted review after cancellation", "action": "continue",
        })
        assert response.status_code == 202, response.text
        run = wait_run(client, run_id)
        assert run["status"] == "awaiting_review", run
        assert run["ai_batches_done"] == run["ai_batches_total"] == 1
        assert run["usage"]["total_tokens"] == 120
        assert run["usage"]["cached_ai_batches"] == 1
        rows = client.get(f"/api/projects/{project_id}/positions").json()["items"]
        assert len(rows) == len({row["id"] for row in rows}) == 8
        assert next(row for row in rows if row["id"] == "position-2")["quantity"] == "1"
    assert len(model_calls) == 1
    assert calls["parse"] == 1
    assert calls["local"] == [1, 5]


def test_repeated_hybrid_run_reuses_local_and_review_results(tmp_path, monkeypatch):
    from tenderproof import ai

    calls = install_local_parser(monkeypatch, missing_quantities={2})
    model_calls = []

    async def review(pages, spans, catalog, model, *, local_batch, review):
        model_calls.append(review)
        return reviewed_batch(local_batch)

    monkeypatch.setattr(ai, "extract_ai_batch", review)
    app = create_app(tmp_path)
    with TestClient(app) as client:
        project_id = app.state.service.create_project(PACKAGE)["id"]
        first = wait_run(client, start_hybrid(client, project_id))
        assert first["status"] == "awaiting_review", first
        second = wait_run(client, start_hybrid(client, project_id))
        assert second["status"] == "awaiting_review", second
        assert second["local_positions_found"] == second["positions_found"] == 8
        assert second["ai_batches_done"] == second["ai_batches_total"] == 1
        assert second["usage"].get("total_tokens", 0) == 0
        assert second["usage"]["cached_ai_batches"] == 1
        assert client.get(f"/api/projects/{project_id}/positions").json()["total"] == 8
    assert len(model_calls) == 1
    assert calls["parse"] == 1
    assert calls["local"] == [1, 5]


def test_accepted_position_is_restored_before_uncovered_sources_are_sent_to_ai(tmp_path, monkeypatch):
    from tenderproof import ai, workflow
    install_local_parser(monkeypatch)
    requests = []

    async def unexpected(*args, **kwargs):
        requests.append(True)
        raise AssertionError("Accepted source must remain protected during triage")

    monkeypatch.setattr(ai, "extract_ai_batch", unexpected)
    app = create_app(tmp_path)
    with TestClient(app) as client:
        project_id = app.state.service.create_project(PACKAGE)["id"]
        assert wait_run(client, start_hybrid(client, project_id))["status"] == "awaiting_review"
        accepted = client.patch("/api/positions/position-6", json={"expected_revision": 1,
            "reason": "Confirmed the original source scope", "changes": {"review_state": "accepted"}})
        assert accepted.status_code == 200, accepted.text
        install_local_parser(monkeypatch, omitted_pages={6})
        monkeypatch.setattr(workflow, "PARSER_VERSION", "test-rediscovery-change")
        run = wait_run(client, start_hybrid(client, project_id))
        assert run["status"] == "awaiting_review", run
        assert run["local_positions_found"] == 7
        assert run["positions_found"] == 8
        assert run["ai_batches_total"] == 0
        assert requests == []
        saved = app.state.repo.project(project_id)
        assert saved["run_provenance"]["positions_found"] == 8
        assert next(row for row in saved["positions"] if row["id"] == "position-6")["review_state"] == "accepted"
