import json
from pathlib import Path

from tenderproof.evaluate import evaluate_rows, golden_rows
from tenderproof.models import Position, SourceSpan

ROOT = Path(__file__).resolve().parents[1]


def source(text="33860R-R Wickelfalzrohr 100"):
    return SourceSpan(id="source", document_id="doc", page=76, text=text, x0=10, top=10,
        x1=200, bottom=25, page_width=595, page_height=842)


def position(**kwargs):
    fields = dict(id="actual", document_id="doc", source_page=76, system="LA01", description="Circular duct",
        source_span_ids=["source"], quantity="33.860", unit="m", product_id="P-DCT-R-100")
    fields.update(kwargs)
    return Position(**fields)


def row():
    return dict(id="H003", page=76, system="LA01", source_snippet="33860R-R Wickelfalzrohr 100",
        quantity="33.860", unit="m", product_id="P-DCT-R-100")


def test_evaluation_reports_real_mismatch_without_using_expected_product_for_detection():
    actual = position(product_id="wrong", quantity="33860")
    result = evaluate_rows([row()], [actual], [source()], "test")
    assert result["detected_rows"] == 1
    assert result["catalogue_reference"]["correct"] == 0
    assert result["quantity_and_unit"]["correct"] == 0
    assert result["system_assignment"]["correct"] == 1


def test_generated_description_cannot_substitute_for_source_evidence():
    actual = position(description=row()["source_snippet"])
    result = evaluate_rows([row()], [actual], [source("unrelated evidence")], "test")
    assert result["detected_rows"] == 0


def test_one_actual_position_cannot_satisfy_two_expected_rows():
    result = evaluate_rows([row(), {**row(), "id": "other"}], [position()], [source()], "test")
    assert result["detected_rows"] == 1
    assert result["detection_recall"] == 0.5


def test_equivalent_decimal_spelling_is_equal():
    result = evaluate_rows([row()], [position(quantity="33.86")], [source()], "test")
    assert result["complete_row"]["correct"] == 1


def test_holdout_covers_all_systems_has_unmatched_and_unknown_rows():
    holdout = json.loads((ROOT / "tests/fixtures/holdout.json").read_text(encoding="utf-8"))
    assert len(holdout["rows"]) >= 24
    assert {r["system"] for r in holdout["rows"]} == {"LA01", "LA02", "LA03", "LA04", "LA05", "ROOF"}
    assert any(r["quantity"] is None for r in holdout["rows"])
    assert any(r["product_id"] is None for r in holdout["rows"])
    golden = golden_rows(ROOT / "Schulhaus_Oberglatt_Hackathon_Starter_Package_v2")
    identities = {(r["page"], r["source_snippet"]) for r in golden}
    assert all((r["page"], r["source_snippet"]) not in identities for r in holdout["rows"])
