from pathlib import Path
import csv

import pytest

from tenderproof.ingestion import _dimensions, _quantity, _schedule, extract_local_batch, parse_pdf
from tenderproof.models import PageRecord, SourceSpan
from tenderproof.pricing import calculate_estimate
from tenderproof.reference import load_reference


ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "Schulhaus_Oberglatt_Hackathon_Starter_Package_v2"


def span(text, kind="text", index=1, page=1):
    return SourceSpan(id=f"s{index}", document_id="doc", page=page, text=text, x0=80, top=100 + index * 12,
                      x1=450, bottom=110 + index * 12, page_width=595, page_height=842, kind=kind)


def test_decimal_and_missing_quantity():
    assert _quantity("Grösse Ø 12.5 cm Stk 6") == ("6", "pc")
    assert _quantity("mit Alu-Folie, gestiftet m2") == (None, "m2")
    assert _quantity("Montagezeit Std. 176") == ("176", "h")


def test_actual_schedule_conversions_and_no_fitting_area_guess():
    page = PageRecord(page=1, width=595, height=842, text="Bauteilliste", system="LA01")
    p = _schedule(page, span("33860R-R Wickelfalzrohr 100"))
    assert p.quantity == "33.86" and p.unit == "m"
    p = _schedule(page, span("2342L Luftleitung 1000 800"))
    assert p.quantity == "8.4312" and p.unit == "m2"
    p = _schedule(page, span("900LT Luftleitungsteil 1000 800"))
    assert p.quantity == "900" and p.unit == "mm"
    assert p.attributes["unsupported_conversion"]


def test_cm_dimensions_and_conflicting_compact_silencer():
    attrs = _dimensions("Schalldämpfer\nB x H x L 40 x 30 x 125 cm", "Druckverlust 30Pa Stk 4")
    assert attrs["width_mm"] == "400" and attrs["length_mm"] == "1250"
    attrs = _dimensions("Kompaktschalldämpfer\nTyp KOSD 100/900", "100 10 28.5x20.5 27 Stk 6")
    assert attrs["length_mm"] == "900" and attrs["schedule_length_mm"] == "1000"


def test_set_components_do_not_multiply_position_quantity():
    rows = [span("Anschlusswinkle für Befestigung an Wand oder Decke", "heading", 1),
            span("50x50x35x2.5mm, 8 Stück pro Durchführung", "text", 2),
            span("Anzahl Durchführungen Stk 8", "quantity", 3)]
    page = PageRecord(page=1, width=595, height=842, text="\n".join(s.text for s in rows), system="LA04")
    p = extract_local_batch([page], rows, []).positions[0]
    assert p.quantity == "8"
    assert p.attributes["components_per_set"] == "8"
    assert p.install_code == "SUPPORT_SET"


@pytest.fixture(scope="module")
def actual_tender():
    if not PACKAGE.exists():
        pytest.skip("Real starter package unavailable")
    pages, spans = parse_pdf(next(PACKAGE.glob("BKP*.pdf")), "regression")
    with (PACKAGE / "catalog.csv").open(encoding="utf-8-sig", newline="") as f:
        catalog = list(csv.DictReader(f))
    batches = [extract_local_batch(pages[i:i + 4], spans, catalog) for i in range(0, len(pages), 4)]
    return pages, spans, [p for b in batches for p in b.positions], [i for b in batches for i in b.issues]


def test_all_pages_and_real_system_conflict(actual_tender):
    pages, spans, positions, issues = actual_tender
    assert len(pages) == 202
    assert len({s.id for s in spans}) == len(spans)
    assert all(s.page_width >= s.x1 and s.page_height >= s.bottom for s in spans)
    assert pages[180].system == "LA05"
    assert any(i.kind == "system_conflict" and "LA03" in i.detail and "LA05" in i.detail for i in issues)
    assert {"LA01", "LA02", "LA03", "LA04", "LA05", "ROOF"} <= {p.system for p in positions}


def test_actual_missing_quantity_roof_and_valves(actual_tender):
    _, _, positions, _ = actual_tender
    assert any(p.source_page == 169 and p.unit == "m2" and p.quantity is None for p in positions)
    assert any(p.source_page == 197 and p.quantity == "150" and p.unit == "pc" and not p.product_id for p in positions)
    assert any(p.source_page == 197 and p.quantity == "500" and p.unit == "m" and not p.product_id for p in positions)
    valve = next(p for p in positions if p.source_page == 78 and p.product_id == "P-AIR-001")
    assert valve.quantity == "5" and valve.attributes["diameter_mm"] == "100"
    assert valve.field_sources["quantity"] and valve.technical_equivalence == "unverified"


def test_actual_air_handling_units_are_priced_with_sizing_and_quantity_assumptions(actual_tender):
    _, _, positions, _ = actual_tender
    refs = load_reference(PACKAGE)
    estimate = calculate_estimate(positions, refs["catalog"], refs["productivity"], refs["parameters"])
    ahus = {p["source_page"]: p for p in estimate["positions"] if p["install_code"] == "AHU_LARGE" and p["source_page"] in {67, 89, 119, 147, 174}}
    expected = {
        67: ("LA01", "700", "P-AHU-1000", True),
        89: ("LA02", "6200", "P-AHU-6200", False),
        119: ("LA03", "3500", "P-AHU-3500", False),
        147: ("LA04", "10500", "P-AHU-10500", True),
        174: ("LA05", "2900", "P-AHU-3500", True),
    }
    assert set(ahus) == set(expected)
    for page, (system, airflow, product_id, quantity_assumed) in expected.items():
        p = ahus[page]
        assert p["system"] == system
        assert p["quantity"] == "1" and p["unit"] == "pc"
        assert p["attributes"]["airflow_m3h"] == airflow
        assert p["product_id"] == product_id
        assert p["status"] == "supplier_quote_required"
        assert p["cost"]["direct_cost_chf"] is not None
        assert p["cost"]["base_hours_per_unit"] == "34"
        assert p["source_span_ids"]
        assert any("supplier quote required" in text and "m3/h" in text for text in p["assumptions"])
        assert product_id in [candidate["product_id"] for candidate in p["candidates"]]
        missing_quantity = [w for w in p["warnings"] if w["kind"] == "missing_quantity"]
        if quantity_assumed:
            assert missing_quantity and missing_quantity[0]["severity"] == "warning"
            assert any("1 pc assumed" in text for text in p["assumptions"])
        else:
            assert not missing_quantity


def test_production_modules_never_read_evaluation_files():
    for module in ("ingestion.py", "matching.py", "ai.py"):
        source = (ROOT / "backend" / "tenderproof" / module).read_text(encoding="utf-8")
        assert "example_lv_positions.csv" not in source
        assert "expected_output_example.json" not in source
