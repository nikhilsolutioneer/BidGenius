"""Real LangGraph/SQLite recovery tests with a bounded synthetic PDF parser."""
from pathlib import Path
from threading import Event
import time

from fastapi.testclient import TestClient

from tenderproof.main import create_app
from tenderproof.models import ExtractionBatch, PageRecord, Position, SourceSpan
from tenderproof.workflow import batch_usage

PACKAGE = Path(__file__).resolve().parents[1] / "Schulhaus_Oberglatt_Hackathon_Starter_Package_v2"


def test_usage_counts_known_cancelled_response_once_and_cached_resume_has_no_new_tokens():
    batch = ExtractionBatch(usage={"total_tokens": 120, "input_tokens_details": {"cached_tokens": 30}, "successful_ai_batches": 1})
    first = batch_usage({}, batch, cached=False)
    resumed = batch_usage(first, batch, cached=True)
    assert resumed["total_tokens"] == 120
    assert resumed["input_tokens_details"]["cached_tokens"] == 30
    assert resumed["successful_ai_batches"] == 1
    assert resumed["cached_ai_batches"] == 1
    assert first.get("cached_ai_batches") is None


def install_parser(monkeypatch, *, fail_second_once=False, second_batch_gate=None):
    from tenderproof import ingestion
    calls = {"parse": 0, "batches": [], "failed": False}
    def parse(path, document_id, progress=None):
        calls["parse"] += 1
        pages, spans = [], []
        for number in range(1, 9):
            span = SourceSpan(id=f"{document_id}-row-{number}", document_id=document_id, page=number,
                text="Zuluft - Tellerventil DN100 Stk 1", x0=50, top=100, x1=400, bottom=115,
                page_width=595, page_height=842, disposition="unresolved")
            pages.append(PageRecord(page=number, width=595, height=842, text=span.text,
                span_ids=[span.id], system="LA01"))
            spans.append(span)
            if progress:
                progress(number, 8)
        return pages, spans
    def extract(pages, spans, catalog):
        calls["batches"].append(pages[0].page)
        if second_batch_gate and pages[0].page == 5:
            entered, release = second_batch_gate
            entered.set()
            assert release.wait(10), "The test did not release extraction"
        if fail_second_once and pages[0].page == 5 and not calls["failed"]:
            calls["failed"] = True
            raise ValueError("Synthetic interruption after a persisted batch")
        return ExtractionBatch(positions=[Position(id=f"position-{s.page}", document_id=s.document_id,
            source_page=s.page, system="LA01", category="Air terminal", description=s.text,
            original_description=s.text, quantity="1", unit="pc", source_span_ids=[s.id],
            product_id="P-AIR-001", install_code="DIFFUSER", match_evidence_band="strong") for s in spans],
            dispositions={s.id: "position" for s in spans})
    monkeypatch.setattr(ingestion, "parse_pdf", parse)
    monkeypatch.setattr(ingestion, "extract_local_batch", extract)
    return calls


def wait_run(client, run_id):
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        response = client.get(f"/api/runs/{run_id}")
        assert response.status_code == 200
        run = response.json()
        if run["status"] not in {"queued", "running"}:
            return run
        time.sleep(0.02)
    raise AssertionError("Workflow did not reach a review or terminal state")


def start(client, project):
    response = client.post(f"/api/projects/{project}/runs", json={"use_ai": False})
    assert response.status_code == 202, response.text
    return response.json()["run_id"]


def test_real_checkpoint_survives_app_restart_and_duplicate_resume_is_idempotent(tmp_path, monkeypatch):
    calls = install_parser(monkeypatch)
    app = create_app(tmp_path)
    with TestClient(app) as client:
        project = app.state.service.create_project(PACKAGE)["id"]
        run_id = start(client, project)
        run = wait_run(client, run_id)
        assert run["status"] == "awaiting_review", run
        initial = client.get(f"/api/projects/{project}/summary").json()
        assert initial["revision"] == 1
        assert initial["coverage"]["positions_extracted"] == 8
    assert (tmp_path / "checkpoints.sqlite").is_file()
    restarted = create_app(tmp_path)
    with TestClient(restarted) as client:
        assert client.get(f"/api/runs/{run_id}").json()["status"] == "awaiting_review"
        stale = client.post(f"/api/runs/{run_id}/resume", json={"expected_revision": 0,
            "reason": "Review stale revision", "action": "continue"})
        assert stale.status_code == 409
        resumed = client.post(f"/api/runs/{run_id}/resume", json={"expected_revision": 1,
            "reason": "Continue as transparent draft", "action": "continue"})
        assert resumed.status_code == 202, resumed.text
        assert wait_run(client, run_id)["status"] == "complete"
        assert client.get(f"/api/projects/{project}/summary").json()["revision"] == 1
        duplicate = client.post(f"/api/runs/{run_id}/resume", json={"expected_revision": 1,
            "reason": "Repeat completed request", "action": "continue"})
        assert duplicate.status_code == 202
        assert duplicate.json()["status"] == "complete"
        assert len(client.get(f"/api/projects/{project}/revisions").json()) == 1
    assert calls["parse"] == 1
    assert calls["batches"] == [1, 5]


def test_single_active_job_and_cancellation_preserve_checkpoint(tmp_path, monkeypatch):
    entered, release = Event(), Event()
    calls = install_parser(monkeypatch, second_batch_gate=(entered, release))
    app = create_app(tmp_path)
    with TestClient(app) as client:
        project = app.state.service.create_project(PACKAGE)["id"]
        other = app.state.service.create_project(PACKAGE)["id"]
        run_id = start(client, project)
        try:
            assert entered.wait(10), "Extraction did not reach the second batch"
            active = client.post(f"/api/projects/{other}/runs", json={"use_ai": False})
            assert active.status_code == 409
            assert app.state.repo.project(other)["latest_run_id"] is None
            busy_edit = client.patch("/api/positions/position-1", json={"expected_revision": 0,
                "reason": "Attempt to edit while extraction is active", "changes": {"quantity": "5"}})
            assert busy_edit.status_code == 409
            cancelled = client.post(f"/api/runs/{run_id}/cancel")
            assert cancelled.status_code == 200
            assert cancelled.json()["cancellation_requested"] is True
        finally:
            release.set()
        stopped = wait_run(client, run_id)
        assert stopped["status"] == "cancelled", stopped
        assert stopped["pages_processed"] == 4
        assert client.get(f"/api/projects/{project}/positions").json()["total"] == 4
        assert client.get(f"/api/projects/{project}/summary").json()["revision"] == 0
    app = create_app(tmp_path)
    with TestClient(app) as client:
        resumed = client.post(f"/api/runs/{run_id}/resume", json={"expected_revision": 0,
            "reason": "Resume cancelled extraction using the saved checkpoint", "action": "continue"})
        assert resumed.status_code == 202, resumed.text
        completed = wait_run(client, run_id)
        assert completed["status"] == "awaiting_review", completed
        positions = client.get(f"/api/projects/{project}/positions").json()["items"]
        assert len(positions) == len({p["id"] for p in positions}) == 8
        assert client.get(f"/api/projects/{project}/summary").json()["revision"] == 1
    assert calls["parse"] == 1
    assert calls["batches"] == [1, 5]


def test_failed_batch_preserves_prior_work_and_resumes_after_restart(tmp_path, monkeypatch):
    calls = install_parser(monkeypatch, fail_second_once=True)
    app = create_app(tmp_path)
    with TestClient(app) as client:
        project = app.state.service.create_project(PACKAGE)["id"]
        run_id = start(client, project)
        run = wait_run(client, run_id)
        assert run["status"] == "failed"
        assert run["pages_processed"] == 4
        assert client.get(f"/api/projects/{project}/positions").json()["total"] == 4
    app = create_app(tmp_path)
    with TestClient(app) as client:
        response = client.post(f"/api/runs/{run_id}/resume", json={"expected_revision": 0,
            "reason": "Retry the interrupted extraction batch", "action": "continue"})
        assert response.status_code == 202, response.text
        run = wait_run(client, run_id)
        assert run["status"] == "awaiting_review", run
        positions = client.get(f"/api/projects/{project}/positions").json()["items"]
        assert len(positions) == len({p["id"] for p in positions}) == 8
        assert client.get(f"/api/projects/{project}/summary").json()["revision"] == 1
    assert calls["parse"] == 1
    assert calls["batches"] == [1, 5, 5]


def test_repeat_run_uses_cache_and_preserves_scope_override(tmp_path, monkeypatch):
    calls = install_parser(monkeypatch)
    app = create_app(tmp_path)
    with TestClient(app) as client:
        project = app.state.service.create_project(PACKAGE)["id"]
        first = start(client, project)
        assert wait_run(client, first)["status"] == "awaiting_review"
        edited = client.patch("/api/positions/position-1", json={"expected_revision": 1,
            "reason": "Confirmed package installation inclusion", "changes": {
                "description": "Confirmed supply air valve with package installation",
                "overrides": {"scope_inclusions": ["installation"]}}})
        assert edited.status_code == 200, edited.text
        assert edited.json()["position"]["cost"]["labour_cost_chf"] == "0.00"
        second = start(client, project)
        run = wait_run(client, second)
        assert run["status"] == "awaiting_review", run
        positions = client.get(f"/api/projects/{project}/positions").json()["items"]
        updated = next(p for p in positions if p["id"] == "position-1")
        assert updated["description"] == "Confirmed supply air valve with package installation"
        assert updated["attributes"]["inclusions"] == ["installation"]
        assert updated["cost"]["labour_cost_chf"] == "0.00"
        proposals = updated["attributes"]["ai_refinement_proposals"]
        assert any(p["changes"].get("description") == "Zuluft - Tellerventil DN100 Stk 1" for p in proposals)
        assert all(p["state"] == "pending" for p in proposals)
        assert run["usage"]["cached_batches"] == 2
        stale_run = client.post(f"/api/runs/{first}/resume", json={"expected_revision": 3,
            "reason": "Attempt to resume superseded run", "action": "continue"})
        assert stale_run.status_code == 409
    assert calls["parse"] == 1


def test_complete_review_skips_clean_calculated_rows_and_creates_one_approved_revision(tmp_path, monkeypatch):
    install_parser(monkeypatch)
    app = create_app(tmp_path)
    with TestClient(app) as client:
        project = app.state.service.create_project(PACKAGE)["id"]
        run_id = start(client, project)
        assert wait_run(client, run_id)["status"] == "awaiting_review"
        draft = client.get(f"/api/projects/{project}/summary").json()
        assert draft["coverage"]["pending_reviews"] == 0
        completed = client.post(f"/api/runs/{run_id}/resume", json={"expected_revision": 1,
            "reason": "No actionable estimator decisions remain", "action": "complete_review"})
        assert completed.status_code == 202, completed.text
        assert wait_run(client, run_id)["status"] == "complete"
        approved = client.get(f"/api/projects/{project}/summary").json()
        assert approved["revision"] == 2
        assert approved["review_complete"] is True
        duplicate = client.post(f"/api/runs/{run_id}/resume", json={"expected_revision": 2,
            "reason": "Retry successful completion request", "action": "complete_review"})
        assert duplicate.status_code == 202
        assert client.get(f"/api/projects/{project}/summary").json()["revision"] == 2
        snapshot = app.state.repo.revision(project, 2)
        assert snapshot["review_complete"] is True


def test_permanent_ai_failure_disables_remaining_requests_but_completes_local_pages(tmp_path, monkeypatch):
    from tenderproof import ai, ingestion
    install_parser(monkeypatch)
    local_extract = ingestion.extract_local_batch
    def unresolved_quantities(*args):
        batch = local_extract(*args)
        for position in batch.positions:
            position.quantity = None
        return batch
    monkeypatch.setattr(ingestion, "extract_local_batch", unresolved_quantities)
    monkeypatch.setenv("OPENAI_API_KEY", "offline-placeholder")
    calls = []
    class RejectedConfiguration(Exception):
        status_code = 400
    async def rejected(*args, **kwargs):
        calls.append(True)
        raise RejectedConfiguration("Never echo provider content or credentials")
    monkeypatch.setattr(ai, "extract_ai_batch", rejected)
    app = create_app(tmp_path)
    with TestClient(app) as client:
        project = app.state.service.create_project(PACKAGE)["id"]
        response = client.post(f"/api/projects/{project}/runs", json={"use_ai": True})
        assert response.status_code == 202
        run = wait_run(client, response.json()["run_id"])
        assert run["status"] == "awaiting_review"
        assert run["extraction_mode"] == "local_then_ai"
        assert run["pages_processed"] == 8
        assert len(calls) == 1
        assert run["usage"]["failed_ai_batches"] == 1
        assert run["usage"]["local_fallback_batches"] == 1
        assert run["usage"]["ai_disabled_configuration"] == 1
        assert "credentials" not in str(run["errors"])


def test_ai_source_reference_failure_is_explained_and_keeps_local_results(tmp_path, monkeypatch):
    from tenderproof import ai, ingestion
    install_parser(monkeypatch)
    local_extract = ingestion.extract_local_batch
    def unresolved_quantities(*args):
        batch = local_extract(*args)
        for position in batch.positions:
            position.quantity = None
        return batch
    monkeypatch.setattr(ingestion, "extract_local_batch", unresolved_quantities)
    monkeypatch.setenv("OPENAI_API_KEY", "offline-placeholder")
    calls = []
    async def invalid_evidence(*args, **kwargs):
        calls.append(True)
        raise ai.AIOutputValidationError("unknown_source_ids", "Unknown source IDs: invented-1")
    monkeypatch.setattr(ai, "extract_ai_batch", invalid_evidence)
    app = create_app(tmp_path)
    with TestClient(app) as client:
        project = app.state.service.create_project(PACKAGE)["id"]
        response = client.post(f"/api/projects/{project}/runs", json={"use_ai": True})
        assert response.status_code == 202
        run = wait_run(client, response.json()["run_id"])
        assert run["status"] == "awaiting_review"
        assert run["extraction_mode"] == "local_then_ai"
        assert len(calls) == 2
        assert run["usage"]["failed_ai_batches"] == 2
        assert run["usage"]["local_fallback_batches"] == 2
        assert all("unknown_source_ids" in error and "invented-1" in error and
            "Local extraction retained" in error for error in run["errors"]), run["errors"]
