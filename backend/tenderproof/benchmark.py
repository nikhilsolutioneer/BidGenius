"""Evaluation-only CLI; never imported by production extraction or demo loading.

Run: python -m tenderproof.benchmark path/to/starter/package
"""
from __future__ import annotations

import argparse
import csv
import json
from decimal import Decimal
from pathlib import Path

from .models import Position
from .pricing import calculate_estimate
from .reference import load_reference


def benchmark_positions(package: Path) -> list[Position]:
    with (package / "example_lv_positions.csv").open(encoding="utf-8-sig", newline="") as handle:
        return [Position(id=row["lv_id"], document_id="benchmark-fixture", system=row["system"],
            category=row["category"], description=row["description"], original_description=row["description"],
            quantity=row["quantity"], unit=row["unit"], source_page=int(row["source_page"]),
            product_id=row["suggested_product_id"], install_code=row["expected_install_code"],
            status=row["ground_truth_status"], match_evidence_band="strong") for row in csv.DictReader(handle)]


def run_benchmark(package: Path) -> dict:
    refs = load_reference(package)
    result = calculate_estimate(benchmark_positions(package), **refs, policy="benchmark_v1")
    expected = json.loads((package / "expected_output_example.json").read_text(encoding="utf-8-sig"), parse_float=str)
    differences = []
    field_map = {"material_cost_chf": "material_cost_chf", "adjusted_install_hours": "adjusted_install_hours",
        "labour_cost_chf": "labour_cost_chf", "direct_position_cost_chf": "direct_cost_chf"}
    actual_positions = {p["id"]: p for p in result["positions"]}
    for target in expected["position_results"]:
        actual = actual_positions[target["lv_id"]]
        for expected_key, actual_key in field_map.items():
            if Decimal(str(target[expected_key])) != Decimal(actual["cost"][actual_key]):
                differences.append({"position": target["lv_id"], "field": expected_key,
                                    "expected": str(target[expected_key]), "actual": actual["cost"][actual_key]})
    for key, value in expected["example_subset_summary"].items():
        if Decimal(str(value)) != Decimal(result["totals"][key]):
            differences.append({"field": key, "expected": str(value), "actual": result["totals"][key]})
    for target, actual in zip(expected["recommended_bid_range"]["scenarios"], result["scenarios"]["scenarios"]):
        for key in ("bid_price_chf", "margin_pct", "estimated_win_probability", "expected_contribution_chf"):
            if Decimal(str(target[key])) != Decimal(actual[key]):
                differences.append({"scenario": target["scenario"], "field": key, "expected": str(target[key]), "actual": actual[key]})
    return {"evaluation": "Deterministic calculation only — verified 22-position subset, not PDF extraction or the full tender",
        "passed": not differences, "positions_checked": len(actual_positions), "differences": differences,
        "totals": result["totals"], "scenarios": result["scenarios"],
        "rounding_note": "Display uses HALF_UP. Labour and aggregates use unrounded quantities, hours and costs."}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("package", type=Path)
    args = parser.parse_args()
    result = run_benchmark(args.package)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    raise SystemExit(0 if result["passed"] else 1)


if __name__ == "__main__":
    main()
