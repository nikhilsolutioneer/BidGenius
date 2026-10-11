"""Commercial evidence regressions. CSV data here are isolated test fixtures, not demo history."""
from decimal import Decimal
from io import BytesIO
import json
from zipfile import ZipFile

from test_api import api, summary


CSV = "record_id,project_name,currency,bid_amount,outcome,estimated_baseline\na,Test won,CHF,1100,won,1000\nb,Test lost,CHF,1200,lost,1000\nc,Test unknown,CHF,1300,unknown,1000\nd,Foreign record,EUR,900,won,1000\n"


def import_rows(client, project, revision=1, text=CSV):
    return client.post(f"/api/projects/{project}/historical/import", json={
        "expected_revision": revision, "reason": "Import isolated estimator test records", "filename": "history.csv", "csv_text": text})


def context_patch(client, project, revision, changes):
    return client.patch(f"/api/projects/{project}/commercial-context", json={
        "expected_revision": revision, "reason": "Review commercial assumptions", "changes": changes})


def test_import_preview_provenance_duplicates_and_stale_revision(api):
    client, app, project, _ = api
    endpoint = f"/api/projects/{project}/historical/preview"
    preview = client.post(endpoint, json={"filename": "history.csv", "csv_text": CSV}).json()
    assert preview["can_import"] and preview["valid_count"] == 4
    assert summary(client, project)["revision"] == 1
    imported = import_rows(client, project)
    assert imported.status_code == 201, imported.text
    assert import_rows(client, project).status_code == 409
    repeated = client.post(endpoint, json={"filename": "history.csv", "csv_text": CSV}).json()
    assert len(repeated["duplicates"]) == 4 and not repeated["can_import"]
    conflict = client.post(endpoint, json={"filename": "history.csv", "csv_text": CSV.replace("1100", "1101")}).json()
    assert conflict["errors"] and not conflict["can_import"]
    current = client.get(f"/api/projects/{project}/commercial-context").json()
    assert current["records"][0]["source_sha256"] == preview["sha256"]
    assert current["imports"][0]["csv_text"] == CSV
    assert app.state.repo.revision(project, 1).get("commercial_state") is None


def test_history_requires_explicit_adoption_and_excludes_unknown_and_non_chf(api):
    client, _, project, _ = api
    before = summary(client, project)["scenarios"]
    assert import_rows(client, project).status_code == 201
    selected = {"selected_record_ids": ["a", "b", "c", "d"]}
    assert context_patch(client, project, 2, selected).status_code == 200
    selected_view = client.get(f"/api/projects/{project}/commercial-context").json()
    assert selected_view["statistics"] == {"selected_count": 4, "eligible_count": 3, "wins": 1, "losses": 1,
        "unknown": 1, "observed_win_rate": "0.5", "median_bid_to_baseline_ratio": "1.2", "ratio_sample_size": 3, "outcome_sample_size": 2}
    assert selected_view["scenarios"]["scenarios"] == before["scenarios"]
    invalid = context_patch(client, project, 3, {"adopt_observed_win_rate": True})
    assert invalid.status_code == 422
    adopted = context_patch(client, project, 3, {"adopt_observed_win_rate": True, "adopt_reference_ratio": True,
        "adoption_rationale": "Estimator confirms comparable scope despite small sample"})
    assert adopted.status_code == 200, adopted.text
    result = summary(client, project)
    assert result["scenarios"]["assumptions"]["reference_win_probability"] == "0.5"
    assert result["scenarios"]["assumptions"]["reference_price_multiplier"] == "1.2"
    assert len(result["scenarios"]["commercial_evidence"]["context"]["comparable_snapshot"]) == 4
    assert result["scenarios"]["scenarios"] != before["scenarios"]


def test_capacity_preserves_probability_and_requires_period(api):
    client, app, project, _ = api
    before = summary(client, project)["scenarios"]["scenarios"]
    bad = context_patch(client, project, 1, {"capacity": {"available_hours": "1", "committed_hours": "0"}})
    assert bad.status_code == 422
    updated = context_patch(client, project, 1, {"capacity": {"period_start": "2026-10-01", "period_end": "2026-10-31", "available_hours": "1", "committed_hours": "0.5"}})
    assert updated.status_code == 200, updated.text
    view = client.get(f"/api/projects/{project}/commercial-context").json()
    assert view["capacity"]["remaining_hours"] == "0.5"
    assert Decimal(view["capacity"]["shortfall_hours"]) > 0
    assert view["scenarios"]["scenarios"] == before
    app.state.repo.update_project(project, lambda p: p["positions"][0].update(cost=None))
    view = client.get(f"/api/projects/{project}/commercial-context").json()
    assert view["capacity"]["labour_incomplete"] and view["capacity"]["unknown_labour_positions"] == 1


def test_saved_scenarios_match_revision_export_and_undo(api):
    client, app, project, _ = api
    before = summary(client, project)["scenarios"]
    overrides = {"scenario_margins_pct": {"Aggressive": "3", "Target": "7", "Conservative": "9"}, "competition_adjustment": "-.1"}
    preview = client.post(f"/api/projects/{project}/scenarios", json={"overrides": overrides}).json()
    assert preview["preview"] and summary(client, project)["revision"] == 1
    saved = client.post(f"/api/projects/{project}/scenarios/save", json={"expected_revision": 1, "reason": "Save reviewed scenario assumptions", "overrides": overrides})
    assert saved.status_code == 200, saved.text
    current = summary(client, project)
    assert current["scenarios"]["scenarios"] == preview["scenarios"]
    assert app.state.repo.revision(project, 1)["estimate"]["scenarios"] == before
    response = client.post(f"/api/projects/{project}/exports", json={"revision": 2, "format": "zip"})
    assert response.status_code == 200
    archive = ZipFile(BytesIO(client.get(response.json()["url"]).content))
    payload = json.loads(archive.read(next(n for n in archive.namelist() if n.endswith("_json.json"))))
    scenario_export = json.loads(archive.read("TenderProof_R2_Szenarien.json"))
    assert scenario_export == payload["summary"]["scenarios"] == current["scenarios"]
    assert payload["positions"][0]["lv_id"] == payload["positions"][0]["id"]
    assert "lv_id" in archive.read(next(n for n in archive.namelist() if n.endswith("_csv.csv"))).decode("utf-8")
    undone = client.post(f"/api/projects/{project}/undo/{saved.json()['decision_id']}", json={"expected_revision": 2, "reason": "Restore previous scenario assumptions"})
    assert undone.status_code == 200, undone.text
    assert summary(client, project)["scenarios"] == before


def test_scenario_reference_context_compares_preview_and_saved_margin_to_package_defaults(api):
    client, _, project, _ = api
    initial = summary(client, project)
    reference = initial["scenario_reference"]
    assert reference["defaults_available"] is True
    assert reference["source"] == "project_parameters.json"
    assert reference["reference_margin_pct"] == "5.5"
    assert reference["default_reference_margin_pct"] == "5.5"
    assert reference["reference_margin_differs_from_default"] is False

    preview = client.post(f"/api/projects/{project}/scenarios", json={
        "revision": 1, "overrides": {"reference_margin_pct": "10"}})
    assert preview.status_code == 200, preview.text
    preview_reference = preview.json()["reference_context"]
    assert preview_reference["reference_margin_pct"] == "10"
    assert preview_reference["default_reference_margin_pct"] == "5.5"
    assert preview_reference["reference_margin_differs_from_default"] is True
    assert preview_reference["reference_price_differs_from_default"] is True
    assert summary(client, project)["revision"] == 1

    saved = client.post(f"/api/projects/{project}/scenarios/save", json={
        "expected_revision": 1, "reason": "Review reference margin against package default",
        "overrides": {"reference_margin_pct": "10"}})
    assert saved.status_code == 200, saved.text
    after = summary(client, project)
    assert after["revision"] == 2
    assert after["scenario_reference"] == preview_reference


def test_history_validation_blocks_malformed_values_and_unknown_records(api):
    client, _, project, _ = api
    endpoint = f"/api/projects/{project}/historical/preview"
    for text in (CSV.replace("1100", "NaN"), CSV.replace("1100", "-1"), CSV.replace("won", "possibly"), CSV.replace("record_id,", "wrong,")):
        result = client.post(endpoint, json={"filename": "history.csv", "csv_text": text})
        assert result.status_code == 200
        assert result.json()["errors"] and not result.json()["can_import"]
    assert context_patch(client, project, 1, {"selected_record_ids": ["missing"]}).status_code == 422
    assert context_patch(client, project, 1, {"scenario_overrides": {"reference_price_multiplier": "9"}}).status_code == 422
    assert context_patch(client, project, 1, {"capacity": {"period_start": "2026-10-31", "period_end": "2026-10-01"}}).status_code == 422
