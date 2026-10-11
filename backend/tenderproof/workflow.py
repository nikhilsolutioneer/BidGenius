"""Durable, bounded extraction with a side-effect-free human review interrupt."""
from __future__ import annotations

import asyncio
from copy import deepcopy
from datetime import datetime
import hashlib
import json
from pathlib import Path
from typing import TypedDict

from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, interrupt

from .config import ai_configured, model_name
from .models import ExtractionBatch, Issue, PageRecord, Position, Requirement, Run, SourceSpan
from .service import EstimateService, identifier
from .storage import DomainError, Repository, now

PARSER_VERSION = "1.6"


def section_batches(pages: list[dict]) -> list[list[dict]]:
    """Bounded page groups that do not mix canonical ventilation sections."""
    batches: list[list[dict]] = []
    for page in pages:
        if not batches or len(batches[-1]) == 4 or batches[-1][0].get("system") != page.get("system"):
            batches.append([])
        batches[-1].append(page)
    return batches


class WorkflowState(TypedDict, total=False):
    project_id: str
    run_id: str
    cursor: int
    page_count: int
    use_ai: bool
    review_action: str
    reviewed_revision: int
    ai_disabled: bool
    selective_ai: bool
    ai_reviews: list[dict]
    ai_cursor: int


class CancelledRun(Exception):
    pass


def batch_usage(previous: dict, batch: ExtractionBatch, cached: bool) -> dict:
    usage = deepcopy(previous)
    def accumulate(target, values):
        for name, value in values.items():
            if isinstance(value, dict):
                accumulate(target.setdefault(name, {}), value)
            elif isinstance(value, (int, float)) and not isinstance(value, bool):
                target[name] = target.get(name, 0) + (0 if cached else value)
    accumulate(usage, batch.usage)
    usage["cached_batches"] = usage.get("cached_batches", 0) + int(cached)
    if cached and batch.usage.get("successful_ai_batches"):
        usage["cached_ai_batches"] = usage.get("cached_ai_batches", 0) + 1
    return usage


def restore_reviewed_positions(project: dict) -> None:
    current_ids = {p["id"] for p in project["positions"]}
    for position in project.pop("_previous_positions", []):
        if position["id"] not in current_ids and (position["origin"] == "manual" or position["overrides"] or position["review_state"] == "accepted"):
            position["assumptions"].append("Retained reviewer decision from an earlier extraction; verify scope coverage.")
            project["positions"].append(position)
            current_ids.add(position["id"])


class WorkflowManager:
    def __init__(self, repo: Repository, service: EstimateService, checkpointer):
        self.repo, self.service = repo, service
        self.tasks: dict[str, asyncio.Task] = {}
        self.lock = asyncio.Lock()
        graph = StateGraph(WorkflowState)
        graph.add_node("parse_document", self.parse_document)
        graph.add_node("extract_batch", self.extract_batch)
        graph.add_node("prepare_ai_review", self.prepare_ai_review)
        graph.add_node("review_ai_batch", self.review_ai_batch)
        graph.add_node("price_draft", self.price_draft)
        graph.add_node("human_review", self.human_review)
        graph.add_node("finish", self.finish)
        graph.add_edge(START, "parse_document")
        graph.add_edge("parse_document", "extract_batch")
        graph.add_conditional_edges("extract_batch", lambda state: "more" if state["cursor"] < state["page_count"] else "review" if state.get("selective_ai") else "done",
                                    {"more": "extract_batch", "review": "prepare_ai_review", "done": "price_draft"})
        graph.add_conditional_edges("prepare_ai_review", lambda state: "review" if state.get("ai_reviews") else "done",
                                    {"review": "review_ai_batch", "done": "price_draft"})
        graph.add_conditional_edges("review_ai_batch", lambda state: "more" if state["ai_cursor"] < len(state["ai_reviews"]) and not state.get("ai_disabled") else "done",
                                    {"more": "review_ai_batch", "done": "price_draft"})
        graph.add_edge("price_draft", "human_review")
        graph.add_edge("human_review", "finish")
        graph.add_edge("finish", END)
        self.graph = graph.compile(checkpointer=checkpointer)

    def _config(self, run_id: str) -> dict:
        return {"configurable": {"thread_id": run_id}, "recursion_limit": 2000}

    def _cancelled(self, run_id: str):
        if self.repo.run(run_id).get("cancellation_requested"):
            raise CancelledRun()

    async def start(self, project_id: str, use_ai: bool = False) -> dict:
        async with self.lock:
            if any(not task.done() for task in self.tasks.values()):
                raise DomainError("Another processing run is active. Finish or cancel it first.", 409)
            if use_ai and not ai_configured():
                raise DomainError("OpenAI is not configured. Add OPENAI_API_KEY to the local .env file and restart, or choose local parsing.")
            project = self.repo.project(project_id)
            from .ingestion import PARSER_VERSION as LOCAL_VERSION
            from .prompts import PROMPT_VERSION, SCHEMA_VERSION
            run = Run(id=identifier("run"), project_id=project_id, extraction_mode="local_then_ai" if use_ai else "local",
                      parser_version=LOCAL_VERSION, prompt_version=PROMPT_VERSION, schema_version=SCHEMA_VERSION,
                      model=model_name() if use_ai else None, started_at=now(), updated_at=now())
            self.repo.create_run(run.model_dump())

            def prepare(p):
                p["latest_run_id"] = run.id
                p["review_complete"] = False
                p["_previous_positions"] = deepcopy(p["positions"])
                p["positions"] = [x for x in p["positions"] if x["origin"] == "manual"]
                p["issues"] = []
                p["requirements"] = []
                p.pop("document_processing", None)
            self.repo.update_project(project_id, prepare)
            state = {"project_id": project_id, "run_id": run.id, "cursor": 0, "page_count": 0,
                     "use_ai": use_ai, "selective_ai": use_ai}
            self.tasks[run.id] = asyncio.create_task(self._execute(run.id, state))
            return {"project_id": project_id, "run_id": run.id}

    async def resume(self, run_id: str, expected_revision: int, reason: str, action: str) -> dict:
        async with self.lock:
            run = self.repo.run(run_id)
            project = self.repo.project(run["project_id"])
            if project["revision"] != expected_revision:
                raise DomainError("Review revision is stale. Refresh before resuming.", 409)
            if run["status"] == "complete":
                return {"run_id": run_id, "project_id": project["id"], "status": "complete"}
            if any(not task.done() for task in self.tasks.values()):
                raise DomainError("A processing run is already active.", 409)
            if project.get("latest_run_id") != run_id:
                raise DomainError("This run was superseded. Resume the latest processing run.", 409)
            if run["status"] not in ("awaiting_review", "resumable", "failed", "cancelled"):
                raise DomainError("This run is not ready to resume.", 409)
            if action == "complete_review":
                blockers = self.service.review_blockers(project["id"])
                if blockers:
                    raise DomainError("Review cannot be marked complete: " + " ".join(blockers), 409)
            state = await self.graph.aget_state(self._config(run_id))
            if not state.values:
                invoke_input = {"project_id": project["id"], "run_id": run_id, "cursor": 0, "page_count": 0,
                                "use_ai": run["extraction_mode"] in ("openai", "mixed", "local_then_ai"),
                                "selective_ai": run["extraction_mode"] == "local_then_ai"}
            elif any(task.interrupts for task in state.tasks):
                invoke_input = Command(resume={"revision": expected_revision, "action": action, "reason": reason})
            else:
                invoke_input = None
            self.repo.update_run(run_id, cancellation_requested=False, status="queued")
            self.tasks[run_id] = asyncio.create_task(self._execute(run_id, invoke_input))
            return {"run_id": run_id, "project_id": project["id"]}

    async def cancel(self, run_id: str) -> dict:
        run = self.repo.run(run_id)
        if run["status"] in ("complete", "cancelled", "failed"):
            return run
        active = run_id in self.tasks and not self.tasks[run_id].done()
        return self.repo.update_run(run_id, cancellation_requested=True, **({} if active else {"status": "cancelled", "stage": "cancelled"}))

    async def shutdown(self):
        for run_id, task in self.tasks.items():
            if not task.done():
                self.repo.update_run(run_id, cancellation_requested=True, status="resumable")
                task.cancel()
        if self.tasks:
            await asyncio.gather(*self.tasks.values(), return_exceptions=True)

    async def _execute(self, run_id: str, invoke_input):
        self.repo.update_run(run_id, status="running", stage="starting")
        try:
            await self.graph.ainvoke(invoke_input, config=self._config(run_id), durability="sync")
            checkpoint = await self.graph.aget_state(self._config(run_id))
            run = self.repo.run(run_id)
            elapsed = (datetime.fromisoformat(now()) - datetime.fromisoformat(run["started_at"])).total_seconds()
            if any(task.interrupts for task in checkpoint.tasks):
                self.repo.update_run(run_id, status="awaiting_review", stage="review", duration_seconds=round(elapsed, 3))
            elif run["status"] != "complete":
                self.repo.update_run(run_id, status="complete", stage="complete", completed_at=now(), duration_seconds=round(elapsed, 3))
        except CancelledRun:
            self.repo.update_run(run_id, status="cancelled", stage="cancelled — completed batches preserved")
        except asyncio.CancelledError:
            self.repo.update_run(run_id, status="resumable", stage="interrupted — resume available")
        except Exception as exc:
            run = self.repo.run(run_id)
            # Provider failures are handled inside extraction; never echo credentials in errors.
            message = str(exc) if isinstance(exc, (DomainError, ValueError)) else f"{type(exc).__name__}: processing failed; completed batches are preserved."
            self.repo.update_run(run_id, status="failed", stage="failed", errors=run["errors"] + [message])
            import logging
            logging.getLogger("tenderproof").exception("Run %s failed", run_id)

    async def parse_document(self, state: WorkflowState):
        from .ingestion import parse_pdf
        self._cancelled(state["run_id"])
        project = self.repo.project(state["project_id"])
        doc = self.repo.document(project["document"]["id"])
        self.repo.update_run(state["run_id"], stage="reading PDF")
        pages = self.repo.pages(doc["id"])
        if not pages:
            def progress(page_number, total_pages):
                self._cancelled(state["run_id"])
                if page_number == total_pages or page_number % 5 == 0:
                    self.repo.update_run(state["run_id"], stage=f"reading PDF · page {page_number}", pages_processed=page_number, total_pages=total_pages)
            parsed_pages, spans = await asyncio.to_thread(parse_pdf, Path(doc["path"]), doc["id"], progress)
            pages = [page.model_dump(mode="json") for page in parsed_pages]
            await asyncio.to_thread(self.repo.save_parsed, doc["id"], pages, [span.model_dump(mode="json") for span in spans])
        self._cancelled(state["run_id"])
        self.repo.update_project(project["id"], lambda p: p["document"].update(page_count=len(pages)))
        self.repo.update_run(state["run_id"], stage="extracting positions", total_pages=len(pages), pages_processed=0, batches_total=len(section_batches(pages)))
        return {"cursor": state.get("cursor", 0), "page_count": len(pages)}

    async def extract_batch(self, state: WorkflowState):
        from .ingestion import extract_local_batch, PARSER_VERSION as LOCAL_VERSION
        from .prompts import PROMPT_VERSION, SCHEMA_VERSION
        from .ai import AI_ADAPTER_VERSION
        self._cancelled(state["run_id"])
        project = self.repo.project(state["project_id"])
        document_id = project["document"]["id"]
        all_pages = self.repo.pages(document_id)
        page_data = section_batches(all_pages[state["cursor"]:])[0]
        pages = [PageRecord.model_validate(page) for page in page_data]
        numbers = [page.page for page in pages]
        spans = [SourceSpan.model_validate(span) for span in self.repo.spans(document_id, numbers)]
        # Older checkpoints retain their original full-batch AI behavior. New
        # runs finish the entire local pass before any selective model request.
        ai_enabled = state["use_ai"] and not state.get("selective_ai") and not state.get("ai_disabled", False)
        key = hashlib.sha256(json.dumps([project["document"]["sha256"], document_id, numbers, ai_enabled, model_name(), PARSER_VERSION, LOCAL_VERSION, PROMPT_VERSION, SCHEMA_VERSION, AI_ADAPTER_VERSION], sort_keys=True).encode()).hexdigest()
        cache_dir = self.repo.directory / "projects" / project["id"] / "cache"
        cache_dir.mkdir(parents=True, exist_ok=True)
        cache_path = cache_dir / f"{key}.json"
        cached = False
        if cache_path.is_file():
            batch = ExtractionBatch.model_validate_json(cache_path.read_text(encoding="utf-8"))
            cached = True
        else:
            batch = await asyncio.to_thread(extract_local_batch, pages, spans, project["catalog"])
            if ai_enabled:
                from .ai import extract_ai_batch, is_configuration_error
                try:
                    ai_batch = await extract_ai_batch(pages, spans, project["catalog"], model_name())
                    # The AI batch is authoritative for its section; deterministic extraction
                    # supplements only source rows not represented, preserving clear provenance.
                    covered = {s for p in ai_batch.positions for s in p.source_span_ids}
                    ai_batch.positions.extend(p for p in batch.positions if not (covered & set(p.source_span_ids)))
                    ai_batch.requirements = list({r.id: r for r in batch.requirements + ai_batch.requirements}.values())
                    ai_batch.issues = list({i.id: i for i in batch.issues + ai_batch.issues}.values())
                    ai_batch.dispositions = {**batch.dispositions, **ai_batch.dispositions}
                    batch = ai_batch
                    batch.usage["successful_ai_batches"] = 1
                except Exception as exc:
                    batch.usage.update(getattr(exc, "usage", {}))
                    error_code = getattr(exc, "code", None)
                    if error_code:
                        batch.errors.append(f"AI batch pages {numbers[0]}–{numbers[-1]} failed validation ({error_code}): {str(exc)[:500]}. Local extraction retained for review.")
                    else:
                        batch.errors.append(f"AI unavailable for pages {numbers[0]}–{numbers[-1]} ({type(exc).__name__}); local extraction retained for review.")
                    self.repo.update_run(state["run_id"], extraction_mode="mixed")
                    batch.usage["failed_ai_batches"] = 1
                    batch.usage["local_fallback_batches"] = 1
                    if is_configuration_error(exc):
                        state["ai_disabled"] = True
                        batch.errors.append("OpenAI configuration or access was rejected; further model requests are disabled for this run. Local processing continues. Correct configuration and start a new run to retry AI.")
                        batch.usage["ai_disabled_configuration"] = 1
            if not ai_enabled:
                batch.usage["local_batches"] = 1
            if not batch.errors:
                temporary = cache_path.with_suffix(".tmp")
                temporary.write_text(batch.model_dump_json(), encoding="utf-8")
                temporary.replace(cache_path)
        if self.repo.run(state["run_id"]).get("cancellation_requested"):
            run = self.repo.run(state["run_id"])
            usage = batch_usage(run["usage"], batch, cached)
            usage["cancelled_after_response_batches"] = usage.get("cancelled_after_response_batches", 0) + 1
            self.repo.update_run(state["run_id"], usage=usage)
        self._cancelled(state["run_id"])

        saved = self._persist_batch(project["id"], batch)
        self.repo.update_pages(document_id, numbers, "processed", batch.dispositions)
        cursor = state["cursor"] + len(pages)
        run = self.repo.run(state["run_id"])
        usage = batch_usage(run["usage"], batch, cached)
        stage = "local extraction" if state.get("selective_ai") else "extracting"
        self.repo.update_run(state["run_id"], stage=f"{stage} · pages {numbers[0]}–{numbers[-1]}", pages_processed=cursor,
                             batches_done=len(section_batches(all_pages[:cursor])), positions_found=len(saved["positions"]), errors=run["errors"] + batch.errors, usage=usage)
        return {"cursor": cursor, "ai_disabled": state.get("ai_disabled", False)}

    def _persist_batch(self, project_id: str, batch: ExtractionBatch, preserve_current: bool = False) -> dict:
        def persist(p):
            previous = {x["id"]: x for x in p.get("_previous_positions", [])}
            if preserve_current:
                previous.update({x["id"]: x for x in p["positions"]})
            merged = {x["id"]: x for x in p["positions"]}
            for position in batch.positions:
                value = position.model_dump(mode="json")
                prior = previous.get(position.id)
                if prior:
                    prior_proposals = prior.get("attributes", {}).get("ai_refinement_proposals", [])
                    new_proposals = value["attributes"].get("ai_refinement_proposals", [])
                    if prior_proposals or new_proposals:
                        # Earlier accepted/rejected decisions win over regenerated proposals.
                        value["attributes"]["ai_refinement_proposals"] = list({x["id"]: x for x in new_proposals + prior_proposals}.values())
                if prior and (prior["review_state"] == "accepted" or prior["overrides"] or any("Estimator override" in a for a in prior["assumptions"])):
                    from .ai import refinement_proposal
                    fields = ("description", "quantity", "unit", "system", "category", "product_id", "install_code", "pricing_basis", "scope_tags")
                    changes = {field: value[field] for field in fields if value[field] != prior.get(field)}
                    attributes = {k: v for k, v in value["attributes"].items() if k != "ai_refinement_proposals" and v != prior.get("attributes", {}).get(k)}
                    if attributes:
                        changes["attributes"] = attributes
                    proposals = value["attributes"].get("ai_refinement_proposals", [])
                    if changes:
                        proposed = refinement_proposal(position, changes, position.source_span_ids)
                        if not any(x["id"] == proposed["id"] for x in proposals):
                            proposals.append(proposed)
                    value = deepcopy(prior)
                    if proposals:
                        value["attributes"]["ai_refinement_proposals"] = proposals
                merged[position.id] = value
            p["positions"] = list(merged.values())
            p["issues"] = list({x["id"]: x for x in p["issues"] + [issue.model_dump() for issue in batch.issues]}.values())
            p["requirements"] = list({x["id"]: x for x in p["requirements"] + [r.model_dump() for r in batch.requirements]}.values())
        saved, _ = self.repo.update_project(project_id, persist)
        return saved

    async def prepare_ai_review(self, state: WorkflowState):
        from .ai_review import build_review_batches
        from .reference import fold_continuation_pages
        self._cancelled(state["run_id"])
        self.repo.update_run(state["run_id"], stage="selecting unresolved items for AI")
        project = self.repo.project(state["project_id"])
        document_id = project["document"]["id"]
        spans = self.repo.spans(document_id)

        def normalize(p):
            p["positions"] = fold_continuation_pages(p["positions"], spans)
            local_count = sum(position["origin"] == "extracted" for position in p["positions"])
            # Protect retained decisions before identifying apparently uncovered
            # sources; AI must not re-create an already reviewed position.
            restore_reviewed_positions(p)
            return local_count

        project, local_count = self.repo.update_project(project["id"], normalize)
        reviews = build_review_batches(
            [PageRecord.model_validate(page) for page in self.repo.pages(document_id)],
            [SourceSpan.model_validate(span) for span in spans],
            [Position.model_validate(position) for position in project["positions"]],
            [Issue.model_validate(issue) for issue in project["issues"]])
        run = self.repo.run(state["run_id"])
        usage = {**run["usage"],
                 "ai_review_positions": len({p for review in reviews for p in review["position_ids"]}),
                 "ai_review_source_blocks": len({s for review in reviews for s in review["target_source_ids"]})}
        self.repo.update_run(state["run_id"],
            local_positions_found=run.get("local_positions_found") if run.get("local_positions_found") is not None else local_count,
            positions_found=len(project["positions"]), ai_batches_total=len(reviews), usage=usage)
        return {"ai_reviews": reviews, "ai_cursor": 0}

    async def review_ai_batch(self, state: WorkflowState):
        from .ai import AI_ADAPTER_VERSION, extract_ai_batch, is_configuration_error
        from .ai_review import REVIEW_VERSION
        from .prompts import PROMPT_VERSION, SCHEMA_VERSION
        self._cancelled(state["run_id"])
        index = state["ai_cursor"]
        run = self.repo.run(state["run_id"])
        if run.get("ai_batches_done", 0) > index:
            return {"ai_cursor": index + 1, "ai_disabled": bool(run["usage"].get("ai_disabled_configuration"))}
        review = state["ai_reviews"][index]
        numbers = review["pages"]
        project = self.repo.project(state["project_id"])
        document_id = project["document"]["id"]
        pages = [PageRecord.model_validate(page) for page in self.repo.pages(document_id) if page["page"] in numbers]
        source_ids = set(review["target_source_ids"] + review["context_source_ids"])
        spans = [SourceSpan.model_validate(span) for span in self.repo.spans(document_id, numbers) if span["id"] in source_ids]
        baseline = ExtractionBatch(
            positions=[Position.model_validate(p) for p in project["positions"]
                       if p["source_page"] in numbers or p["id"] in review["position_ids"]],
            requirements=[Requirement.model_validate(r) for r in project["requirements"] if r["source_page"] in numbers],
            issues=[Issue.model_validate(i) for i in project["issues"] if source_ids.intersection(i["source_span_ids"])],
            dispositions={s.id: s.disposition for s in spans})
        # Fingerprint source/local facts, not prior proposal decisions or prices.
        # Those decisions are reconciled against current saved rows when merging.
        facts = []
        for position in baseline.positions:
            fact = position.model_dump(exclude={"cost", "reference", "lv_id", "candidates"})
            fact["attributes"].pop("ai_refinement_proposals", None)
            facts.append(fact)
        key = hashlib.sha256(json.dumps([REVIEW_VERSION, AI_ADAPTER_VERSION, PROMPT_VERSION, SCHEMA_VERSION,
            run["model"], project["document"]["sha256"], review, facts,
            [s.model_dump() for s in spans], project["catalog"],
            [r.model_dump() for r in baseline.requirements], [i.model_dump() for i in baseline.issues]],
            sort_keys=True).encode()).hexdigest()
        cache_dir = self.repo.directory / "projects" / project["id"] / "cache"
        cache_dir.mkdir(parents=True, exist_ok=True)
        cache_path = cache_dir / f"review-{key}.json"
        cached = cache_path.is_file()
        disabled = False
        self.repo.update_run(state["run_id"], stage=f"AI review · pages {', '.join(map(str, numbers))}")
        if cached:
            batch = ExtractionBatch.model_validate_json(cache_path.read_text(encoding="utf-8"))
        else:
            try:
                batch = await extract_ai_batch(pages, spans, project["catalog"], run["model"], local_batch=baseline, review=review)
                batch.usage["successful_ai_batches"] = 1
                if not batch.errors:
                    temporary = cache_path.with_suffix(".tmp")
                    temporary.write_text(batch.model_dump_json(), encoding="utf-8")
                    temporary.replace(cache_path)
            except Exception as exc:
                batch = baseline.model_copy(deep=True)
                batch.usage = {**getattr(exc, "usage", {}), "failed_ai_batches": 1, "local_fallback_batches": 1}
                error_code = getattr(exc, "code", None)
                detail = f" ({error_code}): {str(exc)[:500]}" if error_code else f" ({type(exc).__name__})"
                batch.errors.append(f"AI review for pages {', '.join(map(str, numbers))} failed{detail}. Local extraction retained for review.")
                disabled = is_configuration_error(exc)
                if disabled:
                    batch.usage["ai_disabled_configuration"] = 1
                    batch.errors.append("AI configuration or access was rejected; remaining AI reviews were skipped. Local extraction is preserved.")
        run = self.repo.run(state["run_id"])
        usage = batch_usage(run["usage"], batch, cached)
        if run.get("cancellation_requested"):
            usage["cancelled_after_response_batches"] = usage.get("cancelled_after_response_batches", 0) + 1
            self.repo.update_run(state["run_id"], usage=usage)
        self._cancelled(state["run_id"])
        before = {p.id: p.model_dump() for p in baseline.positions}
        saved = self._persist_batch(project["id"], batch, preserve_current=True)
        after = {p["id"]: p for p in saved["positions"]}
        usage["ai_positions_added"] = usage.get("ai_positions_added", 0) + sum(p.id not in before for p in batch.positions)
        usage["ai_positions_refined"] = usage.get("ai_positions_refined", 0) + sum(
            p.id in before and after[p.id] != before[p.id] for p in batch.positions)
        if disabled:
            usage["ai_skipped_batches"] = len(state["ai_reviews"]) - index - 1
        self.repo.update_pages(document_id, numbers, "processed", batch.dispositions)
        self.repo.update_run(state["run_id"], ai_batches_done=index + 1, positions_found=len(saved["positions"]),
                             usage=usage, errors=run["errors"] + batch.errors)
        return {"ai_cursor": index + 1, "ai_disabled": disabled}

    async def price_draft(self, state: WorkflowState):
        self._cancelled(state["run_id"])
        self.repo.update_run(state["run_id"], stage="calculating material, labour and scope")
        def calculate(project):
            # This node can be retried after checkpoint failure without duplicating a revision.
            if project.get("_draft_run_id") == state["run_id"]:
                return
            restore_reviewed_positions(project)
            self.service.validate_extracted_inputs(project)
            self.service.recalculate(project)
            project["document_processing"] = self.service.document_progress(project)
            project["run_provenance"] = {**self.repo.run(state["run_id"]),
                                         "positions_found": len(project["positions"])}
            project["revision"] += 1
            project["_draft_run_id"] = state["run_id"]
            project["review_complete"] = False
        # Snapshot insert is handled atomically only once.
        project = self.repo.project(state["project_id"])
        if project.get("_draft_run_id") != state["run_id"]:
            project, _ = await asyncio.to_thread(self.repo.update_project, project["id"], calculate, None, True)
        self.repo.update_run(state["run_id"], positions_found=len(project["positions"]))
        return {}

    async def human_review(self, state: WorkflowState):
        # No writes before interrupt: LangGraph re-executes this node on resume.
        project = self.repo.project(state["project_id"])
        decision = interrupt({"project_id": project["id"], "revision": project["revision"], "message": "Review evidence, unresolved scope and assumptions. Continue as draft or complete review when all blockers are resolved."})
        if decision["revision"] != project["revision"]:
            raise DomainError("The estimate changed after the resume request.", 409)
        return {"review_action": decision["action"], "reviewed_revision": decision["revision"]}

    async def finish(self, state: WorkflowState):
        if state.get("review_action") == "complete_review":
            blockers = self.service.review_blockers(state["project_id"])
            if blockers:
                raise DomainError("Unresolved blockers prevent review completion: " + " ".join(blockers), 409)
            def approve(project):
                if project.get("_approved_run_id") == state["run_id"]:
                    return
                project["revision"] += 1
                project["review_complete"] = True
                project["_approved_run_id"] = state["run_id"]
            project = self.repo.project(state["project_id"])
            if project.get("_approved_run_id") != state["run_id"]:
                self.repo.update_project(project["id"], approve, state["reviewed_revision"], snapshot=True)
        self.repo.update_run(state["run_id"], status="complete", stage="complete", completed_at=now())
        return {}
