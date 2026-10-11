"""Bounded OpenAI structured extraction with local evidence validation."""
from __future__ import annotations

import json
import os
import re
from decimal import Decimal
from typing import Literal

from openai import AsyncOpenAI
from pydantic import BaseModel, ConfigDict

from .ai_review import reviewable_position
from .ingestion import _id, extract_local_batch
from .matching import match_position, normalize_number, normalize_unit
from .models import ExtractionBatch, Issue, PageRecord, Position, Requirement, SourceSpan
from .prompts import EXTRACTION_PROMPT, PROMPT_VERSION, REVIEW_PROMPT, SCHEMA_VERSION, SYSTEM_PROMPT


AI_ADAPTER_VERSION = "3.0"


def is_configuration_error(exc: Exception) -> bool:
    """Permanent provider failures must not be retried on every document batch."""
    return getattr(exc, "status_code", None) in {400, 401, 403, 404, 422}


def refinement_proposal(position: Position, changes: dict, source_ids: list[str]) -> dict:
    return {"id": "REF-" + _id(position.id, json.dumps(changes, sort_keys=True)),
            "changes": changes, "source_span_ids": source_ids, "state": "pending",
            "rationale": "AI interpretation differs from preserved values; estimator approval is required."}


def _validated_attributes(item: ExtractedPosition, source_map: dict) -> dict:
    values = {}
    numeric = {"diameter_mm", "width_mm", "height_mm", "length_mm", "thickness_mm", "angle_deg", "airflow_m3h"}
    for attr in item.attributes:
        _validate_sources(attr.source_ids, source_map)
        if attr.key not in numeric | {"manufacturer", "fire_class", "control_interface", "material", "shape"}:
            continue
        evidence = " ".join(source_map[s].text for s in attr.source_ids)
        if attr.key in numeric:
            value = normalize_number(attr.value)
            supported = {Decimal(normalize_number(n)) for n in re.findall(r"\d[\d']*(?:[.,]\d+)?", evidence)}
            if Decimal(value) not in supported:
                raise ValueError("Technical attribute is unsupported by cited source text")
            values[attr.key] = value
        elif attr.value.casefold() in evidence.casefold():
            values[attr.key] = attr.value
    return values


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Attribute(Strict):
    key: str
    value: str
    source_ids: list[str]


class ExtractedPosition(Strict):
    anchor_source_id: str
    description: str
    original_description: str
    quantity: str | None
    unit: str | None
    raw_quantity: str | None
    raw_unit: str | None
    source_ids: list[str]
    quantity_source_ids: list[str]
    attributes: list[Attribute]
    category: str
    product_id: str | None
    supplied_by_others: bool
    assumption: str | None
    system: str | None = None


class ExtractedRequirement(Strict):
    title: str
    description: str
    category: str
    source_ids: list[str]


class ExtractedIssue(Strict):
    title: str
    detail: str
    kind: str
    severity: Literal["info", "warning", "blocker"]
    source_ids: list[str]
    action: str


class Disposition(Strict):
    source_id: str
    disposition: Literal["position", "requirement", "context", "boilerplate", "unresolved"]


class AIExtraction(Strict):
    positions: list[ExtractedPosition]
    requirements: list[ExtractedRequirement]
    issues: list[ExtractedIssue]
    dispositions: list[Disposition]


class AIOutputValidationError(ValueError):
    """Evidence validation failure safe to show in a persisted run report."""

    def __init__(self, code: str, detail: str):
        super().__init__(detail)
        self.code = code


def _validate_sources(ids: list[str], source_map: dict[str, SourceSpan], required: bool = True) -> None:
    if required and not ids:
        raise AIOutputValidationError("missing_evidence_ids", "Model output is missing required evidence IDs")
    unknown = sorted(set(ids) - source_map.keys())
    if unknown:
        sample = ", ".join(unknown[:8])
        suffix = "" if len(unknown) <= 8 else f" (+{len(unknown) - 8} more)"
        raise AIOutputValidationError("unknown_source_ids", f"Model cited {len(unknown)} source ID(s) outside the provided batch: {sample}{suffix}")


def validate_ai_output(output: AIExtraction, pages: list[PageRecord], spans: list[SourceSpan], catalog: list[dict],
                       *, local_batch: ExtractionBatch | None = None, review: dict | None = None) -> ExtractionBatch:
    if review is not None and local_batch is None:
        raise ValueError("Targeted AI review requires the completed local extraction baseline")
    if review is not None:
        allowed = set(review["target_source_ids"]) | set(review["context_source_ids"])
        spans = [span for span in spans if span.id in allowed and span.page in review["pages"]]
    source_map = {s.id: s for s in spans}
    systems = {p.page: p.system for p in pages}
    catalog_ids = {p["product_id"] for p in catalog}
    # Begin from deterministic extraction: AI must not make detected schedule
    # rows disappear, overwrite numeric conversions, or duplicate package parts.
    result = local_batch.model_copy(deep=True) if local_batch is not None else extract_local_batch(pages, spans, catalog)
    covered = {source for p in result.positions for source in p.source_span_ids}
    by_source = {source: p for p in result.positions for source in p.source_span_ids}
    targets = set(review["target_source_ids"]) if review is not None else set()
    target_positions = set(review["position_ids"]) if review is not None else set()
    seen_anchors: set[str] = set()

    def validate_target(ids: list[str]) -> None:
        if review is not None and not targets.intersection(ids):
            raise AIOutputValidationError("outside_review_scope", "Model output must address a targeted source; context is evidence only")

    for item in output.positions:
        ids = [item.anchor_source_id, *item.source_ids, *item.quantity_source_ids]
        for attr in item.attributes:
            ids.extend(attr.source_ids)
        _validate_sources(ids, source_map)
        _validate_sources(item.source_ids, source_map)
        _validate_sources(item.quantity_source_ids, source_map, required=item.quantity is not None)
        validate_target([item.anchor_source_id])
        if review is not None and item.anchor_source_id in seen_anchors:
            raise AIOutputValidationError("duplicate_review_anchor", "Model returned duplicate positions for a targeted source")
        seen_anchors.add(item.anchor_source_id)
        if item.product_id and item.product_id not in catalog_ids:
            raise ValueError("Model selected an unknown catalogue ID")
        if item.anchor_source_id in covered:
            original = by_source.get(item.anchor_source_id)
            if review is not None:
                matches = [position for position in result.positions if position.id in target_positions
                           and item.anchor_source_id in position.source_span_ids]
                anchored = [position for position in matches if item.anchor_source_id in position.field_sources.get("quantity", [])]
                matches = anchored or matches
                if len(matches) != 1 or not reviewable_position(matches[0]):
                    raise AIOutputValidationError("protected_local_position", "Model cannot change a completed, manual, accepted, or excluded local position")
                original = matches[0]
            if original is None:
                continue
            attributes = _validated_attributes(item, source_map)
            candidate = original.model_copy(deep=True)
            # Deterministic quantities/conversions remain authoritative. Missing
            # attributes can improve retrieval; existing claims become proposals.
            conflicts = {key: value for key, value in attributes.items()
                         if key in original.attributes and str(original.attributes[key]) != value}
            candidate.attributes.update({key: value for key, value in attributes.items() if key not in original.attributes})
            candidate.field_sources.update({a.key: a.source_ids for a in item.attributes
                                            if a.key in attributes and a.key not in original.attributes})
            if item.product_id:
                candidate.product_id = item.product_id
            candidate = match_position(candidate, catalog)
            proposed_product = candidate.product_id
            if candidate.match_evidence_band == "conflicting":
                candidate.product_id = original.product_id
                candidate.pricing_basis = original.pricing_basis
                candidate.status = "review_required"
            changes = {}
            requested_product = item.product_id or proposed_product
            if requested_product != original.product_id and requested_product:
                changes["product_id"] = requested_product
                candidate.product_id = original.product_id
                candidate.pricing_basis = original.pricing_basis
                candidate.status = "review_required"
            if conflicts:
                changes["attributes"] = conflicts
            if item.description and item.description != original.description:
                changes["description"] = item.description
            if item.category != "unclassified" and item.category != original.category:
                changes["category"] = item.category
            if item.system and item.system != original.system and _supported_system(item.system, {source: source_map[source] for source in ids}, systems):
                changes["system"] = item.system
            if item.quantity is not None and normalize_number(item.quantity) != original.quantity:
                evidence = " ".join(source_map[s].text for s in item.quantity_source_ids)
                supported = {Decimal(normalize_number(n)) for n in re.findall(r"\d[\d']*(?:[.,]\d+)?", evidence)}
                if Decimal(normalize_number(item.quantity)) in supported and item.quantity == item.raw_quantity:
                    changes["quantity"] = normalize_number(item.quantity)
                    if original.unit is None and normalize_unit(item.unit) in {"pc", "m", "m2", "h", "LS", "system"} and (review is None or _supported_unit(item, source_map)):
                        changes["unit"] = normalize_unit(item.unit)
            if original.unit is None and _supported_unit(item, source_map):
                changes["unit"] = normalize_unit(item.unit)
            if review is not None:
                # Matching is advisory in the review pass. A suggested product
                # must not silently replace its category, labour rule, or price
                # basis before the estimator accepts the proposal.
                for field in ("quantity", "unit", "raw_quantity", "raw_unit", "description", "category", "system",
                              "product_id", "install_code", "pricing_basis", "status", "technical_equivalence"):
                    setattr(candidate, field, getattr(original, field))
            if changes:
                proposal = refinement_proposal(original, changes, list(dict.fromkeys(ids)))
                proposals = candidate.attributes.setdefault("ai_refinement_proposals", [])
                if not any(existing.get("id") == proposal["id"] for existing in proposals):
                    proposals.append(proposal)
                if review is not None:
                    candidate.status = "review_required"
            result.positions[result.positions.index(original)] = candidate
            for source_id in original.source_span_ids:
                by_source[source_id] = candidate
            continue
        source = source_map[item.anchor_source_id]
        if source.kind.startswith("package"):
            continue
        quantity = normalize_number(item.quantity) if item.quantity is not None else None
        if quantity is not None:
            # A raw value must be present in cited text. This check cannot prove
            # semantic correctness, but prevents obvious fabricated numbers.
            evidence = " ".join(source_map[s].text for s in item.quantity_source_ids)
            numbers = __import__("re").findall(r"\d[\d'’`]*(?:[.,]\d+)?", evidence)
            supported = {normalize_number(n.replace("`", "")) for n in numbers}
            raw = normalize_number(item.raw_quantity) if item.raw_quantity else quantity
            if raw not in supported:
                raise ValueError("Extracted quantity is unsupported by cited source text")
            if quantity != raw:
                raise ValueError("AI numeric conversion must be confirmed by the deterministic parser")
        p = Position(id=f"POS-{_id(source.document_id, source.id)}", document_id=source.document_id,
                     system=item.system if item.system and _supported_system(item.system, {source_id: source_map[source_id] for source_id in ids}, systems) else systems.get(source.page, "Unassigned"), category=item.category,
                     description=item.description, original_description="\n".join(source_map[s].text for s in item.source_ids),
                     quantity=quantity, unit=normalize_unit(item.unit), raw_quantity=item.raw_quantity, raw_unit=item.raw_unit,
                     source_page=source.page, source_span_ids=list(dict.fromkeys(ids)),
                     field_sources={"description": item.source_ids, "quantity": item.quantity_source_ids},
                     attributes=_validated_attributes(item, source_map), product_id=item.product_id,
                     assumptions=[item.assumption] if item.assumption else [])
        if item.supplied_by_others:
            evidence = " ".join(source_map[s].text for s in item.source_ids).lower()
            if "bauseits" not in evidence and "einbau der folgenden feldgeräte" not in evidence:
                raise ValueError("Supplied-by-others claim requires explicit evidence")
            p.scope_tags = ["supplied_by_others"]
        p = match_position(p, catalog)
        # AI-selected conflicting references remain unresolved and cannot price.
        if p.match_evidence_band == "conflicting":
            p.product_id, p.pricing_basis, p.status = None, "unpriced", "review_required"
        result.positions.append(p)
        if review is not None:
            result.dispositions[item.anchor_source_id] = "position"
        covered.update(p.source_span_ids)
        by_source.update({source_id: p for source_id in p.source_span_ids})
    for req in output.requirements:
        _validate_sources(req.source_ids, source_map)
        validate_target(req.source_ids)
        result.requirements.append(Requirement(id=f"REQ-{_id(*req.source_ids, req.title)}", title=req.title, description=req.description, category=req.category, source_page=source_map[req.source_ids[0]].page, source_span_ids=req.source_ids))
    for issue in output.issues:
        _validate_sources(issue.source_ids, source_map)
        validate_target(issue.source_ids)
        result.issues.append(Issue(id=f"ISS-{_id(*issue.source_ids, issue.kind)}", kind=issue.kind, severity=issue.severity, title=issue.title, detail=issue.detail, action=issue.action, source_span_ids=issue.source_ids))
    for item in output.dispositions:
        _validate_sources([item.source_id], source_map)
        validate_target([item.source_id])
        if result.dispositions.get(item.source_id) != "position":
            result.dispositions[item.source_id] = item.disposition
    return result


def _supported_system(system: str, source_map: dict[str, SourceSpan], systems: dict[int, str]) -> bool:
    if system.casefold() in {"", "unassigned", "unknown"}:
        return False
    return system in systems.values() or any(re.search(r"(?<!\w)" + re.escape(system) + r"(?!\w)", source.text, re.I)
                                            for source in source_map.values())


def _supported_unit(item: ExtractedPosition, source_map: dict[str, SourceSpan]) -> bool:
    unit = normalize_unit(item.unit)
    if unit not in {"pc", "m", "m2", "h", "LS", "system"} or not item.raw_unit:
        return False
    if normalize_unit(item.raw_unit) != unit:
        return False
    return any(re.search(r"(?<!\w)" + re.escape(item.raw_unit) + r"(?!\w)", source_map[source].text, re.I)
               for source in set(item.source_ids + item.quantity_source_ids))


def _position_payload(position: Position, allowed_sources: set[str] | None = None) -> dict:
    saved = position.model_dump()
    payload = {key: saved[key] for key in ("id", "description", "original_description", "quantity", "unit",
        "raw_quantity", "raw_unit", "category", "system", "source_span_ids", "field_sources", "attributes",
        "product_id", "install_code", "warnings", "assumptions")}
    if allowed_sources is None:
        return payload
    payload["source_context_truncated"] = bool(set(payload["source_span_ids"]) - allowed_sources)
    payload["source_span_ids"] = [source for source in payload["source_span_ids"] if source in allowed_sources]
    payload["field_sources"] = {field: [source for source in sources if source in allowed_sources]
                                for field, sources in payload["field_sources"].items()}
    payload["attributes"].pop("ai_refinement_proposals", None)
    payload["attributes"].pop("pricing_proposals", None)
    for warning in payload["warnings"]:
        warning["source_span_ids"] = [source for source in warning["source_span_ids"] if source in allowed_sources]
    return payload


async def extract_ai_batch(pages: list[PageRecord], spans: list[SourceSpan], catalog: list[dict], model: str,
                           *, local_batch: ExtractionBatch | None = None, review: dict | None = None) -> ExtractionBatch:
    if review is not None and local_batch is None:
        raise ValueError("Targeted AI review requires the completed local extraction baseline")
    if not os.environ.get("OPENAI_API_KEY"):
        raise RuntimeError("OPENAI_API_KEY is not configured. Local extraction remains available.")
    relevant_pages = {p.page for p in pages}
    source = [s for s in spans if s.page in relevant_pages]
    if review is not None:
        allowed = set(review["target_source_ids"]) | set(review["context_source_ids"])
        source = [span for span in source if span.id in allowed and span.page in review["pages"]]
        pages = [page for page in pages if page.page in review["pages"]]
        if not review["target_source_ids"]:
            raise ValueError("Targeted AI review requires unresolved source targets")
        _validate_sources(review["target_source_ids"], {span.id: span for span in source})
    baseline = local_batch if local_batch is not None else extract_local_batch(pages, source, catalog)
    payload = {
        "schema_version": SCHEMA_VERSION,
        "pages": [{"page": p.page, "system": p.system, "warnings": p.warnings} for p in pages],
        "source_blocks": [{"id": s.id, "page": s.page, "text": s.text, "kind": s.kind} for s in source],
        "existing_positions": [_position_payload(p, {span.id for span in source} if review is not None else None)
                               for p in baseline.positions if review is None or p.id in review["position_ids"]],
        "catalogue": [{k: c.get(k) for k in ("product_id", "category", "description", "unit", "install_code", "supplier_quote_required")} for c in catalog],
    }
    if review is not None:
        payload["review"] = review
        for block in payload["source_blocks"]:
            block["role"] = "target" if block["id"] in review["target_source_ids"] else "context"
    messages: list = [{"role": "system", "content": SYSTEM_PROMPT + "\n" + (REVIEW_PROMPT if review is not None else EXTRACTION_PROMPT) +
                      "\nExisting positions are deterministic parser results. Return existing anchors when you can improve their attributes or matching, plus overlooked positions. Preserve their grounded quantities and conversions; do not reproduce unchanged positions. Do not treat model numbers or dimensions as quantities."},
                      {"role": "user", "content": json.dumps(payload, ensure_ascii=False)}]
    reasoning_effort = os.environ.get("OPENAI_REASONING_EFFORT", "").strip()
    supports_reasoning = model.startswith(("gpt-5", "gpt-6", "o1", "o3", "o4"))
    options = {"reasoning": {"effort": reasoning_effort}} if reasoning_effort and supports_reasoning else {}
    usage: dict = {}
    usage_unavailable_attempts = 0

    def add_usage(target: dict, values: dict):
        for key, value in values.items():
            if isinstance(value, dict):
                add_usage(target.setdefault(key, {}), value)
            elif isinstance(value, (int, float)) and not isinstance(value, bool):
                target[key] = target.get(key, 0) + value

    # SDK retries transient network/rate failures twice; validation gets one repair.
    async with AsyncOpenAI(max_retries=2, timeout=120.0) as client:
        for attempt in range(2):
            response = None
            try:
                # Pydantic schema errors can be raised by parse itself, before a
                # response object is available; they get the same bounded repair.
                response = await client.responses.parse(model=model, input=messages, text_format=AIExtraction,
                                                        store=False, max_output_tokens=16000, **options)
                if response.usage:
                    add_usage(usage, response.usage.model_dump())
                else:
                    usage_unavailable_attempts += 1
                if response.output_parsed is None:
                    raise ValueError("OpenAI returned no structured extraction")
                result = validate_ai_output(response.output_parsed, pages, source, catalog, local_batch=local_batch, review=review)
                result.usage = {"mode": "ai_targeted_review" if review is not None else "ai_with_local_validation", "model": model, "prompt_version": PROMPT_VERSION, "schema_version": SCHEMA_VERSION,
                                "repair_attempts": attempt, "usage_unavailable_attempts": usage_unavailable_attempts, **usage}
                if options:
                    result.usage["reasoning_effort"] = reasoning_effort
                return result
            except ValueError as exc:
                if response is None:
                    # The SDK does not expose usage when structured parsing fails.
                    usage_unavailable_attempts += 1
                if attempt:
                    error = AIOutputValidationError(getattr(exc, "code", "structured_output_validation"),
                        f"AI extraction validation failed after repair: {exc}")
                    error.usage = {**usage, "repair_attempts": attempt, "usage_unavailable_attempts": usage_unavailable_attempts}
                    raise error from exc
                messages.append({"role": "user", "content": f"The previous output failed schema or evidence validation: {exc}. Return a corrected complete structured extraction using existing sources only."})
    raise RuntimeError("AI extraction did not complete")
