"""Import a fresh, clean Oberglatt demo and pin it as the default project."""
import argparse
from datetime import datetime, timezone
from decimal import Decimal
import json
from pathlib import Path
import sys
import time

import httpx

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))


def scenario_reference(summary):
    existing = summary.get("scenario_reference") or summary["scenarios"].get("reference_context")
    if existing is not None:
        return existing
    # Support a server process started before the reference-context API was added.
    from tenderproof.pricing import calculate_scenarios

    source_parameters = json.loads((ROOT / "Schulhaus_Oberglatt_Hackathon_Starter_Package_v2" / "project_parameters.json").read_text(encoding="utf-8"))
    baseline = summary["totals"].get("unrounded_cost_baseline_chf", summary["totals"]["cost_baseline_chf"])
    defaults = calculate_scenarios(baseline, source_parameters)["assumptions"]
    active = summary["scenarios"]["assumptions"]
    active_margin, default_margin = active["reference_margin_pct"], defaults["reference_margin_pct"]
    active_price, default_price = active["reference_price_chf"], defaults["reference_price_chf"]
    return {
        "defaults_available": True,
        "source": "project_parameters.json",
        "reference_price_chf": active_price,
        "reference_margin_pct": active_margin,
        "default_reference_price_chf": default_price,
        "default_reference_margin_pct": default_margin,
        "reference_price_differs_from_default": Decimal(active_price) != Decimal(default_price),
        "reference_margin_differs_from_default": Decimal(active_margin) != Decimal(default_margin),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    args = parser.parse_args()
    started = time.perf_counter()
    with httpx.Client(base_url=args.base_url, timeout=60) as client:
        def request(method, path, **kwargs):
            response = client.request(method, "/api" + path, **kwargs)
            response.raise_for_status()
            return response.json()

        created = request("POST", "/projects/demo", json={"use_ai": False})
        project, run_id = created["project_id"], created["run_id"]
        print(f"Preparing fresh local demo project: {project}", flush=True)
        deadline = time.monotonic() + 1200
        while time.monotonic() < deadline:
            run = request("GET", f"/runs/{run_id}")
            if run["status"] not in ("running", "queued"):
                break
            time.sleep(.5)
        if run["status"] != "awaiting_review":
            raise RuntimeError(f"Preparation did not reach review: {run['status']}; {run['errors']}")

        summary = request("GET", f"/projects/{project}/summary")
        commercial = request("GET", f"/projects/{project}/commercial-context")
        if summary["coverage"]["pages_processed"] != 202:
            raise RuntimeError(f"Expected 202 processed pages; got {summary['coverage']['pages_processed']}.")
        context = commercial["context"]
        if (commercial["records"] or commercial["imports"] or context["selected_record_ids"]
                or context["adopt_observed_win_rate"] or context["adopt_reference_ratio"]
                or context["scenario_overrides"]):
            raise RuntimeError("The new demo project does not have a clean default commercial context.")
        if summary["history"]:
            raise RuntimeError("The new demo project unexpectedly has estimator decision history.")
        reference_context = scenario_reference(summary)
        if not reference_context["defaults_available"]:
            raise RuntimeError("Could not read project_parameters.json defaults for the scenario model.")
        if reference_context["reference_margin_differs_from_default"]:
            raise RuntimeError("Fresh demo scenario margin differs from project_parameters.json defaults.")

        exported = request("POST", f"/projects/{project}/exports", json={
            "revision": summary["revision"], "format": "zip"})
        prepared_at = datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
        report = {
            "prepared_at": prepared_at,
            "demo_label": f"Prepared demo | {prepared_at}",
            "base_url": args.base_url,
            "project_id": project,
            "project_name": summary["name"],
            "run_id": run_id,
            "revision": summary["revision"],
            "mode": "Fresh local parser import; no model call or simulated progress",
            "clean_project": True,
            "source_sha256": summary["document"]["sha256"],
            "processing_seconds": round(time.perf_counter() - started, 3),
            "coverage": summary["coverage"],
            "totals": {
                "material_cost_chf": summary["totals"]["material_cost_chf"],
                "labour_cost_chf": summary["totals"]["labour_cost_chf"],
                "installation_hours": summary["totals"]["installation_hours"],
                "cost_baseline_chf": summary["totals"]["cost_baseline_chf"],
                "selling_price_chf": summary["totals"]["selling_price_chf"],
            },
            "commercial_context": context,
            "scenario_reference": reference_context,
            "run_errors": run["errors"],
            "export": exported,
        }
        path = ROOT / "artifacts" / "prepared-demo.json"
        path.parent.mkdir(exist_ok=True)
        temporary = path.with_suffix(".json.tmp")
        temporary.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        temporary.replace(path)
        print(json.dumps(report, ensure_ascii=True, indent=2), flush=True)


if __name__ == "__main__":
    main()
