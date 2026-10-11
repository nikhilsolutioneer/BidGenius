from copy import deepcopy
from decimal import Decimal
from pathlib import Path

import pytest

from tenderproof.benchmark import benchmark_positions, run_benchmark
from tenderproof.ingestion import _schedule
from tenderproof.models import CommercialAdjustment, PageRecord, Position, SourceSpan
from tenderproof.pricing import calculate_estimate, calculate_scenarios, money, price_position
from tenderproof.reference import load_reference

PACKAGE = Path(__file__).resolve().parents[1] / "Schulhaus_Oberglatt_Hackathon_Starter_Package_v2"


@pytest.fixture
def refs():
    return load_reference(PACKAGE)


@pytest.fixture
def position():
    return benchmark_positions(PACKAGE)[0]


def test_all_22_calculations_totals_and_scenarios():
    report = run_benchmark(PACKAGE)
    assert report["positions_checked"] == 22
    assert report["passed"], report["differences"]


def test_precision_and_unrounded_hours(refs, position):
    p = price_position(position, **refs)
    assert p.cost.unrounded_hours == "4.346875"
    assert p.cost.material_cost_chf == "388.96"
    assert p.cost.labour_cost_chf == "417.30"
    assert p.cost.direct_cost_chf == "806.26"
    assert money("500.225") == "500.23"


@pytest.mark.parametrize("value", ["NaN", "Infinity", "-Infinity", "abc", "-1"])
def test_invalid_quantities(refs, position, value):
    position.quantity = value
    with pytest.raises(ValueError):
        price_position(position, **refs)


def test_missing_quantity_is_unknown(refs, position):
    position.quantity = None
    p = price_position(position, **refs)
    assert p.cost.direct_cost_chf is None
    assert p.cost.material_cost_chf is None
    assert p.status == "insufficient_information"


def test_unknown_rule_does_not_mean_zero_labour(refs, position):
    position.install_code = "UNKNOWN"
    p = price_position(position, **refs)
    assert p.cost.material_cost_chf == "388.96"
    assert p.cost.labour_cost_chf is None
    assert p.cost.direct_cost_chf is None


def test_unit_and_reference_validation(refs, position):
    position.unit = "m2"
    with pytest.raises(ValueError, match="incompatible"):
        price_position(position, **refs)
    position.unit = "pc"
    position.product_id = "invented"
    with pytest.raises(ValueError, match="Unknown product"):
        price_position(position, **refs)


@pytest.mark.parametrize("value", ["0", "-1", "NaN"])
def test_invalid_site_factor(refs, position, value):
    refs["parameters"]["productivity_factors"]["site_efficiency"] = value
    with pytest.raises(ValueError):
        price_position(position, **refs)


def test_hall_replaces_school_factor(refs, position):
    position.system = "LA05"
    p = price_position(position, **refs)
    assert "mounting_height_school" not in p.cost.factors
    assert p.cost.factors["mounting_height_sports_hall"] == "1.25"
    assert Decimal(p.cost.unrounded_hours) == Decimal("5") * Decimal(".65") / Decimal(".88") * Decimal("1.25") * Decimal("1.07")


def test_supplied_by_others_only_charges_labour(refs, position):
    position.scope_tags = ["supplied_by_others"]
    p = price_position(position, **refs)
    assert p.pricing_basis == "labour_only"
    assert p.cost.material_cost_chf == "0.00"
    assert p.cost.direct_cost_chf == "417.30"


def test_included_installation_no_double_charge(refs, position):
    position.attributes["inclusions"] = ["installation"]
    p = price_position(position, **refs)
    assert p.cost.labour_cost_chf == "0.00"
    assert p.cost.direct_cost_chf == "388.96"


def test_matching_confidence_does_not_imply_equivalence(refs, position):
    assert position.match_evidence_band == "strong"
    p = price_position(position, **refs)
    assert p.technical_equivalence == "unverified"
    position.match_evidence_band = "conflicting"
    assert price_position(position, **refs).status == "review_required"


def test_full_policy_buckets_and_fixed_services(refs, position):
    result = calculate_estimate([position], **refs)
    assert result["totals"]["fixed_project_services_chf"] == "115700.00"
    assert result["totals"]["small_material_chf"] == "13.09"
    baseline = Decimal(result["totals"]["cost_baseline_chf"])
    assert sum(Decimal(b["amount_chf"]) for b in result["by_system"]) == baseline
    assert sum(Decimal(b["amount_chf"]) for b in result["by_category"]) == baseline
    assert sum(Decimal(b["amount_chf"]) for b in result["build_up"]) == baseline


def test_supplier_contingency_and_transport_eligibility(refs):
    position = benchmark_positions(PACKAGE)[5]
    result = calculate_estimate([position], **refs)
    assert result["totals"]["supplier_contingency_chf"] == "312.00"
    assert result["totals"]["small_material_chf"] == "0.00"
    assert result["positions"][0]["status"] == "supplier_quote_required"
    position.attributes["inclusions"] = ["supplier_contingency", "transport"]
    result = calculate_estimate([position], **refs)
    assert result["totals"]["supplier_contingency_chf"] == "0.00"
    assert result["totals"]["transport_equipment_chf"] == "0.00"


def schedule_position(text: str):
    page = PageRecord(page=75, width=595, height=842, text="Bauteilliste", system="LA01")
    span = SourceSpan(id="s", document_id="d", page=75, text=text, x0=80, top=100, x1=420, bottom=112, page_width=595, page_height=842)
    return _schedule(page, span)


def test_rectangular_duct_area_rate_rule_sizes_up_to_catalog(refs):
    p = schedule_position("15720 L Luftleitung 1100 350")
    refs["parameters"]["duct_pricing"]["rect_duct_area_rate_enabled"] = "true"
    priced = calculate_estimate([p], **refs)["positions"][0]
    assert p.quantity == "45.588" and p.unit == "m2"
    assert priced["product_id"] == "P-DCT-X-1000x800"
    assert priced["status"] == "assumption_applied"
    assert priced["cost"]["net_unit_cost_chf"] == "220.5"
    assert priced["cost"]["material_cost_chf"] == "10454.24"
    assert "Rectangular duct area rate" in priced["assumptions"][0]
    assert "catalog:P-DCT-X-1000x800" in priced["cost"]["references"]


def test_luftleitungsteil_area_rule_converts_mm_to_m2(refs):
    p = schedule_position("224 LT Luftleitungsteil 100 450")
    refs["parameters"]["duct_pricing"]["lt_area_rate_enabled"] = "true"
    priced = calculate_estimate([p], **refs)["positions"][0]
    assert p.attributes["area_m2"] == "0.2464"
    assert priced["quantity"] == "0.2464" and priced["unit"] == "m2"
    assert priced["product_id"] == "P-DCT-X-400x200"
    assert priced["cost"]["material_cost_chf"] == "22.14"
    assert "2 × (width_mm + height_mm) × length_mm" in priced["attributes"]["conversion"]["formula"]
    assert any(w["kind"] == "geometry_review" and w["severity"] == "warning" for w in priced["warnings"])


def test_straight_duct_bulk_rule_does_not_price_lt_fittings(refs):
    p = schedule_position("224 LT Luftleitungsteil 100 450")
    refs["parameters"]["duct_pricing"]["rect_duct_area_rate_enabled"] = "true"
    priced = calculate_estimate([p], **refs)["positions"][0]
    assert priced["quantity"] == "224"
    assert priced["unit"] == "mm"
    assert priced["product_id"] is None
    assert priced["cost"]["direct_cost_chf"] is None


@pytest.mark.parametrize("text, flag, original_quantity, original_unit", [
    ("15720 L Luftleitung 1100 350", "rect_duct_area_rate_enabled", "45.588", "m2"),
    ("224 LT Luftleitungsteil 100 450", "lt_area_rate_enabled", "224", "mm"),
])
@pytest.mark.parametrize("legacy_saved_row", [False, True])
def test_reversing_area_rule_reprices_from_pdf_fields(refs, text, flag, original_quantity, original_unit, legacy_saved_row):
    original = schedule_position(text)
    refs["parameters"]["duct_pricing"][flag] = "true"
    priced = calculate_estimate([original], **refs)["positions"][0]
    assert priced["cost"]["direct_cost_chf"] is not None
    if legacy_saved_row:
        priced["attributes"].pop("_area_rule_original")
    refs["parameters"]["duct_pricing"][flag] = "false"
    restored = calculate_estimate([Position.model_validate(priced)], **refs)["positions"][0]
    assert restored["quantity"] == original_quantity
    assert restored["unit"] == original_unit
    assert restored["product_id"] is None
    assert restored["cost"]["direct_cost_chf"] is None


def test_rectangular_fitting_prices_known_labour_and_requires_material_quote(refs):
    p = schedule_position("2 BA Bogen asymmetrisch 400 200")
    priced = calculate_estimate([p], **refs)["positions"][0]
    assert priced["install_code"] == "DUCT_FITTING"
    assert priced["status"] == "supplier_quote_required"
    assert priced["cost"]["material_cost_chf"] is None
    assert priced["cost"]["labour_cost_chf"] == "192.60"
    assert priced["cost"]["direct_cost_chf"] is None
    assert "Rectangular fittings: labour priced" in priced["assumptions"][-1]


def test_rectangular_fitting_equivalent_area_material_mode(refs):
    p = schedule_position("2 BA Bogen asymmetrisch 400 200")
    refs["parameters"]["duct_pricing"]["rect_duct_area_rate_enabled"] = "true"
    refs["parameters"]["duct_pricing"]["rect_fitting_material_mode"] = "equivalent_area"
    priced = calculate_estimate([p], **refs)["positions"][0]
    assert priced["status"] == "assumption_applied"
    assert priced["cost"]["material_cost_chf"] == "215.65"
    assert priced["cost"]["labour_cost_chf"] == "192.60"
    assert priced["cost"]["direct_cost_chf"] == "408.25"
    assert "equivalent duct area" in priced["cost"]["formula"]


def test_project_service_charged_once(refs, position):
    service = position.model_copy(update={"id": "service", "included_in": "project:commissioning"})
    result = calculate_estimate([position, service], **refs)
    assert result["positions"][1]["cost"]["direct_cost_chf"] == "0.00"
    assert result["totals"]["fixed_project_services_chf"] == "115700.00"
    position.attributes["inclusions"] = ["project:commissioning"]
    result = calculate_estimate([position, service], **refs)
    assert result["totals"]["fixed_project_services_chf"] == "90900.00"


def test_included_child_and_invalid_ownership(refs, position):
    child = position.model_copy(update={"id": "child", "included_in": position.id})
    result = calculate_estimate([position, child], **refs)
    assert result["positions"][1]["cost"]["direct_cost_chf"] == "0.00"
    position.included_in = "child"
    with pytest.raises(ValueError, match="Cyclic"):
        calculate_estimate([position, child], **refs)


def adjustment(**kwargs):
    return CommercialAdjustment(id="adjustment", kind="risk", title="Logistics risk", amount_chf="1000", basis="Reviewed additional crane mobilisation", **kwargs)


def test_pending_adjustments_not_applied_and_approved_before_overhead(refs, position):
    before = calculate_estimate([position], **refs)
    pending = calculate_estimate([position], **refs, adjustments=[adjustment()])
    assert before["totals"]["cost_baseline_chf"] == pending["totals"]["cost_baseline_chf"]
    assert pending["totals"]["pending_adjustment_delta_chf"] == "1000.00"
    approved = calculate_estimate([position], **refs, adjustments=[adjustment(review_state="accepted")])
    assert Decimal(approved["totals"]["cost_baseline_chf"]) - Decimal(before["totals"]["cost_baseline_chf"]) == Decimal("1085.00")


def test_pending_opportunity_does_not_reduce_official_price(refs, position):
    opp = adjustment().model_copy(update={"kind": "opportunity"})
    before = calculate_estimate([position], **refs)
    after = calculate_estimate([position], **refs, adjustments=[opp])
    assert after["totals"]["cost_baseline_chf"] == before["totals"]["cost_baseline_chf"]
    assert after["totals"]["pending_adjustment_delta_chf"] == "-1000.00"


def test_approved_overlap_requires_resolution(refs, position):
    with pytest.raises(ValueError, match="overlaps"):
        calculate_estimate([position], **refs, adjustments=[adjustment(scope="supplier_contingency", review_state="accepted")])


def test_excess_opportunity_rejected(refs, position):
    opp = adjustment(review_state="accepted").model_copy(update={"kind": "opportunity", "amount_chf": "10000000"})
    with pytest.raises(ValueError, match="non-positive"):
        calculate_estimate([position], **refs, adjustments=[opp])


@pytest.mark.parametrize("margin", ["100", "101", "NaN", "-1"])
def test_scenario_invalid_margin(refs, margin):
    with pytest.raises(ValueError):
        calculate_scenarios("10000", refs["parameters"], {"scenario_margins_pct": {"Target": margin}})


def test_scenario_range_and_probability(refs):
    result = calculate_scenarios("414489.12", refs["parameters"])
    prices = [Decimal(s["bid_price_chf"]) for s in result["scenarios"]]
    assert Decimal(result["low_chf"]) == min(prices)
    assert Decimal(result["high_chf"]) == max(prices)
    with pytest.raises(ValueError):
        calculate_scenarios("10", refs["parameters"], {"minimum_probability": ".9", "maximum_probability": ".5"})


def test_reference_loader_uses_only_production_inputs(tmp_path):
    import shutil
    for name in ("catalog.csv", "productivity.csv", "project_parameters.json"):
        shutil.copyfile(PACKAGE / name, tmp_path / name)
    refs = load_reference(tmp_path)
    assert len(refs["catalog"]) == 56
    assert len(refs["productivity"]) == 22
    assert isinstance(refs["catalog"][0]["net_cost_chf"], str)
