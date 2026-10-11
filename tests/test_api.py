"""Transactional estimator API regression checks using isolated SQLite stores."""
from decimal import Decimal
from copy import deepcopy
from io import BytesIO
import json
from pathlib import Path
from zipfile import ZipFile

from fastapi.testclient import TestClient
import pytest

from tenderproof.main import create_app
from tenderproof.models import PageRecord, Position, Requirement, SourceSpan
from tenderproof.service import position_needs_human_review

PACKAGE = Path(__file__).resolve().parents[1] / "Schulhaus_Oberglatt_Hackathon_Starter_Package_v2"


@pytest.fixture
def api(tmp_path):
    app = create_app(tmp_path)
    with TestClient(app) as client:
        service, repo = app.state.service, app.state.repo
        project = service.create_project(PACKAGE)
        document = project["document"]["id"]
        spans = [SourceSpan(id=f"{document}-{index}", document_id=document, page=1,
            text="Zuluft - Tellerventil DN100 Stk 5" if index == 1 else "Zuluft - Tellerventil DN100 Stk 2",
            x0=50, top=100 * index, x1=400, bottom=100 * index + 15,
            page_width=595, page_height=842, disposition="position") for index in (1, 2)]
        page = PageRecord(page=1, width=595, height=842, text="Test source rows", system="LA01", status="processed")
        repo.save_parsed(document, [page.model_dump()], [s.model_dump() for s in spans])
        p = Position(id="test-position", document_id=document, system="LA01", category="Air terminal",
            description="Zuluft - Tellerventil DN100", original_description=spans[0].text,
            quantity="5", raw_quantity="5", unit="pc", raw_unit="Stk", source_page=1,
            source_span_ids=[spans[0].id], field_sources={"quantity": [spans[0].id]},
            product_id="P-AIR-001", install_code="DIFFUSER", match_evidence_band="strong")
        def seed(value):
            value["document"]["page_count"] = 1
            value["positions"] = [p.model_dump()]
            service.recalculate(value)
            value["revision"] = 1
            value["document_processing"] = service.document_progress(value)
        repo.update_project(project["id"], seed, snapshot=True)
        yield client, app, project["id"], spans


def summary(client, project):
    result = client.get(f"/api/projects/{project}/summary")
    assert result.status_code == 200, result.text
    return result.json()


def edit(client, revision, changes, reason="Estimator confirmed source quantity"):
    return client.patch("/api/positions/test-position", json={"expected_revision": revision, "reason": reason, "changes": changes})


def create_risk(client, project, revision=1, **extra):
    body = {"expected_revision": revision, "reason": "Review additional site access cost", "kind": "risk",
        "title": "Restricted site access", "amount_chf": "1000", "scope": "LA01",
        "basis": "Additional crane mobilisation beyond the original plan"}
    return client.post(f"/api/projects/{project}/adjustments", json={**body, **extra})


def test_pending_review_queue_only_counts_actionable_position_decisions():
    base = {"review_state": "pending", "status": "calculated", "attributes": {}}
    assert position_needs_human_review(base) is False
    assert position_needs_human_review({**base, "status": "insufficient_information"}) is False
    assert position_needs_human_review({**base, "status": "review_required"}) is True
    assert position_needs_human_review({**base, "status": "assumption_applied"}) is True
    assert position_needs_human_review({**base, "status": "supplier_quote_required"}) is True
    assert position_needs_human_review({**base, "review_state": "accepted", "status": "review_required"}) is False
    assert position_needs_human_review({**base, "status": "out_of_scope"}) is False
    assert position_needs_human_review({
        **base,
        "attributes": {"pricing_proposals": [{"id": "proxy", "review_state": "pending"}]},
    }) is True


def test_pinned_demo_manifest_points_to_existing_project_and_timestamp(api, monkeypatch):
    import tenderproof.main as main_module

    client, app, project, _ = api
    root = app.state.repo.directory
    monkeypatch.setattr(main_module, "ROOT", root)
    manifest = root / "artifacts" / "prepared-demo.json"
    manifest.parent.mkdir(parents=True)
    prepared_at = "2026-10-10T12:30:00Z"
    manifest.write_text(json.dumps({"project_id": project, "prepared_at": prepared_at}), encoding="utf-8")

    pinned = client.get("/api/pinned-demo")
    assert pinned.status_code == 200
    assert pinned.json() == {"project_id": project, "prepared_at": prepared_at,
        "project_name": app.state.repo.project(project)["name"]}


def test_stale_update_is_atomic_and_original_evidence_is_unchanged(api):
    client, app, project, spans = api
    before = summary(client, project)
    changed = edit(client, 1, {"quantity": "10"})
    assert changed.status_code == 200, changed.text
    assert changed.json()["revision"] == 2
    assert Decimal(changed.json()["cost_delta_chf"]) > 0
    stale = edit(client, 1, {"quantity": "999"})
    assert stale.status_code == 409
    after = summary(client, project)
    assert after["revision"] == 2
    assert len(after["history"]) == 1
    position = client.get(f"/api/projects/{project}/positions").json()["items"][0]
    assert position["quantity"] == "10"
    assert position["raw_quantity"] == "5"
    assert client.get(f"/api/sources/{spans[0].id}").json()["text"] == spans[0].text
    assert app.state.repo.revision(project, 1)["estimate"]["totals"] == before["totals"]


def test_what_if_preview_is_read_only_apply_matches_and_stale_preview_conflicts(api):
    client, app, project, _ = api
    def remove_legacy_missing_role_rates(value):
        value["parameters"].pop("labour_rates_chf_per_h", None)

    app.state.repo.update_project(project, remove_legacy_missing_role_rates, expected_revision=1)
    before_summary = summary(client, project)
    before_project = app.state.repo.project(project)
    assert "labour_rates_chf_per_h" not in before_project["parameters"]
    assert before_summary["parameters"]["labour_rates_chf_per_h"]["installer"] == "96"
    changes = {
        "productivity_factors": {
            "site_efficiency": "0.90", "mounting_height_school": "1.12",
            "mounting_height_sports_hall": "1.30", "school_logistics": "1.10",
            "timber_interface": "1.09",
        },
        "allowances": {"material_waste_pct": "5.0"},
        "commercial": {"overhead_pct": "9.0", "target_margin_pct": "6.0"},
        "labour_rates_chf_per_h": {"installer": "100"},
    }
    preview_response = client.post(f"/api/projects/{project}/what-if/preview", json={
        "expected_revision": 1, "changes": changes, "include_positions": True,
    })
    assert preview_response.status_code == 200, preview_response.text
    preview = preview_response.json()
    after_preview = app.state.repo.project(project)
    assert after_preview["revision"] == before_project["revision"] == 1
    assert after_preview["parameters"] == before_project["parameters"]
    assert after_preview["history"] == before_project["history"]
    assert after_preview["estimate"] == before_project["estimate"]
    assert preview["current"]["baseline_chf"] == before_summary["totals"]["cost_baseline_chf"]
    assert preview["deltas"]["hours"] != "0"
    assert preview["top_positions"][0]["id"] == "test-position"
    assert preview["affected_positions"][0]["id"] == "test-position"
    assert preview["top_systems"][0]["system"] == "LA01"

    applied = client.patch(f"/api/projects/{project}/assumptions", json={
        "expected_revision": 1, "reason": "Review the What-if scenario against the tender plan", "changes": changes,
    })
    assert applied.status_code == 200, applied.text
    assert applied.json()["revision"] == 2
    after_apply = summary(client, project)
    assert after_apply["revision"] == 2
    assert len(after_apply["history"]) == len(before_summary["history"]) + 1
    assert after_apply["totals"]["material_cost_chf"] == preview["proposed"]["material_chf"]
    assert after_apply["totals"]["labour_cost_chf"] == preview["proposed"]["labour_chf"]
    assert after_apply["totals"]["cost_baseline_chf"] == preview["proposed"]["baseline_chf"]
    assert after_apply["totals"]["selling_price_chf"] == preview["proposed"]["selling_price_chf"]
    assert after_apply["scenarios"]["scenarios"] == preview["proposed"]["scenarios"]

    stale = client.post(f"/api/projects/{project}/what-if/preview", json={
        "expected_revision": 1, "changes": changes,
    })
    assert stale.status_code == 409


def test_sensitivity_is_sorted_read_only_and_directional(api):
    client, app, project, _ = api
    before_revision = app.state.repo.project(project)["revision"]
    response = client.post(f"/api/projects/{project}/sensitivity", json={"revision": before_revision})
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["revision"] == before_revision
    assert app.state.repo.project(project)["revision"] == before_revision
    assert payload["items"]
    magnitudes = [
        max(abs(Decimal(item["down_delta_chf"])), abs(Decimal(item["up_delta_chf"])))
        for item in payload["items"]
    ]
    assert magnitudes == sorted(magnitudes, reverse=True)
    assert any(Decimal(item["down_delta_chf"]) * Decimal(item["up_delta_chf"]) <= 0 for item in payload["items"])


def test_what_if_preview_completes_under_one_second_with_715_positions(api):
    client, app, project, _ = api

    def seed_benchmark_rows(value):
        # Repeat a source-backed row in this isolated test store for a 715-row timing check.
        source = deepcopy(value["positions"][0])
        value["positions"] = [source]
        for index in range(1, 715):
            row = deepcopy(source)
            row["id"] = f"what-if-perf-{index:04d}"
            row["lv_id"] = row["id"]
            row["reference"] = f"LA01 · p.1 · #{index + 1}"
            value["positions"].append(row)

    app.state.repo.update_project(project, seed_benchmark_rows, expected_revision=1)
    response = client.post(f"/api/projects/{project}/what-if/preview", json={
        "expected_revision": 1,
        "changes": {"productivity_factors": {"site_efficiency": "0.90"}},
    })
    assert response.status_code == 200, response.text
    result = response.json()
    assert len(app.state.repo.project(project)["positions"]) == 715
    assert result["elapsed_ms"] < 1000


def test_manual_position_duplicate_acknowledgement_and_repricing(api):
    client, _, project, spans = api
    initial = summary(client, project)
    body = {"expected_revision": 1, "reason": "Intentional separate installation scope", "description": "Supply air valve DN100",
        "system": "LA01", "category": "Air terminal", "quantity": "2", "unit": "pc", "product_id": "P-AIR-001",
        "source_span_ids": [spans[0].id]}
    duplicate = client.post(f"/api/projects/{project}/positions", json=body)
    assert duplicate.status_code == 409
    assert duplicate.json()["detail"]["duplicates"][0]["id"] == "test-position"
    assert summary(client, project)["revision"] == 1
    added = client.post(f"/api/projects/{project}/positions", json={**body, "acknowledge_duplicate": True})
    assert added.status_code == 201, added.text
    p = added.json()["position"]
    assert p["origin"] == "manual"
    assert p["source_span_ids"] == [spans[0].id]
    assert p["cost"]["direct_cost_chf"] is not None
    assert p["review_state"] == "pending"
    after = summary(client, project)
    assert after["coverage"]["positions_manual"] == 1
    assert Decimal(after["totals"]["cost_baseline_chf"]) > Decimal(initial["totals"]["cost_baseline_chf"])


def test_pending_approved_and_edited_adjustment_have_distinct_financial_effects(api):
    client, _, project, _ = api
    baseline = Decimal(summary(client, project)["totals"]["cost_baseline_chf"])
    created = create_risk(client, project)
    assert created.status_code == 201, created.text
    adjustment_id = created.json()["adjustment"]["id"]
    pending = summary(client, project)
    assert pending["totals"]["cost_baseline_chf"] == str(baseline)
    assert pending["totals"]["pending_adjustment_delta_chf"] == "1000.00"
    accepted = client.patch(f"/api/adjustments/{adjustment_id}", json={"expected_revision": 2,
        "reason": "Additional scope verified", "changes": {"review_state": "accepted"}})
    assert accepted.status_code == 200, accepted.text
    assert Decimal(summary(client, project)["totals"]["cost_baseline_chf"]) == baseline + Decimal("1085")
    edited = client.patch(f"/api/adjustments/{adjustment_id}", json={"expected_revision": 3,
        "reason": "Revised estimate requires fresh approval", "changes": {"amount_chf": "1500", "review_state": "accepted"}})
    assert edited.status_code == 200, edited.text
    assert edited.json()["adjustment"]["review_state"] == "pending"
    assert Decimal(summary(client, project)["totals"]["cost_baseline_chf"]) == baseline


def test_impossible_opportunity_rolls_back_transaction(api):
    client, _, project, _ = api
    created = create_risk(client, project, kind="opportunity", amount_chf="99999999")
    assert created.status_code == 201
    item = created.json()["adjustment"]
    before = summary(client, project)
    accepted = client.patch(f"/api/adjustments/{item['id']}", json={"expected_revision": 2,
        "reason": "Attempt invalid cost reduction", "changes": {"review_state": "accepted"}})
    assert accepted.status_code == 422
    after = summary(client, project)
    assert after["revision"] == before["revision"]
    assert after["totals"] == before["totals"]
    assert after["adjustments"][0]["review_state"] == "pending"


def test_allowance_overlap_cannot_be_approved_silently(api):
    client, _, project, _ = api
    created = create_risk(client, project, title="Supplier contingency", scope="supplier_contingency")
    assert created.status_code == 201
    item = created.json()["adjustment"]
    accepted = client.patch(f"/api/adjustments/{item['id']}", json={"expected_revision": 2,
        "reason": "Approve duplicated contingency", "changes": {"review_state": "accepted"}})
    assert accepted.status_code == 422
    assert summary(client, project)["revision"] == 2


def test_allowance_overlap_resolution_can_be_approved_but_edits_reopen_review(api):
    client, _, project, _ = api
    baseline = summary(client, project)["totals"]["cost_baseline_chf"]
    created = create_risk(client, project, title="Supplier contingency", scope="supplier_contingency")
    assert created.status_code == 201
    endpoint = f"/api/adjustments/{created.json()['adjustment']['id']}"
    resolved = client.patch(endpoint, json={"expected_revision": 2,
        "reason": "Document the separate scope beyond the standard allowance", "changes": {
            "overlap_resolution": "Specific crane permit risk; supplier package uncertainty remains in the standard allowance",
            "review_state": "accepted"}})
    assert resolved.status_code == 200, resolved.text
    assert resolved.json()["adjustment"]["review_state"] == "pending"
    accepted = client.patch(endpoint, json={"expected_revision": 3,
        "reason": "The separated additional cost basis has been reviewed", "changes": {"review_state": "accepted"}})
    assert accepted.status_code == 200, accepted.text
    assert Decimal(summary(client, project)["totals"]["cost_baseline_chf"]) > Decimal(baseline)
    edited = client.patch(endpoint, json={"expected_revision": 4,
        "reason": "Revised overlap basis needs another estimator decision", "changes": {
            "overlap_resolution": "Revised crane permit and road closure scope", "review_state": "accepted"}})
    assert edited.status_code == 200, edited.text
    assert edited.json()["adjustment"]["review_state"] == "pending"
    assert summary(client, project)["totals"]["cost_baseline_chf"] == baseline


@pytest.mark.parametrize("archive_name", ["../escape.txt", "nested/../../escape.txt", "C:/escape.txt", "nested\\..\\..\\escape.txt"])
def test_import_rejects_archive_traversal_without_creating_a_project(api, archive_name):
    client, _, _, _ = api
    before = client.get("/api/projects").json()
    archive = BytesIO()
    with ZipFile(archive, "w") as package:
        package.writestr(archive_name, "This archive entry must be rejected")
    response = client.post("/api/projects/import", files={"files": ("unsafe.zip", archive.getvalue(), "application/zip")})
    assert response.status_code == 422, response.text
    assert "unsafe" in response.json()["detail"].lower()
    assert client.get("/api/projects").json() == before


def test_export_is_pinned_to_old_revision(api):
    client, _, project, _ = api
    first = summary(client, project)
    assert edit(client, 1, {"quantity": "100"}).status_code == 200
    exported = client.post(f"/api/projects/{project}/exports", json={"revision": 1, "format": "json"})
    assert exported.status_code == 200, exported.text
    payload = client.get(exported.json()["url"]).json()
    assert payload["project"]["revision"] == 1
    assert payload["summary"]["totals"] == first["totals"]
    assert payload["positions"][0]["quantity"] == "5"
    assert payload["draft"] is True
    assert summary(client, project)["revision"] == 2


def test_undo_creates_reversing_revision_and_restores_price(api):
    client, _, project, _ = api
    before = summary(client, project)
    edited = edit(client, 1, {"quantity": "10"}).json()
    undone = client.post(f"/api/projects/{project}/undo/{edited['decision_id']}", json={
        "expected_revision": 2, "reason": "Restore prior confirmed quantity"})
    assert undone.status_code == 200, undone.text
    after = summary(client, project)
    assert after["revision"] == 3
    assert after["totals"] == before["totals"]
    assert after["history"][-1]["reverses_id"] == edited["decision_id"]
    duplicate = client.post(f"/api/projects/{project}/undo/{edited['decision_id']}", json={
        "expected_revision": 3, "reason": "Attempt repeated reversal"})
    assert duplicate.status_code == 409


def test_undo_position_reopens_adjustment_based_on_changed_scope(api):
    client, _, project, _ = api
    quantity_edit = edit(client, 1, {"quantity": "10"})
    assert quantity_edit.status_code == 200
    created = create_risk(client, project, revision=2)
    assert created.status_code == 201
    adjustment_id = created.json()["adjustment"]["id"]
    accepted = client.patch(f"/api/adjustments/{adjustment_id}", json={"expected_revision": 3,
        "reason": "Access scope confirmed for the revised quantity", "changes": {"review_state": "accepted"}})
    assert accepted.status_code == 200, accepted.text
    undone = client.post(f"/api/projects/{project}/undo/{quantity_edit.json()['decision_id']}", json={
        "expected_revision": 4, "reason": "Quantity reverted so scope assumptions need another decision"})
    assert undone.status_code == 200, undone.text
    after = summary(client, project)
    assert after["revision"] == 5
    assert after["adjustments"][0]["review_state"] == "pending"
    assert after["totals"]["risk_adjustments_chf"] == "0.00"


def test_rejected_position_prevents_review_completion(api):
    client, app, project, _ = api
    assert edit(client, 1, {"review_state": "rejected"}).status_code == 200
    assert app.state.service.review_blockers(project), "Rejected priced scope must not be treated as reviewed and approved"


def test_requirement_decision_blocks_until_accepted_and_can_be_undone(api):
    client, app, project, spans = api
    assert edit(client, 1, {"review_state": "accepted"}).status_code == 200
    requirement = Requirement(id="requirement-hygiene", title="Hygiene documentation",
        description="Confirm the required inspection evidence is included", source_page=1,
        source_span_ids=[spans[1].id])
    app.state.repo.update_project(project, lambda p: p["requirements"].append(requirement.model_dump()))
    assert app.state.service.review_blockers(project)
    endpoint = f"/api/projects/{project}/requirements/{requirement.id}"
    accepted = client.patch(endpoint, json={"expected_revision": 2,
        "reason": "Required evidence confirmed within project scope", "changes": {"review_state": "accepted"}})
    assert accepted.status_code == 200, accepted.text
    assert accepted.json()["revision"] == 3
    assert app.state.service.review_blockers(project) == []
    stale = client.patch(endpoint, json={"expected_revision": 2,
        "reason": "Attempt stale requirement decision", "changes": {"review_state": "rejected"}})
    assert stale.status_code == 409
    undone = client.post(f"/api/projects/{project}/undo/{accepted.json()['decision_id']}", json={
        "expected_revision": 3, "reason": "Reopen requirement pending supplier evidence"})
    assert undone.status_code == 200, undone.text
    after = summary(client, project)
    assert after["requirements"][0]["review_state"] == "pending"
    assert after["history"][-1]["reverses_id"] == accepted.json()["decision_id"]
    assert app.state.service.review_blockers(project)


def test_unsupported_parameter_mutation_does_not_create_revision(api):
    client, _, project, _ = api
    response = client.patch(f"/api/projects/{project}/assumptions", json={"expected_revision": 1,
        "reason": "Check invalid assumptions", "changes": {"productivity_factors": {"site_efficiency": "0"}}})
    assert response.status_code == 422
    assert summary(client, project)["revision"] == 1


def test_explicit_scope_exclusion_is_audited_and_reversible(api):
    client, _, project, spans = api
    before = summary(client, project)
    excluded = edit(client, 1, {"status": "out_of_scope"}, "Labelled recovery exercise: deliberately omit this known row")
    assert excluded.status_code == 200, excluded.text
    assert Decimal(excluded.json()["cost_delta_chf"]) < 0
    position = client.get(f"/api/projects/{project}/positions").json()["items"][0]
    assert position["status"] == "out_of_scope"
    assert position["cost"]["direct_cost_chf"] is None
    assert position["source_span_ids"] == [spans[0].id]
    undo = client.post(f"/api/projects/{project}/undo/{excluded.json()['decision_id']}", json={"expected_revision": 2, "reason": "Restore the original included scope after rehearsal"})
    assert undo.status_code == 200, undo.text
    assert summary(client, project)["totals"] == before["totals"]
