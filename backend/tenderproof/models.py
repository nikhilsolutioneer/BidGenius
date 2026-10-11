"""Shared domain contract. Financial values are decimal strings on the wire."""
from __future__ import annotations

from typing import Any, Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator


class Model(BaseModel):
    model_config = ConfigDict(extra="forbid")


Outcome = Literal["calculated", "supplier_quote_required", "assumption_applied", "review_required", "insufficient_information", "out_of_scope", "non_priceable"]
ReviewState = Literal["pending", "accepted", "rejected"]
PricingBasis = Literal["catalogue", "supplier_reference", "confirmed_quote", "labour_only", "manual_assumption", "included_elsewhere", "unpriced"]


class SourceSpan(Model):
    id: str
    document_id: str
    page: int
    text: str
    x0: float
    top: float
    x1: float
    bottom: float
    page_width: float
    page_height: float
    kind: str = "text"
    disposition: str = "unresolved"


class PageRecord(Model):
    page: int
    width: float
    height: float
    text: str
    span_ids: list[str] = Field(default_factory=list)
    system: str = "Unassigned"
    printed_label: str | None = None
    status: str = "parsed"
    extraction_status: str = "pending"
    warnings: list[str] = Field(default_factory=list)


class Issue(Model):
    id: str
    kind: str
    severity: Literal["info", "warning", "blocker"] = "warning"
    title: str
    detail: str
    source_span_ids: list[str] = Field(default_factory=list)
    position_ids: list[str] = Field(default_factory=list)
    action: str = "Review source evidence."
    review_state: ReviewState = "pending"


class MatchCandidate(Model):
    product_id: str
    satisfied: list[str] = Field(default_factory=list)
    missing: list[str] = Field(default_factory=list)
    conflicts: list[str] = Field(default_factory=list)
    explanation: str = ""


class CostLine(Model):
    material_cost_chf: str | None = None
    labour_cost_chf: str | None = None
    direct_cost_chf: str | None = None
    net_unit_cost_chf: str | None = None
    material_before_waste_chf: str | None = None
    waste_chf: str | None = None
    adjusted_install_hours: str | None = None
    unrounded_hours: str | None = None
    base_hours_per_unit: str | None = None
    labour_role: str | None = None
    hourly_rate_chf: str | None = None
    factors: dict[str, str] = Field(default_factory=dict)
    unrounded_material: str | None = None
    unrounded_labour: str | None = None
    unrounded_direct: str | None = None
    formula: str = ""
    references: list[str] = Field(default_factory=list)


class Position(Model):
    id: str
    lv_id: str = ""
    reference: str = ""
    tender_line_number: str | None = None
    document_id: str
    system: str = "Unassigned"
    category: str = "unclassified"
    description: str
    original_description: str = ""
    quantity: str | None = None
    unit: str | None = None
    raw_quantity: str | None = None
    raw_unit: str | None = None
    source_page: int
    source_span_ids: list[str] = Field(default_factory=list)
    field_sources: dict[str, list[str]] = Field(default_factory=dict)
    attributes: dict[str, Any] = Field(default_factory=dict)
    origin: Literal["extracted", "manual"] = "extracted"
    product_id: str | None = None
    install_code: str | None = None
    pricing_basis: PricingBasis = "unpriced"
    status: Outcome = "insufficient_information"
    review_state: ReviewState = "pending"
    technical_equivalence: Literal["unverified", "reviewer_confirmed", "incompatible"] = "unverified"
    match_evidence_band: Literal["strong", "partial", "conflicting"] = "partial"
    candidates: list[MatchCandidate] = Field(default_factory=list)
    warnings: list[Issue] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    included_in: str | None = None
    scope_tags: list[str] = Field(default_factory=list)
    overrides: dict[str, Any] = Field(default_factory=dict)
    cost: CostLine | None = None

    @model_validator(mode="after")
    def stable_lv_alias(self):
        self.lv_id = self.id
        return self


class Requirement(Model):
    id: str
    title: str
    description: str
    source_page: int
    source_span_ids: list[str] = Field(default_factory=list)
    category: str = "commercial"
    review_state: ReviewState = "pending"


class CommercialAdjustment(Model):
    id: str
    kind: Literal["risk", "opportunity"]
    title: str
    amount_chf: str
    scope: str = "project_level"
    basis: str
    source_span_ids: list[str] = Field(default_factory=list)
    review_state: ReviewState = "pending"
    overlap_resolution: str | None = None
    created_at: str = ""
    updated_at: str = ""


class ReviewDecision(Model):
    id: str
    actor: str = "Local estimator"
    timestamp: str
    reason: str
    entity_type: str
    entity_id: str
    old_value: Any = None
    new_value: Any = None
    revision: int
    price_delta_chf: str = "0.00"
    cost_delta_chf: str = "0.00"
    reverses_id: str | None = None


class Document(Model):
    id: str
    filename: str
    sha256: str
    page_count: int = 0


class Run(Model):
    id: str
    project_id: str
    status: Literal["queued", "running", "awaiting_review", "complete", "failed", "cancelled", "resumable"] = "queued"
    stage: str = "queued"
    pages_processed: int = 0
    total_pages: int = 0
    batches_done: int = 0
    batches_total: int = 0
    positions_found: int = 0
    local_positions_found: int | None = None
    ai_batches_done: int = 0
    ai_batches_total: int = 0
    errors: list[str] = Field(default_factory=list)
    extraction_mode: str = "local"
    model: str | None = None
    prompt_version: str = "1.0"
    schema_version: str = "1.1"
    parser_version: str = "local-1.6"
    started_at: str = ""
    updated_at: str = ""
    completed_at: str | None = None
    duration_seconds: float | None = None
    usage: dict[str, Any] = Field(default_factory=dict)
    cancellation_requested: bool = False


class ExtractionBatch(Model):
    positions: list[Position] = Field(default_factory=list)
    requirements: list[Requirement] = Field(default_factory=list)
    issues: list[Issue] = Field(default_factory=list)
    dispositions: dict[str, str] = Field(default_factory=dict)
    usage: dict[str, Any] = Field(default_factory=dict)
    errors: list[str] = Field(default_factory=list)


class RevisionMutation(Model):
    expected_revision: int
    reason: str = Field(min_length=3, max_length=2000)


class PositionPatch(RevisionMutation):
    changes: dict[str, Any]


class ManualPositionCreate(RevisionMutation):
    source_span_ids: list[str] = Field(min_length=1)
    description: str = Field(min_length=2)
    system: str = "Unassigned"
    category: str = "unclassified"
    quantity: str | None = None
    unit: str | None = None
    product_id: str | None = None
    acknowledge_duplicate: bool = False


class AdjustmentCreate(RevisionMutation):
    kind: Literal["risk", "opportunity"]
    title: str = Field(min_length=3)
    amount_chf: str
    scope: str = "project_level"
    basis: str = Field(min_length=3)
    source_span_ids: list[str] = Field(default_factory=list)
    overlap_resolution: str | None = None


class AdjustmentPatch(RevisionMutation):
    changes: dict[str, Any]


class AssumptionsPatch(RevisionMutation):
    changes: dict[str, Any]


class WhatIfPreviewRequest(Model):
    expected_revision: int
    changes: dict[str, Any]
    include_positions: bool = False


class ResumeRequest(RevisionMutation):
    action: Literal["continue", "complete_review"] = "continue"


class StartRunRequest(Model):
    use_ai: bool = False


class ExportRequest(Model):
    revision: int
    format: Literal["csv", "json", "html", "rfq", "zip"] = "zip"


class ScenarioRequest(Model):
    revision: int | None = None
    overrides: dict[str, Any] = Field(default_factory=dict)
