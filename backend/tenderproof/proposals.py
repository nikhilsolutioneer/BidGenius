"""Deterministic pricing proxy proposals and auditable review decisions."""
from __future__ import annotations

from copy import deepcopy
import hashlib

from .pricing import decimal_value, money
from .models import Position
from .storage import DomainError


def unresolved_causes(position: dict) -> list[str]:
    causes = []
    cost = position.get("cost") or {}
    if position.get("quantity") is None or not position.get("unit"):
        causes.append("missing_quantity")
    if cost.get("material_cost_chf") is None and position.get("pricing_basis") not in {"labour_only", "included_elsewhere"} and not position.get("included_in") and position.get("status") not in {"out_of_scope", "non_priceable"} and not position.get("attributes", {}).get("approved_price_proxy"):
        causes.append("missing_material_reference")
    if cost.get("direct_cost_chf") is None and (not position.get("install_code") or position.get("install_code") == "UNKNOWN"):
        causes.append("missing_installation_rule")
    if position.get("match_evidence_band") == "conflicting" or position.get("technical_equivalence") == "incompatible":
        causes.append("technical_conflict")
    if position.get("status") == "supplier_quote_required":
        causes.append("quotation_required")
    if any(w.get("kind") == "scope_ambiguity" for w in position.get("warnings", [])):
        causes.append("scope_ambiguity")
    return causes


def _fingerprint(position: dict, product: dict) -> str:
    value = "|".join(str(x) for x in (position["id"], position.get("quantity"), position.get("unit"), product["product_id"], product.get("net_cost_chf")))
    return hashlib.sha256(value.encode()).hexdigest()[:20]


def _preview(position: dict, product: dict, project: dict) -> dict:
    if position.get("quantity") is None or not position.get("unit"):
        return {"material_cost_chf": None, "labour_cost_chf": None, "direct_cost_chf": None, "additional_known_cost_chf": None}
    from .models import Position
    from .pricing import price_position
    temporary = Position.model_validate({**position, "product_id": None, "pricing_basis": "manual_assumption",
        "overrides": {**position.get("overrides", {}), "net_unit_cost_chf": str(product["net_cost_chf"])}})
    priced = price_position(temporary, project["catalog"], project["productivity"], project["parameters"], "full_draft_v1")
    cost = priced.cost
    material = decimal_value(cost.material_cost_chf, "preview material", minimum=0) if cost.material_cost_chf is not None else None
    labour = decimal_value(cost.labour_cost_chf, "preview labour", minimum=0) if cost.labour_cost_chf is not None else None
    direct = decimal_value(cost.direct_cost_chf, "preview direct", minimum=0) if cost.direct_cost_chf is not None else None
    existing_labour = (position.get("cost") or {}).get("labour_cost_chf")
    additional = material + (labour or 0) if existing_labour is None else material
    return {"material_cost_chf": money(material) if material is not None else None, "labour_cost_chf": money(labour) if labour is not None else None,
            "direct_cost_chf": money(direct) if direct is not None else None,
            "additional_known_cost_chf": money(additional) if additional is not None else None}


def pricing_proposals(position: dict, project: dict) -> list[dict]:
    # The only dimensional proxy permitted automatically is straight rectangular
    # ductwork on the same m2 price basis. Fittings and other products remain exact.
    if (position.get("attributes", {}).get("approved_price_proxy") or
        position.get("status") in {"out_of_scope", "non_priceable"}):
        return position.get("attributes", {}).get("pricing_proposals", [])
    if (position.get("category") != "Ductwork" or position.get("install_code") != "DUCT_RECT"
        or position.get("unit") != "m2" or position.get("product_id") or position.get("included_in")):
        return position.get("attributes", {}).get("pricing_proposals", [])
    products = [p for p in project.get("catalog", []) if p.get("install_code") == "DUCT_RECT" and p.get("unit") == "m2" and p.get("net_cost_chf")]
    products.sort(key=lambda p: (abs(float(p["net_cost_chf"]) - 100), p["product_id"]))
    old = {x["id"]: x for x in position.get("attributes", {}).get("pricing_proposals", [])}
    proposals = []
    for product in products[:3]:
        pid = _fingerprint(position, product)
        if pid in old:
            proposals.append(old[pid]); continue
        model = product.get("model", "")
        import re
        dims = re.search(r"(\d{2,4})x(\d{2,4})", model)
        tender = position.get("attributes", {})
        tender_dims = f"{tender.get('width_mm','?')}x{tender.get('height_mm','?')} mm"
        differences = [f"Tender: {tender_dims}; reference: {dims.group(0) if dims else model} mm.",
                       "Same DUCT_RECT function and m2 pricing unit; dimensional equivalence is not established.",
                       "Catalogue price is a proxy and requires estimator approval; supplier quote may still be required."]
        proposals.append({"id": pid, "product_id": product["product_id"], "description": product["description"],
            "source_type": product.get("source_type", "catalog"), "net_unit_cost_chf": str(product["net_cost_chf"]),
            "unit": product["unit"], "install_code": product["install_code"], "differences": differences,
            "source_span_ids": position.get("source_span_ids", []), "review_state": "pending",
            "preview": _preview(position, product, project)})
    return proposals


def enrich_position(position: dict, project: dict) -> dict:
    row = deepcopy(position)
    attrs = row.setdefault("attributes", {})
    attrs["pricing_proposals"] = pricing_proposals(row, project)
    attrs["unresolved_causes"] = unresolved_causes(row)
    proxy = attrs.get("approved_price_proxy")
    if proxy:
        cost = row.get("cost") or {}
        refs = list(cost.get("references", []))
        ref = f"pricing_proxy:{proxy.get('product_id')}"
        if ref not in refs:
            refs.append(ref)
        cost["references"] = refs
        cost["formula"] = (cost.get("formula", "") + f"; approved pricing proxy {proxy.get('product_id')} at CHF {proxy.get('net_unit_cost_chf')}/{proxy.get('unit')}").strip("; ")
        row["cost"] = cost
    return row


def review_proposal(service, project_id: str, position_id: str, expected_revision: int, reason: str, change: dict) -> dict:
    field = next(iter(change))
    request = change[field]
    if set(request) != {"id", "review_state"} or request["review_state"] not in ("accepted", "rejected"):
        raise DomainError("Provide a proposal id and accepted or rejected review_state.")
    def apply(project):
        index = next((i for i,p in enumerate(project["positions"]) if p["id"] == position_id), None)
        if index is None: raise DomainError("Position not found.", 404)
        old = deepcopy(project["positions"][index])
        old = enrich_position(old, project)
        previous = deepcopy(old)
        attrs = old.setdefault("attributes", {})
        collection = "pricing_proposals" if field == "pricing_proposal" else "ai_refinement_proposals"
        proposals = attrs.get(collection, [])
        proposal = next((p for p in proposals if p["id"] == request["id"]), None)
        if proposal is None: raise DomainError("Proposal not found; refresh the position and review the current proposal.", 409)
        if proposal.get("review_state", proposal.get("state", "pending")) != "pending":
            raise DomainError("Proposal has already been reviewed.", 409)
        if field == "pricing_proposal":
            product = next((p for p in project["catalog"] if p["product_id"] == proposal["product_id"]), None)
            if not product or product.get("unit") != old.get("unit") or product.get("install_code") != old.get("install_code"):
                raise DomainError("Pricing proxy no longer satisfies the position unit and installation rule.")
            proposal["review_state"] = request["review_state"]
            proposal["reason"] = reason
            if request["review_state"] == "accepted":
                attrs["approved_price_proxy"] = {"product_id": product["product_id"], "net_unit_cost_chf": str(product["net_cost_chf"]),
                    "unit": product["unit"], "source_type": product.get("source_type", "catalog"), "proposal_id": proposal["id"], "reason": reason}
                old["overrides"] = {**old.get("overrides", {}), "net_unit_cost_chf": str(product["net_cost_chf"])}
                old["pricing_basis"] = "supplier_reference" if product.get("source_type") == "supplier_package" else "manual_assumption"
                old["match_evidence_band"] = "partial"
                old["technical_equivalence"] = "unverified"
                old["assumptions"] = list(dict.fromkeys(old.get("assumptions", []) + [f"Pricing-only proxy {product['product_id']} accepted: {reason}. Technical equivalence is unverified."]))
                old["status"] = "assumption_applied"
        else:
            proposal["state"] = request["review_state"]
            proposal["reason"] = reason
            if request["review_state"] == "accepted":
                changes = proposal.get("changes", {})
                allowed = {"system", "category", "attributes", "description", "quantity", "unit", "product_id"}
                if set(changes) - allowed:
                    raise DomainError("AI refinements cannot change numeric source quantities or reviewed prices.")
                if changes.get("product_id"):
                    product = next((p for p in project["catalog"] if p["product_id"] == changes["product_id"]), None)
                    if not product or product.get("unit") != old.get("unit") or product.get("install_code") != old.get("install_code"):
                        raise DomainError("AI product proposal does not satisfy the current unit and installation rule.")
                    old["product_id"] = product["product_id"]
                    old["pricing_basis"] = "supplier_reference" if product.get("source_type") == "supplier_package" else "catalogue"
                    candidate = Position.model_validate(old)
                    from .matching import validate_explicit_reference
                    candidate = validate_explicit_reference(candidate, project["catalog"], product["product_id"])
                    old = candidate.model_dump(mode="json")
                    if candidate.match_evidence_band == "conflicting":
                        old["technical_equivalence"] = "incompatible"
                        old["status"] = "review_required"
                    else:
                        old["technical_equivalence"] = "unverified"
                    old["assumptions"] = list(dict.fromkeys(old.get("assumptions", []) +
                        [f"Catalogue reference suggested by AI and accepted for pricing review: {reason}. Technical equivalence remains subject to review."]))
                source_ids = proposal.get("source_span_ids", [])
                sources = service.repo.sources_for_project(project, source_ids)
                if "quantity" in changes:
                    from decimal import Decimal, InvalidOperation
                    from .matching import normalize_number
                    try:
                        quantity = normalize_number(changes["quantity"])
                        source_numbers = {normalize_number(x) for source in sources for x in __import__("re").findall(r"\d[\d']*(?:[.,]\d+)?", source["text"])}
                    except (ValueError, InvalidOperation):
                        raise DomainError("Proposed quantity is not a valid source-supported number.") from None
                    if quantity not in source_numbers:
                        raise DomainError("Proposed quantity does not appear in its cited source text.")
                    changes["quantity"] = quantity
                if "unit" in changes and changes["unit"] not in {"pc", "m", "m2", "h", "LS", "system"}:
                    raise DomainError("Proposed unit is not supported.")
                for key, value in changes.items():
                    if key == "attributes": old["attributes"].update(value)
                    else: old[key] = value
        project["positions"][index] = old
        return "position", position_id, previous, deepcopy(old), {"position_id": position_id}
    return service.mutate(project_id, expected_revision, reason, apply)
