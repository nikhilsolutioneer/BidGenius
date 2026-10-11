"""Selection is driven by extraction evidence, not general pricing uncertainty."""
from tenderproof.ai_review import build_review_batches
from tenderproof.models import Issue, PageRecord, Position, SourceSpan


def page(number=1, system="LA01"):
    return PageRecord(page=number, width=595, height=842, text="Tender schedule", system=system)


def span(identifier="quantity", number=1, **changes):
    return SourceSpan(id=identifier, document_id="doc", page=number, text="Tellerventil Stk",
                      x0=20, top=100, x1=400, bottom=110, page_width=595, page_height=842,
                      kind="quantity", disposition="position").model_copy(update=changes)


def position(identifier="position", source="quantity", number=1, **changes):
    return Position(id=identifier, document_id="doc", source_page=number, system="LA01",
                    description="Tellerventil", category="Air terminal", quantity="5", unit="pc",
                    source_span_ids=[source], field_sources={"quantity": [source]},
                    status="supplier_quote_required").model_copy(update=changes)


def test_missing_price_catalogue_and_descriptive_context_do_not_trigger_ai():
    clean = position(product_id=None, match_evidence_band="conflicting")
    sources = [span(), span("notes", kind="text", disposition="context"),
               span("heading", kind="heading", disposition="unresolved"),
               span("footer", kind="boilerplate", disposition="unresolved")]
    assert build_review_batches([page()], sources, [clean], []) == []


def test_missing_fields_and_uncovered_candidates_receive_explicit_reasons_and_context():
    sources = [span("heading", kind="heading", disposition="context", top=70),
               span("description", kind="text", disposition="context", top=80), span(),
               span("unhandled", top=130, text="Bespoke grille 2 Stk", disposition="unresolved"),
               span("unrelated", number=2, disposition="context")]
    missing = position(quantity=None, unit=None, category="unclassified", system="Unassigned")
    batches = build_review_batches([page(), page(2)], sources, [missing], [])
    assert len(batches) == 1
    batch = batches[0]
    assert batch["pages"] == [1]
    assert batch["target_source_ids"] == ["quantity", "unhandled"]
    assert batch["position_ids"] == [missing.id]
    assert {reason["kind"] for reason in batch["reasons"]} == {
        "missing_quantity", "missing_unit", "missing_category", "missing_system", "unresolved_source"}
    assert set(batch["context_source_ids"]) == {"heading", "description"}
    assert "unrelated" not in str(batch)


def test_manual_reviewed_excluded_and_allowance_rows_are_preserved():
    adjustments = [{"origin": "manual"}, {"review_state": "accepted"}, {"review_state": "rejected"},
                   {"status": "out_of_scope"}, {"status": "non_priceable"},
                   {"pricing_basis": "included_elsewhere"}, {"included_in": "project:commissioning"}]
    positions = [position(str(index), str(index), quantity=None, **changes) for index, changes in enumerate(adjustments)]
    sources = [span(str(index), disposition="unresolved") for index in range(len(positions))]
    assert build_review_batches([page()], sources, positions, []) == []


def test_source_conflict_includes_both_claims_but_catalogue_gap_does_not_trigger_review():
    missing = position()
    sources = [span(), span("header", kind="boilerplate", disposition="boilerplate", text="LA01", top=10),
               span("footer", kind="boilerplate", disposition="boilerplate", text="LA02", top=800)]
    conflict = Issue(id="conflict", kind="system_conflict", title="System conflict",
                     detail="Header says LA01; footer says LA02", source_span_ids=["header", "footer"])
    batch = build_review_batches([page()], sources, [missing], [conflict])[0]
    assert batch["target_source_ids"] == ["quantity"]
    assert set(batch["context_source_ids"]) == {"header", "footer"}
    assert batch["reasons"][0]["detail"] == conflict.detail
    conflict.kind = "match_conflict"
    assert build_review_batches([page()], sources, [missing], [conflict]) == []


def test_batches_have_at_most_four_pages_and_never_cross_system_sections():
    pages = [page(index, "LA01" if index <= 5 else "LA02") for index in range(1, 8)]
    sources = [span(str(item.page), number=item.page, disposition="unresolved") for item in pages]
    batches = build_review_batches(pages, sources, [], [])
    assert [batch["pages"] for batch in batches] == [[1, 2, 3, 4], [5], [6, 7]]


def test_page_without_readable_evidence_is_left_for_ocr_or_manual_review():
    unreadable = page().model_copy(update={"text": "", "status": "needs_ocr"})
    issue = Issue(id="ocr", kind="page_extraction", title="OCR needed", detail="No extractable text")
    assert build_review_batches([unreadable], [span(text="", disposition="unresolved")], [], [issue]) == []


def test_accepted_conflicts_do_not_reopen_a_complete_position():
    conflict = Issue(id="conflict", kind="dimension_conflict", title="Length conflict", detail="100 / 200",
                     position_ids=["position"], source_span_ids=["quantity"], review_state="accepted")
    assert build_review_batches([page()], [span()], [position(warnings=[conflict])], [conflict]) == []
