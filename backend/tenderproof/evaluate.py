"""Independent, evaluation-only extraction checks against source-anchored rows.

This module and tests/fixtures/holdout.json are never imported by production
ingestion. Detection uses source evidence, never the expected price/product.
Run: python -m tenderproof.evaluate PACKAGE --output artifacts/evaluation.json
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections import Counter
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from time import perf_counter

from .models import Position, SourceSpan
from .reference import load_reference


# Manually transcribed German quantity rows for the supplied 22 examples.
# These selectors identify evidence, independently of the predicted product.
GOLDEN_SELECTORS = {
    "LV0001": ("Grösse Ø 10 cm Stk 5", "Zuluft - Tellerventil"),
    "LV0002": ("Ø 12.5 cm Stk 6", "Zuluft - Tellerventil"),
    "LV0003": ("Grösse Ø 10 cm Stk 5", "Abluft - Tellerventil"),
    "LV0004": ("Grösse (B x H) 10 Ø cm Stk 4", "Brandschutzklappen"),
    "LV0005": ("Grösse Ø 12.5 cm Stk 6", "Drosselklappen"),
    "LV0006": ("Druckverlust 30Pa Stk 4", "Schalldämpfer"),
    "LV0007": ("BM0 50x30 1217 3100 500 Stk 4", "Volumenstrom"),
    "LV0008": ("250 100 150 Stk 6", "konstant"),
    "LV0009": ("100 10 28.5x20.5 27 Stk 6", "Kompaktschalldämpfer"),
    "LV0010": ("Druckverlust 21Pa Stk 4", "Kanalschalldämpfer"),
    "LV0011": ("Druckverlust 33Pa Stk 6", "Schalldämpfer"),
    "LV0012": ("TVJ-D 30x20 800 1600 300 Stk 6", "Volumenstrom"),
    "LV0013": ("TVR-D 12.5 60 200 150 Stk 10", "TVR-D"),
    "LV0014": ("TVR-D 16 120 400 150 Stk 6", "TVR-D"),
    "LV0015": ("TVR-D 20 180 600 150 Stk 12", "TVR-D"),
    "LV0016": ("mit Alu-Folie, gestiftet m2 52", "30 mm"),
    "LV0017": ("mit Alu-Folie, gestiftet m2 12", "60 mm"),
    "LV0018": ("Wetterfeste Ummantelung V2A inkl. Abdichtung m2 440", "100 mm"),
    "LV0019": ("300 x 200 Stk 4", "Durchdringungen"),
    "LV0020": ("Grösse 16 Ø cm Stk 8", "Durchdringungen"),
    "LV0021": ("Anzahl Durchführungen Stk 8", "Anschlusswinkle"),
    "LV0022": ("400 x 200 Stk 8", "Revisisondeckel"),
}


def canonical(text: str) -> str:
    """Ignore whitespace wrapping without deleting significant numeric tokens."""
    return re.sub(r"\s+", "", text.casefold()).replace("–", "-").replace("²", "2")


def golden_rows(package: Path) -> list[dict]:
    import csv
    with (package / "example_lv_positions.csv").open(encoding="utf-8-sig", newline="") as handle:
        result = []
        for row in csv.DictReader(handle):
            source, context = GOLDEN_SELECTORS[row["lv_id"]]
            result.append({"id": row["lv_id"], "page": int(row["source_page"]),
                "system": re.search(r"LA\d{2}", row["system"])[0], "source_snippet": source,
                "context": context, "quantity": row["quantity"], "unit": row["unit"],
                "product_id": row["suggested_product_id"]})
        return result


def _quantity_equal(actual: str | None, expected: str | None) -> bool:
    if actual is None or expected is None:
        return actual is None and expected is None
    try:
        return Decimal(actual).is_finite() and Decimal(actual) == Decimal(expected)
    except InvalidOperation:
        return False


def _source_match(row: dict, position: Position, span_lookup: dict[str, SourceSpan]) -> tuple[bool, int]:
    spans = [span_lookup[s] for s in position.source_span_ids if s in span_lookup and span_lookup[s].page == row["page"]]
    if not spans:
        return False, 0
    ordered = sorted(spans, key=lambda span: (span.top, span.x0))
    evidence = "\n".join(s.text for s in ordered)
    # Require the row in actual referenced evidence, not only generated prose.
    found = canonical(row["source_snippet"]) in canonical(evidence)
    if row.get("source_match") == "exact_line":
        found = any(canonical(span.text) == canonical(row["source_snippet"]) for span in spans)
    text = "\n".join([evidence, position.original_description, position.description])
    if row.get("context") and canonical(row["context"]) not in canonical(text):
        return False, len(evidence)
    return found, len(evidence)


def evaluate_rows(rows: list[dict], positions: list[Position], spans: list[SourceSpan], label: str) -> dict:
    span_lookup = {span.id: span for span in spans}
    used = set()
    results = []
    for row in rows:
        candidates = []
        for p in positions:
            if p.id in used:
                continue
            matched, evidence_length = _source_match(row, p, span_lookup)
            if matched:
                candidates.append((evidence_length, p.id, p))
        # Prefer the most specific evidence scope. Never use an expected quantity
        # or expected product to choose a detection candidate.
        candidates.sort(key=lambda item: (item[0], item[1]))
        actual = candidates[0][2] if candidates else None
        if actual:
            used.add(actual.id)
        quantity_ok = bool(actual and _quantity_equal(actual.quantity, row["quantity"]) and actual.unit == row["unit"])
        product_ok = bool(actual and actual.product_id == row["product_id"])
        system_ok = bool(actual and actual.system == row["system"])
        result = {"id": row["id"], "page": row["page"], "source_snippet": row["source_snippet"],
            "expected": {key: row.get(key) for key in ("system", "quantity", "unit", "product_id")},
            "detected": actual is not None, "quantity_and_unit_correct": quantity_ok,
            "catalogue_reference_correct": product_ok, "system_correct": system_ok,
            "all_correct": bool(actual and quantity_ok and product_ok and system_ok),
            "ambiguous_detection_candidates": len(candidates),
            "actual": {"id": actual.id, "system": actual.system, "quantity": actual.quantity,
                "unit": actual.unit, "product_id": actual.product_id,
                "evidence_band": actual.match_evidence_band, "status": actual.status,
                "description": actual.description[:240]} if actual else None}
        results.append(result)
    total = len(results)
    detected = sum(row["detected"] for row in results)
    def metric(field):
        count = sum(row[field] for row in results)
        return {"correct": count, "total": total, "rate": round(count / total, 4) if total else None,
                "among_detected_rate": round(count / detected, 4) if detected else None}
    return {"label": label, "expected_rows": total, "detected_rows": detected,
        "detection_recall": round(detected / total, 4) if total else None,
        "quantity_and_unit": metric("quantity_and_unit_correct"),
        "catalogue_reference": metric("catalogue_reference_correct"),
        "system_assignment": metric("system_correct"), "complete_row": metric("all_correct"),
        "matched_reference_rows": sum(row["product_id"] is not None for row in rows),
        "expected_unmatched_rows": sum(row["product_id"] is None for row in rows),
        "results": results,
        "limitations": "Source-anchored recall on annotated rows only; this does not measure full-tender precision, completeness, technical equivalence, or pricing accuracy. Detection candidates are selected without consulting the expected quantity or product."}


def run_evaluation(package: Path, holdout_path: Path) -> dict:
    # Deliberately imported only by the evaluation entry point.
    from .ingestion import PARSER_VERSION, extract_local_batch, parse_pdf
    from .matching import match_position
    refs = load_reference(package)
    pdf = package / refs["parameters"]["project"]["source_tender_file"]
    started = perf_counter()
    pages, spans = parse_pdf(pdf, "independent-evaluation")
    positions = []
    dispositions = {}
    errors = []
    for offset in range(0, len(pages), 4):
        current = pages[offset:offset + 4]
        page_numbers = {p.page for p in current}
        batch = extract_local_batch(current, [s for s in spans if s.page in page_numbers], refs["catalog"])
        positions.extend(match_position(p, refs["catalog"]) for p in batch.positions)
        dispositions.update(batch.dispositions)
        errors.extend(batch.errors)
    holdout = json.loads(holdout_path.read_text(encoding="utf-8"))
    return {"evaluation_mode": "Actual local parser and matching; no LLM used; fixtures are evaluation-only",
        "evaluated_at": datetime.now(timezone.utc).isoformat(), "parser_version": PARSER_VERSION,
        "source_sha256": hashlib.sha256(pdf.read_bytes()).hexdigest(),
        "holdout_sha256": hashlib.sha256(holdout_path.read_bytes()).hexdigest(),
        "source": pdf.name, "elapsed_seconds": round(perf_counter() - started, 3),
        "pages_processed": len(pages), "page_status_counts": dict(Counter(p.status for p in pages)),
        "positions_extracted": len(positions), "position_system_counts": dict(Counter(p.system for p in positions)),
        "unassigned_blocks": sum(value == "unresolved" for value in dispositions.values()),
        "batch_errors": errors,
        "verified_examples": evaluate_rows(golden_rows(package), positions, spans, "Supplied 22 examples"),
        "independent_holdout": evaluate_rows(holdout["rows"], positions, spans, "29 manually annotated rows outside the supplied examples"),
        "holdout_provenance": {k: v for k, v in holdout.items() if k != "rows"}}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("package", type=Path)
    parser.add_argument("--holdout", type=Path, default=Path(__file__).resolve().parents[2] / "tests" / "fixtures" / "holdout.json")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = run_evaluation(args.package, args.holdout)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"Full evaluation saved to {args.output}")
    print(json.dumps({key: value if key not in {"verified_examples", "independent_holdout"} else
        {k: v for k, v in value.items() if k != "results"} for key, value in result.items()}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
