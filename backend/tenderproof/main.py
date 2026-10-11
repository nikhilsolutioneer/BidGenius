"""Local HTTP application. Run with: python -m uvicorn tenderproof.main:app."""
from __future__ import annotations

from contextlib import asynccontextmanager
import asyncio
import io
import json
import logging
from pathlib import Path
import tempfile
import zipfile

from fastapi import Body, FastAPI, File, Form, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from pydantic import ValidationError

from . import __version__
from .config import ROOT, STARTER, ai_configured, data_directory, model_name
from .exports import create_export
from .models import (AdjustmentCreate, AdjustmentPatch, AssumptionsPatch, ExportRequest, ManualPositionCreate,
                     PositionPatch, ResumeRequest, RevisionMutation, ScenarioRequest, StartRunRequest,
                     WhatIfPreviewRequest)
from .service import EstimateService, identifier
from .storage import DomainError, InstanceLock, Repository
from .workflow import WorkflowManager
from .commercial import (CommercialPatch, HistoricalImport, HistoricalPreview, ScenarioSave,
                         apply_commercial, commercial_view, import_history, patch_commercial,
                         preview_history, state as commercial_state, SCENARIO_KEYS)
from .assistant import AssistantRequest, chat as assistant_chat


def create_app(directory: Path | None = None) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        local_directory = directory or data_directory()
        lock = InstanceLock(local_directory)
        lock.acquire()
        repo = None
        try:
            repo = Repository(local_directory)
            repo.recover_runs()
            app.state.repo = repo
            app.state.service = EstimateService(repo)
            async with AsyncSqliteSaver.from_conn_string(str(repo.directory / "checkpoints.sqlite")) as saver:
                await saver.setup()
                app.state.workflow = WorkflowManager(repo, app.state.service, saver)
                try:
                    yield
                finally:
                    await app.state.workflow.shutdown()
        finally:
            if repo:
                repo.close()
            lock.release()

    app = FastAPI(title="TenderProof", version=__version__, lifespan=lifespan, docs_url=None, redoc_url=None)
    app.add_middleware(CORSMiddleware, allow_origins=["http://127.0.0.1:5173", "http://localhost:5173", "http://127.0.0.1:8000", "http://localhost:8000"], allow_methods=["GET", "POST", "PATCH"], allow_headers=["Content-Type"])

    @app.exception_handler(DomainError)
    async def domain_error(_, exc: DomainError):
        return JSONResponse(status_code=exc.status, content={"detail": exc.detail or exc.message})

    @app.exception_handler(ValueError)
    async def invalid_value(_, exc: ValueError):
        return JSONResponse(status_code=422, content={"detail": str(exc)})

    @app.get("/api/health")
    async def health():
        return {"status": "ok", "version": __version__, "ai_configured": ai_configured(), "model": model_name(),
                "processing_modes": ["local", "local_then_ai"]}

    @app.post("/api/assistant/chat")
    async def assistant(request: Request, body: AssistantRequest):
        return await assistant_chat(request, body)

    @app.get("/api/projects")
    async def projects(request: Request):
        return [request.app.state.service.public_project(p) for p in request.app.state.repo.projects()]

    @app.patch("/api/projects/{project_id}/meta")
    async def project_meta(request: Request, project_id: str, body: dict = Body(...)):
        project = request.app.state.repo.project(project_id)
        if "reason" not in body:
            raise DomainError("A reason is required.")
        changes = {key: body[key] for key in ("estimator", "bid_status") if key in body}
        return request.app.state.service.patch_meta(project_id, project["revision"], body["reason"], changes, request.headers.get("X-Actor"))

    @app.post("/api/projects/{project_id}/duplicate")
    async def duplicate_project(request: Request, project_id: str, body: dict = Body(...)):
        from copy import deepcopy
        source = request.app.state.repo.project(project_id)
        if not body.get("name") or not body.get("estimator"):
            raise DomainError("Name and estimator are required.")
        clone = deepcopy(source)
        clone["id"] = identifier("project"); clone["document"]["id"] = identifier("doc")
        clone["name"] = body["name"]; clone["estimator"] = body["estimator"]; clone["bid_status"] = "draft"; clone["revision"] = 1
        clone["history"] = [{"id": identifier("decision"), "actor": request.headers.get("X-Actor", "Local estimator"), "timestamp": clone["updated_at"], "reason": f"duplicated from {project_id}", "entity_type": "project", "entity_id": clone["id"], "old_value": None, "new_value": {"source_project_id": project_id}, "revision": 1, "price_delta_chf": "0.00", "cost_delta_chf": "0.00"}]
        request.app.state.repo.duplicate_project(clone, Path(request.app.state.repo.document(source["document"]["id"])["path"]))
        return request.app.state.service.public_project(clone)

    @app.get("/api/admin/bids")
    async def admin_bids(request: Request):
        rows = []
        for p in request.app.state.repo.projects():
            s = request.app.state.service.summary(p["id"])
            t, c, comp = s.get("totals", {}), s.get("coverage", {}), s.get("completeness", {})
            rows.append({"id": p["id"], "name": p["name"], "estimator": p.get("estimator", "Local estimator"), "bid_status": p.get("bid_status", "draft"), "revision": p["revision"], "updated_at": p["updated_at"], "offer_price": t.get("selling_price_chf"), "cost_baseline": t.get("cost_baseline_chf"), "target_margin_pct": p.get("parameters", {}).get("commercial", {}).get("target_margin_pct", "0"), "pct_value_priced": comp.get("pct_value_priced", "0"), "unpriced_allowance_low": comp.get("allowance_low_chf", "0"), "unpriced_allowance_high": comp.get("allowance_high_chf", "0"), "pending_reviews": c.get("pending_reviews", 0), "supplier_quotes_required": c.get("supplier_quotes_required", 0), "scenarios": {x["scenario"]: x.get("bid_price_chf") for x in s.get("scenarios", {}).get("scenarios", [])}})
        return rows

    @app.get("/api/admin/bids/{project_id}/audit")
    async def admin_bid_audit(request: Request, project_id: str):
        """Management audit view for one bid, including every recorded decision."""
        project = request.app.state.repo.project(project_id)
        return {
            "project_id": project_id,
            "project_name": project["name"],
            "revision": project["revision"],
            "updated_at": project["updated_at"],
            "estimator": project.get("estimator", "Local estimator"),
            "bid_status": project.get("bid_status", "draft"),
            "history": list(reversed(project.get("history", []))),
        }

    @app.get("/api/pinned-demo")
    async def pinned_demo(request: Request):
        manifest_path = ROOT / "artifacts" / "prepared-demo.json"
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            project_id = manifest.get("project_id")
            if not project_id:
                return None
            project = request.app.state.repo.project(project_id)
        except (OSError, ValueError, TypeError, DomainError):
            return None
        return {"project_id": project_id, "prepared_at": manifest.get("prepared_at"),
                "project_name": project["name"]}

    @app.post("/api/projects/demo", status_code=202)
    async def demo(request: Request, body: StartRunRequest = Body(default=StartRunRequest())):
        if body.use_ai and not ai_configured():
            raise DomainError("Configure OPENAI_API_KEY in .env and restart before selecting AI extraction.")
        if not STARTER.is_dir():
            raise DomainError("The supplied Oberglatt package is missing. Import a package instead.", 404)
        project = await asyncio.to_thread(request.app.state.service.create_project, STARTER)
        return await request.app.state.workflow.start(project["id"], body.use_ai)

    @app.post("/api/projects/import", status_code=202)
    async def import_package(request: Request, files: list[UploadFile] = File(...), use_ai: bool = Form(False)):
        if use_ai and not ai_configured():
            raise DomainError("Configure OPENAI_API_KEY in .env and restart before selecting AI review.")
        max_upload, max_expanded = 50 * 1024 * 1024, 150 * 1024 * 1024
        total = 0
        uploads: list[tuple[str, bytes]] = []
        for file in files:
            data = await file.read(max_upload + 1)
            total += len(data)
            if total > max_upload:
                raise DomainError("Package exceeds the 50 MB upload limit.", 413)
            name = (file.filename or "upload").replace("\\", "/")
            if ".." in Path(name).parts or name.startswith("/") or ":" in name:
                raise DomainError("Unsafe upload filename.")
            uploads.append((Path(name).name, data))
        with tempfile.TemporaryDirectory(prefix="tenderproof-import-") as temporary:
            destination = Path(temporary).resolve()
            seen = set()
            expanded_total = entry_count = 0
            for name, data in uploads:
                if name.lower().endswith(".zip"):
                    try:
                        with zipfile.ZipFile(io.BytesIO(data)) as archive:
                            entries = archive.infolist()
                            entry_count += len(entries)
                            expanded_total += sum(item.file_size for item in entries)
                            if entry_count > 1000 or expanded_total > max_expanded:
                                raise DomainError("Expanded package exceeds safe size or file-count limits.", 413)
                            for item in entries:
                                safe_name = item.filename.replace("\\", "/")
                                if item.is_dir():
                                    continue
                                resolved = (destination / safe_name).resolve()
                                if not resolved.is_relative_to(destination) or ":" in safe_name or (item.external_attr >> 16) & 0o170000 == 0o120000:
                                    raise DomainError("Archive contains an unsafe path or symbolic link.")
                                if resolved.suffix.lower() not in (".pdf", ".csv", ".json", ".md", ".txt"):
                                    continue
                                if resolved in seen:
                                    raise DomainError("Archive contains duplicate filenames.")
                                seen.add(resolved)
                                resolved.parent.mkdir(parents=True, exist_ok=True)
                                resolved.write_bytes(archive.read(item))
                    except zipfile.BadZipFile:
                        raise DomainError("The uploaded ZIP is invalid.")
                else:
                    path = destination / name
                    if path in seen:
                        raise DomainError("Duplicate uploaded filename.")
                    seen.add(path)
                    path.write_bytes(data)
            candidates = list(destination.rglob("catalog.csv"))
            if len(candidates) != 1:
                raise DomainError("Import one package containing catalog.csv, productivity.csv, project_parameters.json and the tender PDF.")
            project = await asyncio.to_thread(request.app.state.service.create_project, candidates[0].parent, estimator=request.headers.get("X-Actor", "Local estimator"))
        return await request.app.state.workflow.start(project["id"], use_ai)

    @app.get("/api/projects/{project_id}")
    async def project(request: Request, project_id: str):
        return request.app.state.service.public_project(request.app.state.repo.project(project_id))

    @app.post("/api/projects/{project_id}/runs", status_code=202)
    async def start_run(request: Request, project_id: str, body: StartRunRequest):
        return await request.app.state.workflow.start(project_id, body.use_ai)

    @app.get("/api/runs/{run_id}")
    async def run(request: Request, run_id: str):
        return request.app.state.repo.run(run_id)

    @app.post("/api/runs/{run_id}/cancel")
    async def cancel(request: Request, run_id: str):
        return await request.app.state.workflow.cancel(run_id)

    @app.post("/api/runs/{run_id}/resume", status_code=202)
    async def resume(request: Request, run_id: str, body: ResumeRequest):
        return await request.app.state.workflow.resume(run_id, body.expected_revision, body.reason, body.action)

    @app.get("/api/projects/{project_id}/positions")
    async def positions(request: Request, project_id: str, search: str = "", system: str = "", status: str = "", needs_review: bool = False, unresolved_cause: str = ""):
        p = request.app.state.repo.project(project_id)
        from .proposals import enrich_position, unresolved_causes
        from .reference import fold_continuation_pages
        # Exclude PKG-CONT rows and ensure references are assigned
        positions_list = fold_continuation_pages(p["positions"])
        items = [enrich_position(item, p) for item in positions_list]
        if search:
            query = search.casefold()
            items = [item for item in items if query in f"{item.get('reference', '')} {item['id']} {item['description']} {item['category']} {item['product_id']}".casefold()]
        if system:
            items = [item for item in items if item["system"] == system]
        if status:
            items = [item for item in items if item["status"] == status]
        if needs_review:
            items = [item for item in items if item["review_state"] == "pending"]
        if unresolved_cause:
            items = [item for item in items if unresolved_cause in unresolved_causes(item)]
        return {"items": items, "total": len(items), "revision": p["revision"]}

    @app.post("/api/projects/{project_id}/positions", status_code=201)
    async def create_position(request: Request, project_id: str, body: ManualPositionCreate):
        return request.app.state.service.create_position(project_id, body)

    @app.patch("/api/positions/{position_id}")
    async def edit_position(request: Request, position_id: str, body: PositionPatch):
        return request.app.state.service.patch_position(position_id, body.expected_revision, body.reason, body.changes)

    @app.get("/api/projects/{project_id}/summary")
    async def summary(request: Request, project_id: str):
        return request.app.state.service.summary(project_id)

    @app.get("/api/projects/{project_id}/references")
    async def references(request: Request, project_id: str):
        p = request.app.state.repo.project(project_id)
        return {key: p[key] for key in ("catalog", "productivity", "parameters")}

    @app.patch("/api/projects/{project_id}/assumptions")
    async def assumptions(request: Request, project_id: str, body: AssumptionsPatch):
        return request.app.state.service.patch_assumptions(project_id, body.expected_revision, body.reason, body.changes)

    @app.post("/api/projects/{project_id}/what-if/preview")
    async def what_if_preview(request: Request, project_id: str, body: WhatIfPreviewRequest):
        return request.app.state.service.preview_what_if(project_id, body.expected_revision, body.changes, body.include_positions)

    @app.post("/api/projects/{project_id}/sensitivity")
    async def sensitivity(request: Request, project_id: str, body: ScenarioRequest | None = None):
        return request.app.state.service.sensitivity(project_id, body.revision if body else None)

    @app.post("/api/projects/{project_id}/duct-area-rule")
    async def duct_area_rule(request: Request, project_id: str, body: RevisionMutation):
        return request.app.state.service.apply_duct_area_rule(project_id, body.expected_revision, body.reason)

    @app.post("/api/projects/{project_id}/adjustments", status_code=201)
    async def create_adjustment(request: Request, project_id: str, body: AdjustmentCreate):
        return request.app.state.service.create_adjustment(project_id, body)

    @app.patch("/api/adjustments/{adjustment_id}")
    async def edit_adjustment(request: Request, adjustment_id: str, body: AdjustmentPatch):
        return request.app.state.service.patch_adjustment(adjustment_id, body.expected_revision, body.reason, body.changes)

    @app.patch("/api/projects/{project_id}/issues/{issue_id}")
    async def edit_issue(request: Request, project_id: str, issue_id: str, body: PositionPatch):
        return request.app.state.service.patch_issue(project_id, issue_id, body.expected_revision, body.reason, body.changes)

    @app.post("/api/projects/{project_id}/undo/{decision_id}")
    async def undo(request: Request, project_id: str, decision_id: str, body: RevisionMutation):
        return request.app.state.service.undo(project_id, decision_id, body.expected_revision, body.reason)

    @app.patch("/api/projects/{project_id}/requirements/{requirement_id}")
    async def review_requirement(request: Request, project_id: str, requirement_id: str, body: PositionPatch):
        return request.app.state.service.patch_requirement(project_id, requirement_id, body.expected_revision, body.reason, body.changes)

    @app.get("/api/projects/{project_id}/revisions")
    async def revisions(request: Request, project_id: str):
        return request.app.state.repo.revisions(project_id)

    @app.post("/api/projects/{project_id}/scenarios")
    async def scenarios(request: Request, project_id: str, body: ScenarioRequest):
        p = request.app.state.repo.revision(project_id, body.revision) if body.revision is not None else request.app.state.repo.project(project_id)
        totals = p.get("estimate", {}).get("totals", {})
        if not totals:
            raise DomainError("Finish processing before comparing scenarios.", 409)
        if body.overrides:
            if set(body.overrides) - SCENARIO_KEYS:
                raise DomainError("Unsupported scenario assumption.")
            p["commercial_state"] = commercial_state(p)
            p["commercial_state"]["context"]["scenario_overrides"].update(body.overrides)
            apply_commercial(p)
        result = {**p["estimate"]["scenarios"]}
        if body.overrides:
            result["preview"] = True
        result["reference_context"] = request.app.state.service.scenario_reference_context(p, result)
        return result

    @app.get("/api/projects/{project_id}/commercial-context")
    async def commercial_context(request: Request, project_id: str):
        return commercial_view(request.app.state.repo.project(project_id))

    @app.post("/api/projects/{project_id}/historical/preview")
    async def historical_preview(request: Request, project_id: str, body: HistoricalPreview):
        return preview_history(request.app.state.repo.project(project_id), body.filename, body.csv_text)

    @app.post("/api/projects/{project_id}/historical/import", status_code=201)
    async def historical_import(request: Request, project_id: str, body: HistoricalImport):
        return import_history(request.app.state.service, project_id, body)

    @app.patch("/api/projects/{project_id}/commercial-context")
    async def update_commercial_context(request: Request, project_id: str, body: CommercialPatch):
        return patch_commercial(request.app.state.service, project_id, body)

    @app.post("/api/projects/{project_id}/scenarios/save")
    async def save_scenarios(request: Request, project_id: str, body: ScenarioSave):
        return patch_commercial(request.app.state.service, project_id, CommercialPatch(
            expected_revision=body.expected_revision, reason=body.reason,
            changes={"scenario_overrides": body.overrides}))

    @app.get("/api/documents/{document_id}/file")
    async def document_file(request: Request, document_id: str):
        doc = request.app.state.repo.document(document_id)
        return FileResponse(doc["path"], media_type="application/pdf", filename=doc["filename"], content_disposition_type="inline")

    @app.get("/api/documents/{document_id}/pages/{page}/spans")
    async def page_spans(request: Request, document_id: str, page: int):
        request.app.state.repo.document(document_id)
        pages = request.app.state.repo.pages(document_id)
        item = next((item for item in pages if item["page"] == page), None)
        if item is None:
            raise DomainError("Page is not available yet.", 404)
        return {"items": request.app.state.repo.spans(document_id, [page]), "page": page, "width": item["width"], "height": item["height"]}

    @app.get("/api/sources/{source_id}")
    async def source(request: Request, source_id: str):
        return request.app.state.repo.source(source_id)

    @app.post("/api/projects/{project_id}/exports")
    async def export(request: Request, project_id: str, body: ExportRequest):
        return await asyncio.to_thread(create_export, request.app.state.repo, request.app.state.service, project_id, body.revision, body.format)

    @app.get("/api/exports/{filename}")
    async def download_export(request: Request, filename: str):
        directory = (request.app.state.repo.directory / "exports").resolve()
        path = (directory / filename).resolve()
        if not path.is_relative_to(directory) or not path.is_file() or not filename.startswith(("TenderProof_", "BidGenius AI_")):
            raise DomainError("Export not found.", 404)
        return FileResponse(path, filename=filename, content_disposition_type="inline" if path.suffix == ".html" else "attachment")

    # API routes precede the static application. An API typo never returns index.html.
    @app.api_route("/api/{unknown:path}", methods=["GET", "POST", "PATCH", "DELETE", "PUT"], include_in_schema=False)
    async def unknown_api(unknown: str):
        raise DomainError("API endpoint not found.", 404)

    frontend = ROOT / "frontend" / "dist"
    @app.get("/{path:path}")
    async def frontend_file(path: str):
        candidate = (frontend / path).resolve()
        if path and candidate.is_relative_to(frontend.resolve()) and candidate.is_file():
            return FileResponse(candidate)
        index = frontend / "index.html"
        if index.is_file():
            return FileResponse(index)
        return JSONResponse(status_code=503, content={"message": "Frontend is not built. Run setup.cmd or npm.cmd run build in frontend."})

    return app


app = create_app()
