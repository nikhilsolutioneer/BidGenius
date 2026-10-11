"""Real-provider verification; writes only non-secret metrics and isolated demo data."""
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
import time
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from tenderproof.config import model_name
from openai import OpenAI
from pydantic import BaseModel, ConfigDict

ARTIFACT = ROOT / "artifacts" / "live-ai-verification.json"
report = (json.loads(ARTIFACT.read_text(encoding="utf-8")) if "--resume" in sys.argv else
          {"started_at": datetime.now(timezone.utc).isoformat(), "model": model_name(), "phase": "smoke"})


def save():
    ARTIFACT.write_text(json.dumps(report, indent=2), encoding="utf-8")


def request(path, data=None):
    body = json.dumps(data).encode() if data is not None else None
    req = urllib.request.Request("http://127.0.0.1:8000/api" + path, data=body,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=120) as response:
        return json.load(response)


class Smoke(BaseModel):
    model_config = ConfigDict(extra="forbid")
    source_id: str
    quantity: str
    unit: str


def main():
    if "--resume" in sys.argv:
        report["restarted_at"] = datetime.now(timezone.utc).isoformat()
        project, run_id = report["project_id"], report["run_id"]
        before = request("/runs/" + run_id)
        # Earlier adapter saved a completed response to cache before cancellation
        # without adding its usage to the run. Disclose that measurable difference.
        totals = {name: 0 for name in ("input_tokens", "output_tokens", "total_tokens")}
        for cache in (ROOT / "data/projects" / project / "cache").glob("*.json"):
            values = json.loads(cache.read_text(encoding="utf-8")).get("usage", {})
            for name in totals:
                totals[name] += values.get(name, 0)
        report["pre_restart_known_usage_not_in_run_counter"] = {
            name: max(0, value - before.get("usage", {}).get(name, 0)) for name, value in totals.items()}
        report["adapter_restart_note"] = "First persisted batches used the earlier adapter; resumed batches use final approval-gated refinements. No prices were approved by the model."
        report["restart_preserved_pages"] = before["pages_processed"]
        report["restart_preserved_batches"] = before["batches_done"]
        summary = request(f"/projects/{project}/summary")
        request("/runs/" + run_id + "/resume", {"expected_revision": summary["revision"],
            "reason": "Verify restart resumes durable checkpoint with final adapter", "action": "continue"})
        report.update(phase="full_tender", restart_resume_requested=True)
        save()
        return monitor(project, run_id, cancellation_done=True)
    started = time.monotonic()
    response = OpenAI(timeout=45, max_retries=1).responses.parse(
        model=model_name(), store=False, max_output_tokens=1000, text_format=Smoke,
        input=[{"role": "system", "content": "Extract quantity and normalized unit from this synthetic connectivity fixture. Stk means pc. Return the source ID exactly."},
               {"role": "user", "content": "source_id=connectivity-fixture; Zuluftventil DN100, Menge 5 Stk."}])
    parsed = response.output_parsed
    assert parsed and parsed.source_id == "connectivity-fixture" and parsed.quantity == "5" and parsed.unit == "pc"
    report["smoke"] = {"passed": True, "duration_seconds": round(time.monotonic()-started, 3),
                       "usage": response.usage.model_dump() if response.usage else None,
                       "fixture": "Synthetic connectivity fixture; no project data used in this check"}
    save()
    created = request("/projects/demo", {"use_ai": True})
    project, run_id = created["project_id"], created["run_id"]
    report.update(project_id=project, run_id=run_id, phase="full_tender")
    save()
    monitor(project, run_id, cancellation_done=False)


def monitor(project, run_id, cancellation_done):
    deadline = time.monotonic() + 7200
    while time.monotonic() < deadline:
        run = request("/runs/" + run_id)
        report["run"] = run
        save()
        if not cancellation_done and run["batches_done"] >= 1 and run["status"] == "running":
            request("/runs/" + run_id + "/cancel", {})
            cancellation_done = True
            report["cancellation_requested_at_pages"] = run["pages_processed"]
        if run["status"] == "cancelled":
            summary = request(f"/projects/{project}/summary")
            report["cancelled_at_pages"] = run["pages_processed"]
            request("/runs/" + run_id + "/resume", {"expected_revision": summary["revision"],
                "reason": "Verify live extraction resumes after safe cancellation", "action": "continue"})
            report["resume_requested"] = True
        elif run["status"] in {"awaiting_review", "complete", "failed"}:
            break
        time.sleep(3)
    summary = request(f"/projects/{project}/summary")
    report["coverage"] = summary["coverage"]
    report["page_outcome_count"] = len(summary["page_outcomes"])
    report["revision"] = summary["revision"]
    report["phase"] = "completed" if report["run"]["status"] in {"awaiting_review", "complete"} else "incomplete"
    report["finished_at"] = datetime.now(timezone.utc).isoformat()
    save()
    print(json.dumps({k: report.get(k) for k in ("project_id", "run_id", "phase", "coverage")}, indent=2))


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        report.update(phase="verification_failed", error_type=type(exc).__name__)
        save()
        print("Live verification failed: " + type(exc).__name__ + "; no credential or provider response printed.")
        raise SystemExit(1)
