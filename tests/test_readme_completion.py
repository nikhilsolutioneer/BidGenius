"""Focused verification for the newly covered README workflows."""
from copy import deepcopy
from decimal import Decimal

from tenderproof.models import PageRecord, Position, SourceSpan
from test_api import api as project_api  # noqa: F401 - shared isolated project fixture


def test_rectangular_duct_proxy_requires_approval_and_is_priced_as_assumption(project_api):
    client, app, project_id, _ = project_api
    project = app.state.repo.project(project_id)
    document_id = project["document"]["id"]
    span = SourceSpan(id=f"{document_id}-duct-row", document_id=document_id, page=2,
        text="Luftleitung 150 500 3938 mm", x0=30, top=100, x1=500, bottom=120,
        page_width=595, page_height=842, disposition="position")
    page = PageRecord(page=2, width=595, height=842, text=span.text, system="LA01", status="processed")
    app.state.repo.save_parsed(document_id, [page.model_dump()], [span.model_dump()])
    position = Position(id="duct-test", document_id=document_id, system="LA01", category="Ductwork",
        description="Rectangular ventilation duct 150 x 500 mm", original_description=span.text,
        quantity="5.1194", unit="m2", source_page=2, source_span_ids=[span.id],
        field_sources={"quantity": [span.id]}, attributes={"width_mm": "150", "height_mm": "500"},
        install_code="DUCT_RECT")
    def add(project):
        project["positions"].append(position.model_dump(mode="json"))
        app.state.service.recalculate(project)
    app.state.repo.update_project(project_id, add)

    response = client.get(f"/api/projects/{project_id}/positions")
    assert response.status_code == 200
    duct = next(item for item in response.json()["items"] if item["id"] == "duct-test")
    proposals = duct["attributes"]["pricing_proposals"]
    assert proposals and all(p["review_state"] == "pending" for p in proposals)
    chosen = proposals[0]
    assert any("dimensional equivalence" in x.lower() for x in chosen["differences"])
    assert duct["cost"]["direct_cost_chf"] is None
    before = app.state.service.summary(project_id)["totals"]["cost_baseline_chf"]

    approved = client.patch("/api/positions/duct-test", json={"expected_revision": 1,
        "reason": "Use catalogue area rate as an explicit pricing proxy pending technical confirmation",
        "changes": {"pricing_proposal": {"id": chosen["id"], "review_state": "accepted"}}})
    assert approved.status_code == 200, approved.text
    after = app.state.service.summary(project_id)["totals"]["cost_baseline_chf"]
    updated = next(item for item in client.get(f"/api/projects/{project_id}/positions").json()["items"] if item["id"] == "duct-test")
    assert Decimal(after) > Decimal(before)
    assert updated["technical_equivalence"] == "unverified"
    assert updated["pricing_basis"] == "manual_assumption"
    assert updated["cost"]["direct_cost_chf"] is not None
    assert updated["lv_id"] == updated["id"]
    stale = client.patch("/api/positions/duct-test", json={"expected_revision": 1,
        "reason": "Stale decision", "changes": {"pricing_proposal": {"id": chosen["id"], "review_state": "rejected"}}})
    assert stale.status_code == 409

    def add_ai_proposal(project):
        row = next(item for item in project["positions"] if item["id"] == "duct-test")
        row["attributes"]["ai_refinement_proposals"] = [{"id": "AI-PRODUCT-1",
            "changes": {"product_id": "P-DCT-X-200x200"}, "source_span_ids": [span.id],
            "state": "pending", "rationale": "A source-backed pricing candidate."}]
    app.state.repo.update_project(project_id, add_ai_proposal)
    ai_choice = client.patch("/api/positions/duct-test", json={"expected_revision": 2,
        "reason": "Review the alternative catalogue pricing reference", "changes": {
            "ai_refinement_proposal": {"id": "AI-PRODUCT-1", "review_state": "accepted"}}})
    assert ai_choice.status_code == 200, ai_choice.text
    chosen_position = next(item for item in client.get(f"/api/projects/{project_id}/positions").json()["items"] if item["id"] == "duct-test")
    assert chosen_position["product_id"] == "P-DCT-X-200x200"
    assert chosen_position["technical_equivalence"] == "incompatible"
    assert chosen_position["status"] == "review_required"
    undone_ai = client.post(f"/api/projects/{project_id}/undo/{ai_choice.json()['decision_id']}", json={
        "expected_revision": 3, "reason": "Keep the current pricing reference without technical substitution"})
    assert undone_ai.status_code == 200, undone_ai.text
    capacity = client.patch(f"/api/projects/{project_id}/commercial-context", json={"expected_revision": 4,
        "reason": "Record estimator capacity review", "changes": {"capacity": {
            "period_start": "2026-10-01", "period_end": "2026-10-31", "available_hours": "100", "committed_hours": "20"}}})
    assert capacity.status_code == 200, capacity.text
    undone_capacity = client.post(f"/api/projects/{project_id}/undo/{capacity.json()['decision_id']}", json={
        "expected_revision": 5, "reason": "Reverse isolated capacity test input"})
    assert undone_capacity.status_code == 200, undone_capacity.text
    undone_proxy = client.post(f"/api/projects/{project_id}/undo/{approved.json()['decision_id']}", json={
        "expected_revision": 6, "reason": "Reverse proxy approval after its later review was undone"})
    assert undone_proxy.status_code == 200, undone_proxy.text
    final_position = next(item for item in client.get(f"/api/projects/{project_id}/positions").json()["items"] if item["id"] == "duct-test")
    assert final_position["cost"]["direct_cost_chf"] is None


def test_readme_holdout_is_frozen_and_stratified():
    import json
    from pathlib import Path
    fixture = json.loads((Path(__file__).parent / "fixtures" / "readme_holdout.json").read_text(encoding="utf-8"))
    assert len(fixture["rows"]) >= 80
    systems = {r["system"] for r in fixture["rows"]}
    assert {"LA01", "LA02", "LA03", "LA04", "LA05", "ROOF"} <= systems
    assert "not statistical completeness proof" in fixture["limitations"].lower()
