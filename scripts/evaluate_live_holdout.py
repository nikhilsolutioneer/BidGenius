"""Evaluate frozen source annotations against a completed persisted live run."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys
import time
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from tenderproof.evaluate import evaluate_rows
from tenderproof.models import ExtractionBatch, Position, SourceSpan


def get(path):
    with urllib.request.urlopen("http://127.0.0.1:8000/api" + path, timeout=60) as response:
        return json.load(response)


def main():
    live = json.loads((ROOT / "artifacts/live-ai-verification.json").read_text(encoding="utf-8"))
    project = sys.argv[1] if len(sys.argv) > 1 else live["project_id"]
    fixture_path = ROOT / "tests/fixtures/readme_holdout.json"
    frozen = json.loads(fixture_path.read_text(encoding="utf-8"))
    summary = get(f"/projects/{project}/summary")
    positions = [Position.model_validate(p) for p in get(f"/projects/{project}/positions")["items"]]
    document_id = positions[0].document_id
    spans = []
    for page in sorted({r["page"] for r in frozen["rows"]}):
        payload = get(f"/documents/{document_id}/pages/{page}/spans")
        records = payload if isinstance(payload, list) else payload.get("spans", payload.get("items", []))
        spans.extend(SourceSpan.model_validate(s) for s in records)
    result = evaluate_rows(frozen["rows"], positions, spans, "Frozen 83 source rows: quantity/unit and detection only")
    # A missing expected product denotes no product annotation, not a no-match label.
    for key in ("catalogue_reference", "complete_row", "matched_reference_rows", "expected_unmatched_rows"):
        result.pop(key, None)
    for row in result["results"]:
        row.pop("catalogue_reference_correct", None)
        row.pop("all_correct", None)
    fresh = [r for r in result["results"] if int(r["id"][1:]) <= 81]
    result["previously_unseen_81"] = {"rows": len(fresh), "detected": sum(r["detected"] for r in fresh),
        "quantity_unit_correct": sum(r["quantity_and_unit_correct"] for r in fresh)}
    started = time.monotonic()
    cache_paths = list((ROOT / "data/projects" / project / "cache").glob("*.json"))
    for path in cache_paths:
        ExtractionBatch.model_validate_json(path.read_text(encoding="utf-8"))
    artifact = {"evaluated_at": datetime.now(timezone.utc).isoformat(), "project_id": project,
        "revision": summary["revision"], "frozen_fixture_sha256": hashlib.sha256(fixture_path.read_bytes()).hexdigest(),
        "fixture_provenance": {k: v for k, v in frozen.items() if k != "rows"},
        "holdout": result, "cache_files_validated": len(cache_paths),
        "cache_deserialization_seconds": round(time.monotonic()-started, 4),
        "cache_measurement_scope": "Local validated batch deserialization only; excludes UI and workflow rerun time"}
    target = ROOT / "artifacts/live-holdout-evaluation.json"
    target.write_text(json.dumps(artifact, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({k: v for k, v in result.items() if k != "results"}, indent=2))


if __name__ == "__main__":
    main()
