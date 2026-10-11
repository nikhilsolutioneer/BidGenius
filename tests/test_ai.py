"""Offline Responses adapter checks with real schema and evidence validation."""
from copy import deepcopy
import json
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from tenderproof import ai
from tenderproof.models import ExtractionBatch, Issue, PageRecord, Position, Requirement, SourceSpan


@pytest.fixture
def evidence(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "offline-test-placeholder")
    monkeypatch.delenv("OPENAI_REASONING_EFFORT", raising=False)
    # Exercise AI-only additions independently of deterministic row detection.
    monkeypatch.setattr(ai, "extract_local_batch", lambda *args: ExtractionBatch())
    span = SourceSpan(id="source-1", document_id="document", page=1,
        text="Zuluft Tellerventil DN100, confirmed quantity 5", x0=10, top=20, x1=400,
        bottom=35, page_width=595, page_height=842)
    pages = [PageRecord(page=1, width=595, height=842, text=span.text, system="LA01")]
    catalog = [{"product_id": "AIR-100", "description": "Supply air valve DN100", "unit": "pc",
        "category": "Air terminal", "install_code": "DIFFUSER", "supplier_quote_required": "false"}]
    return pages, [span], catalog


def output(**changes):
    position = dict(anchor_source_id="source-1", description="Zuluft Tellerventil DN100",
        original_description="This model string must not replace original evidence", quantity="5", unit="pc",
        raw_quantity="5", raw_unit="Stk", source_ids=["source-1"], quantity_source_ids=["source-1"],
        attributes=[], category="Air terminal", product_id="AIR-100", supplied_by_others=False, assumption=None)
    return ai.AIExtraction.model_validate({"positions": [{**position, **changes}],
        "requirements": [], "issues": [], "dispositions": [{"source_id": "source-1", "disposition": "position"}]})


def response(parsed, *, input_tokens=10, output_tokens=2, cached_tokens=1, reasoning_tokens=1):
    values = {"input_tokens": input_tokens, "output_tokens": output_tokens,
        "total_tokens": input_tokens + output_tokens, "input_tokens_details": {"cached_tokens": cached_tokens},
        "output_tokens_details": {"reasoning_tokens": reasoning_tokens}}
    return SimpleNamespace(output_parsed=parsed, usage=SimpleNamespace(model_dump=lambda: deepcopy(values)))


def install_client(monkeypatch, outcomes):
    calls, configurations = [], []

    class FakeClient:
        def __init__(self, **kwargs):
            configurations.append(kwargs)
            self.responses = SimpleNamespace(parse=self.parse)

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def parse(self, **kwargs):
            calls.append(deepcopy(kwargs))
            assert len(calls) <= len(outcomes), "Unexpected extra model request"
            result = outcomes[len(calls) - 1]
            if isinstance(result, Exception):
                raise result
            return result

    monkeypatch.setattr(ai, "AsyncOpenAI", FakeClient)
    return calls, configurations


async def test_success_uses_structured_stateless_request_and_configured_reasoning(evidence, monkeypatch):
    pages, spans, catalog = evidence
    monkeypatch.setenv("OPENAI_REASONING_EFFORT", "high")
    calls, configurations = install_client(monkeypatch, [response(output())])
    result = await ai.extract_ai_batch(pages, spans, catalog, "gpt-5")
    assert configurations == [{"max_retries": 2, "timeout": 120.0}]
    assert len(calls) == 1
    assert calls[0]["model"] == "gpt-5"
    assert calls[0]["text_format"] is ai.AIExtraction
    assert calls[0]["store"] is False
    assert calls[0]["reasoning"] == {"effort": "high"}
    assert calls[0]["max_output_tokens"] == 16000
    assert result.positions[0].quantity == "5"
    assert result.positions[0].product_id == "AIR-100"
    assert result.positions[0].original_description == spans[0].text
    assert result.usage["reasoning_effort"] == "high"
    assert result.usage["repair_attempts"] == 0


async def test_missing_values_stay_null_and_other_page_sources_are_not_sent(evidence, monkeypatch):
    pages, spans, catalog = evidence
    outside = spans[0].model_copy(update={"id": "outside-batch", "page": 2})
    calls, _ = install_client(monkeypatch, [response(output(quantity=None, unit=None, raw_quantity=None,
        raw_unit=None, quantity_source_ids=[], product_id=None))])
    result = await ai.extract_ai_batch(pages, [*spans, outside], catalog, "configured-model")
    assert result.positions[0].quantity is None
    assert result.positions[0].unit is None
    assert result.positions[0].raw_quantity is None
    payload = json.loads(calls[0]["input"][1]["content"])
    assert [item["id"] for item in payload["source_blocks"]] == ["source-1"]
    assert "reasoning" not in calls[0]


@pytest.mark.parametrize("changes, expected_error", [
    ({"anchor_source_id": "invented-source"}, "outside the provided batch"),
    ({"quantity_source_ids": []}, "missing required evidence"),
    ({"quantity": "99", "raw_quantity": "99"}, "unsupported by cited source"),
    ({"quantity": "5000", "raw_quantity": "5"}, "numeric conversion"),
    ({"product_id": "invented-product"}, "unknown catalogue ID"),
    ({"attributes": [{"key": "diameter_mm", "value": "100", "source_ids": ["invented-source"]}]}, "outside the provided batch"),
    ({"supplied_by_others": True}, "requires explicit evidence"),
])
async def test_invalid_evidence_or_catalogue_is_rejected_after_exactly_one_repair(evidence, monkeypatch, changes, expected_error):
    bad = response(output(**changes))
    calls, _ = install_client(monkeypatch, [bad, bad, response(output())])
    with pytest.raises(ValueError, match=expected_error) as caught:
        await ai.extract_ai_batch(*evidence, "configured-model")
    assert len(calls) == 2
    assert all(call["store"] is False for call in calls)
    assert len(calls[0]["input"]) == 2
    assert len(calls[1]["input"]) == 3
    assert "existing sources only" in calls[1]["input"][-1]["content"]
    if expected_error == "outside the provided batch":
        assert caught.value.code == "unknown_source_ids"
        assert "invented-source" in str(caught.value)
        assert "invented-source" in calls[1]["input"][-1]["content"]


async def test_repaired_evidence_sums_both_responses_usage(evidence, monkeypatch):
    calls, _ = install_client(monkeypatch, [
        response(output(quantity="99", raw_quantity="99"), input_tokens=10, output_tokens=2, cached_tokens=2),
        response(output(), input_tokens=20, output_tokens=4, cached_tokens=3, reasoning_tokens=2)])
    result = await ai.extract_ai_batch(*evidence, "configured-model")
    assert len(calls) == 2
    assert result.positions[0].quantity == "5"
    assert result.usage["repair_attempts"] == 1
    assert result.usage["input_tokens"] == 30
    assert result.usage["output_tokens"] == 6
    assert result.usage["total_tokens"] == 36
    assert result.usage["input_tokens_details"]["cached_tokens"] == 5
    assert result.usage["output_tokens_details"]["reasoning_tokens"] == 3
    assert result.usage["usage_unavailable_attempts"] == 0


async def test_pydantic_failure_inside_sdk_parse_gets_one_repair_and_discloses_unknown_usage(evidence, monkeypatch):
    with pytest.raises(ValidationError) as error:
        ai.AIExtraction.model_validate({"positions": "invalid-schema"})
    calls, _ = install_client(monkeypatch, [error.value, response(output(), input_tokens=20)])
    result = await ai.extract_ai_batch(*evidence, "configured-model")
    assert len(calls) == 2
    assert result.usage["repair_attempts"] == 1
    assert result.usage["input_tokens"] == 20
    assert result.usage["usage_unavailable_attempts"] == 1


async def test_repeated_schema_failure_is_bounded(evidence, monkeypatch):
    with pytest.raises(ValidationError) as error:
        ai.AIExtraction.model_validate({})
    calls, _ = install_client(monkeypatch, [error.value, error.value, response(output())])
    with pytest.raises(ValueError, match="after repair"):
        await ai.extract_ai_batch(*evidence, "configured-model")
    assert len(calls) == 2


async def test_missing_structured_output_gets_one_repair_and_counts_known_usage(evidence, monkeypatch):
    calls, _ = install_client(monkeypatch, [response(None), response(output())])
    result = await ai.extract_ai_batch(*evidence, "configured-model")
    assert len(calls) == 2
    assert result.usage["total_tokens"] == 24
    assert result.usage["usage_unavailable_attempts"] == 0


async def test_transport_failure_does_not_start_an_extra_validation_retry(evidence, monkeypatch):
    calls, _ = install_client(monkeypatch, [RuntimeError("Provider unavailable")])
    with pytest.raises(RuntimeError, match="Provider unavailable"):
        await ai.extract_ai_batch(*evidence, "configured-model")
    assert len(calls) == 1


async def test_missing_key_fails_before_client_creation(evidence, monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY")
    calls, configurations = install_client(monkeypatch, [])
    with pytest.raises(RuntimeError, match="not configured"):
        await ai.extract_ai_batch(*evidence, "configured-model")
    assert calls == configurations == []


async def test_ai_cannot_replace_quantity_already_grounded_by_local_parser(evidence, monkeypatch):
    pages, spans, _ = evidence
    local = Position(id="local-row", document_id="document", source_page=1, description=spans[0].text,
        quantity="5", unit="pc", source_span_ids=["source-1"])
    monkeypatch.setattr(ai, "extract_local_batch", lambda *args: ExtractionBatch(positions=[local.model_copy(deep=True)]))
    calls, _ = install_client(monkeypatch, [response(output(quantity="99", raw_quantity="99"))])
    result = await ai.extract_ai_batch(*evidence, "configured-model")
    assert len(calls) == 1
    assert len(result.positions) == 1
    assert result.positions[0].id == "local-row"
    assert result.positions[0].quantity == "5"


async def test_gpt4o_omits_reasoning_and_uses_supported_output_budget(evidence, monkeypatch):
    monkeypatch.setenv("OPENAI_REASONING_EFFORT", "high")
    calls, _ = install_client(monkeypatch, [response(output())])
    result = await ai.extract_ai_batch(*evidence, "gpt-4o")
    assert "reasoning" not in calls[0]
    assert "reasoning_effort" not in result.usage
    assert calls[0]["max_output_tokens"] == 16000


async def test_existing_parser_position_can_gain_validated_attributes_and_match(evidence, monkeypatch):
    pages, spans, catalog = evidence
    local = Position(id="stable-id", document_id="document", source_page=1,
        description="Valve", original_description="Valve", quantity="5", unit="pc",
        source_span_ids=["source-1"], install_code="DIFFUSER")
    monkeypatch.setattr(ai, "extract_local_batch", lambda *args: ExtractionBatch(positions=[local.model_copy(deep=True)]))
    calls, _ = install_client(monkeypatch, [response(output(attributes=[
        {"key": "diameter_mm", "value": "100", "source_ids": ["source-1"]}]))])
    result = await ai.extract_ai_batch(*evidence, "gpt-4o")
    position = result.positions[0]
    assert len(result.positions) == 1
    assert position.id == "stable-id"
    assert position.quantity == "5"
    assert position.product_id is None
    assert position.attributes["diameter_mm"] == "100"
    assert position.attributes["ai_refinement_proposals"][0]["state"] == "pending"
    assert position.attributes["ai_refinement_proposals"][0]["changes"]["product_id"] == "AIR-100"
    payload = json.loads(calls[0]["input"][1]["content"])
    assert payload["existing_positions"][0]["id"] == "stable-id"


async def test_fabricated_numeric_attribute_cannot_improve_matching(evidence, monkeypatch):
    bad = response(output(attributes=[{"key": "diameter_mm", "value": "999", "source_ids": ["source-1"]}]))
    calls, _ = install_client(monkeypatch, [bad, bad])
    with pytest.raises(ValueError, match="Technical attribute is unsupported"):
        await ai.extract_ai_batch(*evidence, "gpt-4o")
    assert len(calls) == 2


async def test_failed_validation_preserves_received_token_usage(evidence, monkeypatch):
    install_client(monkeypatch, [response(output(quantity="99", raw_quantity="99")),
                                response(output(quantity="99", raw_quantity="99"))])
    with pytest.raises(ValueError) as error:
        await ai.extract_ai_batch(*evidence, "gpt-4o")
    assert error.value.usage["total_tokens"] == 24
    assert error.value.usage["repair_attempts"] == 1


def review_request(**changes):
    return {"pages": [1], "target_source_ids": ["source-1"], "position_ids": ["local-row"],
            "context_source_ids": ["context"], "reasons": [{"kind": "missing_quantity", "field": "quantity",
                "detail": "Local extraction could not identify the quantity", "position_ids": ["local-row"],
                "source_span_ids": ["source-1"]}], **changes}


async def test_targeted_review_sends_only_gap_with_context_and_current_baseline(evidence, monkeypatch):
    pages, spans, catalog = evidence
    context = spans[0].model_copy(update={"id": "context", "text": "Supply air section"})
    irrelevant = spans[0].model_copy(update={"id": "irrelevant", "text": "An unrelated completed row"})
    gap = Position(id="local-row", document_id="document", source_page=1, description="Already reviewed text",
                   original_description="Saved source evidence", category="Air terminal", system="LA01",
                   unit="pc", source_span_ids=["source-1"], field_sources={"quantity": ["source-1"]})
    clean = gap.model_copy(update={"id": "clean-row", "quantity": "8", "source_span_ids": ["irrelevant"],
                                   "review_state": "accepted", "origin": "manual"}, deep=True)
    requirement = Requirement(id="local-requirement", title="Retained obligation", description="Original text",
                              source_page=1, source_span_ids=["irrelevant"])
    baseline = ExtractionBatch(positions=[gap, clean], requirements=[requirement], dispositions={"irrelevant": "position"})
    before = baseline.model_dump()

    def do_not_reparse(*args):
        pytest.fail("Targeted review must use saved local findings, not reparse partial source context")

    monkeypatch.setattr(ai, "extract_local_batch", do_not_reparse)
    calls, _ = install_client(monkeypatch, [response(output(product_id=None))])
    result = await ai.extract_ai_batch(pages, [*spans, context, irrelevant], catalog, "configured-model",
                                       local_batch=baseline, review=review_request())
    payload = json.loads(calls[0]["input"][1]["content"])
    assert payload["review"]["reasons"][0]["field"] == "quantity"
    assert [(block["id"], block["role"]) for block in payload["source_blocks"]] == [
        ("source-1", "target"), ("context", "context")]
    assert [position["id"] for position in payload["existing_positions"]] == ["local-row"]
    assert payload["existing_positions"][0]["description"] == "Already reviewed text"
    assert payload["existing_positions"][0]["original_description"] == "Saved source evidence"
    assert result.positions[0].quantity is None  # Financial changes remain review proposals.
    assert result.positions[0].attributes["ai_refinement_proposals"][0]["changes"]["quantity"] == "5"
    assert result.positions[1].model_dump() == clean.model_dump()
    assert result.requirements == [requirement]
    assert baseline.model_dump() == before
    assert result.usage["mode"] == "ai_targeted_review"


@pytest.mark.parametrize("section", ["positions", "requirements", "issues", "dispositions"])
def test_review_output_cannot_turn_context_into_new_work(evidence, section):
    pages, spans, catalog = evidence
    context = spans[0].model_copy(update={"id": "context"})
    data = {"positions": [], "requirements": [], "issues": [], "dispositions": []}
    if section == "positions":
        data[section] = [output(anchor_source_id="context", source_ids=["context"], quantity_source_ids=["context"]).positions[0].model_dump()]
    elif section == "requirements":
        data[section] = [{"title": "Unexpected scope", "description": "Context only", "category": "scope", "source_ids": ["context"]}]
    elif section == "issues":
        data[section] = [{"title": "Unexpected issue", "detail": "Context only", "kind": "missing_scope",
                          "severity": "warning", "source_ids": ["context"], "action": "Review"}]
    else:
        data[section] = [{"source_id": "context", "disposition": "position"}]
    with pytest.raises(ai.AIOutputValidationError, match="targeted source"):
        ai.validate_ai_output(ai.AIExtraction.model_validate(data), pages, [*spans, context], catalog,
                              local_batch=ExtractionBatch(), review=review_request(position_ids=[]))


@pytest.mark.parametrize("protection", [{"origin": "manual"}, {"review_state": "accepted"},
                                        {"status": "out_of_scope"}, {"status": "non_priceable"}])
def test_review_cannot_change_protected_saved_rows_even_if_requested(evidence, protection):
    pages, spans, catalog = evidence
    original = Position(id="local-row", document_id="document", source_page=1,
                        description="Saved position", quantity="5", unit="pc", source_span_ids=["source-1"], **protection)
    with pytest.raises(ai.AIOutputValidationError, match="cannot change"):
        ai.validate_ai_output(output(), pages, spans, catalog, local_batch=ExtractionBatch(positions=[original]),
                              review=review_request(context_source_ids=[]))


def test_review_can_add_an_overlooked_position_once_with_grounded_evidence(evidence):
    pages, spans, catalog = evidence
    review = review_request(position_ids=[], context_source_ids=[])
    result = ai.validate_ai_output(output(), pages, spans, catalog, local_batch=ExtractionBatch(), review=review)
    assert len(result.positions) == 1
    assert result.positions[0].quantity == "5"
    assert result.positions[0].original_description == spans[0].text
    duplicate = output()
    duplicate.positions.append(duplicate.positions[0].model_copy(deep=True))
    with pytest.raises(ai.AIOutputValidationError, match="duplicate positions"):
        ai.validate_ai_output(duplicate, pages, spans, catalog, local_batch=ExtractionBatch(), review=review)


def test_review_resolves_shared_headings_using_the_targeted_position(evidence):
    pages, spans, catalog = evidence
    shared = spans[0].model_copy(update={"id": "shared-heading", "text": "Supply air valves"})
    other = spans[0].model_copy(update={"id": "other-row", "text": "Another valve Stk 8"})
    targeted = Position(id="local-row", document_id="document", source_page=1, description="Target",
                        unit="pc", source_span_ids=["shared-heading", "source-1"], field_sources={"quantity": ["source-1"]})
    complete = targeted.model_copy(update={"id": "complete", "source_span_ids": ["shared-heading", "other-row"],
                                           "field_sources": {"quantity": ["other-row"]}, "quantity": "8"}, deep=True)
    result = ai.validate_ai_output(output(), pages, [*spans, shared, other], catalog,
                                  local_batch=ExtractionBatch(positions=[targeted, complete]),
                                  review=review_request(context_source_ids=["shared-heading"]))
    assert result.positions[0].id == targeted.id
    assert result.positions[1].model_dump() == complete.model_dump()


def test_missing_unit_and_system_are_proposed_only_from_source_evidence(evidence):
    pages, spans, catalog = evidence
    spans[0].text += "; Stk; system LA02"
    original = Position(id="local-row", document_id="document", source_page=1, description="Valve",
                        quantity="5", source_span_ids=["source-1"])
    result = ai.validate_ai_output(output(system="LA02"), pages, spans, catalog,
                                  local_batch=ExtractionBatch(positions=[original]), review=review_request(context_source_ids=[]))
    proposed = result.positions[0].attributes["ai_refinement_proposals"][0]["changes"]
    assert proposed["unit"] == "pc"
    assert proposed["system"] == "LA02"
    assert result.positions[0].quantity == "5"
    assert result.positions[0].unit is None
    assert result.positions[0].system == "Unassigned"
    assert result.positions[0].category == original.category
    assert result.positions[0].install_code == original.install_code
    assert result.positions[0].pricing_basis == original.pricing_basis


async def test_review_payload_does_not_expose_unsupplied_evidence_ids_or_prior_proposals(evidence, monkeypatch):
    original = Position(id="local-row", document_id="document", source_page=1, description="Multi-page package",
                        source_span_ids=["source-1", "outside-page"],
                        field_sources={"quantity": ["source-1"], "specification_pages": ["outside-page"]},
                        attributes={"diameter_mm": "100", "ai_refinement_proposals": [{"id": "old", "state": "pending", "source_span_ids": ["old-source"]}],
                                    "pricing_proposals": [{"id": "price", "source_span_ids": ["price-source"]}]},
                        warnings=[Issue(id="conflict", kind="technical_conflict", title="Conflict", detail="Conflicting evidence",
                                        source_span_ids=["source-1", "outside-page"])])
    baseline = ExtractionBatch(positions=[original])
    calls, _ = install_client(monkeypatch, [response(ai.AIExtraction(positions=[], requirements=[], issues=[], dispositions=[]))])
    result = await ai.extract_ai_batch(*evidence, "configured-model", local_batch=baseline,
                                       review=review_request(context_source_ids=[]))
    payload = json.loads(calls[0]["input"][1]["content"])["existing_positions"][0]
    assert payload["source_span_ids"] == ["source-1"]
    assert payload["field_sources"]["specification_pages"] == []
    assert payload["warnings"][0]["source_span_ids"] == ["source-1"]
    assert payload["source_context_truncated"] is True
    assert payload["attributes"] == {"diameter_mm": "100"}
    assert result.positions == baseline.positions
    assert original.source_span_ids == ["source-1", "outside-page"]
