"""Application use cases: immutable revisions, source-backed review and pricing."""
from __future__ import annotations

from copy import deepcopy
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP, ROUND_CEILING
import json
from pathlib import Path
from typing import Any, Callable
import hashlib
import re
import shutil
from time import perf_counter
import uuid

from .models import (AdjustmentCreate, CommercialAdjustment, Document, Issue, ManualPositionCreate, Position, ReviewDecision)
from .storage import DomainError, Repository, now
from .duct_rules import DUCT_DEFAULTS


HUMAN_REVIEW_STATUSES = {"review_required", "assumption_applied", "supplier_quote_required"}


def identifier(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:16]}"


def number(value: Any, name: str, minimum: Decimal | None = None) -> Decimal:
    try:
        if isinstance(value, bool):
            raise InvalidOperation()
        result = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        raise DomainError(f"{name} must be a finite decimal number.")
    if not result.is_finite() or (minimum is not None and result < minimum):
        raise DomainError(f"{name} is outside its permitted range.")
    return result


def amount(value: Any) -> str:
    return str(Decimal(str(value or "0")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def labour_rate_defaults(productivity: list[dict]) -> dict[str, str]:
    """Expose one unambiguous productivity.csv rate for each priced labour role."""
    rates: dict[str, set[Decimal]] = {}
    spellings: dict[str, str] = {}
    for rule in productivity:
        role = str(rule.get("labour_role") or "").strip()
        if not role or rule.get("install_code") == "UNKNOWN":
            continue
        value = Decimal(str(rule.get("default_hourly_rate_chf", "")))
        rates.setdefault(role, set()).add(value)
        spellings.setdefault(role, str(rule["default_hourly_rate_chf"]))
    return {role: spellings[role] for role, values in sorted(rates.items()) if len(values) == 1}


def parameter_defaults(project: dict) -> dict:
    parameters = deepcopy(project["parameters"])
    duct = parameters.get("duct_pricing", {})
    parameters["duct_pricing"] = {**DUCT_DEFAULTS, **(duct if isinstance(duct, dict) else {})}
    labour_rates = parameters.get("labour_rates_chf_per_h", {})
    defaults = labour_rate_defaults(project.get("productivity", []))
    parameters["labour_rates_chf_per_h"] = {
        **defaults,
        **(labour_rates if isinstance(labour_rates, dict) else {}),
    }
    return parameters


def deep_update(original: dict, patch: dict) -> dict:
    result = deepcopy(original)
    for key, value in patch.items():
        if key not in original:
            raise DomainError(f"Unknown parameter: {key}")
        if isinstance(original[key], dict):
            if not isinstance(value, dict):
                raise DomainError(f"{key} must be an object.")
            result[key] = deep_update(original[key], value)
        else:
            result[key] = value
    return result


def position_needs_human_review(position: dict) -> bool:
    if position["review_state"] != "pending" or position["status"] in ("non_priceable", "out_of_scope"):
        return False
    if position["status"] in HUMAN_REVIEW_STATUSES:
        return True
    attrs = position.get("attributes", {})
    proposal_groups = (attrs.get("pricing_proposals", []), attrs.get("ai_refinement_proposals", []))
    return any(
        (proposal.get("review_state") or proposal.get("state")) == "pending"
        for proposals in proposal_groups
        for proposal in proposals
    )


class EstimateService:
    def __init__(self, repo: Repository):
        self.repo = repo

    def create_project(self, package: Path, copy_files: bool = True, estimator: str = "Local estimator") -> dict:
        from .reference import load_reference
        references = load_reference(package)
        references["parameters"].setdefault("duct_pricing", deepcopy(DUCT_DEFAULTS))
        references["parameters"].setdefault("labour_rates_chf_per_h", labour_rate_defaults(references["productivity"]))
        source_filename = references["parameters"].get("project", {}).get("source_tender_file", "")
        pdf_path = package / Path(source_filename).name if source_filename else None
        if pdf_path is None or not pdf_path.is_file():
            candidates = list(package.glob("*.pdf"))
            if len(candidates) != 1:
                raise DomainError("Package must contain exactly one source tender PDF or specify it in project_parameters.json.")
            pdf_path = candidates[0]
        project_id, document_id = identifier("project"), identifier("doc")
        destination = self.repo.directory / "projects" / project_id / "originals"
        destination.mkdir(parents=True, exist_ok=True)
        # Runtime inputs only. Ground-truth fixtures are not read or copied into runtime projects.
        for source in [pdf_path, package / "catalog.csv", package / "productivity.csv", package / "project_parameters.json"]:
            shutil.copy2(source, destination / source.name)
        local_pdf = destination / pdf_path.name
        doc = Document(id=document_id, filename=local_pdf.name, sha256=hashlib.sha256(local_pdf.read_bytes()).hexdigest())
        project = {
            "id": project_id,
            "name": references["parameters"].get("project", {}).get("name", "Tender estimate"),
            "created_at": now(), "updated_at": now(), "revision": 0,
            "estimator": estimator.strip() or "Local estimator", "bid_status": "draft",
            "document": doc.model_dump(), "parameters": references["parameters"],
            "catalog": references["catalog"], "productivity": references["productivity"],
            "positions": [], "issues": [], "requirements": [], "adjustments": [], "history": [],
            "estimate": {}, "latest_run_id": None, "review_complete": False,
            "policy": "full_draft_v1", "_package_dir": str(destination),
        }
        self.repo.create_project(project, local_pdf)
        return project

    def public_project(self, project: dict) -> dict:
        result = {k: deepcopy(project.get(k)) for k in ("id", "name", "revision", "created_at", "updated_at", "document", "parameters", "review_complete", "policy")}
        result["parameters"] = parameter_defaults(project)
        result["latest_run"] = self.latest_run(project)
        result["estimator"] = project.get("estimator", "Local estimator")
        result["bid_status"] = project.get("bid_status", "draft")
        return result

    def patch_meta(self, project_id: str, expected_revision: int, reason: str, changes: dict, actor: str | None = None) -> dict:
        if not changes or set(changes) - {"estimator", "bid_status"}:
            raise DomainError("Unsupported project metadata.")
        if "bid_status" in changes and changes["bid_status"] not in ("draft", "in_review", "approved", "submitted"):
            raise DomainError("Unsupported bid status.")
        def apply(project):
            old = {key: project.get(key, "Local estimator" if key == "estimator" else "draft") for key in changes}
            project.update(changes)
            return "project_meta", project_id, old, changes, {}
        return self.mutate(project_id, expected_revision, reason, apply, actor=actor)

    def latest_run(self, project: dict) -> dict | None:
        return self.repo.run(project["latest_run_id"]) if project.get("latest_run_id") else None

    def check_editable(self, project: dict):
        run = self.latest_run(project)
        if run and run["status"] in ("queued", "running"):
            raise DomainError("Processing is active. Pause or finish the run before editing the estimate.", 409)
        if project["revision"] == 0:
            raise DomainError("Finish the first processing run before editing.", 409)

    def recalculate(self, project: dict):
        from .pricing import calculate_estimate
        from .proposals import enrich_position
        from .reference import fold_continuation_pages
        # Ensure continuation positions are folded into parents and references assigned
        spans = self.repo.spans(project["document"]["id"]) if "document" in project else None
        project["positions"] = fold_continuation_pages(project["positions"], spans)
        positions = [Position.model_validate(p) for p in project["positions"]]
        adjustments = [CommercialAdjustment.model_validate(a) for a in project["adjustments"]]
        estimate = calculate_estimate(positions, project["catalog"], project["productivity"], project["parameters"], adjustments, policy="full_draft_v1")
        project["positions"] = estimate.pop("positions")
        project["positions"] = [enrich_position(p, project) for p in project["positions"]]
        project["estimate"] = estimate
        from .commercial import apply_commercial
        apply_commercial(project)

    def validate_extracted_inputs(self, project: dict):
        """Quarantine invalid extraction references before pricing the draft.

        Interactive edits use strict calculator validation and are never silently
        repaired. Invalid inferred rules must not discard all valid PDF batches.
        """
        products = {p["product_id"]: p for p in project["catalog"]}
        rules = {r["install_code"]: r for r in project["productivity"]}
        for row in project["positions"]:
            if row["origin"] == "manual" or row.get("included_in"):
                continue
            unit = row.get("unit")
            rule = rules.get(row.get("install_code"))
            product = products.get(row.get("product_id"))
            conflicts = []
            if unit and rule and unit != rule["unit"]:
                conflicts.append(f"Inferred rule {row['install_code']} uses {rule['unit']}; source position uses {unit}. Installation remains unresolved.")
                row["attributes"]["rejected_install_code"] = row["install_code"]
                row["install_code"] = "UNKNOWN"
            if unit and product and unit != product["unit"]:
                conflicts.append(f"Proposed product {row['product_id']} uses {product['unit']}; source position uses {unit}. Pricing reference remains unresolved.")
                row["attributes"]["rejected_product_id"] = row["product_id"]
                row["product_id"], row["pricing_basis"] = None, "unpriced"
            if conflicts:
                row["status"] = "review_required"
                row["review_state"] = "pending"
                row["match_evidence_band"] = "conflicting"
                issue = Issue(id=f"{row['id']}-invalid-inferred-unit", kind="unit_conflict", severity="blocker",
                    title="Installation or pricing unit needs review", detail=" ".join(conflicts),
                    source_span_ids=row["source_span_ids"], position_ids=[row["id"]],
                    action="Choose an appropriate installation rule or document a supported unit conversion.")
                row["warnings"] = [w for w in row["warnings"] if w["id"] != issue.id] + [issue.model_dump()]

    def summary(self, project_id: str, revision: int | None = None) -> dict:
        p = self.repo.revision(project_id, revision) if revision is not None else self.repo.project(project_id)
        positions = [x for x in p["positions"] if not x.get("id", "").startswith("PKG-CONT-")]
        evidence_progress = p.get("document_processing") or self.document_progress(p)
        issues = {i["id"]: i for i in p["issues"]}
        for position in positions:
            for issue in position.get("warnings", []):
                issues.setdefault(issue["id"], issue)
        priced = [x for x in positions if x.get("pricing_basis") != "included_elsewhere"
                  and (x.get("cost") or {}).get("direct_cost_chf") is not None
                  and Decimal(str(x["cost"]["direct_cost_chf"])) > 0]
        included = [x for x in positions if x.get("pricing_basis") == "included_elsewhere"]
        provisional = [x for x in priced if x.get("pricing_basis") == "supplier_reference"]
        unpriced = [x for x in positions if (x.get("cost") or {}).get("direct_cost_chf") is None and x["pricing_basis"] != "included_elsewhere" and x["status"] not in ("non_priceable", "out_of_scope")]
        coverage = {
            "pages_processed": evidence_progress["pages_processed"],
            "total_pages": p["document"]["page_count"],
            "positions_extracted": sum(x["origin"] == "extracted" for x in positions),
            "positions_manual": sum(x["origin"] == "manual" for x in positions),
            "positions_priced": len(priced), "positions_unpriced": len(unpriced),
            "positions_included_elsewhere": len(included),
            "provisional_priced_positions": len(provisional),
            "provisional_direct_cost_chf": str(sum((Decimal(x["cost"]["direct_cost_chf"]) for x in provisional), Decimal("0")).quantize(Decimal("0.01"))),
            "pending_reviews": sum(position_needs_human_review(x) for x in positions),
            "unassigned_blocks": evidence_progress["unassigned_blocks"],
            "failed_pages": evidence_progress["failed_pages"],
            "partial_pages": evidence_progress["partial_pages"],
            "approved_positions": sum(x["review_state"] == "accepted" for x in positions),
            "supplier_quotes_required": sum(x["status"] == "supplier_quote_required" for x in positions),
        }
        from .proposals import unresolved_causes
        causes = [unresolved_causes(x) for x in positions]
        coverage["unresolved_by_cause"] = {key: sum(key in row for row in causes) for key in
            ("missing_quantity", "missing_material_reference", "missing_installation_rule", "technical_conflict", "quotation_required", "scope_ambiguity")}
        coverage["partial_cost_positions"] = sum((x.get("cost") or {}).get("direct_cost_chf") is None and
            any((x.get("cost") or {}).get(k) is not None for k in ("material_cost_chf", "labour_cost_chf")) for x in positions)
        grouped = {}
        for issue in issues.values():
            key = f"{issue.get('kind', '')}|{issue.get('detail', '')}"
            group = grouped.setdefault(key, {"group_key": key, "kind": issue.get("kind"), "detail": issue.get("detail"), "count": 0, "pages": [], "source_span_ids": [], "issue_ids": []})
            group["count"] += 1
            group["issue_ids"].append(issue["id"])
            group["source_span_ids"] = list(dict.fromkeys(group["source_span_ids"] + issue.get("source_span_ids", [])))
        span_pages = {s["id"]: s["page"] for s in self.repo.spans(p["document"]["id"])}
        for group in grouped.values():
            group["pages"] = sorted({span_pages[s] for s in group["source_span_ids"] if s in span_pages})
        result = {
            "project_id": p["id"], "revision": p["revision"], "name": p["name"],
            "document": p["document"], "coverage": coverage, "issues": list(issues.values()), "issue_groups": list(grouped.values()),
            "requirements": p["requirements"], "adjustments": p["adjustments"], "history": p["history"],
            "latest_run": p.get("run_provenance") if revision is not None else self.latest_run(p), "review_complete": p["review_complete"],
            "page_outcomes": evidence_progress["page_outcomes"],
            "unresolved_sources": evidence_progress.get("unresolved_sources", []),
            "policy": "full_draft_v1", "parameters": parameter_defaults(p),
            "totals": {}, "build_up": [], "by_system": [], "by_category": [],
            "assumptions": [], "scope_allocations": [], "scenarios": {},
        }
        result.update(p.get("estimate", {}))
        if result.get("scenarios") and not result["scenarios"].get("probability_curve") and result.get("totals"):
            from .pricing import calculate_scenarios
            baseline = result["totals"].get("unrounded_cost_baseline_chf", result["totals"].get("cost_baseline_chf"))
            if baseline:
                result["scenarios"]["probability_curve"] = calculate_scenarios(
                    baseline, parameter_defaults(p), result["scenarios"].get("assumptions", {})
                ).get("probability_curve", [])
        result["scenario_reference"] = self.scenario_reference_context(p, result["scenarios"])
        from .pricing import calculate_completeness, money
        priced_direct = result.get("totals", {}).get("direct_cost_chf")
        result["completeness"] = calculate_completeness(positions, priced_direct)
        allowance_items = {row["position_id"]: row for row in result["completeness"].get("itemized_allowances", [])}
        result["review_cause_stakes"] = []
        for cause, count in coverage["unresolved_by_cause"].items():
            stake = Decimal("0")
            for row, row_causes in zip(positions, causes):
                if cause not in row_causes:
                    continue
                allowance = allowance_items.get(row["id"], {})
                stake += Decimal(str(allowance.get("allowance_median_chf") or 0))
            result["review_cause_stakes"].append({"cause": cause, "count": count, "stake_chf": money(stake),
                "formula": "sum median benchmark allowance for affected positions; causes can overlap",
                "source": f"summary.completeness.itemized_allowances + unresolved causes - {count} positions"})
        result["review_cause_stakes"].sort(key=lambda row: Decimal(row["stake_chf"]), reverse=True)
        totals = result.get("totals", {})
        allowance = result["completeness"]
        overhead_rate = Decimal(str(p.get("parameters", {}).get("commercial", {}).get("overhead_pct", "0"))) / Decimal("100")
        margin = Decimal(str(p.get("parameters", {}).get("commercial", {}).get("target_margin_pct", "5.5"))) / Decimal("100")
        increment = Decimal(str(p.get("parameters", {}).get("commercial", {}).get("round_to_chf", "1000")))
        def likely(value):
            base = Decimal(str(totals.get("cost_baseline_chf", "0"))) + Decimal(str(value)) * (Decimal("1") + overhead_rate)
            return str((base / (Decimal("1") - margin) / increment).to_integral_value(rounding=ROUND_CEILING) * increment)
        result["likely_total_low"] = likely(allowance["allowance_low_chf"])
        result["likely_total_median"] = likely(allowance["allowance_median_chf"])
        result["likely_total_high"] = likely(allowance["allowance_high_chf"])
        result["likely_total_label"] = "Indicative full-scope range (benchmark-based, not a bid)"
        return result

    def sensitivity(self, project_id: str, expected_revision: int | None = None) -> dict:
        from .pricing import money, raw

        project = self.repo.project(project_id)
        revision = project["revision"]
        if expected_revision is not None and revision != expected_revision:
            raise DomainError("This estimate changed. Refresh and review the latest revision.", 409)
        params = parameter_defaults(project)
        steps: list[tuple[str, str, str, Decimal, str]] = [
            ("productivity_factors", "site_efficiency", "Site efficiency", Decimal("0.05"), "project_parameters.productivity_factors"),
            ("productivity_factors", "mounting_height_school", "Mounting height school", Decimal("0.05"), "project_parameters.productivity_factors"),
            ("productivity_factors", "mounting_height_sports_hall", "Mounting height sports hall", Decimal("0.05"), "project_parameters.productivity_factors"),
            ("productivity_factors", "school_logistics", "School logistics", Decimal("0.05"), "project_parameters.productivity_factors"),
            ("productivity_factors", "timber_interface", "Timber interface", Decimal("0.05"), "project_parameters.productivity_factors"),
            ("allowances", "material_waste_pct", "Material waste", Decimal("1"), "project_parameters.allowances"),
            ("commercial", "overhead_pct", "Overhead", Decimal("1"), "project_parameters.commercial"),
            ("commercial", "target_margin_pct", "Target margin", Decimal("1"), "project_parameters.commercial"),
        ]
        for role in params.get("labour_rates_chf_per_h", {}):
            steps.append(("labour_rates_chf_per_h", role, f"Labour rate: {role.replace('_', ' ')}", Decimal("0.05"), "productivity.csv + project_parameters.labour_rates_chf_per_h"))
        items = []
        current_price = Decimal(str(project["estimate"]["totals"]["selling_price_chf"]))
        for group, key, title, step, source in steps:
            current = params.get(group, {}).get(key)
            if current is None:
                continue
            base = Decimal(str(current))
            if group == "labour_rates_chf_per_h":
                down_value = base * (Decimal("1") - step)
                up_value = base * (Decimal("1") + step)
                step_label = "+/-5%"
            else:
                down_value = max(Decimal("0"), base - step)
                up_value = base + step
                step_label = f"+/-{step}"
            down = self.preview_what_if(project_id, revision, {group: {key: raw(down_value)}})
            up = self.preview_what_if(project_id, revision, {group: {key: raw(up_value)}})
            down_delta = Decimal(str(down["proposed"]["selling_price_chf"])) - current_price
            up_delta = Decimal(str(up["proposed"]["selling_price_chf"])) - current_price
            items.append({"key": f"{group}.{key}", "label": title, "group": group, "field": key,
                "step": step_label, "down_delta_chf": money(down_delta), "up_delta_chf": money(up_delta),
                "formula": "what-if preview offer price - current offer price", "source": source})
        items.sort(key=lambda row: max(abs(Decimal(row["down_delta_chf"])), abs(Decimal(row["up_delta_chf"]))), reverse=True)
        return {"revision": revision, "items": items, "steps": [{"key": row["key"], "step": row["step"]} for row in items]}

    @staticmethod
    def scenario_reference_context(project: dict, scenarios: dict) -> dict:
        """Compare the active win-model reference with the copied package defaults."""
        from .pricing import calculate_scenarios, decimal_value

        package_dir = project.get("_package_dir")
        if not package_dir:
            return {"defaults_available": False}
        try:
            source_parameters = json.loads((Path(package_dir) / "project_parameters.json").read_text(encoding="utf-8"))
        except (OSError, ValueError, TypeError):
            return {"defaults_available": False}
        totals = project.get("estimate", {}).get("totals", {})
        baseline = totals.get("unrounded_cost_baseline_chf", totals.get("cost_baseline_chf"))
        if baseline is None:
            return {"defaults_available": False}
        defaults = calculate_scenarios(baseline, source_parameters)["assumptions"]
        active = scenarios.get("assumptions", {})
        active_margin = active.get("reference_margin_pct")
        default_margin = defaults.get("reference_margin_pct")
        active_price = active.get("reference_price_chf")
        default_price = defaults.get("reference_price_chf")
        margin_differs = active_margin is not None and default_margin is not None and decimal_value(active_margin) != decimal_value(default_margin)
        price_differs = active_price is not None and default_price is not None and decimal_value(active_price) != decimal_value(default_price)
        return {
            "defaults_available": True,
            "source": "project_parameters.json",
            "reference_price_chf": active_price,
            "reference_margin_pct": active_margin,
            "default_reference_price_chf": default_price,
            "default_reference_margin_pct": default_margin,
            "reference_price_differs_from_default": price_differs,
            "reference_margin_differs_from_default": margin_differs,
        }

    def document_progress(self, project: dict) -> dict:
        pages = self.repo.pages(project["document"]["id"])
        spans = self.repo.spans(project["document"]["id"])
        return {
            "pages_processed": sum(p.get("extraction_status") == "processed" or p["status"] == "processed" for p in pages),
            "failed_pages": sum(p["status"] in ("failed", "needs_ocr") for p in pages),
            "partial_pages": sum(p["status"] == "partial" for p in pages),
            "unassigned_blocks": sum(s["disposition"] == "unresolved" for s in spans),
            "unresolved_sources": [{k: s[k] for k in ("id", "page", "text")} for s in spans if s["disposition"] == "unresolved"],
            "page_outcomes": [{k: p.get(k) for k in ("page", "status", "extraction_status", "system", "printed_label", "warnings")} for p in pages],
        }

    def mutate(self, project_id: str, expected_revision: int, reason: str, fn: Callable, actor: str | None = None) -> dict:
        def operation(project):
            self.check_editable(project)
            old_totals = deepcopy(project.get("estimate", {}).get("totals", {}))
            entity_type, entity_id, old_value, new_value, extra = fn(project)
            self.recalculate(project)
            project["revision"] += 1
            project["review_complete"] = False
            totals = project["estimate"]["totals"]
            price_delta = amount(Decimal(str(totals.get("selling_price_chf") or 0)) - Decimal(str(old_totals.get("selling_price_chf") or 0)))
            cost_delta = amount(Decimal(str(totals.get("cost_baseline_chf") or 0)) - Decimal(str(old_totals.get("cost_baseline_chf") or 0)))
            decision = ReviewDecision(id=identifier("decision"), actor=actor or "Local estimator", timestamp=now(), reason=reason, entity_type=entity_type, entity_id=entity_id, old_value=old_value, new_value=new_value, revision=project["revision"], price_delta_chf=price_delta, cost_delta_chf=cost_delta, reverses_id=extra.pop("reverses_id", None))
            project["history"].append(decision.model_dump(mode="json"))
            return {"revision": project["revision"], "price_delta_chf": price_delta, "cost_delta_chf": cost_delta, "decision_id": decision.id, **extra}
        project, result = self.repo.update_project(project_id, operation, expected_revision, snapshot=True)
        if result.get("position_id"):
            result["position"] = next(p for p in project["positions"] if p["id"] == result["position_id"])
        return result

    def locate(self, entity: str, entity_id: str) -> dict:
        for project in self.repo.projects():
            if any(item["id"] == entity_id for item in project[entity]):
                return project
        raise DomainError("Requested item not found.", 404)

    def patch_position(self, position_id: str, expected_revision: int, reason: str, changes: dict) -> dict:
        p = self.locate("positions", position_id)
        if set(changes) in ({"pricing_proposal"}, {"ai_refinement_proposal"}):
            from .proposals import review_proposal
            return review_proposal(self, p["id"], position_id, expected_revision, reason, changes)
        allowed = {"description", "system", "category", "quantity", "unit", "product_id", "install_code", "pricing_basis", "review_state", "technical_equivalence", "included_in", "overrides", "status"}
        if not changes or set(changes) - allowed:
            raise DomainError("The position edit contains unsupported fields.")
        if "status" in changes and changes["status"] not in ("out_of_scope", "non_priceable", "review_required"):
            raise DomainError("Scope decisions may exclude, mark non-priceable, or return a position to review. Pricing outcomes are calculated.")

        def apply(project):
            from .matching import match_position, validate_explicit_reference
            index = next(i for i, x in enumerate(project["positions"]) if x["id"] == position_id)
            old = deepcopy(project["positions"][index])
            updated = {**old, **changes}
            if old.get("attributes", {}).get("approved_price_proxy") and set(changes) & {"quantity", "unit", "install_code", "system", "category"}:
                updated["attributes"] = deepcopy(old["attributes"])
                updated["attributes"].pop("approved_price_proxy", None)
                updated["overrides"] = {k: v for k, v in old.get("overrides", {}).items() if k != "net_unit_cost_chf"}
                updated["pricing_basis"] = "unpriced"
                updated["assumptions"] = [a for a in old.get("assumptions", []) if not a.startswith("Pricing-only proxy ")]
            if "quantity" in changes and changes["quantity"] is not None:
                updated["quantity"] = str(number(changes["quantity"], "Quantity", Decimal(0)))
            if "unit" in changes and changes["unit"] not in ("pc", "m", "m2", "h", "LS", "system", None):
                raise DomainError("Unsupported unit. Use pc, m, m2, h, LS, or system.")
            if "overrides" in changes:
                if not isinstance(changes["overrides"], dict):
                    raise DomainError("Overrides must be an object.")
                allowed_overrides = {"net_unit_cost_chf", "hourly_rate_chf", "material_waste_pct", "factor_overrides", "install_code", "labour_only", "scope_inclusions"}
                if set(changes["overrides"]) - allowed_overrides:
                    raise DomainError("Unsupported calculation override.")
                updated["overrides"] = {**old["overrides"], **changes["overrides"]}
                updated["overrides"] = {k: v for k, v in updated["overrides"].items() if v is not None}
                if "scope_inclusions" in changes["overrides"]:
                    inclusions = changes["overrides"]["scope_inclusions"] or []
                    if not isinstance(inclusions, list) or any(not isinstance(x, str) for x in inclusions):
                        raise DomainError("Scope inclusions must be a list of scope names.")
                    updated["attributes"] = {**old["attributes"], "inclusions": inclusions}
            financial_changes = set(changes) - {"review_state", "technical_equivalence"}
            if financial_changes:
                if old.get("attributes", {}).get("_area_rule_original"):
                    updated["attributes"] = deepcopy(updated["attributes"])
                    updated["attributes"].pop("_area_rule_original", None)
                    updated["attributes"].pop("pricing_rule", None)
                    updated["attributes"]["estimator_area_override"] = True
                    updated["assumptions"] = [a for a in updated["assumptions"] if not a.startswith(("Rectangular duct area rate:", "Duct section pieces (LT):"))]
                updated["review_state"] = "pending"
                updated["assumptions"] = list(dict.fromkeys(updated["assumptions"] + [f"Estimator override: {reason}"]))
                updated["status"] = changes.get("status", old["status"] if old["status"] in ("out_of_scope", "non_priceable") else "assumption_applied")
                updated["technical_equivalence"] = "unverified"
                for adjustment in project["adjustments"]:
                    if adjustment["review_state"] == "accepted" and adjustment["scope"] in ("project_level", position_id, old["system"]):
                        adjustment["review_state"] = "pending"
            candidate = Position.model_validate(updated)
            if changes.get("product_id"):
                products = {x["product_id"]: x for x in project["catalog"]}
                if changes["product_id"] not in products:
                    raise DomainError("Selected product does not exist in this project's catalogue.")
                candidate = validate_explicit_reference(candidate, project["catalog"], changes["product_id"])
                # A user's explicit choice is retained; hard conflicts remain visible.
                candidate.product_id = changes["product_id"]
                product = products[candidate.product_id]
                candidate.install_code = product["install_code"]
                candidate.pricing_basis = "supplier_reference" if str(product["supplier_quote_required"]).lower() == "true" else "catalogue"
                candidate.status = "supplier_quote_required" if candidate.pricing_basis == "supplier_reference" else "assumption_applied"
                candidate.assumptions.append(f"Catalogue reference explicitly selected by estimator: {reason}")
            if candidate.review_state == "accepted" and candidate.technical_equivalence == "incompatible":
                raise DomainError("An incompatible technical selection must be corrected before acceptance.")
            if candidate.review_state == "accepted" and candidate.match_evidence_band == "conflicting":
                candidate.technical_equivalence = "unverified"
                candidate.assumptions.append(f"Conflicting pricing reference retained as an explicit estimator assumption: {reason}")
            if updated["status"] in ("out_of_scope", "non_priceable"):
                candidate.status = updated["status"]
            project["positions"][index] = candidate.model_dump(mode="json")
            return "position", position_id, old, deepcopy(project["positions"][index]), {"position_id": position_id}
        return self.mutate(p["id"], expected_revision, reason, apply)

    def create_position(self, project_id: str, request: ManualPositionCreate) -> dict:
        def apply(project):
            from .matching import match_position
            sources = self.repo.sources_for_project(project, request.source_span_ids)
            duplicates = [p for p in project["positions"] if set(p["source_span_ids"]) & set(request.source_span_ids)]
            if duplicates and not request.acknowledge_duplicate:
                raise DomainError("Selected evidence overlaps existing positions.", 409, {"message": "Review existing positions, or acknowledge an intentional split with a reason.", "duplicates": duplicates})
            if request.unit not in ("pc", "m", "m2", "h", "LS", "system", None):
                raise DomainError("Unsupported unit.")
            quantity = str(number(request.quantity, "Quantity", Decimal(0))) if request.quantity is not None else None
            original = "\n".join(s["text"] for s in sorted(sources, key=lambda s: (s["page"], s["top"], s["x0"])))
            position = Position(
                id=identifier("manual"), document_id=project["document"]["id"], system=request.system,
                category=request.category, description=request.description, original_description=original,
                quantity=quantity, unit=request.unit, raw_quantity=None, raw_unit=None,
                source_page=min(s["page"] for s in sources), source_span_ids=list(dict.fromkeys(request.source_span_ids)),
                field_sources={"description": request.source_span_ids}, origin="manual",
                product_id=request.product_id, status="assumption_applied",
                assumptions=[f"Manually created from source evidence: {request.reason}", "Quantity and unit entered by estimator; verify against original evidence."],
            )
            position = match_position(position, project["catalog"])
            position.origin = "manual"
            position.review_state = "pending"
            if request.product_id:
                products = {x["product_id"]: x for x in project["catalog"]}
                if request.product_id not in products:
                    raise DomainError("Unknown product reference.")
                position.product_id = request.product_id
                position.install_code = products[request.product_id]["install_code"]
            project["positions"].append(position.model_dump(mode="json"))
            return "position", position.id, None, position.model_dump(mode="json"), {"position_id": position.id}
        return self.mutate(project_id, request.expected_revision, request.reason, apply)

    def preview_what_if(self, project_id: str, expected_revision: int, changes: dict, include_positions: bool = False) -> dict:
        """Reprice an in-memory candidate with the same Decimal engine used by saved revisions."""
        started = perf_counter()
        project = self.repo.project(project_id)
        if project["revision"] != expected_revision:
            raise DomainError("This estimate changed. Refresh and review the latest revision.", 409)
        self.check_editable(project)
        if not project.get("estimate", {}).get("totals"):
            raise DomainError("Finish processing before previewing estimate changes.", 409)
        project["parameters"] = parameter_defaults(project)

        allowed = {
            "productivity_factors": {"site_efficiency", "mounting_height_school", "mounting_height_sports_hall", "school_logistics", "timber_interface"},
            "allowances": {"material_waste_pct"},
            "commercial": {"overhead_pct", "target_margin_pct"},
            "labour_rates_chf_per_h": set(project["parameters"].get("labour_rates_chf_per_h", {})),
            "duct_pricing": {"rect_duct_area_rate_enabled"},
        }
        if not isinstance(changes, dict) or set(changes) - set(allowed):
            raise DomainError("Unsupported What-if assumption.")
        for group, fields in changes.items():
            if not isinstance(fields, dict) or set(fields) - allowed[group]:
                raise DomainError(f"Unsupported What-if assumption in {group}.")

        from .pricing import calculate_estimate, money, raw, validate_parameters
        candidate = deepcopy(project)
        candidate["parameters"] = deep_update(project["parameters"], changes)
        try:
            validate_parameters(candidate["parameters"])
        except ValueError as exc:
            raise DomainError(str(exc)) from None

        current_estimate = project["estimate"]
        calculated = calculate_estimate(
            [Position.model_validate(row) for row in project["positions"]],
            project["catalog"], project["productivity"], candidate["parameters"],
            [CommercialAdjustment.model_validate(row) for row in project["adjustments"]],
            policy=project.get("policy", "full_draft_v1"),
        )
        candidate["positions"] = calculated.pop("positions")
        candidate["estimate"] = calculated
        from .commercial import apply_commercial
        apply_commercial(candidate)
        proposed_estimate = candidate["estimate"]

        def total_view(estimate: dict, positions: list[dict]) -> dict:
            totals = estimate["totals"]
            hours = sum((Decimal(row["cost"]["unrounded_hours"]) for row in positions
                         if row.get("cost") and row["cost"].get("unrounded_hours") is not None), Decimal("0"))
            return {
                "material_chf": totals["material_cost_chf"],
                "labour_chf": totals["labour_cost_chf"],
                "hours": raw(hours),
                "baseline_chf": totals["cost_baseline_chf"],
                "selling_price_chf": totals["selling_price_chf"],
                "scenarios": deepcopy(estimate.get("scenarios", {}).get("scenarios", [])),
            }

        current = total_view(current_estimate, project["positions"])
        proposed = total_view(proposed_estimate, candidate["positions"])
        metric_map = {
            "material_chf": "material_chf", "labour_chf": "labour_chf",
            "baseline_chf": "baseline_chf", "selling_price_chf": "selling_price_chf",
        }
        deltas = {key: money(Decimal(proposed[key]) - Decimal(current[key])) for key in metric_map}
        deltas["hours"] = raw(Decimal(proposed["hours"]) - Decimal(current["hours"]))
        for key, pct_key in (("baseline_chf", "baseline_pct"), ("selling_price_chf", "selling_price_pct")):
            before = Decimal(current[key])
            change = Decimal(deltas[key])
            deltas[pct_key] = (format((change / before * Decimal("100")).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP), ".1f")
                               if before else None)
        current_scenarios = {row["scenario"]: row for row in current["scenarios"]}
        deltas["scenarios"] = [
            {"scenario": row["scenario"], "current_bid_price_chf": current_scenarios[row["scenario"]]["bid_price_chf"],
             "proposed_bid_price_chf": row["bid_price_chf"],
             "bid_price_delta_chf": money(Decimal(row["bid_price_chf"]) - Decimal(current_scenarios[row["scenario"]]["bid_price_chf"]))}
            for row in proposed["scenarios"] if row["scenario"] in current_scenarios
        ]

        old_positions = {row["id"]: row for row in project["positions"]}
        system_deltas: dict[str, dict[str, Decimal]] = {}
        affected = []
        for row in candidate["positions"]:
            before = old_positions.get(row["id"])
            if before is None:
                continue
            before_cost, after_cost = before.get("cost") or {}, row.get("cost") or {}
            if before_cost.get("unrounded_direct") is None or after_cost.get("unrounded_direct") is None:
                continue
            material_delta = Decimal(after_cost.get("unrounded_material") or "0") - Decimal(before_cost.get("unrounded_material") or "0")
            labour_delta = Decimal(after_cost.get("unrounded_labour") or "0") - Decimal(before_cost.get("unrounded_labour") or "0")
            direct_delta = Decimal(after_cost["unrounded_direct"]) - Decimal(before_cost["unrounded_direct"])
            hours_delta = Decimal(after_cost.get("unrounded_hours") or "0") - Decimal(before_cost.get("unrounded_hours") or "0")
            if direct_delta:
                system = str(row.get("system") or "Unassigned")
                totals = system_deltas.setdefault(system, {"material": Decimal("0"), "labour": Decimal("0"), "direct": Decimal("0")})
                totals["material"] += material_delta
                totals["labour"] += labour_delta
                totals["direct"] += direct_delta
                affected.append({"id": row["id"], "reference": row.get("reference") or row["id"],
                    "description": row.get("description", ""), "system": system,
                    "material_delta_chf": money(material_delta), "labour_delta_chf": money(labour_delta),
                    "direct_delta_chf": money(direct_delta), "hours_delta": raw(hours_delta)})
        affected.sort(key=lambda row: abs(Decimal(row["direct_delta_chf"])), reverse=True)
        systems = [{"system": system, "material_delta_chf": money(values["material"]),
                    "labour_delta_chf": money(values["labour"]), "direct_delta_chf": money(values["direct"])}
                   for system, values in system_deltas.items()]
        systems.sort(key=lambda row: abs(Decimal(row["direct_delta_chf"])), reverse=True)
        result = {
            "revision": expected_revision,
            "elapsed_ms": int((perf_counter() - started) * 1000),
            "current": current,
            "proposed": proposed,
            "deltas": deltas,
            "top_positions": affected[:5],
            "top_systems": systems[:5],
        }
        if include_positions:
            if "duct_pricing" in changes:
                # Include every row shown in the area-rule confirmation, including
                # zero-impact rows where no compatible catalogue rate is available.
                area_rule_positions = []
                candidate_by_id = {row["id"]: row for row in candidate["positions"]}
                for before in project["positions"]:
                    attrs = before.get("attributes", {})
                    if not (before.get("category") == "Ductwork" and before.get("install_code") == "DUCT_RECT"
                            and before.get("unit") == "m2" and not before.get("product_id")
                            and attrs.get("schedule_code") == "L" and attrs.get("width_mm") and attrs.get("height_mm")):
                        continue
                    row = candidate_by_id.get(before["id"], before)
                    before_cost, after_cost = before.get("cost") or {}, row.get("cost") or {}
                    def delta(field: str) -> Decimal:
                        return Decimal(after_cost.get(field) or "0") - Decimal(before_cost.get(field) or "0")
                    area_rule_positions.append({
                        "id": row["id"], "reference": row.get("reference") or row["id"],
                        "description": row.get("description", ""),
                        "material_delta_chf": money(delta("unrounded_material")),
                        "labour_delta_chf": money(delta("unrounded_labour")),
                        "direct_delta_chf": money(delta("unrounded_direct")),
                        "hours_delta": raw(delta("unrounded_hours")),
                    })
                result["affected_positions"] = area_rule_positions
            else:
                result["affected_positions"] = affected
        return result

    def patch_assumptions(self, project_id: str, expected_revision: int, reason: str, changes: dict) -> dict:
        if set(changes) - {"productivity_factors", "allowances", "commercial", "project_costs", "stretch_bid_optimization", "duct_pricing", "labour_rates_chf_per_h"}:
            raise DomainError("Only calculation assumptions can be changed.")
        def apply(project):
            project["parameters"] = parameter_defaults(project)
            old = deepcopy(project["parameters"])
            project["parameters"] = deep_update(old, changes)
            for position in project["positions"]:
                if position["review_state"] == "accepted":
                    position["review_state"] = "pending"
            for adjustment in project["adjustments"]:
                if adjustment["review_state"] == "accepted":
                    adjustment["review_state"] = "pending"
            return "assumptions", project_id, old, deepcopy(project["parameters"]), {}
        return self.mutate(project_id, expected_revision, reason, apply)

    def apply_duct_area_rule(self, project_id: str, expected_revision: int, reason: str) -> dict:
        def eligible(project):
            return [p for p in project["positions"] if p.get("category") == "Ductwork" and p.get("install_code") == "DUCT_RECT"
                    and p.get("unit") == "m2" and not p.get("product_id") and p.get("attributes", {}).get("schedule_code") == "L"
                    and p.get("attributes", {}).get("width_mm") and p.get("attributes", {}).get("height_mm")]
        def apply(project):
            old = deepcopy(project["parameters"])
            count = len(eligible(project))
            project["parameters"].setdefault("duct_pricing", deepcopy(DUCT_DEFAULTS))
            project["parameters"]["duct_pricing"]["rect_duct_area_rate_enabled"] = "true"
            for position in project["positions"]:
                if position["review_state"] == "accepted":
                    position["review_state"] = "pending"
            return "assumptions", project_id, old, deepcopy(project["parameters"]), {"matched_rows": count}
        return self.mutate(project_id, expected_revision, reason, apply)

    def _validate_adjustment(self, project: dict, adjustment: dict):
        if len(adjustment["title"].strip()) < 3 or len(adjustment["basis"].strip()) < 3:
            raise DomainError("Adjustment title and rationale must contain at least three characters.")
        value = number(adjustment["amount_chf"], "Adjustment amount", Decimal("0.01"))
        adjustment["amount_chf"] = str(value)
        self.repo.sources_for_project(project, adjustment["source_span_ids"])
        if adjustment["review_state"] != "accepted":
            return
        text_value = f"{adjustment['title']} {adjustment['basis']} {adjustment['scope']}".lower()
        covered_tokens = ("supplier contingency", "supplier_package_contingency", "lieferantenrisiko", "supplier package contingency", "small material", "transport", "commissioning", "documentation", "hygiene", "engineering")
        overlap = any(token in text_value for token in covered_tokens)
        if overlap and not adjustment.get("overlap_resolution"):
            raise DomainError("This adjustment may overlap an existing allowance or project service. Record how the scopes differ in overlap_resolution before approving.")
        for other in project["adjustments"]:
            if other["id"] != adjustment["id"] and other["review_state"] == "accepted" and other["scope"] == adjustment["scope"] and other["kind"] == adjustment["kind"] and other["title"].casefold() == adjustment["title"].casefold():
                raise DomainError("An accepted adjustment already owns this scope and title.")

    def create_adjustment(self, project_id: str, request: AdjustmentCreate) -> dict:
        def apply(project):
            adjustment = CommercialAdjustment(id=identifier("adjustment"), kind=request.kind, title=request.title,
                amount_chf=request.amount_chf, scope=request.scope, basis=request.basis,
                source_span_ids=request.source_span_ids, overlap_resolution=request.overlap_resolution,
                created_at=now(), updated_at=now()).model_dump()
            self._validate_adjustment(project, adjustment)
            project["adjustments"].append(adjustment)
            return "adjustment", adjustment["id"], None, deepcopy(adjustment), {"adjustment": adjustment}
        return self.mutate(project_id, request.expected_revision, request.reason, apply)

    def patch_adjustment(self, adjustment_id: str, expected_revision: int, reason: str, changes: dict) -> dict:
        p = self.locate("adjustments", adjustment_id)
        allowed = {"title", "amount_chf", "scope", "basis", "source_span_ids", "review_state", "overlap_resolution", "kind"}
        if not changes or set(changes) - allowed:
            raise DomainError("Unsupported adjustment changes.")
        def apply(project):
            index = next(i for i, x in enumerate(project["adjustments"]) if x["id"] == adjustment_id)
            old = deepcopy(project["adjustments"][index])
            updated = {**old, **changes, "updated_at": now()}
            if set(changes) - {"review_state"}:
                updated["review_state"] = "pending"
            updated = CommercialAdjustment.model_validate(updated).model_dump()
            self._validate_adjustment(project, updated)
            project["adjustments"][index] = updated
            return "adjustment", adjustment_id, old, deepcopy(updated), {"adjustment": updated}
        return self.mutate(p["id"], expected_revision, reason, apply)

    def patch_issue(self, project_id: str, issue_id: str, expected_revision: int, reason: str, changes: dict) -> dict:
        if set(changes) != {"review_state"} or changes["review_state"] not in ("pending", "accepted", "rejected"):
            raise DomainError("Use a valid review_state to record an issue decision.")
        def apply(project):
            found = [x for x in project["issues"] if x["id"] == issue_id]
            found += [x for p in project["positions"] for x in p["warnings"] if x["id"] == issue_id]
            # The summary exposes grouped issue keys so one reviewer decision can
            # resolve every identical member without repeating the same reason.
            if not found and "|" in issue_id:
                group_kind, group_detail = issue_id.split("|", 1)
                found = [x for x in project["issues"] if x.get("kind") == group_kind and x.get("detail") == group_detail]
                found += [x for p in project["positions"] for x in p["warnings"] if x.get("kind") == group_kind and x.get("detail") == group_detail]
            if not found:
                raise DomainError("Issue not found.", 404)
            old = deepcopy(found[0])
            for issue in found:
                issue["review_state"] = changes["review_state"]
            return "issue", issue_id, old, deepcopy(found[0]), {}
        return self.mutate(project_id, expected_revision, reason, apply)

    def patch_requirement(self, project_id: str, requirement_id: str, expected_revision: int, reason: str, changes: dict) -> dict:
        if set(changes) != {"review_state"} or changes["review_state"] not in ("pending", "accepted", "rejected"):
            raise DomainError("Use a valid review_state to record a requirement decision.")
        def apply(project):
            item = next((r for r in project["requirements"] if r["id"] == requirement_id), None)
            if item is None:
                raise DomainError("Requirement not found.", 404)
            old = deepcopy(item)
            item["review_state"] = changes["review_state"]
            return "requirement", requirement_id, old, deepcopy(item), {}
        return self.mutate(project_id, expected_revision, reason, apply)

    def undo(self, project_id: str, decision_id: str, expected_revision: int, reason: str) -> dict:
        def apply(project):
            decision = next((d for d in project["history"] if d["id"] == decision_id), None)
            if decision is None:
                raise DomainError("Review decision not found.", 404)
            if any(d.get("reverses_id") == decision_id for d in project["history"]):
                raise DomainError("This decision has already been reversed.", 409)
            kind, item_id = decision["entity_type"], decision["entity_id"]
            previous = deepcopy(decision["old_value"])
            if kind == "commercial":
                from .commercial import state
                current = state(project)
                if current != decision["new_value"]:
                    raise DomainError("Later commercial edits must be reversed first.", 409)
                project["commercial_state"] = previous
                return kind, item_id, current, previous, {"reverses_id": decision_id}
            if kind in ("position", "adjustment"):
                bucket = "positions" if kind == "position" else "adjustments"
                index = next((i for i, x in enumerate(project[bucket]) if x["id"] == item_id), None)
                current = deepcopy(project[bucket][index]) if index is not None else None
                # Derived cost changes do not prevent reversing unchanged user fields.
                # Calculated values, proposal collections, and read-only API aliases
                # can change during repricing without a later estimator edit.
                comparable = lambda x: {k: v for k, v in (x or {}).items() if k not in ("cost", "status", "attributes", "lv_id", "reference", "pricing_basis", "match_evidence_band")}
                if comparable(current) != comparable(decision["new_value"]):
                    raise DomainError("Later edits affect this item. Reverse the latest change first.", 409)
                if previous is None:
                    if index is not None:
                        project[bucket].pop(index)
                elif index is None:
                    project[bucket].append(previous)
                else:
                    project[bucket][index] = previous
                if kind == "position":
                    for adjustment in project["adjustments"]:
                        if adjustment["review_state"] == "accepted" and adjustment["scope"] in ("project_level", item_id, (current or {}).get("system"), (previous or {}).get("system")):
                            adjustment["review_state"] = "pending"
                return kind, item_id, current, previous, {"reverses_id": decision_id}
            if kind == "assumptions":
                current = deepcopy(project["parameters"])
                if current != decision["new_value"]:
                    raise DomainError("Later assumption edits must be reversed first.", 409)
                project["parameters"] = previous
                for position in project["positions"]:
                    if position["review_state"] == "accepted":
                        position["review_state"] = "pending"
                for adjustment in project["adjustments"]:
                    if adjustment["review_state"] == "accepted":
                        adjustment["review_state"] = "pending"
                return kind, item_id, current, previous, {"reverses_id": decision_id}
            if kind == "requirement":
                item = next((r for r in project["requirements"] if r["id"] == item_id), None)
                if item is None or item != decision["new_value"]:
                    raise DomainError("Later requirement decisions must be reversed first.", 409)
                current = deepcopy(item)
                item.update(previous)
                return kind, item_id, current, previous, {"reverses_id": decision_id}
            if kind == "issue":
                found = [x for x in project["issues"] if x["id"] == item_id] + [x for p in project["positions"] for x in p["warnings"] if x["id"] == item_id]
                if not found:
                    raise DomainError("Issue no longer exists.", 409)
                current = deepcopy(found[0])
                for issue in found:
                    issue.update(previous)
                return kind, item_id, current, previous, {"reverses_id": decision_id}
            raise DomainError("This processing event cannot be reversed. Use the saved revision for export.")
        return self.mutate(project_id, expected_revision, reason, apply)

    def review_blockers(self, project_id: str) -> list[str]:
        summary = self.summary(project_id)
        coverage = summary["coverage"]
        blockers = []
        if coverage["positions_unpriced"]:
            blockers.append(f"{coverage['positions_unpriced']} positions have no price.")
        if coverage["supplier_quotes_required"]:
            blockers.append(f"{coverage['supplier_quotes_required']} supplier quotations remain outstanding.")
        if coverage["pending_reviews"]:
            blockers.append(f"{coverage['pending_reviews']} position reviews remain.")
        project = self.repo.project(project_id)
        rejected = sum(p["review_state"] == "rejected" and p["status"] not in ("out_of_scope", "non_priceable") for p in project["positions"])
        if rejected:
            blockers.append(f"{rejected} rejected positions require correction or an explicit scope decision.")
        if any(r["review_state"] != "accepted" for r in project["requirements"]):
            blockers.append("Tender requirements have not all been reviewed.")
        if coverage["failed_pages"] or coverage["partial_pages"] or coverage["unassigned_blocks"]:
            blockers.append("Unresolved document blocks or failed pages remain.")
        if any(x["severity"] == "blocker" and x["review_state"] != "accepted" for x in summary["issues"]):
            blockers.append("Blocking evidence conflicts remain.")
        if any(x["review_state"] == "pending" for x in summary["adjustments"]):
            blockers.append("Commercial adjustments await a decision.")
        return blockers
