"""Authoritative Decimal calculations. No model-generated financial values."""
from __future__ import annotations

from copy import deepcopy
from decimal import Decimal, InvalidOperation, ROUND_CEILING, ROUND_HALF_UP, getcontext, localcontext
from typing import Any

from .duct_rules import (area_from_length, area_rule_assumption, duct_pricing, enabled,
                         raw as duct_raw, select_rect_product)
from .models import CommercialAdjustment, CostLine, Issue, Position

getcontext().prec = 28
ZERO = Decimal("0")
ONE = Decimal("1")
HUNDRED = Decimal("100")
POLICIES = {"benchmark_v1", "full_draft_v1"}


def decimal_value(value: Any, name: str = "value", *, minimum: Decimal | None = None,
                  positive: bool = False) -> Decimal:
    if isinstance(value, bool) or value is None:
        raise ValueError(f"{name} must be a finite decimal number")
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        raise ValueError(f"{name} must be a finite decimal number") from None
    if not result.is_finite():
        raise ValueError(f"{name} must be finite")
    if positive and result <= 0:
        raise ValueError(f"{name} must be positive")
    if minimum is not None and result < minimum:
        raise ValueError(f"{name} must be at least {minimum}")
    return result


def money(value: Decimal | str | int) -> str:
    return format(decimal_value(value).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP), ".2f")

def display_chf(value: Decimal | str | int) -> str:
    """Human-facing CHF formula value: two decimals and Swiss thousands separators."""
    return f"{Decimal(money(value)):,.2f}".replace(",", "'")


def raw(value: Decimal) -> str:
    result = format(value, "f")
    return result.rstrip("0").rstrip(".") if "." in result else result


def _pct(group: dict, key: str, default: str = "0") -> Decimal:
    return decimal_value(group.get(key, default), key, minimum=ZERO) / HUNDRED


def validate_parameters(parameters: dict) -> None:
    for name, value in parameters.get("productivity_factors", {}).items():
        decimal_value(value, name, positive=True)
    for name, value in parameters.get("allowances", {}).items():
        decimal_value(value, name, minimum=ZERO)
    for name, value in parameters.get("project_costs", {}).items():
        decimal_value(value, name, minimum=ZERO)
    labour_rates = parameters.get("labour_rates_chf_per_h", {})
    if not isinstance(labour_rates, dict):
        raise ValueError("labour_rates_chf_per_h must be an object")
    for role, value in labour_rates.items():
        decimal_value(value, f"{role} hourly rate", minimum=ZERO)
    commercial = parameters.get("commercial", {})
    _pct(commercial, "overhead_pct")
    margin = decimal_value(commercial.get("target_margin_pct", "5.5"), "target_margin_pct", minimum=ZERO)
    if margin >= 100:
        raise ValueError("target_margin_pct must be below 100")
    decimal_value(commercial.get("round_to_chf", "1000"), "round_to_chf", positive=True)
    duct = parameters.get("duct_pricing", {})
    if duct:
        decimal_value(duct.get("fitting_section_area_factor", "1.0"), "fitting_section_area_factor", minimum=ZERO)
        if str(duct.get("rect_fitting_material_mode", "quote_required")) not in {"quote_required", "equivalent_area"}:
            raise ValueError("rect_fitting_material_mode must be quote_required or equivalent_area")


def _unit(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip().lower().replace("²", "2").rstrip(".")
    return {"stk": "pc", "stück": "pc", "stueck": "pc", "pcs": "pc", "stückzahl": "pc",
            "m²": "m2", "sqm": "m2", "lfm": "m", "set": "pc", "satz": "pc"}.get(normalized, normalized)


def _inclusions(position: Position) -> set[str]:
    included = position.attributes.get("inclusions", [])
    if isinstance(included, dict):
        return {str(key) for key, value in included.items() if value is True}
    return set(included) if isinstance(included, list) else set()


def _zero_cost(reason: str) -> CostLine:
    return CostLine(material_cost_chf="0.00", labour_cost_chf="0.00", direct_cost_chf="0.00",
                    material_before_waste_chf="0.00", waste_chf="0.00", adjusted_install_hours="0.00",
                    unrounded_hours="0", unrounded_material="0", unrounded_labour="0", unrounded_direct="0",
                    formula=reason)


def _apply_duct_pricing_rule(position: Position, catalog: list[dict], parameters: dict, policy: str) -> Position:
    p = position.model_copy(deep=True)
    attrs = p.attributes
    derived_rule = attrs.get("pricing_rule")
    if derived_rule in {"Rectangular duct area rate", "Duct section pieces (LT)"} and not attrs.get("estimator_area_override"):
        original = attrs.pop("_area_rule_original", None)
        if original:
            for field in ("quantity", "unit", "product_id", "install_code", "pricing_basis", "status",
                          "assumptions", "match_evidence_band", "technical_equivalence"):
                setattr(p, field, deepcopy(original[field]))
            p.warnings = [Issue.model_validate(w) for w in original["warnings"]]
            if original.get("area_m2") is None:
                attrs.pop("area_m2", None)
            else:
                attrs["area_m2"] = original["area_m2"]
        else:
            # Older saved revisions predate the snapshot. Recover the PDF quantity
            # and remove only the catalogue match introduced by the area rule.
            p.product_id = None
            p.pricing_basis = "unpriced"
            p.assumptions = [a for a in p.assumptions if not a.startswith(("Rectangular duct area rate:", "Duct section pieces (LT):"))]
            if derived_rule == "Duct section pieces (LT)":
                p.quantity, p.unit, p.install_code = p.raw_quantity, p.raw_unit, None
                width, height = attrs.get("width_mm"), attrs.get("height_mm")
                if width and height and p.raw_quantity:
                    attrs["area_m2"] = raw(area_from_length(width, height, p.raw_quantity))
            p.status = "insufficient_information"
        attrs.pop("pricing_rule", None)
    if policy != "full_draft_v1" or p.included_in:
        return p
    config = duct_pricing(parameters)
    if attrs.get("estimator_area_override"):
        return p
    width, height = attrs.get("width_mm"), attrs.get("height_mm")
    if (not width or not height) and attrs.get("unsupported_fitting") and len(attrs.get("table_dimensions", [])) >= 2:
        width, height = attrs["table_dimensions"][:2]
        attrs["width_mm"], attrs["height_mm"] = width, height
    if not width or not height:
        return p
    area_rate_enabled = enabled(config.get("rect_duct_area_rate_enabled"))
    area_mode = str(config.get("rect_fitting_material_mode", "quote_required"))
    selected = select_rect_product(catalog, width, height)

    def mark_assumption_applied() -> None:
        p.match_evidence_band = "partial"
        p.technical_equivalence = "unverified"
        p.warnings = [w for w in p.warnings if w.kind != "match_conflict"]

    def remember_original() -> None:
        attrs["_area_rule_original"] = {field: deepcopy(getattr(p, field)) for field in
            ("quantity", "unit", "product_id", "install_code", "pricing_basis", "status",
             "assumptions", "match_evidence_band", "technical_equivalence")}
        attrs["_area_rule_original"]["warnings"] = [w.model_dump(mode="json") for w in p.warnings]
        attrs["_area_rule_original"]["area_m2"] = attrs.get("area_m2")

    if attrs.get("schedule_code") == "LT" and not p.product_id and enabled(config.get("lt_area_rate_enabled")) and selected:
        remember_original()
        factor = config.get("fitting_section_area_factor", "1.0")
        area = area_from_length(width, height, p.raw_quantity or p.quantity, factor)
        product, _ = selected
        p.quantity, p.unit = raw(area), "m2"
        p.product_id = product["product_id"]
        p.install_code = "DUCT_RECT"
        p.pricing_basis = "manual_assumption"
        p.status = "assumption_applied"
        mark_assumption_applied()
        attrs["area_m2"] = raw(area)
        attrs["pricing_rule"] = "Duct section pieces (LT)"
        assumption = (f"Duct section pieces (LT): {width}x{height} mm × {p.raw_quantity} mm × factor {factor} "
                      f"= {raw(area)} m2; priced via {product['product_id']} using rectangular duct area rate.")
        p.assumptions = list(dict.fromkeys(p.assumptions + [area_rule_assumption(product, width, height), assumption]))
        return p

    if p.install_code == "DUCT_RECT" and p.unit == "m2" and not p.product_id and area_rate_enabled and selected:
        remember_original()
        product, _ = selected
        p.product_id = product["product_id"]
        p.pricing_basis = "manual_assumption"
        p.status = "assumption_applied"
        mark_assumption_applied()
        attrs["pricing_rule"] = "Rectangular duct area rate"
        p.assumptions = list(dict.fromkeys(p.assumptions + [area_rule_assumption(product, width, height)]))
        return p

    if attrs.get("unsupported_fitting") and p.unit == "pc":
        p.install_code = "DUCT_FITTING"
        attrs["pricing_rule"] = "Rectangular fittings"
        if area_mode == "equivalent_area" and area_rate_enabled and selected:
            product, _ = selected
            quantity = decimal_value(p.quantity, "quantity", minimum=ZERO)
            factor = config.get("fitting_section_area_factor", "1.0")
            area_each = area_from_length(width, height, Decimal("1000"), factor)
            material_qty = quantity * area_each
            p.overrides = {**p.overrides, "duct_material_quantity_m2": raw(material_qty),
                           "duct_material_net_unit_cost_chf": str(product["net_cost_chf"]),
                           "duct_material_product_id": product["product_id"]}
            p.pricing_basis = "manual_assumption"
            p.status = "assumption_applied"
            mark_assumption_applied()
            p.assumptions = list(dict.fromkeys(p.assumptions + [
                area_rule_assumption(product, width, height),
                f"Rectangular fittings material mode equivalent_area: {raw(quantity)} pc × {raw(area_each)} m2/pc = {raw(material_qty)} m2; supplier geometry remains unverified.",
            ]))
        else:
            p.pricing_basis = "supplier_reference"
            p.status = "supplier_quote_required"
            p.assumptions = list(dict.fromkeys(p.assumptions + [
                "Rectangular fittings: labour priced from DUCT_FITTING; material remains supplier quote required.",
            ]))
        return p
    return p


def price_position(position: Position, catalog: list[dict], productivity: list[dict], parameters: dict,
                   policy: str = "full_draft_v1") -> Position:
    if policy not in POLICIES:
        raise ValueError(f"Unknown calculation policy: {policy}")
    validate_parameters(parameters)
    p = position.model_copy(deep=True)
    p = _apply_duct_pricing_rule(p, catalog, parameters, policy)
    p.cost = CostLine()
    p.attributes.pop("pricing", None)
    overrides = p.overrides
    products = {entry["product_id"]: entry for entry in catalog}
    rules = {entry["install_code"]: entry for entry in productivity}
    if p.product_id and p.product_id not in products:
        raise ValueError(f"Unknown product reference: {p.product_id}")
    product = products.get(p.product_id)
    install_code = overrides.get("install_code", p.install_code or (product or {}).get("install_code"))
    if install_code and install_code not in rules:
        raise ValueError(f"Unknown installation rule: {install_code}")
    p.install_code = install_code
    rule = rules.get(install_code) if install_code != "UNKNOWN" else None

    # Invalid supplied numbers are errors even if another input is still missing.
    quantity = decimal_value(p.quantity, "quantity", minimum=ZERO) if p.quantity is not None else None
    for key in ("net_unit_cost_chf", "hourly_rate_chf", "material_waste_pct", "base_hours_per_unit"):
        if key in overrides:
            decimal_value(overrides[key], key, minimum=ZERO)
    factor_overrides = overrides.get("factor_overrides", {})
    if not isinstance(factor_overrides, dict):
        raise ValueError("factor_overrides must be an object")
    for name, value in factor_overrides.items():
        decimal_value(value, name, positive=True)

    if p.status in {"out_of_scope", "non_priceable"}:
        p.cost.formula = "Excluded from financial totals; the original scope remains visible."
        return p
    if p.included_in:
        p.pricing_basis = "included_elsewhere"
        p.status = "assumption_applied"
        p.cost = _zero_cost(f"Scope charged once to {p.included_in}; no additional charge here.")
        return p
    if p.pricing_basis == "included_elsewhere":
        p.status = "review_required"
        p.cost.formula = "An owning position or project allowance must be identified before excluding this cost."
        return p
    if quantity is None or not p.unit:
        p.status = "insufficient_information"
        p.cost.formula = "Quantity or normalized unit is missing. Unknown cost is not zero."
        return p

    labour_only = p.pricing_basis == "labour_only" or "supplied_by_others" in p.scope_tags
    if product and not labour_only and _unit(p.unit) != _unit(product["unit"]):
        raise ValueError(f"Position unit {p.unit} is incompatible with product unit {product['unit']}")
    if rule and _unit(p.unit) != _unit(rule["unit"]):
        raise ValueError(f"Position unit {p.unit} is incompatible with installation unit {rule['unit']}")

    inclusions = _inclusions(p)
    material_origin = "catalogue"
    net = None
    if labour_only:
        net = ZERO
        p.pricing_basis = "labour_only"
    elif "net_unit_cost_chf" in overrides:
        net = decimal_value(overrides["net_unit_cost_chf"], "net_unit_cost_chf", minimum=ZERO)
        if p.pricing_basis not in {"confirmed_quote", "supplier_reference"}:
            p.pricing_basis = "manual_assumption"
    elif "duct_material_net_unit_cost_chf" in overrides:
        net = decimal_value(overrides["duct_material_net_unit_cost_chf"], "duct_material_net_unit_cost_chf", minimum=ZERO)
        p.pricing_basis = "manual_assumption"
    elif product and product.get("net_cost_chf") not in (None, ""):
        net = decimal_value(product["net_cost_chf"], "net_cost_chf", minimum=ZERO)
        if p.pricing_basis not in {"confirmed_quote", "manual_assumption"}:
            p.pricing_basis = "supplier_reference" if product.get("source_type") == "supplier_package" else "catalogue"
    if p.pricing_basis in {"supplier_reference", "confirmed_quote"} or (product or {}).get("source_type") == "supplier_package":
        material_origin = "supplier_reference"
    waste_pct = decimal_value(overrides.get("material_waste_pct", parameters.get("allowances", {}).get("material_waste_pct", "4")),
                              "material_waste_pct", minimum=ZERO) / HUNDRED
    material_quantity = decimal_value(overrides["duct_material_quantity_m2"], "duct_material_quantity_m2", minimum=ZERO) if "duct_material_quantity_m2" in overrides else quantity
    before_waste = material_quantity * net if net is not None else None
    waste = before_waste * waste_pct if before_waste is not None else None
    material = before_waste + waste if before_waste is not None else None

    factors = {}
    hours = labour = base = rate = None
    role = None
    if "installation" in inclusions:
        hours = labour = ZERO
        role = "included in quoted package"
    elif rule:
        base = decimal_value(overrides.get("base_hours_per_unit", rule["base_hours_per_unit"]), "base_hours_per_unit", minimum=ZERO)
        role = rule["labour_role"]
        role_rates = parameters.get("labour_rates_chf_per_h", {}) if policy == "full_draft_v1" else {}
        rate = decimal_value(overrides.get("hourly_rate_chf", role_rates.get(role, rule["default_hourly_rate_chf"])), "hourly_rate_chf", minimum=ZERO)
        hours = quantity * base
        keys = [key for key in str(rule.get("factor_keys", "")).split("|") if key]
        if policy == "full_draft_v1" and ("LA05" in p.system or p.attributes.get("mounting_context") == "sports_hall"):
            keys = ["mounting_height_sports_hall" if key == "mounting_height_school" else key for key in keys]
        if "mounting_height_school" in keys and "mounting_height_sports_hall" in keys:
            raise ValueError("School and sports-hall mounting factors cannot both apply")
        for key in dict.fromkeys(keys):
            if key not in factor_overrides and key not in parameters.get("productivity_factors", {}):
                raise ValueError(f"Missing productivity factor: {key}")
            factor = decimal_value(factor_overrides.get(key, parameters.get("productivity_factors", {}).get(key)), key, positive=True)
            hours = hours / factor if key == "site_efficiency" else hours * factor
            factors[key] = raw(factor)
        labour = hours * rate

    direct = material + labour if material is not None and labour is not None else None
    proxy = p.attributes.get("approved_price_proxy") or {}
    references = ([f"catalog:{p.product_id}"] if product else []) + ([f"catalog:{overrides.get('duct_material_product_id')}"] if overrides.get("duct_material_product_id") else []) + ([f"pricing_proxy:{proxy.get('product_id')}:{proxy.get('proposal_id')}" ] if proxy else []) + ([f"productivity:{install_code}"] if rule else [])
    formula = "material = quantity × net unit price × (1 + waste); hours = quantity × base hours ÷ site efficiency × applicable factors; labour = unrounded hours × hourly rate"
    if labour_only:
        formula = "Material supplied by others: no purchase charge. " + formula
    if "duct_material_quantity_m2" in overrides:
        formula = "material = equivalent duct area × net m2 rate × (1 + waste); " + formula.split("; ", 1)[1]
    if "installation" in inclusions:
        formula += "; installation already included in package price"
    p.cost = CostLine(material_cost_chf=money(material) if material is not None else None,
        labour_cost_chf=money(labour) if labour is not None else None, direct_cost_chf=money(direct) if direct is not None else None,
        net_unit_cost_chf=raw(net) if net is not None else None,
        material_before_waste_chf=money(before_waste) if before_waste is not None else None,
        waste_chf=money(waste) if waste is not None else None,
        adjusted_install_hours=money(hours) if hours is not None else None, unrounded_hours=raw(hours) if hours is not None else None,
        base_hours_per_unit=raw(base) if base is not None else None, labour_role=role,
        hourly_rate_chf=raw(rate) if rate is not None else None, factors=factors,
        unrounded_material=raw(material) if material is not None else None,
        unrounded_labour=raw(labour) if labour is not None else None,
        unrounded_direct=raw(direct) if direct is not None else None, formula=formula, references=references)
    p.attributes["pricing"] = {"material_origin": material_origin,
        "unrounded_before_waste": raw(before_waste) if before_waste is not None else None,
        "unrounded_waste": raw(waste) if waste is not None else None,
        "policy": policy, "provisional": p.pricing_basis == "supplier_reference"}
    if direct is None:
        p.status = ("supplier_quote_required" if p.pricing_basis == "supplier_reference" else
                    "review_required" if p.candidates or p.match_evidence_band == "conflicting" else
                    "insufficient_information")
    elif p.match_evidence_band == "conflicting" or p.technical_equivalence == "incompatible":
        p.status = "review_required"
    elif p.pricing_basis == "supplier_reference":
        p.status = "supplier_quote_required"
        if not inclusions:
            assumption = "Supplier reference treated as supply-only; installation and package inclusions require confirmation."
            if assumption not in p.assumptions:
                p.assumptions.append(assumption)
    elif p.pricing_basis == "manual_assumption" or overrides or p.origin == "manual":
        p.status = "assumption_applied"
    elif any(issue.review_state != "accepted" and issue.severity == "blocker" for issue in p.warnings):
        p.status = "review_required"
    else:
        p.status = "calculated"
    return p


def calculate_scenarios(baseline: str, parameters: dict, overrides: dict | None = None) -> dict:
    validate_parameters(parameters)
    cost = decimal_value(baseline, "baseline", minimum=ZERO)
    config = deepcopy(parameters.get("stretch_bid_optimization", {}))
    if overrides:
        for key, value in overrides.items():
            if key == "scenario_margins_pct":
                config[key] = {**config.get(key, {}), **value}
            else:
                config[key] = value
    commercial = parameters.get("commercial", {})
    reference_margin = decimal_value(config.get("reference_margin_pct", commercial.get("target_margin_pct", "5.5")), "reference_margin_pct", minimum=ZERO) / HUNDRED
    if reference_margin >= ONE:
        raise ValueError("reference_margin_pct must be below 100")
    increment = decimal_value(commercial.get("round_to_chf", "1000"), "round_to_chf", positive=True)
    probability_base = decimal_value(config.get("reference_win_probability", ".55"), "reference_win_probability", minimum=ZERO)
    sensitivity = decimal_value(config.get("price_sensitivity_probability_points_per_1pct_price", ".05"), "price_sensitivity", minimum=ZERO)
    appetite = decimal_value(config.get("strategic_appetite_adjustment", ".05"), "strategic_appetite_adjustment")
    competition = decimal_value(config.get("competition_adjustment", "-.05"), "competition_adjustment")
    pmin = decimal_value(config.get("minimum_probability", ".05"), "minimum_probability", minimum=ZERO)
    pmax = decimal_value(config.get("maximum_probability", ".95"), "maximum_probability", minimum=ZERO)
    if probability_base > ONE or not pmin <= pmax <= ONE:
        raise ValueError("Probability assumptions must satisfy 0 ≤ minimum ≤ maximum ≤ 1 and reference ≤ 1")
    margins = config.get("scenario_margins_pct", {"Aggressive": "2.5", "Target": "4.0", "Conservative": "6.5"})
    if not isinstance(margins, dict) or not margins:
        raise ValueError("At least one scenario margin is required")
    reference = cost / (ONE - reference_margin)
    if config.get("reference_price_multiplier") is not None:
        reference = cost * decimal_value(config["reference_price_multiplier"], "reference_price_multiplier", positive=True)
    scenarios = []
    for name, margin_value in margins.items():
        margin = decimal_value(margin_value, f"{name} margin", minimum=ZERO) / HUNDRED
        if margin >= ONE:
            raise ValueError(f"{name} margin must be below 100")
        bid = (cost / (ONE - margin) / increment).to_integral_value(rounding=ROUND_CEILING) * increment
        if cost:
            probability = min(pmax, max(pmin, probability_base - sensitivity * ((bid / reference - ONE) * HUNDRED) + appetite + competition))
            achieved = (bid - cost) / bid * HUNDRED
        else:
            probability = achieved = ZERO
        price_vs_reference_pct = (bid / reference - ONE) * HUNDRED if reference else None
        scenarios.append({"scenario": str(name), "bid_price_chf": money(bid), "margin_pct": raw(margin * HUNDRED),
            "achieved_margin_pct": money(achieved), "estimated_win_probability": money(probability),
            "unrounded_win_probability": raw(probability), "expected_contribution_chf": money((bid - cost) * probability),
            "price_vs_reference_pct": raw(price_vs_reference_pct) if price_vs_reference_pct is not None else None})
    curve_points = []
    if cost:
        low_price = min(Decimal(s["bid_price_chf"]) for s in scenarios)
        high_price = max(Decimal(s["bid_price_chf"]) for s in scenarios)
        start = min(low_price, reference) * Decimal("0.94")
        end = max(high_price, reference) * Decimal("1.06")
        for index in range(13):
            price = start + (end - start) * Decimal(index) / Decimal("12")
            probability = min(pmax, max(pmin, probability_base - sensitivity * ((price / reference - ONE) * HUNDRED) + appetite + competition))
            achieved = (price - cost) / price * HUNDRED if price else ZERO
            curve_points.append({"price_chf": money(price), "estimated_win_probability": money(probability),
                "achieved_margin_pct": money(achieved), "expected_contribution_chf": money((price - cost) * probability)})
    return {"scenarios": scenarios, "low_chf": money(min(Decimal(s["bid_price_chf"]) for s in scenarios)),
        "high_chf": money(max(Decimal(s["bid_price_chf"]) for s in scenarios)),
        "probability_curve": curve_points,
        "label": "Bid range based on assumptions, for included scope.",
        "assumptions": {**config, "reference_margin_pct": raw(reference_margin * HUNDRED),
            "reference_price_chf": money(reference), "round_to_chf": raw(increment),
            "disclaimer": "Illustrative scenario model — supplied assumptions, not calibrated predictions."}}


def _fixed_services(parameters: dict) -> dict[str, Decimal]:
    costs = parameters.get("project_costs", {})
    def val(key):
        return decimal_value(costs.get(key, "0"), key, minimum=ZERO)
    return {"engineering": val("engineering_hours") * val("engineering_rate_chf_per_h"),
        "commissioning": val("commissioning_hours") * val("commissioning_rate_chf_per_h"),
        "hygiene": val("hygiene_inspection_chf"), "documentation": val("documentation_chf")}


def _bucket(positions: list[Position], field: str, baseline: Decimal, known_direct: Decimal,
            project_material: Decimal = ZERO, project_labour: Decimal = ZERO) -> list[dict]:
    buckets: dict[str, dict] = {}
    for p in positions:
        key = getattr(p, field) or ("Unassigned" if field == "system" else "unclassified")
        bucket = buckets.setdefault(key, {"key": key, "label": key, "material": ZERO, "labour": ZERO,
            "amount": ZERO, "positions": 0, "unpriced": 0, "provisional": 0})
        cost = p.cost or CostLine()
        material = Decimal(cost.unrounded_material or "0")
        labour = Decimal(cost.unrounded_labour or "0")
        bucket["material"] += material
        bucket["labour"] += labour
        bucket["amount"] += material + labour
        bucket["positions"] += 1
        bucket["unpriced"] += int(cost.direct_cost_chf is None and p.status not in {"out_of_scope", "non_priceable"})
        bucket["provisional"] += int(p.pricing_basis == "supplier_reference")
    result = []
    for value in buckets.values():
        result.append({k: v for k, v in value.items() if k not in {"material", "labour", "amount"}} | {
            "material_cost_chf": money(value["material"]), "labour_cost_chf": money(value["labour"]), "amount_chf": money(value["amount"])})
    residual = Decimal(money(baseline)) - sum((Decimal(b["amount_chf"]) for b in result), ZERO)
    pure_project = baseline - known_direct
    result.append({"key": "project_level", "label": "Project-level costs and display rounding",
        "material_cost_chf": money(project_material), "labour_cost_chf": money(project_labour),
        "amount_chf": money(residual), "positions": 0, "unpriced": 0, "provisional": 0,
        "display_rounding_chf": money(residual - Decimal(money(pure_project)))})
    return result


def calculate_estimate(positions: list[Position], catalog: list[dict], productivity: list[dict], parameters: dict,
                       adjustments: list[CommercialAdjustment] | None = None, policy: str = "full_draft_v1") -> dict:
    if policy not in POLICIES:
        raise ValueError(f"Unknown calculation policy: {policy}")
    validate_parameters(parameters)
    with localcontext() as ctx:
        ctx.prec = 28
        return _calculate_estimate(positions, catalog, productivity, parameters, adjustments or [], policy)


def _calculate_estimate(positions, catalog, productivity, parameters, adjustments, policy):
    ids = {p.id for p in positions}
    if len(ids) != len(positions):
        raise ValueError("Duplicate position identifiers")
    lookup = {p.id: p for p in positions}
    fixed = _fixed_services(parameters) if policy == "full_draft_v1" else {}
    for p in positions:
        if p.included_in:
            owner = p.included_in.removeprefix("position:")
            if p.included_in.startswith("project:"):
                scope = p.included_in.removeprefix("project:")
                if scope not in {*fixed, "transport", "small_material", "supplier_contingency"}:
                    raise ValueError(f"Unknown project scope owner: {p.included_in}")
            elif owner not in ids or owner == p.id:
                raise ValueError(f"Invalid scope owner for {p.id}: {p.included_in}")
            else:
                seen = {p.id}
                current = owner
                while current in lookup:
                    if current in seen:
                        raise ValueError("Cyclic scope ownership")
                    seen.add(current)
                    current = (lookup[current].included_in or "").removeprefix("position:")
    priced = [price_position(p, catalog, productivity, parameters, policy) for p in positions]
    material = labour = hours = rc = rp = waste = ZERO
    small_basis = contingency_basis = transport_basis = ZERO
    scopes = []
    assumptions = []
    for p in priced:
        c = p.cost or CostLine()
        m = Decimal(c.unrounded_material or "0")
        l = Decimal(c.unrounded_labour or "0")
        material += m
        labour += l
        hours += Decimal(c.unrounded_hours or "0")
        meta = p.attributes.get("pricing", {})
        before = Decimal(meta.get("unrounded_before_waste") or "0")
        waste += Decimal(meta.get("unrounded_waste") or "0")
        includes = _inclusions(p)
        if meta.get("material_origin") == "supplier_reference":
            rp += before
            if "supplier_contingency" not in includes:
                contingency_basis += before
        else:
            rc += before
            if "small_material" not in includes:
                small_basis += before
        if "transport" not in includes:
            transport_basis += m + l
        if p.included_in:
            scopes.append({"scope": "position", "owner": p.included_in, "position_ids": [p.id],
                           "amount_chf": "0.00", "status": "included", "basis": "Explicit scope owner; charged once."})
        for scope in includes:
            scopes.append({"scope": scope, "owner": p.id, "position_ids": [p.id], "amount_chf": None,
                           "status": "included", "basis": "Explicit package inclusion; no separate charge."})
            # Only explicit project-wide ownership can displace a project-wide allowance.
            if scope.startswith("project:") and scope[8:] in fixed:
                fixed[scope[8:]] = ZERO
        for text in p.assumptions:
            assumptions.append({"position_id": p.id, "text": text, "source_span_ids": p.source_span_ids})
    allowances = parameters.get("allowances", {})
    small = small_basis * _pct(allowances, "small_material_pct") if policy == "full_draft_v1" else ZERO
    contingency = contingency_basis * _pct(allowances, "supplier_package_contingency_pct") if policy == "full_draft_v1" else ZERO
    transport = transport_basis * _pct(allowances, "transport_equipment_pct")
    services = sum(fixed.values(), ZERO)
    known_direct = material + labour
    direct = known_direct + small + contingency + transport + services
    risk = opportunity = pending = ZERO
    accepted_scopes = set()
    for adjustment in adjustments:
        amount = decimal_value(adjustment.amount_chf, "adjustment amount", positive=True)
        if not adjustment.basis.strip():
            raise ValueError("An adjustment requires evidence or a manual rationale")
        scope = adjustment.scope.casefold().replace("project:", "").replace(" ", "_")
        overlap = scope in {"supplier_contingency", "supplier_package_contingency", "contingency", "transport", "small_material", *fixed}
        if adjustment.review_state == "accepted":
            if overlap and not adjustment.overlap_resolution:
                raise ValueError(f"Adjustment '{adjustment.title}' overlaps an existing allowance; document distinct incremental scope first")
            if scope not in {"project_level", "project"} and scope in accepted_scopes and not adjustment.overlap_resolution:
                raise ValueError(f"Duplicate approved adjustment scope: {adjustment.scope}")
            accepted_scopes.add(scope)
            if adjustment.kind == "risk":
                risk += amount
            else:
                opportunity += amount
        elif adjustment.review_state == "pending":
            pending += amount if adjustment.kind == "risk" else -amount
    adjusted_direct = direct + risk - opportunity
    if opportunity and adjusted_direct <= ZERO:
        raise ValueError("Approved opportunities must not produce a non-positive cost base")
    overhead = adjusted_direct * _pct(parameters.get("commercial", {}), "overhead_pct")
    baseline = adjusted_direct + overhead
    margin = _pct(parameters.get("commercial", {}), "target_margin_pct", "5.5")
    increment = decimal_value(parameters.get("commercial", {}).get("round_to_chf", "1000"), "round_to_chf", positive=True)
    selling = (baseline / (ONE - margin) / increment).to_integral_value(rounding=ROUND_CEILING) * increment
    build = []
    def add(key, label, value, formula, basis):
        build.append({"key": key, "label": label, "amount_chf": money(value), "formula": formula, "basis": basis})
    add("material", "Material including waste", material, "quantity × net unit price × (1 + waste)", "Known material components; unresolved values excluded and disclosed")
    add("labour", "Installation labour", labour, "unrounded hours × hourly rate", "Applicable installation rules and context factors")
    if policy == "full_draft_v1":
        add("small_material", "Small material allowance", small, f"{display_chf(small_basis)} × {allowances.get('small_material_pct', '0')}%", "Eligible catalogue material before waste")
        add("supplier_contingency", "Supplier package contingency", contingency, f"{display_chf(contingency_basis)} × {allowances.get('supplier_package_contingency_pct', '0')}%", "Eligible supplier material before waste")
    add("transport", "Transport and equipment", transport, f"{display_chf(transport_basis)} × {allowances.get('transport_equipment_pct', '0')}%", "Known eligible material including waste and installation labour")
    project_costs = parameters.get("project_costs", {})
    for key, value in fixed.items():
        if key in {"engineering", "commissioning"}:
            formula = f"{project_costs.get(key + '_hours', '0')} h × CHF {project_costs.get(key + '_rate_chf_per_h', '0')}/h (Project assumptions)"
        else:
            parameter = "hygiene_inspection_chf" if key == "hygiene" else "documentation_chf"
            formula = f"Fixed CHF {project_costs.get(parameter, '0')} (Project assumptions)"
        add(key, key.replace("_", " ").title(), value, formula, "Project-wide service; explicit package ownership removes its separate charge")
        scopes.append({"scope": key, "owner": f"project:{key}", "amount_chf": money(value), "position_ids": [p.id for p in priced if p.included_in == f"project:{key}"], "status": "allocated" if value else "covered_elsewhere", "basis": "Single project-wide allowance"})
    add("risk", "Approved risk adjustments", risk, "sum accepted risk adjustments", "Only accepted entries enter the estimate")
    add("opportunity", "Approved opportunity adjustments", -opportunity, "− sum accepted opportunity adjustments", "Only accepted entries enter the estimate")
    add("overhead", "Overhead", overhead, f"{display_chf(adjusted_direct)} × {parameters.get('commercial', {}).get('overhead_pct', '0')}%", "Adjusted direct cost")
    residual = Decimal(money(baseline)) - sum((Decimal(row["amount_chf"]) for row in build), ZERO)
    if residual:
        add("display_rounding", "Display rounding reconciliation", residual, "rounded baseline − sum displayed components", "Full-precision arithmetic retained")
    assumptions.extend([
        {"key": "policy", "text": f"Calculation policy: {policy}. All amounts are CHF; VAT and contractual deductions excluded."},
        {"key": "coverage", "text": "Indicative price for known included scope. Missing quantities, rules, and prices are not treated as zero."},
    ])
    if policy == "full_draft_v1":
        assumptions.append({"key": "allowance_bases", "text": "Prototype allowance bases: small material on eligible catalogue material before waste; contingency on supplier material before waste; transport on eligible material plus labour. Fixed services stay project-level."})
    totals = {"material_cost_chf": money(material), "labour_cost_chf": money(labour),
        "position_direct_cost_chf": money(known_direct), "direct_cost_chf": money(known_direct if policy == "benchmark_v1" else direct),
        "adjusted_direct_cost_chf": money(adjusted_direct), "cost_baseline_chf": money(baseline),
        "unrounded_cost_baseline_chf": raw(baseline), "selling_price_chf": money(selling),
        "installation_hours": money(hours), "risk_adjustments_chf": money(risk), "opportunity_adjustments_chf": money(opportunity),
        "pending_adjustment_delta_chf": money(pending), "pending_baseline_preview_chf": money((adjusted_direct + pending) * (ONE + _pct(parameters.get("commercial", {}), "overhead_pct"))),
        "small_material_chf": money(small), "supplier_contingency_chf": money(contingency),
        "transport_equipment_chf": money(transport), "fixed_project_services_chf": money(services),
        "overhead_chf": money(overhead), "waste_chf": money(waste),
        "catalogue_material_before_waste_chf": money(rc), "supplier_material_before_waste_chf": money(rp),
        "unpriced_positions": sum(p.cost.direct_cost_chf is None and p.status not in {"out_of_scope", "non_priceable"} for p in priced),
        "policy": policy, "currency": "CHF", "label": "Indicative price for included scope"}
    return {"positions": [p.model_dump(mode="json") for p in priced], "totals": totals, "build_up": build,
        "by_system": _bucket(priced, "system", baseline, known_direct),
        "by_category": _bucket(priced, "category", baseline, known_direct),
        "scope_allocations": scopes, "assumptions": assumptions,
        "scenarios": calculate_scenarios(raw(baseline), parameters)}


def _quantile(values: list[Decimal], p_num: int, p_den: int) -> Decimal:
    """Deterministic quantile using linear interpolation on 1-D sorted Decimal values."""
    n = len(values)
    if n == 0:
        return ZERO
    if n == 1:
        return values[0]
    num = (n - 1) * p_num
    idx_floor = num // p_den
    frac_num = num % p_den
    frac = Decimal(frac_num) / Decimal(p_den)
    v0 = values[idx_floor]
    v1 = values[min(idx_floor + 1, n - 1)]
    return v0 + (v1 - v0) * frac


def _median(values: list[Decimal]) -> Decimal:
    """Deterministic median for sorted Decimal values."""
    n = len(values)
    if n == 0:
        return ZERO
    if n % 2 == 1:
        return values[n // 2]
    return (values[n // 2 - 1] + values[n // 2]) / Decimal("2")


def calculate_completeness(positions: list[dict | Position], priced_direct_chf: Decimal | str | None = None) -> dict:
    """Calculate price completeness and benchmark allowance for unpriced scope.
    
    For each unpriced position with a quantity, computes benchmark allowance:
    quantity * median direct unit cost of priced positions with the same (install_code, unit).
    Traceable: includes the reference positions used.
    Positions with no basis stay 'no_basis'.
    Calculates incremental missing cost only: known partial material or labour is already in the baseline.
    """
    raw_positions = [p.model_dump(mode="json") if hasattr(p, "model_dump") else p for p in positions]
    # Filter out PKG-CONT positions if any remain
    raw_positions = [p for p in raw_positions if not p.get("id", "").startswith("PKG-CONT-")]

    # 1. Collect priced benchmark positions
    # key: (install_code, unit) -> list of (unit_cost, ref_str)
    benchmarks: dict[tuple[str, str], list[tuple[Decimal, str]]] = {}
    total_priced_direct = ZERO

    priced_count = 0
    included_count = 0
    unpriced_count = 0
    partial_count = 0

    for pos in raw_positions:
        cost = pos.get("cost") or {}
        direct_str = cost.get("direct_cost_chf")
        qty_str = pos.get("quantity")
        unit = pos.get("unit")
        code = pos.get("install_code")
        pricing_basis = pos.get("pricing_basis")
        status = pos.get("status")

        if pricing_basis == "included_elsewhere":
            included_count += 1
        elif direct_str is not None:
            d_val = Decimal(str(direct_str))
            if d_val > ZERO:
                priced_count += 1
                total_priced_direct += d_val
            try:
                q_val = Decimal(str(qty_str)) if qty_str is not None else None
            except Exception:
                q_val = None
            if d_val > ZERO and q_val is not None and q_val > ZERO and code and unit and code != "UNKNOWN":
                unit_cost = d_val / q_val
                ref = pos.get("reference") or pos.get("id", "")
                benchmarks.setdefault((code, unit), []).append((unit_cost, ref))
        elif pricing_basis != "included_elsewhere" and status not in ("non_priceable", "out_of_scope"):
            unpriced_count += 1
            if any(cost.get(k) is not None for k in ("material_cost_chf", "labour_cost_chf")):
                partial_count += 1

    # Compute group statistics
    groups_benchmarks: dict[tuple[str, str], dict] = {}
    for key, items in benchmarks.items():
        sorted_items = sorted(items, key=lambda x: x[0])
        vals = [x[0] for x in sorted_items]
        refs = [x[1] for x in sorted_items]
        groups_benchmarks[key] = {
            "install_code": key[0],
            "unit": key[1],
            "count": len(vals),
            "median_unit_cost": _median(vals),
            "p25_unit_cost": _quantile(vals, 1, 4),
            "p75_unit_cost": _quantile(vals, 3, 4),
            "references": refs,
        }

    # 2. Score unpriced positions
    allowance_low = ZERO
    allowance_median = ZERO
    allowance_high = ZERO
    with_basis_count = 0
    no_basis_count = 0

    itemized_allowances = []

    for pos in raw_positions:
        cost = pos.get("cost") or {}
        direct_str = cost.get("direct_cost_chf")
        pricing_basis = pos.get("pricing_basis")
        status = pos.get("status")

        if direct_str is not None or pricing_basis == "included_elsewhere" or status in ("non_priceable", "out_of_scope"):
            continue

        code = pos.get("install_code")
        unit = pos.get("unit")
        qty_str = pos.get("quantity")
        try:
            qty = Decimal(str(qty_str)) if qty_str is not None else None
        except Exception:
            qty = None

        key = (code, unit) if (code and unit and code != "UNKNOWN") else None
        if key and key in groups_benchmarks and qty is not None and qty > ZERO:
            g = groups_benchmarks[key]
            known_partial = sum((Decimal(str(cost[k])) for k in ("material_cost_chf", "labour_cost_chf")
                                 if cost.get(k) is not None), ZERO)
            pos_low = max(ZERO, qty * g["p25_unit_cost"] - known_partial)
            pos_median = max(ZERO, qty * g["median_unit_cost"] - known_partial)
            pos_high = max(ZERO, qty * g["p75_unit_cost"] - known_partial)
            allowance_low += pos_low
            allowance_median += pos_median
            allowance_high += pos_high
            with_basis_count += 1
            itemized_allowances.append({
                "position_id": pos.get("id"),
                "reference": pos.get("reference") or pos.get("id"),
                "description": pos.get("description"),
                "install_code": code,
                "unit": unit,
                "quantity": raw(qty),
                "basis_status": "benchmark_matched",
                "median_unit_rate_chf": money(g["median_unit_cost"]),
                "allowance_median_chf": money(pos_median),
                "allowance_low_chf": money(pos_low),
                "allowance_high_chf": money(pos_high),
                "known_partial_chf": money(known_partial),
                "benchmark_references": g["references"][:5],  # top 5 references
                "benchmark_sample_size": g["count"],
            })
        else:
            no_basis_count += 1
            reason = "missing_quantity" if (qty is None or qty <= ZERO) else "no_matching_install_code_in_project"
            itemized_allowances.append({
                "position_id": pos.get("id"),
                "reference": pos.get("reference") or pos.get("id"),
                "description": pos.get("description"),
                "install_code": code or "UNKNOWN",
                "unit": unit or "",
                "quantity": raw(qty) if qty is not None else None,
                "basis_status": "no_basis",
                "no_basis_reason": reason,
                "median_unit_rate_chf": None,
                "allowance_median_chf": None,
                "allowance_low_chf": None,
                "allowance_high_chf": None,
                "known_partial_chf": money(sum((Decimal(str(cost[k])) for k in ("material_cost_chf", "labour_cost_chf") if cost.get(k) is not None), ZERO)),
                "benchmark_references": [],
                "benchmark_sample_size": 0,
            })

    effective_priced_direct = Decimal(str(priced_direct_chf)) if priced_direct_chf is not None else total_priced_direct
    estimated_total_value = effective_priced_direct + allowance_median
    if estimated_total_value > ZERO:
        pct_value_priced = (effective_priced_direct / estimated_total_value * HUNDRED).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)
    else:
        pct_value_priced = ZERO
    pct_positions_priced = (Decimal(priced_count) / Decimal(len(raw_positions)) * HUNDRED).quantize(
        Decimal("0.1"), rounding=ROUND_HALF_UP) if raw_positions else ZERO

    # Summary groups for UI inspection
    group_summaries = []
    for (code, unit), g in sorted(groups_benchmarks.items(), key=lambda x: x[0]):
        group_summaries.append({
            "install_code": code,
            "unit": unit,
            "sample_size": g["count"],
            "median_unit_rate_chf": money(g["median_unit_cost"]),
            "p25_unit_rate_chf": money(g["p25_unit_cost"]),
            "p75_unit_rate_chf": money(g["p75_unit_cost"]),
            "references": g["references"],
        })

    return {
        "positions_total": len(raw_positions),
        "positions_priced": priced_count,
        "positions_included_elsewhere": included_count,
        "positions_unpriced": unpriced_count,
        "positions_partial": partial_count,
        "positions_with_allowance": with_basis_count,
        "positions_no_basis": no_basis_count,
        "allowance_low_chf": money(allowance_low),
        "allowance_median_chf": money(allowance_median),
        "allowance_high_chf": money(allowance_high),
        "priced_direct_cost_chf": money(effective_priced_direct),
        "estimated_total_direct_value_chf": money(estimated_total_value),
        "pct_value_priced": str(pct_value_priced),
        "pct_positions_priced": str(pct_positions_priced),
        "benchmark_groups": group_summaries,
        "itemized_allowances": itemized_allowances,
    }

