import csv
from pathlib import Path

import pytest

from tenderproof.ai import AIExtraction, ExtractedPosition, validate_ai_output
from tenderproof.matching import infer_attributes, match_position, normalize_number, validate_explicit_reference
from tenderproof.models import PageRecord, Position, SourceSpan


@pytest.fixture
def catalog():
    path = Path(__file__).resolve().parents[1] / "Schulhaus_Oberglatt_Hackathon_Starter_Package_v2" / "catalog.csv"
    with path.open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def position(**kwargs):
    return Position(id="p", document_id="d", source_page=1, **kwargs)


def test_strong_pricing_match_is_not_technical_equivalence(catalog):
    p = match_position(position(description="Zuluftventil DN100", quantity="5", unit="pc"), catalog)
    assert p.product_id == "P-AIR-001" and p.match_evidence_band == "strong"
    assert p.technical_equivalence == "unverified"


def test_conflicting_override_is_visible(catalog):
    p = match_position(position(description="Zuluftventil DN160", quantity="2", unit="pc", product_id="P-AIR-001"), catalog)
    assert p.match_evidence_band == "conflicting"
    assert p.status == "review_required"
    assert p.warnings[0].severity == "blocker"


def test_supplier_reference_remains_provisional(catalog):
    p = match_position(position(description="Schalldämpfer 400x300x1250 mm", quantity="4", unit="pc"), catalog)
    assert p.product_id == "P-SIL-001"
    assert p.pricing_basis == "supplier_reference" and p.status == "supplier_quote_required"


@pytest.mark.parametrize(("raw", "normalized"), [("6`200", "6200"), ("10`500", "10500"), ("2'900", "2900"), ("3 500", "3500")])
def test_swiss_airflow_numbers(raw, normalized):
    assert normalize_number(raw) == normalized
    attrs = infer_attributes(f"Luftmenge {raw} m3/h")
    assert attrs["airflow_m3h"] == normalized


@pytest.mark.parametrize(("flow", "product_id"), [("700", "P-AHU-1000"), ("2`900", "P-AHU-3500"), ("6`200", "P-AHU-6200"), ("10`500", "P-AHU-10500")])
def test_supplier_airflow_packages_size_up_from_tender_airflow(catalog, flow, product_id):
    description = f"Zuluftgeraet 5-1\nLuftmenge {flow} m3/h"
    p = match_position(position(description=description, original_description=description, quantity="1", unit="pc", install_code="AHU_LARGE"), catalog)
    assert p.product_id == product_id
    assert p.status == "supplier_quote_required"
    assert p.pricing_basis == "supplier_reference"
    assert any("supplier quote required" in assumption for assumption in p.assumptions)
    assert product_id in [candidate.product_id for candidate in p.candidates]


def test_supplied_by_others_does_not_buy_device(catalog):
    p = match_position(position(description="Kanaltemperaturfühler", category="Controls", quantity="6", unit="pc", scope_tags=["supplied_by_others"]), catalog)
    assert p.pricing_basis == "labour_only" and p.install_code == "CONTROL_POINT"
    assert p.product_id is None

def test_humidity_sensor_function_gap_is_partial_but_temperature_only_stays_strong(catalog):
    humidity = match_position(position(description="Kanaltemperatur- und Feuchtefühler", category="Controls", quantity="1", unit="pc", product_id="P-CTL-002"), catalog)
    assert humidity.match_evidence_band == "partial"
    assert humidity.status == "review_required"
    assert any(w.kind == "functional_gap" and "humidity" in w.detail for w in humidity.warnings)
    plain = match_position(position(description="Kanaltemperaturfühler", category="Controls", quantity="1", unit="pc", product_id="P-CTL-002"), catalog)
    assert plain.match_evidence_band == "strong"


def test_unknown_dimension_does_not_choose_arbitrary_reference(catalog):
    p = match_position(position(description="Zuluftventil", quantity="5", unit="pc"), catalog)
    assert p.product_id is None
    assert p.match_evidence_band == "partial"


def test_inferred_installation_unit_cannot_break_full_estimate(catalog):
    p = match_position(position(description="Einregulierung", quantity="21", unit="h"), catalog)
    assert p.install_code == "UNKNOWN" and not p.product_id
    assert any(w.kind == "installation_unit" for w in p.warnings)
    p = match_position(position(description="Zeigerthermometer für Kanaleinbau", quantity="4", unit="pc"), catalog)
    assert p.install_code is None and p.category == "Controls"
    p = match_position(position(description="Kanaldichtheitsprüfung mit Photodokumentation", quantity="2", unit="pc"), catalog)
    assert p.install_code is None and p.category == "Project services"


def test_explicit_selection_validates_the_selected_record(catalog):
    p = position(description="Zuluftventil DN100", quantity="5", unit="pc")
    selected = validate_explicit_reference(p, catalog, "P-AIR-002")
    assert selected.product_id == "P-AIR-002"
    assert selected.match_evidence_band == "conflicting"
    assert selected.technical_equivalence == "incompatible"
    with pytest.raises(ValueError, match="Unknown"):
        validate_explicit_reference(p, catalog, "invented")


def test_swiss_number_and_nonfinite_rejection():
    assert normalize_number("10’250,50") == "10250.50"
    with pytest.raises(ValueError):
        normalize_number("NaN")


def test_ai_rejects_fabricated_source_ids():
    output = AIExtraction(positions=[ExtractedPosition(anchor_source_id="invented", description="X", original_description="X", quantity=None, unit=None, raw_quantity=None, raw_unit=None, source_ids=["invented"], quantity_source_ids=[], attributes=[], category="unclassified", product_id=None, supplied_by_others=False, assumption=None)], requirements=[], issues=[], dispositions=[])
    with pytest.raises(ValueError, match="outside"):
        validate_ai_output(output, [], [], [])
