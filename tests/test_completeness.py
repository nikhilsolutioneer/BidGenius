"""Tests for completeness calculation and unpriced scope benchmark allowance."""
from decimal import Decimal
import pytest

from tenderproof.pricing import calculate_completeness, ZERO


def test_completeness_decimal_and_deterministic():
    # Construct positions with known deterministic values
    positions = [
        # Group ('DUCT_RECT', 'm2'): 3 priced positions with direct cost / qty:
        # pos 1: qty 10, direct 1000.00 -> unit 100.00
        {
            "id": "P1", "reference": "Vent · p.1 · #1", "install_code": "DUCT_RECT", "unit": "m2",
            "quantity": "10", "cost": {"direct_cost_chf": "1000.00"}
        },
        # pos 2: qty 20, direct 4000.00 -> unit 200.00
        {
            "id": "P2", "reference": "Vent · p.1 · #2", "install_code": "DUCT_RECT", "unit": "m2",
            "quantity": "20", "cost": {"direct_cost_chf": "4000.00"}
        },
        # pos 3: qty 5, direct 1500.00 -> unit 300.00
        {
            "id": "P3", "reference": "Vent · p.1 · #3", "install_code": "DUCT_RECT", "unit": "m2",
            "quantity": "5", "cost": {"direct_cost_chf": "1500.00"}
        },
        # Group ('DIFFUSER', 'pc'): 1 priced position
        # pos 4: qty 4, direct 600.00 -> unit 150.00
        {
            "id": "P4", "reference": "Vent · p.2 · #1", "install_code": "DIFFUSER", "unit": "pc",
            "quantity": "4", "cost": {"direct_cost_chf": "600.00"}
        },
        # Unpriced positions:
        # pos 5: matching DUCT_RECT, qty 15
        # Expected:
        # DUCT_RECT unit costs: [100.00, 200.00, 300.00]
        # median = 200.00, p25 = 100 + (200-100)*0.5 = 150.00, p75 = 200 + (300-200)*0.5 = 250.00
        # For qty 15:
        # median allowance = 15 * 200.00 = 3000.00
        # low allowance = 15 * 150.00 = 2250.00
        # high allowance = 15 * 250.00 = 3750.00
        {
            "id": "U1", "reference": "Vent · p.3 · #1", "install_code": "DUCT_RECT", "unit": "m2",
            "quantity": "15", "cost": {"direct_cost_chf": None}
        },
        # pos 6: matching DIFFUSER, qty 2
        # median = 150.00, p25 = 150.00, p75 = 150.00
        # median allowance = 2 * 150.00 = 300.00
        {
            "id": "U2", "reference": "Vent · p.3 · #2", "install_code": "DIFFUSER", "unit": "pc",
            "quantity": "2", "cost": {"direct_cost_chf": None}
        },
        # pos 7: no basis (unknown install_code)
        {
            "id": "U3", "reference": "Vent · p.4 · #1", "install_code": "SPECIAL_FAN", "unit": "pc",
            "quantity": "1", "cost": {"direct_cost_chf": None}
        },
        # pos 8: no basis (missing quantity)
        {
            "id": "U4", "reference": "Vent · p.4 · #2", "install_code": "DUCT_RECT", "unit": "m2",
            "quantity": None, "cost": {"direct_cost_chf": None}
        },
        # pos 9: included elsewhere - should be excluded from unpriced
        {
            "id": "U5", "reference": "Vent · p.5 · #1", "pricing_basis": "included_elsewhere",
            "quantity": "5", "cost": {"direct_cost_chf": None}
        },
        # pos 10: out of scope - should be excluded from unpriced
        {
            "id": "U6", "reference": "Vent · p.5 · #2", "status": "out_of_scope",
            "quantity": "1", "cost": {"direct_cost_chf": None}
        },
    ]

    priced_direct_chf = "7100.00"  # 1000 + 4000 + 1500 + 600
    res = calculate_completeness(positions, priced_direct_chf)

    assert res["positions_total"] == 10
    assert res["positions_priced"] == 4
    assert res["positions_unpriced"] == 4  # U1, U2, U3, U4
    assert res["positions_with_allowance"] == 2  # U1, U2
    assert res["positions_no_basis"] == 2  # U3, U4

    # Allowances:
    # DUCT_RECT: low 2250.00, med 3000.00, high 3750.00
    # DIFFUSER: low 300.00, med 300.00, high 300.00
    # Total allowance:
    # low = 2550.00, median = 3300.00, high = 4050.00
    assert res["allowance_low_chf"] == "2550.00"
    assert res["allowance_median_chf"] == "3300.00"
    assert res["allowance_high_chf"] == "4050.00"

    # Priced direct: 7100.00
    # Estimated total value: 7100.00 + 3300.00 = 10400.00
    # % priced: 7100 / 10400 = 68.269...% -> rounded half-up: 68.3%
    assert res["priced_direct_cost_chf"] == "7100.00"
    assert res["estimated_total_direct_value_chf"] == "10400.00"
    assert res["pct_value_priced"] == "68.3"

    # Verify traceable references
    groups = {g["install_code"]: g for g in res["benchmark_groups"]}
    assert "DUCT_RECT" in groups
    assert groups["DUCT_RECT"]["sample_size"] == 3
    assert groups["DUCT_RECT"]["median_unit_rate_chf"] == "200.00"
    assert groups["DUCT_RECT"]["references"] == ["Vent · p.1 · #1", "Vent · p.1 · #2", "Vent · p.1 · #3"]

    # Verify itemized allowances
    items = {item["position_id"]: item for item in res["itemized_allowances"]}
    assert items["U1"]["basis_status"] == "benchmark_matched"
    assert items["U1"]["allowance_median_chf"] == "3000.00"
    assert len(items["U1"]["benchmark_references"]) == 3

    assert items["U3"]["basis_status"] == "no_basis"
    assert items["U3"]["no_basis_reason"] == "no_matching_install_code_in_project"
    assert items["U3"]["allowance_median_chf"] is None

    assert items["U4"]["basis_status"] == "no_basis"
    assert items["U4"]["no_basis_reason"] == "missing_quantity"


def test_included_scope_and_partial_costs_are_not_counted_twice():
    positions = [
        {"id": "P", "install_code": "DUCT_RECT", "unit": "m2", "quantity": "2",
         "pricing_basis": "catalogue", "cost": {"direct_cost_chf": "200.00"}},
        {"id": "U", "install_code": "DUCT_RECT", "unit": "m2", "quantity": "3",
         "pricing_basis": "unpriced", "cost": {"direct_cost_chf": None, "labour_cost_chf": "120.00"}},
        {"id": "I", "install_code": "DUCT_RECT", "unit": "m2", "quantity": "1",
         "pricing_basis": "included_elsewhere", "cost": {"direct_cost_chf": "0.00"}},
    ]
    result = calculate_completeness(positions, "320.00")
    assert result["positions_priced"] == 1
    assert result["positions_unpriced"] == 1
    assert result["positions_included_elsewhere"] == 1
    assert result["pct_positions_priced"] == "33.3"
    assert result["allowance_median_chf"] == "180.00"
    assert result["itemized_allowances"][0]["known_partial_chf"] == "120.00"
